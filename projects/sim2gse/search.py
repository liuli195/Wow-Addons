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
    "input_interval_ms": 300,
}


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
    return [list(block) for block in program]


def mutate(program, capabilities, rng, *, feedback=None):
    """执行交换、替换、插删、片段移动、块内调整或重启中的一个操作。"""
    source = _copy_program(program)
    available = [a["simc_action"] for a in capabilities["actions"]]
    if not source or not available:
        return source
    operation = rng.choice(("swap", "replace", "insert", "delete", "move", "block"))
    suggested = None
    if feedback and rng.random() < 0.5:
        if feedback.get('untried'):
            operation,suggested='insert',rng.choice(feedback['untried'])
        elif feedback.get('resource_overflowed') and feedback.get('spenders'):
            operation,suggested='insert',rng.choice(feedback['spenders'])
        else:
            wasted=[name for name,n in feedback.get('attempts',{}).items()
                    if n>2 and feedback.get('successes',{}).get(name,0)/n < 0.05]
            positions=[i for i,b in enumerate(source) if any(name in wasted for name in b)]
            if positions and len(source)>1:
                del source[rng.choice(positions)]
                return source
    if operation == "swap" and len(source) > 1:
        first, second = rng.sample(range(len(source)), 2)
        source[first], source[second] = source[second], source[first]
    elif operation == "replace":
        block = rng.randrange(len(source))
        source[block][rng.randrange(len(source[block]))] = rng.choice(available)
    elif operation == "insert" and len(source) < 128:
        block = rng.randrange(len(source))
        source.insert(block, [suggested or rng.choice(available)])
    elif operation == "delete" and len(source) > 1:
        del source[rng.randrange(len(source))]
    elif operation == "move" and len(source) > 2:
        start = rng.randrange(len(source) - 1)
        end = rng.randrange(start + 1, min(len(source), start + 4) + 1)
        fragment = source[start:end]
        del source[start:end]
        target = rng.randrange(len(source) + 1)
        source[target:target] = fragment
    elif operation == "block":
        block = source[rng.randrange(len(source))]
        if len(block)>1 and rng.random()<0.5:
            index=rng.randrange(len(block))
            command=block.pop(index)
            if rng.random()<0.5:
                block.insert(rng.randrange(len(block)+1),command)
        elif len(block) < 16:
            block.insert(rng.randrange(len(block) + 1), rng.choice(available))
    return source


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
        self.db.commit()

    def save(self):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))

    def publish(self):
        with self.lock:
            brief = {key: self.state.get(key) for key in
                     ('status', 'phase', 'elapsed_seconds', 'locked_candidate_key', 'completed_batches', 'error')}
            temporary = self.destination / 'progress.pending.json'
            temporary.write_text(_json(brief), encoding='utf-8')
            replace_file(temporary, self.destination / 'progress.json')

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

    def put_batch(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?)', (key, _json(value)))
            if value.get('status')=='success' and value['request']['purpose']!='final':
                self.db.execute('INSERT OR REPLACE INTO shared.reusable VALUES (?,?)',(key,_json(value)))
            self.state['completed_batches'] = self.db.execute(
                "SELECT count(*) FROM batches WHERE CASE WHEN json_valid(value) THEN json_extract(value,'$.status') END='success'").fetchone()[0]
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (_json(self.state),))

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
        self.db.close()


def _score(rows):
    return sum(r['dps'] * r['samples'] for r in rows) / sum(r['samples'] for r in rows)


def _tuple(value):
    return tuple(_tuple(v) for v in value) if isinstance(value, list) else value


