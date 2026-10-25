# 装备规划器测试分层

本轮为以 `a311de29092413f8fe2bdae0778d6092a6596d7b` 为基线重新实施的版本，不声称恢复旧 d3 的对象或沿用其绿色结果。

## 当前入口

- 普通：`python -m pytest -q tests/gear-planner -m "not real" --strict-markers`。直接驱动解析、校验、编辑、等级、来源、筛选、合并和计算响应解码；使用公开静态样例和明确局部 IO Mock，不启动引擎、服务或浏览器，不联网或写业务缓存。
- 真实：`python -m pytest -q tests/gear-planner -m real --strict-markers`。普通/神圣/织雾三个固定引擎各一次最轻真实调用，核对哈希、完整快照和基线；另保一条浏览器导入→计算→编辑→保存重载→比较→导出重导链。计算仍由既有 LOCK 串行，不扩大生产并发。
- JavaScript：保留现有8个 `check-*.js` VM/纯规则入口。正式入口与浏览器 helper 必须使用统一配置的 `.local/verify-deps/node/node.exe`；系统 Node 的便携检查不替代该冻结身份验收。
- 缺少引擎、资料、Edge 或冻结 Node 时明确失败，不以 skip 或假输出记为真实通过。

## 原21个Python入口账本

| 原入口 | 普通/真实承接机制 |
| --- | --- |
| check.py | 导入、安全边界、独立公开快照解码；三引擎真实代表与浏览器完整链 |
| check-add-socket.py | 可加插槽、单槽上限、移除及原子编辑；浏览器保真实宝石差值 |
| check-bulk-levels.py | 最低/最高/指定/恢复等级、确认及保留后续编辑 |
| check-catalog.py | 公开目录471/523契约、替换规则；浏览器实际候选替换 |
| check-effects.py | tooltip解析、装等错配拒绝、纯文本、缓存键；在线数据复验保manual |
| check-enchants.py | 附魔mask、职业符文限制、中文标签、删除和不兼容拒绝 |
| check-extra-input.py | 全40专精导入、安全输入、引擎路由/标志、错误与空结果不可伪成功 |
| check-fit.py | 各职业护甲、专精主属性、掉落身份及不同武器机制 |
| check-gems.py | 唯一性、跨槽共享上限、空位置、多插槽与不兼容拒绝 |
| check-item-stats.py | 独立公开快照解码、制作/等级编辑；普通引擎真实基线物品属性 |
| check-levels.py | 来源等级、同级不同轨道、制作品质、末王固定等级、来源重定向 |
| check-merge-selection.py | 同ID不同结果、等价结果、切换与恢复时选择稳定 |
| check-merge-slots.py | 同一合并机制代表，保留原始属性/特效/宝石/附魔判别，不保逐槽原生交叉 |
| check-mistweaver.py | 普通路由/主属性/平均装等；神圣/织雾真实代表；历史修复对照保manual |
| check-names.py | 公开523目录及名称资料完整性、英文/ID显示机制代表 |
| check-option-labels.py | 全公开名称和100附魔中文资料、品质与选项标签机制 |
| check-original-item.py | 恢复原装备时保当前等级与已移除配置、错误槽位拒绝及合并 |
| check-replace-level.py | 最近合法等级的精确确认与原子拒绝 |
| check-replace.py | 同等级/同ID/制作替换、宝石附魔保留、双手/副手原子规则 |
| check-sets.py | 解析与40专精显示规则；65物品/40专精线上资料完整性保manual |
| check-sources.py | 制作、地下城、团本兑换、催化转化、未知来源；真实代表保来源元数据 |

## 浏览器账本

- `check-browser.cjs` 是唯一真实完整链，保重复名称、删除取消、末项空状态、实际 Storage.setItem 失败、候选/装等/附魔编辑及可点击的弱化筛选。
- 原 `check-deathknight.cjs` 的重复职业完整链由该链承接；武器/副手/平均装等分支进入普通Python，候选/套装/主属性来源列进入现有summary VM。迁移完成前不得先删除未承接的独有规则。

## 明确manual的资料复验

以下入口不进入日常60秒验证。原来已是显式专项，不能将此归类称为把旧自动失败移出预算。

- `research/check-cn-reference.py`：历史 `.local` 玩家面板和槽位快照；日常正常基线另由真实代表保护。
- `research/check-deathknight-raidbots.py`：固定引擎/DBC/gear完整回放；公开输入哈希和快照结构复用进普通组。
- `research/check-epic-catalog.py`：上游/KeystoneLoot来源交叉核验；207/101/65/98/52及471/523公开契约复用进普通组。
- `research/check-priest-experimental.py`：全实验回放；路由/标志与公开输入哈希复用进普通组。
- `research/manual-mistweaver-history.py`：原旧/修复引擎主属性、护甲专精、耐力天赋及物理专精不变对照，需要历史 `.local` 引擎；不是独立游戏数值证据。
- `research/check-tooltip-data.py`：原311/321特效、65套装物品/40专精2/4件资料完整性，可联网并写正常特效缓存。

75宝石、100附魔、471产品和523目录的逐项原生接受度已按批准缩为机制代表；不会再逐项证明未选条目被引擎接受。目录/名称静态检查、纯规则或历史manual不能冒充该原生组合广度仍然等价。
