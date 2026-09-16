# 配置存储方式复议：跟随 EUI 档案需要一个偏门挂点

Label（标签）: wayfinder:grilling
Triage（分拣）: ready-for-human
Status（状态）: closed
Assignee（领取者）: Codex（主代理）
Mode（方式）: HITL（与用户共同决策）
Parent（所属地图）: [Crosshair HUD（准星 HUD，EllesmereUI 扩展插件）实施地图](../spec.md)
Blocked by（前置事项）: 无

## Question（问题）

配置**继续跟随 EUI 配置档案**（存进 `EllesmereUIDB`），还是**改为插件自己的 SavedVariables**？

## 背景与讨论范围

本票由[EUI 集成契约核实](03-eui-integration-contract.md)的结论触发——它把一个已知的取舍变成了可量化的事实。

- [需求追问](01-requirements-grilling.md)第 13 项选了"跟随 EUI 配置档案"，理由是"切档案时 HUD 跟着变，与 EUI 整体一致"。同一轮里，用户在**插件结构**问题上明确排斥偏门用法（因此否决了虚拟文件夹名方案）。
- 调研查明：EUI **不允许**外部插件注册"档案切换后重新应用界面"的回调——相关的两个刷新清单都是文件局部数组，全库也不存在公开注册点。**唯一可靠的做法是包装公开函数 `EllesmereUI.RefreshAllAddons`。**
- 也就是说：**"跟随档案"要真正生效，必须使用一个偏门挂点**；而改为**独立存储**，档案切换时本来就没有东西需要重新应用，**这个挂点可以完全不要**。

需要用户权衡的是：用一个受控的偏门挂点换取"配置与 EUI 整体联动"，还是用独立存储换取零偏门依赖。

补充事实（供决策参考，非决定因素）：

- 独立存储方案下，配置不会跟随档案，也不会被 EUI 的默认值裁剪与迁移逻辑触碰。
- 跟随档案方案下，配置**不会随 EUI 的档案导出串对外分享**（导出只遍历 EUI 自己的映射表），这是无解的限制。
- 挂点是包装一个公开函数，失败模式是**静默不刷新**（不是报错崩溃），且可以全程 `pcall` 隔离。

## 关闭条件

- 用户在两条路线之间明确选择，并说明取舍理由。
- 结论回写进[需求追问](01-requirements-grilling.md)的决策表，并作为[方案计划成文](07-plan-writeup.md)的输入。

## 实施交接

- 选**继续跟随档案**：方案必须记录包装挂点、其静默失效模式、`pcall` 要求，以及"配置不随导出串走"的已知限制。
- 选**改为独立存储**：功能插件 `.toc` 声明自己的 `## SavedVariables`，去掉对 `Lite.NewDB` 的依赖，方案中删除"档案切换重新应用"整节。

原始依据：用户 2026-09-16 关于配置存储的决议，与[EUI 集成契约核实](03-eui-integration-contract.md)的调研结论。

## Comments（讨论）

### 2026-09-16 用户决议：改为独立存储

用户明确答复：*"配置这么复杂的话，那就不用搞跟随档案了，我们用独立的方式来做，配置文件独立就好了。"*

**结论：配置存在功能插件自己的 SavedVariables 里，不跟随 EUI 配置档案，不使用 `Lite.NewDB`。**

#### 这条决定消掉的东西

- **不需要包装 `EllesmereUI.RefreshAllAddons`**——档案切换时我们本来就没有东西需要重新应用，[EUI 集成契约核实](03-eui-integration-contract.md)发现的唯一偏门挂点可以完全不要。
- 不需要 `Lite.NewDB`，也就避开了它清空插件自身 SavedVariables 的行为，以及对那个无文档内部框架的依赖。
- 不存在"缓存 `db.profile` 会静默写进废弃表"这个陷阱——那是 `RepointAllDBs` 的行为，我们不参与。
- 不需要依赖 `EllesmereUIDB` 在加载时已是真表，少一条加载顺序风险。

#### 这条决定带来的东西

- `.toc` 声明自己的 `## SavedVariables: MYUI_CrosshairHUDDB`，数据由我们自己读写。
- 需要自己的默认值合并逻辑（读取时用 `or 默认值` 兜底，或启动时一次性补齐缺键）。不再有 EUI 的 `DeepMergeDefaults` 与 `StripDefaults` 帮我们做这件事。
- **配置不跟随档案切换**——这是用户已知并接受的取舍。
- 配置与 EUI 的档案导出串彻底无关：既不会被导出带走，也不会被导入覆盖。将来若要分享配置，需要我们自己提供序列化（属可选增强，记入地图的"尚待明确"）。

#### 对下游的影响

- [需求追问](01-requirements-grilling.md)第 13 项决策已就地更正为"独立存储"。
- [方案计划成文](07-plan-writeup.md)的配置章节按此改写：删除"档案切换重新应用"整节，改记 SavedVariables 的键结构与默认值补齐方式。
- [EUI 集成契约核实](03-eui-integration-contract.md)中"张力"一段已就地标注为已解决；其余结论（侧边栏挂载、注入时机、`alwaysLoaded`、`buildPage` 契约）**不受影响，继续有效**。
