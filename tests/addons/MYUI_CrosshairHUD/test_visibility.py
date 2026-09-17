"""可见性接线的离线测试（票据 01 起）。

**为什么断言打在装配入口上、而不是某个内部函数上**：只测「该不该显示」那个函数的话，
就算它从没被接上去，测试照样全绿——而「接线漏了」恰恰是这类能力最常见的静默失败。
这里走的是与实机同一段路：按清单顺序加载模块 → 触发 `PLAYER_LOGIN` → 观察结果。

**降级为什么是这个方向**：EUI 改版、接口改名、返回值不符合预期时一律答「显示」。
理由是降级发生时配置页上那一行很可能同时失效，用户没有任何自救手段——「条件不起作用」
和「东西没了」在用户眼里是两码事。

harness 的框体 mock 记录 `SetShown` 的实参（现成的解锁元素测试里那是个空函数），
因为「屏幕上到底有没有它」本身就是被测行为之一。

夹具边界：这里的 `EllesmereUI` 是照 EUI 源码抄的**契约夹具**，抄错了会让测试全绿而
实机静默失败。所以它验的是**本插件调用的形状**，不是 EUI 的行为——离线通过不等于
实机通过，两者不得互相冒充。
"""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/MYUI_CrosshairHUD"

MODULES = '{"Logic", "Elements", "Config", "Visibility", "Core"}'


