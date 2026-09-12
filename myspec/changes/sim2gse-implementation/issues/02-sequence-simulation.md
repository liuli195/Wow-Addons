# 同一导出序列的原生模拟

Status（状态）: open
Triage（分拣）: ready-for-agent
Assignee（领取者）: unassigned

## Parent

[开发需求](../spec.md)

## What to build

将第一票生成并编译的同一序列经任务入口送入独立受控引擎，返回真实伤害、动作轨迹与编译一致性结果。沿用原生战斗机制，明确哪些结果是离线模型而非游戏证据。

## Blocked by

[真实角色到最小导出](01-character-and-export.md)

## Acceptance criteria

- [ ] 从同一任务入口评估导出候选，实际消费的动作块、块内顺序和起始规则与导出编译结果相等，差异明确失败。
- [ ] 单技能、不可用中间步骤、公共冷却连按、队列覆盖和同块动作均有原生执行轨迹，不能由自主选招补放。
- [ ] 单主动与双主动物品遵守原生共享限制；不同顺序分别验证，测试装备只用独立样例，不修改用户角色。
- [ ] 关闭控制器时与固定同版本原版回归一致；宠物、替换技能与被动效果保留原生来源。
- [ ] 施法／引导等未支持方式明确拒绝，不能绕过限制或静默跳过；误传原版引擎说明不兼容。
- [ ] 重复战斗的重置、起始相位和固定采样可复现，不复用上次战斗残留状态；用户实际安装继续后置。

## Testing Decisions

最高入口沿用第一票，输入实际产物并读取本次原生结果；覆盖 T04—T13、T15—T17、T21。参考[执行原型证据与交接矩阵](../../../../docs/sim2gse/execution-prototype.md)，把正式序列转换与原型自定义索引串区分开。主要成功与拒绝检查从任务入口运行，底层事件断言作补充。

## Specification coverage

`Sim2GSE evaluates the exported action order`、`Sim2GSE retains native combat behavior`；重置、输入与身份变更场景的执行基础。本票不重写上游被动机制，不增加完整搜索。

## Completion evidence

待记录导出与受测产物身份、实际轨迹、原版回归及错误样例；当前未实施，实机仍待第五票。
