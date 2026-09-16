# 魔兽插件自动化测试与调试配套方案

核查日期：2026-09-17。目标：为「准星 HUD（MYUI_CrosshairHUD）」与「Sim2GSE（按键序列优化器）」寻找可落地的自动化测试与调试配套方案。

本次是**案头核查**：读了上游源码、配置、官方文档与政策原文，并在本机做了只读实测（客户端版本、SavedVariables 写入行为、进程套接字）。**没有安装或运行任何候选工具，没有游戏内验收**。所有结论标注证据层级：【读源码】【本机实测】【官方原文】【作者文档声称】【未核实】。

本报告承接 [插件调试与测试研究](wow-addon-debug-testing.md)（2026-09-07）与[插件专用人工智能工具研究](wow-addon-ai-tools-research.md)（2026-09-08）。那两份文档的候选清单本次逐条复核，**其中三条结论需要更正**，见第四节。

**落地方案见[实施计划](../myspec/changes/wow-addon-automation/plan.md)**：把本报告的结论按投入产出比排成可施工的顺序，每项标注投入、收益、确定性与前置验证。

## 一、结论摘要

| 判断 | 内容 |
| --- | --- |
| **没有替代品** | 不存在能替代实机验收的成熟方案。界面外观、受限值（Secret Values）、受保护操作三层，离线工具原理上验不了 |
| **无人闭环不存在** | 「改代码 → 自动重载 → 回读结果」在合规前提下**没有实现路径**，且卡点只有一步：触发那次 `/reload`（详见第二节） |
| **两处确定性收益** | ① 准星 HUD 的**控件几何**可被自动断言（±1 像素），这是当前唯一无替代品的空白层；② Sim2GSE 的**序列对齐**只差一段纯离线算法，无需重新采集数据 |
| **一条必须先做的验证** | 准星 HUD 硬依赖 EllesmereUI 与 MYUI，**这两个能否在模拟器里加载成功未经验证**。在验证这条之前，不应把模拟器写成既定方案 |
| **一处仓库自身的不一致** | 探针插件的**较新版本只存在于游戏安装目录，从未提交**（详见 3.4） |
| **一处版本漂移** | 本机客户端已是 **12.1.0.69814**，仓库仍锁定 **69587**（详见 5.1） |

## 二、能力边界：为什么无人闭环不存在

这一节解释了为什么下面所有方案都必须保留人工环节。三条都是硬约束，不是工具成熟度问题。

### 2.1 插件沙箱内没有文件系统

