# 文档索引

本目录按主题分组。移动或改名文件前先看文末「改动约定」。

## 顶层

| 文件 | 内容 |
|---|---|
| `CONTEXT.md` | 领域术语（角色级按键序列优化器、准星 HUD） |
| `environment-setup.md` | 本机环境准备（被 AGENTS.md 引用） |
| `wow-addon-development-guide.md` | 魔兽插件开发与人工智能协作指南（被 AGENTS.md 引用） |
| `README.md` | 本索引 |

## agents/

仓库协作文档，三个都**被 `AGENTS.md` 引用**：`domain.md`（领域文档约定）、`issue-tracker.md`（任务跟踪约定）、`triage-labels.md`（分拣标签约定）。

## research/

调研与结论类，跨项目通用：

- `wow-addon-debug-testing.md` — 插件调试与测试研究（2026-09-07）
- `wow-addon-ai-tools-research.md` — 插件专用人工智能工具调研（2026-09-08）
- `wow-addon-automation-research.md` — 自动化测试与调试配套方案（2026-09-17；已被 `myspec/changes/wow-addon-automation/plan.md` 引用）
- `gse-2106-spell-to-macro-rewrite.md` — 第三方插件 GSE 的 spell→macro 改写调研结论（2026-09-17）

## gear-planner/

装备规划器：

- 根：`CONTEXT.md`（术语）、`map.md`（总览，含指向下列文件的链接）、`prototype-delivery.md` / `prototype-test-coverage-review.md`（2 篇原型记录）、`issues/`（9 张票）
- `validation/`（14 篇）：13 个职业的 `*-raidbots-validation.md` + `holy-isolated-gate-validation.md`
- `research/`（8 篇）：`research-{epic-catalog,equipment-data,stat-rules}.md`、`mistweaver-{attribute-research,authoritative-rules,rule-map,minimal-fix}.md`、`healer-engine-restrictions-research.md`

## sim2gse/

按键序列优化器：`implementation-plan.md`（实施方案主文档）、`implementation-handoff.md`、`runtime-contract.md`、`action-capabilities.md`、`engine-research.md`、`gse-research.md`、`target-evidence.md`、`execution-prototype.md`、`export-prototype.md`、`terminal-flow-prototype.html`、`game-test-feedback.md`、`local-task.md`、`project-boundary-proposal.md`、`omnium-rune-data-investigation.md`。

## 改动约定

- **被外部引用的文档**（`AGENTS.md`、`myspec/`、`projects/`、`tests/`、`.build-and-verify/config.json`）：移动或改名必须同步改引用。
  当前集合：`agents/*`、`CONTEXT.md`、`environment-setup.md`、`wow-addon-development-guide.md`、`research/wow-addon-automation-research.md`、`sim2gse/implementation-plan.md`。
- 移动后核对相对链接（`scripts/dev/check.py docs` 只管编码、代码围栏和 JSON 示例，不管链接）。
- 命名统一 kebab-case（短横线命名）（`Sim2GSE_Implementation_Plan.md` 已改为 `sim2gse/implementation-plan.md`）。

## 待办（已知，未处理）

- `gear-planner/` 根下 `prototype-delivery.md` / `prototype-test-coverage-review.md` 暂留原位；若同类继续增加再分 `prototypes/`。

## 已处理（2026-09-17）

- 三篇 `wow-addon-*` 调研 + GSE 结论 → `research/`；`Sim2GSE_Implementation_Plan.md` → `sim2gse/implementation-plan.md`。
- `gear-planner/` 分层：`validation/`（14 篇验证）、`research/`（8 篇深度调研）。
- 修既有坏链：开发指南里 5 条指向本机插件缓存（`C:/Users/liuli/.codex/plugins/cache/...`）的链接改为纯文本技能名；两张 crosshair 票据的相对链接层级。
- 全仓相对链接核对：453 条，0 失效（检查方法见「改动约定」）。
