-- OverFPS 快捷键: 插帧开关 / Anime4K 开关
-- 原写在 input.conf, 改由 lua 统一管理, 以便动态读取 ofps.py 注入的缓冲参数
-- 环境变量: OFPS_BUFFERED / OFPS_CONCURRENT / OFPS_SHADER_UPSCALE (由 ofps.py 注入)
-- 快捷键: Ctrl+i 开/关插帧, Ctrl+s 开/关 Anime4K 超分 shader

local buf = tonumber(os.getenv("OFPS_BUFFERED") or "8")
local con = tonumber(os.getenv("OFPS_CONCURRENT") or "4")
local shader = os.getenv("OFPS_SHADER_UPSCALE")

local vs_spec = string.format(
    "vapoursynth=file=play.vpy:buffered-frames=%d:concurrent-frames=%d", buf, con)

mp.add_key_binding("Ctrl+i", "ofps-interp-toggle", function()
    mp.commandv("vf", "toggle", vs_spec)
    local vf = mp.get_property("vf") or ""
    if vf:find("vapoursynth") then
        mp.osd_message("插帧: 开 (模型加载中 ~2s)", 2)
    else
        mp.osd_message("插帧: 关 (原始帧率)", 1)
    end
end)

mp.add_key_binding("Ctrl+s", "ofps-anime4k-toggle", function()
    if not shader then
        mp.osd_message("本次启动未带 Anime4K 超分 (启动时用 --sr anime4k)", 2)
        return
    end
    mp.commandv("change-list", "glsl-shaders", "toggle", shader)
    mp.osd_message("Anime4K 超分: 已切换", 1)
end)
