# OverFPS · 视频补帧 / 超分（统一 Python 入口）

把视频**拖到入口**，立即以 **2 倍帧率**播放（23.976fps → 47.95fps），基于 **mpv + VapourSynth + RIFE（ONNX Runtime / DirectML）**，本机 RTX 4060 Laptop 实测。

> PowerShell / bat 方案已全部退役：入口统一为 `overfps.py`，运行环境为独立虚拟环境 `.venv`，不污染系统 Python。
> 架构设计见 `..\ARCHITECTURE.md`（根目录原则 + 未来可视化解码规划）。

---

## 一、唯一入口：`overfps.py`

```
python overfps.py                             交互式菜单（显卡/插帧/模型/超分/视频 → 实时 or 离线）
python overfps.py "视频.mp4"                  直接播放（等效 play，自动选独显）
python overfps.py play "视频.mp4" [选项]       补帧/超分播放
python overfps.py gpu                         列出显卡（DXGI 索引 | 名称 | 显存）
python overfps.py bench "视频.mp4" [选项]      基准：补帧速度（不产文件）
python overfps.py render "输入" [输出] [选项]      离线渲染：补帧 / 超分 / 组合
python overfps.py render-sr "输入" [输出] [选项]   离线渲染：补帧 + 超分（默认 RealESRGAN）
```

play / render / bench 通用选项：

| 选项 | 说明 |
|---|---|
| `--model v4_22_lite` | RIFE 模型：`v4_26_heavy` / `v4_26` / `v4_22_lite`(默认) / `v4_17_lite` / `v4_15_lite` / `v4_6` |
| `--scale 1.0` | 光流处理分辨率比例（`v4_6` 可用 `0.5` 提速） |
| `--sr none` | 超分引擎：`none`(默认) / `anime4k`(仅实时) / `realesrgan` / `cugan` / `waifu2x` |
| `--sr-model 2` | realesrgan: `xsx2`/`xsx4`/`v3`；cugan/waifu2x: 倍率 `2/3/4` |
| `--gpu auto` | 推理显卡：`auto`(自动选独显) / 设备号 `0|1|2` |
| `--no-interp` | 关闭插帧（纯超分） |
| `--sub x.ass` | 手动指定外挂字幕文件（play） |
| `--frames N` / `--start S` | （render/bench）帧数 / 起始秒 |
| `--mode fast` | （render）画质模式：`fast`=极速(降分辨率补帧) / `balanced`=均衡(默认) / `quality`=质量(重模型) |
| `--work-h 1080` | （render）强制处理高度（0=原分辨率，高级） |
| `--crf 18` / `--preset medium` / `--codec libx264` | （render）编码画质/预设/编码器（可 `libx265`） |
| `--folder 目录` / `--overwrite` | （render）批量渲染整个目录；覆盖已存在输出 |
| `--burn-sub 字幕.srt` / `--burn-size 22` | （render）把字幕烧录进画面（libass，微软雅黑） |

**自由组合示例：**
```
python overfps.py play "a.mp4"                            # 仅插帧 (默认)
python overfps.py play "a.mp4" --sr anime4k               # 插帧 + Anime4K 实时超分
python overfps.py play "a.mp4" --sr realesrgan --sr-model v3   # 插帧 + RealESRGAN
python overfps.py play "a.mp4" --no-interp --sr cugan     # 仅超分 (关闭插帧)
python overfps.py play "a.mp4" --gpu 0 --sr anime4k       # 指定显卡 + 组合
python overfps.py play "a.mp4" --sub "字幕.ass"           # 手动指定字幕
python overfps.py bench "a.mp4" --model v4_26 --frames 240  # 对比模型速度
```

**离线渲染（不需要实时，慢慢跑高质量）：**
```
python overfps.py render "a.mp4"                          # 补帧 2x，保留音频
python overfps.py render "a.mp4" out.mkv --sr cugan       # 补帧 + CUGAN 超分
python overfps.py render "a.mp4" --no-interp --sr realesrgan --sr-model v3   # 纯超分不插帧
python overfps.py render "a.mp4" --frames 600 --start 120 # 只渲染 120s 起的 600 帧
python overfps.py render-sr "a.mp4"                       # 补帧 + RealESRGAN(默认)
python overfps.py render "a.mp4" --codec libx265 --crf 22 # HEVC 编码
python overfps.py render --folder "D:\视频目录"            # 批量渲染整个目录 (自动跳过已有输出)
python overfps.py render "a.mp4" --burn-sub "字幕.ass"    # 把字幕烧录进画面
python overfps.py render "a.mp4" --mode fast              # 极速模式 (4K 约 12fps 源)
python overfps.py render "a.mp4" --mode quality           # 质量模式 (v4_26_heavy 全分辨率)
```
> 输出自动保留原音频（转 AAC 保证兼容），部分渲染时音频按视频长度截断；默认 2x 帧率。
> 渲染中显示实时进度条（帧数/百分比/fps/剩余时间）；批量模式逐文件进度 + 汇总。
> `--burn-sub` 与 `--start/--frames` 组合时字幕按片段时间轴（从 0 起）渲染。

