# 三阶段任务顺序

状态：门禁一已确认；01—07及阶段1、2最终审查全部通过；08进入爆发内容审核，09—12未开始。

| 票号 | 阶段 | 交付 | 前置票 |
| --- | --- | --- | --- |
| 01 | 1 | [阶段1：构建身份与三方原生对照](issues/01-build-identity-and-native-comparison.md) | 无 |
| 02 | 1 | [阶段1：抽取报告模块并证明行为不变](issues/02-report-module-probe.md) | 01 |
| 03 | 1 | [阶段1：目录接入和最终连接链](issues/03-reproducible-hook-chain.md) | 02 |
| 04 | 2 | [阶段2：控制时间与重置迁移探针](issues/04-controller-lifecycle-probe.md) | 03及阶段1最终审查 |
| 05 | 2 | [阶段2：完整控制模块迁移](issues/05-independent-controller.md) | 04 |
| 06 | 2 | [阶段2：核实客户端并升级对应源码](issues/06-client-matched-upstream-upgrade.md) | 05 |
| 07 | 2 | [阶段2：新版产物验收与回退](issues/07-upgrade-acceptance-and-recovery.md) | 06 |
| 08 | 3 | [审核专精爆发定义并导出独立序列](issues/08-reviewed-burst-export.md) | 07及阶段2最终审查 |
| 09 | 3 | [单场模拟循环键与独立爆发键](issues/09-independent-burst-simulation.md) | 08 |
| 10 | 3 | [搜索不含爆发技能的循环并隔离历史成绩](issues/10-burst-free-search.md) | 09 |
| 11 | 3 | [页面一次启动双场景并输出三个序列](issues/11-dual-scene-page.md) | 10 |
| 12 | 3 | [首批专精真实验收与交付准备](issues/12-real-acceptance.md) | 11 |

06还需核实实际客户端目标；08/09还需审核爆发内容及完整按键计划。全部票受新开发门禁约束。
详细文件改动、连接点、阶段停止和回退条件见 [三阶段方案](three-stage-plan.md)。
旧01—05依次变为08—12，原讨论原位保留。

审查：01—07每票规范/需求双轴分别使用GPT-6.1-Sol、高；03/07之后追加GPT-6-A、中对整个阶段最终审查，通过才进入下一阶段。阶段3原逐票双轴保留。见 [审查安排](review-policy.md)。


## 一次升级与回归验收（当前规则）

用户确认取消两种结构各完整升级的收益对照。只在新结构升级一次，复用固定邪恶死亡骑士模板和现有真实入口作轻量行为回归；旧记录必须身份与冻结条件可核验，缺失才补跑旧版。跨引擎不比较伤害、动作次数、精确时刻或搜索路径，按公共行为契约验收。同上游迁移严格一致与版本内部三方对照保留。新功能按阶段3专项验证，不能要求旧引擎支持。详细成本及证据边界见 [升级回归验收](upgrade-regression-acceptance.md)。




