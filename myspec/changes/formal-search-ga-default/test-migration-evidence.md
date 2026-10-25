# 全仓分层实施证据（2026-10-24，尚未验收）

> 2026-10-25 恢复说明：以下2026-10-24测试与审查为遗失d3版本的历史记录，不能作为当前重做版本验收。当前以远端a311为基线重做；7个已上传blob已核Git哈希恢复，其余按原脚本/审查增量重新实施、重新测试并接受新独审。官方配置、Windows真实全集、60秒与默认对照仍未验收。

本文件记录已批准扩展门禁的实际实施，不改变正式规格或产品默认。固定主干为d08f1d6；分支codex/formal-search-ga-default。此前da02/b80切片已保留引用，未混入本次文档发布历史。

## 已实施与轻量证据

- GSE及gear普通层一次集中常规pytest：305 passed、106 subtests，5.72秒；130 real未执行。GSE412＝284 ordinary＋128 real；gear23＝21 ordinary＋2 real。此为云端普通pytest，不是安装后2.7.1官方守卫或本机60秒通过。
- 插件/dev/素材域136项归类为42 ordinary／94 native；技能/DK ordinary21项、dev纯规则19项及两项真实BLP写出故障代表分别通过。随后从Git LFS取得并逐SHA/大小核验54份素材，仅临时还原精确原字节后执行dev普通20项通过（0.27秒），最后恢复原pointer字节，未改filter/hook/环境。唯一未选是正式配置尚未官方应用的setup角色断言；未冒称完整入口全绿。
- gear普通21项包含新lazy-load并发回归：受控晚期读取暂停时，不允许提前观察公开半成品。旧实现红灯、局部构造成功一次发布后绿灯。真实三引擎和浏览器未重跑。
- 产品接缝14f/d90已有限独立审查：延迟Windows锁导入、配置流读取、可选无输出catalogue、combatlog流/字典输入、TaskStore显式连接/共享库/位置依赖及gear延迟数据读取。默认文件路径、WAL/FULL、相同SQL、锁/关闭/失败传播不变；注入SQLite由TaskStore拥有并关闭，跨线程须check_same_thread=False。此早审不替代最终整票审查。
- 普通测试不再自动复制技能、连接中心、创建文件Store或启动HTTP。共享fixture仅real时动态请求这些能力；现有DuckDB内存中心显式real。内存SQL只证明状态/事务规则，不证明耐久或文件恢复等价。

## 128个GSE real按不可替代机制归类

| 机制组 | 节点数 | 保留理由与准备复用 |
| --- | ---: | --- |
| C++序列/原生兼容/目录/角色与Lua编译 | 38 | sequence24种排队、castsequence/reset、cast/channel、precombat和来源时序不能互相替代；同类准备由类共享。兼容oracle保original/baseline/disabled三个构建。Lua六控制块集合、随机Loop实际顺序与导出往返各保实际编译。 |
| 爆发 | 9 | 真药水、错spell身份、双来源castsequence和共享冷却；冻结定义、旧成果适配及父子恢复的不同边界。 |
| GA训练与材料/前台接入 | 17 | 五场景四成果、四组共享限额/单组失败、准备缓存/损坏历史、发布与缺组恢复。使用原生评分输入替身，称真实持久化而非完整真实SimC训练。 |
| 冠军及双场身份 | 16 | 可靠发布继承、旧十来源消费、distinct winner CAS、部分取消、补发布/补保存零评分、reference-only错误和冻结引擎身份。规则矩阵已下沉内存。 |
| HTTP/browser及时间线文件生命周期 | 14 | 真实双场SimC/正常复测/编译/复制清空、导入原生、方差失败账本、12份写后登记前恢复、重复任务、保存可见性、根目录改名和CLI曲线。非变异目标N1；报告满组故障N12。 |
| 搜索存储与进程 | 12 | 真Parquet整组损坏至少两个不同行为；成功交换报告保留/清理、冷读不补算、预算累计、原生退出/创建中断、硬退出owned tree和other-owner。非变异目标显式关闭测试变异门，仍完成两代及正常复测。 |
| 检查点/独立技能接入/快照/诊断写入 | 17 | 12份尾组提交与两种恢复、空用户目录真实安装接入、锁与定位文件权限、损坏目标和typed读写、原目录占用/非暂态故障。 |
| 战斗日志工具 | 2 | 真CLI文件/最新会话，以及任务指针实际绑定类型化中心读取；纯归因规则已在StringIO/明确报告输入验证。 |
| 冻结有效输入/配置 | 3 | 原始/有效输入字节、禁用omnium字段、恢复配置身份及篡改在Store前拒绝。 |
| 合计 | 128 | 不是128次完整GA，也不宣称128项都已在当前源码执行。 |

