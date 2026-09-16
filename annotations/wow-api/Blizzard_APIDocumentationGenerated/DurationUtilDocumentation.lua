---@meta _
C_DurationUtil = {}

---Creates a zero duration container that can represent a time span.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_DurationUtil.CreateDuration)
---@return LuaDurationObject duration
function C_DurationUtil.CreateDuration() end

---Creates a duration text binding, which automatically updates a font string with formatted text derived from a duration object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_DurationUtil.CreateDurationTextBinding)
---@return any binding
function C_DurationUtil.CreateDurationTextBinding() end

---Creates a manually driven time source for use with duration objects.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_DurationUtil.CreateManualClock)
---@return any clock
function C_DurationUtil.CreateManualClock() end
