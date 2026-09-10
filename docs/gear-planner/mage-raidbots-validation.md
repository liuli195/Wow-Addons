# 法师三专精采集、验证与适配

日期：2026-09-10。奥术、火焰、冰霜三个参考样本的配装器属性与平均装等 42/42 严格一致，操作验收通过；原版完整快照为 84/85，奥术每秒法力恢复仍有一个浮点步长差异。未修改引擎、期望值或验收精度，不能标记全部数值通过。

## 数据来源与口径

取官方固定提交 `b845947a34429874433d8e9362326894650dd20a` 的第二赛季参考配置，分别提交 Raidbots（模拟服务），下载真实报告的实际输入、输出及结构化属性。这些是官方参考配置，不是玩家原始导出或游戏面板实测。

- [奥术官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Mage_Arcane.simc)：虚空精灵。
- [火焰官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Mage_Fire.simc)：矮人。
- [冰霜官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Mage_Frost.simc)：牛头人。

保留身份、天赋、额外系统和完整装备参数；移除原动作循环、来源默认项和消耗品设置，关闭团队增益、药水、合剂、食物、强化符文与临时武器附魔。双方只执行属性快照并等待一秒，不使用奥术智慧、护盾、唤醒等额外施法动作，不触发战斗循环。这是明确一致的静态接入口径，不代表完整战斗表现。报告中的未使用饰品动作提示来自这组控制设置。

三份报告均采用 `b845947a34`、正式服 `12.1.0.69587`、热修日期 `2026-09-04`，热修摘要为 `210cdaf4f71cc8f675a3a62d99e3b6010952c9694959d8d4d59d0e134ffba46a`。同提交未修改源码构建和当前官方程序 `c1935b9` 分别重放实际输入，身份、天赋、装备与游戏数据全部一致，两种本机程序产生相同的通过项和差异。来源见[既有构建记录](deathknight-raidbots-validation.md)。

## 数值结果

| 专精 | 模拟服务报告 | 原版快照严格比较 | 配装器属性与平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 奥术 | [报告](https://www.raidbots.com/simbot/report/uEKzicLdRC9YKag6yYSH6g) | 28/29 | 14/14 | 337.375 |
| 火焰 | [报告](https://www.raidbots.com/simbot/report/s5GaFoh84eRUP92fHsB6Tb) | 29/29 | 14/14 | 337.375 |
| 冰霜 | [报告](https://www.raidbots.com/simbot/report/jVBxvCbUhkZ5t1qMWG9dFM) | 27/27 | 14/14 | 338 |

配装器的 14 项为四项基础属性、护甲、四个副属性等级和四个百分比、平均装等。平均装等由报告逐槽装备等级推导；不作为独立游戏面板证据。配装器不展示每秒法力恢复，因此 42/42 通过与完整快照尚有差异并不矛盾。

## 保留的未通过项

- 奥术 `stats.manareg_per_second`（每秒法力恢复）：报告 `6738.956521739131`，本机 `6738.95652173913`；差值 `9.094947017729282e-13`。
- 标准库确认两者是相邻双精度浮点数。同提交未修改构建也复现，差异不经过配装器就存在，不能归因于配装器数值转换。
- 官方 `engine/class_modules/sc_mage.cpp` 的 `mage_t::resource_regen_per_second` 在基础恢复上乘入奥术精通与相应状态倍率，涉及双精度乘加运算。当前差异符合舍入特征，但具体产生位置未定位，不能认定官方规则错误。
- 保留原始数据和严格未通过状态，不加修正系数、不改期望值、不放宽比较精度。法师验证命令继续返回状态码 1。2026-09-11 用户确认：本项浮点精度差异暂不处理，暂停排查与修复。

## 适配与操作验收

- 接入法师及奥术 62、火焰 63、冰霜 64；布甲、智力、法师专属装备及掉落专精筛选。武器支持法杖、匕首、单手剑、魔杖，副手只支持副手物品，排除盾牌与双持。依据[暴雪法师介绍](https://worldofwarcraft.blizzard.com/en-us/game/classes/mage)及当前装备资料。
- 法师与死亡骑士的冰霜都使用 `frost`（冰霜）标识。候选筛选和原装备合并改为“职业＋专精”键；套装说明使用服务端统一职业／专精编号映射。角色保存格式不变，避免法师冰霜 64 与死亡骑士冰霜 251 混用。
- 智力来源展示、宝石、附魔、装等和方案操作复用术士路径；法杖替换清空副手，法杖搭配副手会被拦截，单手主手可配副手物品，平均装等按实际武器组合计算。
- 实际法师套装肩部资料包含三个专精各自的两件和四件中文说明；显示沿用“套装(2)：”“套装(4)：”。
- 三个参考样本均通过独立临时浏览器存储下的导入、候选和套装专精选择、宝石及附魔修改、替换装备、保存、另存为、刷新恢复、比较、导出再导入；另验证智力来源列、法杖／单手加副手切换与平均装等。测试没有修改用户保存方案。

## 证据与复现

此前死亡骑士、恶魔猎手、盗贼、术士十二份样本的数值复验无新增差异，十二个专精的浏览器操作回归全部通过。另通过原装备返回、同物品选中边框、十五槽位合并、候选适配、导入输入和异步请求专项检查。仓库默认快速验证六项均实际执行通过，后续文档更新验证复用有效缓存；这些通过项不抵消奥术回蓝或既有盗贼躲闪的严格数值差异。

样本：`prototypes/gear-planner/fixtures/raidbots-mage/`。清单保存报告链接、实际输入与报告的校验摘要、身份、完整期望快照和装备。原始官方配置、提交文本、实际输入／输出、两种引擎复验、既有职业数值回归及套装资料保存在 `.local/gear-planner-mage-validation/`。

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-mage --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-mage-validation/current-engine-check.json
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-mage --engine .tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/simc.exe --output .local/gear-planner-mage-validation/matched-engine-check.json
node prototypes/gear-planner/check-deathknight.cjs fixtures/raidbots-mage
.venv/Scripts/python.exe prototypes/gear-planner/check-fit.py
.venv/Scripts/python.exe prototypes/gear-planner/check-extra-input.py
build-and-verify verify --project .
```

应用导入验证只提取实际输入中的角色与装备字段，不把模拟服务控制参数当作插件导入格式。当前三份样本不代表全种族、全部天赋组合、护盾／宠物／临时增益或游戏内所有状态已验收；任务 09 保持开放。
