# 实施验证记录

## 票01：成功摘要

新工作区：`C:/Users/liuli/.codex/worktrees/sim2gse-reference-guided-breeding/Wow Addons`；分支`codex/sim2gse-reference-guided-breeding`；固定基线`f8b8c120a0ef9244876191937cf480270f22c561`。主工作区仍main，只有用户原有未跟踪需求目录，未改其文件。

### 先失败后通过

- 真实run_task入口接受坏时长、缺摘要的失败检查，修复后拒绝，正确摘要通过；随后发现坏相邻分母和位置次数未拒绝，补检查红→绿。训练ensure_prepared公开入口同样拒绝缺摘要且不保存准备结果。
- 首次旧引擎缺少成功摘要，原生验证明确失败；实现后单请求1有效场，多请求4排暖场后3有效场。
- 初次真实摘要误含派生necrotic_coil，原始报告完整保留并标不接受；限定APL真实按钮与基础归并后排除该项，festering_strike与festering_scythe合计49次，吻合原伤害统计的25+24。
- 位置采用原引擎0起点，最初校验误拒绝0，修正后从原始报告重读，不追加模拟或伪造输出。

### 原生预算和原始证据

整个变更额外原生口径验证已用12调用、45请求、累计3.967秒；上限12调用/每批4请求/45秒未扩大。账本位于`.local/sim2gse/acceptance/reference-guided-breeding/native-budget.json`，构建另计，失败计入额度。

| 证据目录 | 结果及限制 |
|---|---|
| reference-corrected | 基础按钮85948=49，派生1242174排除；3有效场、540000毫秒 |
| reference-single-request | 请求1仍1有效场、180000毫秒 |
| controlled-normal、controlled-diagnostics-off | 同种子伤害和全部业务计数完全一致；日志关闭不影响统计。后续只补特殊按钮与范围回报 |
| reference-explicit-exclude、reference-utility-and-frozen-scope | 实际参考自由选招；显式排除三种爆发按钮，未套候选窗口；scope保存原目录与排除集合，自动攻击每场仅一次 |
| controlled-window-no-precombat | 三有效场普通成功6次，窗口前后不连接；最初读取因位置0校验失败，修复后验证原始报告 |
| controlled-zero-success | 三有效场、真实成功空、时长540000；原有trace=True入口因无执行轨迹拒绝，原生摘要本身通过格式核验；生产粗评trace=False不受此保护影响，不冒称此trace入口成功 |
| controlled-queued-cross-window | 三有效场3次排队、9次普通执行；第二原输入在爆发窗口内延迟成功，仍归普通源；成功9次不重复、源位置0=9、相邻对为空；爆发无成功。最后一次原生调用通过 |

初始短输入样例被战前步骤/公共冷却吃掉，trace入口拒绝；此失败已记账，调整为无战前、战斗2000毫秒后的输入验证。不清理失败证据。上述是本地模拟与统计口径证据，不证明游戏验收或伤害提升。

### 回归与审查

- 统一构建最后通过：原版、参考版、受控版及素材检查均实际执行。
- 逻辑回归511项、172子项通过；新增训练准备入口断言6项文件单跑通过。保留现有导入元数据弃用提示，非此次改动。
- 正式固定基线差异验证及独立双维审查：待提交后执行，未提前记通过。
