# 03：重建共同种群及有界八配对pilot控制

Status（状态）: pilot-completed (7/8 budget-complete; formal verification failed; next stage user decision)
Triage（分拣）: ready-for-agent
Blocked by（前置事项）: 结果最终核验及用户后续决定；正式统一验证未通过

## 交付

按[变更规格](../spec.md)重建训练供应器和隔离CLI，8trial完整留痕、真实预算、平衡控制、4seed独立终点；不重造旧提交或旧native报告，不影响正式搜索。

## 验收

- [ ] 默认None／训练专用供应器，复用原评分／晋升、实际父本反馈；正式不加载DEAP。
- [ ] 共同pool8、2elite＋2轮转完整原始结构、16unique子代、全部已评分档案，父本不改写。
- [ ] 策略身份／RNG／pending原子恢复；实验与普通任务不互相静默恢复。
- [ ] manifest全部8slots，seed实际派生互不交，4新endpoint、AB/BA与材料位置平衡。
- [ ] 准备前隔离、冻结爆发ID、每trial/arm全新中心及邻接cache，正式资产不变。
- [ ] 从隔离到保存180秒，pair600及全部4800累计硬截止；失败也计时，不补seed。
- [ ] coverage不足保留实际赢家端点；无赢家失败、端点不齐不完整，全部尝试保留。
- [ ] winner先固定、独立4seed128不回流，报告m/8条件log比值SD与可靠性，不把endpoint当n。
- [ ] CLI真实红绿／构造native测试及双轴审查后才真实pilot，统一verify失败准确披露。

## Comments（讨论）

2026-10-22：用户对完整开发门禁明确回复“确认”，之后原环境对象／文件回退；全面云端及本机只读检查未找到可用原件，用户授权“检查到本地还没有的话，就重新弄呗”。父在同工作树显式获取已合主干13e7998并创建原功能分支，保留旧分支。当前为新实现，绝不宣称c0bab11恢复。

2026-10-22 03:51 UTC：最高入口CLI检查因脚本缺失真实红灯，最小重建后check-only绿灯。独立.local venv从正规PyPI仅wheel安装DEAP1.4.4及numpy2.4.4，依赖／时间／安装日志保留在.local/population-mvp；原.venv不变，无源码编译。正在补针对性无native回归，尚无pilot运行。

2026-10-22 04:08 UTC：重建实现已冻结供审查，12项无native定向检查9.682秒通过；实际CLI预检连接隔离数据存储、精确爆发定义及原_training_inputs且禁止native。文档389份、inventory、py_compile及diff检查通过。正式统一verify未通过，误用local上下文的失败不当作云端验收，父提交后以正确cloud上下文重跑。尚未pilot、无新收益数据；待GPT-6-A双轴审查。详见../pilot-readiness.md。

2026-10-22 04:16 UTC：b26827c双轴审查四项阻塞统一修复：恢复2轮无提升停止、已退出worker的owned组幂等清理、启动登记前固定pair截止并共用父wait、无效同后缀交换不合谱系／不跳父本反馈。新回归先红后绿，14项无native测试9.718秒通过；无新能力、无真实native／pilot，等待差异复审。父cloud统一fast verify因Windows路径／xdist实际失败，正式验收未过。详见../pilot-readiness.md。

2026-10-22 05:17 UTC：运行提交31dd2e1的新8pair pilot退出0，总3248.562秒，在4800秒内；全部slot保留、无替换种子。7/8预算与端点完整，slot3 B最终保存超180秒，保存前178.240字段不冒充最终耗时；4slot A覆盖不足但有实际winner仍完成端点，全部8输出／端点齐全。96份原始endpoint逐份匹配summary；2条原生超时批次如实保留，不声称worker退出0代表所有批次成功。正式data未创建，无遗留实验进程。报告../pilot-report.md仅作条件方差／可靠性结论，待独立原始及统计核验；不改代码、不追加native／trial，不git。统一cloud verify仍失败，正式验收未过，后续由用户决定。

2026-10-22 05:19 UTC：补充独立统计核验：7预算合规pair条件几何+6.2869%、探索性t95[+2.3637%,+10.3605%]；点SD下1%／2%正式N134／36，保守80%上限SD下260／68，均非保证且须另获用户决定。4条A覆盖不足路径都有16个pending的32档评分，不是未搜索；A实际6/8原始赢家、2/8晋升子代，短切片初始化及核验差异影响归因。扩样前建议审视slot3保存超时与1.5GB重复状态保存成本，仅建议不修复、不删除、不追加模拟。
