# 重建交审状态（非真实pilot结果）

基线13e799833985a51270dd3c62817031ee60ae26f5，同云端工作树及codex/sim2gse-population-mvp。旧c0bab11／旧raw未恢复，绝无补造报告。本次新增隔离实验CLI与研究测试；生产唯一差异是训练供应器接缝，正式规格／配置／数据未改。

## 已做验证

最高层CLI检查在脚本缺失处真实红灯，后续转绿；原optimize集成回归也实际抓出规范化返回映射与搜索列表表示误用，已修复再验证。当前定向套件覆盖原筛选／CI晋升、未晋升父本繁殖、正式默认路径、恢复身份及池／RNG原子中断、真实存储接入与独立邻接cache、结构轮转／Loop完整块、seed manifest／ABBA及材料平衡、覆盖不足实际winner仍进4seed独立端点、无winner／不齐端点／全部8slot及进程组截止。全部构造评分仅用于单元测试，不是实际A/B证据。

实际CLI --check-only在任何native前核验两个真实引擎identity／冻结模板，并经原burst.validate/definition_id将仓库既有定义只发布到临时实验中心，再调用原_training_inputs。运行时禁止创建native进程，不是只检查一份静态JSON。

复跑命令：

- .venv/bin/python tests/sim2gse/research/population-pilot-check.py
- .venv/bin/python scripts/dev/check.py docs
- .venv/bin/python tests/dev/test_inventory.py
- .venv/bin/python -m py_compile scripts/dev/sim2gse/population_ab.py projects/sim2gse/search.py
- git diff --check

原始定向日志在.local/population-mvp/red.log和green.log；12项定向检查9.682秒通过，文档389份及inventory通过。正式统一verify第一次因缺execution-context失败；第二次误用local上下文、因baseline_worktree_not_clean失败，实际日志unified-verify.log保留，该尝试不能作为云端验收。父固定提交后须使用正确cloud上下文重跑，不把定向PASS冒充统一验收。

## 依赖与实际时间

2026-10-22约03:51 UTC，在.local/population-mvp/venv从正规PyPI以--only-binary=:all:安装deap1.4.4／numpy2.4.4；实际依赖还包括moocore0.3.2、cffi2.1.1、platformdirs4.13.5、pycparser3.11。没有源码构建、没有改原.venv、没有安装pymoo；install.log和dependencies.txt保留。现有两Linux ELF仅作identity只读核验，摘要与原记录一致，无重编译或真实模拟。

## 下一步及限制

目前仅实现／无native验证，未启动80分钟pilot，未生成任何真实收益数据；待父固定提交及GPT-6-A双轴审查。统一verify尚未通过。审查后先执行独立预检（输出须在.local/population-mvp）：

.venv/bin/python scripts/dev/sim2gse/population_ab.py --materials .local/population-mvp/materials.json --output .local/population-mvp/rebuilt-preflight --check-only

获准由父启动的实际入口为同命令去掉--check-only并换全新输出，例如.local/population-mvp/pilot-rebuilt-01。该命令会启动一次预登记8pair，整体4800秒，不与其他模拟同时运行；不自动补种子、重复pilot、继续正式N或接正式搜索。每pair独立worker，父截止杀整个worker进程组，native子进程继承其组；任何失败及未启动slot均保留。180秒含隔离／可靠存储，若收尾实际超限如实标记失败，不能声称保存耗时被扣除。

统计只报告完整m/8的条件log比值SD及全部失败／覆盖／端点缺失；没有稳健优效结论，也不把候选或4seed算n。更大正式N及1%／2%目标后由用户决定。

## b26827c审查修复（04:16 UTC，待差异复审）

两轴审查指出四项阻塞，按原批准策略作最小修复，没有增加能力：供应器恢复原no_improvement>=config门槛（本实验2轮）；父进程即使worker已经退出也幂等清理其owned进程组；启动登记前固定同一pair绝对截止，同时传worker和父wait，不从Popen后重新计算600秒；相同后缀交换无结构变化时不标crossed、不合谱系，后续纯变异仍取实际父本反馈。

新增回归先在原实现实际红灯：提前停止仍调用供应器、10秒启动耗时使wait错误保留600而非589秒、worker退出码−9却未清理存活child、同后缀误标交叉。修复后完整14项无native检查9.718秒通过，覆盖同后缀后的实际变异反馈；py_compile／diff检查通过。红绿原始日志在.local/population-mvp/review-red.log、ownership-red.log及review-green.log。未运行任何真实native或pilot，未自行提交。

父代理已以正确cloud上下文真实执行统一fast verify，因仓库Windows Python路径／xdist检测失败；正式验证仍未通过。之前local误上下文的失败记录保留，不作云端验收证据。以上修复尚待固定提交的GPT-6-A差异复审。

## 已运行pilot的最终事实（05:17 UTC）

审查后父以31dd2e1运行一次8pair，退出0，总3248.562秒；全部8尝试保留，预算及终点完整7/8，coverage两臂亦满足3/8。slot3 B最终可靠保存超180秒，4slot A coverage不足但实际winner端点仍保留；全部8输出／端点齐全，不将条件7样本包装成8次无条件收益。详见[pilot结果](pilot-report.md)。96份独立端点原始报告逐一匹配；搜索批次有2条真实超时failed，不能因父／worker退出0宣称全部原生成功。无遗留实验进程、正式data不存在；原始1.5G实验完整保留，未清理。仅补文档，不追加模拟／修代码／新trial，统一cloud verify仍未通过。待独立证据／统计核验后由用户决定后续。

独立统计核验补充：7合规pair条件几何+6.2869%，探索t95[+2.3637%,+10.3605%]，不能表述为8次无条件稳定收益；点SD正式N134／36、保守上限SD260／68（1%／2%）仅供下一步ROI决定。4条A覆盖不足路径已有16pending首32评分，未完成非初始入档，并非未探索。A6/8原材料输出、2/8晋升子代，短切片策略差异限制归因。slot3可靠保存超时与大重复日志负担建议扩样前由用户决定是否最小修复，本次不改代码／不删数据／不再试跑。
