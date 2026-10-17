# Sim2GSE 规则初始化与自适应搜索开发规格

Status: planning
Triage: needs-info

日期：2026-10-17。本文件及 issues/01、02、03 是唯一四份变更方案。01已有初始化实现与历史验证；本次依据用户新增要求修订为两个可编辑、数据化规则库，尚未实施该修订。单JSON两库保存格式及文件编辑/校验/加载、可视化界面后做已获确认；生效与恢复口径也已确认：新生成/新任务读取新规则，运行中固定启动规则，暂停恢复遇规则变化则拒绝并提示新建任务。引擎与规则库边界亦已确认；具体schema、实现细节及候选新行为仍按下文逐项讨论，不能将文档保存或示例视为实现批准；02/03未开始。

## 问题与用户结果

本变更最初要替换目录均匀起点；当前01已生成规则起点，但业务条件、顺序和停止判断仍分散在Python函数中，保存APL条目并不等于实际按其排位。用户要求把这些逻辑全部收敛为通用与专精两份结构化规则数据，编辑后能生效且日常不重编SimC，再接学生诊断与后续选择器。


1. 用户提交真实角色资料后，得到可合法导出的规则起点及来源说明。
2. 用户能区分静态估算、明确近似、未知条件与真实模拟证据。
3. 用户保留原有其他起点、训练代表、冠军、缓存、预算和晋级能力。
4. 用户看到实际学生状态对应的问题及具体对象、位置、改量，不接受教师状态代替学生诊断。
5. 用户的全部规则问题同时交给选择器，候选一次只做一个操作，不人工先挑一条规则。
6. 不同角色和专精可积累通用经验；继续旧任务不能回滚其他任务的新经验。
7. 非法表示、缺字段、未知条件及恢复问题明确报告，不静默删条件或改爆发。
8. 用户按三张开发票逐票讨论、实施、审查和验收，最终同条件新旧各600秒直接比较输出DPS。
9. 用户或助手可编辑两个规则库；条件、映射、次数、先后、停止及未知处理都能查看和修改，已支持能力内无需重新编译SimC。
10. 每条入库规则逐条审阅：保存什么、怎样对应初始化、生成怎样使用、后续诊断和选择器怎样使用；原目标已确认不等于新数据表达已确认。


## 1. 最终交付什么

用户从现有任务入口提交角色资料，得到合法可导出的 GSE 和既有搜索成绩。内部改两处：

1. 四个基础起点中，只将“目录均匀排列”改为“通用规则＋专精绑定生成的起点”。另三个来源保留；训练代表最多四个，训练冠军与正式搜索冠军各一个；去重后最多 4＋4＋2，不保证一定有十个。
2. 所有起点及新启动的既有训练统一使用：学生模拟诊断→合法修改候选→Coba 选择一个操作→既有模拟和晋级→积累经验。整体替换旧随机算子选择、固定启发式和搜索中的洗牌兜底。随机初始化仍保留。

保留已有模拟、缓存、行为去重、预算、晋级和冠军机制。旧任务不原地换算法、不自动重训；兼容的旧结果可作新任务起点，旧分数不冒充新验证。

本轮不做：完整 APL 解释器、战斗实时调度器、自动改爆发宏、片段/特征挖掘、新增预训练种群或遗传算法、新数据库/常驻经验服务、多算法评测。通用能力首批落地已审核的邪 DK 绑定，不声称所有专精已经配置或验证。

## 2. 两个可编辑规则库与通用执行机制

已确认目标：业务逻辑只来自两个结构化规则库；人和助手都能编辑，程序按数据执行。不能把Python回调移进“规则库”就称为配置化，也不能用规则ID、技能名或CD/消费/Buff等业务类别选择隐藏实现。

| 部分 | 职责 | 边界 |
| --- | --- | --- |
| 通用规则库（数据） | 参数化条件、提议动作、次数、优先/依赖、停止、unknown策略、诊断证据与合法编辑方向、选择器固定语义字段及版本 | 无具体职业技能或私设职业阈值；规则ID仅身份，不是函数名 |
| 专精规则库（数据） | 绑定模板参数、动作/替换身份、事实来源、场景、完整APL条件和父列表优先，以及有来源的人工覆盖 | 不含Python函数、callable或以字符串调用任意代码；不删原条件或伪造未知值 |
| 通用执行机制（程序） | 读取与校验、事实解析、有限比较/组合/算术、排序/依赖/计数、资源/GCD账、既有程序编辑/编译与模拟调用 | 不是第三个规则库；旧“通用过程库”只可指这些机制，不能存业务先后、补几个或收尾策略 |

“规则执行层”是Python中的上述通用机制；“原生引擎”是SimC的数据采集和模拟。日常编辑改规则数据，不改C++、原生编译锁或执行程序。单JSON两库保存形式已确认；下文具体字段与执行契约仍待确认，不是已实现接口。

邪 DK 的骨架周转资源绑定为符能；符文仍约束执行和可排性，不与符能相加。Outbreak 的技能身份、疾病条件、低频过程选择及参数来源写在邪 DK 专精规则库；通用生成器只执行配置引用的过程。这一分层由用户 2026-10-16 15:13:31 的决定明确，具体持续时间数值并未因此自动批准。

2026-10-17 用户决定撤回网站规则路线：专精规则基础仅采用当前引擎固定同版本 SimC APL，并补充用户明确批准的人工规则；网页仅作参考，不作为规则输入。保留灵魂收割 CD 示范、腐化疾病替代、单体枯萎凋零及消费动作一次示范；撤回网站概述及其引入的初始维护优先排序/收尾要求，脓疮打击恢复原有安排。

### 2.1 保存格式已确认；最小字段待确认

2026-10-17 用户确认：用一个JSON配置文件分为通用规则库和专精规则库两个区域，配套保存；先支持编辑文件、校验并加载，可视化编辑界面以后再做。确认依据为用户对“第一项，规则怎么保存”的回复“确认”。

UTF-8、`general`/`specializations`键名、标准库读取及下表schema字段仍是待审建议；生效/恢复口径按2.4的第二项确认执行；两次确认均不包含逐条规则表达或实现授权。尚无正式配置文件或求值实现。

| 字段 | 类型及意义 |
| --- | --- |
| schema_version | 正整数；本稿建议1，不支持的版本拒绝加载，不猜测兼容 |
| general.templates | 按字符串ID索引的对象；类型化parameters、各阶段条件、unknown、initialize、diagnose、edits、features；模板ID只做引用 |
| general.initialization | 对象；骨架stop、消费资源来源目标、有限二层编辑stop及有界次数。覆盖哪些动作、合格生成动作引用、目标资源/费用、完成谓词及停止表达式都写数据；128节点等表示硬限制仍由现有程序保护 |
| specializations | 专精ID到对象的映射；每项含source_revision、actions、facts、bindings。专精ID只索引数据，不选Python分支 |
| actions | 别名到对象；native_action为原生动作键，button为现有基础按钮键，可列variants共享按钮。不能按技能名猜替换关系 |
| facts | 别名到类型/单位/来源映射；来源仅限已登记的capability、scenario、static、estimate、student及有限派生；plan/interval/finding是各阶段保留上下文事实，也需类型/单位/阶段校验，不能任意JSON路径执行函数 |
| bindings | 有序对象数组；id、template、arguments、scope、priority、before/after、yields_to、target、source、overrides；动作及事实引用必须存在 |
| initialize | coverage_id显式标识共享覆盖目标，coverage_when决定本阶段是否纳入，required为布尔值，count为非负整数；when在每个排位机会重求是否可尝试，attempt为动作引用，目标完成谓词与尝试次数分开，另有顺序/依赖及有限间隔/替换声明。次数是尝试数，不是成功数，不能每次when变真重新补count |
| diagnose / edits / features | 所需同次证据和结论条件；既有单操作的对象/位置/改量及界限；固定语义数值特征引用。01校验契约，02实现诊断编辑，03实现选择使用 |
| overrides | 有来源的显式路径和值数组；仅替换声明字段，不隐式深合并数组或抹除原APL条件。同路径冲突拒绝，人工覆盖须记录批准依据 |

模板展开只做类型化参数替换，再按明示路径应用专精人工覆盖，最后校验完整引用与依赖。原通用模板及源条件都保留在快照供追溯；不得另藏自动覆盖顺序。初始化和诊断分别有条件入口，人工初始化例外不能被诊断完整条件的unknown再次挡住，也不能反向修改诊断条件。

### 2.2 一个完整最小例子（结构待审，不能直接当完整邪DK规则库）

人能读的含义：模板要求尝试指定动作；邪DK把动作映射为灵魂收割，保留单体APL斩杀/DT条件；用户已批准的覆盖只让01在能力可用时示范一次，02仍检查完整条件和前序。例子不包含AOE库、其他22条绑定、消费来源目标及二层策略，只用于讨论一条从数据到后续候选的契约。动态事实和区间聚合标为02待支持；缺少前序证据时不能据此得出已证违规。

