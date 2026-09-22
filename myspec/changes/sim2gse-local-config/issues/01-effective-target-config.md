# 01：接通实际生效的目标配置

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: closed

## What to build

读取并校验本地 TOML（配置文件）目标配置，在服务启动时形成实际生效值；让基线与受控引擎共用目标参数，并把配置写入任务条件和恢复检查。

## Blocked by

无，门禁 1 批准后可实施。

## Acceptance criteria

- [x] 配置文件缺失或字段省略时使用约定默认值。
- [x] 无效配置在服务启动时给出明确错误，且不会启动任务。
- [x] 基线与受控引擎使用相同的目标名、等级、护甲系数和目标数。
- [x] 报告目标数按实际生效配置核对。
- [x] 任务状态记录实际生效配置，配置变化后在模拟前拒绝恢复。
- [x] 相同配置可恢复；原始输入或任务副本被篡改时拒绝恢复且保留旧结果。
- [x] 服务和命令行入口只在各自进程启动时读取配置。
- [x] 角色入口和接口检查覆盖上述行为并通过。

## Completion evidence

- RED：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_simulation_config.py`；配置模块尚不存在，收集阶段失败。
- RED（审查修复）：同一命令暴露 2 个失败：独立 `target_count` 仍被接受，篡改两个输入副本后恢复未拒绝。
- RED（第二轮审查修复）：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_simulation_config.py -k before_task_store` 在修复前失败并命中 `TaskStore must not open`；覆盖两份输入副本篡改。
- GREEN：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_simulation_config.py`；`15 passed, 5 subtests passed`。
- 回归：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse --dist=worksteal`；`86 passed, 36 subtests passed`。
- 规格：同步 `myspec/specs/sim2gse-character-input/spec.md`，明确默认单目标且目标数可由已记录本地模拟配置调整。
- 语法与差异检查：`compileall`、`git diff --check` 通过；统一 Build and Verify（构建与验证）及独立审查由主代理继续执行。
- 独立审查：两轮修复后最终复核未发现高、中问题，票据 01 获准完成。
