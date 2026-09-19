-- Drives reviewed native leaves. Event checkpoint scheduling is a declared test contract,
-- not a recreation of the complete Blizzard XML dispatcher.
return function(M,nativeSource,cases,profiles)
 local results=M.array()
 for _,case in ipairs(cases)do
  local ctx=M.context(case.steps[1].state,case.profile,{},profiles)
  local e=ctx.env
  e.PowerBarColor={};e.UnitFrameHealPredictionBars_Update=function()end -- feature explicitly out of scope
  M.load(nativeSource,'reference/native.lua',e)
  local function bar()
   local b={unit='player',lockColor=true,unitFrame={frameType='Player',state='player'}}
   function b:SetMinMaxValues(a,z)self.minimum=a;self.maximum=z end
   function b:SetValue(v)self.value=v end
   function b:UpdateTextString()end
   function b:SetStatusBarColor()end
   function b:SetStatusBarTexture()end
   return b
  end
  local health,primary=bar(),bar()
  local output=M.array()
  for _,step in ipairs(case.steps)do
   ctx.set_state(step.state);ctx.now=step.state.time
   -- Inputs at a settled checkpoint. Native evaluation is deliberately stateless across samples;
   -- the addon under test remains alive across the whole sequence.
   e.UnitFrameHealthBar_Update(health,'player');e.UnitFrameManaBar_Update(primary,'player')
   local h={value=health.value,maximum=health.maximum,connected=not health.disconnected}
   local p={type=primary.powerType,token=primary.powerToken,value=primary.value,maximum=primary.maximum}
   local fam=step.state.resource_kind
   local out={kind=fam}
   local function holder(pt)
    local b={unit='player',powerType=pt,classResourceButtonTable={},usePooledResourceButtons=true}
    function b:GetUnit()return 'player'end
    function b:Layout()end
    b.classResourceButtonPool={active={}}
    function b.classResourceButtonPool:ReleaseAll()self.active={}end
    function b.classResourceButtonPool:Acquire()
     local node={};function node:Show()end
     function node:Update(full,charged)self.full=full;self.charged=charged end
     function node:SetActive(active)self.full=active end
     self.active[#self.active+1]=node;return node
    end
    function b.classResourceButtonPool:EnumerateActive()local i=0;return function()i=i+1;return self.active[i]end end
    return b
   end
   if fam=='none' then
    out={kind='none'} -- product contract: no selected secondary component, not a game-wide absence claim
   elseif fam=='combo' or fam=='druid_combo' or fam=='chi' or fam=='arcane' then
    local pt=({combo=4,druid_combo=4,chi=12,arcane=16})[fam];local b=holder(pt)
    local mix=({combo=e.RogueComboPointBarMixin,druid_combo=e.DruidComboPointBarMixin,chi=e.MonkPowerBar,arcane=e.MagePowerBar})[fam]
    b.UpdatePower=mix.UpdatePower
    if fam=='druid_combo' then assert(e.DruidComboPointBarMixin.ShouldShowBar(b),'druid combo requires energy state')end
    e.ClassResourceBarMixin.UpdateMaxPower(b)
    out.capacity=b.maxUsablePoints;out.nodes=M.array()
    for _,node in ipairs(b.classResourceButtonTable)do local n={full=node.full};if fam=='combo'then n.charged=node.charged end;out.nodes[#out.nodes+1]=n end
   elseif fam=='holy' then
    local b=holder(9);local maximum=e.UnitPowerMax('player',9);out.capacity=maximum;out.nodes=M.array()
    for i=1,maximum do local n={};function n:SetVisualState(v)self.state=v end;b['rune'..i]=n end
    function b:UpdateVisualState(v,power)self.holderState=v;self.lastPower=power end
    e.PaladinPowerBar.UpdatePower(b)
    for i=1,maximum do out.nodes[i]={full=b['rune'..i].state~=e.PaladinPowerBar.VisualState.Inactive}end
   elseif fam=='shards' then
    local b=holder(7);b.UnitPower=e.WarlockPowerBar.UnitPower
    local n={};function n:Update(amount)self.amount=amount end
    b.classResourceButtonPool.active={n};e.WarlockPowerBar.UpdatePower(b)
    out.capacity=e.UnitPowerMax('player',7);out.amount=n.amount
   elseif fam=='essence' then
    local b=holder(19);b.maxUsablePoints=e.UnitPowerMax('player',19);out.capacity=b.maxUsablePoints;out.nodes=M.array()
    for i=1,b.maxUsablePoints do
     local n={value={state='empty'}}
     n.EssenceFilling={FillingAnim={IsPlaying=function()return false end,GetProgress=function()return 0 end,Stop=function()end},CircleAnim={Stop=function()end}}
     n.EssenceFull={IsShown=function()return false end}
     function n:SetEssennceFull()self.value={state='full'}end
     function n:AnimOut()self.value={state='empty'}end
     function n:AnimIn(speed,portion)self.value={state='recharging',partial=portion,duration=5/speed}end
     b.classResourceButtonTable[i]=n
    end
    e.EssencePowerBar.UpdatePower(b)
    for i,n in ipairs(b.classResourceButtonTable)do out.nodes[i]=n.value end
   elseif fam=='runes' then
    out.nodes=M.array()
    for i=1,6 do
     local b={runeIndex=i}
     function b:ShowAsOnCooldown(start,duration)self.observed={state='cooldown',start=start,duration=duration}end
     function b:ShowAsEmpty()self.observed={state='empty'}end
     function b:ShowAsReady()self.observed={state='ready'}end
     e.RuneButtonMixin.UpdateState(b);out.nodes[i]=b.observed
    end
   elseif fam=='stagger' then
    local b={GetUnit=function()return 'player'end}
    out.value=e.MonkStaggerBarMixin.GetCurrentPower(b)
    local _,mx=e.MonkStaggerBarMixin.GetCurrentMinMaxPower(b);out.maximum=mx
   else error('no native reference for '..tostring(fam))end
   output[#output+1]={health=h,primary=p,resource=out}
  end
  results[#results+1]={id=case.id,snapshots=output}
 end
 return results
end