~~~json
{
  "schema_version": 1,
  "general": {
    "initialization": {
      "stop": {"eq": [{"fact": "plan.required_attempts_remaining"}, 0]},
      "edit_limit": 0,
      "edit_stop": {"gte": [{"fact": "plan.edits_applied"}, 0]}
    },
    "templates": {
      "timely_attempt": {
        "parameters": {"action": "action_ref", "coverage_id": "string", "coverage": "predicate", "condition": "predicate", "attempts": "integer"},
        "unknown": "record_not_applied",
        "initialize": {
          "coverage_id": {"param": "coverage_id"}, "required": true,
          "coverage_when": {"param": "coverage"},
          "when": {"param": "condition"},
          "attempt": {"param": "action"}, "count": {"param": "attempts"}
        },
        "diagnose": {
          "when": {"param": "condition"},
          "observe": "proven_opportunity_interval",
          "action": {"param": "action"},
          "expect": {"gte": [{"fact": "interval.attempt_count"}, 1]}
        },
        "edits": [{"operation": "move", "object": {"fact": "finding.source_position"},
                   "destination": {"fact": "finding.opportunity_position"}}],
        "features": [{"name": "attempt_count", "value": {"fact": "interval.attempt_count"}}]
      }
    }
  },
  "specializations": {
    "252": {
      "source_revision": "eed909156d8eccbfca0f284cc271c080949d6a20",
      "actions": {"reaper": {"native_action": "soul_reaper", "button": "soul_reaper"}},
      "facts": {
        "targets": {"type": "integer", "unit": "count", "from": "scenario.target_count"},
        "available": {"type": "boolean", "from": "capability.available", "action": "reaper"},
        "dt_up": {"type": "boolean", "from": "student.buff.up", "key": "dark_transformation", "phase": "02"},
        "dt_remaining": {"type": "number", "unit": "ms", "from": "student.cooldown.remains_ms", "key": "dark_transformation", "phase": "02"},
        "health": {"type": "number", "unit": "percent", "from": "student.target.health_pct", "phase": "02"}
      },
      "bindings": [{
        "id": "unholy.single_target.2", "template": "timely_attempt",
        "source": {"file": "engine/class_modules/apl/apl_death_knight.cpp", "line": 387,
          "parent": "call_action_list,name=single_target,if=active_enemies<3",
          "entry": "soul_reaper,target_if=min:health.pct,if=buff.dark_transformation.up&cooldown.dark_transformation.remains<38|target.health.pct<35"},
        "scope": {"lt": [{"fact": "targets"}, 3]},
        "priority": {"list": "single_target", "position": 2},
        "yields_to": [{"source_entries": ["default.racials", "default.high_priority", "default.trinkets", "default.cooldowns", "unholy.single_target.1"],
                       "when": {"unknown": "preceding_entries_not_bound_in_example"}}],
        "target": {"mode": "min", "fact": "health"},
        "arguments": {
          "action": "reaper", "coverage_id": "ordinary_reaper_demo", "coverage": {"fact": "available"}, "attempts": 1,
          "condition": {"or": [
            {"and": [{"fact": "dt_up"}, {"lt": [{"fact": "dt_remaining"}, 38000]}]},
            {"lt": [{"fact": "health"}, 35]}
          ]}
        },
        "overrides": [{
          "path": "initialize.when", "value": {"fact": "available"},
          "source": {"kind": "user_approval", "date": "2026-10-17",
                     "decision": "可用灵魂收割纳入一次普通CD示范"},
          "report": "initialization_demo; dynamic_applicability_unknown"
        }]
      }]
    }
  }
}
~~~

例子的38秒和35%来自固定APL，不是新阈值；GCD/CD/费用/收益都从动作映射后的静态快照读取，不在配置编造。`edit_limit: 0`只是这个单条例子不演示二层编辑，迁移真实规则必须另列已有有限二层策略，不能据此禁用现有行为。

迁移前，`unholy_rules.bind`用Python将 `soul_reaper` 追加到 `cooldowns`，并填写 `initialization_coverage`；生成器按固定类别次序和停止分支处理。迁移后是上述动作映射、一次尝试及带来源的阶段覆盖，通用执行器只消费数据。类似地，现有 `spending_decisions` callable中的符能缺口及高/低位判断迁为事实算术、谓词和明确优先；`cooldowns_before_spender`、`buff_demo_needed`、`burst_alignment`、`periodic_action`分别迁为先后关系、条件/次数、锚点引用、条件选择与间隔/替换数据，不保留同名回调或按rule_id分派。

### 2.3 怎样读取、映射和执行

1. 启动任务读取整个包一次，检查版本、类型、单位、动作/事实/模板引用、覆盖路径、依赖无环及阶段支持；参数展开后固定不可变内存快照。现有 `initial_programs` 接收该快照，调用者不自己挑规则类别或合并覆盖。
2. 用 `native_action` 对应 `capabilities.actions[].simc_action` 和 `static_snapshot.actions[].name`，再用button/variants对应现有程序按钮与编译目录。同动作多条APL条目仍保留各自条件/位置；静态同按钮行不一致沿用明确失败，不能取第一条。真实路径和生命周期由有限事实目录解释，不执行配置字符串。
3. 01先用scope与coverage_when建立本阶段覆盖目标及count，同一coverage_id的条目共享一个计数项（声明次数/required/纳入条件不一致则拒绝），之后每个排位机会按更新后的estimate重求when及通用资源/GCD可排性；选中并实际加入一次满足该目标完成谓词的尝试，才对选中条目声明的coverage_id扣一次；消费目标还须符合3.2的资源来源要求，不能仅凭尝试消费便完成，条件再次为真不重新创建目标。高/低位消费条目保留各自条件但显式引用同一消费目标，不因按钮名相同自动合并、也不各增加一次消费。required=true的count是必须完成数，false的count仅为可选尝试上限；plan.required_attempts_remaining只汇总显式required项。FS及资源填充的可选性、上限和阶段停止都须由数据声明，执行器不按Buff/generator类别推断，亦不允许无界填充。按显式before/after、优先及稳定数组顺序选择可排动作。只排序不会创造次数或满足未知条件；没有声明必需示范的具体生成动作仍不要求各出现一次，但CD收益够消费不能绕过3.2的合格来源目标。二层仅执行已声明的有界编辑和停止条件，不以“CD/消费/Buff/生成”分类暗定策略。冲突、不可达或预算/表示上限终止并说明，禁止无限补动作。
例如初始余额低于消费费用时，消费的覆盖目标仍为一次，只是当下不可排；数据已声明的填充产生确定收益后重求谓词，消费在满足其资源来源完成谓词后排入并将剩余计数减为0，其他目标也完成才按stop收尾；初始/CD附赠/被动资源只进入实际预计账，不能用于证明该来源目标。初始when为false不能永久删除覆盖目标，ON_HIT或未知收益不能凭示范次数当作已经赚到资源。

4. 02求scope、diagnose.when、target及完整让位关系。`proven_opportunity_interval`是待实现的通用同次证据聚合：必须证明所需条件/就绪/无高位占用在区间成立；不是按模板名调用专精诊断器。区间、源位置或改量缺失就报告unknown，不造候选；存在时才调用现有单操作编辑及合法性检查。
5. 03将所有诊断和合法候选映射到稳定含义的数值列；例中attempt_count是尝试数。未知附有效性标记而非当实测0，ID只是追溯键，不能当连续大小。Coba一次选一个具体操作，再用现有共同批次DPS反馈学习；新增特征含义要版本化并审查共享模型兼容性。

建议只支持本批需要的有限操作：字面量、param/fact引用；eq/ne/lt/lte/gt/gte；and/or/not；add/subtract/multiply/divide（仅有限数值、单位一致）；必要的min/max及ceil用于已有时间/资源换算。没有用户定义函数、循环、赋值、任意属性访问、eval、Python callable或插件；目标min/is_boss是数据选择方式，只在对应阶段有真实目标事实时求值，不让静态GSE自动选目标。APL字符串只供审计，不建立完整APL解释器。

unknown采用三值逻辑：false AND unknown为false，true OR unknown为true，其余未定保留unknown；未知不是false、0或空列表。缺少GCD/费用等生成所必需事实则拒绝相应起点并说明；动态事实可记录unknown_not_applied。允许未知条件下示范必须有显式人工初始化覆盖；未知收益不入确定性余额，ON_HIT不冒充ON_CAST。原生事实、静态预计账和动作尝试计数分开保存；尝试一次不能将未知小食尸鬼层数/Buff更新成已知值。未知操作、非法类型、除零、无效引用/覆盖及依赖环是配置错误，不降级为unknown继续运行。字符串来源说明不能替代可求值事实或授权。unknown字段建议限定为error、record_not_applied或attempt_with_report，按阶段声明；最后一项仅用于有明确批准依据的初始化示范，诊断不能用它证明条件成立。

### 2.4 生效与恢复已确认；保存、快照和缓存实现待审

2026-10-17 用户确认第二项：保存并通过校验后，下一次生成初始化序列或启动新任务读取新规则，已支持能力内无需重编译引擎；运行中的任务继续使用启动时规则，不在热循环重读配置。暂停任务恢复时若发现规则变化，沿用现有冲突拒绝，提示重新启动任务。

以下为实现建议，未因上述语义确认而自动获准实施：一个原子JSON包保证两库同版。复用 `task.py:328` 的JSON写入、`runtime.py:16` 的replace_file和 `burst.py:70–96` 的发布/摘要模式；当前固定.tmp写法不自动解决并发；保存接缝应限定单写者，或在能覆盖实际多个写者的同一锁/事务临界区核对预期旧digest并原子替换，不能先无锁比较再写造成竞态。冲突明确失败，不引入服务或跨文件事务框架。

通过保存入口的非法内容不得替换上一有效版本；直接手工把文件写坏则无法保证磁盘文件未被覆盖，但新启动必须显示该文件/字段错误并拒绝使用，不能静默加载旧值冒充保存生效。现有运行任务保留已验证内存快照及其版本标识；双场父任务只加载一次，再把同一快照传给单体/AOE子场，不由两场各读current。旧有效快照保留用于追溯与核验，不作为规则变化后继续旧任务的旁路，也不能自动隐瞒坏文件。

取消原草案“规则变化后仍沿旧配置快照恢复”的路径，复用现有规则变化即拒绝恢复的政策；不改 `myspec/specs/sim2gse-reviewed-burst/spec.md` 的该项约束。规则未变也仍须通过既有引擎、事实协议及执行兼容核验，不能只凭JSON相同宣称可续跑。

