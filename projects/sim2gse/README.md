# Sim2GSE（角色级按键序列优化器）

本目录是项目入口。当前页面一次输入，依次搜索单目标和5目标，各最多600秒，输出两个普通循环和独立爆发序列。爆发内容来自已审核专精定义，其技能、消耗品和装备动作自动排除普通搜索。三个结果可分别复制，也可一次导入集合；取消、继续和刷新保留已完成场。当前首批审核邪恶死亡骑士，本机通过不等于实际游戏验收。运行与按法见[本地任务说明](../../docs/sim2gse/local-task.md)。

- [实施地图](../../myspec/changes/sim2gse-wayfinder/spec.md)
- [实施方案](../../docs/sim2gse/implementation-plan.md)
- [项目目录与维护边界](../../docs/sim2gse/project-boundary-proposal.md)
- [邪恶角色与独立原版基线](../../docs/sim2gse/target-evidence.md)
- [原生动作来源与首轮能力映射](../../docs/sim2gse/action-capabilities.md)
- [最小序列的数据格式与编译原型](../../docs/sim2gse/export-prototype.md)

历史首轮使用用户提供的邪恶死亡骑士样本，单目标、300毫秒；当前双场页面默认200毫秒。项目说明与研究资料位于 `docs/sim2gse/`，开发脚本按需放入 `scripts/dev/sim2gse/`；复用仓库根的工具缓存、解释器环境与本地报告目录。后续只按当前票据需要创建文件。

本项目引擎独立于配装器：从官方固定源码单独维护补丁、构建和程序，放在本项目专属目录。公共工具目录不代表共用引擎文件；不得修改、覆盖或自动调用配装器的专用引擎。产品专用构建与研究原型分目录保存。

## 搜索探索开关

默认使用旧原生起点与旧随机局部搜索。两个探索能力独立控制，写在本工作树 `.local/sim2gse/config.toml`：

```toml
[search]
rule_initialization_enabled = false
adaptive_selector_enabled = false
search_timeline = false
```

规则起点开启仅替换四个原生来源中的均匀起点，不追加路径，也不改正式独立爆发计划。选择器开启才加载模型、采集专用诊断并学习；关闭仍保留旧搜索必要的位置反馈。训练读取同一区域，逐材料起点始终使用原材料，不被规则起点替换。

任务、界面服务和训练 CLI 支持 `--rule-initialization-enabled`、`--adaptive-selector-enabled` 及对应的 `--no-…` 参数；显式参数优先，未传参数沿用配置。公开任务 API 通过 `search_config` 传同名布尔值。恢复使用任务冻结配置，不因后来改 TOML 而切换算法；旧任务未记录开关时拒绝续跑，已保存成果仍可读，已验证训练成果仍可作为新任务的重新评分起点。

轻量曲线另用 `[search] search_timeline = true` 或 `--search-timeline` 开启，`--no-search-timeline` 显式关闭；任务、服务启动及训练共用，默认关闭且不新增页面控件。它不打开 `diagnostic_logging`、不改变算法或评分缓存身份，也不增加模拟/追踪。恢复时曲线按本次参数或配置选择，算法仍沿原冻结设置。

开启后每次执行结束在任务目录保存独立 `search-timeline-*.json` 与同名静态 HTML（内嵌 SVG）。只采集已有成绩和当前赢家的修订，内存最多10,000事件，达到上限明确标截断。每10秒取当时最后已知值，首次成绩前留空，修订可下降；停止后虚线延续，不填补失败/截断以后的未知成绩。恢复是新时间段，不补造上次时间。训练逐路径独立、同次公开调用共用时间原点；双场也包含第二场等待。`call_seconds` 是业务收尾后的采集截止秒数，不是含导出完成的调用总时长；实际性能外层计时包含全部导出。强制终止可丢失尚未导出的本段曲线，导出错误不会重跑或覆盖业务结果。

离线比较（不启动任务，目录可递归包含多条路径）：

```powershell
python projects/sim2gse/task.py curves 任务目录A 任务目录B --output comparison.html
python projects/sim2gse/task.py curves --damage 任务目录 batch:已有批次键 --output damage.html
```

