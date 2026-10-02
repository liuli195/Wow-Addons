# 数据管理性能诊断与测试证据修正

2026-10-02。本轮起点为干净的 `a75ed32069a6480ee680f13d3b7a07ba6fef3a3f`，固定正式基线为 `f554538993161cc045d19c4ed47d261f709f741b`。不修改共享 build-and-verify、模式绑定、缓存或并发配置；本轮独立 pytest 诊断不代替正式验收。

## 正式失败的具体范围

原正式报告生成于 `2026-10-02T14:24:35.822Z`，38 项检查，总耗时 60.0143788 秒，原因 `total_budget_timeout`，阶段 `finalization`。重新按报告数组计数，纠正此前口头 37/19 的误报：15 passed、3 timed_out、20 not_started。日志的选择原因是 `config-changed`，没有缓存命中记录。15 个通过项有实际 `check-start/check-end`，不能把未启动项的 0 秒解释为缓存通过。

通过项（秒）：luals 5.75、luacheck 1.86、toc 2.00、sim2gse-probe-luals 6.28、sim2gse-probe-luacheck 0.69、sim2gse-probe-toc 0.64、crosshair-media 3.45、myseries-luals 6.48、myseries-luacheck 0.86、myseries-toc 0.77、myseries-series 1.72、crosshairhud-luals 6.39、crosshairhud-luacheck 0.74、crosshairhud-toc 0.64、crosshairhud-tests 2.95。均带 `verify.` 前缀。

未完成：`verify.sim2gse` 41.67 秒、`verify.sim2gse-data` 41.67 秒、`verify.wowaddontest-skill` 0.44 秒。

未启动 20 项：wowaddontest-dk、sim2gse-probe-test、addon-probe-luals、addon-probe-luacheck、addon-probe-toc、addon-probe-test、assets、docs、checker-tests、annotation-build、test-inventory、gear-async、gear-build-names、gear-delete、gear-empty、gear-save-armor、gear-save-as、gear-stat-filter、gear-summary、myspec-main。均带 `verify.` 前缀。

原配置外层 `maxParallel=3`；前两项分别为 `.venv\Scripts\python.exe -m pytest -q tests/sim2gse --dist=worksteal` 与 `.venv\Scripts\python.exe -B -m pytest -q tests/sim2gse-data --dist=worksteal`，工具配置各注入 8 个 xdist worker。第三个位置依次运行上述 Lua/插件检查。所有具体命令保持在 `.build-and-verify/config.json`，本轮未改变。

两大检查仅获得 41.67 秒，故总预算中约 18.34 秒花在检查外准备和收尾；报告没有更细分的准备计时，不能进一步归因。原深路径单例独立运行 57.719696 秒，保留 220 文件、12 层长路径、同一索引与全部五阶段，其本身已超过该实际窗口。8+8 worker 并行可能增加争用，但本轮没有并行/独占的受控全套对照，不能宣称争用是根因。

## 有限诊断结果

全部使用临时合成数据、原生 `--durations` 和独立总限时包装器；没有重跑正式工具。

| 诊断 | 结果 | pytest 秒 | 外层秒 |
| --- | --- | ---: | ---: |
| 旧截断注入加实际触发断言，15 秒上限 | 如预期失败，文件仍存在 | 0.83 | 1.259 |
| 修正后的维护全组串行，20 秒上限 | 超时，仅部分完成，不算通过 | 未完成 | 20.444（含终止收尾） |
| 修正截断及相邻两个容量用例，12 秒上限 | 3 passed | 3.97 | 4.260 |
| 可复制最小运行技能用例，串行，12 秒上限 | 1 passed | 0.91 | 1.184 |
| 同一最小运行技能用例，8 worker，12 秒上限 | 1 passed | 1.90 | 2.217 |
| 维护全组，原有 8 worker，25 秒上限 | 10 passed | 11.20 | 11.512 |

