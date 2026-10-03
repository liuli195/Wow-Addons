-- 正式反馈入口：只在主动调用时读取状态并创建复制窗口，不注册轮询或自动日志。
local NS = _G.MYUI_CHH
local Diagnostics = {}
NS.Diagnostics = Diagnostics
local window, edit, scroll

local function Readable(value)
    local detector = _G.issecretvalue
    if detector then
        local ok, secret = pcall(detector, value)
        if not ok or secret then return false end
    end
    return true
end

local function Number(value)
    if not Readable(value) then return "受限或不可读取" end
    if type(value) ~= "number" or value ~= value or math.abs(value) == math.huge then return "缺失" end
    return string.format("%.6g", value)
end

local function KnownText(value)
    if not Readable(value) or type(value) ~= "string" then return "不可读取" end
    -- 此函数仅接收游戏版本和插件元数据，不接收错误原文或玩家输入。
    return value:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("[\r\n]", " "):sub(1, 80)
end

local function Metadata(key)
    local api = _G.C_AddOns
    if not (api and api.GetAddOnMetadata) then return "接口不可用" end
    local ok, value = pcall(api.GetAddOnMetadata, "MYUI_CrosshairHUD", key)
    return ok and KnownText(value) or "读取失败"
end

local function Loaded(name)
    local api = _G.C_AddOns
    if not (api and api.IsAddOnLoaded) then return "接口不可用" end
    local ok, value = pcall(api.IsAddOnLoaded, name)
    if not ok or not Readable(value) then return "读取失败或受限" end
    return value and "已加载" or "未加载"
end

local function Switch(value)
    if not Readable(value) then return "受限" end
    return value == false and "关闭" or "开启"
end

local function ReadingStatus(value)
    if not Readable(value) then return "受限，交给游戏绘制" end
    return value == nil and "尚未取得" or "可读取"
end

