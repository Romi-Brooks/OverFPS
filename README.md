# OverFPS · 视频补帧 / 超分
基于 **mpv + VapourSynth + RIFE（ONNX Runtime / DirectML）**

> **部署**：`python setup.py` 一键安装（自动下载模型/运行时，详见 [Docs/SETUP.md](Docs/SETUP.md)）；
> 架构设计见 [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md)。

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

## 三、左上角 FPS / 延迟 OSD

`Ctrl+d` 开/关；`config.json` 的 `osd` 键控制默认开关。显示：

```
插帧 v4_22_lite x2  |  超分 cugan
源 23.98 fps  ->  输出 47.95 fps
管线延迟 ≈ 334 ms
```
- **源帧率**：由 `play.vpy` 在滤镜内逐帧实测（VFR 感知——帧时长波动 >2% 会标注 `(VFR)`，数字随内容每秒变化）
- **输出帧率**：mpv 滤镜链实测（`estimated-vf-fps`，随负载波动）
- **延迟** = 缓冲帧数/输出fps + 并发帧数/源fps，用上述实测值计算——管线变慢时数字会真实变大
- 插帧被 `Ctrl+i` 关掉后自动显示"插帧: 关 (原始帧率)"

---

## 四、字幕加载的三种方式

1. **自动**：外挂字幕放视频同目录且同名（`a.mp4` + `a.srt`），或放 `subs\` 子目录
   （`sub-auto=fuzzy`），自动加载；内嵌字幕轨道自动可用。
2. **手动**：播放中按 **`Ctrl+l`**，扫描当前视频同目录 + `subs\`，加载所有未加载的
   `.srt/.ass/.ssa/.sub/.vtt`（中文路径安全，UTF-8）。
3. **启动时指定**：`--sub "字幕.ass"`；也可以直接把字幕文件**拖进播放窗口**。
4. 字体已设微软雅黑（`mpv.conf`）。

---

## 五、显卡：自动找最佳 / 手动指定

- **自动（推荐）**：`--gpu auto` 通过 DXGI 枚举适配器自动挑独显，实测正确识别
  `#1 = RTX 4060 Laptop`（核显 #0/#2，另有虚拟显示器 #3）。
- **手动**：`--gpu 0|1|2` 或菜单选择，写入 `config.json`。
- **独显直连后**：DXGI 列表会变化（独显可能变 #0），`auto` 自动适配；
  手动指定过旧设备号的话，把 `config.json` 的 `gpu` 改回 `"auto"` 即可。
- 本机 DXGI vtable 槽位/描述偏移非标准，已做槽位扫描 + 双布局解析，换机兼容。

---