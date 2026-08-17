#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头播放测速: 对比不同容器的补帧吞吐 (全 Python, 替代不可靠的 pwsh 测量)
用法: .venv\\Scripts\\python.exe tests\\speed_test.py
"""
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "realtime-interp", "scripts")
MPV = os.path.join(ROOT, "realtime-interp", "mpv", "mpv.exe")
VS_PATH = os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth")

FILES = [
    ("合成 720p",        os.path.join(ROOT, "tests", "demo.mp4")),
    ("合成 4K",          os.path.join(ROOT, "tests", "demo_4k.mp4")),
]

FRAMES = 240
HWDEC = ["no", "auto-safe"]


def run(path, hwdec):
    env = os.environ.copy()
    env["PATH"] = VS_PATH + ";" + env.get("PATH", "")
    env.update({
        "VS_INTERP": "1", "VS_MODEL": "v4_22_lite", "VS_SCALE": "1.0",
        "VS_SR": "none", "VS_SR_MODEL": "2", "VS_GPU": "1", "VS_FP16": "1",
    })
    vf = "vapoursynth=file=play.vpy:buffered-frames=8:concurrent-frames=4"
    cmd = [MPV, "--no-config", "--vo=null", "--ao=null",
           "--frames=%d" % FRAMES, "--keep-open=no", "--msg-level=all=info",
           "--hwdec=" + hwdec,
           "--vf=" + vf, path]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=SCRIPTS, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    dt = time.perf_counter() - t0
    text = p.stdout.decode("utf-8", errors="replace")
    errs = [ln for ln in text.splitlines()
            if any(k in ln.lower() for k in ("error", "failed", "fatal"))][:4]
    return dt, p.returncode, errs


def main():
    for name, path in FILES:
        if not os.path.exists(path):
            print("%-18s 文件不存在" % name)
            continue
        for hwdec in HWDEC:
            dt, rc, errs = run(path, hwdec)
            fps = FRAMES / dt if dt > 0 else 0
            print("%-18s hwdec=%-10s %5.1fs ~%5.0f 输出fps exit=%s"
                  % (name, hwdec, dt, fps, rc))
            for e in errs:
                print("      ! " + e)


if __name__ == "__main__":
    main()
