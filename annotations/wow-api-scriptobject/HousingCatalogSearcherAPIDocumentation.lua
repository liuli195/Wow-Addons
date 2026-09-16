---@meta _
---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_IsBaseVariantOnlyActive)
---@return boolean isActive
function HousingCatalogSearcher:IsBaseVariantOnlyActive() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_IsStoredOnlyActive)
---@return boolean isActive
function HousingCatalogSearcher:IsStoredOnlyActive() end

---Search parameter; If true, only the base variant of each decor entry will be included
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_SetBaseVariantOnly)
---@param isActive boolean
function HousingCatalogSearcher:SetBaseVariantOnly(isActive) end

---Search parameter; If true, only entries that you have instances of available in storage will be included; This does not include entries that you own but have all been placed in a house; See IsCollectedActive for param that includes placed entries
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_SetStoredOnly)
---@param isActive boolean
function HousingCatalogSearcher:SetStoredOnly(isActive) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_ToggleBaseVariantOnly)
function HousingCatalogSearcher:ToggleBaseVariantOnly() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_HousingCatalogSearcher_ToggleStoredOnly)
function HousingCatalogSearcher:ToggleStoredOnly() end
