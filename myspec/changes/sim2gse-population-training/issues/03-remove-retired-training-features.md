# 03：清理废弃能力与旧训练执行

**What to build（交付）:** 用户只看到并使用新预训练，正式搜索不再暴露自适应选择器／规则化起点功能；两能力及旧训练执行的专属残留消除，同时新链、共享能力、旧成果读取和活数据不被破坏。

**Blocked by（前置）:** 02“打通GA预训练与四起点消费”及其Astra两轴独立审查前置已完成，门禁一已确认，本票实施与审查亦已完成。当前整体候选最终官方本机fast待100代实验结束后执行，Gate2尚未完整展示并获批准。

**Status（分拣）:** ready-for-agent（源码清理、必要构造及两轴独立审查完成；既有重编／统一验证及真实隔离小验收按实际适用提交保留，后续三项性能实现／审查及03实际产品回放已完成，不能替代当前候选最终官方本机fast；100代实验不改正式2代早停，任务7／8暂停排除，Gate2未批准，整体交付未完成，历史物理对象未擅自删除）

**Authorization（授权状态）:** 门禁一已确认，02及其独立审查完成后按已展示范围实施本票；Sol串行实施、Astra独立审查及整体共享20分钟隔离真实验收不变，必要本机验证可拉取对应功能分支；真实小验收按用户最新指定仅本机执行。未获门禁二、主干合并、发布、完整生产训练或具体对象不可恢复删除授权。

## 公开入口与最小接缝

经既有训练CLI／配置读取、正式run_task／resume_task及现有界面启动的真实调用，观察旧开关已移除／明确报错，新预训练和正式local默认能力保留；经原成果读取观察v1兼容。复用公开入口及数据中心读写，不新增删除服务／迁移框架／新用户API。最高测试接缝和阻塞边随门禁一并确认。

## Acceptance criteria（验收）

- [ ] 自适应选择器、规则化起点能力及开关完整移除，包含专属实现／调用分支／配置读写／死代码／测试和文档可用声明；不是默认关闭。旧键／旧CLI参数明确已移除，不静默忽略或回退旧算法。
- [ ] 旧逐材料local预训练专用入口执行／配置／测试及旧用法清理，不保留闲置第二模式；保留的公开训练入口直接执行02的新预训练，不能将消费者的旧成果读取误删成旧执行残留。
- [ ] 正式local搜索、原四起点、预训练、曲线／新早停／基础位置反馈／随机变异／模拟／缓存／存储／适配及版本读取保留；正式搜索原full诊断／过程观测／damage不删不降级，不再以“共享诊断”保留整套规则解释器。根据后续明确授权删除四套职业优先规则、八模板解释/编辑/手动单步和专属原生观察链；只保留三元成果隔离薄识别与旧v1必要只读验真，不把新增职业规则子系统当共享context保留。原生只定点裁关联观察挂点，保留目录、静态英雄证据和基础控制。
- [ ] 预训练本次仅支持基础性能日志与时间DPS曲线（默认关闭）；日志恢复按本次开关、曲线已有产物可离线比较且不补跑评分。diagnostics full／未知档位或非off search_observability明确拒绝，不静默降级；不新增预训练damage适配。此边界不限制正式搜索现有full／过程观测／damage。
- [ ] 清理前列两能力专属模型／学习状态／缓存／历史／索引的具体逻辑键与物理对象，核对共享反向引用；不整删混合任务／报告索引／起点／冠军／正式赢家回流记录。不可恢复永久删除具体对象须执行时明确确认，未获确认只报告清单及阻塞，不扩大为全库清理。
- [ ] 旧完整成果可读；算法／身份不兼容的未完成任务显式拒绝恢复，不修改历史identity伪造兼容。正式冠军匹配与历史赢家材料回流不放松、不停止。
- [ ] 最高公开入口构造回归证明旧开关／专属路径无残留且新功能与共享默认可用，保留一条旧成果读取、正式run／resume和存储失败代表；只删除已废功能专属断言，不放宽活契约、统一验证口径或真实样本门槛。
- [ ] 两票完成后由Astra独立复核清理范围及共享引用，构建／统一验证依仓库既有规则单独记录；仅在本机执行一次共享20分钟真实小验收和数量级性能估算，32与128分开计时、观察实际4×5及明显保存／收尾争用，缺测如实标注，无精密统计或新监控框架。
- [ ] 真实小验收仅本机、两票独立审查后执行，整体隔离TaskStore、共享数据根／缓存／报告索引／准备写入／发布目标，正式来源只读；默认最多15分钟单组受控真实8材料小链＋5分钟四组并发冒烟，含准备／收尾，超时暂停报未完成，不改早停／参数凑通过、不冒称全70验证或生产发布。

