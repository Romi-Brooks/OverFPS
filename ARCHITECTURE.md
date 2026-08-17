# OverFPS 架构设计

> 本文档对应需求 4/5: 以 `D:\Project\Repo\OverFPS` 为唯一根目录的架构方案。
> 迁移进度：`realtime-interp` → `runtime`、`ofps.py` → `overfps.py`、README 移根 **已完成**；
> 逻辑层拆分（`ofps/` 包）与 `pipelines/` 拆分为**后续建议**。

## 1. 根目录原则

- `D:\Project\Repo\OverFPS` 是唯一根目录（ROOT），所有路径以 `overfps.py` 所在目录为锚；
  vpy/lua 内的路径已改为 `OFPS_ROOT` 环境变量驱动，禁止硬编码绝对路径。
- E 盘 Waifu2x 资源**只读**：模型只用复制，从不写入/修改（用户红线）。
- 一切入口统一走 `python overfps.py`（venv 自动重执行），不引入 bat/ps1。
- 全部 UTF-8（中文路径/字幕安全）。

## 2. 现状（当前结构，可工作）

```
OverFPS/
├── overfps.py               # ★ 唯一入口 (菜单/play/render/render-sr/bench/gpu)
├── setup.py                 # 一键部署 (venv + 依赖 + 模型 + mpv/ffmpeg)
├── fetch_models.py          # 模型/后端下载安装 (RIFE + SR + vsort)
├── requirements.txt         # Python 依赖 (numpy / onnx)
├── README.md                # 使用文档 (根目录)
├── SETUP.md                 # 部署文档
├── config.json              # 模型/超分/显卡/缓冲参数
├── models/                  # 模型目录 (fetch 下载, 不入库; rife/ rife_v2/ SR)
├── .venv/                   # Python 3.12 + VapourSynth + 插件/后端
├── runtime/                 # ★ 运行时层 (二进制 + 配置 + 管线脚本, 只读使用)
│   ├── mpv/                 # mpv.exe + portable_config/ (mpv.conf, input.conf, scripts/*.lua)
│   ├── ffmpeg/              # ffmpeg.exe (无则用 PATH)
│   ├── vsmlrt/scripts/      # vsmlrt.py v15.16 (补丁: VSMLRT_MODELS_PATH)
│   ├── shaders/             # Anime4K glsl
│   └── scripts/             # play.vpy 实时 / render.vpy 离线 / bench_rife.vpy / list_subs.py
├── tests/                   # 无头回归 + 合成样片 (demo.mp4 / demo_4k.mp4)
├── .runtime/                # 运行时数据 (fps_stats.json / 下载缓存, gitignore)
├── video/                   # 本地素材 (gitignore, 勿上传)
└── tools/7zr.exe            # 7-Zip 精简版 (部署解压用)
```

## 3. 目标架构 v2（部分已执行，其余待确认）

按"逻辑 / 运行时 / 管线 / 资源"四层分离，为后续可视化解码铺路：

```
OverFPS/
├── overfps.py                    # 入口: ensure_venv + 分发 (保持根目录, 支持拖放)  ✅ 已执行
├── config.json
├── ofps/                      # ★ 逻辑层 (纯 Python, 无二进制, 可单测)  ← 建议 (未执行)
│   ├── __init__.py
│   ├── cli.py                 # 子命令/参数解析
│   ├── config.py              # config.json 读写
│   ├── gpu.py                 # DXGI 探测/独显选择
│   ├── player.py              # mpv 启动: 命令行 + OFPS_*/VS_* 环境变量
│   ├── render.py              # 离线渲染: vspipe + ffmpeg
│   ├── bench.py               # 基准测试
│   └── pipeline.py            # vpy 脚本"参数化生成" (为可视化解码铺路)
├── runtime/                   # ★ 运行时层 (只读使用, 不手改)  ✅ 已执行 (原 realtime-interp)
│   ├── mpv/                   # mpv.exe + portable_config/ (mpv.conf, input.conf, scripts/*.lua)
│   ├── ffmpeg/
│   ├── vsmlrt/
│   └── shaders/
├── pipelines/                 # ★ 管线层 (VapourSynth 脚本)  ← 建议 (当前在 runtime/scripts)
│   ├── play.vpy               # 实时: 解码→RGBH→对齐→RIFE→超分→显示
│   ├── render.vpy             # 离线
│   └── bench.vpy
├── assets/                    # 字体/图标 (预留)
├── tests/                     # 无头回归测试
└── .venv/
```

**迁移状态**：
- ✅ `realtime-interp` → `runtime`（mpv/ffmpeg/vsmlrt/shaders/scripts）
- ✅ `ofps.py` → `overfps.py`；README/SETUP 移到根目录
- ✅ 硬编码路径改为 `OFPS_ROOT` 环境变量（overfps.py 注入，vpy/lua 读取）
- ✅ 模型独立到 `models/`（vsmlrt 补丁 `VSMLRT_MODELS_PATH`），部署脚本 `setup.py`/`fetch_models.py`
- ⏳ 逻辑层 `ofps/` 包拆分（当前逻辑仍集中在 overfps.py，可后续按需拆）
- ⏳ `runtime/scripts` → `pipelines/`（语义更清晰，当前已可用）

## 4. 未来：可视化解码设计（需求 5 的落地路径）

目标：让"解码链路"可见——用户能看到 源→解码→转RGB→对齐→RIFE→超分→输出 每段的
实时帧率、耗时、分辨率、GPU 占用。

- **管线参数化**（第一步）：`pipeline.py` 把 play.vpy/render.vpy 从手工模板改为
  参数生成（节点列表可配置：`[decode, convert, align, rife, sr, out]`），
  每个节点支持 `probe=True` 时输出该段的元数据（耗时/帧率/分辨率）。
- **`overfps.py diag` 子命令**：用 vspipe 无头跑管线，收集各节点耗时/帧率 → JSON。
- **本地 Web 仪表盘**（远期）：`overfps.py dashboard` 起本地 http 服务，实时读取
  mpv/vspipe 日志与 GPU 计数器，浏览器展示链路状态。逻辑层与运行时层分离正是为此
  准备的：逻辑可独立于 mpv 测试，运行时只做播放/渲染。
- **约束**：所有新节点保持"路径以 ROOT 为锚 + 全 UTF-8 + 统一入口"。

## 5. 环境变量与命名规范

- `VS_*`：VapourSynth 脚本读取（VS_INTERP/VS_MODEL/VS_SCALE/VS_SR/VS_SR_MODEL/VS_GPU/VS_FP16）
- `OFPS_*`：mpv lua 脚本读取（OFPS_MODEL/OFPS_SR/OFPS_BUFFERED/OFPS_CONCURRENT/OFPS_SHADER_UPSCALE/OFPS_INTERP）
- 快捷键全部在 `portable_config/scripts/*.lua` 中注册（input.conf 只留注释）
- 测试脚本一律无头运行（`--vo=null`），不得弹窗打扰
