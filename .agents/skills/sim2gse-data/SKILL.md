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

当前第01—04票提供共用入口、登记与保护预留、事实提取、查询比较导出和不可变快照，以及分包归档、恢复和SQLite一致性备份。迁移清理及维护按后续票据实现后更新说明；未支持的命令显式失败。

`inventory` 不哈希文件、不建索引，仅对显式根有界扫描；默认最多检查1000个目录项，`truncated: true` 表示部分盘点，不可当作全量容量或删除清单。`logical_bytes` 是已扫描普通文件逻辑字节，不是物理占用。`status` 不扫描整棵树，仅报告根、索引是否存在、所在卷可用空间及配置。两者不更新业务 `last_used`。

## 安装发现入口与启用生产分开

仅当用户要求两个宿主共用技能时，先预览，再显式安装仓库内联接；已有不同目录或链接必须拒绝，不覆盖、不删改。这个操作不会登记或修改数据根，不修改用户全局配置，不启用生产。

```text
python "<技能目录>/scripts/simdata.py" install-junction --repository "<仓库绝对路径>"
python "<技能目录>/scripts/simdata.py" install-junction --repository "<仓库绝对路径>" --apply
```

联接目标固定为当前仓库的 `.agents/skills/sim2gse-data`，入口为 `.claude/skills/sim2gse-data`，同目标重复安装不变更。宿主技能发现是否已刷新须另行确认，不把目录存在称为宿主已加载。

## 数据安全与配置

默认模板为 [config.default.json](assets/config.default.json)。复制模板到技能外机器配置后再商量参数；不要填入建议值或自行启用。`production_enabled` 默认关闭，容量、保留、维护频率、维护预留、分包目标都未设置。`check-config --for-write` 只检查，不执行写入。

真实历史本次只能按需只读小样本，不能登记写入、迁移、压缩或删除，不全量扫描/哈希，不重打包已有归档，不安装启用计划任务。原始输入、验收/分析/模型证据、私人存档、来源不明缓存和未知引用默认保护。文件存在不表示锁占用，陈旧心跳不表示无主。

数据路径拒绝链接/重解析点，配置与命令指定根不一致时拒绝。未配置不等于无限容量；生产未启用或策略不完整时写入预检失败。发现失败保留现场、说明具体原因，不转为成功。

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

初始化批准执行前也检查容量与所在卷空间，当前固定初始化表结构预留256KiB内部峰值以覆盖索引、WAL/SHM（预写日志/共享索引）及根标记，再叠加用户配置的维护和元数据余量；该内部峰值不是用户容量限额建议。空间不足不发布根标记或索引。分配的持久状态允许父目录尚未创建，崩溃后可以预览批准核销预留；已存在的非目录障碍或重解析点仍拒绝，不能当成空目录。释放和死亡恢复不做业务限额/全树扫描准入，仅核验元数据物理空间余量，原件不删除；实际卷满且无余量时拒绝维护并保留状态。

旧缓存的WAL模式即使没有现存侧文件，也拒绝直接打开；存在非空WAL或回滚日志同样拒绝。必须先取得停写一致性备份作为适配输入，不能用 `immutable=1`（不可变连接）忽略活跃WAL。拒绝发生在连接旧缓存前，未批准预览不会创建源库的WAL/SHM文件。后续归档票负责一致性备份能力。

`pin --action add/remove --label ...` 管理保留标记；`reference --action add --owner ... --kind durable/cache/unknown` 区分持久、可撤销缓存和未知引用。缓存失效须通过预览及批准，并明确可能重算；持久引用、保留标记、未知引用和活动锁阻止失效。旧 SQLite 适配器只读 batches/reusable（批次/共享缓存）表，保留 absolute origin（绝对来源路径）与 relative artifact（相对产物路径）语义；旧消费者尚无解析接口，因此已识别路径同时建立持久兼容引用，不能据此移动旧 native.json。未识别引用保护全根。原始 SQLite 文件暂拒绝普通登记，后续归档票须用一致性备份处理 WAL（预写日志）。

测试模式仅接受系统临时目录中新建且身份绑定的根，须显式配置 `mode=test`、`root_id`、容量与各项余量；测试中的参数不能复制为生产建议值。生产模板仍为禁用态且所有限额、保留及频率未设置。每次增长同时核算原件、数据库及 WAL、现有预留、维护余量、元数据余量和卷可用空间；满额拒绝增长。当前预算核验上限为 1000 个目录项，超限明确拒绝写入，不能把截断盘点用于容量承诺；规模化容量核算仍须在后续生命周期票完成。

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

外部包须先分别登记分包和格式1清单，再用 `restore --manifest <清单绝对路径>`（恢复清单）预览。只接受有界清单、精确普通USTAR成员和连续片段，拒绝绝对路径、上级路径、设备名、链接、扩展头、重复/额外成员、缺失或损坏包、覆盖和超过声明的解压字节。当前每批至多1000个来源/包、清单1MiB，超过时明确分批。

