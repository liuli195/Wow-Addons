# 整体复审第二轮：取消/失败保存的冻结人数

上一轮取消测试错误地从完整结果复制并保留search，无法代表run_task的真实取消/失败结果。本轮改用仅有status、phase、elapsed_seconds及error的结果，不含search；冻结人数仅存在state.ga。

生产修复只在task._store_run中，从已有state.ga补入effective_population_size和rtr_window_size。未冻结的字段不写，不根据当前配置、候选列表或默认人数推导，也不改变竞争算法。

参数化覆盖cancelled/failed各自初评已完成与未完成，共四项。沿真实保存函数、结果中心记录读取、默认双场公开读取入口验证：已冻结N=6/W=4保存及读回一致，继续前仍显示原值；未初评没有N/W或复测预算，不捏造0。已冻结复测预算继续保留。持久I/O边界采用既有内存夹具，未宣称真实磁盘或浏览器链完成。

定向命令：现有Python执行 `-m pytest -q tests/sim2gse/test_formal_rtr.py -k progress_and_saved -p no:cacheprovider --tb=short`。

- ticket-03-cancel-shape-red.txt：2失败、2通过，已初评取消/失败缺N/W，exit1。
- ticket-03-cancel-shape-green.txt：4通过，0.53秒，exit0。
- ticket-03-cancel-regression.txt：521普通通过、168子测试通过、4真实排除，7.58秒，exit0。全回归命令为 `-m pytest -q tests/sim2gse -m 'not real' -p no:cacheprovider --basetemp=.local/tests/ticket03-cancel --tb=short`。

本轮仍不运行真实验证，不更换PowerShell启动器，不修改执行策略。按主会话要求，规格预览留待最终修复稳定后刷新，未应用正式规格。整体时间21:10 UTC距19:08起点约122分钟。保存稳定提交后停写，等待两轴整体复审。
