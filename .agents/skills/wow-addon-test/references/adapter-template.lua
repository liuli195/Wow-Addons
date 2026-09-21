-- AI must read the real project's source before replacing this template.
-- This file intentionally fails: an unconnected addon must never be reported as passing.
return function(ctx)
 error('ADAPTER_NOT_IMPLEMENTED: 读取真实生产代码，填写 files，再实现薄适配。不可复制参考算法。')
 -- Example shape (replace filenames and public entry points with verified real ones):
 -- local ns = {}
 -- ctx.load('Core.lua', 'YourAddon', ns)
 -- return {
 --   start = function() ns.Start() end,
 --   snapshot = function() return ns.GetExistingModel() end,
 --   stop = function() ns.Stop() end,
 -- }
end
