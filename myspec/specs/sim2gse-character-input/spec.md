# Sim2GSE Character Input

## Purpose

从用户提供的角色导出中取得可信的角色配置和可按动作，无须用户维护技能或物品清单。

## Requirements

### Requirement: Sim2GSE preserves the imported character

系统 MUST 保留单个角色导出所声明的等级、种族、专精、天赋和当前装备；中文名称、说明注释和背包装备不得改变当前装备身份，职业、专精及职责是否可运行由固定 SimC（模拟引擎）决定。原始输入 MUST 逐字节保留；实际模拟副本可按已记录的本地开关关闭完整有效的 `omnium_talents=` 行，但不得删除注释或其他包含同名文本的行。

#### Scenario: Character export contains bag alternatives

- **WHEN** 用户输入含中文名称、天赋、已装备物品及注释形式背包装备的有效单角色导出
- **THEN** 系统使用该角色当前装备、专精与天赋进行评估，并保留可核对的原始输入，不替换为背包候选。

#### Scenario: Omnium talents are disabled for the effective copy

- **WHEN** 已记录的本地模拟配置关闭万奥宝典输入
- **THEN** 系统逐字节保留用户原始输入，只从实际模拟副本删除完整有效的 `omnium_talents=` 行，并从原始输入解析角色身份。

#### Scenario: Omnium talents are enabled for the effective copy

- **WHEN** 已记录的本地模拟配置开启万奥宝典输入
- **THEN** 系统的原始输入与实际模拟副本均逐字节保留用户输入。
### Requirement: Sim2GSE rejects unsupported or unsafe input

系统 MUST 明确拒绝不可解析的角色、多个角色、外部文件引用、输出路径覆盖及未经允许的模拟指令；固定引擎拒绝角色或运行失败时须如实报告，不得自行改写支持范围或静默重试后声称成功。

#### Scenario: Export attempts external configuration

- **WHEN** 角色文本夹带外部文件、远程导入或输出路径覆盖指令
- **THEN** 系统在执行模拟前拒绝输入，给出具体原因，不读取所指外部配置或写入指定路径。

#### Scenario: Fixed engine rejects the character

- **WHEN** 固定引擎拒绝用户提交的职业、专精、职责或原生配置
- **THEN** 系统保留原始输入并报告引擎失败，不注入自定支持开关或替换为默认角色。
### Requirement: Sim2GSE derives the active action set from native evidence

系统 MUST 从当前角色原生基准批次实际执行的动作及引擎原生标记中识别可按技能与已装备主动使用物品，作为同一动作集合；不要求用户逐项选择。被动和派生效果 MUST 保留原生处理且不得生成额外按键，结果不得声称穷尽角色在其他场景中的全部动作。

#### Scenario: Equipped trinket can be activated

- **WHEN** 原生基准证据包含已装备且受支持的主动使用饰品
- **THEN** 该物品自动作为可按动作参与序列生成，遵守其原生使用限制。

#### Scenario: Native evidence contains passive effects

- **WHEN** 原生基准报告包含宠物、周期伤害或其他不要求玩家按键的派生效果
- **THEN** 系统保留其原生伤害或状态处理，但不把它们加入可按动作集合。

#### Scenario: Selected native action is unsupported

- **WHEN** 基准证据选中的主动动作不能映射或采用尚未支持的执行方式
- **THEN** 系统明确报告不支持原因，不能静默删除该动作并声称完整角色评估成功。
### Requirement: Sim2GSE keeps comparison conditions consistent

系统 MUST 默认使用名称 `Damage_Dummy`、等级 90、护甲系数 4531.03、数量 1 的静止目标，每场 180 秒并关闭战斗药剂；目标名称、等级、护甲系数和数量可由已记录的本地模拟配置调整，基线与受控引擎 MUST 使用同一套实际配置；模拟按键间隔默认为 300 毫秒，用户调整时同次对照与候选必须使用相同间隔及派生复测情景。

#### Scenario: User starts a default run

- **WHEN** 用户以默认本地模拟配置和默认按键间隔提交固定引擎可运行的角色
- **THEN** 系统使用 `Damage_Dummy`、等级 90、护甲系数 4531.03、数量 1、180 秒和 300 毫秒名义间隔，且不使用战斗药剂；对照与候选采用相同角色和场景。

#### Scenario: User records custom target conditions

- **WHEN** 用户在本地模拟配置中记录自定义目标名称、等级、护甲系数或目标数并启动任务
- **THEN** 系统按实际生效值运行，基线与受控引擎使用相同目标条件，并将完整配置纳入恢复身份。

#### Scenario: User changes the simulated input interval

- **WHEN** 用户把模拟按键间隔调整为界面允许的 50 至 2000 毫秒整数
- **THEN** 系统把该值用于候选、对照和全部派生复测情景，并将其纳入任务身份。