# 与场景无关的部分：魔兽接口 mock、框体 mock、以及把它装起来的入口。
MOCKS = r'''
local dir = assert(arg[1])

----------------------------------------------------------------------
-- 纹理与框体 mock
--
-- 与现成 harness 的区别只有一处：`SetShown` 记录实参。屏幕上有没有它，
-- 正是本契约要断言的，空函数会让这一整类断言失去意义。
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

local frames = {}
function CreateFrame()
    local f = { events = {}, scripts = {}, shown = true }
    function f:CreateTexture() return NewTexture() end
    function f:CreateMaskTexture() return NewTexture() end
    function f:SetSize(w, h) f.width, f.height = w, h end
    function f:SetPoint() end
    function f:ClearAllPoints() end
    function f:SetFrameStrata() end
    function f:SetShown(v) f.shown = v ~= false end
    function f:IsShown() return f.shown end
    function f:GetWidth() return f.width or 0 end
    function f:GetHeight() return f.height or 0 end
    function f:GetEffectiveScale() return 1 end
    function f:RegisterEvent(event) f.events[#f.events + 1] = event end
    -- 与读数 harness 同一套校验：真客户端对单位事件有白名单，注册了非单位事件
    -- 会在加载期直接抛错、中断整个文件，而空函数 mock 一声不吭
    function f:RegisterUnitEvent(event, unit)
        assert(type(event) == "string" and event:sub(1, 5) == "UNIT_",
            "RegisterUnitEvent 收到了非单位事件：" .. tostring(event))
        assert(unit == "player", "本插件只注册 player 单位")
        f.events[#f.events + 1] = event
    end
    function f:UnregisterAllEvents() f.events = {} end
    function f:SetScript(kind, callback) f.scripts[kind] = callback end
    function f:GetFrameLevel() return 1 end
    frames[#frames + 1] = f
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
-- EllesmereUI mock 的公共部分（每个场景再往上面挂自己要的那几个接口）
--
-- 先 `local api` 再赋值：`local api = { f = function() api.x = 1 end }` 里的
-- `api` 会落到全局——局部变量要整条语句结束后才进作用域。
----------------------------------------------------------------------
-- 场景可翻转的两个开关。**必须先声明**：下面的闭包引用它们，而局部变量要等
-- 整条语句结束后才进作用域，写反了就会落到全局上（本文件已经踩过一次）。
local sharedVerdict = true     -- EUI 共享引擎的判定（仅在配了多选模式集时被问到）
local inCombat = false         -- 旧标量兜底要用的交互状态
local optionsVeto = false      -- 选项通道的隐藏否决（目标／敌对目标／骑乘中…这一类）
local overrideValue = nil      -- EUI 专精覆盖的值（本插件不接受它，但会话中会短暂存在）

-- ⚠ 这一条不能漏：EUI 的判定链里，**选项通道的隐藏否决排在模式集之前**，
-- 而且它是独立的一半。漏掉它的后果不是报错，是「目标／敌对目标／骑乘中／
-- 御空术坐骑／副本／住宅／休息中／载具」这一整类条件静默地什么都不做。
-- 实机复现过：用户勾了「敌对目标」毫无反应。

local api
api = {
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
    RegisterUnlockElements = function(_, list) api._elements = list end,

    -- 忠实模拟 EUI 的求值器契约：
    --   配了**多选模式集**（store.visibilityModes 有东西）→ 共享引擎给判定
    --   否则（单个条件被存进旧标量）→ 交回「空」，由调用方自己按标量兜底
    --
    -- 这条路是常态：EUI 把「只勾了一个条件」直接存进标量，与旧版单选逐字节一致。
    -- 夹具抄错的话测试会绿而实机静默失败，所以这里照契约写、并且**让它可翻转**。
    EvalVisibilityExtended = function(store)
        -- 专精覆盖**排在模式集之前**并替换整份配置（EUI 的实现就是这个顺序）。
        -- 夹具漏掉这一段，会让「覆盖说总是」被误判成隐藏——正是本文件的夹具
        -- 第三次没跟上真实契约。
        if store and overrideValue then
            if overrideValue == "never" then return false end
            return true
        end
        if store and store.visibilityModes then return sharedVerdict end
        return nil
    end,
    CheckVisibilityMode = function(mode, state)
        if mode == "never" then return false end
        if mode == "always" then return true end
        if mode == "in_combat" then return state.inCombat end
        if mode == "out_of_combat" then return not state.inCombat end
        if mode == "in_raid" then return state.inRaid end
        if mode == "in_party" then return state.inParty end
        if mode == "solo" then return not state.inRaid and not state.inParty end
        return true
    end,
    IsInCombat = function() return inCombat end,
    CheckVisibilityOptions = function() return optionsVeto end,
    VisOverrideValue = function() return overrideValue end,
}
_G.EllesmereUI = api

function IsInRaid() return false end
function IsInGroup() return false end

----------------------------------------------------------------------
-- 装配入口：与实机同一段路——按清单顺序加载，再触发 PLAYER_LOGIN
----------------------------------------------------------------------
local function Load()
    for _, name in ipairs(MODULES) do
        assert(loadfile(dir .. "/" .. name .. ".lua"))()
    end
    return assert(_G.MYUI_CHH)
end

local function FireLogin()
    local fired = false
    for _, f in ipairs(frames) do
        for _, event in ipairs(f.events) do
            if event == "PLAYER_LOGIN" then
                f.scripts.OnEvent(f, "PLAYER_LOGIN")
                fired = true
            end
        end
    end
    assert(fired, "应有帧注册 PLAYER_LOGIN")
end
'''.replace("MODULES", MODULES)


