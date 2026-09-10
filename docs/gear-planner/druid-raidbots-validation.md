# 德鲁伊验证记录

本轮按平衡、野性、守护、恢复验证。未修改原版引擎。由于固定源码没有可用的 MID2（第二赛季）德鲁伊成品配置，使用当前 12.1 装备池中各槽位首个专精适配且不重复的候选；项链与戒指复用已配对的萨满样本，保留合法宝石。天赋分别来自 Method（职业攻略作者）对应专精天赋页。精确输入和构造记录存入 fixtures/raidbots-druid（德鲁伊参考样本目录）。这不是玩家原始导出，也不是官方德鲁伊参考配置。

用户确定的状态是无变形、脱战预览。原版 reset（重置）将 form（形态）置为 CASTER_FORM（无变形），本轮只调用 snapshot_stats（属性快照），没有施放变形动作。恢复使用原版默认 attack（攻击角色），保持恢复专精；能够生成静态快照不表示支持治疗模拟。

四份本机探针均成功生成属性快照。两种未修改原版程序严格快照均为 109/112；配装器属性与平均装等 56/56 通过。平衡、野性、恢复各有一项躲闪末位浮点差异，守护 28/28；差异保留未通过，不改期望或精度。

- [balance（专精报告）](https://www.raidbots.com/simbot/report/tirSKZMDyrjpePQ9CRL2nK)
- [feral（专精报告）](https://www.raidbots.com/simbot/report/toML1Jao1vxduVBH7qrmdW)
- [guardian（专精报告）](https://www.raidbots.com/simbot/report/jSJJpovdyTFcxhXW4mWBTd)
- [restoration（专精报告）](https://www.raidbots.com/simbot/report/vgpJSTJhPVYR1uBLbEVH4Z)

四专精操作闭环通过；平衡、恢复包含法杖／单手加副手切换，野性、守护核实敏捷列、副手候选及双手平均装等。

2026-09-11 用户确认：上述浮点末位精度差异统一标为“暂不处理”，暂停排查与修复；保留原始证据与严格未通过结果，不改引擎、期望值或比较精度。
