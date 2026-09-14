# Omnium Folio 符文数据核查

核查日期：2026-09-14。范围限定为本次 Blood DK（鲜血死亡骑士）90级、单目标地下城伤害假人测试中出现的 Rune of Burning Haste（燃烧急速符文）、Rune of Unleashed Fire（释放之火符文）和 Rune of Lingering（持久符文）相关数据；只读核查，没有修改代码或配置。

## 结论

1. 本次 `input.simc` 的 `omnium_talents=136814:1/136821:1/136817:1/136819:1/136822:1` 格式有效。SimC（SimulationCraft，模拟引擎）会按斜杠拆分；数字节点通过 `trait_data_t::find()` 映射为正式服法术，再注册为角色的特殊效果。`:1` 等级字段在当前实现被明确忽略，因此它表示“启用这些节点”，不是独立的等级计算。[解析源码](../../.tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/player/unique_gear.cpp#L3677-L3699)

2. 这五个节点的映射是：`136814 → 1279614` Overload（过载）；`136821 → 1279610` Burning Haste；`136817 → 1287555` Lingering；`136819 → 1279603` Self-Mending（自我修复）；`136822 → 1279599` Unleashed Fire。节点是被动效果输入，不是玩家主动技能。[本地能力记录](action-capabilities.md#装備与被动效果)

3. SimC 中三者的联动不是“燃烧急速符文造成伤害”。Unleashed Fire 的回调在触发时：先触发由 Burning Haste 等节点选择出的属性增益；若触发来源目标是敌人，执行 `1286970` 伤害，否则执行 `1263002` 治疗。若启用了 Lingering，则该核心符文命中后附加 `1287663` 持续伤害（治疗分支为 `1287665`）；Overload 还会直接提高核心符文倍率。[实现源码](../../.tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/player/unique_gear_midnight.cpp#L5738-L5759)[实现源码](../../.tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/player/unique_gear_midnight.cpp#L5791-L5810)[实现源码](../../.tools/gear-planner-dk-reference/simulationcraft-simc-b845947/engine/player/unique_gear_midnight.cpp#L5816-L5836)

4. SimC 自己明确把 Unleashed Fire 标为 `implementation_not_yet_verified`（实现尚未验证）：它假设触发目标就是触发事件的同一目标，并按敌我目标分别走伤害／治疗分支。因此模拟报告里出现该伤害，证明的是“当前引擎模型被启用并执行”，不证明游戏实机机制与模型完全一致。[报告日志](../../.local/sim2gse/ui-tasks/tasks/27338133c76b47c1be51b9dfb410bf31/batches/031716cf48552ec3bfd1cd211b966df0b7b82b01443ceabf5f1d6c9afe336fb3/native.json)

5. 本次实测日志中没有 `1286970` Unleashed Fire 伤害，也没有对应的 `1287774` Burning Haste 增益；这不是统计时剔除过量伤害造成的，因为这里核查的是事件是否存在及其法术 ID（编号）。因此当前证据支持“游戏内该符文链未触发／未被战斗日志记录”，不支持“实测只是伤害被归类到别的技能”。

6. “普通训练假人不触发 Omnium”有玩家现场旁证，但不是官方机制说明：2026-07-08/09 的暴雪论坛报告称 Unleashed Fire 与 Void-Touched Orbs（虚空触须宝珠）在训练假人上不触发，而在世界战斗或决斗中可以触发。[暴雪论坛旁证](https://us.forums.blizzard.com/en/wow/t/omnium-folio/2324698)[暴雪论坛旁证](https://us.forums.blizzard.com/en/wow/t/tier-1-omnium-folio-won%E2%80%99t-proc/2325302)

7. 截至 2026-09-14，查到的官方热修复包括：修复 Unleashed Fire 曾导致拉入未处于战斗中的敌人（2026-09-09），以及修复 Lingering 对治疗者不总是激活（2026-09-10）。没有查到官方宣布“普通训练假人不触发 Omnium”已修复，或明确保证该假人会触发这些效果。[官方 9月9日热修复](https://worldofwarcraft.blizzard.com/en-us/news/24296142)[官方 9月10日热修复](https://worldofwarcraft.blizzard.com/en-us/news/24296142)

## 证据等级与下一步

| 判断 | 等级 | 说明 |
| --- | --- | --- |
| 输入节点被 SimC 解析并启用 | 已确认 | 输入文件、解析源码和报告均一致 |
| SimC 的三符文联动逻辑 | 已确认 | 源码明确写出回调、伤害／治疗分流和 Lingering 附加效果 |
| SimC 的 Unleashed Fire 数值／目标模型等于实机 | 未确认 | 引擎自身输出未验证警告 |
| 本次木桩没有记录该链 | 已确认 | 实测战斗日志没有相关法术事件 |
| 普通木桩存在系统性不触发行为 | 强推断 | 多条玩家报告一致，但不是官方机制文档 |
| 暴雪已修复普通木桩不触发 | 未确认 | 当前官方热修复未找到该声明 |

因此，当前最小、正确的解释是：基准和 GSE 模拟都启用了 `136822`，所以会出现 SimC 假设的 Unleashed Fire／Burning Haste／Lingering 链；游戏内普通地下城伤害假人没有产生对应事件。下一轮若要验证实机机制，应只增加一个对照：同一角色、同一符文，在普通假人之外用一个明确会进入战斗的真实敌对目标测试；不要先改统计口径或模拟引擎。
