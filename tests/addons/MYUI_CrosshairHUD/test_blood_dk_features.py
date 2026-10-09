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
local playerSpec, now, pageRefreshes = 250, 10, 0
local secret = setmetatable({}, { __index = function() error("secret read") end })
local detectorThrows, auraThrows, feeThrows = false, false, false
local feeEntries
function issecretvalue(v)
    if detectorThrows then error("detector unavailable") end
    return rawequal(v, secret)
end
function UnitClass() return "死亡骑士", playerClass end
function GetTime() return now end
C_SpecializationInfo = {
    GetSpecialization = function() return 1 end,
    GetSpecializationInfo = function() return playerSpec end,
}
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
function CreateFrame(kind, _, parent, template)
    local f = { events={},scripts={},kind=kind,parent=parent,template=template }
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
    function f:SetScale(v) self.scale=v end
    function f:GetFrameLevel() return self.level or 5 end
    function f:SetFrameLevel(v) self.level=v end
    function f:EnableMouse() end
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
__NATIVE_SUPPORT__
local rows, section, gears, gearRefresh = {}, nil, {}, {}
EllesmereUI = { _modules={}, _prebuilding=true, Widgets={} }
function EllesmereUI.Widgets:SectionHeader(_,title) section=title;rows[title]={};return {},20 end
function EllesmereUI.Widgets:DualRow(_,_,left,right)
    rows[section][left.text]=left
    if right.text then rows[section][right.text]=right end
    return { _leftRegion={}, _rightRegion={} },20
