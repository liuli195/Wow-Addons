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
-- 来源色块**不可编辑**
--
-- 职业色／能量色／职业资源色都由 EUI 统一管理，本插件只能"选用"、不能在这里改色。
-- 实机上报过"点了方框之后再点会弹出取色器"——那正是把这条规则漏了。
-- 规则写成数据（描述符上的 editable），页面照着做，测试盯着它。
----------------------------------------------------------------------
for _, key in ipairs(ORDER) do
    local src = Config.CellPlan(key)[2].source
    assert(src.editable == false,
        key .. " 的来源色块必须标成不可编辑（点了不能再弹取色器）")
end

----------------------------------------------------------------------
-- 常规节的格子清单：总开关 + **可见性** + 缩放 + 图层
--
-- 四项正好两行填满。可见性排在总开关右边，是因为总开关关掉时它会置灰——
-- 两个相邻才看得出从属关系。
--
-- 缩放**要在**（用户复议：宽度／高度／缩放三者走的是同一个 scale，改哪个都一样，
-- 所以留着不冲突，多一个入口更方便）。它的范围必须与 SetHUDSize 的钳位共用同一份
-- 常量——两处各写一份就会出现"滑块能拖到 3.0、实际被钳到 2.0"这种静默不一致。
----------------------------------------------------------------------
assert(type(Config.GeneralCells) == "function", "需要 Config.GeneralCells 这个出口函数")
local general = Config.GeneralCells()
assert(type(general) == "table" and #general > 0, "常规节要有格子")

local texts = {}
for i = 1, #general do
    texts[general[i].text] = true
end
assert(texts["启用准星HUD"], "常规节要有总开关")
assert(texts["图层"], "常规节要有图层")

local scaleCell
for i = 1, #general do
    if general[i].text:find("缩放", 1, true) then scaleCell = general[i] end
end
assert(scaleCell, "常规节要有缩放")
assert(scaleCell.kind == "slider", "缩放应是个滑块")
assert(scaleCell.min == Config.SCALE_MIN and scaleCell.max == Config.SCALE_MAX,
    "缩放滑块的范围必须与钳位共用 Config.SCALE_MIN/MAX")

-- 格子类型是**封闭集合**：新加一种必须在这里显式登记，不能顺手就混进来。
-- `visibility` 是 2026-09-18 有意加的一种：它由 EUI 的共享可见性清单填充，
-- 只需要一个槽位，因此和别的格子一样占半格、走同一套自适应排布。
-- `color` 是 2026-09-19 有意加的一种：阴影是全局一格（颜色 + 浓淡同格），
-- 与元素那些颜色格走同一套 CellSwatches/AttachSwatch，只是配置对象是顶层 cfg。
local ALLOWED = { toggle = true, dropdown = true, slider = true, visibility = true,
                  color = true }
for i = 1, #general do
    local kind = general[i].kind
    assert(ALLOWED[kind],
        "常规节的格子只能是开关、下拉、滑块、可见性或颜色，实得 " .. tostring(kind))
end

-- 可见性紧挨总开关：总开关关掉时它会置灰，相邻才看得出从属关系。
assert(general[2] and general[2].kind == "visibility",
    "第 2 项应是可见性格子，实得 " .. tostring(general[2] and general[2].kind))

----------------------------------------------------------------------
-- 阴影：**全局一格**，颜色与浓淡同格，且只有自定义色
--
-- 用户选的是「一个设置项」——不是每个元素各一套。它是"把 HUD 从混乱背景里抠出来"
-- 这一件事，天然只需要一个口径；所以它落在常规节，不进 Config.CellPlan。
-- 颜色只有自定义色，与「条背景只有自定义」同理，**不能**有来源色块。
----------------------------------------------------------------------
local shadowCell
for i = 1, #general do
    if general[i].kind == "color" and general[i].colorKey == "shadow" then
        shadowCell = general[i]
    end
end
assert(shadowCell, "常规节要有阴影颜色格")
assert(shadowCell.text == "阴影", "阴影格的文字，实得「" .. tostring(shadowCell.text) .. "」")
assert(shadowCell.alphaKey == "shadowAlpha", "阴影格带的是**它自己**的浓淡")
assert(shadowCell.modeKey == nil, "阴影没有第二种来源，不该有 modeKey")
assert(shadowCell.source == nil, "阴影只有自定义色，**不能**有来源色块")

-- 顺序：阴影排在**末位**，而前两项（总开关、可见性）的位置由上面的断言钉住不动。
-- 它会多出来一行（5 项 → 三行、末行右边留空），这是清单自己的排布规则，不是破例。
assert(general[#general] == shadowCell, "阴影格应在常规清单末位")

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
