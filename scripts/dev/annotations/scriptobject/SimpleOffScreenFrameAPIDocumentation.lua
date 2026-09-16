---@meta _
---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_ApplySnapshot)
---@param texture SimpleTexture
---@param snapshotID number
---@return boolean success
function OffScreenFrame:ApplySnapshot(texture, snapshotID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_Flush)
function OffScreenFrame:Flush() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_GetMaxSnapshots)
---@return number maxSnapshots
function OffScreenFrame:GetMaxSnapshots() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_IsSnapshotValid)
---@param snapshotID number
---@return boolean isValid
function OffScreenFrame:IsSnapshotValid(snapshotID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_SetMaxSnapshots)
---@param maxSnapshots number
function OffScreenFrame:SetMaxSnapshots(maxSnapshots) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_TakeSnapshot)
---@return number? snapshotID
function OffScreenFrame:TakeSnapshot() end

---Unavailable in public builds
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_TestPrintToFile)
---@param snapshotID number
---@param filename string
---@return boolean success
function OffScreenFrame:TestPrintToFile(snapshotID, filename) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_OffScreenFrame_UsesNPOT)
---@return boolean? usesNPOT
function OffScreenFrame:UsesNPOT() end
