---
name: sim2gse-data
description: 通过共用命令行入口盘点与管理 Sim2GSE 数据。先只读检查与预览，使用稳定身份、引用保护和明确清单控制生命周期；未启用生产策略不得改变真实历史数据。
---

# Sim2GSE 数据管理

本文件所在目录即技能根。Codex 使用本目录，Claude Code 使用指向本目录的仓库内目录联接，只有一份内容。

## 共用入口

把下面的 `<技能目录>` 替换为本技能的绝对路径，使用宿主已有 Python 3.12 或更新版本，不安装软件。数据根须显式传入绝对路径，也可通过技能外的机器配置指定；命令不依赖当前工作目录。

```text
python "<技能目录>/scripts/simdata.py" status --root "<受管数据根绝对路径>"
python "<技能目录>/scripts/simdata.py" inventory --root "<受管数据根绝对路径>" --limit 1000
python "<技能目录>/scripts/simdata.py" check-config --root "<受管数据根绝对路径>" --config "<机器配置绝对路径>" --for-write
```

第01—06票提供共用入口、登记与保护预留、事实提取、查询比较导出和不可变快照、分包归档/恢复/SQLite一致性备份、迁移/隔离/逐项删除，以及维护和禁用计划任务预览。生产启用、真实历史迁移和删除仍须另行配置及具体批准。

`inventory` 不哈希文件、不建索引，仅对显式根有界扫描；默认最多检查1000个目录项，`truncated: true` 表示部分盘点，不可当作全量容量或删除清单。`logical_bytes` 是已扫描普通文件逻辑字节，不是物理占用。`status` 不扫描整棵树，仅报告根、索引是否存在、所在卷可用空间及配置。两者不更新业务 `last_used`。

## 安装发现入口与启用生产分开

仅当用户要求两个宿主共用技能时，先预览，再显式安装仓库内联接；已有不同目录或链接必须拒绝，不覆盖、不删改。这个操作不会登记或修改数据根，不修改用户全局配置，不启用生产。

```text
python "<技能目录>/scripts/simdata.py" install-junction --repository "<仓库绝对路径>"
python "<技能目录>/scripts/simdata.py" install-junction --repository "<仓库绝对路径>" --apply
```

联接目标固定为当前仓库的 `.agents/skills/sim2gse-data`，入口为 `.claude/skills/sim2gse-data`，同目标重复安装不变更。宿主技能发现是否已刷新须另行确认，不把目录存在称为宿主已加载。

## 数据安全与配置

默认模板为 [config.default.json](assets/config.default.json)。复制模板到技能外机器配置后再商量参数；不要填入建议值或自行启用。`production_enabled` 默认关闭，容量、保留、维护频率、维护预留和元数据余量都未设置。写入仍须生产显式启用并绑定绝对数据根与 `root_id`；`check-config --for-write` 只预检这些门槛，不执行写入。

真实历史本次只能按需只读小样本，不能登记写入、迁移、压缩或删除，不全量扫描/哈希，不重打包已有归档，不安装启用计划任务。原始输入、验收/分析/模型证据、私人存档、来源不明缓存和未知引用默认保护。文件存在不表示锁占用，陈旧心跳不表示无主。

显式对象路径、运行目录、产品工作区、恢复、隔离和删除边界拒绝链接/重解析点；配置与命令指定根不一致时拒绝。普通根盘点及根容量扫描只跳过可识别的目录符号链接/目录联接，不进入目标，目标字节不计入根的逻辑字节，并报告跳过路径与数量；文件链接、悬空且类型未知的符号链接及未知 Windows 重解析标签仍拒绝。长期容量、额外维护/元数据余量、保留期与维护频率可未设置；未设容量不作虚构限额，实际卷可用空间、并发预留与操作自身的元数据峰值仍强制检查。`archive` 需要已配置分包大小；新运行及读者租约申请/续租需要租约时长。发现失败保留现场、说明具体原因，不转为成功。

## 第02票：登记与保护预留

单个标准库 SQLite（关系数据库）索引位于受管根，运行索引和机器配置不得放入技能目录。`init-root`、`register`、`reference --action invalidate`、`lease --action recover` 均先预览，执行必须带同次完整计划的 `--approve-hash`。所有命令接收绝对 `--config` 路径；登记保持原始文件位置不变。

```text
python "<技能目录>/scripts/simdata.py" init-root --config "<机器配置绝对路径>"
python "<技能目录>/scripts/simdata.py" register --config "<机器配置绝对路径>" --path "<原始文件绝对路径>" --role native
python "<技能目录>/scripts/simdata.py" begin --config "<机器配置绝对路径>" --request-id "<唯一请求>" --owner-pid <持有进程ID> --reserve-bytes <预留字节> --token "<重试时保持一致的令牌>"
python "<技能目录>/scripts/simdata.py" finish --config "<机器配置绝对路径>" --run-id "<运行ID>" --token "<令牌>" --outcome success
python "<技能目录>/scripts/simdata.py" resolve --config "<机器配置绝对路径>" --artifact-id "<文件ID>" --inspect
python "<技能目录>/scripts/simdata.py" protect --config "<机器配置绝对路径>" --artifact-id "<文件ID>"
python "<技能目录>/scripts/simdata.py" cache-references --config "<机器配置绝对路径>" --database "<旧缓存数据库绝对路径>"
```

