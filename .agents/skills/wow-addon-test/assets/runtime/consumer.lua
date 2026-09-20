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
     -- 顺序不能反：先用**上一检查点**的状态把时间推到位，再安装这一步的输入。
     -- 反过来的话，在上一检查点与这一步之间到期的计时器（例如 100.1 秒的刷新）
     -- 会读到 101 秒才该出现的输入——参考侧与实际侧观测的就不是同一个时刻了。
     ctx.advance(step.state.time-ctx.now)
     ctx.set_state(step.state)
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
