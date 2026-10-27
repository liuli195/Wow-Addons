# 三票整体审查：默认双场页面证据修复

整体两路审查在2825a993发现一项有效P2：单场公开映射已有N/W，但默认双场读取绕过该映射，页面也没有展示实际复测预算与样本。本轮修复不改变DC/RTR竞争、评分或停止算法。

## 完整数据路径

- 现有TaskStore进度发布在正式复测名单冻结后返回实际入围预算及已完成有效样本；名单尚未冻结时不虚构预算。
- 保存正式结果时保留预算摘要，读取结果中心记录时还原；取消后即使没有最终冠军摘要，也从可靠冻结复测状态保存预算。旧记录缺少这些证据时仍可读，不用现行默认补造。
- 默认dual（双场）GET入口逐场传递冻结N/W及复测预算，支持运行中的进度、取消/继续前的保存状态及完成结果；尚未开始的场景不填0。冠军有效样本与全部入围复测有效样本分别显示。
- 页面既有进度区域展示各场初始人数、窗口、已知代数、入围人数、完成/计划批数、计划请求及有效样本。缺项明确显示“待初评”或“尚未提供”。

## 实际验证

现有Python定向命令：`-m pytest -q tests/sim2gse/test_interface.py tests/sim2gse/test_formal_rtr.py -k 'default_dual_http or progress_and_saved' -p no:cacheprovider --tb=short`。

- ticket-03-dual-red.txt：2失败，分别缺双场人数与已发布进度预算，exit1。
- ticket-03-dual-green.txt：2通过，exit0。测试执行实际HTTP处理器与dual_task.read，替换持久输入边界，不只检查单场私有映射。
- ticket-03-dual-paused-red.txt：追加取消保存预算负例后1失败，exit1；随后补齐保存分支。
- ticket-03-dual-regression.txt：全部普通测试518通过、168子测试通过、4真实排除，7.52秒，exit0，包含取消保存负例。命令为 `-m pytest -q tests/sim2gse -m 'not real' -p no:cacheprovider --basetemp=.local/tests/ticket03-dual --tb=short`。

Node内存DOM（文档对象模型）诊断使用现有Node及标准vm模块，直接加载生产interface.html完整脚本，执行真实按钮回调、轮询与继续回调，仅替换DOM和fetch输入；不启动浏览器、HTTP服务或模拟。脚本 `.local/tests/dual-page-display.cjs`，命令 `.local/verify-deps/node/node.exe .local/tests/dual-page-display.cjs`。ticket-03-dual-dom-red.txt实际因页面缺人数失败exit1；ticket-03-dual-dom-green.txt实际通过exit0，覆盖默认mode=dual、运行中2/18批与254样本、继续、完成18/18批与2286样本/381冠军样本，以及待开始场景无假零值。

原有唯一真实页面测试已加入对应最终DOM与每场预算断言，仍由统一验证登记；本轮没有运行它，不把内存DOM诊断冒充浏览器或真实链通过。测试登记核验522=518普通+4真实，未新建测试框架或额外真实测试入口。

## 规格及交付边界

既有MySpec候选已明确“公开页面、进度及完整结果保留实际N/W、阶段、有效样本及实际入围预算”，本轮落实该承诺，无需求内容变化，未改增量正文或正式规格。现存预览回执绑定a70b7701源码，不可冒称已重新绑定本轮代码；下一次正式应用前需按新输入指纹走受控预览刷新，并取得该会话无活动操作确认。现有预览差异仍可作为不变需求内容供复审。

真实统一验证此前在Windows PowerShell启动阶段被AuthorizationManager拒绝，入口尚未执行；已有批准的单次启动未产生真实模拟。未擅自更换启动器、调整策略或再次运行。保留启动与清理回执于.local/tests/sim2gse-dc-rtr-verify。

整体预算从19:08 UTC起，21:04 UTC约116分钟，任务产物仍远低于50MB；本轮仅小代码、测试及日志。提交后停写，交由主会话安排同一code-review技能内两路独立整体复审，不自行派子代理、不申请第二门禁、不应用规格、不推送或合并。
