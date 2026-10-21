# 03：轻量曲线诊断与性能验收

Status: in-progress（最终实现与定向功能通过；严格性能门禁证据不足，待正式验证）
Blocked by: 性能验收证据不足及正式 Windows 验证（A 固定 c481455；最终 B/C 固定 5b302de）

## What to build

提供独立默认关闭的曲线配置和CLI覆盖，记录真实墙钟下已有DPS事件，结束后离线生成10秒采样及同图对照；复用已有原生伤害时间桶，不增加评分。

## Acceptance criteria

- [ ] 正式搜索和预训练共享配置，显式参数优先，诊断参数不改变评分/缓存身份。
- [ ] 默认不加载采集器、不产事件或图文件、不做额外模拟；开启不扣时间、不启全量追踪或定时线程。
- [ ] 成绩修订/首次结果/停止/失败/取消/恢复/截断如实表示，绘图在业务搜索结束后。
- [ ] 支持同口径多运行比较；战斗伤害桶单独标识原生统计，不叠加已含宠物伤害，缺失不补跑。
- [ ] 复用标准库与既有能力，无新的实时框架/绘图库/数据库。
- [ ] 固定工作量及必要限时三臂性能对照，原始数据/噪声/适用平台明确，未达检测能力不得记无退化。
- [ ] 更新独立曲线与原详细诊断总开关的规格候选，不提前写正式规格。
- [ ] 独立审查及准确的正式验证状态，实验不冒充全仓通过，不自动合并发布。

## Comments

2026-10-21：先使用原生已存在的timeline_dmg，避免另加战斗采集体系。


2026-10-21 最终实施与功能证据：
- 票 03 初始实现 `4299531`，比较条件修复 `5b302de`；测试 patch 隔离修复 `de5ceeb`。两个探索开关及新早停语义保持不变，未修改 native、sequence.py、engine.py 或结果存储格式。
- 独立 `search_timeline` 配置及正反 CLI 已接任务、恢复、服务、双场与训练。默认不加载模块、不取曲线时钟、不产事件或文件；开启只取已有成绩，采集器不入检查点，业务结束后导出有界 JSON 和静态 HTML/SVG。
- 审查后的两轴修复均有公开链红/绿证据：时间轴起于异步公开调用，准备及排队等待不隐藏；比较轴复用冻结角色 SHA、引擎身份、模拟配置及输入间隔/reset/burst 等物理条件，算法开关和随机种子只作标签。同角色不同算法可同图，不同角色同目标不能自动合图；准备失败、未知条件各自独立。
- 9 项新用例覆盖 task.main/run_task→read/resume、默认 OFF 防线和业务等价、离线多文件分组、10.001 秒边界、取消恢复、成绩向下修订、截断、导出失败不覆盖业务/原异常、现有伤害桶和上述两轴修复。另复用训练 CLI 2 个参数化用例、HTTP 双场 1 个用例；最终共 **12 passed in 8.22s**，日志 `.local/spec-work/search-closeout/03-physical-groups-final.log`。
- `task.main curves --damage` 仅复用已有报告，核验固定原生 manifest 后读取玩家已含宠物的 1 秒桶，不再叠加 stats_pets；标为原生分桶伤害统计而非评分 DPS。缺桶、未知来源/桶宽或多玩家不明确均说明不支持，不补模拟。
- 功能测试的原生外部边界为构造数据，不能当真实性能或 Windows 验证。POSIX 实锁 wrapper 和 conftest 使用临时数据中心；未写正式数据。旧测试仅迁移默认关闭后的必要前提；既有 scoped-checkpoint 等失败保留原断言及基线复现证据，没有改业务掩盖，全仓并非全绿。
- 正式规格修订候选为 `.local/spec-work/search-closeout/03-lightweight-diagnostics-spec-candidate.md`：详细 `diagnostic_logging` 总开关不控制独立曲线。未修改 `myspec/specs/`。

2026-10-21 真实 Linux 性能证据（严格门禁未证明通过）：
- A=`c481455`，最终 B/OFF、C/ON=`5b302de`；真实受检 Linux SimC/Lua、同角色和种子、独立进程/临时数据中心，最小 subprocess + POSIX lockf runner，不改产品 Windows 支持。计量公开 run_task 全墙钟，包含导出；准备及进程启动另计，但完整子进程耗时全部计入 600 秒预算。
- 看最终版数据前固定 36 个 ABC 配对终点，ABC/BCA/CAB 均衡。108 次全部完成，每对候选、评分、样本、请求及 native 评分批次指纹一致，无丢样或不完整对。每臂 6 候选、1 轮，随种子为 11/13/15 个评分批次。
- 最终版 457.203 秒，加旧版和 pilot 124.437 秒，累计 **581.640/600 秒**；已停止，无扩测或额外 60 秒级限时场景。最终版快照准备另为 0.059 秒。
- 配对算术耗时变化均值/单侧 95% 上界：**B/A −2.791% / +1.188%（门禁 0.5%）；C/B −0.985% / +1.486%（门禁 1%）**。保守配对 t 区间；同时保留几何口径上界 +0.328% / +1.313%，最终取较保守值，不能挑口径宣称通过。均值为负不等于提速，上界超门禁也不等于已证明退化；结论为检测能力不足，不能严证无退化。
- 全部墙钟样本保留，单次范围 3.350–7.473 秒。A/B 无曲线文件；C 每次 11–13 事件，JSON+HTML 合计 5,820–6,295 字节。资源及完整统计见 `.local/performance/search-timeline-final/final-analysis.json`，短报告见同目录 `REPORT.md`，原始数据见 ledger 与各 measurement.json。
- 旧 B/C=`4299531` 的 10 对在 `.local/performance/search-timeline-closeout/` 单独保留；几何上界 B/A +3.604%、C/B +4.149%，均未通过。旧 6 对中途暂过不作最终证据，不与新版本混池。旧阶段下一 worker 在 native 前退出 75 是已批准的配对边界暂停，不是业务故障。
- 独立审查、正式 Windows 锁/JobObject 及真实入口链、全仓状态由主代理统一确认；本票不自动合并、发布、扩大预算或放宽门禁。

可复用定向功能命令（仓库根目录；不启动性能测试）：

```sh
DATA_STORE_TEST_SKILL="$PWD/../cloud-skills/managed/skills/data-store" .venv/bin/python .local/spec-work/pytest-posix.py tests/sim2gse/test_search_timeline.py tests/sim2gse/test_seed_training.py::test_closeout_default_training_preserves_material_without_selector tests/sim2gse/test_interface.py::InterfaceTests::test_dual_freezes_one_rule_pack_even_when_file_changes_between_scenes -q
```

Windows 使用本机已有的隔离 data-store 测试 skill，保持同一组测试，入口替换为 `.venv\Scripts\python.exe -m pytest`，不使用 POSIX wrapper；这是定向功能验证，不替代真实 native 链及平台取消验收。
