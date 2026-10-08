# 邪恶死亡骑士材料清洗与全量筛选

> 人工清洗、标准角色循环检查、全量五轮训练和历史反馈验收已完成。所有可训练材料都是明确改写，不是原作者宏的完整复现。

## 清洗结果

共整理 82 件：社区宏35件、WCL原始战斗记录10件及新构造片段5件、插件有序记录28件（对应31条原始记录）、受许可限制只留引用的SLG序列4件。
其中63件清洗材料带有程序；按程序文本精确去重后为52种。此处只按程序JSON文本去重，不代表编译后的行为已去重；需要实际编译并按模拟器身份复核。另有19件只保留原件/来源并标为当前不支持。所有带程序的清洗件均为明确改写；没有把任何人工件称为语义完全保留。
每件清洗件的完整节点、元数据或来源位置、逐项改动和程序保存在 `.local/tests/seed-training/full/materials/`。文件由一次性离线整理脚本生成；该脚本读取既有展开记录和固定人工决策，不新增宏解释器。

## 社区GSE记录

来源：主仓库本地 `.local/sim2gse/community-schemes-20261008/structure-records.json` 与 `expanded-structures.json`；35个成员逐个留档，原节点、作者字段、版本、原文件哈希和1基节点展开位置都保存在清洗件 `original`。作者 `Help` 字段原样保留在 `instructions`。

