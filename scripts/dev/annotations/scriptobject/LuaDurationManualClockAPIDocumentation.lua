---@meta _
---Resets the clock to a zero time value.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_LuaDurationManualClock_ResetTime)
function LuaDurationManualClock:ResetTime() end

---Rewinds the clock by a specified number of seconds.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_LuaDurationManualClock_RewindTime)
---@param delta DurationSeconds
function LuaDurationManualClock:RewindTime(delta) end

---Sets the current clock timestamp to a given value.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_LuaDurationManualClock_SetTime)
---@param time FrameTime
function LuaDurationManualClock:SetTime(time) end
