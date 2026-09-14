# 仓库测试

所有自有插件、项目和开发工具的测试统一放在根目录 `tests/`，按被测对象分组。新增插件测试使用 `tests/addons/<插件名>/`，项目测试使用 `tests/<项目名>/`；没有测试的对象不创建空目录。

| 目录 | 内容与运行条件 |
| --- | --- |
| `dev/` | 开发检查器回归，使用本机已准备的 Lua（脚本语言）检查工具 |
| `sim2gse/` | 序列项目测试；`test_*.py` 使用构造样例，`manual_native_task.py`、`manual_search_task.py`、`manual_interface.py` 依赖本机私人角色数据 |
| `sim2gse/research/` | 独立运行的原型与源码检查；`prototype-engine-check.py` 同样依赖本机私人角色数据 |
| `gear-planner/` | 装备规划器回归；纯 JavaScript（脚本语言）检查进入 PR（拉取请求），Python（编程语言）计算和浏览器检查需要本机引擎与数据 |
| `gear-planner/research/` | 固定样例回放和本地研究证据检查，需按脚本参数准备引擎、样例及报告 |

统一入口：

```powershell
build-and-verify build --project .
build-and-verify verify --project .
```

构建先于验证执行，避免引擎与构建身份文件在测试期间变化。配置位于 `.build-and-verify/config.json`，只登记干净仓库可准备、可重复的构建和验证。`sim2gse/test_*.py` 自动发现；`dev/test_inventory.py` 会拦截未登记的可移植测试。

PR（拉取请求）中的代码、配置和工作流变更依次执行产品构建和全部可移植验证；仅配置中登记的文档或 MySpec（自有规格）路径变更不构建产品，按目标分支固定提交运行匹配检查。主干推送生成可供后续拉取请求恢复的 SimulationCraft（战斗模拟器）构建缓存。缺文件、缺工具、断言失败和超时均返失败，不将跳过记为通过。依赖私人角色、本机研究引擎或历史报告的检查作为本机验收，在对应项目改动后按下方入口单独执行并记录结果。

素材构建输出到 `.local/build/assets/`，只重建仍保留原图的素材；已明确删除原图的现有成品仍由素材一致性验证保护。私人角色及研究样本仍使用原始本机证据，不上传私人文件来修复远端检查。

在仓库根目录运行单组检查：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/sim2gse -p 'test_*.py'
.venv/Scripts/python.exe tests/dev/test_checks.py
.venv/Scripts/python.exe tests/gear-planner/check-extra-input.py
node tests/gear-planner/check-async.js
```

`check-browser.cjs` 和 `check-deathknight.cjs` 需要 Playwright（浏览器自动化工具）和 Edge（浏览器）；准备脚本使用锁文件安装 Playwright。本机验收入口启动并清理本次专用的本地装备规划器服务，8765 端口已被占用时失败；不能用语法检查替代实际浏览器验收。私人角色单序列检查直接运行 `tests/sim2gse/manual_native_task.py`；完整搜索检查直接运行 `tests/sim2gse/manual_search_task.py`，使用默认十分钟预算。

生产程序仍使用的 `projects/gear-planner/fixtures/`（样例目录）保持原位。测试生成的新报告写入 `.local/tests/`；既有研究报告维持原有证据路径。新增测试时同步核对构建与验证配置的执行命令、变更匹配路径及缓存输入，不能只移动文件。

任务四浏览器回归包含在 `test_interface.py` 自动发现中，使用锁定的 Playwright（浏览器自动化工具）与 Edge（浏览器）。完整真实角色界面检查直接运行 `tests/sim2gse/manual_interface.py`，启动独立动态端口服务，核对真实计算、剪贴板、修改输入清理，并保存截图及验收摘要。
