# 05：完成页面导入和验收

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: in-progress

## What to build

本机页面允许粘贴角色资料和第三方 GSE 字符串、选择集合成员及版本、发起模拟并查看可模拟性或 DPS 结果；验证完整任务及搜索回归。

## Blocked by

04：Karen ST 原始第三方邪 DK 串已通过受控原生 DPS 模拟。Søl 两条 12.1 原串此前的 DPS 数值因错误跳过条件成立的 `/petattack` 而无效；当前在源位置拒绝。动作查询生命周期、名称形式查询、随机循环来源对齐、不支持成员按钮门控及宠物命令拒绝均已有实现与回归测试。固定基线的 Build and Verify（构建与验证）已通过 9 项检查；独立复审复查和游戏内验收仍待完成。

## Acceptance criteria

- [x] 页面与 API（应用程序接口）支持检查、选择、发起、取消和查看导入模拟任务。
- [x] 成功、无效编码、合法但不支持、可解析但不可模拟均有清楚的页面与任务状态。
- [ ] 真实样本与边界回归、统一构建验证和独立审查通过。
- [x] 列出游戏内验收操作和尚未取得的实机证据，不把本机验证当游戏验证。

## Completion evidence

页面和 HTTP 服务测试覆盖字符串检查、成员/版本选择、异步启动、取消、任务查询、成功 DPS 响应以及编译前拒绝。不支持成员会显示原因并禁用模拟按钮。导入用例验证 `/targetenemy [noharm][dead]` 在默认有效敌方目标场景为空效果；宠物就绪且条件成立的 `/petattack`、`/petassist` 会按宏行位置拒绝，条件不成立时才跳过。固定上游多随机种子测试核对 Random Loop 展开顺序及 Repeat 来源身份；同路径来源以序列、版本、路径三项联合识别。角色原生查询严格解析 `Epidemic` 和 `Festering Strike` 名称形式；法师 Mirror Image 查询确认动作初始化和宠物创建顺序正确。无动作查询时主 reference 报告仍与原基线逐字段相同。

固定兼容锁下的 baseline、controlled、tc 原生引擎本地构建均 exit=0。当前完整 Sim2GSE 测试通过：169 passed、73 个子检查、119.97 秒。固定基线 `fa2ea1360858942a8bc3d065fbad81c5a9cef417` 的搜索 golden 回归比较旧版与当前版结果，候选键、GSE SHA/文本及 10 个编译点击一致；它是测试用角色和小预算回归，不作为真实样本或 DPS 验收。对代码提交 `4a3e528a56847635a2c9e993831a15bbb933e291` 的统一 Build and Verify（构建与验证）已通过，9 项检查全部通过；Sim2GSE 为 169 passed、73 个子检查。独立复审复查仍待完成，因此第三项保持未完成。

Karen ST 原串的来源、SHA-256、成员版本、22 次点击与来源路径、场景、受控 DPS 和独立角色参考 DPS 记录在 `docs/sim2gse/gse-import-corpus.md`。该任务报告为 `game_validation=not_run`。Søl 两条真实 12.1 串现明确拒绝；先前输出的 37842.240154123254 和 41627.01167663097 是错误跳过宠物命令的无效历史结果，不作为验收。游戏内操作和证据限制记录在 `docs/sim2gse/game-test-feedback.md`：启用 `/gse debug` 并导出原始追踪，同时启用 `/combatlog` 保存战斗日志，记录目标、按键间隔和战斗条件。目前尚未取得真实序列的游戏内导入、追踪与战斗日志，也没有完成游戏内验收；本机模拟不等同于实机验证。