最小入口的测试体分别 0.88/0.89 秒，8 worker 额外约 1.03 秒主要在体外；不外推为完整测试配置收益。维护组最慢用例：56 万条流式合成盘点 10.19 秒、增量盘点 4.02 秒、完整维护授权链 3.30 秒、大未知根 3.25 秒。并行维护组的截断用例 1.18 秒，独立相邻组三项中该用例 0.80 秒。

## 测试修正范围

远端审查发现旧注入依赖第三次 `scandir.close`，当前路径只扫描一次，导致截断场景没有发生。现在仅在测试的 `shutil.disk_usage` 操作系统边界、读取模拟 free 之前删除既有 3 MiB producer 文件；落盘 marker 记录 `before=3145728, after=0`，父测试断言文件消失及 marker 精确值，然后保留原“可用空间不足”拒绝断言。没有修改生产容量逻辑、恢复额外扫描或减少测试数。

## 按收益与风险排序的下一步

1. 深路径单例是已测量的主瓶颈。已知准备 19.97 秒、归档批准执行 10.11 秒，五阶段合计约 37.36 秒；后续优先定位重复路径/身份/盘点调用的成本，但任何合并必须保留并验证每个锁和竞态边界。不得改 220 文件、五阶段、同根累积历史或元数据拒绝断言。需先形成具体安全等价设计供父端评估。
2. 检查前约 18.34 秒直接挤占预算；本轮仅报告事实。共享验证工具和跨工作区模式调查由父端负责，本仓不改工具、不调用 doctor、不改缓存。
3. 批量登记可减少每文件两次 CLI 启动，但当前最慢深路径准备已批量登记 220 文件；已有小型多文件夹具可逐项检查是否适合批量接口，收益上限先按实际调用数估算，涉及注册语义/覆盖改变须先评估。
4. 不采用简单 worker 数量下降或取消追踪：独立最小用例只能证明约 1 秒启动成本，尚无整套收益证据。56 万流式夹具在 tracemalloc 下逐条创建对象；复用同一对象会削弱“错误全树物化超过内存上限”检测，不能当作等价优化。

原 121 项核心测试和原五阶段保持，正式整套仍失败。没有生产启用、真实历史操作或计划任务安装。

## 优先调度单行试验

父端远端完整审查提出采用 unittest 既有字典序及 xdist 既有调度，不添加 hook 或修改 runner。修改前 collect 大例为第 18 项（index 17）；仅改名为 `test_000_large_legal_restore_plan_is_admitted_before_any_metadata_write`，修改后首项，仍 121 项（0.06 秒），方法体和所有断言完全不变。实现检查点 `4320aeff1c25141fc93605b32d27bc321826ceb0`。

本轮安装的共享工具已由外部恢复为原有 CLI，不支持此前 `--execution-context local`。第一次启动仅解析参数即退出（0.246 秒，exit 2），没有运行检查。只读核对当前技能和 parser 后，以其支持的 `verify --project . --base f554538993161cc045d19c4ed47d261f709f741b` 实际执行一次；不修改共享工具、绑定、配置或缓存，外层同样从启动起硬限时 60 秒。

实际验证仍超时，外层报告 `bounded-deadline=60.601; owned-pid=40592; taskkill=128`，包含终止收尾时间，不能记为通过。当前入口汇总输出被缓冲，截止时没有逐项输出或新的性能报告；原报告仍为 `2026-10-02T14:24:35.822Z`。因此本轮已完成/未完成项、cache fresh/hit、深路径在并发环境的实际耗时均无法从证据可靠确定，不能沿用旧报告统计当本轮结果。日志保存在系统 Temp 的 `simdata-formal-4320aef-priority-compatible-60s.log`；参数拒绝日志另存 `simdata-formal-4320aef-priority-60s.log`。

单行调度未获得整套通过，不继续盲调核心或反复正式运行。数据单例独立 57.72 秒距离总预算仅 2.28 秒，而此前检查外时间约 18.34 秒，仍需具体、保留安全边界的性能方案。批量登记在主瓶颈中已采用；缩小文件/阶段或复用 56 万条同一对象均会改变核心覆盖，不采用。下一步由父端评估主路径安全等价优化与准备成本的责任范围，已有开放问题仍保留。

