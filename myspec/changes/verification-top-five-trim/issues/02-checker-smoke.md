# 02：真实检查器反例与内存源码身份判断

**What to build:** 保留实际LuaLS和luacheck各一条有判别力错误输入，既有正式主检查继续提供正常仓库输入验证；源码身份比较和加载清单缺文件拒绝直接在现有普通测试中检查。

**Blocked by:** None（技术独立，可在完整Gate1确认后与另外两票并行；共享Git和最终验证由root串行）

**Status:** ready-for-agent

**Execution:** technically complete, delivery pending — 三票代码独审与文案增量已收口；b18/tree560088的Windows正式43项全过、0成功缓存跳过。8×2后续实验亦43项全过；用户已明确保留，官方配置已保存于42eb6c8并核对一致。正式规格应用、PR、合并及安全清理仍待完整第二门禁。

## 实施边界与所有权

- 仅编辑 tests/dev/test_checks.py、tests/dev/test_validation_units.py。
- 真实checker只保LuaLS错误接口名/参数及luacheck错误全局名反例；主LuaLS与其它正式检查不动。
- 现行build.verify_upstream的commit/tree匹配和拒绝通过已有内存测试接缝验证，不造新runner/模块。
- TOC缺文件拒绝迁入test_validation_units：直接调用生产check_toc，只mock glob/read_text/is_file等读取边界，核缺失文件的ValueError，并断言不会启动Lua；不删除此规则。
- 删除旧prototype临时Git仓、补丁往返/文件清单组合，以及本自测重复语法正反例；现有CRLF/补丁散列普通规则保留。

## Acceptance criteria

- [x] 两个真实检查器实际启动，返回失败且错误类型符合输入，不能仅用非零退出掩盖工具缺失。
- [x] 现行源码commit/tree身份匹配与错配规则在普通守卫下通过；不以模拟Git输出证明真实Git应用已测。
- [x] 准确披露TOC缺文件规则移内存（不再走真实CLI/文件链）、重复语法和旧prototype Git/写盘路径删除；正式主检查未被移除。
- [x] 只删除本票专属无消费者辅助代码；最终完整43项通过并报告checker组耗时。

## Comments

既有技术精简方案已经用户批准；完整Gate1已明确确认同树新分支、并行子代理、最后独审和本轮取舍。三个票据无产品或文件依赖；不得各自提交、推送或运行Windows重验证。必要普通定向检查云端完成，测试资源冲突时排队。

开发收据（2026-10-25）：`.local/verification-top-five/checker/ordinary-before-trim{.log,-summary.json}`确认新内存4项在删除真实重复路径前通过（0.17秒），守卫错误为空。`ordinary-after-trim{.log,-summary.json}`为完整dev普通24通过/1失败（0.27秒），失败是`test_committed_crosshair_names_sizes_and_source_pixels`读取当前浅clone的LFS指针而非PNG；不将退出1写成全过。两改动Python文件解析通过，守卫零违规不消除该环境缺口；本轮未填充大型工具或LFS资产，Windows冻结环境统一验证。保留LuaLS/luacheck两真实反例尚未在云端执行。

正式收据（2026-10-25）：b18/tree560088在官方BAV 2.7.1完整入口43项全部实际通过、0缓存跳过，17普通守卫完整，GSE388普通＋168子测试/4真实＋2子测试、gear两真实与checker均通过；原参数工具36.2841764秒、实际36.532秒。后续已授权8×2实验工具28.733572秒、实际28.975秒，同样43项全过且0缓存跳过。原云端环境失败记录保持原事实，不改写为通过；Windows正式结果和后续授权、清理、配置保存状态统一见[verification.md](../verification.md)。
