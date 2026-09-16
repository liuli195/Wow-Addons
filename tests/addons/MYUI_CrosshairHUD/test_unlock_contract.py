"""解锁元素契约的离线测试（票据 06 的契约，在票据 08 补上回归）。

**为什么必须离线测**：这条契约里最贵的几项在实机只能靠"进解锁模式看一眼"发现，
而看的人未必知道该看什么。三处已经踩过或差点踩到的地方，都能在这里钉死：

- **不许设 `noResize`。** EUI 把齿轮面板里的宽度／高度／**X/Y 位置**几行全放在
  `if canResize and elem then` 块里（`EUI_UnlockMode.lua`）。当初为了绕开尺寸匹配
  的缩放缺陷设上了 `noResize`，代价是把 X/Y 输入一起藏掉——绕开问题的同时把功能
  也绕没了。正确做法是启用尺寸并给出合理语义，再用 `matchUnavailable` 关掉匹配。
- **`getSize` 永远返回数字。** 未创建框体时返回 nil 会让 EUI 的尺寸判断直接报错
  （票据 06 结论）。这里连"没有框体"这条路径一起断言。
- **齿轮里的「元素选项」跳转**只认 `_ELEMENT_SETTINGS_MAP`，而且页面名必须是本模块
  声明过的页面之一——两处任一处对不上，那一项就静默不出现。

harness 以零参数 `loadfile` 依次加载四个模块，再调用 `NS.Mount()`——与实机同一段
装配路径，因此断言的是真实装配结果而不是某个局部函数。
"""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/MYUI_CrosshairHUD"


