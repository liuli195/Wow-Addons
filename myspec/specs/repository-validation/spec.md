# Repository Validation

## Purpose

让开发者在本机快速获得完整、可复核的仓库验证结果，同时保持远端验证覆盖。

## Requirements

### Requirement: Local full verification reports the sixty-second budget

系统 MUST 在本机完整验证中执行全部已登记检查及自动发现的角色按键序列优化器测试，并报告总耗时、60 秒预算和是否超出预算；性能预算不得通过跳过仍登记的必要检查、降低生产默认计算预算或把失败改写成通过达成。经用户对具体范围与覆盖损失明确确认，可精简重复或低收益边缘测试。日常验证保留已确认的核心真实冒烟，实际执行其所声明的依赖；保留检查必须能判别其承诺的成功、失败或隔离结果。每次精简公开保留入口、删除风险及未验证范围，不把内存规则通过冒充物理或原生验证；普通检查不得进行其被禁止的外部操作，不得弱化生产身份核验或已确认保留的进程所有权隔离等核心保护，不得跳过剩余登记项或将失败写成通过。超出已确认删减范围须重新明确确认。

#### Scenario: Local full verification meets the budget

- **WHEN** 开发者在目标本机运行完整验证并生成性能报告
- **THEN** 所有已登记检查和 Sim2GSE 测试均实际通过，报告总耗时不超过 60 秒且标记未超预算。

#### Scenario: Local full verification exceeds the budget

- **WHEN** 完整验证总耗时超过 60 秒
- **THEN** 系统如实标记超预算并保留各项功能检查结果，不用性能警告掩盖或改写功能失败状态。
### Requirement: Continuous integration retains complete verification

系统 SHALL 在 PR（拉取请求）的完整验证中执行全部标记为可在 PR 运行的已登记检查，并明确报告仅本机检查被排除；引擎构建和依赖产品引擎的 Sim2GSE 测试组仅由本机完整验证执行。远端结果按功能通过或失败报告，不以本机 60 秒预算作为远端通过条件。

#### Scenario: Pull request runs its complete check set

- **WHEN** 远端 CI（持续集成）执行 PR 完整验证
- **THEN** 所有 PR 可执行检查均实际执行，且仅本机检查明确显示为排除
- **THEN** 远端不准备或构建产品引擎，也不运行依赖产品引擎的 Sim2GSE 测试组

#### Scenario: Local full verification retains engine coverage

- **WHEN** 开发者在已准备好引擎的本机运行规范构建和完整验证
- **THEN** 引擎构建及依赖产品引擎的 Sim2GSE 测试组仍实际执行，并纳入本机结果
### Requirement: Local build and full verification use separate budgets

系统 MUST 将规范构建与完整验证的性能预算分别报告；完整验证独立使用60秒预算，不再将构建与验证两段合计作为此次验证验收条件。全部当前登记检查及自动发现的测试仍实际执行，必要构建身份校验不得跳过，生产默认计算预算和语义不改变。

#### Scenario: Prepared local verification meets its independent budget

- **WHEN** 开发者在已准备有效引擎的本机运行完整验证
- **THEN** 全部当前登记检查及自动发现的测试实际通过，验证自身总耗时不超过60秒
- **THEN** 构建时间及结果单独报告，不混入或替代完整验证时间

#### Scenario: Build identity is no longer valid

- **WHEN** 固定来源、补丁、编译器或已有产物的身份不再匹配
- **THEN** 构建 MUST 重新执行必要工作或明确失败，不得把未核验的已有产物当作有效构建结果
