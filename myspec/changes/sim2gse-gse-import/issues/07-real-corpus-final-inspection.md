# 07：补充真实语料并逐成员逐版本复跑

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

补充公开真实 GSE 原串，并在最终代码上把已收集的每条原串交给公开导入检查入口，逐个核对所有成员和版本。真实来源与固定上游合成向量分开登记、统计和报告。

## Blocked by

06：无损解析锁定 GSE 3.3.32 的全部导入语法。

## Acceptance criteria

- [x] 以现有清单为起点继续寻找真实 Pause（暂停）与 Embed（嵌入）原串，并补足其他明显的作者写法缺口。新增原串原样保存，记录来源、原帖标注的游戏版本、GSE 版本、SHA-256、成员及其全部版本和实际观察到的语法；只保存获准再分发的原文，其他原文按仓库规则留在忽略目录。
- [x] 对最终代码可用的全部已收集真实原串，逐条通过公开导入检查入口；对每条原串的每个成员和每个版本，记录完整解析结果及通过/失败状态。不得抽样代替全量复跑。
- [x] 验收报告列出每条原串摘要、来源、外层格式、成员、版本、语法和检查结果；真实样本、固定上游合成向量及游戏内证据分别统计。
- [x] 找到真实 Pause 与 Embed 原串；固定上游合成向量单独统计，不抵作真实语料或游戏内验收。
- [x] 全部已收集原串、成员及版本均解析成功；没有需要阻断或转用户判断的解析失败。

## 最高层公开入口与失败路径

最高层语料复跑入口是本机页面所用的 `POST /api/gse/inspect`，每条原串单独提交并保存响应。回归同时核对该响应列出的全部成员和版本，不能只调用内部解码函数或只验证集合中的首个成员。

入口拒绝、成员/版本缺失、语法清单不全或原字段有损均算失败；报告保留 HTTP 错误、摘要、成员、版本及错误位置。原始样本无法重新取得时记录来源与摘要并单列，不得伪造样本内容或把合成向量记入真实样本通过数。

## 最终验收记录（2026-09-25）

- **语料**：16 个本机文件、15 个不同 SHA-256、1 个重复文件；检查 21 组文件级成员/版本，按原串 SHA 去重后为 20 组。外层格式、来源、日期、摘要、成员、版本和语法清单见 Git 忽略目录 `.local/sim2gse/gse-corpus-inspection/corpus-manifest-2026-09-25.json`；原串不提交到 Git。
- **公开解析**：16/16 文件分别 POST 到 `/api/gse/inspect`，HTTP 200 且 `decoded`；21/21 文件级成员/版本均返回。`collection_compatibility_blocks` 为 0，原始语法清点与返回的全部 `syntax_locations` 一致，没有未列出的路径或解析失败。
- **真实语法覆盖**：Action 268、Loop 20、Repeat 30、If 4、Pause 2、Embed 2。真实 Pause 来自 Wowlazymacros 的 DrussRet 原串；两条 Jafoweb 原串经 CBOR 解码后均在 `Sequences[Jafo_Master].Versions[1].Actions[2][7]` 返回 `Type=Embed`。第一条引用集合外的 `MPB`，第二条导入集合内含 `MPB`。
- **已知解析警告**：唯一 warning 是 DrussRet `DRUSS_ST_v6` v1 缺少 `Actions` 数组，路径 `Sequences[DRUSS_ST_v6].Versions[1].Actions`。数值块在解析的 raw/parsed 字段中保留；该版解析成功，但不能模拟。
- **解析与模拟分开**：21 组版本的模拟门禁状态为 19 `unsupported`、2 `requires_character_validation`；inspect 响应全部 `simulation_started=false`。这不是解析失败，也不是 DPS 结果。本票没有执行 DPS 或游戏内验收；固定上游合成向量单独统计，不计入以上真实语法计数。
- **完整证据**：逐文件完整公开响应（包括 raw/parsed 字段、警告、语法路径和 preflight）在 `.local/sim2gse/gse-corpus-inspection/final-2026-09-25.json`；可读报告在同目录 `report-final-2026-09-25.md`。完整原串仅保存在忽略目录。
- **门禁校验**：从本机文件复核 SHA-256、16 个保存响应的 `raw_import` 和状态、21 组成员版本、全部语法路径与门禁汇总；未发现校验差异。