# 场景一：EUI 一个可见性接口都没有——降级必须答「显示」。
SCENARIO_DEGRADATION = r'''
-- **真的把可见性接口全部拆掉。**
--
-- 这条断言曾经是空转的：共享 mock 后来加上了齐全的求值器，而这个场景的注释
-- 仍声称「EUI 一个可见性接口都没有」——它从此只测到一个布尔类型，却照旧全绿。
-- 声明与行为分了家且不报错，所以这里必须显式地拆，并由下面几条断言钉住。
api.EvalVisibilityExtended = nil
api.CheckVisibilityMode = nil
api.RegisterVisibilityUpdater = nil
api.IsInCombat = nil
api.CheckVisibilityOptions = nil

local NS = Load()
FireLogin()

local Visibility = assert(NS.Visibility, "应有可见性模块")
assert(type(Visibility.ShouldShow) == "function", "应暴露「该不该显示」这一条问答")

local verdict = Visibility.ShouldShow()
assert(type(verdict) == "boolean",
    "必须返回真布尔——四值协议（真／假／悬停／空）要压在这个模块里面，实得 "
    .. type(verdict) .. "：" .. tostring(verdict))
assert(verdict == true,
    "接口认不出来时必须答「显示」：降级时配置页那一行多半也一起失效了，"
    .. "用户没有自救手段，显示至少还能用")

----------------------------------------------------------------------
-- 但「关掉状态」不受降级影响
--
-- 总开关与「从不」是**我们自己存的数据**，不需要 EUI 就能判。它们表达的是
-- 「这东西不该存在」，与「条件判不出来」不是一回事——所以接口没了，
-- 它们照样要隐藏。
----------------------------------------------------------------------
local Config = NS.Config

Config.Get().visibility = "never"
assert(Visibility.ShouldShow() == false,
    "「从不」是我们自己的数据，不依赖 EUI——接口认不出来时它照样该隐藏")
assert(Visibility.IsOff() == true, "「从不」属于关掉状态")

Config.Get().visibility = "always"
Config.Get().enabled = false
assert(Visibility.ShouldShow() == false,
    "总开关关着同样是我们自己的数据，接口没了也不该显示")
assert(Visibility.IsOff() == true, "总开关关着属于关掉状态")

Config.Get().enabled = true
Config.Get().visibility = "in_combat"
assert(Visibility.ShouldShow() == true,
    "而「条件判不出来」才是降级：这条路径答显示")

Config.Get().visibility = "always"
io.write("PASS: degradation\n")
'''

# 场景二：EUI 提供更新器注册入口——装配时必须接上，且只接一次。
SCENARIO_WIRING = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

assert(api._updaters, "装配时必须向 EUI 注册可见性更新器，否则条件变化永远收不到通知"
    .. "——这是本能力最容易发生的静默失败")