`resolve` 默认更新应用层 `last_used`（最近业务使用时间）；`--inspect`、扫描、引用登记和哈希校验不更新它。`finish` 保存 success/failed/incomplete/censored（成功/失败/未完成/删失），同结果、同成员可重试；超预留拒绝封口。令牌和 PID（进程标识）出生身份共同验证租约持有者；心跳过期不能单独判死。`lease` 支持 status/heartbeat/release/recover-preview/recover（状态/续约/释放/恢复预览/恢复）。恢复释放预留但保留未完成原件。

`begin --path <根内绝对新目录>` 可绑定生产任务的原输出路径；省略仍使用 `runs/<ID>`。已有未绑定目录、运行路径重叠和管理目录拒绝接管。`begin --resume` 保留同请求、同路径、同令牌与原预留；先核验原持有者身份及运行锁，另一持有者只有在原进程死亡或 PID 复用后才能续领，不能把过期心跳当证明。此续领不同于核销预留的 `lease recover`。

`init-root` 预览会列出引用目标索引及 `reference_index_ready`（是否已具备）。新根同时建立索引；已有根须先预览并批准，再在根锁和事务内补齐缺失索引，不改引用内容。旧根补索引前，按至少256KiB或现有数据库页体量四倍的保守构建峰值复用容量、实际空间及并发预留检查；这不是长期容量政策。索引已存在则不重建。失败回滚，原数据保留；当前批次运行时不要执行升级。

初始化批准执行前也检查已配置容量与所在卷空间，当前固定初始化表结构预留256KiB内部峰值以覆盖索引、WAL/SHM（预写日志/共享索引）及根标记，再叠加已配置的维护和元数据余量；该内部峰值不是用户容量限额建议。未设容量时仍按真实所在卷可用空间准入。空间不足不发布根标记或索引。初始化先提交并关闭索引，再发布根标记；可捕获错误只回收本次独占创建且身份未变的索引/标记和空新根，既有文件不动。进程被强杀、身份变化或清理失败则保留现场，不能声称初始化成功。分配的持久状态允许父目录尚未创建，崩溃后可以预览批准核销预留；已存在的非目录障碍或重解析点仍拒绝，不能当成空目录。登记、pin（保留标记）、引用、resolve（解析）及租约等索引写入始终核验基于SQLite页大小/页数与编码数据估算的本次元数据峰值，另加已配置元数据余量；释放和死亡恢复不做业务限额/全树扫描准入，仅核验元数据物理空间余量，原件不删除；实际卷满时拒绝维护并保留状态。

旧缓存的WAL模式即使没有现存侧文件，也拒绝直接打开；存在非空WAL或回滚日志同样拒绝。必须先取得停写一致性备份作为适配输入，不能用 `immutable=1`（不可变连接）忽略活跃WAL。拒绝发生在连接旧缓存前，未批准预览不会创建源库的WAL/SHM文件。后续归档票负责一致性备份能力。

`pin --action add/remove --label ...` 管理保留标记；`reference --action add --owner ... --kind durable/cache/unknown` 区分持久、可撤销缓存和未知引用。缓存失效须通过预览及批准，并明确可能重算；持久引用、保留标记、未知引用和活动锁阻止失效。旧 SQLite 适配器只读 batches/reusable（批次/共享缓存）表，保留 absolute origin（绝对来源路径）与 relative artifact（相对产物路径）语义；旧消费者尚无解析接口，因此已识别路径同时建立持久兼容引用，不能据此移动旧 native.json。未识别引用保护全根。原始 SQLite 文件暂拒绝普通登记，后续归档票须用一致性备份处理 WAL（预写日志）。

测试模式仅接受系统临时目录中新建且身份绑定的根，须显式配置 `mode=test`、`root_id` 和根路径；按测试动作设置必要参数。测试中的参数不能复制为生产建议值。生产模板仍为禁用态且所有限额、保留及频率未设置。已设逻辑容量时，在同一根写锁内完整流式核算原件、数据库及 WAL、未知文件与现有预留。容量未设时不重复扫描全仓来比较不存在的限额，逻辑合计为 null；OS（操作系统）的真实卷 free（可用空间）仍包含未知占用，并始终核验完整并发未来承诺、操作/元数据峰值与额外余量。未扫描不是已审查的安全证明，显式对象及私有工作区仍严格核验；不使用截断盘点或陈旧游标作为额度依据。

## 生产任务封口

