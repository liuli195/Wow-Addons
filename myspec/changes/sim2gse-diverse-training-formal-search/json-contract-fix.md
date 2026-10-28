# 正式训练成果读取：v3 JSON契约修复

授权：用户批准单入口修复、真实存储回归、普通回归与两轴独立复审，预算从2026-10-28 07:23 UTC起35–65分钟，新增修复产物小于10MB。原四组训练成果和约1.20GB专项现场保留，不重训练、不修改快照或检查点。本提交之后停止等待两轴复审，尚未运行正式搜索或统一验证。

## 最小修改

seed_training.selected_contract_version的v3分支复用现有decode函数，把evaluation的JSON文本规范为对象后验证publication。损坏JSON与非对象明确报ValueError，并保留既有“发布人数”错误上下文。函数不修改传入快照；旧v1/v2分支不变。没有修改result_store全局读取约定、算法参数或失败重试政策。

## 真实红绿证据

接缝采用用户明确批准的真实Parquet写入→正式result_store.read_records读取→selected_contract_version，扩展既有test_connected_consumer_reads_writes_without_old_user_installation核心，不新增真实组。临时接入项目与真实技能副本仍由原夹具建立，使用SELECTED_V2_SCHEMA写入v3行，读取后明确断言evaluation实际是字符串再调用契约入口，不以已解码内存字典替代存储证据。另有7项内存负例覆盖损坏JSON、JSON数组/null/数值/文本及原生非对象。

命令：现有Python执行 -m pytest -q tests/sim2gse/test_data_store_connection.py -p no:cacheprovider --basetemp=.local/t/json-r --tb=short。json-contract-red.txt实际8失败、2通过、exit1，真实存储接缝复现str.get错误。

最小解码修复后相同检查使用独立临时目录.local/t/json-g，json-contract-green.txt实际10通过，0.77秒，exit0。随后全普通回归发现1项既有错误信息匹配不兼容（json-contract-regression.txt），未隐藏失败；仅给新增错误补回“发布人数”上下文后，最终全回归json-contract-regression-final.txt实际528通过、168子测试通过、4真实排除，8.38秒，exit0。

全回归命令：现有Python执行 -m pytest -q tests/sim2gse -m 'not real' -p no:cacheprovider --tb=short。全真实页面搜索尚未重跑，不将本回归称为完整端到端通过。

## 后续恢复边界

修复改变规则源码哈希，不能改写旧失败搜索身份或强行继续。两轴复审及正式验证通过后，应创建明确的新搜索记录，复用原隔离中心中本轮已发布的四组8条v3快照，并逐条核对适用训练来源。原四组训练已自然完成，不需要重训。规格预览需求内容不变，但最终交付前输入指纹须刷新，正式规格未应用。未推送、合并或发布。
