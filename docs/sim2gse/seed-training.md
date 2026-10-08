# 人工启动的起点整理

先人工清洗材料，登记到现有数据中心。入口不会自动解释复杂宏，也不会访问网络或安装到游戏。待筛选和已入选是同一中心中的逻辑记录；普通搜索接入以对应开发票完成为准。

## 登记

清洗件是一个对象，包含label（名称）、class_name（职业）、spec（专精）、source（来源）、original（原件文本）、instructions（使用说明）、semantic（语义状态）、changes（清洗说明列表）、family（结构家族）、core（核心分组片段）和program（搜索程序）。semantic使用preserved（语义保留）、rewritten（明确改写）或unsupported（当前不可表达）。不可表达材料同样登记原件和原因，程序必须为空列表，不参与训练；通过list --state unsupported（查看不可表达材料）读取。

示例：

```json
{
  "label": "示例",
  "class_name": "deathknight",
  "spec": "unholy",
  "source": "作者页面及版本",
  "original": "原件文本或完整记录",
  "instructions": "连续普通按键",
  "semantic": "rewritten",
  "changes": ["明确记录删除或替换"],
  "family": "人工指定的结构家族",
  "core": [["putrefy"], ["death_coil"]],
  "program": [["outbreak"], ["putrefy"], ["death_coil"]]
}
```

从目标工作树执行，`--project`指向已经接入数据存储、拥有现有data（数据中心）目录的主项目，不会新建数据中心或用户技能链接：

```powershell
.venv/Scripts/python.exe projects/sim2gse/seed_training.py --project "D:\My Project\Wow Addons" register "清洗件.json"
.venv/Scripts/python.exe projects/sim2gse/seed_training.py --project "D:\My Project\Wow Addons" run
.venv/Scripts/python.exe projects/sim2gse/seed_training.py --project "D:\My Project\Wow Addons" list --state selected --targets 1
.venv/Scripts/python.exe projects/sim2gse/seed_training.py --project "D:\My Project\Wow Addons" list --state processed --targets 5
```

默认依次处理1和5目标；`--targets 1`可以只处理单体。默认模板来自锁定引擎配套邪恶角色。完整模板供真实模拟使用，身份解析副本不参与伤害模拟。实际沿用项目原生参数，包括关闭消耗品；模板、引擎、规则和实际参数均进入处理身份，不与外部默认报告成绩混排。

每个候选独立搜索最多5个完整轮次、每轮最多16候选、600秒上限，缓存不能导致额外轮次。之后以三个固定独立随机条件复测，成绩代表只在可信提升时替换；不同家族可保留复测过的初始结构，最多4个新增代表。日志起手不自动认定为循环，清洗者需确认核心与回绕含义。

没有新材料时不重复搜索。发布失败时旧库保持，已保存处理结果可重新发布；条件改变时重新评估。处理失败返回非零退出码，用processed（已处理记录）查看原因。暂时不可读的存储不会被当成空库。

日常执行只输出简短状态，不生成报告。运行目录只保留现有任务检查点和必要临时文件，业务材料、成绩及起点快照通过共享数据中心保存。ABC和全量材料需分别完成验收，不将开发冒烟当作游戏验收。
