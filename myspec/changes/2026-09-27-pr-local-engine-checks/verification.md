# 验证记录

固定基线：`adf7414baa175070b7e183b31b3eafb6fa204996`。工作树：`D:/My Project/Wow Addons`；分支：`codex/pr-local-engine-checks`。

| 场景 | 入口 | 结果 |
| --- | --- | --- |
| 红灯：PR 构建 | `build-and-verify build --project . --pr` | 引擎构建仍运行，`excluded-by-pr` 为空；验收断言失败。 |
| 红灯：PR 完整验证 | `build-and-verify verify --project . --pr --full` | Sim2GSE 测试组仍运行，226 passed、83 subtests passed；验收断言失败。 |
| 绿灯：PR 构建 | 同上 | `status: passed`；仅 `build.assets`，排除 `build.sim2gse-product`。 |
| 绿灯：PR 完整验证 | 同上 | `status: passed`；36 项检查，排除 `verify.sim2gse`。 |
| PR 环境准备 | `pwsh -NoProfile -File scripts/dev/setup.ps1 -Pr` | 通过；仅安装 PR 所需依赖，未进入引擎同步分支。 |
| 本机环境准备 | `pwsh -NoProfile -File scripts/dev/setup.ps1` | 通过；保留引擎依赖准备。 |
| 本机构建＋完整验证 | 先 `build-and-verify build --project .`，再 `build-and-verify verify --project . --full --performance-report` | 均通过；构建 13.55 秒、验证 39.74 秒、合计 53.29 秒；2 个构建目标、37 项验证，Sim2GSE 测试组仍执行。 |
| 开发检查器回归 | `.venv/Scripts/python.exe tests/dev/test_checks.py` | 通过。 |
| 测试入口清单 | `.venv/Scripts/python.exe tests/dev/test_inventory.py` | 通过。 |
| PR 固定基线验证 | `build-and-verify verify --project . --pr --base adf7414baa175070b7e183b31b3eafb6fa204996` | `status: passed`，36 项，排除 `verify.sim2gse`。 |
| 本机固定基线验证 | `build-and-verify verify --project . --base adf7414baa175070b7e183b31b3eafb6fa204996` | `status: passed`，37 项。 |
| MySpec 更新预览 | `myspec validate-delta`、`apply-delta` 到预览目录、`validate-main`、`diff` | 均通过；只修改既有 CI 完整验证要求，主规格未动。 |

原始输出保存在忽略目录 `.local/pr-local-engine-checks/`。PR 远端检查和独立审查仍待完成；本文件不将它们标为已通过。
