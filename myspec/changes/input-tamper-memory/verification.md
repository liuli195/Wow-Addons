# 阶段二首切片验证

固定基线04008b17，代码仅改test_simulation_config.py：39行增加/22行删除。无生产、正式配置、预算或其他阶段变更。

- 普通定向：1 passed、2 subtests，pytest 0.08秒；不是官方守卫验收。
- 灵敏度检查：仅在独立测试进程临时替换_verify_task_inputs为无操作，公开resume随后触发TaskStore禁构造哨兵，两子测试均失败；恢复原函数后普通全组绿。该证据是测试敏感性红/绿，不冒称产品缺陷修复或修改前已完成新测试的红灯。
- 普通全组：288 passed、122 deselected、108 subtests，4.65秒。
- inventory：GSE410=288普通+122真实；gear23=21普通+2真实，互补/登记通过。
- 真实承接定向：实际执行失败于原run_task→foreground_search，Linux缺msvcrt；新增物理篡改断言尚未运行。不加假锁，不宣称通过。
- 固定data-store副本四文件SHA与父层本机记录逐项一致，DuckDB1.5.6；从已有云端源复制到固定.local/verify-deps/data-store，无安装工具。
- 当前云端官方守卫身份未确认。按父层要求不安装/升级、不冒用历史guard；官方普通守卫及Windows真实节点/全43交父层当前官方入口验证。
- 日志：.local/tests/input-tamper-memory/{ordinary-first,sensitivity-red,ordinary-suite,inventory,real-target}.log。

## Windows交接

先固定交付提交，同原正式配置。定向执行：

```
.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_simulation_config.py::SimulationConfigTests::test_tampered_input_is_rejected_before_task_store_construction tests/sim2gse/test_simulation_config.py::SimulationConfigTests::test_task_records_effective_config_and_rejects_changed_resume --strict-markers --durations=10
```

随后由当前官方build-and-verify入口运行普通守卫与无缓存全43：

```
build-and-verify verify --project . --full --performance-report --execution-context local
```

60秒预算及恢复后的正式配置不变。保留原始日志、起止提交、计数、退出码、未完成项及总调用耗时。对照为恢复后本机e793679全43外层58.062秒；单项历史3.54秒不是净节省。云端定向不替代本机结果。独立代码审查已对04008b1…c26a0a3固定提交范围完成：Standards规范轴0发现，Spec需求轴0发现，均无阻塞。两个只读Reviewer使用gpt-6.1-sol/high通用回退，未运行测试或修改状态。代码静态通过不替代上述Windows运行验收。


## Windows实际验收（2026-10-25，父层回读）

执行提交均为远端 `ae8063b98941372fbb1ed41d18efa72dd62e9107`（云端同树 `5bcb4fee`）；以下为父层从本机任务取得的结果，非云端测量。

| 检查 | 实际结果 |
| --- | --- |
| 新两个目标节点 | 2 passed＋2 subtests，外层2.734秒；物理篡改、TaskStore禁构造、SQLite逻辑及三个成果文件原字节保护已实际执行 |
| 第一次完整验证 | 42通过/1失败；工具57.684171秒、外层57.938秒；GSE真实121通过/1失败＋24子测试，检查47.73秒；普通288＋108及17普通守卫通过；无残留 |
| 旧benchmark定向诊断 | 3次全过，未捕获额外真实异常；不能记成偶发已修复 |
| 同提交第二次完整验证 | 43项全部通过；工具57.4255589秒、外层57.672秒；GSE普通288＋108、真实122＋24；真实检查47.42秒/pytest46.04秒，普通检查5.06秒；17普通守卫通过、无缓存/残留，本机工作树干净 |

第一次失败为既有 `test_benchmark.py::BenchmarkTests::test_snapshot_publication_recovers_from_brief_directory_occupation` 第87行：预期重试调用3次、实际4次。该项把固定注入失败和真实目录读写/替换重试混在同一个计数中；现有日志不足以定位额外PermissionError的具体来源。本票未修改它或生产重试逻辑，不把后续通过称为已修。风险保持开放，若改第二个测试文件须另按授权范围处理。

本机证据目录（均在仓库内）：
- `.local/formal-ga-development/stage2-target-fb942120ee6e4b70a4d7bb87761d3d9a`
- `.local/formal-ga-development/stage2-full-7524836144824318b9d98171573c8ffb`
- `.local/formal-ga-development/snapshot-diagnosis-a244434197e24313aae7888cb2addc83`
- `.local/formal-ga-development/stage2-repeat-c1d6cb66d39a4a8c95155f5162733f7b`

输入迁移的定向、真实边界、官方普通守卫和全43验收已完成。相对恢复配置基线外层58.062秒，本次通过外层57.672秒单次少0.390秒；不是统计收益，也不证明稳定低于60秒。第一次完整失败仍为有效历史，不被第二次成功覆盖。后续本提交仅记录验证文档，代码不变。阶段三慢测试和阶段四Lua尚未实施，不能据本票宣布全仓优化完成。
