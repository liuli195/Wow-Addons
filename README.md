# 魔兽世界插件与素材

本仓库保存个人脚本、配置文本、自制素材和第三方界面插件副本。

## 人工智能开发环境

当前目标为魔兽正式服 12.1.0（构建号 69587）。环境部署、检查范围和已知限制见[环境使用说明](DOC/environment-setup.md)；完整开发与交付流程见[协作指南](DOC/wow-addon-development-guide.md)。

首次准备工具，在仓库根目录执行：

```powershell
pwsh -NoProfile -File scripts/dev/setup.ps1
```

日常验证使用本机 build-and-verify（构建与验证）技能与命令：

```powershell
build-and-verify verify --project .
```

PR Flow（拉取请求流程）已配置本地入口；提交前读取当前技能。热修复允许管理员在授权短语校验及完整验证后直推。CodeQL（安全扫描）用于 Python（脚本语言），Lua（插件脚本）由独立检查器验证。

## 目录

| 目录 | 用途 |
| --- | --- |
| `AddOns/`（插件） | 自制插件及 AzeriteUI（第三方界面插件）；插件说明和许可证保留在各自目录 |
| `Assets/EUI_FacetedMedia/`（素材） | 原始图片、共享媒体素材和预览图片；插件运行所需的内置素材仍随插件保存 |
| `DOC/`（文档） | 开发指南、研究记录和环境说明 |
| `scripts/dev/`（开发脚本） | 环境安装、检查脚本和工具版本清单 |
| `scripts/media/`（素材脚本） | 素材生成与验证脚本 |
| `scripts/snippets/`（代码片段） | 个人 Lua（脚本语言）片段，使用前确认其运行环境 |
| `Archive/`（历史存档） | 原 `My Project` 和 `profiles`，整个目录仅保留本地并忽略 |
| `.tools/`（工具缓存） | 下载的工具和接口资料，不上传 |

## 素材生成与验证

在仓库根目录执行下列命令。需要 Python（解释器），以及 NumPy（数组处理库）和 Pillow（图像处理库）。

验证现有素材：

```powershell
build-and-verify verify --project .
```

生成素材的入口：

```powershell
.\scripts\media\build_assets.ps1
```

目前生成脚本所需的 `02-Rectangular-Fill.png` 和 `07-Circular-Border-v2.png` 在 `Assets/EUI_FacetedMedia/New-Crystal-Set/Final-PNG/` 中缺失。补齐原图前不要运行生成命令；生成过程会覆盖部分现有素材。现有成品继续保留。

## 版本管理范围

`.gitattributes`（文件属性规则）集中保存 Git LFS（大文件存储）的通用固定类型，整合量化与技能仓库的现有规则，并补充本仓库的 `.tga`（游戏贴图）。规则按类型生效，小文件匹配后也会进入大文件存储；源码和普通说明文本维持原有存储方式。

新机器需要先安装大文件存储工具，再在仓库根目录执行 `git lfs install --local`（启用当前仓库的大文件处理与推送钩子）。检出后若素材仍是文本指针，执行 `git lfs pull`（从远程取回素材）；前提是远程仓库已配置并上传对应对象。当前素材转为大文件存储不会迁移旧提交。

编辑器缓存、历史备份、游戏账号配置和本地整合包由 `.gitignore`（忽略规则）排除。公有仓库从整理后的内容建立基线；包含旧整合包的历史仅保留在原机器的本地备份分支，不推送。仓库内整理不会自动同步到游戏安装目录。

`Archive/profiles`（历史配置）已退出当前版本的跟踪，文件仍完整保留本机；此前已公开的提交仍包含旧配置，本次不重写公开历史。
