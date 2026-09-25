# 09：补齐 GSE 导入语法并沉淀调研证据

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: ready

## What to build

用户从本机页面检查锁定 GSE 3.3.32 支持的导入字符串时，全部合法外壳、成员、版本、字段与控制块都能无损呈现；仓库文档能说明语法验收证据、真实样本覆盖、开源宏解析实现的可借鉴部分及许可边界。

## Blocked by

06、07（已完成）；本票补齐其后发现的导入外壳缺口，不改写历史验收记录。

## Acceptance criteria

- [ ] 对照锁定上游逐项列出普通与受保护外壳、集合成员形式、独立变量/宏对象、六类块及字段；说明语法识别、GSE 控制展开、宏解释与 DPS 的不同结果。
- [ ] 公开 `POST /api/gse/inspect` 接受集合内普通编码序列及普通编码的独立 `VARIABLE/MACRO` 对象，保持原始载荷、路径、成员身份和失败诊断；上游不接受的结构明确拒绝。
- [ ] 固定上游合成向量经公开入口核对上述新增形式；已收集 16 个原串的全部成员和版本在最终代码上复跑，真实语料与合成向量分开统计。
- [ ] 仓库文档记录外部宏解析器的具体可参考部分、适用版本、授权限制及后续边界；不复制第三方代码。

## Highest public seam and failure path

本机页面调用的 `POST /api/gse/inspect`；无法解码、非法成员、缺失依赖与超出锁定版本时返回明确位置，不把宏执行不支持写成语法解析失败。

## Comments

2026-09-25 范围修订：本票只验收 GSE 导入语法，宏命令完整解释与 12.1 邪 DK DPS 不在本票。

基础缺口的 TDD（测试驱动开发）红绿命令：`.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k decodes_unprotected_sequence_string_inside_collection`，修复前 1 failed，修复后 1 passed；`.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k decodes_unprotected_standalone_variable_and_macro`，修复前 1 failed，修复后 1 passed。两项均从公开 `POST /api/gse/inspect` 验证，不调用私有解析入口。

2026-09-25 锁定导入分派复核：基准只用 `gse-f225d4c`（GSE 3.3.32），不用较新提交。公开接口身份/类别测试红灯命令 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k "uses_inner_sequence_identity_for_plain_members or dispatches_plain_encoded_collection_members_by_object_type"`：2 failed、78 deselected；实现普通编码 pair/direct 序列的内部身份、原始显式 `MetaData.Name` 和 `objectType=VARIABLE/MACRO` 跨分类分派后，同两项 2 passed。旧数组 pair 拒绝实现经真实语料发现 `mob-guardian-01.txt` 含同形状。结构摘要是 `payload.Sequences[MOB_Guardian_Elunes]` 长度 2，第一项同名，第二项有 `MetaData.Name/GSEVersion`、`Versions`；原串未复制。按锁定 `Utils.lua:496-500` 注入的 `MetaData.Name` 属于外层数组，`:544-550` 将整张数组传给 `processWAGOImport`，`:556-575` 因数组顶层缺 `MetaData.GSEVersion` 而拒绝存储该成员。修复后 inspect 保持 `decoded`，完整保留 `raw_payload`/`raw_sequence`，显示第二项只读预览并记录 1 个 `collection_compatibility_blocks`，所有版本预检为 `unsupported`；模拟任务接口返回 HTTP 400 且不创建任务。

数组 pair 回归红灯命令 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k reports_gse_rejection_of_raw_collection_sequence_pair`：1 failed、80 deselected（公开 inspect 返回 HTTP 400）。同命令修复后 1 passed、80 deselected；另以 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k "uses_inner_sequence_identity_for_plain_members or dispatches_plain_encoded_collection_members_by_object_type or reports_gse_rejection_of_raw_collection_sequence_pair"` 复核 3 passed、78 deselected。

`Variables` / `Macros` 原始序列 table 与数组 pair 的公开入口测试先运行 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k dispatches_raw_sequence_tables_from_variables_and_macros`：1 failed、81 deselected；按通用导入路径分派后同命令 1 passed、81 deselected。用例同时把受保护变量/宏放在与载荷名不同的外层键下，确认受保护值仍按所属类别和外层键存储。

审查前历史记录：本机临时服务逐个读取忽略目录 `.local/sim2gse/gse-corpus/` 与 `.local/sim2gse/gse-corpus-additional/` 的 16 个 `.txt` 文件，分别 POST 到公开 `POST /api/gse/inspect`；终端汇总为 `{"compatibility_blocks":1,"decoded":16,"failures":[],"files":16,"members":21,"syntax":{"Action":268,"Embed":2,"If":4,"Loop":20,"Pause":2,"Repeat":30},"versions":21}`。唯一区别是上述 `MOB_Guardian_Elunes` 上游拒绝诊断；16/16 原串仍可无损检查。未保存新原串或逐文件响应；汇总证据位于 `docs/sim2gse/gse-grammar-and-macro-research.md` 本节。

审查前历史记录：聚焦套件命令 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py tests/sim2gse/test_program.py -q`：117 passed、52 个子检查通过（87.61s）。此前合成递归集合、坏编码、过深、资源总量、同名歧义及 2.2 MB 对象只计一次测试均包含在内。当前没有实机导入或 DPS 证据。

2026-09-25 独立审查修复，提交 `823d48371f6a2414ae2e4f75434543baa265c3db`：1) 对照锁定 `f225d4c` 的 `Utils.lua:484-485,509-510,531-550`，`Variables` / `Macros` 中没有 `objectType=VARIABLE/MACRO`、也不是可识别序列形状的原始 table 不再当有效变量/宏；公开 inspect 保留 `raw_payload`、原始字段和成员路径，给出兼容性阻断，并将同集合序列的模拟预检标为 `unsupported`。真实语料中 `violent-benediction-if-01.txt` 与 `wow-wide-64007-1.txt`（相同 SHA-256）各含两个此类变量；两者 inspect 均 `decoded`，模拟任务入口均 HTTP 400 拒绝，未创建任务。红灯 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py -q -k blocks_raw_variable_macro_tables_without_upstream_shape` 为 1 failed、82 deselected；修复后同命令为 1 passed、82 deselected。2) 研究文档新增不含原串的 21 行成员/版本证据表，并区分真实语料与合成向量。最终公开接口复跑为 16/16 文件 decoded、21/21 文件级成员/版本完成结构解析，15 个不同 SHA-256，5 个文件级兼容性阻断（原始 Sequences 数组 pair 1 个、重复摘要下原始变量 table 4 个）；模拟预检 19 unsupported、2 requires_character_validation。聚焦套件 `.venv/Scripts/python.exe -m pytest tests/sim2gse/test_interface.py tests/sim2gse/test_program.py -q`：118 passed、52 个子检查通过（76.56s）。当前仍无实机导入或 DPS 证据。
