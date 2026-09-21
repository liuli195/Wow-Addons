---@meta _
---Returns true if this nameplate permits changes to its hit-test points. Updates are normally blocked for tainted code during combat, except on the tick a unit is first assigned or when untainted code updates hit-test points on the same tick.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_CanChangeHitTestPoints)
---@return boolean canChangeHitTestPoints
function NamePlate:CanChangeHitTestPoints() end

---Clears the anchor points that determine where the mouse interacts with the nameplate.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_ClearAllHitTestPoints)
function NamePlate:ClearAllHitTestPoints() end

---Returns the anchor points that determine where the mouse interacts with the nameplate.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_GetHitTestPoints)
---@return AnchorBinding[] anchors
function NamePlate:GetHitTestPoints() end

---Sets the anchor points that determine where the mouse interacts with the nameplate to fully encompass the target region.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_SetAllHitTestPoints)
---@param relativeTo ScriptRegion
function NamePlate:SetAllHitTestPoints(relativeTo) end

---Sets the anchor points that determine where the mouse interacts with the nameplate.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_SetHitTestPoints)
---@param anchors AnchorBinding[]
function NamePlate:SetHitTestPoints(anchors) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_NamePlate_SetStackingBoundsFrame)
---@param frame SimpleFrame
function NamePlate:SetStackingBoundsFrame(frame) end
