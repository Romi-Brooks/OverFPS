#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup.py — 一键部署 OverFPS (全 Python, 无 bat)

用法:
  python setup.py                 # 完整部署 (venv + 依赖 + 模型 + mpv/ffmpeg)
  python setup.py --skip-models   # 跳过模型下载 (已有 models/)
  python setup.py --skip-mpv      # 跳过 mpv 下载 (用户侧已装或稍后手动)
  python setup.py --skip-ffmpeg   # 跳过 ffmpeg 下载 (用户侧已装进 PATH)

流程: Python 版本检查 -> 建 venv -> requirements -> vapoursynth wheel
      -> fetch_models -> mpv -> ffmpeg -> python dll -> vapoursynth 配置 -> 验证
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "realtime-interp")
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
DL = os.path.join(ROOT, ".runtime", "dl")
SEVENZ = os.path.join(ROOT, "tools", "7zr.exe")

VS_URL = ("https://github.com/vapoursynth/vapoursynth/releases/download/"
          "R79/VapourSynth64-Portable-R79.zip")
VS_WHEEL_INNER = "wheel/vapoursynth-79-cp312-abi3-win_amd64.whl"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def run(cmd, **kw):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, **kw)


def ensure_python():
    if sys.version_info < (3, 12):
        print("需要 Python 3.12+ (当前 %s)" % sys.version.split()[0])
        sys.exit(1)


def ensure_venv():
    if not os.path.exists(VENV_PY):
        print("创建虚拟环境 .venv ...")
        run([sys.executable, "-m", "venv", os.path.join(ROOT, ".venv")],
            check=True)
    if os.path.realpath(sys.executable).lower() != os.path.realpath(VENV_PY).lower():
        print("切换到 venv Python 重新执行 ...")
        sys.exit(subprocess.run([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:]).returncode)


def pip(*args):
    run([VENV_PY, "-m", "pip"] + list(args), check=True)


def install_requirements():
    print("安装 Python 依赖 (requirements.txt) ...")
    pip("install", "-U", "pip")
    pip("install", "-r", os.path.join(ROOT, "requirements.txt"))


