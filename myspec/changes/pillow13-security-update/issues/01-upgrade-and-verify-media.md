# 01：升级图像依赖并验证现有素材

**What to build:** 沿用 PR74 在当前主干组合上消除已知受影响图像依赖版本，证明少量受影响新生成图片仍满足现有素材意图，并交付可复核的现行 CI 结果。

**Blocked by:** None（单一纵向票据；完整门禁一已确认，按单票串行实施）

**Status:** ready-for-human（技术验收通过，等待第二门禁）

## 验收条件

- [x] 将最新 main 合入同一个 PR74 的现有分支，记录当时 main、更新后新 head、最终依赖身份与实际一行升级差异，不新建重复实现分支。
- [x] 使用同源现有 EUI 图，在旧、新 Pillow 下报告输出尺寸、像素和 alpha 差异；兼容不预设零像素差，有差异时解释其范围，必要时局部目视及最小修复后重验。
- [x] 保持现有轮廓、位置、透明意图；复用准星完整 BLP 缩小层、原始 alpha、格式与成品清单检查。
- [x] 最终现有公开构建入口及全部当前 PR 可执行检查通过；两个必需检查与 CodeQL 门禁均在准确新 head 上核对，不拿旧结果冒充新通过。
- [x] 原图缺失、输入异常、安装、构建或检查失败均明确记录并停止相依步骤，保留 PR 未合并；不降低断言或跳过守卫来变绿。
- [x] 不覆盖原图、不批量提交重生成成品、不增加长期工具、不改 GSE、引擎、8×2、60 秒或守卫。
- [x] 最终固定差异通过独立审查，证据与未验证项如实归档，提交完整第二门禁；未获确认不合并。

## 技术范围与公开测试接缝

- 依赖仅 `scripts/dev/requirements.txt` 的 Pillow 12.3.0→13.0.0；`scripts/dev/versions.json` 没有第二处 Pillow 锁。
- 最高层真实入口：`.github/workflows/verify.yml` → `build-and-verify build --project . --pr` → `build-and-verify verify --project . --pr --full`；`build.assets` 使用 `scripts/media/build_assets.py --output-root .local/build/assets`。局部函数对比只是定位缩放变化的补充，不替代该公开入口。
- 定向风险在 `build_assets.contain()` 的 RGBA `thumbnail()`。现有五张 PNG 对应六处输出：`03-Square-Fill`、`04-Circular-Fill`、`05-Hexagonal-Fill`、`06-Square-Border`、`08-Hexagonal-Border`；后者包括肖像 128×128 与普通 256×256，肖像派生遮罩顺带核对。用相同原图、相同 NumPy 和 Python 比较两版，仅隔离 Pillow。
- 现有 `scripts/media/verify.py` 读已提交 TGA，不读新构建目录；其绿灯不能代替新图对比。准星已有 `test_media_mipmaps.py` 的真实 15 套构建、独立 BLP 层级读取及 `test_validation_units.py` 普通规则可复用。
- 仅在出现实际退化时考虑最小修改 `scripts/media/build_assets.py` 及对应既有测试；先复现后修复，不预先改算法或新增兼容框架。没有行为失败时不虚构 TDD 红灯；受影响旧版本身份是已知不满足安全要求的前态。
- `assets/CrosshairHUDMedia/README.md` 已警示裸跑统一素材脚本会改写两个相对脚本过期的 EUI 成品。所有新输出必须位于本轮仓内 `.local/`，与两版对照输出区分；不得把既有脚本/成品差异归因于此次升级。

## 已核身份、准备与成本

- 固定需求基线：`2d607d0e36e4685576b7cae6da6f47c1d145b96c`，tree `4125350988ceea8d6d95f5b63226b181d57abba3`；同一云端工作树 `/workspace/scratch/0af43d0efb8f/wow-addons-pr76-ci`。
- 既有非 main 分支完整名 `dependabot/pip/scripts/dev/pip-bbf36862e1`，PR74 旧 head `686a2102f81f7bea1027dc9ce99444ac7dec4327`；旧 base `13e79983`，当前 main 多 91 个提交。旧 Windows 检查实际安装 Pillow13、构建并通过36项当时检查；当前配置有43项总检查、其中41项 PR 可执行，刷新后按当前配置全跑，不固定为旧36项。
- 完整门禁一后才把最新 main 合入现有 PR 分支，保留普通合并历史并接收新 head；先保留仅本轮需求文件，再由 root 串行处理同树分支/Git。采用正常快进可推的提交与引用更新，不重写机器人旧提交；不必评论机器人变基。不得在 main 安装或实施，不新建重复分支，不强推或绕过保护。
- 当前 canonical 的 PNG 均为 Git LFS 指针。EUI 原图目录7张声明总 3,873,559 字节，约4MB；门禁一后只取此素材目录或更窄所需对象并核对 OID（内容摘要），不恢复整个历史工作区。五张定向输入合计 2,940,503 字节。
- 可复用退役 `wow-addons-performance/.venv/bin/python` 的 Python3.12.14、Pillow12.3.0、NumPy2.4.4；只借现成依赖，不从退役源码开发，不复制虚拟环境、`.tools` 或数据中心。
- 新 Pillow wheel 仅隔离到 canonical 本轮 `.local/` 目录，复用旧 Python/NumPy；已观察 Windows wheel7.3MB，云端包实际大小需安装前核对。原图、隔离依赖和对照输出合计预计小于100MB；单操作预计小于15分钟。达到预计15分钟或516MB阈值前暂停申请，不拆分规避。
- 云端完成实现和可行图片比较，CI 沿用既有环境准备。只有确需已冻结 Windows 工具链的验证才复用用户本机，不因此迁移云端可做的工作。

## Comments

- 本票为一个可独立验收的安全依赖升级纵向切片，无其他票据阻塞；不是分拆实现、测试、CI三张横向票。
- 需求阶段只创建本 change 的 spec、票据与门禁文件；未安装、未下载 LFS、未评论机器人、未更新分支、未改代码、未执行新测试或合并。

实施授权：用户 Sentinel_f453868b9ef48191b57bc40c704f582b 已确认完整门禁一。

候选与正式收据见 ../verification.md；所有勾选仅指本票技术验收，不授权合并。
