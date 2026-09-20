-- 准星 HUD 的薄适配器。
--
-- 职责只有三件：把宿主接口补齐、走真实生命周期启动、把**生产代码实际产出的读数**原样交出去。
-- 不计算任何业务量：生命与主资源在这里是**插件产出的角度**，不是比例——
-- 比例由仓库侧的比较层用独立映射换算（见 .wow-test/projection 的说明）。
--
-- 加载清单与 .toc 的差别：只加载 Logic / Elements / Config / Core 四个文件，
-- 可见性（Visibility）与三个组件无关且有独立回归，不在此列。

local FILES = {
    "addons/MYUI_CrosshairHUD/Logic.lua",
    "addons/MYUI_CrosshairHUD/Elements.lua",
    "addons/MYUI_CrosshairHUD/Config.lua",
    "addons/MYUI_CrosshairHUD/Core.lua",
}

return function(ctx)
    local env = ctx.env
    local frames, timers = {}, {}

    ---------------------------------------------------------------- 曲线
    -- 生产代码把「比例 → 角度」做成曲线交给引擎求值；这里按同一契约实现求值端，
    -- 且**必须使用生产代码实际传入的那条曲线与其端点**——否则生产曲线的错误传不到观测结果。
    local Curve = {}
    Curve.__index = Curve
    function Curve:SetType(kind) self.curveType = kind end
    function Curve:AddPoint(x, y) self.points[#self.points + 1] = { x, y } end
    function Curve:Evaluate(x)
        local p = self.points
        if #p == 0 then return x end
        if x <= p[1][1] then return p[1][2] end
        for i = 2, #p do
            if x <= p[i][1] then
                local x0, y0, x1, y1 = p[i - 1][1], p[i - 1][2], p[i][1], p[i][2]
                if x1 == x0 then return y1 end
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            end
        end
        return p[#p][2]
    end

    env.Enum = env.Enum or {}
    env.Enum.LuaCurveType = env.Enum.LuaCurveType or { Linear = 0 }
    env.SlashCmdList = env.SlashCmdList or {}
    env.C_CurveUtil = {
        CreateCurve = function() return setmetatable({ points = {} }, Curve) end,
    }

    ---------------------------------------------------------------- 读数
    local function healthRatio()
        local h = ctx.state.health
        local maximum = h.maximum
        if maximum == 0 then maximum = 1 end -- 与原生一致：零上限用 1 兜底
        return h.current / maximum
    end

    local function powerRatio(powerType)
        local entry = ctx.state.powers[tostring(powerType)]
        assert(entry, "unconfigured power type: " .. tostring(powerType))
        local maximum = entry.maximum
        if maximum == 0 then maximum = 1 end
        return entry.current / maximum
    end

    local function curveValue(curve, ratio)
        if curve and curve.Evaluate then return curve:Evaluate(ratio) end
        return ratio
    end

    -- 记下生产代码**实际请求的那个资源类型**：这是可观测的行为，不参与任何计算。
    local powerTypeRequested

    env.UnitHealthPercent = function(_, _, curve) return curveValue(curve, healthRatio()) end
    env.UnitPowerPercent = function(_, powerType, _, curve)
        powerTypeRequested = powerType
        return curveValue(curve, powerRatio(powerType))
    end

    ---------------------------------------------------------------- 显示对象
    local function Texture()
        local t = {}
        function t:SetTexture(...) self.texture = true end
        function t:SetSize(w, h) self.width, self.height = w, h end
        function t:SetPoint(...) self.anchor = { ... } end
        function t:SetAllPoints(...) self.allPoints = true end
        function t:SetShown(v) self.shown = not not v end
        function t:SetVertexColor(...) self.color = { ... } end
        function t:AddMaskTexture(m) self.mask = m end
        return t
    end

    local function Mask()
        local m = {}
        function m:SetTexture(...) self.texture = true end
        function m:SetAllPoints(...) self.allPoints = true end
        function m:SetRotation(v) self.rotation = v end
        return m
    end

    local function extend(frame)
        function frame:SetSize(w, h) self.width, self.height = w, h end
        function frame:SetPoint(...) self.anchor = { ... } end
        function frame:ClearAllPoints() self.anchor = nil end
        function frame:SetFrameStrata(s) self.strata = s end
        function frame:CreateTexture(...) return Texture() end
        function frame:CreateMaskTexture(...) return Mask() end
        return frame
    end

    local toolCreateFrame = env.CreateFrame
    env.CreateFrame = function(...)
        local frame = extend(toolCreateFrame(...))
        frames[#frames + 1] = frame
        return frame
    end

    local toolTimer = env.C_Timer
    env.C_Timer = {
        After = function(d, f) local t = toolTimer.After(d, f); timers[#timers + 1] = t; return t end,
        NewTimer = function(d, f) local t = toolTimer.NewTimer(d, f); timers[#timers + 1] = t; return t end,
        NewTicker = function(d, f, n) local t = toolTimer.NewTicker(d, f, n); timers[#timers + 1] = t; return t end,
    }

    ---------------------------------------------------------------- 生命周期
    local readings

    return {
        start = function()
            for _, path in ipairs(FILES) do ctx.load(path) end
            -- 真实启动路径：生产代码在登录时装配曲线并首次读数
            ctx.emit("PLAYER_LOGIN")
            ctx.advance(0)
        end,

        -- 交出去的**只有**生产代码实际产出的东西：角度、符文三元组与状态、能否读到。
        snapshot = function()
            readings = ctx.env.MYUI_CHH and ctx.env.MYUI_CHH.Core
                and ctx.env.MYUI_CHH.Core.GetReadings and ctx.env.MYUI_CHH.Core.GetReadings()
            assert(readings, "生产代码未提供读数接口")
            return ctx.copy({
                observed = {
                    has_health = readings.hasHealth == true,
                    has_power = readings.hasPower == true,
                    health_angle = readings.healthRotation,
                    power_angle = readings.powerRotation,
                    power_type = powerTypeRequested,
                    runes = readings.runes,
                },
            })
        end,

        -- 生产代码没有停止入口（设计如此）；这里只释放本适配器自己捕获的宿主句柄。
        stop = function()
            for _, frame in ipairs(frames) do
                if frame.UnregisterAllEvents then frame:UnregisterAllEvents() end
            end
            for _, timer in ipairs(timers) do
                if timer.Cancel then timer:Cancel() end
            end
        end,
    }
end
