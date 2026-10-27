# 现有原生报告字段最小只读核验

## 范围与身份
读取云端既有4,962,559字节冻结输入中的真实report；没有新模拟、事件采集或整库扫描。摘要与原文件SHA见evidence.json。原provenance记录真实原生报告来源及哈希。报告为1210-01/2.0.0，单目标、请求2、有效样本1、战斗180秒；不能冒充已验证全部角色/多目标/批均值场景。
当前compatibility/lock.json与只读上游源码HEAD均为eed909156d8eccbfca0f284cc271c080949d6a20。另只读一个已存在San'layn报告确认相同字段类别，不拿旧自有采集扩展当新依赖。

## 已证明
- stats.num_executes.mean存在；例outbreak为25，180秒下为8.3333次/分钟。上游action/action.cpp:1927–1928在execute路径调用stats.add_execute；action/stats.cpp:185–195累加执行次数。控制器dispatch_failed提前返回(native/src/controller.cpp:673–700)。因此不是失败按键尝试数；但不保证伤害命中、GCD事件数、完整引导成功或所有动作都经过同一统计路径。
- stats有sim2gse_actor_index/name/owner_type及动作id，必须结合当前可按动作/替换形态映射，不能遍历伤害树后全部相加。自动攻击等特殊动作需明确是否进入受支持频率名单，不补造一个0。
- 玩家报告buffs与buffs_constant包含uptime百分数。runic_corruption=45%，sudden_doom约48.5656%。上游buff/buff.cpp:1878明确100×持续时间/战斗时间。
- JSON report_json.cpp:157–161只有来源不同于受益者时写source/target；缺source不能简单等同玩家自身。
- report_helper.cpp:531–555会合并玩家、宠物和全局buff列表；实际dark_transformation/death_and_decay各有两个同名不同spell条目，按名字直接合并错误。
- report_json.cpp:169–174省略零uptime；:191–210及report_helper.cpp:30–43省略未触发/quiet对象。必须读取动态和常驻两组，已证明注册、适用、非quiet及明确身份的对象省略才可按已知序列化规则解释为可靠零；未知对象/未知schema/歧义不套用此规则。

## 未证明与最小建议
- DoT只有total_tick_time.mean等统计；action/stats.cpp:201–205累加每次tick时长并丢弃target参数。这不是已证明的逐目标有效覆盖时间，不能除以战斗时间或目标数冒称覆盖。目标buff表里没有本样本的两种plague对象。
- 不新增事件采集，不用历史高体积effect_events重建通用覆盖。用户已确认一期相似指标仅为动作频率与经专精源码/角色适用性核验的关键玩家buff；DoT不进入相似指标，但照常模拟、计入DPS并保留原有正确性验证。
- 初始可核查对象是runic_corruption（class_modules/sc_death_knight.cpp:15859按邪恶专精注册）和sudden_doom（:16238按真实天赋可用性注册）；不能把这两个名字机械用于所有专精。具体描述上下文需依据实际角色、受检声明及参考证据形成并冻结，不随候选表现改名单，不随意硬码技能数字ID。
- 这证明一个最小可行报告口径，但尚不是完整实现/当前全部原生构建验收。用户已确认不要求本期通用DoT覆盖相似指标；相关证据不足不再构成需求阻塞，全部适用动作和增益的身份映射仍须在票据实现中验证。
