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


SEARCH_ALGORITHM = "multi-start-local-v1"
STATS_VERSION = "paired-bootstrap-v1"
DEFAULT_SCENARIOS = ("nominal", "jitter", "slow", "pause", "phase")
DEFAULT_CONFIG = {
    "total_budget_seconds": 600.0,
    "search_budget_seconds": 420.0,
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
    for key, maximum in (('total_budget_seconds',600),('search_budget_seconds',420)):
        value=config[key]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= maximum:
            raise ValueError('计算预算必须在已确认上限内')
    if config['search_budget_seconds'] >= config['total_budget_seconds']:
        raise ValueError('必须为最终复测保留时间')
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


def mutate(program, capabilities, rng, *, feedback=None, reset_flags=(), observation=None):
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
    if operation != "loop" and feedback and rng.random() < 0.5:
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
        replacement = rng.choice(available)
        action = rng.randrange(len(source[block]))
        source[block][action] = replacement
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
        target = rng.randrange(len(source) + 1)
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
            block.insert(index, rng.choice(available))
            position = {"segment": block_index, "action": index}
    elif operation == "loop":
        if wait_indices:
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
        loop["count"] = 3 if loop["count"] == 2 else 2
        position = {"segment": index}
    elif operation == "wait_clicks":
        if wait_indices:
            index = rng.choice(wait_indices)
            wait = source[index]
            wait["clicks"] = rng.choice(tuple(value for value in (2, 3, 4)
                                               if value != wait.get("clicks")))
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
                members[position] = rng.choice(alternatives)
                sequence["members"] = members
                position = {"segment": index, "member": position}
    elif operation == "castsequence_reset":
        index = rng.choice(castsequence_indices)
        sequence = source[index]
        reset = sequence.get("reset") or {}
        current = reset.get("timeout_seconds")
        timeout = rng.choice(tuple(value for value in (None, 1, 2, 3, 5)
                                   if value != current))
        flags = list(reset.get("flags", []))
        sequence["reset"] = ({"timeout_seconds": timeout, "flags": flags}
                             if timeout is not None or flags else None)
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
    summary["positions"] = sorted(
        summary["positions"].values(),
        key=lambda row: (row["candidate_identity"], row["click_position"],
                         row["action_position"], row["action"]),
    )
    exported = {"mode": value["mode"], "summary": summary}
    if value["mode"] == "full" and include_details:
        exported["details"] = value["details"]
    return exported


def _position_observations(candidate, candidate_identity, trace):
    from sequence import compiled_program

    blocks = compiled_program(candidate)
    rows = {}
    for click_position, block in enumerate(blocks):
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

    failures = {
        "not_ready", "outside_window", "dispatch_failed", "observed_failed",
        "native_interrupt", "commit_failed", "queue_rollback", "late_negative_feedback",
    }
    for event in trace:
        click_position = event.get("step")
        if type(click_position) is not int:
            continue
        positions = [key for key in rows if key[0] == click_position]
        if event.get("event") == "input":
            for key in positions:
                rows[key]["turns"] += 1
            continue
        action = event.get("signature")
        if not action or action == "-":
            action = event.get("action")
        matches = [key for key in positions if key[2] == action]
        if not matches:
            continue
        # 原生轨迹按动作名和点击位置归属；同名动作在不同点击位置不会合并。
        row = rows[matches[0]]
        kind = event.get("event")
        if kind in {"queue", "queue_commit", "queue_confirm", "queue_tentative"}:
            row["queued"] += 1
        if kind in {"busy", "queue_locked"}:
            row["queue_blocked"] += 1
        if kind in {"dispatch", "dispatch_deferred", "dispatch_failed", "native_execute", "native_interrupt"}:
            row["processing"] += 1
        if kind == "native_execute":
            row["successes"] += 1
        if kind in failures:
            row["failures"][kind] = row["failures"].get(kind, 0) + 1
    return list(rows.values())


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
        row = self.db.execute('SELECT value FROM state WHERE id=1').fetchone()
        self.state = json.loads(row[0]) if row else {}
        self.state_write_count = 0
        self.lua_compiler_starts = 0
        self.db.commit()

    def save(self):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))
            self.state_write_count += 1

    def publish(self):
        with self.lock:
            brief = {key: self.state.get(key) for key in
                     ('status', 'phase', 'elapsed_seconds', 'locked_candidate_key', 'completed_batches',
                      'batch_requests', 'batch_cache_hits', 'native_batch_starts',
                      'canonicalized_duplicates', 'error')}
            observation = self.state.get("search_observability")
            if observation and observation.get("mode") != "off":
                brief["search_observability"] = _export_search_observability(
                    observation, include_details=False)
            temporary = self.destination / 'progress.pending.json'
            temporary.write_text(_json(brief), encoding='utf-8')
            replace_file(temporary, self.destination / 'progress.json')

    def note_lua_start(self):
        with self.lock:
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
            if value['status']=='success' and not {'artifact','sha256','request','dps','samples'} <= value.keys():
                raise ValueError('缓存行缺少完整身份')
            return value
        except (ValueError,TypeError):
            self.put_batch(key,dict(status='invalid',error='缓存行损坏'))
            return None

    def put_batch(self, key, value, *, counter=None):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?)', (key, _json(value)))
            if value.get('status')=='success' and value['request']['purpose']!='final':
                self.db.execute('INSERT OR REPLACE INTO shared.reusable VALUES (?,?)',(key,_json(value)))
            self.state['completed_batches'] = self.db.execute(
                "SELECT count(*) FROM batches WHERE CASE WHEN json_valid(value) THEN json_extract(value,'$.status') END='success'").fetchone()[0]
            if counter is not None:
                self.state[counter] = self.state.get(counter, 0) + 1
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))
            self.state_write_count += 1

    @contextmanager
    def active(self, runtime):
        """进程崩溃最多按尚未消耗的单批额度扣费，恢复扣除只发生一次。"""
        stop = threading.Event()
        def beat():
            with self.lock:
                self.state['elapsed_seconds'] = runtime.elapsed_seconds
                if self.state.get('status') in ('running','stopping') and (runtime.cancel_event.is_set() or runtime.elapsed_seconds>=runtime.budget_seconds):
                    self.state['status']='stopping'
                self.save()
                self.publish()
        def heartbeat():
            while not stop.wait(0.5):
                beat()
        self.state['status'] = 'running'
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
        self.db.close()


