# Sim2GSE /castsequence 搜索、模拟与评分

## Problem Statement

Sim2GSE 当前自动搜索已经能生成普通动作、Sequential Loop（顺序循环）和 WaitClicks（等待点击）候选，也能导入并有限解释普通 WoW 宏，但还不能把 `/castsequence` 作为搜索语法生成、忠实模拟并参与 DPS（每秒伤害）评分。若把 `/castsequence` 静态展开为固定动作列表，会错误处理失败、中断和等待确认：真实客户端只有当前成员成功施法后才推进，失败或中断后仍停留在原成员。

## Solution

保持现有三层职责不变：搜索层只生成和变异结构化 `/castsequence` 候选；宏命令解释层负责解析序列成员和 Reset（重置）规则；Program（统一程序）与按键控制层把解析后的有状态命令交给 Native SimC（原生战斗模拟器）运行。原生控制器在每场模拟中维护当前成员、pending（等待施法结果）和重置状态，并复用现有施法队列与成功/失败反馈。最终候选继续走现有搜索评分、预算、复测和选择流程，并导出真正的 `/castsequence` 宏。

本期支持 `/castsequence` 序列本体和 Reset（重置）语义；暂不新增 Macro conditions（宏条件）解释能力。带宏条件的 `/castsequence` 必须在模拟前明确拒绝，不能静默忽略条件。

## User Stories

1. 作为 Sim2GSE 用户，我希望自动搜索能生成包含 `/castsequence` 的候选，以便比较这种宏结构是否能提高最终 DPS。
2. 作为 Sim2GSE 用户，我希望 `/castsequence A,B,C` 只有当前成员真正成功后才推进，以免失败技能被错误跳过。
3. 作为 Sim2GSE 用户，我希望技能失败、中断、资源不足、冷却未好或公共冷却阻挡时序列位置保持不变。
4. 作为 Sim2GSE 用户，我希望序列存在 pending 时重复点击不会提前提交下一成员。
5. 作为 Sim2GSE 用户，我希望最后一个成员成功后序列回到第一个成员。
6. 作为 Sim2GSE 用户，我希望 `reset=N` 按真实超时规则重置，并且每次使用序列都会重新开始计时。
7. 作为 Sim2GSE 用户，我希望 `reset=target`、`reset=combat`、`reset=shift`、`reset=ctrl`、`reset=alt` 及其与一个数字超时的合法组合被准确表示和运行。
8. 作为 Sim2GSE 用户，我希望玩家死亡时施法序列按客户端规则重置。
9. 作为 Sim2GSE 用户，我希望不同成员顺序和不同 Reset 规则形成不同候选身份与缓存身份。
10. 作为 Sim2GSE 用户，我希望导出的 GSE 序列仍包含真正的 `/castsequence` 文本，而不是 Sim2GSE 私有语法。
11. 作为 Sim2GSE 用户，我希望最终选中的 `/castsequence` 候选确实经过真实 Native SimC 评价，而不是仅靠静态估算。
12. 作为开发者，我希望搜索层不承担宏解释逻辑，保持现有搜索 → Program/按键控制 → 宏解释/原生执行的职责分层。
13. 作为开发者，我希望普通动作、Loop 和 WaitClicks 的现有导出、模拟和评分行为不受影响。
14. 作为开发者，我希望带未知或未支持宏条件的 `/castsequence` 在进入 Native SimC 前明确失败并给出来源位置。
15. 作为结果使用者，我希望本机模拟结果和 WoW 正式服验收继续分别报告，避免把离线模拟称为实机验证。

## Implementation Decisions

- 保持三层职责：搜索层生成候选；宏命令解释层解析 `/castsequence` 序列成员和 Reset；Program/按键控制与 Native SimC 负责运行时状态。
- `/castsequence` 作为 Action（动作）中的有状态宏命令表达，不新增平行于 Loop/Pause 的 GSE 顶层控制类型。
- 宏解释层输出结构化序列定义，包括成员、Reset 规则和来源；不在解释层保存运行时索引、pending 或时间状态。
- Native SimC 为每场模拟维护序列状态。推进依据必须对应真实成功事实；失败、中断和不可执行均不推进。
- 外层 GSE 点击步进与 `/castsequence` 内层成功步进相互独立。
- Reset 支持无重置、单一数字超时、target/combat/shift/ctrl/alt，以及这些事件标志与一个数字超时的合法组合；死亡重置作为运行规则处理。
- 数字 Reset 使用“距上次使用超过 N 秒重置”的语义，并在每次使用时刷新计时。
- Macro conditions（宏条件）不在本期扩展；任何条件前缀或多条件分支如果不能由现有宏解释能力确定，必须拒绝模拟。
- 自动搜索优先生成 2 至 4 个当前角色可忠实模拟的技能成员。Reset 候选身份使用结构化规则；在没有相应目标/战斗/修饰键事件的默认搜索场景中，不应制造行为完全等价的事件型 Reset 变体。
- 不修改现有搜索评分算法、统计方法、预算、复测方法或预训练行为。
- 候选键、任务恢复和批次缓存必须纳入完整 `/castsequence` 定义，避免不同 Reset 或成员序列复用错误成绩。
- GSE 导出继续通过现有锁定上游编译路径核对；普通动作、Loop、WaitClicks 保持原有路径。

## Testing Decisions

- 最高层公开测试接缝使用现有 `POST /api/tasks`：让搜索实际产生 `/castsequence` 候选，经 GSE 编译、真实 Native SimC 运行、DPS 评分、候选选择并导出最终序列。
- 红灯到绿灯测试必须首先证明端到端闭环，而不是只测试宏解析函数。
- 轨迹测试覆盖成功推进、失败保持、中断保持、pending 阻塞、末项回环、数字超时重置和可注入的 Reset 事件。
- 明确测试未支持宏条件会在原生评价前失败，且不能删除条件后继续模拟。
- 回归测试核对普通动作、Sequential Loop 和 WaitClicks 的候选身份、编译计划和评分行为不变。
- 超限或不能忠实编译的候选继续在 Native SimC 评价前拒绝。
- 正式验证使用仓库 Build and Verify（构建与验证）固定基线流程；WoW 正式服 GSE + Sim2GSEProbe + 战斗日志验收单独记录。

## Out of Scope

- 不实现完整 WoW Macro conditions（宏条件）系统，也不新增 `[@target]`、`[harm]`、`[mod:shift]` 等条件求值能力。
- 不支持多条件 `;` 分支、嵌套 `/castsequence`、`null` 门闩语义或物品序列，除非它们已经能由现有宏解释能力忠实处理且不扩大本期范围。
- 不修改搜索评分算法、搜索预算、预训练或其他 GSE 高级控制语法。
- 不把本机 SimC 验证等同于 WoW 正式服实机验证。

## Further Notes

- 固定开发基线：`dd00b24a2f0eac590b82d105c55f023574f6caeb`。
- 推荐功能分支：`codex/sim2gse-castsequence-search`。
- 当前工作树：`D:\My Project\Wow Addons`。
- 流程等级：Full（完整），原因是该变更跨搜索、宏解释、按键控制和 Native SimC 运行状态，并改变可评价候选语义。
