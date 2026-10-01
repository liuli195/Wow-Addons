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

## 验证

```text
python "<技能目录>/scripts/tests/test_cli.py"
```

自测仅使用临时合成数据和临时仓库，不使用真实历史；统一仓库验证登记同一测试入口。测试结果和未运行项分别报告，见 [第01票验证记录](references/validation-01.md)。
