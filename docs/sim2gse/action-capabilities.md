# 原生动作来源与首轮能力映射

日期：2026-09-12。对应[确定首版动作与饰品支持范围](../../myspec/changes/sim2gse-wayfinder/issues/06-supported-actions.md)。按用户决定，从当前角色的 SimC（模拟引擎）取得输出动作，本清单记录映射和证据状态，不作为人工删减技能的白名单。本轮只读官方源码与已有基线，没有运行新模拟、修改引擎或制作导入串。

当前状态：用户明确本票只需确定自动识别规则，任务 6 已完成，具体清单由后续程序生成。任务 8 结项时用户进一步明确：被动效果沿用固定上游引擎，不由本项目另行处理；三个疑点保留为上游模型限制，不阻塞离线搜索。本文不证明识别器、上游模型或游戏行为已经通过验收。历史交接以最新结项决议为准。

用户随后明确了全自动产品流程：具体角色能力清单由工具代码在运行时生成，本文的技能表只用于开发取证，不是用户需要人工核对的步骤，也不是完成任务 6 前必须手工做出的最终清单。首版战斗药水固定关闭，不提供逐能力配置选项；受支持主动饰品自动处理。有效输入直接经过自动检查、模拟优化和导出；异常输入或未支持能力自动说明原因并停止。详见[全自动生成决议](../../myspec/changes/sim2gse-wayfinder/issues/06-supported-actions.md)及[实施方案](../Sim2GSE_Implementation_Plan.md)第 5.2 节。

## 来源与适用范围

- 当前输入、独立原版程序及单目标基线沿用[角色取证报告](target-evidence.md)：邪恶死亡骑士、90 级、正式服 `12.1.0.69587`；程序提交 `c1935b92f40d1063696861b0f4f6701e714ebd09`。300 毫秒是未来序列的名义输入间隔，不是该原生基线采用的控制器。
- 本地官方源码归档提交为 `b845947a34429874433d8e9362326894650dd20a`；其引擎目录与程序提交对应关系沿用[固定来源记录](engine-research.md)。引用源码的逐字节归档核对结果记录在本轮证据摘要。源码只作只读参考，不是本项目的补丁工作树。
- 数据均取正式服文件；不使用名称带 `_ptr`（测试服）的数据替代。GSE（按键序列插件）格式依据仍为 `3.3.32 / f225d4c947d168c63451ef7c567d7063c38cc239`，不是用户实际安装版本。
- 本轮证据摘要为 `.local/sim2gse/support-scope/evidence.json`，来源报告为 `.local/sim2gse/target-evidence/task-05/native-baseline.json`，报告散列为 `180c5e60164fc363133995a057d63cb8f6d6e0c11222fb36bb181b730346fe6b`。摘要保留动作统计、样例轨迹名称及源码散列；不是产品能力检查器。

## 动作取得规则

1. 先用同版本的职业主动法术表、天赋及替换关系、玩家／宠物归属和物品使用标记确定主动候选；再核对当前角色初始化后的能力。原生标准 APL（动作优先级列表）用于确定参考策略使用哪些能力，不作为“游戏中是否主动”的定义。用户输入仍按安全角色字段读取，不开放任意用户动作脚本。
2. 不能把某次模拟中未施放、战斗开始时尚未就绪或暂未满足斩杀条件，当成不可用。静态角色／场景条件与战斗中会变化的资源、增益及冷却条件必须分开；后者不能用初始状态过滤掉动作。
3. 实际施放轨迹与统计只用来核对候选和解释频率，不能反过来生成主动清单。当前列出的 8 类战斗技能是该角色与固定单目标参考流程的核对结果，不是邪恶专精全部主动技能；换版本、天赋、装备或场景后重新取得。
4. 可按动作、替换形态、派生效果分别记录。用户按一次基础按钮，由角色状态决定其合法替换；不能让搜索器绕开状态直接任选替换技能。疾病、自动挥击、宠物自主动作及装备触发继续由原生引擎结算。
5. 列表调用、变量、目标排序和外部增益请求属于原生策略或场景设施，不直接转换成角色按钮。导出只表达已核对的游戏命令，不把原生实时条件偷偷搬进固定序列，也不允许原生后台补放候选主动技能。
6. 如原生参考实际使用了尚不能表达的主动能力，报告具体缺口并阻止宣称完整兼容；不静默删除或给一个看似正常的最终成绩。输出兼防御动作也按此规则检查，本轮没有另加人工排除表。

