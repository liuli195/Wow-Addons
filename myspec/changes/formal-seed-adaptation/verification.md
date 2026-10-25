# 正式搜索起点适配实现与验证

## 对象和改动边界

- 基线：`cfcf8954937282053b38c641a05d06b6e413eafa`，树 `06cdc5560f640a2f4747f994cb9678ddd8b1cddd`。
- 独立云端树：`wow-addons-seed-adaptation`；分支 `codex/fix-formal-seed-adaptation`。
- 生产仅3文件：起点消费判断；共享裁剪的语法／已知成员预检；原施法序列结构和重置文本的小段提取。未更改通用按钮准入、训练排除策略、搜索评分或起点启动组装段。
- 测试仅3文件：新普通规则回归；原生目录样例将伪 `spell` 类型纠正为固定上游真实 `hostile_spell`；既有双场 HTTP（超文本传输协议）代表改用零编号／背景化原生形状（未新增真实链）。
- 固定上游 `eed909156d8eccbfca0f284cc271c080949d6a20` 的 `engine/util/util.cpp:2675–2688` 证明真实法术／攻击类型为 `hostile_spell`、`attack`、`heal_spell`、`absorb_spell`。`use`、`other`、设施及未知类型不纳入删除集合。

## 红绿过程

证据目录为本树 `.local/tests/formal-seed-adaptation/`，未提交生成日志。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 真实零编号／background 的 `native_non_button` 技能 | 红：1失败；绿：1通过 | `red-native.log`、`green-native.log` |
| 施法序列裁剪后0／1／多个成员 | 红：3失败；绿：4通过（含前一例） | `red-castsequence.log`、`green-castsequence.log` |
| 空签名值与当前正式内存评分 | 54通过、1失败（签名 None 导致 AttributeError）后修复 | `boundaries-score.log` |
| 修复后新增完整规则集 | 55通过，0.23秒 | `targeted-final.log` |
| 初次7模块普通检查 | 144通过、14失败、9子测试通过；失败均为新树缺只读Lua／GSE输入，不是产品断言 | `targeted-ordinary.log` |
| 复用固定依赖后普通全组 | 344通过、108子测试通过；122 real 项未运行，4.87秒 | `ordinary-all.log` |
| 最终普通全组复验 | 344通过、108子测试通过；122 real 项未运行，4.52秒 | `ordinary-final.log` |

最终命令：

```sh
../wow-addons-performance/.venv/bin/python -m pytest -q tests/sim2gse -m 'not real' -p no:cacheprovider --strict-markers
```

## 云端证据边界

- 新增规则测试用真实 `engine.inspect`（原生目录解释）、结构解析、canonical（规范化）、导出预检和 SQLite `:memory:` 正式搜索状态机；仅外部目标掩码／编译输出／原生评分输入为明确构造边界。没有读写正式数据、启动训练或实际原生引擎。
- 规则评分例当前结果 DPS 321／381有效样本，与来源99999不同；当前程序保留合法余部，原程序、源快照和能力目录均未修改，重复派生结果不凑起点数量。
- 云端当前最新版官方守卫不可用，父协调要求不更新云端安装。本轮直接 pytest 通过仅为普通逻辑回归，**不冒充正式守卫、Windows 全仓60秒、真实引擎或游戏验收**。
- 仅以本树 `.tools/lua-5.1.5` 和 `.tools/sim2gse-research/gse-f225d4c` 两个符号链接只读复用父树固定依赖。未复制 `.tools`、虚拟环境或 `data` 大目录；本树约22 MiB，小于516 MB授权上限。
- 此时独立审查、Windows 定向及最终正式验证尚待父协调；未合并或发布，`myspec/specs/` 无变更。后续通过证据如下，云端限制和失败历史仍保留。

## 独立审查与 Windows 正式验收（2026-10-25）

以下由父协调读取本机证据、核验后回传；云端实施者没有操作用户本机。

- GPT-6-A 独立审查范围：`cfcf8954937282053b38c641a05d06b6e413eafa..c92790d6ef753ace257adb815d0f1d7d63bc1122`。实际读取差异和日志后批准，P0／P1／P2 均0项；共享训练裁剪未新增训练禁用策略。
- 对应远端代码提交：`18bc043c40112a7bd13a05bc130e8fdf6329d5ce`；父提交 `b85afd617158533d6129778c06cfc78e44d07c2b`。云端及远端树均精确为 `de90bc35e6d076834a1ac5269d0a4e591b7d3fde`，远端分支 `codex/fix-formal-seed-adaptation` 已回读确认。
- Windows 新增普通定向55项全部通过，外层2.562秒；既有双场真实报告消费和训练安全裁剪代表2项全部通过，外层5.610秒。
- 最新官方全仓验证43检查全部通过；17普通守卫通过，无缓存、无残留。Sim2GSE 普通层344项＋108子测试通过（检查5.31秒），真实层122项＋24子测试通过（检查49.50秒）。
- **工具报告59.8889264秒，在原60秒预算内；外层墙钟60.157秒，超过60秒。** 两种计时不混用；本次工具验收通过不等于端到端外层低于60秒，不作提速或稳定低于60秒主张。
- 本机本轮新增输出230.6 MB；未修改正式数据，不重训，不合主干，不发布。

本机证据（仓库内相对路径）：

- 定向：`.local/formal-ga-development/seedfix-target-28fa298683c045d8b4e3e22b8b6c68b5/`
- 全套：`.local/formal-ga-development/seedfix-full-e902eae100464ef88ae8eeef77b5d9e6/verify.log`
- 性能：`.local/formal-ga-development/seedfix-full-e902eae100464ef88ae8eeef77b5d9e6/performance-report.json`
- 结果：`.local/formal-ga-development/seedfix-full-e902eae100464ef88ae8eeef77b5d9e6/result.json`

当前仅补充验证文档和票据状态，生产与测试保持已审、已验版本。等待父协调在另一任务的可整合点合并功能分支；没有主干合并或发布授权。
