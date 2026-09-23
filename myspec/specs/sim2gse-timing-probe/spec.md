# Sim2GSE Timing Probe

## Purpose

按需保存真实 GSE（宏序列插件）动作提交与游戏原生施法、资源和冷却事件，供离线核对输入时序和状态分叉；探针不产生按键或施法。

## Requirements

### Requirement: Sim2GSE probe sessions persist on demand

探针 MUST 允许用户用 `/s2gprobe start | mark | stop | status` 管理单次采集，在会话活动时记录并将结果保存在 SavedVariables（保存变量）中；新会话替换旧会话，停止后不再追加采集事件。

#### Scenario: User captures one test session

- **WHEN** 用户开始采集、标记边界、停止并重载游戏界面
- **THEN** 保存变量包含本次会话的开始、标记、停止及其间记录，旧会话未混入本次结果。
### Requirement: Sim2GSE probe records GSE submissions without producing input

探针 MUST 监听可观察的 GSE 安全动作提交消息，记录时间、点击序号、序列、可还原的提交步骤和动作信息；探针不得自行按键、施法或修改 GSE 文件，消息记录不得冒充物理按键边沿。

#### Scenario: GSE submits two actions

- **WHEN** 活动会话收到同一序列连续的两次 GSE 安全动作提交消息
- **THEN** 保存记录按顺序包含两次提交的时间、序号及可获得的动作身份；重复消息不会形成额外提交记录。
### Requirement: Sim2GSE probe records native cast lifecycle clues

探针 MUST 在活动会话中记录玩家原生施法请求、失败、开始、停止、成功、引导开始／更新／停止及施法延迟事件，保存可读取的技能编号、施法标识和事件后的施法状态；当前技能变化和相关错误亦须保留事件时刻。

#### Scenario: A cast is delayed during a channel

- **WHEN** 游戏在采集期间发出玩家引导更新或施法延迟事件
- **THEN** 该事件及可读取的技能编号、施法标识、读条或引导快照按实际采样时刻写入会话。
### Requirement: Sim2GSE probe records resource and cooldown changes

探针 MUST 在活动会话中记录玩家符文、符文能量、技能冷却与充能变化的事件时刻及安全可读的事后状态，并在 GSE 提交和关键施法反馈处保存资源、公共冷却与已观察候选技能状态快照；快照不得标作按键前状态或已确认的内部施法队列。

#### Scenario: Resource or cooldown changes after input

- **WHEN** 采集期间出现玩家符文能量、符文、冷却或充能变化事件
- **THEN** 保存记录标明事件和采样时刻，并包含可读取的对应状态，以供事后与提交、施法事件排序。
### Requirement: Sim2GSE probe preserves records when fields are unreadable

探针 MUST 在游戏接口缺失或返回受限值时保留事件，并将无法安全读取的字段标为不可读取，而不伪造数值或中断采集。

#### Scenario: A protected field cannot be read

- **WHEN** 某次施法或冷却事件含不能安全序列化的字段
- **THEN** 会话仍保存该事件，其受限字段明确标为不可读取，后续事件继续采集。
### Requirement: Sim2GSE probe reports game validation separately from deployment

交付记录 MUST 将插件部署、离线测试与正式服实际采集验收分别标识；新增事件在正式服采集证据确认前必须标为 `game_validation: not_run`，不得称为游戏内验收通过。

#### Scenario: Version 0.1.7 is deployed without a new in-game capture

- **WHEN** 0.1.7 已复制到游戏插件目录且文件指纹一致，但尚无新增事件的正式服采集记录
- **THEN** 交付记录仍显示 `game_validation: not_run`，不以部署或离线测试代替游戏内验收。
