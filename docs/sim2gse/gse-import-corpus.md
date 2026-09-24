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

2026-09-24 的 11 个旧样本成员均可解码，均未得到 DPS：

| 原串 / 成员 | 编译或映射结果 |
| --- | --- |
| Søl `SOL_UDK_AOE` | `spell 207317` 未映射到当前角色 |
| Søl `SOL_UDK_ST` | `spell 316239` 未映射到当前角色 |
| Flip 两个成员 | `/castsequence [@target,harm,nodead] reset=target/combat outbreak, null` 不支持 |
| MOB Unholy 两个成员 | `item 13` 未映射到当前角色；不把它假定为空点击 |
| MOB Blood | `[nochanneling]` 条件无法确定 |
| MOB Guardian | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持了该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Guardian 角色输入重跑 |
| MOB Shadow `MOB_SP_OPENER` | 未替换占位文本 `Need Stuff Here` 不支持 |
| MOB Shadow `MOB_SP_Myth` | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Shadow 角色输入重跑 |
| Violent Benediction | `=GSE.V.VB_IsHeals()` 需要游戏内变量，无法确定 If 分支 |

支持的精确宏场景依据：当目标存在、存活且可攻击时，`[noharm]` 和 `[dead]` 条件均不成立，`/targetenemy [noharm][dead]` 不执行；该行占用的输入仍保留为空点击。`enemy_target_ready` 是编译上下文，默认为 true；false 时拒绝。其他 `/targetenemy` 写法仍拒绝。该组合用于缺少可攻击目标或目标已死亡时重新选敌的公开示例见[暴雪论坛讨论](https://eu.forums.blizzard.com/en/wow/t/help-with-targeting-macro/547862)及[另一讨论](https://us.forums.blizzard.com/en/wow/t/help-targeting-next-target-macro/31865)。

另有 `wow-wide-64007-1.txt` 与 Violent Benediction 原串 SHA-256 相同，按重复原串去重。维护者 Pause 讨论关联帖 18312、35227，以及后续候选 37781、36270、32673、31200、26914 均未发现可提取的 `!GSE3!` 原串。不得将合成向量称为真实覆盖。
