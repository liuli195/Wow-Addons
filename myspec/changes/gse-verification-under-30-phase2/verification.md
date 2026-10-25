# 阶段2开发证据（尚未完整验收）

## 最新整合代码证据

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

- 修改后的真实118、正式BAV普通守卫、43全仓、当前性能、独立Astra双轴审查：**未完成**，不得沿用8路旧结果冒称本候选通过。
- 父层三项诊断修复已随main3ee整合，其新回归已纳入上述416＋168普通结果；真实118与性能仍待官方完整全仓验收，不把8路旧基线当新main实测。
- 未写正式规格、未合并主干；完整目标未达标不关闭总任务。