## 失败恢复与预算

执行清理只针对可证明专属对象；共享引用不明或不可恢复对象未获确认时停止该删除、保留清单与证据，不使用其他路径绕过。新链／旧读回归失败先在同票修复，不能保留死能力兜底。真实20分钟为两票累计共享预算，02不再重复一次；不完整只报告未完成及必要增量建议，不自动扩跑。无主干合并／生产发布授权。

## Comments（讨论）

2026-10-22 23:00 UTC 两轴审查共同P2最小修复（HEAD e272853，待快速复审，非本机/真实验收）：

- 带burst首次执行会在defer区提前写入内存behavior_identity_version，原首次检查误以为完整身份已可靠保存；首12条Parquet已发布、SQLite登记前一次存储错误后，discard会恢复残缺state，公开resume_task拒绝旧行为身份。新增HTTP启动带burst及公开恢复构造稳定复现此错误：red-burst-first-publication-recovery-3.log，1 failed/32 deselected，1.12s，EXIT_CODE=1。前两次准备性失败不作本缺陷红证据。
- 只将search.optimize首次初始化判断改为TaskStore既有saved_fields中是否已有可靠行为版本、持久phase是否仍initialize；仍在prepared/starts及run_nonce完整后的原一次checkpoint保存。不增加逐评分/缓存命中保存、正式local每12评分保存或RNG恢复框架，不改变爆发plan/cache策略。
- 原无burst故障用例复用同一公开检查，另加use_burst=True，并断言启动/恢复的每次构造评分均带对应爆发候选。保留已发布可验回12键各评分一次、重复仅来自未提交尾部、组号/报告数量/完整身份/故障隔离断言，不改活保存契约。
- 定向green-burst-first-publication-recovery.log：3 passed/30 deselected，4.44s，EXIT_CODE=0。必要小组合green-burst-first-small-shared.log：21 passed，50.94s，EXIT_CODE=0，覆盖带/不带burst故障恢复、部分组提交、检查点增量/回滚、原四起点、旧行为身份拒绝、预训练日志on/off取消恢复与feedback12及时提交/RNG、正式取消恢复曲线。完整命令存同名.command；使用独立basetemp及三路径Popen阻断器，无研究子进程/真实native执行。本次通过不覆盖此前明确排除的真实/Windows项，不替代统一构建或本机小验收；历史测试成本披露不变。

2026-10-22：用户已批准两可选能力、旧训练专用执行及专属历史残留的需求清理范围；具体行动仍受门禁一和不可恢复删除对象确认约束。当前仅需求草案，01实验票据保持原样。

2026-10-22 最新授权：19:10 UTC门禁一已完整展示，用户 Sentinel_4ecb203be170819188a71ee173d434be 补充必要本机拉分支验证，Sentinel_759ece870e648191b5c92c67028a5ef0 明确确认进入开发；该确认覆盖已展示票据粒度、依赖及公开接缝，原待答说明保留为历史。03仍依赖02完成并通过独立审查，不因门禁已通过而提前启动；不可恢复永久删除具体对象仍须执行时另行明确确认，不将清理需求扩大为物理删除授权。

