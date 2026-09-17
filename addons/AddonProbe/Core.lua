-- AddonProbe —— 通用诊断探针
-- ---------------------------------------------------------------------------
-- 解决的问题：某个值被谁、在什么时候、改成了什么。这类 bug 不报 Lua 错误，
-- 事后也没有痕迹，所以要把"改动发生的那一刻"存下来：调用栈 + 改前改后。
--
-- 通用部分（不针对任何插件）：
--   AddonProbe.Watch(owner, name, opts)   在任意表上挂具名函数的 secure hook
--   AddonProbe.Snapshot(action)           只取受跟踪字段，值归一成字符串
--   AddonProbe.ChangedFields(before, after) 两次快照之间真正变了的字段
--   AddonProbe.DetectFlip(before, after)  默认规则：spell 消失且 macro 出现
--   /probe start|mark|stop|status|clear   主动触发的证据采集
--
-- 新增一个诊断目标 = 在 PRESET_HANDLERS / INSTALLERS 里各加一段（看哪两个
-- 函数、用哪条规则），通用部分不用动。
--
-- 用法：/reload → 打开一次 GSE 编辑器（GSE_GUI 是 LoadOnDemand，钩子要等它加载）
-- → /probe status 看到「钩子 3/3」且「SetText 钩子 ≥1 个」→ /probe start → 复现
-- → /probe mark <说明> → /probe stop → /reload，
-- 然后读 WTF\Account\<账号>\SavedVariables\AddonProbe.lua（会话里的 diagnostics 自带覆盖自检）。
--
-- SetText 追踪：程序化 SetText 是 OnTextChanged 的触发源，而引擎回调期间的尾调用
-- 会把更下层的帧抹掉（栈里只剩 [tail call]: ?），所以"谁调的 SetText"必须另找入口——
-- SetText 自己的钩子是在调用者还没返回时执行的，那一刻取栈就能拿到调用者。
--
-- 环境事实（踩过的坑）：GSE 3.3.x 起 _G.GSE 只是四字段公开代理
-- （GSE/API/Plugins.lua 的 "legacy plugin compatibility shim"：只有 RegisterAddon /
-- GetSequenceNamesFromLibrary / isEmpty / Statics，写入被丢弃），真表是私有的，
-- 只通过 <子模块>_Initialize(gse) 这个全局入口外流（GSE/API/Init.lua 的 pushGSEInto，
-- 由 GSE 的 ADDON_LOADED 派发器触发）。所以要在子模块 ADDON_LOADED 时先挂好入口钩子，
-- 把真表截下来——本插件名以 A 开头、加载早于 GSE，ADDON_LOADED 处理器先注册先执行。
--
-- 已知取舍：写记录一律带调用栈（这就是证据），所以有 MAX_RECORDS 上限；
-- 超出后停止记录并置 session.truncated。ticker 兜底的记录没有栈（不在调用里）。
-- 12.x 战斗保密值读不出来时记 "unavailable"（与 Sim2GSEProbe 同一套词汇），
-- 绝不因为单个字段读不出来就丢掉整条记录。

local PREFIX = "|cff58c7ffAddonProbe:|r "
local SCHEMA = 1
local MAX_RECORDS = 400
local MAX_SESSIONS = 5
local MAX_TEXT = 80
local SWEEP_INTERVAL = 0.5
local INSTALL_INTERVAL = 3
local SETTEXT_TRAIL_MAX = 20
local SETTEXT_MATCH_WINDOW = 1
local UNAVAILABLE = "unavailable"
local TRACKED_FIELDS = { "type", "spell", "macro", "item", "action", "toy" }

local C_Timer = _G.C_Timer
local CreateFrame = _G.CreateFrame
local GetTime = _G.GetTime
local debugstack = _G.debugstack
local hooksecurefunc = _G.hooksecurefunc
local issecretvalue = _G.issecretvalue

local AddonProbe = {}
_G.AddonProbe = AddonProbe
AddonProbe.MAX_RECORDS = MAX_RECORDS
AddonProbe.UNAVAILABLE = UNAVAILABLE

