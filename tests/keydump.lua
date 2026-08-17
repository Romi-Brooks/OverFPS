-- 测试工具: 打印当前 mpv 所有 Ctrl 组合键绑定 (查冲突)
local b = mp.get_property_native("input-bindings") or {}
local out = {}
for _, e in ipairs(b) do
    if e.key and e.key:lower():find("ctrl") then
        out[#out + 1] = string.format("%-10s => %s  (%s)", e.key, e.cmd or "", e.comment or "")
    end
end
table.sort(out)
print("CTRLBINDS_BEGIN")
for _, l in ipairs(out) do print(l) end
print("CTRLBINDS_END")
mp.commandv("quit")
