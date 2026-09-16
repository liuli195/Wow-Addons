"""系列名册的离线测试。

被测的是 `addons/MYUI/Series.lua`——它加载时不触碰任何魔兽接口（EUI 的存在与否
是运行时查的），所以能以零参数 `loadfile` 加载。

**这条测试锁的是一个已经踩过的坑**：侧边栏那一行曾经由功能插件自己注入，结果
用户点行右边的电源按钮禁用本插件后，重载时插件不再加载、行就再也写不回去，
**整行消失且无法恢复**。修法是把名册搬进永不被禁用的核心。

所以断言的核心是：**只加载核心、且功能插件根本没加载时，那一行也必须在册**——
这正是当初会失败的地方。另外两条同样是这次踩出来的：

- **不许设 alwaysLoaded**：EUI 侧那是"不提供电源按钮"的意思，不是"行常驻"；
  设了它会让被禁用的行显示成启用、并把电源按钮藏掉。
- **幂等**：重复注入不能把同一个目录名塞进 members 两次，否则侧边栏会出两行。
"""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
SERIES = ROOT / "addons/MYUI/Series.lua"


HARNESS = r'''
local source = assert(arg[1])

----------------------------------------------------------------------
-- WoW 接口 mock
----------------------------------------------------------------------
local frames = {}
function CreateFrame()
    local frame = { scripts = {} }
    function frame:RegisterEvent() end
    function frame:UnregisterAllEvents() end
    function frame:SetScript(kind, callback) self.scripts[kind] = callback end
    frames[#frames + 1] = frame
    return frame
end

local function FireLogin()
    assert(#frames > 0, "Series.lua 应注册 PLAYER_LOGIN")
    for _, frame in ipairs(frames) do
        if frame.scripts.OnEvent then frame.scripts.OnEvent(frame, "PLAYER_LOGIN") end
    end
end

----------------------------------------------------------------------
-- 没有 EUI：必须静默无操作，且不许报错
----------------------------------------------------------------------
assert(loadfile(source))()
local MYUI = assert(_G.MYUI, "Series.lua 应导出全局 MYUI")
assert(type(MYUI.InjectSidebar) == "function", "应导出 InjectSidebar")
assert(MYUI.InjectSidebar() == false, "没有 EUI 时应返回 false")
FireLogin()                       -- 事件路径上也不许报错

----------------------------------------------------------------------
-- 有 EUI：核心**独自**加载时，系列里每一行都必须在册
--
-- 注意这里没有加载任何功能插件——这正是修好之前会失败的情形。
----------------------------------------------------------------------
local api = {
    _addonInfoByFolder = {},
    -- 先摆一个 EUI 自家的分组：本系列必须插到它前面，而不是追在末尾
    ADDON_GROUPS = { { key = "eui-own", label = "EllesmereUI", members = { "SomeEUIAddon" } } },
    _syncExempt = {},
}
_G.EllesmereUI = api

FireLogin()
for _, entry in ipairs(MYUI.SERIES) do
    local info = api._addonInfoByFolder[entry.folder]
    assert(info, "功能插件没加载，行也必须在册：" .. entry.folder)
    assert(info.folder == entry.folder and type(info.display) == "string",
        "行信息要带 folder 与 display")
    -- alwaysLoaded 会让 EUI 把被禁用的行画成启用、并藏起电源按钮
    assert(info.alwaysLoaded == nil, "不许设 alwaysLoaded")
end

local group
for _, candidate in ipairs(api.ADDON_GROUPS) do
    if candidate.key == MYUI.GROUP_KEY then group = candidate end
end
assert(group, "应建出 MYUI 分组")
assert(group.label == MYUI.GROUP_LABEL, "分组名应是 MYUI")

-- 侧边栏的分组顺序就是这张数组的顺序：本系列必须排在最上面
assert(api.ADDON_GROUPS[1] == group, "MYUI 分组必须排在侧边栏最上面")
assert(api.ADDON_GROUPS[2] and api.ADDON_GROUPS[2].key == "eui-own",
    "EUI 原有分组应顺延到其后，而不是被顶掉")
for _, entry in ipairs(MYUI.SERIES) do
    local found = 0
    for _, member in ipairs(group.members) do
        if member == entry.folder then found = found + 1 end
    end
    assert(found == 1, entry.folder .. " 应恰好属于 MYUI 分组一次，实得 " .. found .. " 次")
end

----------------------------------------------------------------------
-- 幂等：反复注入不能长出第二行，也不能重复建分组
----------------------------------------------------------------------
local groupCount = #api.ADDON_GROUPS
MYUI.InjectSidebar()
MYUI.InjectSidebar()
assert(#api.ADDON_GROUPS == groupCount, "重复注入不许再建分组")
assert(api.ADDON_GROUPS[1] == group, "重复注入后仍应排在最上面")
for _, entry in ipairs(MYUI.SERIES) do
    local found = 0
    for _, member in ipairs(group.members) do
        if member == entry.folder then found = found + 1 end
    end
    assert(found == 1, "重复注入后 " .. entry.folder .. " 仍应只属于分组一次")
end

----------------------------------------------------------------------
-- 分组已存在但不在最前面时，注入要把它挪上去
--
-- 钉的是"保证"而不是"只在新建时插队"：别处若先建过这个分组，它也得上得来。
----------------------------------------------------------------------
table.remove(api.ADDON_GROUPS, 1)
api.ADDON_GROUPS[#api.ADDON_GROUPS + 1] = group
MYUI.InjectSidebar()
assert(api.ADDON_GROUPS[1] == group, "已存在的分组也必须被挪到最上面")

----------------------------------------------------------------------
-- 核心与功能插件各自注入时也必须收敛（功能插件那边有一次幂等兜底调用）
----------------------------------------------------------------------
local infoBefore = api._addonInfoByFolder[MYUI.SERIES[1].folder]
MYUI.InjectSidebar()
assert(api._addonInfoByFolder[MYUI.SERIES[1].folder] == infoBefore,
    "已存在的行信息不许被覆盖重建")

io.write("PASS: series roster\n")
'''


def test_series_roster():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "series_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(SERIES)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: series roster" in result.stdout
