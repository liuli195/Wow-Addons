# 全仓慢项精简：正式验收与8×2有限对照

## 当前结论与固定身份

三票代码已通过Windows官方完整验证；技术验收完成。用户已明确保留8×2，官方配置已保存于42eb6c8并核对一致；正式规格应用、PR和合并仍待完整第二门禁。本文由root提供并回读的本机原始收据整理，云端未自行启动本机验证。

- 优化前固定基线：`87bce49de64060b10a001d61d2a63f6b0cf7d300`，tree `6d693c873380c29e295335253f34cf3cbe4d1ba2`。
- 本轮已验远端/本机：`b18bdf8fcd98b1fe5d05c05594623b8640569a22`；云端同树提交`3f69afb97e90e40d2f9d692f7cd598fed926684c`。两者tree均为`560088cb6e5f3709bb62490da2272a31e4ce0408`。
- 远端主干仍为`3ee81b5048ed51c4238b40df9abb15d17569b5e0`；旧GSE功能分支仍87b，新功能分支为b18，尚未合并。
- 原正式配置SHA256为`c505ac85c11a4db730f955b54fcd36ab94db43decc253900476b7507800f6970`。8×2实验结束时曾由官方init恢复，字节与语义均一致、本机b18干净；之后用户明确要求保留，已在42eb6c8正式保存，身份见末节。两阶段不能混写。

## 正式全仓：保留原参数的代码精简收益

官方BAV 2.7.1执行`verify --project . --full --performance-report --execution-context local`，非诊断、60秒硬预算。`--full`不读取成功缓存跳过检查，但可写通过缓存；没有为此删除缓存或改产品缓存语义。

| 同环境正式完整结果 | 原87b | 精简后b18 |
| --- | ---: | ---: |
| 全仓实际执行并通过 | 43，0缓存跳过 | 43，0缓存跳过 |
| 工具总时（秒） | 39.5877264 | 36.2841764 |
| 实际墙钟（秒） | 39.858 | 36.532 |
| GSE真实（秒） | 17.48 | 17.14 |

b18保留外层4、GSE普通4/真实8及其它原参数，故本轮先独立确认代码精简收益。GSE388普通＋168子测试、4真实＋2子测试均通过；gear两真实通过，checker真实反例通过，17普通守卫完整。各组耗时：gear真实9.84秒、checker4.94秒、GSE普通5.91秒、主LuaLS5.48秒。原诊断Top5不作为严格同比数据。

证据：本机`.local/verification-top-five-full-a2f4c2ca5c4e4e0780319773c4f6df0c/`。成功后按来源allowlist清本轮可重建临时119783105字节，保留核心约33.4KB；未清历史或正式数据。该清理量不是持续采样峰值。

随后固定base87b的正式差异验证通过：17项有效缓存命中、0项实跑，7.401秒。它满足差异门禁的非空checked通过，不冒充另一次无缓存全仓实跑。

## 后续明确授权：8×2与按耗时降序启动

原Gate1不增加并发矩阵的范围，被用户随后对本次有限实验的明确指令覆盖，未自行扩大为其它矩阵：

- 用户`Sentinel_fb604c4444488191be1a0541f32a2225`：**“这样改成8×2，把测试耗时从高到低排列，依序启动”**。
- 用户`Sentinel_493e789ad8cc8191a92e16a79617b7ae`：**“执行吧”**。
- 实验完成后，用户`Sentinel_d158364fb6c48191acaf5879691317f4`：**“保留8×2的并发，然后正式收尾，进入第二门禁吧”**。据此已获采用授权，root已用当前官方init保存并核对候选42eb6c8，不再重复请求采用许可；这不代替尚未展示的完整第二门禁。

MySpec预览输入固定使用已提交b18的gate1.md、spec.md、design-notes.md，生成预览后不再修改这些绑定输入。其中原“不调并发/无新增矩阵”描述原始门禁范围；以上用户后续明确指令仅覆盖本次8×2/降序实验与保留，不回写原始输入冒充早已批准，也不授权扩大其它矩阵。新范围、执行与采用状态在本文件和Gate2完整展示。

实验仅改变验证编排配置：外层最多8；13个pytest检查全部使用2个worker；全部43项依据上一轮实测耗时稳定降序登记，平手保原顺序。普通5组的2worker守卫证据完整，其余真实8组均有xdist启动2worker证据；30个非pytest检查没有新增pytest字段。不修改调度器或关闭任何检查。5×2未运行，不假称已比较。

| 同一代码候选的正式完整结果 | 原参数 | 8×2＋耗时降序实验 |
| --- | ---: | ---: |
| 全仓实际执行并通过 | 43，0缓存跳过 | 43，0缓存跳过 |
| 工具总时（秒） | 36.2841764 | 28.733572 |
| 实际墙钟（秒） | 36.532 | 28.975 |
| GSE真实（秒） | 17.14 | 19.39 |
| gear真实（秒） | 9.84 | 11.92 |
| GSE普通（秒） | 5.91 | 9.42 |
| 主LuaLS（秒） | 5.48 | 7.56 |

实际全仓少7.557秒，约20.69%。单组因同轮并发竞争反而变慢，故收益应表述为本次整仓编排收益，而不是各组代码又提速；单次通过不保证任何负载下稳定同一秒数。实验HUD LuaLS为7.27秒。

登记前8项为GSE真实、gear真实、GSE普通、主LuaLS、wow-test技能真实、checker、HUD LuaLS、annotation。首批日志第4/5项的线程输出互换不能单独判为登记排序错误；完整候选ID/排序清单与配置哈希由root正式回读后归档。

