# OverFPS 部署说明（克隆仓库后）

本仓库只包含**源码 / 配置 / 脚本**，运行时二进制与模型因体积与 GitHub 限制不纳入版本控制。
从零部署步骤如下。

## 1. 恢复运行时二进制（mpv / ffmpeg）

- **有本机备份**：解压根目录 `downloads_backup.7z`，其中 `mpv.7z`、`ffmpeg.7z` 解出
  `mpv.exe` 放到 `realtime-interp\mpv\`，`ffmpeg.exe` 放到 `realtime-interp\ffmpeg\`。
- **无备份**：从官网下载对应版本：
  - mpv：https://sourceforge.net/projects/mpv-player-windows/files/ （选择 64bit 静态构建，
    与 `realtime-interp\mpv\portable_config\` 配套，0.41+ 均可）
  - ffmpeg：https://www.gyan.dev/ffmpeg/builds/ （release 版，取 `ffmpeg.exe`）
  - 注意：`portable_config\`（mpv.conf / input.conf / scripts\*.lua）已在仓库内，直接使用即可。

## 2. 准备 Python 虚拟环境

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -U pip
```

VapourSynth 与模型依赖（推荐从 `downloads_backup.7z` 恢复，比在线装省事）：
1. 解压 `vapoursynth-portable.zip` 中的 wheel：`pip install vapoursynth-*-win_amd64.whl`
2. 解压 `vsmlrt-scripts.7z` → `realtime-interp\vsmlrt\scripts\vsmlrt.py`
3. 解压 `vsmlrt-vsort.7z` 与 `vsmlrt-vsncnn.7z` → 对应 dll 放入
   `.venv\Lib\site-packages\vapoursynth\plugins\`（vsort 需建 `vsort\` 子目录放运行时）
4. 解压 `vsmlrt-models.7z`（约 850MB）→ 模型放入
   `.venv\Lib\site-packages\vapoursynth\plugins\models\`
5. `python -m vapoursynth config` 生成配置，并把 `python3.dll`、`python312.dll`
   复制到 `.venv\` 根目录（VSScript 探测需要）

> 需要完整运行（含所有模型）时最省事的方式：直接把本机原 `.venv\` 整个复制过来。
> 首次运行请 `python ofps.py gpu` 验证显卡探测，再 `python ofps.py` 进菜单。

## 3. 运行

```bat
python ofps.py menu
```
入口会检测并自动使用 `.venv\Scripts\python.exe` 重新执行。

## 4. 可选：模型/素材放回

- 测试视频放 `video\`（已被 .gitignore 忽略）
- 更新备份：`python ofps.py` 之外，重新压缩 `downloads` 源目录即可（见 ARCHITECTURE.md）