固定源码的 `init_action_list`（动作列表初始化）按邪恶专精选择其原生流程；该流程的单目标与爆发分支包含下表技能。多目标分支要求至少 3 个目标；当前固定 1 个目标不能到达它，这与“恰好没有施放”不同。[专精入口](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L15505)、[原生邪恶流程](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/apl/apl_death_knight.cpp#L324)

## 官方主动能力来源复核（2026-09-12）

用户要求先找官方主动技能清单或引擎明确标记，不从伤害报告倒推按钮。复核结论：有直接的数据来源，应该先做主动身份识别，再做模型、参考策略与导出映射。此前八项表不能称为完整主动技能清单。

### 暴雪资料能直接提供什么

本轮检索了暴雪职业页、版本新闻及开发者文档入口；没有取得一份可直接采用、完整列出 `12.1.0.69587` 邪恶死亡骑士全部战斗主动能力的官网文章。搜索出现的巨龙时代天赋预览属于旧版本；部分官网正文返回 403，开发者门户仅返回动态页面外壳。不能据此宣称暴雪没有该资料，也不能将旧文章或论坛玩家发言冒充当前完整清单。[暴雪职业页](https://worldofwarcraft.blizzard.com/en-gb/game/classes/death-knight)、[旧版天赋预览](https://worldofwarcraft.blizzard.com/en-us/news/23797209/world-of-warcraft-dragonflight-talent-preview)、[开发者入口](https://develop.battle.net/documentation/world-of-warcraft/game-data-apis)

已经取得的同版本暴雪生成接口文档更加直接：

| 所需事实 | 暴雪接口／字段 | 解释 |
| --- | --- | --- |
| 法术书条目是不是被动 | `C_SpellBook.GetSpellBookItemInfo`（读取法术书条目）的 `isPassive`（是否被动）；也有 `IsSpellBookItemPassive`（判断被动） | 有明确标记，不需要从伤害是否出现推断。非技能条目也可能返回假，必须一起判断 `itemType`（条目类型）。 |
| 是否属于当前专精、是否学会 | `isOffSpec`（其他专精）、`FutureSpell`（尚未学会的法术类型），以及 `C_SpellBook.IsSpellKnown`（是否掌握法术） | 官方法术书自身也区分其他专精和未学会状态。 |
| 基础按钮与替换技能 | `actionID`（基础编号）与 `spellID`（当前替换编号） | 有官方对应关系；不能把替换形态都变成独立按钮。 |
| 物品使用对应法术 | `C_Item.GetItemSpell`（物品使用法术） | 取得法术名称及编号；物品是否已加载、当前能否使用仍须分别处理。 |
| 此刻能不能施放 | `C_Spell.IsSpellUsable`（当前可用性） | 是动态状态检查，不能因为资源不足等暂时不可用，就从主动候选中删除。 |

以上来源是暴雪生成内容，由 Gethe（源码镜像维护者）保存，不是暴雪运营的代码仓库。已核对本地 `version.txt` 为 `12.1.0.69587`；固定提交仍为 `8ea15b61e45c0ed4eba01439c90757f86eb78d34`。[法术书接口与结构](https://github.com/Gethe/wow-ui-source/blob/8ea15b61e45c0ed4eba01439c90757f86eb78d34/Interface/AddOns/Blizzard_APIDocumentationGenerated/SpellBookDocumentation.lua#L270)、[法术被动和可用性接口](https://github.com/Gethe/wow-ui-source/blob/8ea15b61e45c0ed4eba01439c90757f86eb78d34/Interface/AddOns/Blizzard_APIDocumentationGenerated/SpellDocumentation.lua#L896)、[物品法术接口](https://github.com/Gethe/wow-ui-source/blob/8ea15b61e45c0ed4eba01439c90757f86eb78d34/Interface/AddOns/Blizzard_APIDocumentationGenerated/ItemDocumentation.lua#L948)

本轮只读文档，没有调用游戏接口或要求安装。接口证明有直接识别途径，不等于已经取得这个角色的完整实机法术书。非被动也不自动等于战斗可用；战斗限制、目标限制和当前状态须另外保留。

### 模拟器官方来源与实际查询

官方提供 `spell_query`（法术数据查询）功能；固定源码还直接保存 `active_class_spell_t`（职业主动法术表）、`active_pet_spell_t`（宠物主动法术表）和 `passive_class_spell_t`（职业被动法术表），无需先模拟伤害。职业表带专精编号，天赋表带专精适用范围及基础／替换编号；天赋法术还须结合 `SX_PASSIVE`（被动属性）判断。[官方查询文档](https://github.com/simulationcraft/simc/wiki/SpellQuery)、[主动表定义](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/class_spells.hpp#L13)、[天赋表定义](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/trait_data.hpp#L15)

官方查询文档将 `class_spell`（职业法术集合）描述为可点击的职业／宠物法术，但固定实现还加入了职业被动表。因此不能直接将查询名称当成筛选保证。另一个版本差异是查询职业名：固定实现接受 `deathknight`，文档旧示例的 `death_knight` 会得到空集合；本轮初次查询因此为空，随后根据源码更正，而不是把空结果当成没有技能。[集合实现](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/sc_spell_data.cpp#L393)、[职业名称实现](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/sc_spell_data.cpp#L210)

本轮用项目独立原版程序执行数据查询：`(class_spell.class=deathknight|talent_spell.class=deathknight)&spell.attribute!=6&spell.attribute!=22`。其中属性 6 是被动，22 是禁止战斗；这是候选筛选，不是“所有战斗按钮”的充分判据。原始集合为 66 项，仍含其他死亡骑士专精、宠物和替换前能力。再按职业主动表的通用／邪恶专精及天赋适用范围交叉筛选，留下以下 32 个来源候选编号：

| 分组 | 来源候选（编号） | 本轮解释 |
| --- | --- | --- |
| 已有单目标参考流程中的八类 | 爆发 `77575`、脓疮打击 `85948`、天灾打击 `55090`、死亡缠绕 `47541`、亡者大军 `42650`、黑暗突变 `1233448`、灵魂收割 `343294`、Putrefy（中文名待核）`1247378` | 这些可以从数据来源直接找到，不必靠已有伤害报告发现它们。 |
| 其他邪恶主动来源 | 亡者复生 `46584`、传染 `207317` | 前者在已有基线战前使用，后者的主动身份不因当前单目标参考未施放而消失。 |
| 职业通用来源 | 冰霜之路 `3714`、枯萎凋零 `43265`、寒冰锁链 `45524`、死亡脚步 `48265`、反魔法护罩 `48707`、巫妖之躯 `49039`、死亡之握 `49576`、死亡之门 `50977`、黑暗命令 `56222`、复活盟友 `61999` | 覆盖输出、控制、移动、辅助等能力；这里只证明来源候选，尤其不能因查询未筛掉死亡之门就声称它允许战斗使用。 |
| 适用于邪恶的天赋来源 | 心灵冰冻 `47528`、天灾契约 `48743`、冰封之韧 `48792`、灵界打击 `49998`、反魔法领域 `51052`、控制亡灵 `111673`、致盲冰雨 `207167`、幽魂步 `212552`、窒息 `221562` | 适用专精不等于当前角色已选；需要按角色天赋核对，不能全部认作本角色按钮。 |
| 替换前编号 | 亡者复生 `46585`、符文打击 `316239` | 邪恶主动表分别记录 `46584`、`85948` 对它们的替换，不能重复加入。 |
| 游戏策略辅助按钮 | Single-Button Assistant（一键辅助）`1229376` | 不是另一项伤害技能；不得将游戏动态策略当成固定序列技能。 |

这 32 项仍不是当前角色最终清单：没有完成已选天赋过滤，不包含完整种族能力、物品和状态替换展开。替换形态如脓疮镰刀也不能仅靠天赋入口编号查询发现。该表证明可以从元数据取得并分类候选，不能固化成新的人工白名单。[正式服主动数据](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/class_spells.inc)、[正式服天赋数据](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/trait_data.inc)、[属性定义](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/data_enums.hh#L1856)

查询输出与筛选摘要保存在 `.local/sim2gse/active-ability-sources/`：`dk-nonpassive-combat-query.xml`、`query.log`、`evidence.json`。这次执行的是数据库查询，没有加载角色进行战斗，也没有生成新的伤害成绩。

### 执行动作、饰品和药水的明确标记

| 标记／入口 | 能说明什么 | 不能单独说明什么 |
| --- | --- | --- |
| `action_t.background`（后台动作） | 为真时不能被动作优先级列表直接选择，但可以由其他动作触发。 | 不能单独判定游戏里是否有按钮；主动饰品的内部代理也可能被设成后台。 |
| `foreground_action_list`（前台动作列表） | 初始化后可供该列表直接选择的动作集合。 | 仍可能包含变量、列表调用及外部增益请求；宠物也有自己的列表。 |
| `dual`（重复统计控制） | 是否计入报告执行次数。 | 不是主动／被动标记。 |
| `SPECIAL_EFFECT_USE`（物品主动使用效果）、`has_use_special_effect()`（是否有主动效果） | 直接识别模型中的物品主动使用效果，之后对应 `use_item`（使用单件物品）。 | 有标记不等于物品特殊机制已验证，也不能把代理的后台标记当成被动物品。 |
| `potion`（药水动作） | 消耗品有独立入口，其基础效果也设为主动使用类型。 | 不能只查已装备的两个饰品槽位就认为覆盖了药水；当前基线关闭消耗品的设置仍然有效。 |

依据：[动作标记定义](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/action/action.hpp#L113)、[前台列表填充](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/action/action.cpp#L2850)、[物品主动检查](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/item/item.hpp#L252)、[主动饰品代理](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/player.cpp#L10450)、[消耗品效果初始化](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/consumable.cpp#L916)。

因此本票采用的取证顺序明确为：版本数据及主动标记 → 当前角色拥有的能力与替换关系 → 对应的原生执行入口 → 参考策略及日志交叉核对。主动身份与被动模型是否准确分开记录；规则决策完成，下文三个模型问题由执行模型验证承接。

## 当前角色的主动映射证据

下表状态均为“原生映射有证据；导出与输入控制待验证”，不代表已经通过游戏验收。编号由职业动作构造与正式服法术／天赋数据共同核对，不是照抄伤害日志。平均次数沿用 99 个统计样本，只描述基线，不规定序列中必须重复几次。

| 游戏能力 | 原生动作标识 | 当前施法编号 | 原生平均次数 | 对应关系及预期用例 |
| --- | --- | --- | --- | --- |
| 爆发 | `outbreak` | `77575` | 1.00 | `196780` 是范围子效果，不另建按钮；核对技能与疾病应用，T03／T13。 |
| 脓疮打击 | `festering_strike` | `85948` | 基础 10.58；替换 10.13 | 脓疮镰刀 `458128` 由当前状态替换，不能独立任选；核对替换前后同一按钮，T03／T13。 |
| 天灾打击 | `scourge_strike` | `55090` | 62.51 | 当前报告为该形态；其他天赋的吸血打击替换不能仅凭通用流程提及就认作当前已启用，T03／T13。 |
| 死亡缠绕 | `death_coil` | `47541` | 39.75 | 伤害／治疗子效果不是新按钮；本场景施放目标为当前敌人，T03／T13。 |
| 亡者大军 | `army_of_the_dead` | `42650` | 2.00 | 玩家召唤动作与召唤物后续行为分开；不能把每次宠物攻击算一次玩家输入，T03／T13。 |
| 黑暗突变 | `dark_transformation` | `1233448` | 4.00 | 当前主动编号不是旧增益 `63560` 或等级被动 `325554`；引擎对公共冷却有特殊处理，见下文，T03／T13。 |
| 灵魂收割 | `soul_reaper` | `343294` | 8.00 | 目标生命值及相关增益限制由原生角色状态处理；不能因为开场不可施放就剔除，T03／T13。 |
| Putrefy（邪恶主动技能，中文名待核） | `putrefy` | `1247378` | 12.00 | `1277016` 是伤害子动作，不能反代玩家施法编号；其召唤、消耗与效果继续走原生模型，T03／T13。 |

对应来源：职业模块的[动作构造入口](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L14328)、[正式服天赋映射](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/trait_data.inc#L1531)、[职业基础法术](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/class_spells.inc)。当前报告确实记录了上述 8 类主动动作；爆发有独立统计和样例轨迹，不能因文本摘要未列出完整明细就判定没有施放。

目标策略以原生动作性质核对：直接伤害技能使用当前敌人，亡者大军按召唤动作处理，黑暗突变按自身／宠物关联处理；不因统计里存在治疗分支就自动改变施法目标。公共冷却及施法期间可用性必须读取实际动作，黑暗突变的特殊处理不能由静态法术编号推断。这里确定了必须记录的能力，不代替后续控制器的实际限制检查。

还须保留两种初始化／启动能力：

| 能力 | 原生证据 | 处理与验收 |
| --- | --- | --- |
| 亡者复生 | `raise_dead / 46584`，基线战前执行 1 次；邪恶专精映射不同于其他专精的 `46585`。 | 保留明确的战前准备，双方初始宠物状态一致；不能把召唤物当作凭空出现。准备说明及控制器初始化在对应原型核对，T03／T13／T21。 |
| 开始自动攻击 | `auto_attack` 启动后由 `auto_attack_mh` 继续挥击；本身不占普通公共冷却。 | 对应明确的开始攻击命令；后续挥击保留原生时序，不每次挥击消耗一次输入。启动时机在执行原型核对，T03／T21。 |

来源：[亡者复生构造与战前处理](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L12216)、[专精编号映射](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/specialization_spells.inc#L276)、[自动攻击启动](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L7727)。

## 必须保留的模型与映射限制

- **状态替换**：脓疮打击明确根据 `festering_scythe`（替换增益）转交脓疮镰刀；其天赋编号 `455397` 与实际替换动作 `458128` 也不同。T13 必须检查基础按钮、替换状态、实际执行动作及导出结果的对应关系。[替换实现](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L10449)
- **黑暗突变公共冷却**：固定引擎在构造函数中将 `trigger_gcd`（公共冷却触发时间）设为零，并解释数据中的公共冷却只与其替换能力相关。因此不能按原始法术表的 1.5 秒硬编码。该特殊处理、可能的替换状态、同块命令顺序及公共冷却期间输入留给执行原型，尚无实机证明。[固定处理](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L8697)
- **目标与可用性**：灵魂收割有真实的目标生命值／增益可用性检查；黑暗突变还检查宠物状态。候选按钮不能绕过这些检查。资源、急速、冷却和施法限制继续由原生动作处理，不复制成一份静态数值表。[灵魂收割](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L12656)
- **导出依据尚有边界**：作者规范允许法术与宏命令动作块；固定编译器会处理法术编号与宏文本，但这不证明上述每个编号及替换在当前中文客户端可直接导出。沿用[序列编码研究](gse-research.md)，下一项只核对其编码／编译契约，实机校正仍在候选结果之后。[作者块规范](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/wiki/GSE-3.3-Block-Specification)、[固定编译入口](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2176)

## 装备与被动效果

当前两件饰品为虫群之瘤 `250245`、共鸣咆哮石 `250228`，均为被动触发。前者驱动 `1250589`，后者驱动 `1250564`，已有专用模型及本角色实际触发证据，继续完整保留装备和效果，不生成 `/use 13`、`/use 14`（使用饰品槽位命令）。这只说明当前样本不需要主动调用，**没有撤销方案中的主动饰品与双主动联合优化要求**。[物品取证](target-evidence.md)、[虫群之瘤模型](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear_midnight.cpp#L2943)、[共鸣咆哮石模型](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear_midnight.cpp#L2106)

当前 Omnium（全能天赋系统）五个节点的正式服映射如下。它们是原生被动效果输入，不是五个主动按钮；中文效果名尚未在目标客户端核对，保留英文标识及编号。

| 输入节点 | 驱动法术 | 效果标识 |
| --- | --- | --- |
| `136814` | `1279614` | Rune of Overload（符文效果） |
| `136821` | `1279610` | Rune of Burning Haste（符文效果） |
| `136817` | `1287555` | Rune of Lingering（符文效果） |
| `136819` | `1279603` | Rune of Self-Mending（符文效果） |
| `136822` | `1279599` | Rune of Unleashed Fire（符文效果） |

[正式服节点表](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/trait_data.inc#L3425)可直接查询这五项；不能因在测试服法术文本中未找到节点编号就判定缺少映射。

`Rune of Unleashed Fire`（符文效果）的伤害 `1286970` 与治疗 `1263002` 在原生报告中分别平均触发 24.17、5.77 次；引擎明确标记触发目标和伤害／治疗分流为尚未验证。它来自节点 `136822`，不是两件饰品或主手非天启提示。保留原模型与提示，归入“仅引擎支持、效果假设待验证”；不得把有伤害或退出码为零当成模型准确的证明。[模型与提示](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear_midnight.cpp#L5819)

节点解析入口会把编号解析为正式服法术；当前实现明确忽略输入中的等级字段。Overload、Burning Haste、Lingering（上述三项符文）虽然在注册表中是禁用的独立标记，核心模型仍读取它们，分别修改数值、生成急速增益及持续效果，不能据注册标记误判它们完全失效。[节点解析](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear.cpp#L3677)、[核心组合效果](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear_midnight.cpp#L5700)

另有本轮新确认的模型缺口：Self-Mending（自我修复符文，暂译）的节点与法术可解析，但未找到 `1279603 / 1287908` 的非生成代码注册或执行读取，不能声称其额外自疗已实现。正式服文本描述低于 75% 生命时，核心符文造成伤害或治疗后产生自疗。保留用户节点与这一缺口，不改天赋、不编造补偿，也不把角色可运行解释成完整效果支持。该治疗能力不属于本轮生存评分；其潜在触发联动仍待模型核对，不能仅以当前伤害正常排除影响。[效果文本](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/spelltext_data.inc#L28486)、[固定注册表](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/unique_gear_midnight.cpp#L6255)

主手 `enchant_id=6241` 对应 Rune of Sanguination（死亡骑士符文熔铸，中文名待核），驱动为 `326801`，不是天启符文 `6245`。固定模型包含灵界打击伤害修正与后台自疗，因此“非天启”本身不是未知附魔错误。但低生命触发文本与源码回调比较方向有需要核对的差异，不能将治疗阈值认作已验证；本轮没有修改附魔或引擎。[附魔表](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/spell_item_enchantment.inc#L4151)、[符文回调](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L12924)

肩部 `271472` 和腿部 `271473` 属于套装 `2055`，当前只有两件，启用邪恶 `MID2`（当前套装类别）的两件效果 `1296654`，不具备四件效果 `1296655`。两件效果修改魔导师与亡者之主的自主施法，已有报告中的对应宠物伤害；这些不是额外玩家按钮。[物品归属](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/item_data.inc#L182550)、[套装映射](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/dbc/generated/item_set_bonus.inc#L1168)、[宠物动作替换](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/sc_death_knight.cpp#L4588)

主动饰品继续执行原方案：从真实槽位和物品效果取得动作；经验证的主动使用方式进入序列及组合搜索，未知效果明确阻止相应模式，不能变成被动或默默删除。严格模式拒绝 `manual`（手动使用）与后台完美补放。本样本不能承担双主动使用的验收，对应用例保留到已有票据，不为本票替换用户装备。

## 三类状态与后续验收

| 类别 | 当前对象 | 处理及预期用例 |
| --- | --- | --- |
| 原生映射有证据 | 上述 8 类战斗主动技能、亡者复生、自动攻击启动；当前装备被动效果由原生机制保留。 | 保留能力，不宣称导出或实机已经通过。T03 检查同一角色下的动作来源、等级／天赋及物品身份。 |
| 待验证 | 当前按钮的中文导出、状态替换、黑暗突变特殊公共冷却、输入失败与队列语义；符文效果的官方模型假设、自我修复模型缺口与主手符文治疗阈值；未来主动饰品的具体模型与使用方式。 | 保留输入及现有原生模型，明确哪些效果未确认；不能标为完整角色兼容。T03 覆盖模型缺口报告，T13 核对施法／替换／派生效果编号；T21 检查隐藏主动扫描和手动模式拒绝。 |
| 不作为合法序列命令 | 派生伤害或宠物攻击编号、原生策略变量／列表调用、实时条件选择、无控制器的手动技能或饰品、尚未学会／错误天赋的技能。 | 拒绝错误命令，但保留合法的原生被动效果。未知动作必须报错，不自动跳过。T03／T13／T21 应有明确失败用例。 |

当前固定单目标流程没有使用灵界打击、反魔法护罩等额外输出兼防御动作，因此本票没有新增删除它们的策略。其他配置若在原生参考中使用此类能力，必须重新处理映射和比较条件，不能套用一份永久排除表。多目标分支中的枯萎凋零及传染不属于当前固定单目标可达流程；这不等于引擎不认识它们。

当前基线已关闭消耗品；原生模板虽然有能量灌注请求，本角色报告没有该增益，它也不是死亡骑士按钮。后续比较必须统一角色、战前准备、消耗品、外部增益及模型选项；不得一边得到额外效果、一边没有，仍宣称差距只来自序列。[原生流程](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/class_modules/apl/apl_death_knight.cpp#L368)、[外部增益请求实现](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/player.cpp#L10889)

## 缺口处置状态

| 事项 | 交接边界 | 对应验证须取得的结论 |
| --- | --- | --- |
| 导出、状态替换、输入与队列的实际验证 | 原型分别由既定导出契约和执行模型票承接，实机验证按用户决定后置；相应能力通过前不能标为已验证。 | 继续保留既有验收用例；不要求当前提前安装或执行后续原型。 |
| 核心符文的触发目标及伤害／治疗分流假设 | 沿用原生模型与提示，不改目标分流，不生成主动按钮。 | 模型及警告保持；未声称上游假设已准确性验收。 |
| 自我修复符文模型未确认 | 保留角色节点及原生处理，不自行补算自疗。 | 未找到专用代码不等于已证明缺失；保留疑点，不把核实全部上游实现作为控制器验收。 |
| 主手符文治疗阈值疑点 | 保留原始附魔及原生阈值，不按文本推断修改源码。 | 源码与文本差异未判为已证实错误；不新增项目修复。 |

按用户在[验证输入控制与饰品的最小执行模型](../../myspec/changes/sim2gse-wayfinder/issues/08-execution-prototype.md)结项时的最新决议，以上三项处置为继承的上游模型限制：保持固定模型即可开展离线搜索，输出保留引擎版本及原有提示，不宣称真实游戏收益。本项目仍须明确拒绝无法解析的角色数据、无法映射的主动动作和不支持的执行类型；不能借沿用上游之名删掉输入或静默漏掉动作。新增控制器造成的原生事件回归仍须修复。

本票已确定自动识别规则、映射边界、用例及模型疑点交接。自动能力提取器、导出器、输入控制器及上述测试均未由本文实现；继续按地图顺序处理，不能把决策完成或文档检查通过当作兼容性、产品或游戏验收通过。