产品任务 CLI（命令行）及 HTTP（本机界面接口）共用同一个准入/恢复接口，使用明确配置与本任务载荷预留，保持原输出路径。默认禁用行为不变；已标记根内漏配置会拒绝新写入。首次输入保存先于任何模拟、晚于准入。令牌保存在任务的 `.simdata-run.json`，不登记为业务产物，也不在界面输出。

成功生产者关闭业务数据库，先保存可重试封口意图，在仍持运行锁时调用 `finish --prepare` 写入持久封口阶段，释放运行锁后再调用 `finish`。普通文件按至多1000项、至多1MiB清单的批次登记；`--limit` 可缩小登记批次以验收真实跨批。整次登记持根锁，一次完整额度准入覆盖各批元数据，每批检查真实物理余量，最终再核验成员及空间，不为每千项重复扫描全仓。输入与结果证据有保护角色；SQLite 主库作为可变来源，WAL/SHM 不冒充封口普通文件。

`finish --database <父目录/cache.sqlite3>` 声明真实共享缓存；预留比较保守计入它当前的主库和侧文件总量，不声称能精确归因本任务的净增长。任务库和共享缓存各在终态获取一次一致性映像，沿用原有备份、完整性核验和中断恢复协议；不在每个原生批次复制整库。只有同一运行令牌、封口阶段和准确来源可用于窄范围备份例外，其他活动运行仍拒绝。共享缓存可并发写，映像只承诺该事务的已提交视图。

映像中的缓存引用用现有有界适配器登记；原路径兼容引用保留。自动接入每表最多读取1000行，未知行或截断明确返回 `dependencies_complete=false` 并保留全根未知引用保护，不能据此执行 purge（永久清理）。载荷已登记、映像已核验后的运行预留可以核销；这不表示未知引用已解除。手工适配仍保留现有明确 `--limit` 上限，不增加新的固定清单字节门槛，也不自动解除旧未知或持久引用。

只有全部登记与映像核验成功后才封口并核销运行预留。`artifact_count`、`registration_batches` 报告真实数量，返回ID最多1000个并明确是否截断。中断、超预留或备份失败保留阶段和预留；恢复进入封口阶段的任务只重试登记，不重跑模拟。已封口重试核对成员与映像后只读返回；回执写入采用现有原子替换，管理端已封口而回执发布失败也可恢复。业务状态与管理状态分开，数据未封口不得在界面伪报完成。

## 第03票：事实、比较与不可变快照

```text
python "<技能目录>/scripts/simdata.py" extract --config "<机器配置绝对路径>" --artifact-id "<已登记JSON文件ID>"
python "<技能目录>/scripts/simdata.py" extract --config "<机器配置绝对路径>" --artifact-id "<原生报告ID>" --context-artifact-id "<已登记缓存行JSON文件ID>" --player-name "<多人报告中的唯一玩家>"
python "<技能目录>/scripts/simdata.py" query --config "<机器配置绝对路径>" --limit 100 --offset 0
python "<技能目录>/scripts/simdata.py" export --config "<机器配置绝对路径>" --limit 100
python "<技能目录>/scripts/simdata.py" compare --config "<机器配置绝对路径>" --left "<事实ID>" --right "<事实ID>" --axis condition.engine.controlled.version
python "<技能目录>/scripts/simdata.py" snapshot --config "<机器配置绝对路径>" --fact-id "<事实ID>" --fact-id "<另一个事实ID>"
python "<技能目录>/scripts/simdata.py" query --config "<机器配置绝对路径>" --snapshot-id "<快照ID>" --limit 100
```

`extract`（提取）只处理已封口且身份/原始SHA256匹配的JSON对象，上限16MiB，不整读更大报告。支持原生 `sim.players[].collected_data.dps`、多人报告的 `sim.statistics.raid_dps`，实际TaskStore缓存行的 `status/request/dps/samples/requested_iterations`，以及 `result.json` 的 `search_result`。不会调用TaskStore构造器、模拟器或改变诊断开关。原生多人报告须唯一选玩家，不能把个人与团队指标混用。上下文JSON须是已登记对象，实际缓存行 `sha256` 与原生报告匹配，缓存DPS和样本数也须吻合。

新提取事实schema（结构版本）为3，保留状态、失败原因、未完成/删失、请求迭代数、实际样本数及现有误差字段；样本标准差与均值误差保留原名，不互相冒充，不从摘要计算置信区间。版本3使用新的版本化事实ID，已有版本1/2事实与冻结快照不覆盖，缺少新字段视为未知。缺失为null，不补零、不编造概率或可按动作。已有原生 `action_sequence`（动作序列）记录条目数与指向原件的JSON指针，不将大轨迹复制到事实；输入尝试轨迹未记录时仍标缺失，不能把成功动作当成全部尝试。提取幂等，不更新源业务last_used；每个事实对原件和上下文建立持久引用。

