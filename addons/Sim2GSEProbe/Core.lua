local PREFIX = "|cff58c7ffSim2GSEProbe:|r "
local GSE_CLICK_MESSAGE = "GSE_MODS_VISIBLE"
local ACTIONS_PER_ITERATION = 253
local messageReceiver = {}
local messageRegistered = false
local messageSerials = {}
local nextPositions = {}
local C_CVar = _G.C_CVar
local C_Spell = _G.C_Spell
local CreateFrame = _G.CreateFrame
local Enum = _G.Enum
local GetNetStats = _G.GetNetStats
local GetRuneCooldown = _G.GetRuneCooldown
local GetServerTime = _G.GetServerTime
local GetTimePreciseSec = _G.GetTimePreciseSec
local UnitPower = _G.UnitPower
local issecretvalue = _G.issecretvalue

local function GetDB()
    return _G.Sim2GSEProbeDB
end

local function GetGSE()
    return rawget(_G, "GSE")
end

local function GetMessageBus()
    local gse = GetGSE()
    if gse and type(gse.RegisterMessage) == "function" then return gse end
    local libStub = rawget(_G, "LibStub")
    if not libStub then return nil end
    local ok, bus = pcall(libStub, "AceEvent-3.0", true)
    if ok and bus and type(bus.RegisterMessage) == "function" then return bus end
end

local function SafeScalar(value)
    if value == nil then return nil end
    if issecretvalue then
        local ok, secret = pcall(issecretvalue, value)
        if ok and secret then return "unavailable" end
    end
    local kind = type(value)
    if kind == "number" then
        local ok, copy = pcall(function() return value + 0 end)
        return ok and copy or "unavailable"
    elseif kind == "string" then
        local ok, copy = pcall(function() return "" .. value end)
        return ok and copy or "unavailable"
    elseif kind == "boolean" then
        local ok, copy = pcall(function() return value == true end)
        return ok and copy or "unavailable"
    end
    return "unavailable"
end

local function SafeCall(callback, ...)
    local ok, value = pcall(callback, ...)
    if not ok then return "unavailable" end
    return SafeScalar(value)
end

local function NowMs()
    local value = SafeCall(GetTimePreciseSec)
    if type(value) ~= "number" then return 0 end
    return math.floor(value * 1000 + 0.5)
end

local function ServerTime()
    return GetServerTime and SafeCall(GetServerTime) or nil
end

local function ReadAttribute(button, name)
    if not (button and button.GetAttribute) then return nil end
    return SafeCall(button.GetAttribute, button, name)
end

local function ReadCVar(name)
    if not (C_CVar and C_CVar.GetCVar) then return nil end
    return SafeCall(C_CVar.GetCVar, name)
end

local function ReadLatency()
    if not GetNetStats then return nil, nil end
    local ok, _, _, home, world = pcall(GetNetStats)
    if not ok then return "unavailable", "unavailable" end
    return SafeScalar(home), SafeScalar(world)
end

local function ReadCooldown(spellID)
    if not (spellID and C_Spell and C_Spell.GetSpellCooldown) then return nil end
    local ok, info = pcall(C_Spell.GetSpellCooldown, spellID)
    if not ok or type(info) ~= "table" then return "unavailable" end
    return {
        startTime = SafeScalar(info.startTime),
        duration = SafeScalar(info.duration),
        isEnabled = SafeScalar(info.isEnabled),
        modRate = SafeScalar(info.modRate),
    }
end

local function ReadRunes()
    local runes = {}
    if not GetRuneCooldown then return runes end
    for index = 1, 6 do
        local ok, start, duration, ready = pcall(GetRuneCooldown, index)
        runes[index] = ok and {
            startTime = SafeScalar(start),
            duration = SafeScalar(duration),
            ready = SafeScalar(ready),
        } or "unavailable"
    end
    return runes
end

local function ReadRunicPower()
    local powerType = Enum and Enum.PowerType and Enum.PowerType.RunicPower
    if not (UnitPower and powerType) then return nil end
    return SafeCall(UnitPower, "player", powerType)
