# 01：让训练按动态收敛结束

**What to build：** 训练取消搜索总时间和候选数硬上限，保持两轮无改善、空间耗尽及取消，安全恢复未完成路径。

**Blocked by：** None。

**Status：** ready-for-agent

- [x] 公开入口先红后绿证明超过600秒和候选上限仍按两轮结束。
- [x] 明确原身份与执行策略凭据，不重算成功成果，恢复失败/取消状态。
- [x] 普通搜索预算、部分发布和原完整性保护不回归。

## Comments
仅云端实现和定向验证，不执行真实训练，不提交Git。父线程负责实际失败任务恢复。

2026-10-20：独审确认这是执行停止策略调整，保留原condition/config/版本和旧执行证据，当前执行及state显式标记策略。训练搜索使用真正无限TaskRuntime，不改普通配置；仅训练取消总候选限制并保持完整两轮/真实空间耗尽。旧done截止任务在原行为、报告和赢家核验及反馈结算后恢复search；已收敛done只复测。

红灯：超过601秒、总候选限1原返回2，2失败/0.85秒（/tmp/dynamic-training-stop-red.log）；旧deadline/candidate_limit不能恢复，2失败2通过/8.52秒（/tmp/dynamic-training-resume-red.log）。绿灯：动态两组、四种恢复、普通搜索时间/候选上限共8通过/12.99秒（/tmp/dynamic-training-final.log）；原身份不变、旧executions不回写，完整成功0新评分，旧已结算选择确实存在且不再学习，已收敛恢复禁止调用optimize。

必要回归：runtime取消/单次30秒超时（无限搜索runtime仍生效）、部分失败发布及完整性拒绝、历史完成复用和缺identity拒绝，8通过/7子测试/8.36秒（/tmp/dynamic-training-regression.log）。非deferred反馈恢复在累计601秒下，训练/普通×sparse/旧模式4项通过/1.47秒（/tmp/dynamic-training-feedback.log），训练不冻结待评分选择、普通任务仍遵守原截止。均使用既有Linux真实锁适配与外部引擎边界，不证明Windows Job Object真实训练。正式规格留父线程统一交付，不越权修改。
