# 猎人三专精采集、验证与适配

日期：2026-09-10。野兽控制、射击、生存三个参考样本均通过：原版完整快照 87/87、配装器属性与平均装等 42/42。三个样本的浏览器操作验收通过。未修改官方引擎。

## 数据来源与口径

从已固定并校验的官方提交 `b845947a34429874433d8e9362326894650dd20a` 提取以下第二赛季配置，再实际提交 Raidbots（模拟服务）。三份均为矮人，不是玩家原始导出或游戏面板实测。

- [野兽控制官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Hunter_Beast_Mastery.simc)
- [射击官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Hunter_Marksmanship.simc)
- [生存官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Hunter_Survival.simc)

保留身份、天赋、额外系统、站位和装备；移除原动作循环与消耗品配置，关闭团队增益、药水、合剂、食物、强化符文及临时武器附魔，仅执行属性快照并等待一秒。没有召唤宠物或执行输出循环。这是接入一致性测试，不代表宠物增益、伤害模拟或全部游戏状态验收。

从真实报告下载实际输入、文本输出和结构化结果，期望值直接摘自角色属性快照，未使用本机计算结果生成。实际输入与摘要、完整期望值和装备保存于 `projects/gear-planner/fixtures/raidbots-hunter/`；官方原文、提交文本、下载原文和复验结果保存在 `.local/gear-planner-hunter-validation/`。

报告使用 `b845947a34`，正式服 `12.1.0.69587`，热修日期 `2026-09-04`，热修摘要 `210cdaf4f71cc8f675a3a62d99e3b6010952c9694959d8d4d59d0e134ffba46a`。分别用同提交未修改构建及当前官方 `c1935b9` 程序重放，身份、天赋、装备、游戏数据和快照均一致。程序来源沿用[死亡骑士构建记录](deathknight-raidbots-validation.md)。

## 数值结果

| 专精 | 报告 | 原版完整快照 | 应用属性／平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 野兽控制 | [报告](https://www.raidbots.com/simbot/report/1j4zLhvYdbKP6GEtvsGnbV) | 29/29 | 14/14 | 338.625 |
| 射击 | [报告](https://www.raidbots.com/simbot/report/5VH4YSxC2No7BZUHzvVqxt) | 29/29 | 14/14 | 339.25 |
| 生存 | [报告](https://www.raidbots.com/simbot/report/5xafPSzGHz2PELm9ZMPCfG) | 29/29 | 14/14 | 339.25 |

未通过项：本轮三份猎人样本没有数值差异。应用 14 项为四项基础属性、护甲、四个副属性等级及四个百分比、平均装等。平均装等按报告各部位装备和既定十六槽口径推导，不是独立游戏实测值，也不直接采用模拟器按有效物品数量平均的装备摘要。

## 适配与验收

- 接入猎人及野兽控制 253、射击 254、生存 255；敏捷来源列、锁甲专精、职业限定和掉落专精筛选。武器种类依据[暴雪猎人说明](https://worldofwarcraft.blizzard.com/zh-cn/game/classes/hunter)及固定版本装备资料。
- 野兽控制、射击候选使用弓、枪、弩，不提供副手候选；生存候选使用近战武器，支持双手和双持。官方固定源码 `engine/class_modules/sc_hunter.cpp` 的 `init_action_list()`、近战攻击和双持分支明确处理双手、单手及小型近战武器；未把生存错误限制为双手武器。
- 远程武器和双手近战武器按占用两手处理：替换时清除副手，装备这类主手后禁止再选择副手；双持按两个实际槽位计装等。新增公共两手占用判断，弓、枪、弩计入双槽，魔杖不因同为远程栏位而被错误翻倍。
- 三个参考样本完成导入、候选筛选、套装专精选择、宝石、附魔、装备替换、保存、另存为、刷新恢复、比较、导出再导入。
- 野兽控制和射击另验弓／弩／枪依次替换及平均装等；生存另验双手状态选择副手被拦截、单手加副手成功、重新选择双手清除副手及对应平均装等。生存双持属于本机操作及计算检查，未额外采集双持模拟服务快照。
- 实际套装肩部 271490 的资料包含三个专精各自两件、四件中文效果，已保存到本机证据并确认共六条；界面继续按专精选择对应说明。
- 候选适配、输入边界检查通过；此前六职业十七份成功样本的应用数值回归全部保持通过，完整快照仅保留既有奇袭躲闪、奥术回蓝各一个浮点步长差异。神圣圣骑士按用户指示暂缓处理，未列入成功样本。
- 仓库六项默认快速检查全部实际执行通过；文档更新后按同一入口复验。未运行远端交付检查或实际游戏验收，未提交代码。

## 复现

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures projects/gear-planner/fixtures/raidbots-hunter --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-hunter-validation/current-engine-check.json
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures projects/gear-planner/fixtures/raidbots-hunter --engine .tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/simc.exe --output .local/gear-planner-hunter-validation/matched-engine-check.json
node projects/gear-planner/check-deathknight.cjs fixtures/raidbots-hunter
.venv/Scripts/python.exe projects/gear-planner/check-fit.py
.venv/Scripts/python.exe projects/gear-planner/check-extra-input.py
build-and-verify verify --project .
```

任务 09 继续开放：本轮只覆盖三个固定参考样本与上述操作，不宣称猎人全种族、全部天赋、宠物与全部游戏状态已完成验收。
