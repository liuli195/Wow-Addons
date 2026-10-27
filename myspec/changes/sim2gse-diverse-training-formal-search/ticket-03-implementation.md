# 票03实施与验证记录

状态：票02在90068d9通过独立本机Astra high审查后实施；本票待独立审查。未进行真实模拟、训练、安装、重编译、推送或合并。正式规格未应用。

## 实现与证据

- 复用现有训练、命令行及页面结果入口，增加实际入围人数、场景数、每候选批数、每批请求数、计划总批数/请求数、已完成批数与有效样本；训练快照保存相同预算摘要。
- 训练结果分别返回原生批启动次数、诊断请求及缓存命中；未启用诊断的后两项返回null（未采集），不假称0。已有源材料、适配、阶段、代数、实际发布人数与错误保留。
- 修正训练曲线内算法标签为当前训练算法；失败提示使用“旧快照”而非固定“旧四条”。
- 更新项目README、训练说明及升级技能证据要求：新训练DC（确定性拥挤竞争）、正式RTR（受限锦标赛替换）、实际P/N/W、独立配置、正常复测、历史只读边界。默认最终复测15360→3072，仅此阶段减少80%。
- 复用票01/02的公开恢复与失败验证：不足最低发布数不写快照，发布重试复用已完成复测，缺凭据核验、整代提交、旧完整版本可读、旧未完成拒绝及页面开始/继续配置冻结。普通层是内存与合成报告证据，不能替代物理链与游戏验证。

## 真实红绿记录

以下命令均在仓库根目录使用现有Python，设置PYTHONDONTWRITEBYTECODE=1，无新真实模拟。日志尾部保存退出码。

| 检查 | 命令核心 | 实际结果 | 日志 |
| --- | --- | --- | --- |
| 训练预算红灯 | `-m pytest -q tests/sim2gse/test_seed_training.py -k actual_retest_budget -p no:cacheprovider --basetemp=.local/tests/ticket03 --tb=short` | 2失败，缺retest字段，exit1 | ticket-03-budget-red.txt |
| 训练预算首次绿灯 | 同上 | 2通过，0.44秒，exit0；当时未单独保存绿灯文件，后续全回归覆盖 | 本机工具输出，后续见全回归日志 |
| 页面预算红灯 | `-m pytest -q tests/sim2gse/test_formal_rtr.py -k freezes_actual -p no:cacheprovider --basetemp=.local/tests/ticket03 --tb=short` | 4失败，缺planned_requested_iterations，exit1 | ticket-03-page-budget-red.txt |
| 页面预算绿灯 | 同上 | 4通过、11未选，0.61秒，exit0 | ticket-03-page-budget-green.txt |
| 普通全回归 | `-m pytest -q tests/sim2gse -m 'not real' -p no:cacheprovider --basetemp=.local/tests/ticket03-regression --tb=short` | 511通过、168子测试通过、4real排除，6.98秒，exit0 | ticket-03-regression-green.txt |

训练样例通过公开API（程序接口）与CLI（命令行）：K=8实际6人，18批、2304请求、2286有效样本；关闭诊断时请求/命中未采集，原生批启动24。页面分别验证9/10/13/15实际人数，正常入围8人的预算3072请求、3048样本。

页面首轮绿灯执行会话21210在环境断连后结果不确定；恢复时旧会话无法读取，进程查询确认没有Python/pytest进程，才重新运行并保存上述4通过日志。最后一次文档写操作随后在创建进程前断连；再次恢复Git核对确认文档未改，再执行更新。没有把断连当通过，没有并行重复测试。

静态检查：`scripts/dev/check.py docs`最终通过486份文档；`tests/dev/test_inventory.py`通过，明确515=511普通+4real，自动测试均登记。`git diff --check`通过。以上为专项诊断，不冒充统一正式验证通过。

## 正式规格候选

已实际执行MySpec 2.7.1：state-init、state-set-conflicts、state-status、validate-delta、apply-delta（输出到预览目录）、validate-main、diff；增量及完整预览校验退出码均为0。预览涉及seed-training、sequence-evaluation、user-workflow三个能力：16项修改、2项新增；旧冠军/五场景条款限定为旧完整记录只读语义，无删除或改名。已批准新需求覆盖原行为，无另需用户决定的来源冲突，conflicts为空。

- 工作状态：`.local/spec-work/current/state.json`，`applicationPhase=PREVIEW_ONLY`，`status=READY_TO_APPLY`。
- 增量：`.local/spec-work/current/delta/`。
- 完整预览：`.local/spec-work/current/preview/`。
- 完整差异：`.local/spec-work/ticket03-preview.diff`。
- 输入指纹：`.local/spec-work/ticket03-fingerprints.json`；证据为本需求spec及gate-preparation。主规格未改，锁及预览保留供审查与门禁二。

这些是本机忽略目录中的真实工具产物，不纳入本次Git提交，不代表已获准应用正式规格。

## 未完成边界与预算

统一固定基线正式验证尚未运行：会命中verify.sim2gse-real；本次禁止新模拟。四项真实检查的具体影响与建议命令见[真实检查范围](ticket-03-real-check-scope.md)。现有普通全绿不能满足完整构建验证门禁。真实训练、策略统计对照和游戏实测均未执行。

整体计时从2026-10-27 19:08 UTC开始，20:31 UTC约83分钟，仍在4小时内。本次只读统计：本次规格工作目录约303KB（含整个预览），本变更证据目录约67KB，票03两个pytest临时目录无文件；新增源码、测试及小日志总体远低于50MB。此为已落盘任务产物统计，不把已有约426MB三引擎算新增；真实浏览器临时目录的峰值未测，不能保证未来真实检查不触及50MB。

本票完成后停止等待独立本机审查，不进入合并、发布或正式规格应用。
