"""AddonProbe 的公开接缝：翻转规则、证据记录、兜底扫描。

规则必须能从 Lua 侧直接断言（AddonProbe.DetectFlip / AddonProbe.Snapshot /
AddonProbe.ChangedFields），记录必须落到 SavedVariables，供离线分析。
"""
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LUA = ROOT / ".tools/lua-5.1.5/src/lua.exe"
ADDON = ROOT / "addons/AddonProbe/Core.lua"

PRELUDE = r'''
local source = assert(arg[1])
local now = 100
local pending = {}
local secureHooks = {}
local messages = {}
local stackReads = 0

function GetTime() return now end
function print(message) messages[#messages + 1] = tostring(message) end
function debugstack()
    stackReads = stackReads + 1
    return "STACK:OnTextChanged\nSTACK:callCallback\nSTACK:IndentationLib.disable\n"
end

local eventFrame
local function NewFrame(name)
    local frame = { name = name, scripts = {}, events = {} }
    function frame:RegisterEvent(event) self.events[event] = true end
    function frame:SetScript(kind, callback) self.scripts[kind] = callback end
    function frame:GetName() return self.name end
    return frame
end

function CreateFrame(_, name)
    local frame = NewFrame(name)
    if not eventFrame then eventFrame = frame end
    if name then _G[name] = frame end
    return frame
end

C_Timer = {
    After = function(_, callback) pending[#pending + 1] = callback end,
    NewTicker = function(_, callback)
        pending[#pending + 1] = callback
        return { Cancel = function() end }
    end,
}

-- 与真实 hooksecurefunc 一致：包装原函数，先调原函数再调钩子
function hooksecurefunc(owner, name, callback)
    secureHooks[#secureHooks + 1] = { owner = owner, name = name, callback = callback }
    local original = owner[name]
    if type(original) == "function" then
        owner[name] = function(...)
            local results = { original(...) }
            callback(...)
            return unpack(results)
        end
    end
end

-- 12.x 战斗保密值哨兵：issecretvalue 只认它（与 Sim2GSEProbe 的测试写法一致）
secretSentinel = {}
function issecretvalue(value) return value == secretSentinel end

SlashCmdList = {}

-- 模拟真实 GSE 3.3.34 的形状：_G.GSE 只是四字段公开代理（GSE/API/Plugins.lua），
-- 真表由 GSE 私有持有，只经 GSE_Utils_Initialize(gse) 交付（GSE/API/Init.lua 的 pushGSEInto）
local function FakeGSE(real)
    real.CreateGSE3Button = real.CreateGSE3Button or function() end
    _G.GSE = {
        RegisterAddon = function() end,
        GetSequenceNamesFromLibrary = function() end,
        isEmpty = function(s) return s == nil or s == "" end,
        Statics = {},
    }
    function GSE_Utils_Initialize(gse) deliveredToSubmodule = gse end
    return real
end

local function FireSecure(owner, name, ...)
    for _, hook in ipairs(secureHooks) do
        if hook.owner == owner and hook.name == name then hook.callback(...) end
    end
end

local function FirePending()
    local queued = pending
    pending = {}
    for _, callback in ipairs(queued) do callback() end
end

local function Has(list, value)
    for _, item in ipairs(list or {}) do
        if item == value then return true end
    end
    return false
end
'''


