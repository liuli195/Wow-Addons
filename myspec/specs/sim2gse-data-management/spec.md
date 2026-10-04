# Sim2GSE Data Management

## Purpose

通过自包含统一入口管理稳定身份、生命周期、分析事实及可恢复维护。上线参数待确认，生产默认禁用；本次验收只操作隔离合成数据。

## Requirements

### Requirement: Self-contained explicit entry

系统 SHALL 以自包含技能提供一个公开 CLI，运行时不反向依赖仓库开发测试。受管根和机器配置必须显式指定，生产默认禁用；生产写入须明确启用并绑定根身份。长期容量、额外维护及元数据余量、保留期和维护频率可以未设置，不以虚构临时额度替代；归档分包大小和租约时长仅在相关动作使用时必须配置。

#### Scenario: Detached skill remains usable

- **WHEN** 技能复制到脱离仓库的目录并指定隔离配置和受管根
- **THEN** 基本公开命令可以运行，索引与大数据留在技能外部，不修改全局工具或启用生产

#### Scenario: Long-term policy is deferred

- **WHEN** 生产根身份和启用条件已满足，但长期容量、额外余量、保留期或维护频率尚未设置
- **THEN** 相关动作仍核验自身必需参数和实际写入空间，不因无关长期政策缺失而拒绝，也不自动安装或启动维护任务
### Requirement: Stable identity and conservative capacity

系统 MUST 将稳定 run/artifact ID 与物理位置分离，在独立 SQLite 索引记录角色、摘要、封口、依赖、租约及预留。容量核算覆盖所有受管卷、未知文件、DB/WAL、原件与产品共存、临时区、隔离区和并发未来承诺；同卷隔离不算释放空间。配置逻辑容量时完整核算占用；容量未设时可以不为无效比较重复全根扫描，但未计量逻辑合计须报告为未知而非零。管理入口的写入准入仍检查所在卷可用空间、并发未来承诺、操作和元数据自身峰值，以及已配置的额外余量。

#### Scenario: Concurrent reservation admission

- **WHEN** begin 或操作申请容量
- **THEN** 在同一根写锁内按已配置逻辑额度及真实物理空间核验既有预留，不足时拒绝新增长，不自动清理；只有身份和载荷校验成功的 finish 或明确放弃才核销相应未来承诺

#### Scenario: Missing logical quota does not bypass physical safety

- **WHEN** 长期容量和额外余量未设置，但实际可用空间不足以覆盖本次操作、元数据峰值与并发未来承诺
- **THEN** 拒绝写入或维护，不伪造逻辑总量和无限额度；初始化空间预检失败时不发布根标记或索引

#### Scenario: Initialization fails after admission

- **WHEN** 初始索引或根标记写入发生可捕获错误
- **THEN** 仅回收本次新建且身份仍可核实的对象，既有用户文件保持不变；进程强杀、身份变化或回收失败保留现场并明确失败，不声称原子成功
### Requirement: Dependency and live-consumer protection

系统 MUST 保留持久依赖、pins、未知引用及活动生产者和读者保护，并沿依赖图传递。过期心跳或 PID 相同不能单独证明进程死亡；扫描、哈希和压缩不得更新业务 last_used。撤销加速引用需要明确批准并提示可能重算。

#### Scenario: Uncertain ownership remains protected

- **WHEN** 对象有未知消费者、活动锁、无法确认的进程身份或持久依赖
- **THEN** 位置操作或销毁拒绝；未接入 resolver 的旧消费者原路径仍保持可读
### Requirement: Truthful bounded facts and immutable snapshots

系统 SHALL 从既有结果幂等提取事实，绑定原始字节 SHA 与上下文；缺失动作、概率或时序必须标为缺失，不从 DPS 编造。失败、未完成、删失、样本数与可用误差不得丢失。query/compare/export 有界，变化轴显式，其余条件匹配或分层；snapshot 固定身份、条件、版本与事实并建立持久依赖。

#### Scenario: Source changes after fact registration

- **WHEN** 来源摘要或绑定上下文不再匹配
- **THEN** 拒绝将旧事实冒充当前来源或改写既有快照，不额外运行模拟补齐缺失数据
### Requirement: Streaming verified archive and safe restore

系统 MUST 流式生成确定性 USTAR 和 gzip，按稳定来源及原片段顺序共包小片段，不为填缝重新切片；每包有效载荷不超过 part_bytes，成员及总包数量各不超过 1000，清单不超过 1MiB，空原件保留零字节成员。保留原件并核验包、成员及原始字节 SHA；恢复只写受管根内新目录，拒绝绝对路径、父目录穿越、链接、覆盖和膨胀超限。

#### Scenario: Interrupted archive resumes

- **WHEN** 写入或核验阶段中断后重试同一操作
- **THEN** 按持久阶段保留残留并核验或重建未完成产品；既有 sealed 产品不重写，verified/published 产品先核验，不删除原件
### Requirement: Consistent SQLite backup

系统 MUST 使用 SQLite 一致性备份获取已提交逻辑视图，覆盖 WAL，不用仅主文件 SHA 冒充一致性映像；可变源与封口映像身份分开。

#### Scenario: Committed data remains in WAL

- **WHEN** 备份包含已提交但尚未并入主文件的数据
- **THEN** 映像保留该数据，经核验后封口登记
### Requirement: Recoverable location changes and exact purge authorization

系统 MUST 持久化操作计划、身份、摘要、配置、引用与阶段，并在执行前重核。跨卷迁移先复制核验再切换首选位置，保留旧消费者原路径；quarantine 可恢复。purge 仅按当前计划摘要绑定的逐项授权执行，无万能 yes；Windows 使用同一排他句柄验证身份与 SHA 后操作，不重新按解锁路径指定对象。

