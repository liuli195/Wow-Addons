# 第03票验证记录

固定起点658ca9670a074d64ed06990daca9452bcbd6deaa，全局固定基线f554538993161cc045d19c4ed47d261f709f741b，功能分支codex/sim2gse-data-management。本机GPT6.1sol low串行实施；不启动本机架构或审查角色，独立审查由云端父线程承担。

## 字段证据与边界

读取仓库领域/任务约定、CONTEXT、相关sequence-evaluation/user-workflow规格及现有实现：engine.py203—250的玩家选择、raid_dps/dps、mean/count/fight_length；search.py1270—1325的实际TaskStore缓存request及结果；1690附近的search_result；task.py461—468的完整条件摘要。仅源代码取证，没有读取或登记真实历史文件。

保留实际缓存字段，不调用TaskStore构造器。旧行的条件hash不可逆，不能从摘要推测角色、版本或预算；可核验原始条件展开须匹配实际hash，缺少完整条件或保真度时保留事实但拒绝比较。这一拒绝条件已在技能说明公开。已有动作序列保留可追溯原件指针和实际条目数，未记录尝试轨迹或概率保持缺失。

## 公开CLI测试驱动开发

1. 首轮7项均未通过：5项失败、2项错误，根因公开extract命令未实现。实现后7项通过，14.908秒。
2. 补多人/上下文标记、快照来源重核及字节边界后11项中2项失败：上下文censored丢失、源变化仍允许发布快照。修复后11项通过，47.166秒。
3. 根据实际原生action_sequence字段补源指针测试，首先因字段缺失失败；实现指针及条目数，概率继续null。全部回归和统一验证结果在固定提交交付消息中记录。

覆盖幂等/业务last_used不刷新、失败/未完成/预算删失/样本/误差、多人团队指标、已绑定上下文和摘要不符拒绝、完整条件摘要核验、版本变化轴与种子/保真度/预算匹配或分层、缺失条件拒绝、不可变快照持久依赖、预览后源变化拒绝、源修改/NaN/错误结构拒绝、分页上限及1MiB输出/快照上限。72个合成事实演练字节上限，未读取真实数据。

查询/导出仅返回有界JSON，不创建磁盘scratch或文件；事实/快照的SQLite增长有保守准入。源JSON16MiB、事实16KiB、候选页1001条、输出和快照1MiB是实现安全边界，不是生产容量建议。正式容量、保留和频率仍未设置。

```text
Ran 41 tests in 74.027s
OK
```

共12项事实测试、11项第01票入口测试和18项生命周期测试。本票未改变产品或素材构建输入，沿用此前两个构建项目通过证据；提交后在干净工作树对固定全局基线运行统一快速验证，分别报告实际执行、有效缓存和full-not-run（未运行完整模式）。

未运行/尚未实施：实际游戏验收、生产启用和真实数据登记迁移；第04票一致性备份与归档恢复、第05票迁移删除、第06票维护。1000项增长盘点限制仍须在本次全框架验收前解决，读取租约与依赖传递必须在破坏性操作前落实。不把未完成能力移出授权范围。

## 首次云端审查返工

固定修复起点fd3d2439092dc4ba7a032de211627004214fff20。云端结论REWORK_REQUIRED（须修改），两轴分别记录，不计为已验收。

Spec（规格）轴3项：

- P1：实际search.py1270—1325缓存格式无新增条件展开/保真度字段，初版全部拒绝比较。新增按该实际格式的合成记录，不加enriched（增强）字段；同实际条件hash下已记录请求变化轴可以比较，未知展开/标签/预算值仍显式列明，不同hash拒绝。不变更生产入口。
- P2：读取task.py512—524/740—751的validation_incomplete，以及search.py1619—1625/1685—1698的预算终止和partial_round。保留原始搜索摘要，区分搜索删失、样本完整性及独立验证状态；比较不能宣称未完成或未知独立验证已经完整。
- P2：实际elapsed_seconds独立保留，不与native fight_length混用；查询、导出及快照均保留墙钟耗时、阶段、完成批次数与已记录停止/收敛摘要。

Standards（规范）轴2项：

- P2：包含字面点号键或空键的条件明确拒绝扁平比较，防止config.x.y覆盖嵌套config.x/y。
- P2：校验请求trace、种子、迭代数和时刻类型，JSON规范编码比较保留布尔/数字及嵌套列表/字典类型差别，false不等于0。

五项对应公开CLI测试首次全部失败（5.244秒），修复后全部通过（9.503秒）。增加自适应32/128/512请求预算、31/124/496有效样本与1/4/16批次兼容回归，未拉取新主干、重设基线或接入PR41搜索实现。短暂执行服务断连后只读调用恢复，未更换推送工具或安全配置。

```text
Ran 47 tests in 86.837s
OK
```

新事实使用schema2和版本化ID，已有schema1事实/快照不覆写；旧事实新增完整性字段缺失保持未知。对应新增测试为test_actual_production_rows_can_compare_known_axes_under_same_opaque_condition、test_search_termination_validation_and_elapsed_survive_export_and_snapshot、test_incomplete_search_comparison_does_not_claim_complete_validation、test_ambiguous_dot_keys_cannot_hide_condition_changes、test_request_types_and_nested_json_boolean_numeric_differences_are_preserved；另有自适应计数回归。固定提交后的统一验证、推送和增量审查结果在交付消息记录。

## 第二次增量审查的窄返工

固定起点36681d7897df8edf92c39d389b44f97fa976c38b。原五项云端已关闭，新增两项分别返工：Spec（规格）P2完整search_summary被永远判不完整；Standards（规范）P1全面拒绝点号使task.py420—425实际rules绝对文件路径不可用。先跑两项公开CLI，均失败（2.546秒），修复后连同原碰撞/未完成拒绝测试4项通过（10.677秒）。

完整汇总正向须具备completed、独立验证true、完整轮次false及已知正常停止原因，保留有效DPS/样本数；六类负向覆盖验证false/未知、validation_incomplete、deadline、轮次未知和partial_round true。没有为了正向用例放宽所有unknown。新提取schema3及版本化ID保留此前不可变事实，不原地覆盖。

实际规则结构测试含Windows空格绝对task.py/codec.lua/compatibility.json键，与task.py的_rule_hashes字段形状一致。键段采用无碰撞百分号转义，普通点分axis兼容；相同规则可以比较，规则摘要变化必须声明已编码axis或拒绝。原x.y字面键与嵌套x/y变化均测试，不能通过声明字面轴掩盖嵌套变化。全部技能及固定全局基线统一验证结果由修复交付消息记录。

```text
Ran 49 tests in 92.911s
OK
```
