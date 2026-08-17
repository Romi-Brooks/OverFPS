#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跳转音画同步回归测试: 真实 mpv 配置下对比 video-sync / hwdec 组合
用法: .venv\\Scripts\\python.exe tests\\sync_test.py
会短暂弹出小播放窗口 (~60s), 静音播放, 测试结束自动关闭
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
APP = os.path.join(ROOT, "realtime-interp")
SCRIPTS = os.path.join(APP, "scripts")
MPV = os.path.join(APP, "mpv", "mpv.exe")
VS_PATH = os.path.join(ROOT, ".venv", "Lib", "site-packages", "vapoursynth")
VIDEO = os.path.join(ROOT, "video", "东京食尸 第一季第6集.mp4")
PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_probe.lua")

# (名称, video-sync, hwdec)
VARIANTS = [
    ("display-resample + hwdec=auto-safe (当前配置)", "display-resample", "auto-safe"),
    ("audio + hwdec=auto-safe",                       "audio",           "auto-safe"),
    ("audio + hwdec=no",                              "audio",           "no"),
    ("display-resample + hwdec=no",                   "display-resample", "no"),
]

PROBE_RE = re.compile(r"PROBE t=([\d.-]+) ap=([\d.-]+) avsync=([\d.-]+)")


def run(vsync, hwdec):
    env = os.environ.copy()
    env["PATH"] = VS_PATH + ";" + env.get("PATH", "")
    env.update({
        "VS_INTERP": "1", "VS_MODEL": "v4_22_lite", "VS_SCALE": "1.0",
        "VS_SR": "none", "VS_SR_MODEL": "2", "VS_GPU": "1", "VS_FP16": "1",
    })
    vf = "vapoursynth=file=play.vpy:buffered-frames=8:concurrent-frames=4"
    cmd = [MPV, "--vo=gpu-next", "--ao=wasapi", "--volume=0",
           "--video-sync=" + vsync, "--hwdec=" + hwdec,
           "--frames=600", "--keep-open=no", "--geometry=480x300",
           "--msg-level=all=info",
           "--vf=" + vf, "--script=" + PROBE, VIDEO]
    p = subprocess.run(cmd, cwd=SCRIPTS, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    text = p.stdout.decode("utf-8", errors="replace")
    rows = []
    for m in PROBE_RE.finditer(text):
        if m.group(3) == "-":
            continue
        rows.append((float(m.group(1)), float(m.group(3))))
    return rows


def window_stats(rows, lo, hi):
    seq = [d for t, d in rows if lo <= t < hi]
    if not seq:
        return "n/a"
    return "max|%.3f|" % max(abs(x) for x in seq)


def main():
    if not os.path.exists(VIDEO):
        print("测试视频不存在:", VIDEO)
        sys.exit(1)
    for name, vsync, hwdec in VARIANTS:
        try:
            rows = run(vsync, hwdec)
        except subprocess.TimeoutExpired:
            print("== %s == TIMEOUT" % name)
            continue
        print("== %s ==" % name)
        print("   跳转前(0-1.5s)     : %s" % window_stats(rows, 0, 1.5))
        print("   跳30s后(29.5-36s)  : %s" % window_stats(rows, 29.5, 36))
        print("   跳200s后(199.5-206): %s" % window_stats(rows, 199.5, 206))
        print("   全程最大|avsync|   : %s" % window_stats(rows, 0, 999))


if __name__ == "__main__":
    main()
