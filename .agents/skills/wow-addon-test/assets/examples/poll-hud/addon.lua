-- Independent example: polling controller + output sink, not shared with the oracle.
local name,ns=...
local updates=CreateFrame('Frame')
local sink
local pointType={PALADIN=9,ROGUE=4}
local specKind={[62]='arcane',[268]='stagger',[269]='chi'}
local specPower={[62]=16,[269]=12}
local function sample()
 local _,class=UnitClass('player')
 local index=GetSpecialization();local id=GetSpecializationInfo(index)
 local pt,token=UnitPowerType('player')
 local connection=UnitIsConnected('player')
 local hmax=math.max(UnitHealthMax('player'),1)
 local h=UnitHealth('player');local pmax=UnitPowerMax('player',pt);local p=UnitPower('player',pt)
 if not connection then h=hmax;p=pmax end
 sink.health(h,hmax,connection);sink.primary(pt,token,p,pmax)
 if class=='WARLOCK'then
  local scale=UnitPowerDisplayMod(7);local raw=UnitPower('player',7,true)
  local value=0;if scale~=0 then value=raw/scale end
  if id~=267 then value=math.floor(value)end
  sink.resource({kind='shards',amount=value,capacity=UnitPowerMax('player',7)});return
 end
 if class=='DEATHKNIGHT'then
  local result={kind='runes',nodes={}}
  for n=1,6 do
   local s,d,r=GetRuneCooldown(n);local v={state='empty'}
   if r then v.state='ready'elseif s~=nil then v={state='cooldown',start=s,duration=d}end
   result.nodes[n]=v
  end
  sink.resource(result);return
 end
 if class=='EVOKER'then
  local current=UnitPower('player',19);local maximum=UnitPowerMax('player',19)
  local result={kind='essence',capacity=maximum,nodes={}}
  local speed=GetPowerRegenForPowerType(19)
  if not speed or speed==0 then speed=1/5 end
  for n=1,maximum do
   local item={state='empty'}
   if n<=current then item.state='full'
   elseif n-current==1 then item={state='recharging',partial=UnitPartialPower('player',19)*.001,duration=1/speed}end
   result.nodes[n]=item
  end
  sink.resource(result);return
 end
 if id==268 then sink.resource({kind='stagger',value=UnitStagger('player')or 0,maximum=UnitHealthMax('player')});return end
 local kind='none';local power=pointType[class]or specPower[id]
 if class=='ROGUE'then kind='combo'elseif class=='PALADIN'then kind='holy'
 elseif class=='DRUID'and pt==3 then kind='druid_combo';power=4
 elseif specKind[id]then kind=specKind[id]end
 if kind=='none'then sink.resource({kind='none'});return end
 local result={kind=kind,capacity=UnitPowerMax('player',power),nodes={}}
 local active=UnitPower('player',power,kind=='arcane');local set={}
 if class=='ROGUE'then for _,pos in ipairs(GetUnitChargedPowerPoints('player'))do set[pos]=true end end
 for n=1,result.capacity do
  result.nodes[n]={full=n<=active};if kind=='combo'then result.nodes[n].charged=set[n]==true end
 end
 sink.resource(result)
end
function ns.Start(outputSink)sink=outputSink;updates:SetScript('OnUpdate',sample);sample()end
function ns.Stop()updates:SetScript('OnUpdate',nil)end
