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
local messages={}
function print(msg) messages[#messages+1]=msg end
SlashCmdList = {}
Enum = { PowerType = { RunicPower = 6 }, LuaCurveType = { Linear = 0 }, StatusBarRenderMode = { Radial = 1 } }
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
    function t:SetTexture(path, _, _, filter) self.path = path; self.filter = filter end
    function t:SetSize(w,h) self.w,self.h=w,h end
    function t:SetPoint(_,_,_,x,y) self.x,self.y=x,y end
    function t:SetAllPoints() end
    function t:AddMaskTexture(mask) self.mask=mask end
    function t:SetShown(v) self.shown=v end
    function t:SetRotation(v) self.rotation=v end
    function t:SetRadialProgressBarStartOffset(v) self.radialStart=v end
    function t:SetRadialProgressBarEndOffset(v) self.radialEnd=v end
    function t:SetRadialProgressBarReverse(v) self.radialReverse=v end
    function t:SetRadialProgressBarFeather(v) self.radialFeather=v end
    function t:SetTexCoord(...) self.coords={...} end
    function t:SetVertexColor(r,g,b,a) self.color={r,g,b,a} end
    function t:SetColorTexture(r,g,b,a) self.color={r,g,b,a} end
    function t:SetStartPoint(_,_,x,y) self.start={x,y} end
    function t:SetEndPoint(_,_,x,y) self.finish={x,y} end
    function t:SetThickness(v) self.thickness=v end
    function t:SetSnapToPixelGrid(v) self.snap=v end
    function t:SetTexelSnappingBias(v) self.bias=v end
    return t
end
function CreateFrame(kind)
    local f = { events={},scripts={},kind=kind }
    function f:SetStatusBarTexture(t) self.texture=t end
    function f:SetStatusBarColor(...) self.texture:SetVertexColor(...) end
    function f:GetStatusBarTexture() return self.texture end
    function f:SetRenderMode(v) self.mode=v end
    function f:SetMinMaxValues(a,b) self.minimum,self.maximum=a,b end
    function f:SetValue(v) self.value=v end
    function f:GetMinMaxValues() return self.minimum,self.maximum end
    function f:GetValue() return self.value end
    function f:CreateTexture(_,_,_,sub)
        local t=Region();t.sub=sub;textures[#textures+1]=t;return t
    end
    function f:CreateMaskTexture() return Region() end
    function f:CreateLine() local t=Region();lines[#lines+1]=t;return t end
    function f:RegisterEvent(e) self.events[e]=true end
    function f:RegisterUnitEvent(e,unit) assert(e:sub(1,5)=="UNIT_");assert(unit=="player");self.events[e]=true end
    function f:SetScript(e,fn) self.scripts[e]=fn end
    function f:UnregisterAllEvents() self.events={} end
    function f:SetAllPoints() end
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
local function Marker()
    return Layer("death_strike_marker.png")
end
local function Position(t,u,v)
    local q=assert(t.coords)
    local ux,uy=q[5]-q[1],q[6]-q[2]
    local vx,vy=q[3]-q[1],q[4]-q[2]
    local du,dv=u-q[1],v-q[2]
    local det=ux*vy-uy*vx
    local fx=(du*vy-dv*vx)/det
    local fy=(ux*dv-uy*du)/det
    return {t.x+(fx-0.5)*t.w,t.y+(0.5-fy)*t.h}
end
local function Ends(t) return Position(t,0.0625,0.5),Position(t,0.9375,0.5) end
local function Thickness(t)
    local a,b=Position(t,0.5,0.375),Position(t,0.5,0.625)
    return math.sqrt((a[1]-b[1])^2+(a[2]-b[2])^2)
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
local start=Ends(assert(Marker()))
Near(start[1], 49.1 * math.cos(angle))
Near(start[2], -49.1 * math.sin(angle))
''')


def test_aura_controls_and_visibility_through_login_events_and_settings():
    run_scenario(r'''
local controls=assert(rows["凝固之血"],"existing settings page must include blood aura")
local bg=assert(Layer("coagulated_blood_arc.png",0),"aura background required")
local fill=assert(Layer("coagulated_blood_fill.png",1),"aura fill required")
local shadow=assert(Layer("coagulated_blood_arc_shadow.png"))
assert(shadow.sub < Layer("health_arc_shadow.png").sub,"aura shadow below health shadow")
assert(not shadow.mask,"shadow must not be fill-masked")
assert(bg.shown and fill.shown and shadow.shown)
Near(controls["满条层数"].getValue(),150)
-- 75/150 的中间位置：起点99减2度余量，加53度的一半。
assert(not fill.mask and fill.radialStart==nil and fill.radialEnd==nil)
controls["启用"].setValue(false)
assert(not bg.shown and not fill.shown and not shadow.shown)
SlashCmdList.MYUICHH("demo")
assert(not bg.shown and not fill.shown and not shadow.shown)
SlashCmdList.MYUICHH("demo")
controls["启用"].setValue(true)
controls["满条层数"].setValue(75)
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Near(bar.minimum,-9.90566037735849);Near(bar.maximum,499.528301886792)
assert(bar.value==75)
aura=nil;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown and not shadow.shown)
aura={applications=75};Event("UNIT_AURA")
assert(bg.shown and fill.shown and shadow.shown)
playerClass="MAGE";Page()
for _,control in pairs(rows["凝固之血"]) do assert(control.disabled()) end
''')


def test_filtered_marker_changes_position_direction_scale_and_switch():
    run_scenario(r'''
local controls=assert(rows["灵打消耗刻度"],"cost marker controls required")
local line=assert(Marker(),"must draw one filtered line texture")
assert(line.shown)
Near(Thickness(line),1.5)
fee=50;Tick()
-- 满符能100、费用50，在从441度向339度填充的弧中点390度。
local start,finish=Ends(line)
Near(start[1],49.1*math.sqrt(3)/2);Near(start[2],-24.55)
Near(finish[1],58.9*math.sqrt(3)/2);Near(finish[2],-29.45)
controls["粗细"].setValue(2.25)
Near(Thickness(line),2.25)
rows["常规"]["HUD 缩放"].setValue(2)
Near(Thickness(line),4.5);start,finish=Ends(line);Near(finish[2],-58.9)
maximum=200;Event("UNIT_MAXPOWER")
-- 费用仍50，比例改为1/4，刻度位置和方向一起变。
start,finish=Ends(line)
assert(math.abs(finish[2]+58.9)>1)
Near(start[1]*finish[2]-start[2]*finish[1],0)
controls["启用"].setValue(false)
assert(not line.shown)
SlashCmdList.MYUICHH("demo");assert(not line.shown)
''')


def test_unreadable_values_hide_only_new_data_and_recover():
    run_scenario(r'''
local bg=Layer("coagulated_blood_arc.png",0)
local fill=Layer("coagulated_blood_fill.png",1)
local shadow=Layer("coagulated_blood_arc_shadow.png")
local line=Marker()
aura={applications=secret};fee=secret;Tick()
assert(bg.shown and shadow.shown and fill.shown and not line.shown)
assert(Layer("health_arc.png",1).shown and Layer("power_arc.png",1).shown)
aura=secret;maximum=secret;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown and not shadow.shown and not line.shown)
aura={applications=300};fee=0;maximum=100;Tick()
assert(bg.shown and fill.shown and line.shown)
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Near(bar.maximum,999.056603773585);assert(bar.value==300)
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
local fill=Layer("coagulated_blood_fill.png",1)
local shadow=Layer("coagulated_blood_arc_shadow.png")
rows["凝固之血"]["条背景"].setValue(40)
rows["凝固之血"]["填充颜色"].setValue(25)
rows["灵打消耗刻度"]["刻度颜色"].setValue(60)
rows["常规"]["阴影"].setValue(30)
Near(bg.color[4],0.4);Near(fill.color[4],0.25);Near(Marker().color[4],0.6)
Near(shadow.color[4],0.3);Near(Layer("health_arc_shadow.png").color[4],0.3)
assert(fill.color[1]==1 and fill.color[2]==1 and fill.color[3]==1)
MYUI_CrosshairHUDDB.elements.coagulatedBlood.fill={0.2,0.3,0.4}
NS.Config.Load();NS.Core.ApplyConfig()
Near(fill.color[1],0.2);Near(fill.color[2],0.3);Near(fill.color[3],0.4)
assert(not bg.mask and not shadow.mask and not fill.mask)
''')


def test_tracked_blood_aura_survives_restricted_direct_lookup():
    run_scenario(r'''
aura=nil
local item={auraDataCached={applications=75},auraDataUnit="player"}
function item:GetCooldownInfo() return {spellID=463730} end
function item:IsActive() return true end
BuffIconCooldownViewer={GetItemFrames=function() return {item} end}
Tick()
local fill=Layer("coagulated_blood_fill.png",1)
assert(fill.shown, "tracked buff must render when direct lookup misses")
assert(not fill.mask and fill.radialStart==nil and fill.radialEnd==nil)
item.auraDataCached={applications=secret};Tick()
assert(fill.shown and Layer("coagulated_blood_arc_shadow.png").shown, "restricted stacks must reach native drawing")
item.auraDataCached=nil;Tick()
assert(not fill.shown and not Layer("coagulated_blood_arc_shadow.png").shown)
item.auraDataCached={applications=75}
function item:GetCooldownInfo() return {spellID=999} end
Tick();assert(not fill.shown)
item.auraDataCached={spellId=463730,applications=75}
Tick();assert(fill.shown, "match actual buff identity, not only monitor item identity")
item.auraDataCached={spellId=secret,applications=75}
Tick();assert(not fill.shown, "do not compare restricted spell identity")
''')


def test_filtered_marker_uses_mipmaps_without_native_line():
    run_scenario(r'''
local marker=assert(Marker())
assert(#lines==0, "avoid native segmented line rasterization")
assert(marker.filter=="TRILINEAR", "shrinking must sample mipmaps")
assert(marker.snap==false and marker.bias==0)
''')


def test_linked_blood_aura_passes_restricted_stacks_to_native_radial_fill():
    run_scenario(r'''
aura=nil
local item={auraDataCached={applications=secret},auraDataUnit="player"}
function item:GetCooldownInfo() return {spellID=49998} end
function item:GetCooldownID() return 42 end
function item:IsActive() return true end
C_CooldownViewer={GetCooldownViewerCooldownInfo=function(id)
    assert(id==42);return {spellID=49998,linkedSpellIDs={463730}}
end}
BuffIconCooldownViewer={GetItemFrames=function() return {item} end}
Tick()
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
assert(bar and bar.shown,"linked buff must have visible native radial fill")
assert(rawequal(bar.value,secret),"original restricted stacks must reach the engine unchanged")
Near(bar.minimum,-19.811320754717);Near(bar.maximum,999.056603773585)
assert(bar.mode==Enum.StatusBarRenderMode.Radial)
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil)
assert(bar.texture.radialReverse==false and not bar.texture.mask)
rows["凝固之血"]["满条层数"].setValue(200)
Near(bar.maximum,1332.07547169811);assert(rawequal(bar.value,secret))
rows["凝固之血"]["启用"].setValue(false);assert(not bar.shown)
rows["凝固之血"]["启用"].setValue(true);assert(bar.shown)
item.auraDataCached=nil;Tick();assert(not bar.shown)
''')


def test_native_blood_fill_zero_full_range_scaling_and_missing_stacks():
    run_scenario(r'''
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
assert(bar)
for _,value in ipairs({0,75,150,300}) do
    aura={applications=value};Tick()
    assert(bar.shown and bar.value==value)
    Near(bar.minimum,-19.811320754717);Near(bar.maximum,999.056603773585)
end
rows["常规"]["HUD 缩放"].setValue(2)
assert(NS.Elements.scale==2)
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil)
aura={};Tick()
assert(not bar.shown and Layer("coagulated_blood_arc.png",0).shown)
local original=bar.SetValue
function bar:SetValue() error("engine rejected value") end
aura={applications=secret};Tick();assert(not bar.shown)
bar.SetValue=original;Tick();assert(bar.shown and rawequal(bar.value,secret))
''')


def test_blood_monitor_skips_wrong_ambiguous_and_broken_cache_items():
    run_scenario(r'''
