# 正式规格目标文本提案（未应用）

这些文件仅是已批准行为的完整目标文本、增量草案和审阅差异，**不是MySpec受控预览或已经通过的主规格**。正式主规格尚未修改。必须由本机当前受支持MySpec按状态流程登记输入与主规格指纹、完整冲突和逐项决定，校验增量、生成完整预览，再展示全部差异并取得最终确认后原子应用。

## 表示方式与需求身份

用户已明确批准两项旧规则按“删除旧规则＋新增新规则”表示，不再使用“改名＋改正文”。MySpec 2.7.1不允许同一需求在一份增量中同时改名和修改正文；没有修改工具或绕过校验。

| 退役需求身份 | 对应新增需求身份 |
|---|---|
| Sim2GSE respects the confirmed runtime budget | Sim2GSE stops formal genetic algorithm search by natural stagnation |
| Sim2GSE 按需要追加候选评估并复核晋级 | Sim2GSE exposes only the current formal genetic algorithm execution |

另删除`Sim2GSE rotates valid search starts with a matching stagnation limit`。这些旧身份不继续作为当前规则，替代关系由本表和版本历史保留。除此以外保持已有需求身份，没有扩大删除或新增功能。

用户随后要求三份目标全文只写外部可观察功能、现象和验收，不写代码字段、函数、路径或内部数据结构。本次据此将原有实现描述外部化，并展开正文简称；具体实现移至[开发说明](../implementation-notes.md)。可观察的输入输出、设置优先级、数量与性能、失败保护、旧成果查看及兼容恢复边界保持。没有扩展为全库历史规格改名。

正文使用“遗传算法”“每秒伤害”“命令行”等全称。唯一包含旧缩写的既有需求标题`Sim2GSE limits pretraining observation to basic logs and time DPS curves`仅保留为既有身份，其中DPS指每秒伤害，未另外改名；其正文已展开。Sim2GSE、GSE、Codex、Claude Code为产品名称。`/castsequence`是用户输入和导出的游戏宏命令，不是内部实现字段。MySpec规定的Requirement、Scenario、MUST、WHEN、THEN分别表示需求、场景、必须、触发条件及预期结果，属于规格格式关键字。

`delta/`为可交官方校验的增量草案，不是手工主规格。`proposal.diff`仅辅助审阅目标内容；正式完整差异以官方预览为准，新增需求可能按工具规则排列到文件末尾。主规格原文指纹保存在`source-fingerprints.json`。最终不得沿用首次失败预览的就绪状态或确认。

当前增量静态计数：3项删除、41项修改、2项新增、0项改名。格式段落完整性已静态检查；官方命令验证和完整预览仍待执行。