|序号|成员|状态/结构家族|实际取用内容|明确变化|
|---:|---|---|---|---|
|1|SCG_UNH_AOE v1 Default|已编译改写候选<br>`flat-expanded-priority-repeat`（优先循环展开为固定点击顺序后循环）|展开表中的普通技能点击顺序；剔除不映射的辅助/物品动作。|source_tokens展开为22个位置；Repeat/interval转成普通按键顺序，不保留原时间语义。 out_of_bounds_insertions=3；采用已存展开表，不声称与GSE运行时完全等价。|
|2|SCG_UNH_ST v1 Default|已编译改写候选<br>`flat-expanded-priority-repeat`（优先循环展开为固定点击顺序后循环）|展开表中的普通技能点击顺序；剔除不映射的辅助/物品动作。|source_tokens展开为17个位置；Repeat/interval转成普通按键顺序，不保留原时间语义。 out_of_bounds_insertions=3；采用已存展开表，不声称与GSE运行时完全等价。|
|3|Orb_UDK_ST-3.7 v1 Mythic+ w/semi|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及死亡缠绕、腐化、灵魂收割填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|4|Orb_UDK_ST-3.7 v2 Mythic+ w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及普通填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|5|Orb_UDK_ST-3.7 v3 PvP w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及普通填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|6|Orb_UDK_AoE-3.7 v1 Mythic+ w/semi|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|7|Orb_UDK_AoE-3.7 v2 Mythic+ w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|8|Orb_UDK_AoE-3.7 v3 PvP w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|9|Orb_UDK_AoE-3.0 v1 Mythic+ w/semi|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|10|Orb_UDK_AoE-3.0 v2 Mythic+ w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|11|Orb_UDK_AoE-3.0 v3 PvP w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条AOE内层施法序列及腐化填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|12|Orb_UDK_ST-3.0 v1 Mythic+ w/semi|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及普通填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|13|Orb_UDK_ST-3.0 v2 Mythic+ w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及普通填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|14|Orb_UDK_ST-3.0 v3 PvP w/auto|已编译改写候选<br>`embedded-castsequence-plus-fillers`（一条内层施法序列加普通填充按键）|一条ST内层施法序列及普通填充。|所选CastSequence保留成功施放才推进；GSE外层前进/失败/重置调度未完整复现。 @player/@cursor/目标条件改用当前固定敌方模型，不能据此验证游戏中的地面落点。|
|15|SBA_UNHOLY v1|保留原件，不生成候选<br>`assistedbutton-conditional`（按条件选技能的辅助按钮，当前不能表达）|AssistedButton（辅助按钮）和条件当前不能表达。|SBA_UNHOLY.Macros[1].Actions[4] -> 原件完整保留；当前搜索入口不支持AssistedButton及其条件，未猜测成普通技能序列。 SBA_UNHOLY.Macros[1].Actions[5] -> 原件完整保留；当前搜索入口不支持AssistedButton及其条件，未猜测成普通技能序列。|
|16|SheHulks_UNSing_-_1_Button v1|已编译改写候选<br>`one-button-sequential-cycle`（单按键按顺序逐步循环）|一圈单体Sequential（顺序执行）正文。|SheHulks_UNSing_-_1_Button.Macros[1].Actions[2] -> 删除：选敌、开始攻击、宠物或停止宏控制不属于当前技能循环模拟。 移除Raise Dead、饰品13/14、反魔法护罩及nochanneling门控；原count只取一圈顺序正文。|
|17|SheHulks_UNMult_-_1_Button v1|已编译改写候选<br>`one-button-sequential-cycle`（单按键按顺序逐步循环）|一圈群体Sequential（顺序执行）正文。|SheHulks_UNMult_-_1_Button.Macros[1].Actions[2] -> 删除：选敌、开始攻击、宠物或停止宏控制不属于当前技能循环模拟。 移除Raise Dead、饰品13/14、反魔法护罩及nochanneling门控；原count只取一圈顺序正文。|
|18|EA_UDK_v0.2 v1 Default|已编译改写候选<br>`paired-independent-castsequences`（两条独立推进的施法序列加普通填充按键）|EA人工整理件B：7成员与4成员两条独立施法序列，加两个普通填充键。|改成四个外层按键：保留Actions[4]七成员、Actions[2]/Actions[6][2]四成员的顺序及重置。 删除ReversePriority、定期插入/重复、其它独立CastSequence、修饰键/null、宠物、饰品及地面定位；不是原宏完整复现。|
|19|MOB_UDK_ST v1 Default|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|MOB人工整理件A：爆发前缀+34步三角递增循环。|采用已审过的MOB-derived37：Outbreak、Army、Dark Transformation前缀+34步三角循环；三个前缀取自合法动作池，不声称原件自动施放。 删除Actions[1]饰品、宠物、选敌/攻击与停止宏；Priority外层改为固定顺序。|
|20|MOB_UDK_MYTH_AOE v1 Default|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|6步逐层增长重复两轮，再接4步尾段；与MOB-ST及SOL同属一个结构家族。|按预先生成的source_tokens顺序取每次点击的无修饰键普通分支；去掉宠物准备与饰品13/14，Priority/Sequential外层展平。 源@player死亡凋零使用当前固定敌方模型，不等同原游戏地面落点。|
|21|Main_Spam_UDK v1|保留原件，不生成候选<br>`same-key-builder-spender-pair`（同一按键块含两个GCD动作，当前入口不能表达）|同一按键块含脓疮打击+天灾打击两个GCD，入口拒绝；不拆成两个键。|Main_Spam_UDK.Versions[1].Actions[1][4] -> 保留原件但不生成程序：Main_Spam同一个GSE Action含脓疮打击和天灾打击两个GCD；搜索入口拒绝同块多GCD，拆成两键会改推进语义。 Main_Spam_UDK.Versions[1].Actions[1][5] -> 保留原件但不生成程序：Main_Spam同一个GSE Action含脓疮打击和天灾打击两个GCD；搜索入口拒绝同块多GCD，拆成两键会改推进语义。|
|22|Burst_Cooldowns_UDK v1|保留原件，不生成候选<br>`burst-only-action-set`（独立爆发键含普通输出，不构成主循环）|Kim独立爆发键含冷却与普通输出；作者要求在需要爆发时持续按，不是一次性冷却按钮。|Burst_Cooldowns_UDK.Versions[1].Actions[1][5] -> 保留原件但不作为起点：这是独立爆发键，但含腐化、死亡缠绕等普通输出；作者要求需要爆发时持续按，不是一次按下就结束的纯冷却键。 Burst_Cooldowns_UDK.Versions[1].Actions[1][6] -> 保留原件但不作为起点：这是独立爆发键，但含腐化、死亡缠绕等普通输出；作者要求需要爆发时持续按，不是一次按下就结束的纯冷却键。|
|23|Main_Spam_UDK v1|保留原件，不生成候选<br>`same-key-builder-spender-pair`（同一按键块含两个GCD动作，当前入口不能表达）|同一按键块含脓疮打击+天灾打击两个GCD，入口拒绝；不拆成两个键。|Main_Spam_UDK.Versions[1].Actions[1][4] -> 保留原件但不生成程序：Main_Spam同一个GSE Action含脓疮打击和天灾打击两个GCD；搜索入口拒绝同块多GCD，拆成两键会改推进语义。 Main_Spam_UDK.Versions[1].Actions[1][5] -> 保留原件但不生成程序：Main_Spam同一个GSE Action含脓疮打击和天灾打击两个GCD；搜索入口拒绝同块多GCD，拆成两键会改推进语义。|
|24|Burst_Cooldowns_UDK v1|保留原件，不生成候选<br>`burst-only-action-set`（独立爆发键含普通输出，不构成主循环）|Kim V1.1独立爆发键含冷却与普通输出；作者要求在需要爆发时持续按，不是一次性冷却按钮。|Burst_Cooldowns_UDK.Versions[1].Actions[1][5] -> 保留原件但不作为起点：这是独立爆发键，但含腐化、死亡缠绕等普通输出；作者要求需要爆发时持续按，不是一次按下就结束的纯冷却键。 Burst_Cooldowns_UDK.Versions[1].Actions[1][6] -> 保留原件但不作为起点：这是独立爆发键，但含腐化、死亡缠绕等普通输出；作者要求需要爆发时持续按，不是一次按下就结束的纯冷却键。|
|25|unholydk_ST v1|已编译改写候选<br>`flat-cooldown-led-cycle`（冷却动作前置的展开顺序循环）|单体普通技能展开顺序。|改写保留：取无修饰键普通分支作为展开顺序第22次点击；重复位置依source_tokens保留。 移除选敌/开始攻击；展开普通技能顺序作为新循环，不保留原GSE分段和间隔。|
|26|unholydk_m+ v1|已编译改写候选<br>`mod-free-priority-expansion`（移除修饰键分支后的优先循环展开）|无修饰键的普通分支展开；一次56点击顺序。|保留source_tokens对应的无修饰键末级技能分支，删去ctrl/shift手动爆发和channel门控；Priority/Repeat展平为一次56步顺序。 源@player死亡凋零使用固定敌方模型，目标位置语义有变化。|
|27|unholydk_m+ v1|已编译改写候选<br>`long-sequential-body-compressed`（长顺序主体仅取一圈）|999次循环中取一次完整13步正文。|原999次循环只取一次13步正文，作为候选新循环；循环次数被压缩，不宣称原件等价。 删除首个选敌/攻击宏。|
|28|unholydk_m+ v1|已编译改写候选<br>`long-body-with-manual-burst-slots-removed`（删去手动爆发位置后的顺序主体）|取正文11个普通动作，移除两个只由Alt控制的爆发位置。|原13个位置中的Army与Dark Transformation仅有alt手动键分支，删除两格，周期由13步缩短为11步。 999次循环压缩为一次正文，删除选敌/攻击宏。|
|29|FLIP_UH_AOE_V4 v1 AOE V4 - RP Drain + Cursor DnD|已编译改写候选<br>`interleaved-epidemic-and-spender`（资源生成与消耗技能交错；此族包含单体和群体成员，单体成员不含Epidemic（群体消耗技能），英文旧代号不表示每件都含Epidemic）|FLIP群体普通施法展开，首步Outbreak（疾病爆发）改成普通动作。|删除宠物、mod:shift、目标条件、target/combat重置与null；固定点击间隔。 @cursor/@player死亡凋零改为当前固定敌方模型。|
|30|FLIP_UH_ST_V3 v1 ST V3 - Controlled Outbreak|已编译改写候选<br>`interleaved-epidemic-and-spender`（资源生成与消耗技能交错；此族包含单体和群体成员，单体成员不含Epidemic（群体消耗技能），英文旧代号不表示每件都含Epidemic）|FLIP单体普通施法展开，首步Outbreak（疾病爆发）改成普通动作；本件含Death Coil（死亡缠绕），不含Epidemic（群体消耗技能）。|删除宠物、mod:shift、目标条件、target/combat重置与null；固定点击间隔。 @cursor/@player死亡凋零改为当前固定敌方模型。|
|31|SOL_UDK_Aoe v1 Rider|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|Rider（天启骑士）无修饰键普通分支；两轮三角增长后接尾段。|把Priority循环依source_tokens展开。 源@player死亡凋零按固定敌方模型执行，目标位置变化。|
|32|SOL_UDK_Aoe v2 San'layn|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|San’layn（血裔）无修饰键普通分支；两轮三角增长后接尾段。|源@player死亡凋零按固定敌方模型执行，目标位置变化。 原件中San’layn专属Putrefy修饰键分支未进入候选。|
|33|SOL_UDK_ST v1 Rider|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|Rider（天启骑士）无修饰键普通分支；两轮三角增长后接尾段。|把Priority循环依source_tokens展开。 源@player死亡凋零按固定敌方模型执行，目标位置变化。|
|34|SOL_UDK_ST v2 San'layn|已编译改写候选<br>`triangle-growth-with-two-pass-and-tail`（三角递增顺序重复两轮后接固定尾段）|San’layn（血裔）无修饰键普通分支；两轮三角增长后接尾段。|源@player死亡凋零按固定敌方模型执行，目标位置变化。 原件中San’layn专属Putrefy修饰键分支未进入候选。|
|35|EA_UDK_v0.2 v1 Default|已编译改写候选<br>`paired-independent-castsequences`（两条独立推进的施法序列加普通填充按键）|EA人工整理件B：7成员与4成员两条独立施法序列，加两个普通填充键。|改成四个外层按键：保留Actions[4]七成员、Actions[2]/Actions[6][2]四成员的顺序及重置。 删除ReversePriority、定期插入/重复、其它独立CastSequence、修饰键/null、宠物、饰品及地面定位；不是原宏完整复现。|
### 作者整套方案的按键说明与来源

