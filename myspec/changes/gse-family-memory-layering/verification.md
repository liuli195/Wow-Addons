# 整族分层实施验证

固定基线：云端9b1a958f86bb4d35133fe35913debfff59e67ad7；此前已验收执行代码abb20fc，本机阶段三43通过、59.937秒/GSE49.41秒。当前沿codex/formal-search-ga-default同树；他人未跟踪Lua草案保留。

## 票01

已完成云端实现，修改范围test_dual_engine_identity.py、test_data_store_connection.py。能力拒绝移普通；locator两文件真实读取异常链保留，页面错误映射调用真实_read_public_state内存验证，移除JSONL唯一重复HTTP。引擎读取注入改为物理产物篡改，真实SHA拒绝且_launch/Popen均不调用。身份多次启动/恢复整链与启动故障三组合保留：直接迁移_worker会涉及子任务、lease、导出及持久化编排，不新建模拟调度器，不能称该部分已下沉。

- 红证据：移除binary能力拒绝逻辑、移除异常cause遍历、移除引擎SHA核验的独立诊断进程分别使对应断言失败；生产文件未因这些诊断落盘修改。
- 绿证据：普通全组291通过＋108子测试，122真实排除，4.79秒；inventory为413=291普通+122真实。
- 两文件定向13实例：9通过、4失败；对原HEAD函数原位替换的基线诊断同4失败。locator两例直接缺msvcrt；optimize启动及身份整链的handle.error亦为ModuleNotFoundError('msvcrt')，未绕锁、未计通过。物理引擎篡改新节点通过。
- 日志：.local/tests/gse-family-memory-layering/ticket1/ 下*-red*.log、ordinary-suite.log、inventory.log、targeted-final.log、baseline-targeted.log；约5MB。
- 主代理再次直接运行普通两项通过，文档423份检查通过。正式Windows守卫与真实平台链由父层安排；云端直接pytest不作为官方守卫证据。
- 首轮固定80b511b独审：规范0；需求P2指出SHA规则未普通化。返工补显式内存lock/manifest/bytes调用真实identity，先成功再变更bytes拒绝，并调用真实页面错误映射；物理代表不变。去SHA核验红灯失败，正常普通+物理2通过；普通全组更新292通过＋108子测试，inventory414=292普通+122真实。返工固定291f997，规范/需求两轴复审均0发现，P2关闭。全部独审只读，通用Reviewer回退gpt-6.1-sol/high。

## 票02/03

票01独审完成，票02已从291f997串行开始；票03待后。未改正式规格、配置、默认预算、正式数据或Lua。


## 票02云端实现结果

唯一生产变化是task._assemble_formal_starts原样提取53行纯组装。独立AST核验：原段和新函数体（不含说明及simulation_config局部别名）一致；原_run_optimize只替换一次调用，snapshot保存、phase、后续save时序不变。

原14函数逐assert表达式快照及逐节点去向见.local/tests/gse-family-memory-layering/ticket2/{original-assertions.json,implementation-summary.md}。关键承接：

- 十来源真实initial_programs/_seed_programs/组装→memory_ga完整复测→真实CAS，保4/4/1/1、旧200/新300、空chains、自然停滞、v2/空promotion/两完整代/3×128与381样本；use_burst=True，组装和GA共用生产过滤后的能力。真实载体改准确命名HTTP双场发布/读回/三导出集合，外部固定评分促自然停滞，不改生产预算。
- 两场继承分别用完整明确证据、真实_freeze/组装/GA重新评分/_prepare/_publish/CAS；观察真实发布参数，避免同behavior提前unchanged掩盖错误version。精确current_score回填与旧分相同断言移到现存实际取消恢复末尾。
- stale竞争保两份完整已存不同赢家、真实两线程Windows锁、冻结absent→expected0/None→published/conflict→中心重读；撤原4场准备。普通精确保护版本/完整incumbent拒绝及零write。
- v1历史选择/伪造拒绝/去重/65上限进普通，保两真实旧来源、公开profile拒绝与成功管理导入，不把v2当v1。撤foreign物理来源与重复拒绝任务；原helper本不跑GA，不夸大省搜索。
- 取消首轮只准备必要单体冠军，取消/检查点/外部version更新/恢复断言全留。pending发布恢复保原合法单任务准备；不造新的checkpoint协议。其他已内存组合原样保留。

验证：全普通301通过＋108子测试；fixture使用者71通过，退出码均0；inventory422=301普通+121真实。formal模块48普通通过，5真实因Linux缺msvcrt失败，未绕锁/跳过，待Windows。敏感性红证据包括新接缝缺失、删正式来源造成9≠10、最高改最低、绕CAS版本、发布错传version；全部仅进程内诊断，无生产落盘修改。日志与临时数据累计约7MB。云端直接pytest不是正式守卫；未测本机墙钟，尚不宣称收益。固定提交e6a844f，独立规范/需求两轴均0发现；两轴均只读未运行。票03随后开始。


