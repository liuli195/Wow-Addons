---@meta _
C_Discord = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.Authorize)
function C_Discord.Authorize() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetDiscordChannelName)
---@param serverIndex number
---@param channelIndex number
---@return string name
function C_Discord.GetDiscordChannelName(serverIndex, channelIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetDiscordUserID)
---@return any userID
function C_Discord.GetDiscordUserID() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetDiscordUserName)
---@param userID any
---@return any userName
function C_Discord.GetDiscordUserName(userID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetDisplayNameType)
---@return Enum.DiscordDisplayNameType type
function C_Discord.GetDisplayNameType() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetGuildLinkStatus)
---@return boolean isFullyLinked
---@return string linkedChannelName
---@return string linkedServerName
function C_Discord.GetGuildLinkStatus() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetNumDiscordChannels)
---@param serverIndex number
---@return number count
---@return boolean valid
function C_Discord.GetNumDiscordChannels(serverIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetNumDiscordServers)
---@return number count
function C_Discord.GetNumDiscordServers() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetServerLinkableChannels)
---@param index number
function C_Discord.GetServerLinkableChannels(index) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GetServerName)
---@param index number
---@return string name
function C_Discord.GetServerName(index) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GuildLink)
---@param serverIndex number
---@param channelIndex number
function C_Discord.GuildLink(serverIndex, channelIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.GuildUnlink)
function C_Discord.GuildUnlink() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.IsEnabled)
---@return boolean enabled
function C_Discord.IsEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.IsGuildChannelLinked)
---@return boolean isLinked
function C_Discord.IsGuildChannelLinked() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.IsGuildSettingSet)
---@param setting Enum.DiscordGuildSettings
---@return boolean isSet
function C_Discord.IsGuildSettingSet(setting) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.IsUserOAuthed)
---@return boolean hasOAuth
function C_Discord.IsUserOAuthed() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.RefreshAuth)
function C_Discord.RefreshAuth() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.SetGuildSetting)
---@param setting Enum.DiscordGuildSettings
---@param set boolean
function C_Discord.SetGuildSetting(setting, set) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.UpdateDiscordServers)
function C_Discord.UpdateDiscordServers() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_Discord.UpdateGuildLobby)
function C_Discord.UpdateGuildLobby() end