复用 `search.py:121–126` 规范化摘要、TaskStore（797起）JSON状态及现有结果初始化记录。规范化对象键而保留数组顺序，快照保存整包、来源、schema/事实协议/执行版本和 `rule_config_digest`。摘要显式加入 `task.py:1303–1331` 的生成/搜索条件及训练语义身份；`seed_training.py:476–491` 会删除旧源码 `rules` 字段，因此新摘要必须独立保留，不能只塞进展示或被删的字段。规则变化不得命中旧规则生成/搜索缓存；旧原生模拟分数只有在既有完整输入/程序身份兼容时才按原缓存政策复用。规则文件不进入 `native_build.py` 的sources/patches身份，未变原生引擎不因此重建。

### 2.5 引擎与规则库边界已确认；具体补口实现待审

2026-10-17 用户确认第三项：技能选择、条件、优先级、次数、替换关系均保存在规则库；程序仅执行通用比较、排序、计数与序列修改。本次将按具体技能限定的数据读取改为通用接口，优先复用已有能力；已有数据和通用操作范围内修改规则，保存校验后按2.4生效且无需重编译。新原生数据或全新操作另行讨论，不为无限扩展新增复杂框架。

当前070补丁仍列9个动作名；catalogue已能遍历实例化动作，但战后目录使用的基础trigger_gcd不能替代战前有效值。具体实现建议一次性复用已有动作目录/实例集合，扩为已支持动作类别的安全静态采集；普通新增已存在且可用的动作映射、阈值、次数和排位才可只改配置。需要先完成这次开发及验证，此前不能承诺当前引擎已支持全部动作。

采集仍在 `precombat_init` 后、预战动作前；仅处理已初始化的合法动作实例，逐类核验GCD/CD/费用/收益getter及目标/state要求、空指针和观察副作用，不以删名单后对所有动作调用 `composite_energize_amount(nullptr)` 代替安全设计。无法安全导出的字段标unknown或拒绝必需能力，禁止为采集执行动作或额外ready。

支持目录首批复用static_snapshot的resources.current/maximum、actions的gcd_ms/cooldown_ms/cast_ms/channeled/costs/gains/gain_status/gain_timing/charges/max_charges及已存在parameters。070中的Blightburst、Cycle、Scythe天赋、疾病时长、初始小食尸鬼层数及符文恢复参数也有专精采集代码；去掉9技能名单不等于这些事实全已通用。已导出的事实映射可改配置；新增原生事实、未安全支持的动作或新机制仍需单独批准开发，可能重编引擎。学生动态事实为02补口，不在01复制完整战斗模拟器。

## 3. 初始 GSE 怎样生成

### 3.1 真实静态数据

按角色装备、急速、天赋和常驻加成取得动作的有效静态 GCD/CD、费用、确定性收益、资源初值/容量及必要恢复信息。不能统一假设1.5秒，也不能把目录基础 trigger_gcd 当成有效GCD；不要求预测所有战斗触发。

复用引擎已有动作和资源实现，只导出已支持事实。数据必须具有明确采集时点和来源，不能从战后平均值倒推非战斗静态值。当前已有战前静态快照；此次需一次性消除逐技能采集名单的维护依赖，具体零编译边界见2.5，不把既有战后动作目录直接充作有效静态值。

### 3.2 两层生成

1. 按已确认规则数据声明的先后、依赖和保护约束排位。执行代码不内置“CD→消费→Buff→生成”顺序；迁移必须逐条列出当前静态先后与APL先后的差异，不能将更换格式暗作行为修正。
2. 当前已确认的骨架覆盖约定必须写入规则数据：普通循环负责的各 CD 完成一次示范，绑定的资源消费动作完成一次示范，且这一次消费所需资源全部来自配置指定的资源生成动作；在最早满足这些骨架条件的位置收尾。初始/CD附赠/被动资源不能用于证明该来源目标。按绑定动作及其实际静态费用判断，不累计一份资源容量；消费总量仅作报告。邪 DK 消费动作绑定符能，符文仍只约束动作可排性。
3. 这是起点估算，不要求资源先满后空、收支平衡、首尾所有状态恢复或下一轮CD就绪。长CD允许轮空，不以最长CD、最小公倍数或爆发45秒间隔强行拉长骨架。
4. 再按数据中显式声明的有限编辑、可替换范围与完成条件调整骨架的顺序、频次、间隔和长度，形成初始GSE；第4条动态短窗口的初始化边界见下文。同一CD一轮尝试两次允许，最终序列无需维持最初覆盖计数或生成额度；不为重复演示骨架而无依据铺长排列。

2026-10-16 用户最新确认：骨架由“消耗一轮资源”改为“消费动作示范一次”，覆盖此前容量目标；第二层仍为有限规则编辑，不把一次示范次数重新锁成最终序列要求。用户另批准邪DK单体初始化也示范一次枯萎凋零，前提为能力可用且对应天赋开启；此初始化覆盖策略写在专精绑定，保留原APL至少3目标条件和来源，明确不是上游单体推荐，不虚构减CD或固定周期。

2026-10-17 用户明确补充：灵魂收割在当前角色能力可用时，单体和AOE初始化都作为普通CD加入一次示范，不再以动态斩杀或黑暗突变条件未知为由排除。复用既有CD排位和真实静态GCD/CD/费用；不硬定施放时点，不修改冻结爆发。完整APL条件与优先保留为后续诊断依据，本次静态覆盖明确标为用户批准的示范，动态适用性仍为unknown。此决定不要求一次尝试成功，也不启动02/03。

2026-10-16 用户明确确认：第4条动态短窗口优化交由后续学生诊断与搜索处理。01静态初始化保留完整规则/专精绑定及 `unknown_not_applied`（未知、未应用）说明，不要求据此独立调序，也不将普通填充贴成该规则已执行；该边界不再作为01缺口阻断。02按学生实际窗口诊断和提出修改，03接入既有后续搜索流程，三票结构与执行顺序不变。

2026-10-17 用户明确增加骨架限定：用于完成一次消费示范的资源，必须全部来自配置指定的资源生成动作。旧待确认AOE“脓疮→天灾”强制示范链由此通用骨架方案替代并撤下，不再列为待批准方案；不保证任何特定技能必现，也不把每种生成动作各尝试一次。

**仅适用于最初骨架。** 用户此前已明确：骨架只是最初模板，随后由8条规则填充、调整，最终标准是那8条规则。资源来源目标不是第9条规则，也不是最终初始化或搜索候选的硬约束。第二层允许按有依据的规则移动、替换、删除或增加动作；只须追溯修改理由及影响，不强制复核并补回骨架生成额度，不增加“必须保留generator”的政策。硬合法性、真实预计资源/GCD约束和冻结爆发保护仍有效。

**最小机制建议，细节尚未批准：** 实际预计资源账保持原值，另记从0开始的“合格生成额度”，只统计配置指定动作对目标资源的known/on_cast有效收益，扣除容量溢出部分；初始资源、CD附赠、被动收益不计入该额度。同资源消费扣减可用额度，目标消费前额度足以覆盖该次真实静态费用时，才可据此完成一次来源合格的消费示范。未知/命中后收益不虚构为确定额度，其他资源只约束可排性，不与目标资源相加。这是有限静态构造核算建议，不证明真实施放成功，也不建立逐资源单位的复杂归因系统；动作集合、资源引用、完成/扣减条件及停止均由规则数据声明。

2026-10-17 用户明确满资源开场的处理：骨架内先安排一次消费腾出空间，再安排生成→目标消费；前面腾空间的这一次不算完成骨架消费示范。该条件和一次上限写入规则数据，真实预计资源/GCD/容量照常核算；不引入自适应多次清空。若特殊数据在这一次后仍无法满足目标，明确报告局限，不自动继续预消费或扩展设计。此安排仍只属于最初骨架，后续8规则可修改。

额度具体字段、扣减/归属算法与unknown处理仍待逐条讨论；实现方案和验收细节确认后再开发，不改造真实初值或以无限填充规避冲突。

已有FS增益维护身份、初始层数条件和一次示范上限也须迁移，不能只迁移疾病维护。现有代码未把FS声明为必须完成的独立覆盖目标，资源够用时仍可能省略；本轮格式迁移不得暗中补成必现、恢复爆发前保证或改变其停止条件。具体动作是否进入最初骨架，由上述通用来源目标及已确认规则数据决定，不单设AOE强制链。

静态消耗账表示预计成功时的消费，失败尝试不能称为已实际消费。资源预留仅在源规则要求时采用；预计接近上限时选择适用消费，否则依据源优先及必要多资源账安排。未知疾病、伤口或随机触发条件仍标未知，不造第二个战斗模拟器。

### 3.3 从时间到点击

普通瞬发占GCD动作先采用已确认的保守初值：点击跨度＝ceil(该动作静态有效GCD／实际按键间隔)，动作尝试本身占一次，空点击数＝跨度−1。一次尝试后仍按现有语义推进，不默认增加重试。

该做法每机会可能多等不足一个按键间隔，累计代价由第8规则及搜索检查；不保证施放成功或最优。off-GCD、施法/引导及特殊动作另按引擎语义处理。空点击为0可省略，为1时现有搜索表示存在缺口，不能自动改成0或2。

CD除以静态GCD只用于估算施放机会间距，不能直接当GSE步骤数。多个动作争同一占GCD机会时按适用APL优先，其他顺延；越窗、越界或无法表达要报告，不挤入同槽或无限顺延。

### 3.4 Outbreak 与爆发边界

