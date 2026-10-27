# Sim2GSE User Workflow

## Purpose

让用户通过简洁的中文三步操作取得真实可复制的游戏导入结果，保留本地数据与明确的验收边界。

## Requirements

### Requirement: Sim2GSE exposes only the simple daily workflow

角色按键序列优化器 MUST 在页面主搜索提供一次角色输入、未提供配置或明确运行值时默认200毫秒的可选按键间隔、开始和实际进度；主搜索不选择目标数量，依次运行单目标和5目标。服务未指定诊断设置时默认关闭，页面诊断和按键间隔初始状态展示配置与明确运行值合并后的服务设置，用户可为本次任务明确选择，页面选择优先，额外设置不成为必经步骤。第三方导入模拟保留自身1或5目标选择与原序列的按键行为。

#### Scenario: First opening

- **WHEN** 用户首次打开页面
- **THEN** 主搜索显示角色输入、按有效配置显示的间隔（未提供时200毫秒）和开始操作，结果隐藏；1或5目标选择仅用于第三方导入模拟；诊断选择可操作，初始状态与服务启动设置一致。

#### Scenario: One input starts both scenes

- **WHEN** 适用当前审核爆发定义的角色通过检查并开始搜索
- **THEN** 两场绑定相同冻结输入和定义，先单目标再5目标，分别显示实际成绩和进度；不得并行运行两场或重复输入。
### Requirement: Sim2GSE displays real progress and actionable failures

系统 MUST 在运行期间展示来自实际任务的当前阶段与进度，不把定时演示冒充计算；失败时以简短中文说明原因与下一步。双场任务已失败、中断、取消或部分结束时，仍显示运行中的场景 MUST 改为失败或未完成，保留已有成果和恢复所需信息，不暗示仍在计算。

#### Scenario: Start with an empty input

- **WHEN** 用户没有输入角色字符串就点击开始
- **THEN** 页面提示先粘贴角色导出，不启动模拟。

#### Scenario: Real evaluation is running

- **WHEN** 角色输入通过检查并启动真实评估
- **THEN** 页面显示实际进行的阶段和任务进度，尚无结果时不显示复制结果区。

#### Scenario: A dual task ends while a scene still appears to be running

- **WHEN** 双场任务已失败、中断、取消或部分结束，而场景仍显示此前的运行中状态
- **THEN** 页面将该场景显示为失败或未完成，保留完成成果、错误及恢复所需信息，且不把未完成场景标为成功或继续计算。
### Requirement: Sim2GSE reveals only available export results

系统 MUST 为单目标、5目标和爆发提供三个不同用途名称及单独复制，名称不得改变受测动作；全部有效并通过集合的实际导入及动作一致性检查后，另提供一次导入三份的集合包。失败保留已经成功的单独结果，整体不冒称完成；修改角色或重新开始须清空旧显示。

#### Scenario: Three exports are available

- **WHEN** 两场搜索与冻结爆发均有有效结果且集合校验通过
- **THEN** 用户可分别复制三份导入文本，也可复制一个包含三份独立名称的GSE（高级按键序列插件）集合；即使两个循环动作相同，其用途名称仍不同。

#### Scenario: The second scene or collection fails

- **WHEN** 第一场成功但第二场或集合整理失败
- **THEN** 已成功的单独导出保留，整体报告未完成，复制全部不可用，不能返回假集合或拼接文本冒充集合。

#### Scenario: Input changes after completion

- **WHEN** 用户修改角色输入或再次开始运行
- **THEN** 旧结果隐藏并清空，不把旧角色结果当作新结果。
### Requirement: Sim2GSE distinguishes local and game validation

系统 MUST 分别记录战斗行为核验、最终独立复测、导入文本完整性及动作一致性检查、实际游戏验证是否完成，不把离线检查当成游戏通过；当前正式遗传算法结果仅在全部冻结入围者完成正常场景独立复测后标为该项完成，实际游戏安装及手动导入验证须在离线结果和导入文本就绪后进行。

#### Scenario: Offline export awaits game validation

