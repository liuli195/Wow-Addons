# 01: /castsequence 最小搜索到评分闭环

**What to build:** 让用户通过现有搜索入口得到包含两至四个可模拟技能的 `/castsequence` 候选，该候选能被解释、导出、交给真实 Native SimC 运行并取得 DPS 评分和最终选择结果。

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] `POST /api/tasks` 的红灯测试证明当前搜索不能完成 `/castsequence` 的生成、真实 SimC 评价与最终选择。
- [x] 搜索能生成和变异结构化 `/castsequence` 候选，搜索层不解释宏文本。
- [x] 宏解释层能解析无宏条件的序列成员和 Reset 定义，并映射到当前角色可模拟技能。
- [x] GSE 导出包含真正的 `/castsequence`，候选身份和缓存身份包含完整序列定义。
- [x] 同一候选经真实 Native SimC 得到 DPS，搜索评分、复测和最终选择沿用现有流程。
- [x] 普通动作、Loop 和 WaitClicks 回归不变；不支持宏条件在原生评价前明确拒绝。

## Comments

- Red：`pytest tests/sim2gse/test_interface.py -k castsequence -q` 初始失败，公开任务未生成 `/castsequence` 候选。
- Green：同一公开测试最终 `1 passed`；真实 controlled Native SimC（受控原生模拟器）完成评价，最终 GSE 导出保留真实 `/castsequence 77575,47541`。
- Native build（原生构建）：baseline 与 controlled 均 `exit=0`，兼容锁包含 `029-castsequence-runtime.patch`。
- Regression（回归）：`castsequence or sequential_loop or wait_clicks or macro_interpreter` 聚焦检查 `5 passed`。
- WoW 正式服实机验收：`not_run`，不作为本票本地技术验收的一部分。
