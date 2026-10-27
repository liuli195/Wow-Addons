# 03 训练接口隔离与参数一致性

Status: done
Blocked by: none (02 completed)

## 验收
- 训练十项参数与4组×5路、两代耐心、原采样默认不变，不继承正式128/5/8或根随机种子。
- 接受的训练运行设置真正生效；不支持及重复权威来源在计算前明确报错。
- 爆发按键间隔不静默改写显式值；支持则透传，不支持明确拒绝。
- 基础日志和曲线能力保留；文件仅兼容既有共享曲线选项，训练显式选择优先，不新增从正式文件读取其他日志项。恢复使用原冻结计算清单。

## Comments
通过现有run_training与训练命令行公开入口作小型内存红绿，禁止实际训练。


### 实施记录（待独立审查）
- 公共训练／准备raw输入拒绝参考次数、根种子、错误来源并发及正式算法项；专用并发参数不变。内部历史完整配置与原规则快照仍只读验真，未放宽摘要锁。
- 明确日志总闸与细分不再被覆盖，重复总闸权威来源报错；爆发间隔明确值透传，未指定仍200／300毫秒。新训练开启总闸默认summary；恢复未明确细分沿保存值，不把saved off升级。
- 恢复准备与评分均使用原冻结计算，合法新文件不热改；明确计算冲突在原生计算前拒绝。非法当前文件仍报错，不扩展混合组加载。
- 红绿证据均位于 `.local/config-separation-ticket01/ticket03-*.log`：`invalid-red/green`（22例）、`runtime-red/green`（日志与重复来源）、`public-run-red2/public-run-green5`（完整公开运行）、`resume-red/green`（6例冻结／冲突）。补充CLI run／prepare、共享曲线与false优先、训练默认／采样／Reset实际消费回归。
- 核心普通回归：`ticket03-core-regression.log`，135 passed、26 subtests passed、guard complete。扩展含旧冠军验真检查：`ticket03-current-regression.log`，145 passed／3 failed；3项均已有客户端目标数据CRLF兼容锁基线失败，不修改锁或绕过验证。最终扩展回归 `ticket03-final-regression.log`：168 passed／3 failed、26 subtests passed、guard complete；仍为相同3项基线锁失败。
- 不执行真实搜索／训练，不复制数据库，不提交／推送／部署；正式规格未写入。

代码完成待独立审查：公开训练及准备入口拒绝未消费正式参数和重复权威来源；按键间隔、重置与基础日志真实透传；冻结恢复只允许明确观测覆盖，计算冲突提前拒绝。训练十项默认和原生算法不变，历史内部九字段仍按原记录验真。

公开贯穿内存检查证明250毫秒、重置事件、显式细分关闭、训练32与3×128及两代不变。核心守卫135项与26子检查通过；扩展168项与26子检查通过，3项目标数据CRLF锁基线失败明确保留。非法当前配置文件仍明确报错，不为坏文件恢复重写混合组调度。


### 独立审查返工：多次恢复观测
- 修复Spec1发现：恢复省略观测时取最新可靠检查点中的四项观测配置，而非回到不可变清单初始值；无检查点配置时回退清单。计算始终取原清单，摘要锁及UUID机制未改。
- 三次公开run_training恢复覆盖总闸开关双向、summary→off细分、曲线开关，以及原计算清单不变。红绿日志：`ticket03-rework-three-calls-red.log`／`ticket03-rework-three-calls-green.log`，目录同上；最终相关回归：`ticket03-rework-regression.log`。

### 最终独立审查与整合
- 提交 `e1a8c50`：独立 Spec 与 Standards 两轴复审均通过，无剩余发现。多次恢复观测修复已复核。
- 最终相关回归：`ticket03-rework-regression.log`，152 passed、26 subtests passed。
- 最终全体普通测试：`integrated-reviewed.log`，461 passed、168 subtests passed、4 failed、4 deselected，14.86秒，guard complete。4项失败均为已确认基线客户端目标数据换行与锁摘要差异；4项真实测试按范围排除。
