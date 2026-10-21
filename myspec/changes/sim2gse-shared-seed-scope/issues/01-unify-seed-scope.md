# 01：统一起点训练和使用的三元范围

**What to build：** 同一三元范围保存、读取4个代表和1个训练冠军，完整凭据保留；未知旧记录不混用。

**Blocked by：** None（可开始）。

**Status：** ready-for-agent（实现完成，待独立审查及Windows验收）

- [x] 公开训练与查询按三元组分区，每组最多4个代表，完整处理记录不丢失。
- [x] 搜索从已验证原生英雄身份取得同一三元组，不按具体目标数隔离。
- [x] 训练冠军按来源凭据验真、当前重评分；角色历史冠军和模型不改。
- [x] 未知旧记录保留不猜，已验证同条件旧成果可由公开入口恢复。
- [x] 公开入口红绿及定向回归通过，记录平台和验证限制。

## Comments
2026-10-20：按用户最新三元身份、每组4+4+2实施；此前按condition拼接入选行与无界selected建议均已取消。固定基线9125206；不提交推送，不改正式规格。


云端定向红灯：公开run后按三元查询，旧CLI拒绝新三元参数，1失败/1.56秒（/tmp/shared-seed-red.log）。最终定向集合43通过、1排除/56.35秒（/tmp/shared-seed-final.log），另2项原规则包篡改及原复测英雄身份不符用例通过/1.75秒（/tmp/shared-seed-proof.log）。使用既有Linux真实文件锁适配器和DATA_STORE_TEST_SKILL隔离副本；没有替换生产并发锁。

已排除的test_foreground_search_does_not_wait_for_training_and_stops_it[foreground]依赖新Python子进程，子进程没有父进程Linux msvcrt适配，须Windows原样验证；未为此修改生产或增加兼容层。首次扩范围尝试中8个真实引擎/Windows Job Object用例也在云端不可运行，另一个非本票历史冠军管理缓存用例失败（缓存摘要不符），不冒称全仓通过。本票定向正式历史冠军4+4+2及冻结恢复用例通过。

未运行真实训练、未改正式规格、未提交推送；未创建归档或清理策略。旧数据仅沿原目录完整身份核验恢复当前条件，不做全库迁移。当前通过包括未知旧身份不混用；已验证旧批次恢复路径未单独增加完整迁移专项，需交付审查保持该限制。

最后小幅去重消除重复canonical调用并保留空prepare状态后，四范围发布/恢复、精确scope读取及来源验真5项再次通过/13.47秒（/tmp/shared-seed-last.log）。

审查前自检修复：新三元processed必须同样执行既有condition.txt存在但identity.json缺失的拒绝规则。新增公开run训练后移走identity再run的用例，修复前错误返回0并重建身份（1失败/1.97秒，/tmp/shared-seed-missing-identity-red.log）；复用同一缺身份保护后，新增及原三元发布/恢复、旧凭据拒绝共4项通过/12.41秒（/tmp/shared-seed-missing-identity-green.log）。没有新增策略或修复历史冠军管理逻辑。

关闭历史冠军管理测试的生产者不一致：source_scores构造200/300分后未同步既有native.json，真实缓存摘要校验正确拒绝。单例红灯2失败、2子测试通过/1.37秒（/tmp/shared-seed-cache-fixture-red.log）；仅测试夹具补1行同步最终报告后，该单例、4+4+2、公开恢复及训练冠军冻结恢复4项和3子测试通过/5.52秒（/tmp/shared-seed-cache-fixture-green.log）。生产校验及断言未修改；未运行基线对照，不宣称基线同样失败。

独审P2测试修正：预算与foreground（前台）取消用例的已有入选快照改为当前训练规则configuration_key对应的真实三元存储键，并在同键断言快照不变；发布失败后的空结果断言亦改为该三元键。scope取自既有测试规则配置，不猜英雄；旧键只读兼容专门用例保留。预算、发布失败恢复及两组三元正常/恢复共4项通过/14.25秒（/tmp/shared-seed-current-snapshot-green.log）。foreground真实子进程项仍留Windows原样验收，产品逻辑及断言强度未减。
