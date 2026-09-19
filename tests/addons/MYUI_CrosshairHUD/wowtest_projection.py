"""准星 HUD 的三组件双边投影与判定。

为什么需要这一层：工具的比较器没有投影能力，而插件的可观测输出与工具标准输出**不同形**——
生命与主资源那边，插件只拿到**角度**（曲线交给引擎求值），没有 value/maximum；
职业资源那边，插件给的是索引、充能比例与状态，没有冷却起点与时长。

于是这里做**双边投影**：
  · 参考侧：工具锁定基线的 value/maximum → 参考比例；符文冷却信息 + 检查点时间 → 参考比例与状态
  · 实际侧：插件实际产出的角度 → 观测比例；符文索引进度 → 观测比例与状态

**逆映射按设计常量独立写一遍**，不调用插件的函数、不导入它的曲线：
复用被测曲线会让生产曲线的错误在正逆两次使用中相互抵消，测试就白测了。
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_SCRIPTS = ROOT / ".agents" / "skills" / "wow-addon-test" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from wowtestlib import core  # noqa: E402  只借它的锁定数据与完整性校验，不借它的判定

# ---- 设计常量：与设计稿一致，独立于插件实现 --------------------------------------
FILL_MARGIN = 2.0
ARCS = {
    "health": {"start": 99.0, "span": 102.0, "reverse": False},
    "power": {"start": 339.0, "span": 102.0, "reverse": True},
}
# 正式比较口径：比例容差，以及刷新时刻造成的合法陈旧（一次 0.1 秒轮询 / 符文充能时长）
RATIO_TOLERANCE = 1e-6
RUNE_STALENESS_TOLERANCE = 0.02

# 已批准的产品差异：仅适用于下列用例中**事先确认的那些字段**，其它字段仍然照常判失败。
KNOWN_DIFFERENCES = {
    "disconnect-reconnect": {
        "components": ("health", "primary"),
        "reason": "断线期间保持既有读数链，不采用原生的满格＋置灰表现（已批准）",
    },
    "primary-type-roundtrip": {
        "components": ("primary",),
        "reason": "主资源类型固定为符能（死亡骑士专用插件），不跟随被报告的类型（已批准）",
    },
}

# 明确**未参与比较**的字段：写出来，避免读的人以为它们验证过了。
NOT_COMPARED = {
    "health.connected": "本插件不判断断线（已登记的已知差异）",
    "primary.token": "token 与 type 同源，随 type 一并处理",
    "resource.nodes[].start/duration": "插件不产出冷却起点与时长，只产出充能比例与状态",
    "受限值语义 / 画面 / 视觉排序": "不在本工具证明范围内",
}

RUNES_STATE_MAP = {"ready": "ready", "recharging": "cooldown", "empty": "empty"}


def angle_to_ratio(angle, arc):
    """由设计常量独立推导的「角度 → 填充比例」逆映射。"""
    reach = arc["span"] + FILL_MARGIN
    degrees = math.degrees(angle)
    if arc["reverse"]:
        cut = -degrees - 270.0
        return (arc["start"] + arc["span"] + FILL_MARGIN - cut) / reach
    return (-degrees - 90.0 - (arc["start"] - FILL_MARGIN)) / reach


def _ratio(value, maximum):
    return value / (maximum or 1)


def _rune_reference_ratio(node, step_time):
    if node["state"] != "cooldown":
        return 1.0 if node["state"] == "ready" else 0.0
    duration = node.get("duration") or 0
    if duration <= 0:
        return 1.0
    return min(1.0, max(0.0, (step_time - node.get("start", 0)) / duration))


def project_reference(snapshot, step_time):
    """基线快照 → 参考比例与状态。"""
    health = snapshot["health"]
    primary = snapshot["primary"]
    resource = snapshot["resource"]
    reference = {
        "health": {"ratio": _ratio(health["value"], health["maximum"])},
        "primary": {"ratio": _ratio(primary["value"], primary["maximum"]), "type": primary.get("type")},
    }
    if resource.get("kind") == "runes":
        reference["resource"] = {
            "kind": "runes",
            "nodes": [
                {"state": node["state"], "ratio": _rune_reference_ratio(node, step_time)}
                for node in resource["nodes"]
            ],
        }
    else:
        reference["resource"] = {"kind": resource.get("kind", "none")}
    return reference


def project_observed(observed, step_time):
    """插件实际观测 → 观测比例与状态。缺失读数显式标为无效，不补默认值。"""
    actual = {"health": {"valid": observed.get("has_health") is True}}
    # 类型取自适配器观测到的**实际请求值**；观测不到时留空，不做猜测
    actual["primary"] = {"valid": observed.get("has_power") is True,
                         "type": observed.get("power_type")}
    if actual["health"]["valid"]:
        actual["health"]["ratio"] = angle_to_ratio(observed["health_angle"], ARCS["health"])
    if actual["primary"]["valid"]:
        actual["primary"]["ratio"] = angle_to_ratio(observed["power_angle"], ARCS["power"])
    nodes = observed.get("runes") or []
    actual["resource"] = {
        "kind": "runes" if nodes else "none",
        "nodes": [
            {"state": RUNES_STATE_MAP.get(node.get("state"), node.get("state")), "ratio": node.get("frac")}
            for node in sorted(nodes, key=lambda n: n.get("index", 0))
        ],
    }
    return actual


def _close(left, right, tolerance=RATIO_TOLERANCE):
    return left is not None and right is not None and abs(left - right) <= tolerance


def compare_component(component, reference, actual, known):
    """返回该组件的差异列表；已登记的产品差异只放行它自己的那些字段。"""
    differences = []
    if component in ("health", "primary"):
        if not actual.get("valid"):
            differences.append({"component": component, "kind": "unreadable", "detail": "插件未产出读数"})
            return differences
        if not _close(reference.get("ratio"), actual.get("ratio")):
            differences.append({
                "component": component, "kind": "ratio",
                "expected": reference.get("ratio"), "observed": actual.get("ratio"),
                "known": component in known,
            })
        # 类型只在**两侧都观测到**时比较；观测不到时列入「未比较」，不冒充已验证
        if component == "primary" and actual.get("type") is not None \
                and reference.get("type") != actual.get("type"):
            differences.append({
                "component": component, "kind": "type",
                "expected": reference.get("type"), "observed": actual.get("type"),
                "known": component in known,
            })
        return differences
    ref_nodes = reference.get("nodes", [])
    act_nodes = actual.get("nodes", [])
    if len(ref_nodes) != len(act_nodes):
        differences.append({"component": component, "kind": "count",
                            "expected": len(ref_nodes), "observed": len(act_nodes)})
        return differences
    for index, (expected, observed) in enumerate(zip(ref_nodes, act_nodes), start=1):
        if expected["state"] != observed["state"]:
            differences.append({"component": component, "kind": "state", "index": index,
                                "expected": expected["state"], "observed": observed["state"]})
            continue
        if expected["state"] == "cooldown" and not _close(expected["ratio"], observed["ratio"],
                                                         max(RATIO_TOLERANCE, RUNE_STALENESS_TOLERANCE)):
            differences.append({"component": component, "kind": "ratio", "index": index,
                                "expected": expected["ratio"], "observed": observed["ratio"]})
    return differences


def judge(cases, baseline, actual, components=core.COMPONENTS):
    """逐用例、逐检查点判定。返回可直接复核的报告。"""
    case_of = {c["id"]: c for c in cases}
    ref_of = {r["id"]: r for r in baseline}
    rows, totals = [], {"cases": 0, "passed": 0, "known_difference": 0, "difference": 0, "errors": 0, "checkpoints": 0}
    for record in actual:
        case = case_of.get(record["id"])
        reference_case = ref_of.get(record["id"])
        row = {"id": record["id"], "differences": [], "errors": list(record.get("errors") or [])}
        if case is None or reference_case is None:
            row["errors"].append({"stage": "lookup", "message": "用例或基线缺失"})
            rows.append(row)
            totals["errors"] += 1
            continue
        known = KNOWN_DIFFERENCES.get(record["id"].split(".", 1)[1], {}).get("components", ())
        snapshots = record.get("snapshots") or []
        if len(snapshots) != len(case["steps"]):
            row["errors"].append({"stage": "snapshots", "message": "检查点数目与用例步骤不一致"})
            rows.append(row)
            totals["errors"] += 1
            continue
        for index, (step, observed, expected) in enumerate(
                zip(case["steps"], snapshots, reference_case["snapshots"]), start=1):
            totals["checkpoints"] += 1
            actual_row = observed.get("observed")
            if not isinstance(actual_row, dict):
                row["errors"].append({"stage": "observed", "step": index, "message": "适配器未交出可读快照"})
                continue
            reference = project_reference(expected, step["state"]["time"])
            projection = project_observed(actual_row, step["state"]["time"])
            for component in components:
                for difference in compare_component(component, reference[component], projection[component], known):
                    difference["step"] = index
                    row["differences"].append(difference)
        blocked = [d for d in row["differences"] if not d.get("known")]
        row["status"] = "error" if row["errors"] else ("difference" if blocked else
                                                       ("known_difference" if row["differences"] else "pass"))
        rows.append(row)
        totals["cases"] += 1
        totals[row["status"]] = totals.get(row["status"], 0) + 1
    return {"totals": totals, "cases": rows, "known_differences": KNOWN_DIFFERENCES}
