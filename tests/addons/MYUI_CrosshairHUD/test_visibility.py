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
}
_G.EllesmereUI = api

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
local NS = Load()
FireLogin()

local Visibility = assert(NS.Visibility, "应有可见性模块")
assert(type(Visibility.ShouldShow) == "function", "应暴露「该不该显示」这一条问答")

local verdict = Visibility.ShouldShow()
assert(type(verdict) == "boolean",
    "必须返回真布尔——四值协议（真／假／悬停／空）要压在这个模块里面，实得 "
    .. type(verdict) .. "：" .. tostring(verdict))
assert(verdict == true,
    "EUI 没有可见性接口时必须答「显示」：降级时配置页那一行多半也一起失效了，"
    .. "用户没有自救手段，显示至少还能用")

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
local verdict = true
api.EvalVisibilityExtended = function() return verdict end
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")

assert(frame.shown == true, "判定为显示时，框体应当在屏幕上")
assert(elem.isHidden(elem.key) == false, "判定为显示时，不应报告隐藏")

-- 翻转判定，再走 EUI 通知更新器那条路（这正是实机里条件变化时的路径）
verdict = false
assert(api._updaters and api._updaters[1], "应已注册更新器")
api._updaters[1]()

assert(frame.shown == false, "判定为隐藏时，框体必须从屏幕上消失")
assert(elem.isHidden(elem.key) == true,
    "同一次翻转下，解锁元素必须同时报告隐藏——两处不一致的可见症状是"
    .. "「屏幕上看不见它，正中却留着一个能拖的空框」")

-- 翻回来也要一致
verdict = true
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
api.EvalVisibilityExtended = function() return nil end   -- 旧标量：共享引擎交回「空」
api.RegisterVisibilityUpdater = function(fn)
    api._updaters = api._updaters or {}
    api._updaters[#api._updaters + 1] = fn
end

local NS = Load()
FireLogin()

local elem = assert(api._elements and api._elements[1], "应注册解锁元素")
local frame = assert(NS.Elements.frame, "应建出框体")

-- 「空」的语义是「回落旧标量」，不是「显示」；本插件没有旧标量可回落，
-- 于是按「无条件」处理。旧存档因此与升级前完全一致。
assert(frame.shown == true, "没有可见性配置的旧存档，行为必须与升级前一致")
assert(elem.isHidden(elem.key) == false, "同上：不该报告隐藏")

-- 换成一个明确的隐藏判定，确认上一段不是碰巧
api.EvalVisibilityExtended = function() return false end
api._updaters[1]()
assert(frame.shown == false, "明确的隐藏判定下应当消失")

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
local W = {}
function W:DualRow()
    return { _leftRegion = Region(), _rightRegion = Region() }, 10
end
function W:SectionHeader() return {}, 20 end

_G.EllesmereUI = {
    Widgets = W,
    BuildColorSwatch = function() return Widget() end,
    RegisterWidgetRefresh = function() end,
    ShowWidgetTooltip = function() end,
    HideWidgetTooltip = function() end,
    AttachVisibilityChecklist = function(region, opts) attached[#attached + 1] = opts end,
}

local height = Config.BuildPage(nil, nil, 0)
assert(type(height) == "number", "建完页仍要返回数字高度，实得 " .. type(height))
assert(#attached == 1, "应恰好挂一份可见性清单，实得 " .. #attached)

local opts = attached[1]
assert(opts.legacyKey == "visibility",
    "键名必须是 visibility，实得 " .. tostring(opts.legacyKey))
assert(type(opts.getStore) == "function",
    "存储必须以**取值函数**交出：配置加载会替换整个表对象，交缓存表会读写废表")
assert(opts.caps == Config.VIS_CAPS, "设置页必须用与求值同一份能力集")

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
