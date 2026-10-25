# 正式规格完整预览（仅预览，未应用）

官方MySpec 2.7.1会话：`b10835350fbe47a6837b627213e09317`，状态`READY_TO_APPLY / PREVIEW_ONLY`，未决冲突0。仅修改`repository-validation`中的1个Requirement，原2个Scenario不变；目标能力总计3个Requirements、6个Scenarios。其它正式规格不变。

以下差异完整复制自本机官方预览，不是手写正式规格。原官方CRLF差异SHA256：`ccf9ec6b410c737dd1d059bbb9f6145d93a5bc4d84ece237930ad8d5509fad2a`；本页内LF原文1709字节，SHA256：`ac839c9a00112376ef8ab2f2344837a897354da59e2b5d354e192b32b3a94b7b`。已逐字核验：仅LF转换为CRLF即与官方原diff哈希一致。预览目标spec文件SHA256：`6d24efad5aa122c677caba2bf7577c6f6a0b48aad78fbd3198c15f66e0e09463`。

官方会话指纹：主规格`sha256:10dbbd0c25a682ede373183d032202e467879b81aee8f9c9c6781cd64b643238`；输入`sha256:4656dce5e91629617e6a074f7f57317fe1155ec07abc9d1c3dbc5c9bd3276490`；预览`sha256:15ef09378c827f818a2ab50e6acca37716e93e3a9c698adbf4cd951e8cd1c04f`。应用前必须由官方会话重核。输入绑定已提交b18版本gate1.md、spec.md、design-notes.md；后续8×2用户授权和结果另外记录在verification.md，不修改这三份绑定输入。完整第二门禁确认前不应用。

```diff
--- a/repository-validation/spec.md
+++ b/repository-validation/spec.md
@@ -8,7 +8,7 @@
 
 ### Requirement: Local full verification reports the sixty-second budget
 
-系统 MUST 在本机完整验证中执行全部已登记检查及自动发现的 Sim2GSE 测试，并报告总耗时、60 秒预算和是否超出预算；性能预算不得通过跳过仍登记的必要检查、降低生产默认计算预算或把失败改写成通过达成；经用户明确批准的ROI测试重构可删除重复场景、合并等价逻辑、缩减低收益理论规模并将纯逻辑移到内存，必须保留最少且有判别力的实际数据损坏/锁/恢复边界，准确说明覆盖变化，不伪称原规模集成已验证。
+系统 MUST 在本机完整验证中执行全部已登记检查及自动发现的角色按键序列优化器测试，并报告总耗时、60 秒预算和是否超出预算；性能预算不得通过跳过仍登记的必要检查、降低生产默认计算预算或把失败改写成通过达成。经用户对具体范围与覆盖损失明确确认，可精简重复或低收益边缘测试。日常验证保留已确认的核心真实冒烟，实际执行其所声明的依赖；保留检查必须能判别其承诺的成功、失败或隔离结果。每次精简公开保留入口、删除风险及未验证范围，不把内存规则通过冒充物理或原生验证；普通检查不得进行其被禁止的外部操作，不得弱化生产身份核验或已确认保留的进程所有权隔离等核心保护，不得跳过剩余登记项或将失败写成通过。超出已确认删减范围须重新明确确认。
 
 #### Scenario: Local full verification meets the budget
 
```
