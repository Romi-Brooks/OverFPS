-- OverFPS: 手动加载字幕 (Ctrl+l)
-- 扫描当前视频同目录及 subs/ 子目录, 加载尚未加载的外挂字幕
-- 依赖 venv python 小工具 list_subs.py (UTF-8 安全, 支持中文路径)
-- 其他加载字幕方式: ① 拖字幕文件进播放窗口 ② 同目录/同名字幕自动加载

local root = os.getenv("OFPS_ROOT") or "D:/Project/Repo/OverFPS"
local PY = root .. "/.venv/Scripts/python.exe"
local HELPER = root .. "/runtime/scripts/list_subs.py"

local function already_loaded(f)
    local tracks = mp.get_property_native("track-list") or {}
    for _, t in ipairs(tracks) do
        if t.external then
            local ef = t["external-filename"] or t.filename or ""
            if ef == f then return true end
        end
    end
    return false
end

local function load_subs()
    local path = mp.get_property("path")
    if not path or path == "" then
        mp.osd_message("没有正在播放的视频", 1.5)
        return
    end
    local dir = path:match("^(.-)[/\\][^/\\]*$")
    if not dir or dir == "" then dir = "." end
    local res = mp.command_native({
        name = "subprocess",
        args = { PY, "-X", "utf8", HELPER, dir },
        capture_stdout = true,
    })
    if not res or res.status ~= 0 then
        mp.osd_message("字幕扫描失败", 1.5)
        return
    end
    local n = 0
    local names = {}
    for line in (res.stdout or ""):gmatch("[^\r\n]+") do
        local f = line:gsub("^%s+", ""):gsub("%s+$", "")
        if f ~= "" and not already_loaded(f) then
            mp.commandv("sub-add", f)
            n = n + 1
            local base = f:match("([^/\\]+)$") or f
            if #names < 4 then names[#names + 1] = base end
        end
    end
    if n > 0 then
        mp.osd_message("已加载 " .. n .. " 个字幕: " .. table.concat(names, ", "), 3)
    else
        mp.osd_message("没找到新字幕 (同目录 或 subs\\ 下: .srt/.ass/.ssa/.sub/.vtt)", 3)
    end
end

mp.add_key_binding("Ctrl+l", "ofps-load-subs", load_subs)
