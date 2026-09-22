# 02：按配置处理万奥宝典任务副本

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: closed

## What to build

在同一实际生效配置中加入万奥宝典开关：关闭时只从任务副本删除完整的 `omnium_talents=` 行，开启时保留；原始输入始终逐字节保存，开关参与恢复条件。

## Blocked by

01：接通实际生效的目标配置。

## Acceptance criteria

- [x] 关闭开关时，任务副本不含完整的 `omnium_talents=` 行，其他内容保持不变。
- [x] 开启开关时，任务副本原样保留该行。
- [x] `input.original.simc` 在两种设置下都与用户输入逐字节一致。
- [x] 角色身份始终从原始输入解析，任务记录同时包含原始与有效输入散列。
- [x] 开关变化后在模拟前拒绝恢复旧任务。
- [x] 本地 `.local/sim2gse/config.toml` 按已批准默认值落地且继续被 Git 忽略。
- [x] 角色入口和页面接口检查通过。

## Completion evidence

- RED：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_simulation_config.py -k omnium`；关闭开关时任务副本仍保留有效行，1 项失败。
- GREEN：同一命令；`3 passed, 15 deselected`。
- 聚焦回归：`.venv\Scripts\python.exe -m pytest -q tests/sim2gse/test_simulation_config.py`；`18 passed, 5 subtests passed`。
- 本地配置：`load_config(.local/sim2gse/config.toml) == DEFAULT_CONFIG`；五项值已落地，`git check-ignore -v` 确认继续由 `/.local/` 忽略。
- 规格：同步 `myspec/specs/sim2gse-character-input/spec.md`，明确原始输入保留与有效副本开关策略。
- Sim2GSE 全量回归、统一 Build and Verify（构建与验证）及独立审查待主代理继续执行；本票不操作服务。
- 独立审查：未发现高、中问题，票据 02 获准完成；换行形式的显式子用例列为低风险非阻断项。
