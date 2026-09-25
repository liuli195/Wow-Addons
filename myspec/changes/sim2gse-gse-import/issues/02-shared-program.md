# 02：统一序列程序并保持搜索结果

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

导入序列与现有搜索候选共用可扩展的序列程序边界；现有搜索用户仍得到与基线一致的简单序列和候选选择。

## Blocked by

01：收集样本并查看导入结构。

## Acceptance criteria

- [x] 来源无关的 Program 保留 Action、EmptyClick、Loop、Repeat、Pause、If、Embed 控制结构与来源位置；统一 CompiledProgram 逐次呈现动作和空点击。
- [x] 现有简单动作块经 Program 适配后仍走原 codec 导出，文本、编译步骤、动作块及模拟顺序与直接导出一致。
- [x] 搜索生成、变异与选择空间保持简单动作块；本票没有把高级语法加入搜索。
- [x] 公开搜索任务回归及简单程序编译对照通过。

## Completion evidence

完成证据（2026-09-25）：`tests/sim2gse/test_program.py` 8 passed，覆盖共享搜索/导入 Program 节点、六类控制结构、逐点击来源位置、空点击、固定上游导入、If `=true` 常量和原 codec 编译对照；其中 If 常量回归先因通用公式校验被误拒而失败，随后调整为仅放行 `=true`/`=false` 的 If Variable 后通过。`test_character_export.py` 10 passed、15 subtests；`test_sequence.py` 38 passed、5 subtests；公开优化任务 `test_public_entry_runs_multi_start_search_with_isolated_validation` 1 passed。搜索仍通过 `codec.export` 内部适配器，候选文本、compiled steps、动作块和点击顺序与直接导出一致，未改搜索空间和选择规则。
