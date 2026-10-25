# 全仓测试与验证工具扩展门禁一草案

> 2026-10-25 恢复说明：以下2026-10-24测试与审查为遗失d3版本的历史记录，不能作为当前重做版本验收。当前以远端a311为基线重做；7个已上传blob已核Git哈希恢复，其余按原脚本/审查增量重新实施、重新测试并接受新独审。官方配置、Windows真实全集、60秒与默认对照仍未验收。

**状态：** 用户已允许执行六步方向；本文补齐完整门禁选择及精确配置。正式配置尚未 overwrite（覆盖），全仓测试实现尚未开始。

## 核心摘要

- 继续同一工作树 `/workspace/scratch/0af43d0efb8f/wow-addons-performance`、现有 `codex/formal-search-ga-default`；固定验证主干 `d08f1d6f540f3ced2496a59bdce6bd3badc7151a`。
- 当前生产及远端为 `cc1ec310cad5dad564a2bacaf65cab67f4a140c7`；原集中 test-only（仅测试）切片 `da02bda67436ef0a67af52474e3f7b99d51c9cae` 本地保留，已经独审但未本机验证、未远端同步。新范围取代其21节点安排，不丢既有成果。
- Flow Level 为 Full（完整）：全仓测试边界、工具链、配置、缓存与CI迁移，不满足单缺陷快速修复条件。GPT-6-A已独立只读审核领域和架构方向；代码最后仍由独立Reviewer审核。
- 推荐沿用原单票01并追加本扩展，不新建重复基础设施票；按互不冲突领域由子代理并行实施，公共fixture/配置/Git由实施协调者串行，全部完成后独立整票审查，再收窄审查修复差异。不是多代理同时改同文件。
- 目标入口仍是公开 `build-and-verify build/verify`，不另造调度器、缓存、guard（守卫）、假数据库或假Lua。生产GA、评分、正式并发、训练五场景四成果与后续新旧默认自然DPS对照不取消。
- 版本2草案为2构建＋43验证：17 ordinary、26 native，其中15是不可伪造的Lua静态工具检查。不是43个业务集成链，也不是把旧37项整组白名单。

## 当前全集和口径

静态盘点为GSE 28自动测试模块、287函数、理论369参数展开项，不含subtests（子测试），未实际collect（收集）。addons为14测试模块、97函数／98理论项，另技能布局15项；dev有3个直接脚本。技能manifest声明846构造cases／1613检查点，实际自测列43代表ID，不冒称运行846次。AzeriteUI继续既有第三方排除，不宣称全插件自有质量验收。

gear目前只有8个Node VM（脚本虚拟机）／伪DOM（页面对象）检查纳统一验证；21 Python、2浏览器、4research（研究）入口原为显式本机专项，旧37项通过不包含它们。本扩展将21 Python的纯规则移入自动普通组，3种仍支持引擎路由与1条浏览器完整主链移入聚焦真实组；4研究逐项拆可静态复用规则与历史／私有／在线复验，后者仍明示manual（手工验收）。

## 普通测试的真实边界

1. 解析、宏与CBOR、配置、canonical（规范行为身份）、遗传计划／繁殖／反馈／早停／评分选择、冠军凭据和版本、曲线采样、日志解析，直接驱动现有域函数或既有评价回调。使用dict、StringIO和明确局部Mock输入；不重写业务算法来生成期待，不复制SQL解释器或引擎。
2. 普通组退出自动installed_data_store、tmp_path、技能copytree、TaskStore物理构造、HTTP服务和子进程。真实环境fixture只由real标记的测试请求，复用量化项目既有按需隔离形态，不引入新框架。
3. 现有DuckDB `:memory:`仍是native，不能叫受保护普通测试。TaskStore的真实WAL／ATTACH／共享cache不改为内存后冒称等价；纯规则不构造物理Store，真实事务与重开恢复保留。只有本来适用的SQLite纯内存事务才复用工具允许的内存连接。
4. 必要小seam（接缝）仅限现有IO初始化／数据读取及将msvcrt导入延迟到现锁函数，使云端可导入纯函数；默认路径、SQL、锁、错误与生产行为不变。无需新Linux产品适配或环境修复。

## 领域 → 最小不可替代真实代表

