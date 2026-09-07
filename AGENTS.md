# 仓库工作约定

- 使用中文输出，英文名词附中文释义。
- 开发环境与交付流程见 [协作指南](docs/wow-addon-development-guide.md)；部署、接口变更、验证或远端交付前阅读相应章节。
- 自有插件范围为 `EUI_FacetedMedia/EUI_FacetedPortrait`，素材验证复用 `EUI_FacetedMedia/verify.py`。第三方副本与个人片段边界见 [项目说明](README.md)。
- 仅面向 12.1 正式服；客户端、接口资料和工具版本以 `tools/versions.json` 为准。新增游戏接口先检索 `.tools/wow-ui-source/Interface/AddOns/Blizzard_APIDocumentationGenerated` 和同版本界面源码；注解候选不代表完整覆盖。
- 使用 `codex/` 功能分支，保留已有修改。常规验证读取当前 build-and-verify（构建与验证）技能，执行 `build-and-verify verify --project .`；正式差异验证使用干净工作树及固定基线，跳过不等于通过。
- GitHub（代码托管平台）初始化与交付读取当前 PR Flow（拉取请求流程）技能；分别报告本机检查、远端检查和实际游戏验收。
- 工具缓存位于 `.tools/`，报告位于 `.local/`。游戏部署和安装包发布按任务授权执行；素材生成缺少源图时保留现有成品。