## 缺少配置根的计划任务预览修正

远端审查发现机器配置缺 `data_root` 时，单次 `--root` 可使预览生成 XML，但任务动作仅带 `--config`，后续无法找到根。仅将 `data_root` 加入预览的 unresolved 字段元组，不扩大 CLI 或安装计划任务。扩展既有预览测试：配置根置 null，同时传入临时 `--root`，断言 XML 为 null、未决项精确为 `[data_root]`、未安装/未启用、机器配置字节不变和数据根目录内容不变；随后恢复配置字段继续原有未定参数拒绝测试。有效 XML、Windows 内存任务 XML 解析及 744/745 小时间隔断言均保留。

测试先失败：旧实现仍输出 XML，pytest 1.01 秒，外层 1.406 秒。单字段修正后，只运行两个预览/间隔相关测试，2 passed / 8 deselected，pytest 2.19 秒，外层 2.520 秒（15 秒硬限时）。collect 仍 121 项、0.04 秒。未运行完整正式 60 验证，未减少原大型五阶段覆盖；候选票据和整套验证门禁仍未完成。

## 用户批准的覆盖矩阵取舍量测

用户明确批准 Sentinel_1a4a1203b51c8191b11fcdff1bff695b。第一项保留大型220源/12层深路径/801KiB及两次紧容量拒绝全部断言，只留verified大规模持久中断恢复；普通同根同index同archive五阶段保持，补operation ID/sealed/返回数量的零I/O断言。明确少四条大规模中断交叉及1100→220恢复位置历史，不声称等价。相关2 tests/6 subtests passed，pytest23.74秒、外层24.120秒；大型22.63秒、普通4.20秒。固定实现f48bbc402512fad1ccc1a83c546dd52c8845dd61随后正式统一入口仍被60秒外层终止（60.585含收尾，PID33412，taskkill128），无逐项输出，不作通过。

第二项经父端完整review确认，56万规模保持一次complete全数/字节/未截断及32MiB峰值检测；去除同规模低容量/足额两准入交叉，准入继续由2400实体未知文件用例覆盖，补返回reserved_bytes=10。每条仍新对象，tracemalloc不变，增长/截断竞态不变。8 worker维护组仍10 passed，pytest5.63秒、外层5.951秒；56万用例4.09秒，对照此前同组11.20秒/用例10.19秒，整组约少5.57秒、该例少6.10秒，存在机器噪声，不能保证正式整套同幅收益。目标30–40秒，正式硬上限仍60秒；未获正式pass不能交付。

最后采用公开夹具批量登记优化，敌意tar七种输入（穿越、绝对、驱动器、设备名、软链、硬链、PAX）及七次恢复拒绝/目标不存在断言完整保留。先生成独立7包+7清单，清单包摘要/大小取实际包字节；公开legacy-register一次预览一次批准登记全部14文件，再逐项核对登记SHA/size。准备28→2次CLI，没有生产改动或新增helper。相同单测前1 passed/7 subtests passed，pytest6.71秒/外层7.042；后同样1+7通过，pytest2.77秒/外层3.128，约少3.94秒。正式整套另测，不将局部改善冒充30–40秒目标已达。

本轮最终正式量测固定干净实现 `ec3dac6d27d71a17b52b444631a14c18d0cbb514`，统一入口、原固定基线、外层60秒上限；设置PYTHONUNBUFFERED仅用于输出证据，不改工具或配置。结果仍超时：`scene: local; selection-reason: config-changed; bounded-deadline=60.605; owned-pid=7036; taskkill=128`，墙钟含终止收尾。没有完整逐项汇总或新性能报告，旧报告仍不代表本轮fresh/cache和完成范围。完整日志位于系统Temp `simdata-formal-ec3dac6-final-60s.log`。正式未通过，30–40秒目标未达成，不能交付或关闭票据；不再盲删其他核心测试或扩大本轮优化范围。

