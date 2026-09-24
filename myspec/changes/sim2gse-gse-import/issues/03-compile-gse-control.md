# 03：按上游语义编译全部 GSE 控制块

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

用户可看到导入序列的 Action、Repeat、Loop、Pause、If、Embed 如何展开；条件、变量、引用或随机状态不足时，准确指出不可模拟的来源，不静默丢步骤。

## Blocked by

01：收集样本并查看导入结构；02：统一序列程序并保持搜索结果。

## Acceptance criteria

- [x] 选中版本与嵌套控制块按固定上游行为编译，含顺序、优先级、反向优先级、随机、定期重复和空点击。
- [x] If 与 Embed 有明确条件/依赖时可展开，缺失或循环引用时给出位置和原因。
- [x] 外部 Lua 代码不执行，未知宏、变量和编译环境不被猜测。
- [x] 编译步骤、来源位置与上游输出核对，资源上限生效。

## Completion evidence

完成证据（2026-09-25）：`tests/sim2gse/test_program.py` 覆盖六类节点、所有 Loop 步进方式、Repeat、Pause 时长与点击换算、If 常量与未知条件、Embed 默认版本/缺失引用/循环引用、来源位置、点击速率一致性、逐步资源上限和固定上游编译。固定上游锁仍为 GSE 3.3.32；未来 GSE 版本只被检查和标记为不可模拟。

宏场景补充采用红绿验证：新测试先因 `_map_step` 不接受显式 `enemy_target_ready` 而失败，随后通过。只精确支持 `/targetenemy [noharm][dead]` 在“当前目标存在、存活且可攻击”场景下无效果；这个块仍占一个点击；目标未就绪或其他写法拒绝。`test_default_scene_skips_modifier_cast_and_uses_targeted_macro` 与 `test_targetenemy_noharm_dead_is_a_noop_only_with_ready_enemy_target` 验证编译结果、场景记录和拒绝边界。

最终验证：`tests/sim2gse` 为 145 passed、52 个子检查通过（116.52 秒）。真实原串的缺口和拒绝记录见 `docs/sim2gse/gse-import-corpus.md`；本票没有把合成控制向量计作真实 Pause/Embed 语料。
