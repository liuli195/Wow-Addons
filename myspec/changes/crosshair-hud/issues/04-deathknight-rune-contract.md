# 死亡骑士符文读数契约

Label（标签）: wayfinder:research
Triage（分拣）: ready-for-agent
Status（状态）: closed
Assignee（领取者）: Codex（主代理）
Mode（方式）: AFK（只读接口文档与源码，不写游戏）
Parent（所属地图）: [Crosshair HUD（准星 HUD，EllesmereUI 扩展插件）实施地图](../spec.md)
Blocked by（前置事项）: 无

## Question（问题）

死亡骑士那 6 个符文，各自的**充能比例**在 12.1 客户端里怎么读？需要哪些事件、哪些失效保护？

## 调查或讨论范围

用户已明确**符文充能必须做**（不是就绪／未就绪两态），因此这一票要拿到足以直接实现的读数契约。

按仓库约定的顺序取证：先查 `.tools/wow-ui-source/Interface/AddOns/Blizzard_APIDocumentationGenerated` 及同版本界面源码，再查固定版本的社区接口资料；注解与本机模拟都不能替代游戏验收。

需核实的点：

1. **读数接口**：逐符文的充能起止时间与是否就绪怎么取；返回值的含义与边界（充能时长为零、未开始充能、就绪态怎么表示）。6 个符文的索引范围与顺序。
2. **充能比例的算法**：由起止时间与当前时间算出 0–1 的比例；需要考虑时间来源的一致性。
3. **符文是否有类型**：现代版本是否还存在血／冰／邪的类型区分，还是 6 个符文同类。这一条直接影响"符文格是否用单一颜色"。（代理判断为同类，但必须核实后才写入方案。）
4. **最大数量是否会变**：是否存在改变符文数量的天赋、增益或专精差异；若会变，需要对应的重建布局路径。
5. **事件集**：哪些事件驱动更新（逐符文事件与整体事件），哪些事件需要**下一帧重读**或延迟，是否存在需要节流的低频事件。
6. **失效保护**：12.x 的秘密值（secret value）机制对本组接口的影响——读到不可读值时如何降级，避免报错或显示错误比例。参考 EUI 自家资源条的同位置防御写法。
7. **边界场景**：死亡与复活、切换专精、天赋改动、载具、区域切换、冷却缩减类增益生效或失效时，读数是否仍正确。

### 边界

- 只覆盖死亡骑士；其他职业的映射已由用户划出 v1 范围。
- 只覆盖符文与符能读数；不改动任何游戏状态，不写入、不施法。
- 本票不做实机验证；实机确认合并到[弧线渲染实机原型](02-arc-fill-prototype.md)的那一次进游戏里完成。

## 关闭条件

- 给出确定的读数接口、充能比例算法、事件集与索引约定，均附证据。
- 明确回答"符文是否有类型"与"最大数量是否会变"，若有风险则给出处理方式。
- 给出失效保护写法（秘密值、异常返回、边界场景）。
- 明确列出仍需实机验证的项。

## 实施交接

方案计划的资源读数章节；正式实现的符文读数模块直接从本票结论起步。

原始依据：用户 2026-09-16 关于职业范围与符文充能的决议。

## Comments（讨论）

### 2026-09-16 只读调研结论

证据基座：`.tools/wow-ui-source` @ `8ea15b61e45c0ed4eba01439c90757f86eb78d34`、`.tools/wow-resources` @ `36dd01d`、`.tools/wow-api` @ `d0b5b51`、以及 EUI 的 `EllesmereUIResourceBars.lua`。

#### 一、读数接口

```lua
startTime, duration, isRuneReady = GetRuneCooldown(runeIndex)
```

- `startTime`：该符文冷却**开始**时的 `GetTime()` 值；就绪时为 `0`。单位秒，基准必须是 `GetTime()`，不能用 `GetServerTime()`／`time()`。
- `duration`：该符文冷却**总时长**（秒），**即使已就绪也照样返回真实值**——所以 `duration > 0` 不能当作"正在充能"的判据。它会随急速、Runic Corruption、Runic Command、Rune Mastery 等动态变化。
- `isRuneReady`：是否可用。`0` 在 Lua 里是 truthy，所以判据必须用这个布尔值，不能用 `start`。
- 文档标志位：`MayReturnNothing = true`、`SecretArguments = "AllowedWhenUntainted"`，**没有 `SecretReturns`**（`PlayerScriptDocumentation.lua:805-822`）。
- 另有 `GetRuneCount(runeIndex)` 返回 0/1，是就绪的数值版，**不含时间信息**，做充能动画不能用它。

#### 二、索引是 1..6，但**索引顺序不等于屏幕槽位**（关键）

