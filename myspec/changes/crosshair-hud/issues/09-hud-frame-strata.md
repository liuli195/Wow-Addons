# HUD 的框架层级

Label（标签）: wayfinder:grilling
Triage（分拣）: ready-for-human
Status（状态）: closed
Assignee（领取者）: Codex（主代理）
Mode（方式）: HITL（与用户共同决策）
Parent（所属地图）: [Crosshair HUD（准星 HUD，EllesmereUI 扩展插件）实施地图](../spec.md)
Blocked by（前置事项）: 无

## Question（问题）

准星 HUD 放在哪一层框架层级（FrameStrata）？这一层要不要做成配置项？

## 背景与调研结果

用户在[弧线渲染实机原型](02-arc-fill-prototype.md)关闭后提出：HUD 应当处于**中层**——在所有窗口类界面（配置窗口、菜单）**之下**，但在一些低优先级界面**之上**。

代理按固定版本的源码核实了三件事：

**一、层级从低到高的顺序**（魔兽全屏界面的标准分层）：

```
BACKGROUND < LOW < MEDIUM < HIGH < DIALOG < FULLSCREEN < FULLSCREEN_DIALOG < TOOLTIP
```

**二、各关键界面实际所在的层级**：

| 界面 | 层级 | 证据 |
| --- | --- | --- |
| 暴雪设置窗口 | `DIALOG` | `.tools/wow-ui-source/.../Blizzard_Settings.lua:176` |
| 插件列表、法术弹出、聊天输入框 | `DIALOG` | `AddonList.lua:227`、`SpellFlyout.lua:319`、`ChatFrameUtil.lua:459` |
| 下拉菜单 | `FULLSCREEN_DIALOG` | `UIDropDownMenu.lua:346` |
| 鼠标提示 | `TOOLTIP` | 惯例 |
| **EUI 自家资源条** | **`MEDIUM`（默认，且暴露为配置项）** | `EllesmereUIResourceBars.lua:1344`、`:2081`、`:3028`、`:3190`、`:3349`、`:6497`、`:8075`、`:8354` |
| **EUI 自家单位框体** | **`MEDIUM`**；分离式能量条默认 `HIGH` | `EllesmereUIUnitFrames.lua:5362-5367` |

**三、结论**：`MEDIUM` 恰好落在用户描述的位置——低于所有窗口类界面（`DIALOG` 及以上），高于 `BACKGROUND` / `LOW`；而且**EUI 自己的资源条与单位框体就是 `MEDIUM`**，作为 EUI 的扩展与之同层是最自然的选择。鼠标提示在 `TOOLTIP` 层，永远在我们之上，符合预期。

**需要用户决定的一点**：EUI 把资源条的层级暴露成了配置项（默认 `MEDIUM`）。本插件要不要照做？

- 写死 `MEDIUM`：配置项最少，符合 v1 的最小范围原则。
- 做成配置项（默认 `MEDIUM`）：与 EUI 一致；将来想调整（例如希望 HUD 盖在 EUI 单位框体之上）不必改代码；代价是多一个下拉项。

**同层级内的次序**：同一 `FrameStrata` 内的前后关系由 `SetFrameLevel` 决定，与层级是两个维度。本 HUD 在 `MEDIUM` 内取一个正常层级即可；实施时若与 EUI 的元素同层重叠，再按实测调整。

## 关闭条件

- 用户确认层级取值，以及是否做成配置项。
- 结论写入[方案计划成文](07-plan-writeup.md)的渲染契约章节。

## 实施交接

方案计划的渲染契约章节；正式实现按此设置 `SetFrameStrata`（以及可能的配置项）。

原始依据：用户 2026-09-16 提出的层级要求，与固定版本源码的核实结果。

## Comments（讨论）

### 2026-09-16 用户决议

用户明确答复：**选 (b)**——层级做成配置项，默认 `MEDIUM`。

**结论**：

- 默认 `MEDIUM`；下拉项提供层级选择（至少覆盖 `LOW` / `MEDIUM` / `HIGH` / `DIALOG`，具体选项集在方案里定）。
- 理由：与 EUI 自家资源条的做法一致；层级属于"装上去看一眼才知道对不对"的参数，留开关比写死省事。
- 配置项总数由 19 变为 **20**（`MYUI_CrosshairHUD` 的配置规格表已相应更新——见[方案计划成文](07-plan-writeup.md)的输入）。

**实施提示**：同一层级内部的前后关系由 `SetFrameLevel` 决定，与层级是两个维度；本 HUD 在所选层级内取正常序号即可，只有与 EUI 元素在同层重叠时才需按实测微调。
