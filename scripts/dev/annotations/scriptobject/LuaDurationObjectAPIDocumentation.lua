---@meta _
---Calculates the total duration in seconds and evaluates it against a supplied curve.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_EvaluateTotalDuration)
---@param curve LuaCurveObjectBase
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return LuaCurveEvaluatedResult result
function DurationObject:EvaluateTotalDuration(curve, modifier) end

---Formats the elapsed duration of this object to a string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_FormatElapsedDuration)
---@param formatter any
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return string formatted
function DurationObject:FormatElapsedDuration(formatter, modifier) end

---Formats the remaining duration of this object to a string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_FormatRemainingDuration)
---@param formatter any
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return string formatted
function DurationObject:FormatRemainingDuration(formatter, modifier) end

---Formats the total duration of this object to a string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_FormatTotalDuration)
---@param formatter any
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return string formatted
function DurationObject:FormatTotalDuration(formatter, modifier) end

---Returns the clock source used by this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_GetClock)
---@return any? clock
function DurationObject:GetClock() end

---Returns true once the duration has reached its end time.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_HasExpired)
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return boolean hasExpired
function DurationObject:HasExpired(modifier) end

---Returns true once the duration has reached its start time.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_HasStarted)
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return boolean hasStarted
function DurationObject:HasStarted(modifier) end

---Returns true while the duration is at or after its start time and before its end time.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_IsActive)
---@param modifier? Enum.DurationTimeModifier Default = RealTime
---@return boolean isActive
function DurationObject:IsActive(modifier) end

---Configures the clock source used by this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationObject_SetClock)
---@param clock? any
function DurationObject:SetClock(clock) end
