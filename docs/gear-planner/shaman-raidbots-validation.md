# 萨满三专精采集、验证与适配

日期：2026-09-10。元素、增强、恢复三份样本的应用属性与平均装等 42/42 严格一致。原版完整快照 92/93，增强躲闪比例存在一个浮点步长差异，保留未通过。未修改引擎或放宽比较精度。

## 数据来源与构造

元素、增强使用固定官方提交 `b845947a34429874433d8e9362326894650dd20a` 的第二赛季配置：

- [元素参考配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Shaman_Elemental.simc)，牛头人。
- [增强参考配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Shaman_Enhancement.simc)，巨魔。

固定源码没有恢复第二赛季参考配置。恢复使用元素样本的牛头人身份和全部装备，改为恢复专精及 [Method（攻略网站）作者 Radio 的 12.1 团本图腾天赋](https://www.method.gg/guides/restoration-shaman/talents)。该页面更新日期为 2026-08-11。全部原装备均通过恢复候选筛选，未替换装备；构造明细保存于 `restoration-construction.json`。此样本是受控静态测试配置，不是官方恢复模板或毕业推荐。

三份都实际提交 Raidbots（模拟服务），下载真实报告的输入、输出和结构化属性，期望值来自远端角色快照，不使用本机结果生成。它们均不是玩家原始导出或游戏实测。

沿用之前口径：保留身份、天赋、额外系统、站位与装备，关闭消耗品、团队增益、临时武器附魔，动作只生成属性快照并等待一秒；没有施放护盾、武器灌注、图腾或输出／治疗循环。静态口径一致，不代表所有游戏内状态。

## 版本及结果

远端版本 `b845947a34`，正式服 `12.1.0.69587`，热修日期 `2026-09-04`，热修摘要 `210cdaf4f71cc8f675a3a62d99e3b6010952c9694959d8d4d59d0e134ffba46a`。分别使用同提交未修改构建与当前官方 `c1935b9` 程序重放实际输入；身份、天赋、完整装备和游戏数据均一致，两种程序的通过项与差异相同。

| 专精 | 真实报告 | 原版完整快照 | 应用属性／平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 元素 | [报告](https://www.raidbots.com/simbot/report/oRaFTF9Fx6fHsTt7syySv7) | 31/31 | 14/14 | 337.375 |
| 增强 | [报告](https://www.raidbots.com/simbot/report/8hDi2u3CYBb4zif7Zx392e) | 30/31 | 14/14 | 338.625 |
| 恢复 | [报告](https://www.raidbots.com/simbot/report/5kTveWcRRgwLPesiZtQqeX) | 31/31 | 14/14 | 337.375 |

应用 14 项为四项基础属性、护甲、四个副属性等级和四个百分比、平均装等。平均装等由报告逐槽装备推导，不作为独立游戏实测。应用当前没有躲闪展示项，所以 42/42 与完整快照一项差异并不矛盾。

## 未通过项与恢复边界

增强 `stats.dodge`（躲闪比例）：远端 `0.1532988497580691`，本机 `0.15329884975806907`，差值 `2.7755575615628914e-17`。标准库确认两者是相邻双精度浮点数。同提交未修改构建也复现，差异在配装器之外已经存在。其具体运算来源尚未定位，不能据此断言官方规则错误。

该项保留严格未通过，命令返回状态码 1；不修正期望值、不加容差、不改引擎。2026-09-11 用户确认：增强本项浮点精度差异暂不处理，暂停排查与修复。

恢复的 `spec=restoration`（恢复专精）与恢复天赋始终保留，`role=spell`（法术角色）使用原版支持路径。官方 `engine/class_modules/sc_shaman.cpp` 的 `primary_role()` 默认把恢复映射为法术角色，`validate_actor()` 允许这一组合；应用现有默认角色路径也取得相同快照。显式设置 `role=heal`（治疗角色）会转为混合角色并被原版拒绝，探测日志已保存。因此本次恢复静态属性对照通过，不代表治疗模拟、治疗量或所有恢复被动规则已游戏验收。未启用实验专精或修改引擎。

## 配装器适配

- 接入元素 262、增强 263、恢复 264，中文名称、专精套装和角色身份保留。
- 锁甲专精；元素／恢复采用智力，增强采用敏捷，来源明细显示对应主属性；按职业和掉落专精筛选候选。
- 武器依据[暴雪萨满介绍](https://worldofwarcraft.blizzard.com/zh-cn/game/classes/shaman)及固定版本物品资料：增强候选为单手斧、锤、拳套双持；元素／恢复可用智力单手武器加盾牌或副手物品，也可用适配双手武器。排除剑、长柄、魔杖及板甲。
- 元素／恢复禁止双持武器；双手主手替换清除副手，双手状态加副手被拦截。复用现有十六槽平均装等规则与宝石、附魔、方案操作，无新增计算引擎。
- 实际套装资料已取得三个专精的两件、四件中文说明。恢复四件的动态吸收数值在资料接口原文为 0，尚未证明游戏中实际吸收值，本次未对其造值修补；中文说明存在与动态效果数值正确是不同验收项。

## 验证与复现

样本及期望清单：`prototypes/gear-planner/fixtures/raidbots-shaman/`。原始模板、提交文本、实际报告、角色探测、浮点差异与复验结果：`.local/gear-planner-shaman-validation/`。当前引擎文件摘要保持 `f1281cdc7224d9d08e23cca1c090fa1b144b8b22491ffd8459ccefb8d8120987`。

三个参考样本的浏览器操作均通过：导入、候选和套装专精选择、宝石、附魔、替换、保存、另存为、刷新恢复、比较、导出再导入。增强追加单手锤／拳套双持替换与平均装等检查；元素和恢复追加法杖清除副手、双手时加盾牌被拦截、单手加盾牌／副手物品切换及平均装等检查。测试使用独立临时存储，没有修改用户方案。

候选与输入检查通过。此前七职业二十份成功参考样本的应用数值回归没有新增差异，完整快照仅保留既有奇袭躲闪与奥术回蓝差异。神圣圣骑士按用户决定保持暂缓，不计入成功样本。仓库默认快速检查六项全部实际执行通过，文档更新后按统一入口复验。

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-shaman --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-shaman-validation/current-engine-check.json
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-shaman --engine .tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/simc.exe --output .local/gear-planner-shaman-validation/matched-engine-check.json
node prototypes/gear-planner/check-deathknight.cjs fixtures/raidbots-shaman
.venv/Scripts/python.exe prototypes/gear-planner/check-fit.py
.venv/Scripts/python.exe prototypes/gear-planner/check-extra-input.py
build-and-verify verify --project .
```

未提交代码、未修改引擎，未执行远端交付或游戏内验收。任务 09 继续开放，全种族、全部天赋、图腾和护盾等状态未因此视为完成。