比较要求实际请求种子、输入种子、迭代数、统计版本、程序、用途、按键时刻、轨迹开关及重置事件可用。trace须为布尔值，种子和迭代数须为整数；布尔值不能冒充0/1，嵌套JSON也按类型比较。完整条件通过上下文中的 `condition_details` 展开，字段严格对应 `task.py` 的条件摘要输入：fields/class_name/engine/options/config/simulation_config/cbor2/rules（角色字段/职业/引擎/选项/配置/模拟配置/依赖版本/规则）。展开的规范JSON摘要须与实际 `request.condition` 相同；这不是旧报告必有字段，也不能凭DPS或当前机器状态补造。完整展开路径同时要求已记录保真度和总预算，可比较声明为变化轴的不同引擎版本，其余条件仍核对。

实际生产缓存行没有condition_details/fidelity，仍有最小可用路径：只在双方实际 `request.condition` 的64位SHA256完全相同时，比较可核验的request字段。该摘要由现有task.py把角色、引擎、配置、模拟选项、依赖和规则共同纳入；摘要相同仅用于限制到同一冻结条件，不展开或猜测其内容。变化轴/分层仅允许request中的已记录叶字段，其余请求条件匹配。输出 `comparison_scope=same_opaque_condition`（同一不透明条件）及实际未知项，保真度标签/总预算值未记录就保持null，不声称这些数值已知；条件摘要不同拒绝跨未知条件比较。查询和快照仍保留原始缺失信息。示例：`compare ... --axis request.seed --axis request.input_seed`；模拟种子变化时须同时声明实际随之变化的输入种子，不能静默忽略。

`--axis`（变化轴）可重复，须精确到完整叶字段。每个字典键段分别按UTF-8百分号编码，字面点号编码为%2E、百分号为%25、空键为%EMPTY；点号只分隔层级，普通 `condition.engine.controlled.version` 保持兼容。例如嵌套x/y是 `condition.config.x.y`，字面键x.y是 `condition.config.x%2Ey`，两者不碰撞。实际rules中的绝对.py/.lua/.json文件名作为一个键段保留，冒号/反斜杠/空格/点号分别转义，不因正常文件名拒绝比较。未声明条件变化的错误信息给出可直接用于axis的已编码路径。其余全部条件一致，或用重复 `--stratify`（分层）明确不同口径。不同分层返回双方条件及null差值，不跨层混算；失败、删失、未完成或缺样本不计算DPS差值。原生批次与搜索汇总、不同指标不能静默混合。比较给出双方独立验证状态及三态 `validation_complete`（true/false/null），不把成功缓存样本的数值比较冒充已完成独立验证；旧事实缺少样本完整性字段时也不推定完整。

完整搜索汇总也有正向比较路径：status为completed、独立验证明确完成、partial_round明确false、停止原因为已知正常终点（no_improvement/candidate_limit/space_stalled），且没有删失/未完成反证、DPS及样本数可用时，样本汇总完整性可记录true；比较还须满足原有请求/条件/口径匹配。验证未知或未完成、轮次未知或不完整、search_deadline等预算终止不满足此证据链，继续保守返回不可比和null差值。该版本化完整性修正不重写以前冻结的事实。

保留 `search.partial_round/stop_reason/rounds/candidate_count/unique_candidates`（未完整轮/停止原因/轮数/候选数/去重候选数），以及phase/completed_batches（阶段/完成批次数）。search_deadline（搜索阶段预算终止）标为搜索范围的删失，partial_round及validation_incomplete（验证未完成）如实记录；搜索没完成不意味着此前每个DPS样本损坏，`sample_censored/sample_incomplete/sample_complete`（样本删失/未完成/完整）单独记录。成功TaskStore记录可证明已完成的缓存样本，未记录独立验证完成标记仍为unknown（未知）。`elapsed_seconds` 是实际墙钟耗时，`fight_length_seconds` 是原生战斗时长，旧seconds字段仅作为战斗时长兼容别名，不能混算。自适应搜索按实际requested_iterations与samples保留，允许32、128、512等预算和不同有效样本数，不把合法提前筛除判为损坏或强制补齐512；缺失批次数、耗时或停止原因不补零。

`query/export`（查询/导出）输出同一有界JSON页，limit最多1000，offset最多1000000，最终JSON不超过1MiB；返回has_more/next_offset（还有数据/下一页位置），超字节限制须缩小页大小。查询无磁盘scratch（临时空间），不创建输出文件或临时文件；仅使用有界内存，候选页最多1001个、每事实16KiB。创建事实或快照前，数据库增长、WAL及元数据峰值按保守增长预算准入；不以不受管临时文件绕开空间预留。需要可复现分页时使用快照ID，不能把变化中的实时分页当作冻结集合。

`snapshot`（快照）显式选择最多1000个事实，总冻结JSON最多1MiB；先预览，再携同一 `--approve-hash` 执行。预览和执行都重核所有原件/上下文来源，源变化或活动锁拒绝；同一选择内容产生同一快照ID，可幂等批准。快照在SQLite单事务内冻结事实、源身份、摘要及条件，并对所有来源直接建立持久依赖；没有修改/覆盖快照入口。随后提取新事实不会改变旧快照。查询冻结事实无需重新模拟，源文件之后的未授权修改不会悄悄重写快照事实。

