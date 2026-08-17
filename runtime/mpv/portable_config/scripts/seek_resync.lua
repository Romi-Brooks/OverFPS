-- OverFPS 跳转音画强制重同步 (用户要求: 允许卡顿, 必须保证音画同步)
-- 机制: 跳转完成后等待 VS 管线 warmup (~2s), 检查 avsync;
--       若偏差 > 0.15s 且未超过重试上限, 强制重新 seek 到当前播放位置
--       让音频/视频从同一位置重新开始 (代价: 一次短暂停顿, 换取同步)
local armed = false
local rescues = 0
local MAX_RESCUES = 3

mp.register_event("seek", function()
    armed = true
end)

mp.register_event("playback-restart", function()
    if not armed then return end
    armed = false
    mp.add_timeout(2.0, function()
        local av = mp.get_property_number("avsync")
        local tp = mp.get_property_number("time-pos")
        if av and tp and math.abs(av) > 0.15 and rescues < MAX_RESCUES then
            rescues = rescues + 1
            mp.osd_message(string.format("检测到音画偏差 %.2fs, 强制重同步...", av), 2.5)
            mp.commandv("seek", tp, "absolute")
        end
    end)
end)

mp.register_event("end-file", function()
    rescues = 0
    armed = false
end)
