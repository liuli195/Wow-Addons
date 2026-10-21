# 01：允许合格部分成果入选

**What to build：** 部分失败仍发布已完成成果，并保持失败记录和错误退出码。

**Blocked by：** None。

**Status：** ready-for-agent（实现及定向验证完成，待独立审查）

- [x] 一条成功一条预算失败时，成功可入选、失败不入选、命令仍返回2。
- [x] 全部失败不清空旧selected，其他scope不变，取消和存储/身份异常保持拒绝。
- [x] 公开入口红绿及必要回归通过，不增加筛选或存储机制。


## Comments
2026-10-20：公开run两路径一完成一search_deadline（搜索超时未收敛），原实现退出2且入选为空，红灯1失败/2.08秒（/tmp/partial-training-publish-red.log）。仅将未覆盖报错移至既有completed筛选和保存之后，取消及持久化异常原前置分支不动。新用例与全部失败保旧、发布失败恢复、缺原identity拒绝共4项通过/5.89秒（/tmp/partial-training-publish-green.log）。使用既有Linux真实文件锁适配器，不代表Windows真实训练验收。

安全补发沿现有公开run的--candidate-id限定已完成材料；同条件prepare确认无待训练路径后，run从原processed恢复入选，不调用模拟；新用例已验证限定已完成材料时不重算且失败记录不变。原完整批次失败不能被补发子操作退出0掩盖。当前其他训练运行时不热替换代码或争抢写锁，不新增发布CLI，也不手改底层文件。取消真实子进程仍按既有Windows用例验收。本次未运行真实训练、未提交、未改正式规格。

独审修复：混合成功和损坏 training_result 检查点的公开 run 原先误吞身份错误，红灯1失败、1通过/3.46秒（/tmp/partial-training-integrity-red.log）。完整性 ValueError 保留 failed 证据后交现有批次 fatal 通道，不发布；未收敛改用已有 BudgetExceeded。补发测试先清空本测试 scope 的 selected，证明限定成功材料实际零模拟重建而非仅重复运行。定向5项通过/8.37秒（/tmp/partial-training-integrity-green.log），覆盖部分发布、完整性失败保旧、预算失败保旧、发布失败恢复、缺原身份拒绝。600秒预算政策不在本补丁更改范围。

用户追加多失败要求：同一公开入口用例扩为1成功+1预算失败、1成功+2预算失败、1成功+1完整性失败。验证失败数量、selected仅completed且≤4、exit2、其他scope不变，以及实际缺失selected后零模拟补发。3项通过/5.89秒（/tmp/partial-training-multiple-failures.log）；仅补测试，不改产品。