## 通用适配修复的授权整合

父层明确授权在已审干净e6a844f只拣选独立任务c92790d（代码）及640e1e3（文档），无冲突得到6bb0b2e、13a6d89。两组稳定patch-id分别与源提交一致（a9d6ed423805d4ef8aeea7af38b0d2bba52ab62d、283ddb552e48c091e8893ecb54458f6fdc16d731），未覆盖已审组装提取、调用或save/phase窗口。整合规范/需求独审均0发现。

组合云端普通356通过＋108子测试（5.40秒），inventory477=356普通+121真实通过；证据.local/tests/gse-family-memory-layering/integration/。原适配分支的Windows通过不替代组合验证。最终提速对照优先采用同适配修复基线的工具59.8889秒/墙钟60.157秒，不能与未修算法的旧单轮混称净收益。本机AB与正式验收由父层串行安排，本任务不擅启本机运行。


## 票03云端实现结果

仅test_checkpoint_changes.py新增普通真实SQLite SQL组合节点：_commit_report_group→deferred put_batch/checkpoint→immediate，真实flush因空缓冲自然返回，不替换返回值。原real中本对象完成数4和摘要逐值相等迁普通；普通再精确保护五份编码各1、state_write_count2、shared.reusable仅batch/cached/immediate。

原真实stage_report→flush→locator/Parquet、第二Store共享隔离、物理重开完整状态相等全部保留；其编码/写次数仍保接线交叉证明，不以直接_commit冒充flush。13份部分提交布局、12份原引用回填、末组失败same_object/reopen全部原样。此票不减少真实准备，不宣称性能收益。

敏感性红：重复编码使batch-0计数2≠1；移除final共享过滤使真实SQL多出final；均仅进程内诊断，正常绿。普通模块10通过/5真实排除；组合全普通357通过＋108子测试（4.99秒），inventory478=357普通+121真实。真实mixed定向1失败，原因ReportLocations.locked缺msvcrt；未绕锁或skip。详见.local/tests/gse-family-memory-layering/ticket3/implementation-summary.md与日志；全任务证据约7MB。固定提交2513b4f，独立规范/需求两轴均0发现；Windows组合正式验收待父层串行安排。全部原测试实际核销及数量见outcome.md。


## Windows组合定向首轮与返工

远端0f2574（云端6a9b7aa，同树5b153772）四模块定向80通过、2失败；pytest23.19秒/墙钟23.547秒，无进程残留。尚未运行完整43；不能将此轮计为验收通过。父层回读证据：`.local/formal-ga-development/family-target-6e484f29c2594d3f80805bcb2d52fc5f/{pytest.log,result.json}`。

两项均为本轮测试夹具缺陷，Windows只读诊断证据位于`.local/formal-ga-development/family-diag-ed3e76a57637435e801114a77db9bd56/diagnosis.log`：

- CAS竞争：首线程已持真实冠军锁与共享_PUBLICATION_LOCK，却等待次线程到冠军锁入口；次线程此前的真实来源验真经report_locations也需同一_PUBLICATION_LOCK，形成测试等待环。不是超时太短，不改变生产锁或增加等待预算。
- 取消恢复：单场准备profile.write_text在Windows将LF写为CRLF（401字节/14个CRLF），HTTP原始资料为UTF-8 LF（387字节）。配置、simulation与condition相同，但有效输入SHA及冠军condition_key不同；第一场已成功发布version1，双场读取的是另一字节身份的absent记录。应使准备输入与HTTP负载字节精确一致，不能改生产身份算法或伪造冠军。

在同一已授权票02内返工；原断言、真实锁/报告/取消/版本更新/恢复全部保留，最终通过以修复后的Windows定向及完整43为准。

返工实现只改test_formal_champion.py：两发布者在尚未持冠军锁前完成来源核验握手，再有序竞争原真实锁；原10秒界限不变，不替换_PUBLICATION_LOCK或msvcrt。单场准备写入UTF-8原始bytes，并检查实际原始输入副本与HTTP资料一致、取消冻结冠军键与已发布冠军一致。云端Windows换行敏感性红401字节/14CRLF失败、绿387字节/0CRLF通过；模块普通48通过，全普通357通过＋108子测试通过。两个真实节点仍因Linux缺msvcrt失败，未绕过；Windows成功尚待重验。证据`.local/tests/gse-family-memory-layering/repair/`，整批云端约7MB。


## Windows修复重验与全仓新失败