**三档画质模式（4K 源实测，RTX 4060）：**

| 模式 | 做法 | 4K 速度 | 适合 |
|---|---|---|---|
| `fast` 极速 | 降到 1080p 补帧(v4_6+半光流) → ffmpeg 放大回原分辨率 | ~12 fps 源（一集约 50 分钟） | 快速出片 |
| `balanced` 均衡 | 当前模型全分辨率直接跑 | ~0.5 fps（一集约 19 小时） | 2K 以下 |
| `quality` 质量 | v4_26_heavy 全分辨率光流（4K 自动降 v4_26 防显存爆） | ≤1080p ~16fps；4K 很慢 | 1080p 细节至上 |

> 交互式菜单（`python overfps.py`）里选完显卡/模型/超分/视频路径后，会再问"处理方式
> (实时/离线)"和"离线画质模式 (极速/均衡/质量)"，共用同一套配置。

`config.json` 持久化（含默认值）：

| 键 | 默认 | 说明 |
|---|---|---|
| `model` / `scale` / `sr` / `sr_model` | v4_22_lite / 1.0 / none / 2 | 插帧与超分参数 |
| `gpu` | auto | 推理设备 |
| `fp16` | 1 | 半精度加速 |
| `buffered` / `concurrent` | 8 / 4 | mpv vapoursynth 缓冲/并发（越大越顺滑但延迟越高；跳转卡顿可试 4/2） |
| `osd` | 1 | 左上角 FPS/延迟 OSD（`1`开/`0`关；播放中 `Ctrl+d` 随时切换） |
| `auto_res` | 1 | 分辨率感知：1080p 自动切 `v4_6`+半分辨率光流（否则 65% 丢帧严重卡顿） |

---

## 二、播放窗口快捷键

| 键 | 功能 |
|---|---|
| `Ctrl+i` | 开/关插帧（关=原帧率；重开需 ~2s 加载模型） |
| `Ctrl+s` | 开/关 Anime4K 超分 shader |
| `Ctrl+d` | 开/关左上角 **FPS/延迟 OSD** |
| `Ctrl+l` | **手动加载字幕**（扫描同目录 + `subs\`） |
| `v` / `Shift+v` | 循环字幕轨道 / 字幕显隐 |
| `.` `,` | 逐帧前进 / 后退 |
| `Ctrl++` / `Ctrl+-` | 音画微调 ±0.1s（手动补救，mpv 默认） |

> `Ctrl+s` 覆盖了 mpv 默认的"截图"键；需要截图可改用 `s`（mpv 默认截图当前帧）。

---

## 三、左上角 FPS / 延迟 OSD（需求 1）

`Ctrl+d` 开/关；`config.json` 的 `osd` 键控制默认开关。显示：

```
插帧 v4_22_lite x2  |  超分 cugan
源 23.98 fps  ->  输出 47.95 fps
管线延迟 ≈ 334 ms
```

**全部是实测/实时数据，不是声明值**：
- **源帧率**：由 `play.vpy` 在滤镜内逐帧实测（VFR 感知——帧时长波动 >2% 会标注 `(VFR)`，数字随内容每秒变化）
- **输出帧率**：mpv 滤镜链实测（`estimated-vf-fps`，随负载波动）
- **延迟** = 缓冲帧数/输出fps + 并发帧数/源fps，用上述实测值计算——管线变慢时数字会真实变大
- 插帧被 `Ctrl+i` 关掉后自动显示"插帧: 关 (原始帧率)"

---

## 四、字幕加载的三种方式（需求 2）

1. **自动**：外挂字幕放视频同目录且同名（`a.mp4` + `a.srt`），或放 `subs\` 子目录
   （`sub-auto=fuzzy`），自动加载；内嵌字幕轨道自动可用。
2. **手动**：播放中按 **`Ctrl+l`**，扫描当前视频同目录 + `subs\`，加载所有未加载的
   `.srt/.ass/.ssa/.sub/.vtt`（中文路径安全，UTF-8）。
3. **启动时指定**：`--sub "字幕.ass"`；也可以直接把字幕文件**拖进播放窗口**。
4. 字体已设微软雅黑（`mpv.conf`）。

---

## 五、双显卡：自动找最佳 / 手动指定（需求 3）

- **自动（推荐）**：`--gpu auto` 通过 DXGI 枚举适配器自动挑独显，实测正确识别
  `#1 = RTX 4060 Laptop`（核显 #0/#2，另有虚拟显示器 #3）。
- **手动**：`--gpu 0|1|2` 或菜单选择，写入 `config.json`。
- **独显直连后**：DXGI 列表会变化（独显可能变 #0），`auto` 自动适配；
  手动指定过旧设备号的话，把 `config.json` 的 `gpu` 改回 `"auto"` 即可。
