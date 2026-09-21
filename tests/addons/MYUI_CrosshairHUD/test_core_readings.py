"""弧线角度取值链的离线测试。

**为什么这条必须离线测**：受限上下文里血量和符能是秘密值，实机**无法按需触发**
这一段——用户没办法在游戏里切换"现在给我秘密值"。而这条链恰好又是整个 HUD 最容易
悄悄失效的地方：它一旦断了，表现就是两条弧永远空着，而任何断言都不会报错。

被断言的行为是**策略**，分两条：

1. 比例 → 角度的映射由曲线端点定死。`MaskAngle` 对比例是仿射的，所以曲线只用两个
   端点就精确等价于原公式——测试直接核对"曲线的线性求值 == MaskAngle"。
2. 引擎交回来的角度**可能是秘密值**：必须原样转交，绝不运算、绝不因为它是秘密值就
   丢弃。这条反过来断言——喂一个会被判为秘密值的数值进去，看它是否**原封不动**地
   出现在结果里（任何算术都会改变它）。

harness 以零参数 `loadfile` 依次加载 `Logic`、`Elements`、`Config`、`Core`——
这正是仓库 harness 提供的**文件级接缝**。测试不需要 `PLAYER_LOGIN`：读数走
`Core.UpdateReadings()`，不碰渲染，因此不必 mock 任何纹理接口。
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
-- WoW 接口 mock（必须在加载 Core 之前就位——它在主 chunk 里就读全局）
----------------------------------------------------------------------
local secret = {}                 -- 「不可读对象」哨兵
local secretNumber = nil          -- 「数值型秘密值」哨兵，见下方关键用例
local issecretvalueThrows = false

function issecretvalue(value)
    if issecretvalueThrows then error("secret check unavailable") end
    return value == secret or value == secretNumber
end

-- 符文读数：默认 1、2 就绪，其余充能中；runeSecret 打开时整次调用返回哨兵值
local runeSecret = false
function GetRuneCooldown(index)
    if runeSecret then return secret, secret, secret end
    return index, 10, index <= 2
end

function GetTime() return 100 end
function InCombatLockdown() return false end
function print() end

UIParent = {}
SlashCmdList = {}
C_AddOns = { GetAddOnMetadata = function() return "test" end,
             IsAddOnLoaded = function() return true end }
C_Timer = { After = function() end, NewTicker = function() return {} end }

Enum = { PowerType = { RunicPower = 6 }, LuaCurveType = { Linear = 0 } }

----------------------------------------------------------------------
-- 引擎端的曲线：只实现线性插值，被测代码也只用线性
--
-- 记录每一根建出来的曲线，供断言"端点是不是从 ArcCurvePoints 来的"。
----------------------------------------------------------------------
local curves = {}
C_CurveUtil = {
    CreateCurve = function()
        local curve = { points = {}, curveType = nil }
        function curve:SetType(kind) self.curveType = kind end
        function curve:AddPoint(x, y) self.points[#self.points + 1] = { x = x, y = y } end
        function curve:Evaluate(x)
            local p, q = self.points[1], self.points[2]
            return p.y + (q.y - p.y) * ((x - p.x) / (q.x - p.x))
        end
        curves[#curves + 1] = curve
        return curve
    end,
}

local healthFrac, powerFrac = 1.0, 0.6
local engineThrows = false
local forcedAngle = nil           -- 非 nil 时引擎直接返回它（可以是秘密值）

function UnitHealthPercent(unit, usePredicted, curve)
    assert(unit == "player", "只查 player")
    assert(usePredicted == false, "电弧要的是**实际**血量，不是预测治疗后的")
    assert(type(curve) == "table" and curve.Evaluate, "第三条必须是曲线")
    if engineThrows then error("engine unavailable") end
    if forcedAngle ~= nil then return forcedAngle end
    return curve:Evaluate(healthFrac)
end

-- 参数次序是 单位、能量类型、unmodified、曲线——顺序错了这里就炸
function UnitPowerPercent(unit, powerType, unmodified, curve)
    assert(unit == "player", "只查 player")
    assert(powerType == 6, "能量类型必须是 RunicPower")
    assert(unmodified == false, "unmodified 必须是 false")
    assert(type(curve) == "table" and curve.Evaluate, "第四条必须是曲线")
    if engineThrows then error("engine unavailable") end
    if forcedAngle ~= nil then return forcedAngle end
    return curve:Evaluate(powerFrac)
end

-- 事件注册**必须校验**，否则这个 mock 会放过真实的加载期错误：
-- 真客户端对单位事件有白名单，注册了非单位事件会直接抛错、中断整个文件，
-- 而空函数 mock 一声不吭。这里用"单位事件一律以 UNIT_ 开头"这条近似约束兜住它。
local registered = {}
local function isUnitEvent(name) return name:sub(1, 5) == "UNIT_" end

local firstFrame
function CreateFrame(_, name)
    local frame = { name = name, scripts = {} }
    function frame:RegisterEvent(event)
        registered[#registered + 1] = event
    end
    function frame:RegisterUnitEvent(event, unit)
        assert(isUnitEvent(event),
            "RegisterUnitEvent 收到了非单位事件：" .. tostring(event))
        assert(unit == "player", "本插件只注册 player 单位")
        registered[#registered + 1] = event
    end
    function frame:SetScript(kind, callback) self.scripts[kind] = callback end
    function frame:UnregisterAllEvents() end
    function frame:GetFrameLevel() return 1 end
    if not firstFrame then firstFrame = frame end
    return frame
end

----------------------------------------------------------------------
-- 按清单顺序加载四个模块（这正是仓库 harness 提供的文件级接缝）
----------------------------------------------------------------------
for _, name in ipairs({ "Logic", "Elements", "Config", "Core" }) do
    assert(loadfile(dir .. "/" .. name .. ".lua"))()
end
local NS = assert(_G.MYUI_CHH)
local Logic = assert(NS.Logic)
local Core = assert(NS.Core)

-- 生产环境里曲线是 PLAYER_LOGIN 时建的；这里比照调用同一段装配
assert(type(NS.Core.BuildArcCurves) == "function", "建曲线的入口应可被测试调用")
NS.Core.BuildArcCurves()

local function Near(a, b, what)
    assert(type(a) == "number" and math.abs(a - b) < 1e-9,
        what .. "：期望 " .. tostring(b) .. " 实得 " .. tostring(a))
end

----------------------------------------------------------------------
-- 曲线端点必须来自 ArcCurvePoints（几何的唯一来源）
----------------------------------------------------------------------
assert(#curves == 2, "应只建两根曲线（血量、符能），实得 " .. #curves)
local a0, a1 = Logic.ArcCurvePoints(Logic.ARCS.power.start, Logic.ARCS.power.span,
    Logic.ARCS.power.reverse)
local found = false
for _, curve in ipairs(curves) do
    local p, q = curve.points[1], curve.points[2]
    assert(curve.curveType == Enum.LuaCurveType.Linear, "曲线必须是线性")
    if p and math.abs(p.y - a0) < 1e-12 and math.abs(q.y - a1) < 1e-12 then
        found = true
    end
end
assert(found, "符能曲线端点必须等于 ArcCurvePoints")

----------------------------------------------------------------------
-- 关键性质：曲线的线性求值 == MaskAngle（仿射映射的两个端点足够）
--
-- 这条成立，曲线才可能"精确等价于原公式"；不成立就该回头改公式而不是改曲线。
----------------------------------------------------------------------
for _, arc in ipairs({ Logic.ARCS.health, Logic.ARCS.power }) do
    local low, high = Logic.ArcCurvePoints(arc.start, arc.span, arc.reverse)
    for i = 0, 20 do
        local f = i / 20
        local linear = low + (high - low) * f
        Near(linear, Logic.MaskAngle(arc.start, arc.span, f, arc.reverse),
            "曲线求值必须等于 MaskAngle（f=" .. f .. "）")
    end
end

----------------------------------------------------------------------
-- 满血与半血
----------------------------------------------------------------------
Core.UpdateReadings()
local r = Core.GetReadings()
assert(r.hasHealth == true, "满血应取到角度")
Near(r.healthRotation, Logic.MaskAngle(Logic.ARCS.health.start, Logic.ARCS.health.span, 1),
    "满血角度")
assert(r.hasPower == true, "符能应取到角度")
Near(r.powerRotation, Logic.MaskAngle(Logic.ARCS.power.start, Logic.ARCS.power.span,
    powerFrac, Logic.ARCS.power.reverse), "符能角度")

healthFrac = 0.5
Core.UpdateReadings()
Near(Core.GetReadings().healthRotation,
    Logic.MaskAngle(Logic.ARCS.health.start, Logic.ARCS.health.span, 0.5), "半血角度")

-- 血量归零：角度虽为起点值，但"取到了"仍然必须为真——空弧靠遮罩自然表现，
-- 不靠在这里拦。
healthFrac = 0
Core.UpdateReadings()
assert(Core.GetReadings().hasHealth == true, "空血也必须算取到")

----------------------------------------------------------------------
-- **关键用例**：引擎交回秘密值时，必须**原样转交**
--
-- 上一版策略是"检测到秘密值就丢弃、保留上次的值"。那是错的：秘密值本身就是
-- 合法的显示输入，丢弃它等于在受限内容里把血条打死。正确做法是把它从 setter
-- 转交到 setter。这条用 4242 当哨兵——任何算术都会改变它，因此"原封不动"就
-- 等价于"没运算过"。
----------------------------------------------------------------------
healthFrac = 0.5
secretNumber = 4242
forcedAngle = secretNumber
Core.UpdateReadings()
local s = Core.GetReadings()
assert(s.hasHealth == true, "秘密值也是合法的显示输入，不许丢弃")
assert(s.healthRotation == secretNumber,
    "秘密角度必须原封不动地转交（任何算术都会改变它），实得 " ..
    tostring(s.healthRotation))
assert(s.hasPower == true, "符能同理")

----------------------------------------------------------------------
-- 引擎抛错时才保留上一次的值（取不到 ≠ 取到的是秘密值）
----------------------------------------------------------------------
forcedAngle = nil
engineThrows = true
Core.UpdateReadings()
local t = Core.GetReadings()
assert(t.hasHealth == true, "引擎抛错应保留上一次的取数状态")
assert(t.healthRotation == secretNumber, "引擎抛错应保留上一次的角度")
engineThrows = false
secretNumber = nil

----------------------------------------------------------------------
-- 恢复正常后必须继续跟随（降级不能把它卡死）
----------------------------------------------------------------------
healthFrac = 0.25
Core.UpdateReadings()
Near(Core.GetReadings().healthRotation,
    Logic.MaskAngle(Logic.ARCS.health.start, Logic.ARCS.health.span, 0.25), "恢复后跟随")

----------------------------------------------------------------------
-- 符文：读到不可读的值必须降级成「空转」，绝不猜一个数字
--
-- GetRuneCooldown 结构上不返回秘密值，但真遇上时一律按空转处理——空转的表现是
-- 整格背景色，而不是把比例算成 1% 或 0%。
----------------------------------------------------------------------
runeSecret = true
Core.UpdateReadings()
local runes = Core.GetReadings().runes
for i = 1, Logic.PIPS.count do
    assert(runes[i].state == Logic.RUNE_EMPTY,
        "不可读的符文读数必须降级成空转，第 " .. i .. " 格实得 " .. tostring(runes[i].state))
end
runeSecret = false
Core.UpdateReadings()
assert(Core.GetReadings().runes[1].state == Logic.RUNE_READY, "恢复后就绪态应回来")

io.write("PASS: arc rotation chain\n")
'''


def test_arc_rotation_chain():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "readings_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: arc rotation chain" in result.stdout
