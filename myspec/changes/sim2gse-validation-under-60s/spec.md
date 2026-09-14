# Sim2GSE 全量验证 60 秒本机门禁

**Status（状态）：** ready-for-agent

## Problem Statement

仓库完整验证当前约需 250 秒，其中 Sim2GSE（角色级按键序列优化器）的 68 项测试串行运行约 234 秒，导致本机反馈过慢。用户要求保留全部检查和测试语义，并把本机完整验证耗时控制在 60 秒内。

## Solution

使用现成的 pytest（Python 测试框架）、pytest-xdist（Pytest 并行插件）和 build-and-verify（构建与验证）并行配置运行现有 unittest（单元测试），不开发自有并行运行器。采用适合耗时不均测试的 worksteal（工作窃取）调度，限制并行规模，记录 60 秒完整验证预算。

## User Stories

1. 作为本仓库开发者，我希望完整验证在本机 60 秒内结束，以便快速得到可靠反馈。
2. 作为维护者，我希望现有 68 项 Sim2GSE 测试全部自动发现和执行，以免性能优化降低覆盖。
3. 作为维护者，我希望复用 build-and-verify 与 pytest-xdist 的官方能力，以免维护自制并行运行器。
4. 作为维护者，我希望并行数固定且受控，以免同时启动过多进程造成性能回退或不稳定。
5. 作为 CI（持续集成）使用者，我希望远端仍执行全部检查，但不要求受 60 秒本机性能门禁约束。

## Implementation Decisions

- 固定使用 pytest 9.1.1 和 pytest-xdist 3.8.0。
- 保留现有 unittest 测试内容，改由 pytest 自动收集。
- Sim2GSE 使用 8 个 pytest-xdist 工作进程和 worksteal 调度。
- build-and-verify 的检查项并行上限设为 2，让短检查与 Sim2GSE 重叠，同时限制资源竞争。
- 完整验证预算设为 60 秒；预算超限保留 build-and-verify 的警告语义，不替代功能失败状态。
- Sim2GSE 的 600 秒异常超时保持不变。
- CI 保留同一套完整覆盖；CI 耗时单独报告，不以 60 秒作为交付阻断条件。

## Testing Decisions

- 最高层级公开测试接缝是完整构建后运行 build-and-verify 的完整验证并生成性能报告。
- 验收必须看到全部检查通过、检查清单非空、68 项 Sim2GSE 测试全部通过且没有跳过。
- 本机连续运行三次完整验证，最慢一次总耗时不得超过 60 秒。
- 测试清单检查必须继续证明以后新增的 Sim2GSE 测试会被自动发现。
- 远端 CI 必须完整通过，但只记录实际耗时。

## Out of Scope

- 不减少测试数量、SimulationCraft（战斗模拟器）迭代次数或失败检查。
- 不编写自有并行测试运行器。
- 不更换或购买更大的 CI 运行器。
- 不修改游戏功能、模拟算法或真实游戏验收范围。

## Further Notes

现有只读原型以 8 个独立工作进程运行全部 68 项测试，实测 48.94 秒并全部通过。正式结果仍以落地后的 build-and-verify 性能报告为准。
