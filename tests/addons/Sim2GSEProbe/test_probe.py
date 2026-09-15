import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/Sim2GSEProbe/Core.lua"


def test_probe_captures_one_real_input_path():
    harness = r'''
local source = assert(arg[1])
local now = 10
local eventFrame
local messages = {}
local restricted = false
local secret = {}

function GetTimePreciseSec() return now end
function GetServerTime() return 1789474410 end
function GetNetStats() return 0, 0, 28, 25 end
function UnitPower() return restricted and secret or 80 end
function GetRuneCooldown(index) return index, 10, index <= 2 end
function InCombatLockdown() return false end
function IsLoggedIn() return true end
function issecretvalue(value) return value == secret end
function print(message) table.insert(messages, message) end

Enum = { PowerType = { RunicPower = 6 } }
C_CVar = { GetCVar = function(name)
    if name == "ActionButtonUseKeyDown" then return "1" end
end }
C_Spell = {
    GetSpellQueueWindow = function() return restricted and secret or 400 end,
    GetSpellCooldown = function()
        if restricted then error("restricted cooldown") end
        return { startTime = 9, duration = 1.5, isEnabled = true, modRate = 1 }
    end,
    GetBaseSpell = function(id) return id end,
    GetOverrideSpell = function(id) return id == 55090 and 207311 or id end,
}

local function NewFrame(name)
    local frame = { name = name, scripts = {}, attrs = {} }
    function frame:RegisterEvent() end
    function frame:RegisterUnitEvent() end
    function frame:SetScript(kind, callback) self.scripts[kind] = callback end
    function frame:HookScript(kind, callback) self.scripts[kind] = callback end
    function frame:GetName() return self.name end
    function frame:GetAttribute(key) return self.attrs[key] end
    return frame
end

function CreateFrame(_, name)
    local frame = NewFrame(name)
    if not eventFrame then eventFrame = frame end
    if name then _G[name] = frame end
    return frame
end

function hooksecurefunc(owner, name, callback)
    owner["__hook_" .. name] = callback
end

SlashCmdList = {}
GSE = { SequencesExec = {
    TESTSEQ = { { { type = "spell", spell = 55090 }, { type = "spell", spell = 47541 } } },
    FAKE = { { { type = "spell", spell = 55090 } } },
} }
TESTSEQ = NewFrame("TESTSEQ")
TESTSEQ.attrs = {
    type = "spell", spell = 55090, step = 2, iteration = 1,
    gseclickserial = 1,
}
TESTSEQ_KD = NewFrame("TESTSEQ_KD")
TESTSEQ_KD.gseKeyDownRelay = true
FAKE = NewFrame("FAKE")
FAKE_KD = NewFrame("FAKE_KD")

assert(loadfile(source))()
assert(SLASH_SIM2GSEPROBE1 == "/s2gprobe")
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
assert(FAKE_KD.scripts.PreClick == nil)
SlashCmdList.SIM2GSEPROBE("start")

now = 10.070
TESTSEQ_KD.scripts.PreClick(TESTSEQ_KD, "LeftButton", true)
TESTSEQ.scripts.PreClick(TESTSEQ, "LeftButton", false)
now = 10.071
TESTSEQ.scripts.PostClick(TESTSEQ, "LeftButton", false)
now = 10.072
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_SENT", "player", "Target", "Cast-1", 55090)
now = 10.090
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 55090)
SlashCmdList.SIM2GSEPROBE("mark")
SlashCmdList.SIM2GSEPROBE("stop")

local session = assert(Sim2GSEProbeDB.session)
assert(session.active == false)
assert(session.environment.spellQueueWindowMs == 400)
assert(session.environment.actionButtonUseKeyDown == "1")
assert(session.environment.homeLatencyMs == 28)
assert(session.environment.worldLatencyMs == 25)

local click = session.records[2]
assert(click.kind == "click")
assert(click.timeMs == 10070)
assert(click.observedAtMs == 10071)
assert(click.sequence == "TESTSEQ")
assert(click.clickSerial == 1)
assert(click.submittedStep == 1 and click.submittedIteration == 1)
assert(click.actionType == "spell" and click.spell == 55090)
assert(click.baseSpellID == 55090 and click.overrideSpellID == 207311)
assert(click.triggerEdge == "keydown-relay-observed")
assert(click.runicPower == 80 and #click.runes == 6)

assert(session.records[3].event == "UNIT_SPELLCAST_SENT")
assert(session.records[3].castGUID == "Cast-1")
assert(session.records[4].event == "UNIT_SPELLCAST_SUCCEEDED")
assert(session.records[5].kind == "mark")
assert(session.records[6].kind == "stop")

restricted = true
now = 20
SlashCmdList.SIM2GSEPROBE("start")
TESTSEQ.scripts.PreClick(TESTSEQ, "LeftButton", false)
now = 20.001
TESTSEQ.scripts.PostClick(TESTSEQ, "LeftButton", false)
local restrictedSession = Sim2GSEProbeDB.session
local restrictedClick = restrictedSession.records[2]
assert(restrictedSession.environment.spellQueueWindowMs == "unavailable")
assert(restrictedClick.triggerEdge == "unknown")
assert(restrictedClick.runicPower == "unavailable")
assert(restrictedClick.gcd == "unavailable")
assert(restrictedClick.spellCooldown == "unavailable")
io.write("PASS: probe public seam\n")
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "probe_harness.lua"
        path.write_text(harness, encoding="utf-8")
        result = subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: probe public seam" in result.stdout
