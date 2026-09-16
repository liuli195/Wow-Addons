---@meta _
---Adds a roleset tag to this frame without removing existing ones.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_AddRoleset)
---@param roleset string
function Frame:AddRoleset(roleset) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_CreateVectorGraphics)
---@param name? string
---@param drawLayer? DrawLayer
---@param templateName? string
---@param subLevel? number
---@return any vectorGraphics
function Frame:CreateVectorGraphics(name, drawLayer, templateName, subLevel) end

---Returns the currently configured OnUpdate script execution mode.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_GetOnUpdateMode)
---@return Enum.OnUpdateMode onUpdateMode
function Frame:GetOnUpdateMode() end

---Returns the roleset tags assigned to this frame. Returns a list containing 'roleless' if none are assigned.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_GetRolesetNames)
---@return string[] rolesets
function Frame:GetRolesetNames() end

---Returns whether this frame is hidden because of its rolesets being filtered.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_IsRolesetFiltered)
---@return boolean isRolesetFiltered
function Frame:IsRolesetFiltered() end

---Removes a roleset tag from this frame.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_RemoveRoleset)
---@param roleset string
function Frame:RemoveRoleset(roleset) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_ResizeToBoundsRect)
function Frame:ResizeToBoundsRect() end

---Changes when OnUpdate scripts are executed for this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_SetOnUpdateMode)
---@param onUpdateMode Enum.OnUpdateMode
function Frame:SetOnUpdateMode(onUpdateMode) end

---Sets the roleset tags for this frame, used by the UI mode system to gate visibility. Supports comma-separated names to assign multiple rolesets. Pass nil to clear.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_Frame_SetRolesets)
---@param rolesetsString? string
function Frame:SetRolesets(rolesetsString) end
