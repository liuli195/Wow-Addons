# 建立候选行为身份与搜索约束

Triage（分拣）: ready-for-agent
Status（状态）: in-progress
Assignee（领取者）: Implementer
Parent（所属变更）: [Sim2GSE 搜索候选标准化与约束](../spec.md)
Blocked by（前置事项）: 无

## What to build（交付内容）

让执行行为相同的搜索候选得到相同身份，让行为不同的候选保持分离，并让已定义的非法或无效候选在调用 SimC（战斗模拟器）前被拒绝。保留可导出程序及来源信息，不让显示或调试元数据污染行为身份。

## Acceptance criteria（验收条件）

- [ ] 固定等价样本 100% 得到相同身份。
- [ ] 固定非等价样本 100% 保持不同身份。
- [ ] 固定非法样本 100% 在 SimC 前拒绝，并返回可定位原因。
- [ ] 主动饰品仍算有效动作；只有空点击或不可映射动作的候选判为无效。
- [ ] 行为身份具有版本，且能与实际编译点击计划核对一致。
- [ ] 通过完整 `run_task`（运行任务）测试证明两个等价写法不会产生两次原生评估。

## Comments（讨论）

实施使用 TDD（测试驱动开发）；只覆盖第一阶段身份与约束，不调整局部变异策略。

### 红灯证据

- 命令：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_search.py::SearchAndValidationTests::test_run_task_deduplicates_equivalent_programs_before_native_evaluation`
- 结果：失败（1 failed）。完整 `run_task` 对同一主动饰品点击计划的 Loop（循环）写法与展开写法分别生成 2 条归档记录、启动 2 次原生评估；期望各 1 次。

### 绿灯证据

- 命令：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_search.py::SearchAndValidationTests::test_run_task_deduplicates_equivalent_programs_before_native_evaluation`
- 结果：通过（1 passed）；同一完整入口仅归档并评估该行为一次。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_search.py`
- 结果：通过（41 passed，5 subtests passed）。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/sim2gse`
- 结果：通过（254 passed，92 subtests passed）。
- 固定 DK（死亡骑士）基线仅更新为 `sim2gse-search-behavior-v1-*` 版本化键；候选顺序、导出文本散列 `322b8c36260b2402927d0a5db2b62ff788623193525a8c966f452ea96b404486`、编译步骤均由金样测试保持不变。本轮实测两个候选 DPS（每秒伤害）依次为 `10218.007233071205`、`12906.213074898955`。

### 审查修复证据

- 红灯：起始规则字段缺失、重复且乱序的 `/castsequence reset.flags` 被拒绝、标准形式与编译计划不一致的候选仍进入原生评估；对应定向测试分别失败。
- 绿灯：生产搜索直接调用 `canonicalize_search_program`，使用其保留来源的程序编译，并要求 canonical form（标准形式）与 `compiled_identity`（编译身份）完全一致；不一致候选在 SimC 前作为 `CandidateError`（候选错误）拒绝。
- 标准形式固定包含 `start_step=1` 和 `sequence_reset='end'`；`reset.flags` 按集合语义去重排序。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_search.py`
- 结果：通过（44 passed，5 subtests passed）。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/sim2gse`
- 结果：通过（257 passed，92 subtests passed）。

### Deferred（延期）

- SimC 请求数和缓存命中统计属于后续票二／票三，本票不实施。
