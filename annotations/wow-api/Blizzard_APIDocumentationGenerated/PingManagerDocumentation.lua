---@meta _
C_Ping = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.GetCooldownInfo)
---@return PingCooldownInfo cooldownInfo
function C_Ping.GetCooldownInfo() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.GetDefaultPingOptions)
---@return PingTypeInfo[] pingTypes
function C_Ping.GetDefaultPingOptions() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.GetTextureKitForType)
---@param type Enum.PingSubjectType
---@return textureKit uiTextureKitID
function C_Ping.GetTextureKitForType(type) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.IsPingSystemEnabled)
---@return boolean isEnabled
function C_Ping.IsPingSystemEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.SendMacroPing)
---@param macroInfo PingMacroInfo
function C_Ping.SendMacroPing(macroInfo) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Ping.TogglePingListener)
---@param down boolean
function C_Ping.TogglePingListener(down) end

---@class PingTypeInfo
---@field orderIndex number
---@field type Enum.PingSubjectType
---@field uiTextureKitID textureKit
