# render.vpy - 离线渲染统一管线 (vspipe + ffmpeg 由 ofps.py render / render-sr 驱动)
# 环境变量 (由 ofps.py 注入):
#   VS_INPUT    = 输入视频 (必填)
#   VS_START    = 起始秒 (默认 0)
#   VS_FRAMES   = 渲染帧数 (0 = 全部)
#   VS_INTERP   = 1/0        插帧开关 (默认 1)
#   VS_MODEL    = RIFE 模型 (v4_26_heavy / v4_26 / v4_22_lite / v4_17_lite / v4_15_lite / v4_6)
#   VS_SCALE    = 光流分辨率比例 (v4_6 可用 0.5 加速; v4.7+ 仅支持 1.0)
#   VS_SR       = none/realesrgan/cugan/waifu2x   超分引擎 (默认 none)
#   VS_SR_MODEL = realesrgan: xsx2/xsx4/v3 ; cugan/waifu2x: 倍率 2/3/4
#   VS_GPU      = DML 设备号
#   VS_FP16     = 1/0
#   VS_WORK_H   = 极速模式: 处理高度 (源更高时降采样处理, 结束后放大回; 0=原分辨率)
import os
import sys
from fractions import Fraction

import vapoursynth as vs
from vapoursynth import core

sys.path.insert(0, os.path.join(os.environ.get("OFPS_ROOT", r"D:\Project\Repo\OverFPS"),
                                "runtime", "vsmlrt", "scripts"))
import vsmlrt

SRC = os.environ.get("VS_INPUT", "")
assert SRC, "VS_INPUT 未设置"
INTERP = os.environ.get("VS_INTERP", "1") == "1"
MODEL = os.environ.get("VS_MODEL", "v4_22_lite")
SCALE = float(os.environ.get("VS_SCALE", "1.0"))
SR = os.environ.get("VS_SR", "none").lower()
SR_MODEL = os.environ.get("VS_SR_MODEL", "2")
GPU = int(os.environ.get("VS_GPU", "1"))
FP16 = os.environ.get("VS_FP16", "1") == "1"
START = int(os.environ.get("VS_START", "0"))
FRAMES = int(os.environ.get("VS_FRAMES", "0"))

src = core.bs.VideoSource(SRC)
if FRAMES > 0:
    n = src.num_frames
    end = min(START + FRAMES - 1, n - 1)
    if START >= n:
        raise SystemExit("VS_START 超出视频长度 (%d 帧)" % n)
    src = src.std.Trim(START, end)

matrix, rng = "709", "limited"
clip = core.resize.Bicubic(src, format=vs.RGBH, matrix_in_s=matrix, range_in_s=rng)

# ---- 极速模式: 降分辨率处理再放大回 (VS_WORK_H > 0 且源更高时) ----
WORK_H = int(os.environ.get("VS_WORK_H", "0"))
orig_w, orig_h = src.width, src.height
work_w, work_h = orig_w, orig_h
if WORK_H and clip.height > WORK_H:
    work_h = WORK_H
    work_w = max(2, clip.width * WORK_H // clip.height // 2 * 2)  # 等比, 保持偶数
    clip = core.resize.Bicubic(clip, width=work_w, height=work_h,
                               matrix_in_s=matrix, range_in_s=rng)

ALIGN = 64
PAD_W = (ALIGN - clip.width % ALIGN) % ALIGN
PAD_H = (ALIGN - clip.height % ALIGN) % ALIGN
if PAD_W or PAD_H:
    clip = core.std.AddBorders(clip, right=PAD_W, bottom=PAD_H)

backend = vsmlrt.Backend.ORT_DML(fp16=FP16, device_id=GPU)

out = clip
if INTERP:
    out = vsmlrt.RIFE(out, multi=2, scale=SCALE,
                      model=getattr(vsmlrt.RIFEModel, MODEL), backend=backend)

if PAD_W or PAD_H:
    out = core.std.CropAbs(out, width=work_w, height=work_h)

if SR == "realesrgan":
    m = {"xsx2": vsmlrt.RealESRGANv2Model.animevideo_xsx2,
         "xsx4": vsmlrt.RealESRGANv2Model.animevideo_xsx4,
         "v3": vsmlrt.RealESRGANv2Model.animevideov3}.get(SR_MODEL, vsmlrt.RealESRGANv2Model.animevideo_xsx2)
    out = vsmlrt.RealESRGAN(clip=out, model=m, backend=backend)
elif SR == "cugan":
    out = vsmlrt.CUGAN(clip=out, noise=-1, scale=int(SR_MODEL), backend=backend)
elif SR == "waifu2x":
    out = vsmlrt.Waifu2x(clip=out, model=vsmlrt.Waifu2xModel.cunet,
                         scale=int(SR_MODEL), noise=0, backend=backend)

# 极速模式: 若最终分辨率低于原分辨率, 放大回原尺寸
# (VS_UPSCALE_OUT=0 时由 ffmpeg scale 负责放大, 减少 vspipe 侧 4K 处理)
if os.environ.get("VS_UPSCALE_OUT", "1") == "1" and (out.width < orig_w or out.height < orig_h):
    out = core.resize.Bicubic(out, width=orig_w, height=orig_h,
                              matrix_in_s=matrix, range_in_s=rng)

if INTERP:
    if src.fps_num and src.fps_den:
        f = Fraction(src.fps_num, src.fps_den).limit_denominator(1000000)
    else:
        f = Fraction(24000, 1001)
    out = core.std.AssumeFPS(out, fpsnum=f.numerator * 2, fpsden=f.denominator)

out = core.resize.Bicubic(out, format=vs.YUV420P8, matrix_s=matrix, range_s=rng)
out.set_output()