以下说明来自本地 `report.md`、`structure-analysis.md` 和保存的主题内容，描述作者原方案。上表和清洗件的 `program` 字段描述本次整理件。导入署名与论坛主题作者不同的情况已分别写明。

- **1 Community 01 SCG_UNH_AOE v1 Default**：本件是SCG配套中的群体成员。作者方案还需要游戏内外层宏：SHIFT选择单体凋零缠绕／群体传染分支，CTRL选择灵界打击，再调用指定的单体或群体GSE成员。群体技能也有一部分写在外层宏里；GSE成员本身还会自动尝试亡者大军和黑暗突变。来源：SCG论坛主题 https://wowlazymacros.com/t/50005；收集报告记录版本为12.0.7，导入版本字段TOC（客户端接口号）=120007，不是12.1验证。论坛主题作者标为Thesairen，导入序列署名Detnit@Echo Isles，身份不合并。
- **2 Community 02 SCG_UNH_ST v1 Default**：本件是SCG配套中的单体成员。作者方案还需要游戏内外层宏：SHIFT选择凋零缠绕，CTRL选择灵界打击，再调用指定的单体或群体GSE成员。群体技能的一部分写在外层宏里；GSE成员本身还会自动尝试亡者大军和黑暗突变。来源：SCG论坛主题 https://wowlazymacros.com/t/50005；收集报告记录版本为12.0.7，导入版本字段TOC（客户端接口号）=120007，不是12.1验证。论坛主题作者标为Thesairen，导入序列署名Detnit@Echo Isles，身份不合并。
- **15 Community 15 SBA_UNHOLY v1**：作者帖子把整套内容称为单体与顺劈/群体的游戏单键辅助轮转。包内共列五项：SBA_UNHOLY序列，以及Mind Freeze（打断）、Lichborne（自保）、Anti-Magic Zone（群体减伤）、Death’s Advance（移动）四个辅助宏。SBA_UNHOLY调用游戏内辅助选择（技能ID 1229376），不是展开成普通技能优先序列的宏。来源：https://wowlazymacros.com/t/60282；帖子标题写12.0，导入版本字段TOC（客户端接口号）=120000。论坛发帖账号为lloskka，导入序列署名Demonchild@DunModr，两者不合并。
- **16 Community 16 SheHulks_UNSing_-_1_Button v1**：本件是SheHulk旧论坛方案的单体键。作者说明把导入的单体与群体成员分别绑定按键，并配套天启骑士天赋；帖子提供先导入GSE序列、再绑定自己按键、导入天赋的步骤。这两个键按目标数量切换，不是主循环键加爆发键。来源：https://wowlazymacros.com/t/60347；旧序列导入版本字段TOC（客户端接口号）=120000，未明确支持12.1。当前GSEUnited集合是另一份未取得的方案，不能混为同一版本。
- **17 Community 17 SheHulks_UNMult_-_1_Button v1**：本件是SheHulk旧论坛方案的群体键。作者说明把导入的单体与群体成员分别绑定按键，并配套天启骑士天赋；帖子提供先导入GSE序列、再绑定自己按键、导入天赋的步骤。这两个键按目标数量切换，不是主循环键加爆发键。来源：https://wowlazymacros.com/t/60347；旧序列导入版本字段TOC（客户端接口号）=120000，未明确支持12.1。当前GSEUnited集合是另一份未取得的方案，不能混为同一版本。
- **19 Community 19 MOB_UDK_ST v1 Default**：作者MOB提供单体与群体两条成员，建议3个以上目标切到群体键。循环中ALT配合按键触发亡者大军/黑暗突变，SHIFT控制天灾打击；群体键还有CTRL地面死亡凋零。已展开的原宏仍有普通按键可用的死亡凋零，所以CTRL不表示它已从主循环完全移除。起手会尝试使用饰品13和14。来源：https://wowlazymacros.com/t/61486；帖子明确写12.0.5，导入版本字段TOC（客户端接口号）=120005，是旧版参考。论坛主题作者名为MOB，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。
- **20 Community 20 MOB_UDK_MYTH_AOE v1 Default**：作者MOB提供单体与群体两条成员，建议3个以上目标切到群体键。循环中ALT配合按键触发亡者大军/黑暗突变，SHIFT控制天灾打击；群体键还有CTRL地面死亡凋零。已展开的原宏仍有普通按键可用的死亡凋零，所以CTRL不表示它已从主循环完全移除。起手会尝试使用饰品13和14。来源：https://wowlazymacros.com/t/61486；帖子明确写12.0.5，导入版本字段TOC（客户端接口号）=120005，是旧版参考。论坛主题作者名为MOB，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。
- **21 Community 21 Main_Spam_UDK v1**：本件来自Kim两键方案首帖的主循环。作者说平时持续按主循环键，另一个键用于开怪、大怪群或首领爆发；还建议用冷却提示并手动使用饰品。来源：https://wowlazymacros.com/t/62086；本件来自首帖，导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **22 Community 22 Burst_Cooldowns_UDK v1**：本件来自Kim两键方案首帖的独立爆发键。作者把它用于开怪、大怪群或首领，但它同时含普通输出动作（腐化、死亡缠绕等），并非只按一下就结束的纯冷却键；作者要求在需要爆发时继续按这个键。另建议用冷却提示；饰品由玩家手动使用。来源：https://wowlazymacros.com/t/62086；本件来自首帖，导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **23 Community 23 Main_Spam_UDK v1**：本件来自Kim两键方案第7帖的V1.1主循环。作者说明单体时必须按住SHIFT继续按主循环键，死亡缠绕才会触发；作者称测试时群体伤害提高，并请读者试用反馈。此SHIFT分支不是完整互斥的单体/群体切换。来源：https://wowlazymacros.com/t/62086/7；这是首帖之后的V1.1修订，不与首帖版本合并；导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **24 Community 24 Burst_Cooldowns_UDK v1**：本件来自Kim两键方案第7帖的V1.1独立爆发键。作者把它用于开怪、大怪群或首领，但它同时含普通输出动作（腐化、死亡缠绕等），并非只按一下就结束的纯冷却键；作者要求在需要爆发时继续按这个键。另建议用冷却提示；饰品由玩家手动使用。来源：https://wowlazymacros.com/t/62086/7；这是首帖之后的V1.1修订，不与首帖版本合并；导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **25 Community 25 unholydk_ST v1**：本件是Karen首帖的单体成员。首帖同时给出单体和大秘境/顺劈方案，作者强调按顺序循环、先准备再消耗资源，并称单体版本含自动爆发。第49帖（https://wowlazymacros.com/t/62253/49）作者说大秘境版已更新、单体版尚未更新；因此本件只是首帖单体，不代表后来已修订的单体方案。来源：https://wowlazymacros.com/t/62253；本件取首帖，导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **26 Community 26 unholydk_m+ v1**：本件是Karen首帖的大秘境成员。首帖版本在循环中重复带CTRL的亡者大军/黑暗突变步骤和SHIFT灵魂收割步骤；第49帖（https://wowlazymacros.com/t/62253/49）作者确认大秘境版已更新，但单体版尚未更新。不要把首帖自动爆发与后续手动修订当成同一方案。来源：https://wowlazymacros.com/t/62253；本件取首帖，导入版本字段TOC（客户端接口号）=120005，帖子未明确标注12.1。
- **27 Community 27 unholydk_m+ v1**：本件来自Karen后续第16帖版本，取一圈13步顺序正文，把原件999次外层重复压成一次候选循环。结构分析记录该版本仍有自动爆发；它不是第21帖的手动修订版。来源：https://wowlazymacros.com/t/62253/16；导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **28 Community 28 unholydk_m+ v1**：本件来自Karen后续第21帖版本，取一圈13步顺序正文；原串把亡者大军和黑暗突变放在ALT条件步骤，需要按到对应位置并继续按键，不是一键爆发。作者第49帖（https://wowlazymacros.com/t/62253/49）说大秘境版已更新、单体版尚未更新；第51帖（https://wowlazymacros.com/t/62253/51）另解释：CTRL控制大军/黑暗突变，SHIFT控制灵魂收割；该说明与保存的第21帖ALT原串分别记录，不把它们写成同一版本。不要把第16帖仍自动爆发的版本与第21帖手动修订混在一起。来源：https://wowlazymacros.com/t/62253/21；导入版本字段TOC（客户端接口号）=120001，帖子未明确标注12.1。
- **29 Community 29 FLIP_UH_AOE_V4 v1 AOE V4 - RP Drain + Cursor DnD**：本件是Flip群体V4成员。作者把大军/黑暗突变等爆发与饰品留给手动操作；ALT改变地面技能死亡凋零的位置，SHIFT用于补疾病。清洗候选只取普通分支，不复现这些修饰键与落点操作。来源：https://wowlazymacros.com/t/63714；帖子与导入版本字段标为12.0.7（TOC=120007），作者未称其为已验证的12.1方案。
- **30 Community 30 FLIP_UH_ST_V3 v1 ST V3 - Controlled Outbreak**：本件是Flip单体V3成员。作者说明疾病爆发会按目标/战斗状态自动施放一次；长首领战可按住SHIFT强制刷新。宠物协助/攻击及原单体版本的死亡缠绕、脓疮打击、天灾打击、腐化节奏仍保留；大冷却、打断、防御、移动、饰品和药水由玩家手动操作。来源：https://wowlazymacros.com/t/63714；帖子与导入版本字段标为12.0.7（TOC=120007），不是已验证的12.1方案。作者原文说明Help字段全文保留在本件前段说明。
- **31 Community 31 SOL_UDK_Aoe v1 Rider**：作者Søl的12.1方案；本件为群体、天启骑士天赋版本。作者要求手动起手疾病爆发和两次脓疮打击，平时按主键；按住ALT并继续按主键，直到饰品13、亡者大军、黑暗突变完成。CTRL控制腐化相关组合，SHIFT控制灵魂收割，CTRL+SHIFT控制致盲冰雨；黑暗突变放在两次亡者大军之间，必要时手动补脓疮打击。这是组合键控制方式，不是独立第三个爆发序列；候选只取无修饰键普通分支。来源：https://wowlazymacros.com/t/64010；帖子明确标注12.1、首帖9月27日更新，导入TOC=120100。帖子作者标为Søl，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。
- **32 Community 32 SOL_UDK_Aoe v2 San'layn**：作者Søl的12.1方案；本件为群体、萨莱因天赋版本。作者要求手动起手疾病爆发和两次脓疮打击，平时按主键；按住ALT并继续按主键，直到饰品13、亡者大军、黑暗突变完成。CTRL控制腐化相关组合（萨莱因分支含8秒重置），SHIFT控制灵魂收割，CTRL+SHIFT控制致盲冰雨；黑暗突变放在两次亡者大军之间，必要时手动补脓疮打击。这是组合键控制方式，不是独立第三个爆发序列；候选只取无修饰键普通分支。来源：https://wowlazymacros.com/t/64010；帖子明确标注12.1、首帖9月27日更新，导入TOC=120100。帖子作者标为Søl，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。
- **33 Community 33 SOL_UDK_ST v1 Rider**：作者Søl的12.1方案；本件为单体、天启骑士天赋版本。作者要求手动起手疾病爆发和两次脓疮打击，平时按主键；按住ALT并继续按主键，直到饰品13、亡者大军、黑暗突变完成。CTRL控制腐化相关组合，SHIFT控制灵魂收割，CTRL+SHIFT控制致盲冰雨；黑暗突变放在两次亡者大军之间，必要时手动补脓疮打击。这是组合键控制方式，不是独立第三个爆发序列；候选只取无修饰键普通分支。来源：https://wowlazymacros.com/t/64010；帖子明确标注12.1、首帖9月27日更新，导入TOC=120100。帖子作者标为Søl，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。
- **34 Community 34 SOL_UDK_ST v2 San'layn**：作者Søl的12.1方案；本件为单体、萨莱因天赋版本。作者要求手动起手疾病爆发和两次脓疮打击，平时按主键；按住ALT并继续按主键，直到饰品13、亡者大军、黑暗突变完成。CTRL控制腐化相关组合（萨莱因分支含8秒重置），SHIFT控制灵魂收割，CTRL+SHIFT控制致盲冰雨；黑暗突变放在两次亡者大军之间，必要时手动补脓疮打击。这是组合键控制方式，不是独立第三个爆发序列；候选只取无修饰键普通分支。来源：https://wowlazymacros.com/t/64010；帖子明确标注12.1、首帖9月27日更新，导入TOC=120100。帖子作者标为Søl，序列导入信息署名Tippuhdisdek@Burning Blade，身份不合并。

