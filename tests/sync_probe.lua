-- 同步探针: 持续采样 avsync, 在 1s 和 8s 各做一次跳转 (15s / 45s, 适配 60s 样片)
mp.add_periodic_timer(0.1, function()
    local ap = mp.get_property_number("audio-pts")
    local av = mp.get_property_number("avsync")
    local tp = mp.get_property_number("time-pos")
    mp.msg.log("info", string.format(
        "PROBE t=%.2f ap=%s avsync=%s",
        tp or -1,
        ap and string.format("%.3f", ap) or "-",
        av and string.format("%.3f", av) or "-"))
end)
mp.add_timeout(1.0, function() mp.commandv("seek", 15, "absolute") end)
mp.add_timeout(8.0, function() mp.commandv("seek", 45, "absolute") end)
