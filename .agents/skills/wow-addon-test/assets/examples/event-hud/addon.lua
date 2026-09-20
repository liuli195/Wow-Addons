-- Executable example addon, NOT MYUI and NOT an oracle. Uses direct event updates.
local addonName,ns=...
local frame=CreateFrame('Frame')
local model={}
local function family()
 local _,class=UnitClass('player');local idx=GetSpecialization();local spec=GetSpecializationInfo(idx)
 if class=='DRUID'then return UnitPowerType('player')==3 and 'druid_combo' or 'none' end
 if class=='ROGUE'then return 'combo'end
 if class=='PALADIN'then return 'holy'end
 if class=='DEATHKNIGHT'then return 'runes'end
 if class=='WARLOCK'then return 'shards'end
 if class=='EVOKER'then return 'essence'end
 if spec==62 then return 'arcane'end
 if spec==269 then return 'chi'end
 if spec==268 then return 'stagger'end
 return 'none'
end
local function refresh()
 local connected=UnitIsConnected('player')
 local hm=UnitHealthMax('player');if hm==0 then hm=1 end
 model.health={value=connected and UnitHealth('player')or hm,maximum=hm,connected=connected}
 local pt,token=UnitPowerType('player');local pm=UnitPowerMax('player',pt)
 model.primary={type=pt,token=token,value=connected and UnitPower('player',pt)or pm,maximum=pm}
 local kind=family();local r={kind=kind};model.resource=r
 if kind=='combo'or kind=='druid_combo'or kind=='holy'or kind=='chi'or kind=='arcane'then
  local t=({combo=4,druid_combo=4,holy=9,chi=12,arcane=16})[kind]
  local max=UnitPowerMax('player',t);local current=UnitPower('player',t,kind=='arcane')
  r.capacity=max;r.nodes={};local charges=kind=='combo'and GetUnitChargedPowerPoints('player')or{}
  for i=1,max do
   r.nodes[i]={full=i<=current}
   if kind=='combo'then
    local charged=false;for _,index in ipairs(charges)do if i==index then charged=true end end
    r.nodes[i].charged=charged
   end
  end
 elseif kind=='shards'then
  local mod=UnitPowerDisplayMod(7);local amount=mod==0 and 0 or UnitPower('player',7,true)/mod
  if GetSpecialization()~=3 then amount=math.floor(amount)end
  r.capacity=UnitPowerMax('player',7);r.amount=amount
 elseif kind=='essence'then
  local n=UnitPower('player',19);local mx=UnitPowerMax('player',19)
  local rate=GetPowerRegenForPowerType(19);if rate==nil or rate==0 then rate=.2 end
  r.capacity=mx;r.nodes={}
  for i=1,mx do
   if i<=n then r.nodes[i]={state='full'}
   elseif i==n+1 then r.nodes[i]={state='recharging',partial=UnitPartialPower('player',19)/1000,duration=1/rate}
   else r.nodes[i]={state='empty'}end
  end
 elseif kind=='runes'then
  r.nodes={};for i=1,6 do
   local start,duration,ready=GetRuneCooldown(i)
   if ready then r.nodes[i]={state='ready'}elseif start then r.nodes[i]={state='cooldown',start=start,duration=duration}else r.nodes[i]={state='empty'}end
  end
 elseif kind=='stagger'then r.value=UnitStagger('player')or 0;r.maximum=UnitHealthMax('player')end
end
local events={'UNIT_HEALTH','UNIT_MAXHEALTH','UNIT_POWER_UPDATE','UNIT_POWER_FREQUENT','UNIT_MAXPOWER','UNIT_DISPLAYPOWER','UNIT_POWER_POINT_CHARGE','UNIT_AURA','PLAYER_SPECIALIZATION_CHANGED','PLAYER_ENTERING_WORLD','PLAYER_TALENT_UPDATE','UPDATE_SHAPESHIFT_FORM','RUNE_POWER_UPDATE'}
function ns.Start()
 for _,event in ipairs(events)do frame:RegisterEvent(event)end
 frame:SetScript('OnEvent',function(_,event,unit)
  if event:sub(1,5)=='UNIT_'and unit~='player'then return end
  refresh()
 end)
 refresh()
end
function ns.Snapshot()return model end
function ns.Stop()frame:UnregisterAllEvents();frame:SetScript('OnEvent',nil)end
