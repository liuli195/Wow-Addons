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
local aceEvent = {}
local restricted = false
local cooldownRestrictedFields = false
local secretReturn = false
local channeling = false
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
        if secretReturn then return secret end
        if cooldownRestrictedFields then
            return setmetatable({}, { __index = function() error("restricted field") end })
        end
        return { startTime = 9, duration = 1.5, isEnabled = false, modRate = 1 }
    end,
    GetSpellCharges = function(id)
        if restricted then error("restricted charges") end
        if secretReturn then return secret end
        if id == 55090 then
            return { currentCharges = 1, maxCharges = 2,
                cooldownStartTime = 9, cooldownDuration = 15, chargeModRate = 1,
                isActive = true }
        end
    end,
    GetBaseSpell = function(id) return id end,
    GetOverrideSpell = function(id) return id == 55090 and 207311 or id end,
    IsCurrentSpell = function(id)
        if restricted then return secret end
        return id == 55090
    end,
}
function UnitCastingInfo()
    if restricted then return secret, nil, nil, secret, secret, nil, secret, nil, secret end
    if channeling then return nil end
    return "Frost Strike", "Frost Strike", 1, 10000, 11000, false, "Cast-1", false, 55090, nil, 0
end
function UnitChannelInfo()
    if not channeling then return nil end
    return "Army of the Dead", "Army of the Dead", 1, 22000, 26000, false, false, 42650
end

local function NewFrame(name)
    local frame = { name = name, scripts = {}, attrs = {}, registered = {} }
    function frame:RegisterEvent(event) self.registered[event] = true end
    function frame:RegisterUnitEvent(event, unit) self.registered[event] = unit end
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

function aceEvent.RegisterMessage(receiver, message, callback)
    gseMessages[message] = callback
end
LibStub = setmetatable({}, { __call = function(_, name, silent)
    if name == "AceEvent-3.0" then return aceEvent end
    if not silent then error("unknown library") end
end })

SlashCmdList = {}
-- Current GSE exposes only a compatibility proxy in _G; internals stay private.
GSE = { RegisterAddon = function() end }
TESTSEQ = NewFrame("TESTSEQ")
TESTSEQ.attrs = {
    type = "spell", spell = 55090, step = 1, iteration = 1,
    gseclickserial = 0,
}
FAKE = NewFrame("FAKE")
LONGSEQ = NewFrame("LONGSEQ")
LONGSEQ.attrs = { type = "spell", spell = 55090 }
SECONDSEQ = NewFrame("SECONDSEQ")
SECONDSEQ.attrs = { type = "spell", spell = 55090, step = 1, iteration = 1 }

assert(loadfile(source))()
assert(SLASH_SIM2GSEPROBE1 == "/s2gprobe")
assert(eventFrame.registered.CURRENT_SPELL_CAST_CHANGED)
assert(eventFrame.registered.UI_ERROR_MESSAGE)
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
assert(click.runes[3].ready == false)
assert(click.gcd.isEnabled == false and click.spellCooldown.isEnabled == false)

assert(session.records[4].event == "UNIT_SPELLCAST_SENT")
assert(session.records[4].castGUID == "Cast-1")
assert(session.records[5].event == "UNIT_SPELLCAST_SUCCEEDED")
assert(session.records[6].kind == "mark")
assert(session.records[7].kind == "stop")

now = 15
SlashCmdList.SIM2GSEPROBE("start")
LONGSEQ.attrs.step = 253
LONGSEQ.attrs.iteration = 1
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "LONGSEQ", ClickSerial = 1,
})
LONGSEQ.attrs.step = 1
LONGSEQ.attrs.iteration = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "LONGSEQ", ClickSerial = 2,
})
LONGSEQ.attrs.step = 1
LONGSEQ.attrs.iteration = 1
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "LONGSEQ", ClickSerial = 3,
})
assert(Sim2GSEProbeDB.session.records[3].submittedIteration == 1)
assert(Sim2GSEProbeDB.session.records[3].submittedStep == 253)
assert(Sim2GSEProbeDB.session.records[4].submittedIteration == 2)
assert(Sim2GSEProbeDB.session.records[4].submittedStep == 1)

