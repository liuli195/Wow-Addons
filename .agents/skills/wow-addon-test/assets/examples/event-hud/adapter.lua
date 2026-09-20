return function(ctx)
 local addon={}
 ctx.load('addon.lua','ExampleEventHUD',addon)
 return {start=addon.Start,snapshot=addon.Snapshot,stop=addon.Stop}
end