def run_harness(harness):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "addonprobe_harness.lua"
        path.write_text(harness, encoding="utf-8")
        return subprocess.run(
            [str(LUA), str(path), str(ADDON)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )


def test_flip_rule_separates_rewrites_from_edits():
    harness = PRELUDE + r'''
assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe, "探针必须把规则挂在全局表上")

-- 规则 1：spell 没了、macro 出现 = 被脚本改写
assert(AddonProbe.DetectFlip({ spell = "49020" }, { macro = "符文刃舞" }) == true)
-- 规则 2：spell 换成另一个 spell = 正常编辑
assert(AddonProbe.DetectFlip({ spell = "49020" }, { spell = "47541" }) == false)
-- 规则 3：spell 还在、只是多了 macro 文本 = 用户在敲键盘
assert(AddonProbe.DetectFlip({ spell = "49020" }, { spell = "49020", macro = "x" }) == false)
-- 规则 4：没有基线时不判定
assert(AddonProbe.DetectFlip(nil, { macro = "x" }) == false)
-- 规则 5：快照只收受跟踪字段，值归一成字符串
local snapshot = AddonProbe.Snapshot({ type = "spell", spell = 49020, Icon = 5 })
assert(snapshot.spell == "49020" and snapshot.type == "spell")
assert(snapshot.Icon == nil)
-- 规则 6：只列出真正变化的字段
local changed = AddonProbe.ChangedFields({ spell = "1" }, { spell = "1", macro = "x" })
assert(#changed == 1 and changed[1] == "macro")
-- 规则 7：记录有上限，超出后停止并标记 truncated（SavedVariables 不能失控）
assert(AddonProbe.MAX_RECORDS > 0)
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
for index = 1, AddonProbe.MAX_RECORDS + 5 do commands("mark " .. index) end
commands("stop")
local capped = assert(_G.AddonProbeDB).sessions[#_G.AddonProbeDB.sessions]
assert(#capped.records == AddonProbe.MAX_RECORDS and capped.truncated == true,
    "超出上限要停止记录并置 truncated")
io.write("PASS: flip rules\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: flip rules" in result.stdout


def test_probe_records_rewrite_with_stack_and_fallback():
    harness = PRELUDE + r'''
local sequence = {
    MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = {
        ["1"] = { type = "spell", spell = 49998 },
        ["2"] = { type = "spell", spell = 49020 },
    } } },
}
local function Action(keyPath)
    return sequence.Versions[1].Actions[keyPath]
end

local real = { GUI = {} }
function real.GUI.RefreshActionIconFor() end
function real.CreateSpellEditBox() end
FakeGSE(real)

assert(loadfile(source))()
assert(SLASH_ADDONPROBE1 == "/probe")
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local commands = assert(_G.SlashCmdList).ADDONPROBE

-- 第一段：hook 路径。渲染取基线 -> 陈旧闭包改写 -> 记录
commands("start")
FireSecure(real, "CreateSpellEditBox", Action("2"), 1, "2", sequence)
now = 101
commands("mark 删掉第 1 行")
now = 102
Action("2").macro = "符文刃舞"
Action("2").spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "2")
now = 103
commands("stop")

local session = assert(_G.AddonProbeDB).sessions[#_G.AddonProbeDB.sessions]
assert(session.armed == false, "stop 之后会话必须关闭")
local write, mark
for _, record in ipairs(session.records) do
    if record.kind == "write" then write = record end
    if record.kind == "mark" then mark = record end
end
assert(mark and mark.label == "删掉第 1 行", "mark 必须进入时间线")
assert(write and write.flip == true, "应记录并判定为翻转")
assert(write.preset == "gse" and write.detectedBy == "hook")
assert(write.sequence == "TESTSEQ" and write.version == 1 and write.keyPath == "2")
assert(write.before.spell == "49020" and write.after.spell == nil)
assert(write.after.macro == "符文刃舞")
assert(Has(write.changed, "spell") and Has(write.changed, "macro"))
assert(write.stack and string.find(write.stack, "IndentationLib.disable", 1, true),
    "翻转必须带调用栈")

-- 第二段：正常换 spell 不能误报
commands("start")
FireSecure(real, "CreateSpellEditBox", Action("1"), 1, "1", sequence)
now = 110
Action("1").spell = 47541
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "1")
now = 111
commands("stop")
assert(_G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records[1].flip == false,
    "正常替换 spell 不应判成翻转")

-- 第三段：hook 没触发的改写，靠 ticker 兜底
Action("2").macro = nil
Action("2").spell = 49020
commands("start")
FireSecure(real, "CreateSpellEditBox", Action("2"), 1, "2", sequence)
now = 120
Action("2").macro = "符文刃舞"
Action("2").spell = nil
FirePending()
now = 121
commands("stop")
local swept
for _, record in ipairs(_G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records) do
    if record.detectedBy == "ticker" then swept = record end
