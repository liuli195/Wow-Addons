# 01：旧默认与两个独立探索开关

Status: in-progress（实现、独立审查及定向验证完成；待交付门禁与 CI）
Blocked by: None

## What to build

从同一公开配置驱动正式搜索、双场入口及预训练，默认旧起点旧搜索，两个独立探索开关支持四组合，不回退已有成果和可靠性修复。

## Acceptance criteria

- [x] 默认OFF行为确为旧起点及旧候选生成，而非冷选择器。
- [x] 四组合、配置/显式参数优先级和非法值行为一致。
- [x] 规则生成与共享身份上下文解耦，关闭起点仍可匹配历史训练成果与冠军。
- [x] 起点开关不改变正式首爆设置，选择器关闭不加载/学习/写模型或进行专用诊断。
- [x] 保留旧算法必要观察、评分、去重、晋级、取消恢复和保存修复。
- [x] 未安装选择器可选依赖时默认模式可用，开启时明确缺依赖。
- [x] 新任务冻结模式；旧不兼容任务拒绝静默换算法，成果仍可读，不清空历史冠军。
- [x] 预训练同配置，起点训练正常且OFF不更新模型；现有10×2本机配置不改。

## Comments

2026-10-21：方案获用户确认，仅准备需求，未开始产品实现。


2026-10-21：用户确认开发门禁后实施，固定基线 65b22c60ea6afe49c769ae3808f859c0644605eb。
- 公开 run_task 红绿：开关非法值原报“未知搜索配置”、原入口不加载 [search]、默认仍调用 generate、扩展仍导入 selector；逐项最小实现后通过。
- 云端仅测试进程采用 POSIX fcntl.lockf 真实锁适配，原 conftest 仍复制测试数据中心并使用 tmp DATA_ROOT。该证据不是 Windows 锁或 JobObject 验证。
- 公开四组合、默认无选择器导入、CLI 显式关闭覆盖 TOML 开启、旧未冻结任务可读但拒绝续跑、新起点仅替换均匀槽等通过。
- 训练 CLI 默认禁止 generate/selector 仍完整训练并保存原材料；历史 v1 训练凭据和当前 v2 凭据均经双场重新评分，原三份复测校验保留。
- 固定基线同样失败的既有用例单独记录，不为断言绕过存储：on-demand mismatch（不一致诊断）读取缺 records；capture publication recovery（诊断发布恢复）拒绝规则配置。基线以原测试和原模块 Git 对象最小重现，未修改产品以迎合。
- 正式统一验证与真实 Windows 验证由主代理在提交/后续票据完成后执行；本票不宣称全仓通过。

实施交接（未提交，待三票统一审查）：
- 新公开入口矩阵 `test_search_closeout.py`：12 passed，4.52 秒。CLI 配置覆盖使用外部评分边界取消，避免为参数测试跑完整搜索。
- 规则起点全文件：35 passed，5.40 秒。旧测试已显式开启能力，首爆断言改为不变正式计划。
- 已有训练冠军全文件：13 passed；新增原 v1 凭据矩阵及训练 ON/OFF 联合小组：7 passed。
- 训练动态恢复/三条件/部分发布选集：8 passed，23.43 秒；材料规则开关双值及默认缺模型依赖选集：3 passed，3.68 秒。
- 相关搜索业务选集：10 passed，另一个耗尽轮数断言失败已在固定基线同样复现（2 != 1）。
- 诊断回归：58 passed；排除的既有 7 例加末尾 2 例均留失败，不修改断言。对应基线重现类别为：mismatch 缺 records（三参数）；capture publication 规则变化；budget end 30 秒收尾次数；shared publish 未抛 SystemExit；partial freeze 缺 intents；recovery time 评分次数；mixed state 重复观察行。
- 整组搜索中的 Windows `_kernel32`、WinDLL、JobObject 不可执行，不能认作本票通过或平台已适配。POSIX lockf 不模拟同进程多线程 Windows 区域锁，前台训练互斥测试需真实 Windows。
- `compileall`、`git diff --check` 通过；正式规格 tracked/untracked 差异均为空。未运行干净提交要求的最终统一 verify，由主代理统一完成。

提交前窄检查补充：
- 原 selector ON 任务显式独立诊断确实误入依赖检查。新增公开 resume_task 禁止 selector/numpy/coba 导入红测试后，实际 selector_enabled 排除独立诊断，并将特征导入移至 guard 后；诊断不再编码 selection_context。
- 共享 context 原新增完整 rule_snapshot 重复序列化，现不保存该字段；运行时浅组装已冻结 state.rule_snapshot。四开关组合通过 SQLite 持久化字段断言红绿，不增加引用/迁移框架。旧生成报告继续兼容读取，原本 state 与生成报告的重复未扩大改造。

2026-10-21 最终证据：云端联合 58 项与 13 子测试通过（41.03 秒）；Windows 必要验证及其失败项的限定复测已通过。原 HTTP 失败为执行权限限制，正常审批后 2 项与 3 子测试通过；前台抢占测试显式固定自身 2 worker 后单例通过（2.876 秒），未修改产品、原断言、本机 10×2 或正式数据。详见 report.md。尚未完成远端 CI 与合并，历史阶段“未提交”等描述不代表当前状态。
