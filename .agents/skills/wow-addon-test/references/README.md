# WoW Addon Test（魔兽插件逻辑测试工具）1.0.0

**可放进项目使用的命令行工具＋共享技能。没有代理插件打包，没有服务，没有截图测试。**

第一版提供 40 个专精的基础人工接口场景，覆盖生命、主资源和已声明的职业资源语义。AI（人工智能）负责首次接入真实插件；接好以后直接运行命令即可回归测试，不需要模型服务。

## 1. 最短使用方式

把整个 `wow-addon-test` 目录放在你的插件项目根目录，然后向本地编程代理发送：

> 读取 `wow-addon-test/skills/wow-addon-test/SKILL.md`。按技能检查环境，必要时安装该工具的本地依赖；读取本项目真实源码，完成生命、主资源和职业资源测试接入，运行所有已支持的 40 专精基础用例。不要用示例插件替代本项目，不要修改参考基线。给出真实差异、覆盖缺口和验证报告；通过后在临时副本中验证至少一个实际缺陷会被抓到。

**首次接入不能由一个无模型脚本自动理解所有陌生插件。技能提供具体步骤、接口契约和两个可工作的适配示例，供你现有的代理执行。**

## 2. 安装与演示

### Windows（视窗系统）

需要已安装 Python（编程语言）3.10 或以上。进入工具目录：

```bat
py -3 bootstrap.py
run.cmd doctor
run.cmd selftest
run.cmd run --config examples\event-hud\wowtest.json --output reports\local-event.json
```

`bootstrap.py` 建立工具自己的 `.venv` 并安装 Lupa（Python/Lua 桥接库），首次安装需要网络。精确安装版本写入 `requirements.installed.txt`。不安装到玩家插件目录，也不改变游戏客户端。

### Linux / macOS（其他桌面系统）

```sh
python3 bootstrap.py
./run.sh doctor
./run.sh selftest
./run.sh run --config examples/event-hud/wowtest.json --output reports/local-event.json
```

已有兼容 Lua（脚本）运行时时可以不安装 Lupa。工具支持 Lupa Lua 5.1、`WOWTEST_LUA` 指定的程序，以及本机 Lua 5.3/5.4 共享库。建议 Windows 使用 Lupa Lua 5.1。普通 Lua 不是魔兽客户端内置运行时。

### 本次实际验证

| 项目 | 结果 |
|---|---|
| 宿主 | Linux + Python 3.13 + Lua 5.4 共享库 |
| 用例库 | 40 专精，846 条，1,613 检查点 |
| 事件型示例插件 | 846/846 通过 |
| 逐帧型独立示例插件 | 846/846 通过 |
| 原生方法摘录重生成 | 与保存的基线完全一致 |
| 工具自测 | 详见 `reports/selftest.json`，包含缺陷注入、超时和清理检查 |
| 尚未执行 | Windows 安装、真实 MYUI、真实客户端、代理自主接入端到端验收 |

本次执行报告不是你的 MYUI 测试结果。接入以后，报告会记录实际加载文件和适配器的摘要。

## 3. 常用命令

以下命令在工具目录使用；也可以从任意目录执行带路径的 `run.cmd` 或 `wowtest.py`。

| 命令 | 功能 |
|---|---|
| `run.cmd doctor --json` | 环境与基线完整性检查 |
| `run.cmd catalog --json` | 40 专精、资源种类、适用范围和缺口 |
| `run.cmd validate` | 用例结构与完整性检查 |
| `run.cmd init --project .. --name MYUI` | 在上级项目创建 `.wow-test` 配置和故意不通过的适配模板 |
| `run.cmd run --config ..\.wow-test\wowtest.json --output ..\.wow-test\report.json` | 执行真实插件并生成 JSON（数据）与 Markdown（说明）报告 |
| `run.cmd run --config <配置> --specs 250 --case rune` | 定向重跑鲜血死亡骑士符文相关用例 |
| `run.cmd compare --actual <输出.json> --output <报告.json>` | 比较外部测试输出，不要求使用内置运行器 |
| `run.cmd export --specs 259 --output <文件.json>` | 导出包含预期的独立可消费数据 |
| `run.cmd export --inputs-only --specs 259 --output <文件.json>` | 只导出输入，不泄露参照路由字段 |
| `run.cmd reference-check` | 重新执行附带原生方法摘录，与固定基线比较，不改写基线 |
| `run.cmd selftest` | 执行工具和示例的自动自测 |

写入已有报告是允许的；初始化、技能安装和用例导出会拒绝覆盖不同的用户内容。不要把报告输出路径指向源代码文件。

## 4. 可选：注册为代理的项目技能

不是插件打包，只安装共享技能：

```bat
run.cmd install-skill --project .. --agent codex
run.cmd install-skill --project .. --agent claude
```

分别写入项目 `.agents/skills/wow-addon-test` 和 `.claude/skills/wow-addon-test`。其中的指针仍引用原来的工具目录，不复制运行器或用例库。不同代理触发方式不同；首次显式要求读取技能最可靠。移动工具以后需要更新技能指针。

不注册也能用：让代理直接读取工具中的 `SKILL.md` 即可。

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

`reference/sources.json` 保存原文件标识、哈希、方法名和观察边界。基线中大量普通数值是人工构造，既不是实机角色档案，也不证明该天赋真的造成某个上限。

网络可用时，可额外下载完整锁定源文件并做语句标记匹配：

```bat
.venv\Scripts\python.exe reference\verify_upstream.py
```

该脚本校验完整文件的 Git（版本管理）对象摘要，再比较所选方法的 Lua 标记序列；不会更新本版源码或基线。本次环境未执行完整网络下载复核，具体边界见 `docs/VALIDATION.md`。

## 7. 文档入口

- `docs/CONTRACT.md`：数据、事件、适配和退出码的详细约定。
- `docs/COVERAGE.md`：每个专精的实际用例数量、资源种类和额外缺口。
- `docs/VALIDATION.md`：真实执行范围和尚未验证项目。
- `skills/wow-addon-test/SKILL.md`：交给代理的完整接入指令。
- `examples/event-hud`、`examples/poll-hud`：两个独立实现与极薄适配。
- `reports/selftest.json`：可复查的工具自测结果。

## 安全与开发依赖

只在受信任的项目上运行。Lua 环境隔离和进程超时用于防止测试互相污染/挂死，不是恶意代码安全沙箱。工具不访问账号、银行或聊天数据，不上传源码，不启动监听端口，不需要模型 API（接口）密钥。测试源码和数据不应加入正常玩家发布包的 `.toc`（插件清单）。