节点数由实际收集得到；实际引擎启动/夹具准备次数、并发峰值及各机制耗时要由后续统一真实运行记录，不能从静态节点数推算成实测。Node/HTTP/浏览器及所有权辅助进程单独计，名义工作进程数不等于OS进程总数。

## 明确退役的重复联调广度

- 训练取消由2种中断×3日志转换的6次真实全链，收为3次代表：foreground on→on、foreground off→on、interrupt on→off。两种中断机制和三种转换分别仍有真实代表，成功批次/冻结身份/尾组刷新/零重算/两段曲线断言保留；不再声称所有2×3交叉都真实联调。
- 正式冠军/训练规则与故障矩阵直接运行真实验证器、原SQL及明确报告输入，不逐故障重跑HTTP全搜索。burst旧/当前引擎适配的重复HTTP组合只保旧引擎真实一条，两种契约规则仍普通验证。
- timeline原9条整段任务流程收为5普通计算断言与1真实文件生命周期，完成、CLI覆盖、取消恢复、准备计时、绘图失败及早期原生错误保障合入该链。
- gear21旧Python入口下沉规则，三个仍支持的引擎各一真实调用；两browser合一完整持久链。原75宝石/100附魔/471产品等逐条原生接受度矩阵退休，不声称未选择条目仍真实联调。四个既有研究入口及两个新增历史/在线回放入口明确manual，不属于自动43项通过。
- 非GSE保Lua本体和原生运行时，不将Lua算法改写Python自证。纯parser/类型、像素/字节、TOC/清单判定进入既有dev-unit；真检查器、构建/打包/部署/WTF备份与损坏目标仍native，复用只读基产物。

## 配置、依赖与后续边界

43项精确候选仍保17 ordinary／26 native、原2build、外4/唯一GSE普通内4。只补实际遗漏依赖，不新增通用manifest或调度框架：Ketho Core固定519文件供LuaLS；Gethe固定TOC612 Lua，生成实际读取611正文及TOC（排除规则在生成器源码输入）。两源独立，不删正确上游资料。

Node普通命令和两browser都运行repo内同一冻结exe，inputs直接hash该exe；setup仅复制现有已装node并核源/目标字节一致，不改系统PATH。CI复用既有锁定Python依赖，不构建或缓存GSE/gear原生引擎。data-store测试副本按实际源码SHA/依赖核身份，无versionmanifest时不沿历史“2.4”名义冒充版本核验。

正式配置与PR Flow工具身份/受管workflow须通过本机已安装新版官方初始化入口写入，保备份；此阶段未手写最终配置，也未伪造官方守卫结果。后续固定全差异独立整审、官方guard及全部43项无缓存60秒验证、必要CI，完成后再做原同输入新旧完整默认自然搜索时间/DPS对照。全部未完成，游戏未验收；不含主干推送、合并或发布授权。

## 完整静态审查五项集中收口（19:08 UTC）

- 硬退出父/子使用同一显式测试0/0概率，恢复另要求completed；不放宽生产恢复契约。该Windows代表待统一执行。
- 入口清单内部collect增加-s，关闭默认fd临时捕获，保StringIO和无cacheprovider；不放宽ordinary写权限。
- 项目/测试README不再走只有空venv的CI快路；它们按真实paths会命中ordinary/inventory，复用现有完整依赖准备，无新runner。
- 技能夹具实际复制源固定为inputs已登记的repo内.local/verify-deps/data-store，外部环境变量若指向其他位置立即拒绝；实际夹具错误源负例已验证在复制前拒绝。
- check_report先核真实整数样本数与原请求一致，再仅把明确数值mean的NaN/Inf/负值分成CandidateScoreError。禁止零、非数值/结构、身份、进程/IO等不隔离；训练及nominal仍终止。新内存代表穿真实check_report→原重试账本→正式GA：旧源实际红灯，新源验证两次坏mean后剔除及恢复不再重试、混错样本优先失败、训练/复测失败关闭。既有子代整槽回退代表不改。

