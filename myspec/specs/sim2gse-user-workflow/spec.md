# Sim2GSE User Workflow

## Purpose

让用户通过简洁的中文三步操作取得真实可复制的游戏导入结果，保留本地数据与明确的验收边界。

## Requirements

### Requirement: Sim2GSE exposes only the simple daily workflow

系统 MUST 在初始页面提供角色输入、可选的模拟按键间隔、开始操作和进度区域，并提供默认关闭的“诊断日志总开关”；额外诊断、验证明细、取消恢复与资源配置不得成为日常必经步骤。

#### Scenario: First opening

- **WHEN** 用户首次打开工具
- **THEN** 页面显示角色输入、默认300毫秒的模拟按键间隔、默认关闭的诊断日志总开关、开始操作及等待开始的进度区域，复制结果区隐藏且不显示药剂设置。
### Requirement: Sim2GSE displays real progress and actionable failures

系统 MUST 在运行期间展示来自实际任务的当前阶段与进度，不把定时演示冒充计算；失败时以简短中文说明原因与下一步。

#### Scenario: Start with an empty input

- **WHEN** 用户没有输入角色字符串就点击开始
- **THEN** 页面提示先粘贴角色导出，不启动模拟。

#### Scenario: Real evaluation is running

- **WHEN** 角色输入通过检查并启动真实评估
- **THEN** 页面显示实际进行的阶段和任务进度，尚无结果时不显示复制结果区。
### Requirement: Sim2GSE reveals only available export results

系统 MUST 在真实导出结果就绪后才显示复制区；重新输入或再次运行时隐藏并清空旧结果，不提供伪造或未通过必要一致性检查的导入字符串。

#### Scenario: Export is available

- **WHEN** 当前候选已取得满足适用检查的真实导入文本
- **THEN** 页面出现复制区，用户点击复制取得与该候选对应的文本。

#### Scenario: Input changes after completion

- **WHEN** 用户修改角色输入或再次开始运行
- **THEN** 旧结果区隐藏并清空，不能把旧角色结果当作新任务结果复制。

#### Scenario: Encoding fails

- **WHEN** 结果无法编码或编译一致性检查失败
- **THEN** 系统保留具体诊断并提示导出失败，不生成假的可复制字符串。
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
