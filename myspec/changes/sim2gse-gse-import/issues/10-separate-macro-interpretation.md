# 10：把已有宏解释从 GSE 控制层剥离

Label（标签）: change:task
Triage（分拣）: ready-for-agent
Status（状态）: done

## What to build

导入序列仍在相同场景下产生相同的按键动作或拒绝原因；GSE 控制层只交付逐次按键与宏原文，已有宏条件和命令解释由单独模块承担，便于日后独立扩充。

## Blocked by

09：先固定完整导入语法与公开检查结果，再做行为保持的剥离。

## Acceptance criteria

- [x] 已有宏条件、命令、预检及角色动作映射移出 GSE 导入/控制模块；模块交接只包含宏原文、来源位置、场景和角色动作目录，不让 GSE 控制代码理解宏条件。
- [x] 不新增宏语法或游戏状态模拟；既有可模拟输入的逐次动作、来源路径与 DPS 保持一致，不支持输入仍按原位置和原因拒绝。
- [x] 真实第三方原串验证代表性成功、宏拒绝及 If/Embed 的无损解析；可达的外部 If 变量拒绝与缺失 Embed 引用拒绝可使用明确标注的构造 GSE 导入串，经同一公开 inspect/tasks 接口验证；完成统一验证与独立审查。

## Highest public seam and failure path

`POST /api/gse/inspect` 与导入模式 `POST /api/tasks`；宏不能忠实解释时在模拟前保留原文位置拒绝，GSE 语法检查不因宏语义失败而报解析失败。

## Comments

2026-09-25 范围修订：这是最小架构整理，不实施完整 WoW 宏解释器。

2026-09-25 验收补证（HEAD `380bad23c3e07c165c46ff62ddb1517a4ff2498b`；本地 HTTP 接口模拟，未做游戏内实测）：

- 复跑命令（仓库根目录 PowerShell）：
  `& .venv/Scripts/python.exe .local/sim2gse/ticket10-public-api-380bad2/capture_public_api.py after`
  `& .venv/Scripts/python.exe .local/sim2gse/ticket10-public-api-380bad2/capture_public_api.py before`
  脚本向检查接口 `POST /api/gse/inspect` 和任务接口 `POST /api/tasks` 发请求；HTTP（网页协议）、GSE（宏序列格式）、DPS（每秒伤害）、GCD（公共冷却）、If（条件分支）、Embed（嵌入序列引用）。完整响应摘要、输入 SHA-256（摘要）、任务结果保存在 `.local/sim2gse/ticket10-public-api-380bad2/`。
