# 01: 当前消费读取使用限定身份

**What to build:** 页面、双场任务与当前训练历史入口读取已有结果时，只访问显式需要的逻辑表、已知记录及字段；旧接口在计算前明确拒绝，存储故障保持可识别。

**Blocked by:** 公共限定查询契约实现及 API（应用接口）版本 2 的隔离源可供验证

**Status:** review-passed

- [x] 所有生产及现有检查的通用查询明确非空逻辑表范围，不隐式全中心注册
- [x] 摘要不读取完整报告，详情按已知批次组批读并过滤组内无关行，候选使用已知逻辑键批读
- [x] 单键或已知组缺失不会无条件退回全表查询；无关坏表不会阻止已知记录点读
- [x] 双场父冻结爆发身份传至子任务且保持当前定义变化拒绝；首次发现仅查询爆发表
- [x] 现有报告位置清单复用增量，首次完整性核验、锁和原子发布保持
- [x] 存储故障在现有页面接口保留原因或类型并得到正确中文提示
- [x] 基准快照通过既有绑定接口使用原共享中心，启动检查明确公共能力要求
- [x] 最小真实隔离样本保留公开入口红绿证据，不启动真实训练或全库查询

## Comments

门禁一已确认，固定基线 a687dbb。消费仓 01→独立审查→02，由同一实施者串行负责；公共技能仓可并行，隔离 API 可用是集成绿灯前置。

## 验证证据

证据目录：`.local/tests/data-center-scoped-consumers/`（本地运行证据，未上传）。

- `01-api-gate-red.log` → `01-api-gate-green.log`：旧接口版本未拒绝 → 1 PASS / 0.17 秒
- `01-task-locators-red.log` → `01-task-locators-green.log`：已知详情读到无关坏分片 → 1 PASS / 0.96 秒
- `01-ui-storage-red.log` → `01-ui-storage-green.log`：真实 HTTP（网页接口）将包装存储错误返回 404 → 1 PASS / 0.31 秒且可行动存储错误
- `01-benchmark-binding-red.log` → `01-benchmark-binding-green.log`：源码快照未绑定原项目 → 1 PASS / 0.68 秒
- `01-burst-freeze-red.log` → `01-burst-freeze-green.log`：子任务第三次通用查询导致失败 → 1 PASS / 0.86 秒；父仅两次爆发表发现、子点读，变化定义仍拒绝
- `01-core-smoke.log`：上述公开接缝及既有独立连接入口 7 PASS / 2.95 秒
- `01-projection-memory-smoke.log`：真实旧单条/三条组多键投影过滤、缺键不扩大、摘要三列/完整报告保持及既有准备缓存回归 7 PASS / 3.43 秒
- `01-current-regression.log`：既有基准纯逻辑及新快照绑定、当前结果读写与冻结身份回归 22 PASS / 2.52 秒

独立审查待固定提交。统一构建验证与 Windows（操作系统）正式验收另列实际结果；上述定向通过不代表全仓、真实引擎、游戏或已发布安装验收。票 02 尚未开始。

### 独立审查返工（仍属票 01）

固定初版 32a8403381ca38f61cedd5b8955b99f3f646e97f 的独立审查确认两个 P2（中优先级）问题，父级要求本票最小修复：

1. 新位置清单消费边界的锁文件或清单打开失败未转为 DataReadError（数据读取错误），真实网页返回 404。仅在 report_locations 捕获 OSError（文件系统错误）并保留原因；任务缺少检查点定位、真实组与 HTTP 样本在锁/清单打开接缝分别注入权限错误，`01-locator-permission-red.log` 2 FAIL → `01-locator-permission-green.log` 2 PASS / 0.68 秒；原因链可见。
2. 旧 API 在页面同步双场启动时断开连接，后台启动误报引擎错误。版本及缺能力复用既有 DataReadError，保留“同步 API 版本 2 后重启”具体提示；首查所需爆发表的数据库错误也在适配器查询边界保留原因，参数校验错误不改类别。`01-api-http-red.log` 3 FAIL → `01-api-http-green.log` 3 PASS / 0.64 秒，覆盖双场/普通任务旧 API 及真实坏定义分片，均未启动原生进程。不扩大 HTTP（网页接口）的通用捕获或增加重试、锁、状态机。

`01-review-fix-smoke.log`：上述当前接缝最终 14 PASS / 4.80 秒。

统一受管入口 `build-and-verify verify --project <本工作树> --pr --base a687dbb1c0ff288578ad06c07409a1c85d75133f --execution-context cloud` 实际失败；8 个选中检查都因现配置 Windows 解释器 `.venv\Scripts\python.exe` 在 Linux（操作系统）无法启动，Sim2GSE 因既有 `pr:false` 正常排除。证据 `01-bav-cloud-pr.log`；未修改配置或工具规避，也不记为正式通过。直接使用既有云 Python 运行 docs（文档）356 份检查和 test-inventory（测试入口登记）均通过，仅作云可移植诊断。正式 Windows、60 秒统一门禁与当前已发布安装版接入仍待最终跨仓候选验证。


### 票 01 独立复审结论

2026-10-11：GPT-6 Astra（独立审查模型）只读复审消费固定提交 6b4df5f4f920df9fd9196a5c071f04f3fb29d274，公共固定提交 e0256d611c97363b4d779748bb7b4e73e562600c。两个原 P2（中优先级）问题已闭合，未发现可操作阻断，父级明确转交通过后进入票 02。

实施者的最终定向检查为 14 PASS / 4.80 秒；独审实际重跑为 12 PASS，另两项因只读审查环境的 codec（编解码器）目录写入限制失败，不能将其表述为 14 项独立通过。该票代码审查通过不代表正式统一验收完成：受管云端入口的八项检查仍因 Windows（视窗系统）解释器不可启动而失败；Windows、正式安装版接入与全仓 60 秒门禁仍待验证。
