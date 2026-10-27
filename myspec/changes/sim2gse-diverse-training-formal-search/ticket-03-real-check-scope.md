# 四项真实检查：只读核查与待授权范围

本文件是执行前范围，不是通过记录。当前四项均未运行。用户本轮明确禁止新真实模拟；本票未以普通测试替代它们，也未安装或重编译依赖。

## 测试及影响

| 节点（tests/sim2gse下） | 实际动作 | 新模拟 | 时间/新增磁盘预估（非实测、非硬上限） |
| --- | --- | --- | --- |
| `test_data_store_connection.py::test_connected_consumer_reads_writes_without_old_user_installation` | 复制既有约63.6KB测试技能到隔离临时项目，再用现有Python连接该隔离项目并写读合成Parquet/BLOB；不连接生产数据中心 | 无 | 1–5秒，低于1MB量级 |
| `test_search.py::SearchAndValidationTests::test_owned_process_tree_hard_exit_does_not_stop_other_owner` | 建立两组owner→child→grandchild Python进程，终止本测试owner并验证只清理其所属子树；另一组保留至测试清理 | 无 | 1–20秒，文本记录小于1MB；启动等待每组8秒及清理等待另计 |
| `test_native_compatibility.py::NativeComparisonTests::test_original_baseline_and_disabled_controller_keep_native_combat` | 现有original、baseline及禁用控制器的controlled各运行一次；各请求2迭代、180秒模拟时间、单目标，比较战斗报告 | 有，3次引擎调用 | 2–15秒，报告约1–10MB量级；original子进程超时30秒 |
| `test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate` | 本机HTTP服务、现有Node/Playwright与无头Edge；页面输入到双场引擎、编译、隔离物理存储、复制与清空。固定一个合法起点且不改变行为，两代自然停滞；并发1、参考2、粗评32、正常3×128，单目标及5目标各执行一次 | 有，每场参考、粗评及3批复测；不做训练 | 10–40秒，预计10–50MB量级但浏览器临时目录峰值未测，不能保证总新增≤50MB；页面等待35秒，Node进程超时120秒 |

页面前半部分使用拦截响应检查交互；后半部分是真实双场链，不能把整项说成纯UI检查。固定起点仅减小种群，未降低正式复测批数或请求数；两场各预期381有效复测样本。正常无重试且空隔离成果库的固定单候选路径，每场为1次参考、1次粗评、3次复测，共双场10次原生调用、836次请求迭代；加三引擎一致性共13次调用、842次请求迭代。报告失败的既有重试可能增加调用，不能把该正常路径计数当硬上限。准备含能力目录检查与编译，不额外执行训练。表内时间不是完整官方检查承诺。

现有三个预编译引擎只读身份核对已完成：baseline142117172字节、controlled142213147字节、original142004854字节；没有重建。Node、测试数据中心副本、Playwright目录及Edge可执行文件存在。文件存在不证明运行链通过；没有执行浏览器或引擎来提前验证。

## 最小运行建议（尚未执行）

若主会话取得真实验证授权，先明确50MB限制下浏览器临时目录峰值的处理，再使用仓内临时目录；不安装、重编译或采集真实训练数据。单项诊断命令如下，均须用实际绝对仓库路径设置TEMP/TMP，以避免tempfile落到仓外：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:TEMP='D:\My Project\Wow Addons\.local\tests\ticket03-real-temp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP
.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_native_compatibility.py::NativeComparisonTests::test_original_baseline_and_disabled_controller_keep_native_combat -p no:cacheprovider --basetemp=.local/tests/ticket03-native --durations=1
.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate -p no:cacheprovider --basetemp=.local/tests/ticket03-page --durations=1
```

另外两项用上表完整节点替换相应节点即可；它们不模拟，但按本次“只读核查四项”的任务边界尚未单独执行。不要为诊断重复跑一轮后再无必要地重复全链；优先在授权后直接完成正式入口。

## 正式验证门禁

统一配置真实组命令为：

```powershell
.venv/Scripts/python.exe -m pytest -q tests/sim2gse -m real --strict-markers --basetemp=.local/t/gse-r --dist=worksteal
```

配置由统一工具补入2个pytest工作进程，单组timeoutSeconds=600；整个本机正式验证另有60秒预算，不可用单组600秒绕过。需在干净工作树和稳定提交执行：

```powershell
build-and-verify verify --project . --base a914e40c9e20225647729b0ea16d680cc476fdf9 --execution-context local
```

上述入口会按固定基线选出适用检查，包含真实组；不能用PR模式、删检查、降预算参数或声称普通全绿绕过。已有受检构建可供最小冒烟；本次不执行build重新编译。历史README记录的约17–20秒真实组/约29秒整仓仅供估算，绝不是本提交实测。当前状态：待真实模拟及必要临时磁盘范围授权，未执行、非失败、非通过。