搜索图按已有角色输入SHA、引擎身份、模拟配置、按键间隔、重置事件和爆发计划分组；算法开关和种子只作对照标签。同角色不同算法可同图，不同角色或单目标与5目标不混图；准备失败或旧诊断缺少条件时各自单图，未知口径不自动合并。伤害图单独读取已有中心报告，必要时用 `--project 已接入项目` 指定中心；任务目录默认读取该任务受控报告或原生参考报告。图中“原生报告1秒分桶伤害统计”是原报告桶值，已含宠物，不再叠加宠物，也不归一成最终评分DPS。来源/版本或桶宽未知的外部JSON、多玩家或缺桶会说明不支持/缺数据，不补模拟。输出同时保留可审查的 JSON。


选择器需要额外安装 `requirements-selector.txt`，默认模式无需该可选组。缺依赖时显式开启会报错，不自动安装或降级；开发完整验证的依赖说明见 [测试说明](../../tests/README.md)。

## 实机时机探针

`addons/Sim2GSEProbe/` 是独立开发诊断插件，只记录玩家真实输入，不自动按键或施法，也不修改 GSE（宏序列插件）。游戏内依次使用 `/s2gprobe status`、`/s2gprobe start`；每轮结束使用 `/s2gprobe mark`，全部结束后使用 `/s2gprobe stop` 和 `/reload`。保存记录位于 `_retail_/WTF/Account/<账号>/SavedVariables/Sim2GSEProbe.lua`。每次 `start` 会替换上一段探针会话，应先保留仍需分析的旧文件。

记录中的 `click`（点击）是 GSE 按钮提交观测，`spellcast`（施法事件）来自游戏原生 `UNIT_SPELLCAST_*` 事件。公开接口不能直接读取客户端内部法术队列，后续分析只能依据两类记录反推状态转换；离线检查不能替代真实客户端验收。

## 训练假人日志分析

游戏中先用 `/combatlog` 开始记录，测试结束后再输入一次 `/combatlog` 停止记录。然后在仓库根目录运行：

```powershell
.venv\Scripts\python.exe projects\sim2gse\combat_log.py `
  "D:\Program Files\World of Warcraft\_retail_\Logs\WoWCombatLog.txt" `
  --player "角色名" `
  --duration 180 `
  --gse-debug "GSE调试导出.txt" `
  --simulation "simc-result.json" `
  --primary-target "主训练假人"
```

只有战斗日志和 `--player` 是必需参数。工具会用成功施法的目标推断主目标；需要严格指定时使用 `--primary-target`，同名目标改填 GUID（全局唯一标识）。已经在开始记录前召出的宠物或守护者可重复传入 `--owned-source "名称或GUID"`；同名来源无法唯一确定时必须填 GUID，否则日志无法证明其归属。

`--gse-debug` 用最后一次 GSE（按键序列插件）调试区间定位测试，并列出各技能尝试次数、阻断原因和估算按键间隔。默认按运行电脑的本地时区解释 GSE 时间；分析来自另一时区的日志时，用 `--gse-utc-offset 8` 指定客户端相对 UTC（协调世界时）的小时偏移。`--simulation` 接受 SimC（模拟引擎）的 JSON 结果；角色和时长一致时，工具只用已确认的主目标比较单目标 DPS（每秒伤害），并明确报告排除的次要目标伤害。`damage` 和 `dps` 使用日志记录的完整命中伤害，适合不会死亡的训练假人；`overkill` 单列过量伤害，`effective_damage` 和 `effective_dps` 保留普通目标的实际扣血口径。伤害来源按法术 ID（标识符）和归属单位分组；SimC 未按法术细分的差额单列，不猜测归属。

战斗日志不能证明专精、天赋、装备、游戏版本、候选序列、敌人攻击和生命时间线、目标防御、各技能实际覆盖范围以及输入节奏与模拟一致。输出中的百分比只是完整命中伤害的吞吐量比值；`simulation_comparison.accuracy_assessed` 在这些条件未核对时为 `false`，不能将该百分比当作模拟准确率结论。

正式早停在两种搜索模式下共用：全局冠军晋升，或非初始起点通过统计验证成为该分支冠军，均视为本轮有改善。仅完整无改善轮累加一个全局计数；未完成轮有改善清零、无改善不累加。正式阈值为实际有效分支数，预训练沿用连续两轮无改善且无 600 秒总硬时限。初始分支建立不作为分支改善，不新增早停开关。
