---@meta _
---Returns true if the given number of seconds is within an appropriate range for approximated formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_CanApproximate)
---@param seconds any
---@return boolean canApproximate
function SecondsFormatter:CanApproximate(seconds) end

---Returns true if the formatter can promote values to higher interval bands.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_CanRoundUpIntervals)
---@return boolean canRound
function SecondsFormatter:CanRoundUpIntervals() end

---Returns true if the formatter should round the final unit up rather than down.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_CanRoundUpLastUnit)
---@return boolean canRound
function SecondsFormatter:CanRoundUpLastUnit() end

---Returns the unit count that a given number of seconds will use for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_EvaluateDesiredUnitCount)
---@param seconds any
---@return number count
function SecondsFormatter:EvaluateDesiredUnitCount(seconds) end

---Returns the maximum interval band that a given number of seconds will use for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_EvaluateMaxInterval)
---@param seconds any
---@return Enum.SecondsFormatterInterval interval
function SecondsFormatter:EvaluateMaxInterval(seconds) end

---Returns the minimum interval band that a given number of seconds will use for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_EvaluateMinInterval)
---@param seconds any
---@return Enum.SecondsFormatterInterval interval
function SecondsFormatter:EvaluateMinInterval(seconds) end

---Formats a number of seconds and returns the resulting string.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_Format)
---@param seconds any
---@param abbreviation? Enum.SecondsFormatterAbbreviation
---@return string formattedSeconds
function SecondsFormatter:Format(seconds, abbreviation) end

---Returns formatted string representing a zero second duration.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_FormatZero)
---@param abbreviation? Enum.SecondsFormatterAbbreviation
---@return string formattedSeconds
function SecondsFormatter:FormatZero(abbreviation) end

---Returns the threshold below which numeric values are formatted as approximated strings.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetApproximationSeconds)
---@return any approximationSeconds
function SecondsFormatter:GetApproximationSeconds() end

---Returns true if the formatter should lowercase all unit format strings.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetConvertToLower)
---@return boolean convert
function SecondsFormatter:GetConvertToLower() end

---Returns the default abbreviation mode used for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetDefaultAbbreviation)
---@return Enum.SecondsFormatterAbbreviation? abbreviation
function SecondsFormatter:GetDefaultAbbreviation() end

---Returns the desired unit count for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetDesiredUnitCount)
---@return number? count
function SecondsFormatter:GetDesiredUnitCount() end

---Returns the desired unit count curve for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetDesiredUnitCountCurve)
---@return LuaCurveObject? curve
function SecondsFormatter:GetDesiredUnitCountCurve() end

---Returns the maximum interval band permitted for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetMaxInterval)
---@return Enum.SecondsFormatterInterval? interval
function SecondsFormatter:GetMaxInterval() end

---Returns the maximum interval band curve permitted for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetMaxIntervalCurve)
---@return LuaCurveObject? curve
function SecondsFormatter:GetMaxIntervalCurve() end

---Returns the threshold below which a value will be formatted as a decimal number of seconds with one place for milliseconds (eg. '3.4')
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetMillisecondsThreshold)
---@return any threshold
function SecondsFormatter:GetMillisecondsThreshold() end

---Returns the minimum interval band permitted for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetMinInterval)
---@return Enum.SecondsFormatterInterval? interval
function SecondsFormatter:GetMinInterval() end

---Returns the minimum interval band curve permitted for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetMinIntervalCurve)
---@return LuaCurveObject? curve
function SecondsFormatter:GetMinIntervalCurve() end

---Returns how fractional seconds are rounded when not displaying milliseconds.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetRounding)
---@return Enum.SecondsFormatterRounding rounding
function SecondsFormatter:GetRounding() end

---Returns the whitespace stripping mode of the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_GetStripIntervalWhitespace)
---@return Enum.SecondsFormatterIntervalWhitespace strip
function SecondsFormatter:GetStripIntervalWhitespace() end

---Configures the formatter to render numeric values between zero and this value as approximated strings (eg. '< 1m').
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetApproximationSeconds)
---@param seconds any
function SecondsFormatter:SetApproximationSeconds(seconds) end

---Configures the formatter to promote intervals if values are large enough (eg. '60m' -> '1h').
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetCanRoundUpIntervals)
---@param canRound boolean
function SecondsFormatter:SetCanRoundUpIntervals(canRound) end

---Configures the formatter to round the last formatted unit up, rather than down.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetCanRoundUpLastUnit)
---@param canRound boolean
function SecondsFormatter:SetCanRoundUpLastUnit(canRound) end

---Configures the formatter to convert all interval format strings to lowercase.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetConvertToLower)
---@param convert boolean
function SecondsFormatter:SetConvertToLower(convert) end

---Sets the default abbreviation mode used for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetDefaultAbbreviation)
---@param abbreviation Enum.SecondsFormatterAbbreviation
function SecondsFormatter:SetDefaultAbbreviation(abbreviation) end

---Sets the desired unit count used for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetDesiredUnitCount)
---@param count number
function SecondsFormatter:SetDesiredUnitCount(count) end

---Sets the desired unit count used for formatting to a curve that will be evaluated with seconds values to produce a desired unit count.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetDesiredUnitCountCurve)
---@param curve LuaCurveObject
function SecondsFormatter:SetDesiredUnitCountCurve(curve) end

---Sets the maximum interval band used for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetMaxInterval)
---@param interval Enum.SecondsFormatterInterval
function SecondsFormatter:SetMaxInterval(interval) end

---Sets the maximum interval band used for formatting to a curve that will be evaluated with seconds values to produce a value matching a SecondsFormatterInterval enum member.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetMaxIntervalCurve)
---@param curve LuaCurveObject
function SecondsFormatter:SetMaxIntervalCurve(curve) end

---Sets the threshold below which a value will be formatted as a decimal number of seconds with one place for milliseconds (eg. '3.4')
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetMillisecondsThreshold)
---@param threshold any
function SecondsFormatter:SetMillisecondsThreshold(threshold) end

---Sets the minimum interval band used for formatting.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetMinInterval)
---@param interval Enum.SecondsFormatterInterval
function SecondsFormatter:SetMinInterval(interval) end

---Sets the minimum interval band used for formatting to a curve that will be evaluated with seconds values to produce a value matching a SecondsFormatterInterval enum member.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetMinIntervalCurve)
---@param curve LuaCurveObject
function SecondsFormatter:SetMinIntervalCurve(curve) end

---Sets how fractional seconds are rounded when not displaying milliseconds.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetRounding)
---@param rounding Enum.SecondsFormatterRounding
function SecondsFormatter:SetRounding(rounding) end

---Sets the whitespace stripping mode for the formatter.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_SecondsFormatter_SetStripIntervalWhitespace)
---@param strip Enum.SecondsFormatterIntervalWhitespace
function SecondsFormatter:SetStripIntervalWhitespace(strip) end
