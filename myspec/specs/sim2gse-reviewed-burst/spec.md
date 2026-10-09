# Sim2GSE Reviewed Burst

## Purpose

按专精人工审核独立爆发内容，生成第三个按键序列，并在真实角色模拟中与普通循环共享资源。

## Requirements

### Requirement: Sim2GSE requires an applicable reviewed burst definition

系统 MUST 按专精保存当前人工审核定义及历史版本，包含完整动作、数据版本、药水和按键计划。爆发不参加自动搜索；两场冻结同一审核定义。新版定义保存失败须保留旧定义可用。定义按专精固定，不按角色天赋或装备删改；缺失、损坏、未审核或专精不匹配时明确拒绝，不修改角色或套用其他定义。

#### Scenario: Burst definition is missing or changed

- **WHEN** 当前角色专精无审核定义，或恢复时定义、引擎或规则已改变
- **THEN** 报告原因并要求新审核或新任务，原角色与旧结果保留，不能混用旧条件成绩。
### Requirement: Sim2GSE derives loop exclusions from reviewed burst contents

系统 MUST 根据当前审核爆发内容，排除普通单目标和5目标序列中的相应技能、替换形态、药水和装备使用动作。所有训练材料、搜索起点及最终导出均遵守同一限制；不符合限制的旧序列明确拒绝，原资料保留。爆发内容变化后排除范围随之变化，不限制正常宠物与派生伤害。

#### Scenario: A reviewed macro changes its contents

- **WHEN** 宏内容重新审核并发布，新任务使用新定义
- **THEN** 排除范围随宏实际内容改变，已移出的动作可按当前角色能力重新搜索，新加入内容从普通循环排除。

#### Scenario: Historical or nested content includes a burst action

- **WHEN** 起点或训练材料在任意层级包含当前爆发动作
- **THEN** 整条结构不进入普通搜索与导出，原材料及旧库保留，不继承其他条件的历史成绩。
### Requirement: Sim2GSE simulates burst and loop keys on the same actor

系统 MUST 让普通循环和独立爆发作用于同一个模拟角色，分别保留序列位置，共享该角色的资源和冷却。两种输入的执行和失败可分别核对，技能、药水和饰品的实际效果共同计入结果；不能分开计算后拼接伤害。默认按爆发时暂停普通循环，结束后从原位置继续。

#### Scenario: The reviewed unholy schedule runs

- **WHEN** 当前审核邪恶死亡骑士在180秒模拟中采用默认200毫秒间隔
- **THEN** 在第3、48、93、138秒开始各1秒爆发窗口，每轮按5次；两个块位置跨窗口保留，首轮从第一块开始、下一轮从第二块开始，结束后恢复原循环位置。

#### Scenario: A burst item or spell is unavailable

- **WHEN** 技能确实未学、饰品为被动或槽位为空，或动作受到冷却、资源及队列限制
- **THEN** 不可用内容不产生效果，临时限制按游戏规则处理；完整宏及序列位置保持不变，不绕过冷却或补算效果。训练、页面模拟和独立复测行为一致；无法准确模拟的动作明确报错。模拟药水不写显式星级，实际客户端品质选择仍另行验收。