end
function EllesmereUI.BuildInlineCog(region,opts)
    assert(region == opts.captureRegion, "齿轮必须挂在所属设置格上")
    gears[section] = opts
    local function update() opts.blocked = opts.disabled and opts.disabled() or false end
    update();gearRefresh[#gearRefresh+1]=update
    for _,r in ipairs(opts.rows) do
        rows[section][r.label]={getValue=r.get,setValue=r.set,disabled=r.disabled}
    end
end
function EllesmereUI:RefreshPage()
    pageRefreshes=pageRefreshes+1
    for _, fn in ipairs(gearRefresh) do fn() end
end
for _, name in ipairs({"Logic","Elements","Config","Debug","Core"}) do
    assert(loadfile(dir.."/"..name..".lua"))()
end
local NS = MYUI_CHH
local function Event(e,a,b,c)
    if a==nil then a="player" end
    for _,f in ipairs(frames) do if f.events[e] then f.scripts.OnEvent(f,e,a,b,c) end end
end
local function Tick() for _,fn in ipairs(tickers) do fn() end end
local function Page()
    rows={};gears={};gearRefresh={};EllesmereUI._modules.MYUI_CrosshairHUD.buildPage(nil,{},0)
end
local function Layer(file,sub,x)
    for _,t in ipairs(textures) do
        if t.path and t.path:sub(-#file)==file and (sub==nil or t.sub==sub) and (x==nil or t.x==x) then return t end
    end
end
local function Marker()
    return Layer("death_strike_marker.blp")
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
-- 行为回归使用明确量程与缩放，避免新安装默认值改变几何测试输入。
MYUI_CrosshairHUDDB={scale=1,elements={coagulatedBlood={maxStacks=150},deathStrike={thickness=1.5}}}
Event("PLAYER_LOGIN")
Page()
__SCENARIO__
io.write("PASS: blood DK features\n")
'''


def run_scenario(scenario, native=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'features.lua'
        source = HARNESS.replace('__SCENARIO__', scenario).replace('__NATIVE_SUPPORT__', NATIVE_SUPPORT if native else '')
        if native:
            source = source.replace('{"Logic","Elements","Config","Debug","Core"}', '{"Logic","NativeBlood","Elements","Config","Debug","Core"}')
        path.write_text(source, encoding='utf-8')
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


def test_blood_specialization_switch_hides_controls_and_preserves_settings():
    run_scenario(r'''
local cfg=NS.Config.Get()
local controls=rows["凝固止血监控条"]
local fill=assert(Layer("coagulated_blood_fill.blp",1))
assert(fill.shown and not controls["启用"].disabled())
controls["启用"].setValue(false)
assert(not controls["启用"].disabled(),"disabled element must remain re-enableable")
controls["启用"].setValue(true)
cfg.elements.coagulatedBlood.fill={0.2,0.3,0.4}
local oldRefresh=pageRefreshes
playerSpec=251;Event("PLAYER_SPECIALIZATION_CHANGED")
assert(not fill.shown,"frost specialization must hide blood feature")
assert(pageRefreshes>oldRefresh,"specialization event must refresh open settings")
for _,control in pairs(controls) do assert(control.disabled()) end
controls["启用"].setValue(false)
assert(cfg.elements.coagulatedBlood.enabled,"ineligible callbacks must preserve saved toggle")
playerSpec=250;Event("PLAYER_SPECIALIZATION_CHANGED")
assert(fill.shown and not controls["启用"].disabled())
Near(fill.color[1],0.2);Near(fill.color[2],0.3);Near(fill.color[3],0.4)
playerSpec=secret;Event("PLAYER_SPECIALIZATION_CHANGED")
assert(not fill.shown and controls["启用"].disabled())
playerSpec=250;Event("PLAYER_SPECIALIZATION_CHANGED")
assert(fill.shown)
''')


def test_boiling_point_pair_countdown_chain_and_clearing_through_events():
    run_scenario(r'''
local controls=assert(rows["沸点循环监控条"],"boiling point must use the existing settings page")
local cfg=NS.Config.Get().elements.boilingPoint
assert(cfg.enabled and cfg.fillMode==nil and cfg.maxStacks==nil)
Near(cfg.fill[1],0.77);Near(cfg.fill[2],0.12);Near(cfg.fill[3],0.23)
assert(cfg.fillAlpha==1 and cfg.bgAlpha==0 and cfg.bg[1]==0.77)
assert(#NS.Config.CellPlan("boilingPoint")==3 and not gears["沸点循环监控条"])
local function Echo()
    for _,t in ipairs(textures) do
        if t.path and t.path:find("coagulated_blood_fill.blp",1,true) and t.mask then return t end
    end
end
local fill=assert(Echo(),"right-side fine arc must reuse the centered material")
assert(not fill.shown)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
assert(not fill.shown,"proc alone must not start the 3-second echo")
Event("UNIT_SPELLCAST_SUCCEEDED","player","cast1",50842)
now=10.2;Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842)
assert(fill.shown and fill.mask,"paired cast/HIDE must display the right fine arc")
local initial=fill.mask.rotation
now=11.5;Tick();local halfway=fill.mask.rotation
assert(initial~=halfway,"time must advance the displayed fill")
Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
assert(fill.mask.rotation==halfway,"new proc must not reset this countdown")
    now=13.4;Tick();assert(fill.shown,"pending proc must continue at the old deadline")
now=16;Tick();assert(not fill.shown,"a round without new proc must hide on expiry")
-- Opposite event order, unrelated units/spells, and a cast outside the pairing window.
now=20;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842)
now=20.2;Event("UNIT_SPELLCAST_SUCCEEDED","target","x",50842)
Event("UNIT_SPELLCAST_SUCCEEDED","player","x",999)
assert(not fill.shown)
Event("UNIT_SPELLCAST_SUCCEEDED","player","cast2",50842);assert(fill.shown)
now=23.2;Tick();assert(not fill.shown)
now=30;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
Event("UNIT_SPELLCAST_SUCCEEDED","player","cast3",50842)
now=30.31;Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842)
assert(not fill.shown,"unpaired signals must not start an echo")
now=40;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",secret)
Event("UNIT_SPELLCAST_SUCCEEDED","player","x",secret)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",secret);assert(not fill.shown)
now=50;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
Event("UNIT_SPELLCAST_SUCCEEDED","player","cast4",50842)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842);assert(fill.shown)
controls["启用"].setValue(false);assert(not fill.shown and not controls["启用"].disabled())
controls["启用"].setValue(true);Tick();assert(not fill.shown,"re-enable must not guess history")
now=60;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
Event("UNIT_SPELLCAST_SUCCEEDED","player","cast5",50842)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842);assert(fill.shown)
playerSpec=251;Event("PLAYER_SPECIALIZATION_CHANGED")
assert(not fill.shown and controls["启用"].disabled())
playerSpec=250;Event("PLAYER_SPECIALIZATION_CHANGED");assert(not fill.shown)
-- A new confirmed manual consumption replaces the pending automatic round.
now=70;Event("UNIT_SPELLCAST_SUCCEEDED","player","cast6",50842)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842)
now=71;Event("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",50842)
now=71.5;Event("UNIT_SPELLCAST_SUCCEEDED","player","cast7",50842)
Event("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",50842)
now=73.2;Tick();assert(fill.shown)
now=74.5;Tick();assert(not fill.shown,"second manual consumption must expire at its cast+3")
''')


def test_reused_shapes_and_four_source_crosshair_preserve_rendered_layout():
    run_scenario(r'''
