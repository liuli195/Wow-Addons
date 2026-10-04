# 01: 仓库根盘点与真实空间准入

**What to build:** 维护者能够对包含已识别目录链接的仓库根进行如实的完整/增量盘点，并在长期容量与额外余量未决定时使用已批准的按需生命周期动作；实际所在卷、并发承诺及每次元数据峰值仍拦截不安全写入。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] 普通根遍历报告但不跟随已识别目录链接，字节口径明确；未知重解析类型拒绝。
- [x] 显式对象、运行目录、产品工作区、恢复、隔离和删除路径继续严格拒绝链接及越界。
- [x] 长期容量、额外维护/元数据余量、保留期和频率可未设置；相关输出不伪造数值。
- [x] 所有增长和必要维护写入覆盖实际载荷与元数据峰值，保留同一锁内并发预留和所在卷检查。
- [x] 缺分包参数的归档或缺租约参数的运行明确拒绝；生产未启用和根身份不符仍拒绝。
- [x] 公开 CLI 的成功、空间不足、未知链接和初始化失败路径有同入口红绿证据；不创建真实生产配置。

## Comments

- 用户已确认门禁一；按固定基线 `86cee66129685d0a2aa6c25f99d36c17e9c92163` 在同一分支实施，仅改票01涉及的管理 CLI、合成测试、技能说明、根级 `.gitignore` 固定产物路径及本票。
- 红绿证据与逐条原始输出：`.local/repository-data-adoption/ticket01-evidence.txt`。完整与增量真实 CLI 根盘点分别先因目录 symlink 返回 code 2，再在同入口转绿；长期配置全 null 的生产合成根先因旧全局策略门槛失败，再通过 check-config、init-root、register、pin、reference、resolve，status 中各 unset 字段仍为 null；仅有1字节卷空闲但 metadata reserve 配为1时，旧逻辑错误允许 pin，补上独立SQLite写入峰值后同一 CLI 返回空间不足；根级管理产物忽略规则先失败、补固定路径后通过。
- 票01相关定向组：`pytest -q tests/sim2gse-data/test_cli.py tests/sim2gse-data/test_maintenance.py tests/sim2gse-data/test_lifecycle.py`，44 passed、2 skipped、22 subtests passed。初始化容量/物理空间失败和 POSIX 文件链接拒绝路径均在组内通过；已封口 finish 重试先核验成员/身份/outcome，再只读返回。
- 完整 `pytest -q tests/sim2gse-data`：111 passed、2 skipped、5 failed、78 subtests，83.51s。5项为当前云端 Linux 对 Windows 专用行为的覆盖失败：`msvcrt` 不可用、缺 `pwsh`、POSIX 文件句柄语义不等于 Windows、两项依赖 `ctypes.WinDLL`；票01逻辑断言未失败。Windows junction（含悬空junction）与原生文件句柄边界仍需 Windows 验收，不能将本次报告为全绿。
- 正式 `myspec/specs/` 未改；没有创建或修改真实生产配置，没有真实数据操作、提交或推送。实施完成，待主代理逐票验收；票02/03保持未修改。

- 统一审查修复：完整容量计量恢复逐目录查询运行，不物化活动运行集合；初始化可捕获错误仅回收本次独占创建且身份未变的对象，不动既有用户文件。公开CLI注入建表失败后原文件字节不变、marker/index不遗留且可重试，红绿记录为 `review-init-*`。

- 交付验收更新（2026-10-04）：本票实现与本机验收通过，统一审查及修复复核完成；最终代码a186873固定基线fast通过，正式规格已按门禁二批准应用。完整证据见[需求验收汇总](../spec.md)。远端CI、合并和非强制收尾待本机正式流程执行。
