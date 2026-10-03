-- 原生增益容器拥有受限层数；插件只提供外观和显示量程。
local NS = _G.MYUI_CHH or {}
_G.MYUI_CHH = NS
local Native = {}
NS.NativeBlood = Native
local MEDIA = "Interface\\AddOns\\MYUI\\Media\\CrosshairHUD\\"
local container, appearance
local retryAfter = 0
Native.status = "尚未绑定"

local function Texture(parent, file, sub, ox, oy)
    local t = parent:CreateTexture(nil, "ARTWORK", nil, sub)
    t:SetTexture(MEDIA .. file .. ".blp", nil, nil, "TRILINEAR")
    t:SetSize(128, 128)
    t:SetPoint("CENTER", parent, "CENTER", ox or 0, oy or 0)
    return t
end

function Native.Create(parent)
    Native.host = _G.CreateFrame("Frame", nil, parent)
    Native.host:SetSize(128, 128)
    Native.host:SetPoint("CENTER", parent, "CENTER")
    Native.host:EnableMouse(false)
    Native.host:SetShown(false)
end

local function Appearance(st)
    local out = { st.maxStacks, st.fillAlpha, st.bgAlpha, st.shadowAlpha }
    for _, key in ipairs({ "fillColor", "bgColor", "shadowColor" }) do
        for i = 1, 3 do out[#out + 1] = st[key][i] end
    end
    return out
end

local function Changed(nextAppearance)
    if not appearance then return true end
    for i, value in ipairs(nextAppearance) do
        if appearance[i] ~= value then return true end
    end
    return false
end

local function Build(st)
    if container then container:SetEnabled(false); container:SetShown(false) end
    container = _G.CreateFrame("AuraContainer", nil, Native.host, "CustomAuraContainerTemplate")
    container:SetAllPoints(Native.host)
    container:SetUnit("player")
    container:AddAuraSlot("coagulatedBlood", "HELPFUL", {
        candidateFilters = { includeSpellIDs = { [463730] = true } },
        initializeFrame = function(button)
            -- 只在暴雪允许的初始化阶段接触子控件；不保存增益按钮或数值对象。
            button:SetAllPoints(container)
            button:EnableMouse(false)
            button:SetShown(false)
            button:SetFrameLevel(math.max(0, NS.Elements.frame:GetFrameLevel() - 1))
            local bg = Texture(button, "coagulated_blood_arc", 0, -32, -16)
            local bc = st.bgColor
            bg:SetVertexColor(bc[1], bc[2], bc[3], st.bgAlpha)
            local bar = _G.CreateFrame("StatusBar", nil, button)
            bar:SetAllPoints(button)
            bar:SetFrameLevel(NS.Elements.frame:GetFrameLevel() + 1)
            bar:EnableMouse(false)
            local fill = Texture(bar, "coagulated_blood_fill", 1)
            bar:SetStatusBarTexture(fill)
            fill:SetTexture(MEDIA .. "coagulated_blood_fill.blp", nil, nil, "TRILINEAR")
            bar:SetRenderMode(_G.Enum.StatusBarRenderMode.Radial)
            fill:SetAllPoints(bar)
            local arc = NS.Logic.ARCS.coagulatedBlood
            local start = arc.start - NS.Logic.FILL_MARGIN - 90
            -- 原生绑定固定0到量程；末端偏移是从整圆末端扣除的部分。
            fill:SetRadialProgressBarStartOffset(start / 360)
            fill:SetRadialProgressBarEndOffset(1 - (start + arc.span + NS.Logic.FILL_MARGIN) / 360)
            fill:SetRadialProgressBarReverse(false)
            fill:SetRadialProgressBarFeather(1 / (2 * math.pi * arc.radius))
            local fc = st.fillColor
            bar:SetStatusBarColor(fc[1], fc[2], fc[3], st.fillAlpha)
            bar:SetShown(true)
            button:SetApplicationBar(bar, { maxApplications = st.maxStacks })
        end,
    })
    container:SetEnabled(true)
end

function Native.Apply(st, scale)
    Native.host:SetScale(scale)
    local enabled = st.visible ~= false and not st.probe
    Native.host:SetShown(enabled and Native.ready == true)
    if not enabled then return end
    local nextAppearance = Appearance(st)
    if not Changed(nextAppearance) then return end
    local now = _G.GetTime()
    if now < retryAfter then return end
    -- 设置变更重建单个槽位，避免访问已经受限的按钮和进度条。
    local ok, err = pcall(Build, st)
    if ok then
        appearance = nextAppearance
        Native.ready = true
        retryAfter = 0
        Native.host:SetShown(true)
        Native.status = "原生层数绑定就绪；增益存在与层数由暴雪管理"
    else
        appearance = nil
        -- 借用既有刷新节奏，每秒至多重试一次，不增加定时器。
        retryAfter = now + 1
        Native.ready = false
        Native.host:SetShown(false)
        Native.status = "原生绑定失败"
        local detector = _G.issecretvalue
        local readable, secret = true, false
        if detector then readable, secret = pcall(detector, err) end
        if readable and not secret and type(err) == "string" then
            Native.status = Native.status .. "：" .. err
        end
    end
end
