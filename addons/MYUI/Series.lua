-- MYUI 系列核心：把本系列的模块登记进 EllesmereUI 的侧边栏。
--
-- 为什么这件事必须在核心、而不能在功能插件里：
--
-- EUI 的侧边栏行只认 `EllesmereUI._addonInfoByFolder` 这张表，而表里的条目是
-- **谁加载谁写**。功能插件被行右边的电源按钮禁用之后，下次重载它**不再加载**，
-- 于是它自己没法把行写回去——表现就是"禁用之后整行消失，再也点不回来"。
--
-- EUI 自家的模块没有这个问题，因为它的名册是写死在核心里的静态清单
-- （`ADDON_ROSTER`）：模块没加载也照样在册，行在渲染时按
-- `info.alwaysLoaded or IsAddOnLoaded(info.folder)` **实时**算出启用与否。
-- 所以核心只要加载，行就一直在册；功能插件加载与否只决定它置灰与否。
--
-- 本文件就是 MYUI 系列的对应名册。新增功能插件时在 MYUI.SERIES 里加一行即可，
-- EUI 那边一个字都不用改。
--
-- 两个字段缺一不可：
--   `_addonInfoByFolder[folder] = { folder, display }`  → 决定"有没有这一行"
--   `ADDON_GROUPS` 里对应分组的 members 里加上 folder   → 决定"这行挂在哪个分组下"
--
-- 分组的**显示顺序就是 `ADDON_GROUPS` 的数组顺序**，所以本系列是插在最前面的
-- （EUI 自己的独立版构建也是这么把自己那个分组插到第 1 位的）。
--
-- **不设 alwaysLoaded**：那是"不提供电源按钮"的意思，不是"行常驻"。
-- 设了它反而会让被禁用的行显示成启用、并把电源按钮藏起来。

local MYUI = _G.MYUI or {}
_G.MYUI = MYUI

MYUI.GROUP_KEY = "myui"
MYUI.GROUP_LABEL = "MYUI"

-- 系列名册。folder 是插件目录名，display 是侧边栏上显示的名字。
MYUI.SERIES = {
    { folder = "MYUI_CrosshairHUD", display = "准星HUD" },
}

local function EUI()
    return rawget(_G, "EllesmereUI")
end

-- 幂等：可以反复调用。EUI 没装就静默返回 false——本系列整体依赖 EUI，
-- 没有它时这里什么都不该发生。
function MYUI.InjectSidebar()
    local api = EUI()
    if not (api and api._addonInfoByFolder and api.ADDON_GROUPS) then
        return false
    end

    local group
    for _, candidate in ipairs(api.ADDON_GROUPS) do
        if candidate.key == MYUI.GROUP_KEY then group = candidate break end
    end
    if not group then
        group = { key = MYUI.GROUP_KEY, label = MYUI.GROUP_LABEL, members = {} }
        table.insert(api.ADDON_GROUPS, 1, group)
    end

    -- 本系列排在侧边栏最上面：EUI 就是按 ADDON_GROUPS 的数组顺序渲染的。
    -- 无条件钉一次，而不是只在新建时插队——分组若已存在（比如别处先建过一行），
    -- 也要把它挪上来。
    for i, candidate in ipairs(api.ADDON_GROUPS) do
        if candidate == group and i ~= 1 then
            table.remove(api.ADDON_GROUPS, i)
            table.insert(api.ADDON_GROUPS, 1, group)
            break
        end
    end

    local function InGroup(folder)
        for _, member in ipairs(group.members) do
            if member == folder then return true end
        end
        return false
    end

    for _, entry in ipairs(MYUI.SERIES) do
        if not api._addonInfoByFolder[entry.folder] then
            api._addonInfoByFolder[entry.folder] = {
                folder = entry.folder,
                display = entry.display,
            }
        end
        -- 本插件与 EUI 档案无关（配置独立存放），没有可同步的档案数据，
        -- 也就没有同步图标存在的理由。
        if api._syncExempt then api._syncExempt[entry.folder] = true end
        if not InGroup(entry.folder) then
            group.members[#group.members + 1] = entry.folder
        end
    end
    return true
end

-- 注入必须早于用户首次打开 EUI 面板（行只在首次建面板时创建），PLAYER_LOGIN
-- 时 EUI 的表格早已就位。核心自己不依赖 EUI，所以不能靠加载顺序，只能在这里补。
local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterAllEvents()
    MYUI.InjectSidebar()
end)
