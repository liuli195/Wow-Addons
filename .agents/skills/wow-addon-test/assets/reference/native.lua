-- Reviewed original method excerpts, not a replacement implementation.
-- Upstream: Gethe/wow-ui-source @ 78282522143e25c3540583734fd192c3d69be910.
-- See sources.json for each method's original file and observation boundary.
-- Tables below replace only file-level mixin declarations. Appearance is not tested.
ClassResourceBarMixin = {};
RogueComboPointBarMixin = {};
DruidComboPointBarMixin = {};
MagePowerBar = {};
MonkPowerBar = {};
WarlockPowerBar = {};
PaladinPowerBar = {};
PaladinPowerBar.VisualState = { Inactive = 1, Active = 2, SpellReady = 3 };
HOLY_POWER_SPELL_READY = 3;
EssencePowerBar = {};
local FillingAnimationTime = 5.0;
RuneButtonMixin = {};
RuneButtonMixin.VisualState = { Empty = 1, OnCooldown = 2, CooldownEnding = 3, Ready = 4 };
MonkStaggerBarMixin = {};

-- BEGIN UnitFrameHealthBar_Update
function UnitFrameHealthBar_Update(statusbar, unit)
	if ( not statusbar or statusbar.lockValues ) then
		return;
	end

	if ( unit == statusbar.unit ) then
		local maxValue = UnitHealthMax(unit);

		-- Safety check to make sure we never get an empty bar.
		statusbar.forceHideText = false;
		if ( maxValue == 0 ) then
			maxValue = 1;
			statusbar.forceHideText = true;
		end

		statusbar:SetMinMaxValues(0, maxValue);

		if statusbar.AnimatedLossBar then
			statusbar.AnimatedLossBar:UpdateHealthMinMax();
		end

		statusbar.disconnected = not UnitIsConnected(unit);
		if ( statusbar.disconnected ) then
			if ( not statusbar.lockColor ) then
				statusbar:SetStatusBarColor(0.5, 0.5, 0.5);
			end
			statusbar:SetValue(maxValue);
			statusbar.currValue = maxValue;
		else
			local currValue = UnitHealth(unit);
			if ( not statusbar.lockColor ) then
				statusbar:SetStatusBarColor(0.0, 1.0, 0.0);
			end
			statusbar:SetValue(currValue);
			statusbar.currValue = currValue;
		end
	end
	statusbar:UpdateTextString();
	UnitFrameHealPredictionBars_Update(statusbar.unitFrame);
end
-- END UnitFrameHealthBar_Update