| 领域 | 保留的真实边界 | 下沉普通与明确限制 |
| --- | --- | --- |
| 正式页面 | 既有browser双场真实SimC、两完整代、正常3×128、原生编译、copy/copyCollection/输入清空 | 版本、选优、冻结、故障分类矩阵不重复跑整段GA；真实烟测N1/no-op只改测试工作量，不改产品默认 |
| 导入／原生兼容 | imported loop／空点击的公开原生调用；original-baseline-disabled战斗一致oracle | 元数据与错误分类由固定报告测，不冒称C++回归 |
| C++按键机制 | castsequence、queue、precombat、cast/channel等每个不可替代机制留最轻判别代表；复用准备，保原生时刻和来源断言 | 同机制重复组合可下沉；异构机制不能统称一happy path。确有独有覆盖减少须逐项再确认 |
| GSE编译 | 上游六控制块集合实际Lua5.1编译及导出回读 | 结构／限制／非法输入纯数据；不造Lua解释器 |
| 可靠成果 | TaskStore＋Parquet批量发布、12份写后登记前故障、真实损坏组修复、CAS、安装技能连接读写 | 规则／收据／排序／版本下沉既有函数；内存结果不证明耐久性 |
| 进程与恢复 | 硬退出时已持久成功批＋live owned process，所有权清理和余批恢复；other-owner不受影响 | 超时／取消状态细分用受控时钟和过程替身；不弱化真实所有权代表 |
| 预训练 | 最低合法材料数、五场景、四成果、可靠发布与失败保旧 | 现链原生评分是替身，称真持久化，不称完整真实SimC训练；不为测试另造完整训练引擎链 |
| 日志／对照 | 一条战斗日志CLI文件读写闭环，快照来源绑定／可靠发布代表 | 伤害／宠物／主目标／分布／曲线比较纯数据；GA默认自然对照另行执行 |
| 插件Lua | 各自生产Lua＋伪WoW API的最轻事件／命令／受限值／保存表链；真实缺陷注入与恢复 | 内部已内存，不翻成Python自证；Lua子进程不在Python guard保护内，显式native |
| 素材／打包 | 一次真实素材build、包白名单／字节、损坏前置拒绝、独立部署目标、备份／WTF保护 | 像素／字节规则普通；共享只读基产物，损坏副本隔离，不能用mock代替数据安全 |
| 装备规划器 | 普通／神圣／织雾引擎各最轻真实调用；一条导入／计算／编辑／保存重载／比较／导出重导浏览器链，保删除取消／末项／持久化失败 | 路由、编辑、槽位、名称、合并、输入安全和其余浏览器组合用现fixture／VM；不是每职业每物品仍联调 |
| 工具／文档 | LuaLS／luacheck／TOC实际工具，注解生成＋语法判别，myspec官方CLI；构建2项分开报告 | 只读素材、docs、inventory和开发工具纯判断ordinary；不因工具未知启动名放开整领域 |

### 已披露的覆盖变化

- 取消“职业×物品×故障”重复整段搜索／计算交叉，保逻辑与每机制真实代表；不能声称全部旧组合仍做过真实联调。
- gear的75宝石、100附魔、471产品和523目录遍历各为不同口径。改按属性／插槽／来源／升级／唯一性／武器机制代表后，不再逐项证明未选条目的原生接受度。禁止从同源表造mock分数再自比。
- 两浏览器变一条完整链，其余职业／武器组合由现VM和路由验证承接，真实浏览器组合广度减少。历史修复前后引擎逐项bit-for-bit（逐字节）研究不再作为每次日常回归。
- wowtest正常生产对照已缓存每进程一次，不重复宣称提速。其生产缺陷注入如果减少独有反面检出，须列明并另确认，不能静默删除。
- 自动离线验收不替代真实WoW客户端、私人角色、完整插件集及受限值游戏验收。

## 精确配置草案与缓存前提

### 普通规则的明确迁移表（不整入口豁免）

以下均移入已登记的 `tests/dev/test_validation_units.py`／`verify.dev-unit`，原真实入口删除对应重复调用，只保最后一列。该组的paths／inputs包含实际media、addon、原图、dev及源测试依赖；不是只有tests/dev的空普通壳。