### 社区候选的统一边界

所有可搜索程序都把原作者的完整方案改成固定自动点击序列。修饰键、饰品、选敌、宠物、停宏、等待与GSE外层调度只在原件/清洗说明中记录，不在候选中假装已重现。原序列中删去步骤可能缩短周期，具体到节点的原因见每件JSON。
Orbalisk（奥巴里斯克）成员只取实际内层 `/castsequence`（施法成功才推进）片段和明确填充；不复制外层Priority（优先循环）、多条独立序列之间的状态共享、null（空位）及完整重复结构。Kim（Kim）主循环因同块两个GCD不被搜索入口接受而保留为unsupported（当前不可表达）；独立爆发键不冒充主循环。Karen（Karen）长件把999次重复缩为一份正文，步骤变化写入JSON。

## WCL数据

来源：本地 `wcl-structure-precheck-20261008/ordered-analysis.json`。10份成功施法日志完整保存为不可直接复现的原始参考；未把施法时间解释为按键间隔。另选分析文件前五个高重叠片段，分别构成新的六动作循环，统一归入 `wcl-core-family`（多场日志中重叠的六步施法片段）；这五条互有重叠，不代表五种独立结构，也不是五个来源名额。这些不是原玩家宏或已证明的循环。

|排名|角色|成功施法事件数|作为原始参考的状态|
|---:|---|---:|---|
|1|이촌동|350|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|2|꿀꿀멍멍꿀꿀멍멍|345|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|3|Zzdk|334|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|4|이해도|346|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|5|룬부패|344|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|6|Exodk|381|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|7|Zados|362|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|8|紅袖添香灬|358|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|9|Rimwaztok|352|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|
|10|Raashe|410|unsupported（当前不支持原宏重现）：无按键/失败/等待/循环边界。|

