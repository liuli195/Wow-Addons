# 数据管理性能诊断与测试证据修正

2026-10-02。本轮起点为干净的 `a75ed32069a6480ee680f13d3b7a07ba6fef3a3f`，固定正式基线为 `f554538993161cc045d19c4ed47d261f709f741b`。不修改共享 build-and-verify、模式绑定、缓存或并发配置；本轮独立 pytest 诊断不代替正式验收。

## 正式失败的具体范围

原正式报告生成于 `2026-10-02T14:24:35.822Z`，38 项检查，总耗时 60.0143788 秒，原因 `total_budget_timeout`，阶段 `finalization`。重新按报告数组计数，纠正此前口头 37/19 的误报：15 passed、3 timed_out、20 not_started。日志的选择原因是 `config-changed`，没有缓存命中记录。15 个通过项有实际 `check-start/check-end`，不能把未启动项的 0 秒解释为缓存通过。

通过项（秒）：luals 5.75、luacheck 1.86、toc 2.00、sim2gse-probe-luals 6.28、sim2gse-probe-luacheck 0.69、sim2gse-probe-toc 0.64、crosshair-media 3.45、myseries-luals 6.48、myseries-luacheck 0.86、myseries-toc 0.77、myseries-series 1.72、crosshairhud-luals 6.39、crosshairhud-luacheck 0.74、crosshairhud-toc 0.64、crosshairhud-tests 2.95。均带 `verify.` 前缀。

未完成：`verify.sim2gse` 41.67 秒、`verify.sim2gse-data` 41.67 秒、`verify.wowaddontest-skill` 0.44 秒。

未启动 20 项：wowaddontest-dk、sim2gse-probe-test、addon-probe-luals、addon-probe-luacheck、addon-probe-toc、addon-probe-test、assets、docs、checker-tests、annotation-build、test-inventory、gear-async、gear-build-names、gear-delete、gear-empty、gear-save-armor、gear-save-as、gear-stat-filter、gear-summary、myspec-main。均带 `verify.` 前缀。

原配置外层 `maxParallel=3`；前两项分别为 `.venv\Scripts\python.exe -m pytest -q tests/sim2gse --dist=worksteal` 与 `.venv\Scripts\python.exe -B -m pytest -q tests/sim2gse-data --dist=worksteal`，工具配置各注入 8 个 xdist worker。第三个位置依次运行上述 Lua/插件检查。所有具体命令保持在 `.build-and-verify/config.json`，本轮未改变。

两大检查仅获得 41.67 秒，故总预算中约 18.34 秒花在检查外准备和收尾；报告没有更细分的准备计时，不能进一步归因。原深路径单例独立运行 57.719696 秒，保留 220 文件、12 层长路径、同一索引与全部五阶段，其本身已超过该实际窗口。8+8 worker 并行可能增加争用，但本轮没有并行/独占的受控全套对照，不能宣称争用是根因。

## 有限诊断结果

全部使用临时合成数据、原生 `--durations` 和独立总限时包装器；没有重跑正式工具。

| 诊断 | 结果 | pytest 秒 | 外层秒 |
| --- | --- | ---: | ---: |
| 旧截断注入加实际触发断言，15 秒上限 | 如预期失败，文件仍存在 | 0.83 | 1.259 |
| 修正后的维护全组串行，20 秒上限 | 超时，仅部分完成，不算通过 | 未完成 | 20.444（含终止收尾） |
| 修正截断及相邻两个容量用例，12 秒上限 | 3 passed | 3.97 | 4.260 |
| 可复制最小运行技能用例，串行，12 秒上限 | 1 passed | 0.91 | 1.184 |
| 同一最小运行技能用例，8 worker，12 秒上限 | 1 passed | 1.90 | 2.217 |
| 维护全组，原有 8 worker，25 秒上限 | 10 passed | 11.20 | 11.512 |

最小入口的测试体分别 0.88/0.89 秒，8 worker 额外约 1.03 秒主要在体外；不外推为完整测试配置收益。维护组最慢用例：56 万条流式合成盘点 10.19 秒、增量盘点 4.02 秒、完整维护授权链 3.30 秒、大未知根 3.25 秒。并行维护组的截断用例 1.18 秒，独立相邻组三项中该用例 0.80 秒。

## 测试修正范围

远端审查发现旧注入依赖第三次 `scandir.close`，当前路径只扫描一次，导致截断场景没有发生。现在仅在测试的 `shutil.disk_usage` 操作系统边界、读取模拟 free 之前删除既有 3 MiB producer 文件；落盘 marker 记录 `before=3145728, after=0`，父测试断言文件消失及 marker 精确值，然后保留原“可用空间不足”拒绝断言。没有修改生产容量逻辑、恢复额外扫描或减少测试数。

## 按收益与风险排序的下一步

1. 深路径单例是已测量的主瓶颈。已知准备 19.97 秒、归档批准执行 10.11 秒，五阶段合计约 37.36 秒；后续优先定位重复路径/身份/盘点调用的成本，但任何合并必须保留并验证每个锁和竞态边界。不得改 220 文件、五阶段、同根累积历史或元数据拒绝断言。需先形成具体安全等价设计供父端评估。
2. 检查前约 18.34 秒直接挤占预算；本轮仅报告事实。共享验证工具和跨工作区模式调查由父端负责，本仓不改工具、不调用 doctor、不改缓存。
3. 批量登记可减少每文件两次 CLI 启动，但当前最慢深路径准备已批量登记 220 文件；已有小型多文件夹具可逐项检查是否适合批量接口，收益上限先按实际调用数估算，涉及注册语义/覆盖改变须先评估。
4. 不采用简单 worker 数量下降或取消追踪：独立最小用例只能证明约 1 秒启动成本，尚无整套收益证据。56 万流式夹具在 tracemalloc 下逐条创建对象；复用同一对象会削弱“错误全树物化超过内存上限”检测，不能当作等价优化。

原 121 项核心测试和原五阶段保持，正式整套仍失败。没有生产启用、真实历史操作或计划任务安装。