| 原位置 | 普通组保留的原判断 | 原native入口剩余边界 |
| --- | --- | --- |
| `test_build_wow_annotations.check_parser_rules` | 原Table数组真值、标量／引用、负数／十六进制、转义、类型／枚举／未知any、联合类型、可空／stride全部断言；直接`parse_documentation`与Generator输入字典 | 真实生成结果与磁盘比对、真实Lua批量语法及第二文件坏掉反例 |
| `test_checks.main`前置声明和源码字节判断 | setup／workflow／配置角色与入口约束、LF／CRLF补丁规范化字节及错误类型；用明确读取边界或repo只读文本 | 临时Git实际apply/reverse／来源身份；LuaLS／luacheck／TOC对成功与失败真实判别 |
| `test_media_mipmaps.test_white_material_preserves_alpha_and_rectangular_chain` | `_levels`的4×2→2×1→1×1值；BLP头／偏移／长度／alpha／尺寸／非白／截短错误，通过局部字节接缝传内存；不生成临时文件 | 一条真实写盘BLP及成品读取、真实非法源不得破坏旧成品 |
| 两个重复完整build素材代表的纯几何／命名判断 | 已有独立像素／尺寸／四源命名／矩形层级预期；已提交素材只读验证继续ordinary；不再每条先重复完整build | 一次实际15套构建、产物集合／写入成功，损坏副本单独隔离 |
| `package_crosshair_hud.expected_files/toc_files`的白名单计算 | 给定manifest／TOC文本的精确列表、排序、正式运行入口限制；直接现函数＋明确只读／字符串输入，不假造目录树 | 包体实际白名单与字节、链接拒绝、坏包写入前失败、独立部署／备份／WTF保护 |

十个HUD模块的生产Lua主体不翻译为Python；真实Lua／文件边界仍在 `verify.crosshairhud-tests`，纯字节／几何规则不再随该入口重复。既有wowtest投影／判定按同模块严格ordinary／real选择，正常生产报告不由同源期待伪造。

全部ID／命令／paths／inputs／realChecks／PR归属见同目录 `verification-config.candidate.json`；该文件不是正式配置，不手写 `.build-and-verify/config.json`。

- 原2个build保留，verify迁移43项（表列如下），验收要求为无空检查。普通／真实配对用同目录／模块的严格互补real标记，inventory须以实际收集证明全集无遗漏无重复，保留不许-k筛测试的门禁。
- 普通GSE与新gear纯组拟加入PR，CI只增可公开纯依赖，不准备GSE/gear原生引擎；真实GSE／gear仍pr:false。其他原PR归属保留。新增真实gear链计入本机60秒，不藏在预算外。
- 依赖固定副本放repo内 `.local/verify-deps/data-store`，实际两脚本、requirements逐文件进入inputs；测试复制源只读，不重新建生产中心。版本／实现记录在正式证据，不用缺失身份文件冒充可靠缓存。
- 不引入身份sidecar刷新框架。对ignored Ketho API目录，已从版本清单固定的Ketho/vscode-wow-api提交d0b5b51逐项读取非截断Git树，519个Annotations/Core实际文件逐条列入使用者inputs；GSE锁定上游Lua也用显式文件。Node在必要环境准备时把当前已安装的可用运行时冻结到repo内 `.local/verify-deps/node/node.exe`，普通Node命令和真实浏览器调用均使用此明确路径，实际二进制直接入inputs；不是安装另一版本，不改系统PATH。若输入缺失／运行时不可用必须失败，不以missing键缓存成功。
- 两份上游不是同一API目录：Ketho/vscode-wow-api d0b5b51的Annotations/Core固定519文件供LuaLS类型库；Gethe/wow-ui-source 4e3cbb8的Blizzard_APIDocumentationGenerated固定TOC列612 Lua，注解生成实际消费其中611正文（排除ConfigurationWarningsDocumentation.lua）。annotation-build显式输入611正文、TOC和实现中的排除规则；不拿519与612相减、不清理正确本机资料或更改版本。
- 具名插件LuaLS补生成注解、实际LuaLS二进制／主脚本及519个API文件；luacheck／TOC分别补实际luacheck／Lua二进制；技能真实组补Lua；checker／annotation补实际工具和API。所有pytest组补共享tests/conftest.py与pytest.ini的paths/inputs；Node／锁依赖及工具实现身份纳验证输入。构建身份核真，不重标签已有artifact（产物）。
- 2.7.1只用公开init --config --overwrite应用已审精确候选；PR Flow公开初始化写真实toolchain身份与受管workflow，不伪造哈希。当前旧de7871a CI pin必须更新，开发模式保留。
- Windows verify.yml的PR full是真验证；toolchain工作流干净fast可能skipped，不以该绿灯冒称全套。build配置1200秒在当前源码未传run调用，不称已有防挂保证，也不本票越权修工具。

