# EUI 集成契约核实：侧边栏挂载与配置档案切换

Label（标签）: wayfinder:research
Triage（分拣）: ready-for-agent
Status（状态）: closed
Assignee（领取者）: Codex（主代理）
Mode（方式）: AFK（只读源码核实，不写游戏）
Parent（所属地图）: [Crosshair HUD（准星 HUD，EllesmereUI 扩展插件）实施地图](../spec.md)
Blocked by（前置事项）: 无

## Question（问题）

一个**非 `Ellesmere*` 前缀的真插件**，怎样确定性地把自己的页面挂进 EllesmereUI 的配置界面并打开它？用户切换 EUI 配置档案后，怎样触发 HUD 重新应用？配置存进 EUI 档案后的读写契约是什么？

## 调查或讨论范围

按固定版本的 EUI 源码（`D:\Program Files\World of Warcraft\_retail_\Interface\AddOns\EllesmereUI\` 与 `EllesmereUIOptions\`）核实以下各点，逐条给出结论与证据行号：

### 一、侧边栏挂载

1. 三张注入表（模块描述表、行元数据表、分组表）对**外部分文件夹名**是否有隐藏假设：白名单、命名约定、LoD（按需加载）解析、`FOLDER_HOST` 之类的映射、同步图标、CPU 统计遍历。
2. 侧边栏行的"可用状态"判定与电源按钮创建条件——确认 `alwaysLoaded` 的语义，以及不设它时对一个**真插件**的行为。
3. 注入的**最晚时机**：确认"必须早于用户首次打开 EUI 面板"这一约束是否准确，以及面板已打开后注入会怎样失败。
4. 打开指定页面的入口函数与其副作用（是否会自动加载选项插件、是否会切分组）。
5. **风险清单**：列出会被 EUI 版本更新破坏的点，并给出每点的失效表现（静默失败还是报错）。

### 二、配置档案切换后的重新应用

6. EUI 自家的兄弟插件（动作条、资源条等）在切换配置档案后靠什么机制把新配置应用到界面上？找出那个注册点或事件。
7. 该机制对外部插件是否可用；若不可用，列出可行的替代（监听事件、包装内部函数、在页面 `setValue` 里自行应用等）及各自代价。
8. 确认 `db.profile` 指针重指向后，外部插件持有的旧引用是否会失效（是否需要每次读取都走 `db.profile` 而不是缓存表）。

### 三、配置读写契约

9. 配置存进 `EllesmereUIDB` 后的默认值机制：默认值裁剪会删掉哪些键、读取时缺失键应如何解释。
10. 配置写入是否会被 EUI 的迁移逻辑改写；外部模块的配置键有没有保留命名空间。
11. 从零创建模块配置时的推荐姿势（以 EUI 自家模块的写法为准），以及外部插件按此写法是否会被任何门禁拦下。

### 边界

- 本票**只读源码**，不做实机验证。实机确认合并到[弧线渲染实机原型](02-arc-fill-prototype.md)的那一次进游戏里完成。
- 不修改 EUI 自身文件；所有结论以"外部插件可用的调用方式"表述。
- 若某项只能靠实机确认，明确标注为待实机验证，不写成已确认。

## 关闭条件

- 逐条给出上述各点的结论与源码证据。
- 产出一段**可直接使用的侧边栏挂载代码骨架**（含调用时机与空值守卫），以及配置档案切换后的重新应用方案。
- 产出风险清单：每项标注失效表现与缓解手段。
- 明确列出仍需实机验证的项，供原型票一并在游戏中确认。

## 实施交接

方案计划的集成章节；正式实现的挂载与配置模块直接从本票结论起步。

原始依据：用户 2026-09-16 关于配置页位置、插件结构与配置存储的决议。

## Comments（讨论）

### 2026-09-16 只读调研结论

调研版本：EllesmereUI / EllesmereUIOptions **9.1.8**。

#### 一、侧边栏挂载：可行，且对文件夹名**没有前缀要求**

- **没有 `Ellesmere*` 前缀白名单。** `RegisterModule` 的白名单校验的是**调用者文件路径**（`debugstack` → `AddOns/([^/]+)/`，`EllesmereUI.lua:9863-9889`），不是 `folderName`。所以 `MYUI_CrosshairHUD` 这个文件夹名本身没有任何障碍。
- `IsModuleAddonLoaded` 的 `FOLDER_HOST` 解析只对 `ADDON_DB_MAP` 内的文件夹生效（`EllesmereUI_Profiles.lua:669-671`、`:108-115`），外部文件夹回落到直查，安全。
- 全局搜索会遍历 `_modules` 并**离屏真实调用你的 `buildPage`**（`EllesmereUI_GlobalSearch.lua:126-146`、`:617-636`），期间把 `EllesmereUI.Widgets` 换成桩并用 `pcall` 吞错。`buildPage` 因此必须幂等、必须容忍控件工厂为空、**构建期不得注册长生命周期监听**。
- 侧边栏行点击的硬门槛是 `self._loaded and modules[self._folder]`（`:7915-7923`）——**只挂行不注册模块 = 点了没反应，且静默**。两者必须成对写入。

#### 二、`alwaysLoaded`：**不要设**（与用户决议一致）

`alwaysLoaded = true` 是"硬覆盖已安装/已加载判定"，不是"预加载"，并且会**跳过电源按钮创建**（`EllesmereUI.lua:7693`、`:10554`、`:10560`）。

对一个**真实存在且已加载**的插件文件夹，不设它是完全正常的：行可点、颜色正常、电源按钮出现并可真正禁用/启用该插件。这正是用户要的"每个功能边上的小开关"。**推荐配置：不设 `alwaysLoaded`。**

#### 三、注入时机：最晚是用户首次打开 EUI 面板之前

- 行只在 `CreateMainFrame` 内一次性创建（`:7935-7950`），该函数幂等且只被 `Show()`／`Toggle()`／`ShowModule()` 调用。
- `RefreshSidebarStates` 是**未导出的 local 函数**，只重排已有按钮，不补建行；全库没有 `RebuildSidebar` 之类的 API。
- **面板已打开后再注入 = 静默失败**（不显示新行、不报错）。但此时 `EllesmereUI:ShowModule(folder)` **仍然可用**——页面能开，只是没有侧边栏行。
- 强制重建需自己手搓按钮塞进 `EllesmereUI._sidebarButtons` 并满足 `_label`／`_dlIcon`／`_loaded`／`_indicator`／`_glow`／`_glowTop`／`_glowBot` 字段依赖，**脆弱，不采用**；直接提示 `/reload` 是稳妥兜底。

#### 四、`ShowModule(folder)` 的副作用

- 战斗中直接 return（打印红字）。
- 首次调用会 `EnsureLoaded()` → **自动按需加载 EllesmereUIOptions 并在此刻创建 `EllesmereUI.Widgets`**，本次调用被推迟一帧。选项插件被禁用时 `Widgets` 为 `nil`，面板照样打开。
- **不切分组**（分组只是同一滚动列表里的表头）。
- `_euiCore ~= true` 只关掉两样东西：**页内搜索框**与**专精覆盖按钮**（`:10373-10380`，全库仅此一处消费）。没有别的功能被关掉。

#### 五、档案切换后重新应用：**没有注册 API，只有一个可用的包装挂点**

这是本次调研最关键、也是**与本项目第 13 项决策存在张力**的发现。

- EUI 自家兄弟插件之所以"切档案就变"，是因为 `Ellesmere` 把它们的 apply 函数名**硬编码**进了文件局部数组 `REFRESH_ADDON_STEPS`（`EllesmereUI_Profiles.lua:1350-1432`），由公开函数 `EllesmereUI.RefreshAllAddons`（`:1496`）遍历调用。同一份清单在专精覆盖系统里被重复维护了一份（`EllesmereUI_SpecOverrides.lua:88-107`）。
- **两个数组都是文件 local，外部无法追加**；全库也**不存在** `RegisterModuleRefresh` 之类的公开注册点。所以"被 EUI 自动调用"这条路**不通**。
- **唯一可靠的挂点：包装 `EllesmereUI.RefreshAllAddons`。** 它本身是公开无门禁的，且所有调用点都写作 `EllesmereUI.RefreshAllAddons(...)`、没有任何地方缓存局部引用，所以运行时替换可以覆盖全部路径（手工切换／导入／专精驱动／同步领养／未映射兜底）。
- 替代方案对比（详见调研原文）：包装 `SwitchProfile` 覆盖不全；轮询档案名有延迟且漏掉导入与条件翻转；**无可用游戏事件**（EUI 没有自定义事件总线）；只靠 `db.profile` 换表**不够**——已建好的框体不会自己变。

```lua
-- 一次性安装，幂等；务必 pcall（全量刷新路径本身没有 pcall）
if not EllesmereUI._myuiRefreshHooked then
    EllesmereUI._myuiRefreshHooked = true
    local orig = EllesmereUI.RefreshAllAddons
    EllesmereUI.RefreshAllAddons = function(budgeted)
        if orig then orig(budgeted) end
        pcall(MyUI.ApplyProfile)
    end
