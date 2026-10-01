# 01：双宿主入口与禁用态盘点

**What to build（交付行为）：** 共用入口和隔离根只读inventory/status。

**Blocked by（阻塞任务）：** None（可开始）

**Status（状态）：** ready-for-agent

- [x] 技能内容自包含，Claude显式幂等联接不复制、不改全局配置。
- [x] 空格/中文/不同cwd身份一致，路径边界和重解析点拒绝。
- [x] 生产未配置变更拒绝，盘点不刷新last_used。

## 测试与审查

通过技能单一CLI（命令行入口）先失败再转绿，仅隔离合成根。记录红绿及脱敏检查证据，固定起止提交后推送功能分支，暂停该审查范围新增提交，父线程远端独立审查；修复再推再审。

## Comments（讨论）

门禁一已确认：用户在 Sentinel_169873e099008191b7ce3c9b82730cc7 回复“确认执行吧”，此前门禁内容完整展示。正式规格、真实数据、生产启用和计划任务安装不在本票范围。

第01票实施及7项合成CLI测试完成，等待固定提交后的统一验证和父线程远端独立审查，未宣称票据已验收。红绿记录见技能 references/validation-01.md。统一构建 checked 为 build.sim2gse-product、build.assets，status 为 passed。没有启动本机架构或审查模型。
