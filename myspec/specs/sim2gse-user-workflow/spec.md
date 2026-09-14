# Sim2GSE User Workflow

## Purpose

让用户通过简洁的中文三步操作取得真实可复制的游戏导入结果，保留本地数据与明确的验收边界。

## Requirements

### Requirement: Sim2GSE exposes only the simple daily workflow

系统 MUST 在初始页面提供角色输入、可选的模拟按键间隔、开始操作和进度区域；诊断场景、验证明细、取消恢复与资源配置不得成为日常必经步骤。

#### Scenario: First opening

- **WHEN** 用户首次打开工具
- **THEN** 页面显示角色输入、默认 300 毫秒的模拟按键间隔、开始操作及等待开始的进度区域，复制结果区隐藏且不显示药剂或调试设置。
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

系统 MUST 分别记录模型、独立复测、编码编译与实际游戏验证状态，不把离线检查当成游戏通过；实际游戏安装及手动导入验证须在离线结果和导入文本就绪后进行。

#### Scenario: Offline export awaits game validation

- **WHEN** 已生成可供手动导入的离线结果但没有实际客户端验证证据
- **THEN** 系统可以提供导入文本，但记录游戏尚未验证，不能声称首版已完成实机验收。
### Requirement: Sim2GSE runs locally without mandatory packaging

系统 MUST 提供可在用户电脑运行的中文三步界面，保持角色输入和结果本地保存，支持中文与空格路径；打包、安装器或公开发布不是必需能力。

#### Scenario: Local run uses a Chinese path

- **WHEN** 用户在含中文和空格的可写路径运行工具并保存结果
- **THEN** 实际输入、评估和结果读取正常完成，不要求管理员权限或上传角色数据。

#### Scenario: Tool generates a sequence

- **WHEN** 本地工具生成游戏导入文本
- **THEN** 工具不自动写入游戏目录、不接管按键，也不修改配装器的引擎或数据。
