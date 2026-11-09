# GearInsight 打法指南与手法模块复用研究（2026-11-09）

## 结论

**可以减少逐场手工挖 WCL（魔兽战斗日志网站）的工作，最先复用现成起手、施放频率、效果覆盖率和出处；动态推荐树适合做下一阶段研究材料，不能直接当作可循环按键程序。** 当前最小接法是人工或代理清洗一次，登记到既有起点库，继续使用现有准入、适配和评价流程。本文只研究，没有登记材料、改配置、开发接入、运行游戏、模拟或训练。

本文按 research（主来源研究）技能，区分“安装文件真实内容”“作者在注释中自报的成绩”“我们的推断与建议”。安装版本 1.14.6 是软件版本，不是所有日志或网页资料的日期；出处见安装包[说明文件第 7 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/GearInsight_Rotation.toc:7>)。

## 一、已经核实的事实

### 1. 同一页面包含两类不同材料

| 内容 | 实际是什么 | 能提供什么 | 不能证明什么 |
|---|---|---|---|
| 日志整理数据 | 高手成功施放记录的汇总 | 有顺序的短起手、每分钟次数、效果覆盖、人物及场景信息 | 原始按键、失败尝试、空点击、等待、完整循环宏 |
| 动态手法建议 | 当前状态 → 分类树排序 → 可用性检查 → 人工规则覆盖 | 现在推荐哪个、备选哪个、理由与判断条件 | 可脱离状态直接执行的长序列、自动代按、实际伤害收益 |

证据：数据文件头定义 `core`（每分钟次数）、`watch`（效果覆盖）、`opener`（真实起手）和 `follow`（接续统计），见[RotationData.lua 第 1—4 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Data/RotationData.lua:1>)；邪恶死亡骑士建议计算见[UnholyRot.lua 第 764—815 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:764>)，其第 8 行明确只提示、不代按。

页面和屏幕提示也没有共用同一套起手表：页面按需读取日志数据，动态提示直接取当前专精的引擎。见[RotationPage.lua 第 67—88 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/ui/RotationPage.lua:67>)。当前页面将旧起手展示开关设为关闭，因此“文件里有起手”不等于“当前页面正在展示”，见[第 2644—2655 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/ui/RotationPage.lua:2644>)。

**来源选择以较新的来源模块为准。** 有自主引擎的专精固定使用该引擎，无引擎才使用暴雪助手；团本专用规则没做时，团本也可能沿用大秘境规则，页面给提示。不能依据页面内旧按钮断言可以自由切换。见[RotSource.lua 第 1—15 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/ui/RotSource.lua:1>)及[第 50—70 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/ui/RotSource.lua:50>)。

### 2. 静态材料覆盖广，动态引擎只登记十个专精

主代理对当前安装数据的只读统计：13 职业、40 专精，共 1239 条起手记录；在每个专精内按完整技能顺序去重，共 1112 种，长度 7—15。邪恶死亡骑士 31 条、28 种。邪恶段从[RotationData.lua 第 227 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Data/RotationData.lua:227>)开始。记录数包含不同栏目重复引用，不能直接称作独立场次或可训练程序数。

统计方法：主代理用仓库现有 Lua（轻量脚本语言）只读加载两份数据表，逐栏目遍历。邪恶段为第 227—337 行：团本起手第 231 行、大秘境群体第 242 行、单体第 246 行，各首领栏目从第 254 行开始。起手记录字段集合为整波敌人数量、人物、战斗名、地区、技能顺序、服务器和天赋，没有原日志报告码或施法时间戳。整波敌人数量不证明各时刻同时存在的目标数，不能直接当作固定五目标参考。核验文件 SHA256（文件内容校验值）为 `21829d9faaa0e0a9b6150f9e1a96e80f18f2cf3b1c98c405d2bdfa639f026209`，用于定位本次快照，不推断日志日期。

**新版确有原始起手增量。** 主代理将当前邪恶专精原始有序技能编号串，与仓库旧采集件`.local/sim2gse/gearinsight-research-20261008/inspection.tsv`中每条SEQ记录第9列比较：旧版去重28种、新版去重28种，两集合交集为0。当前60条训练材料中的28条插件起手来自旧采集件，没有自动随安装包更新。此对比只证明28种原始顺序不同；按当前可按动作清洗、独立爆发分离、角色适配及行为去重后净增多少，尚未验证，不能提前宣称新增28个合法训练起点。

