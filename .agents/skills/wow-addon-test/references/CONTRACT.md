# 接入契约 v1

## 一、输入与预期分离

工具的输入在 `data/cases.json`；预期在 `data/baselines.json`，普通运行只读且校验摘要。适配器不会收到预期或用于参照路由的 `resource_kind`。生成器知道哪段原生代码对应哪个用例；被测代码必须自己通过实际接口、职业、专精和形态选择资源。

“输入隔离”用于防止误接线，不是对恶意代码的保密沙箱。文件都在用户本地。

每个用例包含完整初始输入和完整后续快照，不使用隐式深度合并。用例之间新建 Lua（脚本）环境；同一用例的步骤之间保留插件对象、缓存、订阅与计时器。

## 二、项目配置

配置路径相对自身定位 `project_root`；`adapter`、`files` 相对项目根。源文件不能越出项目根，不自动递归执行陌生文件。

```json
{
  "schema_version": 1,
  "project_root": "..",
  "addon_name": "MYUI",
  "adapter": ".wow-test/adapter.lua",
  "files": ["真实生产文件.lua"],
  "specs": "all",
  "components": ["health", "primary", "resource"],
  "require_cleanup": true,
  "timeout_seconds": 60
}
```

`files` 是明确的加载白名单；用例执行后会检查它们确实被加载。它不是“加载了就证明全部逻辑测到”的代码覆盖率。只列出这三个组件实际需要的模块及依赖即可，不必执行整个插件所有功能。

`specs` 可以是 `all` 或专精 ID 数组，不能使用 1/2/3 这种专精索引代替 ID。

## 三、薄适配器

```lua
return function(ctx)
    local addon = {}
    ctx.load('真实生产文件.lua', 'MYUI', addon)
    return {
        start = function() addon.真实启动方法() end,
        snapshot = function() return addon.已有业务状态 end,
        stop = function() addon.真实停止方法() end,
    }
end
```

这是接口形状，不是对 MYUI 真实方法名的承诺。可工作的具体实现见两个示例。

| 功能 | 接口 |
|---|---|
| 被测环境 | `ctx.env`，在加载生产代码前可按已核实契约添加项目专用外部依赖 |
| 加载真实文件 | `ctx.load(path, addonName, namespace)`；只加载配置白名单 |
| 创建事件/状态条替身 | `ctx.env.CreateFrame` 支持 Frame、StatusBar、Button；默认不支持 XML 模板 |
| 复制业务数据 | `ctx.copy(value)` |
| 空数组输出 | `ctx.array()`；避免把空数组误当对象 |
| 事件与时间 | 工具自动通过 `ctx.emit`、`ctx.advance` 驱动已注册回调；适配器不得主动循环刷新 |

必须将真正状态转成下面的结构。只允许字段重命名、索引整理、明确的单位适配，不允许重写业务计算或用期望值填空。

## 四、输出契约

每个检查点返回包含所选组件的普通 Lua 表：

```lua
{
  health = {value=500, maximum=1000, connected=true},
  primary = {type=3, token='ENERGY', value=50, maximum=100},
  resource = {kind='combo', capacity=6,
    nodes={{full=true,charged=false}, ...}}
}
```

| 类型 | `resource` 的字段 |
|---|---|
| `none`（未选择次级组件） | 只有 `kind` |
| `combo`（盗贼连击点） | `capacity`、`nodes[].full`、`nodes[].charged` |
| `druid_combo`（德鲁伊连击点）、`holy`（圣能）、`chi`（真气）、`arcane`（奥术充能） | `capacity`、`nodes[].full` |
| `shards`（碎片） | `capacity`、`amount`，毁灭允许小数，其他两专精整点 |
| `essence`（精华） | `capacity`、`nodes[].state`：full / recharging / empty；恢复节点附 `partial`（0–1）、`duration`（秒） |
| `runes`（符文） | 六项 `nodes[].state`：ready / empty / cooldown；冷却项附 `start`、`duration`（秒） |
| `stagger`（醉拳） | `value`、`maximum` |

生命和主资源比较的是**原生请求写入的逻辑值**，不是图形引擎插值后的像素。原生生命上限零会用 1 兜底；断线时填满条。采用不同产品策略的插件应提出显式契约差异，不能悄悄改适配器伪装相同。

本版关闭预测消耗、动画、视觉排序；不比较对象分配数量。精华比较重新采样时的充能语义，不比较原生动画在 0.1 容差内的平滑过程。符文尚未到期但 `ready=true`、到期而 `ready=false` 仍以输入为准，不用时钟重新模拟服务器。

## 五、事件检查点

执行顺序：安装初始输入 → 真正启动插件 → 每步安装完整输入 → 推进到该步时间 → 投递该步事件 → 推进约定等待 → 再排空一轮零延迟回调 → 读取业务输出。

这里的事件序列是人工测试刺激，不是实际客户端录制。原生参照在每个检查点重新采样目标方法；被测插件保持状态并通过自身事件/逐帧链更新。因此能发现漏更新和旧状态，但不证明原生完整启动时序、全部过滤或缓存策略一致。

`C_Timer`（计时器）有确定顺序、取消与回调预算。框架的 `OnUpdate`（逐帧）只在明确推进时调用，不模拟显示帧率。框架可见性只处理自身 shown 属性，不实现复杂父子显示传播。

测试结束先调用插件 `stop`，检查订阅/计时器是否仍存在，再强制清理环境。已有插件没有停止入口时，适配器可使用已暴露资源进行清理；不能仅依赖环境销毁来宣称生产清理正确。确实无法测试时可明确关闭 `require_cleanup` 并说明缺口。

## 六、接口范围与缺口

内置：生命、资源、主资源类型、专精身份、形态索引、连接/死亡/战斗、连击点强化、符文三返回值、部分资源、资源恢复、醉拳、已知法术布尔、按法术 ID 查询光环的有限入口、事件与计时器。

它们按数据返回，不计算职业机制。可选缺失的冷却起点保持 `nil`（空值），后续返回位置不移动。没有配置的资源类型/单位会报错。当前基本单位是 player（玩家），并不是全单位模拟器。

`C_UnitAuras`（光环接口）的有限替身不是完整的光环迭代协议。增强、复仇、噬灭的附加计数没有原生预期；接口存在不等于该功能已覆盖。

不支持的真实客户端能力：受限值语义、污染、安全按钮、受保护操作、战斗锁定权限、原生 C++ 控件内部行为。普通 Lua 成功不得被表述为这些能力已验证。

## 七、状态与退出码

| 退出码 | 含义 |
|---:|---|
| 0 | 选定范围内通过，或命令成功；仍需读取覆盖缺口 |
| 1 | 发现业务差异；或自测失败 |
| 2 | 环境、配置、执行、清理错误；无匹配用例也报错 |

未知专精、重复 ID、缺少用例、缺少检查点不能算通过。报告中的 `not_selected`（未选择）也不能算通过。
