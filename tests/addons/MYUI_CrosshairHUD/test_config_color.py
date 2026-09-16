"""颜色与透明度的离线测试。

两件事，各锁一个已经出过问题的地方：

1. **颜色只从 EUI 取。** 职业色／能量色／职业资源色都由 EUI 统一管理，本插件不能
   打破这一条。实机上曾经"选了职业配色但毫无变化"，根因是 EUI 的颜色缓存**以类名
   令牌为键**，而 `UnitClass` 在受限上下文里可能交回**秘密令牌**——秘密值不能当表键，
   查表抛错，于是静默回落到自定义色。现在整条路径都 pcall，且**绝不退回暴雪的色表**
   （`C_ClassColor`／`RAID_CLASS_COLORS`）——那会拿到暴雪默认色而不是用户在 EUI 里
   配的色。取不到就回落到自定义色，绝不能是 nil 或黑；这条用探针钉死。

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
-- 色源开关。**只有 EUI 一个来源**——暴雪的色表在测试里被探针盯着，碰一下就报错。
----------------------------------------------------------------------
local euiColor, euiThrows = nil, false

local DK = "DEATHKNIGHT"
local powerColor, powerThrows = nil, false
local resourceColor, resourceThrows = nil, false
_G.EllesmereUI = {
    -- EUI 加载时就缓存好的类名令牌，优先于现读 UnitClass
    _playerClass = DK,
    GetClassColor = function(token)
        assert(token == DK, "取职业色要拿 EUI 缓存的令牌，实得 " .. tostring(token))
        if euiThrows then error("table index is nil") end   -- 秘密令牌当表键就是这个错
        return euiColor
    end,
    CLASS_POWER_MAP = { DEATHKNIGHT = "RUNIC_POWER" },
    GetPowerColor = function(key)
        assert(key == "RUNIC_POWER", "能量色要按玩家主能量类型取，实得 " .. tostring(key))
        if powerThrows then error("no power color") end
        return powerColor
    end,
    -- 色表按**资源名**取（DK 是 Runes），资源名由职业推——不是拿职业令牌当键。
    -- 传职业令牌查不到，页面上那个色块会画成黑。
    CLASS_RESOURCE_MAP = { DEATHKNIGHT = "Runes" },
    GetClassResourceColor = function(key)
        assert(key == "Runes", "职业资源色要按资源名取，实得 " .. tostring(key))
        if resourceThrows then error("no resource color") end
        return resourceColor
    end,
}

local unitClassCalls = 0
function UnitClass() unitClassCalls = unitClassCalls + 1; return "Death Knight", DK, 6 end

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
assert(unitClassCalls == 0, "有 EUI 缓存的类名令牌时，不该再去现读 UnitClass")

----------------------------------------------------------------------
-- 第二个来源**按元素不同**，而且三个来源在 EUI 里各有各的接口
--
--   血弧、准星 → 职业色（GetClassColor）
--   符能弧     → 能量色（GetPowerColor，键按玩家的主能量类型）
--   符文格     → 职业资源色（GetClassResourceColor）
-- 一律不许自己定色。
----------------------------------------------------------------------
powerColor = { r = 0.31, g = 0.52, b = 0.93 }
resourceColor = { r = 0.44, g = 0.61, b = 0.66 }

element.fillMode = "power"
Near(Config.ResolveFill(element)[1], 0.31, "符能弧取的是能量色")
Near(Config.ResolveFill(element)[2], 0.52, "g")

element.fillMode = "resource"
Near(Config.ResolveFill(element)[1], 0.44, "符文格取的是职业资源色")

-- 元素的第二个来源是设计决定，不是用户配置
local sources = Config.FILL_SOURCE
assert(sources.health.mode == "class", "血弧的第二个来源是职业色")
assert(sources.power.mode == "power", "符能弧的第二个来源是能量色")
assert(sources.runes.mode == "resource", "符文格的第二个来源是职业资源色")
assert(sources.crosshair.mode == "class", "准星的第二个来源是职业色")
assert(sources.power.tooltip == "Power Colored", "提示语用 EUI 自己的词条键")

----------------------------------------------------------------------
-- 来源取不到时一律回落到自定义色，不许画成黑
----------------------------------------------------------------------
powerThrows = true
element.fillMode = "power"
Near(Config.ResolveFill(element)[1], element.fill[1], "能量色取不到就回落自定义色")
powerThrows = false

resourceThrows = true
element.fillMode = "resource"
Near(Config.ResolveFill(element)[1], element.fill[1], "资源色取不到就回落自定义色")
resourceThrows = false

----------------------------------------------------------------------
-- 背景的第二种来源**固定是职业色**（与 EUI 自己的"职业着色背景"一致），
-- 不像填充那样按元素换成能量色／职业资源色
----------------------------------------------------------------------
element.fillMode = "power"
element.bgMode = "class"
Near(Config.ResolveBg(element)[1], 0.11, "背景选职业时应取职业色（不是能量色）")
Near(Config.ResolveFill(element)[1], 0.31, "同一时刻填充仍按它自己的来源取")
element.bgMode = "custom"
Near(Config.ResolveBg(element)[1], element.bg[1], "背景选自定义时取自定义色")
element.fillMode = "class"

----------------------------------------------------------------------
-- 二、**只能认 EUI**：EUI 取不到就回落自定义色，绝不退回暴雪的色表
--
-- 职业色／能量色／职业资源色都由 EUI 统一管理。退回 C_ClassColor 或
-- RAID_CLASS_COLORS 会拿到暴雪默认色——不是用户在 EUI 里配的那个——同一套界面里
-- 就会冒出两套职业色。这条用一个探针把"绝不碰暴雪色表"钉死。
----------------------------------------------------------------------
local blizzardTouched = false
_G.C_ClassColor = {
    GetClassColor = function()
        blizzardTouched = true
        return { r = 0.77, g = 0.12, b = 0.23 }
    end,
}
_G.RAID_CLASS_COLORS = setmetatable({}, {
    __index = function() blizzardTouched = true; return { r = 0.1, g = 0.2, b = 0.3 } end,
})

euiThrows = true
c = Config.ResolveFill(element)
Near(c[1], element.fill[1], "EUI 取不到时回落到自定义色")
assert(not blizzardTouched, "绝不退回暴雪的色表：那些色不是用户在 EUI 里配的")

----------------------------------------------------------------------
-- 三、颜色通道本身可能是秘密值：必须原封不动地转交
--
-- 用数值哨兵：任何算术都会改变它，所以"原封不动"等价于"没运算过"。
-- 也要能通过校验——校验只许用 type，不许真值判断。
----------------------------------------------------------------------
euiThrows = false
euiColor = { r = secretNumber, g = secretNumber, b = secretNumber }
c = Config.ResolveFill(element)
assert(c[1] == secretNumber and c[2] == secretNumber and c[3] == secretNumber,
    "秘密通道必须原样转交，实得 " .. tostring(c[1]))
euiColor = { r = 0.11, g = 0.22, b = 0.33 }

----------------------------------------------------------------------
-- 四、（已并入二）不退回暴雪色表
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
-- 颜色对象取不出通道时：不许抛错，也不许把上一次的颜色弄没
--
-- 渲染侧整次 SetVertexColor 是 pcalled 的——防的就是一个坏色值把每帧的渲染打断。
----------------------------------------------------------------------
local beforeBg = healthBg.vertex[1]
local ok = pcall(Elements.Apply, {
    health = { visible = true, rotation = 1, hasRotation = true,
               fillColor = {}, fillAlpha = 0.4,      -- 通道读不出来
               bgColor = { 0.5, 0.6, 0.7 }, bgAlpha = 0.8 },
    runes = {},
    crosshair = { visible = true, fillColor = { 1, 1, 1 }, fillAlpha = 0.25 },
})
assert(ok, "颜色取不出来时不许抛错")
Near(healthBg.vertex[1], beforeBg, "取不出来时应保留上一次的颜色")

----------------------------------------------------------------------
-- 七、默认值：两个 alpha 都在，且旧数据里的单一 alpha 不会把新键顶掉
----------------------------------------------------------------------
local defaults = Config.DEFAULTS.elements
assert(defaults.health.fillAlpha ~= nil and defaults.health.bgAlpha ~= nil,
    "血弧要同时有填充与背景两个透明度")
assert(defaults.crosshair.fillAlpha ~= nil and defaults.crosshair.bgAlpha == nil,
    "准星是线，没有背景透明度")
assert(defaults.health.alpha == nil, "单一的 alpha 键必须已经去掉")
assert(defaults.health.bgMode ~= nil and defaults.crosshair.bgMode == nil,
    "背景要有自己的来源（职业色）；准星没有背景，也就不该有它的来源")

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