end
```

> **张力**：用户在[需求追问](01-requirements-grilling.md)里选了"配置跟随 EUI 配置档案"，同时明确排斥偏门用法（否决虚拟文件夹名）。而让"跟随档案"真正生效，**恰好需要一个偏门挂点**。已就此新开[配置存储方式复议](08-config-storage-reconsideration.md)。
>
> 附带说明：若改为独立存储，档案切换时本来就没有东西需要重新应用，**这个挂点可以完全去掉**。

#### 六、`RepointAllDBs` 的陷阱：绝不能缓存 `db.profile`

`RepointAllDBs`（`EllesmereUI_Profiles.lua:792-805`）每次切换都把 `db.profile` 指向**一个全新的表**。任何在登录时缓存的 `local p = db.profile` 会永久指向废弃表——**写出去的数据不保存、读到的永远是上一个档案的值，且完全静默**。

对策：只提供 `GetProfile()` 即时解引用；另外 `RepointAllDBs` **只遍历 `EllesmereUI.Lite._dbRegistry`**，只有走 `Lite.NewDB` 建的库才会被重指向。

#### 七、配置读写契约

- **`StripDefaults`（`EllesmereUI_Lite.lua:187-200`）只删除 defaults 里存在的键**，递归比较，等于默认值的叶子键被删、空子表（非数组）被删、数组即使空也保留。**defaults 里没有的键永不删除。**
- "缺失的键等于默认值"成立，但机制不是读取兜底、而是 `DeepMergeDefaults` 在 `NewDB` 时和每次切档案时补齐。**注意 `false`／`0`／`""` 这类默认值与"未设置"不可区分**（`Lite.lua:172-179`）。
- **硬约束（静默失败）**：`Lite.NewDB` 从 SavedVariables 名反推文件夹键（`svName:match("^(.+)DB$")`，`Lite.lua:259`）。因此 **SavedVariables 名必须恰好是 `插件文件夹名 .. "DB"`**，否则 `db.folder` 与侧边栏／同步／导出的 folder 分裂成两套键，配置看起来"丢失"。
  → 对本项目即：功能插件的 `.toc` 写 `## SavedVariables: MYUI_CrosshairHUDDB`。（修正[需求追问](01-requirements-grilling.md)中"不写 SavedVariables"的表述——该变量虽为宿主占位、会被清空，但必须声明，因为它是文件夹键的来源。）
