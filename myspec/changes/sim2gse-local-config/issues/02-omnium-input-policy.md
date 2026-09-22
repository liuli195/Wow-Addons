# 02：按配置处理万奥宝典任务副本

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: open

## What to build

在同一实际生效配置中加入万奥宝典开关：关闭时只从任务副本删除完整的 `omnium_talents=` 行，开启时保留；原始输入始终逐字节保存，开关参与恢复条件。

## Blocked by

01：接通实际生效的目标配置。

## Acceptance criteria

- [ ] 关闭开关时，任务副本不含完整的 `omnium_talents=` 行，其他内容保持不变。
- [ ] 开启开关时，任务副本原样保留该行。
- [ ] `input.original.simc` 在两种设置下都与用户输入逐字节一致。
- [ ] 角色身份始终从原始输入解析，任务记录同时包含原始与有效输入散列。
- [ ] 开关变化后在模拟前拒绝恢复旧任务。
- [ ] 本地 `.local/sim2gse/config.toml` 按已批准默认值落地且继续被 Git 忽略。
- [ ] 角色入口和页面接口检查通过。

## Completion evidence

实施后填写失败检查、通过检查、服务重启和页面可访问结果。
