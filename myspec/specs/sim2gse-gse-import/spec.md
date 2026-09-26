# Sim2GSE GSE Import

## Purpose

让本机用户无损检查适用于锁定 GSE 3.3.32 上游的第三方导入序列，并区分结构解析、按键动作展开、角色可模拟性和正式服游戏内验收结果。

## Requirements

### Requirement: Sim2GSE inspects external GSE sequences before simulation

系统 MUST 按锁定 GSE 3.3.32 所接受的导入格式识别普通 `!GSE3!` Base64 压缩 CBOR（压缩二进制对象）外壳和受保护 `!GSE3!+` 外壳；受保护内容仅在其密钥编号与对象形态受锁定版本支持时才可继续。系统 MUST 识别单序列 `[名称, 序列对象]` 或具有 `MetaData.Name` 与 `Versions` 的序列对象，以及 `{type="COLLECTION", payload={Sequences, Variables, Macros}}` 集合。集合成员包括锁定版本接受的原始序列表、普通或受保护编码序列、普通编码 `[内部名, 序列对象]`、直接序列表、嵌套集合、Delta fork 序列对象，以及 `objectType="VARIABLE"` / `"MACRO"` 的独立变量或宏对象；变量和宏也可以包含锁定版本接受的序列形状。系统 MUST 按锁定版本解出后的对象身份和集合类别列出可识别成员及其全部版本；外层键、内部名称、版本身份和默认版本不得混为一项。超出锁定版本、无效或超限输入 MUST 给出明确诊断且不得启动模拟。结构已解码但锁定上游不接受的成员 MUST 单独显示兼容性阻断，不得伪报为可导入成员。

#### Scenario: A collection contains mixed encoded members and versions

- **WHEN** 用户提供可解码的普通或受保护集合串，其中含 `Sequences`、`Variables`、`Macros`、嵌套集合、普通编码成员或多个序列版本
- **THEN** 检查结果按锁定版本列出可识别的集合成员、对象类别、内部身份及每个版本，并允许用户明确选择可导入的序列成员和版本；独立变量或宏作为集合对象显示，不伪装成序列版本。

#### Scenario: A decoded member has a shape rejected by the locked importer

- **WHEN** 可解码集合中的原始成员形状不被锁定上游接受，例如未编码的 `Sequences` 数组 pair
- **THEN** 检查结果保留该成员的原始结构及集合来源位置，给出兼容性阻断，并将其标为不可模拟，而不把它作为有效序列选择或报告整个外壳解码失败。

#### Scenario: An envelope or version is invalid or unsupported

- **WHEN** Base64、压缩内容、CBOR、受保护密钥、对象字段或 GSE 版本不符合锁定范围，或输入超过公开资源限制
- **THEN** 系统报告能定位的外壳、对象或成员位置和拒绝原因，不生成可模拟序列或启动伤害模拟。
### Requirement: Sim2GSE preserves imported GSE data and exact source positions

检查结果 MUST 保留导入串中全量成员与版本的完整解码结构，包括未知字段、显式空值、数组顺序、数值键和文本键、禁用状态、变量表达式、宏原文及其换行；不得为了展示或选取而静默丢弃或改写这些值。任务结果 MUST 保留原始导入串以及所选成员和版本的完整解码结构与来源位置；不要求任务结果包含未选成员和版本的完整结构。系统 MUST 同时保留足以区分外层集合类别与键、内部名称、版本、嵌套控制块和宏行的来源位置；名称冲突或导入顺序不确定时 MUST 显示冲突来源并阻止含糊选择，不得猜选胜出成员。

#### Scenario: A sequence includes unknown fields and nested source locations

- **WHEN** 用户检查一个含未知自定义字段、多版本、嵌套控制块和多行宏文本的有效序列
- **THEN** 结果保留各字段原值和结构，列出外层成员键、内部身份、版本、控制块路径；发生宏语义拒绝时另指出宏行号，用户可将结果追溯到原导入位置。

#### Scenario: Two collection members resolve to the same ambiguous identity

- **WHEN** 不同成员路径产生同名对象，且锁定 GSE 顺序不能确定最终使用哪一个
- **THEN** 检查结果保留完整原始载荷，列出冲突的成员路径并阻止该身份被选择或模拟，不猜测其中一个成员已覆盖另一个。
### Requirement: Sim2GSE preserves GSE control flow in imported plans

