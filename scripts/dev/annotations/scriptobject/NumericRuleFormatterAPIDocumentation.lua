---@meta _
---Adds a new breakpoint to the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NumericRuleFormatter_AddBreakpoint)
---@param breakpoint NumericRuleFormatBreakpoint
function NumericRuleFormatter:AddBreakpoint(breakpoint) end

---Removes all configured breakpoints from the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NumericRuleFormatter_ClearBreakpoints)
function NumericRuleFormatter:ClearBreakpoints() end

---Returns a list of all configured breakpoints on this formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NumericRuleFormatter_GetBreakpoints)
---@return NumericRuleFormatBreakpoint[] breakpoints
function NumericRuleFormatter:GetBreakpoints() end

---Replaces all breakpoints on the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NumericRuleFormatter_SetBreakpoints)
---@param breakpoints NumericRuleFormatBreakpoint[]
function NumericRuleFormatter:SetBreakpoints(breakpoints) end