local arms,armShadows,dots,dotShadows=0,0,0,0
for _,t in ipairs(textures) do
    if t.path then
        if t.path:find("crosshair_arm.blp",1,true) then
            arms=arms+1;assert(t.coords and #t.coords==8,"arms need fixed UV rotations")
        elseif t.path:find("crosshair_arm_shadow.blp",1,true) then
            armShadows=armShadows+1;assert(t.coords and #t.coords==8)
        elseif t.path:find("crosshair_point.blp",1,true) then dots=dots+1
        elseif t.path:find("crosshair_point_shadow.blp",1,true) then dotShadows=dotShadows+1 end
        assert(not t.path:find("power_arc.blp",1,true),"power must reuse the health shape")
        assert(not t.path:find("resource_04",1,true) and not t.path:find("resource_05",1,true)
            and not t.path:find("resource_06",1,true),"right runes must reuse the three left shapes")
    end
end
assert(arms==4 and armShadows==4 and dots==1 and dotShadows==1,"four sources, ten instances")
local power
for _,t in ipairs(textures) do
    if t.path and t.path:find("health_arc.blp",1,true) and t.x==32 and t.sub==1 then power=t end
end
assert(power and power.coords[1]==1 and power.coords[2]==0,"right shape alone must mirror")
assert(power.mask and power.mask.coords==nil,"fill mask must retain its original orientation")
local arm,shadow
for _,t in ipairs(textures) do
    if t.path and t.path:find("crosshair_arm.blp",1,true) then arm=t end
    if t.path and t.path:find("crosshair_arm_shadow.blp",1,true) then shadow=t end
end
for i=1,8 do assert(arm.coords[i]==shadow.coords[i],"arm and shadow rotations must match") end
rows["准星"]["启用"].setValue(false)
for _,t in ipairs(textures) do if t.path and t.path:find("crosshair_",1,true) then assert(not t.shown) end end
rows["准星"]["启用"].setValue(true)
rows["常规"]["HUD 缩放"].setValue(2)
    Near(arm.x,0);Near(arm.y,31)
Near(arm.w,16);Near(arm.h,64)
''')


def test_settings_gears_write_live_controls_and_preserve_existing_settings():
    run_scenario(r'''
local count=0;for _ in pairs(gears) do count=count+1 end
assert(count==3 and #gears["常规"].rows==2)
assert(gears["凝固止血监控条"].rows[1].label=="最大显示层数")
assert(gears["灵打消耗刻度"].rows[1].label=="粗细")
local cfg=NS.Config.Get()
rows["常规"]["HUD 缩放"].setValue(0.8);assert(NS.Elements.scale==0.8)
rows["常规"]["图层"].setValue("HIGH");assert(cfg.strata=="HIGH")
rows["凝固止血监控条"]["最大显示层数"].setValue(100);assert(cfg.elements.coagulatedBlood.maxStacks==100)
rows["灵打消耗刻度"]["粗细"].setValue(2);Near(Thickness(Marker()),1.6)
cfg.elements.coagulatedBlood.enabled=false;assert(gears["凝固止血监控条"].disabled())
cfg.elements.coagulatedBlood.enabled=true;playerClass="MAGE";assert(gears["凝固止血监控条"].disabled())
playerClass="DEATHKNIGHT"
cfg.position={x=42,y=-9};cfg.visHideMounted=true;cfg.scale=1.25
NS.Config.Load();assert(NS.Config.Get().scale==1.25)
assert(NS.Config.Get().position.x==42 and NS.Config.Get().visHideMounted==true)
''')


def test_each_gear_refreshes_with_its_toggle_and_explains_its_own_settings():
    run_scenario(r'''
for _, sectionName in ipairs({"常规","凝固止血监控条","灵打消耗刻度"}) do
    local controlName=sectionName=="常规" and "启用准星HUD" or "启用"
    local toggle=rows[sectionName][controlName]
    local gear=gears[sectionName]
    assert(not gear.blocked)
    toggle.setValue(false);assert(gear.blocked,"关闭后齿轮必须立即置灰: "..sectionName)
    for _, control in ipairs(gear.rows) do assert(control.disabled()) end
    toggle.setValue(true);assert(not gear.blocked,"打开后齿轮必须立即可点: "..sectionName)
end
assert(gears["常规"].tip:find("图层",1,true))
assert(gears["凝固止血监控条"].tip:find("层",1,true))
assert(gears["灵打消耗刻度"].tip:find("粗细",1,true))
assert(not gears["灵打消耗刻度"].disabledTooltip():find("凝固之血",1,true))
rows["常规"]["启用准星HUD"].setValue(false)
assert(gears["凝固止血监控条"].blocked and gears["灵打消耗刻度"].blocked)
assert(rows["常规"]["阴影"].disabled(), "总开关关闭后阴影滑杆必须置灰")
local oldAlpha=NS.Config.Get().shadowAlpha
rows["常规"]["阴影"].setValue(25)
assert(NS.Config.Get().shadowAlpha==oldAlpha, "禁用时不得写入阴影透明度")
rows["常规"]["启用准星HUD"].setValue(true)
assert(not gears["凝固止血监控条"].blocked and not gears["灵打消耗刻度"].blocked)
assert(not rows["常规"]["阴影"].disabled(), "总开关打开后阴影滑杆必须恢复")
playerClass="MAGE";EllesmereUI:RefreshPage()
assert(gears["凝固止血监控条"].blocked and not gears["灵打消耗刻度"].blocked)
assert(gears["凝固止血监控条"].disabledTooltip():find("死亡骑士",1,true))
''')


def test_aura_controls_and_visibility_through_login_events_and_settings():
    run_scenario(r'''
local controls=assert(rows["凝固止血监控条"],"existing settings page must include blood aura")
local bg=assert(Layer("coagulated_blood_fill.blp",0),"aura background required")
local fill=assert(Layer("coagulated_blood_fill.blp",1),"aura fill required")
assert(not Layer("coagulated_blood_arc_shadow.blp"),"blood shadow must not be created")
assert(bg.shown and fill.shown)
Near(controls["最大显示层数"].getValue(),150)
-- 75/150 的中间位置：起点99减2度余量，加104度的一半。
assert(not fill.mask and fill.radialStart==nil and fill.radialEnd==nil)
controls["启用"].setValue(false)
assert(not bg.shown and not fill.shown)
SlashCmdList.MYUICHH("demo")
assert(not bg.shown and not fill.shown)
SlashCmdList.MYUICHH("demo")
controls["启用"].setValue(true)
controls["最大显示层数"].setValue(75)
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Near(bar.minimum,-5.04807692307692);Near(bar.maximum,254.567307692308)
assert(bar.value==75)
aura=nil;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown)
aura={applications=75};Event("UNIT_AURA")
assert(bg.shown and fill.shown)
playerClass="MAGE";Page()
for _,control in pairs(rows["凝固止血监控条"]) do assert(control.disabled()) end
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
local bg=Layer("coagulated_blood_fill.blp",0)
local fill=Layer("coagulated_blood_fill.blp",1)
assert(not Layer("coagulated_blood_arc_shadow.blp"))
local line=Marker()
aura={applications=secret};fee=secret;Tick()
assert(bg.shown and fill.shown and not line.shown)
assert(Layer("health_arc.blp",1).shown and Layer("health_arc.blp",1,32).shown)
aura=secret;maximum=secret;Event("UNIT_AURA")
assert(not bg.shown and not fill.shown and not line.shown)
aura={applications=300};fee=0;maximum=100;Tick()
assert(bg.shown and fill.shown and line.shown)
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Near(bar.maximum,509.134615384615);assert(bar.value==300)
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
local bg=Layer("coagulated_blood_fill.blp",0)
local fill=Layer("coagulated_blood_fill.blp",1)
assert(not Layer("coagulated_blood_arc_shadow.blp"))
rows["凝固止血监控条"]["条背景"].setValue(40)
rows["凝固止血监控条"]["填充颜色"].setValue(25)
rows["灵打消耗刻度"]["刻度颜色"].setValue(60)
rows["常规"]["阴影"].setValue(30)
Near(bg.color[4],0.4);Near(fill.color[4],0.25);Near(Marker().color[4],0.6)
Near(Layer("health_arc_shadow.blp").color[4],0.3)
assert(fill.color[1]==1 and fill.color[2]==1 and fill.color[3]==1)
MYUI_CrosshairHUDDB.elements.coagulatedBlood.fill={0.2,0.3,0.4}
NS.Config.Load();NS.Core.ApplyConfig()
Near(fill.color[1],0.2);Near(fill.color[2],0.3);Near(fill.color[3],0.4)
assert(not bg.mask and not fill.mask)
''')


def test_tracked_blood_aura_survives_restricted_direct_lookup():
    run_scenario(r'''
aura=nil
local item={auraDataCached={applications=75},auraDataUnit="player"}
function item:GetCooldownInfo() return {spellID=463730} end
function item:IsActive() return true end
BuffIconCooldownViewer={GetItemFrames=function() return {item} end}
Tick()
local fill=Layer("coagulated_blood_fill.blp",1)
assert(fill.shown, "tracked buff must render when direct lookup misses")
assert(not fill.mask and fill.radialStart==nil and fill.radialEnd==nil)
item.auraDataCached={applications=secret};Tick()
assert(fill.shown, "restricted stacks must reach native drawing")
item.auraDataCached=nil;Tick()
assert(not fill.shown)
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
assert(marker.snap==nil and marker.bias==nil)
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
Near(bar.minimum,-10.096153846154);Near(bar.maximum,509.134615384615)
assert(bar.mode==Enum.StatusBarRenderMode.Radial)
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil)
assert(bar.texture.radialReverse==false and not bar.texture.mask)
rows["凝固止血监控条"]["最大显示层数"].setValue(200)
Near(bar.maximum,678.846153846154);assert(rawequal(bar.value,secret))
rows["凝固止血监控条"]["启用"].setValue(false);assert(not bar.shown)
rows["凝固止血监控条"]["启用"].setValue(true);assert(bar.shown)
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
    Near(bar.minimum,-10.096153846154);Near(bar.maximum,509.134615384615)
end
rows["常规"]["HUD 缩放"].setValue(2)
assert(NS.Elements.scale==2)
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil)
aura={};Tick()
assert(not bar.shown and Layer("coagulated_blood_fill.blp",0).shown)
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