HARNESS = r'''
local dir = assert(arg[1])

----------------------------------------------------------------------
-- 纹理与框体 mock：Elements.Create 会用到的部分
----------------------------------------------------------------------
local function NewTexture()
    local t = {}
    function t:SetTexture() end
    function t:SetSize() end
    function t:SetPoint() end
    function t:SetAllPoints() end
    function t:AddMaskTexture() end
    function t:SetShown() end
    function t:SetVertexColor() end
    function t:SetRotation(v) t.rotation = v end
    return t
end

local frame
function CreateFrame()
    local f = {}
    function f:CreateTexture() return NewTexture() end
    function f:CreateMaskTexture() return NewTexture() end
    function f:SetSize(w, h) f.width, f.height = w, h end
    function f:SetPoint() end
    function f:ClearAllPoints() end
    function f:SetFrameStrata() end
    function f:SetShown() end
    function f:GetWidth() return f.width or 0 end
    function f:GetHeight() return f.height or 0 end
    function f:GetEffectiveScale() return 1 end
    function f:RegisterEvent() end
    -- 与读数 harness 同一套校验：真客户端对单位事件有白名单，注册了非单位事件
    -- 会在加载期直接抛错、中断整个文件，而空函数 mock 一声不吭
    function f:RegisterUnitEvent(event, unit)
        assert(type(event) == "string" and event:sub(1, 5) == "UNIT_",
            "RegisterUnitEvent 收到了非单位事件：" .. tostring(event))
        assert(unit == "player", "本插件只注册 player 单位")
    end
    function f:UnregisterAllEvents() end
    function f:SetScript() end
    function f:GetFrameLevel() return 1 end
    return f
end

UIParent = { GetEffectiveScale = function() return 1 end }
Enum = { PowerType = { RunicPower = 6 }, LuaCurveType = { Linear = 0 } }
SlashCmdList = {}
C_AddOns = { GetAddOnMetadata = function() return "test" end,
             IsAddOnLoaded = function() return true end }
C_Timer = { After = function() end, NewTicker = function() return {} end }
function GetTime() return 100 end
function InCombatLockdown() return false end
function print() end
function issecretvalue() return false end
function GetRuneCooldown(index) return index, 10, index <= 2 end
C_CurveUtil = { CreateCurve = function()
    local c = { points = {} }
    function c:SetType() end
    function c:AddPoint(x, y) self.points[#self.points + 1] = { x = x, y = y } end
    function c:Evaluate(x)
        local p, q = self.points[1], self.points[2]
        return p.y + (q.y - p.y) * ((x - p.x) / (q.x - p.x))
    end
    return c
end }
function UnitHealthPercent(_, _, curve) return curve:Evaluate(1) end
function UnitPowerPercent(_, _, _, curve) return curve:Evaluate(1) end

----------------------------------------------------------------------
-- EllesmereUI mock：只实现本契约用到的入口
----------------------------------------------------------------------
local registeredElements
local api = {
    _modules = {},
    _addonInfoByFolder = {},
    ADDON_GROUPS = {},
    _syncExempt = {},
    _ELEMENT_SETTINGS_MAP = {},
    PP = {
        SnapCenterForDim = function(v) return v end,
        SnapForES = function(v) return v end,
    },
    MakeUnlockElement = function(opts) return opts end,
    RegisterUnlockElements = function(_, list) registeredElements = list end,
}
_G.EllesmereUI = api

----------------------------------------------------------------------
-- 按清单顺序加载并走与实机相同的装配入口
----------------------------------------------------------------------
for _, name in ipairs({ "Logic", "Elements", "Config", "Core" }) do
    assert(loadfile(dir .. "/" .. name .. ".lua"))()
end
local NS = assert(_G.MYUI_CHH)
local Core = assert(NS.Core)
NS.Core.BuildArcCurves()
NS.Elements.Create()          -- 没有框体时 getSize 也得能返回数字，两种情形都测
NS.Mount()

assert(registeredElements, "Mount 应注册解锁元素")
assert(#registeredElements == 1, "本插件只注册一个解锁元素")
local elem = registeredElements[1]

----------------------------------------------------------------------
-- 元素身份
----------------------------------------------------------------------
assert(elem.key == "MYUI_CrosshairHUD", "元素 key 应是插件目录名")
assert(elem.group == "MYUI", "元素应挂在 MYUI 分组下")
assert(type(elem.label) == "string" and elem.label ~= "", "元素要有可读的 label")

----------------------------------------------------------------------
-- **不许设 noResize**：EUI 把 X/Y 位置输入也一起放在 canResize 块里
--
-- 这条是踩过的坑：设了 noResize 之后齿轮面板里就没有 X/Y 了，而配置页又已经
-- 去掉了自建的位置控件——两头都没有，位置就改不了了。
----------------------------------------------------------------------
assert(elem.noResize == nil, "不许设 noResize：它会连齿轮里的 X/Y 输入一起藏掉")

-- 于是必须给出尺寸语义，否则宽度/高度那两行改不动任何东西
assert(type(elem.setWidth) == "function", "要能承接齿轮里的宽度")
assert(type(elem.setHeight) == "function", "要能承接齿轮里的高度")
assert(elem.linkedDimensions == true, "等比缩放的元素，宽高必须联动")

-- 尺寸匹配对等比缩放的框体语义不成立，用官方给的 matchUnavailable 关掉，
-- 而不是用 noResize 一刀切
assert(type(elem.matchUnavailable) == "function", "应给出尺寸匹配不可用的理由")
local reason = elem.matchUnavailable(elem.key)
assert(type(reason) == "string" and reason ~= "", "理由必须是非空字符串")
assert(elem.noSizeMatchTarget == true, "别的元素不许匹配到本元素上")

----------------------------------------------------------------------
-- getSize 永远返回数字（票据 06：返回 nil 会让 EUI 的尺寸判断直接报错）
----------------------------------------------------------------------
local w, h = elem.getSize(elem.key)
assert(type(w) == "number" and type(h) == "number", "getSize 必须返回两个数字")
assert(w == 128 and h == 128, "缩放 1.0 时应报设计稿尺寸，实得 " .. tostring(w))

----------------------------------------------------------------------
-- 宽度／高度改的是整体缩放，且与配置页共用同一个值
----------------------------------------------------------------------
local Config = assert(NS.Config)
local key = elem.key

elem.setWidth(key, 256)
assert(math.abs(Config.Get().scale - 2.0) < 1e-9,
    "宽度 256 → 缩放 2.0，实得 " .. tostring(Config.Get().scale))
w = elem.getSize(key)
assert(w == 256, "改完之后 getSize 必须跟着变，实得 " .. tostring(w))

elem.setHeight(key, 64)
assert(math.abs(Config.Get().scale - 0.5) < 1e-9, "高度 64 → 缩放 0.5")

-- 越界必须钳到滑块的范围，不能因为齿轮那边没限位就跑到范围外
elem.setWidth(key, 9999)
assert(math.abs(Config.Get().scale - (Config.SCALE_MAX or 2.0)) < 1e-9, "超上界应钳位")
elem.setWidth(key, 1)
assert(math.abs(Config.Get().scale - (Config.SCALE_MIN or 0.5)) < 1e-9, "超下界应钳位")
elem.setWidth(key, 0)
assert(math.abs(Config.Get().scale - (Config.SCALE_MIN or 0.5)) < 1e-9, "0 必须被忽略")

----------------------------------------------------------------------
-- 齿轮里的「元素选项」跳转
----------------------------------------------------------------------
local nav = api._ELEMENT_SETTINGS_MAP[key]
assert(nav, "齿轮的「元素选项」只认这张表，缺了它那一项就不出现")
assert(nav.module == "MYUI_CrosshairHUD", "跳转目标模块应是本插件")
local module = api._modules["MYUI_CrosshairHUD"]
assert(module, "模块必须已注册，否则 ShowModule 不会选中它")
local pageOK = false
for _, name in ipairs(module.pages or {}) do
    if name == nav.page then pageOK = true end
end
assert(pageOK, "跳转的页面名必须是本模块声明过的页面之一，实得 " .. tostring(nav.page))

----------------------------------------------------------------------
-- 主开关关闭时必须报告隐藏，否则解锁模式里会残留可拖动的空框
----------------------------------------------------------------------
Config.Get().enabled = true
assert(elem.isHidden(key) == false, "启用时不该报告隐藏")
Config.Get().enabled = false
assert(elem.isHidden(key) == true, "总开关关闭时必须报告隐藏")
Config.Get().enabled = true

io.write("PASS: unlock element contract\n")
'''


def test_unlock_element_contract():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "unlock_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: unlock element contract" in result.stdout