系统 MUST 保留并识别 `Action`（动作）、`Repeat`（定期重复）、`Loop`（循环）、`Pause`（暂停）、`If`（条件分支）和 `Embed`（嵌入序列）六类控制块及其嵌套、禁用状态和来源。动作块的语义字段包括 `type`、`spell`、`item`、`macro` / 旧字段 `macrotext`、宠物 `action` 和 `toy`；重复块保留动作字段及 `Interval`（旧输入可从 `Repeat` 字段读取间隔），循环块保留数字子项、次数 `Repeat` 和 `StepFunction`，暂停块保留 `Clicks` 与 `MS`（含锁定上游支持的 `GCD`〔公共冷却〕特殊值），条件块保留 `Variable` 原表达式及数字键 `1`、`2` 对应的分支，嵌入块保留 `Sequence` 引用。系统 MUST 按锁定版本的固定控制规则生成可核对的逐次按键动作块：保留一次输入中合法的多个动作、`Sequential` / `Priority` / `ReversePriority` / `Random` 步进、重复间隔、暂停占用的按键或时间，以及条件分支和嵌入序列的来源；没有可按动作的推进仍须保留为空点击。无法确定的条件或引用不得静默跳过。

#### Scenario: A supported nested sequence expands to button steps

- **WHEN** 用户选择的版本包含可确定的 `Action`、`Repeat`、`Loop`、`Pause`、`If` 和 `Embed` 结构，且引用和分支均可按固定场景确定
- **THEN** 系统按锁定规则显示逐次按键动作块、空点击、循环步进、重复或暂停占用及完整嵌套来源，使展开结果可从所选版本追溯到每个原始块。

#### Scenario: A control block contains unrecognized fields

- **WHEN** 有效控制块带有当前语义未使用的额外字段
- **THEN** 系统保留额外字段和所属块，不把它们静默删除，也不把它们解释成新的宏命令或游戏状态。

#### Scenario: A decoded control block has no supported type

- **WHEN** 序列结构已解码，但某个控制块缺少 `Type` 或包含锁定版本不支持的 `Type`
- **THEN** 系统保留该块的原始结构和来源位置，将其标为不能忠实展开并阻止模拟；不得把它改成空点击或其他动作，也不得将已解码外壳误报为无法解析。
### Requirement: Sim2GSE simulates only faithfully mapped imported commands

遇到宏时，GSE 按键控制层 MUST 仅将宏原文、来源位置、给定场景和当前角色动作目录交给独立宏解释能力；控制层不得自行识别宏条件或命令。独立宏解释能力 MUST 负责现有范围内的条件与命令解释、预检、动作映射及从宏命令提取可映射的法术引用，不得扩大现有语义或增加宏命令、条件及游戏状态。

系统 MUST 在静态预检已知所选序列包含无法忠实表达的条件、命令、角色映射或引用阻断时，于提交伤害模拟任务前拒绝，并在拒绝原因中提供可定位的成员、版本、块路径或宏行。静态预检通过仅表示任务可提交，不保证伤害引擎一定能初始化或完成；若引擎在初始化阶段失败，系统 MUST 将任务报告为初始化失败并提供当时可用的错误信息，不生成 DPS，也不得将其报告为宏解析失败或模拟成功。对此类失败，系统 MUST 保留任务输入及可用的原生日志；公开结果 MUST 报告初始化阶段和现有错误信息，但不承诺公开错误包含精确来源路径。系统 MUST 不得删掉命令、猜测替换动作、扩展宏语法或游戏状态，也不得执行导入内容中的脚本代码。

#### Scenario: An existing macro condition cannot be evaluated

- **WHEN** 已解码宏含有当前场景无法确定的条件，例如 `[nochanneling]` 或依赖外部游戏变量的 `If`
- **THEN** 检查结果仍报告结构已解码，并在成员、版本、控制块或宏行的准确来源处说明条件不可确定；任务入口按同一原因拒绝，且不启动伤害模拟或给出 DPS。

#### Scenario: A statically known macro command cannot be represented

- **WHEN** 已解码宏包含当前模型无法忠实模拟的命令，例如 `/petattack`，或角色动作目录中缺少所需技能或物品
- **THEN** 检查结果保留宏原文并显示命令或映射阻断的准确来源位置；任务入口在创建伤害模拟任务前拒绝，不静默略过该动作、改用其他动作或生成 DPS。
### Requirement: Sim2GSE distinguishes import, simulation, and game validation outcomes

系统 MUST 将格式无效、结构已解码但不兼容、结构可解析但不可模拟、等待角色能力核验、任务已接受、引擎初始化失败、本机受控模拟完成及游戏内验收分别显示。宏语义或模拟能力不受支持时 MUST 把序列报告为已解码并附具体模拟阻断，而不得把宏拒绝称为 GSE 语法解析失败。仅已完成的本机受控模拟可以显示其 DPS、角色场景和可追溯动作路径；引擎初始化失败 MUST 不得显示 DPS 或成功状态。缺少正式服客户端验收证据时，游戏验证状态 MUST 显示 `not_run`，不得把离线检查、模拟完成或旧样本证据称为游戏内通过。

#### Scenario: Import structure decodes but the selected command blocks simulation

- **WHEN** `POST /api/gse/inspect` 能解码所选序列，但其宏条件或命令无法按给定场景模拟
- **THEN** 检查结果保留 `decoded` 结构并给出模拟拒绝原因和来源路径；导入任务入口以同一原因拒绝，页面不得显示语法解析失败或伤害成绩。

