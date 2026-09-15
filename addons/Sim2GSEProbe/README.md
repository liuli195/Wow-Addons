# Sim2GSEProbe（实机时机探针）

该开发插件只记录玩家真实输入，不自动按键或施法，也不修改 GSE（宏序列插件）。

## 使用

1. 输入 `/s2gprobe status`，确认已经监听到 GSE 按钮。
2. 输入 `/combatlog` 和 `/s2gprobe start`。
3. 完成一轮测试后输入 `/s2gprobe mark`；可继续下一轮。
4. 全部结束后输入 `/s2gprobe stop`、`/combatlog`、`/reload`。

保存记录位于 `_retail_/WTF/Account/<账号>/SavedVariables/Sim2GSEProbe.lua`。每次 `start` 会替换上一段探针会话，因此应先保留仍需分析的旧文件。

记录中的 `click`（点击）是 GSE 按钮提交观测，`spellcast`（施法事件）来自游戏原生 `UNIT_SPELLCAST_*` 事件。两者只能用于反推法术队列行为；公开接口不能直接读取客户端内部队列。
