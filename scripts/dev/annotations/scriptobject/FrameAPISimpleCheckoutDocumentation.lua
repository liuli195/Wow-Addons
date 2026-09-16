---@meta _
---[Documentation](https://warcraft.wiki.gg/wiki/API_SimpleCheckout_CancelOpenCheckout)
function SimpleCheckout:CancelOpenCheckout() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_SimpleCheckout_CloseCheckout)
function SimpleCheckout:CloseCheckout() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_SimpleCheckout_CopyExternalLink)
function SimpleCheckout:CopyExternalLink() end

---[Documentation](https://warcraft.wiki.gg/wiki/API_SimpleCheckout_OpenCheckout)
---@param checkoutID number
---@return boolean wasOpened
function SimpleCheckout:OpenCheckout(checkoutID) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_SimpleCheckout_OpenExternalLink)
function SimpleCheckout:OpenExternalLink() end
