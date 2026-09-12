# 序列编码、编译与按键语义研究

核查日期：2026-09-12。对应[核实序列编码、编译与按键语义](../../myspec/changes/sim2gse-wayfinder/issues/03-gse-evidence.md)。本轮在用户确认上一项完成后，按地图顺序复核固定发布版源码；没有制作导入串、执行插件或完成游戏测试。

## 研究版本

本次以 GSE（按键序列插件）`3.3.32` 为可复查的研究快照；发布标签指向提交 `f225d4c947d168c63451ef7c567d7063c38cc239`。这不是用户实际安装版本的证明，也不是替用户选择目标版本。[发布页](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/releases/tag/3.3.32)、[对应提交](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/commit/f225d4c947d168c63451ef7c567d7063c38cc239)

本轮重新核对发布页，并从完整提交地址取得 5 份源码：序列化、存储／编译、图形导出、工具函数、静态脚本定义。只读快照位于 `.tools/sim2gse-research/gse-f225d4c/`，每份文件的来源、大小和 SHA-256（文件散列）在 `.local/sim2gse/gse-source-review.json`。下述行号以本轮固定提交文件为准，不沿用旧页面或浮动主分支行号。

## 已取得的依据

| 事项 | 结论与来源 |
| --- | --- |
| 普通编码链 | `EncodeMessage`（编码入口，6 行）将 CBOR（紧凑对象表示）序列化、压缩、Base64（二进制转文本编码）串联，加上 `!GSE3!` 前缀。`DecodeMessage`（解码入口，13 行）另行区分 `!GSE3!+` 打包路径，不能混用。[固定序列化源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Serialisation.lua#L6) |
| 两种普通导出外壳 | 图形导出的 `compileExport`（封装函数，29 行）创建 `type = COLLECTION`（集合类型）和 `payload`（载荷）；序列载荷按名称作键保存原始序列对象。另有真实的 `ExportSequence`（单序列导出，工具文件 1826 行），编码“名称、序列”二元数组；两者都不能被当成唯一格式。[图形导出源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_GUI/Export.lua#L29)、[单序列导出源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_Utils/Utils.lua#L1826) |
| 导入与元数据 | `ImportSerialisedSequence`（导入入口，434 行）按集合、单对象及二元数组分支处理。当前结构使用 `MetaData`（元数据）、`Versions`（版本数组）及其 `Actions`（动作数组）；图形导出还会在克隆对象上更新版本和校验字段。解码成功不能等同于导入成功。[导入源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_Utils/Utils.lua#L434)、[导出元数据](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_GUI/Export.lua#L434) |
| 编译与法术转换 | `CompileTemplate`（模板编译入口，2457 行）经 `processAction`（块展开，2284 行）生成线性动作表，普通循环保留子动作顺序。`buildAction`（动作编译，2176 行）分别处理法术编号与宏文本转换；伤害日志编号不能直接视为可按技能映射。[固定编译源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2176) |
| 执行边缘与推进 | 执行按钮使用 `AnyUp`（松开事件）并固定 `useOnKeyDown=false`（不按下执行）；直接按下触发由单独转发按钮处理。有效执行路径写入当前编译步骤后推进，不查询施法成功；因此资源或公共冷却造成的失败不使该步骤原地等待。暂停与重置例外见下文。[执行与转发源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2509) |
| 结构诊断 | `checkSeqStructure`（结构检查，768 行）由 `ScanMacrosForErrors`（错误扫描，1234 行）调用，检查数组缺口、块类型及宏文本等；不能把诊断函数的存在当成每条导入路径都会严格拒绝所有非法输入。宏正文的 255 长度检查优先用专用计长函数，不是整条导出字符串的长度限制。[固定诊断源码](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE_Utils/Utils.lua#L768) |

作者的块规范把动作块定义为一次点击对应的一组命令，并区分动作、循环、暂停等类型；它能支持首版选用有限子集的研究方向，但不能证明模拟器队列与真实客户端相同。[作者块规范](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/wiki/GSE-3.3-Block-Specification)

本地锁定的客户端接口资料列出默认 Deflate（无损压缩方法）与 Standard（标准文本编码变体）。这只说明参数默认值，二进制封装及表类型仍要用真实样本核实。[固定接口源码](https://github.com/Gethe/wow-ui-source/blob/8ea15b61e45c0ed4eba01439c90757f86eb78d34/Interface/AddOns/Blizzard_APIDocumentationGenerated/EncodingUtilDocumentation.lua)、[本仓库版本记录](../../scripts/dev/versions.json)

普通解码源码第 18 行从第 6 个字符取子串，仍包含前缀的最后一个 `!`。外部解码实现不能悄悄把它当成已经验证过的标准库调用；分隔符容忍、压缩封装及对象键类型留给后续离线往返样例核对。本轮没有据此宣称上游故障或修改其代码。

## 暂停与重置的边界

- 命中 `shiftpause`、`altpause` 或 `ctrlpause`（修饰键暂停）时，脚本清空本次宏并提前返回，不执行当前步骤，也不推进。普通动作失败与主动暂停是两种情况。[暂停分支](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2668)
- 宏重置修饰键生成的前置脚本只设置 `step=1`（步号归一），没有提前返回，也没有重置 `iteration`（分段号）；随后继续本次点击。若同时命中暂停，重置先发生，再由暂停分支返回。[重置模板](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Statics.lua#L304)、[脚本拼接顺序](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2665)
- `ResetButtons`（按钮重置，1304 行）也只重置步号；按钮重编译在 `combatReset`（战斗重置条件）为真时，才同时重置步号与分段号。不能统称为“任何脱战都回到完整序列第一步”；事件调用时机和用户实际配置尚未验证。[按钮重置](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L1304)、[重编译复位](https://github.com/TimothyLuke/GSE-Advanced-Macro-Compiler/blob/f225d4c947d168c63451ef7c567d7063c38cc239/GSE/API/Storage.lua#L2659)

以上是固定源码的分支证据，不是客户端按键、技能队列或网络延迟已经实测。300 毫秒是用户选定的名义输入间隔，不能与上述触发边缘或技能队列窗口混为一个参数。

## 后续必须补齐的证据

1. 按地图顺序，用固定研究版本为后续离线原型核对导出外壳、必要元数据、键类型、编译顺序、法术替换与本地化；本票不提前制作原型。
2. 原型从少量代表性动作块开始；完整矩阵按最终支持范围覆盖中文、重复技能、多命令块、错误与超长输入。暂停等高级块不能仅凭名称推断时长或执行语义。
3. 先产出离线候选模拟结果和可导入产物；到真实导入阶段才讨论实际发布版、绑定和重置配置。若目标版本不同，再比对并重跑受影响检查，不要求现在安装插件。
4. 到该阶段，由用户实际导入、查看编译结果并再次导出；比较核心顺序与对象语义，不要求压缩字符串逐字相同。
5. 在实际绑定下观察失败推进、暂停、初始位置、重置、公共冷却期间输入及当前候选用到的物品能力。成功施法日志不足以证明全部失败按键；缺少观察则保持待验证。

这些缺口分别由[取得目标版本、角色与最小序列样本](../../myspec/changes/sim2gse-wayfinder/issues/05-target-evidence.md)、[验证最小序列的导入与编译契约](../../myspec/changes/sim2gse-wayfinder/issues/07-export-prototype.md)及[验证输入控制与饰品的最小执行模型](../../myspec/changes/sim2gse-wayfinder/issues/08-execution-prototype.md)承载。本研究已完成的是来源定位与实验边界，不是编码、导入、编译或游戏行为四层验收。