集中云端普通层重跑306 passed、106 subtests，6.56秒；130 real未执行。最新实际集合GSE413＝285 ordinary＋128 real，gear23＝21 ordinary＋2 real。候选配置/README分类断言另以明确候选输入通过，不冒称正式配置已应用。docs和实际集合核查通过。五项修复仍待独立增量复核和新版官方守卫/原生全集；此处不是最终验收通过。

## 2026-10-25 重做版实际证据（以a311为基线）

本节只记录本次重新执行结果，前文2026-10-24的d3结果均为历史。原d3完整源码/Git对象与普通节点清单缺失；旧413＝285普通＋128真实与当前412＝284普通＋128真实相差1个ordinary，现有材料无法定位其确切旧node，不能编造原因或新增低价值测试凑数。独审需特别核这一证据缺口，依据当前a311原始行为/断言映射而不是旧计数宣称无退化。

- 当前实际自动清单：GSE412＝284普通＋128真实；gear23＝21普通＋2真实。inventory实际一次完整收集后验证声明式两选择严格互补；候选仍43项/17普通/26原生、2构建分开、外4/唯一GSE普通内4及60秒不变。正式配置尚未应用。
- 本次集中普通回归：GSE＋gear305 passed、106 subtests，4.10秒，130 real未执行，无skip。不是官方2.7.1守卫/Windows/60秒验收。
- 插件/工具：21技能与DK普通新通过；136项收集为42普通＋94原生。dev纯规则20项新通过；CI/setup/角色另一项使用明确candidate输入直接通过，不把尚未应用的正式config记绿。实际两条BLP写盘/坏源保旧代表新通过。
- 本次取回固定提交的82个所需LFS素材（68唯一payload），逐个核oid/大小后只为只读测试临时还原，完成后逐字恢复原pointer；没有修改素材或Git过滤配置。13项成品TGA只读检查通过。
- 现有8个JS VM全部使用云端同一冻结Node副本新通过：v24.22.1，源/副本SHA256一致。该云端身份与Windows预备的Node分开，不冒充本机浏览器通过。唯一browser语法通过；原重复职业browser只有对应4个Python规则实际通过且summary60行迁回后才删，完整真browser未跑。

### a311断言到当前实现的可核索引

`test-migration-recovery-map.json` 索引每个a311 GSE测试函数、当前位置、实际ordinary/real与展开项，全部改动参数有明确说明；它是审查索引，不是靠AST名字证明语义等价。除明确target_tests/target_file的改名、跨文件和合并映射外沿用原名；已披露的时间线5流程断言并入现有文件生命周期代表及独立曲线等价测试。完整completion/CLI覆盖/取消恢复新段/冻结算法/准备计时/绘图故障仍在。

- 原训练取消2×3真实交叉缩为三条已批准代表；burst旧/当前重复HTTP组合只保旧引擎一条，两个版本规则普通验证。历史损坏分支拆成独立规则项，不丢拒绝与不重发断言。
- `tests/gear-planner/README.md`逐个映射原21 Python入口、两browser及六manual入口；未恢复已批准退役的逐物品原生大矩阵，不夸称其接受度广度仍等价。
- 原注解parser/type主体、DK四个生产缺陷注入和正常链、release全部原assert经本次AST/源码核对；Lua/C++异构原生机制仍真实，不以Python重实现。
- checkpoint九条普通展开项仍跑原TaskStore SQL；以SQLite内存backup交接给新Store，验证状态/事务回滚不丢失，不证明文件WAL耐久。四条真实组提交/恢复保持物理中心。默认TaskStore另在云SQLite实测原路径、WAL/FULL和重开状态不变，不能替代Windows崩溃验收。runtime三个规则测试只替明确进程输出IO，原等待/关闭/仅winerror32重试/取消与局部超时断言保留；真实所有权/进程创建清理由search十二原生代表保护。

### 已知五P2本次状态

1. 坏mean：原确切审查增量先只加测试，本次真实check_report链得到NativeEvaluationError红灯；原样应用窄修复后3容错代表绿。先角色/装备/目标/时长及整数samples身份，再仅明确数值NaN/Inf/负mean分类；训练/nominal/错samples/零分禁止仍fail-closed。
2. 硬退出：父/子测试概率同0/0、恢复要求completed已入新源码；Windows真实硬退出未执行，不能沿用历史绿。
3. inventory内嵌pytest保-s及禁cacheprovider，直接candidate完整收集实际通过；官方ordinary守卫待验。
4. 项目/测试README走既有完整CI准备，CI/setup/candidate断言本次通过；真实CI/官方toolchain生成待验。
5. 数据技能实际源固定为inputs同repo路径；本次负例确认外部env源在复制前拒绝。真实安装/共享中心原生链待验。

