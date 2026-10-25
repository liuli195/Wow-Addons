# Full需求路由与设计证据

## 固定现场与来源

- 恢复工作区：/workspace/scratch/0af43d0efb8f/wow-addons-pr76-ci；root以指定功能分支depth1/no-tags浅克隆恢复，当前是独立.git，不冒称原linked worktree登记仍在。
- HEAD87bce49de64060b10a001d61d2a63f6b0cf7d300 / tree6d693c873380c29e295335253f34cf3cbe4d1ba2；开始需求写入前clean，1867 tracked / 14024703B，整树约24164KB。旧678仅曾回报的纯文档提交，本轮未从远端恢复，不伪造该对象。
- 已验87b正式全仓43实际通过0cache、17普通/26真实角色完整；GSE17.48、工具39.5877264、wall39.858；418+168普通、4+2真实。来源为root实际本机回报及指定原始证据目录，不是新跑结果。
- 当前技能入口解析恢复方式已由用户明确确认：Sentinel_09cbdbe0bfd881918c43336d50b3d73c，紧接“本轮继续直接读取已核来源版本的现有技能文件，其余完整门禁保留”。不把此当新实现Gate1已过。
- 读取路径是cloud-skills/managed/skills/<精确名>/SKILL.md；installed.json登记own-skills v2.7.1/6620a27、mattpocock v1.3.1/24fe0ef，源实际HEAD及frontmatter已核。云端旧npm不是当前正式工具，不用于本机验收。

## 依赖实际使用

1. dev-flow及requirements/implementation：选择Full，因为三个独立切片和主动覆盖取舍；仅允许门禁前需求产物。
2. subagent-policy：具名Architect不可用，显式通用回退gpt-6-sol/xhigh、只读；实际委派top_five_architect核源码，不由集成者假装替代。该代理已读codebase-design，并逐票返回Interface/Seam及风险；无写入/测试。
3. grill-with-docs按其入口展开grilling与domain-modeling：已读两依赖，以如下决策树逐项校准；已有用户答案不重复询问，尚待流程选择统一放Gate1。
4. to-spec：从既有对话、源码和架构证据合成可观察spec；用户“规格不写实现”优先于默认Implementation Decisions模板，实现细节另放票据/本文件。
5. to-tickets：三条完整可验的纵向测试切片，无相互阻塞，文件互斥；root串行集成/共享Git与Windows验证，最后统一独审。票据粒度/依赖/入口统一在Gate1请用户确认，不另插同义确认。

## 决策树与术语校准

- 目标：进一步精简慢项而非修产品功能；技术方案已获“先按这个方案精简”批准。
- 保留：主LuaLS不动、GSE四核心不动、普通守卫不动；Lua整体内存化取消。均为已有明确决定。
- gear“主计算10→5”：是浏览器调用次数约10→5，绝非SimC iterations（生产固定1）；避免把测试规模改变说成产品默认改变。
- “最简真实冒烟”：实际依赖仍执行；普通规则不是物理或原生覆盖证明。低ROI边缘主动删除，必须披露。
- “旧正式绿 / 新候选 / 诊断”：三者不同。诊断排序提供优先级，不作为与正式基线严格同比；目前新候选尚未实施。
- 已确认frontier（完整门禁Sentinel_67b5e46600748191ba4223a01c0cefce，用户确认Sentinel_0ac161c3fe8c8191b697b37d3c04d7ee）：同树新分支完整名称、并行三Implementer与最后Astra双轴、三票范围/接缝/依赖、单处验证政策对齐、时间/磁盘及正规交付边界。统一见gate1.md。
- 项目使用docs/CONTEXT.md和gear领域术语、正式规格表达规则；无新产品领域词，无新增GLOSSARY/ADR框架。

## 架构核查结果

- gear：既有Playwright route Seam足够；仅abort未断言的original-matches/effects，保真实bootstrap/import/calculate及下载重导。check-browser.cjs:17–52有约10次主计算触发；server.py:649–665为固定iterations=1；旁路index.html:117–132可经replacement_signature再触发计算。未执行旁路的后端/缓存风险主动退出。
- checker：check.py真实命令入口保两个错误代表；test_checks.py:25–65旧临时Git混合现行verify_upstream与旧prototype，现行commit/tree比较见build.py:24–31，可用现有test_validation_units内存Seam；旧prototype补丁往返和重复语法自测直接删除并披露；TOC缺文件拒绝则调用生产check_toc迁入内存，以glob/read_text/is_file读取Mock构造缺文件，核ValueError且不调用Lua。正式TOC/主LuaLS仍运行。
- GSE：conftest.py:44–56 autouse对全部real准备中心，而仅browser需要该中心安装/API加载；连接测试已显式请求安装副本，另两真实不访问中心。所有real的DATA_ROOT仍逐例隔离，仅安装复制/API加载通过显式usefixtures按需，不删数据根保护，不造新抽象或按函数名硬编码。退役11×4共用生产reject_removed_search_settings Seam：保硬编码11键+其余三入口代表，共14；不由生产键集合自动生成期望。
- 三票文件、产品功能和最终入口相互独立；并行写互斥文件可行，所有共享Git与真实资源必须串行。

## 测试证据口径

本任务没有产品功能失败，不能伪造红灯。以既有正式性能和已核冗余调用/组合为优化前态；新增内存规则先执行验证，再删除对应重复真实链；必要失败按原入口定位后修复。最终记录相同Windows环境/43项/0成功缓存跳过的官方非诊断full，报告实际三组及总耗时。只允许必要短云端定向和最终整合验证，不新建runner、全量profile或并发矩阵。

## 旧验证政策冲突

repository-validation/spec.md首条中“必须保留最少且有判别力的实际数据损坏/锁/恢复边界”与用户前轮已明确选择四真实/允许删除低ROI边缘的覆盖口径不一致。不能称当前四条已满足该旧字面条款。本轮门禁提出仅对齐该覆盖政策，保留生产功能和已有四核心；正式规格当前不写，精确预览在Gate2确认后才应用。拟可观察文案见gate1.md，不是无限删除关键保护的许可。

## 实施准入记录

root已从87b真实基线创建codex/trim-verification-top-five，同一路径恢复后的独立浅clone。三名实际实施者为GPT-6.1 Sol/xhigh（宿主强制）；文件互斥，共享Git和Windows仍由root串行。当前新任务处于实施中，不能复用旧GSE17.48秒宣称本轮已验收。旧678仅曾回报纯docs身份，不在当前对象库、不伪称已恢复。
