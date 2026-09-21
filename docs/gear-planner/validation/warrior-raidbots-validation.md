# 战士三专精验证

日期：2026-09-11。配装器属性与平均装等 42/42 一致；原版严格快照 98/99。未修改引擎。

| 专精 | 报告 | 原版快照 | 应用 |
| --- | --- | --- | --- |
| 武器 | [报告](https://www.raidbots.com/simbot/report/iRJzGnVzaFcfAYWYoGiQER) | 33/33 | 14/14 |
| 狂暴 | [报告](https://www.raidbots.com/simbot/report/uwFCNtpCH7Akh7hZ7CoU6P) | 33/33 | 14/14 |
| 防护 | [报告](https://www.raidbots.com/simbot/report/c8PYJbgof5Evveaa1hddDn) | 32/33 | 14/14 |

采用固定官方 b845947a34429874433d8e9362326894650dd20a 的 MID2_Warrior 三份配置，实际提交模拟服务并保存其真实输入和快照。这是官方参考配置，不是玩家导出或游戏面板实测。双方关闭临时增益及动作循环，只生成静态属性快照。当前 c1935b9 与报告同提交未修改构建产生相同通过项与差异，游戏数据均为 12.1.0.69587、2026-09-04 热修。

防护 stats.parry（招架比例）：报告 0.28650352609651175，本机 0.2865035260965118，相差一个浮点步长。保留严格未通过，未改变精度、期望值或引擎。

适配力量板甲、武器双手、防护单手加盾、狂暴双持双手斧锤剑；狂暴副手可选择双手武器，其他专精不因此获得双手副手。狂暴缺失副手的本机探测确认该槽贡献为零，不把主手重复计入。武器与盾牌限制参考[暴雪战士介绍](https://worldofwarcraft.blizzard.com/zh-cn/game/classes/warrior)和固定官方源码 warrior_t::validate_actor()。

样本与期望：projects/gear-planner/fixtures/raidbots-warrior/；两版本复验和原始报告：.local/gear-planner-warrior-validation/。复用 check-deathknight-raidbots.py 的 --fixtures 参数及 check-deathknight.cjs fixtures/raidbots-warrior 复验。完整种族、天赋、游戏状态未因此完成。

三份浏览器导入、编辑、保存、另存为、刷新、比较、导出再导入全部通过，狂暴副手双手武器替换通过。

2026-09-11 用户确认：上述浮点末位精度差异统一标为“暂不处理”，暂停排查与修复；保留原始证据与严格未通过结果，不改引擎、期望值或比较精度。