2026-10-22 20:36 UTC：父任务明确确认02两轴Astra最终通过，现从HEAD 1f08058f06729a71e5b5ed51259ead784b481cb0串行实施03；全局固定基线不变。源码/测试仅本实施者写入，另委派只读数据/共享引用盘点，不执行任何物理历史删除。真实中心目前未发现，待盘点精确对象；本机不连、真实20分钟预算未用。

2026-10-22 21:43 UTC 范围纠正与用户新增清理确认（实施中，非验收通过）：

- 用户 Sentinel_31ac7571414c8191847d03686c166ba2 指出四套邪DK配置、八类通用诊断模板也属于退役能力新增，不得仅凭现存调用保留；Sentinel_e4a152f88010819182900e4205bde44f 明确Git历史只作范围参考、不能整提交照撤；Sentinel_3ef47030e5bc8191b224139b218d8d71 要求保留训练与正式搜索必需的最小代码、删除退役能力相关入口/config/tests/docs。按父任务传递的最新授权实施，替代本票此前“保留整套共享诊断”的过宽解释；不回滚整个commit，不扩大到无关项目。
- 历史来源：87c055d 首加rule_initialization/unholy_rules与静态snapshot；2adfc65 首加rule_config.py/rules.json用于可编辑起手；3c1ad0a 首加rule_diagnostics.py/selector.py、八模板/完整单步池/手动rule_step与专属原生观察请求；052fd76 再抽rule_context以实现两开关独立。旧87c055d父版本已有原四来源、feedback_from_trace、_parent_positions、index99反馈及随机mutate，不依赖上述职业规则库。
- 删除：当前职业四配置/八模板解释与规则编辑能力，规则起手/自适应/手动单步/明确规则补采诊断的专属执行、CLI/API/config、专属请求与新保存生产链，以及专属测试/可用声明。保留旧报告字段读取不等于保留可执行解释器。
- 保留或薄解耦：c90a240后成为独立业务契约的专精/真实英雄/目标类型三元成果范围，当前GA继续要求；改用原生spec与hero证据及明确scene识别，不继续强制加载current职业规则库。保留原四起点、基础失败/位置反馈/变异、动作目录和替换/合法性、编译评分缓存/存储、固定独立burst、曲线与GA早停。已有原生static_snapshot的英雄证据保留，不整撤原生目录。
- 只读兼容：旧v1内嵌rule_snapshot、alignment、完整条件及三份报告的必要验真保留，不能让它反向成为新任务依赖；正式旧完整任务/报告/冠军不删除、不改写身份。不兼容未完成任务明确拒恢复。
- 原生专属观察的controller/070/080/090/lock身份边界先由独立只读审查核定最小删除与重编成本；实施者尚未改native源码/补丁/lock，不只删Python就宣称全部清理完成。具体不可恢复正式数据对象仍未授权删除。
- 时点/cache：用户 Sentinel_c8a22241558c81919ab3c66633d622d6 明确“暂时不需要动”；调查确认prepared可能复用旧5秒plan，无alignment并无自动fallback。保留现行行为及原完整评价身份，不新增动态值/resolver/强制默认或迁移，不列为本票待审批阻塞。
- 验证口径纠正：03 live-core-first/second各已混入一项真实controlled评分，确认累计至少2次；另interface-first条件式真实入口0或1次无法从保留日志确定。对应三套件wall91.84/90.37/39.74s仅是原生耗时保守上界而非逐调用计时。02 shared/review-shared/review2-shared三套件58.36/62.86/49.32s缺完整启动命令，原生范围未知单列；不再声称所有既有检查均纯构造或预算零。21:34 UTC已中断core第三轮session88592、退出130，之后未执行测试；真实验收未运行，亦不得用此掩盖前述流程偏差。后续仅经父任务核对的构造白名单和真引擎路径阻断启动器运行；统一测试及真实20分钟验收的实际成本另计，不改统一门禁。


