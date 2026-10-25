# 阶段三验证记录（待Windows正式验收）

基线云端8f2d25ec/远端同树bc5efe725，原正式配置与60秒预算不变。用户已明确批准两票，本轮不进入Lua。

## 票01

代码仅test_formal_champion.py，12增/3删。首次通过公开单体run_task准备旧冠军，补完成/发布断言；第二次HTTP dual及十来源、正常复测、替换断言保留。已提交c495579；独立Standards、Spec两轴对8f2d25ec…c495579审查均0发现。

云端运行原目标及双场继承专项：2失败。原目标明确在foreground_search因缺msvcrt失败；双场继承返回failed而非completed，未取得真实完成证据。未加假锁绕过，需Windows实际验证，不能当作通过或已测得提速。

## 票02

代码仅test_benchmark.py，29增/10删。普通用例精确保护3次替换调用与2次0.02等待；真实回调分开记录两次注入与非注入PermissionError，保原内容/清理/篡改拒绝，等待实际执行。生产重试及永久/其他错误测试不动。

- 红灯：独立诊断进程在真实替换边界额外构造一次PermissionError，旧测试稳定出现4!=3（1失败）。这是可控故障复现计数问题，不是捕获本机原偶发的真实根因。
- 绿灯：相同额外故障构造下改后测试1通过（0.10秒），确认额外错误计数1；未吞异常或放宽为>=3。
- 正常定向三项（新普通规则、真实短暂占用恢复、永久/其他失败）：3通过＋2子测试，0.12秒；真实等待调用约0.04秒。
- 普通全组：289通过、122按real选择排除、108子测试，4.61秒；这是直接pytest，不冒称官方守卫验收。
- inventory：GSE411=289普通+122真实；gear23=21普通+2真实，登记和互补通过。
- 日志：`.local/tests/stage3-slow-test-roi/` 下champion-target.log、retry-red-extra-permission.log、retry-extra-permission-green.log、retry-target-green.log、ordinary-suite.log、inventory.log。

## Windows交接

先固定最终远端提交；按既有当前官方入口，不安装/更新云端工具。

```
.venv/Scripts/python.exe -m pytest -q tests/sim2gse/test_formal_champion.py::test_dual_preserves_legacy_ten_source_paths_and_replaces_champion_after_complete_retests tests/sim2gse/test_formal_champion.py::test_dual_inherits_each_scenes_formal_champion_after_publication tests/sim2gse/test_benchmark.py::BenchmarkTests::test_replacement_retries_two_permission_failures_then_succeeds tests/sim2gse/test_benchmark.py::BenchmarkTests::test_snapshot_publication_recovers_from_brief_directory_occupation tests/sim2gse/test_benchmark.py::BenchmarkTests::test_snapshot_publication_preserves_persistent_and_unrelated_failures --strict-markers --durations=10
build-and-verify verify --project . --full --performance-report --execution-context local
```

保全部43项、17普通守卫、无缓存、60秒及恢复后的正式参数。记录实际单项与总墙钟，不将历史10.18秒直接当收益；阶段二外层57.672秒仅单次参考。额外真实权限错误仍可能发生，最多11次边界和其他错误原样失败；未证明原偶发系统原因已修。票02独立Standards、Spec两轴已对c495579…8348b0c完成审查，均0发现。两票审查均只读，使用按策略通用回退gpt-6.1-sol/high；静态通过不替代Windows验收。文档检查416份通过。Windows未验收前不称完成。