def _score(rows):
    return sum(r['dps'] * r['samples'] for r in rows) / sum(r['samples'] for r in rows)


def _tuple(value):
    return tuple(_tuple(v) for v in value) if isinstance(value, list) else value


def optimize(*, profile, character, capabilities, reference, destination, runtime,
             config, condition_key, store, simulation_config=None):
    from engine import check_report, player_report, CandidateError
    from program import BEHAVIOR_IDENTITY_VERSION
    from sequence import evaluate, compiled_identity
    from simulation_config import config_for
    simulation_config = config_for(simulation_config)
    state = store.state
    verify_behavior_identity_state(state)
    observation_mode = config['search_observability']
    observability = None
    observation_events = {}
    if observation_mode != 'off':
        observability = state.setdefault(
            'search_observability', _new_search_observability(observation_mode))
        if observability.get('mode') != observation_mode:
            raise ValueError('任务恢复时搜索记录模式不能改变')
        observation_events = {row['event_id']: row for row in observability['details']}

    def event_for(work):
        return observation_events.get(work.get('observation_id')) if observability else None

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
            'phase_seconds': {},
        })

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

    def add_position_summary(work, rows):
        if not observability or work.get('observation_positions_recorded'):
            return
        work['observation_positions_recorded'] = True
        positions = observability['summary']['positions']
        for row in rows:
            key = _json([row['candidate_identity'], row['click_position'],
                         row['action_position'], row['action']])
            current = positions.get(key)
            if current is None:
                positions[key] = dict(row, failures=dict(row['failures']))
                continue
            for field in ('turns', 'queued', 'queue_blocked', 'processing', 'successes'):
                current[field] += row[field]
            for failure, count in row['failures'].items():
                current['failures'][failure] = current['failures'].get(failure, 0) + count
        row = event_for(work)
        if row is not None:
            row['position_summary'] = rows

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
            stage_seconds={},
        )

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
            if event['legal']:
                summary['legal_candidates'] += 1
                stats['legal_candidates'] += 1
            else:
                summary['invalid_candidates'] += 1
                stats['invalid_candidates'] += 1
                reason = event['illegal_reason'] or 'unknown'
                summary['invalid_reasons'][reason] = summary['invalid_reasons'].get(reason, 0) + 1
            if event['duplicate_reason']:
                summary['duplicates'] += 1
                stats['duplicates'] += 1
                reason = event['duplicate_reason']
                summary['duplicate_reasons'][reason] = summary['duplicate_reasons'].get(reason, 0) + 1
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
    state.setdefault('canonicalized_duplicates', 0)
    state.setdefault('batch_requests', 0)
    state.setdefault('batch_cache_hits', 0)
    state.setdefault('native_batch_starts', 0)
    state.setdefault('completed_batches', 0)
    state.setdefault('batch_estimate', 0.25)
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

    def candidate(program):
        nonlocal candidate_compilations
        source_key = program_key(program)
        if source_key in prepared:
            return prepared[source_key][1]
        from program import compile_program, canonicalize_search_program
        try:
            canonical = canonicalize_search_program(program, capabilities)
            key = canonical['identity']
            compiled = candidates.get(key)
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
                    candidate_compilations += 1
                    if canonical['form'] != compiled_identity(compiled):
                        raise CandidateError('候选标准形式与编译计划不一致')
                candidates[key] = compiled
            if config['diagnostics'] == 'full':
                diagnostic_events.append(dict(event='candidate_prepared', behavior_identity=key,
                                              candidate_compilations_so_far=candidate_compilations))
        except CandidateError:
            raise
        except ValueError as error:
            raise CandidateError(str(error)) from error
        prepared[source_key] = (key, candidates[key])
        return candidates[key]

    def candidate_key(program):
        candidate(program)
        return prepared[program_key(program)][0]

    def batch(program, purpose, index, iterations, scenario='nominal', trace=False):
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
        with store.lock:
            state['batch_requests'] += 1
        cached = store.batch(key)
        if cached and cached['status'] == 'success':
            try:
                origin=Path(cached.get('origin',destination)).resolve()
                folder=(origin/cached['artifact']).resolve()
                if not folder.is_relative_to(origin):
                    raise ValueError('缓存路径越界')
                raw = (folder / 'native.json').read_bytes()
                if hashlib.sha256(raw).hexdigest() != cached['sha256'] or cached['request'] != request:
                    raise ValueError('缓存报告散列或身份不符')
                summary = check_report(json.loads(raw), character, iterations,
                                       simulation_config=simulation_config)
                if summary['dps'] != cached['dps'] or summary['samples'] != cached['samples']:
                    raise ValueError('缓存摘要不符')
                store.put_batch(key, cached, counter='batch_cache_hits')
                return dict(cached, cached=True)
            except (ValueError, OSError, KeyError, TypeError):
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
        try:
            kwargs = {'reset_events': list(config['reset_events'])} if config['reset_events'] else {}
            def native_started():
                with store.lock:
                    state['native_batch_starts'] += 1
            result = evaluate(profile, compiled, folder, character=character, iterations=iterations, seed=seed,
                              input_times=times, trace=trace, runtime=runtime,
                              simulation_config=simulation_config, on_native_start=native_started, **kwargs)
            raw = (folder / 'native.json').read_bytes()
            row = dict(status='success', request=request, dps=result['summary']['dps'],
                       samples=result['summary']['samples'], requested_iterations=iterations,
                       artifact=folder.relative_to(destination).as_posix(), origin=str(destination), sha256=hashlib.sha256(raw).hexdigest(),
                       feedback=feedback_from_trace(result['trace'],[a['simc_action'] for a in capabilities['actions']],
                           player_report(result['report'], character)['collected_data'].get('resource_overflowed',{}).get(reference['identity']['resource'],{}).get('mean',0)>0,
                           {v['simc_action']: a['simc_action'] for a in capabilities['actions'] for v in a.get('variants',[a])}) if trace else None)
            if trace and observability:
                row['position_summary'] = _position_observations(
                    compiled, behavior_id, result['trace'])
            with store.lock:
                state['inflight'].pop(key, None)
                state['batch_estimate'] = max(0.1, 0.8 * state['batch_estimate'] + 0.2 * (time.monotonic()-started))
                store.put_batch(key, row)
            return row
        except (BudgetExceeded, TaskCancelled):
            raise
        except CandidateError as error:
            store.put_batch(key, dict(status='failed', request=request, error=str(error)))
            raise
        finally:
            with store.lock:
                state.setdefault('inflight', {}).pop(key, None)
                store.save()

    def pair(first, second, purpose, count, scenario='nominal'):
        rows = [[], []]
        trace_candidate = purpose == 'validation' and observability is not None
        # 外层只允许两个引擎；结果始终按预分配的对象顺序消费。
        for index in range(count):
            candidate(first)
            candidate(second)
            if candidate_key(first) == candidate_key(second):
                row = batch(first, purpose, index,
                            config['final_iterations'] if purpose == 'final' else config['iterations'],
                            scenario, trace=trace_candidate)
                rows[0].append(row)
                rows[1].append(row)
                continue
            with ThreadPoolExecutor(max_workers=config['max_processes']) as pool:
                futures = [pool.submit(batch, program, purpose, index,
                                       config['final_iterations'] if purpose == 'final' else config['iterations'],
                                       scenario, trace=trace_candidate if side == 0 else False)
                           for side, program in enumerate((first, second))]
                for side, future in enumerate(futures):
                    rows[side].append(future.result())
        return rows

    def record(program):
        compiled = candidate(program)  # 编译合法性必须先于任何原生计算。
        key = candidate_key(program)
        rows, previous = [], 0
        incumbent = next((r for r in state['archive'] if r['key'] == state.get('best')), None)
        for index, target in enumerate(config['batch_targets']):
            row = batch(program, 'search', index, target-previous,
                        trace=(not state['archive'] and index == 0))
            row = dict(row, target=target)
            rows.append(row)
            previous = target
            if incumbent and len(rows) >= 2:
                reference_rows = incumbent['batches'][:len(rows)]
                # 独立批次比较；明确落后才停止，不按一次噪声排名淘汰。
                ci = paired_ci([r['dps'] for r in rows], [r['dps'] for r in reference_rows])
                if ci and ci[1] < 0:
                    break
        return dict(key=key, program=program, batches=rows, score=_score(rows),
                    candidate=compiled,candidate_sha256=digest(compiled))

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
                lane.update(feedback=diagnostic['feedback'],feedback_source=base['key'])
                generated = []
                generation_observations = []
                existing = set(state['seen'])
                for attempt in range(160):
                    if len(generated) >= min(config['round_candidate_limit'], config['candidate_limit']-len(state['evaluated_keys'])):
                        break
                    kwargs = {'reset_flags': observable_flags} if observable_flags else {}
                    mutation_observation = {} if observability else None
                    mutation_started = time.perf_counter() if observability else None
                    mutation_kwargs = dict(feedback=lane['feedback'], **kwargs)
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
                        state['canonicalized_duplicates'] += 1
                        continue
                    existing.add(key)
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
                    state['canonicalized_duplicates'] += 1
                    mark_duplicate(work, 'already_scored')
                    state['pending'].pop(0)
                    store.save()
                    continue
                if observability:
                    mark_work(work, 'score_started', 'score_started')
                    store.save()
                    scoring_started = time.perf_counter()
                current = record(work['program'])
                if observability:
                    row = event_for(work)
                    if row is not None:
                        row['candidate_score'] = current['score']
                        parent_score = work.get('observation_parent_score')
                        if parent_score is not None:
                            row['parent_score'] = parent_score
                            row['score_change'] = current['score'] - parent_score
                    add_stage_time(work, 'scoring', time.perf_counter() - scoring_started)
                    mark_work(work, 'score_completed', 'score_completed')
            except CandidateError as error:
                if observability:
                    mark_candidate(work, error=error)
                    row = event_for(work)
                    if row is not None and work.get('observation_score_started'):
                        row['score_error'] = str(error)
                    if scoring_started is not None and not work.get('observation_timed_scoring'):
                        add_stage_time(work, 'scoring', time.perf_counter() - scoring_started)
                state.setdefault('errors', []).append(
                    dict(program=program_key(work['program']), error=str(error)))
                current = None
            if current:
                if not state['archive']:
                    state['best']=key
                else:
                    opponent_key=state['best'] if work['start'] else state['chains'][work['lane']]['best']
                    opponent=next(r for r in state['archive'] if r['key']==opponent_key)
                    if current['score']>opponent['score']:
                        if observability:
                            if work['start']:
                                mark_promotion(work, 'global', checked=True)
                            else:
                                mark_promotion(work, 'route', checked=True)
                                if opponent_key == state['best']:
                                    mark_promotion(work, 'global', checked=True)
                            store.save()
                            promotion_started = time.perf_counter()
                        try:
                            left,right=pair(current['program'],opponent['program'],'validation',config['validation_batches'])
                        finally:
                            if observability:
                                add_stage_time(work, 'promotion_check',
                                              time.perf_counter() - promotion_started)
                        if observability:
                            add_position_summary(work, [position for batch_row in left
                                                        for position in batch_row.get('position_summary', [])])
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
                            if not work['start']:
                                state['chains'][work['lane']]['best']=key
                            global_best=next(r for r in state['archive'] if r['key']==state['best'])
                            if opponent_key==state['best']:
                                state['best']=key
                                state['round_improved']=True
                            elif current['score']>global_best['score']:
                                if observability:
                                    mark_promotion(work, 'global', checked=True)
                                    store.save()
                                    global_started = time.perf_counter()
                                try:
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
                                if global_promoted:
                                    state['best']=key
                                    state['round_improved']=True
                state['archive'].append(current)
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

    if state['phase'] == 'search':
        try:
            search()
        except BudgetExceeded:
            state['stop_reason'] = 'search_deadline'
        finally:
            runtime.phase_limit = runtime.budget_seconds
        if not state['archive']:
            raise BudgetExceeded('搜索窗口内未完成有效初始序列')
        state['locked_candidate_key'] = state['best']
        state['phase'] = 'final'
        store.save()
        store.publish()
    seed = state['archive'][0]
    best = next(r for r in state['archive'] if r['key'] == state['locked_candidate_key'])
    final = dict(dataset='final', scenarios={})
    interrupted = None
    for scenario in config['scenarios']:
        try:
            left, right = pair(best['program'], seed['program'], 'final', config['final_batches'], scenario)
            comparison = summarize_pairs(left, right)
            final['scenarios'][scenario] = dict(candidate=left, seed=right, comparison=comparison,
                                                 complete=True, effective_samples=[sum(r['samples'] for r in side) for side in (left,right)])
        except (BudgetExceeded, TaskCancelled) as error:
            interrupted = error
            break
    complete = (set(final['scenarios']) == set(DEFAULT_SCENARIOS)
                and config['final_batches'] >= DEFAULT_CONFIG['final_batches']
                and config['final_iterations'] == DEFAULT_CONFIG['final_iterations'])
    improved = complete and all(v['comparison']['status'] == 'improvement_confirmed' for v in final['scenarios'].values())
    chosen = best if improved or not complete else seed
    result = dict(status='completed' if complete else 'validation_incomplete', phase='done',
                  search=dict(dataset='search', starts=starts, records=state['archive'], chains=state['chains'],rounds=state['rounds'],
                              candidate_count=len(state['evaluated_keys']),unique_candidates=len(state['seen']),
                              canonicalized_duplicates=state['canonicalized_duplicates'], errors=state.get('errors', []),
                              batch_requests=state['batch_requests'], batch_cache_hits=state['batch_cache_hits'],
                              native_batch_starts=state['native_batch_starts'],
                              partial_round=bool(state['pending']) or not state.get('full_round',True),stop_reason=state.get('stop_reason')),
                  validation=dict(dataset='validation',records=[r[k] for r in state['archive'] for k in ('validation','global_validation') if k in r]), final=final, locked_candidate_key=state['locked_candidate_key'],
                  candidate=candidate(chosen['program']), independent_validation_complete=complete,
                  improvement='improvement_confirmed' if improved else 'not_proven_better',
                  selected_candidate_key=chosen['key'], native_reference=reference,
                  elapsed_seconds=runtime.elapsed_seconds, completed_batches=state['completed_batches'])
    if observability:
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
        result['status'] = 'cancelled' if isinstance(interrupted, TaskCancelled) else 'validation_incomplete'
        result['phase'] = 'final'
    store.save()
    return result
