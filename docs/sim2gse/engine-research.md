# 引擎复用基础与输入控制入口研究

核查日期：2026-09-12。对应[核实引擎可复用基础及按键控制入口](../../myspec/changes/sim2gse-wayfinder/issues/02-engine-evidence.md)。本轮在用户要求完成下一项后，按地图顺序复核此前的背景研究；只读源码和现有资料，没有构建、运行模拟或改变现有程序。

## 可复用的研究起点

| 证据 | 当前核对结果 |
| --- | --- |
| 官方原生程序 | 本地 `.tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe`，大小 121016832 字节，SHA-256（文件散列）为 `f1281cdc7224d9d08e23cca1c090fa1b144b8b22491ffd8459ccefb8d8120987`；主代理重新计算一致。 |
| 程序来源 | 对应提交 `c1935b92f40d1063696861b0f4f6701e714ebd09`；上游发布任务和本仓库既有记录可追溯。[官方发布任务](https://github.com/simulationcraft/simc-publish/actions/runs/34184702422)、[现有来源记录](../gear-planner/deathknight-raidbots-validation.md) |
| 本地源码 | `.tools/gear-planner-dk-reference/simulationcraft-simc-b845947` 为归档展开目录，来源提交是 `b845947a34429874433d8e9362326894650dd20a`，不是有版本库元数据的正式补丁工作树。本轮受检的 7 个源码／许可文件与现有固定归档逐字节一致。 |
| 两份版本关系 | 前轮上游核对与既有记录显示，两提交的 `engine/`（引擎目录）树对象相同，为 `a0f97e0abef4805028dbe849a3adca198fc05052`。可以用本地源码定位引擎入口；完整输入与构建仍须锁定同一提交，不能把两个版本整体混为一体。[上游差异](https://github.com/simulationcraft/simc/compare/b845947a34429874433d8e9362326894650dd20a...c1935b92f40d1063696861b0f4f6701e714ebd09) |

本轮复核记录在 `.local/sim2gse/engine-evidence-review.json`，包含程序、归档与受检文件散列。现有归档 `.local/gear-planner-dk-validation/b845947-source.zip` 的 SHA-256（文件散列）为 `412fe6f536e181ef73fd4fcf6d27dbcd2e17d873511c545a1cea1138c44e8110`；受检文件为 `player.cpp`、`player.hpp`、`action.cpp`、`sequence.cpp`、`sim.cpp`、`report_json.cpp` 和许可文件。本轮上游比较页面未能重新取回，版本关系沿用前轮固定提交证据，不冒充新取得的远端确认。

现有 [装备规划器服务](../../projects/gear-planner/server.py)第 22 行仍引用上述官方程序；[研究探测脚本](../../scripts/dev/gear-planner-research/probe-simc.py)也在复用它，因此后续项目补丁不能直接覆盖此程序。

既有脚本已使用该原生程序，但其中有把角色动作替换成属性快照和等待的研究输入。因此这些成功记录不证明正常战斗基线或本项目执行模型成立。[原有探测入口](../../scripts/dev/gear-planner-research/probe-simc.py)、[原有验证边界](../gear-planner/deathknight-raidbots-validation.md)

## 已定位的调用链

以下链接固定到程序对应的上游提交；名称是阅读入口，不是已批准的补丁设计。

| 关注点 | 入口及其对规划的意义 |
| --- | --- |
| 前台动作 | `player_ready_event_t`（角色就绪事件，312 行）调用 `execute_action`（执行动作，7354 行），依次优先处理严格序列、已预选动作，最后才经 `select_action`（选择动作，14175 行）扫描列表。不能只改默认列表调用，更不能把一次优先级决策当成一次用户输入。[角色源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/player.cpp#L7354) |
| 额外扫描 | `player_gcd_event_t`（公共冷却期间的额外动作事件，241 行）与 `player_cwc_event_t`（施法中动作事件，282 行）分别扫描专用列表；调度入口在 6790、6839 行。共同事件逻辑在 205—224 行还能取消另一项已排队动作并换成新动作，所以也必须审计共享排队状态。[额外事件源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/player.cpp#L205) |
| 队列和执行 | `queue_execute`（排队执行，2161 行）及其事件处理冷却队列延迟；`schedule_execute`（安排执行）中的法术预选事件在 2277—2293 行另行扫描前台列表，并交给前台就绪事件消费。这与 `strict_gcd_queue`（严格公共冷却队列延迟模型）是不同机制，不应合成同一个“队列窗口”。[动作源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/action/action.cpp#L2277) |
| 物品动作 | `use_item_t`（单件物品动作，9847 行）绑定单件物品的原生使用效果及冷却；`use_items_t`（物品扫描动作，10216 行）在初始化时生成主动效果代理，运行时从代理列表执行首个就绪项。须避免后者隐藏补放；没有物品同名统计不能单独证明效果未执行。[物品动作源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/player/player.cpp#L10216) |
| 报告 | 原生 JSON（结构化报告）已有动作时间、资源／增益快照及 `queue_failed`（队列失败，491 行）。该标记覆盖前台排队动作到期后就绪检查失败，未覆盖所有替换、取消和预选丢弃。后续优先复用，再补逐次输入、拒绝原因和队列覆盖统计；样例动作记录不等于完整输入轨迹。[报告源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/report/json/report_json.cpp#L474) |
| 原生序列 | 普通序列默认向后跳过不可用动作，可改为等待；严格序列提交后跨多个角色就绪事件保持优先权，每次排队一个子动作，默认遇到不可用动作时终止，可选跳过。两者均不是逐次按键推进，不能直接用作 GSE（按键序列插件）模型。[原生序列源码](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/engine/action/sequence.cpp#L145) |

就绪检查也有层次：`action_ready`（完整动作条件，`action.cpp:2567`）还包含目标选择、动作列表条件、同步和行冷却等；`ready`（基础就绪，2631 行）主要检查冷却、资源、移动和部分施法限制。前台排队事件到期时只重查基础与目标就绪，不重新评估完整动作列表条件。后续输入控制须保留物理限制，并明确移除哪些策略条件；本票只定位这一区别，不在此确定补丁实现。

## 给原型的最小建议

推断：优先在目标角色的主动选择来源隔离输入控制，复用原生职业、资源、物品效果和战斗结算。先核对所有选择入口及回调，使用满足原型的最小改动；目前没有证据要求预建接口类、适配器层或通用插件架构。

必须留到原型检验的问题：同块饰品与技能的事件先后、失败输入推进、技能队列预选与覆盖、原生就绪检查中哪些属于物理条件而非优先级条件、隐式物品扫描关闭后的校验行为、被动触发保留，以及目标物品效果是否完整。用户已确定邪恶死亡骑士、单目标与 300 毫秒名义输入间隔；真实按键、队列和重置配置按其要求留到有候选结果后的导入验证阶段。

计划书的 `sim2gse_info`（项目诊断参数）、`sim2gse_input`（项目输入参数）、`sim2gse_metrics`（项目统计参数）仍是拟新增接口；本轮核对原生参数注册源码，没有这些名称，不将它们当成原版功能。

## 隔离、回归与交接

补丁应使用独立源码与程序路径；现有装备规划器程序保留。关闭控制器后，与相同完整源码、编译条件、输入、种子及线程的原版对比，重点覆盖前台、非公共冷却、物品和队列；输出比较排除耗时等非确定字段。具体形式由[确认项目目录与上游补丁维护边界](../../myspec/changes/sim2gse-wayfinder/issues/04-project-boundary.md)及[验证输入控制与饰品的最小执行模型](../../myspec/changes/sim2gse-wayfinder/issues/08-execution-prototype.md)决定。

上游主许可为 GPL-3.0（GNU 通用公共许可证第 3 版），另有第三方许可材料。后续按实际运行包组成核对源码提供、修改说明与随附材料；本研究不作最终分发判定。[上游许可](https://github.com/simulationcraft/simc/blob/c1935b92f40d1063696861b0f4f6701e714ebd09/LICENSE)

研究结论只证明有可复用且可定位的基础。目标角色原生基线、动作与饰品能力清单、实际游戏对照和补丁回归均未由本轮执行。
