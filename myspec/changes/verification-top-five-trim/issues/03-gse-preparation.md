# 03：GSE四核心不变的准备与组合精简

**What to build:** 保留已验四条真实核心，避免与被测功能无关的结果中心准备，缩减页面诊断和退役设置的重复交叉，同时明确留下的代表性拒绝与页面操作。

**Blocked by:** None（技术独立，可在完整Gate1确认后与另外两票并行；共享Git和最终验证由root串行）

**Status:** ready-for-agent

**Execution:** technically complete, delivery pending — 三票代码独审与文案增量已收口；b18/tree560088的Windows正式43项全过、0成功缓存跳过。8×2后续实验亦43项全过；用户已明确保留，官方配置已保存于42eb6c8并核对一致。正式规格应用、PR、合并及安全清理仍待完整第二门禁。

## 实施边界与所有权

- 仅编辑 tests/sim2gse/conftest.py、tests/sim2gse/test_interface.py、tests/sim2gse/test_retired_capabilities.py。
- **所有real测试仍保留各自DATA_ROOT指向临时目录的隔离，不能删除这层保护。** 仅安装副本复制/数据中心API加载改为按需：真实浏览器显式请求；接入节点继续显式使用真实安装副本、自行连接独立项目；原生比较/进程所有权不为无关安装/加载付费。不按函数名造特判框架。
- 四真实节点的核心引擎、HTTP、编译、物理中心、剪贴板、所有权边界不变；诊断页面组合仅裁重复，保可操作开关和任务/恢复请求代表。
- 退役11键×4入口的44实例改为硬编码11键在一个公共入口各核一次，加其余3入口各一个代表，共14；禁止直接从生产集合生成期望导致漏键时测试一起消失，保读取角色/旧任务前拒绝。
- 属主动减少30格交叉，不称逐格等价；最终普通数量以实际收集为准，实际本组418→388，真实4不变。

## Acceptance criteria

- [x] 四真实核心仍实际通过，浏览器不得恢复内存中心或假原生；普通守卫未放宽。
- [x] 退役键全集仍有独立期待，四入口各有拒绝代表，输入/旧任务读取前拒绝断言保留。
- [x] 页面诊断组合减少的具体分支及覆盖损失明确登记，不删必要开关接线。
- [x] 普通守卫与inventory完整互补通过；固定后root统一真实/全仓；原计划不加矩阵，后仅按用户新增明确授权执行一次8×2与耗时降序对照，未新增profile或其它矩阵。

## Comments

既有技术精简方案已经用户批准；完整Gate1已明确确认同树新分支、并行子代理、最后独审和本轮取舍。三个票据无产品或文件依赖；不得各自提交、推送或运行Windows重验证。必要普通定向检查云端完成，测试资源冲突时排队。

开发收据（历史前态，2026-10-25）：`.local/verification-top-five/gse/focused.log`及`focused-guard-summary.json`为83通过＋98子测试、0.56秒、守卫错误为空。`all-ordinary.log`实际为**373通过/15失败，总388项，168子测试通过、4.06秒**；15次均FileNotFoundError（Export.lua缺失2次、冻结lua.exe缺失13次），云端浅clone未准备这些依赖，不能回写为388全过。`batch-guard-summary.json`记录4worker与5 start/finish完整、零违规/evidence_error=null。`inventory.log`与对应守卫收据通过：GSE392=388普通＋4真实，gear23=21普通＋2真实，选择互补且入口完整。真实4项未在云端执行，后续root已有依赖的Windows正式通过见下段。

页面覆盖主动削减：诊断接线mock段由两轮true/false×start/resume/import的6次请求缩为3次代表，保留mock start=true、运行中true→false不改变已有请求、resume=false、import=false；未拦截的真实双场链另核默认false。删除mock start=false、resume=true、import=true及运行中false→true的对称组合，不再声称全排列等价承接。物理结果中心、真实引擎/编译/剪贴板和4核心未移内存。

正式收据（2026-10-25）：b18/tree560088在官方BAV 2.7.1完整入口43项全部实际通过、0缓存跳过，17普通守卫完整，GSE388普通＋168子测试/4真实＋2子测试、gear两真实与checker均通过；原参数工具36.2841764秒、实际36.532秒。后续已授权8×2实验工具28.733572秒、实际28.975秒，同样43项全过且0缓存跳过。原云端环境失败记录保持原事实，不改写为通过；Windows正式结果和后续授权、清理、配置保存状态统一见[verification.md](../verification.md)。
