---@meta _
C_PingSecure = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.ClearHitTestPingInfo)
function C_PingSecure.ClearHitTestPingInfo() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.CreateFrame)
function C_PingSecure.CreateFrame() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.DisplayError)
---@param error string
function C_PingSecure.DisplayError(error) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.GetTargetPingReceiver)
---@param mousePosX number
---@param mousePosY number
---@return ScriptRegion frame
function C_PingSecure.GetTargetPingReceiver(mousePosX, mousePosY) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SendHitTestPing)
---@param type? Enum.PingSubjectType
---@return SendPingResult result
function C_PingSecure.SendHitTestPing(type) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SendPlayerItemPing)
---@param itemID number
---@return SendPingResult result
function C_PingSecure.SendPlayerItemPing(itemID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SendPlayerSpellCategoryPing)
---@param spellCategoryID number
---@return SendPingResult result
function C_PingSecure.SendPlayerSpellCategoryPing(spellCategoryID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SendPlayerSpellPing)
---@param spellID number
---@return SendPingResult result
function C_PingSecure.SendPlayerSpellPing(spellID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SendUnitPing)
---@param target WOWGUID
---@param type? Enum.PingSubjectType
---@param isPlayerResource? boolean
---@return SendPingResult result
function C_PingSecure.SendUnitPing(target, type, isPlayerResource) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetHitTestPingTarget)
---@param mousePosX number
---@param mousePosY number
---@param forcePointPing? boolean
---@return Enum.PingSetTargetState state
function C_PingSecure.SetHitTestPingTarget(mousePosX, mousePosY, forcePointPing) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetHitTestTargetAndSendPing)
---@return SendPingResult result
function C_PingSecure.SetHitTestTargetAndSendPing() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPendingPingOffScreenCallback)
---@param cb PendingPingOffScreenCallback
function C_PingSecure.SetPendingPingOffScreenCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPingCooldownStartedCallback)
---@param cb PingCooldownStartedCallback
function C_PingSecure.SetPingCooldownStartedCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPingPinFrameAddedCallback)
---@param cb PingPinFrameAddedCallback
function C_PingSecure.SetPingPinFrameAddedCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPingPinFrameRemovedCallback)
---@param cb PingPinFrameRemovedCallback
function C_PingSecure.SetPingPinFrameRemovedCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPingPinFrameScreenClampStateUpdatedCallback)
---@param cb PingPinFrameScreenClampStateUpdatedCallback
function C_PingSecure.SetPingPinFrameScreenClampStateUpdatedCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetPingRadialWheelCreatedCallback)
---@param cb PingRadialWheelCreatedCallback
function C_PingSecure.SetPingRadialWheelCreatedCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetSendMacroPingCallback)
---@param cb SendMacroPingCallback
function C_PingSecure.SetSendMacroPingCallback(cb) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_PingSecure.SetTogglePingListenerCallback)
---@param cb TogglePingListenerCallback
function C_PingSecure.SetTogglePingListenerCallback(cb) end

---@class PingActionCooldownUIInfo
---@field durationMs number? Default = 0
---@field remainingMs number? Default = 0

---@class PingActionUIInfo
---@field spellID number? Default = 0
---@field itemID number? Default = 0
---@field textureFileDataID number? Default = 0
---@field cooldownInfo PingActionCooldownUIInfo?
---@field spellCategoryID number? Default = 0

---@class SendPingResult
---@field type Enum.PingSubjectType?
---@field result Enum.PingResult

---@alias PendingPingOffScreenCallback FunctionContainer|fun()

---@alias PingCooldownStartedCallback FunctionContainer|fun(info: PingCooldownInfo)

---@alias PingPinFrameAddedCallback FunctionContainer|fun(region: ScriptRegion, uiTextureKit: textureKit, isWorldPoint: boolean, actionInfo?: PingActionUIInfo)

---@alias PingPinFrameRemovedCallback FunctionContainer|fun(region: ScriptRegion)

---@alias PingPinFrameScreenClampStateUpdatedCallback FunctionContainer|fun(region: ScriptRegion, state: boolean)

---@alias PingRadialWheelCreatedCallback FunctionContainer|fun(region: ScriptRegion)

---@alias SendMacroPingCallback FunctionContainer|fun(macroInfo: PingMacroInfo)

---@alias TogglePingListenerCallback FunctionContainer|fun(down: boolean)