- **WHEN** 已生成可供手动导入的离线搜索结果但没有实际客户端验证证据
- **THEN** 系统可以提供导入文本，但明确显示正常场景独立复测结果和游戏尚未验证，不冒称已完成训练五场景复测或实际游戏验收。
### Requirement: Sim2GSE runs locally without mandatory packaging

系统 MUST 提供可在用户电脑运行的中文三步界面，保持角色输入和结果本地保存，支持中文与空格路径；打包、安装器或公开发布不是必需能力。

#### Scenario: Local run uses a Chinese path

- **WHEN** 用户在含中文和空格的可写路径运行工具并保存结果
- **THEN** 实际输入、评估和结果读取正常完成，不要求管理员权限或上传角色数据。

#### Scenario: Tool generates a sequence

- **WHEN** 本地工具生成游戏导入文本
- **THEN** 工具不自动写入游戏目录、不接管按键，也不修改配装器的引擎或数据。
### Requirement: Sim2GSE stores and queries shared typed results

系统 MUST 通过已接入的数据存储能力统一保存和查询普通模拟与搜索结果，同一项目的所有任务共用一个结果中心。任务、候选、评分批次及按需产生的动作轨迹 MUST 保留相应的实际运行条件、成绩和原生伤害统计；数值、类型、层次关系和空统计的原义不得改变。用户无需手工解包即可查询，也不因保存方式额外长期占用一份完整报告副本的空间。既有诊断开关、成绩复用条件与取消恢复规则继续适用。

#### Scenario: A simulation or search produces results

- **WHEN** 单次模拟、导入模拟或搜索产生有效结果
- **THEN** 系统将实际配置、按键条件、成绩、候选及相应原生伤害分布和伤害来源保存到共享结果中心；查询结果保留原有数值、类型和层次关系，空统计仍表示没有统计内容，不变成零成绩。只有确认完整结果可靠保存后，才清理临时报告。

#### Scenario: A consumer reads completed results

- **WHEN** 页面读取或复制结果，或分析与训练功能查询已保存数据
- **THEN** 使用者直接取得同一共享中心的相应结果，可一次查询多项结果，无需手工定位压缩包或先解压完整历史数据。

#### Scenario: Result storage is unavailable

- **WHEN** 当前环境缺少可用的数据存储能力或其运行条件
- **THEN** 任务在启动模拟前明确失败并提示补齐数据存储运行条件，不启动模拟，也不宣称结果已经保存。
### Requirement: Sim2GSE reuses verified task results without repeated storage access

系统 MUST 在同一搜索任务重复比较已经核验的成功批次时，直接复用已确认成绩；由该次重复比较引起的已保存结果再次读取和重复保存次数为零，不重复保存批次或全部任务信息。重复使用 MUST 不增加独立样本或成功批次数量；首次引入历史结果仍核对其角色、版本、按键序列、运行与采样条件、成绩和统计，并准确记录本任务对该结果的使用。

#### Scenario: A task compares the same verified batch again

- **WHEN** 当前任务再次使用已经成功保存、登记并核验的批次
- **THEN** 任务使用当前已核验成绩，重复读取和重复登记次数为零，独立样本及成功批次数量不变

#### Scenario: A new or resumed task imports historical results

- **WHEN** 新任务或恢复任务首次引入一个历史成功批次
- **THEN** 任务读取该批次的完整结果，重新核对其角色、版本、按键序列、运行与采样条件、成绩和统计，并只记录一次本任务对该结果的使用
- **THEN** 同一任务内使用已经核验的成绩；任务自身更新该结果或确认其失效后不继续使用旧成绩。其他任务或外部操作更改的结果，在新任务或恢复任务使用时重新核验
### Requirement: Sim2GSE preserves successful cache references during temporary storage failures

系统 MUST 区分结果缺失、确定损坏及运行条件或成绩不符，与存储暂时不可读；只有前一类问题允许宣布原结果失效并重新计算。存储不可读 MUST 保留原有成功结果及其可追溯关系，并明确报告失败，不静默补跑。读取和复用成绩 MUST 继续遵守取消、恢复及本模式适用运行时限，不把取消或超时误判为损坏；正式遗传算法不设搜索总截止。