aura=nil
local wrong={auraDataUnit="player",auraDataCached={spellId=999,applications=75}}
function wrong:GetCooldownInfo() return {spellID=49998,linkedSpellIDs={463730}} end
local broken={auraDataUnit="player"}
function broken:GetCooldownInfo() error("stale item") end
local good={auraDataUnit="player",auraDataCached={spellId=463730,applications=secret}}
function good:GetCooldownInfo() return {spellID=49998,linkedSpellIDs={463730,999}} end
local entries={wrong}
BuffIconCooldownViewer={GetItemFrames=function() return entries end}
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Tick();assert(not bar.shown,"explicit different buff must not match linked metadata")
entries={broken,good};Tick()
assert(bar.shown and rawequal(bar.value,secret),"bad cache must not stop later valid items")
good.auraDataCached={spellId=secret,applications=secret};entries={good};Tick()
assert(not bar.shown,"ambiguous linked buffs must not impersonate coagulated blood")
function good:GetCooldownInfo() return {spellID=49998,linkedSpellIDs={463730}} end
Tick();assert(bar.shown and rawequal(bar.value,secret))
good.auraDataCached=setmetatable({}, {__index=function() error("restricted table access") end})
Tick();assert(not bar.shown,"unreadable table fields must be caught")
''')


def test_blood_fill_has_same_filtered_unsnapped_sampling_as_other_shapes():
    run_scenario(r'''