end
assert(swept and swept.flip == true, "ticker 兜底要抓到没走 hook 的改写")
assert(swept.stack == nil and swept.before.spell == "49020")
assert(stackReads > 0)
io.write("PASS: probe evidence\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: probe evidence" in result.stdout


def test_path_text_renders_keys_readably():
    """keyPath 有时是路径对象（表），记录里必须印成可读路径，不能是 table: 0x...。"""
    harness = PRELUDE + r'''
assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)

-- 普通键：原样
assert(AddonProbe.PathText(5) == "5")
assert(AddonProbe.PathText("12") == "12")
-- 路径对象：按层级拼
assert(AddonProbe.PathText({ 5 }) == "5")
assert(AddonProbe.PathText({ 1, 2 }) == "1/2")
assert(AddonProbe.PathText({ 1, 2, 3 }) == "1/2/3")
-- 混着非数字也能渲染，且不抛错
assert(AddonProbe.PathText({ 1, "a" }) == "1/a")
-- 读不出来的值走安全渲染
assert(AddonProbe.PathText(secretSentinel) == "unavailable")
-- nil / 空表
assert(AddonProbe.PathText(nil) == "?")
assert(AddonProbe.PathText({}) == "?")
io.write("PASS: path text\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: path text" in result.stdout


def test_settext_trail_pins_the_caller():
    """程序化 SetText 是 OnTextChanged 的触发源；它的调用者只能在 SetText 自己的钩子里取到。"""
    harness = PRELUDE + r'''
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = { ["3"] = { type = "spell", spell = 49998 } } } } }
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")

-- 一个 GSE 动作块的 macro 框：包装器 + 内层 EditBox
local inner = { text = "" }
function inner:SetText(text) self.text = text end
local widget = { editBox = inner }
function widget:SetText(text) self.editBox:SetText(text) end

local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
-- GSE 的重绘会带着 widget 进来：探针借此在内层 EditBox 上装 SetText 钩子
FireSecure(real.GUI, "RefreshMacroEditorColoredText", widget, "灵界打击")
assert(AddonProbe.BoxHooks() == 1, "应当在内层 EditBox 上装好 SetText 钩子：" .. AddonProbe.BoxHooks())

-- 程序化 SetText（真实里由重建/重绘触发）
now = 500
inner:SetText("灵界打击")

-- 紧接着发生翻转：应把这次 SetText 的调用栈挂上去
FireSecure(real, "CreateSpellEditBox", sequence.Versions[1].Actions["3"], 1, "3", sequence)
sequence.Versions[1].Actions["3"].macro = "灵界打击"
sequence.Versions[1].Actions["3"].spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "3")
commands("stop")

local session = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions]
local record = session.records[1]
assert(record.flip == true, "翻转要记下来")
assert(record.after.macro == "灵界打击")
assert(record.setTextStack and record.setTextStack:find("STACK", 1, true),
    "翻转记录必须挂上 SetText 的调用栈（tail call 抹不掉的入口）")
assert(type(record.setTextAge) == "number" and record.setTextAge >= 0, "要记距今多久")

