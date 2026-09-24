# 04：把可模拟的导入序列送入原生 DPS 模拟

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

用户选定导入序列和版本后，当前角色可按动作得到严格映射，逐次按键计划驱动原生受控引擎；不可映射动作在模拟前被拒绝。

## Blocked by

03：按上游语义编译全部 GSE 控制块。已完成。

## Acceptance criteria

- [x] 可模拟的邪恶死亡骑士样本从真实导入字符串获得 DPS 报告、逐次输入轨迹与条件摘要。
- [x] 空点击占用输入，动作块、来源路径和原生回报保持一致。
- [x] 未知技能、物品、条件、宏命令或环境依赖不进入伤害模拟且有具体诊断。
- [x] 角色原始输入及导入字符串可追溯；现有优化与单次评估行为不变。

## Completion evidence

全部四项由公开导入任务入口及 Sim2GSE 测试验证。失败导入不会运行受控序列伤害模拟；任务保留 `input.original.simc`、`input.gse`、序列与版本、SHA-256、来源路径及编译场景。旧搜索候选仍走原 codec 适配，并由固定基线 golden 测试保护搜索起点和顺序。

真实 DPS 验收由 Karen 邪 DK 原帖中的未修改 ST 成员完成：集合原串 SHA-256 `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497`，GSE 3.3.13（3313），成员 `unholydk_ST` 版本 1。角色查询严格映射 `316239` 与名称形式 `Festering Strike` 到 `festering_strike`（原生动作编号 85948）；完整动作计划和证据路径见 `docs/sim2gse/gse-import-corpus.md`。

该序列在无修饰键、已有存活可攻击目标、宠物已召唤的场景下展开为 22 个点击；`click_ms = input_interval_ms = 300 ms`、`gcd_ms = 1500 ms`、seed `20260912`。受控原生模型 DPS 为 50873.80836033131；同角色自由选择参考 DPS 为 77044.71054312987，单独报告，不是导入序列的预期值或比较门槛。完整任务产物位于忽略目录 `.local/sim2gse/import-review-karen-st-20260925-name-map/`。此前 Søl 12.1 AOE/ST 的 37842.240154123254 和 41627.01167663097 来自错误地跳过条件成立的 `/petattack [@target,harm,nodead]`，现标记为无效历史结果；两个成员当前都会在模拟前按来源位置拒绝。其余无法严格映射的真实成员仍按具体原因拒绝；没有猜技能、替换 `item 13` 或改动伤害模型。

本票功能验收已完成。原生模拟尚未替代游戏内导入和战斗日志验收，该人工验收仍由 05 跟踪。
