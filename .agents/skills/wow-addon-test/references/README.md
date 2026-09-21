# WoW Addon Test（魔兽插件逻辑测试工具）1.0.0

**可放进项目使用的命令行工具＋共享技能。没有代理插件打包，没有服务，没有截图测试。**

第一版提供 40 个专精的基础人工接口场景，覆盖生命、主资源和已声明的职业资源语义。AI（人工智能）负责首次接入真实插件；接好以后直接运行命令即可回归测试，不需要模型服务。

## 1. 最短使用方式

把整个 `wow-addon-test` 目录放在你的插件项目根目录，然后向本地编程代理发送：

> 读取本技能根目录下的 `SKILL.md`。按技能检查环境，必要时安装该工具的本地依赖；读取本项目真实源码，完成生命、主资源和职业资源测试接入，运行所有已支持的 40 专精基础用例。不要用示例插件替代本项目，不要修改参考基线。给出真实差异、覆盖缺口和验证报告；通过后在临时副本中验证至少一个实际缺陷会被抓到。

**首次接入不能由一个无模型脚本自动理解所有陌生插件。技能提供具体步骤、接口契约和两个可工作的适配示例，供你现有的代理执行。**

## 2. 安装与演示

**本技能是纯 Python 标准库实现，不需要安装任何 Python 依赖**，也不往用户级或玩家插件目录写东西。只需要一个 Python 3.10 或以上，加一个可用的 Lua（脚本）后端。

后端由 `doctor` 报出，按这个顺序找：`WOWTEST_LUA` 指定的程序 → `lupa.lua51` → 本机 Lua 5.3/5.4 共享库 → 本机 `lua` 可执行程序。都没有时，把 `WOWTEST_LUA` 指向一个 Lua 程序即可。

```bat
python scripts\wowtest.py doctor --json
python scripts\wowtest.py selftest --json
python scripts\wowtest.py run --config assets\examples\event-hud\wowtest.json --output .wow-test\local-event.json
```

Linux / macOS（其他桌面系统）把 `python` 换成 `python3`、反斜杠换成正斜杠即可；`scripts/wowtest.py` 本身跨平台。

普通 Lua 不是魔兽客户端内置运行时，因此本工具**不声称**覆盖受限值、污染与受保护执行——那部分只在真实客户端里成立。

### 上游交付时的自验

下表是工具作者在交付时那次运行的结果，**不是本仓库的当前状态**，也不是你的插件测试结果。本仓库当前状态看 `selftest` 的现场输出。

| 项目 | 结果 |
|---|---|
| 宿主 | Linux + Python 3.13 + Lua 5.4 共享库 |
| 用例库 | 40 专精，846 条，1,613 检查点 |
| 事件型示例插件 | 846/846 通过 |
| 逐帧型独立示例插件 | 846/846 通过 |
| 原生方法摘录重生成 | 与保存的基线完全一致 |
| 工具自测 | 含缺陷注入、超时和清理检查 |

接入以后，报告会记录实际加载文件和适配器的摘要。

## 3. 常用命令

下面的 `<技能>` 指本技能目录的绝对路径；命令可从任意目录执行。
技能只有 `scripts/wowtest.py` 这一个入口，没有包装脚本。

| 命令 | 功能 |
|---|---|
| `python <技能>/scripts/wowtest.py doctor --json` | 环境与基线完整性检查 |
| `python <技能>/scripts/wowtest.py catalog --json` | 40 专精、资源种类、适用范围和缺口 |
| `python <技能>/scripts/wowtest.py validate` | 用例结构与完整性检查 |
| `python <技能>/scripts/wowtest.py init --project .. --name MYUI` | 在上级项目创建 `.wow-test` 配置和故意不通过的适配模板 |
| `python <技能>/scripts/wowtest.py run --config ..\.wow-test\wowtest.json --output ..\.wow-test\report.json` | 执行真实插件并生成 JSON（数据）与 Markdown（说明）报告 |
| `python <技能>/scripts/wowtest.py run --config <配置> --specs 250 --case rune` | 定向重跑鲜血死亡骑士符文相关用例 |
| `python <技能>/scripts/wowtest.py compare --actual <输出.json> --output <报告.json>` | 比较外部测试输出，不要求使用内置运行器 |
| `python <技能>/scripts/wowtest.py export --specs 259 --output <文件.json>` | 导出包含预期的独立可消费数据 |
| `python <技能>/scripts/wowtest.py export --inputs-only --specs 259 --output <文件.json>` | 只导出输入，不泄露参照路由字段 |
| `python <技能>/scripts/wowtest.py reference-check --output <报告.json>` | 重新执行附带原生方法摘录，与固定基线比较；屏幕只显示受限摘要，完整结果落盘且不改写基线 |
| `python <技能>/scripts/wowtest.py selftest` | 执行工具和示例的自动自测（加 `--output <路径>` 才落盘） |
| `python <技能>/scripts/maintain.py` | 维护入口：重生成用例与基线，带缺口时拒绝写入 |