2026-10-22 22:12 UTC 关联子系统清理实施进展（仍待组合回归和独立审查）：

- 原生清理遵照Astra最小清单：删除080/090及锁应用项；040仅去执行观察/结束挂点，060仅去观察/结束而保留transfer_replacement；070仅去sim2gse_read_rule_action，保留静态快照、hero_subtree_ids及安全getter；controller去请求option、报告、reset/init/tick观察器，保留write_trace、handle_event、issued_actions、排队、连续施法。catalogue.cpp/.hpp未改。baseline/controlled补丁已从固定upstream.zip在隔离临时目录静态重放成功，新source/patch/patched-file散列写入lock；未编译或运行新引擎，旧二进制应失配，需后续重编而不是伪装通过。
- 产品删除rule_config.py、rule_initialization.py、rule_diagnostics.py、rules.json；不保留四配置/八模板执行或规则编辑、rule_step、补采诊断的闲置实现。独立legacy_training_rules.py仅验证旧v1内嵌声明/三条件/战前身份，不读取current、不生成、求值、编辑或观察。search._validate_saved_batch、旧检查点诊断引用还原、旧Parquet字段无损解码及正式旧回执观察字段/hash保留为只读兼容。新任务正式run/read/resume与GA在规则库不存在时公开通过。
- 规则专属四组测试模块及七项原生请求观察测试移除；活随机搜索、原四起点、位置反馈、WaitClicks编译/原生回放、HTTP错误、曲线/储存失败断言保留，仅替换专属模板供给接缝。原生实际门禁和混合真实项不改假核凑绿。
- 构造白名单再次纠正：interface整集另有三个真实入口意图（public_service_simulates_selected_import_and_returns_dps、public_service_reports_unmapped_import_skill_without_dps、interface_reports_native_and_export_failures_without_internal_paths），本轮在新lock/旧构建身份处提前失败，三路径Popen阻断器在位，未启动真实核；今后与原两项一起排除并单列未验证，不称整集纯构造。临时阻断器只拦本项目original/baseline/controlled绝对路径，按cwd解析相对参数，不合并产品/统一配置。
- 删除专属提前save揭示正式共享保存边界接线缺口：首次报告组可早于起点评分完成提交，而behavior_identity_version尚未持久化。补一次首次身份/起点边界保存，不恢复规则分支、不逐分数或缓存命中保存；保留原中断恢复/无重复报告断言。
- GA日志恢复新红证据：首次关闭、恢复开启时runtime真而state.config假；本票按已批准观测/恢复契约只覆盖本次采集logging与派生summary/off，算法、种子、材料与identity.json不改。公开on↔off取消恢复回归正在执行。GA full diagnostics/summary或full observability和damage未完整接通，矩阵另列，未扩建或冒充支持。


2026-10-22 22:40 UTC 云端可审查交接（非最终真实验收通过）：

