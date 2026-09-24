# 01：收集样本并查看导入结构

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

用户提供公开 GSE 导入字符串后，能够得到经过边界检查的序列、版本、语法特征与准确错误；用多条真实样本记录版本和语法覆盖证据。

## Blocked by

无，当前开发授权已具备。

## Acceptance criteria

- [x] 多条真实原串优先覆盖 12.1 邪恶死亡骑士及已找到的主要语法；六类块的完整矩阵由真实导入串和明确标注的固定上游合成向量共同验证。记录来源、版本、摘要和授权边界，并单独保留真实 Pause/Embed 原串缺口。
- [x] 单序列、集合和上游支持的直接序列对象可解码，保留全部版本和源路径，畸形/超限/不支持的格式返回可读错误。
- [x] 公开导入检查入口与锁定 GSE 3.3.32 编译器核对，不把成功解码报告为可模拟。
- [x] 任务入口级失败及样本矩阵回归通过。

## Completion evidence

完成证据（2026-09-24）：收集入口刷新得到 9 条公开真实导入串，其中 6 条 DK（死亡骑士）串（Søl 2、Flip 2、MOB Unholy 1、MOB Blood 1），MOB Unholy 一条集合串含两个序列成员；另有 2 条作者标注适用 12.1。单体、集合及多版本成员均保留来源、GSE 版本和 SHA-256。真实原串覆盖 Action、Loop、Repeat、If；完整六类块矩阵由这些真实导入串与明确标注的固定上游合成 Pause/Embed 向量共同验证，合成向量只证明固定上游语法处理能力，不计作真实样本。真实 Pause 与 Embed 原串仍缺，作为明确的语料覆盖限制记录。页面检查测试覆盖单体/集合、直接对象外壳、损坏尾随数据、4 MiB 解压上限、32 层深度/10000 节点上限和 GSEVersion 逐成员兼容标记。

红绿证据：`test_import_inspection_accepts_direct_sequence_object` 从 HTTP 400 转为 decoded；`test_upstream_compiles_direct_sequence_object_shell` 首次因上游适配器无法取序列而失败，修正后通过并得到 `outbreak` 一步；`test_import_rejects_gse_version_newer_than_locked_upstream_before_compiling` 先确认 GSEVersion 3333 会继续运行编译器，加入锁定版本守卫后通过且上游命令未运行。定向接口边界为 4 passed、2 个子检查通过；此前 Sim2GSE 定向全组为 127 passed、41 个子检查通过。

语料覆盖限制：已检查维护者 Pause 讨论关联的帖子 18312、35227，以及后续候选 37781、36270、32673、31200、26914，均未发现可提取的 `!GSE3!` 原串；现有 12 条收集源共有 9 条可解码结果，真实原串没有 Pause/Embed。按需求中“最好覆盖全部语法”及本票“主要语法 + 六类矩阵”的范围，本票通过固定上游合成向量验证这两类处理能力，并明确保留真实来源缺口；不得将合成向量描述为真实覆盖。