## 并发资源与完整60秒

初始方案只有普通GSE内4；经2026-10-25本机完整真实组选参后，候选采用外层4，`verify.sim2gse-unit`与`verify.sim2gse-real`各内层xdist4／worksteal，其余无xdist，全部原checkParallel:true保留。两GSE组同时运行时为8 worker＋2 pytest控制端＋2其他check主进程＝12，不含BAV／guard自身；不是外4每组各4/8。

真实GSE测试每个worker最多2个单线程SimC，内4的GSE局部静态上界为8；若gear真实组同时运行，其既有LOCK串行原生调用另计最多1个。三路适配和browser不在同一gear check内并发。最多两个browser会话（GSE/gear各一），实际浏览器自身多进程、HTTP/Node服务和所有权helper另计；名义≤16不等于OS总进程≤16。20线程共享并发契约的受控回调代表保逻辑边界，不借此运行20个真实引擎。

本机真实内2一次60秒未结束，内4一次123 passed／24 subtests、pytest55.36秒／外层55.687秒，未改覆盖或预算；后者只证明单组完成，不证明全43项60秒或实测OS峰值。本机保存argv和WorkStealingScheduling日志已核，候选绑定同次实测的real内4／worksteal，正式配置待官方init应用后全组验收，不追加真实重复试验或内8/12组合。realChecks只定义守卫角色，2.7.1对native pytest同样支持pytestXdistWorkers；real保持候选第二项且checkParallel:true，与普通组同第一波启动，沿用既有顺序尽早运行长项。checkParallel:false会等所有parallel结束后串行，不采用该做法、不新增调度器。

60秒覆盖验证入口所需准备、官方调用至报告收尾，enforceLocalBudget=true；完整正式运行--full不读成功缓存。仅事先构建和环境安装另列真实耗时，不能把本次验证所需指纹刷新／夹具复制移到预算外。诊断、云端warning、缓存命中、未完成、skip均不能作正式绿灯。所有本机TEMP/TMP/TMPDIR和basetemp都在repo内短唯一路径，不能用系统临时目录越过用户限制。

## 票据、分域所有权与验证顺序

沿用票01的扩展验收：
1. 普通GSE／真实代表迁移；主实施者拥有 tests/sim2gse 及必要Python接缝。
2. 插件／dev／素材域由独立实施者拥有对应tests、纯dev入口与打包复用；不得写GSE或正式配置。
3. gear域由独立实施者拥有对应tests、现VM/浏览器链与必要server数据入口；不得写其他域。
4. 公共配置／toolchain／CI／inventory／顶层fixture和Git只由协调实施者串行整合；域代理报告需要的改动，不交叉改写。

先写最小公开2.7.1入口红证据，迁移相同入口转绿；云端能执行的纯计算与可移植部分先完成，准确标新工具版本和守卫证据。Windows Lua5.1、Edge、原生引擎与进程所有权必须在对应可用环境验证；本机连接状态由父协调在执行前核验，不因先前offline阻云实施，也不伪造本机结果。各域完成后固定整票独审，最后同HEAD官方无缓存全集≤60、PR检查、gear专项、游戏未验分别报告；之后继续原同角色同冻结输入的新旧完整默认自然对照。

## 已确认的实施边界

用户已明确确认以下整套选择，现已进入分域实施（进度与覆盖退让见`test-migration-evidence.md`）：沿用 `codex/formal-search-ga-default`；互不冲突领域子代理并行、共享文件/Git串行；全部完成后独立Reviewer整票审；应用附件43项精确配置时使用官方overwrite，保留备份。该确认不授权合并、主干推送、release或游戏部署。

## 43项公开入口