## 分包归档、恢复与一致性备份

以下命令先预览；核对来源、目的、预留与配置后，重复命令并附返回的 `--approve-hash <plan_hash>`（批准计划摘要）才执行。配置模板仍未启用生产，也未替用户决定容量、分包或维护参数。

```text
python "<技能目录>/scripts/simdata.py" archive --config "<机器配置绝对路径>" --artifact-id "<已登记封口ID>"
python "<技能目录>/scripts/simdata.py" restore --config "<机器配置绝对路径>" --archive-id "<归档ID>" --destination "<受管根内不存在的新目录绝对路径>"
python "<技能目录>/scripts/simdata.py" backup-sqlite --config "<机器配置绝对路径>" --database "<受管根内SQLite绝对路径>" --request-id "<唯一备份请求>"
python "<技能目录>/scripts/simdata.py" operation --config "<机器配置绝对路径>" --operation-id "<操作ID>"
```

归档保持原件原路径可读，不刷新业务使用时间。按配置的原始片段字节上限流式写确定性tar.gz（无损压缩包），单个大文件可跨包；每包、成员和完整原字节均核对SHA-256。分包大小是未压缩有效载荷上限，tar头、填充和压缩开销另计，不承诺压缩文件恰好小于该值。发布前后核对产品身份及摘要，归档清单/分包登记并有持久引用。恢复到新目录，保留稳定ID并登记验证的位置；原路径缺失才按路径排序有界检查最多1000个登记位置，跳过确认缺失的副本，遇到身份/摘要不符、权限错误或路径边界异常直接拒绝，不跳过可疑副本选择另一个。原路径有篡改也拒绝回退。旧native.json原路径仍保留。

新写gzip显式使用6级，压缩格式及全部SHA/恢复检查不变；已封口的9级包保持原样且仍可恢复。

新归档按稳定来源和原片段顺序，把能放入同包的小片段流式共包，不为填缝重新切片；空原件仍保留一个0字节成员。每包有效载荷不超过已配置上限、成员不超过1000；格式1和读取器不变，容量预留仍按旧单片段包数保守计算。旧封口归档不重写，旧验证/发布阶段核验原产品；预留/写入阶段重试仍先保留残留再重建。

外部包须先分别登记分包和格式1清单，再用 `restore --manifest <清单绝对路径>`（恢复清单）预览。只接受有界清单、精确普通USTAR成员和连续片段，拒绝绝对路径、上级路径、设备名、链接、扩展头、重复/额外成员、缺失或损坏包、覆盖和超过声明的解压字节。当前每批至多1000个来源/包、每包至多1000个成员、清单1MiB，超过时明确分批。

SQLite原件不能作为普通封口文件登记/压缩：`backup-sqlite`先登记可变源（sealed=false，主文件摘要不代表WAL逻辑快照），使用SQLite一致性备份接口捕获已提交视图，包含WAL内提交并排除未提交事务，生成DELETE日志模式不可变映像再登记。固定读快照建立后，在创建目标映像之前核对page_count×page_size不超过批准的product_bound（映像有效载荷上界），进度检查也使用该边界；重试期间源增长超界时拒绝，不允许借用metadata总预留。管理索引自身也使用该接口，不直接复制主文件忽略WAL。相同请求ID只返回首次映像；捕获后续提交使用新的请求ID。

操作阶段为reserved/writing/verified/published/sealed（预留/写入/验证/发布/封口），每阶段持久化日志。中断不会释放预留。用同种命令 `--operation-id <ID> --approve-hash <原plan_hash>` 重试；同卷验证后才发布，拒绝以原子移动处理跨卷。未完成产品重试时转入操作私有retained隔离目录，原字节不删除；同卷隔离不节省空间，保留字节仍计预算，耗尽批准预留则拒绝继续增长。容量准入计原件、分包、临时区、恢复副本、保留产品、DB/WAL和并发预留，再留配置的元数据/维护空间。满额或磁盘不足不偷偷清理。

元数据预算单独显示 `metadata_phase_bytes/metadata_peak_bytes/retry_metadata_bytes`（各阶段/总峰值/重试元数据预留），由实际UTF-8编码计划、产品路径及字段上界、封口目录记录和阶段/隔离日志估算，并结合SQLite页面大小和索引深度上界，计入主库、WAL及索引复制/拆分页峰值。计划本身包含预算，按序列化字节固定点收敛后批准；在DDL、jobs插入及第一次阶段提交之前检查整个峰值，不能以payload固定常数替代大清单元数据。完成某阶段后，已落盘字节按实际根盘点计入，未完成阶段元数据和重试余量继续预留，不重复保留已完成阶段预算。产品清单编码不得超过批准上界。旧未封口操作缺少此预算时拒绝执行，保留状态/放弃入口；旧封口操作仍可验证解析。