## 一次完整诊断和数据组独立测量

按父端明确授权，只运行一次完整诊断：固定 `7a78c613d84ccc1f00fe902e085f97f276065337`，既有统一工具 `verify --project . --full --performance-report`，原Temp防挂包装器180秒，未修改全局工具/模式/仓库预算或worker配置。此为诊断，不是正式60秒验收。原生工具报告111.81秒、外层113.426秒、exit1：38项检查实际执行，37 passed、1 failed；full路径不读取通过缓存，本轮各项均fresh，原工具正常写入37个成功结果缓存，未把失败数据组写成通过。原生完整报告已保留为 `data-management-diagnostic-7a78c61-full-report.json`，其中含38项状态/耗时。系统Temp完整日志 `simdata-diagnostic-7a78c61-full-180s.log`。

主要检查：原Sim2GSE 311 passed/95 subtests passed、pytest62.26秒/check66.76秒；数据组 `check_timeout: verify.sim2gse-data exceeded 60s`，check实际111.73秒；wowaddontest-dk19.14秒、wowaddontest-skill16.47秒、checker-tests11.89秒、annotation-build9.94秒。数据超时路径不保留其partial pytest stdout。111.73包含cache-key准备/命令/超时收尾，不能当纯测试体耗时或推断精确阶段。源码通过Windows shell=True调用subprocess.run，超时后的后代持有管道可能延长收尾，但当前证据没有父子进程和开始/结束精确轨迹，不能断言因果。

并行核验：当前真实调用源码 `_run_scheduled_checks` 使用ThreadPoolExecutor，max=min(配置3,并行检查数)，提交所有checkParallel；两个pytest的命令构造在实际调用路径各注入 `-n 8`，--dist不被误判为已有-n。执行输出有xdist节点启动及测试进度，没有降级提示。38项原生耗时合计322.79秒，整仓wall111.81秒，比值2.89，构成外层实际重叠执行证据，不能把汇总迟到解读成全组串行。该工具在所有future结束后按配置顺序输出，不提供每check start/end/排队或worker分配轨迹；未新造runner补伪时间。原生源码+节点输出支持内层启用，但无法从quiet输出验证每个worker的具体分配。

为了取得优化后数据121组独立耗时，再使用授权的原生单组诊断 `.venv/Scripts/python.exe -B -m pytest -q tests/sim2gse-data --dist=worksteal -n 8 --durations=15`，独立90秒上限，未修改生产配置。121 passed、79 subtests passed，pytest64.81秒、外层65.154秒、exit0；这是超60的诊断通过，不能变成正式通过。系统Temp日志 `simdata-diagnostic-7a78c61-data-alone-90s.log`。最慢：深路径37.98秒、1000空成员27.25秒、事实输出边界21.76秒、隔离恢复五阶段15.44秒、过期purge新计划14.43秒、旧归档五阶段12.88秒、迁移阶段11.03秒、purge阶段11.01秒。数据自身超60，原项目也62.26秒，因此并非仅靠某一大例再命名即可达到30–40。

进程与taskkill核验：以前7036/33412/40592 PID在本轮查询时均不存在，但旧包装器没有保留当时poll/最终child.returncode及taskkill文本，不能追溯证明自然退出或树终止成功，`taskkill=128`必须视为未证实的终止结果。只在既有Temp包装器补poll/最终exit/捕获的taskkill stdout和stderr，不修改共享runner；本轮两次诊断均正常结束，不触发taskkill，完整诊断exit1、独立组exit0。系统有较早Python/Node进程，但八个旧Python累计CPU数十秒间隔完全不变；CIM父进程/命令行读取被拒，不提权、不终止其他进程，无法确认其他仓库是否正在测试或CPU竞争。