- **迁移不会动外部插件**：`EllesmereUI_Migration.lua` 里对 `addons[...]` 只有具名访问，没有通用遍历。
- **导入保留、导出不包含**：档案导出只遍历 `ADDON_DB_MAP`（`Profiles.lua:987-1000`），**外部插件的配置不会随导出串走**（静默限制，需在方案里注明）；导入侧是透传语义，不会删你的数据。
- **专精／条件覆盖的间接风险**：外部文件夹不在黑名单、**可被捕获**进覆盖，但应用时 `REFRESH_FNS` 命中不到 → 走全量兜底，而全量兜底不含你 → 界面停在覆盖前的旧值。**把 apply 挂在 `RefreshAllAddons` 上可以顺带修掉这个坑。**

#### 八、挂载代码骨架

已产出完整可用骨架，包含：`EnsureDB`（含 `type(EllesmereUIDB) ~= "table"` 守卫）、`InjectSidebar`（幂等、不设 `alwaysLoaded`、分组追加）、`RegisterModule`（**直接写 `_modules`，绝不调 `RegisterModule`**）、`buildPage`（首行取 `EllesmereUI.Widgets` 并判空返回）、`InstallRefreshHook`、`PLAYER_LOGIN` 装配与 `/slash` 打开入口。正式实现照此起步。