-- BEGIN UnitFrameManaBar_UpdateType
function UnitFrameManaBar_UpdateType(manaBar)
	if (not manaBar) then
		return;
	end

	if(not manaBar.unitFrame.frameType) then
		UnitFrameManaBar_UpdateTypeOld(manaBar);
		return;
	end

	local powerType, powerToken, altR, altG, altB = UnitPowerType(manaBar.unit);
	local info = PowerBarColor[powerToken];

	-- Check for override power info, use that if any exist (used for cases where units want to use the same power type as other cases, but with slightly different visuals).
	local overrideInfo = manaBar.overrideInfo;
	if overrideInfo then
		info = overrideInfo;
	end

	local portraitType = manaBar.unitFrame.portrait and "PortraitOn" or "PortraitOff";

	-- Some mana bar art is different for a frame depending on if they are in a vehicle or not.
	-- Special case for the party frame.
	local vehicleText = "";
	if(manaBar.unitFrame.frameType == "Party" and manaBar.unitFrame.state == "vehicle") then
		vehicleText = "-Vehicle";
	end

	if (info) then
		local manaBarAtlas;
		if (manaBar.unitFrame.frameType and info.atlasElementName) then
			-- Some player spec/classes use a third "alternate" bar, requiring their primary bar to use slightly different bar art
			-- Very few bars have this ClassResource variant so far, hence the hasClassResourceVariant check which for now is much cheaper than constant GetAtlasInfo nil checks.
			local classResourceText = "";
			if(manaBar.unitFrame.frameType == "Player" and manaBar.unitFrame.state == "player" and manaBar.unitFrame.activeAlternatePowerBar and info.hasClassResourceVariant) then
				classResourceText = "-ClassResource";
			end

			local manaBarTexture = "UI-HUD-UnitFrame-"..manaBar.unitFrame.frameType.."-"..portraitType..vehicleText..classResourceText.."-Bar-"..info.atlasElementName;
			manaBar:SetStatusBarTexture(manaBarTexture);
			manaBarAtlas = manaBarTexture;
		elseif (info.atlas) then
			manaBar:SetStatusBarTexture(info.atlas);
			manaBarAtlas = info.atlas;
		end

		manaBar:SetStatusBarColor(1, 1, 1);

		local playerDeadOrGhost = (manaBar.unit == "player" and (UnitIsDead("player") or UnitIsGhost("player")));
		local statusBarTexture = manaBar:GetStatusBarTexture();
		statusBarTexture:SetDesaturated(playerDeadOrGhost);
		statusBarTexture:SetAlpha(playerDeadOrGhost and 0.5 or 1);

		if (manaBar.FeedbackFrame) then
			-- Ensure feedback frame gets the atlas we actually used rather than having it duplicate the same handling
			manaBar.FeedbackFrame:Initialize({atlas = manaBarAtlas}, manaBar.unit, powerType);
		end

		if (manaBar.FullPowerFrame) then
			manaBar.FullPowerFrame:Initialize(info.fullPowerAnim);
		end

		if (manaBar.Spark) then
			manaBar.Spark:SetVisuals(info.spark);
		end
	else
		-- If we cannot find the info for what the mana bar should be, default either to Mana or Mana-Status (colorable).
		local manaBarTexture = "UI-HUD-UnitFrame-"..manaBar.unitFrame.frameType.."-"..portraitType..vehicleText.."-Bar-Mana";
		manaBar:SetStatusBarColor(1, 1, 1);

		if (altR) then
			-- This steps around manaBar.lockColor as it is initially setting things.
			manaBarTexture = "UI-HUD-UnitFrame-"..manaBar.unitFrame.frameType.."-"..portraitType..vehicleText.."-Bar-Mana-Status";
			manaBar:SetStatusBarColor(altR, altG, altB);
		end

		manaBar:SetStatusBarTexture(manaBarTexture);
	end

	if (manaBar.powerType ~= powerType) then
		manaBar.powerType = powerType;
		manaBar.powerToken = powerToken;

		if (manaBar.FeedbackFrame) then
			manaBar.FeedbackFrame:StopFeedbackAnim();
		end

		if (manaBar.FullPowerFrame) then
			manaBar.FullPowerFrame:RemoveAnims();
		end

		manaBar.currValue = UnitPower("player", powerType);
		if (manaBar.unitFrame.myManaCostPredictionBar) then
			manaBar.unitFrame.myManaCostPredictionBar:Hide();

			local predictionColor;
			if (info and info.predictionColor) then
				predictionColor = info.predictionColor;
			else
				-- No prediction color set, default to mana prediction color
				predictionColor = POWERBAR_PREDICTION_COLOR_MANA;
			end
			manaBar.unitFrame.myManaCostPredictionBar:SetFillColor(predictionColor);
		end

		manaBar.unitFrame.predictedPowerCost = 0;
	end

	-- Update the manabar text
	manaBar:UpdateTextString();
end
-- END UnitFrameManaBar_UpdateType

-- BEGIN UnitFrameManaBar_Update
function UnitFrameManaBar_Update(statusbar, unit)
	if ( not statusbar or statusbar.lockValues ) then
		return;
	end

	if ( unit == statusbar.unit ) then
		-- be sure to update the power type before grabbing the max power!
		UnitFrameManaBar_UpdateType(statusbar);

		local maxValue = UnitPowerMax(unit, statusbar.powerType);

		statusbar:SetMinMaxValues(0, maxValue);

		statusbar.disconnected = not UnitIsConnected(unit);
		if ( statusbar.disconnected ) then
			statusbar:SetValue(maxValue);
			statusbar.currValue = maxValue;
			if ( not statusbar.lockColor ) then
				statusbar:SetStatusBarColor(0.5, 0.5, 0.5);
			end
		else
			local predictedCost = statusbar.unitFrame.predictedPowerCost;
			local currValue = UnitPower(unit, statusbar.powerType);
			if (predictedCost) then
				currValue = currValue - predictedCost;
			end
			if ( statusbar.FullPowerFrame ) then
				statusbar.FullPowerFrame:SetMaxValue(maxValue);
			end

			statusbar:SetValue(currValue);
			statusbar.forceUpdate = true;
		end
	end
	statusbar:UpdateTextString();
end
-- END UnitFrameManaBar_Update

