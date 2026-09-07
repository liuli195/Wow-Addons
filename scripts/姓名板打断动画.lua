function(allstates, event, ...)
    if event == "COMBAT_LOG_EVENT_UNFILTERED" then
      local _, subevent, _, _, sourceName, _, _, destGUID, _, _, _ = CombatLogGetCurrentEventInfo()
      if subevent == "SPELL_INTERRUPT" then
        for i = 1, 40 do
          local unitID = "nameplate" .. i
          if UnitExists(unitID) then
            local unitGUID = UnitGUID(unitID)
            if unitGUID == destGUID and UnitCanAttack("player", unitID) then
                allstates[unitID] = {
                    progressType = 'static',
                    show = true,
                    changed = true,
                    sourceName = sourceName,
                    value = 100,
                    total = 100,
                    unit = unitID,
                    autoHide = true,
                    duration = 1,
                    expirationTime = GetTime() + 1,
                }
                return true
            end
          end
        end
      end
    end
    return false
end

CLEU:SPELL_INTERRUPT