|新六步候选|整理动作顺序|来源重叠角色数|来源位置数|状态|
|---:|---|---:|---:|---|
|1|death_coil → scourge_strike → festering_strike → festering_strike → death_coil → scourge_strike|8|8|新构造，已通过两次外层回绕检查|
|2|scourge_strike → festering_strike → festering_strike → death_coil → scourge_strike → scourge_strike|8|8|新构造，已通过两次外层回绕检查|
|3|scourge_strike → scourge_strike → death_coil → death_coil → scourge_strike → festering_strike|7|7|新构造，已通过两次外层回绕检查|
|4|festering_strike → festering_strike → death_coil → scourge_strike → scourge_strike → death_coil|7|7|新构造，已通过两次外层回绕检查|
|5|scourge_strike → death_coil → death_coil → scourge_strike → festering_strike → festering_strike|6|6|新构造，已通过两次外层回绕检查|

## GearInsight插件数据

来源：本地 `gearinsight-research-20261008/inspection.tsv`。31条原始SEQ记录按完整有序ID串精确合并为28件；重复动作位置保留，重复来源行号全部留在各JSON。它们归为 `plugin-opener`（插件统计得到的有序起手动作串），不是原玩家完整循环。每件新候选按300毫秒普通点击排列并循环，这是新增模拟假设；原网页只描述opener（起手顺序），没有原按键、失败点击、等待或循环边界。

