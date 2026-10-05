"""多起点局部搜索、分批统计和任务缓存。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
import threading
import uuid
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import statistics
import time

from runtime import replace_file
from runtime import BudgetExceeded, TaskCancelled, TaskRuntime


SEARCH_ALGORITHM = "multi-start-local-adaptive-v2"
STATS_VERSION = "paired-bootstrap-v1"
SCREENING_ERROR_MULTIPLIER = 1.96
DEFAULT_SCENARIOS = ("nominal", "jitter", "slow", "pause", "phase")
DEFAULT_CONFIG = {
    "total_budget_seconds": 600.0,
    "search_budget_seconds": 600.0,
    "candidate_limit": 1000,
    "round_candidate_limit": 16,
    "no_improvement_rounds": 5,
    "batch_targets": (32, 128, 512),
    "validation_batches": 4,
    "final_batches": 20,
    "iterations": 100,
    "final_iterations": 100,
    "max_processes": 2,
    "scenarios": DEFAULT_SCENARIOS,
    "random_seed": 20260912,
    "trace_search": False,
    "diagnostic_logging": False,
    "diagnostics": "off",
    "search_observability": "off",
    "input_interval_ms": 300,
    "reset_events": (),
}


def verify_behavior_identity_state(state):
    from program import BEHAVIOR_IDENTITY_VERSION
    search_state_keys = ('archive', 'pending', 'seen', 'evaluated_keys',
                         'locked_candidate_key')
    saved = state.get('behavior_identity_version')
    if saved != BEHAVIOR_IDENTITY_VERSION and (
            saved is not None or any(key in state for key in search_state_keys)):
        raise ValueError('候选行为身份版本已变化，请创建新任务')


def config_for(values=None):
    config = dict(DEFAULT_CONFIG)
    if values:
        if set(values)-set(config):
            raise ValueError('未知搜索配置')
        config.update(values)
        if 'total_budget_seconds' in values and 'search_budget_seconds' not in values:
            config['search_budget_seconds'] = config['total_budget_seconds']
    for key, maximum in (('total_budget_seconds',600),('search_budget_seconds',600)):
        value=config[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= maximum:
            raise ValueError('计算预算必须在已确认上限内')
    if config['search_budget_seconds'] > config['total_budget_seconds']:
        raise ValueError('搜索预算不能超过总预算')
    for key, maximum in (('candidate_limit',1000),('round_candidate_limit',16),('no_improvement_rounds',5),
                         ('max_processes',2),('validation_batches',20),('final_batches',20),
                         ('iterations',512),('final_iterations',100),('random_seed',1000000000)):
        if type(config[key]) is not int or not 1 <= config[key] <= maximum:
            raise ValueError('搜索配置超出范围: '+key)
    if type(config['input_interval_ms']) is not int or not 50 <= config['input_interval_ms'] <= 2000:
        raise ValueError('按键间隔必须为 50 至 2000 毫秒的整数')
    if config['diagnostics'] not in {'off', 'summary', 'full'}:
        raise ValueError('诊断模式必须是 off、summary 或 full')
    if (not isinstance(config['search_observability'], str) or
            config['search_observability'] not in ('off', 'summary', 'full')):
        raise ValueError('搜索记录模式必须是 off、summary 或 full')
    if type(config['diagnostic_logging']) is not bool:
        raise ValueError('诊断日志总开关必须为布尔值')
    if not config['diagnostic_logging']:
        config['diagnostics'] = 'off'
        config['search_observability'] = 'off'
    config['batch_targets']=tuple(config['batch_targets'])
    previous=0
    for value in config['batch_targets']:
        if type(value) is not int or value-previous < 2 or value>512:
            raise ValueError('独立加测批次必须至少请求两场，累计不超过512场')
        previous=value
    if not config['batch_targets']:
        raise ValueError('缺少搜索批次')
    config['scenarios']=tuple(config['scenarios'])
    if not config['scenarios'] or len(set(config['scenarios']))!=len(config['scenarios']) or set(config['scenarios'])-set(DEFAULT_SCENARIOS):
        raise ValueError('最终复测情景无效')
    events = config['reset_events']
    if not isinstance(events, (list, tuple)) or any(
            not isinstance(row, (list, tuple)) or len(row) != 2 or
            type(row[0]) is not int or not 0 <= row[0] < 180000 or
            row[1] not in {'target', 'combat', 'shift', 'ctrl', 'alt', 'death'}
            for row in events):
        raise ValueError('/castsequence Reset 事件配置无效')
    config['reset_events'] = tuple(tuple(row) for row in events)
    if any(kind in {'shift', 'ctrl', 'alt'} for _, kind in config['reset_events']):
        if (config['scenarios'] != ('nominal',) or
                any(ms % config['input_interval_ms'] for ms, kind in config['reset_events']
                    if kind in {'shift', 'ctrl', 'alt'})):
            raise ValueError('修饰键 Reset 事件只支持与 nominal 情景点击对齐')
    return config


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def program_key(program) -> str:
    return digest(program)


def _action_name(row, actions_by_id, actions_by_name):
    name = row.get("name")
    if name in actions_by_name:
        return actions_by_name[name]
    return actions_by_id.get(str(row.get("id")))


def _unique_names(names, available):
    return list(dict.fromkeys(name for name in names if name in available))


def initial_programs(capabilities, reference, seed=20260912):
    """从四个来源产生稳定合法的起点，而不读派生或宠物动作。"""
    actions = [a["simc_action"] for a in capabilities["actions"]]
    available = set(actions)
    by_id = {str(v['spell_id']): a['simc_action'] for a in capabilities['actions']
             for v in a.get('variants', [a]) if v.get('spell_id') is not None}
    by_name = {v.get('native_name', v['simc_action']): a['simc_action'] for a in capabilities['actions']
               for v in a.get('variants', [a])}
    starts = []

    def add(names):
        names = _unique_names(names, available)
        if names:
            starts.append([[name] for name in names])

    add(actions)  # 均匀合法的完整排列。
    frequency = []
    for row in reference.get("action_sequence", []):
        if row.get("queue_failed"):
            continue
        name = _action_name(row, by_id, by_name)
        if name:
            frequency.append(name)
    if frequency:
        from collections import Counter
        counts=Counter(frequency)
        scale=max(1,max(counts.values())/8)
        starts.append([[name] for name,count in counts.most_common()
                       for _ in range(max(1,round(count/scale)))][:128])
    repeated = _unique_names(frequency[:3] or actions[:3], available)
    if repeated:
        starts.append([[name] for name in repeated] * 2)
    rng = random.Random(seed)
    shuffled = list(actions)
    rng.shuffle(shuffled)
    add(shuffled)
    unique = []
    seen = set()
    for program in starts:
        key = program_key(program)
        if key not in seen:
            seen.add(key)
            unique.append(program)
    return unique


def _copy_program(program):
    copied = []
    for segment in program:
        if isinstance(segment, dict):
            item = dict(segment)
            if segment.get("kind") == "Loop":
                item["blocks"] = [list(block) for block in segment["blocks"]]
            elif segment.get("kind") == "CastSequence":
                item["members"] = list(segment.get("members", []))
                reset = segment.get("reset")
                if isinstance(reset, dict):
                    item["reset"] = dict(reset, flags=list(reset.get("flags", [])))
            copied.append(item)
        else:
            copied.append(list(segment))
    return copied


def mutate(program, capabilities, rng, *, feedback=None, reset_flags=(), observation=None,
           excluded_programs=()):
    """执行动作块、顺序 Loop 或 WaitClicks 变异。"""
    source = _copy_program(program)
    available = [a["simc_action"] for a in capabilities["actions"]]
    if not source or not available:
        if observation is not None:
            observation.update(sampled_mutation=None, actual_mutation="no_change",
                               modification_position=None)
        return source
    loop_indices = [index for index, segment in enumerate(source)
                    if isinstance(segment, dict) and segment.get("kind") == "Loop"]
    ordinary_indices = [index for index, segment in enumerate(source) if isinstance(segment, list)]
    wait_indices = [index for index, segment in enumerate(source)
                    if isinstance(segment, dict) and segment.get("kind") == "WaitClicks"]
    castsequence_indices = [index for index, segment in enumerate(source)
                            if isinstance(segment, dict) and segment.get("kind") == "CastSequence"]
    operations = ["swap", "replace", "insert", "delete", "move", "block"]
    operations.append("repeat_count" if loop_indices else "loop")
    operations.append("wait_clicks")
    operations.append("castsequence_member" if castsequence_indices else "castsequence")
    if castsequence_indices:
        operations.append("castsequence_reset")
        if reset_flags:
            operations.append("castsequence_reset_flag")
    sampled_operation = rng.choice(operations)
    operation = sampled_operation
    position = None

    def finish():
        if observation is not None:
            observation.update(
                sampled_mutation=sampled_operation,
                actual_mutation=operation if source != program else "no_change",
                modification_position=position if source != program else None,
            )
        return source

    suggested = None
    def choose_value(container, key, values):
        previous = container[key]
        allowed = []
        for value in values:
            container[key] = value
            if value != previous and program_key(source) not in excluded_programs:
                allowed.append(value)
        container[key] = rng.choice(allowed) if allowed else previous
        return bool(allowed)

    def legal_block(block):
        from sequence import select
        try:
            select(capabilities, [block])
            return True
        except ValueError:
            return False

    if operation != "loop" and feedback and rng.random() < 0.5:
        targets = [row['source_position'] for row in feedback.get('positions', [])
                   if row.get('unresolved_inputs', 0) > 0 and not row.get('ambiguous')
                   and row.get('source_position') is not None]
        if targets:
            target = rng.choice(targets)
            index = target['segment']
            segment = source[index]
            choices = ['move', 'swap', 'wait_clicks']
            if isinstance(segment, dict) and segment.get('kind') == 'Loop':
                choices.append('repeat_count')
            operation = rng.choice(choices)
            position = dict(target, repair=True)
            if operation == 'repeat_count':
                choose_value(segment, 'count', (2, 3))
            elif operation == 'wait_clicks':
                neighbors = [i for i in (index - 1, index + 1)
                             if i in wait_indices]
                if neighbors:
                    wait = source[rng.choice(neighbors)]
                    choose_value(wait, 'clicks', (2, 3, 4))
                elif len(source) < 128:
                    source.insert(index, dict(kind='WaitClicks', clicks=rng.choice((2, 3, 4))))
            else:
                container, start = source, index
                if 'loop_block' in target:
                    container, start = segment['blocks'], target['loop_block']
                elif 'member' in target:
                    container, start = segment['members'], target['member']
                destinations = [i for i in range(len(container))
                                if i != start and container[i] != container[start]]
                if destinations:
                    destination = rng.choice(destinations)
                    position['target'] = destination
                    if operation == 'swap':
                        container[start], container[destination] = container[destination], container[start]
                    else:
                        container.insert(destination, container.pop(start))
            if source != program:
                return finish()
            operation = sampled_operation
            position = None
        if feedback.get('untried'):
            operation,suggested='insert',rng.choice(feedback['untried'])
        elif feedback.get('resource_overflowed') and feedback.get('spenders'):
            operation,suggested='insert',rng.choice(feedback['spenders'])
        else:
            wasted=[name for name,n in feedback.get('attempts',{}).items()
                    if n>2 and feedback.get('successes',{}).get(name,0)/n < 0.05]
            positions=[i for i,b in enumerate(source)
                       if any(name in wasted
                              for block in (b.get("blocks", []) if isinstance(b, dict) else [b])
                              for name in block)]
            if positions and len(source)>1:
                index = rng.choice(positions)
                del source[index]
                operation, position = "delete", {"segment": index}
                return finish()
    if operation == "swap" and len(source) > 1:
        first, second = rng.sample(range(len(source)), 2)
        source[first], source[second] = source[second], source[first]
        position = {"segments": [first, second]}
    elif operation == "replace" and ordinary_indices:
        block = rng.choice(ordinary_indices)
        action = rng.randrange(len(source[block]))
        alternatives = [name for name in available if name != source[block][action]
                        and legal_block(source[block][:action] + [name] + source[block][action + 1:])]
        if alternatives:
            if choose_value(source[block], action, alternatives):
                position = {"segment": block, "action": action}
    elif operation == "insert" and len(source) < 128:
        block = rng.randrange(len(source))
        source.insert(block, [suggested or rng.choice(available)])
        position = {"segment": block}
    elif operation == "delete" and len(source) > 1:
        if wait_indices and len(ordinary_indices) <= 1:
            index = rng.choice(wait_indices)
        else:
            index = rng.randrange(len(source))
        del source[index]
        position = {"segment": index}
    elif operation == "move" and len(source) > 2:
        start = rng.randrange(len(source) - 1)
        end = rng.randrange(start + 1, min(len(source), start + 4) + 1)
        fragment = source[start:end]
        del source[start:end]
        targets = [target for target in range(len(source) + 1)
                   if source[:target] + fragment + source[target:] != program
                   and program_key(source[:target] + fragment + source[target:]) not in excluded_programs]
        target = rng.choice(targets) if targets else start
        source[target:target] = fragment
        position = {"segments": [start, end], "target": target}
    elif operation == "block":
        if not ordinary_indices:
            return finish()
        block_index = rng.choice(ordinary_indices)
        block = source[block_index]
        if len(block) > 1 and rng.random() < 0.5:
            index=rng.randrange(len(block))
            command=block.pop(index)
            if rng.random()<0.5:
                target = rng.randrange(len(block)+1)
                block.insert(target,command)
                position = {"segment": block_index, "actions": [index, target]}
            else:
                position = {"segment": block_index, "action": index}
        elif len(block) < 16:
            index = rng.randrange(len(block) + 1)
            alternatives = [name for name in available
                            if legal_block(block[:index] + [name] + block[index:])]
            if alternatives:
                if choose_value(source, block_index,
                                [block[:index] + [name] + block[index:] for name in alternatives]):
                    position = {"segment": block_index, "action": index}
    elif operation == "loop":
        if wait_indices or castsequence_indices:
            if not ordinary_indices:
                return finish()
            start = rng.choice(ordinary_indices)
            source[start:start + 1] = [dict(kind="Loop", count=rng.choice((2, 3)),
                                            blocks=[source[start]])]
            position = {"segments": [start, start + 1]}
        elif len(source) > 1:
            start = rng.randrange(len(source) - 1)
            end = rng.randrange(start + 2, min(len(source), start + 4) + 1)
            source[start:end] = [dict(kind="Loop", count=rng.choice((2, 3)),
                                      blocks=source[start:end])]
            position = {"segments": [start, end]}
        elif ordinary_indices:
            start, end = 0, 1
            source[start:end] = [dict(kind="Loop", count=rng.choice((2, 3)),
                                      blocks=source[start:end])]
            position = {"segments": [start, end]}
    elif operation == "repeat_count":
        index = rng.choice(loop_indices)
        loop = source[index]
        choose_value(loop, 'count', (2, 3))
        position = {"segment": index}
    elif operation == "wait_clicks":
        if wait_indices:
            index = rng.choice(wait_indices)
            wait = source[index]
            choose_value(wait, 'clicks', (2, 3, 4))
            position = {"segment": index}
        elif len(source) < 128:
            index = rng.randrange(len(source) + 1)
            source.insert(index,
                          dict(kind="WaitClicks", clicks=rng.choice((2, 3, 4))))
            position = {"segment": index}
    elif operation == "castsequence":
        spells = {action["simc_action"] for action in capabilities["actions"]
                  if action.get("kind") == "spell"}
        eligible = [index for index, segment in enumerate(source)
                    if isinstance(segment, list) and len(segment) == 1 and segment[0] in spells]
        pairs = [(first, second) for first, second in zip(eligible, eligible[1:])
                 if second == first + 1]
        if pairs:
            start, second = rng.choice(pairs)
            end = second + 1
            while end < len(source) and end - start < 4:
                segment = source[end]
                if not (isinstance(segment, list) and len(segment) == 1 and segment[0] in spells):
                    break
                if rng.random() < 0.5:
                    break
                end += 1
            members = [source[index][0] for index in range(start, end)]
            source[start:end] = [dict(kind="CastSequence", members=members, reset=None)]
            position = {"segments": [start, end]}
    elif operation == "castsequence_member":
        index = rng.choice(castsequence_indices)
        sequence = source[index]
        members = list(sequence.get("members", []))
        spells = [action["simc_action"] for action in capabilities["actions"]
                  if action.get("kind") == "spell"]
        if members and spells:
            position = rng.randrange(len(members))
            alternatives = [name for name in spells if name != members[position]]
            if alternatives:
                choose_value(sequence['members'], position, alternatives)
                position = {"segment": index, "member": position}
    elif operation == "castsequence_reset":
        index = rng.choice(castsequence_indices)
        sequence = source[index]
        reset = sequence.get("reset") or {}
        current = reset.get("timeout_seconds")
        flags = list(reset.get("flags", []))
        choose_value(sequence, 'reset',
                     [{"timeout_seconds": timeout, "flags": flags}
                      if timeout is not None or flags else None
                      for timeout in (None, 1, 2, 3, 5) if timeout != current])
        position = {"segment": index}
    elif operation == "castsequence_reset_flag":
        index = rng.choice(castsequence_indices)
        sequence = source[index]
        reset = sequence.get("reset") or {}
        flag = rng.choice(reset_flags)
        flags = set(reset.get("flags", []))
        if flag in flags:
            flags.remove(flag)
        else:
            flags.add(flag)
        timeout = reset.get("timeout_seconds")
        sequence["reset"] = ({"timeout_seconds": timeout,
                              "flags": [name for name in ("target", "combat", "shift", "ctrl", "alt")
                                        if name in flags]}
                             if timeout is not None or flags else None)
        position = {"segment": index}
    return finish()


def feedback_from_trace(trace, available=(), overflow=False, aliases=None):
    from collections import Counter
    attempts,successes=Counter(),Counter()
    observed=set()
    spenders=set()
    previous=None
    for event in trace:
        name=event.get('signature')
        if name in (None,'-'):
            name=event.get('action')
        name = (aliases or {}).get(name, name)
        key=(event.get('battle'),event.get('origin'),name)
        if event.get('event') in ('not_ready','outside_window','queue','dispatch','busy','dispatch_failed') and key not in observed:
            observed.add(key)
            attempts[name]+=1
        if event.get('event')=='native_execute':
            successes[name]+=1
            if previous and previous.get('battle')==event.get('battle') and event['rp']<previous['rp']:
                spenders.add((aliases or {}).get(previous['signature'], previous['signature']))
            previous=event
    return dict(attempts=dict(attempts),successes=dict(successes),
                untried=[name for name in available if name not in attempts],
                resource_overflowed=overflow,spenders=sorted(spenders & set(available)))


def input_times(scenario, seed=0, interval_ms=300):
    if scenario == "nominal":
        return list(range(0, 180000, interval_ms))
    if scenario == "slow":
        return list(range(0, 180000, round(interval_ms * 4 / 3)))
    if scenario == "phase":
        return list(range(interval_ms // 2, 180000, interval_ms))
    if scenario == "pause":
        return [at for at in range(0, 180000, interval_ms) if not (60000 <= at < 62000 or 120000 <= at < 122000)]
    if scenario == "jitter":
        rng = random.Random(seed)
        times, current = [], 0
        while current < 180000:
            times.append(current)
            current += rng.randint(round(interval_ms * 0.9), round(interval_ms * 1.1))
        return times
    raise ValueError(f"未知输入情景: {scenario}")


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (position - low)


def paired_ci(candidate, control, seed=20260912, samples=2000):
    differences = [a - b for a, b in zip(candidate, control)]
    if not differences:
        return None
    if len(differences) < 2:
        return None
    rng = random.Random(seed)
    means = [statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(samples)]
    return [_percentile(means, 0.025), _percentile(means, 0.975)]


def summarize_pairs(candidate_rows, control_rows, seed=20260912):
    candidate = [float(row["dps"]) for row in candidate_rows]
    control = [float(row["dps"]) for row in control_rows]
    differences = [a - b for a, b in zip(candidate, control)]
    mean_candidate = statistics.mean(candidate) if candidate else None
    mean_control = statistics.mean(control) if control else None
    difference = statistics.mean(differences) if differences else None
    ci = paired_ci(candidate, control, seed) if differences else None
    return {
        "candidate_mean_dps": mean_candidate,
        "control_mean_dps": mean_control,
        "mean_difference": difference,
        "relative_gain": (mean_candidate / mean_control - 1) if mean_candidate is not None and mean_control else None,
        "ci95": ci,
        "status": "improvement_confirmed" if ci and ci[0] > 0 else "not_proven_better",
        "batch_count": len(differences),
        "method": STATS_VERSION,
    }


def _new_search_observability(mode):
    return {
        "mode": mode,
        "next_event_id": 0,
        "details": [],
        "summary": {
            "mutation_attempts": 0,
            "initial_candidates": 0,
            "outcomes": {},
            "legal_candidates": 0,
            "invalid_candidates": 0,
            "duplicates": 0,
            "score_started": 0,
            "score_completed": 0,
            "route_checks": 0,
            "route_promotions": 0,
            "global_checks": 0,
            "global_promotions": 0,
            "invalid_reasons": {},
            "duplicate_reasons": {},
            "sampled_mutations": {},
            "actual_mutations": {},
            "methods": {},
            "phase_seconds": {},
            "positions": {},
        },
    }


def _export_search_observability(value, *, include_details=True):
    summary = dict(value["summary"])
    summary["generated_events"] = (summary["initial_candidates"] +
                                   summary["mutation_attempts"])
    summary["resolved_events"] = sum(summary["outcomes"].values())
    summary["pending_events"] = summary["generated_events"] - summary["resolved_events"]
    summary["positions"] = sorted(
        summary["positions"].values(),
        key=lambda row: (row["candidate_identity"], row["click_position"],
                         row["action_position"] is None,
                         row["action_position"] or 0, row["action"]),
    )
    exported = {"mode": value["mode"], "summary": summary}
    if value["mode"] == "full" and include_details:
        exported["details"] = value["details"]
    return exported


def _position_observations(candidate, candidate_identity, trace):
    from collections import Counter
    from sequence import compiled_program

    blocks = compiled_program(candidate)
    rows = {}
    for click_position, block in enumerate(blocks):
        repeated_actions = {action for action, count in Counter(block).items() if count > 1}
        for action_position, action in enumerate(block):
            rows[(click_position, action_position, action)] = dict(
                candidate_identity=candidate_identity,
                click_position=click_position,
                action_position=action_position,
                action=action,
                turns=0,
                queued=0,
                queue_blocked=0,
                processing=0,
                successes=0,
                failures={},
            )
        for action in repeated_actions:
            rows[(click_position, None, action)] = dict(
                candidate_identity=candidate_identity,
                click_position=click_position,
                action_position=None,
                action=action,
                ambiguous=True,
                ambiguity_reason="trace_missing_action_position",
                turns=0,
                queued=0,
                queue_blocked=0,
                processing=0,
                successes=0,
                failures={},
            )

    failures = {
        "not_ready", "outside_window", "dispatch_failed", "observed_failed",
        "native_interrupt", "commit_failed", "queue_rollback", "late_negative_feedback",
    }
    observed = set()
    inputs = {(e.get('battle'), e.get('origin'), e.get('step')) for e in trace
              if e.get('event') == 'input' and type(e.get('battle')) is int
              and type(e.get('origin')) is int and e['origin'] > 0}
    failed_inputs, successful_inputs = {}, {}
    for event in trace:
        click_position = event.get("step")
        if type(click_position) is not int:
            continue
        positions = [key for key in rows if key[0] == click_position]
        input_key = (event.get('battle'), event.get('origin'), click_position)
        identified = input_key in inputs
        if event.get("event") == "input":
            token = ('input', input_key)
            if identified and token in observed:
                continue
            observed.add(token)
            for key in positions:
                if key[1] is not None:
                    rows[key]["turns"] += 1
            continue
        action = event.get("signature")
        if not action or action == "-":
            action = event.get("action")
        matches = [key for key in positions if key[2] == action]
        if not matches:
            continue
        action_position = event.get("sequence_member") if event.get("sequence_step") == click_position else event.get("action_position")
        exact = [key for key in matches if key[1] == action_position]
        if type(action_position) is int and exact:
            row = rows[exact[0]]
        elif len(matches) == 1:
            row = rows[matches[0]]
        else:
            row = rows[(click_position, None, action)]
        kind = event.get("event")
        metric = ('queued' if kind in {"queue", "queue_commit", "queue_confirm", "queue_tentative"}
                  else 'processing' if kind in {"native_execute", "native_interrupt"} else kind)
        row_key = (row['click_position'], row['action_position'], row['action'])
        token = (input_key, row_key, metric)
        repeated = identified and token in observed
        if identified:
            observed.add(token)
            if kind in failures:
                failed_inputs.setdefault(row_key, set()).add(input_key)
            if kind == 'native_execute':
                successful_inputs.setdefault(row_key, set()).add(input_key)
        if repeated and kind != 'native_execute':
            continue
        if kind in {"queue", "queue_commit", "queue_confirm", "queue_tentative"}:
            row["queued"] += 1
        if kind in {"busy", "queue_locked"}:
            row["queue_blocked"] += 1
        if kind in {"native_execute", "native_interrupt"} and not repeated:
            row["processing"] += 1
        if kind == "native_execute":
            success_token = (input_key, row_key, 'success')
            if not identified or success_token not in observed:
                row["successes"] += 1
            observed.add(success_token)
        if kind in failures:
            row["failures"][kind] = row["failures"].get(kind, 0) + 1
    for key, row in rows.items():
        row['unresolved_inputs'] = len(failed_inputs.get(key, set()) - successful_inputs.get(key, set()))
    return list(rows.values())


def _parent_positions(program, capabilities, positions):
    """只按本次父序列绑定位置，不借用共享编译缓存中的来源。"""
    sources = [None] * len(capabilities.get('precombat_actions', []))
    for index, segment in enumerate(program):
        if isinstance(segment, list):
            sources.append({'segment': index})
        elif segment['kind'] == 'Loop':
            sources.extend({'segment': index, 'loop_block': child}
                           for _ in range(segment['count'])
                           for child in range(len(segment['blocks'])))
        elif segment['kind'] == 'WaitClicks':
            sources.extend([{'segment': index}] * segment['clicks'])
        else:
            sources.append({'segment': index})
    bound = []
    for position in positions:
        row = dict(position)
        click = row['click_position']
        source = sources[click] if 0 <= click < len(sources) else None
        row['source_position'] = dict(source) if source is not None else None
        if source is not None and isinstance(program[source['segment']], dict) and program[source['segment']]['kind'] == 'CastSequence':
            if row['action_position'] is not None:
                row['source_position']['member'] = row['action_position']
        bound.append(row)
    return bound


class TaskStore:
    """任务检查点与成功批次；锁保护心跳与主线程共用的事务。"""
    def __init__(self, destination):
        self.destination = Path(destination)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.destination / 'task.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('ATTACH DATABASE ? AS shared',(str(self.destination.parent/'cache.sqlite3'),))
        self.db.execute('PRAGMA shared.journal_mode=WAL')
        self.db.execute('PRAGMA shared.synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS shared.reusable (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS runtime_progress (id INTEGER PRIMARY KEY, elapsed REAL NOT NULL, status TEXT NOT NULL, inflight TEXT NOT NULL)')
        row = self.db.execute('SELECT value FROM state WHERE id=1').fetchone()
        self.state = json.loads(row[0]) if row else {}
        progress = self.db.execute('SELECT elapsed,status,inflight FROM runtime_progress WHERE id=1').fetchone()
        if progress and progress[0] >= self.state.get('elapsed_seconds', 0):
            self.state.update(elapsed_seconds=progress[0], status=progress[1], inflight=json.loads(progress[2]))
        self.state_write_count = 0
        self.lua_compiler_starts = 0
        self.verified_batches = {}
        self.db.commit()

    def save(self):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))
            if self.state.get('config', {}).get('diagnostic_logging', False):
                self.state_write_count += 1
            self._save_progress()

    def _save_progress(self):
        self.db.execute('INSERT OR REPLACE INTO runtime_progress VALUES (1,?,?,?)',
                        (self.state.get('elapsed_seconds', 0), self.state.get('status', 'running'),
                         _json(self.state.get('inflight', {}))))

    def save_runtime(self):
        with self.lock, self.db:
            self._save_progress()

    def publish(self):
        with self.lock:
            brief = {key: self.state.get(key) for key in
                     ('status', 'phase', 'elapsed_seconds', 'locked_candidate_key', 'completed_batches',
                      'batch_requests', 'batch_cache_hits', 'native_batch_starts',
                      'canonicalized_duplicates', 'error')}
            if not self.state.get('config', {}).get('diagnostic_logging', False):
                for key in ('batch_requests', 'batch_cache_hits', 'native_batch_starts', 'canonicalized_duplicates'):
                    brief.pop(key, None)
            observation = self.state.get("search_observability")
            if observation and observation.get("mode") != "off":
                brief["search_observability"] = _export_search_observability(
                    observation, include_details=False)
            temporary = self.destination / 'progress.pending.json'
            temporary.write_text(_json(brief), encoding='utf-8')
            replace_file(temporary, self.destination / 'progress.json')

    def note_lua_start(self):
        with self.lock:
            if self.state.get('config', {}).get('diagnostic_logging', False):
                self.lua_compiler_starts += 1

    def batch(self, key):
        with self.lock:
            row = self.db.execute('SELECT value FROM batches WHERE key=?', (key,)).fetchone()
            if row is None:
                row = self.db.execute('SELECT value FROM shared.reusable WHERE key=?',(key,)).fetchone()
        if row is None:
            return None
        try:
            value=json.loads(row[0])
            if not isinstance(value,dict) or value.get('status') not in ('success','failed','invalid'):
                raise ValueError('缓存行结构损坏')
            if value['status']=='success' and not {'data_key','request','dps','samples','variance'} <= value.keys():
                raise ValueError('缓存行缺少完整身份')
            return value
        except (ValueError,TypeError):
            self.put_batch(key,dict(status='invalid',error='缓存行损坏'))
            return None

    def put_batch(self, key, value, *, counter=None, verified=False):
        with self.lock, self.db:
            self.verified_batches.pop(key, None)
            self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?)', (key, _json(value)))
            if value.get('status')=='success' and value['request']['purpose']!='final':
                self.db.execute('INSERT OR REPLACE INTO shared.reusable VALUES (?,?)',(key,_json(value)))
            self.state['completed_batches'] = self.db.execute(
                "SELECT count(*) FROM batches WHERE CASE WHEN json_valid(value) THEN json_extract(value,'$.status') END='success'").fetchone()[0]
            if counter is not None and self.state.get('config', {}).get('diagnostic_logging', False):
                self.state[counter] = self.state.get(counter, 0) + 1
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))
            if self.state.get('config', {}).get('diagnostic_logging', False):
                self.state_write_count += 1
            self._save_progress()
            if verified and value.get('status') == 'success':
                self.verified_batches[key] = value

    @contextmanager
    def active(self, runtime):
        """进程崩溃最多按尚未消耗的单批额度扣费，恢复扣除只发生一次。"""
        stop = threading.Event()
        def beat():
            with self.lock:
                self.state['elapsed_seconds'] = runtime.elapsed_seconds
                if self.state.get('status') in ('running','stopping') and (runtime.cancel_event.is_set() or runtime.elapsed_seconds>=runtime.budget_seconds):
                    self.state['status']='stopping'
                self.save_runtime()
                self.publish()
        def heartbeat():
            while not stop.wait(0.5):
                beat()
        self.state['status'] = 'running'
        self.save()
        beat()
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()
            beat()

    def close(self):
        if getattr(self, 'diagnostics_mode', 'off') != 'off':
            diagnostics = dict(getattr(self, 'diagnostic_summary', {}),
                               task_state_writes=self.state_write_count,
                               lua_compiler_starts=self.lua_compiler_starts)
            (self.destination / 'diagnostics.json').write_text(
                _json(diagnostics), encoding='utf-8')
        self.verified_batches.clear()
        self.db.close()


def _score(rows):
    return sum(r['dps'] * r['samples'] for r in rows) / sum(r['samples'] for r in rows)


def _score_bounds(rows):
    count = sum(row['samples'] for row in rows)
    mean = _score(rows)
    variance_sum = sum(row['samples'] * (row['variance'] + (row['dps'] - mean) ** 2)
                       for row in rows)
    error = SCREENING_ERROR_MULTIPLIER * math.sqrt(variance_sum / count / count)
    return mean - error, mean + error


def _tuple(value):
    return tuple(_tuple(v) for v in value) if isinstance(value, list) else value


def optimize(*, profile, character, capabilities, reference, destination, runtime,
             config, condition_key, store, simulation_config=None):
    from engine import check_report, player_report, damage_statistics, CandidateError
    from program import BEHAVIOR_IDENTITY_VERSION
    from sequence import evaluate, compiled_identity
    from simulation_config import config_for
    simulation_config = config_for(simulation_config)
    state = store.state
    verify_behavior_identity_state(state)
    observation_mode = config['search_observability']
    observability = None
    observation_events = {}
    position_jobs = []
    observation_pause_seconds = 0.0
    observation_call_depth = 0
    search_recording_active = state.get('phase', 'search') == 'search'
    if observation_mode != 'off':
        with store.lock:
            observability = state.setdefault(
                'search_observability', _new_search_observability(observation_mode))
            if observability.get('mode') != observation_mode:
                raise ValueError('任务恢复时搜索记录模式不能改变')
            observation_events = {row['event_id']: row for row in observability['details']}
            position_jobs = observability.setdefault('position_jobs', [])

    def serialize_observability(function):
        def call(*args, **kwargs):
            nonlocal observation_pause_seconds, observation_call_depth
            if observability is None:
                return function(*args, **kwargs)
            outermost = observation_call_depth == 0
            started = time.perf_counter() if outermost and search_recording_active else None
            observation_call_depth += 1
            try:
                with store.lock:
                    return function(*args, **kwargs)
            finally:
                observation_call_depth -= 1
                if started is not None:
                    seconds = time.perf_counter() - started
                    observation_pause_seconds += seconds
                    runtime.started += seconds
        return call

    def event_for(work):
        return observation_events.get(work.get('observation_id')) if observability else None

    @serialize_observability
    def method_summary(work):
        if not observability:
            return None
        name = work.get('observation_actual_mutation', 'initial')
        return observability['summary']['methods'].setdefault(name, {
            'attempts': 0,
            'legal_candidates': 0,
            'invalid_candidates': 0,
            'duplicates': 0,
            'score_started': 0,
            'score_completed': 0,
            'route_checks': 0,
            'route_promotions': 0,
            'global_checks': 0,
            'global_promotions': 0,
            'outcomes': {},
            'score_changes': dict(count=0, total=0.0, minimum=None, maximum=None),
            'phase_seconds': {},
        })

    @serialize_observability
    def mark_work(work, flag, counter):
        if not observability:
            return
        internal_flag = 'observation_' + flag
        if work.get(internal_flag):
            return
        work[internal_flag] = True
        observability['summary'][counter] += 1
        stats = method_summary(work)
        stats[counter] += 1
        row = event_for(work)
        if row is not None:
            row[flag] = True

    @serialize_observability
    def mark_candidate(work, key=None, error=None):
        if not observability or work.get('observation_candidate_recorded'):
            return
        work['observation_candidate_recorded'] = True
        summary = observability['summary']
        row = event_for(work)
        if row is not None:
            row['candidate_identity'] = key
            row['legal'] = error is None
            row['illegal_reason'] = str(error) if error is not None else None
        if error is None:
            summary['legal_candidates'] += 1
            method_summary(work)['legal_candidates'] += 1
        else:
            summary['invalid_candidates'] += 1
            method_summary(work)['invalid_candidates'] += 1
            summary['invalid_reasons'][str(error)] = summary['invalid_reasons'].get(str(error), 0) + 1

    @serialize_observability
    def mark_duplicate(work, reason):
        if not observability or work.get('observation_duplicate_recorded'):
            return
        work['observation_duplicate_recorded'] = True
        summary = observability['summary']
        summary['duplicates'] += 1
        summary['duplicate_reasons'][reason] = summary['duplicate_reasons'].get(reason, 0) + 1
        method_summary(work)['duplicates'] += 1
        row = event_for(work)
        if row is not None:
            row['duplicate_reason'] = reason

    @serialize_observability
    def mark_promotion(work, kind, *, checked=None, promoted=None):
        if not observability:
            return
        summary = observability['summary']
        stats = method_summary(work)
        row = event_for(work)
        if checked:
            flag = 'observation_' + kind + '_checked'
            if not work.get(flag):
                work[flag] = True
                counter = kind + '_checks'
                summary[counter] += 1
                stats[counter] += 1
                if row is not None:
                    row[kind + '_promotion']['checked'] = True
        if promoted is not None:
            flag = 'observation_' + kind + '_promoted'
            if promoted and not work.get(flag):
                work[flag] = True
                counter = kind + '_promotions'
                summary[counter] += 1
                stats[counter] += 1
            if row is not None:
                row[kind + '_promotion']['promoted'] = bool(promoted)
                row[kind + '_promotion']['complete'] = True

    @serialize_observability
    def add_stage_time(work, stage, seconds):
        if not observability:
            return
        flag = 'observation_timed_' + stage
        if work.get(flag):
            return
        work[flag] = True
        seconds = max(0.0, seconds)
        summary = observability['summary']
        summary['phase_seconds'][stage] = summary['phase_seconds'].get(stage, 0.0) + seconds
        stats = method_summary(work)
        stats['phase_seconds'][stage] = stats['phase_seconds'].get(stage, 0.0) + seconds
        row = event_for(work)
        if row is not None:
            row['stage_seconds'][stage] = seconds

    @serialize_observability
    def add_score_change(work, change):
        changes = method_summary(work).setdefault(
            'score_changes', dict(count=0, total=0.0, minimum=None, maximum=None))
        changes['count'] += 1
        changes['total'] += change
        changes['minimum'] = change if changes['minimum'] is None else min(changes['minimum'], change)
        changes['maximum'] = change if changes['maximum'] is None else max(changes['maximum'], change)
        changes['mean'] = changes['total'] / changes['count']

    @serialize_observability
    def mark_outcome(work, outcome):
        if not observability or work.get('observation_outcome') is not None:
            return
        work['observation_outcome'] = outcome
        row = event_for(work)
        if row is not None:
            row['outcome'] = outcome
        summary = observability['summary']['outcomes']
        summary[outcome] = summary.get(outcome, 0) + 1
        outcomes = method_summary(work).setdefault('outcomes', {})
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    @serialize_observability
    def add_position_summary(work, rows):
        if not observability:
            return
        positions = observability['summary']['positions']
        for row in rows:
            key = _json([row['candidate_identity'], row['click_position'],
                         row['action_position'], row['action']])
            current = positions.get(key)
            if current is None:
                positions[key] = dict(row, failures=dict(row['failures']))
                continue
            _merge_position_counts(current, row)
        event = event_for(work)
        if event is not None:
            event_rows = event.setdefault('position_summary', [])
            event_positions = {
                _json([row['candidate_identity'], row['click_position'],
                       row['action_position'], row['action']]): row
                for row in event_rows
            }
            for position in rows:
                key = _json([position['candidate_identity'], position['click_position'],
                             position['action_position'], position['action']])
                current = event_positions.get(key)
                if current is None:
                    current = dict(position, failures=dict(position['failures']))
                    event_rows.append(current)
                    event_positions[key] = current
                else:
                    _merge_position_counts(current, position)
            event['position_comparison_count'] = event.get('position_comparison_count', 0) + 1

    def queue_position_observation(work, program, comparison):
        if observability is not None:
            with store.lock:
                if any(job['event_id'] == work['observation_id'] and job['comparison'] == comparison
                       for job in position_jobs):
                    return
                position_jobs.append(dict(
                    event_id=work['observation_id'], program=_copy_program(program),
                    comparison=comparison, status='pending'))

    def _merge_position_counts(current, row):
        for field in ('turns', 'queued', 'queue_blocked', 'processing', 'successes'):
            current[field] += row[field]
        for failure, count in row['failures'].items():
            current['failures'][failure] = current['failures'].get(failure, 0) + count

    def make_observation_event(event_id, *, parent_identity, sampled_mutation,
                               actual_mutation, modification_position):
        return dict(
            event_id=event_id,
            parent_identity=parent_identity,
            sampled_mutation=sampled_mutation,
            actual_mutation=actual_mutation,
            modification_position=modification_position,
            candidate_identity=None,
            legal=None,
            illegal_reason=None,
            duplicate_reason=None,
            parent_score=None,
            candidate_score=None,
            score_change=None,
            score_started=False,
            score_completed=False,
            route_promotion=dict(checked=False, promoted=False, complete=False),
            global_promotion=dict(checked=False, promoted=False, complete=False),
            outcome=None,
            stage_seconds={},
        )

    @serialize_observability
    def reserve_initial_observation():
        event_id = observability['next_event_id']
        observability['next_event_id'] += 1
        event = make_observation_event(
            event_id, parent_identity=None, sampled_mutation='initial',
            actual_mutation='initial', modification_position=None)
        if observation_mode == 'full':
            observability['details'].append(event)
            observation_events[event_id] = event
        observability['summary']['initial_candidates'] += 1
        return event_id

    @serialize_observability
    def commit_mutation_observations(events):
        if not observability:
            return
        summary = observability['summary']
        for event in events:
            summary['mutation_attempts'] += 1
            sampled = event['sampled_mutation'] or 'unknown'
            actual = event['actual_mutation'] or 'unknown'
            summary['sampled_mutations'][sampled] = summary['sampled_mutations'].get(sampled, 0) + 1
            summary['actual_mutations'][actual] = summary['actual_mutations'].get(actual, 0) + 1
            work = {'observation_actual_mutation': actual}
            stats = method_summary(work)
            stats['attempts'] += 1
            if event['legal'] is True:
                summary['legal_candidates'] += 1
                stats['legal_candidates'] += 1
            elif event['legal'] is False:
                summary['invalid_candidates'] += 1
                stats['invalid_candidates'] += 1
                reason = event['illegal_reason'] or 'unknown'
                summary['invalid_reasons'][reason] = summary['invalid_reasons'].get(reason, 0) + 1
            if event['duplicate_reason']:
                summary['duplicates'] += 1
                stats['duplicates'] += 1
                reason = event['duplicate_reason']
                summary['duplicate_reasons'][reason] = summary['duplicate_reasons'].get(reason, 0) + 1
            outcome = ('invalid_candidate' if event['legal'] is False else
                       'duplicate' if event['duplicate_reason'] else None)
            if outcome:
                event['outcome'] = outcome
                outcomes = summary['outcomes']
                outcomes[outcome] = outcomes.get(outcome, 0) + 1
                method_outcomes = stats.setdefault('outcomes', {})
                method_outcomes[outcome] = method_outcomes.get(outcome, 0) + 1
            for stage, seconds in event['stage_seconds'].items():
                summary['phase_seconds'][stage] = summary['phase_seconds'].get(stage, 0.0) + seconds
                stats['phase_seconds'][stage] = stats['phase_seconds'].get(stage, 0.0) + seconds
            if observation_mode == 'full':
                observability['details'].append(event)
                observation_events[event['event_id']] = event
        observability['next_event_id'] += len(events)

    if 'behavior_identity_version' not in state:
        state['behavior_identity_version'] = BEHAVIOR_IDENTITY_VERSION
    state.setdefault('run_nonce', uuid.uuid4().hex)
    state.setdefault('phase', 'search')
    state.setdefault('archive', [])
    state.setdefault('pending', [])
    state.setdefault('rounds', 0)
    state.setdefault('no_improvement', 0)
    state.setdefault('seen', [])
    state.setdefault('chains', [])
    state.setdefault('evaluated_keys', [])
    if config['diagnostic_logging']:
        for name in ('canonicalized_duplicates', 'batch_requests', 'batch_cache_hits', 'native_batch_starts'):
            state.setdefault(name, 0)
    state.setdefault('completed_batches', 0)
    state.setdefault('batch_estimate', 0.25)
    starts = state.get('starts')
    if starts is None:
        starts = initial_programs(capabilities, reference, config['random_seed'])
    observable_flags = tuple(name for name in ('target', 'combat', 'shift', 'ctrl', 'alt')
                             if any(kind == name for _, kind in config['reset_events']))
    state.setdefault('starts', starts)
    rng = random.Random(config['random_seed'])
    if state.get('rng'):
        rng.setstate(_tuple(state['rng']))
    candidates = {}
    prepared = {}
    candidate_compilations = 0
    diagnostic_events = []
    from result_store import CANDIDATE_SCHEMA, write as write_records, write_batch, write_traces

    def prepare(program):
        source_key = program_key(program)
        if source_key in prepared:
            return prepared[source_key]
        from program import canonicalize_search_program
        try:
            prepared[source_key] = canonicalize_search_program(program, capabilities)
        except ValueError as error:
            raise CandidateError(str(error)) from error
        return prepared[source_key]

    def candidate(program):
        nonlocal candidate_compilations
        from program import compile_program
        try:
            canonical = prepare(program)
            key = canonical['identity']
            compiled = candidates.get(key)
            if compiled is not None:
                return compiled
            if compiled is None:
                saved = next((r for r in state['archive'] if r['key'] == key and r.get('candidate')), None)
                if (saved and digest(saved['candidate']) == saved['candidate_sha256']
                        and canonical['form'] == compiled_identity(saved['candidate'])):
                    compiled = saved['candidate']
                else:
                    compiled = compile_program(canonical['program'],
                                               destination / 'exports' / key,
                                               identity=reference['identity'], runtime=runtime,
                                               on_lua_start=store.note_lua_start)
                    if config['diagnostic_logging']:
                        candidate_compilations += 1
                    if canonical['form'] != compiled_identity(compiled):
                        raise CandidateError('候选标准形式与编译计划不一致')
                candidates[key] = compiled
                candidate_data_key = digest(dict(run_id=state['run_id'], candidate_key=key))
                search_order = next((index for index, row in enumerate(state['archive'])
                                     if row.get('key') == key), len(state['archive']))
                write_records('candidates', candidate_data_key, [dict(
                    run_id=state['run_id'], candidate_key=key,
                    candidate_data_key=candidate_data_key,
                    search_order=search_order,
                    source=compiled.get('source', 'search'),
                    program=canonical['program'], export_text=compiled['text'],
                    simulation=compiled.get('simulation'),
                    selected_sequence=compiled.get('selected_sequence'),
                    selected_version=compiled.get('selected_version'),
                    import_sha256=compiled.get('import_sha256'),
                    game_validation=compiled.get('game_validation'))],
                    schema=CANDIDATE_SCHEMA)
            if config['diagnostics'] == 'full':
                diagnostic_events.append(dict(event='candidate_prepared', behavior_identity=key,
                                              candidate_compilations_so_far=candidate_compilations))
        except CandidateError:
            raise
        except ValueError as error:
            raise CandidateError(str(error)) from error
        return candidates[key]

    def candidate_key(program):
        return prepare(program)['identity']

    def score_variance(report):
        variance = damage_statistics(report, character).get('variance')
        if type(variance) not in (int, float) or not math.isfinite(variance) or variance < 0:
            raise CandidateError('伤害方差无效')
        return variance

    def batch(program, purpose, index, iterations, scenario='nominal', trace=False):
        runtime.check()
        seed_offset = {'search': 0, 'validation': 100000, 'final': 200000}[purpose]
        # 每次运行独立的最终样本，恢复复用同一编号，不借用旧任务见过的最终样本。
        nonce = int(state['run_nonce'][:8], 16) % 100000000 if purpose == 'final' else 0
        seed = config['random_seed'] + seed_offset + index + DEFAULT_SCENARIOS.index(scenario) * 1000 + nonce
        input_seed = seed + 500000
        times = input_times(scenario, input_seed, config["input_interval_ms"])
        compiled = candidate(program)
        behavior_id = candidate_key(program)
        request = dict(condition=condition_key, program=compiled_identity(compiled), purpose=purpose,
                        behavior_identity=behavior_id,
                        seed=seed, input_seed=input_seed, iterations=iterations, times=times,
                        stats=STATS_VERSION, trace=trace,
                        reset_events=[list(row) for row in config['reset_events']])
        key = digest(request)
        program_identity = json.dumps(request['program'], ensure_ascii=False,
                                      sort_keys=True, separators=(',', ':'))
        with store.lock:
            if config['diagnostic_logging']:
                state['batch_requests'] += 1
            verified = store.verified_batches.get(key)
            if verified is not None and config['diagnostic_logging']:
                state['batch_cache_hits'] += 1
        if verified is not None:
            runtime.check()
            return dict(verified, cached=True)
        cached = store.batch(key)
        if cached and cached['status'] == 'success':
            try:
                from result_store import one as read_record
                saved = read_record('batches', 'batch_key', cached['data_key'])
                report = saved['report'] if saved is not None else None
                if (cached['request'] != request or not isinstance(report, dict)
                        or saved['batch_key'] != key
                        or saved['condition_key'] != request['condition']
                        or saved['candidate_key'] != request['behavior_identity']
                        or saved['purpose'] != request['purpose']
                        or saved.get('program_identity') != program_identity
                        or saved['seed'] != request['seed']
                        or saved['input_seed'] != request['input_seed']
                        or saved['iterations'] != request['iterations']
                        or saved.get('batch_index') != index
                        or saved.get('scenario') != scenario
                        or saved.get('stats_version') != request['stats']
                        or saved['times'] != request['times']
                        or saved['trace'] != request['trace']
                        or (saved.get('reset_events') or []) != [
                            dict(ms=ms, kind=kind) for ms, kind in request['reset_events']]):
                    raise ValueError('缓存报告或请求身份缺失')
                summary = check_report(report, character, iterations,
                                       simulation_config=simulation_config)
                if (summary['dps'] != cached['dps'] or summary['samples'] != cached['samples']
                        or score_variance(report) != cached['variance']
                        or saved['dps'] != cached['dps'] or saved['samples'] != cached['samples']
                        or saved['variance'] != cached['variance']):
                    raise ValueError('缓存摘要不符')
                store.put_batch(key, cached, counter='batch_cache_hits', verified=True)
                return dict(cached, cached=True)
            except (ValueError, OSError, KeyError, TypeError, RuntimeError):
                store.put_batch(key, dict(status='invalid', request=request))
        elif cached and cached['status'] == 'failed':
            raise CandidateError('该批次此前失败，不自动重跑: ' + cached['error'])
        runtime.check()
        if runtime.remaining_seconds < state['batch_estimate']:
            raise BudgetExceeded('剩余阶段时间不足一个预计批次')
        allowance = min(30, runtime.remaining_seconds)
        with store.lock:
            state.setdefault('inflight', {})[key] = dict(start=runtime.elapsed_seconds, allowance=allowance)
            if purpose=='search' and index!=99 and behavior_id not in state['evaluated_keys']:
                state['evaluated_keys'].append(behavior_id)
            store.save()
        folder = destination / 'batches' / key
        started = time.monotonic()
        report_valid = False
        center_stored = False
        try:
            kwargs = {'reset_events': list(config['reset_events'])} if config['reset_events'] else {}
            def native_started():
                with store.lock:
                    state['native_batch_starts'] = state.get('native_batch_starts', 0) + 1
            result = evaluate(profile, compiled, folder, character=character, iterations=iterations, seed=seed,
                              input_times=times, trace=trace, runtime=runtime,
                              simulation_config=simulation_config, on_native_start=native_started, **kwargs)
            variance = score_variance(result['report'])
            report_valid = True
            row = dict(status='success', request=request, dps=result['summary']['dps'],
                       samples=result['summary']['samples'], variance=variance, requested_iterations=iterations,
                       data_key=key,
                       feedback=feedback_from_trace(result['trace'],[a['simc_action'] for a in capabilities['actions']],
                           player_report(result['report'], character)['collected_data'].get('resource_overflowed',{}).get(reference['identity']['resource'],{}).get('mean',0)>0,
                           {v['simc_action']: a['simc_action'] for a in capabilities['actions'] for v in a.get('variants',[a])}) if trace else None)
            if trace:
                row['position_summary'] = _position_observations(
                    compiled, behavior_id, result['trace'])
            from result_store import write as write_records
            stored = dict(batch_key=key, run_id=state['run_id'],
                          condition_key=request['condition'],
                          candidate_key=request['behavior_identity'],
                          program_identity=program_identity, purpose=request['purpose'],
                          batch_index=index, scenario=scenario, stats_version=request['stats'],
                          seed=request['seed'],
                          input_seed=request['input_seed'], iterations=iterations,
                          times=request['times'], trace=trace, dps=row['dps'],
                          samples=row['samples'], variance=row['variance'],
                          requested_iterations=iterations, report=result['report'])
            if request['reset_events']:
                stored['reset_events'] = [dict(ms=ms, kind=kind)
                                          for ms, kind in request['reset_events']]
            write_batch(key, stored, diagnostic_logging=config['diagnostic_logging'])
            center_stored = True
            if trace and config['diagnostic_logging']:
                write_traces(key, state['run_id'], result['trace'], batch_key=key)
            with store.lock:
                state['inflight'].pop(key, None)
                state['batch_estimate'] = max(0.1, 0.8 * state['batch_estimate'] + 0.2 * (time.monotonic()-started))
                store.put_batch(key, row, verified=True)
            return row
        except (BudgetExceeded, TaskCancelled):
            raise
        except CandidateError as error:
            store.put_batch(key, dict(status='failed', request=request, error=str(error)))
            raise
        finally:
            if center_stored or not report_valid:
                (folder / 'native.json').unlink(missing_ok=True)
            (folder / 'native.pending.json').unlink(missing_ok=True)
            if not config['diagnostic_logging']:
                from engine import discard_diagnostic_files
                discard_diagnostic_files(folder)
            with store.lock:
                if state.setdefault('inflight', {}).pop(key, None) is not None:
                    store.save()

    def pair(first, second, purpose, count, scenario='nominal'):
        rows = [[], []]
        # 外层只允许两个引擎；结果始终按预分配的对象顺序消费。
        for index in range(count):
            candidate(first)
            candidate(second)
            if candidate_key(first) == candidate_key(second):
                row = batch(first, purpose, index,
                            config['final_iterations'] if purpose == 'final' else config['iterations'],
                            scenario, trace=False)
                rows[0].append(row)
                rows[1].append(row)
                continue
            with ThreadPoolExecutor(max_workers=config['max_processes']) as pool:
                futures = [pool.submit(batch, program, purpose, index,
                                       config['final_iterations'] if purpose == 'final' else config['iterations'],
                                       scenario, trace=False)
                           for side, program in enumerate((first, second))]
                for side, future in enumerate(futures):
                    rows[side].append(future.result())
        return rows

    def append_score(program, rows, index):
        target = config['batch_targets'][index]
        previous = config['batch_targets'][index - 1] if index else 0
        row = batch(program, 'search', index, target - previous,
                    trace=(config['diagnostic_logging'] and not state['archive'] and index == 0))
        rows.append(dict(row, target=target))

    def screen_round():
        pending = state['pending']
        if all(work.get('screen_complete') for work in pending):
            return
        for index in range(len(config['batch_targets'])):
            active = [work for work in pending if not work.get('screened_out') and not work.get('score_error')]
            for work in active:
                rows = work.setdefault('score_batches', [])
                try:
                    if len(rows) <= index:
                        append_score(work['program'], rows, index)
                        store.save()
                except CandidateError as error:
                    work['score_error'] = str(error)
                    store.save()
            active = [work for work in active if not work.get('score_error')]
            if not active:
                break
            bounds = [_score_bounds(work['score_batches'][:index + 1]) for work in active]
            best_lower = max(lower for lower, upper in bounds)
            for work, (lower, upper) in zip(active, bounds):
                if upper < best_lower:
                    work['screened_out'] = True
            store.save()
            if sum(not work.get('screened_out') for work in active) <= 1:
                break
        for work in pending:
            work['screen_complete'] = True
        store.save()

    def record(program, rows=None):
        compiled = candidate(program)  # 编译合法性必须先于任何原生计算。
        key = candidate_key(program)
        if rows is None:
            rows = []
            targets = len(config['batch_targets']) if not state['archive'] else 1
            for index in range(targets):
                append_score(program, rows, index)
        return dict(key=key, program=program, batches=rows, score=_score(rows),
                    candidate=compiled,candidate_sha256=digest(compiled))

    def challenges(current, opponent):
        for index in range(len(config['batch_targets'])):
            for item in (current, opponent):
                if len(item['batches']) <= index:
                    append_score(item['program'], item['batches'], index)
                    item['score'] = _score(item['batches'])
                    store.save()
            left = current['batches'][:index + 1]
            right = opponent['batches'][:index + 1]
            low, high = _score_bounds(left)
            other_low, other_high = _score_bounds(right)
            if high < other_low:
                return False
            if low > other_high:
                return True
        return _score(left) > _score(right)

    def search():
        runtime.phase_limit = min(config['search_budget_seconds'], config['total_budget_seconds'])
        if not state['archive'] and not state['pending']:
            with store.lock:
                state['pending'] = []
                for program in starts[:config['candidate_limit']]:
                    work = dict(program=program, start=True)
                    if observability:
                        work.update(observation_id=reserve_initial_observation(),
                                    observation_actual_mutation='initial')
                    state['pending'].append(work)
                store.save()
        while len(state['evaluated_keys']) < config['candidate_limit'] or state['pending']:
            runtime.check()
            if not state['pending']:
                if state['no_improvement'] >= config['no_improvement_rounds']:
                    state['stop_reason']='no_improvement'
                    break
                lane_index=state['rounds']%len(state['chains'])
                lane=state['chains'][lane_index]
                base = next(r for r in state['archive'] if r['key'] == lane['best'])
                diagnostic=batch(base['program'],'search',99,2,trace=True)
                feedback = dict(diagnostic['feedback'])
                feedback['positions'] = _parent_positions(
                    base['program'], capabilities, diagnostic.get('position_summary', []))
                lane.update(feedback=feedback,feedback_source=base['key'])
                generated = []
                generation_observations = []
                existing = set(state['seen'])
                existing_sources = {program_key(record['program']) for record in state['archive']}
                for attempt in range(160):
                    if len(generated) >= min(config['round_candidate_limit'], config['candidate_limit']-len(state['evaluated_keys'])):
                        break
                    kwargs = {'reset_flags': observable_flags} if observable_flags else {}
                    mutation_observation = {} if observability else None
                    mutation_started = time.perf_counter() if observability else None
                    mutation_kwargs = dict(feedback=lane['feedback'], excluded_programs=existing_sources, **kwargs)
                    if mutation_observation is not None:
                        mutation_kwargs['observation'] = mutation_observation
                    program = mutate(base['program'], capabilities, rng, **mutation_kwargs)
                    if rng.randrange(16)==0:
                        program = [[a['simc_action']] for a in capabilities['actions']]
                        rng.shuffle(program)
                        if mutation_observation is not None:
                            mutation_observation.update(
                                actual_mutation='shuffle', modification_position={'segments': 'all'})
                    if mutation_observation is not None and program == base['program']:
                        mutation_observation.update(actual_mutation='no_change', modification_position=None)
                    mutation_seconds = time.perf_counter() - mutation_started if observability else 0.0
                    event_id = (observability['next_event_id'] + len(generation_observations)
                                if observability else None)
                    event = (make_observation_event(
                        event_id, parent_identity=base['key'],
                        sampled_mutation=mutation_observation['sampled_mutation'],
                        actual_mutation=mutation_observation['actual_mutation'],
                        modification_position=mutation_observation['modification_position'])
                             if mutation_observation is not None else None)
                    if event is not None:
                        event['parent_score'] = base['score']
                        event['stage_seconds']['mutation'] = mutation_seconds
                    candidate_check_started = time.perf_counter() if observability else None
                    try:
                        key = candidate_key(program)
                    except CandidateError as error:
                        if event is not None:
                            event.update(legal=False, illegal_reason=str(error))
                            event['stage_seconds']['candidate_check'] = (
                                time.perf_counter() - candidate_check_started)
                            generation_observations.append(event)
                        continue
                    if event is not None:
                        event.update(candidate_identity=key, legal=True)
                        event['stage_seconds']['candidate_check'] = (
                            time.perf_counter() - candidate_check_started)
                    if key == base['key']:
                        duplicate_reason = 'parent_unchanged'
                    elif key in state['seen']:
                        duplicate_reason = 'already_seen'
                    elif key in existing:
                        duplicate_reason = 'same_round'
                    else:
                        duplicate_reason = None
                    if event is not None:
                        event['duplicate_reason'] = duplicate_reason
                        generation_observations.append(event)
                    if duplicate_reason is not None:
                        if config['diagnostic_logging']:
                            state['canonicalized_duplicates'] += 1
                        continue
                    existing.add(key)
                    existing_sources.add(program_key(program))
                    work = dict(program=program, start=False, lane=lane_index)
                    if event is not None:
                        work.update(observation_id=event_id,
                                    observation_actual_mutation=event['actual_mutation'],
                                    observation_parent_score=base['score'],
                                    observation_candidate_recorded=True)
                    generated.append(work)
                commit_mutation_observations(generation_observations)
                if not generated:
                    state['stop_reason'] = 'space_stalled'
                    store.save()
                    break
                state['pending'] = generated
                state['round_improved'] = False
                state['full_round'] = len(generated)==config['round_candidate_limit']
                state['rng'] = rng.getstate()
                store.save()
            work = state['pending'][0]
            key = program_key(work['program'])
            scoring_started = None
            try:
                key = candidate_key(work['program'])
                mark_candidate(work, key=key)
                if key in state['seen']:
                    if config['diagnostic_logging']:
                        state['canonicalized_duplicates'] += 1
                    mark_duplicate(work, 'already_scored')
                    mark_outcome(work, 'duplicate')
                    state['pending'].pop(0)
                    store.save()
                    continue
                if observability:
                    mark_work(work, 'score_started', 'score_started')
                    scoring_started = time.perf_counter()
                if not work['start']:
                    screen_round()
                    if work.get('score_error'):
                        raise CandidateError(work['score_error'])
                current = record(work['program'], work.get('score_batches'))
                if observability:
                    with store.lock:
                        row = event_for(work)
                        if row is not None:
                            row['candidate_score'] = current['score']
                            parent_score = work.get('observation_parent_score')
                            if parent_score is not None:
                                row['parent_score'] = parent_score
                                row['score_change'] = current['score'] - parent_score
                                add_score_change(work, row['score_change'])
                    add_stage_time(work, 'scoring', time.perf_counter() - scoring_started)
                    mark_work(work, 'score_completed', 'score_completed')
                    mark_outcome(work, 'scored')
            except CandidateError as error:
                if observability:
                    mark_candidate(work, error=error)
                    mark_outcome(work, 'score_failed' if scoring_started is not None
                                 else 'invalid_candidate')
                    with store.lock:
                        row = event_for(work)
                        if row is not None and work.get('observation_score_started'):
                            row['score_error'] = str(error)
                    if scoring_started is not None and not work.get('observation_timed_scoring'):
                        add_stage_time(work, 'scoring', time.perf_counter() - scoring_started)
                state.setdefault('errors', []).append(
                    dict(program=program_key(work['program']), error=str(error)))
                current = None
            if current:
                route_promoted = global_promoted = False
                if not state['archive']:
                    state['best']=key
                else:
                    opponent_key=state['best'] if work['start'] else state['chains'][work['lane']]['best']
                    opponent=next(r for r in state['archive'] if r['key']==opponent_key)
                    if not work.get('screened_out') and challenges(current, opponent):
                        if observability:
                            if work['start']:
                                mark_promotion(work, 'global', checked=True)
                            else:
                                mark_promotion(work, 'route', checked=True)
                                if opponent_key == state['best']:
                                    mark_promotion(work, 'global', checked=True)
                            promotion_started = time.perf_counter()
                        try:
                            queue_position_observation(work, current['program'], 'route')
                            left,right=pair(current['program'],opponent['program'],'validation',config['validation_batches'])
                        finally:
                            if observability:
                                add_stage_time(work, 'promotion_check',
                                              time.perf_counter() - promotion_started)
                        ci=paired_ci([r['dps'] for r in left],[r['dps'] for r in right])
                        current['validation']=dict(comparison=summarize_pairs(left,right),candidate=left,control=right)
                        route_promoted = bool(ci and ci[0] > 0)
                        if observability:
                            if work['start']:
                                mark_promotion(work, 'global', promoted=route_promoted)
                            else:
                                mark_promotion(work, 'route', promoted=route_promoted)
                                if opponent_key == state['best']:
                                    mark_promotion(work, 'global', promoted=route_promoted)
                        if route_promoted:
                            global_best=next(r for r in state['archive'] if r['key']==state['best'])
                            if opponent_key==state['best']:
                                global_promoted = True
                            elif challenges(current, global_best):
                                if observability:
                                    mark_promotion(work, 'global', checked=True)
                                    global_started = time.perf_counter()
                                try:
                                    queue_position_observation(work, current['program'], 'global')
                                    left,right=pair(current['program'],global_best['program'],'validation',config['validation_batches'])
                                finally:
                                    if observability:
                                        add_stage_time(work, 'global_check',
                                                      time.perf_counter() - global_started)
                                ci=paired_ci([r['dps'] for r in left],[r['dps'] for r in right])
                                current['global_validation']=dict(comparison=summarize_pairs(left,right),candidate=left,control=right)
                                global_promoted = bool(ci and ci[0] > 0)
                                if observability:
                                    mark_promotion(work, 'global', promoted=global_promoted)
                state['archive'].append(current)
                # 后续加测可能取消；只有候选完整入档后才发布赢家指针。
                if route_promoted and not work['start']:
                    state['chains'][work['lane']]['best'] = key
                if global_promoted:
                    state['best'] = key
                    state['round_improved'] = True
                if work['start']:
                    state['chains'].append(dict(best=key,visited=[key],rounds=0))
                else:
                    state['chains'][work['lane']]['visited'].append(key)
            state['seen'].append(key)
            state['pending'].pop(0)
            if not state['pending'] and not work['start']:
                state['rounds'] += 1
                state['chains'][work['lane']]['rounds']+=1
                if state['full_round']:
                    state['no_improvement'] = 0 if state.get('round_improved') else state['no_improvement']+1
            store.save()
        state.setdefault('stop_reason', 'candidate_limit')

    search_interrupted = None
    if state['phase'] == 'search':
        try:
            search()
        except (BudgetExceeded, TaskCancelled) as error:
            state['stop_reason'] = ('cancelled' if isinstance(error, TaskCancelled)
                                    else 'search_deadline')
            pending_outcome = ('cancelled_not_scored' if isinstance(error, TaskCancelled)
                               else 'budget_not_scored')
            for work in state['pending']:
                mark_outcome(work, pending_outcome)
            if isinstance(error, TaskCancelled):
                search_interrupted = error
            store.save()
        finally:
            search_recording_active = False
            runtime.started -= observation_pause_seconds
            runtime.phase_limit = runtime.budget_seconds
        if not state['archive']:
            if isinstance(search_interrupted, TaskCancelled):
                raise search_interrupted
            raise BudgetExceeded('搜索窗口内未完成有效初始序列')
        state['locked_candidate_key'] = state['best']
        state['phase'] = 'search' if search_interrupted else 'done'
        store.save()
        store.publish()
    best = next(r for r in state['archive'] if r['key'] == state['locked_candidate_key'])
    final = dict(dataset='final', status='not_requested', scenarios={})
    interrupted = search_interrupted

    if observability is not None and not isinstance(interrupted, TaskCancelled):
        observation_runtime = runtime
        with store.lock:
            observability['summary'].pop('position_observation_incomplete', None)
        for job_index, job in enumerate(position_jobs):
            if job.get('status') == 'completed':
                continue
            work = {'observation_id': job['event_id']}
            program = job['program']
            comparison = job['comparison']
            try:
                compiled = candidate(program)
                seed = config['random_seed'] + 100000
                observation_kwargs = ({'reset_events': list(config['reset_events'])}
                                      if config['reset_events'] else {})
                traced = evaluate(
                    profile, compiled,
                    destination / 'observability' / f"{work['observation_id']}-{comparison}-{job_index}",
                    character=character, iterations=2, seed=seed,
                    input_times=input_times('nominal', seed + 500000,
                                            config['input_interval_ms']),
                    trace=True, runtime=observation_runtime,
                    simulation_config=simulation_config,
                    **observation_kwargs,
                )
                trace_key = digest(dict(run_id=state['run_id'], event_id=work['observation_id'],
                                        comparison=comparison, job_index=job_index))
                write_batch(trace_key, dict(
                    batch_key=trace_key, run_id=state['run_id'], purpose='position_observation',
                    candidate_key=candidate_key(program), seed=seed, requested_iterations=2,
                    samples=traced['summary']['samples'], dps=traced['summary']['dps'],
                    report=traced['report']), diagnostic_logging=config['diagnostic_logging'])
                observation_folder = destination / 'observability' / f"{work['observation_id']}-{comparison}-{job_index}"
                (observation_folder / 'native.json').unlink(missing_ok=True)
                if config['diagnostic_logging']:
                    write_traces(trace_key, state['run_id'], traced['trace'], batch_key=trace_key)
                add_position_summary(
                    work, _position_observations(
                        compiled, candidate_key(program), traced['trace']))
                with store.lock:
                    job['status'] = 'completed'
            except TaskCancelled as error:
                with store.lock:
                    observability['summary']['position_observation_incomplete'] = True
                interrupted = error
                break
            except BudgetExceeded:
                with store.lock:
                    observability['summary']['position_observation_incomplete'] = True
                break
    chosen = best
    result = dict(status='completed', phase='done',
                  search=dict(dataset='search', starts=starts, records=state['archive'], chains=state['chains'],rounds=state['rounds'],
                              candidate_count=len(state['evaluated_keys']),unique_candidates=len(state['seen']),
                              errors=state.get('errors', []),
                              partial_round=bool(state['pending']) or not state.get('full_round',True),stop_reason=state.get('stop_reason')),
                  validation=dict(dataset='validation',records=[r[k] for r in state['archive'] for k in ('validation','global_validation') if k in r]), final=final, locked_candidate_key=state['locked_candidate_key'],
                  candidate=candidate(chosen['program']), independent_validation_complete=False,
                  improvement='search_result',
                  search_result=dict(dps=chosen['score'],
                                     samples=sum(row['samples'] for row in chosen['batches']),
                                     reference_dps=reference['dps'],
                                     reference_ratio=chosen['score']/reference['dps'] if reference['dps'] else None),
                  selected_candidate_key=chosen['key'], native_reference=reference,
                  elapsed_seconds=runtime.elapsed_seconds, completed_batches=state['completed_batches'])
    if config['diagnostic_logging']:
        result['search'].update({name: state[name] for name in
                                ('canonicalized_duplicates', 'batch_requests', 'batch_cache_hits', 'native_batch_starts')})
    if observability:
        with store.lock:
            result['search']['observability'] = _export_search_observability(observability)
    if config['diagnostics'] != 'off':
        result['search']['diagnostics'] = dict(
            mode=config['diagnostics'], task_state_writes=store.state_write_count,
            candidate_compilations=candidate_compilations,
            lua_compiler_starts=store.lua_compiler_starts)
        if config['diagnostics'] == 'full':
            result['search']['diagnostics']['events'] = diagnostic_events
        store.diagnostics_mode = config['diagnostics']
        store.diagnostic_summary = result['search']['diagnostics']
    result['candidate']['simulation'] = 'passed_native_model'
    if interrupted:
        result['status'] = 'cancelled' if isinstance(interrupted, TaskCancelled) else 'completed'
        result['phase'] = 'search' if isinstance(interrupted, TaskCancelled) else 'done'
    store.save()
    return result