#### Scenario: Deletion is interrupted or approval expires

- **WHEN** 删除中断、授权过期或目标身份/引用变化
- **THEN** 保留逐项进度和墓碑；过期授权必须重新绑定原操作及当前清单逐项确认，重新出现对象不接管，身份变化拒绝
### Requirement: Bounded live inventory and disabled maintenance preview

系统 SHALL 提供完整总量盘点和有界增量盘点，不把未完成页当作容量或删除证据。普通根盘点及根容量扫描跳过已识别的目录符号链接和目录联接，不遍历目标、不重复计入目标字节，并报告跳过路径、数量和报告截断情况；文件链接、类型未知的悬空链接、未知重解析类型、非普通对象和目录身份变化仍拒绝。显式对象、运行工作区及位置或删除动作保持严格链接边界。跨页是实时观察而非冻结快照，游标绑定根与未完成目录身份。maintenance 复用同一安全入口；schedule-preview 只生成禁用任务预览，不安装启用，缺失必要调度策略或带时区开始时间时不生成。

#### Scenario: Directory changes between pages

- **WHEN** 游标关联目录身份改变
- **THEN** 拒绝继续旧游标并说明需重新盘点；不把局部统计当完整空间证明

#### Scenario: Repository root contains skill junctions

- **WHEN** 普通根包含可识别的技能目录联接和普通业务、代码、工具及隐藏文件
- **THEN** 普通文件按同一范围计量，目录联接只列入跳过报告；显式指定链接作为管理对象仍拒绝，逻辑字节不冒充去重后的物理占用
### Requirement: ROI-focused truthful validation

系统 SHALL 按明确用户批准的收益与成本保留最少有判别力测试：纯逻辑内存调用；必要数据损坏、身份、锁和恢复边界保留小样真实操作。生产限制及默认计算语义不因测试缩量改变，覆盖变化必须准确记录。

#### Scenario: Large theoretical samples are reduced

- **WHEN** 空成员真实集成缩为 8 文件、长路径恢复缩为 3 份不同内容，或重复阶段/职业/模拟交叉合并
- **THEN** 保留对应真实关键流程及独立限值逻辑检查，明确不声称已完成 1000/220 规模或旧全交叉集成；最终同 SHA 实际运行全部当前登记检查，失败、未运行及平台诊断如实区分
### Requirement: Production and historical data require separate approval

系统 MUST 保持生产禁用和策略未设置。框架实现与合成验收不得自动登记、迁移、重打包或删除真实历史数据，不得启用定时清理。

#### Scenario: Framework tests complete

- **WHEN** 合成数据验证通过
- **THEN** 仅证明对应已执行验证；真实历史操作、生产参数、正式规格应用及主干合并仍按独立明确授权门禁处理
### Requirement: Managed production admission and original-path recovery

系统 MUST 让产品任务 CLI 和本机界面共用现有管理入口，在受管生产已启用时先用明确的任务载荷预留准入，再保存输入或启动生产，保持原输出路径与运行身份；缺少必要配置、预留或空间不得静默回退到未受管写入。显式禁用管理时保留已有使用方式，不为所有用户增加必填资源参数。任务预留不是操作系统硬配额；实际产物超出预留时须拒绝封口并保留保护，不声称能阻止所有瞬时增长。恢复保持原请求、令牌、路径与预留；另一持有者只有在原进程死亡或 PID 复用被核实后才能续领，不能以过期心跳代替证明。

#### Scenario: Managed task lacks its reservation

- **WHEN** 用户在已启用的受管根通过 CLI 或界面启动任务，但未提供本次任务载荷预留
- **THEN** 明确拒绝，任务目录与粘贴输入尚未写入，不启动模拟

#### Scenario: Interrupted task resumes at the original location

- **WHEN** 原运行身份和载荷预留匹配，且持有者与运行锁核验允许恢复
- **THEN** 在原输出路径续领同一运行而不重复分配预留；原输入字节保留，活动或身份不明的其他持有者仍被保护
### Requirement: Managed task sealing and truthful completion

系统 SHALL 对受管成功任务的普通不可变产物分批登记，保留原路径、稳定身份和输入及结果证据保护，不因单批上限漏掉后续成员或嵌套同名普通文件。可变 SQLite 主库及侧文件不得冒充不可变普通产物；任务库和父目录共享缓存在终态复用一致性备份与核验协议，不在每个原生批次复制整库。全部载荷登记和所需映像核验完成后才能封口并核销未来写入承诺。缓存引用登记保留原路径兼容关系；未知行或有界扫描截断须明确报告依赖不完整并保护全根，运行预留核销不解除引用保护，也不授权位置变更或永久清理。

#### Scenario: A task contains multiple registration batches

- **WHEN** 成功任务的产物数量超过单批登记上限
- **THEN** 通过有界批次登记所有实际成员并报告总数和返回清单截断状态，只有登记与所需映像核验全部成功才核销运行预留

#### Scenario: Sealing preparation or publication fails

- **WHEN** 业务计算已完成，但封口准备、登记、一致性备份或回执发布失败
- **THEN** 保留可核实的封口意图及失败信息，不把数据未封口的任务在界面伪报完成，也不把已结束任务句柄的写入失败显示为仍在运行；恢复只补封口，不重跑已完成模拟，管理端已封口的重试核验原成员和映像后恢复回执

#### Scenario: Unknown references remain after production completes

- **WHEN** 载荷及一致性映像已完成，但缓存引用适配有未知行或截断
- **THEN** 可以核销已结束生产的未来写入预留，同时公开依赖不完整状态并保留全根未知引用保护；不能把封口状态解释为可迁移或可删除
