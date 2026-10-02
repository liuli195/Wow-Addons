"""从登录、游戏事件和现有设置页到真实绘制的行为检查。"""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / '.tools/lua-5.1.5/src/lua.exe'
ADDON = ROOT / 'addons/MYUI_CrosshairHUD'

HARNESS = r'''
local dir = assert(arg[1])
local frames, textures, lines, tickers = {}, {}, {}, {}
local aura, fee, maximum, playerClass = { applications = 75 }, 35, 100, "DEATHKNIGHT"
local secret = setmetatable({}, { __index = function() error("secret read") end })
local detectorThrows, auraThrows, feeThrows = false, false, false
local feeEntries
function issecretvalue(v)
    if detectorThrows then error("detector unavailable") end
    return rawequal(v, secret)
end
function UnitClass() return "死亡骑士", playerClass end
function GetTime() return 10 end
function GetRuneCooldown() return 0, 0, true end
function UnitPowerMax() return maximum end
function UnitHealthPercent(_, _, curve) return curve:Evaluate(1) end
function UnitPowerPercent(_, _, _, curve) return curve:Evaluate(0.7) end
function InCombatLockdown() return false end
function print() end
SlashCmdList = {}
Enum = { PowerType = { RunicPower = 6 }, LuaCurveType = { Linear = 0 } }
C_AddOns = { GetAddOnMetadata = function() return "test" end }
C_UnitAuras = { GetPlayerAuraBySpellID = function(id)
    assert(id == 463730)
    if auraThrows then error("aura unavailable") end
    return aura
end }
C_Spell = { GetSpellPowerCost = function(id)
    assert(id == 49998)
    if feeThrows then error("fee unavailable") end
    if feeEntries then return feeEntries end
    return { { type = 0, minCost = 1, cost = 1 },
        { type = 6, minCost = fee, cost = 90, requiredAuraID = 0, hasRequiredAura = false } }
end }
C_Timer = { After = function(_, fn) fn() end, NewTicker = function(_, fn)
    tickers[#tickers + 1] = fn; return {}
end }
C_CurveUtil = { CreateCurve = function()
    local c = { points = {} }
    function c:SetType() end
    function c:AddPoint(x, y) self.points[#self.points + 1] = {x,y} end
    function c:Evaluate(x)
        if rawequal(x, secret) then return secret end
        local fraction = math.max(0, math.min(1, x / self.points[2][1]))
        return self.points[1][2] + (self.points[2][2]-self.points[1][2])*fraction
    end
    return c
end }
UIParent = { GetEffectiveScale = function() return 1 end }
local function Region()
    local t = { shown = true }
    function t:SetTexture(path) self.path = path end
    function t:SetSize(w,h) self.w,self.h=w,h end
    function t:SetPoint(_,_,_,x,y) self.x,self.y=x,y end
    function t:SetAllPoints() end
    function t:AddMaskTexture(mask) self.mask=mask end
    function t:SetShown(v) self.shown=v end
    function t:SetRotation(v) self.rotation=v end
    function t:SetVertexColor(r,g,b,a) self.color={r,g,b,a} end
    function t:SetColorTexture(r,g,b,a) self.color={r,g,b,a} end
    function t:SetStartPoint(_,_,x,y) self.start={x,y} end
    function t:SetEndPoint(_,_,x,y) self.finish={x,y} end
    function t:SetThickness(v) self.thickness=v end
    function t:SetSnapToPixelGrid(v) self.snap=v end
    function t:SetTexelSnappingBias(v) self.bias=v end
    return t
end
function CreateFrame()
    local f = { events={},scripts={} }
    function f:CreateTexture(_,_,_,sub)
        local t=Region();t.sub=sub;textures[#textures+1]=t;return t
    end
    function f:CreateMaskTexture() return Region() end
    function f:CreateLine() local t=Region();lines[#lines+1]=t;return t end
    function f:RegisterEvent(e) self.events[e]=true end
    function f:RegisterUnitEvent(e,unit) assert(e:sub(1,5)=="UNIT_");assert(unit=="player");self.events[e]=true end
    function f:SetScript(e,fn) self.scripts[e]=fn end
    function f:UnregisterAllEvents() self.events={} end
    function f:SetSize(w,h) self.w,self.h=w,h end
    function f:GetWidth() return self.w end
    function f:GetHeight() return self.h end
    function f:GetEffectiveScale() return 1 end
    function f:SetPoint() end
    function f:ClearAllPoints() end
    function f:SetFrameStrata() end
    function f:SetShown(v) self.shown=v end
    frames[#frames+1]=f;return f
end
local rows, section = {}, nil
EllesmereUI = { _modules={}, _prebuilding=true, Widgets={} }
function EllesmereUI.Widgets:SectionHeader(_,title) section=title;rows[title]={};return {},20 end
function EllesmereUI.Widgets:DualRow(_,_,left,right)
    rows[section][left.text]=left
    if right.text then rows[section][right.text]=right end
    return {},20
end
for _, name in ipairs({"Logic","Elements","Config","Core"}) do
    assert(loadfile(dir.."/"..name..".lua"))()
end
local NS = MYUI_CHH
local function Event(e)
    for _,f in ipairs(frames) do if f.events[e] then f.scripts.OnEvent(f,e,"player") end end
end
local function Tick() for _,fn in ipairs(tickers) do fn() end end
local function Page()
    rows={};EllesmereUI._modules.MYUI_CrosshairHUD.buildPage(nil,{},0)
end
local function Layer(file,sub)
    for _,t in ipairs(textures) do
        if t.path and t.path:sub(-#file)==file and (sub==nil or t.sub==sub) then return t end
    end
end
local function Near(a,b) assert(math.abs(a-b)<0.00001,tostring(a).." != "..tostring(b)) end
Event("PLAYER_LOGIN")
Page()
__SCENARIO__
io.write("PASS: blood DK features\n")
'''