def test_shapes_preserve_original_pixel_alignment_defaults():
    run_scenario(r'''
local fill=assert(Layer("coagulated_blood_fill.blp",1))
assert(fill.filter=="TRILINEAR")
assert(fill.snap==nil and fill.bias==nil,"new fill must preserve original alignment defaults")
for _,file in ipairs({"health_arc.blp","health_arc.blp","coagulated_blood_fill.blp"}) do
    local t=assert(Layer(file));assert(t.filter=="TRILINEAR" and t.snap==nil and t.bias==nil)
end
for _,scale in ipairs({0.5,1,2}) do
    rows["常规"]["HUD 缩放"].setValue(scale)
    Near(NS.Elements.frame.w,128*scale)
    assert(fill.filter=="TRILINEAR" and fill.snap==nil and fill.bias==nil)
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
assert(result:find("游戏绘制量程：-10.0962～509.135",1,true))
assert(result:find("圆形进度：0.0502593",1,true))
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
Near(bar.minimum,-10.096153846154);Near(bar.maximum,509.134615384615)
Tick();assert(bar.value==16,"polling must retain the calibration value")
SlashCmdList.MYUICHH("bloodtest 75");assert(bar.value==75)
SlashCmdList.MYUICHH("bloodtest 0");assert(bar.value==0)
SlashCmdList.MYUICHH("bloodtest 150");assert(bar.value==150)
SlashCmdList.MYUICHH("bloodtest 999");assert(bar.value==150,"invalid probe must not affect rendering")
rows["凝固止血监控条"]["启用"].setValue(false);assert(not bar.shown)
rows["凝固止血监控条"]["启用"].setValue(true)
SlashCmdList.MYUICHH("bloodtest off");assert(rawequal(bar.value,secret))
aura=nil;Tick();assert(not bar.shown)
SlashCmdList.MYUICHH("bloodtest 16");assert(bar.shown and bar.value==16)
SlashCmdList.MYUICHH("bloodtest off");assert(not bar.shown)
Near(rows["凝固止血监控条"]["最大显示层数"].getValue(),150)
''')