- 索引范围 1..6：`RuneFrame.xml` 定义 `Rune1..Rune6` 各带 `runeIndex`；EUI 同样硬编码 `for i = 1, 6`。
- Blizzard 的符文框会**动态重排**：`RuneFrame.lua:66` 的 `table.sort` + `CompareRuneButtons`（`:330-366`）按"是否就绪 → 充能剩余时间升序 → runeIndex"排序，就绪的在最左。EUI 独立复刻了同一规则。
- 所以 `runeIndex` 是**稳定标识符**，不是屏幕位置；渲染时必须自己维护 `槽位 → runeIndex` 映射。
- **本票发现的待定项**：我们的 HUD 要不要也做动态重排？已并入[弧线渲染实机原型](02-arc-fill-prototype.md)一并实机对比决定。

#### 三、符文有**三种**状态，不是两种

| 状态 | 判据 | 成因 |
| --- | --- | --- |
| 就绪 | `isRuneReady == true` | — |
| 充能中 | `isRuneReady == false` 且 `start` 有值 | — |
| **Empty（空转）** | **整次调用什么都没返回**（三个值全是 `nil`） | 同时最多只有 **3 个**符文在充能；一次花掉 4 个以上时，多余的符文在"排队等充能位" |

第三态是常规状态而非异常，成因是 `MAX_REGENERATING_RUNES = 3`。**降级时把 Empty 的填充比例取 0（即整格背景色），绝不能显示成"1% 充能"。**（本插件不显示数值，所以 Empty 与"0% 充能"视觉相同，无需额外视觉。）

判定顺序必须是**先 ready → 再判空 → 最后才做除法**，否则会踩三个坑：就绪时 `start == 0` 导致除法爆值、整次返回 `nil` 导致算术报错、`duration == 0` 导致除零。

#### 四、**正式服没有符文类型**——设计稿的单一配色成立

三重独立证据：

1. `GetRuneType` 在接口 flavor 表中为 `0xE`（`wow-api/src/data/flavor.ts:5944`），而位定义 `0x1=mainline`（`src/providers/flavor.ts:9-14`）——`0xE` 明确排除正式服。（`GetRuneCooldown` 是 `0xF` 全版本。）
2. 正式服客户端的全局接口 dump 里没有它（`wow-resources/Resources/GlobalAPI.lua` 只有 `GetRuneCooldown`/`GetRuneCount`）。
3. 固定版本的整个 `Interface/` 下**没有任何一处**读 `RuneBlood`/`RuneFrost`/`RuneUnholy`；它们只作为 PowerType 枚举常量存在（枚举固定 30 槽所以删不掉）。`RUNE_TYPE_UPDATE` 事件虽在，但全代码库无人注册，且没有配套读取 API。

**容易误判的一点**：`RuneFrame.lua:108-112` 的 `ArtTypeBySpec = {Blood, Frost, Unholy}` 按**专精**换贴图——那是纯美术，读的是专精索引，不是符文类型。

**对配色的结论**：6 个符文同质，颜色只能按**状态**编码（就绪／充能中／空转），不能按类型区分。EUI 同理：DK 分支只返回 `{ power = PT.RUNES, max = 6, type = "runes" }`，且注释明确说符文没有专属资源色、回落到职业色。

#### 五、数量**固定 6**，不要从 `UnitPowerMax` 推导

UI 侧恰好 6 个按钮、EUI 五处硬编码 6、模拟器里 `MAX_RUNES = 6` 是 `const`。天赋不会加数量（`rune_mastery` 是回复速度 buff，`Runic Power Mastery` 加的是符能上限）。EUI 刻意不查 `UnitPowerMax`；本实现照做。

#### 六、事件集

- **`RUNE_POWER_UPDATE`**：唯一逐符文事件，消耗与就绪两个方向都触发。`SecretPayloads = true`——**负载可能不可读，一律忽略参数、整表重读**（Blizzard 与 EUI 都是这么做的）。
- **结构性与边界事件**：`PLAYER_SPECIALIZATION_CHANGED`、`ACTIVE_TALENT_GROUP_CHANGED`、`TRAIT_CONFIG_UPDATED`、`PLAYER_TALENT_UPDATE`、`PLAYER_ENTERING_WORLD`、`PLAYER_DEAD`／`PLAYER_ALIVE`、`ZONE_CHANGED_NEW_AREA`、`UNIT_ENTERED_VEHICLE`／`UNIT_EXITED_VEHICLE`。
- **去抖**：天赋类事件会成串触发，用 `C_Timer.After(0.1, ...)` 合并成一次重建（EUI 的写法；注意它的实现里有 `InCombatLockdown()` 直接 return 的缺口，需靠轮询兜底）。
- **延迟**：`PLAYER_ENTERING_WORLD` 后延迟 0.5 秒再重读（登录竞态：`PLAYER_SPECIALIZATION_CHANGED` 只在变化时触发，登录时不触发）。
- **不要注册 `RUNE_TYPE_UPDATE`**：正式服无符文类型，且无读取 API。