低频或间隔的数值计算是通用机制。是否启用、对应动作、间距事实、允许替换哪些资源填充、跨轮不足如何处理均由两库数据声明，Outbreak只是专精动作引用；不以短骨架每轮一次来决定频率，也不把“全场无病”伪装成GSE实时判断。可以使用顶层Action/WaitClicks平铺；仅不含等待的重复动作片段可用现有Loop。具体间距需来自已核验绑定参数，尚无被批准的固定秒数。

2026-10-16 用户批准邪DK初始化维护替代：仅当原生明确导出 `blightburst=true`，且Putrefy可用并纳入普通CD骨架时，专精绑定令 `periodic_action=None`，省略普通起点中的Outbreak及其周期尾等。Blightburst为false、缺失未知或Putrefy不可用时保留原Outbreak安排。Putrefy仍按原CD/伤害动作处理，不改为疾病固定周期；省略是用户初始化策略，不保证首次爆炸前或全程疾病覆盖，完整APL开场及断病兜底来源继续保留。

来源边界：固定SimC `sc_death_knight.cpp:12103–12130,12153–12157,12184–12188` 明确由Blightburst控制Putrefy的施病/延病；APL:372仍有Outbreak开场及断病兜底。Wowhead仅核对到只读索引，未全文核实；网页仅作参考，不作为规则输入；上述行为依据固定源码和明确人工批准，不以指南摘要覆盖完整条件。

当前独立爆发宏内容与节奏不变，Army/DT/Blightfall不加入普通循环搜索。当前邪DK配置在3/48/93/138秒安排爆发输入，各1秒；这是当前绑定配置，不是通用周期。普通输入暂停、位置保留，墙钟和资源/CD仍继续。按键尝试不等于施放成功，静态普通循环不保证每轮对齐真实Buff窗口。

## 4. 八条规则及可提出的修改

下表是实施范围。每条仍须保留专精绑定的完整条件、父入口、前序让位和例外；表内摘要不能替代完整源条件。硬GSE合法性、可优化规则事实和学习经验参数分开。

| 规则 | 通用含义与当前邪DK绑定 | 有证据时的合法修改 | 不能误判的边界 |
| --- | --- | --- | --- |
| 1 窗口或满充能释放 | AoE Putrefy：DT开启 **或** 当前满充能；至少3目标及前序优先保留。单体条目独立绑定 | 前移、补一次尝试、缩短关联间隔 | 非DT满充能可合法使用；被高优先占用不自动违规 |
| 2 低优先消费预留资源 | 单体低位Death Coil：Army剩余>5 **或** 符能缺口<50；只约束此低位条目 | 后移/减少该低位消费，或提前有依据的前置动作 | 不改成固定留50符能，不禁止其他高位Death Coil；5目标案例不能证明单体行为 |
| 3 近满资源时及时消费 | 高位Epidemic的完整OR条件及epidemic_prio；deficit<15只是其中一支 | 提前或补消费；仅在证据明确时减少冗余生成 | 近满不等于已溢出；不能越过预留/窗口的源优先 |
| 4 短窗口及时用指定动作 | Scourge Strike：Vampiric Strike.up且Essence.up且Essence.remains<gcd×3，保留基础按钮替换身份 | 提前/分散指定按钮尝试，缩短关联等待 | 01保留绑定及unknown，不要求独立调序；动态优化由02/03承接。不泛化为所有Buff不断档，不新增独立吸血按钮，不保证随机触发相位 |
| 5 普通循环配合固定爆发 | 只诊断普通排列对既定爆发的资源、等待和受益动作影响 | 仅改普通循环动作/等待 | 爆发宏内容、时点、来源和排除策略均受保护 |
| 6 普通CD在源允许时及时尝试 | D&D完整APL仍保留至少3目标、天赋、镰刀增益、Putrefy充能、战斗/小怪剩余及数量、自身充能组合；单体初始化另按用户批准覆盖一次 | 前移/补尝试；有证据时降低过早重复密度 | 单体覆盖不称为上游单体推荐；不是CD好就放；源允许等待不违规；裸duration不能换成地面持续时间 |
| 7 必要持续效果按条件补齐 | Outbreak保留天赋、Putrefy剩余/开场、玩家全场Dread Plague计数为0、战斗/小怪剩余等条件 | 补漏时前移/补尝试；已证重复时减少或拉开 | active_dots=0不是当前目标没病；低频初始化是显式近似 |
| 8 尽量减少可避免GCD空闲 | 实际有可用且符合相关前七项/APL的具体动作，却未及时尝试 | 减少已证多余等待、前移或插入合法填充 | 低于前七项；合理等待和unknown不据此删等待；动作数差不是理论损失GCD数 |

第8项分三类：已证可避免空闲；有源依据的合理等待；证据不足的unknown。正常GCD、施法/引导占用不算空闲。优先汇总已证空闲时长，合理/未知分列；不把教师动作总数当绝对天花板，不从用户举例生成全职业硬阈值。

