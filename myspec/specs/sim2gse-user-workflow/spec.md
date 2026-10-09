# Sim2GSE User Workflow

## Purpose

让用户通过简洁的中文三步操作取得真实可复制的游戏导入结果，保留本地数据与明确的验收边界。

## Requirements

### Requirement: Sim2GSE exposes only the simple daily workflow

系统 MUST 在页面主搜索提供一次角色输入、默认200毫秒的可选按键间隔、开始和实际进度；主搜索不选择目标数量，依次运行单目标和5目标。诊断日志默认关闭，额外设置不成为必经步骤。第三方导入模拟保留自身1或5目标选择与原程序语义。

#### Scenario: First opening

- **WHEN** 用户首次打开页面
- **THEN** 主搜索显示角色输入、默认200毫秒和开始操作，结果隐藏；1或5目标选择仅用于第三方导入模拟。

#### Scenario: One input starts both scenes

- **WHEN** 适用当前审核爆发定义的角色通过检查并开始搜索
- **THEN** 两场绑定相同冻结输入和定义，先单目标再5目标，分别显示实际成绩和进度；不得并行运行两场或重复输入。
### Requirement: Sim2GSE displays real progress and actionable failures

系统 MUST 在运行期间展示来自实际任务的当前阶段与进度，不把定时演示冒充计算；失败时以简短中文说明原因与下一步。

#### Scenario: Start with an empty input

- **WHEN** 用户没有输入角色字符串就点击开始
- **THEN** 页面提示先粘贴角色导出，不启动模拟。

#### Scenario: Real evaluation is running

- **WHEN** 角色输入通过检查并启动真实评估
- **THEN** 页面显示实际进行的阶段和任务进度，尚无结果时不显示复制结果区。
### Requirement: Sim2GSE reveals only available export results

系统 MUST 为单目标、5目标和爆发提供三个不同用途名称及单独复制，名称不得改变受测动作；全部有效并通过原生集合导入编译检查后，另提供一次导入三份的集合包。失败保留已经成功的单独结果，整体不冒称完成；修改角色或重新开始须清空旧显示。

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

系统 MUST 分别记录模型、最终独立复测是否运行、编码编译与实际游戏验证状态，不把离线检查当成游戏通过；当前搜索结果明确标为未进行最终独立复测，实际游戏安装及手动导入验证须在离线结果和导入文本就绪后进行。

#### Scenario: Offline export awaits game validation

- **WHEN** 已生成可供手动导入的离线搜索结果但没有实际客户端验证证据
- **THEN** 系统可以提供导入文本，但明确显示搜索结果、未进行最终独立复测及游戏尚未验证，不能声称已完成实机验收。
### Requirement: Sim2GSE runs locally without mandatory packaging

系统 MUST 提供可在用户电脑运行的中文三步界面，保持角色输入和结果本地保存，支持中文与空格路径；打包、安装器或公开发布不是必需能力。

#### Scenario: Local run uses a Chinese path

- **WHEN** 用户在含中文和空格的可写路径运行工具并保存结果
- **THEN** 实际输入、评估和结果读取正常完成，不要求管理员权限或上传角色数据。

#### Scenario: Tool generates a sequence

- **WHEN** 本地工具生成游戏导入文本
- **THEN** 工具不自动写入游戏目录、不接管按键，也不修改配装器的引擎或数据。
### Requirement: Sim2GSE stores and queries shared typed results

系统 MUST 通过已安装的 data-store（数据存储）技能统一保存和查询普通模拟与搜索结果；同一仓库的所有任务共用根目录 data（数据目录），以 Parquet（列式文件）内部 Zstd（压缩算法）保存可查询字段。runs（任务）、candidates（候选）、batches（批次）及按需产生的 traces（轨迹）逻辑表 MUST 保留相应的实际运行条件、候选、成绩和普通原生伤害统计；数据查询不要求用户先手工解包，也不另外长期保留完整原生 JSON（数据交换格式）报告副本。既有诊断开关、缓存身份与取消恢复规则继续适用。

#### Scenario: A simulation or search produces results

- **WHEN** 单次模拟、导入模拟或搜索产生有效结果
- **THEN** 系统将实际配置、按键条件、成绩、候选及相应原生伤害分布和伤害来源写入共享结果中心；列式数据保留非空数值和嵌套内容，原生空统计对象表示为空值，运行交换报告在成功保存后清理。

#### Scenario: A consumer reads completed results