|序号|原始行号|原有序ID|清洗后的动作顺序|
|---:|---|---|---|
|1|2, 18|`77575,85948,458128,1233448,1297761,42650,1247378,1242174,343294,1242174,1247378,1242174,55090,1242174,55090`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → death_coil → soul_reaper → death_coil → putrefy → death_coil → scourge_strike → death_coil → scourge_strike|
|2|3, 19|`444347,77575,85948,458128,1297761,42650,1233448,1242174,1247378,1247378,1242174,55090,55090,55090,1242174`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → death_coil → putrefy → putrefy → death_coil → scourge_strike → scourge_strike → scourge_strike → death_coil|
|3|4, 20|`444347,77575,85948,458128,1297761,42650,1233448,1247378,1242174,1247378,1242174,55090,55090,343294,1242174`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → putrefy → death_coil → scourge_strike → scourge_strike → soul_reaper → death_coil|
|4|7|`48265,77575,55090,433895,55090,85948,458128,55090,55090,55090,77575`|outbreak → scourge_strike → scourge_strike → scourge_strike → festering_strike → festering_strike → scourge_strike → scourge_strike → scourge_strike → outbreak|
|5|8|`48265,77575,85948,48792,458128,42650,1233448,1247378,48707,433895,43265,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → scourge_strike → death_and_decay → scourge_strike|
|6|9|`433895,207317,433895,433895,49576,433895,48707,207317,433895,207317,207317,433895,207317,433895,55090`|scourge_strike → epidemic → scourge_strike → scourge_strike → scourge_strike → epidemic → scourge_strike → epidemic → epidemic → scourge_strike → epidemic → scourge_strike → scourge_strike|
|7|10|`55090,77575,47541,458128,1233448,1247378,433895,207317,433895,43265,433895,207317,207317,433895,433895`|scourge_strike → outbreak → death_coil → festering_strike → dark_transformation → putrefy → scourge_strike → epidemic → scourge_strike → death_and_decay → scourge_strike → epidemic → epidemic → scourge_strike → scourge_strike|
|8|13|`77575,85948,458128,42650,1233448,1297761,1242174,1247378,1247378,433895,343294,1242174,1242174,1242174,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → death_coil → putrefy → putrefy → scourge_strike → soul_reaper → death_coil → death_coil → death_coil → scourge_strike|
|9|14|`77575,85948,458128,42650,1233448,1297761,1247378,1247378,1242174,1242174,1242174,433895,433895,433895,343294`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → putrefy → death_coil → death_coil → death_coil → scourge_strike → scourge_strike → scourge_strike → soul_reaper|
|10|15|`85948,458128,42650,1233448,343294,1297761,1247378,1242174,55090,1242174,55090,55090,55090,1242174,85948`|festering_strike → festering_strike → army_of_the_dead → dark_transformation → soul_reaper → putrefy → death_coil → scourge_strike → death_coil → scourge_strike → scourge_strike → scourge_strike → death_coil → festering_strike|
|11|23|`85948,458128,42650,1233448,1297761,343294,1247378,1242174,433895,1242174,1247378,433895,433895,433895,1242174`|festering_strike → festering_strike → army_of_the_dead → dark_transformation → soul_reaper → putrefy → death_coil → scourge_strike → death_coil → putrefy → scourge_strike → scourge_strike → scourge_strike → death_coil|
|12|24|`77575,85948,458128,1297761,1233448,42650,1247378,1247378,1242174,1242174,1242174,343294,1242174,433895,433895`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → putrefy → death_coil → death_coil → death_coil → soul_reaper → death_coil → scourge_strike → scourge_strike|
|13|25|`77575,85948,458128,42650,1297761,1233448,1247378,343294,1242174,1242174,433895,1242174,433895,1242174,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → soul_reaper → death_coil → death_coil → scourge_strike → death_coil → scourge_strike → death_coil → scourge_strike|
|14|28|`77575,55090,85948,458128,42650,1233448,1297761,49039,1247378,1242174,433895,1242174,433895,433895,1242174`|outbreak → scourge_strike → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → scourge_strike → death_coil → scourge_strike → scourge_strike → death_coil|
|15|29|`77575,85948,458128,42650,1297761,1233448,1247378,1242174,1242174,433895,433895,1242174,433895,433895,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → death_coil → scourge_strike → scourge_strike → death_coil → scourge_strike → scourge_strike → scourge_strike|
|16|30|`77575,85948,458128,1233448,1297761,42650,1247378,1242174,1242174,433895,433895,1247378,343294,1242174,1242174`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → death_coil → death_coil → scourge_strike → scourge_strike → putrefy → soul_reaper → death_coil → death_coil|
|17|33|`77575,85948,458128,1297761,42650,1233448,1247378,1242174,1247378,1242174,48265,433895,1242174,343294,1242174`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → putrefy → death_coil → scourge_strike → death_coil → soul_reaper → death_coil|
|18|34|`85948,458128,42650,1233448,343294,1247378,1242174,433895,1242174,433895,1242174,433895,85948,433895`|festering_strike → festering_strike → army_of_the_dead → dark_transformation → soul_reaper → putrefy → death_coil → scourge_strike → death_coil → scourge_strike → death_coil → scourge_strike → festering_strike → scourge_strike|
|19|35|`77575,85948,458128,1233448,1297761,42650,1247378,1242174,1242174,1242174,433895,433895,433895,1242174,433895`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → death_coil → death_coil → death_coil → scourge_strike → scourge_strike → scourge_strike → death_coil → scourge_strike|
|20|38|`77575,85948,458128,42650,1233448,1297761,1242174,1247378,1247378,433895,433895,343294,1242174,1242174,1242174`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → death_coil → putrefy → putrefy → scourge_strike → scourge_strike → soul_reaper → death_coil → death_coil → death_coil|
|21|39|`77575,85948,458128,1297761,42650,1233448,1247378,1242174,1247378,433895,1242174,1242174,343294,433895,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → putrefy → scourge_strike → death_coil → death_coil → soul_reaper → scourge_strike → scourge_strike|
|22|40|`77575,85948,48265,458128,1297761,1233448,42650,1247378,1242174,1242174,433895,433895,1247378,343294,1242174`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → death_coil → death_coil → scourge_strike → scourge_strike → putrefy → soul_reaper → death_coil|
|23|43|`77575,85948,458128,42650,1233448,1297761,49039,1242174,1247378,1242174,1247378,1242174,55090,343294,55090`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → death_coil → putrefy → death_coil → putrefy → death_coil → scourge_strike → soul_reaper → scourge_strike|
|24|44|`77575,85948,458128,1297761,42650,1233448,1247378,1242174,48707,1242174,1242174,1247378,1242174,55090,343294`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → death_coil → death_coil → death_coil → putrefy → death_coil → scourge_strike → soul_reaper|
|25|45|`77575,85948,458128,1297761,42650,1233448,1247378,1247378,1242174,1242174,343294,55090,55090,1242174,1242174`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → putrefy → putrefy → death_coil → death_coil → soul_reaper → scourge_strike → scourge_strike → death_coil → death_coil|
|26|48|`77575,85948,458128,1233448,1297761,42650,1247378,1242174,1242174,1242174,1247378,48707,343294,1242174,55090`|outbreak → festering_strike → festering_strike → dark_transformation → army_of_the_dead → putrefy → death_coil → death_coil → death_coil → putrefy → soul_reaper → death_coil → scourge_strike|
|27|49|`77575,85948,458128,49039,1297761,42650,1233448,1242174,1242174,1247378,433895,1242174,1247378,343294,433895`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → death_coil → death_coil → putrefy → scourge_strike → death_coil → putrefy → soul_reaper → scourge_strike|
|28|50|`77575,85948,458128,42650,1297761,1233448,343294,1242174,1242174,1247378,1247378,1242174,1242174,1242174,55090`|outbreak → festering_strike → festering_strike → army_of_the_dead → dark_transformation → soul_reaper → death_coil → death_coil → putrefy → putrefy → death_coil → death_coil → death_coil → scourge_strike|

映射固定为：`1242174→death_coil`（死亡缠绕）、`433895→scourge_strike`（天灾打击）、`458128/85948/316239→festering_strike`（脓疮打击）、`1247378→putrefy`（腐化）、`1233448→dark_transformation`（黑暗突变）、`77575→outbreak`（疾病爆发）、`42650→army_of_the_dead`（亡者大军）、`343294→soul_reaper`（灵魂收割）、`207317→epidemic`（传染（群体技能））、`43265→death_and_decay`（死亡凋零）、`55090→scourge_strike`（天灾打击）。`1297761`装备项、`444347/48265`移动、`48707/49039/48792`防御、`49576`死亡之握按原位置逐项删除；其他未映射ID也保留原件并在清洗JSON说明，不猜成伤害动作。

## SLG下载包限制

只准备4个出处记录：`SLG-DK-UHL`单体、`SLG-DK-UHL-AOE`群体、`SLG-DK-Oh-!@#$`爆发/战复、`SLG-DK-GetOverHerE`拉怪/战复。文件8746796的下载包没有解码；清洗件只保留标题、来源和许可证引用，没有复制包内宏内容。许可证原文节选（`slg-license.txt` 第2(e)条）：

