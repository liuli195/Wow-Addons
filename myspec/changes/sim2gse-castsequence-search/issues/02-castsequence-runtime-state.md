# 02: 忠实执行成功推进与 pending 状态

**What to build:** 让 `/castsequence` 在真实 Native SimC 中按 WoW 规则运行：只有当前成员成功才推进，失败或中断保持原位，等待结果时重复点击不提前执行下一成员。

**Blocked by:** 01 /castsequence 最小搜索到评分闭环

**Status:** completed

- [x] 成功施法推进到下一成员，最后一项成功后回到第一项。
- [x] 失败、中断、资源不足、冷却未好、公共冷却阻挡均不推进。
- [x] pending 期间重复点击不重复提交当前成员，也不提前提交下一成员。
- [x] 原生轨迹能够关联输入、序列身份、成员位置、实际动作和推进结果。
- [x] 搜索评分使用上述真实运行结果，而不是静态 `A/B/A/B` 展开结果。
- [x] 相关失败反馈、施法队列和 Loop/WaitClicks 现有行为保持回归通过。

## Comments

- Red：真实受控引擎在第二成员排队后收到重复点击，产生 `replace` 并替换待执行请求；`test_castsequence_repeated_clicks_do_not_replace_pending_member` 失败。
- Green：为序列块记录待执行输入，成功、失败、回滚或中断时清理；重复点击只记录等待。该检查转绿，失败保持原位与末项成功回绕检查也通过。
- 原生轨迹新增 `sequence_step` 与 `sequence_member`，Python（脚本语言）层核对成员与动作一致；排队失败包括原生目标失效、排队前条件失效、施法执行条件失效。
- 兼容锁的补丁与三份受控源码散列吻合，baseline（基准）和 controlled（受控）重建均 `exit=0`；Sim2GSE 全量回归 `230 passed, 83 subtests passed`。WoW 正式服验收仍为 `not_run`。
