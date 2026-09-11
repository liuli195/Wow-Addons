# 术士三专精采集、验证与适配

日期：2026-09-10。本轮按痛苦、恶魔学识、毁灭各一份参考配置进行配对验证。原版引擎快照 93/93、配装器属性与平均装等 42/42 严格一致，没有调整期望值或验收精度，没有修改引擎。

## 来源与计算口径

使用官方固定提交 `b845947a34429874433d8e9362326894650dd20a` 的第二赛季参考配置，提交 Raidbots（模拟服务）后下载真实报告的输入及结果。这三份是官方参考配置，不是玩家原始导出或游戏面板实测。

- [痛苦官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Warlock_Affliction.simc)：巨魔。
- [恶魔学识官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Warlock_Demonology.simc)：兽人。
- [毁灭官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Warlock_Destruction.simc)：矮人。

保留角色、专精、种族、天赋、额外系统与完整装备参数；去掉原动作循环、来源默认项和消耗品设置，改为关闭团队增益、药水、合剂、食物、强化符文及临时武器附魔，只执行属性快照并等待一秒。双方均不召唤宠物、不使用恶魔牺牲或战斗触发动作。这是本轮明确一致的静态接入口径，不验证宠物伤害或完整战斗表现。报告提示缺少饰品使用动作，与本次不主动使用饰品的设置一致，不作为数值校准依据。

三份报告均采用提交 `b845947a34`，正式服数据 `12.1.0.69587`、热修日期 `2026-09-04`、热修摘要 `210cdaf4f71cc8f675a3a62d99e3b6010952c9694959d8d4d59d0e134ffba46a`。同提交未修改源码构建和网站当前官方发行程序 `c1935b9` 分别重放实际输入，两者的身份、天赋、装备、游戏数据和全部快照字段都与报告一致。程序来源沿用[构建记录](deathknight-raidbots-validation.md)。

## 数值结果

| 专精 | 模拟服务报告 | 原版快照严格比较 | 配装器属性与平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 痛苦 | [报告](https://www.raidbots.com/simbot/report/9PsD6g8B3ufCoCtDZGnD98) | 31/31 | 14/14 | 337.375 |
| 恶魔学识 | [报告](https://www.raidbots.com/simbot/report/3VJf7z4SS7PQATvsjdvtF5) | 31/31 | 14/14 | 337.375 |
| 毁灭 | [报告](https://www.raidbots.com/simbot/report/fCfmD6FQXEU15AM7v4A18F) | 31/31 | 14/14 | 337.375 |

配装器 14 项为力量、敏捷、智力、耐力、护甲、四个副属性等级与四个百分比、平均装等。平均装等由报告逐槽装备等级推导，不冒充独立游戏面板结果；原始护甲均为 1392.7，没有为了匹配而添加取整或修正系数。本轮没有未通过的术士数值项。

## 配装器适配

- 接入术士及痛苦 265、恶魔学识 266、毁灭 267；标题与套装说明使用对应中文专精。
- 种族导入兼容官方配置中的 `Orc`、`Dwarf` 大写形式，按引擎对应名称规范为小写，继续拒绝非法输入和职业／专精错配。
- 候选按布甲、智力、职业专属限制与当前掉落专精筛选；武器支持匕首、单手剑、法杖、魔杖，副手只提供副手物品，排除盾牌与副手武器。武器类别依据[暴雪术士介绍](https://worldofwarcraft.blizzard.com/en-gb/game/classes/warlock)及本地当前装备资料。
- 换成双手法杖时清空副手；使用法杖时选择副手物品，会提示先换成单手主手。单手加副手分别计算装等，双手法杖按两个武器槽位计算。
- 复用宝石、附魔、装等与方案保存路径，排除死亡骑士符文熔铸。属性来源表按职业／专精显示主属性，术士及噬灭显示智力，敏捷职业显示敏捷，死亡骑士保持力量。
- 已读取实际术士套装肩部资料，三个专精各有两件和四件中文效果；选择对应专精的内容，沿用“套装(2)：”“套装(4)：”格式。

## 证据与复现

三个专精参考样本均已完成独立临时浏览器存储下的导入、候选与套装专精选择、宝石修改、替换项链、附魔修改、保存、另存为、刷新恢复、比较、导出再导入。另逐一验证智力来源表、单手加副手切换为法杖后清空副手、阻止法杖搭配副手、切回单手并装入副手，以及两种组合的平均装等。测试未修改用户保存的方案。

候选与输入校验、异步请求回归均通过。此前死亡骑士、恶魔猎手与盗贼九份快照及应用输出复验无新增差异，九个专精的浏览器操作回归也全部通过；奇袭躲闪仍保留原来的一个浮点步长差异。仓库默认快速验证六项均实际执行并通过，与配装器专项验证分别记录。

版本管理中的样本：`prototypes/gear-planner/fixtures/raidbots-warlock/`。清单保存报告链接、原始输入与结果文件的校验摘要、完整期望快照及装备。原始官方配置、提交文本、实际输入与输出、两种引擎重放及套装资料保存在 `.local/gear-planner-warlock-validation/`。

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-warlock --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-warlock-validation/current-engine-check.json
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-warlock --engine .tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/simc.exe --output .local/gear-planner-warlock-validation/matched-engine-check.json
node prototypes/gear-planner/check-deathknight.cjs fixtures/raidbots-warlock
.venv/Scripts/python.exe prototypes/gear-planner/check-fit.py
.venv/Scripts/python.exe prototypes/gear-planner/check-extra-input.py
build-and-verify verify --project .
```

脚本沿用既有文件名，通过参数选择职业。应用导入检查只提取实际输入中的角色与装备字段，服务控制参数不属于插件导入格式。

本轮不代表全部种族与天赋组合、宠物相关增益或游戏内全部状态已验收。任务 09 保持开放；盗贼奇袭躲闪的既有差异仍按用户决定暂不处理，不因术士通过而改变其状态。
