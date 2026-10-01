# 第01票验证记录

测试接缝：技能单一 `scripts/simdata.py` 命令行入口；全部数据和联接在临时合成目录。

## 门禁一证据

父线程在消息 Sentinel_7af6445967d48191a3864e6dded28700 完整展示门禁一；用户在 Sentinel_169873e099008191b7ce3c9b82730cc7 回复“确认执行吧”。确认分支 codex/sim2gse-data-management，同一工作树、固定基线 f554538993161cc045d19c4ed47d261f709f741b，六票串行主实施，父线程每票远端独立审查。主实施 GPT6.1sol low（低），无本机架构或审查角色。

## 红绿记录

命令：`.venv/Scripts/python.exe -B .agents/skills/sim2gse-data/scripts/tests/test_cli.py`。

1. inventory 红：入口文件不存在，退出2；实现后1项通过。
2. status 红：命令未支持，退出2；实现后2项通过。
3. 生产写入预检红：命令未支持，未产生预期结构化拒绝；实现后3项通过。
4. 共用目录联接红：命令未支持，退出2；实现后4项通过，覆盖预览、两次显式安装及双路径结果相同。
5. 错误配置根红：布尔根触发未捕获类型错误，退出1；修复后通过。
6. 补充有界扫描、相对根/根不一致拒绝、根和子目录重解析点拒绝、既有普通目录不覆盖；7项通过，未跳过。

末次原始输出摘要（合成测试名，无私人路径）：

```text
Ran 7 tests in 1.691s
OK
```

统一构建使用已安装CLI包的 bin/build-and-verify.js 入口，并设置进程级 BUILD_AND_VERIFY_PYTHON 指向仓库现有虚拟环境；未改全局配置或安装软件。原始末尾输出：

```text
checked: build.sim2gse-product, build.assets
status: passed
```

默认容量/保留/频率均未设置；只读盘点不创建索引且文件集合不变。本票未登记写入、迁移、压缩或删除真实历史，未启用生产或计划任务。固定提交后的正式统一验证及远端独立审查结果由本轮交付消息另行记录。
