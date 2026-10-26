# GSE 最简候选验证记录：87b 正式全仓已通过

## 正式验收结果（2026-10-25）

固定候选 `87bce49de64060b10a001d61d2a63f6b0cf7d300`，tree `6d693c873380c29e295335253f34cf3cbe4d1ba2`，由本机当前官方 BAV 2.7.1 执行 `verify --project . --full --performance-report --execution-context local`：

- **43项全部实际通过，0成功缓存跳过**；17普通守卫/26真实分组完整，unfinished、notStarted和残留进程均为0。
- GSE **418普通＋168子测试、4真实＋2子测试全部通过**。4条核心实际依赖均执行，不以替身冒充原生/浏览器/物理边界。
- GSE真实 **17.48秒**，工具总时 **39.5877264秒**，实际墙钟 **39.858秒**；外4/普通4/GSE真实8/worksteal不变，local、非诊断、60秒硬预算有效。
- 严格GSE<30已达到，工具与实际总时均优于原8路完整基线51.1566279/51.406秒。此结果仅绑定87b，不替代后续Top5候选的正式验收。
- CrosshairHUD既存UTF-8线程警告仍出现，该组通过；不将警告改写成无警告。
- Windows原始证据：`.local/gse-minimal-full-4ea68b5f02de49ea8e62e9f625b48fb3/`。本轮结束时119910327字节可重建临时已按来源allowlist清理，保留核心证据约33.5KB；当时历史账本约965MB。结束临时量不是持续采样峰值。

Astra对精简候选双轴审查及最后P3/文案增量收口均无未解决阻断。性能与保留测试已验通过，但完整第二门禁、正式规格政策对齐和合并仍由root统一处理，不能把此记录当作已经合并。

## 实际传输与恢复身份

曾拟私有Library补丁交本机；Windows官方helper因`os.setxattr`缺失未能物化，正常重试后目标文件仍未落地，未安装、未应用该补丁。实际成功路径是已授权功能分支Git整批同步到87b，本机正常fetch/快进、核同tree后正式验证。后续仓库跟踪文件只走Git功能分支整批同步，不把Library作为替代通道。

后续云端恢复为同路径独立浅clone，核准87b/tree6d693c。此前未推送的纯文档提交678不在当前对象库；本记录按root本机只读回核的上述正式证据重新整理，不声称恢复了678对象或原云端`.local`文件。原云端证据路径在下文保留为历史记录，不冒充当前恢复区存在的文件。

## 最终小收口开发证据（历史前态）

Astra 对 261a/tree41d4 双轴审查0阻断，指出 final_export_compilations 的真实消费者已删除、仅剩自身自测。本轮追加删除该 helper、Path 导入和**1个**普通自测（内部2次调用/断言，不是2节点），保留同文件直接调用生产 task._validate_formal_source 的另一测试；未动4真实或2迁移逻辑。

- 最新收集门禁在同2.7.1原生审计适配器下通过：**422 = 418 ordinary + 4 real**；gear仍23=21+2；所有自动入口登记且选择互补，守卫错误为空。
- 最新普通审计：**418 passed +168 subtests，3.66秒，退出0、4 worker完整、零违规**；证据 `.local/tests/gse-phase2/minimal-final-{guard.log,guard-summary.json,inventory.log}` 及审计JSONL。
- 当前精简账本仍为旧118真实中的4保留/2迁移/112删除，额外删除上述1普通自测。原416普通保留415，迁移增加3项，合计418。没有为了数量删除其它生产逻辑测试。
- 当时尚待独立审查建议落实和Windows正式验收；后续均按本页开头记录完成。私有补丁未落地，最终通过Git同步验证，不提前合并。

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

## 已采用的验收与清理口径

固定候选经独立 Astra 双轴审查，再由 root 排队本机验证。保持外4/普通4/GSE真实8/worksteal、43项、17/26分组和60秒硬预算；官方 BAV2.7.1完整模式无成功缓存跳过。87b已满足GSE<30、tool≤51.1566279、wall≤51.406、所有剩余检查全过，无诊断/超预算/未完成。

按结构化 BAV cached/cache-hit/skip 和实际计数核零成功缓存跳过；不要把测试验证产品缓存所产生的合法 hit 或节点名 cached 当违规。正式差异门禁另按固定基线执行，不与full混传base。

本旧任务按已批准1.7GB上限核完整目录总账；临时置于正式规格约定的仓内目录。成功后保留日志/报告、身份、计时、清单，只清本轮allowlist内可重建大产物；不清历史和正式数据。该旧预算不延伸到后续Top5新任务，后者按其独立门禁与单操作15分钟/516MB规则执行。正式通过不等于第二门禁已批准或已经合并。
