"""配置页"格子清单"的离线测试。

**为什么单列一条**：页面的排版规则（每项半格、成对成行、末行右边留空、颜色与它
自己的透明度同格、背景没有来源色块）在实机里来回漂过五次——每次都"看着改对了"，
但没有一条断言守着它，所以下一次改动顺手就带回去了。

修法与颜色规则那次一样：把**决策**收进一个纯函数（`Config.CellPlan`），页面只负责
照单渲染。于是规则变成了数据，可以离线断言。

只加载 `Config.lua` 就够——这正是仓库的文件级接缝：页面清单不碰任何魔兽接口，
也不碰 EUI。
"""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
CONFIG = ROOT / "addons/MYUI_CrosshairHUD/Config.lua"


HARNESS = r'''
local source = assert(arg[1])
assert(loadfile(source))()
local Config = assert(_G.MYUI_CHH, "Config.lua 应导出全局表").Config
assert(Config, "全局表上应有 Config")

Config.Load()
local ORDER = Config.ELEMENT_ORDER

assert(type(Config.CellPlan) == "function", "需要 Config.CellPlan 这个出口函数")

----------------------------------------------------------------------
-- 每项只占半格：格子总数决定行数，**末行右边留空**
--
-- 不是"把空位放到第一行"、也不是"为了填满而挪动配置项"。三个元素各有 3 项，
-- 于是 2 行、末行只占左半；准星只有 2 项，正好一行填满。
----------------------------------------------------------------------
local expected = {
    health    = { "启用", "填充颜色", "条背景" },
    power     = { "启用", "填充颜色", "条背景" },
    runes     = { "启用", "填充颜色", "条背景" },
    crosshair = { "启用", "填充颜色" },          -- 准星是线不是块，没有背景
}

for _, key in ipairs(ORDER) do
    local plan = Config.CellPlan(key)
    assert(type(plan) == "table", key .. " 要给出格子清单")

    local want = expected[key]
    assert(#plan == #want,
        key .. " 应恰好 " .. #want .. " 格，实得 " .. #plan)
    for i = 1, #want do
        assert(plan[i].text == want[i],
            key .. " 第 " .. i .. " 格应是「" .. want[i] .. "」，实得「"
            .. tostring(plan[i].text) .. "」")
    end

    -- 行数 = ceil(格数 / 2)；奇数格意味着末行右边留空
    for i = 1, #plan do
        assert(plan[i].kind == "toggle" or plan[i].kind == "color",
            "格子类型只能是开关或颜色")
    end
end
assert(#Config.CellPlan("health") % 2 == 1, "生命值条末行应留空（3 格 → 2 行）")
assert(#Config.CellPlan("crosshair") % 2 == 0, "准星 2 格正好一行，不留空")

----------------------------------------------------------------------
-- 颜色格：**色块与它自己的透明度滑块同格**
--
-- 键必须是该格自己的 alpha——把填充的透明度放到别的格里，就是用户说的
-- "又被你分开了"。
----------------------------------------------------------------------
local plan = Config.CellPlan("health")
local fillCell = plan[2]
assert(fillCell.kind == "color", "第二格是颜色格")
assert(fillCell.alphaKey == "fillAlpha", "填充颜色格带的是填充透明度")
assert(fillCell.colorKey == "fill", "填充颜色格带的是填充色")

local bgCell = plan[3]
assert(bgCell.kind == "color", "第三格是颜色格")
assert(bgCell.alphaKey == "bgAlpha", "条背景格带的是背景透明度")
assert(bgCell.colorKey == "bg", "条背景格带的是背景色")

-- 一格里只能有一个 alpha，不能两个颜色格共用一个
assert(fillCell.alphaKey ~= bgCell.alphaKey, "填充与背景的透明度必须是两个值")

----------------------------------------------------------------------
-- 来源色块：只有填充有，背景没有
----------------------------------------------------------------------
assert(fillCell.source ~= nil, "填充颜色格要有第二个色块（来源色）")
assert(bgCell.source == nil, "条背景格**不能**有来源色块——背景只有自定义色")

assert(fillCell.source.mode == "class", "生命值条的来源色是职业色")
assert(Config.CellPlan("power")[2].source.mode == "power", "能量条的来源色是能量色")
assert(Config.CellPlan("runes")[2].source.mode == "resource",
    "职业资源条的来源色是职业资源色")
assert(Config.CellPlan("crosshair")[2].source.mode == "class", "准星的来源色是职业色")

----------------------------------------------------------------------
-- 置灰：总开关关掉时所有子项都算关掉（子开关与色块一起失效）
----------------------------------------------------------------------
for _, key in ipairs(ORDER) do
    Config.Get().enabled = true
    Config.Get().elements[key].enabled = true
    assert(Config.Grayed(key) == false, key .. " 全开时不该置灰")
    Config.Get().elements[key].enabled = false
    assert(Config.Grayed(key) == true, key .. " 自己关掉时该置灰")
    Config.Get().elements[key].enabled = true
    Config.Get().enabled = false
    assert(Config.Grayed(key) == true, key .. " 总开关关掉时该置灰")
    Config.Get().enabled = true
end

----------------------------------------------------------------------
-- 界面文案：显示名与层级名
----------------------------------------------------------------------
assert(Config.ELEMENT_LABELS.health == "生命值条", "生命值条的显示名")
assert(Config.ELEMENT_LABELS.power == "能量条", "能量条的显示名")
assert(Config.ELEMENT_LABELS.runes == "职业资源条", "职业资源条的显示名")
assert(Config.ELEMENT_LABELS.crosshair == "准星", "准星的显示名")

-- 层级：**键是存下来交给魔兽的值，内容是显示文字**。哪天有人把键也改成中文，
-- SetFrameStrata 就会收到非法值——这条断言就是防这个的。
local strata = Config.STRATA_VALUES
assert(strata, "层级映射表要导出，测试才盯得住")
for _, key in ipairs({ "LOW", "MEDIUM", "HIGH", "DIALOG" }) do
    assert(type(strata[key]) == "string" and strata[key] ~= key,
        "层级「" .. key .. "」应显示为中文")
end

io.write("PASS: config cell plan\n")
'''


def test_config_cell_plan():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "plan_harness.lua"
        path.write_text(HARNESS, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(CONFIG)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: config cell plan" in result.stdout
