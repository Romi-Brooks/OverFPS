# play.vpy - 统一插帧 + 超分管线 (mpv --vf=vapoursynth 桥接)
# 环境变量 (由 ofps.py 注入):
#   VS_INTERP   = 1/0        插帧开关 (默认 1)
#   VS_MODEL    = RIFE 模型   v4_26_heavy / v4_26 / v4_22_lite / v4_17_lite / v4_15_lite / v4_6
#   VS_SCALE    = 光流处理分辨率比例 (v4_6 可用 0.5 加速; v4.7+ 仅支持 1.0)
#   VS_SR       = none/realesrgan/cugan/waifu2x   超分引擎 (默认 none)
#   VS_SR_MODEL = 超分引擎参数: realesrgan: xsx2/xsx4/v3 ; cugan/waifu2x: 2/3/4 (倍率)
#   VS_GPU      = DML 设备号 (由启动器自动探测独显或手动指定)
#   VS_FP16     = 1/0        fp16 加速 (默认 1)
#   OFPS_ROOT   = OverFPS 根目录 (帧统计 JSON 输出位置)
import os
import sys
from fractions import Fraction

import vapoursynth as vs
from vapoursynth import core

# 由 overfps.py 注入 OFPS_ROOT; vsmlrt 在 runtime\vsmlrt\scripts 下
sys.path.insert(0, os.path.join(os.environ.get("OFPS_ROOT", r"D:\Project\Repo\OverFPS"),
                                "runtime", "vsmlrt", "scripts"))
import vsmlrt

INTERP = os.environ.get("VS_INTERP", "1") == "1"
MODEL = os.environ.get("VS_MODEL", "v4_22_lite")
SCALE = float(os.environ.get("VS_SCALE", "1.0"))
SR = os.environ.get("VS_SR", "none").lower()
SR_MODEL = os.environ.get("VS_SR_MODEL", "2")
GPU = int(os.environ.get("VS_GPU", "1"))
FP16 = os.environ.get("VS_FP16", "1") == "1"

# ---------------- 源帧率实测 (VFR 感知, 供 OSD 显示真实数据) ----------------
# mpv 会给 video_in 每帧设置 _DurationNum/_DurationDen; 这里累计最近 N 帧时长,
# 周期性写 JSON 到 OFPS_ROOT/.runtime/fps_stats.json (lua OSD 每秒读取)
import json as _json

ROOT_DIR = os.environ.get("OFPS_ROOT", r"D:\Project\Repo\OverFPS")
STATS_FILE = os.path.join(ROOT_DIR, ".runtime", "fps_stats.json")

_stats = {"durs": [], "count": 0}


def _write_stats():
    durs = [d for d in _stats["durs"] if d is not None and d > 0]
    n = len(durs)
    if n < 8:
        return
    avg = sum(durs) / n
    var = sum((d - avg) ** 2 for d in durs) / n
    std = var ** 0.5
    try:
        os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
        tmp = STATS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump({
                "src_fps": round(1.0 / avg, 3),
                "vfr": std / avg > 0.02,          # 帧时长波动 >2% 视为 VFR
                "frames": _stats["count"],
                "avg_dur": round(avg, 6),
            }, f, ensure_ascii=False)
        os.replace(tmp, STATS_FILE)
    except Exception:
        pass


def _fps_acc(n, *args, **kw):
    """ModifyFrame 选择器: 不改画面, 只累计源帧时长统计
    实测: 本 VS 版本回调为 fn(n, f=<VideoFrame>), 原样返回 f 即可透传"""
    src = kw.get("f", args[0] if args else None)
    if src is not None:
        _stats["count"] += 1
        d = src.props.get("_DurationNum") or src.props.get("DurationNum")
        dd = src.props.get("_DurationDen") or src.props.get("DurationDen")
        dur = (d / dd) if (d and dd) else None
        _stats["durs"].append(dur)
        if len(_stats["durs"]) > 180:
            _stats["durs"].pop(0)
        if _stats["count"] % 24 == 0:
            _write_stats()
    return src


# ---------------- 管线 ----------------
BACKEND = vsmlrt.Backend.ORT_DML(fp16=FP16, device_id=GPU)

matrix, rng = "709", "limited"
clip = video_in
orig_w, orig_h = clip.width, clip.height

# 源帧率统计 (插在源侧, 不改变画面)
clip = core.std.ModifyFrame(clip, clip, _fps_acc)

clip = core.resize.Bicubic(clip, format=vs.RGBH, matrix_in_s=matrix, range_in_s=rng)

ALIGN = 64
PAD_W = (ALIGN - clip.width % ALIGN) % ALIGN
PAD_H = (ALIGN - clip.height % ALIGN) % ALIGN
if PAD_W or PAD_H:
    clip = core.std.AddBorders(clip, right=PAD_W, bottom=PAD_H)

out = clip
if INTERP:
    out = vsmlrt.RIFE(out, multi=2, scale=SCALE,
                      model=getattr(vsmlrt.RIFEModel, MODEL), backend=BACKEND)

# 裁掉对齐补边, 回到原始尺寸 (超分前处理干净画面)
if PAD_W or PAD_H:
    out = core.std.CropAbs(out, width=orig_w, height=orig_h)

if SR == "realesrgan":
    m = {"xsx2": vsmlrt.RealESRGANv2Model.animevideo_xsx2,
         "xsx4": vsmlrt.RealESRGANv2Model.animevideo_xsx4,
         "v3": vsmlrt.RealESRGANv2Model.animevideov3}.get(SR_MODEL, vsmlrt.RealESRGANv2Model.animevideo_xsx2)
    out = vsmlrt.RealESRGAN(clip=out, model=m, backend=BACKEND)
elif SR == "cugan":
    out = vsmlrt.CUGAN(clip=out, noise=-1, scale=int(SR_MODEL), backend=BACKEND)
elif SR == "waifu2x":
    out = vsmlrt.Waifu2x(clip=out, model=vsmlrt.Waifu2xModel.cunet,
                         scale=int(SR_MODEL), noise=0, backend=BACKEND)

if INTERP:
    if container_fps and container_fps > 0:
        f = Fraction(container_fps).limit_denominator(1000000)
    else:
        f = Fraction(24000, 1001)
    out = core.std.AssumeFPS(out, fpsnum=f.numerator * 2, fpsden=f.denominator)

out = core.resize.Bicubic(out, format=video_in.format, matrix_s=matrix, range_s=rng)
out.set_output()
