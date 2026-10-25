# 退役实施验证（进行中）

固定基线：`6b5861fc548ce9753a03f1bc78453ef5cad01faf`。独立分支`codex/retire-legacy-search`；无正式数据、AB目录或主工作树修改。

## 已完成

- 公开run/resume/dual的11退役键先取得红灯（candidate_limit原先落入普通范围错误而非退役拒绝），实现后33项通过；随后加入训练入口、TOML与HTTP前置拒绝，最小组合46项及22个子例通过，0.51秒。
- 旧双场读取的`recoverable=false`先取得红灯（原为true），实现后通过；原预算与结果仍可读取。
- 冻结正常/训练场景的修饰键Reset合法性、旧v1 pending补保存/补发布禁止写入4项通过，0.27秒。
- 旧Git源码提取执行benchmark及其专用测试删除；共用两次PermissionError重试测试原义移入`test_runtime.py`。
- 普通层：`PYTHONDONTWRITEBYTECODE=1 <既有venv>/bin/python -m pytest tests/sim2gse -m 'not real' -p no:cacheprovider -q`，最终本轮403通过、118个real未执行、130个子例通过，6.32秒。最初轻量worktree没有固定`.tools`导致15个只读依赖缺失失败，未冒称产品回归；仅软链接复用原树固定工具后通过，未复制工具或执行构建。
- `git diff --check`通过；旧专用符号及工具执行引用反查完成。历史11键仅保留明确拒绝清单、隔离legacy解码、旧报告读取和原始兼容证明测试；runtime共享时限与单次/导入安全上限保持。
- 56份历史说明原位加退役提示（清单`history-annotations.txt`）；原文数字、路径、结论未删。正式GA对照阶段补“已结束/仅历史”提示。

## 未完成，不作通过

- 本机最新MySpec状态流程、完整受控预览、最终确认与原子应用。`spec-proposals`仅目标文本提案；主规格未改。云端实际解析CLI2.3.0与当前技能不匹配，未用旧工具绕流程。
- 当前最终提交的统一BAV及必要本机真实边界验收；此前主线43通过不代替本变更验收。没有启动新AB、重训或引擎构建。

新增工作树及文档当前约20MB，复用既有venv/固定tools；整体90–150分钟投入已授权，未扩大到正式数据清理或主干合并。

## 首轮独审与返工

固定`6b5861f...d5a48bb`双轴只读审查：Standards无阻塞硬违规，提出postcheck正向/计划篡改覆盖与配置投影命名；Spec发现P1归档读取布局、P2旧恢复拒绝前可写两项阻塞。

- P1：归档实际在`state_archive`，不是`state_fields`。用生产TaskStore写真实SQLite内存格式再只读查询的回归先失败，随后补按ordinal读取归档；不实例化写存储、不加载无关归档。
- P2：公共恢复先只读预检原版本、旧配置与v1意图，再允许foreground/曲线/锁和写TaskStore；锁内重读及实例状态复核保留。公开run(resume=True)同样前置，旧双场恢复/已退出任务取消均不再改写旧状态，读取失去执行者的旧记录不再探测写锁。当前GA仍保持原同版本恢复。旧版本与旧pending负例先在foreground/曲线路径失败，修复后只出现SELECT；旧双场负例验证引擎、写锁和保存均未触达。
- 复用现有`memory_ga`与真实SQLite backup补训练五场景→四条代表→页面正式GA重新评分的成功链和冻结计划篡改拒绝；只替换现有原生/文件/中心读取边界，不新跑真实训练。postcheck全8项通过，0.98秒。投影名称改为`comparable_config`，无新抽象。
- 首次扩展普通回归暴露原输入篡改测试未提供新增只读检查点输入，按明确IO边界补当前版本清单，保原输入哈希及禁止写TaskStore断言。最终普通410项通过、118个real未运行、130个子例通过，6.58秒；`git diff --check`通过。

主线`b393dbd`局部mock退栈修复和`f5ae3b2`最终验收文档均已正常cherry-pick纳入；退役测试移除旧参数的改动保留，没有退回全局mock或旧参数。

## 功能分支同步授权

第一次GitHub tree上传被安全审核拒绝，未创建远端树/分支，未改通道。用户随后对准确仓库`liuli195/Wow-Addons`、分支`codex/retire-legacy-search`、本轮源码/测试/文档/规格提案约102文件1.7MB及后续必要修正再次明确确认（`Sentinel_6add6c6fb50c81919e4fddf4ef177d0b`，对应请求`Sentinel_8e184d15e4ec81919b452190cb50cbcf`）。仅修后复审通过版本重试原上传操作；不上传正式数据/凭据，不main、不force、不发布。远端同步成功须以真实回读为准。

## 修后固定双轴复审

固定`d5a48bb...2cd6640`已通过Standards/Spec两轴只读复审；P1/P2及两项建议全部关闭，无新增阻塞。保留原源码/引擎身份保护，未引入第二套恢复或存储框架。

只读恢复普通测试证明连接使用`mode=ro`、只发SELECT且不调用TaskStore/foreground/曲线；它使用SQLite内存边界，不能替代真实磁盘WAL/SHM行为验收。相应函数注释仅陈述只读连接，不扩大证据结论。本机真实存储与最终统一验收仍待执行。
