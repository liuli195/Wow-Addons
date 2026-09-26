# 01: 正确模拟并评价顺序循环与暂停

**What to build:** 用户提交含顺序循环与暂停的可模拟按键程序时，Sim2GSE 按 GSE 实际编译出的点击顺序评价；暂停在内部只表示为 `WaitClicks(n)`（等待 n 次空点击）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] 顺序循环的展开顺序和重复次数与官方 GSE 编译输出一致，每次点击可追溯来源。
- [x] Clicks/MS/GCD 在不同按键间隔下转换为正确空点击数，模拟与编译计划一致；不一致时拒绝评价。
- [x] 确定性测试覆盖展开顺序、次数、暂停点击数、按键间隔、临界值及超限。
- [ ] 现有简单搜索与导入行为无回归；完整验证结果可复核，游戏内验收状态如实报告。
- [x] 不扩充其他循环模式、宏语义、`/castsequence`、预训练或搜索算法。

## 实施证据

- 官方 GSE 3.3.34（提交 `c33be915`）与仓库锁定的 3.3.32（`f225d4c9`）`Storage.lua` 均显示：`Clicks=1` 不生成步；普通非空 `MS` 固定按 1000ms 换算；GCD 比值交给 Lua 整数循环截步。官方 3.3.34 `storagecompile_spec.lua` 覆盖顺序循环和 Repeat 展开。
- TDD 红灯：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_interface.py::InterfaceTests::test_run_task_import_uses_gse_integer_gcd_pause_steps`，失败于本机计划 4 步、上游编译 3 步不一致。相同命令绿灯：`1 passed`，且 `run_task(mode="import")` 受控引擎收到 3 个空块及后续技能块。
- 高层覆盖顺序循环重复、Clicks 1/2、MS 间隔 300/400/1000ms、GCD 非整除及等于 1 的临界值、4097 步拒绝；受控引擎动作块和来源路径均与计划一致。
- 本机 Sim2GSE 可移植测试：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse -k "not test_tc_"`，`224 passed, 6 deselected, 86 subtests passed`。
- 实施已完成；正式固定基线验证待主代理提交后运行；真实游戏验收 `not_run`。