function Diagnostics.BuildReport()
    local cfg = NS.Config.Get()
    local lines = { "准星HUD 诊断报告（格式版本1）", "插件版本：" .. Metadata("Version"),
        "安装包编号：" .. Metadata("X-MYUI-Build") }
    local function Line(label, value) lines[#lines + 1] = label .. "：" .. value end
    if _G.GetBuildInfo then
        local ok, version, build, _, interface = pcall(_G.GetBuildInfo)
        Line("游戏版本", ok and (KnownText(version) .. " / " .. KnownText(build)
            .. " / 接口 " .. Number(interface)) or "读取失败")
    else Line("游戏版本", "接口不可用") end
    for _, name in ipairs({ "MYUI", "EllesmereUI", "EllesmereUIOptions", "Blizzard_AuraContainer" }) do
        Line(name .. "（依赖组件）", Loaded(name))
    end
    Line("总开关", Switch(cfg.enabled))
    Line("缩放", Number(cfg.scale))
    local strata = { LOW="低", MEDIUM="中", HIGH="高", DIALOG="对话框" }
    Line("图层", Readable(cfg.strata) and (strata[cfg.strata] or "未知") or "受限")
    Line("阴影透明度", Number(cfg.shadowAlpha))
    for _, key in ipairs(NS.Config.ELEMENT_ORDER) do
        local item = cfg.elements[key]
        Line(NS.Config.ELEMENT_LABELS[key] .. "开关", Switch(item.enabled))
        Line(NS.Config.ELEMENT_LABELS[key] .. "填充透明度", Number(item.fillAlpha))
        if item.bgAlpha then Line(NS.Config.ELEMENT_LABELS[key] .. "背景透明度", Number(item.bgAlpha)) end
    end
    Line("最大显示层数", Number(cfg.elements.coagulatedBlood.maxStacks))
    Line("刻度粗细", Number(cfg.elements.deathStrike.thickness))
    local ok, readings = pcall(NS.Core.GetReadings)
    if ok and type(readings) == "table" then
        Line("生命值最近一次读取", readings.healthReadOK and "成功" or "未成功或尚未开始")
        Line("能量最近一次读取", readings.powerReadOK and "成功" or "未成功或尚未开始")
        Line("生命值角度", ReadingStatus(readings.healthRotation))
        Line("能量角度", ReadingStatus(readings.powerRotation))
        Line("灵打费用刻度", readings.hasMarker and "位置已计算" or "未取得可用费用或最大符能")
    else Line("运行状态", "读取失败") end
    local native = NS.NativeBlood
    Line("凝固之血绑定", not native and "组件未加载" or
        (native.ready == true and "原生绑定就绪；存在与层数由游戏管理" or "尚未就绪或绑定失败"))
    Line("凝固之血层数", "由游戏管理，诊断不反向读取受限数值")
    local hiddenOK, hidden = pcall(NS.Core.IsHidden)
    Line("界面是否隐藏", hiddenOK and (hidden and "是" or "否") or "读取失败")
    lines[#lines + 1] = "报告不包含账号、角色名、聊天、本机路径或错误原文。请另附问题描述和截图。"
    return table.concat(lines, "\n")
end

local function CreateWindow()
    window = _G.CreateFrame("Frame", "MYUICHHDiagnosticWindow", _G.UIParent, "BackdropTemplate")
    local width = math.min(760, _G.UIParent:GetWidth() - 40)
    local height = math.min(560, _G.UIParent:GetHeight() - 40)
    window:SetSize(width, height)
    window:SetPoint("CENTER")
    window:SetFrameStrata("DIALOG")
    window:SetBackdrop({ bgFile="Interface\\Buttons\\WHITE8X8", edgeFile="Interface\\Buttons\\WHITE8X8",
        edgeSize=1, insets={left=1,right=1,top=1,bottom=1} })
    window:SetBackdropColor(0.08, 0.1, 0.12, 0.98)
    window:SetBackdropBorderColor(0.4, 0.45, 0.5, 1)
    window:EnableMouse(true)
    window:SetMovable(true)
    window:RegisterForDrag("LeftButton")
    window:SetScript("OnDragStart", function(self) self:StartMoving() end)
    window:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    local title = window:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText("准星HUD诊断报告：点击文本后全选、复制，贴给我们")
    local close = _G.CreateFrame("Button", nil, window, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -4, -4)
    scroll = _G.CreateFrame("ScrollFrame", nil, window, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 16, -46)
    scroll:SetPoint("BOTTOMRIGHT", -36, 46)
    edit = _G.CreateFrame("EditBox", nil, scroll)
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    edit:SetFontObject("ChatFontNormal")
    edit:SetWidth(width - 60)
    edit:SetHeight(1200)
    edit:SetTextInsets(4, 4, 4, 4)
    edit:SetScript("OnEscapePressed", function() window:Hide() end)
    -- 文本可选取和复制；误输入不会覆盖报告，也不写存档。
    edit:SetScript("OnTextChanged", function(self, userInput)
        if userInput then self:SetText(Diagnostics.text); self:HighlightText() end
    end)
    scroll:SetScrollChild(edit)
    local all = _G.CreateFrame("Button", nil, window, "UIPanelButtonTemplate")
    all:SetSize(120, 24)
    all:SetPoint("BOTTOMLEFT", 16, 12)
    all:SetText("全选报告")
    all:SetScript("OnClick", function() edit:SetFocus(); edit:HighlightText() end)
    window:SetScript("OnHide", function() edit:ClearFocus() end)
    local specialFrames = rawget(_G, "UISpecialFrames")
    if specialFrames then table.insert(specialFrames, "MYUICHHDiagnosticWindow") end
end

function Diagnostics.Show()
    Diagnostics.text = Diagnostics.BuildReport()
    if not window then CreateWindow() end
    window:Show()
    edit:SetText(Diagnostics.text)
    edit:SetCursorPosition(0)
    scroll:SetVerticalScroll(0)
    edit:SetFocus()
    edit:HighlightText()
    _G.print("诊断报告已生成，请在报告窗口中全选并复制。")
end

_G.SLASH_MYUICHH1 = "/chh"
local commands = rawget(_G, "SlashCmdList")
commands.MYUICHH = function(msg)
    local command = (msg or ""):lower():gsub("%s+", "")
    if command == "" or command == "diag" or command == "report" or command == "诊断" then
        Diagnostics.Show()
    else
        _G.print("输入 /chh diag 打开可复制的诊断报告。")
    end
end
