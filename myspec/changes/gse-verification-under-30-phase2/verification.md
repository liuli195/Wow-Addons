# 当前精简候选验证记录：尚未最终验收

## 当前最终小收口证据（2026-10-25）

Astra 对 261a/tree41d4 双轴审查0阻断，指出 final_export_compilations 的真实消费者已删除、仅剩自身自测。本轮追加删除该 helper、Path 导入和**1个**普通自测（内部2次调用/断言，不是2节点），保留同文件直接调用生产 task._validate_formal_source 的另一测试；未动4真实或2迁移逻辑。

- 最新收集门禁在同2.7.1原生审计适配器下通过：**422 = 418 ordinary + 4 real**；gear仍23=21+2；所有自动入口登记且选择互补，守卫错误为空。
- 最新普通审计：**418 passed +168 subtests，3.66秒，退出0、4 worker完整、零违规**；证据 `.local/tests/gse-phase2/minimal-final-{guard.log,guard-summary.json,inventory.log}` 及审计JSONL。
- 当前精简账本仍为旧118真实中的4保留/2迁移/112删除，额外删除上述1普通自测。原416普通保留415，迁移增加3项，合计418。没有为了数量删除其它生产逻辑测试。
- 独立审查只需再核该建议落实；Windows4真实及官方43完整性能仍未验收。候选先以私有受控补丁交本机验证，不在此提前公开推送或合并。

## 261a初次精简开发证据（历史前态）

- 261a工作树在 fc696 中间提交后实施用户新范围。4 保留 / 2 迁移 / 112 删除已落代码；原 416 普通保留，迁移增加3个参数实例。
- pytest 原生收集：**423 项 = 419 普通 + 4 真实**；不增加隐藏选择、skip 或 xfail。实际四节点见 coverage.md。
- 清理前直接普通开发回归：419 pass +168 subtests，4真实 deselected，5.94秒；这不是守卫证明。
- 清理后使用云端现有 BAV **2.7.1 源内置 protected_command** 和 evidence_error，原生审计适配器实际运行 `pytest -q tests/sim2gse -m "not real" --strict-markers --dist=worksteal -n 4`：**419 pass +168 subtests，4.13秒，退出0；4 worker start/finish完整，evidence_error=null，零违规**。一次 PytestAssertRewriteWarning（xdist 已导入）不影响审计完整性。
- 适配器 SHA256：`7b412689b8020dfba993a33ba0bb3a0c433139168a385ab3920fef523392d2b6`，来自云端已存在的 plugin-migration-readonly/plugins/build-and-verify/python/build_and_verify_guard.py。未使用旧 2.3 CLI，未更改其审计规则。
- 证据：云端 `.local/tests/gse-phase2/minimal-smoke-{real-nodes.txt,unit.log,guard.log,guard-summary.json}` 和守卫 unit JSONL。该定向开发检查不是官方 CLI 全仓通过，不能证明 Windows4真实或 <30秒。
- 配置 SHA256 仍为 `c505ac85c11a4db730f955b54fcd36ab94db43decc253900476b7507800f6970`；产品、正式功能规格没有本轮变更。

## 上一正式全仓结果（历史基线，不冒充当前候选）

`4626deec00157561abed71039e4113735e8373dd` / tree `b50f144ea911ec1e578095cf7ba02ae92b65ee26`：官方完整43实际全过、0cache、17普通守卫/26真实分组完整；416+168 ordinary、118+19 real。GSE **33.05秒**，工具 **48.9808578秒**，wall **49.229秒**；local/non-diagnostic、60秒硬预算有效，无unfinished/notStarted/残留。未达到严格<30。

Windows证据 `.local/gse-phase2-full-next-70de787f96e240fea7e93f1b8a1d9370/`。经用户批准清本轮可重建临时178346016B与已解决旧失败现场190618575B，保留核心结果；此前总账约960MB。结束临时量不是持续采样的峰值，不虚报峰值。

## 更早对照与失败（保留事实）

- 原6/8完整对照均43全跑全过、0cache：6 GSE43.09 / tool53.2089958 / wall53.453；8 GSE37.61 / tool51.1566279 / wall51.406。8已采用，不重复矩阵。
- 第一整组候选 f044/tree02e848：42pass1fail，GSE37.95 / tool53.7462042 / wall54.016，不能作收益证明。失败为预建max_processes2与HTTP1导致冻结身份不同；单行归一为1且原断言全保后，唯一失败节点真实绿1pass/1.84秒。
- 用户要求的同8单组对照：main3ee前118+19全过，pytest31.76/wall32.087；5e后118+19全过，pytest29.24/wall29.575，wall少2.512秒(7.83%)。它证明当时单组改善，不是全仓<30。
- main3ee 的诊断开关/恢复修复已正常整合，未丢失；fc696旧全契约候选保留为中间成果，不继续按旧路线验证。

## 下一正式验收与清理

固定候选后独立 Astra 双轴审查，再按正式流程由 root 排队本机验证。保持外4/普通4/GSE真实8/worksteal、43项、17/26分组和60秒硬预算；官方 BAV2.7.1 `verify --project . --full --performance-report --execution-context local` 无成功缓存跳过。验收 GSE<30、tool≤51.1566279、wall≤51.406、所有剩余检查全过，无诊断/超预算/未完成。

按结构化 BAV cached/cache-hit/skip 和实际计数核零成功缓存跳过；不要把测试验证产品缓存所产生的合法 hit 或节点名 cached 当违规。正式差异门禁另按固定基线执行，不与full混传base。

每轮运行前核完整目录总账与1.7GB上限；临时置于正式规格约定的仓内目录。成功后保留日志/报告、身份、计时、清单，只清本轮allowlist内可重建大产物；失败现场先保留诊断，不清历史和正式数据。未取得本轮正式结果前不宣称完成或合并。
