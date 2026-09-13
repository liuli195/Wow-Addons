# 仓库测试

所有自有插件、项目和开发工具的测试统一放在根目录 `tests/`，按被测对象分组。新增插件测试使用 `tests/addons/<插件名>/`，项目测试使用 `tests/<项目名>/`；没有测试的对象不创建空目录。

| 目录 | 内容与运行条件 |
| --- | --- |
| `dev/` | 开发检查器回归，使用本机已准备的 Lua（脚本语言）检查工具 |
| `sim2gse/` | 序列项目测试；`test_*.py` 使用构造样例，`manual_native_task.py`、`manual_search_task.py`、`manual_interface.py` 依赖本机私人角色数据 |
| `sim2gse/research/` | 独立运行的原型与源码检查；`prototype-engine-check.py` 同样依赖本机私人角色数据 |
| `gear-planner/` | 装备规划器的 Python（编程语言）及 JavaScript（脚本语言）回归；原生计算需要对应引擎和数据缓存 |
| `gear-planner/research/` | 固定样例回放和本地研究证据检查，需按脚本参数准备引擎、样例及报告 |

统一入口：

```powershell
build-and-verify build --project .
build-and-verify verify --project .
```

构建先于验证执行，避免引擎与构建身份文件在测试期间变化。配置位于 `.build-and-verify/config.json`：全部测试入口均已登记，`sim2gse/test_*.py` 自动发现，其余入口各自报告结果。`dev/test_inventory.py` 会拦截未登记的新测试；辅助模块须显式登记调用者。常规职业样例分别登记当前发行引擎、固定对照引擎和浏览器操作；登记检查同时核对这些参数组合。治疗与实验资料使用专用检查，不能套用常规职业回放协议。

PR（拉取请求）工作流依次执行构建和完整验证；构建失败后仍收集验证失败。完整验证表示执行全部登记项，不代表具备所有环境依赖。缺文件、缺工具、断言失败、超时均返回失败，不能将跳过记为通过。正式差异验证按当前技能使用干净工作树和固定基线。

素材构建输出到 `.local/build/assets/`，保留现有成品；缺少原图会使构建失败。私人角色及研究样本仍使用原始本机证据，不能上传私人文件来修复远端检查。远端缺少这些输入时必须报告未满足验证条件，不能声称全仓通过。

在仓库根目录运行单组检查：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests/sim2gse -p 'test_*.py'
.venv/Scripts/python.exe tests/dev/test_checks.py
.venv/Scripts/python.exe tests/gear-planner/check-extra-input.py
node tests/gear-planner/check-async.js
```

`check-browser.cjs` 和 `check-deathknight.cjs` 需要 Playwright（浏览器自动化工具）和 Edge（浏览器）；统一入口启动并清理本次专用的本地装备规划器服务，8765 端口已被占用时失败；不能用语法检查替代实际浏览器验收。私人角色单序列检查运行 `tests/sim2gse/manual_native_task.py`；完整搜索检查运行 `tests/sim2gse/manual_search_task.py`，使用默认十分钟预算，统一入口允许 660 秒含收尾。

生产程序仍使用的 `projects/gear-planner/fixtures/`（样例目录）保持原位。测试生成的新报告写入 `.local/tests/`；既有研究报告维持原有证据路径。新增测试时同步核对构建与验证配置的执行命令、变更匹配路径及缓存输入，不能只移动文件。

任务四浏览器回归包含在 test_interface.py 自动发现中，使用本机已有 Playwright（浏览器自动化工具）与 Edge（浏览器）。完整真实角色界面检查运行 tests/sim2gse/manual_interface.py，启动独立动态端口服务，核对真实计算、剪贴板、修改输入清理，并保存截图及验收摘要；统一入口允许 680 秒含浏览器启动与清理。