-- BEGIN ClassResourceBarMixin:UpdateMaxPower
function ClassResourceBarMixin:UpdateMaxPower()
	local oldMaxPoints = self.maxUsablePoints;
	self.unit = self.unit or self:GetParent():GetParent().unit or "player";
	self.maxUsablePoints = UnitPowerMax(self.unit, self.powerType);

	if self.usePooledResourceButtons then
		-- Avoid resetting resource buttons if max points hasn't changed
		if oldMaxPoints and self.maxUsablePoints == oldMaxPoints and self.classResourceButtonTable and #self.classResourceButtonTable == self.maxUsablePoints then
			return;
		end

		self.classResourceButtonPool:ReleaseAll();
		self.classResourceButtonTable = { };

		assertsafe(self.maxUsablePoints < 100, "MaxUsablePoints unexpectedly high maxUsablePoints = " .. self.maxUsablePoints .. " powerType = " .. self.powerType);

		for i = 1, self.maxUsablePoints do
			local resourcePoint = self.classResourceButtonPool:Acquire();
			self.classResourceButtonTable[i] = resourcePoint;
			if(self.resourcePointSetupFunc) then
				self.resourcePointSetupFunc(resourcePoint);
			end
			resourcePoint.layoutIndex = i;
			resourcePoint:Show();
		end

		self:Layout();

		-- Since we just re-acquired all the resource buttons, make sure they all get the current power state applied to them
		-- Very important since it's possible for max to update either without or after other power update events
		self:UpdatePower();
	end
end
-- END ClassResourceBarMixin:UpdateMaxPower

-- BEGIN RogueComboPointBarMixin:UpdatePower
function RogueComboPointBarMixin:UpdatePower()
	local unit = self:GetUnit();
	local comboPoints = UnitPower(unit, self.powerType);
	local chargedPowerPoints = GetUnitChargedPowerPoints(unit);
	for i = 1, #self.classResourceButtonTable do
		local isFull = i <= comboPoints;
		local isCharged = chargedPowerPoints and tContains(chargedPowerPoints, i) or false;

		self.classResourceButtonTable[i]:Update(isFull, isCharged);
	end
end
-- END RogueComboPointBarMixin:UpdatePower

-- BEGIN DruidComboPointBarMixin:ShouldShowBar
function DruidComboPointBarMixin:ShouldShowBar()
	local showBar = false;
	local unit = self:GetUnit();
	local _, myclass = UnitClass(unit);
	if myclass == "DRUID" then
		local powerType = UnitPowerType(unit);
		showBar = (powerType == Enum.PowerType.Energy);
	end
	return showBar;
end
-- END DruidComboPointBarMixin:ShouldShowBar

-- BEGIN DruidComboPointBarMixin:UpdatePower
function DruidComboPointBarMixin:UpdatePower()
	local comboPoints = UnitPower(self:GetUnit(), self.powerType);

	for i = 1, #self.classResourceButtonTable do
		self.classResourceButtonTable[i]:SetActive(i <= comboPoints);
	end
end
-- END DruidComboPointBarMixin:UpdatePower

-- BEGIN MagePowerBar:UpdatePower
function MagePowerBar:UpdatePower()
	local numCharges = UnitPower(self:GetUnit(), self.powerType, true);
	for i = 1, #self.classResourceButtonTable do
		self.classResourceButtonTable[i]:SetActive(i <= numCharges);
	end
end
-- END MagePowerBar:UpdatePower

-- BEGIN MonkPowerBar:UpdatePower
function MonkPowerBar:UpdatePower()
	local numChi = UnitPower(self:GetUnit(), Enum.PowerType.Chi);
	for i = 1, #self.classResourceButtonTable do
		self.classResourceButtonTable[i]:SetActive(i <= numChi);
	end
end
-- END MonkPowerBar:UpdatePower

-- BEGIN PaladinPowerBar:UpdatePower
function PaladinPowerBar:UpdatePower()
	if self.delayedUpdate then
		return;
	end
	local unit = self:GetUnit();
	local numHolyPower = UnitPower( unit, Enum.PowerType.HolyPower );
	local maxHolyPower = UnitPowerMax( unit, Enum.PowerType.HolyPower );

	local isSpellReady = numHolyPower >= HOLY_POWER_SPELL_READY;

	for i=1,maxHolyPower do
		local holyRune = self["rune"..i];
		local runeState = PaladinPowerBar.VisualState.Inactive;
		if i <= numHolyPower then
			runeState = isSpellReady and PaladinPowerBar.VisualState.SpellReady or PaladinPowerBar.VisualState.Active;
		end

		holyRune:SetVisualState(runeState);
	end

	local holderState = PaladinPowerBar.VisualState.Inactive;
	if numHolyPower > 0 then
		holderState = isSpellReady and PaladinPowerBar.VisualState.SpellReady or PaladinPowerBar.VisualState.Active;
	end

	self:UpdateVisualState(holderState, numHolyPower);
end
-- END PaladinPowerBar:UpdatePower

