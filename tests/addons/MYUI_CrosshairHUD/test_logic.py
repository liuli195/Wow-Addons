"""准星 HUD 纯逻辑模块的离线测试。

被测的是 `addons/MYUI_CrosshairHUD/Logic.lua`——它加载时不触碰任何魔兽接口，
所以能在这个 harness 里以零参数 `loadfile` 加载。

**弧线换算的核对方式是本测试的重点**：它不断言 `MaskAngle` 的返回值等于某个数
（那是对公式自证），而是用一套**独立的几何判据**逐点核对——把公式算出的旋转角喂给
"遮罩如何工作"的独立模型，看它给出的可见性与"该点是否应当被填充"是否处处一致。

这套判据 + `scripts/media/verify_crosshair_media.py` 对遮罩**图像方向**的断言，
合起来才把「遮罩约定 ↔ 换算公式」这一对钉死；只测其中一边都锁不住。

先例：`tests/addons/Sim2GSEProbe/test_probe.py`（同样的"Python 驱动本机 Lua 5.1"形状）。
"""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/MYUI_CrosshairHUD/Logic.lua"


HARNESS = r'''
local source = assert(arg[1])
assert(loadfile(source))()
local Logic = assert(_G.MYUI_CHH, "Logic.lua 应导出全局表").Logic
assert(Logic, "全局表上应有 Logic")

----------------------------------------------------------------------
-- 几何常量与设计稿一致
----------------------------------------------------------------------
assert(Logic.RING.radius == 54 and Logic.RING.stroke == 6, "圆环常量")
assert(Logic.ARCS.health.start == 99 and Logic.ARCS.health.span == 102, "血弧常量")
assert(Logic.ARCS.power.start == 339 and Logic.ARCS.power.span == 102, "符能弧常量")
-- 两条弧都必须**从靠近 6 点钟那端向上长**：左弧顺时针、右弧逆时针。
-- 右弧的几何跨度是 339°→441°，从 441°（下方）那端长起就是逆时针，故必须 reverse。
assert(Logic.ARCS.power.reverse == true, "符能弧必须反向填充")
assert(Logic.ARCS.health.reverse ~= true, "血弧是正向填充")
assert(Logic.PIPS.start == 219 and Logic.PIPS.step == 18
    and Logic.PIPS.span == 12 and Logic.PIPS.count == 6, "符文格常量")

----------------------------------------------------------------------
-- 独立几何判据
--
-- 遮罩图像左半不透明。旋转 θ（弧度，逆时针为正）后，不透明区域是半平面
--     {p : p·(cosθ, sinθ) < 0}
-- 设计稿角度 φ 为从正东顺时针、y 向下；魔兽角度 ψ 向上为正，故 ψ = -φ。
----------------------------------------------------------------------
local function MaskReveals(theta, phi)
    return math.cos(math.rad(-phi) - theta) < 0
end

----------------------------------------------------------------------
-- 弧线填充：逐点核对
--
-- 语义：弧上参数 t ∈ [0,1] 的点被填充，当且仅当
--     正向（reverse 为假）：t < f          —— 从 start 那端长起
--     反向（reverse 为真）：t > 1 - f      —— 从另一端长起
-- 独立模型：该点被遮罩露出，当且仅当它落在不透明半平面内。
-- 两者必须处处一致。跳过切线本身（该点归哪边不影响外观）。
----------------------------------------------------------------------
local curves = {
    { name = "血弧",   start = Logic.ARCS.health.start, span = Logic.ARCS.health.span,
      reverse = Logic.ARCS.health.reverse },
    { name = "符能弧", start = Logic.ARCS.power.start,  span = Logic.ARCS.power.span,
      reverse = Logic.ARCS.power.reverse },
}
for i = 1, Logic.PIPS.count do
    curves[#curves + 1] = {
        name = "符文格" .. i,
        start = Logic.PIPS.start + (i - 1) * Logic.PIPS.step,
        span = Logic.PIPS.span,
    }
end

----------------------------------------------------------------------
-- 填充的映射：切口从「弧起点往回 δ」走到「弧终点」
--
-- δ 是留给遮罩软边与素材描边余量的角度。实机上弧的起点会露出 1–2 像素的一条边：
-- 遮罩的不透明侧在切口之前就开始变淡、素材的弧尖也略超出标称起点，而把切口当作
-- **零宽度的硬边**时，f=0 的切口正好压在弧起点上，那点余量就被点着了。
-- 所以切口要退到起点之前，f=1 时再盖过终点——两头都不留缝。
----------------------------------------------------------------------
local DELTA = 2          -- 规格值：余量至少 2°（实测软边 ≈ 1.06°，留一点裕度）

local function Cut(span, f)
    return (span + DELTA) * f - DELTA
end

assert(Cut(102, 0) <= -DELTA + 1e-9, "f=0 时切口必须退到弧起点之前")
assert(Cut(102, 1) >= 102 - 1e-9, "f=1 时切口必须盖过弧终点")

local checked = 0
for _, curve in ipairs(curves) do
    local span = curve.span
    for fi = 0, 100 do
        local f = fi / 100
        local theta = Logic.MaskAngle(curve.start, span, f, curve.reverse)
        local cut = Cut(span, f)
        for ai = 1, 399 do
            local t = ai / 400
            local along = curve.reverse and span * (1 - t) or span * t
            -- 跳过正好落在切线上的采样点：它归哪边都不影响外观，而浮点相等
            -- 不可靠（1-0.18 是 0.8200000000000001）。
            if math.abs(along - cut) > 1e-6 then
                local phi = curve.start + span * t
                local want = along < cut
                local got = MaskReveals(theta, phi)
                assert(want == got, string.format(
                    "%s f=%.2f t=%.4f 距起点 %.3f 切口 %.3f 期望 %s 实得 %s",
                    curve.name, f, t, along, cut, tostring(want), tostring(got)))
                checked = checked + 1
            end
        end
    end
end
assert(checked > 300000, "核对点数异常偏少")

-- 余量必须是具名的常量，供实现与素材侧校验共用
assert(type(Logic.FILL_MARGIN) == "number" and Logic.FILL_MARGIN >= DELTA,
    "要有具名的余量常量 Logic.FILL_MARGIN，且不小于规格值 " .. DELTA)

----------------------------------------------------------------------
-- 方向（点名核对，便于失败时一眼看出是哪条弧反了）
--
-- 血弧 99°→201°，99° 是刚过 6 点钟；符能弧 339°→441°，441°≡81° 是刚到 6 点钟之前。
-- 两条弧「靠近 6 点钟的那端」分别是参数上的 t=0 与 t=1——填充必须从那里开始。
----------------------------------------------------------------------
local thetaSmall = Logic.MaskAngle(99, 102, 0.1)
assert(MaskReveals(thetaSmall, 99 + 102 * 0.05), "血弧应从 99°（近 6 点钟）那端长起")
assert(not MaskReveals(thetaSmall, 99 + 102 * 0.95), "血弧不该从远端长起")

thetaSmall = Logic.MaskAngle(339, 102, 0.1, true)
assert(MaskReveals(thetaSmall, 339 + 102 * 0.95), "符能弧应从 81°（近 6 点钟）那端长起")
assert(not MaskReveals(thetaSmall, 339 + 102 * 0.05), "符能弧不该从 339° 那端长起")

-- 两个端点值：f=0 全暗、f=1 全亮。反向分支最容易在这里做反（错把切口当保留侧）。
for _, case in ipairs({ { 99, 102, false }, { 339, 102, true } }) do
    local mid = case[1] + case[2] * 0.5
    assert(not MaskReveals(Logic.MaskAngle(case[1], case[2], 0, case[3]), mid),
        "f=0 必须整条弧全暗")
    assert(MaskReveals(Logic.MaskAngle(case[1], case[2], 1, case[3]), mid),
        "f=1 必须整条弧全亮")
end

----------------------------------------------------------------------
-- 符文充能：三态与全部边界
----------------------------------------------------------------------
local frac, state, remaining

-- 就绪：必须短路，绝不进除法（就绪时 start 为 0，除法会得到巨大值）
frac, state, remaining = Logic.RuneCharge(0, 10, true, 100)
assert(frac == 1 and state == Logic.RUNE_READY and remaining == 0, "就绪态")

-- 就绪判定优先于参数检查：即使其余参数不可读，也应报就绪
frac, state = Logic.RuneCharge(nil, nil, true, 100)
assert(state == Logic.RUNE_READY, "就绪应优先于空值检查")

-- 充能中
frac, state, remaining = Logic.RuneCharge(100, 10, false, 106)
assert(state == Logic.RUNE_RECHARGING, "充能中态")
assert(math.abs(frac - 0.6) < 1e-9, "充能比例")
assert(math.abs(remaining - 4) < 1e-9, "剩余时间")

-- 空转：整次调用什么都不返回
frac, state, remaining = Logic.RuneCharge(nil, nil, nil, 100)
assert(frac == 0 and state == Logic.RUNE_EMPTY, "空转态")
assert(remaining == nil, "空转的剩余时间必须是 nil，不能是 math.huge")

-- 空转与「0% 充能」必须可区分——这是初版方案最容易做错的地方
local _, zeroState = Logic.RuneCharge(100, 10, false, 100)
assert(zeroState == Logic.RUNE_RECHARGING, "0% 充能仍属于充能中")

-- duration 为 0 也要降级成空转，不能除零
frac, state, remaining = Logic.RuneCharge(100, 0, false, 100)
assert(state == Logic.RUNE_EMPTY and remaining == nil, "duration 为 0")

-- 时钟抖动：now 早于 start 时钳到 0
frac, state = Logic.RuneCharge(100, 10, false, 95)
assert(frac == 0 and state == Logic.RUNE_RECHARGING, "时钟回拨钳位")

-- 速率突变：now 超过 start + duration 时钳到 1
frac, state = Logic.RuneCharge(100, 10, false, 200)
assert(frac == 1 and state == Logic.RUNE_RECHARGING, "超时钳位")

----------------------------------------------------------------------
-- 符文排序：三个键缺一不可
----------------------------------------------------------------------
local function rune(index, state, remaining)
    return { index = index, state = state, remaining = remaining }
end

-- 键一：就绪在前
local order = Logic.RuneOrder({
    rune(1, Logic.RUNE_RECHARGING, 3),
    rune(2, Logic.RUNE_READY, 0),
    rune(3, Logic.RUNE_EMPTY, nil),
}, 3)
assert(order[1] == 2 and order[2] == 1 and order[3] == 3, "就绪在前、空转垫底")

-- 键二：充能中按剩余升序
order = Logic.RuneOrder({
    rune(1, Logic.RUNE_RECHARGING, 8),
    rune(2, Logic.RUNE_RECHARGING, 2),
    rune(3, Logic.RUNE_RECHARGING, 5),
}, 3)
assert(order[1] == 2 and order[2] == 3 and order[3] == 1, "按剩余升序")

-- 键三：剩余完全相同时，结果必须与输入顺序无关（否则非稳定排序会让槽位每轮换位）
local a = { rune(1, Logic.RUNE_RECHARGING, 5), rune(2, Logic.RUNE_RECHARGING, 5),
            rune(3, Logic.RUNE_RECHARGING, 5) }
local b = { rune(3, Logic.RUNE_RECHARGING, 5), rune(1, Logic.RUNE_RECHARGING, 5),
            rune(2, Logic.RUNE_RECHARGING, 5) }
local oa, ob = Logic.RuneOrder(a, 3), Logic.RuneOrder(b, 3)
for i = 1, 3 do
    assert(oa[i] == ob[i], "同剩余时间的排序必须与输入顺序无关")
end
assert(oa[1] == 3 and oa[2] == 2 and oa[3] == 1, "索引降序决胜")

----------------------------------------------------------------------
-- 曲线端点：比例 → 角度是**仿射**映射，两个端点就把它定死
--
-- 受限上下文里比例是秘密值，只能把这条映射做成曲线交给引擎求值，所以"端点"
-- 是整个几何的对外出口——它必须由 MaskAngle 导出，不许另写一份。这里顺带
-- 核实端点之间的线性求值与原公式处处相等：那是"曲线等价于公式"的全部依据。
----------------------------------------------------------------------
for _, arc in ipairs({ Logic.ARCS.health, Logic.ARCS.power }) do
    local low, high = Logic.ArcCurvePoints(arc.start, arc.span, arc.reverse)
    assert(low == Logic.MaskAngle(arc.start, arc.span, 0, arc.reverse), "曲线起点")
    assert(high == Logic.MaskAngle(arc.start, arc.span, 1, arc.reverse), "曲线终点")
    for i = 0, 20 do
        local f = i / 20
        local linear = low + (high - low) * f
        assert(math.abs(linear - Logic.MaskAngle(arc.start, arc.span, f, arc.reverse)) < 1e-12,
            "端点间的线性求值必须等于 MaskAngle（f=" .. f .. "）")
    end
end

----------------------------------------------------------------------
-- 假数据的两个比例：**方向必须与真实行为一致**
--
-- demo 是"没有战斗时检查外观"的唯一手段（`/chh demo`）。方向演反了，看的人会得出
-- 与真实相反的结论——实机上已经因此误判过一次（"血条默认是空的、能量条不填充"，
-- 其实是 demo 在演反）。生命值满血起、逐步掉；能量空起、逐步涨。
----------------------------------------------------------------------
assert(type(Logic.DemoFills) == "function", "需要 Logic.DemoFills 这个出口函数")

local h0, p0 = Logic.DemoFills(0)
assert(h0 == 1, "假数据的生命值从满开始，实得 " .. tostring(h0))
assert(p0 == 0, "假数据的能量从空开始，实得 " .. tostring(p0))

local hh, pp = Logic.DemoFills(0.5)
assert(math.abs(hh - 0.5) < 1e-9, "半程时生命值应到一半")
assert(math.abs(pp - 0.5) < 1e-9, "半程时能量应到一半")

local h1, p1 = Logic.DemoFills(1)
assert(h1 == 0, "走完一轮后生命值见底")
assert(p1 == 1, "走完一轮后能量充满")

-- 单调：生命值只降不升、能量只升不降（反向演示会在这里露馅）
local lastH, lastP = Logic.DemoFills(0)
for i = 1, 20 do
    local h, p = Logic.DemoFills(i / 20)
    assert(h <= lastH + 1e-9, "生命值必须单调下降")
    assert(p >= lastP - 1e-9, "能量必须单调上升")
    lastH, lastP = h, p
end

-- 越界钳位：轮次回绕不该算出负数或超过 1
assert(Logic.DemoFills(-0.5) == 1, "t 为负应钳到 0 那一刻")
assert(Logic.DemoFills(1.5) == 0, "t 超过 1 应钳到 1 那一刻")

io.write("PASS: logic seam (", checked, " 个弧上采样点逐点核对)\n")
'''


def test_logic_seam():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "logic_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: logic seam" in result.stdout