def test_blood_stack_counts_map_to_full_arc_angles_not_full_circle_fractions():
    run_scenario(r'''
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
for _,pair in ipairs({{0,97},{16,108.093333333333},{75,149},{150,201}}) do
    SlashCmdList.MYUICHH("bloodtest "..pair[1])
    -- 原生整圆比例：底部90度为起点；预期角度取自已确认的完整弧长设计。
    local fraction=(bar.value-bar.minimum)/(bar.maximum-bar.minimum)
    Near(90+360*fraction,pair[2])
end
assert(bar.texture.radialStart==nil and bar.texture.radialEnd==nil,
    "do not crop or remap the native whole-circle defaults")
rows["凝固止血监控条"]["最大显示层数"].setValue(200)
SlashCmdList.MYUICHH("bloodtest off")
aura={applications=100};Tick()
Near(90+360*(bar.value-bar.minimum)/(bar.maximum-bar.minimum),149)
aura={applications=secret};Tick();assert(rawequal(bar.value,secret))
''')


def test_short_blood_fill_enables_narrow_dynamic_edge_smoothing_at_all_scales():
    run_scenario(r'''
local fill=assert(Layer("coagulated_blood_fill.blp",1))
local mask=assert(Layer("health_arc.blp",1).mask)
assert(mask.filter=="TRILINEAR" and mask.snap==nil and mask.bias==nil)
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
    assert(fill.radialFeather==feather and fill.filter=="TRILINEAR" and fill.snap==nil)
    Near(90+360*(bar.value-bar.minimum)/(bar.maximum-bar.minimum),103.933333333333)
end
SlashCmdList.MYUICHH("bloodtest off")
''')


