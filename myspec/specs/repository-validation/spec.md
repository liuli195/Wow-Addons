# Repository Validation

## Purpose

让开发者在本机快速获得完整、可复核的仓库验证结果，同时保持远端验证覆盖。

## Requirements

### Requirement: Local full verification reports the sixty-second budget

系统 MUST 在本机完整验证中执行全部已登记检查及自动发现的 Sim2GSE 测试，并报告总耗时、60 秒预算和是否超出预算；性能预算不得通过减少测试、模拟次数或失败检查达成。

#### Scenario: Local full verification meets the budget

- **WHEN** 开发者在目标本机运行完整验证并生成性能报告
- **THEN** 所有已登记检查和 Sim2GSE 测试均实际通过，报告总耗时不超过 60 秒且标记未超预算。

#### Scenario: Local full verification exceeds the budget

- **WHEN** 完整验证总耗时超过 60 秒
- **THEN** 系统如实标记超预算并保留各项功能检查结果，不用性能警告掩盖或改写功能失败状态。
### Requirement: Continuous integration retains complete verification

系统 SHALL 在 CI（持续集成）中继续执行同一套完整检查和测试覆盖，但不以本机 60 秒预算作为远端通过条件。

#### Scenario: Continuous integration runs full verification

- **WHEN** 远端 CI 执行仓库完整验证
- **THEN** 所有已登记检查和自动发现的 Sim2GSE 测试仍被执行，远端结果按功能通过或失败报告，不因耗时超过 60 秒单独失败。
### Requirement: Daily local build and full verification meet the sixty-second total budget

系统 MUST 在本机已准备与固定来源、补丁及编译器身份一致的两份引擎产物时，使规范构建与完整验证连续运行的合计墙钟时间不超过 60 秒；不得通过减少已登记检查、自动发现的 Sim2GSE 测试、模拟次数或必要的构建身份校验来达标。

#### Scenario: Prepared local build and full verification meet the total budget

- **WHEN** 开发者在上述已准备好的本机依次运行规范构建和完整验证
- **THEN** 两段均实际通过，全部已登记检查和自动发现的 Sim2GSE 测试均执行
- **THEN** 两段连续计时的合计不超过 60 秒

#### Scenario: Build identity is no longer valid

- **WHEN** 固定来源、补丁、编译器或已有产物的身份不再匹配
- **THEN** 构建 MUST 重新执行必要工作或明确失败，不得把未核验的已有产物当作有效构建结果
