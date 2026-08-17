#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实窗口丢帧对比: 真实 mpv.conf + 真实音频时钟, 播放 12s 统计丢帧
用法: .venv\\Scripts\\python.exe tests\\drop_test.py
会短暂弹出小窗口 (~90s), 静音播放
"""
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "runtime", "scripts")
MPV = os.path.join(ROOT, "runtime", "mpv", "mpv.exe")
VS_PATH = os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth")
PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drop_probe.lua")

FILES = [
    ("合成 720p",    os.path.join(ROOT, "tests", "demo.mp4")),
    ("合成 4K",      os.path.join(ROOT, "tests", "demo_4k.mp4")),
]

DROP_RE = re.compile(r"DROPPROBE time=([\d.-]+) frame_drop=([-\d]+) vo_drop=([-\d]+)")


def run(path):
    env = os.environ.copy()
    env["PATH"] = VS_PATH + ";" + env.get("PATH", "")
    env.update({
        "VS_INTERP": "1", "VS_MODEL": "v4_22_lite", "VS_SCALE": "1.0",
        "VS_SR": "none", "VS_SR_MODEL": "2", "VS_GPU": "1", "VS_FP16": "1",
    })
    vf = "vapoursynth=file=play.vpy:buffered-frames=8:concurrent-frames=4"
    cmd = [MPV, "--vo=gpu-next", "--ao=wasapi", "--volume=0",
           "--keep-open=no", "--length=8", "--geometry=480x300",
           "--msg-level=all=info",
           "--vf=" + vf, "--script=" + PROBE, path]
    p = subprocess.run(cmd, cwd=SCRIPTS, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    text = p.stdout.decode("utf-8", errors="replace")
    for m in DROP_RE.finditer(text):
        return float(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def main():
    for name, path in FILES:
        if not os.path.exists(path):
            print("%-16s 文件不存在" % name)
            continue
        try:
            r = run(path)
        except subprocess.TimeoutExpired:
            print("%-16s TIMEOUT" % name)
            continue
        if r is None:
            print("%-16s 无探针数据" % name)
            continue
        t, fd, vo = r
        # 理论应显示帧数 ≈ t * 47.95; 丢帧率
        expect = t * 47.95
        print("%-16s 播放 %.1fs  理论 %.0f 帧  丢帧 %d  vo丢 %d  (%.1f%%)"
              % (name, t, expect, fd, vo, 100.0 * fd / expect if expect else 0))


if __name__ == "__main__":
    main()
