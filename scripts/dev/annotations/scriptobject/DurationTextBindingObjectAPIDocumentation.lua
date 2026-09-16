---@meta _
---Returns true if this binding has enough configuration to produce formatted text.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_CanFormatText)
---@return boolean canFormatText
function DurationTextBindingObject:CanFormatText() end

---Returns true if this binding has enough configuration to update its font string with formatted text.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_CanUpdateFontString)
---@return boolean canUpdateText
function DurationTextBindingObject:CanUpdateFontString() end

---Clears the text color curve used by this binding.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_ClearTextColorCurve)
function DurationTextBindingObject:ClearTextColorCurve() end

---Returns the text shown when the duration has fully expired.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetExpiredText)
---@return string? text
function DurationTextBindingObject:GetExpiredText() end

---Returns the text that would currently be assigned to the configured font string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetFormattedText)
---@return string text
function DurationTextBindingObject:GetFormattedText() end

---Returns the text color that would currently be assigned to the configured font string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetFormattedTextColor)
---@return colorRGBA color
function DurationTextBindingObject:GetFormattedTextColor() end

---Returns the text color curve used by this binding.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetTextColorCurve)
---@return LuaColorCurveObject curve
---@return Enum.DurationTextBindingProperty property
function DurationTextBindingObject:GetTextColorCurve() end

---Returns the time modifier used when sampling duration values for this binding.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetTimeModifier)
---@return Enum.DurationTimeModifier modifier
function DurationTextBindingObject:GetTimeModifier() end

---Returns the minimum number of seconds between automatic text updates. A value of zero updates every game tick.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetUpdateInterval)
---@return number updateInterval
function DurationTextBindingObject:GetUpdateInterval() end

---Returns the text shown when the duration is not configured, or represents a zero-duration time span.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_GetZeroDurationText)
---@return string? text
function DurationTextBindingObject:GetZeroDurationText() end

---Configures the text shown when the duration has fully expired.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetExpiredText)
---@param text? string
function DurationTextBindingObject:SetExpiredText(text) end

---Configures the text format used by this duration text binding to display the remaining duration using the supplied formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetFormatter)
---@param formatter any
function DurationTextBindingObject:SetFormatter(formatter) end

---Configures this duration text binding to adjust fontstring text color by evaluating a duration property through a curve.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetTextColorCurve)
---@param curve LuaColorCurveObject
---@param property Enum.DurationTextBindingProperty
function DurationTextBindingObject:SetTextColorCurve(curve, property) end

---Configures the text format used by this duration text binding. The format string may contain '{}' placeholders, each of which is substituted by the corresponding component in the supplied array.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetTextFormat)
---@param formatString stringView
---@param components DurationTextBindingFormatComponent[]
function DurationTextBindingObject:SetTextFormat(formatString, components) end

---Configures the time modifier used when sampling duration values for this binding.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetTimeModifier)
---@param modifier Enum.DurationTimeModifier
function DurationTextBindingObject:SetTimeModifier(modifier) end

---Configures the minimum number of seconds between automatic text updates. A value of zero updates every game tick.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetUpdateInterval)
---@param updateInterval number
function DurationTextBindingObject:SetUpdateInterval(updateInterval) end

---Configures the text shown when the duration is not configured, or represents a zero-duration time span.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_SetZeroDurationText)
---@param text? string
function DurationTextBindingObject:SetZeroDurationText(text) end

---Immediately updates the configured font string from the current duration state.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_DurationTextBindingObject_UpdateFontString)
function DurationTextBindingObject:UpdateFontString() end