最小后续配置对照候选：保持outer3/data8，仅原Sim2GSE inner8→4，避免两大组同时16worker；必须实测整仓wall与121完整通过才能采用，当前并无受控8/4对照证据，本轮不修改。独立数据组也65.15秒，降低别组worker不能保证数据低于60；不能硬堆worker或继续盲删。正式60仍未通过，需父端评估有边界的并行配置对照和生产主路径成本后继续。

### 独立数据组最慢五项及worker证据原文

以下直接来自既有 `simdata-diagnostic-7a78c61-data-alone-90s.log` 的原生durations，不新增运行：

```text
37.98s call tests/sim2gse-data/test_archive.py::ArchiveTests::test_000_large_legal_restore_plan_is_admitted_before_any_metadata_write
27.25s call tests/sim2gse-data/test_archive.py::ArchiveTests::test_one_thousand_empty_members_are_bounded_and_restore_preview_validates_them
21.76s call tests/sim2gse-data/test_facts.py::FactTests::test_output_byte_bound_refuses_large_query_and_snapshot
15.44s call tests/sim2gse-data/test_safety.py::SafetyTests::test_quarantine_and_recovery_committed_phases_and_post_move_crash
14.43s call tests/sim2gse-data/test_safety.py::SafetyTests::test_expired_interrupted_purge_requires_new_bound_plan_and_item_approval
```

日志节点启动原文只有：

```text
bringing up nodes...
bringing up nodes...
```

该quiet日志没有 `created: 8/8 workers`、`gw0`–`gw7` 或case对应worker前缀，所以可列出的实际worker IDs为空；不能仅根据argv显式 `-n 8` 或启动提示断言八个worker全已创建/每例分配已确认。完整命令是 `.venv/Scripts/python.exe -B C:/Users/liuli/AppData/Local/Temp/simdata-bounded-check.py 90 .venv/Scripts/python.exe -B -m pytest -q tests/sim2gse-data --dist=worksteal -n 8 --durations=15`。已有日志未出现retry/restart/crash/replacing，`u`是subtest进度，不是重试；正常exit0未调用taskkill，但没有后代进程树审计，不能证明全部无残留。本次仅补文档，不重新测量。

## 单点隔离/恢复夹具复用

起点2f3b9a39。只改SafetyTests.test_quarantine_and_recovery_committed_phases_and_post_move_crash的准备：每个reserved/writing/published/sealed/rename阶段fresh一个来源，先完成quarantine故障/恢复/幂等，再复用同一已隔离对象进行同phase recover-quarantine故障/恢复/幂等。五阶段仍五个不同ID，补ID唯一、返回原operation ID/sealed/同artifact断言，无额外业务I/O。十个phase×command故障、rename后exit77、原字节及幂等断言保持。生产计划读取quarantined custody，operation ID包含generation，支持该接续状态；未修改生产。准备72→52 CLI、setup jobs15→10，明确改变每阶段第二来源及正常隔离准备结构，不删除故障组合。

before/after只运行该代表用例，准确pytest参数 `-q tests/sim2gse-data/test_safety.py -k quarantine_and_recovery_committed --dist=worksteal -n 8 --durations=5`，既有Temp包装器各25秒上限。修改前1 passed/10 subtests passed，call13.29秒、pytest23.75秒、外层24.163秒；修改后同样1+10 passed，call9.40秒、pytest10.53秒、外层10.876秒。测试体约少3.89秒；前体外耗时约10.46秒明显大于后约1.13秒，因此不能将wall差13.29秒全归因夹具改动，也不能保证整仓同幅下降。没有运行完整数据组或整仓，本轮正式60仍未通过，等待父端准确远端review与后续放行。

## 放行后的唯一正式60验证

固定干净实现bf04f47b4e2dffd4d3e786264008975af74bbc83，父端确认无budget重测并发后仅一次统一入口 `verify --project . --base f554538993161cc045d19c4ed47d261f709f741b`，既有外层硬限60秒。配置outer3/inner8不变；PYTEST_ADDOPTS=`-v --durations=5`为原生输出参数，未改runner。开始前已知历史owned PID7036/33412/40592/30088均不存在，但历史没有持久化全部后代，不能推断所有历史残留已清空。

