# GSE #2106：删除一个动作块把其它 spell 动作改写成 macro

> 状态：调研结论（2026-09-17）。**待归类**——本文件暂放 `docs/` 根，见 `docs/` 整理提案。
> 对象：第三方插件 GSE（TimothyLuke/GSE-Advanced-Macro-Compiler）3.3.34，本机实机复现。

## 结论（一段话）

GSE 编辑器**分帧延迟重建**（`buildChunk`，每帧 4 个动作块）在删除动作后若干帧才给动作块的文本框灌文本
（`spellEditBox:SetText` / `macroEditBox:SetText`）；这次灌文本会经引擎的 `OnTextChanged` 桥触发
macro 框的处理器（`Editor.lua:8012`），而该处理器用**创建时捕获的 keyPath** 无条件写
`.macro`、清 `.spell`，且不校验"这只框现在还属于这个 block" —— 于是**回收控件上的陈旧回调**改写了别的动作，
表现为"删一行，其它行变红"。3.3.33-a 的修复（`e446d5b`）针对的是 `OnRelease` → `IndentationLib.disable()`
那条拆解期路径，覆盖不到这一条。

## 复现

- 环境：retail 12.1.0.69814 / zhCN / widget pool 开启（默认）；GSE 3.3.34。
- 步骤：导入问题里的序列 → 编辑器里删除一个动作块。
- 结果：**36 个动作**被改写，分 7 波，单波最多 13 个；`{type="spell", spell=49998}` →
  `{type="spell", spell=nil, macro="灵界打击"}`（本地化技能名）；**无 Lua 报错**。
- 对照：`/run GSE_NoWidgetPool = true` + reload → 零改写。

## 证据链（全部实机采集）

写入口（macro 框处理器经引擎桥被触发）：

```
[C]: in function 'RefreshActionIconFor'
GSE_GUI/Editor.lua:8031: in function <8012>    ← macro 框 OnTextChanged 处理器
[tail call]: ?  ×2                             ← GSE 自己的 Fire / callCallback
GSE_GUI/NativeUI.lua:2858: in function <...>   ← MultiLineEditBox 的引擎桥
```

触发者（8 条 SetText 调用栈，全部同一条链）：

```
[C]: in function 'SetText'
GSE_GUI/Editor.lua:7927: in function <7864>    ← spellEditBox:SetText(spelltext)
[C]: in function 'CreateSpellEditBox'
GSE_GUI/Editor.lua:5343: in function <5077>    ← drawAction
GSE_GUI/Editor.lua:6352: in function 'job'     ← 分帧队列 buildChunk（每帧 4 块）
GSE_GUI/Editor.lua:6377: in function <6358>
```

"同一只框"配对（14/36）：`pairBox == setTextBox == fireBox`，`pairAge ≈ 0`——同一框实例在同一瞬间
既收到 `SetText` 又触发处理器。分布：box17 改写 8 个动作、box37 5 个、box33 1 个 = 一个回收框在一轮重建里
被多个块复用。

同族但无文本参与：`resetForReuse` 的 `eb:SetText("")`（`NativeUI.lua:6201`）**同样触发 OnTextChanged**，
所以回收时陈旧回调也会跑。

## 为什么 3.3.33-a 的修复拦不住

- `e446d5b` 的两处改动：`Release()` 里 `self.callbacks = {}`（在 `OnRelease` **之后**）、
  `resetForReuse` 里先剥 `IndentationLib`。两处都针对**拆解期**那条
  `IndentationLib.disable()` → `SetText` → 活处理器。
- 本次栈里**既没有 `IndentationLib` 也没有 `Release`**：火警来自**延迟绘制**，经引擎桥到达一个
  **本拍没被 release** 的框。
- `buildChunk` 有 `buildGeneration` 守卫（`Editor.lua:6364`），防的是"往已拆掉的容器里画"，
  防不了"回收框触发旧生命的回调"。

## 建议方向（给维护者）

与其逐个堵生命周期漏洞，不如**让写入端 fail-safe**：把处理器绑到创建它的那个 block，
不再属于它时直接 no-op（例如创建时在框上存 action/path，写入前要求 `box.gseAction == action`，
或用一次性生命令牌），外加 `Actions[keyPath]` 的 nil 守卫。这样无论哪条路径触发都不会写错对象。

## 采集工具与已知局限

- 工具：`addons/AddonProbe/`（`/probe start|mark|stop`，本仓库自有探针；自检落盘见会话 `diagnostics`）。
  它通过子模块入口 `<子模块>_Initialize(gse)` 截获 GSE 私有表（`_G.GSE` 自 3.3.x 起只是四字段公开代理）。
- 原始数据：`WTF\Account\<账号>\SavedVariables\AddonProbe.lua`（本机 `DONGYI_CHAO`）。
- 局限：火警用 `HookScript` 挂在 GSE 桥**之后**，单次触发的框在写入那一刻缓冲里还没有对应火警，
  所以 14/36 能配对而非全部；机制对其余 22 条相同。
- 回帖草稿：`.local/gse-2106-reply.md`（英文，未发送）。