local state = {
    session = nil,
    baseline = {},
    lastSequence = nil,
    lastVersion = nil,
}
-- 已挂上的 hook 目标（"预设:函数名"），以及声明了但可能还没挂上的目标
local hookedTargets = {}
local DECLARED_TARGETS = {
    { preset = "gse", name = "CreateSpellEditBox" },
    { preset = "gse", name = "RefreshActionIconFor" },
    { preset = "gse", name = "RefreshMacroEditorColoredText" },
}

local function Say(message)
    print(PREFIX .. message)
end

local function GetDB()
    local db = rawget(_G, "AddonProbeDB")
    if type(db) ~= "table" then
        db = { schema = SCHEMA, sessions = {} }
        rawset(_G, "AddonProbeDB", db)
    end
    if type(db.sessions) ~= "table" then db.sessions = {} end
    return db
end

-- 保密值安全读取：仓库现成写法见 addons/Sim2GSEProbe/Core.lua 的 SafeScalar/SafeCall。
-- 读不出来（保密值、读取即报错的值）返回 UNAVAILABLE，而不是让调用方抛错。
function AddonProbe.Scalar(value)
    if value == nil then return nil end
    if issecretvalue then
        local ok, secret = pcall(issecretvalue, value)
        if ok and secret then return UNAVAILABLE end
    end
    local kind = type(value)
    local ok, copied
    if kind == "number" then
        ok, copied = pcall(function() return value + 0 end)
    elseif kind == "string" then
        ok, copied = pcall(function() return "" .. value end)
    elseif kind == "boolean" then
        ok, copied = pcall(function() return value == true end)
    else
        ok, copied = pcall(tostring, value)
    end
    if not ok then return UNAVAILABLE end
    local text = tostring(copied)
    if #text > MAX_TEXT then return string.sub(text, 1, MAX_TEXT) .. "..." end
    return text
end

local function Clamp(value)
    return AddonProbe.Scalar(value) or ""
end

