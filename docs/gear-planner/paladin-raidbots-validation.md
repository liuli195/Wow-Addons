# 圣骑士三专精采集、验证与适配

日期：2026-09-10。防护、惩戒的原版快照 61/61、配装器属性与平均装等 28/28 严格通过。神圣被原版引擎拒绝，没有有效属性快照，不计入通过样本。未修改引擎。

## 样本来源

防护、惩戒采用官方固定提交 `b845947a34429874433d8e9362326894650dd20a` 的 `profiles/MID2/MID2_Paladin_Protection.simc` 和 `MID2_Paladin_Retribution.simc`。分别保留牛头人防护、矮人惩戒的身份、天赋及装备，提交 Raidbots（模拟服务），下载实际输入、输出及结构化报告。这是官方参考配置，不是玩家原始导出或游戏面板实测。

沿用此前口径：关闭团队增益及消耗品，仅执行属性快照并等待一秒，不执行输出循环。实际输入与期望属性保存在 `projects/gear-planner/fixtures/raidbots-paladin/`，原始下载与复验在 `.local/gear-planner-paladin-validation/`。

| 专精 | 报告 | 原版快照 | 应用属性／平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 防护 | [报告](https://www.raidbots.com/simbot/report/sNhRs3ogfJL4QEGUaWTABH) | 30/30 | 14/14 | 338.625 |
| 惩戒 | [报告](https://www.raidbots.com/simbot/report/xctaz9zmmrkACd3tkdjwyJ) | 31/31 | 14/14 | 339.25 |
| 神圣 | [失败报告](https://www.raidbots.com/simbot/report/5xNtRf1YD2MXMZC4ZVPkWr) | 无快照，未通过 | 无法计算，未通过 | 不提供 |

报告版本为 `b845947a34`，游戏版本 `12.1.0.69587`、热修日期 `2026-09-04`。同提交未修改构建与现有官方 `c1935b9` 程序分别重放，身份、天赋、装备、游戏数据以及上述通过项均一致。应用 14 项为四项基础属性、护甲、四项副属性等级及百分比、平均装等；平均装等从报告装备推导，不是独立游戏实测。

## 神圣的明确阻断

固定版本没有神圣第二赛季参考配置，因此本轮神圣仅构造诊断输入：以防护配置为底，改为神圣专精，采用 [Method（攻略网站）作者提供的神圣天赋](https://www.method.gg/guides/holy-paladin/talents)，替换不适配的武器及饰品，明确设置输出角色。改动逐项记录于 `holy-construction.json`。

这份诊断输入不是官方神圣配置或玩家导出；自动替换时两个饰品都选中了同一候选，尚未完成唯一装备合法性验收，因此也不能作为正式配对样本。保留提交原文供追溯，不将其放入成功快照清单。

服务端报告和本机原版均返回“神圣圣骑士当前不受支持”，随后“没有可运行角色”。本机分别尝试输出与治疗角色都失败。固定源码 `engine/class_modules/paladin/sc_paladin.cpp` 的 `paladin_t::validate_actor()` 在神圣分支直接返回 `false`，与装备组合或角色选项无关。仅改角色参数无法解决。此前观察到的默认输出角色不代表该专精可运行。

神圣已接入身份、智力板甲和盾牌候选规则；完整属性及正常计算操作闭环仍未完成。不绕过原版限制，不伪造期望值。若后续需要修改引擎，必须另行取得用户明确同意；此轮没有修改。

## 配装器改动与验证

- 接入神圣 65、防护 66、惩戒 70，中文专精名称及套装专精选择共用现有映射。
- 候选以板甲为护甲专精，神圣采用智力、防护与惩戒采用力量；神圣／防护采用单手武器加盾牌，惩戒采用双手武器。物理可装备与候选相关性仍分开处理。
- 副手禁止双持武器，盾牌只对圣骑士开放；双手主手替换清除副手，平均装等按实际组合计算。
- 修正共享混合主属性编号：官方 `engine/dbc/data_enums.hh` 定义 72 为力量／敏捷、73 为敏捷／智力、74 为力量／智力。此前智力规则错误包含 72、遗漏 74，敏捷规则错误包含 74、遗漏 72；修复于公共候选函数，添加独立枚举回归。
- 防护与惩戒浏览器操作已验证导入、候选、套装选择、宝石、附魔、替换、另存为、刷新恢复、比较和导出再导入；追加盾牌替换、力量来源列与两种武器组合平均装等检查。
- 此前五职业十五个专精的浏览器操作回归全部通过，十五份应用数值全部保持通过；完整快照只保留既有奇袭躲闪、奥术回蓝的各一个浮点步长差异，未新增差异。

神圣失败路径的浏览器检查也通过：导入后明确返回未完成计算、不产生最终属性，候选和保存方案仍可使用。仓库六项快速检查全部实际执行通过，文档更新后复验通过（其余五项复用有效缓存）。两个引擎文件摘要与此前记录一致。

## 复现

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures projects/gear-planner/fixtures/raidbots-paladin --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-paladin-validation/current-engine-check.json
node projects/gear-planner/check-deathknight.cjs fixtures/raidbots-paladin
.venv/Scripts/python.exe projects/gear-planner/check-fit.py
.venv/Scripts/python.exe projects/gear-planner/check-extra-input.py
build-and-verify verify --project .
```

快照比较命令只检查清单中的两份有效报告，退出成功不包含神圣。神圣失败输入及服务日志单独保留。任务 09 持续开放，全种族、全部天赋和游戏内状态未因此验收。

2026-09-10 用户决定神圣专精先记录、暂缓处理；不修改引擎，后续继续猎人。

## 实验性开关复验（2026-09-11）

用户授权开启原版实验性开关。原版校验仍无条件拒绝本职业治疗专精，最小输入退出码 40；失败证据见参考样本目录 experimental-unsupported.json（实验开关失败记录）。配装器已传入开关，界面验证失败时不显示最终属性、保留导入配置且允许保存。原版源码未修改，属性计算继续暂缓，不能计为成功适配。

## 神圣实际配装器接入（2026-09-11，用户授权）

神圣圣骑士现使用 `.tools/gear-planner-holy/b845947-gate1/simc.exe`（独立入口放行程序）。仅按 paladin/holy（圣骑士／神圣）选择该程序，其他专精仍使用原官方程序；实验开关继续按既有授权范围传入。源码补丁保存为 scripts/dev/gear-planner-research/holy-paladin-gate.patch，仅改变一处入口条件。输出版本标记为 `12.1.0.69587 · b845947 · holy-gate1`，不能标为未修改官方引擎。

部署文件摘要为 `7fc6a54acd4fa247fc4e1703619c03da3368ecb4f853a880a427ffdc7a87f6ae`。原版文件保留。重建方式与隔离构建的限制见[隔离试验](holy-isolated-gate-validation.md)。删除或回退独立程序前应先回退引擎选择，不能静默换成其他专精计算。

神圣样本通过实际界面闭环：导入、属性展示、候选筛选、宝石、附魔、替换、另存为、重载、比较、导出再导入、智力来源列与盾牌替换。五件神圣套装均取得专精 65 的两件／四件效果文本。此验证确认显示和交互，不证明套装动态效果的游戏准确性。

专精引擎选择检查通过；空快照不再被判为零属性成功。防护、惩戒原有远端配对回归通过。仓库快速验证通过。

新样本位于 projects/gear-planner/fixtures/holy-paladin-supported（本地接入回归样本），不是 Raidbots（模拟服务）独立准确性样本。神圣完成当前配装器接入，但独立游戏面板及全部天赋准确性仍未验收。织雾继续暂缓。