assert(#api._updaters == 1, "只应注册一次，实得 " .. tostring(#api._updaters))
assert(type(api._updaters[1]) == "function", "注册的必须是函数")

-- 幂等：装配入口可以被再走一遍（例如界面重载），不能越接越多
NS.Mount()
assert(#api._updaters == 1, "重复装配不得重复注册，实得 " .. tostring(#api._updaters))

io.write("PASS: wiring\n")
'''


# 场景三：判定真的驱动准星，而且**两处同时改变**。
#
# 这是本能力唯一可能破坏既有验收的地方：「该不该显示」会被两条不同的代码路径分别
# 算一遍——一条决定画不画，一条决定给不给拖动框。两处算得不一致，症状就是
# 「屏幕上看不见它，正中却留着一个能拖的空框」。所以两处必须由同一次通知驱动。
SCENARIO_VERDICT = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")

-- 配一个多选条件：这样判定才走 EUI 的共享引擎，而不是旧标量兜底那条路
NS.Config.Get().visibilityModes = { in_combat = true }
sharedVerdict = true
NS.Core.Refresh()

assert(frame.shown == true, "判定为显示时，框体应当在屏幕上")
assert(elem.isHidden(elem.key) == false, "判定为显示时，不应报告隐藏")

-- 接线：交给 EUI 的模块表里，建页函数必须就是本插件那一个。
-- 光测「建页函数本身能建出可见性行」不够——它可能根本没被挂上去。
local module = assert(api._modules["MYUI_CrosshairHUD"], "模块应已注册")
assert(module.buildPage == NS.Config.BuildPage,
    "模块表里的建页函数必须是本插件的，否则设置页永远不会被调起")

-- 翻转判定，再走 EUI 通知更新器那条路（这正是实机里条件变化时的路径）
sharedVerdict = false
assert(api._updaters and api._updaters[1], "应已注册更新器")
api._updaters[1]()

assert(frame.shown == false, "判定为隐藏时，框体必须从屏幕上消失")
assert(elem.isHidden(elem.key) == true,
    "同一次翻转下，解锁元素必须同时报告隐藏——两处不一致的可见症状是"
    .. "「屏幕上看不见它，正中却留着一个能拖的空框」")

-- 翻回来也要一致
sharedVerdict = true
api._updaters[1]()
assert(frame.shown == true, "判定回到显示时，框体应当回来")
assert(elem.isHidden(elem.key) == false, "判定回到显示时，不应再报告隐藏")

io.write("PASS: verdict\n")
'''


# 场景四：旧存档兼容与演示模式。
#
# 两件事同源——**「不满足条件」与「不该有这东西」是两回事**：
# 旧存档没有可见性配置，等价于「总是」；演示模式是为了在条件不满足时也能调样式，
# 所以它绕过条件。两者都不该让准星消失。
SCENARIO_LEGACY_AND_DEMO = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")
local Config = NS.Config

-- 旧存档：没有 visibilityModes，标量是默认的「总是」。
-- 共享引擎交回「空」，本插件按标量兜底 → 总是显示。升级前后完全一致。
assert(frame.shown == true, "没有可见性配置的旧存档，行为必须与升级前一致")
assert(elem.isHidden(elem.key) == false, "同上：不该报告隐藏")

----------------------------------------------------------------------
-- 单个条件走**旧标量**，这条路是常态：EUI 把「只勾了一个条件」直接存进标量。
-- 共享引擎对它一律交回「空」，所以兜底链必须在——漏掉的话，
-- 只勾「仅战斗中」时整个条件会静默失效。
----------------------------------------------------------------------
Config.Get().visibility = "in_combat"
inCombat = false
NS.Core.Refresh()
assert(frame.shown == false, "标量是「仅战斗中」且不在战斗时，必须隐藏")
assert(elem.isHidden(elem.key) == true, "同上：不该报告可见")

inCombat = true
NS.Core.Refresh()
assert(frame.shown == true, "进入战斗后应当显示——这证明兜底链真的按标量判了")
assert(elem.isHidden(elem.key) == false, "同上")
inCombat = false

Config.Get().visibility = "out_of_combat"
NS.Core.Refresh()
assert(frame.shown == true, "「仅脱战」且不在战斗时应当显示")

-- 「从不」是最硬的关
Config.Get().visibility = "never"
NS.Core.Refresh()
assert(frame.shown == false, "标量「从不」必须隐藏")
Config.Get().visibility = "always"

----------------------------------------------------------------------
-- 演示模式：绕过条件
----------------------------------------------------------------------
Config.Get().visibility = "in_combat"
NS.Core.Refresh()
assert(frame.shown == false, "条件不满足时隐藏")

NS.Core.demo = true
NS.Core.Refresh()
assert(frame.shown == true,
    "演示模式必须绕过可见性条件——它存在的意义就是「条件不满足时也能看」")
assert(elem.isHidden(elem.key) == false,
    "演示模式既然显示着，就不能报告隐藏，否则拖动框会缺席")

NS.Core.demo = false
NS.Core.Refresh()
assert(frame.shown == false, "退出演示模式后回到条件判定")

io.write("PASS: legacy-demo\n")
'''


# 场景五：设置页那一行——位置、默认值、能力集、置灰、离屏安全。
#
# 这一条只加载 Config.lua（仓库的文件级接缝）：页面清单不碰魔兽接口，也不碰 EUI。
# 控件工厂里页面构建只用到 DualRow 与 SectionHeader 两个方法，所以 mock 得住。
SCENARIO_SETTINGS_ROW = r'''
local dir = assert(arg[1])
assert(loadfile(dir .. "/Config.lua"))()
local Config = assert(_G.MYUI_CHH, "Config.lua 应导出命名空间表").Config

Config.Load()

----------------------------------------------------------------------
-- 位置：常规清单第 2 项，紧随总开关
--
-- 清单是自适应排版的（每行两项、奇数时末行右边留空），可见性就是清单里的普通
-- 一项，不为它做特殊处理——所以位置只能靠清单顺序表达。
----------------------------------------------------------------------
local general = Config.GeneralCells()
assert(type(general) == "table" and general[2], "常规清单至少要有两项")
assert(general[1].text == "启用准星HUD",
    "第 1 项应仍是总开关，实得「" .. tostring(general[1].text) .. "」")
assert(general[2].text == "可见性",
    "可见性应紧挨总开关（第 2 项），实得「" .. tostring(general[2].text) .. "」")
assert(general[2].kind == "visibility",
    "可见性格子的类型应是 visibility，实得 " .. tostring(general[2].kind))
assert(#general == 4,
    "常规清单应为 4 项（启用／可见性／缩放／图层），正好两行填满，实得 " .. #general)

----------------------------------------------------------------------
-- 默认值：显式写「总是」
--
-- 升级前后行为必须完全一致；显式写还能让设置页那行一开始就正确显示，
-- 而不是留一个看似「没设置过」的空白。
----------------------------------------------------------------------
assert(Config.Get().visibility == "always",
    "默认值应显式为 always（总是），实得 " .. tostring(Config.Get().visibility))

----------------------------------------------------------------------
-- 能力集：一处定义，设置页与运行期求值共用
----------------------------------------------------------------------
local caps = assert(Config.VIS_CAPS, "能力集要导出，设置页与求值共用一份")
assert(caps.noMouseover == true,
    "必须声明不做鼠标悬停：共享悬停服务会对注册对象 EnableMouse(true)，"
    .. "那会让屏幕正中吃掉鼠标，违反「点击必须穿透」那条既有规格")
assert(caps.partyIncludesRaid == false, "「队伍」与「团队」必须互斥")
assert(caps.luaDragonriding == true, "御空术判定走 Lua 侧")

----------------------------------------------------------------------
-- 离屏安全：控件工厂不可用时必须安全返回数字，绝不索引 nil
----------------------------------------------------------------------
_G.EllesmereUI = {}
local offscreen = Config.BuildPage(nil, nil, 0)
assert(type(offscreen) == "number",
    "控件工厂缺失时必须返回数字高度，实得 " .. type(offscreen))

----------------------------------------------------------------------
-- 控件工厂可用时：行被建出，且参数形状正确
----------------------------------------------------------------------
local attached = {}
-- 控件 mock：显式列出页面会用到的那些方法。
-- **不用万能元表兜底**——那样连拼错的 API 也会被吞掉，夹具就失去了把关作用。
local function Widget()
    local w = {}
    for _, name in ipairs({
        "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight",
        "SetAlpha", "SetScale", "SetShown", "Show", "Hide",
        "SetFrameStrata", "SetFrameLevel", "SetParent", "EnableMouse",
        "RegisterForClicks", "HookScript", "SetScript", "SetText",
        "SetJustifyH", "SetJustifyV", "SetFontString",
    }) do
        w[name] = function() end
    end
    w.GetScript = function() return nil end
    w.GetWidth = function() return 100 end
    w.GetHeight = function() return 20 end
    w.GetFrameLevel = function() return 1 end
    w.GetEffectiveScale = function() return 1 end
    return w
end
local function Region()
    return { _control = Widget(), GetFrameLevel = function() return 1 end }
end
-- 记下每个槽位落在第几行、哪一侧：只断言「清单里第 2 项」是不够的，
-- 那只证明数据序，证不了建出来的行真的把它放在了总开关右边。
local rowIndex = 0
local W = {}
function W:DualRow()
    rowIndex = rowIndex + 1
    local left, right = Region(), Region()
    left.spot, right.spot = rowIndex .. ":left", rowIndex .. ":right"
    return { _leftRegion = left, _rightRegion = right }, 10
end
function W:SectionHeader() return {}, 20 end

_G.EllesmereUI = {
    Widgets = W,
    BuildColorSwatch = function() return Widget() end,
    RegisterWidgetRefresh = function() end,
    ShowWidgetTooltip = function() end,
    HideWidgetTooltip = function() end,
    AttachVisibilityChecklist = function(region, opts)
        attached[#attached + 1] = { opts = opts, spot = region.spot }
    end,
}

local height = Config.BuildPage(nil, nil, 0)
assert(type(height) == "number", "建完页仍要返回数字高度，实得 " .. type(height))
assert(#attached == 1, "应恰好挂一份可见性清单，实得 " .. #attached)

-- 位置不能只看清单数据序：要断言它真的被挂在了总开关右边那一格
assert(attached[1].spot == "1:right",
    "可见性必须挂在第一行的右槽（总开关右边），实得 " .. tostring(attached[1].spot))

local opts = attached[1].opts
assert(opts.legacyKey == "visibility",
    "键名必须是 visibility，实得 " .. tostring(opts.legacyKey))
assert(type(opts.getStore) == "function",
    "存储必须以**取值函数**交出：配置加载会替换整个表对象，交缓存表会读写废表")
assert(opts.caps == Config.VIS_CAPS, "设置页必须用与求值同一份能力集")

----------------------------------------------------------------------
-- 标量写回：**必须按 EUI 的实参个数调用**
--
-- EUI 的契约是 `applyScalarFn(store, mode)`——两个参数。夹具只把它记下来、
-- 从不调用的话，参数个数写错也照样全绿，而实机的后果是：
-- 标量被写成一张表 → 兜底链全部落空 → 条件静默失效。
-- 所以这里照 EUI 的调用形状**真的调一次**。
--
-- **已知残留缺口**：这个调用形状是从 EUI 源码抄来的，不是由夹具模拟它的调用点
-- 产生的。EUI 哪天改了契约，这里不会自动变红。出处（本机 9.1.8，复核时对着看）：
--   EllesmereUI/EllesmereUI_Visibility.lua  SetVisibilitySelection :561
--                                           VisCopySelection      :1204
--   EllesmereUIOptions/EllesmereUI_Widgets.lua 文档注释          :8360
----------------------------------------------------------------------
assert(type(opts.applyScalarFn) == "function", "要交出标量写回回调")
local settings = Config.Get()
opts.applyScalarFn(settings, "never")
assert(settings.visibility == "never",
    "写回的应是**模式字符串**，实得 " .. type(settings.visibility) .. "：" ..
    tostring(settings.visibility) .. "——若这里是 table，说明回调只接了一个参数，"
    .. "收到的是 store 本身")
opts.applyScalarFn(settings, "in_combat")
assert(settings.visibility == "in_combat", "第二次写回同样要落到模式字符串上")
settings.visibility = "always"

----------------------------------------------------------------------
-- 置灰：总开关关掉时该格不可点
----------------------------------------------------------------------
assert(type(opts.disabledFn) == "function", "要给出置灰回调，否则两个开关会平起平坐")
Config.Get().enabled = true
assert(opts.disabledFn() == false, "总开关开着时不该置灰")
Config.Get().enabled = false
assert(opts.disabledFn() == true, "总开关关掉时该格必须置灰，让「谁是主」一眼可见")
Config.Get().enabled = true

io.write("PASS: settings-row\n")
'''


# 场景六：解锁模式的让路规则。
#
# 要分开的是两类隐藏：
#   「现在不满足条件」——它是活的，编辑时该让你调得到，所以让路；
#   「这东西不该存在」——总开关关着、或选了「从不」，不该冒出一个能拖的空框。
#
# 后半段特意让判定返回**显示**：这样一旦隐藏，只可能来自「关掉状态」那条规则，
# 而不是判定本身——否则测出来的是别的东西。
SCENARIO_UNLOCK_BYPASS = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")
local Config = NS.Config

-- 把条件设成「仅战斗中」，人却不在战斗——正是用户在城里想调位置时的处境
Config.Get().visibility = "in_combat"
inCombat = false
NS.Core.Refresh()
assert(frame.shown == false, "非解锁模式下，条件不满足就该隐藏")

----------------------------------------------------------------------
-- 解锁模式：条件让路
----------------------------------------------------------------------
api._unlockActive = true
NS.Core.Refresh()
assert(frame.shown == true,
    "解锁模式下条件必须让路——否则把条件设成「仅战斗中」之后就再也拖不到它了")
assert(elem.isHidden(elem.key) == false, "同上：这时候必须给拖动框")

----------------------------------------------------------------------
-- 但「这东西不该存在」不让路
--
-- 这两段的判定本身是「显示」的，所以一旦隐藏，只可能来自「关掉状态」那条规则。
----------------------------------------------------------------------
Config.Get().enabled = false
NS.Core.Refresh()
assert(frame.shown == false, "总开关关着时，解锁模式也不该把它显示出来")
assert(elem.isHidden(elem.key) == true, "同上：不该冒出一个能拖的空框")

Config.Get().enabled = true
NS.Core.Refresh()
assert(frame.shown == true, "总开关打开后，解锁模式里又该能拖了")

Config.Get().visibility = "never"
NS.Core.Refresh()
assert(frame.shown == false, "选了「从不」时，解锁模式也不该显示——那与总开关是同一类")
assert(elem.isHidden(elem.key) == true, "同上：不该冒出一个能拖的空框")

----------------------------------------------------------------------
-- 退出解锁模式：回到条件判定
----------------------------------------------------------------------
Config.Get().visibility = "in_combat"
api._unlockActive = false
NS.Core.Refresh()
assert(frame.shown == false, "退出解锁模式后行为必须复原")

-- 条件满足时不受影响
inCombat = true
NS.Core.Refresh()
assert(frame.shown == true, "条件满足时应当显示")

io.write("PASS: unlock-bypass\n")
'''


# 场景七：选项通道的隐藏否决。
#
# 实机报过：勾「目标」「敌对目标」「骑乘中」「御空术坐骑」全部毫无反应。
# 根因是判定链只实现了一半——那一整类条件走的是**选项通道**（存在 visOnly*／
# visHide* 字段里），由独立的一个函数判定，而它排在模式集之前。
SCENARIO_OPTION_VETO = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")

-- 没否决时正常显示
optionsVeto = false
NS.Core.Refresh()
assert(frame.shown == true, "选项通道没否决时应当显示")
assert(elem.isHidden(elem.key) == false, "同上")

-- 选项通道否决：必须隐藏
optionsVeto = true
NS.Core.Refresh()
assert(frame.shown == false,
    "选项通道否决时必须隐藏——「目标」「敌对目标」「骑乘中」「御空术坐骑」"
    .. "「副本」「住宅」「休息中」「载具」这一整类条件走的就是这条路")
assert(elem.isHidden(elem.key) == true, "同上：两处必须一致")

-- 否决解除后恢复
optionsVeto = false
api._updaters[1]()
assert(frame.shown == true, "否决解除后应当恢复显示")

----------------------------------------------------------------------
-- 否决必须**领跑**模式集
--
-- 少了这条，实现被改成「先问模式集，只在它返回空时才问否决」也照样全绿——
-- 而 All 模式下「多选集合 + 选项隐藏」会因此重新静默失效，正是本次修的缺陷类。
-- 这里让模式集明确说「显示」，只有否决能把它压成隐藏。
----------------------------------------------------------------------
NS.Config.Get().visibilityModes = { in_combat = true }
sharedVerdict = true
optionsVeto = true
NS.Core.Refresh()
assert(frame.shown == false,
    "选项通道的否决必须排在模式集**之前**：多选说显示也盖不过它")
assert(elem.isHidden(elem.key) == true, "同上：两处一致")

NS.Config.Get().visibilityModes = nil
optionsVeto = false

io.write("PASS: option-veto\n")
'''


# 场景八：专精覆盖下的「关掉状态」。
#
# 本插件**不接受**专精覆盖（配置独立存放，EUI 会在覆盖会话结束后清掉写进来的值），
# 但会话进行中它确实短暂存在，而且 EUI 全家消费者都认它。那时若我们仍按存下来的
# 「从不」判死，就会出现「EUI 的模块都显示了，只有准星不显示」的不一致。
SCENARIO_OVERRIDE = r'''
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")
local Config = NS.Config
local Visibility = assert(NS.Visibility, "应有可见性模块")

Config.Get().visibility = "never"
NS.Core.Refresh()
assert(Visibility.IsOff() == true, "没有覆盖时，「从不」是关掉状态")
assert(frame.shown == false, "同上：不该显示")

-- 覆盖说「总是」：整份可见性配置被它替换，「从不」不再算关掉
overrideValue = "always"
NS.Core.Refresh()
assert(Visibility.IsOff() == false,
    "EUI 的专精覆盖替换整份可见性配置，说「总是」时「从不」就不该再算关掉——"
    .. "否则会出现「EUI 自家模块都显示了，只有准星不显示」")
assert(frame.shown == true, "同上：应当显示")

-- 但总开关仍然是主，覆盖盖不过它
Config.Get().enabled = false
NS.Core.Refresh()
assert(Visibility.IsOff() == true, "总开关关着时，覆盖说了也不算")
assert(frame.shown == false, "同上：不该显示")
Config.Get().enabled = true

-- 覆盖说「从不」时确实是关掉
overrideValue = "never"
NS.Core.Refresh()
assert(Visibility.IsOff() == true, "覆盖说「从不」时是关掉状态")
assert(frame.shown == false, "同上：不该显示")

overrideValue = nil
Config.Get().visibility = "always"
NS.Core.Refresh()
assert(frame.shown == true, "覆盖撤掉后回到正常判定")

io.write("PASS: override\n")
'''


def _run(scenario: str, marker: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "visibility_harness.lua"
        path.write_text(MOCKS + scenario, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS: {marker}" in result.stdout


def test_visibility_falls_open_without_eui_interfaces():
    """EUI 改版／改名／接口消失时，宁可多显示，也不让准星无声无息消失。"""
    _run(SCENARIO_DEGRADATION, "degradation")


def test_assembly_registers_visibility_updater_once():
    """装配时必须把更新器接上——漏接的话条件永远不生效，而且症状是静默的。"""
    _run(SCENARIO_WIRING, "wiring")


def test_verdict_drives_hud_and_unlock_element_together():
    """一次判定翻转，屏幕上有没有它、给不给拖动框，两个答案必须同时变。"""
    _run(SCENARIO_VERDICT, "verdict")


def test_legacy_save_and_demo_mode_stay_visible():
    """旧存档等价于「总是」；演示模式绕过条件——两者都不该让准星消失。"""
    _run(SCENARIO_LEGACY_AND_DEMO, "legacy-demo")


def test_settings_row_position_default_caps_and_greying():
    """可见性那一行的位置、默认值、能力集、置灰与离屏安全。"""
    _run(SCENARIO_SETTINGS_ROW, "settings-row")


def test_unlock_mode_bypasses_conditions_but_not_off_states():
    """解锁模式里条件让路；总开关与「从不」不让路。"""
    _run(SCENARIO_UNLOCK_BYPASS, "unlock-bypass")


def test_option_lane_veto_hides_the_hud():
    """选项通道（目标／敌对目标／骑乘中／御空术坐骑…）的否决必须生效，且领跑模式集。"""
    _run(SCENARIO_OPTION_VETO, "option-veto")


def test_override_replaces_the_off_state_but_not_the_master_switch():
    """专精覆盖替换整份可见性配置；总开关是主，覆盖盖不过它。"""
    _run(SCENARIO_OVERRIDE, "override")