def test_independent_blood_scan_without_blizzard_monitor():
    run_scenario(r"""
aura=nil;BuffIconCooldownViewer=nil;BuffBarCooldownViewer=nil
local list={{spellId=999,applications=100},{spellId=463730,applications=secret}}
C_UnitAuras.GetUnitAuras=function(unit,filter)
    assert(unit=="player" and filter=="HELPFUL");return list
end
local bar
for _,f in ipairs(frames) do if f.kind=="StatusBar" then bar=f end end
Event("UNIT_AURA");assert(bar.shown and rawequal(bar.value,secret),"independent scan must render restricted stacks without monitor")
list={{spellId=463730,applications=10}};Event("UNIT_AURA");assert(bar.shown and bar.value==10)
list={};Event("UNIT_AURA");assert(not bar.shown,"removal must clear independent fill")
list={{spellId=secret,applications=75}};Event("UNIT_AURA");assert(not bar.shown,"restricted identity must never be guessed")
list={{spellId=463730,applications=16}};Event("UNIT_AURA");assert(bar.shown and bar.value==16)
rows["凝固止血监控条"]["启用"].setValue(false);assert(not bar.shown)
rows["凝固止血监控条"]["启用"].setValue(true);assert(bar.shown)
C_UnitAuras.GetUnitAuras=function() error("read denied") end
Event("UNIT_AURA");assert(not bar.shown,"failed scan must not keep stale stacks")
SlashCmdList.MYUICHH("blood")
local errorReported=false
for _,msg in ipairs(messages) do if msg:find("read denied",1,true) then errorReported=true end end
assert(errorReported,"independent scan must report readable original error")
""")


