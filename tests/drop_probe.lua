-- 丢帧探针 (真实播放): 播放 ~6s 后报告 mpv 统计的丢帧数
mp.add_timeout(6.0, function()
    local fd = mp.get_property_number("frame-drop-count") or -1
    local vo = mp.get_property_number("vo-drop-frame-count") or -1
    local tp = mp.get_property_number("time-pos") or -1
    print(string.format("DROPPROBE time=%.1f frame_drop=%s vo_drop=%s",
                        tp, fd, vo))
    mp.commandv("quit")
end)