#### Scenario: A local imported simulation completes without a game test

- **WHEN** 所选序列通过角色映射并完成本机受控模拟，但没有对应正式服游戏内验收记录
- **THEN** 结果显示本机 DPS、所用成员与版本、场景条件和动作来源，并将游戏验证状态标为 `not_run`。

#### Scenario: The accepted task fails during engine initialization

- **WHEN** 静态预检通过并且任务入口以 HTTP 202（已接受）接收任务，但固定伤害引擎随后在初始化阶段拒绝所选动作组合，例如包含两个 GCD（公共冷却）动作块的序列
- **THEN** 任务结果显示初始化阶段失败及引擎错误（即使只有通用错误信息），不显示 DPS 或成功状态；该结果不得被误报为 GSE 解析失败，也不得称为模拟完成。

#### Scenario: Static preflight passes while character mapping is pending

- **WHEN** 序列语法和版本检查通过，但当前角色的法术或物品映射尚未全部核对
- **THEN** 系统显示待角色核验状态，不把静态预检通过当成本机模拟已完成，不显示 DPS。
### Requirement: Sim2GSE preserves the existing generated search behavior

系统 MUST 保持普通动作候选的导出与模拟语义，以及既有自动搜索的评分、候选选择、预算和复测规则。外部 GSE 导入能力不得令其他高级结构自动进入搜索空间；本次仅允许搜索生成可忠实编译和模拟的顺序 `Loop`（循环）及 `Pause`（暂停空点击）候选。

#### Scenario: A user searches with ordinary actions

- **WHEN** 用户使用原有优化入口搜索普通动作候选
- **THEN** 普通动作候选仍可生成、评价和导出，并沿用原有评分、选择、预算和复测规则。

#### Scenario: Imported structures are outside the supported search subset

- **WHEN** 用户导入包含其他 GSE 高级结构的序列，或运行自动搜索
- **THEN** 导入检查和模拟仍按其原有能力工作；自动搜索仅新增本票支持的顺序循环与空点击候选，不因此生成其他高级结构。
### Requirement: Sim2GSE searches and evaluates sequential loops

系统 MUST 能在自动搜索中生成、评价、选择和导出包含 `Sequential Loop`（顺序循环）及整个循环 `Repeat Count`（重复次数）的候选。不同重复次数 MUST 是不同候选；导出的序列 MUST 与锁定 GSE 编译器逐次按键展开的动作顺序、次数和来源一致，同一展开计划 MUST 用于本机受控模拟。不能忠实编译或展开超过 4096 次按键的候选 MUST 在评价前拒绝。

#### Scenario: Search generates a repeated sequential loop

- **WHEN** 自动搜索尝试包含顺序循环及重复次数的候选
- **THEN** 结果可追溯到该候选的评价与选取；其导出序列经锁定 GSE 编译后的每次按键动作和来源，与本机模拟使用的展开计划一致。

#### Scenario: Loop expansion exceeds the limit

- **WHEN** 候选的顺序循环展开后超过 4096 次按键，或不能按锁定 GSE 规则忠实编译
- **THEN** 系统在本机伤害评价前拒绝该候选，不给出其模拟成绩。
### Requirement: Sim2GSE searches and evaluates empty-click pauses

系统 MUST 能在自动搜索中生成、评价、选择和导出占用多次按键的 `Pause`（暂停）候选；搜索候选以 `WaitClicks(n)`（等待 n 次空点击）区分等待次数，其中可导出的 n 至少为 2。导出边界 MUST 将其变为与锁定 GSE 编译器一致的暂停序列，逐次空点击数及来源 MUST 与本机受控模拟一致。不同按键间隔下，每次空点击 MUST 占用相应输入时刻。`Pause{Clicks=1}` 在锁定 GSE 编译器中不产生等待，系统 MUST 不得把它评价为一次空点击。展开超过 4096 次按键的候选 MUST 在评价前拒绝。

#### Scenario: Search evaluates and selects a pause candidate

- **WHEN** 自动搜索尝试包含等待多次空点击的候选，并在给定按键间隔下对其评价
- **THEN** 候选可参与原有选优；被选中时导出序列的 GSE 编译空点击数、来源与本机模拟一致，各空点击占用对应输入时刻。

#### Scenario: Click interval changes pause timing

- **WHEN** 相同等待次数分别在不同按键间隔下评价
- **THEN** 空点击次数保持一致，占用的输入时刻按各自间隔变化。

#### Scenario: A pause cannot be faithfully represented

- **WHEN** 候选要求一次空点击，或展开超过 4096 次按键
- **THEN** 系统不会把 GSE 的 `Pause{Clicks=1}` 当作一次空点击，也不会对该超限候选给出本机伤害成绩。
