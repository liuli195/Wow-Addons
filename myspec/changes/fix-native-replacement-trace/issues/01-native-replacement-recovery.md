# 01: 恢复原生替换页面搜索

**What to build:** 页面真实搜索将原生队列真实替换归到派发原按钮，严格保持完成、派生、施法序列和反馈边界；任务终态不显示遗留运行中。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 真实替换通过派发一致性门禁，actual和issued签名分别保留
- [ ] 执行、中断、施法序列推进和反馈使用可信同一关系，派生不清pending
- [ ] 替换映射按战斗重置、冲突拒绝、重复终结不隐匿
- [ ] 页面父终态显示失败或未完成，保留成果和检查点
- [ ] 必要公开入口红绿回归、固定基线验证、Astra独立审查与原请求本机复验分别如实记录

## Comments
根因已由GPT-6 Astra读取固定上游eed909156d8eccbfca0f284cc271c080949d6a20独立确认。真实旧请求引擎退出0，315次dispatch对应311次execute，4次缺失均为共享队列实际转交的替换形态；原实现按指针误判native_derived。

实施检查：公开evaluate构造交换报告先以`/castsequence 原生成员轨迹与编译定义不一致`失败，改为完整issued签名后通过；真派生、重复终结及错误签名仍拒绝。页面HTTP任务GET先显示running，修复后failed/incomplete，检查点原字节保持。Linux专用导入适配诊断3项通过，耗时2.01秒；该证据不代表Windows锁或原生引擎验收。新增真实原生标准角色测试覆盖替换推进、trace开关不改战斗数据及原动作late feedback；Windows构建后执行，当前未运行。

源码锁核验：官方固定上游050旧产物hash吻合0028295dd0623d725b10bf837fb850e22358c3768d869a4ce60424c56ce28222；真实应用060后新产物hash为25a33fc4e08867355e7557022a783e7530159b216947b1ad80bd91bf6de73788。全部自有源码/补丁sha256核验通过。相同编译器身份对照证明baseline/original构建身份不变，controlled构建身份改变；没有改版本或伪造旧身份。

正式验证与交付恢复点：Windows构建、固定基线统一验证、真实原请求回归尚待本机执行。云端PR Flow只读diagnose缺PyYAML，未执行成功，不据此绕过交付门禁。正式规格未改，main未合并。