#### Scenario: Stored results are unavailable temporarily

- **WHEN** 已完成结果因权限、锁、磁盘或无法确定为内容损坏的读取错误暂时不可读
- **THEN** 任务报告读取失败并保留原有成功结果及其可追溯关系，不宣布成绩失效或自动补跑

#### Scenario: Stored results are missing or definitely invalid

- **WHEN** 目标结果缺失、确定损坏，或角色、版本、按键序列、运行与采样条件、成绩、统计不符
- **THEN** 任务按原有规则将该批次判为失效并重新计算

#### Scenario: Cancellation or a time limit interrupts result reuse

- **WHEN** 任务在开始处理批次、首次读取或核验结果后、返回已核验成绩前收到取消请求，或本模式适用运行时限耗尽
- **THEN** 任务按原有取消或运行时限规则停止，保留恢复所需的已完成成绩，不把这些成绩误判为损坏
### Requirement: Sim2GSE saves bounded groups of complete search reports

系统 MUST 将搜索每完成的十二份有效完整报告共同可靠保存，使这些报告可查询；正常结束、正常取消和适用超时停止前，不足十二份的已完成报告也 MUST 全部可靠保存并可查询。等待保存的报告不得随任务持续运行而无限积累。普通单次模拟不等待其他搜索报告。查询所得报告的内容、数值、层次关系和类型，以及既有诊断、样本、随机条件、评分、导入一致性检查和导出行为 MUST 保持原规则，不额外长期占用完整报告副本的空间。

#### Scenario: Search saves twelve reports and its remaining completed reports

- **WHEN** 搜索完成十二份有效报告，随后又完成不足十二份报告并正常停止
- **THEN** 前十二份报告和停止前不足十二份的报告均可靠保存，每份报告仍可单独查询完整内容；收尾保存不启动额外模拟或重置累计耗时

#### Scenario: Ordinary simulation completes

- **WHEN** 普通单次模拟产生有效完整报告
- **THEN** 报告直接保存，不等待其他搜索报告
### Requirement: Sim2GSE resumes only reliably saved complete report results

系统 MUST 区分尚未保存的成绩与可靠保存的结果，未保存成绩不能成为恢复任务的有效赢家或成功历史。强制结束后允许重新计算尚未可靠保存或仍在进行的评分，不承诺强制结束后完全无需重算；此前已保存结果、有效赢家、累计耗时和请求计数 MUST 保留，已保存报告继续按角色、版本、按键序列、运行与采样条件、成绩及统计核验。不同任务并发执行相同评分请求后，共享结果中心 MUST 不出现重复的评分批次。使用者无需了解存放位置或保存调优方式，仍能查询单项、多项结果及指定内容。

#### Scenario: Abrupt stop occurs before completed work is saved

- **WHEN** 任务强制结束时已有评分尚未可靠保存，或评分仍在进行
- **THEN** 恢复只接受此前可靠保存的结果，允许重算尚未可靠保存或未完成的评分，不借用只有摘要而缺少完整报告的成绩

#### Scenario: Saved reports survive an interruption before their use is confirmed

- **WHEN** 完整报告已保存，但任务尚未确认使用这些结果时发生中断，包括仅部分报告完成保存的情况
- **THEN** 恢复核验已保存报告后复用有效结果，不产生重复评分批次，不丢失或重复累计计数，不错误覆盖此前成功保存的报告

#### Scenario: Concurrent tasks use the same request

- **WHEN** 不同任务同时计算或保存相同评分请求
- **THEN** 完成后共享结果中心每个评分请求只有一份可查询的批次成绩，各任务仍能核验和读取完整结果

#### Scenario: Saved result provenance is unavailable

- **WHEN** 区分已保存结果所需的来源和运行条件信息丢失、不完整或损坏，无法确认继续保存不会重复或覆盖成功结果
- **THEN** 任务明确报告故障，保留已保存数据，不继续保存重复结果或覆盖已有成功报告
### Requirement: Sim2GSE saves changed task state without rewriting unchanged history

