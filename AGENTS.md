# 仓库开发约定

使用中文输出，英文术语附中文释义。保留已有修改，在同一工作树的 `codex/` 功能分支开发。

## 主干流程与五个核心技能

按宿主当前技能清单加载对应入口，详细门禁以技能为准：

1. **dev-flow（开发流程）**：核对分支和固定基线 → 需求、设计与任务拆分 → 获准开发 → 逐票串行实施，使用 TDD（测试驱动开发）和独立审查 → 验证 → 规格与交付门禁。开始变更时加载；项目补充见[协作指南](docs/wow-addon-development-guide.md)。
2. **my-spec（自有规格）**：管理 `myspec/specs/` 正式规格；需求与票据保存在 `myspec/changes/`。新增、审查或审计规格时加载相应入口，按技能预览、确认和应用。读写票据前读[任务跟踪约定](docs/agents/issue-tracker.md)，分拣前读[标签约定](docs/agents/triage-labels.md)。
3. **build-and-verify（构建与验证）**：构建、验证或修改检查配置时加载相应入口；使用统一命令并确保所有测试被覆盖。正式差异验证使用干净工作树和固定基线，失败、缺依赖与跳过分别报告。入口与测试条件见[仓库测试说明](tests/README.md)。
4. **pr-flow（拉取请求流程）**：初始化或交付时加载对应入口；完成提交、推送、检查和审查门禁后再按授权合并、清理。遵循开发流程的交付授权，分别报告本机检查、远端检查和实际游戏验收；详见[协作指南](docs/wow-addon-development-guide.md)。
5. **subagent-policy（子代理策略）**：使用子代理时加载并遵循该技能。

调查、设计和审查前读[领域文档约定](docs/agents/domain.md)，据此加载术语和设计决策。

## 魔兽背景与工作边界

仅面向 12.1 正式服，客户端、接口和工具版本以[版本清单](scripts/dev/versions.json)为准。新增游戏接口先查 `.tools/wow-ui-source/Interface/AddOns/Blizzard_APIDocumentationGenerated` 及同版本界面源码；注解和本机模拟不能替代游戏验收。环境准备见[环境说明](docs/environment-setup.md)，接口、部署及发布前阅读[协作指南](docs/wow-addon-development-guide.md)对应章节。

自有游戏插件为 `addons/EUI_FacetedPortrait/`；MYUI 系列为 `addons/MYUI/`（公共核心：共享素材与 EUI 侧边栏名册）与 `addons/MYUI_CrosshairHUD/`（准星HUD，硬依赖 EllesmereUI 与公共核心，独立安装但只发布一个项目）；Sim2GSE 的开发诊断插件为 `addons/Sim2GSEProbe/`，只采集用户主动触发的实机证据。第三方副本、素材及个人片段边界见[项目说明](README.md)。游戏部署和安装包发布按任务授权执行；素材缺少源图时保留现有成品。

## 目录导航

- `addons/`、`projects/`：游戏插件与独立项目；`assets/`：素材。
- `tests/`：全仓测试，按插件、项目和开发工具分组；新增测试须接入统一验证。
- `docs/`：项目文档；`myspec/specs/`：正式规格；`myspec/changes/`：变更需求和票据。
- `scripts/dev/`、`scripts/media/`、`scripts/snippets/`：开发工具、素材处理和个人片段。
- `.tools/`：工具与资料缓存；`.local/`：运行证据；`archive/`：仅保留本地的历史存档，整个目录保持忽略。

<!-- 技能配置说明：保留原有区块，补充仓库说明时不要合并或删除。 -->
## Agent skills（代理技能）

开发变更使用当前 dev-flow（开发流程）技能，按其入口加载依赖、执行阶段和确认门禁。仓库约定补充项目边界，流程规则以当前技能为准。

### Issue tracker（任务跟踪）

需求和任务使用本地文件；读写前阅读 [任务跟踪约定](docs/agents/issue-tracker.md)。

### Triage labels（任务分拣标签）

使用默认五类标签；分拣任务时阅读 [任务分拣标签](docs/agents/triage-labels.md)。

### Domain docs（领域文档）

调查、设计和审查前阅读 [领域文档约定](docs/agents/domain.md)，按其规则加载相关术语和决策。
