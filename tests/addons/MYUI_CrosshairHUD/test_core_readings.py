"""读数降级分支的离线测试。

**为什么这条必须离线测**：秘密值降级在实机**无法按需触发**——用户没办法在游戏里
让血量接口返回秘密值，16 条人工验收清单一条都盖不到它。而仓库的测试 harness 今天
就能造出来：`tests/addons/Sim2GSEProbe/test_probe.py:26` 已示范哨兵值写法。

被断言的行为是**策略**，不是实现：取到不可读的值时**跳过本次更新、保留上一次的值**，
绝不让它参与比较或算术，也绝不猜一个数字。

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
local health, healthMax = 1000, 1000
local power, powerMax = 60, 100
local secretHealth, secretPower = false, false
local issecretvalueThrows = false

function UnitHealth() return secretHealth and secret or health end
function UnitHealthMax() return healthMax end
function UnitPower() return secretPower and secret or power end
function UnitPowerMax() return powerMax end
function GetRuneCooldown(index) return index, 10, index <= 2 end
function GetTime() return 100 end
function InCombatLockdown() return false end
function print() end
function issecretvalue(value)
    if issecretvalueThrows then error("secret check unavailable") end
    return value == secret or value == secretNumber
end

UIParent = {}
Enum = { PowerType = { RunicPower = 6 } }
SlashCmdList = {}
C_AddOns = { GetAddOnMetadata = function() return "test" end,
             IsAddOnLoaded = function() return true end }
C_Timer = { After = function() end, NewTicker = function() return {} end }

local firstFrame
function CreateFrame(_, name)
    local frame = { name = name, scripts = {} }
    function frame:RegisterEvent() end
    function frame:RegisterUnitEvent() end
    function frame:SetScript(kind, callback) self.scripts[kind] = callback end
    function frame:UnregisterAllEvents() end
    function frame:GetFrameLevel() return 1 end
    if not firstFrame then firstFrame = frame end
    return frame
end

----------------------------------------------------------------------
-- 按清单顺序加载四个模块（这正是仓库 harness 提供的文件级接缝）
--
-- 先断言 mock 已就位：被测代码在**读取时**查 issecretvalue，若这里忘了定义，
-- 降级分支会静默失效、测试却照过——那是这个 harness 最容易骗过自己的地方。
----------------------------------------------------------------------
assert(type(rawget(_G, "issecretvalue")) == "function",
    "mock 必须先于被测代码就位：issecretvalue")
for _, name in ipairs({ "Logic", "Elements", "Config", "Core" }) do
    assert(loadfile(dir .. "/" .. name .. ".lua"))()
end
local NS = assert(_G.MYUI_CHH)
local Core = assert(NS.Core)

Core.UpdateReadings()

----------------------------------------------------------------------
-- 正常读数
----------------------------------------------------------------------
local readings = Core.GetReadings()
assert(readings.health == 1, "满血应为 1，实得 " .. tostring(readings.health))
assert(math.abs(readings.power - 0.6) < 1e-9, "符能应为 0.6")

healthMax = 2000
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.5, "半血应为 0.5")

----------------------------------------------------------------------
-- 秘密值：必须保留上一次的值，且不报错
----------------------------------------------------------------------
secretHealth = true
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.5,
    "血量读到秘密值时必须保留上一次的值（0.5），实得 " ..
    tostring(Core.GetReadings().health))

secretPower = true
Core.UpdateReadings()
assert(math.abs(Core.GetReadings().power - 0.6) < 1e-9,
    "符能读到秘密值时必须保留上一次的值（0.6）")

----------------------------------------------------------------------
-- 秘密值检测本身失效时，必须**fail closed**（当作不可读）
--
-- 检测函数抛错时无法确定该值是不是秘密值；当成可读会让秘密值悄悄流进计算，
-- 因此宁可当作不可读。注意这里用一个**普通数值**，才能真正隔离这条路径
-- （若沿用 table 哨兵，会被下方的算术兜底顺便拦下，测不到检测函数失效本身）。
----------------------------------------------------------------------
secretHealth, secretPower = false, false
issecretvalueThrows = true
health, healthMax = 800, 1000
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.5,
    "秘密值检测抛错时必须 fail closed、保留上一次的值，实得 " ..
    tostring(Core.GetReadings().health))
issecretvalueThrows = false

----------------------------------------------------------------------
-- **关键用例**：数值型的秘密值必须靠 issecretvalue 拦下
--
-- 真实的魔兽秘密值是**数值型**：对它做算术不会报错，只会传播秘密。所以
-- ReadNumber 里"能否做加法"那条兜底拦不住它——唯一有效的判据就是 issecretvalue。
-- 这条用例把某个普通数值标记成秘密值，从而验证代码确实咨询了检测函数。
-- （若把检测关掉，4242/1000=4.242 会被钳到 1 用掉，本用例立刻失败。）
----------------------------------------------------------------------
secretNumber = 4242
health, healthMax = secretNumber, 1000
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.5,
    "数值型秘密值必须被 issecretvalue 拦下并保留上一次的值，实得 " ..
    tostring(Core.GetReadings().health))
secretNumber = nil

----------------------------------------------------------------------
-- 恢复正常后必须继续跟随（降级不能把它卡死）
----------------------------------------------------------------------
health, healthMax = 250, 1000
power, powerMax = 25, 100
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.25, "恢复后血量应跟随为 0.25")
assert(Core.GetReadings().power == 0.25, "恢复后符能应跟随为 0.25")

----------------------------------------------------------------------
-- 上限为 0 时不得除零，也不得污染上一次的值
----------------------------------------------------------------------
healthMax = 0
Core.UpdateReadings()
assert(Core.GetReadings().health == 0.25, "上限为 0 时应保留上一次的值，不能被零除污染")

io.write("PASS: reading degradation\n")
'''


def test_reading_degradation():
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
    assert "PASS: reading degradation" in result.stdout