`operation --action abandon-preview`（放弃预览）返回当前 `approval_hash`；核对后 `--action abandon --approve-hash <approval_hash>` 才释放未使用预留并保留全部文件。放弃不能删除数据或重新启用同一操作；永久删除仍由具体清单门槛处理。大根预算完整流式核算，不再受1000项目录准入限制；每批来源/包/清单与查询仍有界。

## 第05票：登记、迁移、隔离和逐项删除

```text
python "<技能目录>/scripts/simdata.py" legacy-register --config "<机器配置>" --directory "<受管根内旧目录>" --role native
python "<技能目录>/scripts/simdata.py" read-lease --config "<机器配置>" --action acquire --artifact-id "<ID>" --owner-pid <消费进程ID>
python "<技能目录>/scripts/simdata.py" read-lease --config "<机器配置>" --action release --lease-id "<租约ID>" --token "<令牌>"
python "<技能目录>/scripts/simdata.py" dependency --config "<机器配置>" --artifact-id "<依赖方ID>" --requires "<来源ID>" --kind durable
python "<技能目录>/scripts/simdata.py" volume-register --config "<机器配置>" --path "<另一卷内新的空目录绝对路径>"
python "<技能目录>/scripts/simdata.py" migration --config "<机器配置>" --artifact-id "<ID>" --volume-id "<卷ID，主卷省略>" --destination "<该卷内不存在的新目录绝对路径>"
python "<技能目录>/scripts/simdata.py" quarantine --config "<机器配置>" --artifact-id "<ID>"
python "<技能目录>/scripts/simdata.py" recover-quarantine --config "<机器配置>" --artifact-id "<ID>"
python "<技能目录>/scripts/simdata.py" purge --config "<机器配置>" --artifact-id "<ID>" --valid-seconds <明确批准有效秒数>
python "<技能目录>/scripts/simdata.py" purge --config "<机器配置>" --plan "<保存的完整预览JSON>" --approve-hash "<plan_hash>" --confirm-item "<ID:confirmation_hash>"
python "<技能目录>/scripts/simdata.py" safety-operation --config "<机器配置>" --operation-id "<ID>"
```

登记、卷登记、迁移、隔离与恢复先预览，再重复完整参数并附 `--approve-hash <plan_hash>` 执行。无万能yes（全部同意）开关。迁移/隔离恢复重试还附原 `--operation-id`，不能换来源、动作或配置。`safety-operation --action abandon-preview/abandon`（放弃预览/放弃）仅允许非破坏性、未封口迁移；批准其 `approval_hash` 才核销预留，复制件和临时件均保留并继续计占用。隔离和删除中断必须恢复同一具体操作，不以放弃掩盖部分变更。

旧目录登记保留UUID5稳定ID和原路径，保守建立unknown（未知消费者）兼容引用。可变SQLite主文件仅登记为未封口sqlite-source；物理主文件摘要不代表包含WAL的逻辑快照，压缩前仍须一致性备份。已识别SQLite侧文件不当成独立封口对象。未知路径、重解析点、活动运行和超界盘点拒绝登记。共享索引只有一份；新增受管卷只有身份标记，不能借卷登记接管非空未知目录。测试卷限系统临时目录或仓库 `.local/simdata-synthetic-<root_id>/` 内的专属合成目录，不影响历史树。

### 核实历史占位保护

已核实消费者的同类历史对象，可按一个既有封口归档批次使用以下动作；先预览，审核具体清单后重复同一命令并附 `--approve-hash <plan_hash>`。清单由已有成员生成，不要求逐文件手填，不依扩展名猜角色。

```text
python "<技能目录>/scripts/simdata.py" reference --config "<机器配置>" --action resolve-legacy --archive-id "<已封口归档ID>" --owner "legacy-path:<已核实的原登记目录相对路径>" --role native --consumer-status unreferenced --reason "<具体登记来源、消费者核实范围及结论>"
```

`--owner` 是操作者依据原登记记录对精确引用归属的确认；旧索引未保存引用创建来源，仅有 legacy-path 前缀不能证明自动生成。来源无法核实或实际代表真实消费者的 owner 不得选择。只处理归档内属于此精确 owner 的对象，其他同形引用也保持；通常每个原登记批次只需确认一个 owner，不逐文件手填。`unreferenced`（无消费者）或 `redirected`（已完成实际消费者转接）及 reason 是具体核实结果的声明，工具不能通过压缩成功推断此事实；仍有旧消费者读取原路径时不得作该声明。所选对象须同类，角色不一致时保持保护并重新明确批次。工具核验已封口归档原字节、当前来源身份/SHA，以及已登记且当前可核验的恢复副本。计划绑定这些记录、消费者理由、精确引用和当前保护，最多使用现有1000成员/1MiB清单上限。变更后旧计划拒绝执行。

