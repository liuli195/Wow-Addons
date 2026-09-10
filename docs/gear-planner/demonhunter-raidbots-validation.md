# 恶魔猎手三专精验证与适配

日期：2026-09-10。使用未修改官方引擎；本轮不提交或合并代码。

## 样本与数值结果

采用固定官方提交 b845947a34429874433d8e9362326894650dd20a 的第二赛季参考角色，分别提交 Raidbots（模拟服务）生成报告。这些是官方参考配置，不是玩家原始导出。保留角色、天赋、额外系统、装备、夜间状态及制作装饰，关闭团队增益和消耗品，记录一次战前属性快照后等待一秒，不进行伤害验收。

| 专精 | 实际报告 | 原版全部快照字段 | 应用属性及平均装等 | 平均装等 |
| --- | --- | --- | --- | --- |
| 浩劫 | [报告](https://www.raidbots.com/simbot/report/be3UjRK7N1Re99hsU8QJ8w) | 31/31 通过 | 14/14 通过 | 339.25 |
| 复仇 | [报告](https://www.raidbots.com/simbot/report/ae6esmXn7DdXgDMBEtEcwX) | 31/31 通过 | 14/14 通过 | 337.375 |
| 噬灭 | [报告](https://www.raidbots.com/simbot/report/7sCA5MKh1KdFKz8DpdQQLU) | 31/31 通过 | 14/14 通过 | 338.0 |

共 93 项原始快照字段与报告精确相同，应用 39 项属性加 3 项逐槽推导平均装等共 42 项通过。角色、天赋、装备结果及正式服数据也一致。平均装等来自报告逐槽结果推导，不冒充服务独立给出的平均装等快照。

服务提交为 b845947a34429874433d8e9362326894650dd20a，正式服构建 12.1.0.69587。与报告同提交的本地未修改源码构建、当前官方发行程序 c1935b9 均通过；版本来源及程序摘要沿用[死亡骑士构建记录](deathknight-raidbots-validation.md)。没有修改、切换或升级运行引擎。

## 配装器适配

- 接入恶魔猎手职业及浩劫 577、复仇 581、噬灭 1480；传递实际角色与天赋。复仇样本的夜间状态、制作装饰按原输入保留，增加对应安全校验。
- 候选池沿用原有赛季范围与索引，按专精、皮甲、武器类型和主属性筛选。浩劫、复仇采用敏捷，噬灭采用智力；不按死亡骑士的力量或板甲筛选。
- 套装说明按实际专精选择，未知说明不回退到鲜血。附魔选项排除恶魔猎手不能使用的死亡骑士符文熔铸；已有导入字段不静默删除。
- 原装备合并使用当前职业、天赋与武器配置，不再借用鲜血角色计算；自动合并只读特效缓存，缺证据时保留图标，不阻塞于联网补查。取消过期前端合并请求，键包含角色，避免跨角色串用。正常展开装备仍可补查特效。

## 证据与复现

样本、实际输入、期望值和内容摘要：`prototypes/gear-planner/fixtures/raidbots-demonhunter/`。原始报告及验证输出：`.local/gear-planner-dh-validation/`。

复用原有验证脚本，通过参数指定职业样本目录：

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures prototypes/gear-planner/fixtures/raidbots-demonhunter --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-dh-validation/current-engine-check.json
node prototypes/gear-planner/check-deathknight.cjs fixtures/raidbots-demonhunter
```

数值检查通过真实导入解析，但先提取角色装备字段，移除服务控制选项。浏览器测试复用仓库现有依赖，使用独立临时存储，不读取或覆盖用户保存方案。

## 依据与边界

- 浩劫：[官方参考输入](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Demon_Hunter_Havoc.simc)。
- 复仇：[官方参考输入](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Demon_Hunter_Vengeance.simc)。
- 噬灭：[官方参考输入](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Demon_Hunter_Devourer.simc)。
- 属性转换依据：官方源码 `engine/class_modules/sc_demon_hunter.cpp` 的 `convert_hybrid_stat`；输入解析依据：`engine/player/unique_gear.cpp` 的额外系统解析。固定源码本机已读取。
- 此次覆盖每专精一个种族与天赋组合，不代表所有种族、全部天赋、恶魔变形或战斗触发效果的游戏内验收。服务的触发效果警告保留在原始输出中。
- 前两次服务提交未跳转报告，编辑器内容尚未完成同步；等待编辑器状态后成功生成三份报告。未使用本地结果冒充服务期望值。

## 操作验收结果

三专精均通过实际浏览器操作：导入、候选及套装说明选择、宝石修改、替换项链、附魔修改、保存、另存为、刷新恢复、比较、导出并重新导入。原装备合并、同编号不同变体选中及范围外原物品回选回归通过。两次刷新超时已按请求积压问题修复，最终串行复验三份全部通过，未放宽数值断言。

死亡骑士三专精数值与浏览器操作回归通过；原有输入、换装及保存回归通过。异步请求检查已补充取消过期请求和角色切换用例并通过。仓库六项默认快速检查通过（使用有效缓存的项目已由工具明确标记），未执行完整模式或游戏内验收。