-- 即使没配上，原始轨迹也要落盘，供离线比对
assert(session.setTextTrail and #session.setTextTrail == 1)
assert(session.setTextTrail[1].text == "灵界打击")
assert(session.setTextTrail[1].stack and session.setTextTrail[1].stack:find("STACK", 1, true))
io.write("PASS: settext trail\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: settext trail" in result.stdout


def test_pool_scan_reaches_macro_boxes_and_reports_coverage():
    """GSE 只在失焦重绘时把 macro 框交出来；改用 GSE.UI.widgetPool 扫，覆盖才稳。"""
    harness = PRELUDE + r'''
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = { ["3"] = { type = "spell", spell = 49998 } } } } }

-- GSE 的 macro 框：包装器 + 内层 EditBox（OnTextChanged 桥来自 GSE_GUI/NativeUI.lua）。
-- 每只包装器各有自己的内层框——真实情况就是如此，共用会让第二只漏钩。
local function MakeBox()
    local inner = { text = "", scripts = {} }
    function inner:SetText(text)
        self.text = text
        -- 引擎的真实签名是 (self, userInput)：第二个参数是布尔，不是文本。
        -- 沙箱必须照着来，否则"从参数取文本"的 bug 会被测试掩盖。
        if self.scripts.OnTextChanged then self.scripts.OnTextChanged(self, true) end
    end
    function inner:GetText() return self.text end
    function inner:GetScript(kind) return self.scripts[kind] end
    function inner:SetScript(kind, callback) self.scripts[kind] = callback end
    function inner:HookScript(kind, callback)
        local previous = self.scripts[kind]
        self.scripts[kind] = function(...)
            if previous then previous(...) end
            callback(...)
        end
    end
    inner.scripts.OnTextChanged =
        loadstring("return function() end", "@Interface/AddOns/GSE_GUI/NativeUI.lua")()
    local widget = { editBox = inner }
    function widget:SetText(text) self.editBox:SetText(text) end
    return widget
end

local widget = MakeBox()          -- 池子里那只
local created = MakeBox()         -- 创建点发放那只
local real = { GUI = {}, UI = { widgetPool = { MultiLineEditBox = { widget } } } }
function real.UI.Create(self, typeName)
    if typeName == "MultiLineEditBox" then return created, "第二个返回值" end
end
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")

-- 池子扫描：不需要任何失焦重绘，也应该把框钩上
FirePending()
assert(AddonProbe.BoxHooks() >= 1, "池子扫描必须钩上框：" .. AddonProbe.BoxHooks())

local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
FirePending()                        -- 让创建点钩子先挂上
local fromCreate, secondFromCreate = real.UI.Create(real.UI, "MultiLineEditBox")
assert(fromCreate == created, "UI:Create 的返回值不能被包装改掉")
assert(secondFromCreate == "第二个返回值", "包装必须保留全部返回值，不只第一个")
assert(AddonProbe.BoxHooks() >= 2, "创建点发放的控件也要钩上：" .. AddonProbe.BoxHooks())
now = 605
created:SetText("血液沸腾")          -- 走创建点拿到的框
now = 610
widget:SetText("灵界打击")           -- GSE 自己的包装器路径

FireSecure(real, "CreateSpellEditBox", sequence.Versions[1].Actions["3"], 1, "3", sequence)
sequence.Versions[1].Actions["3"].macro = "灵界打击"
sequence.Versions[1].Actions["3"].spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "3")
commands("stop")

local session = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions]
local record = session.records[1]
assert(record.flip == true)
-- 自检要落盘：库里就能看出覆盖有没有生效，不用靠聊天框
local d = assert(session.diagnostics, "会话必须写自检")
assert(d.setTextHooks >= 2, "SetText 钩子数")
assert(d.fireHooks >= 2, "火警钩子数（安装成败必须可见，不能再被 pcall 吞掉）")
assert(d.createHooked == true, "UI:Create 钩子挂载状态")
assert(d.poolSeen >= 1, "池子扫描必须报告看见过控件（不是只算新钩上的）")
assert(d.poolHooked >= 1, "池子里新钩上的控件数")
assert(d.fires >= 2, "火警条数")
assert(d.hooks ~= nil, "钩子挂载状态")
-- 两只框各一条 SetText（包装器转发到内层，同一次调用不重复）
assert(session.setTextTrail and #session.setTextTrail == 2, "两条 SetText 都要记，且各自不重复")
local setTextEntry
for _, entry in ipairs(session.setTextTrail) do
    if entry.text == "灵界打击" then setTextEntry = entry end
end
assert(setTextEntry and setTextEntry.box == "box1", "轨迹要带框编号，好和火警对号")
-- 火警：不依赖 SetText 也能记下来，并带框编号与栈
assert(session.setTextFires and #session.setTextFires == 2)
local fireEntry
for _, entry in ipairs(session.setTextFires) do
    if entry.text == "灵界打击" then fireEntry = entry end
end
local fireSummary = {}
for _, entry in ipairs(session.setTextFires or {}) do
    fireSummary[#fireSummary + 1] = tostring(entry.box) .. "=" .. tostring(entry.text)
end
assert(fireEntry and fireEntry.box == "box1", "火警要带框编号：" .. table.concat(fireSummary, ", "))
-- 文本必须从框上读（box:GetText()），不能取回调参数（那是 userInput 布尔）
assert(fireEntry.text == "灵界打击", "火警文本要从框上读，实得：" .. tostring(fireEntry.text))
assert(fireEntry.stack and fireEntry.stack:find("STACK", 1, true))
-- 翻转要同时挂上 SetText 与火警两条线
assert(record.setTextStack and record.fireStack, "翻转必须同时挂 SetText 栈与火警栈")
assert(record.fireBox == "box1" and type(record.fireAge) == "number")
-- ★ 同【一只框】的证明：SetText 与火警必须落在同一个框编号上
assert(record.pairBox == "box1", "必须配出同一只框：" .. tostring(record.pairBox))
assert(record.setTextBox == record.fireBox, "两条线的框编号必须一致")
assert(type(record.pairAge) == "number")
io.write("PASS: pool scan\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: pool scan" in result.stdout


def test_watch_without_preset_records_a_generic_call():
    """需求：任意表上的具名函数都要能挂——没有预设处理器时走通用记录路径。"""
    harness = PRELUDE + r'''
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")

-- 一个与任何预设无关的目标
local arbitrary = { Counter = 0 }
function arbitrary:DoThing(first, second) self.Counter = self.Counter + 1 end

assert(AddonProbe.Watch(arbitrary, "DoThing") == true, "任意具名函数都要能挂上")

local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
now = 700
arbitrary:DoThing("甲", 42)
commands("stop")

local records = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records
assert(#records == 1 and records[1].kind == "call", "通用记录要落盘")
assert(records[1].fn == "DoThing", "记录要带函数名")
assert(records[1].stack and records[1].stack:find("STACK", 1, true), "通用记录也要带调用栈")
-- 参数原样记录（第一个是 self，渲染成字符串）；索引因此从 2 起
assert(records[1].args and records[1].args[2] == "甲" and records[1].args[3] == "42",
    "参数摘要：" .. table.concat(records[1].args or {}, ","))
io.write("PASS: generic watch\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: generic watch" in result.stdout


def test_logout_flushes_an_armed_session():
    """忘记 /probe stop 就 /reload 或掉线时，自检与轨迹必须仍然落盘。"""
    harness = PRELUDE + r'''
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")                      -- 故意不 stop
now = 800

eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGOUT")

local session = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions]
assert(session.armed == false, "登出必须关闭仍开着的会话")
assert(session.endedAt ~= nil, "登出必须写结束时间")
assert(session.diagnostics ~= nil, "登出必须落自检")
assert(session.setTextTrail ~= nil and session.setTextFires ~= nil, "登出必须落两条轨迹")
io.write("PASS: logout flush\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: logout flush" in result.stdout


def test_sweep_survives_an_unreadable_path_key():
    """扫尾排序不能因为键读不出来就中断整轮（键也要走安全渲染）。"""
    harness = PRELUDE + r'''
local throwing = setmetatable({}, { __tostring = function() error("secret key") end })
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = {
        ["2"] = { type = "spell", spell = 49020 },
        [throwing] = { type = "spell", spell = 49998 },
    } } } }
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")

-- 先建基线（普通键与不可读键各一）
real.CreateSpellEditBox(sequence.Versions[1].Actions["2"], 1, "2", sequence)
real.CreateSpellEditBox(sequence.Versions[1].Actions[throwing], 1, throwing, sequence)

-- 两者都变：排序时碰到读不出来的键也不能炸
sequence.Versions[1].Actions["2"].macro = "灵界打击"
sequence.Versions[1].Actions["2"].spell = nil
sequence.Versions[1].Actions[throwing].macro = "符文打击"
sequence.Versions[1].Actions[throwing].spell = nil
now = 900
FirePending()

local records = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records
assert(#records >= 1, "整轮扫描不能被不可读的键中断")
local found
for _, record in ipairs(records) do
    if record.keyPath == "2" then found = record end
end
assert(found and found.flip == true, "可读的那个键仍要被抓到")
io.write("PASS: unreadable key\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: unreadable key" in result.stdout


def test_late_targets_get_hooked_and_status_reports_gaps():
    """GSE_GUI 是 LoadOnDemand、CreateSpellEditBox 是懒创建：目标晚到也必须挂上。"""
    harness = PRELUDE + r'''
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = { ["2"] = { type = "spell", spell = 49020 } } } } }
local real = { GUI = {} }
function real.GUI.RefreshActionIconFor() end
-- 故意先不给 CreateSpellEditBox：真实情况它要等编辑器首次绘制才出现
FakeGSE(real)

assert(loadfile(source))()
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local AddonProbe = assert(_G.AddonProbe)

assert(string.find(AddonProbe.HookReport(), "1/3", 1, true),
    "要先挂上写入点并报出缺口：" .. AddonProbe.HookReport())

-- 迟到的目标出现后，常驻重试必须自己补挂
real.CreateSpellEditBox = function() end
FirePending()
assert(string.find(AddonProbe.HookReport(), "2/3", 1, true),
    "迟到的目标最终必须补挂：" .. AddonProbe.HookReport())

local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
FireSecure(real, "CreateSpellEditBox", sequence.Versions[1].Actions["2"], 1, "2", sequence)
now = 300
sequence.Versions[1].Actions["2"].macro = "符文刃舞"
sequence.Versions[1].Actions["2"].spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "2")
commands("stop")

local records = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records
assert(#records == 1 and records[1].flip == true, "补挂之后必须能抓到翻转")
assert(records[1].before.spell == "49020")
io.write("PASS: late targets\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: late targets" in result.stdout


def test_private_gse_table_is_captured_through_submodule_init():
    """GSE 3.3.x 的 _G.GSE 只是公开代理；真表只经由 <子模块>_Initialize(gse) 外流。"""
    harness = PRELUDE + r'''
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)   -- _G.GSE 变四字段公开代理；真表只经子模块入口交付

assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)

-- 子模块加载（真 GSE 会在这时把私有表推进来）：此刻探针必须先挂好入口钩子
eventFrame.scripts.OnEvent(eventFrame, "ADDON_LOADED", "GSE_Utils")
local report = AddonProbe.TargetReport()
assert(string.find(report, "GSE 公开代理 有", 1, true), report)
assert(string.find(report, "GSE 私有表 无", 1, true), "只有代理时不能当真表用：" .. report)

-- GSE 核心派发（GSE/API/Init.lua 的 pushGSEInto）
GSE_Utils_Initialize(real)
assert(deliveredToSubmodule == real, "钩子不能改变原函数的行为")

report = AddonProbe.TargetReport()
assert(string.find(report, "GSE 私有表 有", 1, true), "私有表必须被截下来：" .. report)

FirePending()   -- 常驻重试：拿到真表后把目标挂上
assert(string.find(AddonProbe.HookReport(), "3/3", 1, true), AddonProbe.HookReport())
io.write("PASS: private table capture\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: private table capture" in result.stdout


def test_status_reports_which_link_is_missing():
    """0/2 时必须能看出卡在哪一环（GSE 表 / GSE.GUI / 具体函数）。"""
    harness = PRELUDE + r'''
-- 真实现状：全局只有四字段公开代理，真表还没交付（界面模块是 LoadOnDemand）
local real = { GUI = {} }
function real.CreateSpellEditBox() end
function real.GUI.RefreshActionIconFor() end
function real.GUI.RefreshMacroEditorColoredText() end
FakeGSE(real)

assert(loadfile(source))()
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local AddonProbe = assert(_G.AddonProbe)

local report = AddonProbe.TargetReport()
assert(string.find(report, "GSE 公开代理 有", 1, true), report)
assert(string.find(report, "GSE 私有表 无", 1, true), report)
assert(string.find(report, "GSE.GUI 无", 1, true), report)
assert(string.find(report, "CreateSpellEditBox 无", 1, true), report)
assert(string.find(report, "RefreshActionIconFor 无", 1, true), report)

-- 用户可观察的接缝：status 要把这一行打出来
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("status")
assert(string.find(messages[#messages], "GSE 私有表 无", 1, true), messages[#messages])

-- GSE 核心交付真表（GSE/API/Init.lua 的 pushGSEInto）：报告要跟着变
GSE_Utils_Initialize(real)
FirePending()
report = AddonProbe.TargetReport()
assert(string.find(report, "GSE 私有表 有", 1, true), report)
assert(string.find(report, "GSE.GUI 有", 1, true), report)
assert(string.find(report, "RefreshActionIconFor 有", 1, true), report)
assert(string.find(AddonProbe.HookReport(), "3/3", 1, true), AddonProbe.HookReport())
io.write("PASS: target report\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: target report" in result.stdout


def test_first_write_fills_missing_baselines():
    """只有写入点钩子时：第一笔写入顺手给其它动作补基线，后续写入才有 before。"""
    harness = PRELUDE + r'''
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = {
        ["1"] = { type = "spell", spell = 49998 },
        ["3"] = { type = "spell", spell = 47541 },
    } } } }