def install_vapoursynth():
    vs_pkg = os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth")
    if os.path.exists(os.path.join(vs_pkg, "vspipe.exe")):
        print("VapourSynth 已安装, 跳过")
        return
    print("下载 VapourSynth R79 portable ...")
    os.makedirs(DL, exist_ok=True)
    zip_path = os.path.join(DL, "vs-portable.zip")
    if not (os.path.exists(zip_path) and os.path.getsize(zip_path) > 1000):
        urllib.request.urlretrieve(VS_URL, zip_path)
    import zipfile
    wheel_out = os.path.join(DL, "vs_wheel")
    os.makedirs(wheel_out, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extract(VS_WHEEL_INNER, wheel_out)
    wheel = os.path.join(wheel_out, VS_WHEEL_INNER.replace("/", os.sep))
    print("安装 VapourSynth wheel ...")
    pip("install", wheel)


def install_models(skip):
    if skip:
        print("跳过模型下载 (--skip-models)")
        return
    import fetch_models
    # 直接调用内部函数, 避免重复解析 argv
    plugins = fetch_models.default_plugins_dir()
    fetch_models.install_generic(plugins)
    fetch_models.install_rife()


def install_mpv(skip):
    mpv_dir = os.path.join(APP, "mpv")
    if skip or os.path.exists(os.path.join(mpv_dir, "mpv.exe")):
        print("mpv: 已存在或跳过")
        return
    print("查找最新 mpv (shinchiro 构建) ...")
    api = ("https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest")
    with urllib.request.urlopen(api) as r:
        rel = json.load(r)
    asset = None
    for a in rel["assets"]:
        if a["name"].startswith("mpv-x86_64-") and a["name"].endswith(".7z"):
            asset = a
            break
    if not asset:
        print("未找到 mpv 资产, 请手动下载到 %s" % mpv_dir)
        return
    print("下载 %s ..." % asset["name"])
    os.makedirs(DL, exist_ok=True)
    arch = os.path.join(DL, asset["name"])
    if not (os.path.exists(arch) and os.path.getsize(arch) > 1000):
        urllib.request.urlretrieve(asset["browser_download_url"], arch)
    print("解压到 %s ..." % mpv_dir)
    os.makedirs(mpv_dir, exist_ok=True)
    p = subprocess.run([SEVENZ, "x", arch, "-o" + mpv_dir, "-y"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        print("mpv 解压失败 (exit %s)" % p.returncode)
    elif os.path.exists(os.path.join(mpv_dir, "mpv.exe")):
        print("✓ mpv 已安装 (portable_config 已就绪)")


def install_ffmpeg(skip):
    if skip or shutil.which("ffmpeg") or os.path.exists(os.path.join(APP, "ffmpeg", "ffmpeg.exe")):
        where = shutil.which("ffmpeg") or os.path.join(APP, "ffmpeg", "ffmpeg.exe")
        print("ffmpeg: 使用 %s" % where)
        return
    print("下载 ffmpeg (gyan.dev release essentials) ...")
    os.makedirs(DL, exist_ok=True)
    zip_path = os.path.join(DL, "ffmpeg-release.zip")
    if not (os.path.exists(zip_path) and os.path.getsize(zip_path) > 1000):
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
    import zipfile
    out = os.path.join(DL, "ffmpeg_extract")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    # 找到 ffmpeg.exe (zip 内是 ffmpeg-x.x.x-essentials_build/bin/ffmpeg.exe)
    found = None
    for root, _, files in os.walk(out):
        if "ffmpeg.exe" in files:
            found = os.path.join(root, "ffmpeg.exe")
            break
    if not found:
        print("ffmpeg 解压后未找到 ffmpeg.exe, 请手动安装并加入 PATH")
        return
    ffmpeg_dir = os.path.join(APP, "ffmpeg")
    os.makedirs(ffmpeg_dir, exist_ok=True)
    shutil.copy2(found, os.path.join(ffmpeg_dir, "ffmpeg.exe"))
    print("✓ ffmpeg 已安装到 realtime-interp\\ffmpeg\\")


def copy_python_dlls():
    """VSScript 探测 Python 需要 python3.dll/python312.dll 在 venv 根目录"""
    for dll in ("python3.dll", "python%s.dll" % sys.version_info.major +
                ("%d" % sys.version_info.minor)):
        src = os.path.join(sys.base_prefix, dll)
        dst = os.path.join(ROOT, ".venv", dll)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print("✓ 复制 %s -> .venv\\" % dll)


def configure_vapoursynth():
    print("生成 vapoursynth 配置 ...")
    p = run([VENV_PY, "-m", "vapoursynth", "config"])
    if p.returncode != 0:
        print("vapoursynth config 异常 (exit %s), 可稍后手动执行" % p.returncode)


def verify():
    print("\n验证 GPU 探测 ...")
    p = run([VENV_PY, os.path.join(ROOT, "ofps.py"), "gpu"])
    if p.returncode == 0:
        print("\n部署完成! 运行: python ofps.py menu")
    else:
        print("\nGPU 探测异常, 请检查显卡驱动/设备号")


def main():
    ap = argparse.ArgumentParser(description="OverFPS 一键部署")
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--skip-mpv", action="store_true")
    ap.add_argument("--skip-ffmpeg", action="store_true")
    args = ap.parse_args()

    ensure_python()
    ensure_venv()
    install_requirements()
    install_vapoursynth()
    install_models(args.skip_models)
    install_mpv(args.skip_mpv)
    install_ffmpeg(args.skip_ffmpeg)
    copy_python_dlls()
    configure_vapoursynth()
    verify()


if __name__ == "__main__":
    main()
