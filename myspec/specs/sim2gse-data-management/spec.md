# Sim2GSE Data Management

## Purpose

通过自包含统一入口管理稳定身份、生命周期、分析事实及可恢复维护。上线参数待确认，生产默认禁用；本次验收只操作隔离合成数据。

## Requirements

### Requirement: Self-contained explicit entry

系统 SHALL 以自包含技能提供一个公开 CLI，运行时不反向依赖仓库开发测试。受管根和机器配置必须显式指定；生产默认禁用，容量、保留和维护参数缺失时拒绝生产变更。

#### Scenario: Detached skill remains usable

- **WHEN** 技能复制到脱离仓库的目录并指定隔离配置和受管根
- **THEN** 基本公开命令可以运行，索引与大数据留在技能外部，不修改全局工具或启用生产
### Requirement: Stable identity and conservative capacity

系统 MUST 将稳定 run/artifact ID 与物理位置分离，在独立 SQLite 索引记录角色、摘要、封口、依赖、租约及预留。容量核算覆盖所有受管卷、未知文件、DB/WAL、原件与产品共存、临时区、隔离区和并发未来承诺；同卷隔离不算释放空间。

#### Scenario: Concurrent reservation admission

- **WHEN** begin 或操作申请容量
- **THEN** 在同一根写锁内核算完整占用与既有预留，不足时拒绝新增长，不自动清理；只有身份和载荷校验成功的 finish 或明确放弃才核销相应未来承诺
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

系统 SHALL 提供完整总量盘点和有界增量盘点，不把未完成页当作容量或删除证据。扫描拒绝链接、非普通对象及目录身份变化；跨页是实时观察而非冻结快照，游标绑定根与未完成目录身份。maintenance 复用同一安全入口；schedule-preview 只生成禁用任务预览，不安装启用，缺失策略或带时区开始时间时不生成。

#### Scenario: Directory changes between pages

- **WHEN** 游标关联目录身份改变
- **THEN** 拒绝继续旧游标并说明需重新盘点；不把局部统计当完整空间证明
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
