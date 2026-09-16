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
-- 语义：弧上参数 t ∈ [0,1] 的点被填充，当且仅当 t < f。
-- 独立模型：该点被遮罩露出，当且仅当它落在不透明半平面内。
-- 两者必须处处一致。跳过切线本身（该点归哪边不影响外观）。
----------------------------------------------------------------------
local curves = {
    { name = "血弧",   start = Logic.ARCS.health.start, span = Logic.ARCS.health.span },
    { name = "符能弧", start = Logic.ARCS.power.start,  span = Logic.ARCS.power.span },
}
for i = 1, Logic.PIPS.count do
    curves[#curves + 1] = {
        name = "符文格" .. i,
        start = Logic.PIPS.start + (i - 1) * Logic.PIPS.step,
        span = Logic.PIPS.span,
    }
end

local checked = 0
for _, curve in ipairs(curves) do
    for fi = 0, 100 do
        local f = fi / 100
        local theta = Logic.MaskAngle(curve.start, curve.span, f)
        for ai = 1, 399 do
            local t = ai / 400
            if t ~= f then
                local phi = curve.start + curve.span * t
                local want = t < f
                local got = MaskReveals(theta, phi)
                assert(want == got, string.format(
                    "%s f=%.2f t=%.4f 期望 %s 实得 %s",
                    curve.name, f, t, tostring(want), tostring(got)))
                checked = checked + 1
            end
        end
    end
end
assert(checked > 300000, "核对点数异常偏少")

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