def run_scenario(scenario):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'features.lua'
        path.write_text(HARNESS.replace('__SCENARIO__', scenario), encoding='utf-8')
        result = subprocess.run([str(LUA), str(path), str(ADDON)], cwd=ROOT,
                                capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS: blood DK features' in result.stdout


def test_lowest_applicable_runic_cost():
    run_scenario(r'''
feeEntries = {
    {type=6,minCost=60,requiredAuraID=0},
    {type=6,minCost=45,requiredAuraID=123,hasRequiredAura=true},
    {type=6,minCost=35,requiredAuraID=456,hasRequiredAura=true},
    {type=6,minCost=5,requiredAuraID=789,hasRequiredAura=false},
    {type=0,minCost=1,requiredAuraID=0},
}
Tick()
local angle = math.rad(441 - 102 * 0.35)
Near(lines[1].start[1], 49.1 * math.cos(angle))
Near(lines[1].start[2], -49.1 * math.sin(angle))
''')


def test_aura_controls_and_visibility_through_login_events_and_settings():
    run_scenario(r'''
local controls=assert(rows["凝固之血"],"existing settings page must include blood aura")
local bg=assert(Layer("coagulated_blood_arc.png",0),"aura background required")
local fill=assert(Layer("coagulated_blood_arc.png",1),"aura fill required")
local shadow=assert(Layer("coagulated_blood_arc_shadow.png"))
assert(shadow.sub < Layer("health_arc_shadow.png").sub,"aura shadow below health shadow")
assert(not shadow.mask,"shadow must not be fill-masked")
assert(bg.shown and fill.shown and shadow.shown)
Near(controls["满条层数"].getValue(),150)
-- 75/150 的中间位置：起点99减2度余量，加53度的一半。
Near(fill.mask.rotation,math.rad(-213.5))
controls["启用"].setValue(false)
assert(not bg.shown and not fill.shown and not shadow.shown)
SlashCmdList.MYUICHH("demo")
assert(not bg.shown and not fill.shown and not shadow.shown)
SlashCmdList.MYUICHH("demo")
controls["启用"].setValue(true)
controls["满条层数"].setValue(75)
Near(fill.mask.rotation,math.rad(-240))
aura=nil;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown and not shadow.shown)
aura={applications=75};Event("UNIT_AURA")
assert(bg.shown and fill.shown and shadow.shown)
playerClass="MAGE";Page()
for _,control in pairs(rows["凝固之血"]) do assert(control.disabled()) end
''')


def test_native_cost_line_changes_position_direction_scale_and_switch():
    run_scenario(r'''
local controls=assert(rows["灵打消耗刻度"],"cost marker controls required")
local line=assert(lines[1],"must draw a native line")
assert(line.shown)
Near(line.thickness,1.5)
fee=50;Tick()
-- 满符能100、费用50，在从441度向339度填充的弧中点390度。
Near(line.start[1],49.1*math.sqrt(3)/2);Near(line.start[2],-24.55)
Near(line.finish[1],58.9*math.sqrt(3)/2);Near(line.finish[2],-29.45)
controls["粗细"].setValue(2.25)
Near(line.thickness,2.25)
rows["常规"]["HUD 缩放"].setValue(2)
Near(line.thickness,4.5);Near(line.finish[2],-58.9)
maximum=200;Event("UNIT_MAXPOWER")
-- 费用仍50，比例改为1/4，刻度位置和方向一起变。
assert(math.abs(line.finish[2]+58.9)>1)
Near(line.start[1]*line.finish[2]-line.start[2]*line.finish[1],0)
controls["启用"].setValue(false)
assert(not line.shown)
SlashCmdList.MYUICHH("demo");assert(not line.shown)
''')


def test_unreadable_values_hide_only_new_data_and_recover():
    run_scenario(r'''
local bg=Layer("coagulated_blood_arc.png",0)
local fill=Layer("coagulated_blood_arc.png",1)
local shadow=Layer("coagulated_blood_arc_shadow.png")
local line=lines[1]
aura={applications=secret};fee=secret;Tick()
assert(bg.shown and shadow.shown and not fill.shown and not line.shown)
assert(Layer("health_arc.png",1).shown and Layer("power_arc.png",1).shown)
aura=secret;maximum=secret;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown and not shadow.shown and not line.shown)
aura={applications=300};fee=0;maximum=100;Tick()
assert(bg.shown and fill.shown and line.shown)
Near(fill.mask.rotation,math.rad(-240))
auraThrows=true;feeThrows=true;Tick()
assert(not bg.shown and not line.shown)
auraThrows=false;feeThrows=false;Tick()
assert(bg.shown and line.shown)
detectorThrows=true;Tick()
assert(not bg.shown and not line.shown)
detectorThrows=false;Tick();assert(bg.shown and line.shown)
''')


def test_independent_alpha_shared_shadow_and_saved_settings():
    run_scenario(r'''
local bg=Layer("coagulated_blood_arc.png",0)
local fill=Layer("coagulated_blood_arc.png",1)
local shadow=Layer("coagulated_blood_arc_shadow.png")
rows["凝固之血"]["条背景"].setValue(40)
rows["凝固之血"]["填充颜色"].setValue(25)
rows["灵打消耗刻度"]["刻度颜色"].setValue(60)
rows["常规"]["阴影"].setValue(30)
Near(bg.color[4],0.4);Near(fill.color[4],0.25);Near(lines[1].color[4],0.6)
Near(shadow.color[4],0.3);Near(Layer("health_arc_shadow.png").color[4],0.3)
assert(fill.color[1]==1 and fill.color[2]==1 and fill.color[3]==1)
MYUI_CrosshairHUDDB.elements.coagulatedBlood.fill={0.2,0.3,0.4}
NS.Config.Load();NS.Core.ApplyConfig()
Near(fill.color[1],0.2);Near(fill.color[2],0.3);Near(fill.color[3],0.4)
assert(not bg.mask and not shadow.mask and fill.mask)
''')


def test_tracked_blood_aura_survives_restricted_direct_lookup():
    run_scenario(r'''
aura=nil
local item={auraDataCached={applications=75},auraDataUnit="player"}
function item:GetCooldownInfo() return {spellID=463730} end
function item:IsActive() return true end
BuffIconCooldownViewer={GetItemFrames=function() return {item} end}
Tick()
local fill=Layer("coagulated_blood_arc.png",1)
assert(fill.shown, "tracked buff must render when direct lookup misses")
Near(fill.mask.rotation,math.rad(-213.5))
item.auraDataCached={applications=secret};Tick()
assert(not fill.shown and Layer("coagulated_blood_arc_shadow.png").shown, "restricted stacks must not be calculated")
item.auraDataCached=nil;Tick()
assert(not fill.shown and not Layer("coagulated_blood_arc_shadow.png").shown)
item.auraDataCached={applications=75}
function item:GetCooldownInfo() return {spellID=999} end
Tick();assert(not fill.shown)
''')


def test_native_marker_does_not_snap_oblique_texture_to_pixels():
    run_scenario(r'''
assert(#lines==1)
assert(lines[1].snap==false and lines[1].bias==0, "oblique line texture must not snap to pixel grid")
''')