结果正式失败：日志scene local、selection-reason config-changed，明确35条cache-hit。其余fresh为verify.sim2gse-data、verify.docs、verify.test-inventory，没有完整结束汇总，不能算通过。缓存原Sim2GSE等35项未实际重跑，不冒充38fresh。原生非quiet worker输出仍被统一工具capture到检查结果，中断前未汇总打印，所以这轮没有created worker行证据，不重新测量补打印。系统Temp日志 `simdata-formal-bf04f47-isolated-60s.log`。

超时边界观察：`bounded-timeout-poll=None; owned-pid=23384`表明该时主进程仍运行；`bounded-deadline=60.495; taskkill=128; bounded-child-exit=1`含终止收尾。taskkill stdout确认主及多个后代终止，但stderr有12个后代“操作不被支持”，故128不能当树终止成功。随后立即只读逐个检查主23384及报错后代6612/12572/27172/40908/30556/36516/23992/23872/36828/3548/41544/33400，13个全部absent；本轮已知节点结束，机器已释放，未盲杀其他进程/提权/重测。包装器实际exit124，统一主进程exit1，不能将PowerShell最后Get-Content的exit0当验证成功。

30–40秒目标仍未达，正式60仍失败。没有自动优化或更多测量，下一步由父端依据现有存量证据安排；候选票据、正式规格和交付门禁未关闭。

## 同源8与12 worker单方向对照

放行后仅8/12各一次，源码固定049e50ff（实现bf04），两轮参数同为原生 `-B -m pytest -v tests/sim2gse-data --dist=worksteal -n N --durations=10`，既有包装器各90秒防挂，不改变正式60。完整日志随仓保留 `data-management-workers8-049e50f.log` 和 `data-management-workers12-049e50f.log`，包含全部121 case对应worker记录。

8轮原文 `created: 8/8 workers; 8 workers [121 items]`，gw0–gw7均出现；121 passed/79 subtests passed，pytest73.52秒、wall73.960秒、exit0。12轮原文 `created: 12/12 workers; 12 workers [121 items]`，gw0–gw11均出现；同样121+79 passed，pytest60.49秒、wall60.819秒、exit0。两轮均WorkStealingScheduling，没有retry/worker crash/重建提示，正常退出未调用taskkill，已知owned28132/41928随后查询均不存在。旧65.154秒来自夹具复用前源码，不作本轮基线。

12轮wall少13.141秒（17.77%），虽关键case均变慢：深路径36.60→44.21秒、1000空成员33.95→39.97秒、事实字节边界20.96→25.64秒；整体并行排队缩短仍改善wall，不能将单case下降或组耗时相加作为目标。设备20逻辑CPU、31.76GiB物理内存，计划时可用6.67GiB；12运行中一次只读快照可用7403372544字节（约6.90GiB）/load78%，非峰值或无争用证明。仅修改verify.sim2gse-data.pytestXdistWorkers为12，外3、原项目8、全部覆盖和timeout不改。配置变更会使相关成功缓存失效，下一次正式整仓必须如实区分fresh/hit，不保证该单组60.819能使正式端到端低于60。

两份入库日志只去行尾空格，原Temp日志保留。首次保存时差异检查因原生行尾空格失败而PowerShell仍继续提交，已在下一提交a1f622b只修日志空白，重新差异检查通过；没有更改用例记录或测试结果。

满足12全组通过且明显更快的条件后，严格只执行一次正式统一整仓：干净a1f622b25ec7428c638cec4851185721c66b2a77，原固定base、outer3/product8/data12、正式60硬预算，原生PYTEST_ADDOPTS=`-v --durations=5`。仍超时：poll主32440=None，收尾wall60.750秒，owned最终exit1，包装器exit124，taskkill128（不作为成功判断）。日志scene local/config-changed，没有cache-hit或完整check汇总；配置变更全选38，不代表38均已执行或结束，fresh完成范围不可得。原performance-report仍是15:55:46的111.81秒诊断，未更新，不当新正式结果。

