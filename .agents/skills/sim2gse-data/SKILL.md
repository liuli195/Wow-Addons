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

当前第01票提供只读盘点、状态、配置预检及目录联接入口；登记与其他生命周期命令按后续票据实现后更新说明。未支持的命令显式失败，不能声称已具备能力。

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

## 验证

```text
python -B -m unittest discover -s "<技能目录>/scripts/tests" -p "test_*.py" -v
```

自测仅使用临时合成数据和临时仓库，不使用真实历史；统一仓库验证登记同一测试入口。测试结果和未运行项分别报告，见 [第01票验证记录](references/validation-01.md)。