- **WHEN** 页面读取或复制结果，或分析与训练调用者通过稳定逻辑表查询已保存数据
- **THEN** 调用者直接读取同一共享中心的相应记录，可按批取得查询结果，无需手工定位压缩包或先解压完整历史数据。

#### Scenario: The storage skill is unavailable

- **WHEN** 当前环境缺少已安装的数据存储技能入口或所需依赖
- **THEN** 任务在启动模拟前明确失败并提示准备安装或依赖，不启动模拟，也不宣称结果已经保存。
### Requirement: Sim2GSE reuses verified task results without repeated storage access

系统 MUST 在同一搜索任务重复比较已经核验的成功批次时，直接复用当前任务的小结果，不再次读取结果中心、报告或本地批次记录，也不重复登记批次和整份任务状态。重复使用 MUST 不增加独立样本或成功批次数量；首次引入历史结果仍核对请求身份、成绩和统计，并登记本任务的使用结果。

#### Scenario: A task compares the same verified batch again

- **WHEN** 当前任务再次使用已经成功保存、登记并核验的批次
- **THEN** 任务使用当前已核验成绩，重复读取和重复登记次数为零，独立样本及成功批次数量不变

#### Scenario: A new or resumed task imports historical results

- **WHEN** 新任务或恢复任务首次引入一个历史成功批次
- **THEN** 任务按该批次的真实存储键读取完整结果，重新核对请求身份、成绩和统计，并只登记一次本任务使用结果
- **THEN** 同一任务内使用已核验快照；任务自身更新或失效该键后不继续使用旧成绩，外部改写在新任务或恢复时重新核验
### Requirement: Sim2GSE preserves successful cache references during temporary storage failures

系统 MUST 区分目标缺失、确定损坏及身份或成绩不符，与存储暂时不可读；只有前一类问题允许失效重算。存储不可读 MUST 保留已有成功引用并明确报告失败，不静默补跑。缓存读取和复用 MUST 继续遵守累计预算、取消和恢复规则，不把取消或预算耗尽误判为损坏。

#### Scenario: Stored results are unavailable temporarily

- **WHEN** 已完成结果因权限、锁、磁盘或无法确定为内容损坏的读取错误暂时不可读
- **THEN** 任务报告读取失败并保留成功引用，不失效成绩或自动补跑

#### Scenario: Stored results are missing or definitely invalid

- **WHEN** 目标结果缺失、确定损坏，或请求身份、成绩、统计不符
- **THEN** 任务按原有规则失效并重算该批次

#### Scenario: Cancellation or budget exhaustion occurs on a cache path

- **WHEN** 任务在进入批次、冷读取或核验后、返回已核验结果前观察到取消或累计预算耗尽
- **THEN** 任务按原有取消或预算规则停止，保留恢复所需的已完成成绩，不将其登记为坏缓存
### Requirement: Sim2GSE saves bounded groups of complete search reports

系统 MUST 将搜索产生的完整报告每十二份保存为一组，缓冲数量有界；正常结束、正常取消和预算停止 MUST 保存不足十二份的尾组。普通单次模拟不等待搜索报告分组。报告字段、数值、嵌套结构和类型，以及既有诊断、样本、随机条件、评分、编译和导出行为 MUST 保持原规则，不增加长期完整报告副本。

#### Scenario: Search completes a group and a tail

- **WHEN** 搜索完成十二份有效报告，随后又完成不足十二份并正常停止
- **THEN** 完整组和尾组均可靠保存，每份报告可按原有逻辑身份和字段查询；尾组保存不启动额外模拟或重置预算

#### Scenario: Ordinary simulation completes

- **WHEN** 普通单次模拟产生有效完整报告
- **THEN** 报告直接保存，不等待其他搜索报告凑组
### Requirement: Sim2GSE resumes only reliably saved complete report results

系统 MUST 区分本轮未保存成绩与可靠保存结果，未保存成绩不能成为恢复任务的有效赢家、归档或成功历史。强制结束后允许重算未保存组；此前已保存结果、有效赢家、累计预算和请求计数 MUST 保留，已保存报告继续按完整身份、成绩及统计核验。相同请求从不同任务目录并发执行后，共享逻辑表中 MUST 不产生重复批次记录。调用方不需要文件路径、文件名或调优参数，既有单条、多条、字段及通用逻辑表查询保持可用。

#### Scenario: Abrupt stop occurs before a group is saved