【官方原文】暴雪 Lua 是改过的 Lua 5.1，**整个 `os` 模块被移除**，`io` 库也不存在；只有 `date()`、`time()`、`difftime()` 三个函数被提升为全局。`os.clock`、`os.getenv`、`io.*` 全部不可用。[Lua functions](https://warcraft.wiki.gg/wiki/Lua_functions)

【读源码】对 `.tools/wow-ui-source`（12.1）全量检索 `os.` / `io.` 调用：**0 命中**，同期 `time()` 使用 18 次。旁证：WoW Lua 虚拟机的复刻项目 [Meorawr/elune](https://github.com/Meorawr/elune) 中，`syslib_global[]` 只有 3 项，`reflibs[]` 无 `io` 条目。

唯一像文件 API 的是 `C_UIFileAsset.IsKnownFile`，它只针对贴图/资产路径，文档明写不验证松散文件的可打开性，**不返回修改时间、不返回哈希、不能枚举目录**。

**推论**：插件**无法感知代码文件变更**——它连"文件"这个概念都没有。

### 2.2 重载必须由硬件事件触发

【读源码】`Blizzard_SharedXML/InterfaceUtil.lua` 全文只有三行：

```lua
function ReloadUI()
	C_UI.Reload();
end
```

【官方原文】`C_UI.Reload` 被标注 `hwevent`——含义是「需要硬件事件，即键盘/鼠标输入」，**但它没有被标 `protected`**（那个才是「只能由安全代码调用」）。精确含义：任何代码都能调，**但必须在键鼠输入的响应路径中**。[API:C_UI.Reload](https://warcraft.wiki.gg/wiki/API:C_UI.Reload)

**注意**：暴雪生成的接口文档里**根本不含 `hwevent` 字段**（对 `wow-ui-source` 与 `wow-api` 全量检索 `hwevent` 为 0 命中）。所以「文档无标注」**不能**推断「无限制」——`C_UI.Reload` 正是「文档无标注但实为 hwevent」的活例。

`/reload` 斜杠命令、`/console ReloadUI`、CVar `reloadUI` **全部走同一个 `C_UI.Reload()`**，不存在绕过该限制的旁路。

### 2.3 结果只在三个时机落盘

【官方原文】客户端只在**登出、断线、退出游戏、重载界面**四个时机把变量写入磁盘，**没有任何会话中途刷盘 API**。[Saving variables between game sessions](https://warcraft.wiki.gg/wiki/Saving_variables_between_game_sessions)

【本机实测】调查期间游戏正在运行。对账户级 SavedVariables 做 **~2.5 分钟、每 3 秒、覆盖 307 个文件**的写入轮询：**零个插件 SavedVariables 被写入**；34 个文件的修改时间停在 02:05（=上次登出时刻）。

**推论**：想读到结果，就必然先发生一次重载——回到 2.2 的死结。

### 2.4 合成输入是唯一的"解法"，也是唯一的红线

外部程序监听文件变化、再向游戏窗口注入按键（如 `SendKeys('^+r')`）在技术上可行，[Falkicon/Mechanic](https://github.com/Falkicon/Mechanic) 就是这么做的。

但【官方原文】暴雪 EULA 的 Cheating 条款明文禁止 **bots**——「任何未经暴雪明确授权、允许**自动控制游戏**的代码和/或软件」，且注明手段「无论是硬件、软件、两者结合，**还是其他方式**」。**该条款没有任何"是否获得游戏优势"或"意图"的豁免**。[Blizzard EULA](https://www.blizzard.com/en-us/legal/fba4d00f-c7e4-4883-b8b9-1b4500a402ea/blizzard-end-user-license-agreement)

【官方原文】CN 版 EULA 措辞**比英文版更严**（动词列表多出「**安装**」）。[CN 战网 EULA](https://legal.battlenet.com.cn/zh-cn/legal/2e90163d-612f-41a5-addd-8a837ac43d02/non-printable)

【本机实测】风险口径：公开可查的案例中**没有**「仅用 SendKeys 触发 reload 而被封」的记录；但没有记录不等于安全——检测边界不公开，且暴雪官方明确拒绝披露。

**结论：不推荐把合成输入写进流程的硬依赖。** 本报告后续所有建议均不含该手段。

### 2.5 一个零风险、可一锤定音的实验

`hwevent` 标注来自社区 Wiki，而暴雪生成文档不含该字段，两者不互证。在游戏内执行下面这一行可以定论：

```
/run C_Timer.After(2, function() ReloadUI() end)
```

- 若界面重载 → 计时器路径可行，**沙箱内定时盲重载成立**（体验差，但可用）
- 若报 `ADDON_ACTION_BLOCKED` → `hwevent` 结论坐实，沙箱内彻底无解

该实验完全在沙箱内，不碰外部工具，无政策风险。**建议先做这个再决定任何投入。**

### 2.6 一条会削弱"自动重载"价值的硬约束

【官方原文】重载界面只更新**已经加载过的**插件文件；**新增或删除文件、修改 `.toc` 清单，必须重启整个游戏**。[API:C_UI.Reload](https://warcraft.wiki.gg/wiki/API:C_UI.Reload)

也就是说，即便 2.5 的实验成功，它也只能覆盖"改已有 `.lua`"这一半开发循环。

### 2.7 官方通道的核查结果

**官方允许的、能与客户端交互的外部通道：不存在。**

【读源码】Battle.net 的 Game Data / Profile API 全部端点的 HTTP 方法**穷举结果只有 `GET`**（脚本核验，方法集合 = `{GET}`）——没有 POST/PUT/DELETE，没有任何"向客户端发指令"的入口。它能给的是静态游戏数据与角色/公会**快照**，官方原文写明角色数据「**在角色登出时**更新」。它读不到 UI 状态、读不到任何插件数据、没有事件流。[官方文档](https://community.developer.battle.net/documentation/world-of-warcraft/game-data-apis)

这从官方一侧印证了 2.1–2.3：**外部程序与游戏客户端是隔离的两套系统。**

**PTR 不是政策沙盒。**【官方原文】EULA 全文检索：`PTR` **0 次命中**、`Public Test` **0 次命中**、`test realm` **0 次命中**。唯一的测试相关条款（Beta Testing Pre-Release Versions）只是**增加**条件（须被指定、账号须良好状态、保密义务），**没有任何"规则放宽"表述**。官方 2025-08-05 的第三方软件公告**未区分正式服与 PTR**。**不要假设在 PTR 上跑自动化更安全。**

**CI 里现实可用的"官方信号"只有两件事**：

- 用 Battle.net API 校验**硬编码 ID**（物品/法术/成就/坐骑/宠物是否仍存在、名称与图标是否变化）。本仓库的装备规划器有大量此类数据，可作为离线数据表校验来源。注意 ToU 限制数据再分发。
- 用 [Gethe/wow-ui-source](https://github.com/Gethe/wow-ui-source) 做**按构建号的界面源码 diff**。

**后者顺带给出了 5.1 版本漂移的具体修法**。【本机实测·读仓库分支】该镜像当前分支与构建号的对应关系：

| 分支 | 版本 | 构建号 |
| --- | --- | --- |
| `live` | 12.1.0 | **69814**（与本机客户端一致） |
| `ptr2` | 12.1.5 | 69848 |
| `ptr` | 12.1.0 | 69587（= 仓库当前锁定值） |
| `beta` | 12.0.1 | 66220（已停更） |

即：**仓库需要把 `wow-ui-source` / `wow-resources` 的固定提交从 `live` 的旧提交换成 69814 对应提交。** 目标分支明确，不需要重新调研。

**一处必须避免的误认**：该仓库里有个名为 `automation` 的分支，那是 **Gethe 自己的镜像导出流水线**（用 TACTSharp 从 CDN 导出），**与暴雪无关**，不是官方提供的自动化能力。

**如果将来要支持 PTR**：PTR 的接口号与正式服**不同**（12.1.5 → `120105`），`.toc` 可用逗号分隔写多版本（`## Interface: 120100, 120105`）。本仓库当前清单只写了 120100。

**发布相关的官方约束**（若将来公开发布）：插件政策现行可引用的文本是[官方论坛置顶帖](https://us.forums.blizzard.com/en/wow/t/ui-add-on-development-policy/24534)（旧的 legal 页面 URL 已 301 到通用索引）。八条里两条与工程直接相关：**必须免费**、**代码必须完全可见且不得混淆**。官方联系邮箱 `WoWUI@blizzard.com`。

## 三、准星 HUD：哪些人工项能被收走

### 3.1 现状：已经自动化的部分

[仓库测试说明](../tests/README.md)与 `.build-and-verify/config.json` 登记的内容已覆盖：LuaLS 类型检查、Luacheck 静态检查、`.toc` 清单校验、准星 HUD 的 5 组离线逻辑测试（Python 驱动本机 Lua 5.1）、素材一致性、文档锚点，外加两道元闸门（`test_inventory.py` 拦截未登记的测试，`test_checks.py` 是检查器自身的回归）。

这套配置**已经高于社区主流**。【读源码】WeakAuras2、DBM、BigWigs 的 CI 只有 lint 加打包，Details、Plater 连 lint 都没有；主流插件里唯一真正跑测试的是 WeakAuras2 自研的 sandbox 套件（`lua5.1 tests/run.lua`），而它服务的是**安全回归**，不是功能回归，且作者明写「跑绿不是安全证明」。

### 3.2 仍然全人工的部分

准星 HUD 的 16 条实机验收清单走了 **5 轮**（9/16–9/17）才收口，五个失败项全部靠人眼发现：

| 失败 | 性质 | 离线工具能否覆盖 |
| --- | --- | --- |
| ① 两条弧默认是空的（`UnitHealth`/`UnitPower` 在受限上下文是秘密值） | 受限值 | **不能** |
| ② 符能弧填充方向反了 | 几何/外观 | 仅能验角度数值，**验不了"看起来对不对"** |
| ③ 假数据驱动的方向与真实行为相反 | 测试夹具缺陷 | 能（属纯逻辑） |
| ④ 电源按钮禁用后侧边栏行消失 | 第三方集成 | **不能**（需真实 EllesmereUI） |
| ⑤ 职业配色无效（秘密令牌不能当表键） | 受限值 | **不能** |

**这张表本身就是结论**：五个失败项里三个是受限值/第三方集成，离线工具原理上够不着。

### 3.3 模拟器能补的那一层

[Osso/wow-ui-sim](https://github.com/Osso/wow-ui-sim) 是唯一能补上「控件真的落在哪」这一层的候选。【读源码】它有真实用例 `tests/frame_positions.rs`，对 PlayerFrame、Minimap 等真实控件断言 x/y/宽/高误差 ≤1 像素、alpha ≤0.02；Lua 侧也提供 `GetPoint(1)`、`IsInDefaultPosition()` 断言。测试框架是作者自研的（`test()`/`async_test()` + 15 个断言，**不是 busted**），虚拟机是自研的 rilua（纯 Rust Lua 5.1 + 污染追踪）。

**当前没有任何工具能替代这一层。**

但四条限制必须先接受：

1. **没有 12.1 的发布产物**。【读源码】源码默认构建已是 12.1/120100（`Cargo.toml` 默认特性 `client-retail → retail-12-1-0`），但已发布的镜像/标签停在 **12.0.x 线**（两轮调查分别读到 `12.0.5` 与 `12.0.7`，**二者不一致，本报告不做取舍**；共同点是**不存在任何 12.1 标签**）。要用目标版本**必须自建并推送镜像**；`@master` 走不通，action 解析非版本 ref 会直接报错。
2. **没有像素比对**。【读源码】全仓无 golden image、无截图 diff；截图是有损 WebP，且**镜像里根本不支持 `screenshot`**（issue 未关）。所以失败项 ② 那类外观问题它一样验不了。
3. **秘密值是宽松桩**。【读源码】`scrub` 直通、受保护控件的 `SetAttribute` 不校验 `issecure()`。在模拟器里跑绿**不能证明**受限上下文正确——正好是失败项 ①⑤ 的情形。
4. **不加载 SavedVariables**。镜像设了 `WOW_SIM_NO_SAVED_VARS=1`，配置持久化验收（清单第 10 条）验不了。

**采用度必须如实说明**：真正 `uses:` 该 action 的**只有作者自己的示例仓库**，未找到任何第三方成熟插件在 CI 里调用它。它自己的 CI 里真机测试步骤是 `if: false` 禁用的。

**最大不确定项**：准星 HUD 的 `.toc` 硬依赖 `EllesmereUI, MYUI`。**这两个插件能否在模拟器里加载成功，本次未验证。** 在验证这一条之前，模拟器不应写成既定方案。

### 3.4 一条对准受限值的官方手段

【读源码】12.0 起客户端提供 6 个 `addon*RestrictionsForced` CVar，可**手动强制进入受限上下文**（重启不保存），配套 `C_Secrets` / `C_RestrictedActions`。

这是目前最接近官方测试手段的东西，且**正好对着失败项 ①⑤**——那两项的根因都是「只能在副本/PvP 里偶然撞上受限上下文」。用它可以把"偶遇"变成"随时复现"。

**代价**：仍需人工进游戏执行。它减少的是**撞见 bug 的等待时间**，不是把验收变成自动。

### 3.5 性能那条可以自动化

验收清单第 13 条（性能）现在只有体感观察。有一个可借鉴的做法：用最小 stub 在离线环境加载真实插件代码、**统计控件 API 调用次数**，对照预算文件（`callsPerFrame` / `callsPerSecond` / `idleCallsPerSecond` / 打包体积），超预算即失败。参考实现：[peavers-code/peavers-warcraft-workflows](https://github.com/peavers-code/peavers-warcraft-workflows)（★1，作者自述 `Deliberately NOT a WoW emulator`，只统计调用次数）。

**边界**：它能抓「不小心加了个 OnUpdate 每帧轮询」这类回归，**不能**证明真实渲染开销。作为体感观察的补充，不作为替代。

## 四、Sim2GSE：执行序列校验

### 4.1 推荐：三层分工，不单押一条

| 层 | 角色 | 理由 |
| --- | --- | --- |
| **战斗日志** | 主证据 | 精度最高、客观、不依赖插件自身正确性 |
| **探针插件** | 解释层 | 回答日志答不了的三件事（见 4.4） |
| **SimC `action_sequence`** | 期望基准 | 直接给出模拟器认为应该执行的序列 |

推荐理由不是"日志最好"，而是**增量最小**：`projects/sim2gse/combat_log.py` 已完成约八成，缺的只是「顺序对齐 + 间隔容差」这段**纯离线算法**——不需要重新采集任何数据。

### 4.2 战斗日志路线：两条必须先纠正的认知

**精度真相**。【本机实测】日志时间戳写 4 位小数，但真实栅格是 **10 毫秒**（对 86,157 行、3 份日志实测，第 4 位恒为 8）。常见的「0.1 毫秒精度」说法**高估了 100 倍**。做 GCD 级间隔判定时按 10ms 栅格设计容差。

**`COMBAT_LOG_EVENT_UNFILTERED` 已被移除**。【读源码】它在 12.0.0 被移除，**不是"受限"而是不存在**；`C_CombatLogSecure` 为 SecureOnly。本机 12.1 的官方文档镜像确认。

**日志的覆盖盲区**。【本机实测·交叉验证】把探针记录与同场次日志对齐：探针的 54 次成功施法 = 日志的 54 次，**完全一致**；但日志只覆盖 **43% 的点击**（527/1225）；探针看到的失败是日志的 **2.2 倍**（1045 vs 473）；**宏型步骤 73/75 在日志中无配对**。

**这条交叉验证同时说明了两件事**：日志对"真的放出去了什么"是准的；对"想放什么但没放出去"是瞎的。这正是需要探针补位的地方。

**解析工具链现状**。【读源码】没有**任何一个**库同时满足「活跃 + 支持日志 v22 + 可自定义查询」。`wcl-ts` 不存在（题面常见误传），实际可用的是 `@wowarenalogs/parser` 与 `@gladlog/parser`。

**WoWAnalyzer 不能对本地日志跑**。【读源码】它只接受 WCL 的 16 位报告码，全仓 0 处 `COMBAT_LOG_VERSION`；其 APL Checker 只覆盖约 10 个专精。**不要把本地日志分析寄望于它。**

### 4.3 SimC 侧：期望序列已经拿得到

【读源码】开关是 `collect_action_sequence`（布尔，**默认 `true`**）；**不存在 `action_sequence=` 这个命令行选项**——那只是 JSON 的字段名。产物路径 `players[].collected_data.action_sequence[]`，字段含 `time` / `id` / `name` / `spell_name` / `target` / `queue_failed` / `item_name` / `wait`；加 `full_states=1` 时另有 `cooldowns[]` 与目标 debuff。

两条限制：**只采集第一个迭代**（官方因此称它 Sample Sequence——一份代表性样本，不是全部迭代），且**只记真正执行的动作**（未执行的以 `queue_failed` 标记）。

**要"这个动作是哪个 APL 列表选的"，有两条路**：

- **HTML 报告的 Sample Sequence 表**：列为 `Time | # | Name [List] | Target | Resources | Buffs`，其中 `Name [List]` **就是动作所属的 APL 列表名**。官方发布的报告里该表内容完整。
- **`log=1` 文本轨迹**：带 `{:.3f}` 秒时间戳前缀，含 `"X performs Y"` 与 `"X runs action list Y"` 两类行。

**一处需要复现的冲突**：本机两个 SimC 构建产出的 HTML 里，Sample Sequence 表是 **0 字节**，原因未查明。由于官方发布的报告该表正常，**这更像本机构建或参数的局部问题，而不是该路线不可用**——投入使用前应先用官方 Docker 镜像复现一次。

**取值范围可以收窄**：34 份官方默认 APL 里，独立 `sequence` 出现 **0 次**，`strict_sequence` 仅 **1 次**（奶德）。这两条 Sim2GSE 可以放到低优先级。

**"不保证最优"的权威表述在源码里**（`engine/player/player.cpp:1228-1234`）：*"It may not result in the absolutely highest possible dps."* 同一段文本也出现在官方默认 APL 文件与 HTML 报告的 Profile 段。**描述期望序列时应沿用这个口径**——它是样本，不是标准答案。

**分发与许可**：官方 Docker 镜像 `simulationcraftorg/simc`（组织名是 `simulationcraftorg`，**不是** `simulationcraft/simc`），tag 形如 `1210-2026-09-16-66096c1`，每日更新，**仅 linux/amd64**。GitHub Releases 为空（最后一个 tag 停在 2020 年），官方改走 `downloads.simulationcraft.org/nightly/`。**官方 JSON schema 不存在**（源码里引用的 `{version}.schema.json` 实测 404），不能拿它做校验。

**许可提示**：SimC 是 **GPL-3.0**。以独立进程调用通常无碍，但**不要把 SimC 源码链接进 Sim2GSE**（此处未做法律分析，需要时请自行确认）。

**SimC 完全不能解析魔兽战斗日志**（全仓仅 1 处命中，且是指向暴雪界面源码的注释 URL）——对照逻辑必须自己实现，本项目已有 `combat_log.py` 在做这件事。

### 4.4 探针插件：能答什么、不能答什么

**不能当主证据**：失败没有原因记录，且受 2.3 的落盘约束。**但它能回答日志答不了的三件事**：点击覆盖 100%、`submittedStep` 说明"序列想放什么"、宏步骤可见。

**GSE 自带调试器的定位**：有 Sequence Debugger，但**导出时间戳只有整秒精度**（`GetServerTime()`），做不了 GCD 级间隔判定；`/gse` 的 CSV 导出需要人工 Ctrl+C。**只适合人工抽查，不能自动化。**

**GSE 的官方扩展点只有两条**。【读源码】`GSE/API/Statics.lua` 只稳定暴露 `GSE_SEQUENCE_ICON_UPDATE` 与 `GSE_MODS_VISIBLE`，**没有**"导出执行记录"类接口；社区也没有现成的执行记录导出插件。其中 `GSE_MODS_VISIBLE` 的载荷已含 `ClickSerial` / `SequenceName` / `Mods` / `SpamKey`。

**一处文档与源码的实质冲突**：Wiki 说该消息"每次点击都触发"，源码门禁实为 `if mods and isFreshSequenceClick`。**采信源码。**

### 4.5 仓库自身的不一致（建议优先处理）

本次核实发现探针插件有**两个版本并存**：

| | 仓库 `addons/Sim2GSEProbe/` | 游戏安装目录 |
| --- | --- | --- |
| 声明版本 | **0.1.0** | **0.1.4** |
| 挂点方式 | `hooksecurefunc` + `HookScript` 挂 GSE 内部按钮 | `RegisterMessage` / `OnMessage` + `GSE_MODS_VISIBLE` |
| 行数 | 361 | 353 |

【本机实测】两文件内容不同；仓库工作树干净，即**v0.1.0 的旧设计是被提交的版本，而走 GSE 官方消息总线的 0.1.4 只存在于游戏目录，从未提交**。

**风险**：该版本没有备份，重装或清理插件目录即丢失。

**取舍提示**：消息总线版走的是官方扩展点，比 hook 内部实现更稳；但它继承了 4.4 那条门禁限制——`GSE_MODS_VISIBLE` 并非文档所称的"每次点击都触发"。迁移前需确认该门禁对采集完整性的实际影响。

**未解决疑点**：GSE 的 `iteration` 是**版本块索引**而非循环计数，且发现 `step + iteration*254` 与"每块 253 条"相差 1。**本次未解决**，是后续最该优先澄清的一点。

## 五、跨项目事项

### 5.1 客户端版本已漂移

【本机实测】

| | 仓库锁定 | 实际安装 |
| --- | --- | --- |
| 版本 | 12.1.0.**69587**（`scripts/dev/versions.json`） | 12.1.0.**69814** |
| 分支 | — | `cn`（网易 CDN） |
| 接口号 | 120100 | 120100（未变） |
| `_retail_` 改动时间 | — | 2026-09-13 |

`docs/environment-setup.md` 写着「本机游戏可执行文件和安装版本记录均为正式服 12.1.0.69587」，`myspec/changes/sim2gse-wayfinder/issues/01` 也记过「Wow.exe 文件版本为 12.1.0.69587，与仓库锁定值相同」。**该结论今天已不成立。**

影响：接口号未变所以没有立刻出错，但**准星 HUD 的 5 轮实机验收（9/16–9/17）实际跑在 69814 上，而仓库固定的接口文档与注解是 69587 那一版**。按[协作指南](wow-addon-development-guide.md)的版本纪律，`versions.json`、受影响的固定提交与 `docs/environment-setup.md` 需要一次对齐。

反向参考：两个上游项目的记录都指向 69814——wowless 的 `data/products/wow/build.yaml` 记正式服为 **12.1.0 / 69814 / 120100**；SimC 源码的 `CLIENT_DATA_WOW_VERSION` 同样是 **12.1.0.69814**（其版本号写作 4 位的 `1210-01`，不使用接口号 120100）。

### 5.2 工具成熟度总表

| 工具 | 定位 | 成熟度 | 对本仓库的判断 |
| --- | --- | --- | --- |
| [Osso/wow-ui-sim](https://github.com/Osso/wow-ui-sim) | 游戏外加载/渲染 + 控件几何断言 | ★33，GPL-3.0，巴士系数 1；发布产物停在 12.0.x | **唯一能验几何的候选**，须先验 EllesmereUI 能否加载 |
| [wowless](https://github.com/wowless/wowless) | headless 解释器（语义正确性） | ★69，MIT，活跃（支持 69814）；**作者自称 pre-alpha**；0 release / 0 tag / 无 Docker / 无 action；133 open issues；巴士系数 1 | 不接门禁：**进程出错也返回 0**，须自写解析器；且作者明说"它报的错几乎肯定在它自己" |
| [Jaliborc/WoWUnit](https://github.com/Jaliborc/WoWUnit) | 游戏内单元测试 | **无开源许可**（清单写 All Rights Reserved），TOC 停在 120001 | **不可用**（更正见 6.1） |
| [Falkicon/Mechanic](https://github.com/Falkicon/Mechanic) | 诊断平台 + MCP + 代码队列 | ★19、2 位贡献者、alpha、9/6 后无提交 | 只建议静态门禁 + 人工确认下的探针；**不要开 `--auto-reload`** |
| [Nighthawk42/wow_api_mcp](https://github.com/Nighthawk42/wow_api_mcp) | 接口检索 MCP | 数据已更新为 **12.1.0.69587 / 120100** | 只读检索可用；版本与仓库锁定值一致 |
| `wow-addon-api-mcp` | 接口检索 MCP | 新建（2026-08-13），Apache-2.0，★0 | 唯一提供**受限值元数据**的服务，值得单独评估 |
| [RdyGaming/hated-wow-mcp](https://github.com/RdyGaming/hated-wow-mcp) | 素材/源码检索 | 默认接口号仍为 120007 | 仅需要素材/图集时补充 |
| [juemrami/wow-dev-mcp](https://github.com/juemrami/wow-dev-mcp) | 接口名/简中字符串 | 停滞 12 个月 | 不采纳 |
| [BigWigsMods/packager](https://github.com/BigWigsMods/packager) | 打包发布 | v2.5.1，事实标准 | 需要公开发布时再接入 |

### 5.3 合规红线

- ❌ **不要**使用会注入游戏输入的外部程序（含 `SendKeys` 式自动重载、AHK、pyautogui 类）。EULA bots 条款无意图豁免，CN 版更严。
- ❌ **不要**使用内存读取、DLL 注入、封包修改类工具。
- ⚠️ Mechanic 的本地服务**无认证、无 OS 沙箱**，其 `SECURITY.md` 自述「MCP 客户端同样获得命令执行权，只读/可变标注**不是访问控制**」。接入等于交出本机任意代码执行权，须单独评估。
- ✅ 合规：写文件进 `AddOns/`、读 `WTF/**/SavedVariables/*.lua`、离线 headless 模拟、静态检查、游戏内单元测试、**人工按一次 `/reload`**。

## 六、对前期文档的三处更正

1. **WoWUnit 已不可用**。[调试与测试研究](wow-addon-debug-testing.md)把它列为「游戏内的另一个选项」。实际：**无开源许可证**（`.toc` 写 All Rights Reserved），清单停在 `120001`（**不支持 12.1**），最后提交 2026-02-08。
2. **「截图/像素回归」在魔兽生态是空白**。多种检索词全零结果（只能说"公开搜不到"）。本仓库 gear-planner 的 Playwright 检查做的是**功能断言 + 截图留档**（`page.screenshot()` 之后没有比对），这个分寸同样适用于插件侧——不要指望视觉回归。
3. **`wow_api_mcp` 的版本保留意见可撤销**：其数据已更新为 12.1.0.69587 / 120100，提交 `8ea15b61` 与仓库 `.tools/wow-ui-source` 锁定值一致。

另需记录一条边界：**ElvUI 仓库的 `AGENTS.md` 明令禁止 AI 工具访问或分析其内容**。后续如涉及 ElvUI 源码，应遵守该约束。

## 七、建议的落地顺序

按「先验证前提、再投入」排序，每步都能独立止损：

1. **游戏内跑一次 2.5 的实验**（一行命令，零风险）。它决定"沙箱内自动重载"这条路是否需要永久划掉。
2. **先验模拟器的加载前提**：EllesmereUI 与 MYUI 能否在 wow-ui-sim 里加载。**不通过就停止这条线**，不要先自建 12.1 镜像。
3. **收编已有的确定性收益**（不依赖任何新工具）：
   - 提交探针 0.1.4，或明确决定保留 0.1.0（见 4.5）
   - 给 `combat_log.py` 加「顺序对齐 + 间隔容差」，按 10ms 栅格设计（见 4.2）
   - 对齐 `versions.json` 与客户端实际版本（见 5.1）
4. **模拟器最小试点**（仅在第 2 步通过后）：只验 `Elements` 的坐标与配置联动，产出 2–3 个几何断言。**验收标准是"故意改错后测试会失败"**，否则不算接入。
5. **按需补充**：性能预算检查（见 3.5）、受限上下文 CVar 复现流程（见 3.4）、接口检索 MCP（见 5.2）。

**明确不做**：合成输入自动重载；像素比对；把任何离线结果当作实机验收。

## 八、原始证据

本轮调研的完整原始记录（含逐条来源链接、证据分级、未核实项）已落盘，未提交，位于 `.local/research/`：

| 文件 | 内容 |
| --- | --- |
| `ui-testing.md` | 界面测试工具链：wow-ui-sim 源码级能力核查、Wowless、成熟插件实况 |
| `mcp-ci-tooling.md` | MCP 服务与 CI 闭环现状 |
| `gse-debugging.md` | GSE 调试能力与扩展点、战斗日志路线、探针挂点 |
| `combat-log-route.md` | 战斗日志精度、CLEU 移除、解析工具链 |
| `simc-route.md` | SimC `action_sequence` schema 与限制 |

官方外部通道与 PTR 政策那一条线的原始记录**未单独落盘**，已并入本文 2.7 节（含来源链接）。

`.local/` 属运行证据目录，按仓库约定不进入提交。需要长期保留的部分应另行归档。

## 研究边界

- **未安装、未运行任何候选工具**。wow-ui-sim 的 Docker 镜像实际可用性、Mechanic 的端到端流程、wowless 的误报率，**均无本机实测**。SimC 侧本机已有可用 `simc.exe`（1210-01），但本轮新下载的二进制未获授权执行，因此 **JSON 字段表为源码推导**；HTML Sample Sequence 有官方发布物的真实样例可对照，但**本机构建产出 0 字节这一现象未复现**。
- **未做游戏内验证**。2.5 的实验、`addon*RestrictionsForced` CVar 的实际效果、探针两版的采集差异，都还只是待验证项。
- **未核实 EllesmereUI / MYUI 能否在模拟器中加载**——这是第 7 节第 2 步的全部内容，也是本报告最大的不确定项。
- 三处**两轮调查结论不一致**且本报告未做取舍：wow-ui-sim 已发布镜像的确切版本（12.0.5 / 12.0.7）；wowless 是否含布局引擎（wow-ui-sim 文档称其"no layout engine"，但 wowless 有 `render.lua` 与 `frames2rects`）；**本机能否访问 `wago.tools`**（一次记录为连接立即失败、疑 DNS 或地域阻断，另一次成功读到 `/api/builds`）。**采信任一方前需自行复核。**
- `wow.tools` 已于 2025 年 5 月退役（站点原文自述），现由 `wago.tools` 承接；暴雪的 `Blizzard/api-wow-docs` 仓库最后推送停在 2019 年，是废弃指路牌。社区常提的 `discord.gg/wowui` 与 `wowui.gg` **实测均无效**。
- **`GSE_MODS_VISIBLE` 的门禁差异对采集完整性的实际影响未实测**，这直接影响 4.5 的版本取舍。
- GitHub 代码搜索多次撞速率限制，「第三方采用」类结论（尤其 wow-ui-sim 与 Mechanic 的采用度）**检索不完整**，只能作为已知样本，不能推断采用率。
- 政策部分以 2026-09-17 抓取的官方页面原文为准；EULA 与蓝贴会更新，**执行前须复核当次版本**。
