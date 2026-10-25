# GSE冠军、双场、恢复与身份整族分层

## Problem Statement

全仓方向是“真实层保最简产品主路和独立跨边界风险，规则组合批量进入内存”，不是继续两处小优化。阶段三代码abb20fc的官方43项通过，墙钟59.937秒、GSE真实49.41秒，没有测出提速。此前阶段二57.672秒不能作为统计基线。Astra按阶段二事件补位估计约8秒GSE拖尾空间，只是上限线索，非收益承诺。

## Solution

本次只规划GSE四模块整族；逐测试承接见mapping.md。已有纯内存项不重复改造，不把减少ID数当收益。在本四模块内保留一条HTTP双场编排主路（真实任务、两场结果、导出集合、发布/读取；评分由既有champion_engine替代），其他真实项仅证明物理损坏、文件锁/CAS、持久化恢复或独立进程边界，不能再为普通规则组合重复完整搜索。

优先复用champion_evidence_fixture.formal_cohort/training_history、memory_ga(formal=True)、TaskStore(connection=sqlite3.connect(':memory:'), reusable_database=':memory:', report_locations={})；显式输入只替换外部I/O，不重写排序、身份、恢复或评分算法。

## User Stories

- 用户仍可由HTTP双场入口获得真实两场及集合结果；实际游戏验收不由本测试替代。
- 普通规则完整、错误分类/冻结/次数/来源/旧成果选择/编码组合在内存内验证真实生产算法。
- 数据损坏、跨文件与数据库恢复、CAS竞争、身份产物篡改仍由最小真实代表实际触发，失败不能被mock消去。

## Implementation Decisions

四测试文件为主范围，允许修改已有champion_evidence_fixture.py以补显式旧v1来源数据；不得加数据库模拟器、通用虚拟文件系统或新调度器。唯一拟新增生产接缝：将task._run_optimize中已存在的起点合并/来源标记/正式冠军适配连续逻辑原样提取为一个内部函数，仍由原路径调用；不改行为、默认、样本和预算。这是本Gate1需明确批准的范围，不属于此前两票授权。若不批准该抽取，十来源整项暂保真实，不能以memory_ga已有起点冒充生产组装验证。

## Testing Decisions

普通层运行真实函数和SQLite SQL；不得标real躲守卫。保留真实代表的物理断言，组合断言搬迁后以原断言到新nodeid的一一清单核验。最终普通官方守卫、inventory互补、全真实组及43项无缓存完整验证，不变正式配置/60秒预算。运行成本和验证次序见gate1.md。

## Out of Scope

不在本票同时修改gear/HUD/DK/skill/checker；其真实主路分别保三引擎/浏览器持久化、素材部署备份、CLI生产Lua报告、隔离安装公开入口、真实Git补丁往返。C++机制和Windows进程线程句柄释放代表（test_search.py末段）不动。Lua暂停ROI审查但非内存要求豁免；A/B不在本票重跑。不合并主干、发布或安装工具。

## Further Notes

固定云端cfcf8954937282053b38c641a05d06b6e413eafa、远端b85afd617158533d6129778c06cfc78e44d07c2b，同树06cdc5560f640a2f4747f994cb9678ddd8b1cddd。已读取仓规、领域词汇、repository-validation/user-workflow正式规格；正式规格不修改。仅规划，尚未授权本整族实施。
