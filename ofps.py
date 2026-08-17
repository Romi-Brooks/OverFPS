#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OverFPS —— 视频补帧 / 超分 统一入口
====================================
用法 (任选):
  python ofps.py                       交互式菜单 (选择显卡/插帧/超分/视频)
  python ofps.py "视频.mp4"            直接播放 (等效 play, 自动选独显)
  python ofps.py play "视频.mp4" [选项] 补帧/超分播放
  python ofps.py gpu                   列出显卡 (DXGI 索引|名称|显存)
  python ofps.py render "输入" [输出] [选项]   离线渲染: 补帧
  python ofps.py render-sr "输入" [输出] [选项] 离线渲染: 补帧+RealESRGAN超分

play / render 选项:
  --model v4_22_lite     RIFE 模型 (v4_26_heavy/v4_26/v4_22_lite/v4_17_lite/v4_15_lite/v4_6)
  --scale 1.0            光流分辨率比例 (v4_6 可用 0.5 加速)
  --sr none|anime4k|realesrgan|cugan|waifu2x   超分引擎 (默认 none)
  --sr-model 2           realesrgan: xsx2/xsx4/v3 ; cugan/waifu2x: 2/3/4 (倍率)
  --gpu auto|0|1|2       DML 设备号 (默认 auto = 自动选独显)
  --no-interp            关闭插帧 (仅超分)
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------- 路径 (venv / 便携目录) ----------------
ROOT = os.path.dirname(os.path.abspath(__file__))          # OverFPS 根目录
APP = os.path.join(ROOT, "realtime-interp")
SCRIPTS = os.path.join(APP, "scripts")
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
VS_PATH = os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth")
VSPIPE = os.path.join(VS_PATH, "vspipe.exe")
MPV = os.path.join(APP, "mpv", "mpv.exe")
FFMPEG = os.path.join(APP, "ffmpeg", "ffmpeg.exe")
CONFIG = os.path.join(ROOT, "config.json")
SHADER_RESTORE = os.path.join(APP, "shaders", "Anime4K_Restore_CNN_Soft_VL.glsl")
SHADER_UPSCALE = os.path.join(APP, "shaders", "Anime4K_Upscale_CNN_x2_M.glsl")

DEFAULT_CONFIG = {
    "model": "v4_22_lite",
    "scale": "1.0",
    "sr": "none",
    "sr_model": "2",
    "gpu": "auto",
    "fp16": "1",
    "buffered": "8",      # mpv vapoursynth 缓冲帧数 (越大越顺滑, 延迟越高)
    "concurrent": "4",    # 并发请求帧数 (越大吞吐越高, 延迟越高)
    "osd": "1",           # 左上角 FPS/延迟 OSD (1开/0关; 播放中 Ctrl+d 切换)
    "auto_res": "1",      # 分辨率感知: 1080p 自动切 v4_6+半分辨率光流 (否则会严重卡顿)
}


def ensure_venv():
    """若未用 venv 解释器运行, 自动切换到 venv 重新执行 (subprocess 在 Windows 下正确加引号)"""
    if sys.platform == "win32" and os.path.exists(VENV_PY):
        here = os.path.realpath(sys.executable).lower()
        target = os.path.realpath(VENV_PY).lower()
        if here != target and "python" in here:
            rc = subprocess.run([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:]).returncode
            sys.exit(rc)


# ---------------- GPU 探测 (ctypes + DXGI, 自动定位 vtable 槽位) ----------------
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

IID_IDXGIFactory1 = GUID(0x770aae78, 0xF26F, 0x4DBA, (0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))


class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [
        ("VendorId", wt.DWORD),
        ("DeviceId", wt.DWORD),
        ("SubSysId", wt.DWORD),
        ("Revision", wt.DWORD),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("Description", ctypes.c_wchar * 128),
    ]


HRESULT = ctypes.c_long
ENUM_ADAPTERS = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.POINTER(ctypes.c_void_p))
GET_RAW = ctypes.CFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p)
RELEASE = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)

DXGI_ERROR_NOT_FOUND = 0x887A0002


def _plausible_name(s):
    return sum(1 for c in s if c.isalnum()) >= 4


def _read_desc_raw(adapter, avtbl):
    """扫描槽位读取适配器描述; 兼容两种布局(名称在偏移0或偏移40), 返回 (name, vram_mb) 或 None"""
    for slot in range(7, 15):
        buf = (ctypes.c_ubyte * 512)()
        get = ctypes.cast(avtbl[slot], GET_RAW)
        if get(adapter, ctypes.byref(buf)) != 0:
            continue
        s0 = bytes(buf[0:256]).decode("utf-16-le", errors="replace").rstrip("\x00")
        s40 = bytes(buf[40:296]).decode("utf-16-le", errors="replace").rstrip("\x00")
        if _plausible_name(s0):
            name = s0
            vram = int.from_bytes(bytes(buf[256:264]), "little")
        elif _plausible_name(s40):
            name = s40
            vram = int.from_bytes(bytes(buf[16:24]), "little")
        else:
            continue
        if vram > 512 * 1024:  # 显存 sanity (>512GB 视为解析错误)
            vram = 0
        return name, vram
    return None


