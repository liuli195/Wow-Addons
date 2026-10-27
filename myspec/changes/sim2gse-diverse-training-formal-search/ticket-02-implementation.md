# 票02实施与验证记录

状态：票01在 `80f1a3c` 通过独立复审后实施；本票在90068d9通过独立本机Astra high审查，规范与需求均无P1/P2；审查确认509项普通测试及168项子测试、4项real排除。随后获准实施票03。

## 实现范围

- 正式契约为 `formal-ga-rtr-v3`。正式参数新增 `rtr_window_ratio=.66`、`behavior_alpha=.5`，分别校验；训练参数不读取它们，正式终评默认8与训练改10独立。
- 版本3训练快照验证生产时记录的实际人数、上限和最低发布数；消费全部已发布程序，移除适配器旧四条截断。版本1/2完整快照继续可读，所有新任务均不扫描、也不加入旧独立训练冠军。
- 起点保留原生程序、适用快照、最多一个历史正式冠军。复用当前角色适配和精确身份去重；成功初评后冻结实际 N，窗口 `max(1,min(N,ceil(ratio*N)))`。合成验证 9/10/13/15 人分别得到 6/7/9/10；初评剔除坏成绩后 1 人窗口为1。
- 复用 DEAP `varAnd`、锦标赛选父（默认3）、并发评价和缓存。每个孩子的无放回窗口在评价前保存；按提案顺序对本代已更新种群寻找最近成员，严格改善才替换，相等保留。生存结果仅在完整代后写入种群和代数。
- 无效粗评后代跳过竞争，不宣称某个固定槽位必然保留；新版容错契约为 version2。旧完整正式 v1/v2 的容错契约仍按原语义验证。
- 正式质量榜独立负责停滞和 top K（前K名）终评；不调用训练最远点代表入围。正常复测最高成绩产生答案，候选和历史冠军相等时保留历史冠军。
- 正式参考报告建立并冻结行为上下文，复用训练的可靠原生执行/玩家增益描述；恢复粗评凭据同时校验描述。
- 页面开始传递独立正式参数；继续只传本次观测选项，不注入服务后来改变的算法设置。运行进度、结果中心记录、发布补写意图及公开结果读取保留人数和窗口。新完整 v3 与旧完整 v1/v2 都可读取；旧未完成 v2 在只读预检拒绝，不开启可写任务。

## 实际红绿证据

本目录日志均为实际执行输出，尾行记录退出码。开发过程中修正过合成夹具的 WaitClicks 最小值及进度 elapsed_seconds；表内红灯日志是在夹具有效后执行，未将夹具错误当作业务红灯。

| 日志 | 检查及实际失败 |
| --- | --- |
| `ticket-02-red.txt` | 9失败：人数/窗口4组、正式独立参数、v3完整人数3组、旧训练冠军排除 |
| `ticket-02-sources-red.txt` | 2失败：实际6/10条快照被旧四条适配上限截断 |
| `ticket-02-read-red.txt` | 1失败/1通过：公开读取v3失败、旧v2读取通过 |
| `ticket-02-page-red.txt` | 4失败：页面公开结果缺少人数与窗口 |
| `ticket-02-skip-red.txt` | 1失败：无效后代诊断仍声称固定槽位保留 |
| `ticket-02-progress-red.txt` | 1失败：运行进度缺少人数与窗口 |
| `ticket-02-green.txt` | 最终普通层509通过、168子测试通过，排除4项真实检查；7.38秒，退出码0 |

共同环境：`$env:PYTHONDONTWRITEBYTECODE='1'`，`.venv/Scripts/python.exe -m pytest`。

定向红灯命令依次为（每条均另带 `-p no:cacheprovider --basetemp=.local/tests/formal-rtr --tb=short`）：

```text
-q tests/sim2gse/test_formal_rtr.py tests/sim2gse/test_formal_champion.py -k "freezes_actual or weights_and_window or v3_snapshot or exclude_independent"
-q tests/sim2gse/test_formal_rtr.py -k assembly
-q tests/sim2gse/test_formal_rtr.py -k public_result
-q tests/sim2gse/test_formal_rtr.py -k freezes_actual
-q tests/sim2gse/test_formal_coarse_tolerance.py -k retains_verified
-q tests/sim2gse/test_formal_rtr.py -k progress
```

最终普通层命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest -q tests/sim2gse -m 'not real' --strict-markers -p no:cacheprovider --basetemp=.local/tests/formal-rtr --tb=short
```

额外保留的检查：两孩子面对已更新种群、严格改善和相等保留；已评缓存不重算；冻结窗口半代中断恢复与不中断运行的种群、随机状态、请求一致；真实报告结构的坏评分剔除、错误样本及非评分失败不掩盖；版本1/2/3完整冠军凭据验真。

## 验证边界

- 普通层使用既有公开 HTTP（网页接口）接线、任务结果读写和共享优化器的合成输入/内存存储。没有以这些检查证明真实引擎执行或物理持久化可靠性。
- 未运行4项 `real`（真实）检查、统一 `build-and-verify verify --project . --base a914e40c9e20225647729b0ea16d680cc476fdf9 --execution-context local` 的真实引擎链、真实训练、新原生模拟或游戏验收。
- 未修改 `myspec/specs/`，未推送、合并、发布或安装。新增文件远低于50MB；整体预算仍从19:08 UTC累计。
