# 01: 使用官方并行能力将本机完整验证压到 60 秒内

**What to build:** 使用 pytest、pytest-xdist 和 build-and-verify 的现有并行能力运行全部 Sim2GSE 测试，并把本机完整验证最慢耗时控制在 60 秒内；CI 保持完整覆盖但不承担该耗时门禁。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] pytest 自动收集并执行现有全部 68 项 Sim2GSE 测试。
- [ ] 不新增自有并行运行器，不减少测试、模拟次数或失败检查。
- [ ] build-and-verify 完整验证实际运行全部检查且通过。
- [ ] 本机连续三次完整验证的最慢总耗时不超过 60 秒。
- [ ] 性能报告记录 60 秒预算，Sim2GSE 异常超时仍为 600 秒。
- [ ] CI 完整验证通过并报告实际耗时，不要求小于 60 秒。

## Comments

- 2026-09-15：用户确认采用单一纵向票据和完整验证公开接缝；本机 60 秒为门禁，CI 耗时不作强制要求。