def _find_enum_slot(factory, vtbl):
    """扫描 vtable 找出"枚举适配器"方法 (不同 DXGI 版本槽位可能不同)"""
    for slot in range(7, 24):
        fn = ctypes.cast(vtbl[slot], ENUM_ADAPTERS)
        a = ctypes.c_void_p()
        if fn(factory, 0, ctypes.byref(a)) == 0 and a.value:
            b = ctypes.c_void_p()
            hr1 = fn(factory, 1, ctypes.byref(b))
            if hr1 == 0 or hr1 == DXGI_ERROR_NOT_FOUND:
                return slot, fn
    return None, None


def list_gpus():
    """返回 [(index, name, vram_mb), ...] 按 DXGI 顺序 (= DML device 顺序)"""
    dxgi = ctypes.windll.dxgi
    create = dxgi.CreateDXGIFactory1
    create.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    create.restype = HRESULT
    factory = ctypes.c_void_p()
    hr = create(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(factory))
    if hr != 0:
        raise RuntimeError("CreateDXGIFactory1 failed: 0x%08X" % (hr & 0xFFFFFFFF))
    obj = ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))
    vtbl = ctypes.cast(obj.contents.value, ctypes.POINTER(ctypes.c_void_p))
    enum_slot, enum_adapters = _find_enum_slot(factory, vtbl)
    if enum_slot is None:
        raise RuntimeError("cannot locate DXGI enum method")
    release_factory = ctypes.cast(vtbl[2], RELEASE)
    gpus = []
    i = 0
    try:
        while True:
            adapter = ctypes.c_void_p()
            hr = enum_adapters(factory, i, ctypes.byref(adapter))
            if hr != 0:
                break
            aobj = ctypes.cast(adapter, ctypes.POINTER(ctypes.c_void_p))
            avtbl = ctypes.cast(aobj.contents.value, ctypes.POINTER(ctypes.c_void_p))
            release_adapter = ctypes.cast(avtbl[2], RELEASE)
            info = _read_desc_raw(adapter, avtbl)
            if info is not None:
                gpus.append((i, info[0], info[1]))
            release_adapter(adapter)
            i += 1
    finally:
        release_factory(factory)
    return gpus


def pick_gpu(gpus, pref="auto"):
    """auto: 优先独显 (NVIDIA/AMD/GeForce/RTX/Radeon), 否则最大显存"""
    if pref and str(pref).lower() != "auto":
        return int(pref)
    for idx, name, vram in gpus:
        n = name.lower()
        if any(k in n for k in ("nvidia", "amd", "radeon", "geforce", "rtx")):
            return idx
    if gpus:
        return max(gpus, key=lambda g: g[2])[0]
    return 0


# ---------------- 配置 ----------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def make_env(interp, model, scale, sr, sr_model, gpu, fp16="1"):
    env = os.environ.copy()
    env["PATH"] = VS_PATH + ";" + env.get("PATH", "")
    env["VS_INTERP"] = "1" if interp else "0"
    env["VS_MODEL"] = model
    env["VS_SCALE"] = str(scale)
    env["VS_SR"] = sr if sr in ("realesrgan", "cugan", "waifu2x") else "none"
    env["VS_SR_MODEL"] = str(sr_model)
    env["VS_GPU"] = str(gpu)
    env["VS_FP16"] = str(fp16)
    # OSD / 快捷键脚本 (lua) 读取的展示信息
    env["OFPS_INTERP"] = "1" if interp else "0"
    env["OFPS_MODEL"] = model
    env["OFPS_SR"] = sr
    env["OFPS_SR_MODEL"] = str(sr_model)
    env["OFPS_SHADER_UPSCALE"] = SHADER_UPSCALE
    env["OFPS_ROOT"] = ROOT
    return env


def build_mpv_cmd(video, interp, model, scale, sr, sr_model, gpu, fp16,
                  buffered=8, concurrent=4, osd="1"):
    env = make_env(interp, model, scale, sr, sr_model, gpu, fp16)
    env["OFPS_BUFFERED"] = str(buffered)
    env["OFPS_CONCURRENT"] = str(concurrent)
    env["OFPS_OSD"] = str(osd)
    vf = "vapoursynth=file=play.vpy:buffered-frames=%d:concurrent-frames=%d" % (buffered, concurrent)
    cmd = [MPV, video, "--vf=%s" % vf, "--cache=yes", "--keep-open=yes"]
    if sr == "anime4k":
        cmd += ["--glsl-shaders=%s" % SHADER_RESTORE,
                "--glsl-shaders=%s" % SHADER_UPSCALE]
    extra = os.environ.get("OFPS_MPV_EXTRA")
    if extra:
        cmd += shlex.split(extra)
    return cmd, env