local fill=assert(Layer("coagulated_blood_fill.png",1))
assert(fill.filter=="TRILINEAR")
assert(fill.snap==false and fill.bias==0,"new fill must not snap edges to pixels")
for _,file in ipairs({"health_arc.png","power_arc.png","coagulated_blood_arc.png","coagulated_blood_arc_shadow.png"}) do
    local t=assert(Layer(file));assert(t.filter=="TRILINEAR" and t.snap==false and t.bias==0)
end
for _,scale in ipairs({0.5,1,2}) do
    rows["常规"]["HUD 缩放"].setValue(scale)
    Near(NS.Elements.frame.w,128*scale)
    assert(fill.filter=="TRILINEAR" and fill.snap==false and fill.bias==0)
    Near(Thickness(Marker()),1.5*scale)
end
''')


def test_blood_diagnostic_reports_actual_range_and_safe_raw_values():
    run_scenario(r'''
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
function bar.texture:GetRadialProgressBarPercent()
    if rawequal(bar.value,secret) then return secret end
    return (bar.value-bar.minimum)/(bar.maximum-bar.minimum)
end
aura={applications=16};Tick();SlashCmdList.MYUICHH("blood")
local result=table.concat(messages,"\n")
assert(result:find("实际读取层数：16",1,true))
assert(result:find("游戏绘制量程：-19.8113～999.057",1,true))
assert(result:find("圆形进度：0.0351481",1,true))
messages={};aura={applications=secret};Tick();SlashCmdList.MYUICHH("blood")
result=table.concat(messages,"\n")
assert(result:find("实际读取层数：受限或缺失",1,true))
assert(result:find("圆形进度：受限或缺失",1,true))
''')


def test_fixed_blood_probe_uses_real_render_path_and_restores_live_buff():
    run_scenario(r'''
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
aura={applications=secret};Tick()
SlashCmdList.MYUICHH("bloodtest 16")
assert(bar.shown and bar.value==16,"fixed probe must bypass restricted live stacks")
Near(bar.minimum,-19.811320754717);Near(bar.maximum,999.056603773585)
Tick();assert(bar.value==16,"polling must retain the calibration value")
SlashCmdList.MYUICHH("bloodtest 75");assert(bar.value==75)
SlashCmdList.MYUICHH("bloodtest 0");assert(bar.value==0)
SlashCmdList.MYUICHH("bloodtest 150");assert(bar.value==150)
SlashCmdList.MYUICHH("bloodtest 999");assert(bar.value==150,"invalid probe must not affect rendering")
rows["凝固之血"]["启用"].setValue(false);assert(not bar.shown)
rows["凝固之血"]["启用"].setValue(true)
SlashCmdList.MYUICHH("bloodtest off");assert(rawequal(bar.value,secret))
aura=nil;Tick();assert(not bar.shown)
SlashCmdList.MYUICHH("bloodtest 16");assert(bar.shown and bar.value==16)
SlashCmdList.MYUICHH("bloodtest off");assert(not bar.shown)
Near(rows["凝固之血"]["满条层数"].getValue(),150)
''')


def test_blood_stack_counts_map_to_short_arc_angles_not_full_circle_fractions():
    run_scenario(r'''
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
for _,pair in ipairs({{0,97},{16,102.653333333333},{75,123.5},{150,150}}) do
    SlashCmdList.MYUICHH("bloodtest "..pair[1])
    -- 原生整圆比例：底部90度为起点；预期角度取自已确认的短弧设计。
    local fraction=(bar.value-bar.minimum)/(bar.maximum-bar.minimum)
    Near(90+360*fraction,pair[2])
