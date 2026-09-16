---@meta _
---Adds access restrictions to a script object, preventing it from being used in API calls when enforced.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_AddAccessRestrictions)
---@param restrictions Enum.ScriptObjectAccessRestriction
function FrameScriptObject:AddAccessRestrictions(restrictions) end

---Adds forbidden aspects to a script object, restricting access to various functionalities such as script bindings.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_AddForbiddenAspects)
---@param aspects Enum.ForbiddenAspect
function FrameScriptObject:AddForbiddenAspects(aspects) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_AddSecretAspect)
---@param aspect Enum.SecretAspect
function FrameScriptObject:AddSecretAspect(aspect) end

---Returns whether the current Lua execution context has permission to access this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_CanBeAccessedInContext)
---@return boolean canAccess
function FrameScriptObject:CanBeAccessedInContext() end

---Returns the mask of all access restrictions applied to this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_GetAccessRestrictions)
---@return Enum.ScriptObjectAccessRestriction restrictions
function FrameScriptObject:GetAccessRestrictions() end

---Returns the mask of all forbidden aspects applied to this object.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_GetForbiddenAspects)
---@return Enum.ForbiddenAspect aspects
function FrameScriptObject:GetForbiddenAspects() end

---Returns the mask of all forbidden aspects applied to this object that can propagate to others.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_GetInheritableForbiddenAspects)
---@param path Enum.ScriptObjectPropagationPath
---@return Enum.ForbiddenAspect aspects
function FrameScriptObject:GetInheritableForbiddenAspects(path) end

---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_GetObjectTable)
---@return FrameScriptObject objectTable
function FrameScriptObject:GetObjectTable() end

---Returns whether this object has any access constraints that may limit access from some Lua execution contexts.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_HasAccessConstraints)
---@return boolean hasAccessConstraints
function FrameScriptObject:HasAccessConstraints() end

---Returns true if this object has any of the supplied access restrictions applied.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_HasAnyAccessRestrictions)
---@param restrictions? Enum.ScriptObjectAccessRestriction
---@return boolean hasAnyAccessRestriction
function FrameScriptObject:HasAnyAccessRestrictions(restrictions) end

---Returns true if this object has any of the supplied forbidden aspects added.
---
---[Documentation](https://warcraft.wiki.gg/wiki/API_FrameScriptObject_HasAnyForbiddenAspects)
---@param aspects? Enum.ForbiddenAspect
---@return boolean hasAnyForbiddenAspect
function FrameScriptObject:HasAnyForbiddenAspects(aspects) end
