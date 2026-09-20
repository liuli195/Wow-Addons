return function(ctx)
 local addon={};local output={}
 ctx.load('addon.lua','ExamplePollHUD',addon)
 local sink={health=function(v,m,c)output.health={value=v,maximum=m,connected=c}end,
 primary=function(t,k,v,m)output.primary={type=t,token=k,value=v,maximum=m}end,
 resource=function(r)output.resource=r end}
 return {start=function()addon.Start(sink)end,snapshot=function()return output end,stop=addon.Stop}
end
