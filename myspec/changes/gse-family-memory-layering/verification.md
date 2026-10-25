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
