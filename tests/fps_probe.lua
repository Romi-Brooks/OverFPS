-- 测试工具: 打印 OSD 依赖的帧率属性
mp.add_timeout(3.0, function()
    local cfps = mp.get_property_number("container-fps")
    local vfps = mp.get_property_number("estimated-vf-fps")
    print(string.format("FPSPROBE cfps=%s vfps=%s", tostring(cfps), tostring(vfps)))
    mp.commandv("quit")
end)