动作只把 unknown 占位角色转为明确现有角色（或保持已有相同角色），关闭该对象路径下精确列出的自动 legacy-path unknown 占位引用；原 input/evidence/model/analysis/sqlite-source 等已明确角色不能降级。raw/native/cache 本身不是自动保护角色，唯一原始输入应使用 input/evidence。pins、真实持久依赖、缓存引用及全根 unknown_refs 均不清除；活动生产者、读者、锁及未完成操作会拒绝核实。结果如实返回剩余保护，仍有保护时原隔离/删除流程继续拒绝。

执行复用根锁、事务、实际元数据空间检查和操作审计，已识别的来源/恢复副本消费者锁持续持有至提交，同批共享祖先去重，失败不部分解除。同计划重试只报告已执行，不重新清除之后增加的保护，也不把历史结果当作当前删除许可。归档时 unknown 角色与当前分类不同时，旧归档恢复仅凭同对象/路径/SHA/大小的批准审计兼容；不修改旧包或清单。此动作不隔离或删除文件；永久删除继续使用既有具体清单和最后单独确认。全根未知来源核实、真实持久引用退役及通用角色编辑不在此入口范围内。

消费端须在读取/训练/分析前取得读者租约，业务使用更新last_used（最近使用时间），结束释放令牌。心跳过期仍保护；死亡/PID复用由操作系统出生身份核实后，recover-preview/recover（恢复预览/批准恢复）才核销。新租约拒绝未完成位置操作。依赖有向图拒绝循环，持久依赖、角色、pin（保留标记）、未知消费者和活动祖先保护向来源传递；缓存关系不能截断持久依赖链。保护目录也包含验收目录、captures/live-evidence/archive（采集/现场证据/私人存档）。

迁移总是流式copy/verify（复制/验证），在目标卷临时区核对原字节和文件身份，然后只在该卷发布并选择新位置；跨卷不移动原件。旧缓存absolute origin（绝对来源）仍可读，原文件稳定ID及last_used不改，持久引用不失效。解析先核验仍存在的原件，再核验首选位置；原件篡改、异常边界、首选位置缺失/损坏均拒绝。归档和事实提取也使用同一登记位置语义。受管卷的现有复制件、staging/quarantine（临时/隔离）、索引/WAL、保守未封口预留全部计逻辑容量；所在卷分别检查物理空间，主卷为跨卷操作保留元数据空间。全额未封口安全操作预留暂保守保留，不以同卷隔离声称释放空间。

隔离只操作已登记原路径副本，持久/未知引用、保护角色/目录、租约、锁或未明确失效的缓存均拒绝。Windows使用排他文件句柄核验原始摘要并按同一句柄移动，拒绝覆盖；保留隔离路径和身份，恢复回原路径也拒绝覆盖。只改位置状态，不删除数据或稳定ID；隔离原件后已有迁移复制件仍可解析。

永久删除仅接受隔离对象的具体保存清单，清单固定根/配置/当前身份、原始摘要、引用、隔离操作及有效期。执行要提供计划摘要及每个ID的confirmation_hash（逐项确认摘要），缺项、重复项、额外项、过期、引用或文件变化均拒绝。全部对象及排他句柄先验证，再逐项按同一已核验Windows句柄删除；逐项删除前后持久日志，中断后核对日志和隔离身份再重试，已删除路径重新出现则拒绝接管。只删除清单中的隔离副本，ID保留为墓碑，其他已登记复制位置不删除。有效时长须操作者显式给定，内部安全上限24小时；未配置任何生产默认时长、容量、保留或维护频率。实际历史永久删除仍必须先向用户展示具体清单并逐项确认，技能可发现不构成删除授权。


05审查修复增加 `purge --renew-operation <原操作ID> --valid-seconds <新有效秒数>`（重新取得当前删除批准预览）。它只读取已登记、未完成的删除操作，核验原隔离身份、已删墓碑及剩余对象的当前引用。返回绑定旧计划摘要、阶段、逐项进度的新保存清单；新计划摘要和每项确认摘要都必须重新明确批准，旧批准不能沿用。保存新JSON后仍用 `--plan/--approve-hash/--confirm-item` 执行，批准变更和核销已删墓碑在同一持久事务内记录，中断后携新清单重试。原已删路径重新出现或剩余对象受保护时拒绝；预检后、逐项日志提交前后再次检查有效期，不忽略过期继续删除。

批量迁移的自身操作豁免由保护计算传递，只豁免当前安全操作对同批来源的直接/传递操作保护；其他安全操作和旧归档操作、读者租约、角色、pins（保留标记）及未知引用仍计算。迁移保留原路径，不撤销持久引用。物理空间按OS卷身份汇总，多个登记目录共享一个未来载荷预留池；计活动运行、旧生命周期操作、安全操作、主卷元数据和维护余量。已写入的私有、身份绑定工作区载荷从未来预留抵扣，部分件重试仍需完整新复制空间，超过批准载荷保留现场并拒绝增长。verified/published（验证/发布）阶段不再写载荷；完成或明确放弃才解除相应未来预留，既有字节仍由卷可用空间及逻辑盘点计入。

