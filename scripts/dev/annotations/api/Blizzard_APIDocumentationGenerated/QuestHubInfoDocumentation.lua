---@meta _
C_QuestHub = {}

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_QuestHub.IsAreaPOICurrentlyRelatedToHub)
---@param areaPoiID number
---@param hubAreaPoiID number
---@return boolean isRelated
function C_QuestHub.IsAreaPOICurrentlyRelatedToHub(areaPoiID, hubAreaPoiID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_C_QuestHub.IsQuestCurrentlyRelatedToHub)
---@param questID number
---@param hubAreaPoiID number
---@return boolean isRelated
function C_QuestHub.IsQuestCurrentlyRelatedToHub(questID, hubAreaPoiID) end
