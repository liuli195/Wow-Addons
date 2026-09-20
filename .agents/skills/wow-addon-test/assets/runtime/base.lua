-- Small explicit test environment. No frame layout, drawing or game-mechanic simulation.
local M = {}
local unpackValues = table.unpack or unpack
local arrayMT = {__wowtest_array=true}
function M.array(t) return setmetatable(t or {},arrayMT) end
function M.clone(v)
 if type(v)~='table' then return v end
 local t={}; for k,x in pairs(v) do t[k]=M.clone(x) end
 if getmetatable(v)==arrayMT then setmetatable(t,arrayMT) end
 return t
end
local function quote(s)
 return '"'..s:gsub('[%z\1-\31\\"]',function(c)
  if c=='"' then return '\\"' elseif c=='\\' then return '\\\\' end
  return string.format('\\u%04x',string.byte(c))
 end)..'"'
end
function M.json(v,seen)
 local typ=type(v)
 if typ=='nil' then return 'null' end
 if typ=='boolean' then return tostring(v) end
 if typ=='number' then
  assert(v==v and v~=math.huge and v~=-math.huge,'nonfinite output')
  return string.format('%.17g',v)
 end
 if typ=='string' then return quote(v) end
 assert(typ=='table','output contains unsupported type '..typ)
 seen=seen or {}; assert(not seen[v],'cyclic output'); seen[v]=true
 local n=0; local count=0; local allInteger=true
 for k in pairs(v) do count=count+1; if type(k)~='number' or k<1 or k%1~=0 then allInteger=false else n=math.max(n,k) end end
 local arr=(getmetatable(v)==arrayMT) or (count>0 and allInteger and n==count)
 local parts={}
 if arr then
  assert(allInteger and n==count or count==0,'noncontiguous array')
  for i=1,n do parts[#parts+1]=M.json(v[i],seen) end
 else
  local keys={}; for k in pairs(v) do assert(type(k)=='string','object key must be string');keys[#keys+1]=k end
  table.sort(keys); for _,k in ipairs(keys) do parts[#parts+1]=quote(k)..':'..M.json(v[k],seen) end
 end
 seen[v]=nil
 return (arr and '[' or '{')..table.concat(parts,',')..(arr and ']' or '}')
end
function M.load(code,name,env,...)
 local f,err
 if _VERSION=='Lua 5.1' then f,err=loadstring(code,'@'..name);if f then setfenv(f,env) end
 else f,err=load(code,'@'..name,'t',env) end
 assert(f,err);return f(...)
end
local function need(t,k,label)
 assert(type(t)=='table' and t[k]~=nil,'missing input: '..(label or '')..tostring(k));return t[k]
end
function M.context(initial,profile,sources,profiles)
 local ctx={state=M.clone(initial),profile=M.clone(profile),frames={},timers={},trace=M.array(),loaded=M.array(),now=initial.time or 0,sequence=0,callbackCount=0}
 local env={}
 for _,k in ipairs({'assert','error','ipairs','pairs','next','select','tonumber','tostring','type','pcall','xpcall','rawequal','rawget','rawset','setmetatable','getmetatable'}) do env[k]=_G[k] end
 env.math=M.clone(math);env.string=M.clone(string);env.table=M.clone(table);env.unpack=unpackValues
 env.min=math.min;env.max=math.max;env.floor=math.floor;env.abs=math.abs;env.assertsafe=assert
 env._G=env;env._VERSION=_VERSION;env.tinsert=table.insert;env.tremove=table.remove
 env.Enum={PowerType={Mana=0,Rage=1,Focus=2,Energy=3,ComboPoints=4,Runes=5,RunicPower=6,SoulShards=7,LunarPower=8,HolyPower=9,Alternate=10,Maelstrom=11,Chi=12,Insanity=13,ArcaneCharges=16,Fury=17,Pain=18,Essence=19,None=-1}}
 env.SPEC_WARLOCK_DESTRUCTION=3;env.SPEC_MONK_BREWMASTER=1
 local function unit(u) assert(u=='player','unconfigured unit: '..tostring(u));return ctx.state end
 local function power(u,p)
  local s=unit(u); p=p==nil and need(s.primary,'type','primary.') or p
  return need(s.powers,tostring(p),'powers.'),p
 end
 local function api(name,fn)
  env[name]=function(...)
   local args=M.array({...});ctx.trace[#ctx.trace+1]={name=name,args=args}
   return fn(...)
  end
 end
 api('UnitHealth',function(u)return need(unit(u).health,'current','health.')end)
 api('UnitHealthMax',function(u)return need(unit(u).health,'maximum','health.')end)
 api('UnitPower',function(u,p,raw)local r=power(u,p);return need(r,raw and 'raw' or 'current','power.')end)
 api('UnitPowerMax',function(u,p,raw)local r=power(u,p);return need(r,raw and 'raw_maximum' or 'maximum','power.')end)
 api('UnitPowerDisplayMod',function(p)return need(power('player',p),'display_mod','power.')end)
 api('UnitPartialPower',function(u,p)return need(power(u,p),'partial','power.')end)
 api('GetPowerRegenForPowerType',function(p)local r=power('player',p);return r.regen,r.regen_interrupted end)
 api('UnitPowerType',function(u)local p=unit(u).primary;return need(p,'type'),need(p,'token')end)
 api('UnitIsConnected',function(u)return need(unit(u).unit,'connected','unit.')end)
 api('UnitExists',function(u)return need(unit(u).unit,'exists','unit.')end)
 api('UnitIsDead',function(u)return need(unit(u).unit,'dead','unit.')end)
 api('UnitIsGhost',function(u)return need(unit(u).unit,'ghost','unit.')end)
 api('UnitIsDeadOrGhost',function(u)local t=unit(u).unit;return t.dead or t.ghost end)
 api('UnitInVehicle',function(u)return need(unit(u).unit,'in_vehicle','unit.')end)
 api('UnitAffectingCombat',function(u)return need(unit(u).unit,'in_combat','unit.')end)
 api('UnitLevel',function(u)return need(unit(u).identity,'level','identity.')end)
 api('UnitClass',function(u)local i=unit(u).identity;return i.class_name or i.class_token,i.class_token,i.class_id end)
 api('UnitGUID',function(u)if unit(u).unit.exists then return 'synthetic-player' end return nil end)
 api('GetSpecialization',function()return need(ctx.state.identity,'spec_index','identity.')end)
 env.C_SpecializationInfo={GetSpecialization=env.GetSpecialization}
 api('GetSpecializationInfo',function(index)
  local id=ctx.state.identity; for _,p in ipairs(profiles or {profile}) do
   if p.class_id==id.class_id and p.spec_index==index then return p.spec_id,p.spec_name,'',0,p.role,p.class_token end
  end
  error('unconfigured specialization index '..tostring(index))
 end)
 api('GetSpecializationInfoByID',function(id)
  for _,p in ipairs(profiles or {profile}) do if p.spec_id==id then return p.spec_id,p.spec_name,'',0,p.role,p.class_token end end
  error('unconfigured specialization ID '..tostring(id))
 end)
 api('GetShapeshiftForm',function()return need(ctx.state.identity,'form','identity.')end)
 api('GetUnitChargedPowerPoints',function(u)return M.clone(need(unit(u),'charged_points'))end)
 api('GetRuneCooldown',function(index)local r=need(ctx.state.runes,index,'runes.');return r.start,r.duration,need(r,'ready','rune.')end)
 api('UnitStagger',function(u)return unit(u).stagger end)
 api('GetTime',function()return ctx.now end)
 api('PlayerVehicleHasComboPoints',function()return ctx.state.unit.vehicle_has_combo end)
 api('IsPlayerSpell',function(id)return need(ctx.state.known_spells,tostring(id),'known_spells.')end)
 env.C_SpellBook={IsSpellKnown=env.IsPlayerSpell,IsSpellKnownOrInSpellBook=env.IsPlayerSpell}
 env.C_UnitAuras={GetPlayerAuraBySpellID=function(id)
  local value=need(ctx.state.auras,tostring(id),'auras.');if value==false then return nil end;return M.clone(value)
 end}
 env.tContains=function(t,v)for _,x in ipairs(t)do if x==v then return true end end;return false end
 env.print=function(...) -- Diagnostics only, never mixed into machine-readable result.
  ctx.trace[#ctx.trace+1]={name='print',message=table.concat({...},' ')}
 end
 local Frame={}
 function Frame:RegisterEvent(e) self.events[e]=true end
 function Frame:RegisterUnitEvent(e,...)self.events[e]={...}end
 function Frame:UnregisterEvent(e)self.events[e]=nil end
 function Frame:UnregisterAllEvents()self.events={}end
 function Frame:IsEventRegistered(e)return self.events[e]~=nil end
 function Frame:SetScript(k,fn)assert(fn==nil or type(fn)=='function','script must be function');self.scripts[k]=fn end
 function Frame:GetScript(k)return self.scripts[k]end
 function Frame:HookScript(k,fn)local old=self.scripts[k];self.scripts[k]=function(...)if old then old(...)end;fn(...)end end
 function Frame:Show()self.shown=true end
 function Frame:Hide()self.shown=false end
 function Frame:SetShown(v)self.shown=not not v end
 function Frame:IsShown()return self.shown end
 function Frame:IsVisible()return self.shown end -- parent visibility is outside this minimal host
 function Frame:SetMinMaxValues(a,b)self.minimum=a;self.maximum=b end
 function Frame:GetMinMaxValues()return self.minimum,self.maximum end
 function Frame:SetValue(v)self.value=v end
 function Frame:GetValue()return self.value end
 function Frame:GetParent()return self.parent end
 function Frame:GetName()return self.name end
 function ctx.frame(kind,name,parent)
  assert(kind==nil or kind=='Frame' or kind=='StatusBar' or kind=='Button','unimplemented frame type '..tostring(kind))
  local f=setmetatable({events={},scripts={},shown=true,parent=parent,name=name}, {__index=Frame})
  ctx.frames[#ctx.frames+1]=f;return f
 end
 env.CreateFrame=function(kind,name,parent,template)
  assert(template==nil,'XML template not implemented: '..tostring(template));local f=ctx.frame(kind,name,parent)
  if name then assert(env[name]==nil,'duplicate named frame');env[name]=f end;return f
 end
 function ctx.emit(event,...)
  local args={...};local count=#ctx.frames
  for i=1,count do local f=ctx.frames[i];local reg=f.events[event];local allow=reg==true
   if type(reg)=='table' then for _,u in ipairs(reg)do if u==args[1]then allow=true end end end
   if allow and f.scripts.OnEvent then f.scripts.OnEvent(f,event,unpackValues(args))end
  end
 end
 local function schedule(delay,callback,period,iterations)
  assert(type(delay)=='number' and delay>=0,'bad timer delay');assert(type(callback)=='function','bad timer callback')
  ctx.sequence=ctx.sequence+1
  local t={deadline=ctx.now+delay,callback=callback,period=period,left=iterations,seq=ctx.sequence,cancelled=false}
  function t:Cancel()self.cancelled=true end
  function t:IsCancelled()return self.cancelled end
  ctx.timers[#ctx.timers+1]=t;return t
 end
 env.C_Timer={After=function(d,f)schedule(d,f)end,NewTimer=function(d,f)return schedule(d,f)end,
 NewTicker=function(d,f,n)assert(d>0,'ticker interval must be positive');return schedule(d,f,d,n)end}
 function ctx.advance(delta)
  assert(type(delta)=='number' and delta>=0,'time must not move backward')
  local target=ctx.now+delta;local steps=0
  while true do
   local best=nil
   for _,t in ipairs(ctx.timers)do if not t.cancelled and t.deadline<=target and (not best or t.deadline<best.deadline or t.deadline==best.deadline and t.seq<best.seq)then best=t end end
   if not best then break end
   steps=steps+1;assert(steps<=10000,'timer callback budget exceeded')
   ctx.now=best.deadline
   if not best.period then best.cancelled=true end
   best.callback(best)
   if best.period and not best.cancelled then
    if best.left then best.left=best.left-1;if best.left<=0 then best.cancelled=true end end
    best.deadline=best.deadline+best.period
   end
  end
  ctx.now=target
  local count=#ctx.frames
  for i=1,count do local f=ctx.frames[i];if f.shown and f.scripts.OnUpdate then f.scripts.OnUpdate(f,delta)end end
  -- Zero-delay work queued by OnUpdate waits for next advance(0); checkpoints call it explicitly.
 end
 function ctx.set_state(state)
  local t=need(state,'time');assert(t>=ctx.now,'state time is behind virtual clock')
  ctx.state=M.clone(state)
 end
 function ctx.load(path,...)
  local source=need(sources,path,'sources.');ctx.loaded[#ctx.loaded+1]=path
  return M.load(source,path,env,...)
 end
 function ctx.cleanup_status()
  local events,timers,updates=0,0,0
  for _,f in ipairs(ctx.frames)do for _ in pairs(f.events)do events=events+1 end;if f.scripts.OnUpdate then updates=updates+1 end end
  for _,t in ipairs(ctx.timers)do if not t.cancelled then timers=timers+1 end end
  return {event_subscriptions=events,live_timers=timers,update_scripts=updates}
 end
 function ctx.close()
  for _,f in ipairs(ctx.frames)do f:UnregisterAllEvents();f.scripts={}end
  for _,t in ipairs(ctx.timers)do t:Cancel()end
 end
 ctx.env=env;ctx.array=M.array;ctx.copy=M.clone;return ctx
end
return M