按场景和英雄天赋划分的数据，提供频率与覆盖，不提供有顺序的循环；邪恶死亡骑士 38 场景、76 个场景与英雄组合，其中 37 个标为材料充足、39 个标为不足。见[RotationHeroData.lua 第 1—3 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Data/RotationHeroData.lua:1>)。主代理逐项解析确认当前接续统计全部为空，不能据此恢复完整循环。

[官方打法指南首页](https://gearinsight.cn/wow/en/rotation)列出 40 专精；[邪恶死亡骑士页](https://gearinsight.cn/wow/en/rotation/death-knight/unholy)标注资料日期 2026-09-08，提供约前 15 个成功施放和大秘境第一波／首个首领等材料。上述网页由主代理核验，本子任务的网页读取超时，没有另行冒称复核。

动态引擎登记如下；英雄与训练范围是**文件作者声明的材料范围**，不代表当前代码一定会拦住其他英雄天赋。

| 专精 | 作者声明的主要材料范围 | 登记与数据证据 |
|---|---|---|
| 鲜血死亡骑士 | 萨莱因，大秘境 40 场，+22/+23 | [BloodRot.lua:922](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BloodRot.lua:922>)；[BloodRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BloodRotData.lua:1>) |
| 邪恶死亡骑士 | 萨莱因，大秘境 40 场，+21/+22 | [UnholyRot.lua:1201](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:1201>)；[UnholyRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRotData.lua:1>) |
| 冰霜死亡骑士 | 死亡使者与冰龙吐息，大秘境 40 场 | [FrostRot.lua:11](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/FrostRot.lua:11>)；[FrostRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/FrostRotData.lua:1>) |
| 武器战士 | 屠戮者，大秘境 40 场 | [ArmsRot.lua:27](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ArmsRot.lua:27>)；[ArmsRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ArmsRotData.lua:1>) |
| 防护战士 | 山丘领主，大秘境 40 场 | [ProtWarRot.lua:15](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ProtWarRot.lua:15>)；[ProtWarRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ProtWarRotData.lua:1>) |
| 踏风武僧 | 天神御身，大秘境 40 场 | [WindwalkerRot.lua:16](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/WindwalkerRot.lua:16>)；[WindwalkerRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/WindwalkerRotData.lua:1>) |
| 酒仙武僧 | 祥和宗师，大秘境 40 场 | [BrewmasterRot.lua:16](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BrewmasterRot.lua:16>)；[BrewmasterRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BrewmasterRotData.lua:1>) |
| 敏锐潜行者 | 诡诈为主，大秘境 40 场 | [SubtletyRot.lua:12](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/SubtletyRot.lua:12>)；[SubtletyRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/SubtletyRotData.lua:1>) |
| 元素萨满 | 先知，大秘境 39 场 | [ElementalRot.lua:13](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ElementalRot.lua:13>)；[ElementalRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/ElementalRotData.lua:1>) |
| 噬灭恶魔猎手 | 虚痕枭雄 41 场、歼灭者 39 场，各一棵树 | [DevourerRot.lua:11](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/DevourerRot.lua:11>)；[DevourerRotData.lua:1](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/DevourerRotData.lua:1>) |

踏风团本规则文件确实存在，安装包说明文件也列入加载；但文件头仍写“测试中、发行时剔除”。应分别保留这两个事实，不能只凭旧注释认定当前未加载，更不能宣称已通过实机验收。它共用大秘境树、替换部分团本规则参数，见[WindwalkerRotRaid.lua 第 1—29 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/WindwalkerRotRaid.lua:1>)及[安装加载顺序第 23 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/GearInsight_Rotation.toc:23>)。邪恶团本来源仍标“制作中”，见[UnholyRot.lua:1013](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:1013>)。

### 3. 邪恶推荐并非单纯把日志频率排个序

离线阶段：`UnholyRotData.lua` 声明由作者的导出脚本生成，保存 24 项状态特征、技能标签、技能编号、资源估算参数和分类树。特征含符能、符文、触发、食尸鬼层数、目标数、首领状态、上两次技能及距上次技能时间。见[第 1—17 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRotData.lua:1>)。安装包没有据此交付可复现训练的原始日志和完整训练环境，本研究未复现作者训练。

运行阶段：读取状态并自行记账；施法成功更新状态，失败反馈修正估计，脱战读取初值。见[UnholyRot.lua:265](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:265>)、[第 376—393 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:376>)、[第 490—520 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:490>)、[第 591—643 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:591>)。

树从根节点按状态值与门槛往下走，叶子保存各技能的分类概率。取概率最高者为主推，第二名不到第一名的一半就不给备选；同时能返回走过的判断条件。见[BloodRotTree.lua 第 6—47 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BloodRotTree.lua:6>)。

邪恶引擎会排除暂时用不了的动作，再让疾病、黑暗突变、腐化、瘟疫降临等人工规则压过树；灵魂收割和凋零另有备选规则。强制规则将主推值写成 `pa=1`，表示规则接管，不能解释成“预测准确率 100%”。见[UnholyRot.lua 第 685—708 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:685>)及[第 764—801 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:764>)。

作者注释自报：原树第一格 46.8%、前两格 71.0%；后续规则说明第一格约 44.6%，0.6 修改后整体前两格 67.5%。这些是与日志动作吻合的统计，不是伤害提升，本研究未复测；页面仍保留旧 47%／71% 文案，不应拿它代表当前完整引擎成绩。证据：[数据头](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRotData.lua:2>)、[规则改动说明](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:685>)、[页面来源文案](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:1013>)。

### 4. 没有核实到名为 PULL_OPEN（开怪固定起手）的现成序列

本次安装文件搜索未找到 `PULL_OPEN`。邪恶代码实际提供 `pull_i`（开怪第几次动作）：停手至少 4 秒重算，并通过 `OB_PULL`（开怪阶段门槛）补疾病。它是单项条件规则，不是完整起手表；见[UnholyRot.lua:386](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:386>)及[第 692—702 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:692>)。可直接研究的有序起手来自前述日志数据中的技能顺序。

## 二、对 Sim2GSE 的判断（推断）

1. **最值钱的是省采集与初筛。** 已有短起手和场景划分可替代大量逐场翻日志；频率和效果覆盖用于解释材料及核对候选差异。它们不能替代从“成功施放”到“可按动作”的人工清洗。依据是上述数据字段，以及现有[正式规格第 31 行](../../myspec/specs/sim2gse-seed-training/spec.md:31)明确禁止把成功日志冒称完整宏。
2. **动态树不是可直接登记的起点程序。** 每一步依赖当时状态、历史动作和人工覆盖；任取一个叶子的概率反复抽样，会丢失状态变化和可用性检查，不能称真实连续轨迹。要研究这种生成方式，须由独立状态模型逐步推进后再生成候选，不能拿真实战斗状态悄悄反馈到“纯序列模拟”。依据：[树解释器](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/BloodRotTree.lua:6>)、[特征与规则](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:376>)和[仓库术语](../CONTEXT.md)。
3. **不能用这棵邪恶树填满现有四组。** 现有训练按双英雄与单目标／五目标分四组，而这棵树只声称萨莱因大秘境样本。树的界面能在其他场景出建议，不证明那些组已得到材料验证。依据：[训练规格第 39 行](../../myspec/specs/sim2gse-seed-training/spec.md:39)与前述树材料头。

邪恶引擎是否可用主要检查专精 252 和来源选择，并不据此证明天启骑士已有独立训练或验证。见[UnholyRot.lua 第 1000—1012 行](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:1000>)。

## 三、建议的最小接法（尚未实施）

| 顺序 | 怎么做 | 现有接点与限制 |
|---|---|---|
| 先做材料批次 | 冻结安装版本、文件指纹、取材日期；按专精、英雄、场景提取起手，保留人物、原顺序及重复出处 | 沿用既有来源库；不新建另一套资料仓库 |
| 清洗后登记 | 分开原件与改写件；识别技能替换形态、物品、防御、移动、独立爆发；不能表达的只存原因 | [seed_training.py:23](../../projects/sim2gse/seed_training.py:23)、[register（登记）:91](../../projects/sim2gse/seed_training.py:91)已经要求原件、用法、改写、家族、核心及程序 |
| 继续原有准入 | 按角色与语法检查、适配、编译、按完整点击行为去重，再进入原人工启动的训练 | [seed_training.py:700](../../projects/sim2gse/seed_training.py:700)已有拒入和准备处理；不是把所有 28 种邪恶起手直接宣布为 28 个合法起点 |
| 后续再研究规则 | 把开疾病、爆发同步等清晰规则记为出处说明或候选核心；动态树另立范围明确的研究 | 不改模拟引擎的真实能力，不把条件树冒称固定宏 |

当前四项复杂语法关闭；建议的接入结果仍是一键一技能的普通动作列表，不开启原生施法序列、循环块、等待或多指令块。把短起手作为可重复搜索候选，是我们增加的模拟假设，必须保存改写说明，不能称原玩家持续循环。独立爆发继续沿用既有审核定义，不凭外部出现次数自动改写。资料提取与候选生成可以参考复杂条件，最终训练、搜索和导出仍遵守当前简单语法。

**当前不建议把外部每分钟次数直接接入定向修改。** [breeding.py:105](../../projects/sim2gse/breeding.py:105)目前比较的是当前条件下、经核验的本机参考与候选成功摘要；外部高层大秘境汇总混有走路、停手、拉怪、不同目标和装备。直接替换会改变训练含义。可先将其用于说明与离线对照，若未来要指导修改，应另外验证场景归一化和来源隔离。

具体而言，[action_summary.py 第 21—58 行](../../projects/sim2gse/action_summary.py:21)要求可核验样本数、每样本 180 秒、原始非负整数成功计数，以及有范围约束的相邻动作与出边计数。外部每分钟次数中位数、树中分类概率都不满足这些要求；不能反算后伪称原始统计，更不能静默替换同角色、同目标的 SimC（角色伤害模拟工具）目标摘要。

**动作编号也不能直接照搬。** [engine.py:219](../../projects/sim2gse/engine.py:219)已有原生可按能力筛选，[第 270—283 行](../../projects/sim2gse/engine.py:270)处理基础按钮与未经确证的替换形态，[第 330—344 行](../../projects/sim2gse/engine.py:330)保存能力范围并在不完整时拒绝。材料应该经过这些现有边界，不为接入外部列表而绕开。

## 四、可以借鉴的产品能力（建议）

- **材料清单**：展示可用起手、重复出处、清洗状态与不能使用的原因；用户无需每次重新挖日志。
- **分场景解释**：明确“来自哪个英雄天赋、哪种战斗”，材料不足就显示不足，避免全专精覆盖造成误解。
- **推荐理由**：学习其“技能＋原因＋三条判断依据”的展示方式；固定序列优化器优先解释为何形成该候选，不承诺实时动态教练。
- **结果对照**：展示当前模拟成功次数与外部频率的差别，并写明条件不同；不把差值直接称操作错误或优化收益。

这些建议参考了[RotationPage.lua:2366](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/ui/RotationPage.lua:2366>)的战后频率对照，以及[UnholyRot.lua:798](<D:/Program Files/World of Warcraft/_retail_/Interface/AddOns/GearInsight_Rotation/core/UnholyRot.lua:798>)返回的理由、条件与状态。它们不是本次新增需求或实施承诺。

## 五、证据边界

本报告以当前安装源码、仓库正式规格及官网为主来源。作者训练脚本路径、样本规模与准确率只按注释记录，没有将注释当作独立复现实验。未查看原始 WCL 全量日志，未验证作者样本挑选、训练与留出数据是否独立；本次没有复制其引擎代码或打包分发原始资料。

没有运行游戏、模拟、训练、来源登记或配置修改；因此本文不证明任何伤害提升、训练收敛、实时推荐准确性或游戏验收。现有规格仍要求登记与训练不改写用户安装内容，本研究遵守该边界。