-- BEGIN WarlockPowerBar:UpdatePower
function WarlockPowerBar:UpdatePower()
	local unit = self:GetUnit();
	local shardPower = self:UnitPower(unit);

	-- Bug ID: 496542: Destruction is supposed to show partial soulshards, but Affliction and Demonology should only show full ones.
	if C_SpecializationInfo.GetSpecialization() ~= SPEC_WARLOCK_DESTRUCTION then
		shardPower = math.floor(shardPower);
	end

	local isInCombat = UnitAffectingCombat(unit);

	local showIsFullPower = false;
	-- Only use "full power" visuals while in combat
	if isInCombat then
		-- Unlike UnitPower, UnitPowerMax doesn't need to be processed by UnitPowerDisplayMod (ie it returns 5, not 50)
		local maxPower = UnitPowerMax(unit, self.powerType);
		showIsFullPower = shardPower >= maxPower;
	end

	for shard in self.classResourceButtonPool:EnumerateActive() do
		shard:Update(shardPower, showIsFullPower);
	end
end
-- END WarlockPowerBar:UpdatePower

-- BEGIN WarlockPowerBar:UnitPower
function WarlockPowerBar:UnitPower(unit)
	local shardPower = UnitPower(unit, self.powerType, true);
	local shardModifier = UnitPowerDisplayMod(self.powerType);
	return (shardModifier ~= 0) and (shardPower / shardModifier) or 0;
end
-- END WarlockPowerBar:UnitPower

-- BEGIN EssencePowerBar:UpdatePower
function EssencePowerBar:UpdatePower()
	if (self.delayedUpdate) then
		return;
	end
	local unit = self.unit or self:GetParent().unit;
	local comboPoints = UnitPower(unit, Enum.PowerType.Essence);
	local maxComboPoints = UnitPowerMax(unit, Enum.PowerType.Essence);
	for i = 1, min(comboPoints, self.maxUsablePoints) do
		self.classResourceButtonTable[i]:SetEssennceFull();
	end
	for i = comboPoints + 2, self.maxUsablePoints do
		self.classResourceButtonTable[i]:AnimOut();
	end

	local isAtMaxPoints = comboPoints == maxComboPoints;
	local fillingPoint = self.classResourceButtonTable[comboPoints + 1];
	if (not isAtMaxPoints and fillingPoint) then
		local partialPoint = UnitPartialPower(unit, Enum.PowerType.Essence);
		local elapsedPortion = (partialPoint / 1000.0);

		local filling = fillingPoint.EssenceFilling.FillingAnim:IsPlaying() or fillingPoint.EssenceFull:IsShown();
		local outdatedProgress = false;
		if filling then
			outdatedProgress = math.abs(elapsedPortion - fillingPoint.EssenceFilling.FillingAnim:GetProgress()) > 0.1;
		end

		if not filling or outdatedProgress then
			local peace,interrupted = GetPowerRegenForPowerType(Enum.PowerType.Essence)
			if (peace == nil or peace == 0) then
				peace = 0.2;
			end
			local cooldownDuration = 1 / peace;
			local animationSpeedMultiplier = FillingAnimationTime / cooldownDuration;
			if not filling then
				fillingPoint.EssenceFilling.FillingAnim:Stop();
				fillingPoint.EssenceFilling.CircleAnim:Stop();
			end
			fillingPoint:AnimIn(animationSpeedMultiplier, elapsedPortion);
		end
	end
end
-- END EssencePowerBar:UpdatePower

-- BEGIN RuneButtonMixin:UpdateState
function RuneButtonMixin:UpdateState()
	local previousState = self.visualState;

	self.isNewlyDepleted = false;

	local start, duration, runeReady = GetRuneCooldown(self.runeIndex);
	self.lastRuneState = { start = start, duration = duration, runeReady = runeReady }

	if not runeReady then
		if start then
			self:ShowAsOnCooldown(start, duration, previousState);
		elseif previousState ~= RuneButtonMixin.VisualState.Empty then
			self:ShowAsEmpty();
		end
	else
		self:ShowAsReady(previousState);
	end
end
-- END RuneButtonMixin:UpdateState

-- BEGIN MonkStaggerBarMixin:GetCurrentPower
function MonkStaggerBarMixin:GetCurrentPower()
	return UnitStagger(self:GetUnit()) or 0;
end
-- END MonkStaggerBarMixin:GetCurrentPower

-- BEGIN MonkStaggerBarMixin:GetCurrentMinMaxPower
function MonkStaggerBarMixin:GetCurrentMinMaxPower()
	local maxHealth = UnitHealthMax(self:GetUnit());
	return 0, maxHealth;
end
-- END MonkStaggerBarMixin:GetCurrentMinMaxPower
