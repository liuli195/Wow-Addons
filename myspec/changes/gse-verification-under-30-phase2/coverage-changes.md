# 最小真实通道与主动删减的覆盖边界

## 四条真实通道：不是 mock 过关

| 节点（省略 tests/sim2gse/） | 输入 → 必须实际执行的依赖 → 可观察结果 |
| --- | --- |
| test_interface.py::InterfaceTests::test_browser_computes_copies_and_clears_real_candidate | 审核角色文本与 180ms 输入 → Edge 真实页面和 HTTP、基准/受控原生引擎、两场真实搜索与复测、Lua 导出/集合编译、任务文件和物理报告中心 → completed、1/5 目标、两代/381 样本、三个合法独立导出/集合、重读状态、实际剪贴板一致、改输入清旧结果。 |
| test_native_compatibility.py::NativeComparisonTests::test_original_baseline_and_disabled_controller_keep_native_combat | 同一角色和2次迭代 → original/baseline/controlled 三个真实二进制与构建/源码身份 → 除明确元数据外战斗报告逐值一致，Live 数据及非空能力/静态参数有效。 |
| test_data_store_connection.py::test_connected_consumer_reads_writes_without_old_user_installation | 隔离安装副本与新项目 → 官方 project_binding connect、新进程加载消费者、真实物理中心 → 数值/嵌套字段和二进制读写、投影/过滤正确，空用户目录下可用。 |
| test_search.py::SearchAndValidationTests::test_owned_process_tree_hard_exit_does_not_stop_other_owner | 两个独立所有者及各自子孙进程 → Windows 真实进程/Job 所有权 → 强杀首个所有者后其后代退出，另一组仍活着，最后本次拥有的所有进程均回收。 |

浏览器此前的 memory_result_center 已移除；此通道写入真实结果中心。sequence.evaluate 只有收集输入的观察包装并立即调用原生产函数，不返回预设评分。它使用现成最小候选准备，不改产品默认；不承担随机种群多样性或最终 DPS 最优性证明。浏览器脚本前半段已有页面日志开关路由构造只验证 UI 接线，后半段独立上下文执行上述真实任务，不能将前半段冒称引擎证据。

## 两条低成本迁移

- combat_log 的最新会话/UTC/DPS 对照：旧物理文件+CLI 调用改为既有 analyze 的 StringIO 输入与 simulation 字典；同样的会话选择、偏移与对照断言保留。不再声称覆盖该 CLI 的进程/文件入口。
- report_write 的 opt-in 阶段统计：调用真实 result_store.write_batch；仅把最终 result_store.write 落盘边界换为 Mock。核 table/key、实际准备的 report 内容、一次写入、开启时 stage calls/seconds/rows 和关闭时不创建性能字段。由原 True 一项扩为 False/True 两项；不声称证明 Parquet 物理写入。

两迁移共同通过 418 普通检查的官方 2.7.1 源审计适配器：4 worker、完整证据、零副作用违规。最终仍由本机官方全仓入口再次检验。

## 明确不再持续覆盖的风险

删除 112 个原真实实例是用户批准的覆盖削减，不是完全等价去重。特别不再持续穷举：

- 每一粗评/复测批次的取消位置、训练/正式冠军版本冻结、旧冠军保护、失败后不发布部分批次、各阶段补发/恢复组合；
- 物理损坏、临时读错、锁、CAS、并发发布、多个 Store/四模板任务并发的专门故障矩阵；
- 多来源施法、队列/重置/共享 CD、节奏/phase/空点击/loop、复杂宏/导入形态、不同原生目录和身份变更的逐例真实执行；
- 旧来源适配、导入/恢复错误、训练模板和诊断 CLI 的重复文件链。

仍有普通内存规则对部分逻辑提供保护，但不能据此称这些物理和原生风险全部承接。四条真实冒烟只证明其表列范围；运行产品功能没有被删除。完整旧节点去向见 coverage.md。

## 辅助代码与历史

另删 final_export_compilations 无消费者辅助函数和仅测试它的 1 个普通自测（内部2次断言），保留同文件直接验证生产来源校验的另一项普通测试。

删除仅供这些边缘用例使用的冠军/页面伪原生 fixture、类型化内存中心、重复准备/并发 helper、已无测试的 formal_champion_review 模块及无用导入。保留普通测试仍消费的 memory_ga、冠军内存证据、unchanged_offspring，以及既有研究脚本仍引用的 _fast_evaluate/_fast_initialization；不创建新的重型套件，不向旧研究入口迁移被删测试。

上一全覆盖路线及 fc696 中间成果留在 Git 历史/保留 ref。当前代码只改测试与任务文档；产品代码、正式功能规格和当前已批准 8 路配置不变。
