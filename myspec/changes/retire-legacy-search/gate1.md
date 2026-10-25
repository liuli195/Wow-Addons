# 门禁一——完整退役旧正式搜索

## 核心摘要

- 状态：用户已确认实施到验收结束。授权记录：`Sentinel_bf699fe7cc388191af5d87ef2f55f1ca`；此前展示范围及成本记录：`Sentinel_871898934bd481919b37a485d17d4660`。
- 目标：当前产品及受管工具无可执行旧正式搜索；新GA、训练、报告、导入与可靠恢复保持。保留旧完整成果只读验真和程序重新评分；旧未完任务不再提供继续入口。
- 流程：Full。固定基线`6b5861fc548ce9753a03f1bc78453ef5cad01faf`；已授权独立轻量工作树`/workspace/scratch/0af43d0efb8f/wow-addons-retire-legacy-search`，分支`codex/retire-legacy-search`。主工作树有其他测试修复，不改主树。
- 安排：一个完整纵向退役票据，由当前实施代理串行完成，已提交固定差异交独立审查；不分多线重复修改配置。
- 已有调查：固定扫描全部1,838受管文件及126个Python文件；普通正式链仅走GA，但旧benchmark仍从Git历史提取执行。旧CI函数无生产调用，旧配置与历史验真共用，不能整文件删除。
- Astra独审修正：共用`replace_file`测试保留到运行时测试；v1仅只读验真，旧pending意图不得补写发布；失效参数与有效参考评价/Reset验证分清。
- 术语沿用领域文档：按键动作块、完整点击行为、正式冠军、训练代表。旧算法执行退役不等于删除旧成果。
- 公开接缝：单场run/resume、双场HTTP读取/恢复、训练公开入口、成果读取；拒绝发生于引擎/持久化动作前。无新增测试专用生产入口。
- 风险：源码全量身份使退役前新GA未完任务也可能拒绝跨版本恢复；用户已明确知情，不放宽保护。历史只读与当前写入须隔离。
- 预计整体90–150分钟及少量必要检查；新增磁盘预计不足30MB。超过15分钟投入已获批准；不新跑AB/重训/引擎构建，不删原数据。明显扩大成本、行为或磁盘超过516MB先报告。

## 已加载与复用的流程依据

实际读取当前管理源的dev-flow（含requirements/implementation）、subagent-policy、codebase-design、grill-with-docs及grilling/domain-modeling、to-spec、to-tickets、tdd（含tests/mocking）、code-review、build-and-verify、my-spec。已确认的范围、兼容选项及公开接缝不重复发问；设计前沿无新未决产品选择。MySpec主规格最终差异确认仍保留，不能以本门禁替代。

## 确认后进入的下一步

按[票01](issues/01-retire-legacy-execution.md)实施，保存最小红绿与静态反查证据；固定提交范围独审并处理阻塞项。最终MySpec完整预览交付前不改`myspec/specs/`，不擅自合并主干。
