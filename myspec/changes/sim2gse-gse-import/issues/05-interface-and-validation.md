# 05：完成页面导入和验收

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: in-progress

## What to build

本机页面允许粘贴角色资料和第三方 GSE 字符串、选择集合成员及版本、发起模拟并查看可模拟性或 DPS 结果；验证完整任务及搜索回归。

## Blocked by

04：原生导入模拟及两条真实 12.1 邪 DK 串的受控 DPS 验收已完成。本轮独立复审提出的动作查询生命周期、名称形式查询、随机循环来源对齐及不支持成员按钮门控均已修复，统一固定基线验证已通过；复审复查与游戏内验收仍待完成。

## Acceptance criteria

- [x] 页面与 API（应用程序接口）支持检查、选择、发起、取消和查看导入模拟任务。
- [x] 成功、无效编码、合法但不支持、可解析但不可模拟均有清楚的页面与任务状态。
- [ ] 真实样本与边界回归、统一构建验证和独立审查通过。
- [x] 列出游戏内验收操作和尚未取得的实机证据，不把本机验证当游戏验证。

## Completion evidence

页面和 HTTP 服务测试覆盖字符串检查、成员/版本选择、异步启动、取消、任务查询、成功 DPS 响应以及编译前拒绝。不支持成员会显示原因并禁用模拟按钮。导入成功用例另验证 `/targetenemy [noharm][dead]` 在默认有效敌方目标场景被严格当作无效果行，并继续执行 `cast`。固定上游多随机种子测试核对 Random Loop 的真实展开顺序及 Repeat 来源身份；同路径来源以序列、版本、路径三项联合识别。名称形式 `Epidemic` 经角色原生动作工厂的单独查询成功解析；法师 Mirror Image 查询确认动作初始化和宠物创建顺序正确。无动作查询时主 reference 报告仍与原基线逐字段相同。

固定兼容锁下的 baseline、controlled、tc 原生引擎本地构建均 exit=0。完整 Sim2GSE 测试通过：164 passed、62 个子检查、94.05 秒。固定基线 `fa2ea1360858942a8bc3d065fbad81c5a9cef417` 的搜索 golden 回归比较旧版与当前版结果，候选键、GSE SHA/文本及 10 个编译点击一致；它是测试用角色和小预算回归，不作为真实样本或 DPS 验收。统一 Build and Verify 已通过，9 项检查全部 checked，其中 Sim2GSE 为 164 passed、62 个子检查。独立复审复查仍待完成，因此第三项保持未完成。

两条真实串的来源、完整摘要、成员版本、模拟场景、逐点击来源及受控 DPS 与角色基准 DPS 的区别记录在 `docs/sim2gse/gse-import-corpus.md`。任务报告中的 `game_validation=not_run`。游戏内操作和证据限制记录在 `docs/sim2gse/game-test-feedback.md`：启用 `/gse debug` 并导出原始追踪，同时启用 `/combatlog` 保存战斗日志，记录目标、按键间隔和战斗条件。目前尚未取得真实序列的游戏内导入、追踪与战斗日志，也没有完成游戏内验收；本机模拟不等同于实机验证。
