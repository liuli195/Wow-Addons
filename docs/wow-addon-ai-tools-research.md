# 魔兽插件专用人工智能工具补充调研

核查日期：2026-09-08。目标：Windows（视窗系统）、正式服 12.1.0.69587、接口号 120100。结论来自作者仓库说明、配置、数据元信息及技能源码；未安装候选、启动服务或执行游戏验收。本仓库版本以 [版本记录](../scripts/dev/versions.json) 为准。

## 结论

已有专门面向插件开发的 MCP（模型上下文协议服务）和技能，前期指南确实遗漏了这一层。Mechanic（魔兽开发诊断平台）最接近完整开发环境；接口查询服务和通用技能适合作为补充。目前证据支持“值得试点”，不足以称为社区标准或经过本机验证的成熟方案。实施建议见[指南第 2.6 节](wow-addon-development-guide.md#26-魔兽专用-mcp模型上下文协议服务与技能)。

## 服务候选与源码证据

| 项目 | 已核查能力 | 版本及限制 | 建议 |
| --- | --- | --- | --- |
| [Mechanic（开发诊断平台）](https://github.com/Falkicon/Mechanic) | 桌面程序、游戏插件、统一命令注册、MCP、错误/性能输出、代码队列、离线沙箱 | 作者标为 alpha（早期测试版）；两个插件清单声明 120100，尚未在本机验收 | 完整诊断流程优先试点 |
| [wow_api_mcp（接口检索服务）](https://github.com/Nighthawk42/wow_api_mcp) | 生成文档、事件、类型、源码和百科检索；显示版本与来源提交 | 打包数据 12.1.0.69404，不等于目标 69587 | 只读检索优先候选，先对齐数据 |
| [hated-wow-mcp（开发工具服务）](https://github.com/RdyGaming/hated-wow-mcp) | 20 个工具，覆盖接口、素材索引、源码、清单和界面标记验证、模板 | 默认接口号仍为 120007；词法检查器不是完整 Lua（脚本语言）解析器 | 补充素材/源码检索，暂不接管生成和验证 |
| [wow-dev-mcp（资料服务）](https://github.com/juemrami/wow-dev-mcp) | 全局接口名、百科、全局字符串翻译，包含简体中文 | 从上游浮动分支读资料，类别参数不是固定补丁版本 | 有本地化需求再考虑 |

Mechanic 当前说明要求 Python（解释器）3.10 以上，Windows 桌面集成最完整。游戏端需要并排安装 `!Mechanic`（引导插件）和 `Mechanic`（诊断插件）；桌面可选依赖提供 MCP，入口为 `mech mcp`（启动服务）。只按当前安装说明准备独立环境，不直接运行会安装开发工具的设置命令。[安装说明](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/README.md)、[引导清单](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/!Mechanic/!Mechanic.toc)、[主插件清单](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/Mechanic/Mechanic.toc)

游戏交互是“写队列 → 指定角色重载 → 保存变量落盘 → 桌面读结果”，不是实时连接。需要明确客户端、账号、角色和配置；读取必须对应本次执行。沙箱替身不复现渲染、受保护接口或全部运行行为。作者列有自动测试与持续集成配置，但本次未重跑，不能作为本机通过证据。[流程与测试边界](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/README.md)

wow_api_mcp 的数据元信息记录源提交 `81d15e42f16f3473131880500e7a8c8eb88fa5e6`；源码缓存按数据提交抓取，而本仓库固定的是另一提交。它的构建号可追溯性较好，但不能据此宣称覆盖全部接口。服务需要 Node.js（运行环境）20 以上，初次源码检索还会下载缓存。[数据元信息](https://github.com/Nighthawk42/wow_api_mcp/blob/938779c110eb8ee6ca243be7cea5002383d68aa0/data/live.json)、[缓存实现](https://github.com/Nighthawk42/wow_api_mcp/blob/938779c110eb8ee6ca243be7cea5002383d68aa0/src/source/repo-cache.ts)

hated-wow-mcp 的正式服默认接口号在配置中写为 120007；包内接口索引和另行同步的界面/素材数据有不同更新路径，不能把“已同步”当成全部资料版本一致。其静态检查仅作补充，不能证明无战斗污染或真实界面正确。[配置源码](https://github.com/RdyGaming/hated-wow-mcp/blob/b6c690bdfb687125a82ba7ad9aa100137ec6ac93/src/config.ts)、[同步及已知限制](https://github.com/RdyGaming/hated-wow-mcp/blob/b6c690bdfb687125a82ba7ad9aa100137ec6ac93/README.md)

wow-dev-mcp 从 Ketho（接口资料维护者）的 `mainline`（正式服分支）读取全局接口和字符串；代码较久未更新不等于读出的资料必然旧，但也没有因此获得 69587 的固定版本保证。[接口来源实现](https://github.com/juemrami/wow-dev-mcp/blob/df70ede5601ef359ce2942129dfab5f79b23ebc1/src/GlobalAPIDocs.ts)、[字符串来源实现](https://github.com/juemrami/wow-dev-mcp/blob/df70ede5601ef359ce2942129dfab5f79b23ebc1/src/GlobalStrings.ts)

## 技能候选

| 项目 | 可借鉴内容 | 采用前需要解决的问题 |
| --- | --- | --- |
| [Mechanic 内置技能](https://github.com/Falkicon/Mechanic/tree/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/.agent/skills) | 工具使用、调试、测试、研究、发布 | 部分技能过期，且有提交/标签/同步操作；按需适配，保留本仓库流程 |
| [DennysOliveira/wow-addon-dev（魔兽开发技能）](https://github.com/DennysOliveira/wow-addon-dev) | 12.0 迁移、受限值、接口参考和模板 | 声明 12.0+，清单参考仍写 120001；不是 12.1 认证资料 |
| [TheMizeGuy/wow-addon-dev（跨代理开发技能）](https://github.com/TheMizeGuy/wow-addon-dev) | 开发任务路由、插件目录管理、Windows 安装示例 | 作者说明支持多种代理，但不是本宿主实测；需核查命令、引用与 12.1 数据 |
| [tusharsaxena/wow-addon（插件开发工作流）](https://github.com/tusharsaxena/wow-addon) | 测试、性能记录、文档审查与交付步骤 | 绑定 Ka0s（作者插件标准），运行时拉取外部规范，整体导入会增加额外规则与版本漂移 |

另外两个容易混淆的点：DennysOliveira 项目虽然带有 MCP 配置，但注册的是 spec-workflow（规格工作流服务），不是魔兽接口服务；TheMizeGuy 的说明明确将 Codex CLI（代码代理命令行）列为“尚未针对该技能实测”。不能把存在配置文件或兼容性声明当作本机可用证据。[服务配置](https://github.com/DennysOliveira/wow-addon-dev/blob/42bad7e0b1e2a18442806223e34d48a19076ad32/.mcp.json)、[兼容性说明](https://github.com/TheMizeGuy/wow-addon-dev/blob/f928572a9428d29327a96c2549b0068101961c4e/README.md)

特别需要修正 Mechanic 的技能：`k-mechanic`（工具知识）仍描述 53 个命令及 5173 端口，当前项目说明则为 60 个命令和 3100 端口；发布技能仍有旧参数形式及直接提交/标签操作。技能是可过期的指引，不能覆盖当前命令参数定义，更不能替换本仓库 Build and Verify（构建与验证）和 PR Flow（拉取请求流程）。[工具技能](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/.agent/skills/k-mechanic/SKILL.md)、[发布技能](https://github.com/Falkicon/Mechanic/blob/55bd418d1be3a045949cb9d7a6f4ae6abd4d5058/.agent/skills/s-release/SKILL.md)

WoW UI Simulator（魔兽界面模拟器）仍值得单独评估：作者提供无界面测试、控件树与截图输出，另有自身维护用技能目录；这不等于提供通用、已验证的插件开发技能或 MCP 服务。本次没有确认可直接采用的专用 MCP 入口。它的示例版本也不能直接当作 12.1.0.69587，仍按指南的实际插件加载与正反用例试点。[模拟器项目](https://github.com/Osso/wow-ui-sim)

## 社区采用与成熟度

以下是 GitHub（代码托管平台）接口在核查时返回的快照；最后推送时间不是稳定版本发布日期。收藏数不是用户数，搜索结果收录也不是社区推荐。

| 项目 | 收藏 / 派生仓库 | 最后推送日期（UTC，协调世界时） |
| --- | --- | --- |
| Mechanic | 20 / 5 | 2026-09-06 |
| wow_api_mcp | 0 / 0 | 2026-09-07 |
| hated-wow-mcp | 3 / 1 | 2026-09-07 |
| wow-dev-mcp | 8 / 1 | 2025-09-04 |

来源：[Mechanic 元数据](https://api.github.com/repos/Falkicon/Mechanic)、[wow_api_mcp 元数据](https://api.github.com/repos/Nighthawk42/wow_api_mcp)、[hated-wow-mcp 元数据](https://api.github.com/repos/RdyGaming/hated-wow-mcp)、[wow-dev-mcp 元数据](https://api.github.com/repos/juemrami/wow-dev-mcp)。

有独立使用线索：Wise（插件项目）的代理说明明确列出 Mechanic 的代码队列、诊断和模拟器工作流，同时提醒工具输出量大，应按具体问题调用。这证明至少有项目记录了采用方式，不能外推为主流插件社区普遍采用。[Wise 项目约定](https://github.com/claytonkimber/Wise/blob/a85e88921c9d3e7892597b24b8fb5724aa2e43de/AGENTS.md)

本次排除角色/拍卖行查询服务、怀旧服专用服务与私服服务端工具：它们解决的问题不同。最终推荐是先做一个只读接口检索试点，再按游戏部署授权验证 Mechanic 的诊断闭环；不一次安装全部候选，不改变现有六项验证与拉取请求交付入口。
