# Sim2GSE 页面目标数量选择

状态：implemented（实现与验证通过，进入规格及PR交付）

## Problem Statement
用户需要在页面选择单目标或五目标，目标行为完全使用 SimC 默认规则；恢复角色导出的万奥宝典天赋参与模拟。

## Solution
复用 target_count 配置，在现有页面增加一个原生下拉框：1 目标、5 目标，默认 1。两套引擎只传 desired_targets，不再传自定义 enemy、目标 level、target_level 或 armor_coefficient。等级、护甲及职责相关行为交给固定版本 SimC。

## User Stories
1. 打开页面默认选择 1 目标，可切换为 5 目标。
2. 自动搜索和导入序列模拟使用同一数量选择。
3. 切换数量时清除旧结果；运行期间禁止修改数量，结束后恢复可选。
4. 每个任务独立记录有效配置，缓存及恢复沿用原有身份约束，不能混用目标条件。
5. 默认开启万奥宝典，原样保留导出行；导出缺失时不凭空生成天赋，显式本地 false 仍生效。

## Implementation Decisions
复用配置 Module（模块）、任务 Interface（接口）、两引擎共有参数 Adapter（适配实现）及页面到任务的公开 Seam（接缝）。页面/API 数量限 1 或 5，底层配置保留现有正整数能力。每次提交构造独立配置，不修改服务器共享快照。删除失效的自定义目标字段，不默默记录未使用的参数；历史文件中的未知字段按现有配置校验报错。已核实用户本地 config.toml 不存在。保留角色自身 level 和 role，不人为关闭坦克默认攻击/治疗，不手动生成五个坦克目标。其它时长、迭代与按键设置不变。无需重编引擎，不改搜索算法、数据中心或缓存框架。

## Testing Decisions
沿用现有页面两种提交与真实 HTTP 接口作为最高入口，以少量检查覆盖默认值、1/5选择、两种提交、配置不串和切换清除结果。复用已有配置、缓存、恢复检查，避免新框架或大矩阵。必要的原生引擎数量核验在 Windows 运行，不用长搜索验收下拉框。本机快验沿用60秒预算，CI 按仓库现有配置。

## Out of Scope
目标类型选择、自定义木桩、等级或护甲覆盖、任意数量输入、大秘境层数、页面偏好持久化、引擎重编译、历史任务迁移。

## Further Notes
固定基线 8ec11acc68842454c0a8000f0cfd95d6ed873519；分支 codex/sim2gse-target-selection。固定 SimC b845947a34429874433d8e9362326894650dd20a 的原生默认主目标是 tank_dummy_enemy，附加目标为普通 enemy，行为随角色职责变化。官方文档：https://github.com/simulationcraft/simc/wiki/Enemies 。armor_coefficient 是攻击者减伤公式的 K 常数，并非目标自身护甲。

用户最终指令 Sentinel_3d84b7377ea88191a201f46bd661a827 将方案收敛为原生默认目标和1/5选择；Sentinel_14e821e10bb081918d7c6c640865711e 明确批准执行，取代较早的 Boss/木桩双下拉框方案。正式规格留到交付门禁后按现有工具更新。
