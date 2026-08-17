# OverFPS 架构设计

> 本文档对应需求 4/5: 以 `D:\Project\Repo\OverFPS` 为唯一根目录的架构方案。
> 其中"目标架构 v2"部分目前是**建议**，确认后再执行迁移。

## 1. 根目录原则

- `D:\Project\Repo\OverFPS` 是唯一根目录（ROOT），所有路径以 `ofps.py` 所在目录为锚，禁止硬编码绝对路径。
- E 盘 Waifu2x 资源**只读**：模型只用复制，从不写入/修改（用户红线）。
- 一切入口统一走 `python ofps.py`（venv 自动重执行），不引入 bat/ps1。
- 全部 UTF-8（中文路径/字幕安全）。

## 2. 现状（v1，可工作）

```
OverFPS/
├── ofps.py               # ★ 唯一入口 (菜单/play/render/render-sr/bench/gpu)
├── config.json           # 模型/超分/显卡/缓冲参数
├── downloads_backup.7z   # 安装包/模型源备份 (原 downloads/ 已压缩, 1.5GB)
├── .venv/                # Python 3.12 + VapourSynth + onnxruntime + 插件/模型
├── realtime-interp/      # 运行时: mpv / ffmpeg / vsmlrt / shaders / vpy 脚本
│   ├── mpv/mpv.exe + portable_config/ (mpv.conf, input.conf, scripts/*.lua)
│   ├── ffmpeg/ffmpeg.exe
│   ├── vsmlrt/           # vsmlrt.py + vsncnn.dll + vsort.dll
│   ├── shaders/          # Anime4K glsl
│   └── scripts/          # play.vpy 实时 / render.vpy 离线 / bench_rife.vpy / list_subs.py
├── tests/                # 无头回归: 同步探针 / 按键 / keydump
├── video/                # 用户测试视频 (勿删)
└── tools/7zr.exe
```

## 3. 目标架构 v2（建议，待确认）

按"逻辑 / 运行时 / 管线 / 资源"四层分离，为后续可视化解码铺路：

```
OverFPS/
├── ofps.py                    # 入口薄壳: ensure_venv + 分发 (保持根目录, 支持拖放)
├── config.json
├── downloads_backup.7z        # 备用资源
├── ofps/                      # ★ 逻辑层 (纯 Python, 无二进制, 可单测)
│   ├── __init__.py
│   ├── cli.py                 # 子命令/参数解析
│   ├── config.py              # config.json 读写
│   ├── gpu.py                 # DXGI 探测/独显选择
│   ├── player.py              # mpv 启动: 命令行 + OFPS_*/VS_* 环境变量
│   ├── render.py              # 离线渲染: vspipe + ffmpeg
│   ├── bench.py               # 基准测试
│   └── pipeline.py            # vpy 脚本"参数化生成" (为可视化解码铺路)
├── runtime/                   # ★ 运行时层 (只读使用, 不手改)
│   ├── mpv/                   # mpv.exe + portable_config/ (mpv.conf, input.conf, scripts/*.lua)
│   ├── ffmpeg/
│   ├── vsmlrt/
│   └── shaders/
├── pipelines/                 # ★ 管线层 (VapourSynth 脚本)
│   ├── play.vpy               # 实时: 解码→RGBH→对齐→RIFE→超分→显示
│   ├── render.vpy             # 离线
│   └── bench.vpy
├── assets/                    # 字体/图标 (预留)
├── tests/                     # 无头回归测试
├── video/                     # 用户素材
└── .venv/
```

**迁移映射**（执行时仅移动，不改内容）：
`realtime-interp/mpv` → `runtime/mpv`；`ffmpeg` → `runtime/ffmpeg`；
`vsmlrt` → `runtime/vsmlrt`；`shaders` → `runtime/shaders`；
`realtime-interp/scripts/*.vpy` → `pipelines/`；`list_subs.py` → `ofps/` 或 `scripts/`。
`ofps.py` 内所有 `APP = realtime-interp` 的引用改为按新目录映射（集中在常量区，改动面小）。

## 4. 未来：可视化解码设计（需求 5 的落地路径）

目标：让"解码链路"可见——用户能看到 源→解码→转RGB→对齐→RIFE→超分→输出 每段的
实时帧率、耗时、分辨率、GPU 占用。

- **管线参数化**（第一步）：`pipeline.py` 把 play.vpy/render.vpy 从手工模板改为
  参数生成（节点列表可配置：`[decode, convert, align, rife, sr, out]`），
  每个节点支持 `probe=True` 时输出该段的元数据（耗时/帧率/分辨率）。
- **`ofps.py diag` 子命令**：用 vspipe 无头跑管线，收集各节点耗时/帧率 → JSON。
- **本地 Web 仪表盘**（远期）：`ofps.py dashboard` 起本地 http 服务，实时读取
  mpv/vspipe 日志与 GPU 计数器，浏览器展示链路状态。逻辑层与运行时层分离正是为此
  准备的：逻辑可独立于 mpv 测试，运行时只做播放/渲染。
- **约束**：所有新节点保持"路径以 ROOT 为锚 + 全 UTF-8 + 统一入口"。

## 5. 环境变量与命名规范

- `VS_*`：VapourSynth 脚本读取（VS_INTERP/VS_MODEL/VS_SCALE/VS_SR/VS_SR_MODEL/VS_GPU/VS_FP16）
- `OFPS_*`：mpv lua 脚本读取（OFPS_MODEL/OFPS_SR/OFPS_BUFFERED/OFPS_CONCURRENT/OFPS_SHADER_UPSCALE/OFPS_INTERP）
- 快捷键全部在 `portable_config/scripts/*.lua` 中注册（input.conf 只留注释）
- 测试脚本一律无头运行（`--vo=null`），不得弹窗打扰