end
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil,
    "do not crop or remap the native whole-circle defaults")
rows["凝固之血"]["满条层数"].setValue(200)
SlashCmdList.MYUICHH("bloodtest off")
aura={applications=100};Tick()
Near(90+360*(bar.value-bar.minimum)/(bar.maximum-bar.minimum),123.5)
aura={applications=secret};Tick();assert(rawequal(bar.value,secret))
''')


def test_short_blood_fill_enables_narrow_dynamic_edge_smoothing_at_all_scales():
    run_scenario(r'''
local fill=assert(Layer("coagulated_blood_fill.png",1))
local mask=assert(Layer("health_arc.png",1).mask)
assert(mask.filter=="TRILINEAR" and mask.snap==false and mask.bias==0)
assert(type(fill.radialFeather)=="number" and fill.radialFeather>0,
    "native moving edge must explicitly enable smoothing")
assert(fill.radialFeather<0.01,"edge smoothing must not blur the whole short arc")
local feather=fill.radialFeather
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
for _,scale in ipairs({0.5,1,2}) do
    rows["常规"]["HUD 缩放"].setValue(scale)
    SlashCmdList.MYUICHH("bloodtest 10")
    assert(bar.value==10,"short-edge calibration must render ten layers")
    assert(fill.radialFeather==feather and fill.filter=="TRILINEAR" and fill.snap==false)
    Near(90+360*(bar.value-bar.minimum)/(bar.maximum-bar.minimum),100.533333333333)
end
SlashCmdList.MYUICHH("bloodtest off")
''')
