---@meta _
---Adds a new breakpoint to the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_AbbreviatedNumberFormatter_AddBreakpoint)
---@param breakpoint NumberAbbreviationBreakpoint
function AbbreviatedNumberFormatter:AddBreakpoint(breakpoint) end

---Removes all configured breakpoints from the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_AbbreviatedNumberFormatter_ClearBreakpoints)
function AbbreviatedNumberFormatter:ClearBreakpoints() end

---Returns a list of all configured breakpoints on this formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_AbbreviatedNumberFormatter_GetBreakpoints)
---@return NumberAbbreviationBreakpoint[] breakpoints
function AbbreviatedNumberFormatter:GetBreakpoints() end

---Removes all configured breakpoints from the formatter and replaces them with appropriate defaults for the client locale.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_AbbreviatedNumberFormatter_ResetBreakpoints)
function AbbreviatedNumberFormatter:ResetBreakpoints() end

---Replaces all breakpoints on the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_AbbreviatedNumberFormatter_SetBreakpoints)
---@param breakpoints NumberAbbreviationBreakpoint[]
function AbbreviatedNumberFormatter:SetBreakpoints(breakpoints) end
