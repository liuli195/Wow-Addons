# 实施第三阶段逐级淘汰与正式服语义校准

Label（标签）: wayfinder:task
Triage（分拣）: needs-info
Status（状态）: open
Assignee（领取者）: unassigned
Mode（方式）: HITL（按 dev-flow 开发门禁实施）
Parent（所属地图）: [Sim2GSE 搜索器长期优化地图](../spec.md)
Blocked by（前置事项）: [第三阶段：确定逐级淘汰与正式服语义校准](04-successive-halving-parity.md)

## Question（问题）

按第三阶段已确认的逐级淘汰预算和正式服语义校准规则完成开发及 A/B 后，是否同时通过效率与语义两个独立门禁？

## 关闭条件

- dev-flow 的实施、测试、独立审查和统一验证完成。
- SimC 总计算量／时间、最终 DPS 和误淘汰率达到第三阶段门槛。
- 正式服语义校准独立通过；失败时不得用搜索 DPS 掩盖。
- 达到停止条件后冻结第三阶段；未达标则停在本票并保存证据。

## Comments（讨论）

等待第三阶段决策票关闭后进入，禁止提前实现。