系统 MUST 在任务只有少量信息变化时可靠保存变化，不因小变化反复重写全部未变化历史，也不要求使用者选择保存方式。进度、正常取消、累计耗时、请求及样本计数、有效报告和恢复结果 MUST 保持一致。历史结果可读取不等于旧任务可以继续；仅当前遗传算法任务在原版本、规则、角色输入及评分条件核验通过后继续，旧正式任务保持只读，不放宽兼容性要求。

#### Scenario: A task changes a small amount of information

- **WHEN** 任务更新、增加或删除少量进度信息或历史候选结果
- **THEN** 变化可靠保存，未变化历史不被整份重写，重新读取所得任务信息完整且与保存前一致

#### Scenario: An existing task resumes

- **WHEN** 当前遗传算法任务通过原版本、规则、角色输入及评分条件检查并恢复
- **THEN** 任务继续使用原定评分计划、累计耗时和可靠保存结果，进度、取消及导出行为保持兼容

#### Scenario: Saving state fails

- **WHEN** 任务进度或报告保存失败
- **THEN** 任务明确报告故障，保留此前可靠保存结果和恢复所需信息，不把尚未保存完成的结果报告为成功
### Requirement: Sim2GSE consumes the project connection established by the installed storage skill

系统 MUST 使用本项目已经接入的统一数据存储能力，继续访问原有共享结果，不因旧安装位置不存在而要求用户重新定位存储程序。正常运行无需用户提供安装位置或额外查找程序；更新后的存储能力在工具重新启动后生效，当前运行不混用更新前后的能力。连接缺失、失效、版本不兼容或缺少必要的多项结果查询能力时，MUST 在模拟启动前明确失败，提示完成存储接入或更新并重新启动，不能静默改用过期或其他来源。

#### Scenario: The previous installation location is absent

- **WHEN** 项目已经接入可用的数据存储能力，而以前的安装位置不再存在
- **THEN** 搜索及其他已接入功能仍成功保存和查询原共享数据，原有数据含义、查询方式、成绩复用、适用运行时限与恢复规则保持

#### Scenario: The project connection is unavailable or updated

- **WHEN** 项目的数据存储连接缺失、失效，或其存储能力已经更新
- **THEN** 缺失或失效时在模拟前明确提示重新接入，不能擅自改用其他存储来源
- **THEN** 更新后的存储能力经确认接入后，已运行工具重新启动才使用新能力

#### Scenario: Connected result storage is incompatible or lacks required queries

- **WHEN** 已接入的数据存储版本不兼容，或不能完成必需的多项结果查询
- **THEN** 普通任务、双场搜索与训练在启动计算前明确失败，页面提示更新数据存储能力并重新启动，不启动原生计算或冒称结果已保存。
### Requirement: Sim2GSE recovers the page task after interruption

系统 MUST 在刷新同一地址后读回任务；取消只停止本次任务所属计算，尚未开始的场景不启动。当前遗传算法任务的执行程序退出或保存中断后，在版本、规则、输入及评分条件仍一致时提供继续入口，保留已完成代、正常复测进度和完成场，不重跑可靠成功评分。旧正式搜索仅显示可读历史，不提供继续按钮，不按新默认规则续跑。存储暂时不可读时须说明错误及处理方式，页面仍持续查询活动任务的实际进展，不伪装结束或成功。

#### Scenario: The current genetic search stops unexpectedly

- **WHEN** 当前未完遗传算法双场任务的执行程序退出，用户重新启动工具并刷新页面
- **THEN** 显示原可靠进度，可在版本、规则、输入及评分条件核验后继续；任务仍在执行时拒绝重复启动。

#### Scenario: Completed work survives interruption

- **WHEN** 当前同版本任务在取消、第二场失败或保存中断后恢复
- **THEN** 完成场与有效导出保持，仅补未完成计算或整理，不重复完成场搜索。

#### Scenario: An old formal task is displayed

- **WHEN** 页面读取旧正式搜索的完整或未完记录
- **THEN** 保留历史结果和原计算时限、复测说明，明确旧搜索已退役且不可继续，不改写原记录。