原正式GA主体、训练_evolution、双场调度/页面算法相对a311不改；产品只恢复原批准IO/import接缝及上述已批准窄评分分类。未改正式myspec/specs。等待审批的稳定代码采用单一完整源码包持久保存并校验全部源码字节，包含新增文件，排除依赖/缓存/生产数据；私有备份标识只回用户，不提交。

新版独立整票审、官方init应用43候选及实际toolchain/CI身份、Windows真实全集/无缓存60秒、新旧冻结输入完整默认自然耗时/DPS对照仍待完成。不合并、不主干推送、不正式发布或游戏部署。

### ac839独审三P2集中修复

- gear现有bulk规则补回合法数字334混合支持/不支持槽的升级与原样保留、gem/enchant/crafted/输入不变，minimum精确305。正确产品同node通过；五种临时结果故障注入在旧断言漏检、新断言均拒绝，未恢复原生大矩阵。
- 自动GSE浏览器不再继承NODE_EXE覆盖，实际调用直接固定repo exe；新静态绑定负例先确认外部变量能选错，再确认修后无效，22普通及38子测试通过。真实浏览器待本机验收。
- 两手工入口去旧‘未复测、空scenes、最多1000候选/600秒’假设，消费自然停止/nominal完整3×128的实际结果；独立复测证据从真实child采集，不硬False。既有普通CLI测试用1001候选/601秒的新完成结果得到旧入口红灯后转绿，且未完成标记/缺finalists不得写验收成果。
- 原--smoke保留兼容，只在独立手工进程使用已有内建首起点和模块局部NoVariationRandom接缝，不改全局Random；外部冻结输入不丢、正常复测不缩、所有任务结束后恢复，默认完全不打补丁。1260秒手工观察防挂保留，不混作产品总限。烟测并非默认搜索/DPS对照；本轮未实际跑长手工流程。

## 2026-10-25 首次官方守卫故障修复

- 本机官方初始化产物已以`e795cc9`同步，原2构建／43验证配置及toolchain身份保留。本轮完整验证41项完成，GSE普通层失败、真实层总截止，不能称全仓通过。
- 普通层同根因集中修复：仅显式`:memory:`注入的ATTACH改固定字面量，使SQLite prepare阶段authorizer可核文件名；默认文件连接、参数绑定、WAL/FULL及共享缓存不变。冠军历史输入的原生SQLite快照改iterdump/executescript，避免deserialize内部ATTACH x；仍执行同一SQL和凭据核验，不声称文件耐久性。
- 纯输入拒绝代表显式隔离真实中心预检，生产缺DuckDB早失败契约不变；模板及冻结manifest路径先resolve、比较Path，不依赖操作系统分隔符。并发上限拒绝代表使用公开配置读取器及空StringIO，避免读取用户本机配置，原max_processes断言保留。
- 云端使用固定`0cecf8a`的守卫原源码（SHA256 `7b412689b8020dfba993a33ba0bb3a0c433139168a385ab3920fef523392d2b6`）作直接开发诊断，不冒充cloud已安装新版CLI。原两代表在守卫下2failed；修复后8个代表通过。完整GSE普通组保持内4后先暴露9项deserialize同源失败，再集中修复，284 passed／106 subtests，3.05秒；4个守卫worker全部start/finish闭合，evidence_error为空，无违规。
- 本机正式2.7.1普通组、真实组慢点与完整43项60秒仍待后续验收；不提高预算、不将普通组改真实角色、不删原断言或恢复重复真实矩阵。

### 已存在数据中心下的普通定位隔离（07:31 UTC）

本机普通守卫继续定位到18项共享内存夹具缺少report_locations输入：生产journal存在才触发物理锁，云端目录缺失曾掩盖。仅memory_ga显式使用虚拟DATA_ROOT及同一reports字典的键位置；生产数据中心、守卫、官方配置及算法不改。原closeout代表强制journal存在、禁止物理锁边界并验证内存定位确被调用，旧夹具红于物理入口；修复后固定0ce守卫源码下全284普通／106子测试通过，内4、2.72秒，四worker证据完整且无违规。测试计数和原行为断言不变；不是Windows或全43验收已通过。

