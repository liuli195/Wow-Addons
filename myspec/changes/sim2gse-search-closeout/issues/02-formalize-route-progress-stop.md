# 02：正式化共用分支进展早停

Status: in-progress（实现完成，待统一审查与正式验证）
Blocked by: none（01 已提交 2e016bd）

## What to build

旧搜索和选择器搜索均把经验证的有效分支晋升视为进展，重置全局无改善计数；不再依赖实验源码注入。

## Acceptance criteria

- [ ] 全局晋升或非起点分支晋升均重置，初始建立和未通过验证的提升不重置。
- [ ] 仅完整无改善轮累加，未完成轮不误计。
- [ ] 正式阈值沿用实际有效分支数，训练沿用两轮，取消训练600秒总硬截断的修复不回退。
- [ ] 两种搜索模式采用同一判定，无额外早停开关、各分支计数或新参数。
- [ ] 通过真实搜索公共链的最小行为测试，不通过source.replace完成产品实现。

## Comments

2026-10-21：用户明确要求作为正式功能并纳入主干清单，覆盖此前仅留实验的方案。

2026-10-21 实施：
- 共用晋级点增加非起点 route_promoted 判定，仅一行；保留现有单全局计数、完整轮累加、实际有效分支数与训练两轮阈值，不增加 checkpoint 或早停参数。
- 公开 run_task 两模式分支晋升红测试均由 2 轮提前停止变为 4 轮；全局晋升、统计拒绝、无进展共 8 例通过。使用真实产品入口和已有外部模拟报告边界，不做源码注入。
- 两模式初始化/部分轮 6 例及已有训练 CLI 时间/候选上限动态终止 2 例通过；部分轮有效进展清零、无进展不累加，训练超过 600 秒仍以两轮无改善停止。
- 沿用本次未发布 independent-search-modes-v2，未引入新身份版本。历史实验脚本仅留历史证据，不作为正式实现依赖。
- 云端测试仍为测试进程 POSIX 实锁适配、原 conftest 临时数据中心隔离，不代表 Windows 锁/JobObject 验证。
- 最终联合命令：`DATA_STORE_TEST_SKILL="$PWD/../cloud-skills/managed/skills/data-store" .venv/bin/python .local/spec-work/pytest-posix.py tests/sim2gse/test_search_closeout.py tests/sim2gse/test_search.py::SearchAndValidationTests::test_normal_search_no_improvement_limit_matches_valid_start_count tests/sim2gse/test_seed_training.py::test_training_uses_two_unimproved_rounds_instead_of_total_limits -q`。初次 29 passed / 1 failed（29.14 秒）：唯一失败是原有效分支数用例旧语义预期 4 轮，新有效分支晋升令其变 5 轮、分支轮数 [3,2]。仅更新该行为断言后单例 1 passed（3.73 秒）。共 30 项分别通过，未宣称重跑整组或全仓。
- `git diff --check` 与 compileall 通过。正式规格未改，未提交，等待主代理统一提交并作为曲线性能基线。
