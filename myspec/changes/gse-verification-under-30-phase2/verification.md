# 阶段2开发证据（尚未完整验收）

## 正式首验、最小修复与同8单组对照

- `f0444f81d6183fc452878b48af31d235f71baf54` / tree `02e848f27444200245e06631e4a978bce2dbcfef`与此前审查的local7657同树。Windows BAV2.7.1完整43实际运行、0缓存：42通过1失败，GSE117通过1失败/19sub，37.95秒；工具53.7462042、wall54.016。**未达标，不是通过验收。**
- 唯一回归是预建单场省略max_processes而HTTP显式1；生产条件哈希正确区分默认2与1。修复只给该预建任务显式1，身份/旧冠军/版本/不发布断言不变。remote `5e5cbb8d4aa1e69ab5e008f408843d8d668a4129` / tree `7c6f3e1e6d4c864749882201b9573702351fcaf9`与localb02同树；独立Astra增量通过，Windows原失败节点1通过，pytest1.84/wall2.176秒。
- 用户要求同8单测GSE对照：before main3ee与after5e产品/依赖/正式规格相同，实验CLI均8/worksteal、相同durations/JUnit参数；不修改before正式config6。

| 单组诊断（不是全仓验收） | before main3ee | after5e |
|---|---:|---:|
| 真实结果 | 118＋19sub全过 | 118＋19sub全过 |
| pytest秒 / wall秒 | 31.76 / 32.087 | 29.24 / 29.575 |
| 全节点累计工作秒W / 最长L | 219.519 / 15.228 | 199.788 / 15.315 |

单组墙钟减少2.512秒（7.83%）、工作量减少19.731秒，证明自身已有收益；**29.575不能当全仓GSE<30**。主要收益来自population36.534→26.504和simulation_config7.498→2.345工作秒；interface39.944→39.572、search25.525→25.547未明显下降。setup最高0.98、teardown最高0.04、worker工作秒21.279–27.203，不支持为了这些数据另造调度器或更大共享准备。

后续统一最简通道候选见`coverage-changes.md`第6节，基于after5e继续，尚未新的Windows完整验收。云端普通416＋168通过、118仅deselected，6.52秒；第6节的生产内存GA阶段反例通过。所有原断言保留，暂停第二粗评新增32场断言。普通通过不替代真实/全仓。规格、生产代码、BAV参数不变；下一固定候选先Astra增量再正式全仓，不插新profile矩阵。

本机原始证据：首验`.local/gse-phase2-full-d4f5237b6b584b68b447575afc83e722`保留失败现场；单组对照`.local/gse-phase2-profile-e227fb2a1e004d6fb251b7074d6d320f`保留stdout/JUnit/118节点/阶段、模块、worker与comparison.json。对照成功临时回收162227065B，核心429KB；不删除首验失败现场或历史。累计上限仍1.7GB，下一本机执行前按实际账核余量。

## 首候选的整合代码证据（历史）

2026-10-25已正常整合main `3ee81b5048ed51c4238b40df9abb15d17569b5e0`，无冲突。被实际测试的代码候选是`e0f42cc79b9ee593d8f7374dedb39a19a2712fab` / tree `c469d1224baef1f820a141fd2300e163cf3405b3`：云端普通选择**416 tests＋168 subtests通过，118 real仅deselected**，6.51秒。相对该新main，产品、技能及正式规格无差异，配置仍仅GSE真实6→8。

当前补充提交仅修改本文和coverage状态说明，未改变上述受测代码；不为文案重复回归，也不循环改写“当前HEAD”。以下410＋130结果对应整合前`2014abd`及其开发阶段，不能充当新候选计数。历史8路37.61秒及全仓51.1566279/51.406秒来自旧main `ea0e230`的资源对照，不是本候选性能结果。

## 固定起点与授权

- 功能分支：`codex/gse-verification-under-30`。
- 起点：`9676c51f6bb7f4e8daa7295f08caed0b5a84acea` / tree `e27443401f723e21de7b8ee789e2957904d54bd5`；8路config SHA256 `c505ac85c11a4db730f955b54fcd36ab94db43decc253900476b7507800f6970`。
- 完整门禁一确认：`Sentinel_c68884e1dcf88191a1786b08b8313862`，沿同feature完成全部目标，不单独结束8路任务。
- 红证据：同机全仓外层4、GSE真实8时GSE37.61秒，尚不满足严格<30；全仓工具51.1566279秒、外层51.406秒为不退化参照。

## 本候选开发检查

2026-10-25云端使用已存在的Python环境，直接pytest普通选择（不是正式BAV守卫/Windows完整通过）：

| 状态 | 结果 |
|---|---|
| 修改前普通层 | 410 passed、130 subtests passed、118 deselected，5.44秒 |
| 共同报告/候选修改后 | 410 passed、130 subtests passed、118 deselected，5.63秒 |
| 共同夹具整合后 | 410 passed、130 subtests passed、118 deselected，5.81秒 |
| 首候选固定前 | 410 passed、130 subtests passed、118 deselected，6.55秒 |

此外：两报告生产者×单目标/5目标直接开发诊断，均一次native.json写入，实际JSON与返回报告相等且目标数正确。全部改动Python语法解析通过，diff无空白错误；原assert/self.assert/pytest.raises AST未改。AST结果不证明覆盖等价，触发链论证见`coverage-changes.md`。

云端运行产物仅在当前仓库`.local/tests/gse-phase2/`，最后检查约64KB，未复制数据中心/大工具或保留成功大产物。原CI历史`.local`和BAV备份未动。

## 必须保留为未完成

- 首候选已独立Astra双轴通过，正式全仓发现的回归已最小修正并单节点/单组真绿；**最新第6节增量的Astra与真实全仓仍未完成**，不得沿用任何旧结果冒称新候选通过。
- 父层三项诊断修复已随main3ee整合，其新回归已纳入上述416＋168普通结果；真实118与性能仍待官方完整全仓验收，不把8路旧基线当新main实测。
- 未写正式规格、未合并主干；完整目标未达标不关闭总任务。
