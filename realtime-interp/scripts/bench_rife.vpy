# RIFE 基准测试脚本（vspipe 驱动）
# 环境变量:
#   VS_MODEL  = RIFEModel 枚举名, 如 v4_22_lite / v4_26 / v4_26_heavy / v4_17_lite / v4_15_lite
#   VS_START  = 起始帧 (默认 600)
#   VS_FRAMES = 处理帧数 (默认 300)
#   VS_RES    = 目标高度 (默认 720, 即原始分辨率)
#   VS_GPU    = DML 设备号 (默认 1)
import os
import sys

import vapoursynth as vs
from vapoursynth import core

sys.path.insert(0, r"D:\Project\Repo\OverFPS\realtime-interp\vsmlrt\scripts")
import vsmlrt

SRC = os.environ.get("VS_INPUT", r"D:\Project\Repo\OverFPS\video\东京食尸 第一季第6集.mp4")
MODEL = os.environ.get("VS_MODEL", "v4_22_lite")
START = int(os.environ.get("VS_START", "600"))
FRAMES = int(os.environ.get("VS_FRAMES", "300"))
HEIGHT = int(os.environ.get("VS_RES", "720"))
SCALE = float(os.environ.get("VS_SCALE", "1.0"))

src = core.bs.VideoSource(SRC)
if FRAMES > 0:
    n = src.num_frames
    end = min(START + FRAMES - 1, n - 1)
    if START >= n:
        raise SystemExit("VS_START 超出视频长度 (%d 帧)" % n)
    src = src.std.Trim(START, end)

if HEIGHT and src.height != HEIGHT:
    src = core.resize.Bicubic(src, width=HEIGHT * 16 // 9, height=HEIGHT,
                              matrix_in_s="709", range_in_s="limited")

clip = core.resize.Bicubic(src, format=vs.RGBH,
                           matrix_in_s="709", range_in_s="limited")

# vsmlrt 要求输入尺寸为 32/64 的倍数 (v4.26+ 需 64) -> 右边/下边补边, 处理后裁回
ALIGN = 64
PAD_W = (ALIGN - clip.width % ALIGN) % ALIGN
PAD_H = (ALIGN - clip.height % ALIGN) % ALIGN
if PAD_W or PAD_H:
    clip = core.std.AddBorders(clip, right=PAD_W, bottom=PAD_H)

out = vsmlrt.RIFE(
    clip,
    multi=2,
    scale=SCALE,
    model=getattr(vsmlrt.RIFEModel, MODEL),
    backend=vsmlrt.Backend.ORT_DML(fp16=os.environ.get("VS_FP16", "1") == "1",
                                   device_id=int(os.environ.get("VS_GPU", "1"))),
)

if PAD_W or PAD_H:
    out = core.std.CropAbs(out, width=src.width, height=src.height)

out = core.resize.Bicubic(out, format=vs.YUV420P8,
                          matrix_s="709", range_s="limited")
out.set_output()
