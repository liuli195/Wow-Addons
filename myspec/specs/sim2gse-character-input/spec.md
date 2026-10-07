# Sim2GSE Character Input

## Purpose

从用户提供的角色导出中取得可信的角色配置和可按动作，无须用户维护技能或物品清单。

## Requirements

### Requirement: Sim2GSE preserves the imported character

系统 MUST 保留单个角色导出所声明的等级、种族、专精、天赋和当前装备；中文名称、说明注释和背包装备不得改变当前装备身份，职业、专精及职责是否可运行由固定 SimC（模拟引擎）决定。万奥宝典输入默认开启；原始输入 MUST 逐字节保留；实际模拟副本可按已记录的本地开关关闭完整有效的 `omnium_talents=` 行，但不得删除注释或其他包含同名文本的行。

#### Scenario: Character export contains bag alternatives

- **WHEN** 用户输入含中文名称、天赋、已装备物品及注释形式背包装备的有效单角色导出
- **THEN** 系统使用该角色当前装备、专精与天赋进行评估，并保留可核对的原始输入，不替换为背包候选。

#### Scenario: Omnium talents are disabled for the effective copy

- **WHEN** 已记录的本地模拟配置关闭万奥宝典输入
- **THEN** 系统逐字节保留用户原始输入，只从实际模拟副本删除完整有效的 `omnium_talents=` 行，并从原始输入解析角色身份。

#### Scenario: Omnium talents are enabled for the effective copy

- **WHEN** 采用默认模拟配置或已记录的本地模拟配置开启万奥宝典输入
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

系统 MUST 从固定 SimC（战斗模拟器）已实例化的完整战斗 APL（动作优先级列表）中识别当前角色合法、GSE（高级按键序列插件）能够表达的可按技能与已装备主动使用物品，作为搜索可用目录；不得仅因本次基准未执行，或当时资源、冷却、目标条件不满足而永久排除合法可按动作。系统 MUST 分别保留完整搜索目录与本次基准实际执行目录；普通默认序列及原有四类起点继续使用后者及基准轨迹，已有按钮的形态和顺序不得因目录扩充改变。不要求用户逐项选择，不扫描整个技能书，不使用职业硬编码白名单，也不把 APL 条件逻辑搬进导入序列。被动、派生效果、控制命令及当前角色不具备的动作不得生成额外按键；结果不得声称穷尽角色全部合法技能，或保证扩充目录必然提高伤害。评分、搜索预算、停止规则、原有动作选择概率及战前动作语义 MUST 保持不变。

#### Scenario: A legal combat action was not executed by the baseline

- **WHEN** 当前角色的完整战斗 APL 包含合法且能够表达的可按动作，但本次单目标基准没有执行它
- **THEN** 搜索可生成包含该动作的候选，并通过原有编译、受控评分和导出流程；基准实际执行统计仍保持原义，评分继续采用用户选择的目标数量

#### Scenario: The search catalogue expands while baseline starts are retained

- **WHEN** 搜索目录增加基准未执行的合法动作或已有按钮的替换形态
- **THEN** 普通默认序列及原有四类起点仍使用原基准目录和轨迹，保留已有按钮的形态与顺序；新增动作只扩充搜索可用范围，不引入新的起点或停滞处理策略

#### Scenario: Equipped trinket can be activated

- **WHEN** 原生证据包含当前已装备且受支持的主动使用饰品
- **THEN** 该物品自动作为可按动作参与序列生成，遵守其原生使用限制；本次未执行不单独构成排除理由

#### Scenario: The APL mentions an unequipped or passive item

- **WHEN** APL 提及未装备物品或只有被动效果的饰品
- **THEN** 该物品不会仅因 APL 提及而进入搜索可按动作目录

#### Scenario: Native evidence contains passive effects

- **WHEN** 原生报告包含宠物、周期伤害、其他不要求玩家按键的派生效果，或非按钮控制命令及当前角色不具备的动作
- **THEN** 系统保留适用的原生伤害或状态处理，但不把这些内容加入可按动作目录

#### Scenario: Selected native action is unsupported

- **WHEN** 原生证据选中的主动动作不能映射、采用尚未支持的执行方式，或只有无法确认基础按钮身份的孤立替换形态
- **THEN** 系统明确报告不支持原因，不能静默删除该动作并声称完整角色评估成功；编译或评分失败不能登记为成功成绩

#### Scenario: The complete APL report contract is unavailable

- **WHEN** 固定基准引擎缺少所需完整 APL 报告协议或提供不兼容的目录报告
- **THEN** 系统明确报告不兼容，不能静默回退为仅使用已执行动作并声称支持完整搜索目录
### Requirement: Sim2GSE keeps comparison conditions consistent

系统 MUST 默认使用固定 SimC 原生创建的单个目标，目标等级、护甲及职责相关行为交由引擎默认处理，不注入自定义敌人或固定目标数值；每场 180 秒并关闭战斗药剂。目标数量可由已记录的本地模拟配置调整，基线与受控引擎 MUST 使用同一套实际配置；模拟按键间隔默认为 300 毫秒，用户调整时同次对照与候选必须使用相同间隔及派生复测情景。

#### Scenario: User starts a default run

- **WHEN** 用户以默认本地模拟配置和默认按键间隔提交固定引擎可运行的角色
- **THEN** 系统使用 SimC 原生默认目标、数量 1、180 秒和 300 毫秒名义间隔，且不使用战斗药剂；对照与候选采用相同角色和场景，保留导出的角色等级及职责。

#### Scenario: User records a target count

- **WHEN** 用户在本地模拟配置中记录有效目标数并启动任务
- **THEN** 系统只指定目标总数，主目标和附加目标的创建沿用 SimC 原生逻辑，基线与受控引擎采用相同数量，并将完整配置纳入缓存及恢复身份。

#### Scenario: User changes the simulated input interval

- **WHEN** 用户把模拟按键间隔调整为界面允许的 50 至 2000 毫秒整数
- **THEN** 系统把该值用于候选、对照和全部派生复测情景，并将其纳入任务身份。