- 用户 Sentinel_9ce487bbe254819195841d34b05fabc2 最终明确产品名称为“预训练”，本次只支持基础性能日志和时间DPS曲线。公开run_training明确拒绝diagnostics full/未知档位及非off search_observability，prepare共同输入也验此边界，旧v1内嵌凭据只读重建不受新选项限制。不接完整事件/过程观测、不加damage读取适配。正式local原full/过程观测/damage不删不降级；预训练已有时间曲线可离线比较，不补跑评分。用户指定真实小验收必须本机，待两票审查通过由父任务安排，原8材料和20分钟预算不扩。
- 共享保存修复仅在首次行为身份/起点初始化做一次checkpoint，越过store.active的defer，避免可靠组提交后恢复拒绝。没有给正式local增加每12分数checkpoint/RNG扩展：该临时3行已依契约撤回，预训练既有12条及时提交逻辑不改。旧中断测试的“所有已算请求均零重算”强于已批准可靠性要求，改为已可靠发布且可验回的12键各调用一次、重复只能来自故障瞬间尚未提交尾部；组号/行数/完整身份/故障隔离原断言保留。故障位置是12行Parquet写后、SQLite登记前，不以未提交内存零丢失为产品承诺。
- 日志恢复只覆盖本次logging及其summary/off，不改manifest、算法、种子或评分条件；on→off/off→on、正常取消尾刷、成功凭据不重算保持。新增公开预训练失败曲线与取消/恢复离线比较，明确禁止run_task/evaluate补分。
- 最终无研究子进程产品组合：final-public-shared-no-research.log，121 passed、60 subtests passed、5 deselected，90.27s，EXIT_CODE=0；完整旧冠军/v1模块另15 passed/17.18s。三路径阻断器在位、每轮独立basetemp、完整命令保存在同名.command。较大主组合final-main-and-shared-constructed.log为205 passed/66 subtests、11 deselected、5 failed，229.21s；五项是清理测试夹具时误删deepcopy import，已恢复并由完整15项及最终121项覆盖，不把原失败集称为全绿。先前session4100因executor key changed断开仅有22点无终态，结果未知不计通过；中断的研究混合复跑session23637工具exit130且无pytest最终汇总，点数/F不作完成或根因证据，完整日志保留。没有因无法取得traceback而编造产品修复。
- 明确排除/未验证：interface五项为真实reduce_wait评分、selected_import真实DPS、unmapped_import_skill真实reference、native/export_failures真实reference及msedge浏览器。较大主组合另排除test_search一个真实评分及五个Windows进程API例，合计11，不称这些模块全通过。原生实际兼容门禁未删不放宽；新baseline/controlled未重编，实际identity应拒旧构建。正式统一build-and-verify尚未运行，不能把脏树前置检查或构造通过冒充统一验证通过。
- 保留ABC/three-evolution，不再长跑其研究回归。本轮研究适配器子Python没有继承父Popen三核阻断；适配器显式mock reference/inspect/sequence.evaluate，父脚本会向每臂传--constructed-native-adapter并在boundary内执行，但这些静态接线不能替代运行证明。研究结果列未完成/未验证，不以父guard声称其零真实执行或计成功；后续未经父任务明确不再启动子测试。适配器仅把profile读取移入已有fast初始化边界，未弱化产品真实engine.identity。
- 删除/保留/数据对象详见.local/ga-pretraining-03/deletion-and-compatibility-inventory.md；精确变更列表见changed-files-final.txt，支持/入口矩阵见retained-capabilities-matrix.md。已发现四个云端隔离learner历史物理对象（含一锁和三Parquet）但未删除；正式生产中心未绑定，本机历史未清理，不将源码清理等同于所有数据已清。混合seed材料/selected/processed/prepared、任务/报告索引、冠军/回流证据不整删，不可恢复对象仍需逐对象确认。
- Git保持HEAD 1f08058f06729a71e5b5ed51259ead784b481cb0；未stage/commit/push/改分支/回滚，myspec/specs正式规格未改。diff --check通过；原生source/patch静态重放成功、关联观察符号与退役模块import检索零命中；不承诺C++重编成功。此前至少2次真实评分偏差、未知混合范围和套件wall保守上界仍按前述证据保留，不说真实验收未开始就意味着验证成本为零。

2026-10-22 22:44 UTC：已将最新职业规则整链清理、预训练仅日志／timeline及不支持档位拒绝、正式诊断不降级、真实小验收仅本机的要求同步至本票顶部当前验收条款及父change spec当前需求段；历史讨论保留追溯，不以过时context／无需重编／待开发授权文字约束当前实施。正式myspec/specs未动。完整预训练用例证据分类见.local/ga-pretraining-03/pretraining-test-evidence.md，不把121混称全部预训练用例。
