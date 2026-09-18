"""颜色与透明度的离线测试。

三件事，各锁一个已经出过问题的地方：

1. **颜色只从 EUI 取。** 职业色／能量色／职业资源色都由 EUI 统一管理，本插件不能
   打破这一条。实机上曾经"选了职业配色但毫无变化"，根因是 EUI 的颜色缓存**以类名
   令牌为键**，而 `UnitClass` 在受限上下文里可能交回**秘密令牌**——秘密值不能当表键，
   查表抛错，于是静默回落到自定义色。现在整条路径都 pcall，且**绝不退回暴雪的色表**
   （`C_ClassColor`／`RAID_CLASS_COLORS`）——那会拿到暴雪默认色而不是用户在 EUI 里
   配的色。取不到就回落到自定义色，绝不能是 nil 或黑；这条用探针钉死。

2. **填充、背景与阴影的透明度是三个值。** 合成一个就只能整条一起淡化。断言在渲染层的
   公开入口（`Elements.Apply`）上做——那里是这套契约最高的接缝：喂一张状态表进去，
   看每条纹理各自收到了哪个 alpha。顺带覆盖秘密通道必须原封不动地转交。

3. **阴影是画在底图之下的一层，且空转时留着。** 画在上面会盖住条本身，那看起来只是
   「颜色偏暗」不报错；跟着填充一起隐藏则会让空转的符文格彻底失去位置标记。两条都只能
   靠断言守。构造状态表的三处（逐元素、准星、假数据模式）必须同契约，所以从真实入口验。
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
    function t:AddMaskTexture() t.masked = true end
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
local Core = assert(NS.Core)
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
-- **背景只有自定义色一种，没有第二个色块**（用户定，且这条来回漂过好几次）
--
-- 这是本测试最该盯住的一条：规则漂了两次都是因为没人守着。所以从三个层面钉：
--   出口函数（页面据此建不建第二个色块）、数据模型（有没有 bgMode）、渲染取值。
----------------------------------------------------------------------
local order = Config.ELEMENT_ORDER
assert(#order == 4, "元素数量变了就要一并检查这条规则")

for _, key in ipairs(order) do
    assert(Config.SourceFor(key, "bg") == nil,
        key .. " 的背景不该有来源色块——背景只有自定义色")
    assert(Config.FILL_SOURCE[key] == nil or Config.FILL_SOURCE[key].mode ~= nil,
        "填充的来源表格式不对")
end
assert(Config.SourceFor("health", "fill") ~= nil, "填充仍要有来源色块")
assert(Config.SourceFor("crosshair", "fill") ~= nil, "准星也要有来源色块")

-- 出口函数对任何"不是 fill 的槽"都必须返回 nil，不是只对 "bg"
assert(Config.SourceFor("health", "border") == nil, "没有来源的槽一律返回 nil")

----------------------------------------------------------------------
-- 数据模型里不该再有"背景来源"这个键；渲染取值恒为自定义色
----------------------------------------------------------------------
local defaults = Config.DEFAULTS.elements
for _, key in ipairs(order) do
    assert(defaults[key].bgMode == nil, key .. " 不该再有 bgMode")
end

element.fillMode = "power"      -- 填充挑任何来源，背景都必须原样不动
Near(Config.ResolveBg(element)[1], element.bg[1], "背景恒取自定义色（不受填充来源影响）")
Near(Config.ResolveBg(element)[2], element.bg[2], "g")
Near(Config.ResolveBg(element)[3], element.bg[3], "b")
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
local defaults2 = Config.DEFAULTS.elements
assert(defaults2.health.fillAlpha ~= nil and defaults2.health.bgAlpha ~= nil,
    "生命值条要同时有填充与背景两个透明度")
assert(defaults2.crosshair.fillAlpha ~= nil and defaults2.crosshair.bgAlpha == nil,
    "准星是线，没有背景透明度")
assert(defaults2.health.alpha == nil, "单一的 alpha 键必须已经去掉")

----------------------------------------------------------------------
-- 八、"有没有角度"必须看 hasRotation 这个**普通布尔**，不许比较 rotation 本身
--
-- rotation 是可能为秘密值的量，而秘密值不许参与比较（Core 的读数段就是这么写的，
-- 那里连"读到了吗"都用另一个布尔表示）。渲染层曾经用 `st.rotation ~= nil` 去判断，
-- 等于给那条规矩开了个口子。
-- 用一份"自称没有角度、却带着角度"的状态来验：填充必须隐藏；若渲染层看的是
-- rotation 本身，它会照画不误。
----------------------------------------------------------------------
Elements.Apply({
    health = { visible = true, rotation = 1, hasRotation = false,
               fillColor = { 1, 1, 1 }, fillAlpha = 1,
               bgColor = { 0, 0, 0 }, bgAlpha = 1 },
    runes = {},
    crosshair = { visible = false, fillColor = { 1, 1, 1 }, fillAlpha = 1 },
})
assert(healthFill.shown == false,
    "hasRotation=false 时填充必须隐藏——渲染层不许去比较 rotation 本身")

----------------------------------------------------------------------
-- 九、假数据模式（`/chh demo`）下准星的透明度也必须生效
--
-- 状态表契约里准星带的是 fillAlpha。DemoState 曾经写的是 `alpha`——键名与契约不符，
-- 渲染层读不到，于是 demo 下调准星透明度毫无反应。两个构造状态的地方必须同契约，
-- 所以这条从真实入口（Core.demo + Core.Refresh）验，而不是手搓一张状态表。
----------------------------------------------------------------------
Config.Get().elements.crosshair.fillAlpha = 0.25
Core.demo = true
Core.Refresh()
Near(crosshair.vertex[4], 0.25, "假数据模式下准星要用配置的透明度")
Core.demo = false
Config.Get().elements.crosshair.fillAlpha = 1

----------------------------------------------------------------------
-- 十、阴影层：画在底图**之下**，颜色与浓淡各是独立的一个值
--
-- 阴影是独立的一层纹理。两件事必须成立：
--
--   1. 它比底图**低**。画在上面就盖住条本身了，而那看起来只是"颜色偏暗"，
--      不会报错，只能靠断言守。
--   2. 颜色与浓淡是**两个**值，且与填充、背景各不相干。合成一个就只能整层一起淡化。
--
-- 另外它**不挂遮罩**：阴影是包住整条弧的轮廓，不随填充比例变化。
----------------------------------------------------------------------
Elements.Apply({
    health = { visible = true, rotation = 1, hasRotation = true,
               fillColor = { 0.1, 0.2, 0.3 }, fillAlpha = 0.4,
               bgColor = { 0.5, 0.6, 0.7 }, bgAlpha = 0.8,
               shadowColor = { 0, 0, 0 }, shadowAlpha = 0.7 },
    runes = {},
    crosshair = { visible = true, fillColor = { 1, 1, 1 }, fillAlpha = 1,
                  shadowColor = { 0.2, 0.1, 0.05 }, shadowAlpha = 0.35 },
})

local function FindShadow(fragment)
    for _, t in ipairs(textures) do
        if t.path and t.path:find(fragment, 1, true) then return t end
    end
end

local healthShadow = FindShadow("health_arc_shadow")
assert(healthShadow, "生命值条要有自己的一层阴影纹理")
assert(healthShadow.sub ~= nil and healthBg.sub ~= nil and healthShadow.sub < healthBg.sub,
    "阴影层必须画在底图之下（阴影 sublevel=" .. tostring(healthShadow.sub)
    .. "，底图 sublevel=" .. tostring(healthBg.sub) .. "）")
assert(healthShadow.vertex, "阴影层要收到顶点色")
Near(healthShadow.vertex[1], 0, "阴影颜色 R")
Near(healthShadow.vertex[2], 0, "阴影颜色 G")
Near(healthShadow.vertex[3], 0, "阴影颜色 B")
Near(healthShadow.vertex[4], 0.7, "阴影浓淡是它自己的一个值，不与填充、背景共用")
assert(healthShadow.masked == nil, "阴影层不挂遮罩——它包住整条弧，不随填充比例变化")

-- 颜色确实会被用上（不是写死黑）
local crosshairShadow = FindShadow("crosshair_shadow")
assert(crosshairShadow, "准星也要有一层自己的阴影纹理")
assert(crosshairShadow.vertex, "准星的阴影层要收到顶点色")
Near(crosshairShadow.vertex[1], 0.2, "阴影颜色跟着配置走，不是写死的黑")
Near(crosshairShadow.vertex[4], 0.35, "准星阴影的浓淡也是独立的")

----------------------------------------------------------------------
-- 十一、真实入口必须把阴影色与浓淡填进状态表
--
-- 渲染层会画阴影，但状态表里没有这两个字段就等于没画。构造状态表的地方有三处
-- （逐元素、准星、假数据模式），三处都得填——假数据模式那次就因为键名与契约不符
-- 翻过车，所以这条从真实入口（Core.Refresh）验，不手搓状态表。
----------------------------------------------------------------------
Core.demo = false
Core.Refresh()
local liveShadow = FindShadow("health_arc_shadow")
assert(liveShadow and liveShadow.vertex,
    "常规路径下阴影层没收到顶点色——Core 构造状态表时漏了阴影字段")
Near(liveShadow.vertex[1], 0, "本票先用固定值：阴影纯黑")
Near(liveShadow.vertex[4], 1, "本票先用固定值：阴影最重")

Core.demo = true
Core.Refresh()
local demoShadow = FindShadow("crosshair_shadow")
assert(demoShadow and demoShadow.vertex,
    "假数据模式下准星阴影没收到顶点色——DemoState 漏了阴影字段")
Core.demo = false
Core.Refresh()

----------------------------------------------------------------------
-- 十二、空转态：填充整格消失，阴影要**留着**
--
-- 空转时最需要阴影——它正是"这里本该有个槽"的标记。跟着填充一起消失的话，
-- 六个符文格在 AOE 里就彻底看不出位置了。
----------------------------------------------------------------------
local blk = { 0, 0, 0 }
Elements.Apply({
    health = { visible = true, rotation = 1, hasRotation = true,
               fillColor = { 1, 1, 1 }, fillAlpha = 1,
               bgColor = blk, bgAlpha = 1, shadowColor = blk, shadowAlpha = 1 },
    runes = { [1] = { visible = true, rotation = 1, hasRotation = true,
                      state = Logic.RUNE_EMPTY,
                      fillColor = { 1, 1, 1 }, fillAlpha = 1,
                      bgColor = blk, bgAlpha = 1, shadowColor = blk, shadowAlpha = 1 } },
    crosshair = { visible = true, fillColor = { 1, 1, 1 }, fillAlpha = 1,
                  shadowColor = blk, shadowAlpha = 1 },
})

local runeFill = Find("resource_01", 1)
local runeShadow = FindShadow("resource_01_shadow")
assert(runeFill and runeFill.shown == false, "空转时填充必须隐藏")
assert(runeShadow and runeShadow.shown == true, "空转的符文格仍然要显示阴影轮廓")

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