SQLite原件不能作为普通封口文件登记/压缩：`backup-sqlite`先登记可变源（sealed=false，主文件摘要不代表WAL逻辑快照），使用SQLite一致性备份接口捕获已提交视图，包含WAL内提交并排除未提交事务，生成DELETE日志模式不可变映像再登记。固定读快照建立后，在创建目标映像之前核对page_count×page_size不超过批准的product_bound（映像有效载荷上界），进度检查也使用该边界；重试期间源增长超界时拒绝，不允许借用metadata总预留。管理索引自身也使用该接口，不直接复制主文件忽略WAL。相同请求ID只返回首次映像；捕获后续提交使用新的请求ID。

操作阶段为reserved/writing/verified/published/sealed（预留/写入/验证/发布/封口），每阶段持久化日志。中断不会释放预留。用同种命令 `--operation-id <ID> --approve-hash <原plan_hash>` 重试；同卷验证后才发布，拒绝以原子移动处理跨卷。未完成产品重试时转入操作私有retained隔离目录，原字节不删除；同卷隔离不节省空间，保留字节仍计预算，耗尽批准预留则拒绝继续增长。容量准入计原件、分包、临时区、恢复副本、保留产品、DB/WAL和并发预留，再留配置的元数据/维护空间。满额或磁盘不足不偷偷清理。

元数据预算单独显示 `metadata_phase_bytes/metadata_peak_bytes/retry_metadata_bytes`（各阶段/总峰值/重试元数据预留），由实际UTF-8编码计划、产品路径及字段上界、封口目录记录和阶段/隔离日志估算，并结合SQLite页面大小和索引深度上界，计入主库、WAL及索引复制/拆分页峰值。计划本身包含预算，按序列化字节固定点收敛后批准；在DDL、jobs插入及第一次阶段提交之前检查整个峰值，不能以payload固定常数替代大清单元数据。完成某阶段后，已落盘字节按实际根盘点计入，未完成阶段元数据和重试余量继续预留，不重复保留已完成阶段预算。产品清单编码不得超过批准上界。旧未封口操作缺少此预算时拒绝执行，保留状态/放弃入口；旧封口操作仍可验证解析。

`operation --action abandon-preview`（放弃预览）返回当前 `approval_hash`；核对后 `--action abandon --approve-hash <approval_hash>` 才释放未使用预留并保留全部文件。放弃不能删除数据或重新启用同一操作；后续永久删除仍由票05具体清单门槛处理。当前1000项目录盘点对大根明确拒绝增长，完整框架交付前由票06增量盘点解除该实现限制。

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

消费端须在读取/训练/分析前取得读者租约，业务使用更新last_used（最近使用时间），结束释放令牌。心跳过期仍保护；死亡/PID复用由操作系统出生身份核实后，recover-preview/recover（恢复预览/批准恢复）才核销。新租约拒绝未完成位置操作。依赖有向图拒绝循环，持久依赖、角色、pin（保留标记）、未知消费者和活动祖先保护向来源传递；缓存关系不能截断持久依赖链。保护目录也包含验收目录、captures/live-evidence/archive（采集/现场证据/私人存档）。

迁移总是流式copy/verify（复制/验证），在目标卷临时区核对原字节和文件身份，然后只在该卷发布并选择新位置；跨卷不移动原件。旧缓存absolute origin（绝对来源）仍可读，原文件稳定ID及last_used不改，持久引用不失效。解析先核验仍存在的原件，再核验首选位置；原件篡改、异常边界、首选位置缺失/损坏均拒绝。归档和事实提取也使用同一登记位置语义。受管卷的现有复制件、staging/quarantine（临时/隔离）、索引/WAL、保守未封口预留全部计逻辑容量；所在卷分别检查物理空间，主卷为跨卷操作保留元数据空间。全额未封口安全操作预留暂保守保留，不以同卷隔离声称释放空间。

隔离只操作已登记原路径副本，持久/未知引用、保护角色/目录、租约、锁或未明确失效的缓存均拒绝。Windows使用排他文件句柄核验原始摘要并按同一句柄移动，拒绝覆盖；保留隔离路径和身份，恢复回原路径也拒绝覆盖。只改位置状态，不删除数据或稳定ID；隔离原件后已有迁移复制件仍可解析。

永久删除仅接受隔离对象的具体保存清单，清单固定根/配置/当前身份、原始摘要、引用、隔离操作及有效期。执行要提供计划摘要及每个ID的confirmation_hash（逐项确认摘要），缺项、重复项、额外项、过期、引用或文件变化均拒绝。全部对象及排他句柄先验证，再逐项按同一已核验Windows句柄删除；逐项删除前后持久日志，中断后核对日志和隔离身份再重试，已删除路径重新出现则拒绝接管。只删除清单中的隔离副本，ID保留为墓碑，其他已登记复制位置不删除。有效时长须操作者显式给定，内部安全上限24小时；未配置任何生产默认时长、容量、保留或维护频率。实际历史永久删除仍必须先向用户展示具体清单并逐项确认，技能可发现不构成删除授权。

票06尚负责维护入口、计划任务配置生成/预览，以及解除1000项目录预算准入限制；当前不能宣称大规模框架最终验收完成。05验证记录见 [validation-05.md](references/validation-05.md)。

## 验证

```text
python -B -m unittest discover -s "<技能目录>/scripts/tests" -p "test_*.py" -v
```

自测仅使用临时合成数据和临时仓库，不使用真实历史；统一仓库验证登记同一测试入口。测试结果和未运行项分别报告，见 [第01票验证记录](references/validation-01.md)。
