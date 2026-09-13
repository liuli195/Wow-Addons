"""Analyze a local WoW target-dummy combat log without encounter markers."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sys


DAMAGE_EVENTS = {
    "SWING_DAMAGE": 28,
    "SPELL_DAMAGE": 31,
    "SPELL_PERIODIC_DAMAGE": 31,
    "RANGE_DAMAGE": 31,
    "DAMAGE_SHIELD": 31,
    "DAMAGE_SPLIT": 31,
}
GSE_BLOCKING_STATES = {
    "not able to cast",
    "resources not available",
    "gcd in cooldown",
    "casting",
}


def _matches_player(source_name: str, player: str) -> bool:
    return source_name == player or source_name.startswith(player + "-")


def _read_events(path: Path) -> list[tuple[datetime, list[str]]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        try:
            timestamp, payload = line.split("  ", 1)
            events.append((datetime.strptime(timestamp, "%m/%d/%Y %H:%M:%S.%f"), next(csv.reader([payload]))))
        except (ValueError, csv.Error) as exc:
            raise ValueError(f"战斗日志第 {line_number} 行格式错误") from exc
    return events


def _latest_gse_session(path: Path) -> tuple[datetime, list[list[str]]]:
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    if not rows or any(len(row) < 4 for row in rows):
        raise ValueError("GSE 调试记录格式错误")
    try:
        timestamps = [int(row[2]) for row in rows]
    except (IndexError, ValueError) as exc:
        raise ValueError("GSE 调试记录格式错误") from exc
    if not timestamps:
        raise ValueError("GSE 调试记录为空")
    session_start = 0
    for index in range(1, len(timestamps)):
        if timestamps[index] - timestamps[index - 1] > 5:
            session_start = index
    session_rows = rows[session_start:]
    return datetime.fromtimestamp(timestamps[session_start]), session_rows


def _summarize_gse_session(
    rows: list[list[str]], start: datetime, end: datetime
) -> dict:
    start_second = math.floor(start.timestamp())
    end_second = math.ceil(end.timestamp())
    session_rows = [row for row in rows if start_second <= int(row[2]) < end_second]
    if not session_rows:
        raise ValueError("GSE 调试记录与测试区间不重合")
    session_times = [int(row[2]) for row in session_rows]
    attempts = Counter(row[3] for row in session_rows)
    blocked = Counter(
        state
        for row in session_rows
        for state in row[4:9]
        if state.casefold() in GSE_BLOCKING_STATES or "not found" in state.casefold()
    )
    interval = 0 if len(session_times) == 1 else (
        session_times[-1] - session_times[0]
    ) * 1000 / (len(session_times) - 1)
    return {
        "rows": len(session_rows),
        "start": datetime.fromtimestamp(session_times[0]).isoformat(sep=" "),
        "end": datetime.fromtimestamp(session_times[-1]).isoformat(sep=" "),
        "estimated_average_input_interval_ms": round(interval, 3),
        "attempts_by_spell": dict(sorted(attempts.items())),
        "blocked_reasons": dict(sorted(blocked.items())),
    }


def _latest_damage_cluster_start(player_damage: list[tuple[datetime, list[str]]]) -> datetime:
    start = player_damage[0][0]
    for (previous, _), (current, _) in zip(player_damage, player_damage[1:]):
        if (current - previous).total_seconds() > 10:
            start = current
    return start


def _damage_identity(row: list[str]) -> tuple[int, str]:
    if row[0] == 'SWING_DAMAGE':
        return 0, '近战攻击'
    if len(row) <= 11:
        raise ValueError(f'{row[0]} 法术字段不完整')
    return int(row[9]), row[10]


def _simulation_damage_sources(player: dict, duration: float) -> list[dict]:
    button_ids = {
        int(row.get('base_spell_id') or row.get('data_id') or 0)
        for row in player.get('sim2gse_actions', [])
        if not row.get('background') and not row.get('passive')
        and row.get('type') not in ('call_action_list', 'action_variable', 'sequence')
    }
    grouped: dict[tuple[str, int], dict] = {}

    def owned_actor_indices(rows: list[dict]) -> set[int]:
        return {
            int(row['sim2gse_actor_index'])
            for row in rows
            if row.get('sim2gse_owner_type') == 'owned_unit'
            and type(row.get('sim2gse_actor_index')) is int
            and row.get('type') == 'damage'
            and isinstance((row.get('actual_amount') or {}).get('mean'), (int, float))
            and not isinstance((row.get('actual_amount') or {}).get('mean'), bool)
        } | {
            actor
            for row in rows
            for actor in owned_actor_indices(row.get('children', []))
        }

    def add(rows: list[dict], inherited_owner: str, separate_owned: set[int]) -> None:
        for row in rows:
            owner_type = row.get('sim2gse_owner_type', inherited_owner)
            actor_index = row.get('sim2gse_actor_index')
            add(row.get('children', []), owner_type, separate_owned)
            if owner_type == 'owned_unit' and actor_index in separate_owned:
                continue
            amount = row.get('actual_amount') or {}
            damage = amount.get('mean') if isinstance(amount, dict) else None
            if (row.get('type') != 'damage' or isinstance(damage, bool)
                    or not isinstance(damage, (int, float)) or damage <= 0):
                continue
            spell_id = int(row.get('id') or 0)
            key = owner_type, spell_id
            target = grouped.setdefault(key, {
                'owner_type': owner_type,
                'spell_id': spell_id,
                'spell_names': set(),
                'actor_indices': set(),
                'actor_names': set(),
                'damage': 0.0,
                'uses': 0.0,
            })
            target['spell_names'].add(row.get('spell_name') or row.get('name') or '未知')
            if type(actor_index) is int:
                target['actor_indices'].add(actor_index)
            if row.get('sim2gse_actor_name'):
                target['actor_names'].add(row['sim2gse_actor_name'])
            target['damage'] += damage
            executes = row.get('num_executes') or {}
            mean_executes = executes.get('mean') if isinstance(executes, dict) else None
            if isinstance(mean_executes, (int, float)) and not isinstance(mean_executes, bool):
                target['uses'] += executes['mean']

    pet_rows = [row for rows in player.get('stats_pets', {}).values() for row in rows]
    add(player.get('stats', []), 'player', owned_actor_indices(pet_rows))
    add(pet_rows, 'owned_unit', set())
    expected_damage = player.get('collected_data', {}).get('dps', {}).get('mean')
    if isinstance(expected_damage, (int, float)) and not isinstance(expected_damage, bool):
        expected_total = expected_damage * duration
        detailed_total = sum(row['damage'] for row in grouped.values())
        if detailed_total > expected_total + max(0.01, expected_total * 1e-9):
            raise ValueError('SimC 伤害来源重复，无法可靠比较')
        unallocated = expected_total - detailed_total
        if unallocated > 0.01:
            grouped[('unattributed', -1)] = {
                'owner_type': 'unattributed',
                'spell_id': -1,
                'spell_names': {'SimC 未细分伤害'},
                'actor_indices': set(),
                'actor_names': set(),
                'damage': unallocated,
                'uses': 0.0,
            }
    result = []
    for row in grouped.values():
        spell_id = row['spell_id']
        row['spell_names'] = sorted(row['spell_names'])
        row['actor_indices'] = sorted(row['actor_indices'])
        row['actor_names'] = sorted(row['actor_names'])
        row['spell_name'] = row['spell_names'][0]
        row['category'] = ('unattributed' if row['owner_type'] == 'unattributed' else
                           'owned_unit' if row['owner_type'] == 'owned_unit' else
                           'swing' if spell_id == 0 else
                           'button_or_shared_effect' if spell_id in button_ids else 'derived')
        row['dps'] = row['damage'] / duration
        result.append(row)
    return sorted(result, key=lambda row: (-row['damage'], row['owner_type'], row['spell_id']))


def analyze(
    path: Path,
    player: str,
    duration: float,
    *,
    gse_debug: Path | None = None,
    simulation: Path | None = None,
    primary_target: str | None = None,
    owned_sources: tuple[str, ...] = (),
) -> dict:
    if duration <= 0:
        raise ValueError("duration 必须大于 0")
    events = _read_events(path)
    player_guids = {
        row[1]
        for _, row in events
        if len(row) > 2 and row[1].startswith("Player-") and _matches_player(row[2], player)
    }
    if len(player_guids) != 1:
        raise ValueError("无法唯一确定角色，请使用战斗日志中的角色名")
    player_guid = next(iter(player_guids))
    player_damage = [(time, row) for time, row in events if row[0] in DAMAGE_EVENTS and row[1] == player_guid]
    if not player_damage:
        raise ValueError("没有找到该角色造成的伤害")
    debug_result = None
    debug_rows = None
    if gse_debug is not None:
        debug_start, debug_rows = _latest_gse_session(gse_debug)
        matching_damage = [item for item in player_damage if item[0] >= debug_start]
        if not matching_damage:
            raise ValueError("GSE 最后一次按键区间之后没有找到角色伤害")
        start = matching_damage[0][0]
    else:
        start = _latest_damage_cluster_start(player_damage)
    owned = {player_guid: player}
    for source_name in owned_sources:
        source_guids = {
            row[1]
            for time, row in events
            if start - timedelta(seconds=10) <= time < start + timedelta(seconds=duration)
            and len(row) > 2
            and (row[1] == source_name or _matches_player(row[2], source_name))
        }
        if len(source_guids) != 1:
            raise ValueError(f"无法唯一确定额外伤害来源：{source_name}；请改用来源 GUID")
        owned[next(iter(source_guids))] = source_name
    if owned_sources:
        owned_damage = [
            item for item in events
            if item[1][0] in DAMAGE_EVENTS and item[1][1] in owned
            and (gse_debug is None or item[0] >= debug_start)
        ]
        start = _latest_damage_cluster_start(owned_damage)
    end = start + timedelta(seconds=duration)
    if debug_rows is not None:
        debug_result = _summarize_gse_session(debug_rows, start, end)
    changed = True
    while changed:
        changed = False
        for time, row in events:
            if time >= end:
                break
            if row[0] == "SPELL_SUMMON" and row[1] in owned and row[5] not in owned:
                owned[row[5]] = row[6]
                changed = True

    target_damage: Counter[tuple[str, str]] = Counter()
    cast_destinations: Counter[tuple[str, str]] = Counter()
    successful: dict[str, list[float]] = defaultdict(list)
    successful_by_id: dict[int, list[float]] = defaultdict(list)
    failed: dict[str, Counter[str]] = defaultdict(Counter)
    damage_records = []
    for time, row in events:
        if (start - timedelta(seconds=5) <= time < end and row[1] == player_guid
                and row[0] == 'SPELL_CAST_SUCCESS'):
            if len(row) <= 10:
                raise ValueError("SPELL_CAST_SUCCESS 字段不完整")
            at = round((time - start).total_seconds(), 4)
            successful[row[10]].append(at)
            successful_by_id[int(row[9])].append(at)
            if row[5] != "0000000000000000" and row[6] != "nil":
                cast_destinations[(row[5], row[6])] += 1
        if not start <= time < end:
            continue
        if row[1] == player_guid and row[0] == "SPELL_CAST_FAILED":
            if len(row) <= 12:
                raise ValueError("SPELL_CAST_FAILED 字段不完整")
            failed[row[10]][row[12]] += 1
        if row[0] not in DAMAGE_EVENTS or row[1] not in owned:
            continue
        amount_index = DAMAGE_EVENTS[row[0]]
        if len(row) <= amount_index + 2:
            raise ValueError(f"{row[0]} 伤害字段不完整")
        amount = int(row[amount_index]) - max(0, int(row[amount_index + 2]))
        target_damage[(row[5], row[6])] += amount
        spell_id, spell_name = _damage_identity(row)
        damage_records.append((row[5], row[6], row[1], row[2], spell_id, spell_name, amount))

    if not target_damage:
        raise ValueError("测试区间内没有伤害")
    if primary_target is not None:
        matches = [
            target
            for target in target_damage
            if target[0] == primary_target or _matches_player(target[1], primary_target)
        ]
        if len(matches) != 1:
            raise ValueError("无法唯一确定指定主目标，请改用目标 GUID")
        primary = matches[0]
        selection = {"method": "explicit_target", "evidence_count": 1}
        destination_matches = Counter()
    else:
        destination_matches = Counter({
            target: count
            for target, count in cast_destinations.items()
            if target in target_damage
        })
        if destination_matches:
            primary, evidence_count = destination_matches.most_common(1)[0]
            selection = {
                "method": "successful_cast_destination",
                "evidence_count": evidence_count,
            }
        else:
            primary = target_damage.most_common(1)[0][0]
            selection = {"method": "highest_owned_damage", "evidence_count": 0}
    primary_damage = target_damage[primary]
    other_targets = [
        {"guid": guid, "name": name, "damage": damage}
        for (guid, name), damage in target_damage.most_common()
        if (guid, name) != primary
    ]
    total_damage = sum(target_damage.values())
    source_groups = {}
    for target_guid, target_name, source_guid, source_name, spell_id, spell_name, amount in damage_records:
        if (target_guid, target_name) != primary:
            continue
        owner_type = 'player' if source_guid == player_guid else 'owned_unit'
        key = owner_type, spell_id
        row = source_groups.setdefault(key, {
            'owner_type': owner_type, 'spell_id': spell_id, 'spell_names': set(),
            'source_guids': set(), 'source_names': set(), 'damage': 0,
        })
        row['spell_names'].add(spell_name)
        row['source_guids'].add(source_guid)
        row['source_names'].add(source_name)
        row['damage'] += amount
    damage_sources = []
    for row in source_groups.values():
        row['spell_names'] = sorted(row['spell_names'])
        row['spell_name'] = row['spell_names'][0]
        row['source_guids'] = sorted(row['source_guids'])
        row['source_names'] = sorted(row['source_names'])
        row['category'] = ('owned_unit' if row['owner_type'] == 'owned_unit' else
                           'swing' if row['spell_id'] == 0 else
                           'button' if row['spell_id'] in successful_by_id else 'derived')
        row['dps'] = row['damage'] / duration
        row['portion_of_primary_percent'] = row['damage'] / primary_damage * 100
        damage_sources.append(row)
    damage_sources.sort(key=lambda row: (-row['damage'], row['owner_type'], row['spell_id']))
    result = {
        "player": player,
        "start": start.isoformat(sep=" "),
        "duration_seconds": duration,
        "primary_target": {
            "guid": primary[0],
            "name": primary[1],
            "damage": primary_damage,
            "dps": primary_damage / duration,
        },
        "primary_target_selection": selection,
        "affected_target_count": len(target_damage),
        "other_affected_target_count": len(other_targets),
        "other_affected_targets": other_targets,
        "secondary_damage": total_damage - primary_damage,
        "total_damage": total_damage,
        "successful_casts": {
            spell: {"count": len(times), "times_seconds": times}
            for spell, times in sorted(successful.items())
        },
        "successful_casts_by_spell_id": {
            str(spell_id): {"count": len(times), "times_seconds": times}
            for spell_id, times in sorted(successful_by_id.items())
        },
        "failed_casts": {spell: dict(reasons) for spell, reasons in sorted(failed.items())},
        "damage_sources": damage_sources,
    }
    if debug_result is not None:
        result["gse_debug"] = debug_result
    if simulation is not None:
        try:
            report = json.loads(simulation.read_text(encoding="utf-8"))
            matches = [
                item for item in report["sim"]["players"]
                if _matches_player(item["name"], player)
            ]
            if len(matches) != 1:
                raise ValueError("SimC 结果无法唯一匹配角色")
            simulation_distribution = matches[0]["collected_data"]["dps"]
            simulation_dps = simulation_distribution["mean"]
            simulation_min = simulation_distribution["min"]
            simulation_max = simulation_distribution["max"]
            simulation_std_dev = simulation_distribution["std_dev"]
            options = report["sim"]["options"]
            simulation_duration = options["max_time"]
            simulation_targets = options["desired_targets"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ValueError("SimC 结果缺少玩家 DPS") from exc
        distribution_values = (
            simulation_dps, simulation_min, simulation_max, simulation_std_dev
        )
        if (not all(not isinstance(value, bool) and
                    isinstance(value, (int, float)) and math.isfinite(value)
                    for value in distribution_values) or
                simulation_dps <= 0 or simulation_min <= 0 or
                not simulation_min <= simulation_dps <= simulation_max or
                simulation_std_dev < 0):
            raise ValueError("SimC 玩家 DPS 分布无效")
        if simulation_targets != 1 or simulation_duration != duration:
            raise ValueError("SimC 结果必须与单目标测试时长一致")
        if selection["method"] == "highest_owned_damage":
            raise ValueError("无法确认主目标，请提供 --primary-target 后再比较 SimC")
        if selection["method"] != "explicit_target" and len(destination_matches) != 1:
            raise ValueError("存在多个成功施法目标，请提供 --primary-target 后再比较 SimC")
        result["simulation_dps"] = simulation_dps
        result["simulation_dps_distribution"] = {
            "mean": simulation_dps,
            "min": simulation_min,
            "max": simulation_max,
            "std_dev": simulation_std_dev,
        }
        result["simulation_conditions"] = {
            "duration_seconds": simulation_duration,
            "targets": simulation_targets,
            "actual_affected_targets": len(target_damage),
            "secondary_damage_excluded": total_damage - primary_damage,
        }
        simulation_sources = _simulation_damage_sources(matches[0], duration)
        result['simulation_damage_sources'] = simulation_sources
        actual_by_id = {(row['owner_type'], row['spell_id']): row for row in damage_sources}
        simulation_by_id = {(row['owner_type'], row['spell_id']): row for row in simulation_sources}
        comparison = []
        for owner_type, spell_id in sorted(set(actual_by_id) | set(simulation_by_id)):
            actual = actual_by_id.get((owner_type, spell_id))
            simulated = simulation_by_id.get((owner_type, spell_id))
            actual_dps = actual['dps'] if actual else 0
            simulation_source_dps = simulated['dps'] if simulated else 0
            comparison.append({
                'owner_type': owner_type,
                'spell_id': spell_id,
                'actual_spell_names': actual['spell_names'] if actual else [],
                'simulation_spell_names': simulated['spell_names'] if simulated else [],
                'actual_category': actual['category'] if actual else None,
                'simulation_category': simulated['category'] if simulated else None,
                'actual_dps': actual_dps,
                'simulation_dps': simulation_source_dps,
                'percent_of_simulation': (actual_dps / simulation_source_dps * 100
                                          if simulation_source_dps > 0 else None),
            })
        result['damage_source_comparison'] = comparison
        result["simulation_conditions_not_verifiable_from_combat_log"] = [
            "specialization", "talents", "gear", "game_version", "sequence"
        ]
        result["primary_target_percent_of_simulation"] = primary_damage / duration / simulation_dps * 100
        result["primary_target_within_simulation_sample_range"] = (
            simulation_min <= primary_damage / duration <= simulation_max
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分析训练假人战斗日志")
    parser.add_argument("combat_log", type=Path)
    parser.add_argument("--player", required=True, help="角色名，可省略服务器和地区后缀")
    parser.add_argument("--duration", type=float, default=180)
    parser.add_argument("--gse-debug", type=Path)
    parser.add_argument("--simulation", type=Path, help="SimC JSON 结果")
    parser.add_argument("--primary-target", help="主目标名称或 GUID；同名目标请使用 GUID")
    parser.add_argument(
        "--owned-source",
        action="append",
        default=[],
        help="日志开始前已经存在的宠物或守护者名称或 GUID；可重复指定",
    )
    args = parser.parse_args(argv)
    try:
        result = analyze(
            args.combat_log,
            args.player,
            args.duration,
            gse_debug=args.gse_debug,
            simulation=args.simulation,
            primary_target=args.primary_target,
            owned_sources=tuple(args.owned_source),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
