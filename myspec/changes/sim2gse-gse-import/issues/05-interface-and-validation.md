# 05：完成页面导入和验收

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: in-progress

## What to build

本机页面允许粘贴角色资料和第三方 GSE 字符串、选择集合成员及版本、发起模拟并查看可模拟性或 DPS 结果；验证完整任务及搜索回归。

## Blocked by

04：原生导入模拟已实现；真实 DK DPS 验收样本仍缺。

## Acceptance criteria

- [x] 页面与 API（应用程序接口）支持检查、选择、发起、取消和查看导入模拟任务。
- [x] 成功、无效编码、合法但不支持、可解析但不可模拟均有清楚的页面与任务状态。
- [ ] 真实样本与边界回归、统一构建验证和独立审查通过。
- [x] 列出游戏内验收操作和尚未取得的实机证据，不把本机验证当游戏验证。

## Completion evidence

页面和 HTTP 服务测试覆盖字符串检查、成员/版本选择、异步启动、取消、任务查询、成功 DPS 响应以及编译前拒绝。导入成功用例另验证 `/targetenemy [noharm][dead]` 在默认有效敌方目标场景被严格当作无效果行，并继续执行 `cast`。本地 Sim2GSE 全量测试通过：145 passed、52 个子检查，116.52 秒。

本票其余门禁尚未完成：真实样本导入 DPS 仍被 04 阻塞；统一 Build and Verify 与独立审查待本阶段最后执行。游戏内操作和证据限制记录在 `docs/sim2gse/game-test-feedback.md`：启用 `/gse debug` 并导出原始追踪，同时启用 `/combatlog` 保存战斗日志，记录目标、按键间隔和战斗条件。目前尚未取得本次真实序列的游戏导入、追踪与战斗日志，也没有完成游戏内验收；本机模拟不等同于实机验证。