local real = { GUI = {} }
function real.GUI.RefreshActionIconFor() end
FakeGSE(real)

assert(loadfile(source))()
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")

now = 400
sequence.Versions[1].Actions["3"].macro = "第一笔"
sequence.Versions[1].Actions["3"].spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "3")

now = 401
sequence.Versions[1].Actions["1"].macro = "第二笔"
sequence.Versions[1].Actions["1"].spell = nil
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "1")
commands("stop")

local records = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records
assert(#records == 2, "两笔都要留下")
assert(records[1].before == nil, "第一笔确实没有基线")
assert(records[2].before and records[2].before.spell == "49998", "第一笔顺手补的基线要生效")
assert(records[2].flip == true)
io.write("PASS: baseline fill\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: baseline fill" in result.stdout


def test_secret_values_degrade_instead_of_losing_the_record():
    harness = PRELUDE + r'''
local throwing = setmetatable({}, { __tostring = function() error("attempt to use a secret value") end })

-- 一个测试只加载一次插件：二次加载会让事件帧仍指向第一个实例，捕获钩子失效
local sequence = { MetaData = { Name = "TESTSEQ" },
    Versions = { [1] = { Actions = { ["3"] = { type = "spell", spell = 49998 } } } } }
local real = { GUI = {} }
function real.GUI.RefreshActionIconFor() end
function real.CreateSpellEditBox() end
FakeGSE(real)

assert(loadfile(source))()
local AddonProbe = assert(_G.AddonProbe)

-- 规则 1：读不出来的值一律记成 "unavailable"（与 Sim2GSEProbe 同一套词汇），不抛错
assert(AddonProbe.Scalar(secretSentinel) == "unavailable", "被 issecretvalue 标记的值")
assert(AddonProbe.Scalar(throwing) == "unavailable", "读取即报错的值")
-- 规则 2：能读的值不受影响
assert(AddonProbe.Scalar(49020) == "49020")
assert(AddonProbe.Scalar("符文刃舞") == "符文刃舞")
assert(AddonProbe.Scalar(nil) == nil)
-- 规则 3：单个字段读不出来，不能让整份快照失败
local snapshot = AddonProbe.Snapshot({ type = "spell", spell = secretSentinel, macro = "x" })
assert(snapshot.spell == "unavailable" and snapshot.macro == "x" and snapshot.type == "spell")

-- 端到端：走真实 hook 路径，遇到保密值必须留下记录（修复前整条丢失）
GSE_Utils_Initialize(real)
eventFrame.scripts.OnEvent(eventFrame, "PLAYER_LOGIN")
local commands = assert(_G.SlashCmdList).ADDONPROBE
commands("start")
FireSecure(real, "CreateSpellEditBox", sequence.Versions[1].Actions["3"], 1, "3", sequence)
now = 200
sequence.Versions[1].Actions["3"].spell = secretSentinel
FireSecure(real.GUI, "RefreshActionIconFor", sequence, 1, "3")
commands("stop")

local records = _G.AddonProbeDB.sessions[#_G.AddonProbeDB.sessions].records
assert(#records == 1, "遇到保密值必须保留记录，不能整条丢")
assert(records[1].before.spell == "49998")
assert(records[1].after.spell == "unavailable" and records[1].after.macro == nil)
assert(Has(records[1].changed, "spell"))
assert(records[1].flip == false, "读不出来就不能判定为翻转")
io.write("PASS: secret values degrade\n")
'''
    result = run_harness(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: secret values degrade" in result.stdout
