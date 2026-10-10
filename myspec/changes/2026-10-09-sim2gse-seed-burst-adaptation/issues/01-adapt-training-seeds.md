# 01：适配旧起点的独立爆发训练

**What to build:** 人工训练公开入口从原登记件/历史成果派生不含固定爆发动作的普通循环，保留原来源与逐项差异，并走既有训练和入选路径。

**Blocked by:** None（无）

**Status:** completed（实施与正式规格验收完成，PR交付待执行）

- [x] 当前固定爆发定义的全部排除动作在训练派生件中移除；不硬编码两技能。
- [x] 普通块、循环剩余顺序/重复和施法序列原reset保持；空循环删除，单成员施法序列明确拒绝。
- [x] 没有普通动作、未知动作和无效结构明确拒绝，无静默转型。
- [x] 原登记/历史不写回，现有处理记录可追溯原程序及删除差异，旧成绩保留。
- [x] run/list公开接缝完成最小红绿覆盖，独立审查无阻塞项；区分云端诊断、统一Windows验证和未运行范围。
- [x] 规格候选经完整预览与门禁二批准后，通过官方工具原子应用并校验正式规格。

## Comments

2026-10-09用户确认门禁一与核心保留补充，并明确批准Fast（快速）流程。固定基线ca346a199291ad1fc983d2fa36ae2edbf6fd4231，云端同一工作树功能分支codex/sim2gse-seed-burst-adaptation。

公开run/list接缝的最小红灯复现旧代码在segments[0]拒绝当前角色不支持的动作。云端Linux诊断沿用真实数据中心副本、Parquet读写、搜索状态机及现有合成外部引擎报告边界，Windows文件锁仅由本次临时POSIX锁适配。五个新增场景和相关旧训练回归共16项通过、9项未选中，58.48秒；文档编码与测试入口登记检查通过。此证据不代表Windows受控引擎或游戏验收；原生相关检查和固定基线统一快速验证仍待支持环境验收。本机正在运行的五目标训练未触碰。

独立两轴审查发现单成员拒绝缺少删除差异、超长原动作块可能因删除被放行，以及历史分支只有去重覆盖。已修正为先保留派生记录再拒绝、删除前保持既有原始块数量上限、补仅历史独立训练。单成员缺差异红灯已复现，超长块在3173ca7旧提交红灯已复现。修正后的七个公开接缝核心场景通过；此前扩展回归17项通过、9项未选中、61.93秒（Linux诊断，不是正式60秒Windows预算验收）。正式统一快验实际在Linux退出1：Windows解释器路径无法执行，checked为verify.sim2gse、verify.docs、verify.test-inventory，不能报告passed。

增量审查另发现原样拒绝超128节点程序时，附带缺members的施法序列会误触新单成员检查并抛KeyError；公开入口红灯已复现，检查仅用于实际删除后的派生件，原错误交原解析处理。最终八个核心场景通过，独立两轴增量审查无阻塞。功能分支仅为后续隔离Windows必要验证发布，不代表门禁二通过。

隔离Windows首次固定基线统一验证49.83秒退出1：verify.sim2gse为413项通过、2项失败、128子测试通过，文档及入口登记通过；两个失败位于既有双场景恢复测试，不记正式通过。云端复现本次新增测试的嵌套替换污染：外层训练引擎替换退出后，整票monkeypatch回收又恢复了临时Mock。既有run/list参数测试增加入口函数回收断言，单场景红灯2.01秒确认真实函数变成Mock；首次训练也用既有monkeypatch.context在外层退出前回收，八场景绿灯21.30秒。仅修测试隔离，不改生产或验证配置；最终提交仍待Windows统一验证。

远端c546963e3dc9c387b8dc5c2bac4e234533b2d3cc（树2d99250174f34f34c5a2985ec7888fbec8029b34）的固定基线Windows统一验证已验收：status=passed，exit=0，总54.41秒；verify.sim2gse 51.17秒、415项通过及128子测试通过，verify.docs 1.69秒、342份文档通过，verify.test-inventory 0.31秒通过；checked三项非空。隔离工作树tracked干净，原主工作区main仍为ca346a199291ad1fc983d2fa36ae2edbf6fd4231。失败两项此前单跑20.20秒均通过，原失败报告含合成边界版本12.1.0.69587及mean=100，与污染红灯一致；实际角色和爆发为12.1.0.69933。原始证据位于D:\My Project\Wow Addons\.local\worktrees\seed-burst-fast-caae24b\.local\validation：formal-fast.log、formal-fast-exit.json、two-failures-rerun.log、failure-evidence/identity-summary.json、failure-evidence/all-artifacts.json，以及最终formal-fast-c546963.log、formal-fast-c546963-exit.json。

独立规范与需求轴审查对原最小实现及af6cb668eadff58cdf3350320bbfb4fda3e5db16测试隔离增量均无阻塞，分别保留红绿和正式验证边界；正式规格候选额外只读核对已收窄为产出派生程序后才承诺删除记录，无效来源在原解析器预校验中被拒绝时不承诺中途局部差异。生产引擎、标准角色、600秒候选预算与两个完整无改善轮次不变。尚未重训此前58个拒绝件、未进行游戏内验收；正式规格应用、PR合并和安全清理仍待门禁二。

2026-10-10T05:30:06Z用户确认门禁二完整收尾范围：应用已展示规格、通过检查后合并、安全清理本次功能工作区，并继续补训。云端本次用MySpec 2.3.0正式应用；应用前重算规格指纹aa601fd953b732e1188e0fc36050e80f812f863457faf528292112e437693cff和输入指纹2c360a798229d0c5c29cbe0ec4ef618a5aec0629ad14f6a79e9e7d3bb8dd3200，均与预览状态一致，READY_TO_APPLY且0冲突。官方validate-main、validate-delta和预览校验均退出0，再用apply-delta原子更新sim2gse-reviewed-burst正式规格；应用后validate-main退出0，正式差异逐字等于已批准预览（SHA256 04c8ffd40fcae9e69e5179fb05ce9650f3f19f08fcd52b3bc2ce88b53e672247，12行增加、2行删除），工具已清理本次current工作区及锁。相对已通过Windows快验的c546963生产和测试代码无变化；本次云端仅增加正式规格与票据证据。主干合并、安全清理及补训仍由本机隔离交付接续，尚未宣告实际游戏验收。

本次应用后的云端最小检查均通过：myspec validate-main myspec/specs退出0；python scripts/dev/check.py docs退出0（342份文档）；python tests/dev/test_inventory.py退出0（测试入口登记）；git diff --check退出0。以上是云端文档、正式规格和入口核验，非新增Windows聚合通过。隔离本机交付须在最终远端提交和干净工作树上，以固定基线ca346a199291ad1fc983d2fa36ae2edbf6fd4231继续官方build-and-verify快速验证及PR Flow收尾。
