# 本机构建与完整验证计时

机器：Intel Core i5-13600KF，14 核 / 20 逻辑处理器。目标是已准备两份引擎的日常构建加完整验证，同一台机器连续执行，不包含清空产物后的冷构建。固定 Git（版本管理）基线：`55e133f7a2773260c539ed1e9e3d27a5105a3fe3`。

统一入口：先执行 `build-and-verify build --project .`，成功后执行 `build-and-verify verify --project . --full --performance-report`；分别用单调时钟计时，并相加判断 60 秒目标。原始输出与逐轮摘要保存在 `.local/verification-performance/`。

| 轮次 | 构建 | 完整验证 | 合计 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 修改前 | 18.46 秒 | 59.73 秒 | 78.19 秒 | 两段通过，超出总目标 |
| 修改后 1 | 13.42 秒 | 36.33 秒 | 49.75 秒 | 两段通过 |
| 修改后 2 | 13.53 秒 | 37.17 秒 | 50.71 秒 | 两段通过 |
| 修改后 3 | 13.25 秒 | 37.61 秒 | 50.85 秒 | 两段通过 |

每轮均执行两项构建检查与 37 项验证检查，Sim2GSE 自动收集的结果均为 **226 passed、83 subtests passed**；无新增跳过。修改后最慢一轮合计 50.85 秒，低于目标 9.15 秒。调整仅涉及将 `verify.sim2gse` 提到检查队列首位，以及把 `verify.maxParallel` 从 2 调至 3；检查命令、测试内容、工作进程数与构建身份校验保持原样。

`.build-and-verify/runs/performance-report.json` 只计验证段，不能单独证明合计目标；此表的合计来自每轮构建与验证的连续计时。原始摘要分别为 `.local/verification-performance/{baseline,trial1,trial2,trial3}-summary.json`，构建和验证输出为对应的 `-build.log` 与 `-verify.log`。
