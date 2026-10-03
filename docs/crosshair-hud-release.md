# 准星HUD正式打包与反馈

正式包从白名单生成，不直接复制整个源码目录。现有个人设置继续使用，不覆盖或清空WTF（个人设置存档目录）。

## 打包

```powershell
.venv/Scripts/python.exe scripts/dev/package_crosshair_hud.py
```

输出在 `.local/dist/crosshair-hud/<安装包编号>/`：

- `MYUI_CrosshairHUD.zip`：可分发的压缩包，解压内容放入游戏 `Interface/AddOns`。
- `AddOns/`：已检查的运行文件。
- `manifest.json`：包外文件清单、大小和校验值，供本机检查。

包含准星HUD的7个运行代码文件、加载清单、MYUI公共核心的2个文件和22张BLP（游戏贴图）素材。保留已验收的素材字节和完整逐级缩小图片；打包不重新加工素材。

不包含PNG（原图核对文件）、Debug.lua（开发测试代码）、固定层数假数据、边缘对照页、独立测试插件、旧备份和制作脚本。这些仍保留在仓库或本地工作区。EllesmereUI（设置界面依赖）需要用户另行安装。

## 带备份部署

```powershell
.venv/Scripts/python.exe scripts/dev/package_crosshair_hud.py --deploy 'D:/Program Files/World of Warcraft/_retail_/Interface/AddOns'
```

先检查安装包，再把以下准确范围备份到 `.local/game-deploy-backups/<日期时间-编号>/`，逐文件核对备份后才部署：

- `MYUI_CrosshairHUD/`。
- `MYUI/Media/CrosshairHUD/`。
- `MYUI/MYUI.toc`、`MYUI/Series.lua`。
- 已存在的 `MYUI_CrosshairHUDEdgeTest/`。

部署后这两个运行目录只留下正式文件，独立测试插件从游戏中移除。MYUI其他素材、其他插件和个人设置都保留。备份清单记录部署前文件校验值；备份核对失败时不动游戏目录。

需要恢复时，退出游戏，仅清空上述两个运行目录并复制备份中对应内容，恢复备份中的公共核心文件和原有测试插件（如果存在）。不要复制到WTF，也不要清理整个MYUI目录。部署中断时同样从本次备份恢复。

部署后先重载界面；如文件或素材未更新，完整退出并重进游戏。真实游戏显示效果由游戏验收确认，本机测试不替代游戏验收。

## 用户反馈

输入 `/chh diag`（手动生成诊断报告），在弹出的文本窗口全选并复制。`/chh report` 和 `/chh` 也可打开报告。按退出键关闭。

报告包含插件和游戏版本、安装包编号、依赖是否加载、相关设置、最近读取状态及凝固之血原生绑定是否就绪。受游戏限制的数据只标注受限，不尝试解密或计算。报告不包含账号、角色名、聊天、本机路径和错误原文。

聊天框只提示报告已生成；插件不发送报告、不自动记录日志，也不增加诊断轮询。反馈时用户自行附上问题描述、截图和复制的报告。
