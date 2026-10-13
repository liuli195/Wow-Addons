# 01: 双场正式搜索消费最终训练冠军

**What to build:** 用户从原网页双场入口开始搜索，原4加4保持，各场独立追加同条件全部已完成训练的最终冠军；当前角色重新适配、评分及去重，来源和冻结结果可查询，恢复不刷新。

**Blocked by:** None（门禁一批准后可开始）

**Status:** ready-for-agent

- [ ] 单目标和群体目标从各自同条件全部completed最终program/scores选择均值最高者；67条样例、initial高分、core=false、final不变、稳定同分均正确。
- [ ] 精确核验模板、引擎、完整语义条件及三份最终复测证据；缺失、损坏、不符与临时读取异常正确区分。
- [ ] 复用严格当前角色适配；最高者不能用时缺席，不改用第二名、不修改旧四代表或旧训练数据。
- [ ] 原程序/旧分与适配后的程序/当前分分开追溯；等价合并保留来源，不凑第九条。
- [ ] 初始化仅冻结一次，取消/崩溃恢复不读新训练冠军；训练流程、并发、语义版本与旧式凭据核验不被默改。
- [ ] 红绿及最终冒烟从POST /api/tasks mode=dual到GET结果，公开任务恢复与故障检查补充；红绿和云端/Windows执行证据分别记录。

## Comments

2026-10-13：已批准业务方案，门禁一完整内容尚待用户确认；本票未实施、未运行测试。此票只读训练成果，不运行真实训练或写用户真实数据。

2026-10-13 14:25 UTC：完整门禁一获用户“确认”（Sentinel_b873d11a5c088191b558d9b9ecbfd0ab）。进入第一票红灯准备。必要Windows验证由父端协调；不得伪造锁模块以绕过平台依赖。

2026-10-13 14:35 UTC：真实Windows红灯成立。远端提交53e3c1a904f6c389c192cc73a2428e5935cedfec，树83fbf7a9154c526eeca6f7668911b7d711ba1369；公开POST双场到GET场景结果在test_training_champion.py:125报KeyError training_champion_snapshot，exit=1，1 failed in 4.00s。证据为本机仓库.local/t/champion-red-20261013-223420/red.log与exit-code.txt。Linux实际收集被msvcrt缺失阻塞，不算红灯。开始最小实现；严格旧凭据不扩范围，旧批次源码兼容限制留待专项核验。

2026-10-13 14:45 UTC：首个同路径Windows绿灯成立，远端b1387007825631045e8dbcea05828ba398f7adce，树a1e67283e977a92348dfd7911725fa98c5450a36；exit=0，1 passed in 4.88s。证据.local/t/champion-green-20261013-224115/green.log及exit-code.txt。开始下个窄纵向参数化批次，覆盖67条最终记录、旧四代表与只读存储、完整条件和原复测故障、非法原生单条拒绝；先跑新增公开入口断言，后修实际红点。

2026-10-13 14:54 UTC：第二窄纵向公开入口Windows红灯为2 failed、16 passed in 25.10s，外层25.55s，exit=1，未超过60秒。远端8ce340a9028a863b0dea1fb459993eb52268a1cb，树6453928ab89d586ab661d817a5c3e02c30af4d17；既有pytest-xdist使用4个独立隔离worker，不减少覆盖。实际失败为缺失最终receipt被误标invalid、来源标记把非法原生起点提升为整场失败。按这两个真实红点最小修复，缺失明确标missing，原生标记只跳过单条非法行为而保留原优化器拒绝语义。证据.local/t/champion-red18-20261013-225240/stdout.log及command/result。

2026-10-13 14:59 UTC：同18项Windows绿灯全部通过，远端2054eb097b8c3cdffb27e0f1a651890ff00eb9cb，树9e4373aaeeb7e1a49ba3f1cd02e4f4a929d0d794；18 passed in 24.92s，exit=0，外层25.38s未超过60秒。证据.local/t/champion-green18-20261013-225653/stdout.log、command.txt、result.txt。只读核对另发现真实训练检查点不保存native，之前合成夹具多加该字段，尚不能据18绿验收真实训练消费。最后窄批去掉虚构字段，启用生产报告角色核验，补角色身份、第二/第三报告关联否定、最高不适配不换第二名、等价来源合并、公开取消恢复冻结及临时读取错误；先取得真实形状公开入口红证据再修产品。

2026-10-13 15:11 UTC：真实生产shape公开入口Windows红灯为22 failed、10 passed in 36.48s，外层36.94s，exit=1，未超过60秒；远端b7658fdfc8f44eaa36f83767f885480cf147c781，树083dd2c20298c39c39ea4af787b12b87e64aefc4。失败集中于真实检查点无native导致冠军缺席（candidate_id缺失）、等价适配为None，临时报告故障未触达。最小修复不再依赖虚构native，从第一份原报告定位并冻结标准角色spec_id，逐份核验姓名/职业/专精/种族/定义及原缓存身份和完整报告；原check_report及_validate_saved_batch不放宽。测试同时以每候选三报告的实际storage_group_key点读，故障修改/注入明确指向实际group和各batch_key，67样例写入分组从201减至67，不减少覆盖。证据.local/t/champion-real-red-20261013-230529/stdout.log、command.txt、result.txt。
