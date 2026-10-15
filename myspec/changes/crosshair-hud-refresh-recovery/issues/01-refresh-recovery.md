# 修复血量与符能显示的及时性和恢复

Status: ready-for-agent
Gate: 门禁一已确认，实施完成，等待正式验证与独立审查
Blocked by: 正式固定基线验证、独立审查和游戏实测分别待报告
Parent: [血量与符能刷新恢复](../spec.md)

## What to build

在同一圆弧显示链端到端交付：血量预测开启、血能保底恢复、最大生命值次帧收敛。三组共享读取与渲染接缝，作为一张纵向票串行实施。

## Acceptance criteria

- [ ] 先新增/修改真实事件到遮罩的失败测试，记录红灯，再进行最小实现并转绿。
- [ ] 血量usePredicted=true且符能unmodified=false；事件返回前已将新角度交给遮罩。
- [ ] 无后续资源事件时，既有ticker能够读取新血/能快照并更新遮罩。
- [ ] API失败保留旧值，恢复后仅靠ticker即可恢复；秘密值哨兵原样到达绘制。
- [ ] 隐藏、总开关关闭、单项关闭不增加该弧周期查询；恢复首个显示状态采样新值；死亡复活可恢复且不强制填满/置灰。
- [ ] 两种最大生命值事件即时读取，同轮只排一个After(0)；手动推进下一帧后显示最终输入。
- [ ] 排队后关闭/隐藏、补读失败、后续再次触发都能正确处理且pending不永久挂起。
- [ ] 十个稳定可见tick为每个启用弧新增十次周期查询，无新增常驻timer，其他指示器节奏不变。
- [ ] 既有曲线、受限值、血骑士功能、可见性、配置、解锁回归通过；记录实际环境与耗时。
- [ ] 独立Reviewer核验实际差异与完整验收证据；未做的游戏实测明确列未验。

## Public test seam

登录并启用HUD→玩家事件/计时/可见性→真实Core和Elements→实际遮罩，复用现有血骑士功能测试框架；新增可推进的零延迟队列只用于观察真实下一帧语义。

## Risks and recovery

开启预测是已批准的取值语义变更，不承诺消除特定毫秒延迟；失败时保留最近成功读数再试。秘密值不能用普通比较推导变化。出现范围扩大、接口不支持或额外性能成本超出方案时停止并报告，不自行加架构。

## Comments

2026-10-15：用户已确认本票内容与粒度；尚未展示并取得门禁一，不允许实施、建分支或部署。开发安排推荐串行子代理、完成后独立子代理审查。


2026-10-15 实施记录：主代理转交用户消息 Sentinel_24e6cf04e5648191832a0ef66b35ecb0 已确认完整门禁一。在同一云端工作树 /workspace/shared/wow-addons、分支 codex/fix-crosshair-hud-refresh、固定基线 80cb3a8b67ca5b86a23b95cec7f6256e79d70b18 实施。具名角色入口不可用，回退通用 Implementer（实施者），实际 gpt-6.1-sol medium，可写但仅本票范围；不提交、不部署、不改正式规格。

三组 TDD（测试驱动开发）均由真实模块登录、事件/计时器到真实 Elements 遮罩旋转观察，复用 test_blood_dk_features.py；仅游戏接口、计时器与显示区域为边界适配器，新增场景 After(0) 手动推进下一帧。每组先运行红灯才改生产代码，原始输出位于 .local/tests/hud-refresh/：

- cycle1-red.txt：预测参数失败，1 failed in 0.03s；cycle1-green.txt：1 passed in 0.02s。事件即时绘制及 usePredicted=true、unmodified=false；保留低层曲线、秘密值及参数断言。最初测试夹具把复用素材误写为独立文件名，修正 Layer 定位后才采集有效红灯，产品尚未修改。
- cycle2-red.txt：无事件快照变更后遮罩仍为旧角度，1 failed in 0.04s；cycle2-green.txt：2 passed in 0.03s。既有 ticker 补读、失败保旧及恢复、秘密值直达、隐藏与恢复、总/单项开关、demo（演示）与10次查询计数。最终扩充双弧各10次、单独血弧/能量弧各10次、双关/隐藏/总关0次，以及首次显示前已采样、死亡/复活无额外资源事件仅 ticker 恢复。
- cycle3-red.txt：modifier（最大生命修正）事件未即时更新，1 failed in 0.03s；cycle3-green.txt：3 passed in 0.04s。两种最大生命事件即时读取，共用一个零延迟补读；隐藏/总关/单关/demo后回调不读，失败后可以再次排队。

精确红绿命令分别为：
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py -k resource_events --durations=0
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py -k resource_ticker --durations=0
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py -k 'resource_events or resource_ticker' --durations=0
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py -k max_health_events --durations=0
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py -k 'resource_events or resource_ticker or max_health_events' --durations=0

相关回归命令：
.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD/test_logic.py tests/addons/MYUI_CrosshairHUD/test_core_readings.py tests/addons/MYUI_CrosshairHUD/test_unlock_contract.py tests/addons/MYUI_CrosshairHUD/test_config_color.py tests/addons/MYUI_CrosshairHUD/test_config_plan.py tests/addons/MYUI_CrosshairHUD/test_visibility.py tests/addons/MYUI_CrosshairHUD/test_blood_dk_features.py --durations=0
最终结果 regression-final.txt：43 passed in 0.72s。另 .tools/lua-5.1.5/src/luac -p addons/MYUI_CrosshairHUD/Core.lua 与 git diff --check 退出0。Linux云端 Lua 5.1.5/Python 3.12 离线行为证据；不代表游戏实测、真实帧率或 Windows 正式完整验证。主代理负责正式提交、固定基线 Build and Verify（构建与验证）和独立审查；本票尚未最终验收。

门禁一确认记录：2026-10-15，用户 Sentinel_24e6cf04e5648191832a0ef66b35ecb0 回复完整门禁 Sentinel_f9a7b1d5b31c819189056657bf2f0854 确认。已在同一工作树创建 codex/fix-crosshair-hud-refresh；后续交付仍待门禁二。

API 核对：已直接读取固定提交 4e3cbb8c5609e4bfc332c0aebbfa4d79731fab59 的官方 UnitDocumentation.lua，UnitMaxHealthModifiersChanged 定义确有 LiteralName=UNIT_MAX_HEALTH_MODIFIERS_CHANGED，并有 unitTarget 负载；事件负载为受限数据，本实现不读、不比较其比例，仅经现有玩家单位注册触发重新采样。来源：https://github.com/Gethe/wow-ui-source/blob/4e3cbb8c5609e4bfc332c0aebbfa4d79731fab59/Interface/AddOns/Blizzard_APIDocumentationGenerated/UnitDocumentation.lua#L4059-L4069

2026-10-15 独立审查P3返工：新增demo中发送UNIT_MAX_HEALTH_MODIFIERS_CHANGED后真实血量查询计数保持不变的断言，先红（review-demo-red.txt，1 failed in 0.04s），再仅对此新增事件在demo下提前Refresh并返回；不更改旧健康事件即时读取语义。相同max_health_events命令转绿（review-demo-green.txt，1 passed in 0.02s）；上述7文件相关回归命令43 passed in 0.66s（review-demo-regression.txt）。luac -p及git diff --check退出0。未提交，等待独立修复差异复审。
