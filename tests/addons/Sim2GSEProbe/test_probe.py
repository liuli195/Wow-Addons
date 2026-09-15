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
local gseMessages = {}
local restricted = false
local secret = {}

function GetTimePreciseSec() return now end
function GetServerTime() return 1789474410 end
function GetNetStats() return 0, 0, 28, 25 end
function UnitPower() return restricted and secret or 80 end
function GetRuneCooldown(index) return index, 10, index <= 2 end
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

SlashCmdList = {}
GSE = { SequencesExec = {
    TESTSEQ = { { type = "spell", spell = 55090 }, { type = "spell", spell = 47541 } },
    FAKE = { { type = "spell", spell = 55090 } },
} }
function GSE.RegisterMessage(receiver, message, callback)
    gseMessages[message] = callback
end
TESTSEQ = NewFrame("TESTSEQ")
TESTSEQ.attrs = {
    type = "spell", spell = 55090, step = 1, iteration = 1,
    gseclickserial = 0,
}
FAKE = NewFrame("FAKE")

assert(loadfile(source))()
assert(SLASH_SIM2GSEPROBE1 == "/s2gprobe")
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
SlashCmdList.SIM2GSEPROBE("")
assert(messages[#messages]:find("GSE 消息已连接", 1, true))
SlashCmdList.SIM2GSEPROBE("start")
assert(#Sim2GSEProbeDB.session.records == 1)

-- GSE advances its secure state before publishing the execution message.
TESTSEQ.attrs.step = 2
TESTSEQ.attrs.gseclickserial = 1
now = 10.071
assert(gseMessages.GSE_MODS_VISIBLE, "GSE click message was not registered")
local clickPayload = {
    SequenceName = "TESTSEQ", ButtonName = "TESTSEQ",
    HardwareEvent = "LeftButton", SpamKey = "F6", ClickSerial = 1,
}
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", clickPayload)
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", clickPayload)
assert(#Sim2GSEProbeDB.session.records == 2, "duplicate GSE message was recorded as another click")
TESTSEQ.attrs.step = 1
TESTSEQ.attrs.spell = 47541
TESTSEQ.attrs.gseclickserial = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ButtonName = "TESTSEQ",
    HardwareEvent = "LeftButton", ClickSerial = 2,
})
assert(Sim2GSEProbeDB.session.records[3].submittedIteration == 1)
assert(Sim2GSEProbeDB.session.records[3].submittedStep == 2)
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
assert(click.timeMs == 10071)
assert(click.observedAtMs == 10071)
assert(click.sequence == "TESTSEQ")
assert(click.clickSerial == 1)
assert(click.submittedStep == 1 and click.submittedIteration == 1)
assert(click.actionType == "spell" and click.spell == 55090)
assert(click.baseSpellID == 55090 and click.overrideSpellID == 207311)
assert(click.hardwareEvent == "LeftButton")
assert(click.spamKey == "F6")
assert(click.triggerEdge == "gse-execution-message-observed")
assert(click.runicPower == 80 and #click.runes == 6)

assert(session.records[4].event == "UNIT_SPELLCAST_SENT")
assert(session.records[4].castGUID == "Cast-1")
assert(session.records[5].event == "UNIT_SPELLCAST_SUCCEEDED")
assert(session.records[6].kind == "mark")
assert(session.records[7].kind == "stop")

restricted = true
now = 20
SlashCmdList.SIM2GSEPROBE("start")
now = 20.001
TESTSEQ.attrs.gseclickserial = 3
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ButtonName = "TESTSEQ",
    HardwareEvent = "LeftButton", ClickSerial = 3,
})
local restrictedSession = Sim2GSEProbeDB.session
local restrictedClick = restrictedSession.records[2]
assert(restrictedSession.environment.spellQueueWindowMs == "unavailable")
assert(restrictedClick.triggerEdge == "gse-execution-message-observed")
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