终止后只读解析日志所有PID及主ID，共79个（含日志父子关联节点），逐个查询79均absent；本轮已知节点退出，机时已释放，不继续重测/优化/杀未知进程。完整正式日志存仓 `data-management-formal12-a1f622b.log`，包含原taskkill stdout/stderr字节证据。12单组wall改善已证实而正式60未通过，30–40目标未达，候选票据及交付门禁仍开放，下一步等待父端准确远端review。

## 三事实组登记与过期时钟准备复用

93e780bd起点，未改生产或worker配置。事实类型6、完成证据8、路径轴5个文档各先生成隔离子目录，以小型batch_extracted测试夹具复用公开legacy-register一次预览一次批准；19个extract仍分别执行，全部原compare/assert保持，少10+14+8=32个准备CLI。坏trace仍原独立注册提取拒绝。72事实字节边界本轮完全不改，不向Safety未知引用推广legacy-register。

过期purge仅reserved/published原两组：复用isolated_plan已有公开300秒计划，取消每组重复preview及其覆盖计划；现有injected_call中替换标准库time.time，初次批准和原commit后exit77在plan.expires-1，后续purge/renew/pin全在expires+1。断言旧error含过期，renewed.created精确expires+1、期限300；原operation ID/新plan hash、published已完成数量、新逐项确认/保护变化/已删除文件重现拒绝/原文件保留及最终全部purged断言完整。去2×2.1秒等待和2次重复preview，没有新时钟框架/改索引/改生产。其他真实1.05秒心跳等待保留。

仅代表小组before/after各一次，原生 `-v tests/sim2gse-data/test_facts.py tests/sim2gse-data/test_safety.py -k 'request_types_and_nested or complete_search_summary or real_rule_path or expired_interrupted_purge' --dist=worksteal -n 4 --durations=5`，既有包装器各30秒防挂；created4/4，4 tests/2 subtests均pass。before pytest12.56/wall12.910秒，after9.90/wall10.258秒。各call前→后：purge11.81→7.47、完成证据5.91→3.66、类型4.82→3.08、路径轴4.26→2.94秒。数据实际小组wall少2.652秒，不能把四个case差值相加当整仓收益，机器噪声仍存在。本轮无整仓或121完整组重测，正式60仍未通过，等待远端review与机时放行。

## 029a802放行后的唯一正式结果

父端确认budget机时结束后放行，仅一次干净source `029a80279c3a75c40d6c3aeada4ead539693e016` 正式统一 `verify --project . --base f554538993161cc045d19c4ed47d261f709f741b`，原outer3/product8/data12、60硬上限；PYTEST_ADDOPTS仅`-v --durations=5`，无代码/配置变化。仍失败：`bounded-timeout-poll=None; owned-pid=8656; bounded-deadline=60.766; taskkill=128; bounded-child-exit=1`，墙钟含收尾、包装器exit124。

原生输出仅scene local/selection-reason config-changed，没有cache-hit、duration/checked或结束汇总。配置变更全选38，但实际started/finished数量及每组耗时不能从当前工具capture结果取得；不声称38fresh均运行或0项实际成功，仅无可确认的完成证据。原performance-report仍为15:55:46/4440字节的旧诊断，不当本轮正式报告。正式原日志存仓 `data-management-formal-029a802.log`（仅去行尾空格，Temp原始日志不变）。本轮真实瓶颈仍是全选路径在60内不能结束、完成时序证据受现有工具汇总限制；既有8/12完整组和最慢case证据保留，不据此断言本轮某一case具体慢了多少。

终止后只读解析日志PID+主，共83关联节点，逐个查询83全部absent，机时明确释放；128不单独当终止成功。没有重复重测、删边界、调整worker、正式规格应用、合并/上线或历史数据操作。30–40目标未达，正式60及交付门禁仍未通过，下一步由父端review存量证据后安排。
