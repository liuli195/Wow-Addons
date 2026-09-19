return function(M,cases,profiles,adapterSource,sources,addonName)
 local results=M.array()
 for _,case in ipairs(cases)do
  local ctx=M.context(case.steps[1].state,case.profile,sources,profiles)
  local r={id=case.id,snapshots=M.array(),errors=M.array()};local adapter
  local ok,err=pcall(function()
   local factory=M.load(adapterSource,'adapter.lua',ctx.env)
   assert(type(factory)=='function','adapter must return function(ctx)')
   adapter=factory(ctx)
   assert(type(adapter)=='table' and type(adapter.start)=='function' and type(adapter.snapshot)=='function' and type(adapter.stop)=='function','adapter needs start, snapshot, stop functions')
   adapter.start(addonName)
  end)
  if not ok then r.errors[#r.errors+1]={stage='initialize',message=tostring(err)} end
  if ok then
   for index,step in ipairs(case.steps)do
    local good,why=pcall(function()
     ctx.set_state(step.state)
     ctx.advance(step.state.time-ctx.now)
     for _,event in ipairs(step.events)do ctx.emit(event[1],(table.unpack or unpack)(event,2))end
     ctx.advance(step.settle or 0);ctx.advance(0)
     local snapshot=adapter.snapshot()
     assert(type(snapshot)=='table','snapshot must return table')
     r.snapshots[index]=M.clone(snapshot)
    end)
    if not good then r.errors[#r.errors+1]={stage='step',step=index,message=tostring(why)};break end
   end
  end
  if adapter and type(adapter.stop)=='function'then
   local good,why=pcall(adapter.stop)
   if not good then r.errors[#r.errors+1]={stage='stop',message=tostring(why)}end
  end
  r.cleanup=ctx.cleanup_status()
  r.loaded=ctx.loaded
  if #r.errors>0 then
   r.trace_tail=M.array();for i=math.max(1,#ctx.trace-19),#ctx.trace do r.trace_tail[#r.trace_tail+1]=ctx.trace[i]end
  end
  ctx.close();results[#results+1]=r
 end
 return results
end
