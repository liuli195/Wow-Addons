# GSE 3.3.32 导入语法与宏解释研究

本文固定 GSE（高级按键序列插件）上游为提交 [`f225d4c947d168c63451ef7c567d7063c38cc239`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/tree/f225d4c947d168c63451ef7c567d7063c38cc239)，目标为本仓库锁定的 WoW 12.1 正式服。上游源码副本位于 `.tools/sim2gse-research/gse-f225d4c/`。本地复核入口主要是 [`Serialisation.lua`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Serialisation.lua)、[`Utils.lua`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_Utils/Utils.lua) 和 [`Storage.lua`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua)。后续 GSE 版本不自动纳入本结论。

## 四层结果各自代表什么

| 层 | 负责回答 | 成功能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| GSE 原串解析 | 能否解码外壳、列出成员和版本、保留字段、识别块及来源位置 | 锁定格式可被无损读取 | 控制块一定能执行或宏一定能解释 |
| GSE 控制展开 | Action、Repeat、Loop、Pause、If、Embed 如何成为逐次点击计划 | 计划符合锁定 GSE 的控制顺序 | 每个点击都对应角色可用技能 |
| WoW 宏解释 | `/cast`、`/use` 等命令及方括号条件在给定场景下是什么意思 | 既有解释器可表达的动作和拒绝原因 | 未实现的游戏状态、修饰键或宏语法已被求值 |
| DPS 模拟 | 角色动作能否交给本机受控伤害引擎计算 | 在指定输入与模型下得到一项模拟结果 | GSE 语法完整、或等于游戏实测伤害 |

本次 09 票验收第一层和锁定版本内的 GSE 控制结构。宏正文须原样保留；宏命令的已有有限处理将在 10 票与 GSE 控制层拆开。宏不能被忠实表达时必须带原文位置说明拒绝，不能跳过命令再算 DPS。

## 锁定上游的导入格式矩阵

