# GSE 导入验证样本

原始导入串保存在 Git 忽略目录 `.local/sim2gse/gse-corpus/`；追加候选保存在 `.local/sim2gse/gse-corpus-additional/`。收集器 [`scripts/dev/collect_gse_samples.py`](../../scripts/dev/collect_gse_samples.py) 为每条原串记录来源、SHA-256（内容摘要）、GSE 版本、成员名和语法种类。原串不提交到 Git；文中记录的摘要用于复核本机文件。作者声称适用某个游戏版本，不代表已完成游戏内验收。

| 来源 | 用途 | 已观察语法 | GSE 版本 |
| --- | --- | --- | --- |
| [Søl 邪 DK 12.1](https://wowlazymacros.com/t/sols-12-1-unholy-dk-midnight-12-1-02-09-2026/64010) | AOE（群体）和 ST（单体） | Action（动作）、Loop（循环） | 3.3.31；作者标注 12.1 |
| [MOB 邪 DK](https://gseunited.com/t/mob-retail-death-knight-unholy/270) | 一条集合原串、两个成员 | Action、Loop | 3.3.13；游戏版本待复核 |
| [Flip 邪 DK 归档](https://gseunited.com/t/flip-s-unholy-death-knight-st-v3-aoe-v4-archived-12-0-7/669) | 两条旧版序列 | Action | 3.3.13；归档注明 12.0.7 |
| [MOB 鲜血 DK](https://gseunited.com/t/mob-retail-death-knight-blood/273) | 定期重复序列 | Action、Loop、Repeat（定期重复） | 3.3.13 |
| [MOB 守护德鲁伊](https://gseunited.com/t/mob-retail-druid-guardian-raid-mythic-delves-leveling/271) | 数组包裹序列 | Action、Loop、Repeat | 3.3.07 |
| [MOB 暗影牧师](https://gseunited.com/t/mob-retail-priest-shadow/277) | 两成员集合 | Action、Loop、Repeat | 3.3.11 |
| [Violent Benediction](https://wowlazymacros.com/t/64007) | 条件块 | Action、If（条件） | 原帖未注明 |
| [Karen 邪 DK](https://wowlazymacros.com/t/karens-unholy-dk-st-and-m-updated-m-macro/62253) | 一条集合原串、ST 与 M+ 两成员 | Action、Loop | 3.3.13 |
| [Kim 邪 DK](https://wowlazymacros.com/t/kims-unholy-sequence/62086) | 两条原串：主循环、爆发 | Loop、Repeat | 3.3.08 |

截至 2026-09-25，已收集 12 条不同的可解码原串，其中 9 条 DK（死亡骑士）串、2 条作者标注适用 12.1。原串共有 15 个序列成员；集合成员数与原串数分开统计。真实语料覆盖 Action、Loop、Repeat、If；公开真实 Pause（暂停）与 Embed（嵌入）原串仍缺。六类控制块完整矩阵由真实串和明确标注的固定上游合成向量共同验证；合成向量只证明固定上游语法处理能力，不算真实样本或游戏内验收。`!GSE3!+` 是上游加密外壳，不属于可解码原串。

## 追加原串摘要

追加采样限于 Karen 与 Kim 两个公开邪 DK 主题，原文未改写：

| 本机文件 | 序列成员 | GSE 版本 | SHA-256 |
| --- | --- | --- | --- |
| `karens-unholy-01.txt` | `unholydk_ST`, `unholydk_m+` | 3313 | `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497` |
| `kims-unholy-01.txt` | `Main_Spam_UDK` | 3308 | `b1f6e2cbebcc19c7c0adeb736cd07bbc1857c3363ff906810df0a175f06cafc2` |
| `kims-unholy-02.txt` | `Burst_Cooldowns_UDK` | 3308 | `5a5430d305b7821ba682e74cd3c07d673aa80d3f988f044cfe05f821d60b7824` |

这三条原串的 `inspect`（检查）均成功，四个成员都经过公开导入任务试跑。四个成员均未进入受控 DPS（每秒伤害）模拟：Karen ST 的 `spell 316239` 不在当前角色能力映射中；Karen M+ 的 `[nochanneling]` 条件无法确定；Kim 主循环的 `[channeling]` 条件无法确定；Kim 爆发序列的 `@player` 目标能力无法验证。没有把未识别动作替换为其他技能。

## 原样本严格映射结果

2026-09-24 的 11 个旧样本成员均可解码；下表记录当时首次试跑结果，不覆盖后续重试：

| 原串 / 成员 | 编译或映射结果 |
| --- | --- |
| Søl `SOL_UDK_AOE` | 首次试跑时 `spell 207317` 未出现在只看已执行动作的窄目录中；2026-09-25 经当前角色动作核对后通过，见下节 |
| Søl `SOL_UDK_ST` | 首次试跑时 `spell 316239` 未出现在只看已执行动作的窄目录中；2026-09-25 经当前角色动作核对后通过，见下节 |
| Flip 两个成员 | `/castsequence [@target,harm,nodead] reset=target/combat outbreak, null` 不支持 |
| MOB Unholy 两个成员 | `item 13` 未映射到当前角色；不把它假定为空点击 |
| MOB Blood | `[nochanneling]` 条件无法确定 |
| MOB Guardian | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持了该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Guardian 角色输入重跑 |
| MOB Shadow `MOB_SP_OPENER` | 未替换占位文本 `Need Stuff Here` 不支持 |
| MOB Shadow `MOB_SP_Myth` | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Shadow 角色输入重跑 |
| Violent Benediction | `=GSE.V.VB_IsHeals()` 需要游戏内变量，无法确定 If 分支 |

## 2026-09-25 当前角色动作目录重试

两条 Søl 原串未经改动，来自[作者的 12.1 邪 DK 帖](https://wowlazymacros.com/t/sols-12-1-unholy-dk-midnight-12-1-02-09-2026/64010)，GSE 版本 3.3.31（3331），各自选择版本 1。原串 SHA-256 与 manifest 一致：AOE `ae596b6966ac87e9776fe34a36dca6561d79616c0b9f0a1c8e17afc98991f7f9`；ST `033e5853eb3b4253b7764b57035fd907294568444cc503f11746accac070cf88`。本机原始文件是 `.local/sim2gse/gse-corpus/sol-unholy-12-1-01.txt` 和 `sol-unholy-12-1-02.txt`。

导入前使用当前邪 DK 角色单独查询这两条原串引用的法术编号；查询输出保存在忽略目录 `.local/sim2gse/import-action-probe-review-sol-both-20260925/`。SimC（战斗模拟器）仅返回能创建为玩家动作、处于等级范围、可用且非后台/被动/静默的动作。核对结果为：`42650 → army_of_the_dead`、`43265 → death_and_decay`、`46585 → raise_dead`（当前动作原生编号 46584）、`47541 → death_coil`、`49576 → death_grip`、`55090 → scourge_strike`、`207317 → epidemic`、`316239 → festering_strike`（当前动作原生编号 85948）、`343294 → soul_reaper`、`1233448 → dark_transformation`、`1247378 → putrefy`。没有用名称猜测替换技能。

两个成员均经公开导入任务入口完成编译和受控原生模拟。条件场景相同：无修饰键、已有存活可攻击的敌方目标、宠物已召唤；`click_ms = input_interval_ms = 300`，`gcd_ms = 1500`，seed `20260912`。角色资料为 `.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc`，未修改。训练木桩设置为 90 级、护甲系数 4531.03、单目标，关闭 Omnium 天赋。

| 成员 | 导入结果 | 47 个编译点击的受控 DPS | 独立角色基准 DPS |
| --- | --- | ---: | ---: |
| `SOL_UDK_AOE` | `passed_native_model` | 37842.240154123254 | 77044.71054312987 |
| `SOL_UDK_ST` | `passed_native_model` | 41627.01167663097 | 77044.71054312987 |

表中“47 个编译点击”是导入序列展开后的点击数；受控模拟按 300 ms 间隔循环执行 180 秒，共 600 个输入时点、99 次迭代。右栏 77044.71054312987 是同一角色无导入点击计划的自由选择基准，不能当作导入序列 DPS 或两种序列的比较值。两次任务均已完成，报告标记 `game_validation=not_run`。

两条成员的 47 个点击都保留了逐项上游来源路径；下列第 n 项就是编译计划第 n 次点击的 `source_path`，顺序与两次结果中的 `candidate.compiled_steps` 一致：

```text
1:1, 2:2.1, 3:2.1, 4:2.2, 5:2.1, 6:2.2, 7:2.3, 8:2.1, 9:2.2, 10:2.3,
11:2.4, 12:2.1, 13:2.2, 14:2.3, 15:2.4, 16:2.5, 17:2.1, 18:2.2, 19:2.3,
20:2.4, 21:2.5, 22:2.6, 23:2.1, 24:2.1, 25:2.2, 26:2.1, 27:2.2, 28:2.3,
29:2.1, 30:2.2, 31:2.3, 32:2.4, 33:2.1, 34:2.2, 35:2.3, 36:2.4, 37:2.5,
38:2.1, 39:2.2, 40:2.3, 41:2.4, 42:2.5, 43:2.6, 44:3.1, 45:3.2, 46:3.3, 47:3.4
```

完整任务产物（含原始导入副本、编译计划、受控报告和角色基准报告）仅在忽略目录：`.local/sim2gse/import-review-sol-aoe-20260925/` 与 `.local/sim2gse/import-review-sol-st-20260925-b/`。其余 9 个此前试过的真实样本成员仍保持上表所述的明确拒绝状态；本次只关闭 Søl 两个成员的映射缺口，没有扩大条件或技能支持范围。

支持的精确宏场景依据：当目标存在、存活且可攻击时，`[noharm]` 和 `[dead]` 条件均不成立，`/targetenemy [noharm][dead]` 不执行；该行占用的输入仍保留为空点击。`enemy_target_ready` 是编译上下文，默认为 true；false 时拒绝。其他 `/targetenemy` 写法仍拒绝。该组合用于缺少可攻击目标或目标已死亡时重新选敌的公开示例见[暴雪论坛讨论](https://eu.forums.blizzard.com/en/wow/t/help-with-targeting-macro/547862)及[另一讨论](https://us.forums.blizzard.com/en/wow/t/help-targeting-next-target-macro/31865)。

另有 `wow-wide-64007-1.txt` 与 Violent Benediction 原串 SHA-256 相同，按重复原串去重。维护者 Pause 讨论关联帖 18312、35227，以及后续候选 37781、36270、32673、31200、26914 均未发现可提取的 `!GSE3!` 原串。不得将合成向量称为真实覆盖。