#### 七、失效保护：风险不是秘密值，是"整次返回空"

`GetRuneCooldown` **没有 `SecretReturns`**，结构上不返回秘密值（对照组：`ClosestUnitPosition` 有）。EUI 对符文读取确实**不做** `issecretvalue` 检查、只做 nil 守卫，而它对 `UnitPower`／`UnitPowerMax` 每一处都加——这个差别印证了标志位的判断。

本组接口的真实风险是 `MayReturnNothing`。加 `issecretvalue` 是无害的未来保险，代价是每轮 18 次调用。

#### 八、必须做 ~10Hz 轮询，不能纯事件驱动（重点）

符文回复速度受急速、Runic Corruption、Runic Command、Rune Mastery 影响，`duration` 是动态值，而**这些变化不保证触发 `RUNE_POWER_UPDATE`**。Blizzard 自己的符文框只在事件时重读，因此官方实现也会短暂持有过期 `duration`。

EUI 的对策是不信任缓存：把 6 连读放进 20Hz 基频 ticker（隔次执行 → 实际 ~10Hz），每轮重算比例。**本实现沿用这一条**——这是"冷却缩减增益生效时进度仍正确"的唯一安全解，直到实机验证清楚客户端是否会在速率变化时就地改写 `start`。

#### 九、边界场景

| 场景 | 处理 |
| --- | --- |
| 死亡／复活 | `PLAYER_DEAD`／`PLAYER_ALIVE` 各重读一次并重新武装轮询 |
| 切换专精 | `PLAYER_SPECIALIZATION_CHANGED` + `ACTIVE_TALENT_GROUP_CHANGED` 全量重建；注意登录时前者不触发 |
| 天赋改动 | `TRAIT_CONFIG_UPDATED` + `PLAYER_TALENT_UPDATE` 去抖 0.1 秒合并 |
| 载具进出 | 客户端仍在跑，但**不应显示**，需自行 gate（Blizzard 是直接隐藏整个符文框） |
| 区域切换 | `ZONE_CHANGED_NEW_AREA` 重校验 |
| 冷却缩减增益生效／失效 | 靠 ~10Hz 轮询全量重读，不缓存 `start`／`duration` |

#### 十、可直接使用的读数骨架

```lua
local NUM_RUNES = 6   -- 固定值，不要从 UnitPowerMax 推导

-- 复用表，零 GC
local rune = {}
for i = 1, NUM_RUNES do
    rune[i] = { frac = 0, remaining = 0, ready = false, state = "unknown" }
end
local order = {}      -- order[slot] = runeIndex

local function isSecret(v) return issecretvalue and issecretvalue(v) or false end

local function ReadRune(i, out)
    local start, duration, ready = GetRuneCooldown(i)
    if isSecret(start) then start = nil end
    if isSecret(duration) then duration = nil end
    if isSecret(ready) then ready = nil end

    if ready == true then                          -- 就绪：短路，避开 start == 0 的除法
        out.frac, out.remaining, out.ready, out.state = 1, 0, true, "ready"
        return
    end
    if not start or not duration or duration <= 0 then
        out.frac, out.remaining, out.ready, out.state = 0, math.huge, false, "empty"
        return
    end

    local now  = GetTime()
    local frac = (now - start) / duration
    if frac < 0 then frac = 0 elseif frac > 1 then frac = 1 end
    out.frac, out.remaining, out.ready, out.state = frac, start + duration - now, false, "recharging"
end
```

事件注册与显示顺序排序的完整骨架见调研报告原文（本票讨论记录已收录要点）；正式实现沿用该分支结构与 EUI 的去抖／延迟模式。

#### 十一、颜色只能按状态编码

就绪 = 填充色；充能中 = 按比例的角度填充；空转 = 背景色。**没有按符文类型分色的选项**——正式服不存在类型。

### 待实机验证（不写成已确认）

1. `UnitPowerMax("player", Enum.PowerType.Runes)` 的返回值（EUI 刻意不使用它）。
2. 冷却进行中回复速率改变时，客户端是否**就地改写** `start`、就绪时刻是否保持不变——这决定能否缓存并逐帧插值；在验证之前一律按"每轮全量重读"实现。
3. 12.1 当前赛季套装是否含改变符文上限的效果（资料未见，但赛季内容变化快）。

### 本票对下游的交付

- 方案计划的资源读数章节直接采用上述接口、状态机与轮询要求。
- 配色按状态编码的结论写入方案的颜色章节。
- 新增待定项（符文格是否动态重排）已并入[弧线渲染实机原型](02-arc-fill-prototype.md)。