证据：本机`.local/eight-by-two-a4a6d8c077904142b8e3da3ebb502b7c/`。清本轮可重建临时3789332字节，保留约1.04MB必要证据和两份官方配置备份。实验结束时官方init恢复原配置、本机b18干净；随后收到上述明确保留指令，当前已由官方init保存于42eb6c8并核对一致。不会把采用过程未返回的结果写成已保存，也不再自动追加5×2或其它矩阵。

## 独立审查身份

GPT-6 Astra双轴固定`87b...18ea771`/tree `1b6f964`：Standards轴0发现，Spec轴代码0阻断、1项覆盖披露待补；随后只审`18ea...3f69afb`/tree `560088`的8份文档增量，唯一披露已关闭，剩余0。云端3f69afb与远端/本机b18同tree，不把不同提交名误写成不同代码。8×2已做只读共享写风险核查，未发现确定冲突且正式43全绿。最终Astra窄审`b18...42eb`及官方预览无阻断：仅max8/13组worker2/顺序变化，其他字段、守卫和预算不变；规格仅1个Requirement变化、Scenario不变、无内部实现字段，CRLF差异哈希一致，3输入及正式规格未提前修改。

## 云端开发收据与覆盖取舍

三票Comments保留原始云端结果：gear8段普通守卫通过；checker新增4项通过，完整普通24通过/1个LFS指针导致的PNG读取失败；GSE定向83＋98子测试通过，完整普通373通过/15个缺冻结依赖失败。Windows已有冻结依赖的正式全仓已把保留测试完整跑绿；不回写云端失败为通过。

保留四条GSE核心真实和主LuaLS。装备退出无断言匹配/特效旁路真实组合；checker移规则入内存并删重复语法/旧prototype Git写盘链；GSE减少30格退役设置交叉和明确列出的诊断对称组合。三票技术完成不代表主动删减风险全部被其它测试等价承接。原118真实的4保留/2迁移/112删除及额外1个无消费者普通自测删除仍需在最终交付说明。

## 交付前待收口

官方MySpec完整预览见spec-preview.md，候选43ID与配置哈希见下节；最终配置/规格窄审无阻断。8×2采用已单独明确授权且正式保存核对完成；root统一同步纯文档并回读完整预览链接后展示第二门禁。未获完整第二门禁确认，不应用正式规格、不合并或清理工作树。现有正式规格未提前修改。本文件为结果记录，不能充当用户的交付授权。

## 已正式保存的8×2配置身份

用户明确保留指令后，本机官方BAV 2.7.1 init已成功采用并正常推送：`42eb6c87a075139a7a009e212c41f3fad6ab3fc3`，tree `363d0949f9992b0945e49fa998556e0e2640f681`，相对b18仅配置变化。云端正常快进后只读回核同身份；配置497502字节，SHA256 `1dda48eb485ac51952d37b77a44b098c9940bce452feef2f2176f3c6fd123a1e`；本机规范化JSON指纹 `494c6468192fea355a2381e03b87f8545a4aa358a4a8d78c2377ae10c7735b22`。与已测候选一致，外层8/全部13pytest各2worker、60秒预算不变，不需重做同候选矩阵。

下表从已保存配置直接读出，非重新估计耗时；原实验已核其稳定降序依据。`—`表示非pytest检查未新增pytest worker字段。

| 登记顺序 | 检查ID | pytest worker |
| --- | --- | ---: |
| 1 | `verify.sim2gse-real` | 2 |
| 2 | `verify.gear-real` | 2 |
| 3 | `verify.sim2gse-unit` | 2 |
| 4 | `verify.luals` | — |
| 5 | `verify.wowaddontest-skill-real` | 2 |
| 6 | `verify.checker-tests` | — |
| 7 | `verify.crosshairhud-luals` | — |
| 8 | `verify.annotation-build` | — |
| 9 | `verify.sim2gse-probe-luals` | — |
| 10 | `verify.myseries-luals` | — |
| 11 | `verify.crosshairhud-tests` | 2 |
| 12 | `verify.addon-probe-luals` | — |
| 13 | `verify.wowaddontest-dk-real` | 2 |
| 14 | `verify.docs` | — |
| 15 | `verify.dev-unit` | 2 |
| 16 | `verify.test-inventory` | — |
| 17 | `verify.luacheck` | — |
| 18 | `verify.assets` | — |
| 19 | `verify.crosshair-media` | — |
| 20 | `verify.toc` | — |
| 21 | `verify.gear-unit` | 2 |
| 22 | `verify.addon-probe-test` | 2 |
| 23 | `verify.wowaddontest-dk-unit` | 2 |
| 24 | `verify.gear-async` | — |
| 25 | `verify.gear-summary` | — |
| 26 | `verify.gear-build-names` | — |
| 27 | `verify.gear-delete` | — |
| 28 | `verify.gear-save-armor` | — |
| 29 | `verify.gear-save-as` | — |
| 30 | `verify.gear-empty` | — |
| 31 | `verify.gear-stat-filter` | — |
| 32 | `verify.wowaddontest-skill-unit` | 2 |
| 33 | `verify.myspec-main` | — |
| 34 | `verify.myseries-series` | 2 |
| 35 | `verify.sim2gse-probe-test` | 2 |
| 36 | `verify.myseries-luacheck` | — |
| 37 | `verify.crosshairhud-luacheck` | — |
| 38 | `verify.crosshairhud-toc` | — |
| 39 | `verify.addon-probe-luacheck` | — |
| 40 | `verify.myseries-toc` | — |
| 41 | `verify.sim2gse-probe-luacheck` | — |
| 42 | `verify.addon-probe-toc` | — |
| 43 | `verify.sim2gse-probe-toc` | — |
