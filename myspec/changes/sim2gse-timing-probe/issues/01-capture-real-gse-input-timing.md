# 01: 采集真实 GSE 输入与施法时机

**What to build:** 提供一个可在 12.1 正式服独立启用的 Sim2GSE 时机探针；用户通过斜杠命令开始、标记和停止会话，插件把 GSE 动作提交及玩家原生施法事件以毫秒时间写入 SavedVariables，且不修改 GSE 或自动产生输入。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `/s2gprobe start|mark|stop|status` 可通过同一个插件入口完成完整采集流程。
- [ ] GSE 点击记录包含可复核的按钮、点击序号、提交步骤、动作和触发边沿。
- [ ] 玩家施法事件记录包含事件名、`castGUID`、技能编号和毫秒时间。
- [ ] 会话条件包含法术队列窗口、按下触发设置、网络延迟、符文和符文能量；受限值安全降级。
- [ ] 离线公开接缝测试先失败后通过，并明确保留实机验收边界。

## Comments

- 2026-09-15：用户确认开始开发独立探针插件；不修改 GSE，不包含自动输入。
