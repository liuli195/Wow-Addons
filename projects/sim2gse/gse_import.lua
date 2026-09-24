-- Run the pinned upstream GSE compiler against a previously bounded CBOR import.
local root, input, contextPath = arg[1], arg[2], arg[3]
local function source(path)
    local result = assert(loadfile(root .. "/" .. path))("GSE_TEST", GSE)
    if GSE and GSE.deferred then
        local pending = GSE.deferred
        GSE.deferred = nil
        for _, setup in ipairs(pending) do setup() end
    end
    return result
end
source("spec/mockGSE.lua")
local context = assert(loadfile(contextPath))()
GSE.L = setmetatable({}, {__index = function(_, k) return k end})
GSE.Print, GSE.PrintDebugMessage = function() end, function() end
GSE.VersionString, GSE.VersionNumber = context.gse_version_string, context.gse_version
WOW_PROJECT_ID = 1
function GetExpansionLevel() return 11 end
function GetLocale() return "zhCN" end
function GetTime() return 0 end
bit = {bxor = function(a, b)
    local result, power = 0, 1
    for _ = 1, 32 do
        if a % 2 ~= b % 2 then result = result + power end
        a, b, power = math.floor(a / 2), math.floor(b / 2), power * 2
    end
    return result
end}
for _, path in ipairs({"Statics", "InitialOptions", "StringFunctions", "CharacterFunctions", "Storage", "translator", "Checksum"}) do
    source("GSE/API/" .. path .. ".lua")
end
source("GSE_Utils/Utils.lua")
local cbor = source("spec/cbor.lua")
local file = assert(io.open(input, "rb"))
local imported = cbor.decode(file:read("*a")); file:close()
local name, version = context.name, context.version
local sequences
if imported.type == "COLLECTION" then
    sequences = imported.payload.Sequences
elseif imported.MetaData and imported.MetaData.Name and imported.Versions then
    sequences = {[imported.MetaData.Name] = imported}
elseif type(imported[1]) == "string" then
    sequences = {[imported[1]] = imported[2]}
else
    error("unsupported sequence envelope")
end
local sequence = assert(sequences[name], "selected sequence absent")
if sequence[2] and sequence[1] == name then sequence = sequence[2] end
assert(sequence.Versions[version], "selected version absent")
local identity = context.identity
GSE.GetClassIDforSpec = function(id)
    assert(id == identity.spec_id, "specialization differs")
    return identity.class_id
end
GSE.GetClickRate = function() return context.click_ms end
GSE.GetGCD = function() return context.gcd_ms / 1000 end
GSE.GetActiveSequenceVersion = function(dep)
    local sequence = sequences[dep]
    return context.versions[dep] or (sequence and sequence.Default) or 1
end
GSE.Library[identity.class_id] = sequences
GSE.Library[0] = {}
GSE.GetCurrentClassID = function() return identity.class_id end
local spellNames = context.spells
GSE.GetSpellInfo = function(value)
    local id = tonumber(value)
    if not id then for k, v in pairs(spellNames) do if v == value then id = k end end end
    if spellNames[id] then return {spellID = id, name = spellNames[id]} end
    -- Keep unknown numeric IDs visible so the simulator can reject them with their source value.
    if id then return {spellID = id, name = tostring(value)} end
end
math.randomseed(context.seed)
local compiled = GSE.CompileTemplate(sequence.Versions[version])
local function hex(value)
    return (tostring(value or ""):gsub(".", function(c) return string.format("%02x", c:byte()) end))
end
for index, step in ipairs(compiled) do
    print(table.concat({"STEP", index, step.type or "", tostring(step.spell or step.item or ""),
                        hex(step.macrotext or step.macro or ""), step.blockPath or ""}, "\t"))
end
print("PASS\t" .. #compiled)
