-- Task-8 source harness: real GSE button builder/snippets, mocked client frames.
-- Run from repo root: .tools/lua-5.1.5/src/lua.exe scripts/dev/sim2gse/prototype-input.lua
-- No combat simulation or actual protected-frame execution is claimed.
local root = '.tools/sim2gse-research/gse-f225d4c/'
local function source(path)
    assert(loadfile(root .. path))('GSE_TEST', GSE)
    if GSE and GSE.deferred then
        local pending = GSE.deferred
        GSE.deferred = nil
        for _, setup in ipairs(pending) do setup() end
    end
end
source('spec/mockGSE.lua')
GSE.L = setmetatable({}, {__index = function(_, k) return k end})
source('GSE/API/Statics.lua')
source('GSE/API/StringFunctions.lua')
source('GSE/API/Storage.lua')
GSE.SequencesExec = {}
GSE.Print = function(message) io.stderr:write(message .. '\n') end
GSE.PrintDebugMessage = function(message) error(message) end
GSE.UpdateIcon = function() end
GSEOptions = {MacroResetModifiers = {LeftControl = false}, ShiftPause = true}
tinsert = table.insert
string.join = function(separator, ...) return table.concat({...}, separator) end
local shift, ctrl = false, false
function IsShiftKeyDown() return shift end
function IsControlKeyDown() return ctrl end
function IsAltKeyDown() return false end
function IsModifierKeyDown() return shift or ctrl end
IsLeftShiftKeyDown, IsRightShiftKeyDown = IsShiftKeyDown, function() return false end
IsLeftControlKeyDown, IsRightControlKeyDown = IsControlKeyDown, function() return false end
IsLeftAltKeyDown, IsRightAltKeyDown = IsAltKeyDown, IsAltKeyDown
function GetMouseButtonClicked() return 'LeftButton' end
function InCombatLockdown() return false end
C_CVar = {GetCVar = function() return '1' end}

-- Only the frame API is substituted; generated setup and OnClick code run unchanged.
function CreateFrame(_, name)
    local frame = {attributes = {}}
    local env = setmetatable({newtable = function(...) return {...} end,
        tinsert = table.insert}, {__index = _G})
    function frame:SetAttribute(k, v) self.attributes[k] = v end
    function frame:GetAttribute(k) return self.attributes[k] end
    function frame:RegisterForClicks(edge) self.edge = edge end
    function frame:Execute(code) setfenv(assert(loadstring(code)), env)() end
    function frame:WrapScript(_, event, code)
        assert(event == 'OnClick')
        self.handler = setfenv(assert(loadstring('return function(self) ' .. code .. ' end')), env)()
    end
    function frame:CallMethod(method) assert(method == 'UpdateIcon') end
    _G[name] = frame
    return frame
end
local function make(name, steps)
    GSE.CreateGSE3Button(steps, name, true)
    local frame = assert(_G[name])
    assert(frame.handler and frame.edge == 'AnyUp')
    assert(frame:GetAttribute('useOnKeyDown') == false)
    return frame
end
local button = make('INPUT_PROTOTYPE', {{type = 'spell', spell = 85948}, {type = 'spell', spell = 55090}})
for i = 1, 4 do
    button:handler()
    local spell = i % 2 == 1 and 85948 or 55090
    assert(button:GetAttribute('spell') == spell)
    assert(button:GetAttribute('step') == i % 2 + 1)
    assert(button:GetAttribute('gseclickserial') == i)
    print(string.format('SOURCE_CLICK\t%dms\t%d\tnext=%d', (i - 1) * 300, spell, button:GetAttribute('step')))
end
-- No cast-result callback exists in this harness: step advancement needs none.
shift = true
button:handler()
assert(button:GetAttribute('step') == 1 and button:GetAttribute('gseclickserial') == 4)
assert(button:GetAttribute('macrotext') == '')
shift = false
button:handler()
assert(button:GetAttribute('spell') == 85948 and button:GetAttribute('step') == 2)

GSEOptions.MacroResetModifiers.LeftControl = true
local reset = make('RESET_PROTOTYPE', {{type = 'spell', spell = 85948}, {type = 'spell', spell = 55090}})
reset:handler()
ctrl, shift = true, true
reset:handler()
assert(reset:GetAttribute('step') == 1 and reset:GetAttribute('gseclickserial') == 1)
ctrl, shift = false, false
reset:handler()
assert(reset:GetAttribute('spell') == 85948 and reset:GetAttribute('step') == 2)

for _, slots in ipairs({{13, 14}, {14, 13}}) do
    local macro = string.format('/use %d\n/use %d\n/cast 脓疮打击', slots[1], slots[2])
    local block = make('BLOCK_' .. slots[1], {{type = 'macro', macrotext = macro}})
    block:handler()
    assert(block:GetAttribute('macrotext') == macro and block:GetAttribute('gseclickserial') == 1)
end
local relay = _G[GSE.GetKeybindClickTarget('INPUT_PROTOTYPE')]
assert(relay.edge == 'AnyDown' and relay:GetAttribute('useOnKeyDown') == true)
assert(relay:GetAttribute('type') == 'click' and relay:GetAttribute('clickbutton') == button)
print('PASS: source step/wrap, pause/resume, reset-before-pause, block order, relay configuration')
print('NOT RUN: client event delivery, spell success/failure, queue, combat, DPS')