### 默认配置的显式普通输入（07:44 UTC）

最后3例并不能证明用户TOML损坏：角色read_bytes宽替身也覆盖了存在的默认config路径。一次全普通环境输入探针模拟该路径存在且内容无效，并禁止读取生产data路径，实际找出32项同类隐藏依赖（含冠军输入、timeline和CLI）；未读写用户文件。共享ordinary夹具将省略路径的文档输入统一为StringIO空文档，仍执行原TOML解析器；明确传入的路径/流及真实组完全不改。旧TOML键拒绝代表改显式流，并断言不读取角色文件，原错误与身份不变性断言保留。相同固定0ce守卫、同内4及同环境探针下284普通／106子测试通过，2.95秒，worker完整且evidence_error为空。临时探针仅pytest既有Mock诊断，不加入长期runner或正式配置；生产代码未变。

### 复测取消后的时间线终态（07:54 UTC）

本机已正式证实上一普通层284／106全绿、守卫完整无违规。真实文件生命周期单点取消状态为cancelled却导出stagnation：新GA先自然结束探索，再于正常复测中取消，Timeline的首次stop没有更新最终原因。产品仅在最终导出时让未完成终态更新顶层stop_reason，保留真实探索停止时间及历史search_stopped事件；不改评分/取消/恢复算法，不放宽旧真实断言。新增一个纯内存Timeline代表先红于cancelled与stagnation不符，再验证终态一致、原10秒停止／12秒保存／15秒调用时长不被重写。固定0ce守卫加环境隔离探针的全普通层285／106通过，3.04秒、四worker完整无违规；新增1项回归因此当前GSE413＝285普通＋128真实，不是找回旧d3缺失节点。真实生命周期原节点仍待本机复验。

## 2026-10-25 最小真实交叉收敛（08:10 UTC）

Timeline产品修复独立提交后，原真实失败节点本机已完整通过取消、恢复和旧时间线字节不变；不以删节点掩盖该故障。本节测试迁移不再改生产或正式配置。最新实际收集GSE410＝287 ordinary＋123 real；gear21＋2未变。相对本轮413＝285＋128，明确退休五条重复物理交叉，新增两个普通承接，其余逻辑合并到已存在节点；partial-group跨文件移动但仍real。全部选择仍为not real/real互补，无skip或隐藏过滤。

| 原流程 | 保留的真实机制 | 普通逻辑承接／明确退役广度 |
| --- | --- | --- |
| plain/burst满组登记恢复 | `test_published_burst_report_group_is_reused_after_registration_interruption`保满12份、写后登记前中断、可靠报告零重算、尾部恢复、所有键/组大小/成绩与计数。 | plain Handler请求、False开关和场景由`test_plain_search_request_preserves_disabled_burst_option`保留，普通评分另断言不带burst；退休plain×完整HTTP/GA/物理故障交叉。 |
| 训练缺组恢复 | `test_public_publication_failure_preserves_old_four_and_resume_repairs_only_missing_report_group[retest]`保实际删除12份Parquet、重开SQLite、旧四条不覆盖、伪造成绩拒绝及只补缺组。 | 原coarse分支并入`test_public_resume_verifies_coarse_before_breeding_and_keeps_temporary_read_errors`：完整66唯一请求后仅删6粗评，补6后累计72次评价，另外60份报告/SQLite凭据逐字段不变；原临时读错与繁殖前修复不变。退休coarse×物理Parquet×完整发布恢复交叉。 |
| 冠军取消 | `test_dual_cancel_freezes_formal_champion_and_never_publishes_a_partial_batch[partial_first_batch]`保未完成不发布、冻结快照、外部版本更新和文件恢复。 | complete-winner成功报告后取消由现`test_cancelled_formal_batches_resume_without_repeating_successful_native_requests`保留完整报告、31样本、SQLite恢复不变与无重复请求；现snapshot/cohort验证版本/来源。退休complete_winner×双场HTTP×发布恢复交叉。 |
| 坏variance／未知导入拒绝 | 真selected-import评分及唯一完整browser不变。 | `test_formal_search_rejects_missing_variance_without_failing_task`走同正式GA：3候选、两次坏评分、剔除、120赢家、2完整finalists各3×128/381样本；未知技能99999999的failed/no-DPS/不可展示并入现`test_unmapped_import_error_is_reported_without_dps`。不再为纯拒绝规则重跑HTTP/GA。 |
| 部分组提交恢复 | 同名`test_resume_after_partial_group_commit_uses_unused_group_number`移到`test_checkpoint_changes.py`原helper，仍真实13报告、11＋legacy第12＋tail、确切SQLite备份重开、report-intent恢复、g0=11/legacy=1/g1=1、next_group=2、键/成绩/摘要与清理。 | 退休整段HTTP/GA准备；原native评价计数与实际输出相关性仍由burst满组真实代表验证，此处只证明13份已产生报告的输入计数恢复不重计，不能称完整搜索联调。 |

