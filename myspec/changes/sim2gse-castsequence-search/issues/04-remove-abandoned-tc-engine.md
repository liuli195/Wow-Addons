# 04: 彻底移除已放弃维护的 TC 引擎

**What to build:** 从 Sim2GSE 仓库删除 TC（旧队列对照）引擎、独立补丁、构建与调用入口、专属测试、验证排除规则、本机派生产物，以及仍要求保留 TC 的现行文档。普通 baseline（基准）与 controlled（受控）引擎继续工作。

**Blocked by:** None；先于 02、03 实施，避免 TC 继续干扰 `/castsequence` 开发。

**Status:** completed

- [x] 删除 TC 补丁、兼容锁字段、`mode='tc'` 调用和构建分支；不重新构建 TC。
- [x] 删除六项 TC 专属测试及其默认排除规则，统一验证完整运行剩余 Sim2GSE 测试。
- [x] 删除仓库内专门为 TC 存在的历史变更文件，并清理其他文档中仍把 TC 当作可选引擎的现行表述。
- [x] 精确核对并移除本机仓库内 `.tools/sim2gse/product/tc`、`.local/sim2gse/build/tc` 及 TC 专属实验派生产物；保留 baseline、controlled 和无关资料。
- [x] 搜索确认产品代码、构建配置和验证配置不再调用 TC；运行受控引擎与公开任务回归。
- [x] 在正式规格交付阶段修订 `myspec/specs/` 中旧的 TC 可选要求；在门禁二前仅存放本地规格候选。

## Comments

- 2026-09-27：用户明确决定 TC 已放弃维护，要求将其本身、构建命令和相关内容从仓库彻底清除。本票覆盖原先“停止日常构建但保留 TC”的旧决定。
- Red：`identity('tc')` 在产物清理后仍尝试读取已删除的 `build.json`，抛出 `FileNotFoundError`；Green：入口先校验模式，聚焦测试 `1 passed`，引擎测试 `8 passed`。
- 完整 Sim2GSE 回归：`227 passed, 83 subtests passed`；公开搜索任务验证真实原生评分并导出宏命令，聚焦测试 `1 passed`；测试入口清单检查通过。
- 残留核对：产品、构建、验证路径没有 TC 入口；`.tools/sim2gse` 与 `.local/sim2gse` 不再有 TC 专属命名产物。正式规格旧条款的替换预览保存在 `.local/spec-work/castsequence-tc-removal/preview/sim2gse-sequence-evaluation/spec.md`，待门禁二应用。
- 2026-09-28：引擎测试里最后一处 `identity('tc')` 示例改为普通未知模式，`test_engine.py` 8 项通过。现存 TC 字样限本票和门禁二待替换的旧正式规格；已删除引擎、构建路径和运行产物没有恢复。
- 2026-09-28：门禁二已确认；MySpec（自有规格）原子应用了完整预览，删除旧 TC 可选要求并明确仅支持 baseline/controlled；`myspec validate-main` 通过。
