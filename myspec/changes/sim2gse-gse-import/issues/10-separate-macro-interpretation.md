# 10：把已有宏解释从 GSE 控制层剥离

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: ready

## What to build

导入序列仍在相同场景下产生相同的按键动作或拒绝原因；GSE 控制层只交付逐次按键与宏原文，已有宏条件和命令解释由单独模块承担，便于日后独立扩充。

## Blocked by

09：先固定完整导入语法与公开检查结果，再做行为保持的剥离。

## Acceptance criteria

- [ ] 已有宏条件、命令、预检及角色动作映射移出 GSE 导入/控制模块；模块交接只包含宏原文、来源位置、场景和角色动作目录，不让 GSE 控制代码理解宏条件。
- [ ] 不新增宏语法或游戏状态模拟；既有可模拟输入的逐次动作、来源路径与 DPS 保持一致，不支持输入仍按原位置和原因拒绝。
- [ ] 用公开检查与任务入口验证真实样本中代表性的成功、宏拒绝、If 外部变量拒绝与缺失 Embed 引用；完成仓库统一验证和独立审查。

## Highest public seam and failure path

`POST /api/gse/inspect` 与导入模式 `POST /api/tasks`；宏不能忠实解释时在模拟前保留原文位置拒绝，GSE 语法检查不因宏语义失败而报解析失败。

## Comments

2026-09-25 范围修订：这是最小架构整理，不实施完整 WoW 宏解释器。