**建议同时使用 `EllesmereUI.RegisterSkin(name, fn)`**——它是 Ellesmere 唯一有开发者文档的公开第三方契约（`SKINNING_API.md`），既让视觉统一，也提供一个稳定的加载顺序保证。

#### 九、风险清单（全部为**静默**失败，除非注明）

| # | 风险 | 缓解 |
| --- | --- | --- |
| 1 | 在 `EllesmereUIDB` 被覆盖前调 `NewDB`（加载顺序） | `## OptionalDeps: EllesmereUI` + `type(EllesmereUIDB) ~= "table"` 守卫并推迟 |
| 2 | SavedVariables 名 ≠ `文件夹名 .. "DB"` | 强制命名一致，启动断言 |
| 3 | 缓存 `db.profile` | 只用 `GetProfile()` 即时解引用 |
| 4 | 面板已打开后才注入 → 无侧边栏行 | 在 `ADDON_LOADED`／`PLAYER_LOGIN` 完成注入；提示 `/reload` |
| 5 | `buildPage` 在 `Widgets == nil` 时被调用 | 页面体首行判空返回 |
| 6 | 档案切换后不重新 apply | 包装 `RefreshAllAddons`，全程 `pcall` |
| 7 | 被专精／条件覆盖捕获后界面不跟随 | 同 6；或用 `RegisterSyncExclusions` 排除布局键 |
| 8 | 布尔默认值用 `false` 导致与"未设置"不可区分 | 谨慎选择默认值语义 |
| 9 | 误设 `alwaysLoaded` → 电源按钮消失 | 真实插件不设 |
| 10 | 主动往 `ADDON_ROSTER` 插入以求 CPU 计入 | 同时影响重置文案与搜索别名；默认不要动 |
| 11 | 配置不随档案导出串走 | 无官方 API；接受并在 UI 注明 |
| 12 | 误调 `RegisterModule` → 静默什么都没注册 | 绝不调用，直接写表 |

其中**第 6 条是唯一的"报错型"风险的来源**——它是包装外部函数，报错会往外冒到选项面板，所以 `pcall` 是必须的。

#### 十、待实机验证

1. `## OptionalDeps` 下 EUI 的 `ADDON_LOADED` 是否确实先于我们触发（决定注入能否看到已填充的三张表）。
2. 我们的 `PLAYER_LOGIN` 是否晚于 EUI 的 `PreSeedSpecProfile`；若不晚，`db.profile` 可能指向错误档案——规避是**该时刻不缓存值**。
3. `ShowModule` 首次调用被推迟一帧时，连续快速调用的 `_openPending` 行为。
4. 包装 `RefreshAllAddons` 在 budgeted 模式下的时序：我们的 apply 被同步调在 `orig()` 之后、但**早于** tail 里的位置落定；若依赖位置，可能需额外延迟一帧。

#### 十一、对下游交付

- 方案计划的集成章节直接采用上述骨架、时机与风险清单。
- **新增待定项**：[配置存储方式复议](08-config-storage-reconsideration.md)。