> “incorporate the Work, or any part of it, into any other software product, or ingest it into any tool, service, or dataset, including for the purpose of format Conversion or of any use described in section 5.”

这4件仅保留来源引用；unsupported（暂不接入）来自材料使用限制，不证明引擎无法表达。

## 后续验收边界

82件已通过公开登记入口写入主仓库既有共享数据中心。单体和五目标各按模拟器身份去重为52种程序，全部实际编译成功；每种请求3次迭代、得到2份有效统计样本，均观察到前两次外层循环回绕及150秒后的继续施放。共104次真实模拟、22份重复来源关联；轨迹和完整模拟记录保存在同一共享中心，检查摘要位于隔离工作树 `.local/tests/seed-training/full/audit-summary.json`。这仅证明改写候选可运行，不能证明原宏等价或内层冷却序列在180秒内完成两次循环。五轮训练、三随机条件复测与反馈结果见下表。

路径说明：本稿准备的材料在隔离工作树 `.local/tests/seed-training/full/materials/`；真实原始采集目录位于主仓库 `.local/sim2gse/`。这份准备稿不代替原作者许可或模拟结果。

## 全量训练与历史反馈验收（2026-10-09）

固定完整标准角色、1和5目标；每条独立五轮，每轮最多16候选、搜索600秒上限；初始和最终程序各在三个固定随机条件下复测。

