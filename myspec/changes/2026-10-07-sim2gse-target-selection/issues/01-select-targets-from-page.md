# 01：从页面选择目标数量并完成模拟

**What to build:** 一个数量下拉框向搜索及导入模拟传递1或5，默认1；使用 SimC 原生默认目标并恢复万奥宝典开启。

**Blocked by:** None（单一纵向票据）

**Status:** done

- [x] 默认值与1/5选择在页面、HTTP及两套引擎一致。
- [x] 仅传 desired_targets，目标等级、护甲和行为由 SimC 默认处理。
- [x] 万奥导出行默认原样保留，显式关闭仍生效。
- [x] 任务配置互不污染，沿用缓存与恢复身份约束。
- [x] 复用公开入口检查，通过本机快验和独立审查，明确原生引擎核验范围。

## Comments
用户已批准最终精简范围；云端串行实施，独立双轴审查，必要 Windows 验证。正式规格尚未修改。

红灯证据：Windows 基线8ec11acc使用既有Edge/Playwright读取真实页面，#targetCount数量0、预期1，断言414毫秒，总1.7秒。云端Chromium启动受到socket权限限制，未将环境失败当成测试红灯。配置默认测试首先因万奥False失败，最小修改后通过；4项配置公开接口检查通过。完整Windows绿灯、正式快验与独立审查待执行。

验收证据（2026-10-07）：实现提交5f02e958652b3c7f5d1cea51d93617b6e64dd6d4，固定基线8ec11acc。Windows配置18项及8子项、页面选择器、导入页面请求与禁用/恢复检查通过；导入页响应使用边界模拟，另有真实HTTP与两套预构建引擎各1/5目标共四次原生检查。独立规范轴和规格轴均无未解决缺陷。

真实页面五目标任务43423659833046c694c498eba6e4c01d从既有检查点续跑完成，205.47秒、399批、400次原生启动，stop_reason=no_improvement。600秒预算、候选上限1000、无改进轮数5保持默认。运行、候选、基线及80个验证批记录写入并能读回，报告为Fluffy_Pillow及4个Dummy。independent_validation_complete=false、final_status=not_requested，未声称独立最终复测或游戏验收通过。

官方本机快验status=passed、exit=0，checked包含verify.sim2gse、verify.docs、verify.test-inventory；Sim2GSE检查329项及112子项通过，单项32.42秒（pytest31.48秒），总入口时间未单独记录，60秒强制预算未关闭。研究夹具仅在隔离工作树临时使用实体副本以满足输入边界，随后恢复原Junction，未改验证器。

证据目录：本机隔离工作树.local/validation-target-selection/，包括fast-verify.log、ui-smoke-resumed.log、engine-smoke/engine-smoke.log和import-page-evidence.json。两项正式规格路径预检均为空、exit=0。票据实现已验收，规格和PR交付按用户Sentinel_776da78cd6848191aa29bc55bed2e126预授权继续。
