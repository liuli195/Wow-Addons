---@meta _
C_BattleNet = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.AreFriendTagsEnabled)
---@return boolean areFriendTagsEnabled
function C_BattleNet.AreFriendTagsEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.AreTitleFriendCustomNamesEnabled)
---@return boolean areTitleFriendCustomNamesEnabled
function C_BattleNet.AreTitleFriendCustomNamesEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.AreTitleFriendsEnabled)
---@return boolean areTitleFriendsEnabled
function C_BattleNet.AreTitleFriendsEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.BNCheckBattleTagInviteToRecentAlly)
---@param recentAllyGUID WOWGUID
function C_BattleNet.BNCheckBattleTagInviteToRecentAlly(recentAllyGUID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.BNCheckTitleFriendInviteToUnit)
---@param unit UnitToken
function C_BattleNet.BNCheckTitleFriendInviteToUnit(unit) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.CanToggleHighResTexturesWithoutClientReload)
---@return boolean canToggle
function C_BattleNet.CanToggleHighResTexturesWithoutClientReload() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetAccountInfoByGUID)
---@param guid WOWGUID
---@return BNetAccountInfo? accountInfo
function C_BattleNet.GetAccountInfoByGUID(guid) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetAccountInfoByID)
---@param id number
---@param wowAccountGUID? WOWGUID
---@return BNetAccountInfo? accountInfo
function C_BattleNet.GetAccountInfoByID(id, wowAccountGUID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetCustomTitleFriendName)
---@param id number
---@return string customName
function C_BattleNet.GetCustomTitleFriendName(id) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetFriendAccountInfo)
---@param friendIndex number
---@param wowAccountGUID? WOWGUID
---@return BNetAccountInfo? accountInfo
function C_BattleNet.GetFriendAccountInfo(friendIndex, wowAccountGUID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetFriendGameAccountInfo)
---@param friendIndex number
---@param accountIndex number
---@return BNetGameAccountInfo? gameAccountInfo
function C_BattleNet.GetFriendGameAccountInfo(friendIndex, accountIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetFriendInviteInfo)
---@param inviteIndex number
---@return BNetFriendInviteInfo? inviteInfo
function C_BattleNet.GetFriendInviteInfo(inviteIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetFriendNumGameAccounts)
---@param friendIndex number
---@return number numGameAccounts
function C_BattleNet.GetFriendNumGameAccounts(friendIndex) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetGameAccountInfoByGUID)
---@param guid WOWGUID
---@return BNetGameAccountInfo? gameAccountInfo
function C_BattleNet.GetGameAccountInfoByGUID(guid) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.GetGameAccountInfoByID)
---@param id number
---@return BNetGameAccountInfo? gameAccountInfo
function C_BattleNet.GetGameAccountInfoByID(id) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.InstallHighResTextures)
function C_BattleNet.InstallHighResTextures() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.InviteFriend)
---@param gameAccountID number
function C_BattleNet.InviteFriend(gameAccountID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.IsBattleNetFriendsListEnabled)
---@return boolean isBattleNetFriendsListEnabled
function C_BattleNet.IsBattleNetFriendsListEnabled() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.IsBattleNetFriendsListSupported)
---@return boolean isBattleNetFriendsListSupported
function C_BattleNet.IsBattleNetFriendsListSupported() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SearchFriends)
---@param searchInfo AuroraFriendsSearchInfo
---@return number[] friendsData
function C_BattleNet.SearchFriends(searchInfo) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SendGameData)
---@param gameAccountID number
---@param prefix stringView
---@param data stringView
---@return Enum.SendAddonMessageResult result
function C_BattleNet.SendGameData(gameAccountID, prefix, data) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SendTitleFriendInviteByName)
---@param name string
function C_BattleNet.SendTitleFriendInviteByName(name) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SendVerifiedBattleNetFriendInvite)
function C_BattleNet.SendVerifiedBattleNetFriendInvite() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SendWhisper)
---@param bnetAccountID number
---@param text stringView
---@return boolean success
function C_BattleNet.SendWhisper(bnetAccountID, text) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetAFK)
---@param isAFK? boolean Default = true
function C_BattleNet.SetAFK(isAFK) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetAppearOffline)
---@param isAppearOffline? boolean Default = true
function C_BattleNet.SetAppearOffline(isAppearOffline) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetCustomMessage)
---@param text string
---@return boolean success
function C_BattleNet.SetCustomMessage(text) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetCustomTitleFriendName)
---@param id number
---@param customName string
function C_BattleNet.SetCustomTitleFriendName(id, customName) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetDND)
---@param isDND? boolean Default = true
function C_BattleNet.SetDND(isDND) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_BattleNet.SetFriendTags)
---@param id number
---@param friendTags Enum.BattleNetFriendTag[]
function C_BattleNet.SetFriendTags(id, friendTags) end

---@class AuroraFriendsSearchInfo
---@field searchText string
---@field isOnline boolean
---@field isOffline boolean
---@field isDND boolean
---@field isAFK boolean
---@field isInQueue boolean
---@field isAvailableForQueue boolean
---@field tags Enum.BattleNetFriendTag[]

---@class BNetAccountInfo
---@field bnetAccountID number
---@field accountName string
---@field battleTag string
---@field isFriend boolean
---@field isBattleTagFriend boolean
---@field friendLevel Enum.BattleNetFriendLevel?
---@field lastOnlineTime number
---@field isAFK boolean
---@field isDND boolean
---@field isFavorite boolean
---@field friendTags Enum.BattleNetFriendTag[]
---@field appearOffline boolean
---@field customMessage string
---@field customMessageTime number
---@field note string
---@field rafLinkType Enum.RafLinkType
---@field gameAccountInfo BNetGameAccountInfo

---@class BNetFriendInviteInfo
---@field inviteID number
---@field accountName any
---@field creationTimestamp number
---@field friendLevel Enum.BattleNetFriendLevel?

---@class BNetGameAccountInfo
---@field gameAccountID number
---@field clientProgram string
---@field isOnline boolean
---@field isGameBusy boolean
---@field isGameAFK boolean
---@field isAppearOffline boolean
---@field wowProjectID number?
---@field characterName string?
---@field realmName string?
---@field realmDisplayName string?
---@field realmID number?
---@field factionName string?
---@field raceName string?
---@field classID number?
---@field className string?
---@field classFilename string?
---@field areaName string?
---@field characterLevel number?
---@field richPresence string?
---@field playerGuid WOWGUID?
---@field canSummon boolean
---@field hasFocus boolean
---@field regionID number
---@field isInCurrentRegion boolean
---@field timerunningSeasonID number?
