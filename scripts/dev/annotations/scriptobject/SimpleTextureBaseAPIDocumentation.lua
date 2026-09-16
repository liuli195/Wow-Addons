---@meta _
---Disable radial progress bar rendering and restore standard texture display.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_ClearRadialProgressBar)
function TextureBase:ClearRadialProgressBar() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_ClearSVG)
function TextureBase:ClearSVG() end

---Returns the end angle offset of the radial progress bar as a normalized value (0 to 1).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_GetRadialProgressBarEndOffset)
---@return normalizedValue offset
function TextureBase:GetRadialProgressBarEndOffset() end

---Returns the feather/blur amount applied to the radial progress bar edge.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_GetRadialProgressBarFeather)
---@return normalizedValue feather
function TextureBase:GetRadialProgressBarFeather() end

---Returns the fill percentage of the radial progress bar (0 to 1).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_GetRadialProgressBarPercent)
---@return normalizedValue percent
function TextureBase:GetRadialProgressBarPercent() end

---Returns whether the radial progress bar fills in reverse (counterclockwise) direction.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_GetRadialProgressBarReverse)
---@return boolean reverse
function TextureBase:GetRadialProgressBarReverse() end

---Returns the start angle offset of the radial progress bar as a normalized value (0 to 1).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_GetRadialProgressBarStartOffset)
---@return normalizedValue offset
function TextureBase:GetRadialProgressBarStartOffset() end

---Sets the end angle offset of the radial progress bar as a normalized value (0 to 1).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetRadialProgressBarEndOffset)
---@param offset normalizedValue
function TextureBase:SetRadialProgressBarEndOffset(offset) end

---Sets the feather/blur amount applied to the radial progress bar edge (higher = more gradual falloff).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetRadialProgressBarFeather)
---@param feather normalizedValue
function TextureBase:SetRadialProgressBarFeather(feather) end

---Sets the fill percentage of the radial progress bar (0 to 1).
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetRadialProgressBarPercent)
---@param percent normalizedValue
function TextureBase:SetRadialProgressBarPercent(percent) end

---Sets whether the radial progress bar fills in reverse (counterclockwise) direction.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetRadialProgressBarReverse)
---@param reverse boolean
function TextureBase:SetRadialProgressBarReverse(reverse) end

---Sets the start angle offset of the radial progress bar as a normalized value (0 to 1), where 0 is at the bottom.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetRadialProgressBarStartOffset)
---@param offset normalizedValue
function TextureBase:SetRadialProgressBarStartOffset(offset) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_TextureBase_SetSVG)
---@param svgAsset FileAsset
---@return boolean success
function TextureBase:SetSVG(svgAsset) end
