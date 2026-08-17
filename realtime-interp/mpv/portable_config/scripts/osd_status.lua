-- OverFPS OSD 状态: 左上角显示 源帧率(实测) / 输出帧率(实测) / 管线延迟
-- 数据来源:
--   源帧率: play.vpy 实测 (OFPS_ROOT/.runtime/fps_stats.json, VFR 感知)
--   输出帧率: mpv estimated-vf-fps (滤镜链实测)
--   延迟: 缓冲帧/输出fps + 并发帧/源fps (用实测值计算, 随负载真实变化)
-- 环境变量 (ofps.py 注入): OFPS_ROOT / OFPS_OSD / OFPS_MODEL / OFPS_SR / OFPS_BUFFERED / OFPS_CONCURRENT
-- 快捷键: Ctrl+d 开/关

local enabled = (os.getenv("OFPS_OSD") or "1") == "1"
local stats_path = (os.getenv("OFPS_ROOT") or "D:/Project/Repo/OverFPS") .. "/.runtime/fps_stats.json"

local function read_stats()
    local f = io.open(stats_path, "r")
    if not f then return nil end
    local s = f:read("*a")
    f:close()
    local src_fps = s:match('"src_fps"%s*:%s*([%d%.]+)')
    local vfr = s:match('"vfr"%s*:%s*(%a+)')
    if not src_fps then return nil end
    return tonumber(src_fps), vfr == "true"
end

-- 当前 vf 链里是否挂着 vapoursynth 补帧 (跟随 Ctrl+i 实时变化)
local function vf_has_vs()
    local vf = mp.get_property("vf")
    return vf ~= nil and vf:find("vapoursynth") ~= nil
end

local function draw()
    if not enabled then
        mp.set_osd_ass(0, 0, "")
        return
    end
    local vfps = mp.get_property_number("estimated-vf-fps") or 0
    local interp_on = vf_has_vs()
    local model = os.getenv("OFPS_MODEL") or "-"
    local sr = os.getenv("OFPS_SR") or "none"
    local sr_disp = (sr == "anime4k") and "Anime4K(渲染)" or sr
    local buf = tonumber(os.getenv("OFPS_BUFFERED") or "8") or 8
    local con = tonumber(os.getenv("OFPS_CONCURRENT") or "4") or 4
    local src_fps, vfr = read_stats()
    if not src_fps or src_fps <= 0 then
        src_fps = mp.get_property_number("container-fps") or 0
        vfr = false
    end
    local style = "{\\an7\\fs13\\bord1.2\\shad0\\1c&HFFFFFF&\\3c&H000000&}"
    local out
    if not interp_on then
        out = style .. "插帧: 关 (原始帧率)\\N" ..
              string.format("源 %s fps%s",
                            src_fps > 0 and string.format("%.2f", src_fps) or "-",
                            vfr and " (VFR)" or "")
    else
        local lat = 0.0
        if src_fps > 0 and vfps > 0 then
            lat = buf / vfps + con / src_fps
        end
        out = string.format("%s插帧 %s x2  |  超分 %s\\N", style, model, sr_disp) ..
              string.format("源 %s fps%s  ->  输出 %.2f fps\\N",
                            src_fps > 0 and string.format("%.2f", src_fps) or "-",
                            vfr and " (VFR)" or "", vfps) ..
              string.format("管线延迟 ≈ %d ms", lat * 1000)
    end
    mp.set_osd_ass(0, 0, out)
end

mp.register_event("file-loaded", draw)
mp.add_periodic_timer(0.5, draw)
mp.add_key_binding("Ctrl+d", "ofps-osd-toggle", function()
    enabled = not enabled
    draw()
    mp.osd_message(enabled and "FPS 显示: 开" or "FPS 显示: 关", 1)
end)