完整绑定源以固定[邪DK APL](https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/apl/apl_death_knight.cpp#L349-L406)为准；本规格附录直接收录取值入口与必要证据。第二条单体Death Coil与第六条D&D已获准进入验证范围，尚无新学生诊断验收。

### 4.1 八条规则的数据表达与阶段边界

下表是迁移覆盖清单，不是八条新表达已获批准。完整APL签名、父入口、优先和前序让位继续保存；初始化近似条件与诊断完整条件分开，未支持的动态事实显式unknown，不删掉后伪称已实现。

| 逐条审阅顺序 | 规则数据必须声明 | 01初始化 | 02诊断与候选数据（03再选择） |
| --- | --- | --- | --- |
| 1 窗口/满充能 | 窗口OR当前/最大充能比较、完整父条件、动作及让位 | 原生首次满充能/已批准窗口尝试近似；再充一次不等于满 | 同次窗口/充能/前序证据；允许移动、插入、调整间隔及有界改量 |
| 2 预留资源 | Army剩余>5 OR符能缺口<50、具体低位条目、上层入口 | 只用已支持的静态缺口分支，Army状态未知 | 证据充分才后移/删除该条消费或前移有依据的前置动作；不泛化所有死缠 |
| 3 近满消费 | 完整OR、epidemic_prio的完整有限右侧、资源事实、max_stack−1等必要算术和前序关系 | 支持的资源分支可估，其余unknown；不等于实际溢出 | 资源/Buff/react及让位证据；插入/前移消费，证实冗余后才减生成 |
| 4 短窗口 | 三项AND、Essence剩余<动作GCD×3、基础按钮替换引用 | 仅保存完整绑定与unknown，不独立调序 | 同次Buff剩余/反应/动作GCD；前移/分散动作或缩短等待，不新增吸血按钮 |
| 5 固定爆发配合 | 冻结计划引用、普通动作与锚点关系、保护对象及允许编辑对象 | 按现有输入暂停/位置及对齐尝试，不证明Buff生效 | 尝试/成功/资源/窗口证据；仅改普通动作/等待，禁止改爆发定义 |
| 6 普通CD | 完整DND条件（含duration×0.75）、动作资格、覆盖次数和人工例外 | DND单体/收割示范由显式人工覆盖，不宣称原APL成立 | CD/充能/场景/时间等完整证据；移动/插入及已证过密的删除；duration语义不换 |
| 7 持续维护 | 完整疾病条件（含gcd.max×2）、替代启用谓词、间距来源、跨轮约束、可替换条目 | 保留已批准腐化替代和Outbreak间距近似；unknown替代不启用 | 全场active_dots及开场/剩余证据；前移/插入或已证重复后删除/拉开 |
| 8 减少空闲 | 低于其他适用规则、占用/就绪事实、合理等待与unknown分类 | 有限待办及资源填充；仅确定性收益入账，不强加全动作覆盖 | 同次已算ready及区间证据；删除/缩短多余等待或插入合法动作；禁止额外全APL ready扫描 |

每项同时声明诊断证据引用、结论条件、候选编辑引用及选择器特征引用。01校验引用/类型和阶段边界但不执行02诊断；02不能另写八段按编号分支，03也不能凭技能或规则ID赋予隐藏优先/奖励。完整源条件可保存为审计文本，但程序只读取经逐条核准的结构化表达；保存文本本身不代表条件已能求值。

## 5. 诊断、候选和模拟如何连接

诊断和候选关系同样来自两个规则库，不在执行代码按规则编号选诊断器。每条诊断声明所需事实、适用谓词、期望/违反谓词、让位引用和缺证策略；每条编辑声明既有操作、目标来源位置引用、方向/改量及有限范围。程序仅匹配同次学生事实、计算结论并调用已有单操作编辑机制。02尚未支持的事实或编辑不因出现在配置中自动可执行。

诊断只读取本次候选的学生实际状态，不用教师轨迹补缺。每项最小记录为：规则/绑定身份，场景和时间/来源位置，适用性及结论，原因与让位关系，证据/缺口，次数或时长及分母摘要。

先区分适用、不适用、适用性未知；只有证据完整时判断符合、违反或合理让位。动作不可用本身不证明整条规则通过或违反。上层条件、react历史或前序优先无法证明时保留unknown。

候选模块把全部已知问题转成统一有限候选池。每个候选只有一个具体操作，带生成父身份、原对象/位置、改前改后参数和影响范围。复用已有插入、删除、移动、交换、替换、块内命令、Loop/次数、WaitClicks和CastSequence/Reset能力；不增加多组合枚举。

- 修改Loop身体会影响全部相应重复，不能伪装为只改日志中一次发生。
- CastSequence成功推进/Reset与普通序列失败仍推进不同，不能无成本互换。
- 不从unknown编造修改原因；有限合法探索须标明探索，不能恢复旧随机兜底。
- 候选经过既有硬合法性与行为去重，再模拟。改后状态必须重新产生，不能套用改前资源或Buff结论。
- 规则改善不直接晋级，仍以原模拟评分与现有晋级机制决定保留。

## 6. Coba怎样选择和积累

沿用Coba现成LinUCB＋NumPy，直接调用predict/learn，不引入其整套实验框架，不自写替代算法。

输入是全八条诊断摘要（含unknown）和当前跨规则合法操作列表，不人工先挑一条规则、不分成八个选择器。固定维度数值列按通用语义编码：规则状态、操作类别、对象机制属性、资源类型及归一化量、位置/方向/改量。角色差异是上下文，不是经验分区；不能把技能ID当连续大小或让同一列换职业就换含义。

特征编码协议（列顺序、维数、单位、归一化和反馈语义）沿现有模型版本保存，在predict、learn和恢复时核验；不兼容时明确拒绝旧模型或待反馈，升级另审。rule_config_digest变化只标识规则任务版本，不自动建立每配置一份learner；特征/反馈语义兼容时继续共享经验。

适配层保留完整候选与选择时数值快照。返回值映射回准确对象和位置；相同数值摘要的不同候选不误去重，不声称模型能区分摘要没有表达的差异。

一次predict选一个操作及probability。现有一轮仍可反复选择、不放回地形成多个独立候选；它们不叠加成一条组合程序。整轮已入队后收到的反馈影响后续选择，不宣称已经排好的同轮候选会即时重排。

**反馈唯一口径：** 使用生成父与候选已有的共同search批次，分别按实际samples加权求DPS，reward＝(候选均值−父均值)／父均值。升正降负，不额外模拟，不加人工评分权重。匹配场景、种子/输入计划及执行配置，不能要求包含不同程序身份的完整data_key相等。没有可比共同批次或分母无效则记录缺口、不learn；正常早筛退出仍可使用其已完成共同批次。取消、预算截断和引擎错误不造零奖励。保留原晋级判断，晋级对手可能是处理时最佳，不偷换生成父。

**共享与恢复：** 同一宿主进程的正式任务和训练共享原生learner，短锁保护predict、learn及必要快照，不持锁跑模拟。不建立每任务副本或结束归并；原生learn持续累积，每个有效反馈只学一次。经验跨角色、专精和任务通用，候选合法性仍由各角色自己的绑定保障。

复用任务检查点与结果中心，保存模型、Coba随机进度、版本、决策快照和反馈去重所需状态。规则未变且通过兼容核验后恢复旧任务，不能回滚其他任务已经积累的全局经验；规则变化时按2.4拒绝恢复并提示新建任务。官方序列化尚不能证明精确随机恢复，必要薄适配、原子提交和崩溃一致性留实现验证；不另建数据库或共享学习服务，不承诺一定正迁移。

## 7. 性能与复用边界

配置在任务启动时读入、校验、规范化和解析引用一次；按当前需求给文件字节、条目数、表达式深度及次数设置有界校验，具体上限实施时列明，不另建大框架；热路径只使用同一内存快照，不每步读盘、重解析JSON或扫描无关规则/全部APL；允许顺序匹配已预选的少量有界适用规则，不为此新建复杂索引。按规则依赖预选所需事实与有限候选，保持既有128节点/4096点击约束；不为可编辑性新增模拟批次。配置读/校验、初始化、缓存失效和保存耗时都计入任务成本，先测小构造例，不新增100种子或长场实验。

性能从设计开始约束：不新增诊断专用完整模拟、不额外调用有副作用的ready、不逐点击扫描完整APL；复用同次事件和已经计算的状态，默认少量聚合与有界样本，不默认全量trace。无法在限定字段与候选范围内证明的条件保留unknown。

静态绑定按实际依赖身份缓存：有效输入、引擎/数据/规则版本及相关场景/爆发配置；程序位置映射还依赖程序身份。动态资源、Buff和就绪不能跨模拟缓存。候选与输出设有界实现，不引入全排列或无限特征列。

LinUCB成本随编码维数增长，默认交互项d=1+q+p×q；预测约O(C×d²)，学习及模型约O(d²)。这是源码推导，尚无实测开销。生成、诊断、选择、学习、保存及锁等待全部计入原搜索600秒，不借日志开关暂停算法计时。

| 既有位置 | 直接复用与必要补口 |
| --- | --- |
| 原生catalogue、controller及engine/sequence适配 | 复用动作/状态/输入来源；补最小静态字段与同次学生聚合，不造新模拟器 |
| search.initial_programs | 接收已冻结两库快照，只替换均匀目录来源，保留其余起点 |
| simulation_config、task._write_json、runtime.replace_file、burst发布模式 | 复用标准库读取/类型校验模式、原子替换和内容摘要；不改爆发内容，不另建配置服务 |
| task条件身份、seed_training.semantic_condition | 配置摘要独立于源码摘要保留进生成/搜索/训练语义身份；不加入原生构建sources/patches |
| search.mutate内实际编辑体 | 参数化对象/位置/改量；替换旧随机和启发式选择，不全面重构 |
| program、codec、burst | 现有合法性、行为身份、导出和受保护爆发检查 |
| search.optimize、TaskStore、result_store | 现有批次、缓存、晋级、预算、检查点与结果中心；接Coba与必要恢复 |

既有硬限制为顶层128节点、展开4096点击、WaitClicks 2–4096、Loop仅动作等，来源在program.py，不能为生成成立自动扩容。单空点击、缺字段、非法对象或无法导出必须明确失败，不静默丢条件或退回旧来源。

## 8. 三张开发票，逐票完成

| 顺序 | 独立开发票 | 交付及验收 | 真实依赖 |
| --- | --- | --- | --- |
| 1 | [规则起点与合法导出](issues/01-rule-initialization.md) | 编辑并校验两库→冻结配置及真实静态参数→通用机制生成→真实GSE及来源；迁移已有初始化，演示只改配置改变排位/次数；第4条仍unknown | 无其他开发票；先确认2节契约、10节决策并逐条审阅；字段和绑定参数须有来源 |
| 2 | [学生诊断与合法修改](issues/02-diagnostic-edits.md) | 同次学生状态→八规则结论→一个明确合法修改→原生评分；验证unknown、爆发保护及观察不改变行为，取得诊断修改的真实证据 | 输入可用现有GSE；数据化诊断复用第1票的已确认规则契约/加载快照机制，不依赖它产出的某条序列 |
| 3 | [统一自适应搜索与共享恢复](issues/03-adaptive-search.md) | 所有起点和训练进入Coba同一机制；已有反馈只学一次、共享及恢复可靠；贯通演示并完成最终两组DPS对比 | 完整交付依赖第1、2票 |

三票只是划分，执行顺序明确为1→2→3，每票讨论清楚、实施、验证并独立审查后再推进下一票。本次修订均为待讨论草案；01旧实现及历史授权保留记录，不等于新架构或新增覆盖已获实施授权。初始化、诊断修改和选择器的原型验证沿实际开发实现产出，同一真实产物贯通复用，不另写一次性demo框架；一个成功例子不能替代各票边界检查。

## 9. 验证及最终对比

环境准备首先使用[统一云端初始化入口](../../../docs/cloud-environment.md)：技能仓库 `scripts/cloud_bootstrap.py` 读取 `scripts/cloud-environment.json` 的项目配置，Linux 使用 `scripts/project_environment.py` 准备依赖，Windows 调用项目 `scripts/dev/setup.ps1`。它不等于原生引擎已构建或正式入口验收通过。其他环境说明：[环境说明](../../../docs/environment-setup.md)、[本机任务与数据中心连接](../../../docs/sim2gse/local-task.md)、[构建验证配置](../../../.build-and-verify/config.json)、[固定兼容版本](../../../projects/sim2gse/compatibility/lock.json)。`.tools/`、`.local/` 属于忽略的缓存/运行目录，clone 只保证取得受版本管理的代码和版本锁，不保证完整 SimC 源码/构建产品、GSE 缓存、实际 data-store 安装连接、私有角色输入或历史报告就绪；按上述现有入口准备并核验。外部 data-store 安装副本存在不等于当前项目已连接。Coba 依赖安装和版本锁属于第03票尚待实施内容。

复用最高现有入口网页→任务API→task.run_task及相关任务恢复，内部复用sequence.evaluate与共享编译接缝。构造样例验证分支与失败路径，真实角色产物验证实际数据和导出，两者区分。新配置保存入口作为同一产品的待确认公开接缝；不测试私有求值函数代替保存→新任务→输出行为。测试加入现有自动发现，不建第二测试框架。

云端完成开发。正式引擎构建、固定Windows/Lua及真实数据中心安装副本相关验证依仓库现有环境要求执行；缺环境明确报告，不用mock或Linux定向结果冒称正式通过。本机具体动作和路径须列入授权，未经允许不在仓库外创建文件。

现有命令与预算依据（带 --base 的正式验证在提交后、干净工作树运行）：build-and-verify build --project .；build-and-verify verify --project . --base 5d7165b798d8a7555a74006a1206bd60d8db4331 --execution-context cloud（本机实际执行时地点改为 local；默认快速验证，完整模式仅按技能允许场景执行）。构建配置中Sim2GSE构建超时1200秒；整套正式验证预算60秒，单项Sim2GSE检查另有600秒上限，不能把单项上限当整套可用时间。以上均为既有上限，不是耗时预测，也不是新增模拟成本阈值。首票真实静态读取/导出的具体执行入口及总限时需在开始该动作前列清。

配置化必要验收（先以独立小mock完成，不新增收益实验）：

- 不改Python/C++，仅改配置中的相对优先或示范次数，新任务生成相应变化；记录同一原生binary/hash，不能把GSE重新导出称为SimC重编译。
- 一致重命名规则ID/事实别名/动作别名后行为不变；第二份synthetic（独立构造）专精配置用无邪DK技能名及不同主/约束资源证明无隐藏分支，不承诺另一真实专精已支持。
- 无效引用、类型/单位不符、未知操作/版本、依赖成环、负/非整数次数、缺事实和三值unknown按声明拒绝或报告，不默认0/false。
- 两任务在配置更新前后各固定完整同版两库；暂停恢复遇规则变化时明确拒绝并提示新建任务；并发保存冲突、损坏文件及直接编辑路径不串版本，坏保存不成为新有效版本。
- 规则digest变化进入任务和seed_training语义身份、不得命中旧规则缓存；原生构建身份不变。旧任务输出可重读其完整快照、来源和摘要。
- 骨架小构造验收须覆盖CD/初始/被动资源不算来源、合格生成有效收益扣溢出、消费扣减、unknown与满资源边界；满资源开场只先消费一次腾空间，该次不完成示范，再生成→目标消费；一次仍不足时报告局限，不自动多次清空。二层按8规则合法修改后不因额度不足被拒绝或强制补回，理由可追溯，不新增收益模拟。
- 对八条通用规则及23条已有专精条目逐条核对迁移表和用户review记录；已确认人工覆盖、unknown和冻结爆发不丢失；旧AOE强制链已由通用骨架来源目标替代，不能再启用。

**最终收益验收只有一项：同样条件下旧方案和新方案各跑600秒，直接比较输出DPS。** 不加额外复测、四组消融、统计门槛、最低提升百分比或5%开销门槛。现有内部晋级机制仍保留。历史100份180秒五目标报告用于研究，不能机械变成本次必须再跑100次的规定；真实战斗按约定完整时长，不人为截短成有利结果。

## 10. 待用户逐项决定与逐条规则审阅

已确认：两个可编辑数据规则库；业务判断及映射全部数据化；已支持能力内编辑免编译；使用固定同版本APL加明确人工规则；全部入库规则重新逐条review。以下只列讨论队列，不要求用户一次回答，更不默认整套通过。

1. **01保存格式和编辑方式已确认。** 用户确认单个JSON文件包含通用与专精两个逻辑库，先编辑文件、校验并加载，可视化界面后做。协议版本、字段、有限操作及具体读取机制尚未确认；不将本项确认扩大为整套schema或实施批准。
2. **01生效与恢复语义已确认。** 保存并通过校验后，下一次生成初始化序列/新任务读取新规则，已支持能力内不重编引擎；运行中保留启动规则。暂停恢复若规则变化，拒绝并提示重新启动任务；取消跨规则变化沿旧快照续跑的建议，沿用现有政策和正式规格，不扩展恢复机制。
3. **01引擎与规则库边界已确认。** 技能选择、条件、优先级、次数、替换关系数据化，程序只执行通用操作；本次优先复用能力，将按具体技能限定的数据读取通用化。已有数据/操作内改规则免编译；新增底层数据或全新操作单独讨论。具体安全采集清单、实现与验证仍待审，不扩成无限能力框架。
4. **骨架资源来源目标已明确，细节待讨论。** 一次目标消费资源须全部来自配置指定生成动作，只用于最初骨架，后续8规则可修改它；旧AOE强制链提议撤下。另账从0计合格有效收益、消费扣减及unknown处理是最小建议；满资源开场先消费一次腾空间已明确，该次不算完成示范；不扩多次清空，也不扩展最终约束。具体额度字段与unknown处理仍待讨论。

### 10.1 逐条review顺序及记录

保存格式已确认；具体协议仍须讨论，确认后按第4节1→8逐个审阅通用模板，再按原APL父列表及行号逐条审阅其专精绑定；同一动作多条条件不得合成一条。当前BINDINGS有23条，经逐条核对签名对应固定APL，但新的数据表达均未确认。人工覆盖另逐条审阅：单次消费、单体DND、腐化替疾病、收割CD示范；骨架新增资源来源要求独立于这8条规则审阅，其具体核算细节待讨论；不再讨论已被替代的AOE强制链，不恢复已撤网站规则。跨规则引用涉及未审条目时标为待核，不能整库批量批准。

每条使用下列同一记录模板，记录保存在本规格/对应票Comments，不新增清单文件；未讨论填“待确认”，不得根据示例自行勾选：

| 项目 | 逐条必须记录的内容 |
| --- | --- |
| 身份与状态 | 通用模板ID／专精绑定ID、场景、来源提交/行号；目标已确认／表达待确认／未实现分别记录 |
| ① 保存什么 | 完整字段、类型/单位、事实来源/时点、动作和替换身份；模板参数、人工覆盖与合并后的具体值 |
| ② 怎样对应初始化 | 可用/适用/unknown判定、动作引用、输入事实→通用模板的参数对应，不依赖技能名或ID分支 |
| ③ 生成怎样用 | 先后/依赖、次数、何时允许插入/删除/替换、阶段停止条件；一例结果和一例unknown/不适用结果 |
| ④ 后续怎样用 | 同次学生诊断证据→结论→有限合法编辑及位置/改量→Coba固定含义数值上下文、一次选择及原有共同DPS反馈 |
| 边界与结果 | 01/02/03各自支持/未实现；保护/缺证/错误处理；用户逐条结论、时间及需修改项，后续复核证据 |

01核对①②③并同时说明④的待实现接口；02补足④的诊断和候选真实证据；03核对选择映射、共同批次反馈及恢复。没有对应证据不得从“已确认目标”跳到“已实现/已验收”。

## 11. 开发状态与流程边界

本次仅修订这四份方案，无正式可执行规则文件、代码或原生补丁变更。01旧代码仍在功能分支，其新增配置化范围回到needs-info；02/03保持draft。依01→02→03逐票讨论、开发、验证和独立审查，不同时开工。02输入可来自已有GSE，但复用01交付的规则数据契约与快照机制；03完整交付依赖01、02，不另写一次性demo框架。

原研究基线为80cb3a8b67ca5b86a23b95cec7f6256e79d70b18；全局固定验证基线为5d7165b798d8a7555a74006a1206bd60d8db4331；本次文档审计起点为f0d26203fc6671ba16b1e857bc5f3f676f76944b。沿用codex/sim2gse-rule-guided-search同一工作树；其78份既有无关素材修改不属于交付。

文档提交先供独立架构审查与用户逐项讨论，不代表产品实施或推送已完成。真正开始新增实施前，按现有流程展示更新范围、固定基线、公开接缝、分支、开发与独立审查安排并取得门禁确认；不把旧01授权自动扩展到本次新架构。正式规格仍在交付阶段按已确认决定更新，本次不触碰myspec/specs/。

## 12. 必要源码与研究证据

以下为既有只读核验结论，用于本机定位实现；没有新增研究、模拟或接口实现。原始大报告和私人角色输入不随本四文件交付，实际验收必须使用获准的有效角色输入及匹配引擎。

### 12.1 项目复用位置与官方选择器

固定 SimC：`eed909156d8eccbfca0f284cc271c080949d6a20`。原项目研究基线：`80cb3a8b67ca5b86a23b95cec7f6256e79d70b18`；后续源码核验 HEAD：`5d7165b798d8a7555a74006a1206bd60d8db4331`。两者不混写。

历史教师研究来自多目标场景，不能充当单体或学生证据。本规格只保留公开源码中的字段结构与推断边界，不保留私人报告标识、运行参数或实际数值摘录；开发不依赖这些报告，也不以历史样本规模强制新增接口实验或最终复测。

#### Coba 原生接入和共享

固定只读核验提交：`0abed4d9779d254b0501f8be10632765c1ce718a`，源码版本 8.1.0；尚未安装或锁定发行依赖。

- [LinUCB](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/learners/linucb.py)：现成 predict(context, actions) / learn(context, action, reward, probability)；稠密数值输入、动态候选列表；learn 持续更新模型，可接受负反馈，不按任务自动清空。
- [预测器](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/learners/utilities.py#L6-L25)、[随机状态](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/random.py#L237-L238)：Coba 有独立随机进度；原生序列化仅保存初始 seed，不能当作精确续跑证据。
- [库内序列化工具](https://github.com/VowpalWabbit/coba/blob/0abed4d9779d254b0501f8be10632765c1ce718a/coba/pipes/multiprocessing.py#L107-L142) 用于对象运输；模型持久恢复仍需薄适配验证。不得由此自建第二套学习算法。
- 项目 `projects/sim2gse/task.py:1700–1725` 与 `seed_training.py:1100–1104,1164–1172` 使用线程/线程池，支持同宿主复用实例；原生模拟子进程不构成按任务复制 learner 的理由。
- 项目 `search.py:1688–1690,1824–1833` 保留评分批次；`TaskStore` 和 `result_store.py` 提供存储接缝。原子保存、一次反馈去重及不同进程同时访问的行为尚未验证。

#### GSE 与静态字段边界

项目 `program.py:134–181,264–287`：顶层最多 128 节点、展开最多 4096 点击；WaitClicks 为 2–4096，Loop 身体仅动作；并非此次新增限制。现有编译导出接缝在 `program.py:435`、`codec.py:125`。

以下行号属于原研究基线：`native/src/catalogue.cpp:100,158,184` 的目录 gcd_ms 为 trigger_gcd 基础值，不能冒充角色静态有效GCD。当前01另有战前有效静态快照；本次通用化采集仍须逐项核验生命周期和getter安全，不将旧研究的“尚未接入”当作当前事实。

固定 GSE 外层按钮有独立步进状态，停止普通输入本身不重置；现有固定爆发采用普通序列暂停、原位续接。其独立按钮状态与暂停续接属于已有源码核验，用户当前实机绑定、手动重置和全局设置未实测，不声称游戏验收通过。



#### 项目最高入口、编辑与反馈接缝

下列项目路径相对本仓库根目录，行号对应固定核验基线 `5d7165b798d8a7555a74006a1206bd60d8db4331`；实施后优先按函数名定位，并核对当前行号。全文省略的项目 Python 模块（search.py、task.py、engine.py、program.py、codec.py、result_store.py、burst.py、seed_training.py、sequence.py）位于 `projects/sim2gse/`；task.py 明确指该目录的任务模块，不是同名开发命令脚本。TaskStore 定义在 `projects/sim2gse/search.py:788`；controller.cpp、catalogue.cpp 位于 `projects/sim2gse/native/src/`。S1–S13 中的 `engine/...` 则是 SimC 官方仓库路径，须从对应固定提交链接读取，不是本仓库根目录。

- projects/sim2gse/search.py:144–188为initial_programs，均匀来源在160附近；projects/sim2gse/task.py与projects/sim2gse/search.py均有调用，须统一替换这一个来源。
- projects/sim2gse/search.py:209–472为现有mutate选择及实际编辑体；1898–1904还有调用侧洗牌，不能只换函数内部而留下旧兜底。
- projects/sim2gse/search.py:1688–1690、1824–1833保留request、dps、samples、variance及batches；545–561、2042–2045为现有配对晋级数据。学习反馈按本规格使用共同search批次，不要求新增配对模拟。
- projects/sim2gse/search.py:34定义32/128/256累积目标；score_batch在1761–1764按target−previous形成32/96/128增量；projects/sim2gse/engine.py:348–354读取实际count并核验其为max(1, iterations−1)，samples取该count，必须使用存档实际samples加权。
- projects/sim2gse/search.py的pending尚需保存生成父身份与选择快照，不能依赖可关闭的observability字段；整轮先入队，后续学习不伪称实时重排已排候选。
- 现有TaskStore使用SQLite检查点，save/flush有既有缓存和事务边界；共享模型与反馈去重原子性仍须验证，不能假定不同存储天然跨库原子。
- tests/sim2gse/test_search.py已有run_task/fast_evaluate接缝，适合契约检查，不能代替真实角色静态参数或正式引擎产物。

### 12.2 补充精确绑定与按钮身份

低位单体消费原文：`death_coil,if=cooldown.army_of_the_dead.remains>5|runic_power.deficit<50`。父入口`active_enemies<3`，保留默认high_priority/trinkets/cooldowns及单体更高位Death Coil的让位。不能将其套到同按钮的所有规则。

普通CD原文：`death_and_decay,if=active_enemies>=3&talent.cycle_of_death&(buff.festering_scythe_tt.up|!talent.festering_scythe)&(cooldown.putrefy.charges<cooldown.putrefy.max_charges&(raid_event.adds.exists&raid_event.adds.remains>=duration*0.75|!raid_event.adds.exists&fight_remains>=duration*0.75)&(raid_event.adds.exists&raid_event.adds.count<active_enemies|!raid_event.adds.exists|charges=max_charges))`。位于cooldowns中Outbreak之后、Army/DT之前；默认入口仍先处理high_priority和trinkets。实际条件以固定APL:373为准。

基础按钮、可替换形态及实际执行身份分开：已核验示例包括脓疮85948→镰刀458128、天灾55090→吸血433895、DT1233448→Blightfall1271967；替换依赖天赋或Buff。按钮DT1233448与玩家DT Buff1235391不能混为同一对象。来源为固定SimC职业模块8739–8746、10482–10491、12676–12684及项目catalogue.cpp:53–68,118–161；具体实际形态以同次学生事件为准。

静态费用与动态费用不同，资源收益不能由两张快照相减反推；符文并非通用线性regen。必要费用/恢复复用固定action.cpp:1192–1252,3272–3276、player.cpp:4950–4957,12619–12660及职业模块。静态天赋谓词只解析本批绑定所需项；available不等于当时ready。

### 12.3 八规则数据可获取性与已有数值

以下直接保留已完成的数据来源研究，作为本规格证据附录。这里的历史教师数据不代表本次学生诊断已实现或验收通过。

#### 研究结论

八项规则引用的资源、冷却、充能、Buff、疾病、GCD 和场景表达式，均已找到固定版本 SimC 的取值入口。主要缺口是项目尚未导出这些数据、需绑定正确对象与时点，以及诊断本身尚未计算；不是需要重新制造一套战斗状态。

最小方向是复用现有报告、控制器事件及 SimC 原生状态/表达式，只补规则实际需要的取值。无需为证明这些入口存在运行新模拟。本次仅阅读源码和已有报告，没有修改接口，也没有新模拟或性能测量。

需要特别区分三件事：
1. 项目已有渠道可读取；
2. SimC 已有数据，但项目需补接或指定上下文；
3. “是否违反规则”“是否合理让位”“可避免空闲区间”是根据事实计算的诊断结论，不是一个等着导出的原始字段。

研究基准：SimC eed909156d8eccbfca0f284cc271c080949d6a20。项目源码核验 HEAD 为 5d7165b798d8a7555a74006a1206bd60d8db4331。以下结论针对这些固定版本，不把接口存在等同于接入已实现、已证明无干扰或性能达标。

#### 现成取值渠道

项目控制器已有：时间、输入来源 origin/step、原按钮签名、实际动作身份、GCD 就绪时刻、主资源当前值、当前动作 CD 剩余、普通循环/爆发来源。见项目 controller.cpp:598–664；sequence.py:323–335 解析，380–387 返回报告/轨迹。[P1、P2]

SimC 自带动作快照已有：各资源 current/max；活动 Buff 的对象、层数和剩余。JSON 默认有资源及 Buff 层数；Buff remains 由 full_states 控制输出。见 player_collected_data.cpp:33–79、report_json.cpp:502–515,553–559。[S1、S2]

这些渠道有明确限制：
- 默认动作快照过滤 quiet/constant Buff，未出现不能一律解释为没有该 Buff。
- full_states 的 cooldowns 仅收 c->down() 的对象，stacks 写的是最大充能 c->charges，不是当前充能。打开 full_states 不能解决满充能诊断。
- Buff 汇总 duration 是观察到的平均持续长度，不是当时的 remains。
- 当前项目 trace 只输出主资源，不能因此说已输出符文和符能双资源。
- native_execute 通知位于 execute 调用之前，不是执行后扣资源或上 Buff 的快照。[P3]

#### 八项规则取值矩阵

1. 窗口或满充能释放
需要：Putrefy 当前/最大充能、CD/重充信息，玩家 Dark Transformation Buff；单体源条目另需符能缺口。
怎么取：从绑定的 cooldown_t 对象复用 charges/max_charges/remains/recharge 原生表达式；多充能当前值来自 current_charge，最大值来自 charges；单充能 charges 表达式按就绪情况返回 0/1。DT 对象为玩家 buffs.dark_transformation；符能缺口为 max-current。[S3、S4、S5]
现状/补法：现有报告已有符能和部分 Buff 层数，项目当前动作 trace 有 CD remains；需补接指定 Putrefy 充能及 DT 实时状态，不能使用 full_states.stacks 代替当前充能。
源绑定：AoE Putrefy 是 DT.up OR charges=max_charges；单体其他 Putrefy 条目独立保留。[S6:363,388,391]

2. 特定低优先消费预留
需要：单体低位 Death Coil 条目的 Army 实际 CD 剩余、符能 current/max/deficit、目标数量及源优先上下文。
怎么取：绑定 Army 的 cooldown.remains；资源复用 resources.current/max；目标数复用原生 active_enemies。[S1、S3、S7]
现状/补法：资源渠道已存在，指定其他动作的 CD 需要项目接出。源条件是 Army.remains>5 OR runic_power.deficit<50，不能改写成固定“保留 50 符能”。前序让位属于诊断判断，不是 SimC 缺一个字段。[S6:394]

3. 近满资源消费
需要：符能缺口、可用符文；Sudden Doom.react；Essence 层数、最大层数、剩余；Vampiric Strike.react；epidemic_prio。
怎么取：资源 current/max；Buff 层数/剩余及 max_stack()/stack_react()；epidemic_prio 的完整右侧为：
active_enemies>=3 & !buff.forbidden_knowledge.up | active_enemies>=4 & buff.forbidden_knowledge.up
因此还需 Forbidden Knowledge Buff，而不是一个静态天赋开关。[S6:365,406；S8]
现状/补法：符能、符文和部分 Buff 层数在原生报告已有；max_stack、react、实时剩余需指定对象接出。受控模式不执行原 APL 选招，不能盲读可能未被赋值的 variable.current_value_；最小做法是绑定上述有限右侧表达式，复用现成目标数和 Buff 状态，不重建 APL 解释器。[S9、P3]

4. 短窗口内及时使用指定动作
需要：Vampiric Strike.up、Essence.up/remains，以及该条动作上下文中的 gcd；基础按钮与实际替换动作身份。
怎么取：绑定 Buff 对象；APL gcd 直接复用 action_t::gcd()，实现由动作及角色状态计算；原按钮和实际动作关联沿用控制器。[S8、S10、P1]
适用阶段：按2026-10-16用户确认，以下实时取值与独立调序属于后续02/03；01只保留绑定及unknown，不预测动态相位。
现状/补法：身份关联现成；Buff 实时剩余和对应动作 gcd 尚需接出。catalogue 的 trigger_gcd 是基础值，gcd_ready 是绝对就绪时刻，均不能代替该谓词的 gcd。原条件保留 Vampiric.up AND Essence.up AND Essence.remains<gcd*3。[S6:360]

5. 普通循环配合受保护爆发
需要：普通/爆发输入计划、来源位置、暂停与续接、实际尝试/执行，以及相关增益状态。
怎么取：复用 sequence.py 的输入计划与来源映射、controller 的事件与动作关联；实际增益用对应 Buff 对象读取。[P1、P2、S5]
现状/补法：输入和来源主要已有，不需要新造时间调度器；需明确状态读取阶段。爆发按钮被尝试不能证明已成功施放，也不能从 execute 前通知推断增益已生效。本项不改变固定爆发内容或节奏。

6. 普通 CD 在源条件允许时使用
需要：D&D 自身 CD/当前及最大充能、Putrefy 充能、Festering Scythe TT.up、active_enemies、raid_event.adds.exists/remains/count、fight_remains、源谓词的 duration 及静态天赋条件。
怎么取：CD/Buff 使用上述对象；场景量复用 SimC 原生表达式，完整入口见下一节。[S3、S5、S7、S11、S12]
现状/补法：原生取值入口都存在，项目需只接出该绑定需要的值。重要区别：APL 的裸 duration 是通用 DoT 表达式，不是 D&D 地面区域持续时间；不能以另一字段替换源条件。[S10、S12、S5]
源条件的目标数、天赋、镰刀、Putrefy 充能、战斗/小怪剩余以及小怪数量组合，均保留，不改成 CD 好就放。[S6:373]

7. 必要持续效果按条件补齐
需要：玩家自己全场 Dread Plague 的 active_dots、Putrefy CD、当前 time、gcd.max、fight_remains 和 adds 相关条件。
怎么取：active_dots 由 dot.internal_id 索引玩家的 active_dots 计数；time、gcd.max 和场景量复用原生表达式。[S10:3632–3640；S7:14382–14389；S11]
现状/补法：全场计数已经存在，无需为判断“全场为零”在每次输入自行遍历所有目标；项目需接出。它不是“当前目标没有病”。保留 Outbreak 的天赋、Putrefy 剩余/开场、小怪及剩余时长完整条件。[S6:372]

8. 减少可避免 GCD 空闲
需要的原始事实：GCD 就绪、执行/引导占用、控制状态、实际输入/空点击/排队、当前动作已计算的 ready_now，以及有限候选所需的资源/CD/Buff 等条件。
怎么取：控制器已有 gcd_ready、输入/队列事件、执行/引导剩余及当前实际动作检查结果。[P1:302–322,702,812–835]
现状/补法：复用已经算出的事实，不为盘点或诊断重新调用有副作用的 ready。其他动作虽存在 ready 接口，但不能把“有这个函数”当成免费且安全的全动作探测器。
真正尚缺的是诊断推导：哪个具体动作在当时满足完整相关规则、空闲何时开始/结束、是否应让位。它们不是缺失的 SimC 原始数据字段。状态、反应历史或前序条件不足时保留 unknown，不把一个时点外推为整段可用。

#### 表达式准确入口

gcd：action.cpp:3284–3285 绑定 action_t::gcd；1285–1326 为计算逻辑。随具体动作及角色状态计算。[S10]

gcd.max：action.cpp:3764–3793；使用 player.base_gcd、attack_haste/spell_haste 与 action.min_gcd，min_gcd 为零时采用 750ms 下限。应复用原生表达式并保留动作上下文，不自行统一用 1.5 秒或另一技能 GCD。[S10]

Buff max_stack：buff.cpp:450–455 读取 max_stack()。Buff react：485–503 读取 stack_react()，2004–2015 根据 current_stack、逐层 stack_react_time 和当前时间计算可反应层数。表达式初始化会设置 reactable，影响触发时反应时刻的记录（491–499、2697–2708）。数据原生可算，但依赖正确初始化和反应历史；缺历史不能用 up 顶替。[S8]

epidemic_prio：原变量读取入口 player.cpp:11939–11970；赋值入口 variable.cpp:260–267。受控模式不跑原 APL 时，使用已绑定的源右侧和原生状态，不能假设缓存变量曾被更新。[S6、S7、S9、P3]

fight_remains：sim.cpp:3582–3585 为 expected_iteration_time-event_mgr.current_time，是当时引擎已有的计划状态，不需读取最终战斗结果。[S11]

adds：sim.cpp:3718–3749 构造 raid_event 表达式；raid_event.cpp:3045–3084 匹配事件和 exists，3087–3094 的 remains 取活跃匹配事件的最长剩余，3179–3187 的 count 取对应 adds 事件 count，pull 则取 spawn_parameters.size。无匹配事件时 exists/remains/count 为 0，in/cooldown 为极大值（3068–3077）；不是一律 unknown。count 不是当前 active_enemies。[S11、S13]

D&D duration：action.cpp:3372–3373 转入 dot_t::create_expression；dot.cpp:448–456 在无 dot state 时返回 0，否则读取 composite_dot_duration(dot->state)。D&D 实现将 dot_duration/base_tick_time 设为 0（sc_death_knight.cpp:9628），实际地面事件 duration 使用 data().duration()（9640–9654）；地面剩余还有 death_and_decay.remains→active_dnds.back()->remaining_time()（14595–14609）。源 APL duration 与地面持续时间是两个不同的原生值，均能找到入口，不得静默互换。本次未跑数值验证，不断言所有状态下裸 duration 恒为零。[S10、S12、S5]

#### 公开报告字段结构与推断边界

字段依据固定公开源码 `player_collected_data.cpp:33–79` 与 `report_json.cpp:474–559`（S1、S2），不使用私人报告摘录。动作记录位于 `sim.players[].collected_data.action_sequence`。

- 动作条目可输出 `time`、`id`、`name`、`target`、`spell_name`、`queue_failed`；等待条目输出 `wait`。资源快照由 `resources` 与 `resources_max` 按相关资源类型输出，不能将教师动作记录当作新GSE学生轨迹。
- Buff记录包含 `id`、`name`、`stacks`；仅启用 `full_states` 时输出该记录的 `remains`。采集会过滤未激活、quiet或constant的Buff，因此缺项不能一概等同于不存在；层数也不能代替react及反应历史。
- 启用完整状态时还可输出冷却的 `id`、`name`、`stacks`、`remains` 及目标debuff记录；采集冷却时只记录 `down()` 的对象。读取前须核对对应配置、采集时点及对象身份，不能把未记录状态补成已知值。
- 这些动作快照不包含完整动作ready证据或GCD表达式求值。Buff汇总的持续时间或覆盖率不能替代指定时刻的剩余时长；同名对象须按身份区分。缺少动态状态时保留unknown，不由汇总量或相似字段倒推。

#### 可用结论与未实施事项

可确认：八规则所需主要原始数据与指定表达式均有源码入口；现有报告可复用资源和部分 Buff 快照，现有控制器可复用输入/队列/动作来源。满充能、react、GCD 语义、全场疾病计数及 D&D duration 都不能从相似字段猜出。

项目待补：指定对象的少量实时值及明确时点；受控状态下有限变量表达式的正确绑定；从原始事实到前序让位和空闲区间的诊断计算。

尚未声称：接口已接入、观察不改变模拟、任何性能阈值通过、八条规则在学生轨迹上全部可判定。上述属于后续接入与诊断工作，不妨碍本次数据可获取性盘点凭源码完成。上述字段盘点依据公开源码，不依赖私人报告或新增模拟。

#### 可复核来源

项目来源 P1–P4 均相对仓库根目录，固定 HEAD 5d7165b798d8a7555a74006a1206bd60d8db4331：
P1 projects/sim2gse/native/src/controller.cpp:302–322,598–664,702,812–835。
P2 projects/sim2gse/sequence.py:180–188,323–335,380–387。
P3 projects/sim2gse/native/hooks/040-control-connections.patch:106–112,465–469。
P4 projects/sim2gse/native/src/catalogue.cpp:71–100,118–161。

SimC 官方固定提交源码：
S1 engine/player/player_collected_data.cpp:33–79
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/player/player_collected_data.cpp#L33-L79
S2 engine/report/json/report_json.cpp:474–559
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/report/json/report_json.cpp#L474-L559
S3 engine/sim/cooldown.cpp:553–599
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/cooldown.cpp#L553-L599
S4 engine/sim/cooldown.hpp:31–51,78–82
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/cooldown.hpp#L31-L82
S5 engine/class_modules/sc_death_knight.cpp:9628–9654,14595–14609,15363,15389,16235–16236,16263–16264
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/sc_death_knight.cpp
S6 engine/class_modules/apl/apl_death_knight.cpp:349–406
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/class_modules/apl/apl_death_knight.cpp#L349-L406
S7 engine/player/player.cpp:11939–11970,14382–14389
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/player/player.cpp
S8 engine/buff/buff.cpp:450–455,485–503,2004–2015,2697–2708
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/buff/buff.cpp
S9 engine/action/variable.cpp:260–267
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/variable.cpp#L260-L267
S10 engine/action/action.cpp:1285–1326,3266–3285,3372–3373,3632–3640,3764–3793
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/action.cpp
S11 engine/sim/sim.cpp:3576–3585,3718–3749
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/sim.cpp
S12 engine/action/dot.cpp:448–456
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/action/dot.cpp#L448-L456
S13 engine/sim/raid_event.cpp:3045–3094,3179–3187
https://github.com/simulationcraft/simc/blob/eed909156d8eccbfca0f284cc271c080949d6a20/engine/sim/raid_event.cpp

开发不依赖私人报告或特定云端路径；上述固定公开源码足以定位字段、采集条件及推断边界。仓库回归使用公开数据或独立构造的最小mock；真实角色报告仅在获准的本地验证范围内保留，不随仓库交付，不将其缺失误报为仓库文件丢失。
