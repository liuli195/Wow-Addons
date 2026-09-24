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

这三条原串的 `inspect`（检查）均成功，四个成员都经过公开导入任务试跑。首轮没有成员进入受控 DPS（每秒伤害）模拟：Karen ST 的 `spell 316239` 当时不在当前角色能力映射中；Karen M+ 的 `[nochanneling]` 条件无法确定；Kim 主循环的 `[channeling]` 条件无法确定；Kim 爆发序列的 `@player` 目标能力无法验证。2026-09-25 的 Karen ST 重试见下文。没有把未识别动作替换为其他技能。

## 原样本严格映射结果

2026-09-24 的 11 个旧样本成员均可解码；下表记录当时首次试跑结果，不覆盖后续重试：

| 原串 / 成员 | 编译或映射结果 |
| --- | --- |
| Søl `SOL_UDK_AOE` | 首次试跑时 `spell 207317` 未出现在只看已执行动作的窄目录中；动作编号已由角色查询映射，但原串含条件成立的 `/petattack`，当前拒绝模拟，旧 DPS 无效 |
| Søl `SOL_UDK_ST` | 首次试跑时 `spell 316239` 未出现在只看已执行动作的窄目录中；动作编号已由角色查询映射，但原串含条件成立的 `/petattack`，当前拒绝模拟，旧 DPS 无效 |
| Flip 两个成员 | `/castsequence [@target,harm,nodead] reset=target/combat outbreak, null` 不支持 |
| MOB Unholy 两个成员 | `item 13` 未映射到当前角色；不把它假定为空点击 |
| MOB Blood | `[nochanneling]` 条件无法确定 |
| MOB Guardian | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持了该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Guardian 角色输入重跑 |
| MOB Shadow `MOB_SP_OPENER` | 未替换占位文本 `Need Stuff Here` 不支持 |
| MOB Shadow `MOB_SP_Myth` | 初测因 `/targetenemy [noharm][dead]` 被拒绝；此后仅精确支持该行在“已有存活且可攻击的敌方目标”场景下的无效果分支，未使用匹配的 Shadow 角色输入重跑 |
| Violent Benediction | `=GSE.V.VB_IsHeals()` 需要游戏内变量，无法确定 If 分支 |

## 2026-09-25 真实样本复核与重试

### Søl 12.1 原串：旧 DPS 结果无效

