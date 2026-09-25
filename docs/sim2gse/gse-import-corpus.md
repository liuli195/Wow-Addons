# GSE 导入验证样本

原始导入串保存在 Git 忽略目录 `.local/sim2gse/gse-corpus/` 和 `.local/sim2gse/gse-corpus-additional/`。原串不提交到 Git；文中记录的 SHA-256（内容摘要）用于复核本机文件。作者声称适用某个游戏版本，不代表已完成游戏内验收。

| 来源 | 来源帖子与时间（UTC） | 用途 | 已观察语法 | GSE 版本 |
| --- | --- | --- | --- | --- |
| [Søl 邪 DK 12.1](https://wowlazymacros.com/t/sols-12-1-unholy-dk-midnight-12-1-02-09-2026/64010) | 主题首帖 #1：2026-09-08T18:28:36.415Z | AOE（群体）和 ST（单体） | Action（动作）、Loop（循环） | 3.3.31；作者标注 12.1 |
| [MOB 邪 DK](https://gseunited.com/t/mob-retail-death-knight-unholy/270) | 主题首帖 #1：2026-07-16T07:32:35.739Z | 一条集合原串、两个成员 | Action、Loop | 3.3.13；游戏版本待复核 |
| [Flip 邪 DK 归档](https://gseunited.com/t/flip-s-unholy-death-knight-st-v3-aoe-v4-archived-12-0-7/669) | 主题首帖 #1：2026-08-28T22:29:08.568Z | 两条旧版序列 | Action | 3.3.23；归档注明 12.0.7 |
| [MOB 鲜血 DK](https://gseunited.com/t/mob-retail-death-knight-blood/273) | 主题首帖 #1：2026-07-16T07:32:38.215Z | 定期重复序列 | Action、Loop、Repeat（定期重复） | 3.3.13 |
| [MOB 守护德鲁伊](https://gseunited.com/t/mob-retail-druid-guardian-raid-mythic-delves-leveling/271) | 主题首帖 #1：2026-07-16T07:32:36.569Z | 数组包裹序列 | Action、Loop、Repeat | 3.3.07 |
| [MOB 暗影牧师](https://gseunited.com/t/mob-retail-priest-shadow/277) | 主题首帖 #1：2026-07-16T07:32:41.180Z | 两成员集合 | Action、Loop、Repeat | 3.3.11 |
| [Violent Benediction](https://wowlazymacros.com/t/64007) | 主题首帖 #1：2026-09-08T18:28:11.805Z | 条件块 | Action、If（条件） | 原帖未注明；原串嵌入 3.3.32 |
| [Karen 邪 DK](https://wowlazymacros.com/t/karens-unholy-dk-st-and-m-updated-m-macro/62253) | 主题首帖 #1：2026-04-18T00:59:35.387Z | 一条集合原串、ST 与 M+ 两成员 | Action、Loop | 3.3.13 |
| [Kim 邪 DK](https://wowlazymacros.com/t/kims-unholy-sequence/62086) | 主题首帖 #1：2026-04-11T03:01:14.879Z | 两条原串：主循环、爆发 | Loop、Repeat | 3.3.08 |
| [DrussRet 惩戒圣骑士](https://wowlazymacros.com/t/drussret-s2-updated-18-09-2026-m-raid-aoe-st-herald-templar-addons/60173?page=20) | 主题首帖 #1：2026-01-21T18:14:38.811Z；样本作者回帖 #388：2026-05-06T00:56:09.806Z | 一条两成员集合：`DRUSS_ST_v6`、`DRUSS_AOE_v6`；未注明游戏版本 | Action、Loop、Pause、Repeat | GSE 3.3.15；原串 SHA-256 `d992c3e47f13ed9e70b594f7f02908224cb6031b5dc3f20f5a03da14e723b0dd` |
| [Jafoweb 牧师 PVP](https://wowlazymacros.com/t/onlyonebutton-discipline-priest-pvp-oracle-based/62541) | 主题首帖 #1：2026-05-01T09:11:28.560Z | 两条原串：单成员 `Jafo_Master`；两成员 `MPB`、`Jafo_Master`；未注明游戏版本 | Action、Embed、Loop、Repeat | GSE 3.3.15；SHA-256 分别为 `e9acce109a55bf6dfc56f3b98537a85624bddc9084543156a4d89bb36167fe94`、`8b83c1cb010ec334b1a3d023ee1b0637cd6abe52e689d68cab8a70c03237540d` |

除 DrussRet 外，表中时间是来源主题首帖 #1 的 `post.created_at`；这表示主题首帖发布时间。DrussRet 样本链接定位到第 20 页，实际样本来源为作者回帖 #388，主题首帖和样本回帖时间分别列出。时间均为 UTC（协调世界时）；逐来源帖子编号、时间和 SHA-256（内容摘要）位于忽略目录 `.local/sim2gse/gse-corpus-inspection/source-publication-dates-2026-09-25.json` 与语料清单。

截至 2026-09-25，共收集 16 个本机文件、15 条不同 SHA-256 原串（1 个重复文件），其中 9 条为 DK（死亡骑士）原串；DrussRet 两成员的 `SpecID（专精编号）=70`，属于惩戒圣骑士，不计入 DK 样本。Søl 的两条由作者标注适用 12.1。逐文件提交公开 `POST /api/gse/inspect` 后，16/16 均为 HTTP 200 且 `decoded`。检查了 21 组文件级成员/版本，按 SHA 去重后为 20 组；无成员/版本解析失败或未列出的语法路径。

真实原串共观察到六类语法：Action 268 处、Loop 20 处、Repeat 30 处、If 4 处、Pause 2 处、Embed 2 处。没有 `collection_compatibility_blocks`。DrussRet 的 `DRUSS_ST_v6` 第 1 版没有 `Actions` 数组，解析器保留该版本数值块并给出 warning（警告），路径为 `Sequences[DRUSS_ST_v6].Versions[1].Actions`；这属于解析成功但不能模拟。21 组版本中，19 组模拟门禁状态为 `unsupported`，2 组为 `requires_character_validation`；公开检查没有启动 DPS（每秒伤害）模拟。

真实原串、固定上游合成向量和游戏内验收分开统计：以上六类是实际第三方原串覆盖；合成向量仅用于补充固定语法验证，不计入真实样本；本票没有游戏内验收证据。逐文件完整 HTTP 请求结果和每个成员/版本响应位于 Git 忽略目录 `.local/sim2gse/gse-corpus-inspection/final-post-review-2026-09-25.json`；复审后可读报告为 `.local/sim2gse/gse-corpus-inspection/report-final-post-review-2026-09-25.md`，原串清单位于 `.local/sim2gse/gse-corpus-inspection/corpus-manifest-2026-09-25.json`。本次真实语料未收集到受保护原串；受保护外壳已有独立合成固定向量验证，不计入真实数量。

## 追加原串摘要

Karen 与 Kim 的三条邪 DK 原串，以及本次新增的 DrussRet Pause 和两条 Jafoweb Embed 原串均未改写：

| 本机文件 | 序列成员 | GSE 版本 | SHA-256 |
| --- | --- | --- | --- |
| `karens-unholy-01.txt` | `unholydk_ST`, `unholydk_m+` | 3313 | `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497` |
| `kims-unholy-01.txt` | `Main_Spam_UDK` | 3308 | `b1f6e2cbebcc19c7c0adeb736cd07bbc1857c3363ff906810df0a175f06cafc2` |
| `kims-unholy-02.txt` | `Burst_Cooldowns_UDK` | 3308 | `5a5430d305b7821ba682e74cd3c07d673aa80d3f988f044cfe05f821d60b7824` |
| `drussret-pause-01.txt` | `DRUSS_ST_v6`, `DRUSS_AOE_v6` | 3315 | `d992c3e47f13ed9e70b594f7f02908224cb6031b5dc3f20f5a03da14e723b0dd` |
| `jafoweb-embed-01.txt` | `Jafo_Master` | 3315 | `e9acce109a55bf6dfc56f3b98537a85624bddc9084543156a4d89bb36167fe94` |
| `jafoweb-embed-02.txt` | `MPB`, `Jafo_Master` | 3315 | `8b83c1cb010ec334b1a3d023ee1b0637cd6abe52e689d68cab8a70c03237540d` |

CBOR（压缩数据格式）实际解码确认，两条 Jafoweb 串都在 `Sequences[Jafo_Master].Versions[1].Actions[2][7]` 包含 `Type=Embed` 并引用 `MPB`。第一条输入没有 `MPB` 成员；第二条集合中包含 `MPB`。这项解析结果不证明外部 Embed 引用一定能加载或模拟。

前三条 Karen/Kim 原串的公开 `inspect`（检查）均成功，四个成员都经过公开导入任务试跑。首轮没有成员进入受控 DPS（每秒伤害）模拟：Karen ST 的 `spell 316239` 当时不在当前角色能力映射中；Karen M+ 的 `[nochanneling]` 条件无法确定；Kim 主循环的 `[channeling]` 条件无法确定；Kim 爆发序列的 `@player` 目标能力无法验证。2026-09-25 的 Karen ST 重试见下文。没有把未识别动作替换为其他技能。

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

2026-09-25 的 08 票复核再次对两条原串分别发送真实本机 `POST /api/gse/inspect`，均为 HTTP 200、`status=decoded`，SHA 与原文件一致，语法为 Action、Loop；`simulation_started=false`。`POST /api/tasks` 在建任务前均以 HTTP 400 返回同一 `/petattack` 来源位置。底层 `run_task(..., mode="import")` 做了自由选择参考模拟和原生动作查询，随后在导入宏编译阶段拒绝；没有进入 `sequence.evaluate()` 受控 GSE 模拟，没有生成 `controlled/` 或候选文件，因此没有可信导入 DPS。自由选择参考值不算导入 DPS。

锁定 SimC 的玩家动作列表也不接受 `petattack`、`pet_attack` 或 `pet.attack`。SimC 会给 DK 宠物安排自动攻击，且宠物初始目标跟随角色目标；但这不是可按原串时间和目标下达 `/petattack` 的接口。已确认场景未确认宠物已经在攻击同一目标，所以不能将命令静默当作无效果。宠物目标/启攻造成的 DPS 差异当前无法量化；需要原生宠物控制模型或用户明确批准更窄的场景等价假设。本机证据 `.local/sim2gse/gse-dps-acceptance/sol-unholy-12-1-import-check.json` 保存逐成员响应、角色摘要、任务结果和三种 SimC 动作名拒绝日志；其中 `POST /api/tasks` 的 HTTP 400 记录来自历史代码 HEAD `296fe2d09f06a41cee275da941da22cb88949ce2`；最终 HEAD `3104c2492dd0604fc9dc5de1acb9811c6607847a` 已重新实测，两条 Søl 成员均 HTTP 400、错误位置为 `/petattack` `macro[行 2]`，且未创建任务。最新证据为 `.local/sim2gse/post-commit-smoke-3104c24-sol-both.json`。

### Karen ST：当前唯一完成的真实原生 DPS 导入样本

[Karen 邪 DK 原帖](https://wowlazymacros.com/t/karens-unholy-dk-st-and-m-updated-m-macro/62253)中的原始集合串未修改，SHA-256 为 `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497`，本机文件 `.local/sim2gse/gse-corpus-additional/karens-unholy-01.txt`；成员 `unholydk_ST`、版本 1、GSE 3.3.13（3313）。该版本的宏没有 `/petattack` 或 `/petassist`。静态检查通过，角色动作查询严格映射所有成员动作；`316239` 与名称形式 `Festering Strike` 都解析到 `festering_strike`，名称查询返回原生动作编号 85948。旧任务结果已被最终代码 HEAD 下的公开 `run_task` 复跑取代；复跑 HEAD 为 `ce7465d6d3877383cee61c7b8c6c218b8b31f871`，完整输出位于忽略目录 `.local/sim2gse/import-review-karen-st-20260925-final-ce7465d/`，包括 `reference/import_action_probe/native.json`、`capabilities/catalogue.json` 和 `result.json`。

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

本次完整复跑在代码 HEAD `ce7465d6d3877383cee61c7b8c6c218b8b31f871` 执行，状态为 `completed`，有 22 个已映射点击且 `game_validation=not_run`。后续最终 HEAD `3104c2492dd0604fc9dc5de1acb9811c6607847a` 的 `POST /api/tasks` smoke 再次返回 `completed`，DPS 为 `50873.80836033131`；同一 smoke 中 `MOB_UDK_ST` 因 `[combat]` 条件不确定而 HTTP 400、未创建任务。证据见 `.local/sim2gse/post-commit-smoke-3104c24.json`。同一角色不使用导入计划的自由选择参考 DPS 不是导入 DPS 的预期值或比较门槛。角色资料 SHA-256 为 `27181b0a92bb198a4266762d5f6fb4b6123c06d07786de58e5eae65a8cf5ee59`；最终任务完整报告位于忽略目录 `.local/sim2gse/import-review-karen-st-20260925-final-ce7465d/`。Søl 两条 12.1 原串仍因宠物命令被拒绝。其余样本成员仍按具体映射或语义原因处理，没有用未识别动作替换其他技能。

## 复审修复证据

角色动作名称查询不依赖 APL（动作优先列表）是否实际执行该技能。对当前 DK 测试角色单独做 1 秒原生查询，名称形式 `Epidemic` 返回 `available=true`、`action_initialized=true`，但不在普通 `sim2gse_actions` 执行列表中；见 `tests/sim2gse/test_engine.py::test_import_probe_resolves_name_form_action_outside_executed_subset`。查询结果只用于导入时严格映射，不改变搜索候选集合。另以法师 Frost 的 `mirror_image`（镜像）验证较早创建动作后仍完成初始化，并能看到 3 个宠物；对应测试为 `test_import_probe_action_is_initialized_for_mage_pet_setup`。

固定基线 `fa2ea1360858942a8bc3d065fbad81c5a9cef417` 的搜索回归使用测试用邪 DK 角色资料和小预算配置；它不是第三方 GSE 原串，结果也不代表 DPS 验收。固定基线旧代码与当前代码选出同一候选键 `818298543af0831284080248c1ce448f252857a96aae0c890e785e5247bd7fdc`，生成 GSE 文本 SHA-256 `322b8c36260b2402927d0a5db2b62ff788623193525a8c966f452ea96b404486`，并产生相同的 10 个编译点击。完整 GSE 文本和逐点击结果保存在 `tests/sim2gse/test_search.py::test_real_deathknight_search_matches_fixed_baseline_golden`；因只申请两场，任务状态是 `validation_incomplete`。

支持的精确宏场景依据：当目标存在、存活且可攻击时，`[noharm]` 和 `[dead]` 条件均不成立，`/targetenemy [noharm][dead]` 不执行；该行占用的输入仍保留为空点击。`enemy_target_ready` 是编译上下文，默认为 true；false 时拒绝。其他 `/targetenemy` 写法仍拒绝。该组合用于缺少可攻击目标或目标已死亡时重新选敌的公开示例见[暴雪论坛讨论](https://eu.forums.blizzard.com/en/wow/t/help-with-targeting-macro/547862)及[另一讨论](https://us.forums.blizzard.com/en/wow/t/help-targeting-next-target-macro/31865)。

另有 `wow-wide-64007-1.txt` 与 Violent Benediction 原串 SHA-256 相同，按重复原串去重。最终语料已找到真实 Pause 和 Embed 原串；Jafoweb 第一个 Embed 引用 `MPB`，该集合成员不在这条导入串内；第二个导入串包含 `MPB`。不得将合成向量称为真实覆盖。
