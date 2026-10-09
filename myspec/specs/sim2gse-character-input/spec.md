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

系统 MUST 根据当前角色的真实能力提供可按动作目录，包含支持的技能和已装备主动物品；不因一次模拟未使用或暂时冷却而永久排除合法动作。搜索目录与本场实际执行记录分别保留；原有起点规则保留，同时遵守当前爆发排除。当前独立爆发中的内容不得再次进入普通循环；被动、派生效果和当前角色不具备的动作不生成额外按键，但其正常效果保留。无法确认或准确模拟的动作明确报错，不静默删除后宣称完整评估；不承诺已列出角色全部能力或伤害必然提高。

#### Scenario: A legal combat action was not executed by the baseline

- **WHEN** 当前角色的真实能力资料包含合法且能够表达、并且不属于当前独立爆发的可按动作，但本次单目标基准没有执行它
- **THEN** 搜索可生成包含该动作的候选，并按实际效果评分和导出；基准实际执行统计仍保持原义，评分采用当前场景的目标数

#### Scenario: The search catalogue expands while baseline starts are retained

- **WHEN** 搜索目录增加基准未执行的合法动作或已有按钮的替换形态
- **THEN** 默认起点保留来自本场基准的原序列行为，并排除当前独立爆发内容；目录扩充本身不改变既有搜索规则

#### Scenario: Equipped trinket can be activated

- **WHEN** 当前角色已装备受支持的主动饰品，且它不属于当前独立爆发内容
- **THEN** 该物品可作为普通循环的可按动作，遵守其原生使用限制；本次未执行不单独构成排除理由

#### Scenario: The APL mentions an unequipped or passive item

- **WHEN** 能力资料提及未装备物品或只有被动效果的饰品
- **THEN** 该物品不会仅因能力资料提及而进入搜索可按动作目录

#### Scenario: Native evidence contains passive effects

- **WHEN** 原生报告包含宠物、周期伤害、其他不要求玩家按键的派生效果，或非按钮控制命令及当前角色不具备的动作
- **THEN** 系统保留适用的原生伤害或状态处理，但不把这些内容加入可按动作目录

#### Scenario: Selected native action is unsupported

- **WHEN** 原生证据选中的主动动作不能映射、采用尚未支持的执行方式，或只有无法确认基础按钮身份的孤立替换形态
- **THEN** 系统明确报告不支持原因，不能静默删除该动作并声称完整角色评估成功；编译或评分失败不能登记为成功成绩

#### Scenario: The complete APL report contract is unavailable

- **WHEN** 当前引擎不能提供所需的完整动作目录
- **THEN** 系统明确报告不兼容，不能静默回退为仅使用已执行动作并声称支持完整搜索目录
### Requirement: Sim2GSE keeps comparison conditions consistent

系统 MUST 对需要同条件比较的候选及复测使用相同角色、目标、战斗时长、按键间隔及爆发规则。自由选招参考若采用不同按法或药水条件，须明确标注，不能将其当作同条件收益证明。每场战斗默认180秒，目标属性按游戏规则处理。页面主搜索依次采用单目标和5目标、默认200毫秒按键间隔；爆发中的药水和饰品实际参与模拟。独立导入及明确选择的历史模式按其声明参数运行，不能把旧模式的默认禁药或300毫秒规则套用到当前双场景爆发模式。用户改变条件后不得沿用旧成绩。

#### Scenario: User starts a default run

- **WHEN** 用户通过页面以默认设置提交支持的角色
- **THEN** 单目标和5目标两场分别按180秒、200毫秒运行，包含固定爆发的实际效果；各场候选采用相同角色和场景；参考成绩的条件差异如实标明。

#### Scenario: User records a target count

- **WHEN** 用户在支持独立目标选择的入口指定有效目标数
- **THEN** 当前任务采用对应目标数，候选及同条件复测采用一致的目标数，不能混入其他目标场景的成绩。

#### Scenario: User changes the simulated input interval

- **WHEN** 用户把模拟按键间隔调整为50至2000毫秒的整数
- **THEN** 当前候选及同条件复测使用相同间隔，旧条件结果不能当作新条件成绩。

#### Scenario: The input interval is invalid

- **WHEN** 用户提供超出50至2000毫秒范围或非整数的按键间隔
- **THEN** 系统明确拒绝该输入，不按未声明的间隔启动计算。
