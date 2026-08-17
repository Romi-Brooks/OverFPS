#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_models.py — 下载并安装 OverFPS 模型与 vsmlrt 后端 (全 Python)

来源 (均已验证):
  1) vs-mlrt v15.16 generic-gpu 包 (843MB):
     - models/  全部 SR 模型 (RealESRGAN/CUGAN/waifu2x/dpir) + 旧版 RIFE (含 v4.6)
     - vsort.dll + vsort/  DirectML 后端 (onnxruntime + DirectML)
  2) vs-mlrt external-models release: 新版 RIFE (v4.15_lite / v4.17_lite /
     v4.22_lite / v4.26 / v4.26_heavy)

用法:
  python fetch_models.py                 # 全量 (模型 + vsort 后端)
  python fetch_models.py --only-rife     # 只补新版 RIFE 模型
  python fetch_models.py --skip-vsort    # 模型但要已装后端
"""
import argparse
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
MODELS = os.path.join(ROOT, "models")
DL = os.path.join(ROOT, ".runtime", "dl")
SEVENZ = os.path.join(ROOT, "tools", "7zr.exe")

GENERIC_URL = ("https://github.com/AmusementClub/vs-mlrt/releases/download/"
               "v15.16/vsmlrt-windows-x64-generic-gpu.v15.16.7z")
EXTERNAL = "https://github.com/AmusementClub/vs-mlrt/releases/download/external-models/%s"
# 我们实际使用的 RIFE 模型 (默认/均衡/极速/质量预设); 资产名版本号带点
RIFE_NEEDED = ["v4.15_lite", "v4.17_lite", "v4.22_lite", "v4.26", "v4.26_heavy"]


def default_plugins_dir():
    """vapoursynth 插件目录 (venv 安装后)"""
    return os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth", "plugins")


def _download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print("已存在, 跳过下载: %s" % os.path.basename(dest))
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("下载 %s" % url)

    def _hook(blocks, bs, total):
        done = blocks * bs
        if total > 0:
            print("\r  %5.1f%%  %d/%d MB  " % (min(100, done / total * 100),
                                                done // 1048576, total // 1048576),
                  end="", flush=True)

    urllib.request.urlretrieve(url, dest, _hook)
    print()
    return dest


def _extract(archive, outdir, include=None):
    os.makedirs(outdir, exist_ok=True)
    cmd = [SEVENZ, "x", archive, "-o" + outdir, "-y"]
    for pat in include or []:
        cmd.append("-i!" + pat)
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise RuntimeError("解压失败: %s (exit %s)" % (archive, p.returncode))


def _merge_tree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)


def install_generic(plugins_dir):
    """generic-gpu: models -> ROOT/models, vsort -> 插件目录"""
    arch = _download(GENERIC_URL, os.path.join(DL, "generic-gpu.7z"))
    print("解压 generic-gpu (模型 + vsort 后端)...")
    tmp = os.path.join(DL, "gen")
    _extract(arch, tmp, include=["models", "vsort.dll", "vsort"])
    _merge_tree(os.path.join(tmp, "models"), MODELS)
    os.makedirs(plugins_dir, exist_ok=True)
    shutil.copy2(os.path.join(tmp, "vsort.dll"), plugins_dir)
    shutil.copytree(os.path.join(tmp, "vsort"),
                    os.path.join(plugins_dir, "vsort"), dirs_exist_ok=True)
    print("✓ SR 模型 + 旧版 RIFE + vsort(DirectML) 后端已安装")


def install_rife():
    """external-models: 新版 RIFE 模型 -> models/ (保留 rife/ 与 rife_v2/ 结构)
    vsmlrt 需要: models/rife/<主模型.onnx> + models/rife_v2/<合并模型.onnx> 成对存在"""
    for name in RIFE_NEEDED:
        asset = "rife_%s.7z" % name
        arch = _download(EXTERNAL % asset, os.path.join(DL, asset))
        tmp = os.path.join(DL, "rife_tmp")
        # 清空上次解压残留, 避免跨包串文件
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        _extract(arch, tmp)
        n = 0
        for root, _, files in os.walk(tmp):
            rel = os.path.relpath(root, tmp)
            for fn in files:
                if not fn.endswith(".onnx"):
                    continue
                # 目标子目录: 保留包内结构 (rife/ 或 rife_v2/), 兜底 rife/
                sub = os.path.normpath(rel).replace(os.sep, "/")
                if sub == "rife_v2":
                    dst_dir = os.path.join(MODELS, "rife_v2")
                else:
                    dst_dir = os.path.join(MODELS, "rife")
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(os.path.join(root, fn), os.path.join(dst_dir, fn))
                n += 1
        print("✓ RIFE %s (%d 个文件)" % (name, n))
    print("✓ 新版 RIFE 模型已安装 → %s" % MODELS)


def main():
    ap = argparse.ArgumentParser(description="OverFPS 模型/后端下载安装")
    ap.add_argument("--plugins-dir", default=None,
                    help="vapoursynth 插件目录 (默认: .venv 内)")
    ap.add_argument("--skip-vsort", action="store_true", help="不装 vsort 后端")
    ap.add_argument("--only-rife", action="store_true", help="只补新版 RIFE 模型")
    a = ap.parse_args()
    plugins = a.plugins_dir or default_plugins_dir()
    if not a.only_rife:
        install_generic(plugins)
    install_rife()
    print("\n完成. 模型目录: %s" % MODELS)


if __name__ == "__main__":
    main()