写入已有报告是允许的；初始化、技能安装和用例导出会拒绝覆盖不同的用户内容。不要把报告输出路径指向源代码文件。

## 4. 可选：注册为代理的项目技能

不是插件打包，只把共享技能复制到目标项目的技能根目录：

```bat
python <技能>/scripts/wowtest.py install-skill --project .. --agent codex
python <技能>/scripts/wowtest.py install-skill --project .. --agent claude
```

`--agent codex` 写入目标项目的 `.agents\skills\`，`--agent claude` 写入 `.claude\skills\`。
**目标是项目目录，不是用户级目录**；已存在且内容不同的文件会被拒绝覆盖。
技能**自包含**：工具、参考资料与数据都在技能目录内，不需要额外的定位文件。
不同代理触发方式不同；首次显式要求读取技能最可靠。

不注册也能用：让代理直接读取技能目录里的 `SKILL.md` 即可。

## 5. 40 专精覆盖到底意味着什么

| 已提供 | 不代表 |
|---|---|
| 每个专精都存在生命、主资源和次级资源选择/状态用例 | 所有天赋和真实战斗场景已实测 |
| 连击点、德鲁伊连击点、圣能、真气、奥术充能、碎片、精华、符文、醉拳参照 | 所有技能、光环计数都已收集 |
| 专精往返、德鲁伊形态、容量变化、单位换算、缺失值等基础序列 | 人工事件顺序就是真实客户端的唯一顺序 |
| 普通可读数值的原生逻辑对比 | 受限值、污染、战斗锁定和安全框架验证 |

**明确缺口：增强的漩涡武器、复仇/噬灭的附加灵魂计数、增辉的黑檀之力时间等未包含原生预期。** 它们在目录和每次报告里保留，不冒充已通过。该工具允许扩充，但本版不为了凑“全资源”编造正确答案。

`none` 只是基本契约“未选择额外次级组件”，不是游戏事实“这个专精没有额外机制”。项目已经实现额外计数时不能删除该功能来适配 `none`。应报告差异/缺口，或明确只测已有对应契约的组件。

## 6. 原生参照怎么来的

锁定镜像版本 `12.1.0.69875`，提交 `78282522143e25c3540583734fd192c3d69be910`。本版运行的是读取并审核过的**16 个原生方法摘录**，保留原有计算语句，在明确的输出边界记录结果；不是完整原生文件、XML（界面定义）或客户端模拟。

`assets/reference/sources.json` 保存原文件标识、哈希、方法名和观察边界。基线中大量普通数值是人工构造，既不是实机角色档案，也不证明该天赋真的造成某个上限。

网络可用时，可额外下载完整锁定源文件并做语句标记匹配：

```bat
python scripts\reference\verify_upstream.py
```

该脚本校验完整文件的 Git（版本管理）对象摘要，再比较所选方法的 Lua 标记序列；不会更新本版源码或基线。本次环境未执行完整网络下载复核，具体边界见 `references/VALIDATION.md`。

## 7. 文档入口

- `SKILL.md`：交给代理的完整接入指令（本技能入口）。
- `references/CONTRACT.md`：数据、事件、适配和退出码的详细约定。
- `references/WORKFLOW.md`：AI 接入的执行清单。
- `references/COVERAGE.md`：每个专精的实际用例数量、资源种类和额外缺口。
- `references/VALIDATION.md`：真实执行范围和尚未验证项目。
- `assets/examples/event-hud`、`assets/examples/poll-hud`：两个独立实现与极薄适配。
- `assets/data/manifest.json`：数据资产的摘要清单，可直接读；用例与基线是压缩容器，经由命令使用。

## 安全与开发依赖

只在受信任的项目上运行。Lua 环境隔离和进程超时用于防止测试互相污染/挂死，不是恶意代码安全沙箱。工具不访问账号、银行或聊天数据，不上传源码，不启动监听端口，不需要模型 API（接口）密钥。测试源码和数据不应加入正常玩家发布包的 `.toc`（插件清单）。