|目标数|完成五轮|重复关联|失败|搜索新模拟|搜索缓存命中|入选|
|---:|---:|---:|---:|---:|---:|---:|
|1|56|33|0|4770|4465|4|
|5|56|33|0|4293|4715|4|

首次全批每场景完成55种程序（外部52种、历史3种），关联16份重复来源。补齐21份作者说明后，16个可表达版本复用旧结果，5个不可表达版本仅留说明，没有重复搜索或复测。中心103份来源版本对应82份材料，24份不可表达版本对应19份材料；版本数不冒称新材料数。

真实普通搜索在两场景均读入原四类起点加四个代表，分别5.032秒、5.078秒返回。历史反馈每场景新增两份记录：一份重复，一份完成五轮。再次启动均返回未变化、处理0份。

|目标数|来源|保留结构|复测平均每秒伤害|
|---:|---|---|---:|
|1|GearInsight ordered opener 27|历史搜索成果|152351.986|
|1|GearInsight ordered opener 11|插件有序起手循环|128818.038|
|1|Community 19 MOB_UDK_ST v1 Default|三角递增两轮加尾段|116370.006|
|1|Community 25 unholydk_ST v1|冷却动作前置的展开顺序循环|112321.402|
|5|既有历史搜索路径|历史搜索成果|358848.475|
|5|GearInsight ordered opener 11|插件有序起手循环|281600.360|
|5|Community 27 unholydk_m+ v1|长顺序主体取一圈|280321.997|
|5|Community 19 MOB_UDK_ST v1 Default|三角递增两轮加尾段|259029.653|

两场景均保留插件11号原始整理循环；优化冠军按历史成果归类。原始结构和优化后的程序分别保存；全部104个外部最终程序均未保留完整登记核心，不能把它们继续命名为原作者结构。五个日志片段均有五轮机会，本轮未入选四个代表；这只评价本次六步片段，不排除其他日志材料价值。

本次仅为固定自动按键、180秒标准场景。冷却技能删改与结构变化同时存在，初始成绩不能单独归因于结构；没有模拟人工爆发时机、分波副本或实际游戏，也未证明新增起点在正常600秒搜索中全面胜过原四起点。

完整证据在同一中心：seed_candidates（来源）、seed_processed（处理）、seed_selected（入选）、batches（模拟）、traces（轨迹）。本地full目录日志与acceptance-counts.json（验收计数）只作本次核查，不是另一套业务库。

主仓库旧基准引擎仍缺030完整动作目录补丁，旧受控二进制与本次构建也有时间字段差异。入选库严格匹配实际构建；目前通过的是隔离工作树入口。交付前须安全同步本次真实product（构建产物）及两份构建身份清单，保留旧目录，不能顺着旧链接覆盖文件。该同步待第二门禁明确批准，不重新构建引擎。
