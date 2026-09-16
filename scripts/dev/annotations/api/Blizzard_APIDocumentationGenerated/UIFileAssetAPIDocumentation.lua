---@meta _
C_UIFileAsset = {}

---Returns the numeric file ID associated with a file asset.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_UIFileAsset.GetFileID)
---@param asset FileAsset
---@return fileID? assetFileID
function C_UIFileAsset.GetFileID(asset) end

---Determines whether a file asset is known to the client, either as a shipped asset or a locally existing loose file.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_UIFileAsset.IsKnownFile)
---@param asset FileAsset
---@return boolean isValid
function C_UIFileAsset.IsKnownFile(asset) end

---Determines whether a file asset refers to a known loose (local) file.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_C_UIFileAsset.IsLooseFile)
---@param asset FileAsset
---@return boolean isLooseFile
function C_UIFileAsset.IsLooseFile(asset) end
