# 01：装备浏览器最短真实配装闭环

**What to build:** 减少没有对应断言的旁路和重复重算，保留导入、真实计算和宝石差值、保存/另存、刷新加载、方案比较、实际下载和重导入。

**Blocked by:** None（技术独立，可在完整Gate1确认后与另外两票并行；共享Git和最终验证由root串行）

**Status:** ready-for-agent

**Execution:** in progress — 完整Gate1已获用户Sentinel_0ac161c3fe8c8191b697b37d3c04d7ee明确确认；root已将实现提交于18ea771，正在独立审查，尚未Windows真实/全仓验收。

## 实施边界与所有权

- 仅由该票实施者编辑 tests/gear-planner/check-browser.cjs、tests/gear-planner/README.md。
- “10→5”指浏览器主计算调用次数约10次收敛到约5次，不是生产SimC迭代参数；生产固定iterations=1不动。
- 测试侧明确abort /api/original-matches、/api/effects；不伪造成功响应，不拦截核心bootstrap/import/calculate，不关闭真实SimC。
- 保留5条主计算的确切位置由实施差异与实际运行核对，不能为了数字删除宝石差值或下载重导的有效性断言。

## Acceptance criteria

- [ ] 主要完整配装闭环保留，计算结果不是fixture预设；样本差值和实际下载/重导断言通过。
- [x] 文档明确不再执行原装备匹配/特效取得及物理缓存的真实组合链，不能称普通规则全部替代该风险。
- [ ] 不改产品、引擎、并发或服务锁；本票固定差异与独立审查通过。
- [ ] 由root统一Windows真实入口及最终全仓验收，记录该组实际耗时。

## Comments

既有技术精简方案已经用户批准；完整Gate1已明确确认同树新分支、并行子代理、最后独审和本轮取舍。三个票据无产品或文件依赖；不得各自提交、推送或运行Windows重验证。必要普通定向检查云端完成，测试资源冲突时排队。

开发收据（2026-10-25）：`.local/verification-top-five/gear/summary.json`、stdout/stderr及8份审计JSONL。现有2.7.1源审计适配器运行8段Node普通检查，退出0、8 start/finish完整、零违规、evidence_error=null，wall0.939秒。环境为云端Node v24.22.1，不能冒充Windows冻结Node或真实Edge/SimC烟测；浏览器5次主计算和实际下载/重导仍待root正式验证。此次不是官方CLI完整通过。