def probe_res(video):
    """用 ffmpeg -i 探测视频分辨率 (快速, 返回 (w, h) 或 None)"""
    try:
        p = subprocess.run([FFMPEG, "-i", video], stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
        for line in p.stderr.decode("utf-8", "replace").splitlines():
            m = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", line)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def apply_auto_res(cfg, video, interp, model, scale, can_switch=True):
    """分辨率感知: 1080p 全质量 RIFE 无法实时 (~21fps, 丢帧65%),
    自动切换 v4_6 + 半分辨率光流 (实测 0 丢帧)。can_switch=False 时只警告不切换
    (用户显式指定了模型/超分时尊重其选择)"""
    if not interp or str(cfg.get("auto_res", "1")) != "1":
        return model, scale
    res = probe_res(video)
    if not res:
        return model, scale
    w, h = res
    if h >= 2160:
        print("注意: %dx%d (4K) 补帧超出本机实时能力, 建议 --no-interp 或离线渲染" % (w, h))
    elif h >= 1080 and model != "v4_6":
        if can_switch:
            print("检测到 %dx%d: 1080p 全质量 RIFE 无法实时 (~21fps 会严重卡顿)," % (w, h))
            print("自动切换 → v4_6 + 半分辨率光流 (实测 0 丢帧). config.json 的 auto_res=0 可关闭")
            return "v4_6", "0.5"
        else:
            print("注意: %dx%d (1080p) 当前模型无法实时 (~21fps 会严重卡顿), 建议 --model v4_6 --scale 0.5" % (w, h))
    elif h >= 1080 and model == "v4_6" and str(scale) != "0.5":
        # 已是 v4_6 但光流仍是全分辨率 (scale 1.0): 1080p 下依然无法实时
        if can_switch:
            print("检测到 %dx%d: v4_6 需配合半分辨率光流 (scale 0.5) 才能实时, 已自动调整" % (w, h))
            return model, "0.5"
        else:
            print("注意: %dx%d (1080p) v4_6 + scale 1.0 仍无法实时, 建议 --scale 0.5" % (w, h))
    return model, scale


def _resolve_gpu(gpu_pref, quiet=False):
    try:
        gpus = list_gpus()
    except Exception as e:
        print("GPU 探测失败: %s (使用默认设备 0)" % e)
        return 0, []
    gpu = pick_gpu(gpus, gpu_pref)
    if not quiet:
        name = gpus[gpu][1] if gpu < len(gpus) else "?"
        print("显卡: DXGI#%d %s" % (gpu, name))
    return gpu, gpus


# ---------------- 子命令 ----------------
def cmd_gpu(_args):
    gpus = list_gpus()
    for idx, name, vram in gpus:
        print("%d|%s|%dMB" % (idx, name, vram))
    if gpus:
        print("推荐(独显): %d" % pick_gpu(gpus, "auto"))


def cmd_play(args):
    cfg = load_config()
    model = args.model or cfg["model"]
    scale = args.scale or cfg["scale"]
    sr = args.sr or cfg["sr"]
    sr_model = args.sr_model or cfg["sr_model"]
    interp = not args.no_interp
    video = os.path.abspath(args.video)  # mpv cwd=SCRIPTS, 视频必须绝对路径
    if not os.path.exists(video):
        print("文件不存在: %s" % args.video)
        sys.exit(1)
    # 分辨率感知 (用户显式指定模型/超分时不自动切换, 仅警告)
    model, scale = apply_auto_res(cfg, video, interp, model, scale,
                                  can_switch=not (args.model or args.scale))
    gpu, _ = _resolve_gpu(args.gpu or cfg["gpu"])
    print("插帧: %s | 模型: %s | 超分: %s" % ("开" if interp else "关", model, sr))
    cmd, env = build_mpv_cmd(video, interp, model, scale, sr, sr_model, gpu,
                             cfg.get("fp16", "1"),
                             int(cfg.get("buffered", 8)), int(cfg.get("concurrent", 4)),
                             cfg.get("osd", "1"))
    if args.sub:
        sub_abs = os.path.abspath(args.sub)
        if not os.path.exists(sub_abs):
            print("字幕文件不存在: %s" % args.sub)
            sys.exit(1)
        cmd.insert(1, "--sub-file=%s" % sub_abs)
    if os.environ.get("OFPS_DEBUG"):
        print("CMD:", cmd)
    # stdin=DEVNULL: 键盘控制走播放窗口, 避免非交互环境下 mpv 卡在读终端输入
    subprocess.run(cmd, cwd=SCRIPTS, env=env, stdin=subprocess.DEVNULL)


def cmd_menu(_args):
    cfg = load_config()
    gpus = list_gpus()
    print("=== 检测到的显卡 ===")
    for idx, name, vram in gpus:
        print("  [%d] %s (%dMB)" % (idx, name, vram))
    print("  [auto] 自动选择独显 (推荐)")
    gpu = input("选择显卡 [auto]: ").strip() or "auto"

    print("\n=== 插帧 ===")
    print("  [1] RIFE 插帧 (默认)")
    print("  [0] 关闭插帧 (仅超分)")
    interp = input("选择 [1]: ").strip() != "0"

    model = cfg["model"]
    model_chosen = False
    if interp:
        print("\n=== 插帧模型 ===")
        models = ["v4_22_lite", "v4_26", "v4_26_heavy", "v4_17_lite", "v4_15_lite", "v4_6"]
        for i, m in enumerate(models):
            print("  [%d] %s%s" % (i, m, " (默认)" if m == cfg["model"] else ""))
        mi = input("选择模型 [默认]: ").strip()
        if mi.isdigit() and int(mi) < len(models):
            model = models[int(mi)]
            model_chosen = True

    print("\n=== 超分 ===")
    print("  [0] 关闭 (默认)")
    print("  [1] Anime4K (实时 shader, 几乎零开销)")
    print("  [2] RealESRGAN (高质量, 慢, 适合离线)")
    print("  [3] Real-CUGAN (动漫向)")
    print("  [4] waifu2x")
    si = input("选择超分 [0]: ").strip()
    sr = {"1": "anime4k", "2": "realesrgan", "3": "cugan", "4": "waifu2x"}.get(si, "none")

    print("\n=== 视频文件 ===")
    video = input("视频路径 (可拖入): ").strip().strip('"')
    if not video or not os.path.exists(video):
        print("文件不存在!")
        sys.exit(1)
    video = os.path.abspath(video)

    # 分辨率感知: 1080p 自动切 v4_6+半分辨率光流 (用户手选模型时只警告)
    scale = cfg["scale"]
    launch_model, launch_scale = apply_auto_res(cfg, video, interp, model, scale,
                                                can_switch=not model_chosen)

    # 只持久化用户显式选择 (自动切换仅本次启动生效, 不污染配置)
    cfg["model"] = model
    cfg["scale"] = scale
    cfg["sr"] = sr
    cfg["gpu"] = gpu
    save_config(cfg)

    gpu_idx = pick_gpu(gpus, gpu)

    # ---------------- 处理方式: 实时播放 还是 离线渲染 ----------------
    print("\n=== 处理方式 ===")
    print("  [1] 实时渲染 (播放, 即时看效果)")
    print("  [2] 离线渲染 (导出成片, 慢慢跑高质量, 可烧字幕)")
    mode = input("选择 [1]: ").strip()

    if mode == "2":
        # ---- 离线渲染: 沿用刚才选择的显卡/模型/超分 ----
        sr_off = sr
        if sr_off == "anime4k":
            print("注意: Anime4K 是实时渲染专用 shader, 离线渲染不可用")
            si = input("离线超分改用: [1] RealESRGAN [2] CUGAN [3] waifu2x [0] 无: ").strip()
            sr_off = {"1": "realesrgan", "2": "cugan", "3": "waifu2x"}.get(si, "none")
        out = input("输出文件 (回车自动命名): ").strip().strip('"') or None
        burn = input("烧录字幕 (回车跳过; 或输入 srt/ass 路径): ").strip().strip('"') or None
        if burn and not os.path.exists(burn):
            print("字幕文件不存在, 忽略: %s" % burn)
            burn = None

        class _R:
            pass
        a = _R()
        a.model, a.scale, a.sr = model, scale, sr_off
        a.sr_model = cfg["sr_model"]
        a.gpu = str(gpu_idx)
        a.no_interp = not interp
        a.frames = 0
        a.start = 0
        a.crf = a.preset = a.codec = None
        a.folder = None
        a.overwrite = False
        a.burn_sub = burn
        a.burn_size = None
        a.video = video
        a.output = out
        a.mode = "balanced"
        a.work_h = None
        # 离线画质模式
        print("\n=== 离线画质模式 ===")
        print("  [1] 极速  (降分辨率补帧再放大, 快 5-20 倍)")
        print("  [2] 均衡  (用当前选择的模型/超分, 默认)")
        print("  [3] 质量  (全分辨率 + 重模型, 细节最好, 慢)")
        mi = input("选择 [2]: ").strip()
        a.mode = {"1": "fast", "3": "quality"}.get(mi, "balanced")
        print()
        render_one(cfg, a, False, video, out, gpu_idx)
        return

    # ---- 实时播放: 沿用上面 apply_auto_res 的结果 (1080p/4K 已降级或警告) ----
    print("\n启动: 插帧=%s 模型=%s 超分=%s 显卡=#%d" % ("开" if interp else "关", launch_model, sr, gpu_idx))
    cmd, env = build_mpv_cmd(video, interp, launch_model, launch_scale, sr, cfg["sr_model"], gpu_idx,
                             cfg["fp16"], int(cfg.get("buffered", 8)), int(cfg.get("concurrent", 4)),
                             cfg.get("osd", "1"))
    subprocess.run(cmd, cwd=SCRIPTS, env=env, stdin=subprocess.DEVNULL)


def _fmt_eta(sec):
    sec = int(max(0, sec))
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def _default_output(video, args, with_sr):
    """按本次渲染参数生成默认输出路径 (与 render_one 同规则)"""
    interp = not args.no_interp
    sr = args.sr or ("realesrgan" if with_sr else "none")
    if interp and sr != "none":
        suffix = "_interp_sr.mkv"
    elif interp:
        suffix = "_interp.mkv"
    elif sr != "none":
        suffix = "_sr.mkv"
    else:
        suffix = "_copy.mkv"
    return os.path.splitext(video)[0] + suffix


def _burn_sub_copy(src):
    """拷贝字幕到 .runtime/burn_sub.<ext> 相对路径 (规避 ffmpeg subtitles 滤镜的 Windows 路径转义)"""
    ext = os.path.splitext(src)[1].lower() or ".srt"
    dst = os.path.join(ROOT, ".runtime", "burn_sub" + ext)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return os.path.relpath(dst, ROOT).replace("\\", "/")  # ffmpeg cwd=ROOT


def _probe_duration_fps(video):
    """ffmpeg -i 探测 (时长秒, 帧率); 失败返回 (0.0, 0.0)"""
    try:
        p = subprocess.run([FFMPEG, "-i", video], stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE)
        dur = fps = 0.0
        for line in p.stderr.decode("utf-8", "replace").splitlines():
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", line)
            if m and not dur:
                dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            m2 = re.search(r",\s*(\d+(?:\.\d+)?)\s*fps", line)
            if m2 and not fps:
                fps = float(m2.group(1))
        return dur, fps
    except Exception:
        return 0.0, 0.0


def _show_progress(vspipe_proc, ff_proc, label, total_out=0):
    """进度条: 数据来自 ffmpeg -progress pipe:1 (实时 flush, 管道下可靠)
    vspipe 的 --progress 在管道下是块缓冲的, 不用于实时显示。
    返回 (vspipe_exit, ffmpeg_exit)"""
    stop = threading.Event()
    cur = {"f": 0, "fps": 0.0}
    t0 = time.perf_counter()

    def _drain_vspipe():
        # 排空 vspipe stderr (防管道写满阻塞); 其缓冲的进度行直接丢弃
        try:
            for _ in vspipe_proc.stderr:
                pass
        except Exception:
            pass

    def _reader():
        # ffmpeg -progress 输出 key=value 块, 每 ~0.5s 一个
        for line in ff_proc.stdout:
            line = line.decode("utf-8", "replace").strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k == "frame":
                try:
                    cur["f"] = int(v)
                except ValueError:
                    pass
            elif k == "fps":
                try:
                    cur["fps"] = float(v)
                except ValueError:
                    pass

    def _show():
        last = -1
        while not stop.is_set():
            f = cur["f"]
            if f != last:
                el = time.perf_counter() - t0
                pct = f / total_out * 100.0 if total_out > 0 else 0.0
                eta = (total_out - f) / cur["fps"] if cur["fps"] > 0 and total_out > 0 else 0.0
                speed = cur["fps"] if cur["fps"] > 0 else (f / el if el > 0 else 0.0)
                if total_out > 0:
                    print("\r  %s %5.1f%%  %d/%d 帧  %.1ffps  剩余 %s    "
                          % (label, pct, f, total_out, speed, _fmt_eta(eta)),
                          end="", flush=True)
                else:
                    print("\r  %s %d 帧  %.1ffps  %s    "
                          % (label, f, speed, _fmt_eta(0)), end="", flush=True)
                last = f
            time.sleep(0.2)

    dt = threading.Thread(target=_drain_vspipe, daemon=True)
    rt = threading.Thread(target=_reader, daemon=True)
    st = threading.Thread(target=_show, daemon=True)
    dt.start()
    rt.start()
    st.start()
    vspipe_proc.wait()
    ff_proc.wait()
    stop.set()
    print()
    return vspipe_proc.returncode, ff_proc.returncode


RENDER_MODES = {
    "fast":     "极速: 降分辨率补帧再放大回 (快 5-20 倍, 细节略降)",
    "balanced": "均衡: 用当前选择的模型/超分直接跑",
    "quality":  "质量: 全分辨率 + v4_26_heavy (细节最好, 速度慢)",
}


def render_one(cfg, args, with_sr, video, output, gpu):
    """单文件离线渲染: vspipe(补帧/超分) + ffmpeg(编码/音频/烧录字幕), 带进度条"""
    model = args.model or cfg["model"]
    sr = args.sr or ("realesrgan" if with_sr else "none")
    interp = not args.no_interp
    mode = getattr(args, "mode", "balanced") or "balanced"
    work_h = getattr(args, "work_h", 0) or 0
    scale = cfg["scale"]
    fast_upscale = None
    # ---- 画质模式覆盖 (fast/quality 重写模型/光流比例/超分) ----
    if mode == "fast":
        model, scale, sr = "v4_6", "0.5", "none"
        res = probe_res(video)
        if res and res[1] > 1080:
            work_h = 1080
            fast_upscale = res  # 由 ffmpeg scale 放大回, 不占 vspipe
            print("极速模式: 降到 1080p 补帧 (v4_6+半光流), 输出放大回 %dx%d, 超分已忽略"
                  % (res[0], res[1]))
        else:
            print("极速模式: v4_6 + 半分辨率光流 (超分已忽略)")
    elif mode == "quality":
        work_h = 0
        res_q = probe_res(video)
        if res_q and res_q[1] >= 2160:
            # v4_26_heavy + 4K 全分辨率超出 8GB 显存 (实测 OOM), 降级到 v4_26
            print("质量模式: 4K 源下 v4_26_heavy 超出显存, 改用 v4_26 + 全分辨率光流")
            model, scale = "v4_26", "1.0"
        else:
            if model != "v4_26_heavy":
                print("质量模式: 改用 v4_26_heavy + 全分辨率光流 (细节最好, 速度慢)")
            model, scale = "v4_26_heavy", "1.0"
    if not os.path.exists(video):
        print("文件不存在: %s" % video)
        return False
    output = os.path.abspath(output or _default_output(video, args, with_sr))
    frames = args.frames or 0
    print("插帧: %s | 模型: %s | 超分: %s | 帧数: %s" %
          ("开" if interp else "关", model, sr, frames or "全部"))
    print("渲染中... 输出: %s" % output)
    # 估算输出总帧数 (进度条用; 探测源时长/帧率)
    dur, src_fps = _probe_duration_fps(video)
    mult = 2 if interp else 1
    if frames:
        total_out = frames * mult
    elif src_fps > 0 and dur > 0:
        total_out = int(max(0.0, dur - (args.start or 0)) * src_fps * mult)
    else:
        total_out = 0
    env = make_env(interp, model, scale, sr, cfg["sr_model"], gpu, cfg["fp16"])
    env["VS_FRAMES"] = str(frames)
    env["VS_INPUT"] = video
    env["VS_START"] = str(args.start or 0)
    env["VS_WORK_H"] = str(work_h)
    if fast_upscale:
        env["VS_UPSCALE_OUT"] = "0"  # 放大交给 ffmpeg scale, 减少 vspipe 侧 4K 处理
    script = os.path.join(SCRIPTS, "render.vpy")
    vspipe = subprocess.Popen([VSPIPE, "-p", "-c", "y4m", script, "-"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, cwd=SCRIPTS)
    # ffmpeg 侧视频滤镜链: 极速模式放大回原分辨率 + 字幕烧录
    vf_chain = []
    if fast_upscale:
        vf_chain.append("scale=%d:%d" % (fast_upscale[0], fast_upscale[1]))
    if args.burn_sub:
        if not os.path.exists(args.burn_sub):
            print("字幕文件不存在: %s" % args.burn_sub)
            vspipe.kill()
            return False
        burn = _burn_sub_copy(args.burn_sub)
        vf_chain.append("subtitles=%s:force_style='FontName=Microsoft YaHei,FontSize=%d'"
                        % (burn, args.burn_size or 22))
    # 视频来自 vspipe (y4m), 音频从原文件按起始位置截取并转 AAC (通用兼容)
    # -ss 作用于第二个输入 (原视频), -shortest 保证部分渲染时音频与视频同长
    preset = args.preset or ("faster" if mode == "fast" else "medium")
    ff_cmd = [FFMPEG, "-y", "-i", "-",
              "-ss", str(args.start or 0), "-i", video,
              "-map", "0:v", "-map", "1:a?",
              "-c:v", args.codec or "libx264",
              "-preset", preset,
              "-crf", str(args.crf or 18),
              "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "192k"]
    if vf_chain:
        ff_cmd += ["-vf", ",".join(vf_chain)]
    ff_cmd += ["-progress", "pipe:1", "-shortest", output]
    ff = subprocess.Popen(ff_cmd, stdin=vspipe.stdout, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, cwd=ROOT)
    vspipe.stdout.close()
    vrc, frc = _show_progress(vspipe, ff, "渲染", total_out)
    if vrc != 0:
        print("警告: 渲染管线异常 (vspipe exit %s), 输出可能不完整" % vrc)
        return False
    if frc != 0:
        print("警告: ffmpeg 编码异常 (exit %s), 输出可能不完整" % frc)
        return False
    print("完成: %s" % output)
    return True


def cmd_render_folder(cfg, args, with_sr):
    """批量渲染整个目录 (默认跳过已存在输出, --overwrite 强制)"""
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print("目录不存在: %s" % folder)
        sys.exit(1)
    exts = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m4v", ".wmv", ".m2ts")
    # 排除 OverFPS 自己的输出命名 (避免把 _interp.mkv 等再次当输入套娃)
    out_re = re.compile(r"_(interp_sr|interp|sr|copy)\.(mkv|mp4|avi|mov|webm)$", re.IGNORECASE)
    files = sorted(f for f in os.listdir(folder)
                   if os.path.splitext(f)[1].lower() in exts and not out_re.search(f))
    if not files:
        print("目录里没有视频文件: %s" % folder)
        return
    gpu, _ = _resolve_gpu(args.gpu or cfg["gpu"])
    print("批量渲染 %d 个文件: %s" % (len(files), folder))
    ok = skip = fail = 0
    for i, name in enumerate(files, 1):
        video = os.path.join(folder, name)
        out = _default_output(video, args, with_sr)
        if os.path.exists(out) and not args.overwrite:
            print("\n[%d/%d] %s -> 输出已存在, 跳过 (--overwrite 强制重渲)" % (i, len(files), name))
            skip += 1
            continue
        print("\n[%d/%d] %s" % (i, len(files), name))
        if render_one(cfg, args, with_sr, video, out, gpu):
            ok += 1
        else:
            fail += 1
    print("\n批量完成: 成功 %d | 跳过 %d | 失败 %d" % (ok, skip, fail))


def cmd_render(args, with_sr=False):
    cfg = load_config()
    if getattr(args, "folder", None):
        cmd_render_folder(cfg, args, with_sr)
        return
    if not args.video:
        print("需要提供 video 路径, 或使用 --folder 批量渲染目录")
        sys.exit(1)
    gpu, _ = _resolve_gpu(args.gpu or cfg["gpu"])
    render_one(cfg, args, with_sr, os.path.abspath(args.video), args.output, gpu)


def cmd_bench(args):
    """基准: 跑 RIFE 补帧但不落盘, 报告输出帧率 (全 Python, 替代旧 bench.ps1)"""
    cfg = load_config()
    model = args.model or cfg["model"]
    frames = args.frames or 240
    video = os.path.abspath(args.video)  # vspipe cwd=SCRIPTS, 输入必须绝对路径
    if not os.path.exists(video):
        print("文件不存在: %s" % args.video)
        sys.exit(1)
    gpu, _ = _resolve_gpu(args.gpu or cfg["gpu"])
    env = make_env(True, model, cfg["scale"], "none", cfg["sr_model"], gpu, cfg["fp16"])
    env["VS_FRAMES"] = str(frames)
    env["VS_INPUT"] = video
    env["VS_START"] = str(args.start or 0)
    env["VS_RES"] = "0"
    script = os.path.join(SCRIPTS, "bench_rife.vpy")
    print("基准: 模型 %s | %d 源帧 (输出 %d 帧) | 渲染中..." % (model, frames, frames * 2))
    t0 = time.perf_counter()
    p = subprocess.run([VSPIPE, "-c", "y4m", script, "-"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env=env, cwd=SCRIPTS)
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        print("vspipe 失败: exit %s" % p.returncode)
        sys.exit(1)
    print("用时 %.2f s | 输出帧率 %.1f fps (含 2x 补帧)" % (dt, frames * 2 / dt))


def main():
    ensure_venv()

    # 无参数 -> 交互菜单; 裸文件参数 -> 直接播放
    if len(sys.argv) == 1:
        cmd_menu(None)
        return
    if len(sys.argv) == 2 and os.path.exists(sys.argv[1]) and not sys.argv[1].startswith("-"):
        class _A:
            video = os.path.abspath(sys.argv[1])
            model = scale = sr = sr_model = gpu = None
            no_interp = False
            sub = None
        cmd_play(_A())
        return

    ap = argparse.ArgumentParser(prog="ofps", description="OverFPS 视频补帧/超分")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_gpu = sub.add_parser("gpu", help="列出显卡")
    p_gpu.set_defaults(func=cmd_gpu)

    p_play = sub.add_parser("play", help="补帧/超分播放")
    p_play.add_argument("video")
    add_common(p_play)
    p_play.add_argument("--no-interp", action="store_true")
    p_play.add_argument("--sub", default=None, help="手动指定外挂字幕文件 (srt/ass/ssa)")
    p_play.set_defaults(func=cmd_play)

    p_menu = sub.add_parser("menu", help="交互式选择")
    p_menu.set_defaults(func=cmd_menu)

    p_r = sub.add_parser("render", help="离线渲染: 补帧(+超分可选)")
    p_r.add_argument("video", nargs="?", default=None)
    p_r.add_argument("output", nargs="?", default=None)
    add_common(p_r)
    p_r.add_argument("--no-interp", action="store_true", help="关闭插帧 (纯超分/纯转码)")
    p_r.add_argument("--frames", type=int, default=0)
    p_r.add_argument("--start", type=int, default=0)
    p_r.add_argument("--crf", type=int, default=None, help="画质 (默认 18)")
    p_r.add_argument("--preset", default=None, help="编码预设 (默认 medium)")
    p_r.add_argument("--codec", default=None, choices=["libx264", "libx265"])
    p_r.add_argument("--folder", default=None, help="批量渲染整个目录 (跳过已存在输出)")
    p_r.add_argument("--overwrite", action="store_true", help="批量时覆盖已存在输出")
    p_r.add_argument("--burn-sub", default=None, help="把字幕烧录进画面 (srt/ass)")
    p_r.add_argument("--burn-size", type=int, default=None, help="烧录字幕字号 (默认 22)")
    p_r.add_argument("--mode", default="balanced", choices=["fast", "balanced", "quality"],
                     help="画质模式: fast=极速(降分辨率补帧) / balanced=均衡 / quality=质量(重模型)")
    p_r.add_argument("--work-h", type=int, default=None, help="强制处理高度 (0=原分辨率, 高级)")
    p_r.set_defaults(func=lambda a: cmd_render(a, with_sr=False))

    p_rs = sub.add_parser("render-sr", help="离线渲染: 补帧+超分 (默认 RealESRGAN)")
    p_rs.add_argument("video", nargs="?", default=None)
    p_rs.add_argument("output", nargs="?", default=None)
    add_common(p_rs)
    p_rs.add_argument("--no-interp", action="store_true", help="关闭插帧 (仅超分)")
    p_rs.add_argument("--frames", type=int, default=0)
    p_rs.add_argument("--start", type=int, default=0)
    p_rs.add_argument("--crf", type=int, default=None)
    p_rs.add_argument("--preset", default=None)
    p_rs.add_argument("--codec", default=None, choices=["libx264", "libx265"])
    p_rs.add_argument("--folder", default=None, help="批量渲染整个目录")
    p_rs.add_argument("--overwrite", action="store_true", help="批量时覆盖已存在输出")
    p_rs.add_argument("--burn-sub", default=None, help="把字幕烧录进画面 (srt/ass)")
    p_rs.add_argument("--burn-size", type=int, default=None, help="烧录字幕字号 (默认 22)")
    p_rs.add_argument("--mode", default="balanced", choices=["fast", "balanced", "quality"],
                     help="画质模式: fast=极速(降分辨率补帧) / balanced=均衡 / quality=质量(重模型)")
    p_rs.add_argument("--work-h", type=int, default=None, help="强制处理高度 (0=原分辨率, 高级)")
    p_rs.set_defaults(func=lambda a: cmd_render(a, with_sr=True))

    p_bench = sub.add_parser("bench", help="基准: 补帧速度 (不产文件)")
    p_bench.add_argument("video")
    p_bench.add_argument("--frames", type=int, default=240)
    p_bench.add_argument("--start", type=int, default=0)
    add_common(p_bench)
    p_bench.set_defaults(func=cmd_bench)

    args = ap.parse_args()
    args.func(args)


def add_common(p):
    p.add_argument("--model", default=None)
    p.add_argument("--scale", default=None)
    p.add_argument("--sr", default=None, choices=["none", "anime4k", "realesrgan", "cugan", "waifu2x"])
    p.add_argument("--sr-model", default=None)
    p.add_argument("--gpu", default=None)


if __name__ == "__main__":
    main()
