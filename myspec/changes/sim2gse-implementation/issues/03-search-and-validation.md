# 自动搜索、复测与恢复

Status（状态）: open
Triage（分拣）: ready-for-agent
Assignee（领取者）: unassigned

## Parent

[开发需求](../spec.md)

## What to build

用户角色经过同一任务入口自动搜索统一动作序列、独立复测并取得真实候选文本。预算、缓存、取消与恢复贯穿一次完整运行，不建立另一套离线手工调度流程。

## Blocked by

[同一导出序列的原生模拟](02-sequence-simulation.md)

## Acceptance criteria

- [ ] 按已确认的多起点局部搜索、分批加测及轨迹反馈实施；技能与主动使用物品同等处理，序列合法性先检查。
- [ ] 原生参考、有效初始序列与候选保持相同角色和场景；锁定候选后使用未参与选优的最终样本，保存有效样本数与差异区间。
- [ ] 十分钟计算上限、最迟第七分钟结束搜索、最多两个单线程进程真实生效；复测不足明确标注，不能延长预算凑成功。
- [ ] 名义、扰动、慢按、暂停和相位情景有实际结果；无可信改善保留有效初始序列，不承诺提高固定百分比。
- [ ] 相同完整身份下的成功批次可复用且不重复计数；变化条件、损坏报告或失败结果不误命中缓存。
- [ ] 实际中断后清理所属进程，保留完整结果和已用预算；恢复已锁定任务只继续其复测，不影响配装器或其他模拟。
- [ ] 输出满足必要一致性检查的真实字符串，独立复测未完成时不能把结果标为已验证。

## Testing Decisions

最高入口沿用前两票的任务启动、取消、恢复与结果读取，覆盖 T17—T20；用受控故障注入检查写入前后中断和版本变化，最终真实角色冒烟仍调用原生引擎。执行细则与示例参数见[运行契约](../../../../docs/sim2gse/runtime-contract.md)，不要把旧测量的 1.82 倍当成搜索保证。

## Specification coverage

`Sim2GSE reports independently tested improvements`、`Sim2GSE respects the confirmed runtime budget`、`Sim2GSE resumes without mixing results`，以及真实导出要求。

## Completion evidence

待记录本次实际搜索耗时、候选与对照、锁定与采样日志、取消恢复结果及错误状态；当前未实施。
