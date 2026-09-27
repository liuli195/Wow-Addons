# 03: Reset 完整语义与最终验收

**What to build:** 在同一 `/castsequence` 搜索、模拟和评分路径上支持 Reset（重置）规则，并完成最高层真实入口验证与正式服验收边界记录。

**Blocked by:** 02 忠实执行成功推进与 pending 状态

**Status:** in-progress

- [x] 支持无 Reset、`reset=N`、target、combat、shift、ctrl、alt，以及事件标志与一个数字超时的合法组合。
- [x] 数字 Reset 按距上次使用超时重置，并在每次使用时刷新计时；死亡重置按客户端规则执行。
- [x] 可注入对应事件的测试证明 target/combat/modifier Reset 会回到第一成员。
- [x] 默认搜索场景不为不可观察事件生成行为等价候选；不同实际可观察 Reset 规则保持不同候选和缓存身份。
- [x] `POST /api/tasks` 最终冒烟覆盖搜索生成、GSE 编译、真实 Native SimC、DPS 评分、候选选择与导出。
- [x] 带未支持 Macro conditions（宏条件）的 `/castsequence` 明确拒绝，不静默降级。
- [ ] Build and Verify 固定基线验证通过；WoW 正式服验收状态单独记录，不用离线结果替代。

## Comments

- 2026-09-28：数字超时与事件重置测试先红后绿；目标变化、脱战、Shift/Ctrl/Alt 点击、死亡及组合规则均由受控引擎验证。连续使用刷新超时，默认搜索仅生成数字规则；显式事件场景才搜索对应标志。
- 2026-09-28：`POST /api/tasks` 通过真实 Native SimC 评价 `reset=2/target` 候选并选择、导出 GSE 宏；独立完整 Sim2GSE 测试为 `237 passed, 90 subtests passed`。029 补丁从固定源码应用后逐文件散列与受控源码一致，baseline/controlled 构建退出码均为 0。正式服验收 `not_run`；独立审查与正式 Build and Verify 待完成。