#### Scenario: Storage is temporarily unavailable

- **WHEN** 无法读取共享存储
- **THEN** 显示存储错误并保留可靠结果；页面继续查询活动任务的实际进展，存储恢复后重新读取。任何继续执行仍必须核验当前遗传算法任务的原版本、规则、输入及评分条件。
### Requirement: Sim2GSE bounds result reads to the requested records

系统 MUST 将页面、搜索、训练与升级核验的结果查询限制在本次所需范围。查询已知任务、评分批次或候选时，只取得所需内容；一次查询多项结果时也不得混入无关结果。摘要查询不读取完整报告，详情查询仍能取得完整目标报告。目标缺失不得触发全中心查询，无关数据损坏不得阻止已知目标读取；目标本身不可读仍明确失败，完整性、运行条件、样本、取消及恢复核验保持原规则。

#### Scenario: The page reads progress or a known report

- **WHEN** 页面读取任务摘要或已知评分批次的详情
- **THEN** 摘要只读取所需进度信息，详情取得目标完整报告并排除无关结果；目标缺失不转成全中心查询，无关数据损坏不影响目标读取，目标读取故障仍显示原因和处理方式。

#### Scenario: Training collects the current specialization history

- **WHEN** 训练整理当前职业专精的历史任务和已知候选
- **THEN** 仅取得当前专精所需的历史任务信息，并一次查询所需候选内容，不为每个候选重复查询全部历史。缺失或异常候选仍分别按原来源及完整性要求核验，存储故障不冒充材料非法。

#### Scenario: A verified burst definition is reused by later scenes

- **WHEN** 双场任务或同次训练准备已经确认本次使用的爆发定义
- **THEN** 后续场景只读取并核对本次使用的爆发定义，不重复查询所有定义；定义已改变时在下一场计算前明确拒绝，不能混用原定规则与新内容。
### Requirement: 角色按键序列优化器按本次任务选择诊断日志

角色按键序列优化器 MUST 在本地页面服务提供的新建搜索、第三方导入模拟及当前支持的未完成双场任务恢复中，以本次页面服务请求的明确选择决定诊断日志是否开启；新建任务省略选择时沿用当前服务默认，恢复任务省略选择时沿用保存值；非布尔选择必须拒绝。本次选择仅影响该任务接下来的运行、子场及相关导出，不改变服务默认、其他任务或已经运行的计算。恢复关闭诊断时 MUST 停止新增被关闭的诊断记录并保留已存历史，开启时不补写过去日志，也不重新计算已完成场景。明确观测选择可以调整后续日志细分程度与曲线，未指定时恢复沿用保存值；计算条件、评分、结果来源及恢复资格不因观测选择改变。直接运行入口同样区分未提供与明确关闭，不把内置关闭值冒充本次选择。

#### Scenario: A request overrides either service default

- **WHEN** 用户在本地页面服务默认关闭时开启本次诊断，或在服务默认开启时关闭本次诊断，再通过页面开始搜索或导入模拟
- **THEN** 本次任务以及实际涉及的子场和导出均沿用明确选择，服务默认与其他任务不变。

#### Scenario: A caller omits or supplies an invalid selection

- **WHEN** 本地页面服务调用者新建任务或恢复当前支持的未完成双场任务时，未提供诊断选择，或者提供的选择不是布尔值
- **THEN** 新建时省略沿用当前服务默认，恢复时省略沿用保存值；非布尔值明确拒绝，不启动或恢复计算。

#### Scenario: A resumed task changes its diagnosis selection

- **WHEN** 当前未完成双场任务通过原有恢复资格核验，用户通过本地页面服务为接下来的运行更改诊断选择
- **THEN** 后续运行及相关导出使用本次选择；关闭后不追加被关闭的诊断记录，已存历史仍保留；开启后不补过去日志，不重复已完成场景。

#### Scenario: The user changes the selection during an active run

- **WHEN** 任务已经运行后，用户修改页面诊断选择
- **THEN** 已运行任务不变，新选择只用于下一次创建或符合条件的恢复请求。