- **WHEN** 任务强制结束时当前组尚未可靠保存
- **THEN** 恢复只接受此前可靠保存的结果，允许重算未保存组，不借用只有摘要而缺少完整报告的成绩

#### Scenario: Reports are published before task registration finishes

- **WHEN** 完整报告已发布但任务登记尚未完成时发生中断，包括多组中的部分提交
- **THEN** 恢复核验已发布报告后复用有效结果，不重复逻辑记录，不丢失或重复累计计数，不错误覆盖此前成功组

#### Scenario: Concurrent tasks use the same request

- **WHEN** 不同任务目录同时计算或保存相同请求
- **THEN** 完成后共享批次表每个请求只有一条逻辑记录，各任务仍能核验和读取完整结果

#### Scenario: Publication identity information is unavailable

- **WHEN** 判断已保存组所需的身份信息丢失、截短或损坏，无法确定安全发布位置
- **THEN** 任务明确报告故障，保留已保存数据，不继续发布重复或覆盖已有成功报告
### Requirement: Sim2GSE saves changed task state without rewriting unchanged history

系统 MUST 自动只保存任务中实际变化的字段和归档记录，避免小变化反复重写全部历史，不要求调用方选择保存参数。进度、正常取消、累计预算、请求及样本计数、有效报告登记和恢复结果 MUST 保持一致；旧格式任务仍可在原有源码与规则身份检查通过后读取和恢复，不能为兼容而绕过身份检查。

#### Scenario: A task changes a small field or an archive entry

- **WHEN** 任务更新、增加或删除部分字段或归档记录
- **THEN** 变化可靠保存，未变化历史不被整份重写，重新读取所得状态与完整状态一致

#### Scenario: An existing task resumes

- **WHEN** 旧格式任务通过原有源码及规则身份检查并恢复
- **THEN** 任务继续使用原有累计预算和可靠保存结果，进度、取消及导出行为保持兼容

#### Scenario: Saving state fails

- **WHEN** 状态或报告保存失败
- **THEN** 任务明确报告故障，保留此前可靠保存结果和可恢复状态，不把未完成保存登记为成功
### Requirement: Sim2GSE consumes the project connection established by the installed storage skill

Sim2GSE（模拟搜索工具）MUST 使用代理通过已安装数据中心随包入口建立的项目共用连接，沿用既有逻辑表读写接口与共享数据根，不固定用户级旧技能链接、开发源码目录或客户端缓存版本。正常运行无需用户提供技能位置或额外定位程序；一个进程只加载一次实现，来源更新后重新启动生效。缺连接或依赖 MUST 在模拟启动前明确失败，不能静默改用过期来源。

#### Scenario: The old user skill link is absent

- **WHEN** 项目已从实际安装技能接入且旧用户技能链接不存在
- **THEN** 搜索及其他已对接命令通过同一项目入口成功读写原共享数据，原格式、查询、缓存、预算与恢复规则保持

#### Scenario: The project connection is unavailable or updated

- **WHEN** 项目连接缺失、失效或其来源已更新
- **THEN** 缺失或失效时模拟前明确提示接入，不能自动猜测其他安装来源
- **THEN** 新来源由代理通过随包更新入口核对并连接，已运行工具重启后使用新实现
### Requirement: Sim2GSE recovers the page task after interruption

系统 MUST 在刷新同一地址后读回原任务，取消仅停止本次所属计算，等待场不启动。父进程退出或保存中断后，页面须提供继续入口，沿用原条件和已用预算，不重跑完成场。存储不可读须明确显示可采取行动的错误；活动计算仍在时不得把读取失败当作任务结束。

#### Scenario: The parent process exits

- **WHEN** 未完成双场任务的执行进程退出后，用户重新启动服务并刷新原页面
- **THEN** 页面识别原任务已失去执行者，允许继续；运行中的另一执行者不能被重复启动或误取消。

#### Scenario: Completed work survives interruption

- **WHEN** 父子保存中断、取消或第二场失败后同条件继续
- **THEN** 完成场与有效导出保留，仅继续未完成计算或整理，不重复完成场的搜索或预算。

#### Scenario: Storage is temporarily unavailable

- **WHEN** 页面无法读取真实共享存储
- **THEN** 明确提示存储错误，活动计算继续轮询；计算已结束时提供恢复入口，存储恢复后可重读可靠结果，不伪装完成或无限仅提示断连。
