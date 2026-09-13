# Sim2GSE（角色级按键序列优化器）

本目录是项目入口，与同级的 `gear-planner/`（配装器）统一放在 `projects/`（项目目录）下。当前已建立角色读取、离线导出、同一序列原生模拟、自动搜索、独立复测及取消恢复；第四票已将同一程序接入三步界面。职业、专精和职责交给固定引擎判断，统一优化伤害。最新测试与审查记录见[第四票](../../myspec/changes/sim2gse-implementation/issues/04-three-step-interface.md)，运行方式和状态边界见[本地任务说明](../../docs/sim2gse/local-task.md)。

- [实施地图](../../myspec/changes/sim2gse-wayfinder/spec.md)
- [实施方案](../../docs/Sim2GSE_Implementation_Plan.md)
- [项目目录与维护边界](../../docs/sim2gse/project-boundary-proposal.md)
- [邪恶角色与独立原版基线](../../docs/sim2gse/target-evidence.md)
- [原生动作来源与首轮能力映射](../../docs/sim2gse/action-capabilities.md)
- [最小序列的数据格式与编译原型](../../docs/sim2gse/export-prototype.md)

首轮使用用户提供的邪恶死亡骑士样本，单目标、300 毫秒名义输入间隔。项目说明与研究资料位于 `docs/sim2gse/`，开发脚本按需放入 `scripts/dev/sim2gse/`；复用仓库根的工具缓存、解释器环境与本地报告目录。后续只按当前票据需要创建文件。

本项目引擎独立于配装器：从官方固定源码单独维护补丁、构建和程序，放在本项目专属目录。公共工具目录不代表共用引擎文件；不得修改、覆盖或自动调用配装器的专用引擎。产品专用构建与研究原型分目录保存。

## 训练假人日志分析

游戏中先用 `/combatlog` 开始记录，测试结束后再输入一次 `/combatlog` 停止记录。然后在仓库根目录运行：

```powershell
.venv\Scripts\python.exe projects\sim2gse\combat_log.py `
  "D:\Program Files\World of Warcraft\_retail_\Logs\WoWCombatLog.txt" `
  --player "角色名" `
  --duration 180 `
  --gse-debug "GSE调试导出.txt" `
  --simulation "simc-result.json" `
  --primary-target "主训练假人"
```

只有战斗日志和 `--player` 是必需参数。工具会用成功施法的目标推断主目标；需要严格指定时使用 `--primary-target`，同名目标改填 GUID（全局唯一标识）。已经在开始记录前召出的宠物或守护者可重复传入 `--owned-source "名称或GUID"`；同名来源无法唯一确定时必须填 GUID，否则日志无法证明其归属。

`--gse-debug` 用最后一次 GSE（按键序列插件）调试区间定位测试，并列出各技能尝试次数、阻断原因和估算按键间隔。`--simulation` 接受 SimC（模拟引擎）的 JSON 结果；只有角色、时长和实际伤害目标数量都与单目标模拟一致时才比较 DPS（每秒伤害），并同时返回模拟均值、样本范围和标准差。战斗日志不能证明专精、天赋、装备、游戏版本和候选序列相同，输出会明确列出这些待人工核对的条件。输出 JSON（结构化文本）仍把主目标和其他受影响单位分别列出；只要范围伤害触及第二个单位，本次记录就不能冒充单目标模拟验收。
