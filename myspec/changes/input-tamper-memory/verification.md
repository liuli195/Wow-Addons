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
