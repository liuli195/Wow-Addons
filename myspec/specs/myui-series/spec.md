# MYUI Series

## Purpose

让 MYUI 系列以「一个系列、多个功能插件」的形态出现在游戏的插件列表与 EllesmereUI 的设置面板里：共享素材与侧边栏名册由公共核心插件持有，每个功能插件在 `MYUI` 分组下各占一行；功能插件被禁用或未加载时，它的行仍须留在面板里。系列整体硬依赖 EllesmereUI，不做任何兜底。首版系列里只有一个功能插件（准星 HUD）。

## Requirements

### Requirement: MYUI series appears as one grouped project in the addon list

系统 MUST 让公共核心与各功能插件在魔兽的插件列表中归入同一个 `MYUI` 分组，功能插件 MUST 使用带系列品牌色的标题，使玩家能看出它们属于同一个系列，而不是互不相干的插件。

#### Scenario: Addon list shows the series as one group

- **WHEN** 玩家打开游戏内的插件列表
- **THEN** 功能插件显示在 `MYUI` 分组下并带系列品牌色标题，公共核心作为该分组的根条目出现
### Requirement: MYUI group is listed first in the EllesmereUI sidebar

系统 MUST 在 EllesmereUI 设置面板的侧边栏里提供 `MYUI` 分组，并把每个功能插件作为该分组下的一行列出；该分组 MUST 排在所有其他分组之前。

#### Scenario: First opening of the EllesmereUI settings panel

- **WHEN** 玩家首次打开 EllesmereUI 的设置面板
- **THEN** 侧边栏最上方是 `MYUI` 分组，其下列出每个功能插件一行，行名与插件的显示名一致

#### Scenario: Feature row opens its configuration page

- **WHEN** 玩家点击某个功能插件的行
- **THEN** 该功能的配置页被打开
### Requirement: A feature row survives being disabled by its power button

行的登记 MUST 由不会被电源按钮禁用的公共核心完成。功能插件被禁用后，它的行 MUST 仍然留在 `MYUI` 分组下并显示为未启用，玩家 MUST 能再次点击它重新启用。系统 MUST NOT 把功能插件标记为「始终视为已加载」，那会隐藏电源按钮。

#### Scenario: Row remains after disabling the feature addon

- **WHEN** 玩家点击某功能行右侧的电源按钮禁用它并重载界面
- **THEN** 该行仍留在 `MYUI` 分组下、显示为未启用，再点一次电源按钮可以重新启用

#### Scenario: Feature addon is not loaded but still listed

- **WHEN** 公共核心已加载而某个功能插件未加载
- **THEN** 侧边栏中该功能插件的行仍然存在，只是显示为未启用
### Requirement: EllesmereUI and the shared core are hard dependencies

每个功能插件 MUST 把 EllesmereUI 与公共核心声明为硬依赖。任一依赖缺失时功能插件 MUST NOT 加载，系统 MUST NOT 提供降级、兜底或替代路径。

#### Scenario: EllesmereUI is disabled

- **WHEN** 玩家禁用 EllesmereUI 后重载界面
- **THEN** 功能插件不加载，屏幕中心不出现任何 HUD 元素

#### Scenario: Shared core is disabled

- **WHEN** 玩家禁用公共核心后重载界面
- **THEN** 依赖它的功能插件同样不加载
### Requirement: Shared core carries the series media and warns against disabling it

系列共享的纹理 MUST 随公共核心发布，功能插件 MUST NOT 重复携带同一批纹理。公共核心的插件说明 MUST 写明它的用途与「请勿单独禁用」及其后果。

#### Scenario: Addon list explains the shared core

- **WHEN** 玩家在插件列表中查看公共核心的说明
- **THEN** 说明写明它提供系列共享素材与侧边栏名册，并提示不要单独禁用它