最新real机制数量为C++/角色/Lua编译38、爆发9、训练/材料/前台16、冠军/双场15、HTTP/browser/时间线10、搜索存储/进程12、检查点/接入/快照/诊断18、战斗日志2、有效输入/配置3，合计123。4+4+1+1旧来源消费未改；唯一browser、异构原生C++/Lua、整组损坏、hardexit/other-owner和DataStore独立接入均保留。不宣称旧重复交叉广度仍真实联调。

各域普通诊断先验证承接，迁移敏感性故障由同输入边界实测，不捏造生产红灯。集中固定0ce守卫＋坏默认配置存在／禁止生产DC读取探针：287 passed、106 subtests、2.98秒，四worker证据完整、evidence_error为空。清单及每个a311原函数映射已按实际收集更新；同名/AST只是索引，新增跨机制承接须独立读断言复核。Windows新真实节点、完整43项/60秒、内2实测及同输入默认新旧DPS对照仍待；本节不是速度或整体通过承诺。

## 2026-10-25 已测真实内4候选（08:29 UTC）

- 固定源码e4ecc2d：本机普通287 passed／106 subtests，官方守卫四worker证据完整无违规；新partial-group真实节点和原Timeline生命周期均通过。真实内2一次60.266秒时79通过、44未完成，无已见失败，不作为通过证据。
- 同源码真实内4单次123 passed／24 subtests，0失败／0未完成，pytest55.36秒、外层55.687秒；没有修改正式配置，未发现本轮内存／路径污染。只证明完整真实组完成，尚不证明全43项入口至收尾60秒通过。
- 本机已有保存argv和WorkStealingScheduling日志确认当次为-n 4 --dist=worksteal；候选仅为verify.sim2gse-real增加pytestXdistWorkers:4及同--dist=worksteal。43个检查、17普通／26 native、real角色、全部123覆盖、paths／inputs、outer4／ordinary4／60秒均不变。0cecf8a官方runner先统一校验/注入xdist字段，再按角色运行，不需要把原生组改为普通组。real仍为第二个并行检查，外4第一波启动；不新增调度机制或串行其他检查。正式config不手改，由本机官方init --config --overwrite应用此候选后统一验证。
- 静态资源边界：两GSE组同时内4，含控制端及另外两check主进程共12个，不含BAV／guard。GSE真实引擎局部上界8个单线程SimC，gear并行原生调用最多再叠1个；浏览器自身多进程、HTTP／Node与所有权helper另计。训练受控20线程回调不是20真实引擎。OS总峰值未实测，不承诺不超过16。

## 2026-10-25 已测真实内6候选（08:53 UTC）

- 官方受管配置7e77e4e仅应用内4／worksteal，整轮43项42通过／1超时，总60.046秒，real检查运行50.16秒被截；不能从两者差额断言全是指纹耗时，首次全选准备及逐项执行重算机制仅为已核静态事实。未修改工具预扫描、必要inputs或守卫。
- 同HEAD独占真实内6／worksteal一次123 passed／24 subtests，pytest43.97秒、外层44.297秒，0失败／0未完成；相较内4外层55.687秒少11.390秒（20.5%），未见本轮进程／内存／路径错误。普通287／106之前本机守卫已通过，未因纯参数改动另跑无关节点；内6混合全43尚未测，不称60秒整体通过。
- 候选唯一区别为verify.sim2gse-real的pytestXdistWorkers:4→6，worksteal／outer4／ordinary4／60秒及全部123覆盖、角色和依赖不变，正式config由本机官方init应用，不手改、不再试其他参数。静态混合check进程14个（10worker＋2控制端＋另2check），真实GSE局部最多12个单线程SimC，gear并行另计最多1个；浏览器／HTTP／Node／所有权helper另计，OS峰值和混合资源竞争仍未实测，不能承诺总进程cap。
