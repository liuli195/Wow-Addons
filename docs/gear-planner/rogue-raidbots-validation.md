# 盗贼三专精采集、验证与适配

日期：2026-09-10。结论：配装器三份参考样本属性与操作通过，原版严格快照比较尚有奇袭躲闪一项差异，不能标记全部数值通过。官方引擎未修改。

## 数据来源与方法

取固定官方提交 b845947a34429874433d8e9362326894650dd20a 的第二赛季三个参考配置，提交 Raidbots（模拟服务）。不是玩家原始导出。保留角色、种族、天赋、额外系统及装备；关闭团队增益与消耗品，用 snapshot_stats（属性快照）后等待一秒。移除原动作循环，不添加潜行、毒药或战斗触发动作；这是本轮双方一致的静态口径，不是伤害验收。

从真实报告下载实际输入及原始结果；本地使用同一实际输入，分别在报告同提交的未修改源码构建和当前官方发行程序 c1935b9 中重放。全部使用正式服 12.1.0.69587 与相同热修数据。程序来源见[既有构建记录](deathknight-raidbots-validation.md)。

| 专精 | 报告 | 原版快照严格对照 | 配装器输出 | 平均装等 | 操作 |
| --- | --- | --- | --- | --- | --- |
| 奇袭 | [报告](https://www.raidbots.com/simbot/report/9DXrX6742VyZ7VhUUeFDLV) | 27/28 | 14/14 | 338.625 | 通过 |
| 狂徒 | [报告](https://www.raidbots.com/simbot/report/oLWckJP5bDfcLU55nk6vSX) | 30/30 | 14/14 | 336.75 | 通过 |
| 敏锐 | [报告](https://www.raidbots.com/simbot/report/4VNTRPwFBex3CXbbYgLA8c) | 30/30 | 14/14 | 338.0 | 通过 |

原版共 87/88 字段通过；两种本机程序的结果一致。应用 13 项展示属性加平均装等，每专精 14 项，共 42/42 通过。平均装等由报告逐槽装等推导，不是独立游戏面板截图。应用不展示躲闪，因此应用通过不代表原版严格快照全部通过。

## 暂不处理的未通过项

2026-09-10 用户决定：奇袭躲闪的一个浮点步长差异暂不处理，暂停针对该项的排查与修复。保留原始证据和严格比较的未通过结果，不修改引擎、期望值或验收精度；此决定不代表该项验证通过。

- 奇袭 `stats.dodge`（躲闪比例）：报告 `0.15685951699522216`，本机 `0.15685951699522213`。同提交源码构建仍能复现，身份、天赋、装备、正式服数据及其余快照字段均相同。
- 已用标准库验证：从本机值向正无穷取相邻的一个双精度浮点数，恰好等于报告值。差异为一个二进制浮点步长，符合构建或平台舍入差异的特征，但具体产生位置尚未定位。不能据此断言官方规则错误。
- 未修改期望值、未放宽精度、未加修正系数或引擎补丁。严格验证命令继续返回状态码 1。

## 适配与验收

- 接入 rogue（盗贼）及奇袭 259、狂徒 260、敏锐 261；角色名称使用中文。
- 使用皮甲与敏捷候选、盗贼可用武器类型及上游掉落专精数据；候选结果按部位保存，原索引不变。奇袭双匕首、敏锐主手匕首、狂徒主手非匕首；狂徒副手允许适配的敏捷匕首，不被主手规则或掉落专精掩码错误排除。
- 套装说明选择当前盗贼专精，附魔排除死亡骑士符文熔铸。引擎输入、宝石、附魔、装饰与已保存方案仍走共享路径。
- 三份均完成独立临时浏览器存储验收：导入、候选与套装文字选择、宝石修改、替换项链、附魔修改、保存、另存为、刷新恢复、比较、导出再导入。没有修改用户保存方案。
- 候选检查覆盖三个专精的主副手类型、皮甲和符文熔铸排除。

## 证据与复现

样本与内容摘要：`projects/gear-planner/fixtures/raidbots-rogue/`。原始报告及当前／同提交验证输出：`.local/gear-planner-rogue-validation/`。期望值只来自服务报告。

```powershell
.venv/Scripts/python.exe scripts/dev/gear-planner-research/check-deathknight-raidbots.py --fixtures projects/gear-planner/fixtures/raidbots-rogue --engine .tools/gear-planner-research/simc-1210.01.c1935b9-win64/simc.exe --output .local/gear-planner-rogue-validation/current-engine-check.json
node projects/gear-planner/check-deathknight.cjs fixtures/raidbots-rogue
```

第一条本轮返回 1（保留躲闪差异）；第二条返回 0。应用导入检查先提取角色装备字段，不能将其描述为整份服务控制脚本都可直接导入。

- 奇袭：[官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Rogue_Assassination.simc)。
- 狂徒：[官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Rogue_Outlaw.simc)。
- 敏锐：[官方配置](https://github.com/simulationcraft/simc/blob/b845947a34429874433d8e9362326894650dd20a/profiles/MID2/MID2_Rogue_Subtlety.simc)。

源码依据：`engine/class_modules/sc_rogue.cpp` 的主属性初始化及毁伤双匕首检查；原默认动作顺序中属性快照在潜行前。当前仍只覆盖三个种族／天赋参考组合，不代表所有合法组合、潜行／战斗增益或游戏内取整全部验收。

死亡骑士与恶魔猎手的六份属性对照、六份浏览器操作回归全部通过；异步请求、原有鲜血编辑恢复和方案序列化回归通过。仓库默认快速验证六项均实际执行并通过。盗贼严格数值命令返回 1 与这些质量检查通过分别记录，不互相抵消。
