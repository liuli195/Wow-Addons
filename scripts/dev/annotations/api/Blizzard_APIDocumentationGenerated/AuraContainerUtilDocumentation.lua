---@meta _
C_AuraContainerUtil = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessAuraTooltipBackdropOptions)
---@param options AuraContainerTooltipBackdropOptions
---@return AuraContainerTooltipBackdropOptions result
function C_AuraContainerUtil.ProcessAuraTooltipBackdropOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessAuraTooltipNineSliceOptions)
---@param options AuraContainerTooltipNineSliceOptions
---@return AuraContainerTooltipNineSliceOptions result
function C_AuraContainerUtil.ProcessAuraTooltipNineSliceOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessAuraTooltipTextureSliceOptions)
---@param options AuraContainerTooltipTextureSliceOptions
---@return AuraContainerTooltipTextureSliceOptions result
function C_AuraContainerUtil.ProcessAuraTooltipTextureSliceOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonApplicationBarOptions)
---@param options CustomAuraButtonApplicationBarOptions
---@return CustomAuraButtonApplicationBarOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonApplicationBarOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonApplicationCountOptions)
---@param options? CustomAuraButtonApplicationCountOptions
---@return CustomAuraButtonApplicationCountOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonApplicationCountOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonDispelTypeTextOptions)
---@param options? CustomAuraButtonDispelTypeTextOptions
---@return CustomAuraButtonDispelTypeTextOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonDispelTypeTextOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonDispelTypeTextureOptions)
---@param options? CustomAuraButtonDispelTypeTextureOptions
---@return CustomAuraButtonDispelTypeTextureOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonDispelTypeTextureOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonDurationBarOptions)
---@param options? CustomAuraButtonDurationBarOptions
---@return CustomAuraButtonDurationBarOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonDurationBarOptions(options) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_AuraContainerUtil.ProcessCustomAuraButtonDurationTextOptions)
---@param options? CustomAuraButtonDurationTextOptions
---@return CustomAuraButtonDurationTextOptions result
function C_AuraContainerUtil.ProcessCustomAuraButtonDurationTextOptions(options) end

---@class AuraContainerTooltipAnchorOffsets
---@field left number? Default = 0
---@field right number? Default = 0
---@field top number? Default = 0
---@field bottom number? Default = 0

---@class AuraContainerTooltipBackdropInfo
---@field bgFile TextureAssetDisk?
---@field edgeFile TextureAssetDisk?
---@field edgeSize number?
---@field insets AuraContainerTooltipBackdropInsets?
---@field tile boolean?
---@field tileEdge boolean?
---@field tileSize number?

---@class AuraContainerTooltipBackdropInsets
---@field left number? Default = 0
---@field right number? Default = 0
---@field top number? Default = 0
---@field bottom number? Default = 0

---@class AuraContainerTooltipBackdropOptions
---@field backdropInfo AuraContainerTooltipBackdropInfo
---@field borderColor colorRGBA?
---@field centerColor colorRGBA?
---@field anchorOffsets AuraContainerTooltipAnchorOffsets?

---@class AuraContainerTooltipNineSliceOptions
---@field layoutName string
---@field borderColor colorRGBA?
---@field centerColor colorRGBA?
---@field anchorOffsets AuraContainerTooltipAnchorOffsets?

---@class AuraContainerTooltipTextureSliceOptions
---@field asset TextureAssetDisk
---@field sliceMargins UITextureSliceMargins?
---@field sliceMode Enum.UITextureSliceMode?
---@field color colorRGBA?
---@field anchorOffsets AuraContainerTooltipAnchorOffsets?
---@field drawLayer DrawLayer?
---@field drawLayerSublevel number? Default = 0

---@class CustomAuraButtonApplicationBarOptions
---@field maxApplications number
---@field interpolation Enum.StatusBarInterpolation?

---@class CustomAuraButtonApplicationCountOptions
---@field formatter any?

---@class CustomAuraButtonDispelTypeTextOptions
---@field showWhenHarmful boolean? Default = true
---@field showWhenHelpful boolean? Default = false
---@field showWithoutDispelType boolean? Default = false
---@field customDispelTextMap stringView[]?

---@class CustomAuraButtonDispelTypeTextureAsset
---@field asset TextureAssetDisk
---@field useAtlasSize boolean? Default = false
---@field texCoords CustomAuraButtonDispelTypeTextureTexCoords?

---@class CustomAuraButtonDispelTypeTextureOptions
---@field showAlways boolean? Default = false
---@field showWhenHarmful boolean? Default = true
---@field showWhenHelpful boolean? Default = false
---@field showWithoutDispelType boolean? Default = false
---@field stealableFilter Enum.CustomAuraButtonDispelTypeStealableFilter?
---@field style Enum.CustomAuraButtonDispelTypeTextureStyle? Default = BorderWithIcon
---@field customDispelAssetMap CustomAuraButtonDispelTypeTextureAsset[]?
---@field customDispelColorMap colorRGB[]?
---@field customDispelColorCurve LuaColorCurveObject?

---@class CustomAuraButtonDispelTypeTextureTexCoords
---@field left number? Default = 0
---@field right number? Default = 1
---@field top number? Default = 0
---@field bottom number? Default = 1

---@class CustomAuraButtonDurationBarOptions
---@field interpolation Enum.StatusBarInterpolation?
---@field direction Enum.StatusBarTimerDirection?

---@class CustomAuraButtonDurationTextOptions
---@field binding any?
---@field textFormatter any?
---@field textFormat DurationTextBindingFormatOptions?
---@field textColor DurationTextBindingColorOptions?
