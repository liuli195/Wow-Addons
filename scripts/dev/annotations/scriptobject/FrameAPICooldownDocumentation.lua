---@meta _
---Returns the threshold below which cooldown numbers are displayed as an abbreviated form without a unit suffix (eg. '1:31').
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Cooldown_GetCountdownAbbrevThreshold)
---@return any seconds
function Cooldown:GetCountdownAbbrevThreshold() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_Cooldown_GetCountdownFormatter)
---@return any? formatter
function Cooldown:GetCountdownFormatter() end

---Returns the threshold below which cooldown numbers are displayed as a decimal value with one place for milliseconds (eg. '8.7').
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Cooldown_GetCountdownMillisecondsThreshold)
---@return any seconds
function Cooldown:GetCountdownMillisecondsThreshold() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_Cooldown_SetCountdownFormatter)
---@param formatter? any
function Cooldown:SetCountdownFormatter(formatter) end

---Sets the threshold below which cooldown numbers are displayed as a decimal value with one place for milliseconds (eg. '8.7').
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Cooldown_SetCountdownMillisecondsThreshold)
---@param seconds any
function Cooldown:SetCountdownMillisecondsThreshold(seconds) end
