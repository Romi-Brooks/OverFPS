#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出目录及 subs/ 子目录下的外挂字幕文件 (供 mpv lua 手动加载字幕, UTF-8 输出)"""
import glob
import os
import sys

EXTS = (".srt", ".ass", ".ssa", ".sub", ".vtt")


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    out = []
    for base in (d, os.path.join(d, "subs")):
        for f in sorted(glob.glob(os.path.join(base, "*"))):
            if os.path.splitext(f)[1].lower() in EXTS:
                out.append(f)
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    main()
