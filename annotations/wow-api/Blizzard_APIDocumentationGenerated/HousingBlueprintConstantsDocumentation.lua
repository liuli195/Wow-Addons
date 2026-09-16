---@meta _
---@class HousingBlueprintBudgetEntry
---@field budgetType Enum.HousingBudgetType
---@field cost number
---@field max number?
---@field current number?

---@class HousingBlueprintBudgetInfo
---@field exteriorBudgets HousingBlueprintBudgetEntry[]
---@field interiorBudgets HousingBlueprintBudgetEntry[]

---@class HousingBlueprintCollection
---@field groups HousingBlueprintGroup[]

---@class HousingBlueprintContentEntry
---@field contentType Enum.HousingBlueprintContentType
---@field recordID number
---@field name string
---@field total number? Default = 0
---@field numMissing number? Default = 0
---@field invalid boolean? Default = false
---@field tooltip string?

---@class HousingBlueprintContentGroup
---@field contentType Enum.HousingBlueprintContentType
---@field entries HousingBlueprintContentEntry[]

---@class HousingBlueprintContentInfo
---@field shareCode string
---@field targetHouseGUID WOWGUID?
---@field budgetInfo HousingBlueprintBudgetInfo
---@field contentGroups HousingBlueprintContentGroup[]
---@field unmetRequirementFlags Enum.HousingBlueprintUnmetRequirementFlags
---@field blockingRequirementFlags Enum.HousingBlueprintUnmetRequirementFlags

---@class HousingBlueprintGroup
---@field name string
---@field entries HousingBlueprintInfo[]

---@class HousingBlueprintInfo
---@field blueprintID BigUInteger
---@field shareCode string
---@field name string
---@field blueprintType Enum.HousingBlueprintType
---@field creationTime time_t
---@field isAutoSave boolean
