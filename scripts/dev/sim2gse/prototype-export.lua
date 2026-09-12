-- Throwaway task-7 harness; run through prototype-export.py from the repository.
-- Reuses unchanged upstream decoder/import/compiler. No client or saved variables.
local root, input, expectedPath, mode = arg[1], arg[2], arg[3], arg[4]
local function loadSource(path)
    local result = assert(loadfile(root .. "/" .. path))("GSE_TEST", GSE)
    if GSE and GSE.deferred then
        local pending = GSE.deferred
        GSE.deferred = nil
        for _, setup in ipairs(pending) do setup() end
    end
    return result
end
loadSource("spec/mockGSE.lua")
GSE.L = setmetatable({}, {__index = function(_, k) return k end})
GSE.Print, GSE.PrintDebugMessage = function() end, function() end
GSE.VersionString, GSE.VersionNumber = "3.3.32", 3332
WOW_PROJECT_ID = 1
function GetExpansionLevel() return 11 end -- Midnight fixture, not a client probe.
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
    loadSource("GSE/API/" .. path .. ".lua")
end
loadSource("GSE_Utils/Utils.lua")
-- Explicit client-boundary fixtures. Unknown spells fail, never echo the input.
local spellNames = {[85948] = "脓疮打击", [55090] = "天灾打击"}
GSE.GetSpellInfo = function(value)
    local id = tonumber(value)
    if not id then for k, v in pairs(spellNames) do if v == value then id = k end end end
    if spellNames[id] then return {spellID = id, name = spellNames[id]} end
end
GSE.GetClassIDforSpec = function(id) assert(id == 252); return 6 end
local cbor = loadSource("spec/cbor.lua")
local file = assert(io.open(input, "rb"))
local payload = cbor.decode(file:read("*a")); file:close()
local expected = assert(loadfile(expectedPath))()
local function same(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= "table" then return a == b end
    for k, v in pairs(a) do if not same(v, b[k]) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end
assert(same(payload, expected.payload), "CBOR object or numeric-key mismatch")
local sequence = payload.type == "COLLECTION" and payload.payload.Sequences[expected.name] or payload[2]
if mode == "checksum" then
    print("CHECKSUM\t" .. assert(GSE.ComputeSequenceChecksum(sequence)))
    return
end
assert(GSE.VerifySequenceChecksum(sequence) == true, "checksum failed")
local imported
GSE.PerformMergeAction = function(operation, classid, name, value)
    assert(operation == "REPLACE" and classid == 6 and name == expected.name)
    assert(not imported, "unexpected second sequence")
    imported = value
end
GSE.GUICall = function(name) error("unexpected import dialog: " .. name) end
GSE.SendMessage = function() end
-- Tests the real import routing after decoding; does not fake native compression.
GSE.ImportSerialisedSequence(payload, true)
assert(imported, "import did not reach storage boundary")
assert(imported.MetaData.Help == expected.help, "Chinese metadata changed")
local compiled = GSE.CompileTemplate(imported.Versions[1])
assert(#compiled == #expected.steps, "compiled step count mismatch")
local function hex(s) return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end)) end
for i, step in ipairs(compiled) do
    local actual = {type = step.type, spell = step.spell, macrotext = step.macrotext, item = step.item}
    assert(same(actual, expected.steps[i]), "compiled step mismatch at " .. i)
    print("STEP\t" .. i .. "\t" .. step.type .. "\t" .. tostring(step.spell or step.item or "") .. "\t" .. hex(step.macrotext or ""))
end
local altered = GSE.CloneSequence(imported)
altered.Versions[1].Actions[1].spell = 1
assert(GSE.VerifySequenceChecksum(altered) == false, "checksum missed mutation")
print("PASS\tdecoded_object\timport_route\tcompile_order\tchecksum_mutation")
