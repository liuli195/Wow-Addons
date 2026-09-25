# 06：无损解析锁定 GSE 3.3.32 的全部导入语法

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

按锁定 GSE 3.3.32 上游导入器可接受的全部格式解析 GSE 原串。完整保留单序列、集合和各版本的所有字段，以及 Action、Repeat、Loop、Pause、If、Embed 六类块的合法字段、嵌套、变量、条件和宏原文；解析器不得静默丢字段、改写原文或把未知结构变成空步骤。

## Blocked by

01：收集样本并查看导入结构。该票已按旧验收口径完成；其验收更正明确列出本票新增的完整语法要求。

## Acceptance criteria

- [x] 以锁定的 GSE 3.3.32 上游导入代码和可接受输入格式为准，列全导入外壳及其解码路径；覆盖单序列、集合、直接序列对象，以及 `!GSE3!+` 受保护导入外壳。对每种格式都有可重复的固定向量；若该外壳受密钥或环境条件限制，须保留原始外壳并明确记录限制和失败原因，不得静默丢弃。
- [x] 对所有上游接受的序列成员和版本，完整保留原始字段和值、字段类型、数组顺序、缺省与显式空值差异、嵌套关系和来源路径；不得只保留当前模拟会用到的字段。
- [x] Action、Repeat、Loop、Pause、If、Embed 六类块均按上游完整字段结构解析，覆盖嵌套子块、各类步进/间隔/时长/条件/引用字段及变量值；宏命令、变量文本和条件表达式逐字符保留。
- [x] 对上游接受但当前实现不认识的普通字段仍原样保留；无法解释的块类型或结构不得伪装成已解析，必须带成员、版本和字段路径明确拒绝。
- [x] 六类块及各导入外壳都有解析后字段对照上游解码结果的回归证据；固定向量标记为合成证据，不冒充真实语料。

## 验收证据

- 定向回归：`.venv\Scripts\python.exe -m pytest tests/sim2gse/test_interface.py tests/sim2gse/test_program.py -q`，结果 **102 passed、48 subtests passed**。
- 公开入口实测：对 `.local/sim2gse/gse-corpus/*.txt` 和 `.local/sim2gse/gse-corpus-additional/*.txt` 中 16 个真实原串逐个调用 `POST /api/gse/inspect`，16/16 返回 `status=decoded`。初始红灯记录为 `.local/sim2gse/gse-corpus-inspection/initial-2026-09-25.json`；最终 16/16 结果记录于此，未另写语料副本。
- 合成外壳与六类语法证据：`tests/sim2gse/test_interface.py` 覆盖普通单序列、集合、直接序列对象、受保护序列/变量/宏和集合内受保护序列；`tests/sim2gse/test_program.py::test_upstream_compiles_six_control_blocks_in_one_collection` 与相邻的嵌套、来源路径用例覆盖六类块。受保护导入未发现真实样本，使用固定合成向量验证；真实 1290 字符原串没有复制进跟踪文件。
- DrussRet 真实样本：`.local/sim2gse/gse-corpus-additional/drussret-pause-01.txt`（SHA-256 `d992c3e47f13ed9e70b594f7f02908224cb6031b5dc3f20f5a03da14e723b0dd`）。公开 inspect 保留并解析 ST 版本级数字块，报告 `Sequences[DRUSS_ST_v6].Versions[1].Actions` 缺失警告，模拟预检拒绝；没有补造 Actions。
- 上游核对路径：`.tools/sim2gse-research/gse-f225d4c/GSE/API/Serialisation.lua:13-24`（普通/受保护外壳）；`GSE_Utils/Utils.lua:294-315, 434-458, 470-513, 814-833, 859-877`（数字键归一、受保护对象、集合导入、版本遍历）；`GSE/API/Storage.lua:2176-2250, 2284-2424, 2444-2452`（动作推断及六类块）；`GSE/API/Statics.lua:439-445`（块类型表）。实现与回归位于 `projects/sim2gse/gse_import.py`、`tests/sim2gse/test_interface.py`、`tests/sim2gse/test_program.py`。

## 限制

- 这 16 个真实样本中的集合 `Sequences` 均为按名称映射；没有用真实样本确认数值键 Sequences 数组的身份规则，本票不据此宣称覆盖该形态。
- 未执行游戏内导入或模拟验收；本票证据是锁定上游源码、自动化回归和公开 inspect 入口检查。

## 最高层公开入口与失败路径

最高层解析验收入口是本机页面使用的 `POST /api/gse/inspect`；它应返回所有成员、版本、原始字段和语法清单，不启动 DPS（每秒伤害）模拟。只有完整检查通过的输入才可报告解析成功。

编码、压缩、载荷、版本、字段或嵌套结构失败时，入口返回可读错误并尽可能给出成员、版本及准确字段路径。超出锁定版本或资源上限的输入须明确标记兼容性或资源限制；不得截断、跳过有问题的字段/块后继续声称完整解析。