NATIVE_SUPPORT = r'''
local nativeAura, nativeContainer
local baseCreate=CreateFrame
AuraContainerInbound={}
function CreateFrame(kind,name,parent,template)
 local f=baseCreate(kind,name,parent,template)
 if kind=="AuraContainer" then
  nativeContainer=f
  function f:SetUnit(v) self.unit=v end
  function f:SetEnabled(v) self.enabled=v end
  function f:AddAuraSlot(key,filter,options)
   assert(filter=="HELPFUL" and options.candidateFilters.includeSpellIDs[463730]==true)
   local button=baseCreate("AuraButton",nil,self,"CustomAuraButtonTemplate")
   function button:SetApplicationBar(bar,opts)
    assert(bar.parent==self,"bound bar must descend from the aura button")
    self.boundBar=bar;self.maximum=opts.maxApplications
   end
   options.initializeFrame(button);self.button=button
  end
 end
 return f
end
C_UnitAuras.GetUnitAuras=function() error("native mode must never enumerate restricted auras") end
C_UnitAuras.GetPlayerAuraBySpellID=function() error("native mode must not query aura by spell ID") end
local function NativeUpdate(value)
 local b=nativeContainer.button;b.shown=value~=nil
 b.boundBar:SetMinMaxValues(0,b.maximum);b.boundBar:SetValue(value or 0)
end
'''


def test_native_container_owns_blood_without_monitor_or_lua_stack_reads():
    run_scenario(r'''
assert(not Layer("coagulated_blood_arc_shadow.blp"),"native blood must not create shadow")
local native=assert(nativeContainer,"must create native aura container")
assert(native.unit=="player" and native.enabled)
local button=assert(native.button);local bar=assert(button.boundBar)
assert(not button.shown,"empty native slot must not leave background or shadow visible")
assert(bar.mode==Enum.StatusBarRenderMode.Radial)
Near(bar.texture.radialStart,7/360);Near(bar.texture.radialEnd,249/360)
NativeUpdate(secret);Tick();assert(rawequal(bar.value,secret),"addon must not overwrite native stacks")
assert(not bar.texture.mask and bar.texture.filter=="TRILINEAR")
local function Cut(value,max)
 return 90+360*(bar.texture.radialStart+(1-bar.texture.radialStart-bar.texture.radialEnd)*value/max)
end
Near(Cut(16,150),108.09333333333);Near(Cut(75,150),149);Near(Cut(150,150),201)
NativeUpdate(nil);Tick();assert(not button.shown and bar.value==0,"native removal must hide entire aura button")
NativeUpdate(10);Tick();assert(button.shown and bar.value==10)
rows["凝固止血监控条"]["启用"].setValue(false);assert(not NS.NativeBlood.host.shown)
rows["凝固止血监控条"]["启用"].setValue(true);assert(NS.NativeBlood.host.shown)
rows["凝固止血监控条"]["最大显示层数"].setValue(200);assert(nativeContainer.button.maximum==200)
rows["常规"]["HUD 缩放"].setValue(0.5);assert(NS.NativeBlood.host.scale==0.5)
SlashCmdList.MYUICHH("bloodtest 10");assert(not NS.NativeBlood.host.shown)
SlashCmdList.MYUICHH("bloodtest off");assert(NS.NativeBlood.host.shown)
''',native=True)


def test_native_binding_recovers_after_temporary_failure_without_config_change():
    run_scenario(r'''
local base=CreateFrame
local fail=true
local attempts=0
local clock=10
GetTime=function() return clock end
CreateFrame=function(kind,...)
 if kind=="AuraContainer" then
  attempts=attempts+1
  if fail then error("temporary bind failure") end
 end
 return base(kind,...)
end
rows["凝固止血监控条"]["最大显示层数"].setValue(200)
assert(not NS.NativeBlood.ready and not NS.NativeBlood.host.shown)
fail=false
for _=1,10 do Tick() end
assert(attempts==1,"binding retry must not create containers on every refresh")
clock=12;Tick()
assert(attempts==2 and NS.NativeBlood.ready and NS.NativeBlood.host.shown,
 "same configuration must recover after transient binding failure")
assert(nativeContainer.button.maximum==200)
NativeUpdate(10);Tick();assert(nativeContainer.button.boundBar.value==10)
''',native=True)
