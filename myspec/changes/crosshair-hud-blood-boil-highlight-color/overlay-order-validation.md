# 沸点填充遮挡恢复验证

日期：2026-10-11 UTC。票据03为既有高亮/满格功能的游戏验收失败恢复，沿用已批准登录/事件/设置到真实 Elements（绘制模块）纹理接缝。

## 身份与范围

- 同一云端工作树：`/workspace/shared/wow-addons`。
- 分支：`codex/hud-blood-boil-highlight-color`。
- 增量固定基线：`d08373866c2a82fdbad49c19459bc6acd8bd5547`；起始 tree（文件树）：`54d408228e51cbe908adaec6dcd67d20a9465920`，起始工作树干净。
- 父级提供远端部署提交 `26050c06462da7b22a230601cd7e91bd2e4b2773` 的同树核验。该对象不在当前云端对象库；本票以可解析的云端基线绑定验证，不声称独立读取远端对象。
- 用户两张截图显示右侧红色计时条被青色能量覆盖；黄色属于游戏场景背景。生产左侧凝固之血与临时探针不同：原生填充框架位于HUD+1，背景位于HUD-1。
- 产品差异只在绘制模块：原纹理/遮罩创建辅助函数接受可选父级，默认仍为原HUD；创建一个与HUD等大、禁鼠标的透明子Frame（框架），层级HUD+1，右细弧填充、遮罩和灵打刻度共用它。细弧填充仍为ARTWORK（图稿层）子层1、刻度子层2；细弧背景仍在原HUD。
- 摆放、遮罩锚点、整体缩放、素材、颜色、独立透明度、镜像遮罩方向和倒计时算法完全沿用。未修改NativeBlood（原生凝固之血）、Core（核心逻辑）、配置或素材，未复制增益容器、受限数值绑定或原生径向算法，未增加每帧排序。

## 红灯到绿灯

复用既有Lua 5.1.5沙箱，只补记录实际请求的框架父级、层级、图层、子层、锚点及禁鼠标实参，不模拟游戏像素合成。

1. 产品仍是基线时，从真实登录入口同时加载NativeBlood；通过50842 SHOW（高亮出现）建立满格提示并观察生产左右条。单一新场景退出1：`right fine fill must use a child frame above power, like production native blood`；`1 failed, 25 deselected in 0.10s`。原始日志：`.local/tests/hud-overlay-order/tdd-red.log`。
2. 红灯实际请求：能量`HUD/5/ARTWORK/1`，左生产填充层级6、背景层级4，右填充`HUD/5/ARTWORK/1`、遮罩父级HUD、刻度`HUD/5/ARTWORK/2`。
3. 最小产品修复后，同一入口退出0：`1 passed, 25 deselected in 0.04s`。实际请求为右填充`child/6/ARTWORK/1`、遮罩父级同一child（子框架）、刻度`child/6/ARTWORK/2`，左生产和能量层级保持原样。原始日志：`.local/tests/hud-overlay-order/tdd-green.log`。
4. 新半格断言的首次手写期望误为-557°，该次检查明确失败；依据既有已确认右弧的满格-609°、空格-713°修正为半格-661°后转绿。仅修正新测试样例，产品角度算法未修改。

新场景覆盖：无计时高亮满格、跨三秒静止、HIDE（高亮消失）隐藏、有效消费后的原红色三秒计时满格与半格、0.5/1/2缩放、到期隐藏后重现、单项及总开关关闭/恢复、刻度始终位于细弧之上；核对能量、细弧背景、原生凝固之血、探针及所有其他纹理/遮罩父级不变。相应角度、圆心、尺寸、刻度粗细、纹理镜像而遮罩不镜像保持不变。既有场景继续保护配置持久化、待续轮、旧截止与生命周期。

## 云端相关检查

- 命令：`.venv/bin/python -m pytest -q tests/addons/MYUI_CrosshairHUD`。退出0，`77 passed in 12.03s`。原始日志：`.local/tests/hud-overlay-order/hud-regression.log`。没有运行全仓耗时套件。
- 原有四份HUD测试及魔兽测试薄适配器只补缺失的GetFrameLevel/SetFrameLevel（框架层级读取/设置）和EnableMouse（鼠标开关）边界方法，不增加业务逻辑或共享测试框架。
- 命令：`.venv/bin/python scripts/dev/check.py toc --source addons/MYUI_CrosshairHUD`。插件加载清单、目标接口号和固定Lua5.1语法通过。
- 命令：`.venv/bin/python tests/dev/test_inventory.py`。所有测试入口登记通过；新场景留在现有已登记文件，无需修改统一验证配置。
- 命令：`git diff --check`。通过；文件按现有属性在Git下次写入时转换CRLF的警告不属于差异空白失败。
- 正式规格的基线差异与未跟踪清单均为空，未提前修改正式规格。上述静态和差异检查原始日志：`.local/tests/hud-overlay-order/cloud-checks.log`。
- 命令：`.venv/bin/python scripts/dev/check.py docs`。本记录及票据写入后退出0，359份文档的编码、代码围栏和JSON示例通过；原始日志：`.local/tests/hud-overlay-order/docs-check.log`。

## 后续恢复点

当前源码未提交、未推送、未部署；共享Git写入由父级串行协调。

父级核对实际差异并固定提交后，以本增量基线执行统一正式验证，安排限定独立审查和必要的Windows原60秒固定基线验证。Linux定向通过不替代统一正式验证、LuaLS（语言服务器）、Luacheck（静态检查器）、Windows或游戏验收；未运行的阶段不记作通过。

实际游戏像素仍待用户验收：原位置和缩放下确认红色满/半倒计时、高亮满格和灵打刻度都显示在青色能量之上，隐藏/重现和整体缩放正常。该恢复票不直接操作游戏、不改正式规格、不合并或发布。