def optimize(*, profile, character, capabilities, reference, destination, runtime,
             config, condition_key, store):
    from codec import export
    from engine import check_report, player_report, CandidateError
    from sequence import select, evaluate, compiled_program
    state = store.state
    state.setdefault('run_nonce', uuid.uuid4().hex)
    state.setdefault('phase', 'search')
    state.setdefault('archive', [])
    state.setdefault('pending', [])
    state.setdefault('rounds', 0)
    state.setdefault('no_improvement', 0)
    state.setdefault('seen', [])
    state.setdefault('chains', [])
    state.setdefault('evaluated_keys', [])
    state.setdefault('completed_batches', 0)
    state.setdefault('batch_estimate', 0.25)
    starts = initial_programs(capabilities, reference, config['random_seed'])
    state.setdefault('starts', starts)
    rng = random.Random(config['random_seed'])
    if state.get('rng'):
        rng.setstate(_tuple(state['rng']))
    candidates = {}

    def candidate(program):
        key = program_key(program)
        if key not in candidates:
            saved=next((r for r in state['archive'] if r['key']==key and r.get('candidate')),None)
            if saved and digest(saved['candidate'])==saved['candidate_sha256']:
                candidates[key]=saved['candidate']
            else:
                candidates[key] = export(select(capabilities, program), destination / 'exports' / key, identity=reference['identity'], runtime=runtime)
        return candidates[key]

    def batch(program, purpose, index, iterations, scenario='nominal', trace=False):
        seed_offset = {'search': 0, 'validation': 100000, 'final': 200000}[purpose]
        # 每次运行独立的最终样本，恢复复用同一编号，不借用旧任务见过的最终样本。
        nonce = int(state['run_nonce'][:8], 16) % 100000000 if purpose == 'final' else 0
        seed = config['random_seed'] + seed_offset + index + DEFAULT_SCENARIOS.index(scenario) * 1000 + nonce
        input_seed = seed + 500000
        times = input_times(scenario, input_seed, config["input_interval_ms"])
        compiled = candidate(program)
        request = dict(condition=condition_key, program=compiled_program(compiled), purpose=purpose,
                       seed=seed, input_seed=input_seed, iterations=iterations, times=times,
                       stats=STATS_VERSION, trace=trace)
        key = digest(request)
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
                summary = check_report(json.loads(raw), character, iterations)
                if summary['dps'] != cached['dps'] or summary['samples'] != cached['samples']:
                    raise ValueError('缓存摘要不符')
                store.put_batch(key,cached)
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
            if purpose=='search' and index!=99 and program_key(program) not in state['evaluated_keys']:
                state['evaluated_keys'].append(program_key(program))
            store.save()
        folder = destination / 'batches' / key
        started = time.monotonic()
        try:
            result = evaluate(profile, compiled, folder, character=character, iterations=iterations, seed=seed,
                              input_times=times, trace=trace, runtime=runtime)
            raw = (folder / 'native.json').read_bytes()
            row = dict(status='success', request=request, dps=result['summary']['dps'],
                       samples=result['summary']['samples'], requested_iterations=iterations,
                       artifact=folder.relative_to(destination).as_posix(), origin=str(destination), sha256=hashlib.sha256(raw).hexdigest(),
                       feedback=feedback_from_trace(result['trace'],[a['simc_action'] for a in capabilities['actions']],
                           player_report(result['report'], character)['collected_data'].get('resource_overflowed',{}).get(reference['identity']['resource'],{}).get('mean',0)>0,
                           {v['simc_action']: a['simc_action'] for a in capabilities['actions'] for v in a.get('variants',[a])}) if trace else None)
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
        # 外层只允许两个引擎；结果始终按预分配的对象顺序消费。
        for index in range(count):
            candidate(first)
            candidate(second)
            if program_key(first) == program_key(second):
                row = batch(first,purpose,index,config['final_iterations'] if purpose=='final' else config['iterations'],scenario)
                rows[0].append(row)
                rows[1].append(row)
                continue
            with ThreadPoolExecutor(max_workers=config['max_processes']) as pool:
                futures = [pool.submit(batch, program, purpose, index,
                                       config['final_iterations'] if purpose == 'final' else config['iterations'], scenario)
                           for program in (first, second)]
                for side, future in enumerate(futures):
                    rows[side].append(future.result())
        return rows

    def record(program):
        candidate(program)  # 编译合法性必须先于任何原生计算。
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
        return dict(key=program_key(program), program=program, batches=rows, score=_score(rows),
                    candidate=candidate(program),candidate_sha256=digest(candidate(program)))

    def search():
        runtime.phase_limit = min(config['search_budget_seconds'], config['total_budget_seconds'])
        if not state['archive'] and not state['pending']:
            state['pending'] = [dict(program=p, start=True) for p in starts[:config['candidate_limit']]]
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
                existing = set(state['seen'])
                for attempt in range(160):
                    if len(generated) >= min(config['round_candidate_limit'], config['candidate_limit']-len(state['evaluated_keys'])):
                        break
                    program = mutate(base['program'], capabilities, rng,
                                     feedback=lane['feedback'])
                    if rng.randrange(16)==0:
                        program = [[a['simc_action']] for a in capabilities['actions']]
                        rng.shuffle(program)
                    key = program_key(program)
                    if key in existing:
                        continue
                    try:
                        candidate(program)
                    except ValueError:
                        continue
                    existing.add(key)
                    generated.append(dict(program=program,start=False,lane=lane_index))
                if not generated:
                    state['stop_reason'] = 'space_stalled'
                    break
                state['pending'] = generated
                state['round_improved'] = False
                state['full_round'] = len(generated)==config['round_candidate_limit']
                state['rng'] = rng.getstate()
                store.save()
            work = state['pending'][0]
            key = program_key(work['program'])
            try:
                current = record(work['program'])
            except CandidateError as error:
                state.setdefault('errors', []).append(dict(program=key, error=str(error)))
                current = None
            if current:
                if not state['archive']:
                    state['best']=key
                else:
                    opponent_key=state['best'] if work['start'] else state['chains'][work['lane']]['best']
                    opponent=next(r for r in state['archive'] if r['key']==opponent_key)
                    if current['score']>opponent['score']:
                        left,right=pair(current['program'],opponent['program'],'validation',config['validation_batches'])
                        ci=paired_ci([r['dps'] for r in left],[r['dps'] for r in right])
                        current['validation']=dict(comparison=summarize_pairs(left,right),candidate=left,control=right)
                        if ci and ci[0]>0:
                            if not work['start']:
                                state['chains'][work['lane']]['best']=key
                            global_best=next(r for r in state['archive'] if r['key']==state['best'])
                            if opponent_key==state['best']:
                                state['best']=key
                                state['round_improved']=True
                            elif current['score']>global_best['score']:
                                left,right=pair(current['program'],global_best['program'],'validation',config['validation_batches'])
                                ci=paired_ci([r['dps'] for r in left],[r['dps'] for r in right])
                                current['global_validation']=dict(comparison=summarize_pairs(left,right),candidate=left,control=right)
                                if ci and ci[0]>0:
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
                              candidate_count=len(state['evaluated_keys']),unique_candidates=len(state['seen']),partial_round=bool(state['pending']) or not state.get('full_round',True),stop_reason=state.get('stop_reason')),
                  validation=dict(dataset='validation',records=[r[k] for r in state['archive'] for k in ('validation','global_validation') if k in r]), final=final, locked_candidate_key=state['locked_candidate_key'],
                  candidate=candidate(chosen['program']), independent_validation_complete=complete,
                  improvement='improvement_confirmed' if improved else 'not_proven_better',
                  selected_candidate_key=chosen['key'], native_reference=reference,
                  elapsed_seconds=runtime.elapsed_seconds, completed_batches=state['completed_batches'])
    result['candidate']['simulation'] = 'passed_native_model'
    if interrupted:
        result['status'] = 'cancelled' if isinstance(interrupted, TaskCancelled) else 'validation_incomplete'
        result['phase'] = 'final'
    store.save()
    return result