now = 18
SlashCmdList.SIM2GSEPROBE("start")
TESTSEQ.attrs.step = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
TESTSEQ.attrs.step = 1
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 3,
})
assert(Sim2GSEProbeDB.session.records[3].submittedStep == nil)
TESTSEQ.attrs.step = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 2,
})
assert(#Sim2GSEProbeDB.session.records == 3, "stale GSE message was recorded as another click")

now = 19
SlashCmdList.SIM2GSEPROBE("start")
TESTSEQ.attrs.step = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
SECONDSEQ.attrs.step = 2
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "SECONDSEQ", ClickSerial = 1,
})
TESTSEQ.attrs.step = 1
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 2,
})
SECONDSEQ.attrs.step = 3
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "SECONDSEQ", ClickSerial = 2,
})
local interleavedSession = Sim2GSEProbeDB.session
assert(interleavedSession.records[4].sequence == "TESTSEQ")
assert(interleavedSession.records[4].submittedStep == 2)
assert(interleavedSession.records[5].sequence == "SECONDSEQ")
assert(interleavedSession.records[5].submittedStep == 2)

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

restricted = false
now = 21
SlashCmdList.SIM2GSEPROBE("start")
TESTSEQ.attrs.spell = 55090
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
now = 21.010
eventFrame.scripts.OnEvent(eventFrame, "CURRENT_SPELL_CAST_CHANGED", false)
now = 21.011
eventFrame.scripts.OnEvent(eventFrame, "UI_ERROR_MESSAGE", 50, "Not ready yet")
now = 21.012
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_FAILED", "player", "Cast-2", 55090)
local nativeSession = Sim2GSEProbeDB.session
local nativeClick = nativeSession.records[2]
assert(nativeClick.currentSpell == true)
assert(nativeClick.statePhase == "post-gse-message")
assert(nativeClick.stateObservedAtMs == 21000)
local current = nativeSession.records[3]
assert(current.event == "CURRENT_SPELL_CAST_CHANGED" and current.cancelledCast == false)
assert(current.candidates[55090] == true)
assert(current.candidates[47541] == nil, "candidate skills leaked across sessions")
assert(current.timeMs == 21010)
assert(current.casting.spellID == 55090 and current.casting.castGUID == "Cast-1")
assert(current.casting.startTimeMs == 10000 and current.casting.endTimeMs == 11000)
assert(current.gcd.duration == 1.5 and current.runicPower == 80 and #current.runes == 6)
assert(current.statePhase == "post-event" and current.stateObservedAtMs == 21010)
local errorRecord = nativeSession.records[4]
assert(errorRecord.event == "UI_ERROR_MESSAGE" and errorRecord.errorType == 50)
assert(errorRecord.message == "Not ready yet" and errorRecord.gcd.duration == 1.5)
assert(errorRecord.candidates[55090] == true)
local failed = nativeSession.records[5]
assert(failed.event == "UNIT_SPELLCAST_FAILED" and failed.spellID == 55090)
assert(failed.candidates[55090] == true and failed.casting.spellID == 55090)
assert(failed.gcd.duration == 1.5 and failed.spellCooldown.duration == 1.5)
assert(failed.runicPower == 80 and #failed.runes == 6)
assert(failed.stateObservedAtMs == 21012)
SlashCmdList.SIM2GSEPROBE("stop")
eventFrame.scripts.OnEvent(eventFrame, "CURRENT_SPELL_CAST_CHANGED", true)
assert(#nativeSession.records == 6, "recording continued after stop")

channeling = true
now = 21.5
SlashCmdList.SIM2GSEPROBE("start")
eventFrame.scripts.OnEvent(eventFrame, "CURRENT_SPELL_CAST_CHANGED", false)
local channel = Sim2GSEProbeDB.session.records[2].casting
assert(channel.kind == "channel" and channel.spellID == 42650)
assert(channel.startTimeMs == 22000 and channel.endTimeMs == 26000)
channeling = false

now = 21.6
SlashCmdList.SIM2GSEPROBE("start")
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
assert(eventFrame.registered.RUNE_POWER_UPDATE)
assert(eventFrame.registered.UNIT_POWER_UPDATE == "player")
assert(eventFrame.registered.SPELL_UPDATE_COOLDOWN)
assert(eventFrame.registered.SPELL_UPDATE_CHARGES)
now = 21.601
eventFrame.scripts.OnEvent(eventFrame, "RUNE_POWER_UPDATE", 2, true)
now = 21.602
eventFrame.scripts.OnEvent(eventFrame, "UNIT_POWER_UPDATE", "player", "RUNIC_POWER")
now = 21.603
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_COOLDOWN", 55090, 55090, 6, 7, nil)
now = 21.604
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_CHARGES")
eventFrame.scripts.OnEvent(eventFrame, "UNIT_POWER_UPDATE", "target", "RUNIC_POWER")
eventFrame.scripts.OnEvent(eventFrame, "UNIT_POWER_UPDATE", "player", "MANA")
local changes = Sim2GSEProbeDB.session.records
assert(#changes == 6, "non-player power event was captured")
assert(changes[3].kind == "resource" and changes[3].runeIndex == 2)
assert(changes[3].added == true and changes[3].timeMs == 21601)
assert(changes[3].runicPower == 80 and #changes[3].runes == 6)
assert(changes[4].kind == "resource" and changes[4].powerType == "RUNIC_POWER")
assert(changes[4].timeMs == 21602 and changes[4].statePhase == "post-event")
assert(changes[5].kind == "cooldown" and changes[5].spellID == 55090)
assert(changes[5].category == 6 and changes[5].startRecoveryCategory == 7)
assert(changes[5].spellCooldown.duration == 1.5 and changes[5].timeMs == 21603)
assert(changes[6].kind == "cooldown" and changes[6].event == "SPELL_UPDATE_CHARGES")
assert(changes[6].observedSpellCooldowns[55090].duration == 1.5)
assert(changes[6].observedSpellCharges[55090].currentCharges == 1)
assert(changes[6].observedSpellCharges[55090].cooldownDuration == 15)
cooldownRestrictedFields = true
now = 21.605
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_COOLDOWN", 55090)
assert(changes[7].spellCooldown.startTime == "unavailable")
assert(changes[7].observedSpellCooldowns[55090].duration == "unavailable")
cooldownRestrictedFields = false
secretReturn = true
now = 21.606
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_CHARGES")
assert(changes[8].gcd == "unavailable")
assert(changes[8].observedSpellCharges[55090] == "unavailable")
secretReturn = false
SlashCmdList.SIM2GSEPROBE("stop")
eventFrame.scripts.OnEvent(eventFrame, "RUNE_POWER_UPDATE", 3, false)
assert(#changes == 9, "resource recording continued after stop")

now = 21.7
SlashCmdList.SIM2GSEPROBE("start")
assert(eventFrame.registered.UNIT_SPELLCAST_CHANNEL_START == "player")
assert(eventFrame.registered.UNIT_SPELLCAST_CHANNEL_UPDATE == "player")
assert(eventFrame.registered.UNIT_SPELLCAST_CHANNEL_STOP == "player")
assert(eventFrame.registered.UNIT_SPELLCAST_DELAYED == "player")
channeling = true
now = 21.701
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_CHANNEL_START", "player", "Cast-3", 42650, 9)
now = 21.702
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "Cast-3", 42650, 9)
channeling = false
now = 21.703
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_CHANNEL_STOP", "player", "Cast-3", 42650, "Cast-4", 9)
now = 21.704
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_DELAYED", "player", "Cast-5", 55090, 10)
local lifecycle = Sim2GSEProbeDB.session.records
assert(#lifecycle == 5)
assert(lifecycle[2].event == "UNIT_SPELLCAST_CHANNEL_START")
assert(lifecycle[2].castGUID == "Cast-3" and lifecycle[2].spellID == 42650)
assert(lifecycle[2].castBarID == 9 and lifecycle[2].casting.kind == "channel")
assert(lifecycle[2].timeMs == 21701 and lifecycle[2].statePhase == "post-event")
assert(lifecycle[3].event == "UNIT_SPELLCAST_CHANNEL_UPDATE" and lifecycle[3].timeMs == 21702)
assert(lifecycle[4].event == "UNIT_SPELLCAST_CHANNEL_STOP")
assert(lifecycle[4].interruptedBy == "Cast-4" and lifecycle[4].castBarID == 9)
assert(lifecycle[5].event == "UNIT_SPELLCAST_DELAYED")
assert(lifecycle[5].castBarID == 10 and lifecycle[5].casting.kind == "cast")
assert(lifecycle[5].timeMs == 21704 and lifecycle[5].stateObservedAtMs == 21704)

restricted = true
now = 22
SlashCmdList.SIM2GSEPROBE("start")
gseMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
eventFrame.scripts.OnEvent(eventFrame, "CURRENT_SPELL_CAST_CHANGED", true)
local restrictedCurrent = Sim2GSEProbeDB.session.records[3]
assert(restrictedCurrent.candidates[55090] == "unavailable")
assert(restrictedCurrent.casting.spellID == "unavailable")
assert(restrictedCurrent.gcd == "unavailable")
assert(restrictedCurrent.runicPower == "unavailable")
eventFrame.scripts.OnEvent(eventFrame, "RUNE_POWER_UPDATE", secret, secret)
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_COOLDOWN", secret, secret)
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_CHANNEL_START", "player", secret, secret, 9)
eventFrame.scripts.OnEvent(eventFrame, "UNIT_SPELLCAST_CHANNEL_START", secret, secret, secret, 9)
local restrictedEvents = Sim2GSEProbeDB.session.records
assert(restrictedEvents[4].runeIndex == "unavailable")
assert(restrictedEvents[4].added == "unavailable")
assert(restrictedEvents[5].spellID == "unavailable")
assert(restrictedEvents[5].observedSpellCooldowns[55090] == "unavailable")
assert(restrictedEvents[6].castGUID == "unavailable")
assert(restrictedEvents[6].spellID == "unavailable")
assert(restrictedEvents[7].event == "UNIT_SPELLCAST_CHANNEL_START")

local globalMessages = {}
GSE = { SequencesExec = {} }
function GSE.RegisterMessage(receiver, message, callback)
    globalMessages[message] = callback
end
LibStub = nil
UnitCastingInfo = nil
UnitChannelInfo = nil
C_Spell.IsCurrentSpell = nil
C_Spell.GetSpellCooldown = nil
C_Spell.GetSpellCharges = nil
GetRuneCooldown = nil
UnitPower = nil
eventFrame = nil
assert(loadfile(source))()
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
assert(globalMessages.GSE_MODS_VISIBLE)
restricted = false
SlashCmdList.SIM2GSEPROBE("start")
globalMessages.GSE_MODS_VISIBLE("GSE_MODS_VISIBLE", {
    SequenceName = "TESTSEQ", ClickSerial = 1,
})
eventFrame.scripts.OnEvent(eventFrame, "CURRENT_SPELL_CAST_CHANGED", false)
eventFrame.scripts.OnEvent(eventFrame, "SPELL_UPDATE_CHARGES")
local missingAPI = Sim2GSEProbeDB.session.records
assert(missingAPI[2].currentSpell == "unavailable")
assert(missingAPI[3].candidates[55090] == "unavailable")
assert(missingAPI[3].casting == "unavailable")
assert(missingAPI[3].gcd == "unavailable")
assert(missingAPI[3].runes == "unavailable")
assert(missingAPI[3].runicPower == "unavailable")
assert(missingAPI[4].observedSpellCharges[55090] == "unavailable")
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
