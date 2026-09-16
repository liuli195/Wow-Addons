"""颜色与透明度的离线测试。

两件事，各锁一个已经出过问题的地方：

1. **职业色的取值链。** 实机现象是"选了职业配色但毫无变化"。根因是 EUI 的颜色缓存
   **以类名令牌为键**，而 `UnitClass` 在受限上下文里交回的是**秘密令牌**——秘密值
   不能当表键，查表直接抛错，于是静默回落到自定义色。修法是补齐取值链，并接受
   "退回 Blizzard 接口拿不到用户自定义的色"这个次要损失。这里逐一断言链条的每一级，
   包括"全都不可用时必须回落到自定义色，绝不能是 nil"。

2. **填充与背景的透明度是两个值。** 合成一个就只能整条一起淡化。断言在渲染层的
   公开入口（`Elements.Apply`）上做——那里是这套契约最高的接缝：喂一张状态表进去，
   看两个纹理各自收到了哪个 alpha。顺带覆盖秘密通道必须原封不动地转交。
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
-- 纹理 mock：记下每条纹理的 sublevel、路径与收到的顶点色
----------------------------------------------------------------------
local textures = {}
local function NewTexture(_, _, _, sub)
    local t = { sub = sub, path = nil, vertex = nil, shown = nil }
    function t:SetTexture(path) t.path = path end
    function t:SetSize() end
    function t:SetPoint() end
    function t:SetAllPoints() end
    function t:AddMaskTexture() end
    function t:SetShown(v) t.shown = v end
    function t:SetRotation() end
    function t:SetVertexColor(r, g, b, a) t.vertex = { r, g, b, a } end
    textures[#textures + 1] = t
    return t
end

local frame
function CreateFrame()
    local f = {}
    function f:CreateTexture(a, b, c, sub) return NewTexture(a, b, c, sub) end
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
    function f:RegisterUnitEvent() end
    function f:UnregisterAllEvents() end
    function f:SetScript() end
    function f:GetFrameLevel() return 1 end
    if not frame then frame = f end
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
function GetRuneCooldown(index) return index, 10, index <= 2 end

-- 秘密值：判为秘密的数值哨兵。颜色通道可能是秘密值，只许原样转交。
local secretNumber = 4242
function issecretvalue(value) return value == secretNumber end

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
-- 颜色取值链的三级来源，测试逐个开关
----------------------------------------------------------------------
local euiColor, euiThrows = nil, false
local blizzardColor, blizzardThrows = nil, false
local raidColors = nil

_G.EllesmereUI = {
    GetClassColor = function()
        if euiThrows then error("table index is nil") end   -- 秘密令牌当表键就是这个错
        return euiColor
    end,
}

local DK = "DEATHKNIGHT"
function UnitClass() return "Death Knight", DK, 6 end

for _, name in ipairs({ "Logic", "Elements", "Config", "Core" }) do
    assert(loadfile(dir .. "/" .. name .. ".lua"))()
end
local NS = assert(_G.MYUI_CHH)
local Config = assert(NS.Config)
local Elements = assert(NS.Elements)
local Logic = assert(NS.Logic)

Config.Load()
local element = Config.Get().elements.health

local function Near(a, b, what)
    assert(type(a) == "number" and math.abs(a - b) < 1e-9,
        what .. "：期望 " .. tostring(b) .. " 实得 " .. tostring(a))
end

----------------------------------------------------------------------
-- 一、EUI 的颜色缓存可用：优先用它（能反映用户在 EUI 里改过的职业色）
----------------------------------------------------------------------
element.fillMode = "class"
euiColor = { r = 0.11, g = 0.22, b = 0.33 }
local c = Config.ResolveFill(element)
Near(c[1], 0.11, "第一级：EUI 缓存的色应优先"); Near(c[2], 0.22, "g"); Near(c[3], 0.33, "b")

----------------------------------------------------------------------
-- 二、**实机那个 bug**：EUI 缓存吃不了秘密令牌，抛错后必须退回 Blizzard 的接口
--
-- Blizzard 的 C_ClassColor.GetClassColor 能直接吃秘密令牌，代价是拿不到用户改过
-- 的色。"取不到"是缺陷，"不是自定义的那个色"只是次要诉求。
----------------------------------------------------------------------
euiThrows = true
_G.C_ClassColor = { GetClassColor = function(token)
    assert(token == DK, "类名令牌要原样传下去")
    if blizzardThrows then error("nope") end
    return blizzardColor
end }
blizzardColor = { r = 0.77, g = 0.12, b = 0.23 }
c = Config.ResolveFill(element)
Near(c[1], 0.77, "第二级：EUI 缓存失效时必须退回 C_ClassColor")
Near(c[2], 0.12, "g"); Near(c[3], 0.23, "b")

----------------------------------------------------------------------
-- 三、颜色通道本身可能是秘密值：必须原封不动地转交
--
-- 用数值哨兵：任何算术都会改变它，所以"原封不动"等价于"没运算过"。
-- 也要能通过校验——校验只许用 type，不许真值判断。
----------------------------------------------------------------------
blizzardColor = { r = secretNumber, g = secretNumber, b = secretNumber }
c = Config.ResolveFill(element)
assert(c[1] == secretNumber and c[2] == secretNumber and c[3] == secretNumber,
    "秘密通道必须原样转交，实得 " .. tostring(c[1]))

----------------------------------------------------------------------
-- 四、Blizzard 接口也拿不到时，退回老牌全局色表
----------------------------------------------------------------------
blizzardThrows = true
_G.RAID_CLASS_COLORS = { DEATHKNIGHT = { r = 0.9, g = 0.1, b = 0.2 } }
c = Config.ResolveFill(element)
Near(c[1], 0.9, "第三级：全局色表")

----------------------------------------------------------------------
-- 五、全都不可用：必须回落到自定义色，**绝不能是 nil 或黑**
----------------------------------------------------------------------
_G.RAID_CLASS_COLORS = nil
_G.C_ClassColor = nil
c = Config.ResolveFill(element)
assert(type(c) == "table" and type(c[1]) == "number" and type(c[2]) == "number"
    and type(c[3]) == "number", "取不到职业色时必须回落到自定义色，不能是 nil")
Near(c[1], element.fill[1], "回落色应是自定义色")

----------------------------------------------------------------------
-- 六、填充与背景的透明度是两个值
--
-- 在渲染层的公开入口上断言：喂一张状态表，看两个纹理各自收到哪个 alpha。
----------------------------------------------------------------------
element.fillMode = "custom"
_G.EllesmereUI = nil          -- 与颜色无关了，避免干扰
Elements.scale = 1
Elements.Create()
Elements.Apply({
    health = { visible = true, rotation = 1, hasRotation = true,
               fillColor = { 0.1, 0.2, 0.3 }, fillAlpha = 0.4,
               bgColor = { 0.5, 0.6, 0.7 }, bgAlpha = 0.8 },
    runes = {},
    crosshair = { visible = true, fillColor = { 1, 1, 1 }, fillAlpha = 0.25 },
})

-- 按 sublevel 区分同一条弧的底图(0)与填充图(1)——它们用的是同一张纹理
local function Find(file, sub)
    for _, t in ipairs(textures) do
        if t.path and t.path:find(file, 1, true) and t.sub == sub then return t end
    end
end

local healthBg, healthFill = Find("health_arc", 0), Find("health_arc", 1)
assert(healthBg and healthFill, "血弧的底图与填充图都应存在")
assert(healthBg.vertex, "底图要收到顶点色")
assert(healthFill.vertex, "填充图要收到顶点色")
Near(healthBg.vertex[4], 0.8, "背景收到的是 bgAlpha")
Near(healthFill.vertex[4], 0.4, "填充收到的是 fillAlpha")
Near(healthBg.vertex[1], 0.5, "背景色")
Near(healthFill.vertex[1], 0.1, "填充色")

local crosshair = Find("crosshair", 2)
assert(crosshair and crosshair.vertex, "准星要收到顶点色")
Near(crosshair.vertex[4], 0.25, "准星用的是 fillAlpha")

----------------------------------------------------------------------
-- 七、默认值：两个 alpha 都在，且旧数据里的单一 alpha 不会把新键顶掉
----------------------------------------------------------------------
local defaults = Config.DEFAULTS.elements
assert(defaults.health.fillAlpha ~= nil and defaults.health.bgAlpha ~= nil,
    "血弧要同时有填充与背景两个透明度")
assert(defaults.crosshair.fillAlpha ~= nil and defaults.crosshair.bgAlpha == nil,
    "准星是线，没有背景透明度")
assert(defaults.health.alpha == nil, "单一的 alpha 键必须已经去掉")

io.write("PASS: config color and alpha\n")
'''


def test_config_color_and_alpha():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "color_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: config color and alpha" in result.stdout
