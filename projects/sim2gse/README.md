# Sim2GSE（角色级按键序列优化器）

本目录是项目入口，与同级的 `gear-planner/`（配装器）统一放在 `projects/`（项目目录）下。当前按实施地图推进，尚未建立正式实现模块。

- [实施地图](../../myspec/changes/sim2gse-wayfinder/spec.md)
- [实施方案](../../docs/Sim2GSE_Implementation_Plan.md)
- [项目目录与维护边界](../../docs/sim2gse/project-boundary-proposal.md)
- [邪恶角色与独立原版基线](../../docs/sim2gse/target-evidence.md)
- [原生动作来源与首轮能力映射](../../docs/sim2gse/action-capabilities.md)
- [最小序列的数据格式与编译原型](../../docs/sim2gse/export-prototype.md)

首轮使用用户提供的邪恶死亡骑士样本，单目标、300 毫秒名义输入间隔。项目说明与研究资料位于 `docs/sim2gse/`，开发脚本按需放入 `scripts/dev/sim2gse/`；复用仓库根的工具缓存、解释器环境与本地报告目录。后续只按当前票据需要创建文件。

本项目引擎独立于配装器：从官方固定源码单独维护补丁、构建和程序，放在本项目专属目录。公共工具目录不代表共用引擎文件；不得修改、覆盖或自动调用配装器的专用引擎。本项目扩展引擎目前尚未实现。