两条 Søl 原串未经改动，来自[作者的 12.1 邪 DK 帖](https://wowlazymacros.com/t/sols-12-1-unholy-dk-midnight-12-1-02-09-2026/64010)，GSE 版本 3.3.31（3331），各自选择版本 1。原串 SHA-256 与 manifest 一致：AOE `ae596b6966ac87e9776fe34a36dca6561d79616c0b9f0a1c8e17afc98991f7f9`；ST `033e5853eb3b4253b7764b57035fd907294568444cc503f11746accac070cf88`。本机原始文件是 `.local/sim2gse/gse-corpus/sol-unholy-12-1-01.txt` 和 `sol-unholy-12-1-02.txt`。

此前两次任务都错误地把条件成立的 `/petattack [@target,harm,nodead]` 当成无效果行。当前场景明确有存活可攻击的敌方目标和已召唤宠物，因此该命令会执行；现有伤害引擎没有忠实表示宠物攻击命令的能力。`37842.240154123254` 与 `41627.01167663097` 只保留为历史审计数值，不是有效受控 DPS，也不满足验收。现在两个成员都会在模拟前拒绝，位置分别是 `SOL_UDK_AOE v1 Versions[1].Actions[1].macro[行 2]` 与 `SOL_UDK_ST v1 Versions[1].Actions[1].macro[行 2]`。

旧任务目录 `.local/sim2gse/import-review-sol-aoe-20260925/` 和 `.local/sim2gse/import-review-sol-st-20260925-b/` 保存当时的报告；报告没有识别上述语义缺陷，不再作为忠实 DPS 证据。两条原串中的法术编号和其查询映射可作动作目录核对记录，但不改变这项拒绝结论。

### Karen ST：当前唯一完成的真实原生 DPS 导入样本

[Karen 邪 DK 原帖](https://wowlazymacros.com/t/karens-unholy-dk-st-and-m-updated-m-macro/62253)中的原始集合串未修改，SHA-256 为 `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497`，本机文件 `.local/sim2gse/gse-corpus-additional/karens-unholy-01.txt`；成员 `unholydk_ST`、版本 1、GSE 3.3.13（3313）。该版本的宏没有 `/petattack` 或 `/petassist`。静态检查通过，角色动作查询严格映射所有成员动作；`316239` 与名称形式 `Festering Strike` 都解析到 `festering_strike`，名称查询返回原生动作编号 85948。证据保存在忽略目录 `.local/sim2gse/import-review-karen-st-20260925-name-map/` 的 `reference/import_action_probe/native.json`、`capabilities/catalogue.json` 和 `result.json`。

在未修改的角色资料 `.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc` 上，经导入任务完整编译并完成 180 秒受控原生模拟。场景为无修饰键、存活可攻击的敌方目标存在、宠物已召唤；`click_ms = input_interval_ms = 300 ms`，`gcd_ms = 1500 ms`，seed `20260912`。22 个点击全部保留来源，`source_path` 依次为 `1` 至 `22`；对应动作依次为：

```text
1 auto_attack, 2 army_of_the_dead, 3 dark_transformation, 4 dark_transformation,
5 outbreak, 6 festering_strike, 7 festering_strike, 8 scourge_strike,
9 death_coil, 10 putrefy, 11 scourge_strike, 12 death_coil, 13 soul_reaper,
14 festering_strike, 15 scourge_strike, 16 death_coil, 17 putrefy,
18 scourge_strike, 19 death_coil, 20 festering_strike, 21 scourge_strike,
22 death_coil
```

| 指标 | 数值 |
| --- | ---: |
| 导入序列受控 DPS（`passed_native_model`） | 50873.80836033131 |
| 同角色自由选择参考 DPS | 77044.71054312987 |
| 输入时点 | 600（每 300 ms 一次，共 180 秒） |

参考值是同一角色不使用导入点击计划的自由选择模拟，不是导入 DPS 的预期值或比较门槛。受控数值说明本机固定角色、配置和模型上的真实原串完整链路已跑通；报告为 `game_validation=not_run`，不代表游戏内行为验收。Søl 两条 12.1 原串仍因宠物命令被拒绝。其余样本成员仍按具体映射或语义原因处理，没有用未识别动作替换其他技能。

## 复审修复证据

角色动作名称查询不依赖 APL（动作优先列表）是否实际执行该技能。对当前 DK 测试角色单独做 1 秒原生查询，名称形式 `Epidemic` 返回 `available=true`、`action_initialized=true`，但不在普通 `sim2gse_actions` 执行列表中；见 `tests/sim2gse/test_engine.py::test_import_probe_resolves_name_form_action_outside_executed_subset`。查询结果只用于导入时严格映射，不改变搜索候选集合。另以法师 Frost 的 `mirror_image`（镜像）验证较早创建动作后仍完成初始化，并能看到 3 个宠物；对应测试为 `test_import_probe_action_is_initialized_for_mage_pet_setup`。

固定基线 `fa2ea1360858942a8bc3d065fbad81c5a9cef417` 的搜索回归使用测试用邪 DK 角色资料和小预算配置；它不是第三方 GSE 原串，结果也不代表 DPS 验收。固定基线旧代码与当前代码选出同一候选键 `818298543af0831284080248c1ce448f252857a96aae0c890e785e5247bd7fdc`，生成 GSE 文本 SHA-256 `322b8c36260b2402927d0a5db2b62ff788623193525a8c966f452ea96b404486`，并产生相同的 10 个编译点击。完整 GSE 文本和逐点击结果保存在 `tests/sim2gse/test_search.py::test_real_deathknight_search_matches_fixed_baseline_golden`；因只申请两场，任务状态是 `validation_incomplete`。

支持的精确宏场景依据：当目标存在、存活且可攻击时，`[noharm]` 和 `[dead]` 条件均不成立，`/targetenemy [noharm][dead]` 不执行；该行占用的输入仍保留为空点击。`enemy_target_ready` 是编译上下文，默认为 true；false 时拒绝。其他 `/targetenemy` 写法仍拒绝。该组合用于缺少可攻击目标或目标已死亡时重新选敌的公开示例见[暴雪论坛讨论](https://eu.forums.blizzard.com/en/wow/t/help-with-targeting-macro/547862)及[另一讨论](https://us.forums.blizzard.com/en/wow/t/help-targeting-next-target-macro/31865)。

另有 `wow-wide-64007-1.txt` 与 Violent Benediction 原串 SHA-256 相同，按重复原串去重。维护者 Pause 讨论关联帖 18312、35227，以及后续候选 37781、36270、32673、31200、26914 均未发现可提取的 `!GSE3!` 原串。不得将合成向量称为真实覆盖。