## 完整盘点、增量续扫与维护

```text
python "<技能目录>/scripts/simdata.py" inventory --config "<机器配置>" --complete
python "<技能目录>/scripts/simdata.py" inventory --config "<机器配置>" --incremental --limit 1000
python "<技能目录>/scripts/simdata.py" inventory --config "<机器配置>" --incremental --limit 1000 --cursor "<上一页next_cursor>"
python "<技能目录>/scripts/simdata.py" maintenance --config "<机器配置>" --limit 100 --offset 0
python "<技能目录>/scripts/simdata.py" maintenance --config "<机器配置>" --task archive --artifact-id "<ID>"
python "<技能目录>/scripts/simdata.py" maintenance --config "<机器配置>" --task purge --plan "<具体保存JSON>" --approve-hash "<plan_hash>" --confirm-item "<ID:confirmation_hash>"
python "<技能目录>/scripts/simdata.py" schedule-preview --config "<机器配置>" --python "<已有Python绝对路径>" --start-at "<明确含时区偏移的ISO8601时间>"
```

普通根盘点、`--complete`（完整）及全仓容量核算仅跳过按文件类型/Windows 重解析标签可识别的目录符号链接与目录联接，不跟随目标，目标不计入 `logical_bytes`。报告 `skipped_directory_links_count` 与 `skipped_directory_links` 路径样本，最多列出1000条；超过时 `skipped_directory_links_truncated=true`，总数仍准确。完整核算内存与同时打开目录数仅随深度增长，上限128层；文件链接、未知重解析标签、特殊对象及目录身份变化仍拒绝，不忽略未知文件。显式对象、运行目录、产品工作区、恢复、隔离与删除等专用检查仍 strict（严格拒绝链接）。它是实时观察，不能冒充文件系统冻结快照；各代理写入通过共用锁协调，外部生产者应同样使用begin/finish。配置逻辑容量时重新核算全根及登记卷；容量未设仅保留真实卷及未来承诺准入，没有长期容量缓存。

增量页仅检查至多limit个选中项，累计文件/字节数量保存在64KiB以内的可续扫游标；每页报告本页 `skipped_directory_links_count`、`skipped_directory_links` 和 `skipped_directory_links_scope=page`，不把链接路径累积进游标。游标绑定根及未完成目录的身份/修改时间，变化则拒绝并重新开始。最多128层。为了不依赖操作系统目录枚举顺序，每页流式枚举当前目录名字、保留至多limit+1个名字；超宽目录的名字枚举可能重复，`enumerated_names`如实报告成本，不宣称每页I/O严格只有limit次。已完成目录之后可能改变，所以报告明确是live_observation_not_snapshot（实时观察而非快照），游标绝不用于预算或删除授权。没有扫描/压缩业务last_used更新，没有缓存替代未知字节。

`maintenance`（维护）默认有界状态页，无自动回收/年龄判断。显式task可选择archive/restore/backup-sqlite/migration/quarantine/recover-quarantine/purge/operation/safety-operation；所有参数直接进入同一生命周期实现和同一锁/配置/保护/预留/中断恢复协议，不另造删除脚本。先预览后批准，purge继续要求具体保存清单和每项确认，非所选动作参数拒绝。不安装后台进程。

`schedule-preview`（计划任务预览）返回禁用的Windows任务XML文本，不创建文件、不调用任务调度器、不安装启用。Python/技能/机器配置路径均为绝对路径，支持空格；最小权限、并发IgnoreNew（忽略新实例），定期动作只调用maintenance状态页。缺维护频率、任何必要策略或明确开始时间时返回unresolved及xml=null，不猜参数；有参数时任务与触发器仍禁用。真实定期数据变更须另行批准具体计划，不能把周期任务当成通用删除授权。

上线前需商量：受管根/卷及容量、保留口径和天数、维护频率/开始时间、维护及元数据余量、分包目标、租约时长、历史登记分批与来源保护、持久/缓存引用的兼容处理、迁移目的卷及恢复空间、具体永久删除清单。生产默认模板全部保持unset（未设置），不采用本机测试值。

## 验证

06审查修复：逻辑预算只用同一次完整总量扫描已计入的业务载荷字节抵扣活动run预留，不用后来扫描的新字节抵扣旧总量。计量随≤128层目录栈保存，不物化全树或活动run列表。合法producer（生产者）可在管理锁外写/截断载荷，不能把共用元数据锁当成文件系统快照；物理空间准入因此保守保留活动run整个批准载荷直到finish/release（结束/释放），可能暂时减少并发可用量。经过持有者身份/令牌、成员和载荷上限校验的finish，只在本次结束准入排除自身未来载荷，不排除其他活动运行或操作、元数据及维护空间；成功封口后才事务核销，不能借此分配新业务数据。同锁内迁移/归档的阶段抵扣及卷池语义保持。schedule-preview生成处拒绝超过744小时的Windows重复间隔（官方最大31天），不静默修改用户策略。