`GSE.EncodeMessage` 将 Lua 表写为 CBOR（二进制对象格式），压缩后进行 Base64（文本编码）；`GSE.DecodeMessage` 区分普通和 `+` 受保护外壳。受保护串还含密钥编号，其密钥和解码能力受锁定上游约束。GSE 集合的最外层是 `type="COLLECTION"` 与 `payload`，其中 `Sequences`、`Variables`、`Macros` 按名称收纳对象。细节见固定提交的 [序列化代码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Serialisation.lua#L13-L24) 和 [导入分派代码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_Utils/Utils.lua#L434-L529)。

| 对象或成员 | 锁定上游接受的形式 | 检查与保留要求 |
| --- | --- | --- |
| 普通外壳 | `!GSE3!` + Base64 压缩 CBOR | 解码后按 CBOR 中的表、数组和值保留原始载荷；畸形 Base64、压缩流或 CBOR 明确报错 |
| 受保护外壳 | `!GSE3!+` + 上游密钥编号 + Base64 受保护内容 | 仅接受已锁定的密钥与受支持对象；未知密钥、短随机数、解密失败和资源超限明确报错 |
| 单序列 | `[名称, 序列对象]`；或带 `MetaData.Name` 与 `Versions` 的序列对象 | 保留名称、完整字段、版本号和数组顺序；不把解析等同于模拟 |
| 集合 | `{type: "COLLECTION", payload: {Sequences, Variables, Macros}}` | 保存集合原始载荷；成员来源路径含集合类别和成员键 |
| `Sequences` 成员 | 原始序列表；普通 `!GSE3!` 编码的 `[内部名, 序列表]` 或带 `MetaData.Name` 的序列表；普通编码的嵌套 `COLLECTION`、变量/宏；受保护编码序列；Delta fork 对象 | 编码 pair 使用内部名，直接序列表保留已有 `MetaData.Name`；只有原始 table 缺少该名称时上游才注入外层键。受保护串直接以外层键存储。未编码数组 pair 会先被注入外层 `MetaData.Name`，通用导入器再把整张数组作为序列载荷；顶层缺 `MetaData.GSEVersion`，所以锁定上游拒绝导入。本地检查器保留原始 pair 与第二项的只读结构预览，并报告兼容性阻断，禁止模拟 |
| `Variables` / `Macros` 成员 | 受保护编码对象、普通 `!GSE3!` 编码对象或集合；带有效序列字段的原始 table/数组 pair；Delta fork 对象 | 受保护串由所属分类按外层键直接存储；普通编码串和原始 table/数组 pair 递归进入通用导入器，解出的 `VARIABLE` / `MACRO` 按内部 `name` 分派，可能跨入另一分类；序列形状按内部 pair 名或 `MetaData.Name` 导入。原始序列形状缺少导入必需的名称、`Versions` 或有效 `GSEVersion` 时带路径拒绝；原始载荷仍原样保留 |
| 独立变量或宏对象 | 普通或受保护编码对象，分别以 `objectType="VARIABLE"` 或 `"MACRO"` 标识，且需有非空 `name` 才能按成员名展示 | 本票新增普通编码对象识别；完整载荷和自定义字段留存，不改写宏文本或变量表达式；响应的 `object_type` 表示普通与受保护对象类型，`protected_object_type` 只用于受保护外壳 |

CBOR 对象允许保留锁定编译器当前不使用的字段，因此字段表不是封闭白名单。缺少 `Type`、未知块类型、错误容器或超出资源边界时，不得改成空块并继续报“完整解析”。

锁定的 `Utils.lua` 会对普通编码成员再次调用 `ImportSerialisedSequence`。非保护串按解码后的 `objectType` 或序列内部身份分派；因此外层集合键仅是来源位置，不能覆盖合法内部名称。`Sequences` 中的原始 table 在调用前仅补入缺失的 `MetaData.Name`，显式名称保持不变；普通编码串不会走这段补名逻辑。`Variables` / `Macros` 的受保护串直接按外层分类和键存储，普通串与原始 table 则递归分派。若解出 `type="COLLECTION"`，继续按 `Variables`、`Sequences`、`Macros` 三类递归导入。三类的处理顺序有源码依据，但每类内部用 Lua `pairs` 遍历，顺序不确定；若递归结果在同一类中出现重名，后写覆盖哪个对象无法静态确定。本地检查器因此保留最外层完整 `raw_payload`、报告全部冲突来源并把该名称从可选成员列表移除，不猜测游戏内最终胜者。递归最多 32 层、累计最多 10,000 个集合成员、所有层合计最多解码 4 MiB；坏编码和越界会带来源路径拒绝。

真实语料 `mob-guardian-01.txt` 的 `payload.Sequences[MOB_Guardian_Elunes]` 使用未编码数组 pair `[同名, 序列对象]`，数组第二项具有 `MetaData.Name`、`MetaData.GSEVersion` 和 `Versions`。锁定上游 `Utils.lua:496-500` 给**数组自身**加 `MetaData.Name`；`:544-550` 因此把整张数组交给 `processWAGOImport`；`:556-575` 检查的是数组自身的 `MetaData.GSEVersion`，该字段缺失，故该成员不会存入 GSE。当前 `inspect` 仍从第二项生成只读结构预览，以外层键展示，并在 `collection_compatibility_blocks` 逐项说明上游会拒绝；所有版本的模拟预检为 `unsupported`。原始数组仍在 `raw_payload` 与 `raw_sequence` 内完整保留。这恢复了语料 16/16 的无损检查结果，不把上游拒绝成员称为可导入或可模拟。

`Variables` / `Macros` 中另一种合法原始成员是带有效 `MetaData.Name`、`MetaData.GSEVersion`、`Versions` 的直接序列表，或 `[内部名, 序列对象]` 数组 pair。两类都需按通用 `ImportSerialisedSequence` 解析；原始 pair 在这两个分类中**不**会走 `Sequences` 的 `MetaData.Name` 注入分支，因此由 `[1]` 作为内部身份导入。合成向量分别覆盖两个分类中的直接 table、数组 pair，并在同一集合里把受保护变量/宏放在不同外层键下，确认受保护对象仍按所属类别和外层键展示。

## 六类控制块与有语义的字段

六种类型由上游 [`Statics.lua`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Statics.lua#L439-L445) 定义；展开逻辑位于 [`Storage.lua`](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2284-L2452)。下表列出控制器当前读作语义的字段。所有未列出的字段仍属于原对象，检查结果必须保留。

| 块 | 有语义的字段 | 结构与解析要求 |
| --- | --- | --- |
| `Action`（动作） | `Type`、`Disabled`、动作子类型 `type`、`spell`、`item`、`macro` / 旧字段 `macrotext`、宠物命令 `action`、`toy`；额外属性也原样保留 | 单个动作对象；不解释宏文本作为语法字段之外的条件和命令 |
| `Repeat`（定期重复） | `Type`、同 `Action` 的动作字段、`Interval`；兼容旧输入时从 `Repeat` 读取间隔 | 仍保留为一类独立块；间隔的默认和旧字段行为按锁定编译器核对 |
| `Loop`（循环） | `Type`、`Disabled`、循环次数 `Repeat`、`StepFunction` | 数字键 `1..n` 为子动作；步进值含 Sequential、Priority、ReversePriority、Random |
| `Pause`（暂停） | `Type`、`Disabled`、点击数 `Clicks`、时长 `MS` | 点击和时长同时保留；`MS` 可含锁定上游的 GCD 特殊值 |
| `If`（条件） | `Type`、`Disabled`、表达式 `Variable` | 数字键 `1`、`2` 分别是两条分支；表达式原样保留，前置 `=` 也不能在原文字段中丢失 |
| `Embed`（嵌入序列） | `Type`、`Disabled`、引用名 `Sequence` | 引用名和来源路径保留；引用缺失或版本无法选择属于编译/模拟阻断，不伪装成解析失败 |

序列和版本对象中的未知字段、显式空值、数值键类型、嵌套容器与原始 CBOR 字节都需保留。原始语法出现 `Pause` 或 `Embed` 只证明相应块被识别；暂停/引用如何进入点击计划属于第二层。

## 真实语料与合成向量分开记录

上一轮 07 票在受测版本上记录了 16 个本机真实原串文件、15 个不同 SHA-256（含 1 个重复文件），覆盖 21 组文件级成员/版本；按原串摘要去重为 20 组。公开 `POST /api/gse/inspect` 当时 16/16 返回 `decoded`，21/21 成员版本均返回，兼容性阻断数为 0。这是 07 票的历史证据，不是本票代码修改后的复跑结果。

该轮真实原串中六类块数为：Action 268、Repeat 30、Loop 20、If 4、Pause 2、Embed 2。此处按原串统计控制块，不含本文件下方的固定合成向量。21 组版本中，19 组为 `unsupported`、2 组为 `requires_character_validation`；inspect 均没有启动模拟。真实解析通过不代表宏可执行、角色映射完成或得到 DPS。历史汇总见 [语料说明](gse-import-corpus.md)、[07 票记录](../../myspec/changes/sim2gse-gse-import/issues/07-real-corpus-final-inspection.md)；原始导入串位于 Git 忽略的 `.local/sim2gse/`，本文不复制。

09 票代码修改后再次逐文件通过本地临时服务调用公开 `POST /api/gse/inspect`：16/16 文件返回 `decoded`，21/21 成员与版本返回，1 个兼容性阻断（`MOB_Guardian_Elunes` 原始数组 pair 经上游拒绝）；六类计数仍为 Action 268、Repeat 30、Loop 20、If 4、Pause 2、Embed 2。聚合输出为 `{"compatibility_blocks":1,"decoded":16,"failures":[],"files":16,"members":21,"syntax":{"Action":268,"Embed":2,"If":4,"Loop":20,"Pause":2,"Repeat":30},"versions":21}`。本次没有保存新的原串或逐文件响应；复跑汇总保存在本研究文档和 09 票 Comments，不含原串。该次只检查导入结构和字段，不启动模拟；原串仅从本机语料文件读取并提交到本地检查接口，未另行复制或保存，也不代表游戏内验收。

合成向量只用于填补真实语料未充分覆盖的结构，不加入上述文件数、成员版本数或块数：

- 普通单序列、直接序列对象、普通集合对象，以及六块组合/嵌套结构：`tests/sim2gse/test_interface.py` 与 `tests/sim2gse/test_program.py`。
- 固定受保护序列、变量、宏和集合内受保护序列：`GSE_PROTECTED_*_VECTOR` 常量及对应 inspect 用例。
- 本票新增的集合内普通 `!GSE3!` 编码序列、独立普通 `VARIABLE` 和 `MACRO`：`test_import_inspection_decodes_unprotected_sequence_string_inside_collection`、`test_import_inspection_decodes_unprotected_standalone_variable_and_macro`。本次后续复核锁定导入分派，又通过公开入口覆盖普通编码 pair/direct sequence 的内层身份、显式 `MetaData.Name` 原始序列表、跨分类 `VARIABLE/MACRO`、`Variables` / `Macros` 中原始 table 与 pair 分派，以及 GSE 会拒绝的原始 Sequences 数组 pair：`test_import_inspection_uses_inner_sequence_identity_for_plain_members`、`test_import_inspection_dispatches_plain_encoded_collection_members_by_object_type`、`test_import_inspection_dispatches_raw_sequence_tables_from_variables_and_macros`、`test_import_inspection_reports_gse_rejection_of_raw_collection_sequence_pair`。被拒绝的 Sequences pair 用例在公开 inspect 先 HTTP 400 红灯，修复后 `decoded` 并带阻断，模拟任务也被 HTTP 400 拒绝；身份/类型旧实现为 2 failed，修复后通过。未编码原始 Sequences 数组 pair 是结构可展示但上游不可导入，不能把它算作合法导入语法。
- 普通编码多成员子集合、子集合变量/宏、完整路径、坏编码、递归深度、4 MiB 总解码预算与重名歧义：`test_import_inspection_recursively_expands_plain_nested_collection_members`、`test_import_inspection_rejects_bad_encoded_member_in_nested_collection_with_path`、`test_import_inspection_rejects_nested_collection_depth_over_limit`、`test_import_inspection_enforces_total_decoded_bytes_across_nested_members`、`test_import_inspection_counts_plain_encoded_object_once_within_total_budget`、`test_import_inspection_marks_nested_sequence_name_collision_ambiguous`。这些是合成向量，不计入真实语料统计；2.2 MB 普通编码变量用例验证单对象不会被预算双计。

新增子集合测试的红绿证据：普通多成员/变量/宏用例与坏编码定位用例先运行 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k "recursively_expands_plain_nested_collection_members or rejects_bad_encoded_member_in_nested_collection_with_path"`，结果为 2 failed、72 deselected；修复后同命令为 2 passed、72 deselected。总解码字节预算先运行 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k enforces_total_decoded_bytes_across_nested_members`，结果为 1 failed、76 deselected（超限输入未被拒绝）；加入总预算后，该用例与其他七项回归合并运行，结果为 8 passed、69 deselected。普通编码成员和独立变量/宏两项缺口也分别先在公开接口得到 HTTP 400，再经相同端点绿灯；测试名见上文。

最终语法与公开接口回归命令 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py tests/sim2gse/test_program.py -q` 结果为 117 passed、52 个子检查通过（87.61s）。该组包含既有畸形编码、受保护密钥、压缩资源边界和控制块来源路径用例。

当前仅有离线源代码和公开检查接口证据。没有在 WoW 实机导入这些语料，也没有完成游戏内伤害验收。

## 宏解释实现参考与适用边界

这些项目只供核对宏语义与拆分职责。此处只记录观察到的逻辑，不复制代码、数据表、注释或测试样例到本仓库。

| 实现 | 版本和许可 | 可借鉴的逻辑 | 不可直接套用的原因 |
| --- | --- | --- | --- |
| [MacroForge `Analyzer.lua`](https://github.com/kriffin/MacroForge/blob/main/Analyzer.lua)，[MIT 许可](https://github.com/kriffin/MacroForge/blob/main/LICENSE) | 面向 Retail（正式服）；README 安装路径为 `_retail_` | 动态收集游戏注册的斜杠命令；逐行检查命令；按 `;` 分支、方括号条件与逗号条件解析；报告行号和未知命令/条件；适合作为独立“识别并诊断”模块的结构参考 | 目标版本和本地已支持的命令不同；静态检查不是宏运行时，也不能替代 GSE 结构解析 |
| [CleveRoidMacros `Core.lua`](https://github.com/vargv666/CleveRoidMacros/blob/main/Core.lua) 与 [`Conditionals.lua`](https://github.com/vargv666/CleveRoidMacros/blob/main/Conditionals.lua)，[MIT 许可](https://github.com/vargv666/CleveRoidMacros/blob/main/LICENSE) | README 目标为 WoW 1.12.1，并建议/要求 SuperWoW、Nampower 的部分能力；项目说明包含 Turtle WoW 安装入口 | 将条件读取与动作选择分开；从左到右检查多个条件组；区分条件成立和目标动作；可用来发现经典宏与插件扩展条件的边界 | 经典客户端 API、外挂前提和大量插件自定义条件与 12.1 正式服不兼容，不把其条件表或运行逻辑直接迁入 |
| [JustAC `MacroParser.lua`](https://github.com/wealdly/JustAC/blob/main/MacroParser.lua)，[GPL-3.0-or-later 许可](https://github.com/wealdly/JustAC/blob/main/LICENSE) | 当前 README 标记适用于 12.1；用于查找动作条上匹配的按键技能 | 共用一条命令行遍历：`/cast`、`/use` 按 `;` 拆备选分支，`/castsequence` 按逗号拆技能并单独去掉 `reset=`；把场景条件解析与动作条查询分开；未处理的目标等条件会按模块目的忽略 | 这是查按键技能的子集，不是完整宏执行器；忽略条件会改变本项目的模拟含义。GPL-3.0-or-later 有再分发和衍生作品义务，本分支不复制其实现 |

**版权边界：** MIT 允许在保留版权和许可文本等条件下再用代码，但本研究只借鉴结构；GPL 代码不移植到本仓库；暴雪界面源码只用于确认对应客户端版本的行为，不复制源码。所有新增实现由本项目独立编写，并以本仓库固定上游和接口用例验证。

## 游戏内行为的原始资料

本仓库同客户端源码镜像 `.tools/wow-ui-source/` 用于锁定 12.1 行为；可浏览的上游入口是 [CastSequenceManager.lua](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_ChatFrameBase/Shared/CastSequenceManager.lua) 与 [SlashCommands.lua](https://github.com/Gethe/wow-ui-source/blob/live/Interface/AddOns/Blizzard_ChatFrameBase/Shared/SlashCommands.lua)。前者处理 `/castsequence` 的点击推进、重置条件和超时；后者展示命令怎样调用 `SecureCmdOptionParse` 与游戏动作 API（应用程序接口）。GitHub 的 `live` 分支会变化，遇到差异以本仓库为目标客户端锁定的源码副本为准。

这些文件用于核对宏执行行为的边界，不把游戏引擎中的宏解析器误作 GSE 文件解析器。能显示某条游戏命令已注册，也不代表本地 DPS 引擎可以模拟它。