- 本机 DXGI vtable 槽位/描述偏移非标准，已做槽位扫描 + 双布局解析，换机兼容。

---

## 六、本机实测性能（RTX 4060 Laptop 8GB，DirectML fp16）

| 模型 | 720p 输出fps | 1080p | 24→48fps 实时？ |
|---|---|---|---|
| v4_26_heavy | 37.4 | 15.6 | ❌ |
| v4_26 | 55.8 | 21.5 | ✅ 720p |
| **v4_22_lite（默认）** | **59.7** | 25.3 | ✅ 720p |
| v4_17_lite | 69.0 | 31.2 | ✅ 720p |
| v4_15_lite | 69.3 | 28.4 | ✅ 720p |
| v4_6 + 半分辨率光流 | — | 46.6 | ✅≈1080p（带缓冲） |

> 实时判定线：输出 ≥ 48fps。720p 全系 lite 实时达标；1080p 全质量实时不了（4060 物理限制），
> 用 `--scale` / v4_6 或离线渲染。超分引擎：Anime4K 实时（shader 零开销）；
> RealESRGAN/CUGAN/waifu2x 较重（适合离线或低帧率预览）。
> 复测：`python overfps.py bench "视频" --model v4_22_lite --frames 240`。

> **重要（"MKV 卡顿"结论）**：真实窗口丢帧回归测试（`tests\drop_test.py`）证明卡顿与容器无关——
> 720p（MP4/MKV/Hi10P/HEVC10bit）全部 **0 丢帧**；**1080p 丢帧 65.5%**（MP4 与 MKV 完全一样）。
> 你的 MKV 卡顿 = 它是 **1080p**，全质量 RIFE 只有 ~21fps < 48fps 实时线。
> **已内置自动适配**：`overfps.py` 探测源分辨率，1080p 自动切换 `v4_6 + 半分辨率光流`
> （实测 0 丢帧）；`config.json` 的 `auto_res=0` 可关闭（关闭后只警告不切换）。

---

## 七、目录结构

```
OverFPS\  (根目录)
├─ overfps.py                   ★ 唯一入口 (播放/渲染/基准/菜单)
├─ setup.py                  一键部署 (venv + 依赖 + 模型 + mpv/ffmpeg)
├─ fetch_models.py           模型/后端下载安装 (RIFE + SR + vsort)
├─ requirements.txt          Python 依赖 (numpy / onnx)
├─ config.json               用户配置
├─ models\                   模型目录 (fetch 下载, 不入库; rife/ + rife_v2/ + SR)
├─ ARCHITECTURE.md           架构设计（v2 建议 + 可视化解码规划）
├─ .venv\                    虚拟环境 (VapourSynth + 插件/后端)
├─ runtime\
│  ├─ mpv\                   mpv.exe + portable_config\ (mpv.conf / input.conf / scripts\*.lua)
│  ├─ ffmpeg\                ffmpeg（离线渲染编码; 无则用 PATH）
│  ├─ scripts\               play.vpy 实时 / render.vpy 离线 / bench_rife.vpy / list_subs.py
│  ├─ vsmlrt\scripts\vsmlrt.py   vsmlrt v15.16 (已打补丁: VSMLRT_MODELS_PATH)
│  ├─ shaders\               Anime4K 实时超分 shader
│  └─ launchers\             （可放测试文件，脚本已全部退役）
├─ tests\                    无头回归 + 合成测试样片 (demo.mp4 / demo_4k.mp4)
└─ video\                    本地素材（勿上传）
```

> **部署**：克隆后 `python setup.py` 一键完成（详见 `SETUP.md`）。模型约 930MB 自动下载。

## 八、已知问题

1. **ncnn(Vulkan) 后端在本机崩溃**（访问冲突）→ 统一用 DirectML。换驱动/显卡后可改回。
2. **CUDA 后端暂不可用**：驱动 572.83 低于 CUDA 13 runtime 要求；升级驱动到 580+ 后可
   改用 `ORT_CUDA`（预计再快 30-50%）。
3. 启动 ~2s 模型加载；跳转时 VS 管线需重新填缓冲（约 0.2-0.5s 短暂停顿属正常）。
   跳转音画同步已修复：`video-sync=audio` + `seek_resync.lua` 兜底（跳转后检测到偏差
   >0.15s 自动强制重同步，允许短暂卡顿但保证最终同步）。
4. 默认按 BT.709/limited 处理色彩；老 DVD(601)/HDR(2020) 会偏色（已知限制）。
5. E 盘 waifu2x-extension 目录未被改动；所有模型为复制副本。
6. **1080p 全质量插帧是 4060 物理极限之外**（~21fps）：已自动降级 v4_6+半分辨率光流
   （≈46fps 实时）；想要 1080p 全质量请用离线渲染 `render-sr`/`render`。