- 真实 Karen ST（`.local/sim2gse/gse-corpus-additional/karens-unholy-01.txt`，SHA-256 `1550b78b2e625309e018fd8901443ec9fc28c7bfc8f7f47bb932e53605c96497`）和 Kim Burst（`.local/sim2gse/gse-corpus-additional/kims-unholy-02.txt`，SHA-256 `5a5430d305b7821ba682e74cd3c07d673aa80d3f988f044cfe05f821d60b7824`）：检查接口均 HTTP（网页协议）200 / `decoded`（已解码）；`unholydk_ST`、`Burst_Cooldowns_UDK` 的 v1 预检通过，状态为 `requires_character_validation`（待角色核验）。这是静态预检通过，仍待角色法术/物品映射核验，没有据此声称取得 DPS（每秒伤害）。
- 真实 Sol（`.local/sim2gse/gse-corpus/sol-unholy-12-1-01.txt`）：检查接口 HTTP 200 / `decoded`，序列 `SOL_UDK_AOE` 在 `Sequences[SOL_UDK_AOE].Versions[1].Actions[1].macro[行 2]` 因 `/petattack` 不可忠实模拟而拒绝；任务接口 POST HTTP 400，未创建任务。
- 真实 Violent Benediction（`.local/sim2gse/gse-corpus/violent-benediction-if-01.txt`）：检查接口 HTTP 200 / `decoded`；实际首要拒绝是集合 `Variables[VB_IsDamage]`、`Variables[VB_IsHeals]` 不符合上游导入格式，任务接口 POST HTTP 400，原因相同。其原始 If 节点引用 `=GSE.V.VB_IsHeals()`、`=GSE.V.VB_IsDamage()`；去掉集合 Variables 后的派生合成投影仍在 `Sequences[Violent Benediction].Versions[1].Actions[1]` 因 If 需要游戏内变量而拒绝（检查接口 HTTP 200 / `decoded`；任务接口 HTTP 400）。因此不把原串的变量集合阻断误报为纯 If 阻断。
- 真实 Jafoweb（`.local/sim2gse/gse-corpus-additional/jafoweb-embed-01.txt`）：检查接口 HTTP 200 / `decoded`，先在 `Sequences[Disc_Oracle].Versions[1].Actions[1].macro[行 2]` 因 `[nochanneling]` 条件无法确定而拒绝；任务接口 HTTP 400 同因。原串可见后续 Embed 引用 `MPB`，但本次不能越过先发宏阻断证明其可达性或缺失；未找到独立的真实缺失 Embed 样本。
- 缺失 Embed 用例是明确标注的合成向量 `SYNTHETIC_MISSING_EMBED`（非第三方原串）：引用 `ABSENT` 在 `Sequences[SYNTHETIC_MISSING_EMBED].Versions[1].Actions[1]` 拒绝；检查接口 HTTP 200 / `decoded`（已解码），任务接口 HTTP 400。
- 成功导入任务使用合成宏 `/targetenemy [noharm][dead]\n/cast 77575`、序列 `MACRO_MAPPING_EVIDENCE`、同一固定测试角色输入，点击/输入间隔 300 ms、GCD（公共冷却）1500 ms；前后 `POST /api/tasks` 均 HTTP 202 并完成。输入 SHA-256 为 `2f27854080ed6dca7c666b6d1811fe7e1ee3d8d507d361581aa2cae5303183b0`。DPS 均为 `1911.0397445569276`；来源路径均为 `1`，动作均为 `outbreak`，编译动作来源均为 `gse_import / MACRO_MAPPING_EVIDENCE / v1 / path 1`。比较文件记录 DPS、来源路径、动作块与点击来源完全相同。基线只替换为 `a157441` 的 `gse_import.py`，复用本次未改的 HTTP/任务/程序及 Lua 导入器代码和同一测试输入；这不是两份完整检出的端到端版本比较。游戏验证状态为 `not_run`。

2026-09-25 范围澄清：用户允许用明确标注的构造 GSE 导入串验证真实第三方语料中不可达的外部 If 变量拒绝与缺失 Embed 引用拒绝；构造串需经同一公开 inspect/tasks 接口验证，不记作真实第三方原串。

2026-09-25 公共任务接口补证（HEAD `68599a924e3b7bcd6c7fe95160d55d2d91235f14`；本地模拟，游戏验证未运行）：Karen ST 原串经 `POST /api/tasks` HTTP 202 后任务完成，DPS（每秒伤害）为 `13095.923336688085`。Kim Burst 原串也被 HTTP 202 接受，但在 `initialize` 阶段失败、没有 DPS；SimC 日志显示 `prototype supports at most one GCD action per block`，来源是 `Sequences[Burst_Cooldowns_UDK].Versions[1].Actions[1]["5"]`（导入动作路径 `1.5`）中的双施法宏。这是模拟引擎初始化限制，不是 GSE 语法解析失败。请求、来源动作与日志详见 `.local/sim2gse/ticket10-public-api-380bad2/current-68599a9/karen-kim-task-api-summary.md`。

2026-09-25 最终门禁（HEAD `cc74d1278bff91940f45b84442ee0704bcc6a6f6`）：`build-and-verify build --project .` passed；`build-and-verify verify --project . --base fa2ea1360858942a8bc3d065fbad81c5a9cef417` passed，checked 9 项，225 passed / 80 subtests passed。Reviewer 双轴最终复审 blocker 0。

最终公开冒烟命令：`.venv/Scripts/python.exe .local/sim2gse/ticket10-public-api-380bad2/capture_public_api.py after`，exit 0。结果位于 `.local/sim2gse/ticket10-public-api-380bad2/after/`：真实 Sol、Violent Benediction、Jafoweb 的拒绝路径，以及明确标注的构造 If 外部变量和缺失 Embed 用例均经公开 inspect/tasks 接口验证；真实 Jafoweb 先被 `[nochanneling]` 阻断，不能据此声称真实缺失 Embed 已验证。合成成功任务 HTTP 202 / completed，DPS `1911.0397445569276`，动作 `outbreak`、来源路径 `1`；`game_validation=not_run`，未做游戏内验收。