远端f4b40e19（云端6b5861f，同树3bc16e05）原两失败目标2通过、四模块82全部通过。随后完整43中42通过、1失败，工具55.2787422秒/墙钟55.547秒；GSE真实120通过、1失败＋21子测，检查45.58秒；普通357＋108及17守卫通过，无残留，精简产物147MB。未达完整验收，不用此失败轮宣称提速。

新失败为范围外test_search.py::SearchAndValidationTests::test_native_global_failure_stops_task：期望TaskError但未抛。父层Windows单项诊断1次通过，8次CreateProcessW均有batches目录、8次命中exit9替换并产生NativeEvaluationError→TaskError；原全仓未记录注入命中，不能声称原轮机制已实证。同轮CrosshairHUD组虽通过但有cmd /c mklink /J的text=True输出解码线程警告；父层确认基线18bc也有相同byte b4/pos288，作为独立未决既有警告记录，不混修。

只读复核定位本轮HTTP主路对sequence.evaluate的替换生命周期：测试使用共享monkeypatch，而champion_engine/page_task_engine用嵌套patch.object；外层monkeypatch最后撤销可能重新装回已经退出的夹具Mock。修复限原批准test_formal_champion.py的替换作用域；不改test_search断言、生产代码、故障注入或超时。原失败轮未采集调用身份的限制仍保留，必须用实际夹具退栈红绿与Windows串行组合重验确认。

旧f4b40第二次完整运行仍42通过/1失败（同native_global_failure节点，gw1），工具54.0628614秒/墙钟54.313秒，GSE真实44.64秒；普通357＋108、17守卫通过，无缓存/残留。证据`.local/formal-ga-development/family-fixed-repeat-e57a19be68374b28bb75a2c6dd639338/`。原及复跑日志没有HTTP主路逐节点worker顺序，不能宣称已经观察到同worker因果。父层已停止旧版本重跑，本机本阶段累计精简产物263.68MB。

云端实际fixture生命周期红绿已完成：直接组合page_task_boundary、champion_engine.__wrapped__生成器及pytest.MonkeyPatch，原顺序退栈残留MagicMock（原函数身份断言失败）；局部patch.object修复后完整退栈恢复原函数。持久测试在局部退出后也断言函数身份恢复。仅该HTTP测试+5/-4行，全部业务断言保留；同文件其余新real替换未发现同类混用。普通357＋108通过，直接pytest不是正式守卫。证据`.local/tests/gse-family-memory-layering/repair-isolation/`。


## 最终Windows验收通过（2026-10-25）

父层读取并核验本机结果后回传：远端`cb4d88ede51469d7e369cefb7c22fb46175d7dee`，云端`b393dbd1ead4708ccf5844ecee5a4c9f995d4c71`，同树`f3d0ced84f33d21981e0b6d24d29b1c3e8377bfb`。第二修规范/需求双轴独审均0发现，首修双轴也均0发现；审查均只读。

- 同一pytest进程顺序执行HTTP双场主路→真实原生失败测试：2通过，pytest2.06秒/墙钟2.391秒。此项补上跨例退出隔离的组合证明；原失败轮没有逐节点身份日志的限制不追溯抹去。
- 正式完整43检查全部通过；工具55.7311596秒、墙钟55.984秒，均在原60秒内。无缓存、未完成检查或进程残留，正式配置未变。
- GSE普通357项＋108子测试通过，17普通守卫通过；真实121项＋21子测试通过，真实检查44.78秒。先前四模块82项已通过，两次修复没有新增或减少测试实例。
- 同适配修复基线18bc：工具59.8889264秒、墙钟60.157秒、真实49.50秒。本轮分别少4.158秒（6.94%）、4.173秒（6.94%）、4.72秒（9.54%）。这是单次观察，不证明统计稳定收益，不把失败轮较短耗时当成功收益。
- 本机本阶段精简产物总382,223,637字节，小于516MB；云端整批证据约7MB。未重训、修改正式数据、合主干或发布；Lua尚未实施，非全仓内存分层全部完成。
- CrosshairHUD既有输出解码线程警告仍开放，所在检查通过；基线已有相同警告，不称已修。此前benchmark目录重试偶发的阶段三处理与本轮结果分开，不用本轮通过虚称所有历史环境偶发均消失。

本机证据均位于`.local/formal-ga-development/`：

- `mock-cleanup-target-b1fd0dd2300b45b39c810e99cfb802b0/pytest.log`
- `mock-cleanup-full-0de23cafab1648418897d38775f78547/verify.log`
- `mock-cleanup-full-0de23cafab1648418897d38775f78547/performance-report.json`

本次仅更新验收文档和票据状态，保持已审、已验代码不变。前述80通过/2失败、42通过/1失败及复跑失败记录均保留。