| ID | 角色 | 归属 | 命令 |
| --- | --- | --- | --- |
| verify.sim2gse-unit | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe -m pytest -q tests/sim2gse -m "not real" --strict-markers --dist=worksteal` |
| verify.sim2gse-real | native（真实） | 本机依赖 | `.venv\Scripts\python.exe -m pytest -q tests/sim2gse -m real --strict-markers --basetemp=.local/t/gse-r --dist=worksteal` |
| verify.luals | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luals` |
| verify.luacheck | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luacheck` |
| verify.toc | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py toc` |
| verify.sim2gse-probe-luals | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luals --source addons/Sim2GSEProbe` |
| verify.sim2gse-probe-luacheck | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luacheck --source addons/Sim2GSEProbe` |
| verify.sim2gse-probe-toc | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py toc --source addons/Sim2GSEProbe` |
| verify.crosshair-media | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe scripts/media/verify_crosshair_media.py` |
| verify.myseries-luals | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luals --source addons/MYUI` |
| verify.myseries-luacheck | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luacheck --source addons/MYUI` |
| verify.myseries-toc | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py toc --source addons/MYUI` |
| verify.myseries-series | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/MYUI/test_series.py` |
| verify.crosshairhud-luals | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luals --source addons/MYUI_CrosshairHUD` |
| verify.crosshairhud-luacheck | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luacheck --source addons/MYUI_CrosshairHUD` |
| verify.crosshairhud-toc | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py toc --source addons/MYUI_CrosshairHUD` |
| verify.crosshairhud-tests | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/MYUI_CrosshairHUD/test_logic.py tests/addons/MYUI_CrosshairHUD/test_core_readings.py tests/addons/MYUI_CrosshairHUD/test_unlock_contract.py tests/addons/MYUI_CrosshairHUD/test_config_color.py tests/addons/MYUI_CrosshairHUD/test_config_plan.py tests/addons/MYUI_CrosshairHUD/test_visibility.py tests/addons/MYUI_CrosshairHUD/test_media_placement.py tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py tests/addons/MYUI_CrosshairHUD/test_media_mipmaps.py tests/addons/MYUI_CrosshairHUD/test_release_package.py` |
| verify.wowaddontest-skill-unit | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe -m pytest -q tests/dev/test_wow_addon_test_skill.py -m "not real" --strict-markers` |
| verify.wowaddontest-skill-real | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/dev/test_wow_addon_test_skill.py -m real --strict-markers --basetemp=.local/t/w-s` |
| verify.wowaddontest-dk-unit | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py -m "not real" --strict-markers` |
| verify.wowaddontest-dk-real | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py -m real --strict-markers --basetemp=.local/t/w-d` |
| verify.sim2gse-probe-test | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/Sim2GSEProbe/test_probe.py` |
| verify.addon-probe-luals | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luals --source addons/AddonProbe` |
| verify.addon-probe-luacheck | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py luacheck --source addons/AddonProbe` |
| verify.addon-probe-toc | native（真实） | PR | `.venv\Scripts\python.exe scripts/dev/check.py toc --source addons/AddonProbe` |
| verify.addon-probe-test | native（真实） | PR | `.venv\Scripts\python.exe -m pytest -q tests/addons/AddonProbe/test_probe.py` |
| verify.assets | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe scripts/media/verify.py` |
| verify.docs | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe scripts/dev/check.py docs` |
| verify.checker-tests | native（真实） | PR | `.venv\Scripts\python.exe tests/dev/test_checks.py` |
| verify.annotation-build | native（真实） | PR | `.venv\Scripts\python.exe tests/dev/test_build_wow_annotations.py` |
| verify.test-inventory | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe tests/dev/test_inventory.py` |
| verify.gear-async | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-async.js` |
| verify.gear-build-names | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-build-names.js` |
| verify.gear-delete | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-delete.js` |
| verify.gear-empty | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-empty.js` |
| verify.gear-save-armor | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-save-armor.js` |
| verify.gear-save-as | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-save-as.js` |
| verify.gear-stat-filter | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-stat-filter.js` |
| verify.gear-summary | ordinary（普通守卫） | PR | `.local/verify-deps/node/node.exe tests/gear-planner/check-summary.js` |
| verify.myspec-main | native（真实） | PR | `myspec validate-main myspec/specs` |
| verify.dev-unit | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe -m pytest -q tests/dev/test_validation_units.py --strict-markers` |
| verify.gear-unit | ordinary（普通守卫） | PR | `.venv\Scripts\python.exe -m pytest -q tests/gear-planner -m "not real" --strict-markers` |
| verify.gear-real | native（真实） | 本机依赖 | `.venv\Scripts\python.exe -m pytest -q tests/gear-planner -m real --strict-markers --basetemp=.local/t/gear-r` |