end

local function ResolveSpellID(spell)
    if type(spell) == "number" then return spell end
    local numeric = tonumber(spell)
    if numeric then return numeric end
    if not (spell and C_Spell and C_Spell.GetSpellInfo) then return nil end
    local ok, info = pcall(C_Spell.GetSpellInfo, spell)
    if not ok or type(info) ~= "table" then return nil end
    return SafeScalar(info.spellID)
end

local function PreviousPosition(sequence, nextStep, nextIteration)
    if type(nextStep) ~= "number" or type(nextIteration) ~= "number" then
        return nil, nil
    end
    if nextStep > 1 then return nextIteration, nextStep - 1 end
    if type(sequence) ~= "table" or #sequence == 0 then return nil, nil end
    local iteration = nextIteration - 1
    if iteration < 1 then iteration = math.ceil(#sequence / ACTIONS_PER_ITERATION) end
    return iteration, math.min(
        ACTIONS_PER_ITERATION,
        #sequence - (iteration - 1) * ACTIONS_PER_ITERATION
    )
end

local function Environment()
    local home, world = ReadLatency()
    local queue = C_Spell and C_Spell.GetSpellQueueWindow
        and SafeCall(C_Spell.GetSpellQueueWindow) or nil
    return {
        capturedAtMs = NowMs(),
        serverTime = ServerTime(),
        spellQueueWindowMs = queue,
        actionButtonUseKeyDown = ReadCVar("ActionButtonUseKeyDown"),
        homeLatencyMs = home,
        worldLatencyMs = world,
    }
end

local function AddRecord(record)
    local database = GetDB()
    local session = database and database.session
    if not (session and session.active) then return end
    record.timeMs = record.timeMs or NowMs()
    record.serverTime = ServerTime()
    table.insert(session.records, record)
end

local function CaptureClick(button, sequenceName, evidence)
    local observedAt = NowMs()
    local gse = GetGSE()
    local sequence = gse and gse.SequencesExec and gse.SequencesExec[sequenceName]
    local serial = SafeScalar(evidence.ClickSerial)
    local nextStep = ReadAttribute(button, "step")
    local nextIteration = ReadAttribute(button, "iteration") or 1
    local previous = nextPositions[sequenceName]
    if not (previous and serial == previous.serial + 1) then previous = nil end
    local iteration, step = previous and previous.iteration, previous and previous.step
    if not previous then
        iteration, step = PreviousPosition(sequence, nextStep, nextIteration)
    end
    local spell = ReadAttribute(button, "spell")
    local spellID = ResolveSpellID(spell)
    local baseSpellID = C_Spell and C_Spell.GetBaseSpell and spellID
        and SafeCall(C_Spell.GetBaseSpell, spellID) or nil
    local overrideSpellID = C_Spell and C_Spell.GetOverrideSpell and spellID
        and SafeCall(C_Spell.GetOverrideSpell, spellID) or nil
    AddRecord({
        kind = "click",
        timeMs = observedAt,
        observedAtMs = observedAt,
        sequence = sequenceName,
        clickSerial = serial,
        submittedStep = step,
        submittedIteration = iteration,
        actionType = ReadAttribute(button, "type"),
        spell = spell,
        macro = ReadAttribute(button, "macro"),
        macrotext = ReadAttribute(button, "macrotext"),
        unit = ReadAttribute(button, "unit"),
        spellID = spellID,
        baseSpellID = baseSpellID,
        overrideSpellID = overrideSpellID,
        hardwareEvent = SafeScalar(evidence.HardwareEvent),
        spamKey = SafeScalar(evidence.SpamKey),
        triggerEdge = "gse-execution-message-observed",
        gcd = ReadCooldown(61304),
        spellCooldown = ReadCooldown(spellID),
        runes = ReadRunes(),
        runicPower = ReadRunicPower(),
    })
    if type(nextStep) == "number" and type(nextIteration) == "number" then
        nextPositions[sequenceName] = { step = nextStep, iteration = nextIteration, serial = serial }
    end
end

local function CaptureGSEMessage(_, payload)
    if type(payload) ~= "table" then return end
    local name = SafeScalar(payload.SequenceName)
    local serial = SafeScalar(payload.ClickSerial)
    if type(name) ~= "string" or type(serial) ~= "number" or messageSerials[name] == serial then return end
    local button = _G[name]
    if not button then return end
    messageSerials[name] = serial
    CaptureClick(button, name, payload)
end

local function ConnectGSE()
    local bus = GetMessageBus()
    if not messageRegistered and bus then
        bus.RegisterMessage(messageReceiver, GSE_CLICK_MESSAGE, CaptureGSEMessage)
        messageRegistered = true
    end
    return messageRegistered
end

local function Print(message)
    print(PREFIX .. message)
end

local function Start()
    messageSerials = {}
    nextPositions = {}
    ConnectGSE()
    _G.Sim2GSEProbeDB = GetDB() or {}
    local database = GetDB()
    database.schema = 1
    database.session = {
        schema = 1,
        active = true,
        environment = Environment(),
        records = {},
    }
    AddRecord({ kind = "start" })
    Print("采集已开始；本次会话会替换旧会话。")
end

local function Mark()
    local database = GetDB()
    local session = database and database.session
    if not (session and session.active) then
        Print("当前没有活动会话。")
        return
    end
    AddRecord({ kind = "mark" })
    Print("已记录测试边界。")
end

local function Stop()
    local database = GetDB()
    local session = database and database.session
    if not (session and session.active) then
        Print("当前没有活动会话。")
        return
    end
    AddRecord({ kind = "stop" })
    session.active = false
    Print("采集已停止；请使用 /reload 写入保存文件。")
end

local function Status()
    ConnectGSE()
    local database = GetDB()
    local session = database and database.session
    local state = session and session.active and "采集中" or "未采集"
    local records = session and session.records and #session.records or 0
    local connection = messageRegistered and "已连接" or "未连接"
    Print(string.format("%s；GSE 消息%s；记录 %d 条。", state, connection, records))
end

_G.SLASH_SIM2GSEPROBE1 = "/s2gprobe"
local slashCommands = assert(rawget(_G, "SlashCmdList"))
slashCommands.SIM2GSEPROBE = function(input)
    local command = string.lower((input or ""):match("^%s*(%S*)") or "")
    if command == "start" then
        Start()
    elseif command == "mark" then
        Mark()
    elseif command == "stop" then
        Stop()
    else
        Status()
    end
end

local spellEvents = {
    "UNIT_SPELLCAST_SENT",
    "UNIT_SPELLCAST_FAILED",
    "UNIT_SPELLCAST_FAILED_QUIET",
    "UNIT_SPELLCAST_INTERRUPTED",
    "UNIT_SPELLCAST_START",
    "UNIT_SPELLCAST_STOP",
    "UNIT_SPELLCAST_SUCCEEDED",
}

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:RegisterEvent("ADDON_LOADED")
for _, event in ipairs(spellEvents) do
    if events.RegisterUnitEvent then
        events:RegisterUnitEvent(event, "player")
    else
        events:RegisterEvent(event)
    end
end
events:SetScript("OnEvent", function(_, event, ...)
    if event == "PLAYER_LOGIN" or event == "PLAYER_REGEN_ENABLED" or event == "ADDON_LOADED" then
        _G.Sim2GSEProbeDB = GetDB() or { schema = 1 }
        ConnectGSE()
        return
    end

    local unit = ...
    if unit ~= "player" then return end
    if event == "UNIT_SPELLCAST_SENT" then
        local _, target, castGUID, spellID = ...
        AddRecord({
            kind = "spellcast",
            event = event,
            target = SafeScalar(target),
            castGUID = SafeScalar(castGUID),
            spellID = SafeScalar(spellID),
        })
    else
        local _, castGUID, spellID = ...
        AddRecord({
            kind = "spellcast",
            event = event,
            castGUID = SafeScalar(castGUID),
            spellID = SafeScalar(spellID),
        })
    end
end)
