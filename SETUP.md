# OverFPS 部署说明

仓库只包含**源码 / 配置 / 脚本 / 测试样片**。运行时（mpv、ffmpeg、VapourSynth、
vsmlrt 后端、全部模型）由 `setup.py` 一键从官方源下载安装，**模型不纳入版本控制**
（约 600MB+，由 `fetch_models.py` 负责）。

## 一键部署（推荐）

```bat
git clone https://github.com/Romi-Brooks/OverFPS.git
cd OverFPS
python setup.py
```

`setup.py` 自动完成：
1. 检查 Python ≥ 3.12（VapourSynth wheel 要求），创建 `.venv`
2. `pip install -r requirements.txt`（numpy、onnx）
3. 从官方 GitHub Release 下载 **VapourSynth R79**（portable zip 内含 cp312 wheel）并安装
4. **下载模型 + vsmlrt 后端**（`fetch_models.py`，约 930MB）：
   - `vsmlrt-windows-x64-generic-gpu`（843MB）：RealESRGAN/CUGAN/waifu2x 全部 SR 模型
     + vsort（DirectML 后端：onnxruntime + DirectML.dll）
   - `external-models` 的 5 个新版 RIFE 模型（v4.15_lite / v4.17_lite / v4.22_lite /
     v4.26 / v4.26_heavy，约 90MB）
5. 下载 **mpv**（shinchiro 最新静态构建，解压到 `runtime\mpv\`，配套的
   `portable_config\` 已在仓库内）
6. **ffmpeg**：优先使用系统 PATH 里已安装的 ffmpeg；没有则从 gyan.dev 自动下载到
   `runtime\ffmpeg\`
7. 复制 `python3.dll` / `python312.dll` 到 `.venv\` 根（VSScript 探测需要），
   生成 vapoursynth 配置，最后跑 `python overfps.py gpu` 验证

完成后：`python overfps.py menu`。

## 可选参数

```
python setup.py --skip-models   # 已有 models/ 时跳过下载
python setup.py --skip-mpv      # mpv 稍后手动放置
python setup.py --skip-ffmpeg   # ffmpeg 用 PATH 里的
```

## 组件来源（均官方）

| 组件 | 来源 |
|---|---|
| VapourSynth R79 | github.com/vapoursynth/vapoursynth releases（wheel 在 portable zip 内） |
| vsmlrt 后端 + SR 模型 | github.com/AmusementClub/vs-mlrt releases（v15.16 generic-gpu 包） |
| RIFE 新模型 | 同上，external-models release |
| mpv | github.com/shinchiro/mpv-winbuild-cmake releases（x86_64 静态构建） |
| ffmpeg | gyan.dev release essentials，或系统 PATH |

## 环境要求

- **Python 3.12+**（Windows）
- **NVIDIA 显卡**（推理走 DirectML，本机 RTX 4060 实测；AMD 也可试，Intel 核显很慢）
- 磁盘：模型 + venv + 运行时约 2.5GB；首次安装需下载约 1.1GB

## 手动部署（不想用 setup.py 时）

按上面来源表手动下载解压到对应位置即可；模型目录结构必须为：

```
models/
├── rife/        # RIFE 主模型 rife_v4.22_lite.onnx 等
├── rife_v2/     # RIFE 合并模型 (与主模型成对, 否则报 "expects 7 input planes")
├── RealESRGANv2/  cugan/  waifu2x/  dpir/
```

> 注意：`runtime\vsmlrt\scripts\vsmlrt.py` 已升级到 v15.16 并打补丁支持
> `VSMLRT_MODELS_PATH` 环境变量（overfps.py 自动注入为项目 `models\` 目录）。
> RIFE 主模型与 rife_v2 合并模型必须来自同一版本，混用会报错。

## 离线/无网环境

把本机原 `.venv\` 与 `models\` 目录整个复制过去即可（最省事）；模型也可从
`downloads_backup.7z`（根目录备份包）中的 `vsmlrt-models.7z` 解压。