-- 记录里的键两种形态都有：路径对象（表）和索引。一律渲染成可读文本，
-- 否则日志里全是 "table: 0x..."。
function AddonProbe.PathText(key)
    if key == nil then return "?" end
    if issecretvalue then
        local ok, secret = pcall(issecretvalue, key)
        if ok and secret then return UNAVAILABLE end
    end
    if type(key) == "table" then
        local parts = {}
        for index = 1, 8 do
            local part = rawget(key, index)
            if part == nil then break end
            parts[#parts + 1] = AddonProbe.PathText(part)
        end
        if #parts == 0 then return "?" end
        return table.concat(parts, "/")
    end
    return AddonProbe.Scalar(key) or "?"
end

-- 可断言的规则 --------------------------------------------------------------

function AddonProbe.Snapshot(action)
    if type(action) ~= "table" then return nil end
    local snapshot = {}
    for _, field in ipairs(TRACKED_FIELDS) do
        local value = action[field]
        if value ~= nil then snapshot[field] = Clamp(value) end
    end
    return snapshot
end

function AddonProbe.ChangedFields(before, after)
    local changed = {}
    if not before or not after then return changed end
    for _, field in ipairs(TRACKED_FIELDS) do
        if before[field] ~= after[field] then changed[#changed + 1] = field end
    end
    return changed
end

function AddonProbe.DetectFlip(before, after)
    if not before or not after then return false end
    if before.spell == nil then return false end
    if after.spell ~= nil then return false end
    return after.macro ~= nil
end

-- 记录 ----------------------------------------------------------------------

local function CaptureStack()
    if not debugstack then return nil end
    local ok, stack = pcall(debugstack, 2, 20, 20)
    if ok and type(stack) == "string" then return stack end
    return nil
end

-- GSE 私有表捕获：见文件头的「环境事实」。放在最前面，后面的 ScanPool/预设都要用它。
local GSE_SUBMODULES = { "GSE_Utils", "GSE_Options", "GSE_GUI", "GSE_LDB", "GSE_QoL", "GSE_Companion" }
local gseTable = nil
local hookedInitializers = {}

local function CaptureGSE(gse)
    -- 公开代理不是真表：它没有 CreateGSE3Button 这类真表才有的方法
    if type(gse) == "table" and type(gse.CreateGSE3Button) == "function" then gseTable = gse end
end

local function InstallCaptureHooks()
    for _, addon in ipairs(GSE_SUBMODULES) do
        local key = addon .. "_Initialize"
        if not hookedInitializers[key] and type(_G[key]) == "function" then
            hookedInitializers[key] = true
            hooksecurefunc(_G, key, CaptureGSE)
        end
    end
end

local function ResolveGSE()
    if gseTable then return gseTable end
    local global = rawget(_G, "GSE")
    -- 真表判定：只有真表才有 CreateGSE3Button（公开代理只有四个字段）
    if type(global) == "table" and type(global.CreateGSE3Button) == "function" then return global end
    return nil
end

-- SetText / 火警轨迹：环形缓冲，只在采集期内记录。两条线并存：
--   setTextTrail —— 谁在程序化写文本（包装器与内层各一条，同一次调用去重）
--   setTextFires —— 框的 OnTextChanged 真的被触发了（不依赖"谁调的 SetText"）
-- 每条都带框编号，好把两条线对号入座。
local setTextTrail = {}
local setTextFires = {}
local hookedBoxes = {}
local boxIds = {}
local boxHookCount = 0
local fireHookCount = 0
local nextBoxId = 0

local function BoxId(box)
    local id = boxIds[box]
    if not id then
        nextBoxId = nextBoxId + 1
        id = "box" .. nextBoxId
        boxIds[box] = id
    end
    return id
end

local function NoteSetText(box, text)
    local session = state.session
    if not (session and session.armed) then return end
    if type(text) ~= "string" or #text < 2 then return end
    local now = GetTime and GetTime() or 0
    local last = setTextTrail[#setTextTrail]
    -- 包装器转发到内层是同一次调用：同文本、同一瞬间只记一条
    if last and last.text == Clamp(text) and (now - last.t) < 0.001 then return end
    if #setTextTrail >= SETTEXT_TRAIL_MAX then table.remove(setTextTrail, 1) end
    setTextTrail[#setTextTrail + 1] = {
        t = now,
        box = BoxId(box),
        text = Clamp(text),
        stack = CaptureStack(),
    }
end

local function NoteFire(box, text)
    local session = state.session
    if not (session and session.armed) then return end
    if #setTextFires >= SETTEXT_TRAIL_MAX then table.remove(setTextFires, 1) end
    setTextFires[#setTextFires + 1] = {
        t = GetTime and GetTime() or 0,
        box = BoxId(box),
        text = Clamp(text or ""),
        stack = CaptureStack(),
    }
end

-- 拿到一个 macro 框就装三条线：内层 EditBox 的 SetText、包装器的 SetText、内层的火警。
-- 每个实例只装一次。
local function WatchBox(widget)
    local box = widget and (widget.editBox or widget.editbox)
    if type(box) ~= "table" or hookedBoxes[box] then return end
    hookedBoxes[box] = true
    BoxId(box)   -- 按钩上的先后编号，日志里可读
    local hooked = false
    if hooksecurefunc and type(box.SetText) == "function" then
        if pcall(hooksecurefunc, box, "SetText", function(_, text) NoteSetText(box, text) end) then
            hooked = true
        end
    end
    if widget ~= box and hooksecurefunc and type(widget.SetText) == "function" then
        pcall(hooksecurefunc, widget, "SetText", function(_, text) NoteSetText(box, text) end)
    end
    if box.HookScript then
        -- 引擎的 OnTextChanged 第二个参数是 userInput 布尔，不是文本；
        -- 文本必须从框上读（GSE 自己的桥也是 self:GetText()）。
        if pcall(box.HookScript, box, "OnTextChanged", function()
            NoteFire(box, box.GetText and box:GetText() or nil)
        end) then
            fireHookCount = fireHookCount + 1
        end
    end
    if hooked then boxHookCount = boxHookCount + 1 end
end

function AddonProbe.BoxHooks()
    return boxHookCount
end

function AddonProbe.FireHooks()
    return fireHookCount
end

-- 创建/领用点：GSE 每次发放控件都走 GSE.UI.Create（含回收再领用），从这里抓覆盖最完整——
-- 池子扫描的窗口太窄，控件微秒级就被领走，扫不到。用包装（非 secure）：GSE 是通过
-- GSE.UI.Create(...) 这个表字段调用的，所以包装对它生效。
local createHooked = false
local wrappedCreate = nil
local function InstallCreateHook()
    if createHooked then return end
    local gse = ResolveGSE()
    local ui = gse and gse.UI
    if not (ui and type(ui.Create) == "function") then return end
    local original = ui.Create
    wrappedCreate = function(self, typeName, ...)
        local widget = original(self, typeName, ...)
        if widget ~= nil then WatchBox(widget) end
        return widget
    end
    ui.Create = wrappedCreate
    createHooked = true
end

-- 池子扫描：GSE 把用过的控件放回 GSE.UI.widgetPool，被回收的 macro 框就躺在里面。
-- 这是稳定的抓取入口——不依赖 GSE 恰好把框交给外部（失焦重绘那条路很窄）。
-- poolSeen 是"看见过的控件次数"（不是新钩上的个数），用来判断扫描到底扑到没有。
local poolSeen = 0
local poolHooked = 0

local function ScanPool()
    local gse = ResolveGSE()
    local ui = gse and gse.UI
    local pools = ui and ui.widgetPool
    if type(pools) ~= "table" then return end
    for _, pool in pairs(pools) do
        if type(pool) == "table" then
            for _, widget in ipairs(pool) do
                if type(widget) == "table" then
                    poolSeen = poolSeen + 1
                    local before = boxHookCount
                    WatchBox(widget)
                    if boxHookCount > before then poolHooked = poolHooked + 1 end
                end
            end
        end
    end
end

-- 翻转记录配一次痕迹：文本相同、且在时间窗内
local function RecentSetText(text)
    local now = GetTime and GetTime() or 0
    local wanted = Clamp(text)
    for index = #setTextTrail, 1, -1 do
        local entry = setTextTrail[index]
        if (now - entry.t) > SETTEXT_MATCH_WINDOW then return nil end
        if entry.text == wanted then return entry end
    end
    return nil
end

-- 同一只框的证明：同文本 + 同框编号 + 都在时间窗内。两条轨迹按时间有序，越界即停。
local function PairTrails(text)
    local now = GetTime and GetTime() or 0
    local wanted = Clamp(text)
    for index = #setTextFires, 1, -1 do
        local fire = setTextFires[index]
        if (now - fire.t) > SETTEXT_MATCH_WINDOW then break end
        if fire.text == wanted then
            for other = #setTextTrail, 1, -1 do
                local setText = setTextTrail[other]
                if (now - setText.t) > SETTEXT_MATCH_WINDOW then break end
                if setText.text == wanted and setText.box == fire.box then
                    return fire, setText
                end
            end
        end
    end
    return nil
end

local function RecentFire(text)
    local now = GetTime and GetTime() or 0
    local wanted = Clamp(text)
    for index = #setTextFires, 1, -1 do
        local entry = setTextFires[index]
        if (now - entry.t) > SETTEXT_MATCH_WINDOW then return nil end
        if entry.text == wanted then return entry end
    end
    return nil
end

local function AddRecord(record)
    local session = state.session
    if not (session and session.armed) then return end
    if #session.records >= MAX_RECORDS then
        session.truncated = true
        return
    end
    record.t = GetTime and GetTime() or 0
    session.records[#session.records + 1] = record
end

local function BeginSession()
    local db = GetDB()
    local session = {
        startedAt = GetTime and GetTime() or 0,
        armed = true,
        records = {},
    }
    db.sessions[#db.sessions + 1] = session
    while #db.sessions > MAX_SESSIONS do table.remove(db.sessions, 1) end
    state.session = session
    Say("开始记录。复现后用 /probe mark <说明> 标注，再 /probe stop。")
end

local function EndSession()
    local session = state.session
    if not session then
        Say("当前没有在记录。")
        return
    end
    session.armed = false
    session.endedAt = GetTime and GetTime() or 0
    -- 两条轨迹整个落盘：即使没能和某条翻转配上，也能按时间离线比对
    local trail = {}
    for index, entry in ipairs(setTextTrail) do
        trail[index] = { t = entry.t, box = entry.box, text = entry.text, stack = entry.stack }
    end
    session.setTextTrail = trail
    local fires = {}
    for index, entry in ipairs(setTextFires) do
        fires[index] = { t = entry.t, box = entry.box, text = entry.text, stack = entry.stack }
    end
    session.setTextFires = fires
    -- 自检落盘：离线读文件就能知道覆盖有没有生效，不用靠聊天框复述
    session.diagnostics = {
        hooks = AddonProbe.HookReport(),
        setTextHooks = boxHookCount,
        fireHooks = fireHookCount,
        createHooked = createHooked,
        poolSeen = poolSeen,
        poolHooked = poolHooked,
        fires = #setTextFires,
        setTextTrail = #setTextTrail,
    }
    state.session = nil
    Say(
        string.format(
            "已停止：%d 条记录%s。现在 /reload 落地 SavedVariables。",
            #session.records,
            session.truncated and "（已达上限，被截断）" or ""
        )
    )
end

local function Mark(label)
    if not (state.session and state.session.armed) then
        Say("先 /probe start 再 mark。")
        return
    end
    AddRecord({ kind = "mark", label = Clamp(label ~= "" and label or "mark") })
end

local function Status()
    local db = GetDB()
    local session = state.session
    if session and session.armed then
        Say(string.format("正在记录第 %d 段，已有 %d 条。钩子 %s",
            #db.sessions, #session.records, AddonProbe.HookReport()))
    else
        Say(string.format("未在记录；已保存 %d 段证据。钩子 %s", #db.sessions, AddonProbe.HookReport()))
    end
    Say(string.format("SetText 钩子 %d 个 / 火警钩子 %d 个%s",
        AddonProbe.BoxHooks(), AddonProbe.FireHooks(), createHooked and "（创建点已挂）" or ""))
    Say("目标：" .. AddonProbe.TargetReport())
end

local function Clear()
    GetDB().sessions = {}
    state.session = nil
    state.baseline = {}
    Say("已清空证据。")
end

-- 通用 hook：给任意表上的具名函数挂记录 ---------------------------------------

-- 先声明，Watch 里要引用；具体内容在预设段填充
local PRESET_HANDLERS = {}
local INSTALLERS

function AddonProbe.Watch(owner, name, opts)
    if not hooksecurefunc then return false end
    if type(owner) ~= "table" or type(owner[name]) ~= "function" then return false end
    local handlers = PRESET_HANDLERS[(opts or {}).preset]
    if not handlers or not handlers[name] then return false end
    hooksecurefunc(owner, name, function(...)
        -- 探针自身的错误绝不能破坏被观察的界面
        local ok, err = pcall(handlers[name], ...)
        if not ok then Say("记录出错：" .. tostring(err)) end
    end)
    return true
end

-- 逐个目标独立挂载：目标可能晚到（GSE_GUI 是 LoadOnDemand，CreateSpellEditBox 还是懒创建），
-- 所以不要求一次全挂上——挂上就记住，缺的继续重试。
local function InstallTarget(preset, owner, name)
    local key = preset .. ":" .. name
    if hookedTargets[key] then return true end
    if AddonProbe.Watch(owner, name, { preset = preset }) then
        hookedTargets[key] = true
        Say(string.format("已挂上 %s 探针：%s", preset, name))
        return true
    end
    return false
end

-- 钩子挂不上时，先说清卡在哪一环：公开代理在不在、私有表拿到没、具体函数有没有
function AddonProbe.TargetReport()
    local proxy = rawget(_G, "GSE")
    local gse = ResolveGSE()
    local gui = gse and gse.GUI
    local function yes(value) return value and "有" or "无" end
    return table.concat({
        "GSE 公开代理 " .. yes(proxy),
        "GSE 私有表 " .. yes(gse),
        "GSE.GUI " .. yes(gui),
        "CreateSpellEditBox " .. yes(gse and type(gse.CreateSpellEditBox) == "function"),
        "RefreshActionIconFor " .. yes(gui and type(gui.RefreshActionIconFor) == "function"),
    }, " / ")
end

function AddonProbe.HookReport()
    local done, missing = 0, {}
    for _, target in ipairs(DECLARED_TARGETS) do
        if hookedTargets[target.preset .. ":" .. target.name] then
            done = done + 1
        else
            missing[#missing + 1] = target.name
        end
    end
    if done == #DECLARED_TARGETS then return string.format("%d/%d", done, done) end
    return string.format("%d/%d（缺 %s）", done, #DECLARED_TARGETS, table.concat(missing, "、"))
end

-- GSE 预设：编辑器把 spell 动作改写成 macro（issue #2106） --------------------

local function SequenceName(sequence)
    local metadata = sequence and sequence.MetaData
    local name = metadata and (metadata.Name or metadata.name)
    if name == nil then return "?" end
    return Clamp(name)
end

local function SequenceActions(sequence, version)
    local versionTable = sequence and sequence.Versions and sequence.Versions[version]
    local actions = versionTable and versionTable.Actions
    if type(actions) ~= "table" then return nil end
    return actions
end

local function SequenceAction(sequence, version, keyPath)
    local actions = SequenceActions(sequence, version)
    if not actions then return nil end
    return actions[keyPath]
end

-- 基线钩子迟到时（GSE.CreateSpellEditBox 是懒创建的），用第一次看到的状态给其它动作补基线；
-- 不补的话后续写入只有 after、没有 before，判不出变化。
local function FillBaselines(sequence, version)
    local actions = SequenceActions(sequence, version)
    if not actions then return end
    for keyPath, action in pairs(actions) do
        if state.baseline[keyPath] == nil then
            local snapshot = AddonProbe.Snapshot(action)
            if snapshot then state.baseline[keyPath] = snapshot end
        end
    end
end

local function WriteRecord(sequence, version, keyPath, detectedBy)
    local after = AddonProbe.Snapshot(SequenceAction(sequence, version, keyPath))
    local before = state.baseline[keyPath]
    state.baseline[keyPath] = after
    state.lastSequence, state.lastVersion = sequence, version
    FillBaselines(sequence, version)

    local flip = AddonProbe.DetectFlip(before, after)
    -- 翻转时把触发它的那次 SetText 也钉上：那条栈才是"谁干的"
    local pairFire, pairSetText
    if flip and after then pairFire, pairSetText = PairTrails(after.macro) end
    local setText = pairSetText or (flip and after and RecentSetText(after.macro) or nil)
    local fire = pairFire or (flip and after and RecentFire(after.macro) or nil)
    local now = GetTime and GetTime() or 0
    local record = {
        kind = "write",
        preset = "gse",
        detectedBy = detectedBy,
        sequence = SequenceName(sequence),
        version = version,
        keyPath = AddonProbe.PathText(keyPath),
        setTextStack = setText and setText.stack or nil,
        setTextAge = setText and (now - setText.t) or nil,
        setTextBox = setText and setText.box or nil,
        fireStack = fire and fire.stack or nil,
        fireAge = fire and (now - fire.t) or nil,
        fireBox = fire and fire.box or nil,
        pairBox = pairFire and pairFire.box or nil,
        pairAge = pairFire and (now - pairFire.t) or nil,
        before = before,
        after = after,
        flip = flip,
        changed = AddonProbe.ChangedFields(before, after),
        stack = detectedBy == "hook" and CaptureStack() or nil,
    }
    AddRecord(record)
    if flip then
        Say(
            string.format(
                "抓到翻转：%s 的 %s 变成 macro（%s）",
                record.sequence,
                record.keyPath,
                record.after.macro or ""
            )
        )
    end
end

PRESET_HANDLERS = {
    gse = {
        -- 每次重建都会调用：趁渲染前记下真实状态，作为下一次比较的基线
        CreateSpellEditBox = function(action, version, keyPath, sequence)
            state.lastSequence, state.lastVersion = sequence, version
            state.baseline[keyPath] = AddonProbe.Snapshot(action)
        end,
        -- 写入点：spell 框与 macro 框的 OnTextChanged 都从这里经过
        RefreshActionIconFor = function(sequence, version, keyPath)
            WriteRecord(sequence, version, keyPath, "hook")
        end,
        -- 重绘时会带着 macro 框进来：借机在内层 EditBox 上装 SetText 钩子，
        -- 好把"谁在程序化设置文本"钉死（尾调用抹掉的那一环）
        RefreshMacroEditorColoredText = function(widget)
            WatchBox(widget)
        end,
    },
}

INSTALLERS = {
    gse = function()
        local gse = ResolveGSE()
        if not gse then return false end
        local done = true
        if not InstallTarget("gse", gse, "CreateSpellEditBox") then done = false end
        if gse.GUI then
            if not InstallTarget("gse", gse.GUI, "RefreshActionIconFor") then done = false end
            if not InstallTarget("gse", gse.GUI, "RefreshMacroEditorColoredText") then done = false end
        else
            done = false
        end
        return done
    end,
}

-- 兜底扫描：hook 没触发但数据变了，至少留下"什么变了" --------------------------

local function Sweep()
    local session = state.session
    if not (session and session.armed) then return end
    local sequence, version = state.lastSequence, state.lastVersion
    if not (sequence and version) then return end
    local actions = SequenceActions(sequence, version)
    if not actions then return end

    local changed = {}
    for keyPath, action in pairs(actions) do
        local after = AddonProbe.Snapshot(action)
        local before = state.baseline[keyPath]
        if before and #AddonProbe.ChangedFields(before, after) > 0 then
            changed[#changed + 1] = keyPath
        end
    end
    table.sort(changed, function(left, right) return tostring(left) < tostring(right) end)
    for _, keyPath in ipairs(changed) do
        WriteRecord(sequence, version, keyPath, "ticker")
    end
end

-- 命令 ----------------------------------------------------------------------

local function HandleCommand(input)
    local command, rest = string.match(input or "", "^%s*(%S*)%s*(.-)%s*$")
    if command == nil or command == "" or command == "status" then
        Status()
    elseif command == "start" then
        BeginSession()
    elseif command == "stop" then
        EndSession()
    elseif command == "mark" then
        Mark(rest)
    elseif command == "clear" then
        Clear()
    else
        Say("用法：/probe start | mark <说明> | stop | status | clear")
    end
end

local slashCommands = rawget(_G, "SlashCmdList")
if slashCommands then
    rawset(_G, "SLASH_ADDONPROBE1", "/probe")
    slashCommands.ADDONPROBE = HandleCommand
end

-- 装载 ----------------------------------------------------------------------

local function InstallPresets()
    local all = true
    for _, installer in pairs(INSTALLERS) do
        if not installer() then all = false end
    end
    return all
end

-- 常驻重试：目标随时可能出现（打开 GSE 编辑器才加载 GSE_GUI），所以不设次数上限。
-- 已挂上的目标在 InstallTarget 里短路，常态开销只是几次表查询。
local function TryInstall()
    InstallCaptureHooks()
    InstallPresets()
    InstallCreateHook()
    ScanPool()
end

-- 文件作用域先试一次：万一本插件加载晚于某个子模块，这里就能补上入口钩子
InstallCaptureHooks()

if C_Timer and C_Timer.NewTicker then
    -- 0.5 秒一拍：先扫池子（抓框，与是否在采集无关），再做数据兜底扫描
    C_Timer.NewTicker(SWEEP_INTERVAL, function()
        ScanPool()
        Sweep()
    end)
    C_Timer.NewTicker(INSTALL_INTERVAL, TryInstall)
end

local events = CreateFrame("Frame")
if events then
    events:RegisterEvent("PLAYER_LOGIN")
    events:RegisterEvent("ADDON_LOADED")
    -- 子模块 ADDON_LOADED 先于 GSE 自己的派发器执行（本插件加载更早），
    -- 所以这里挂上的入口钩子能在 GSE 把私有表推进去之前就位
    events:SetScript("OnEvent", function()
        GetDB()
        TryInstall()
    end)
end
