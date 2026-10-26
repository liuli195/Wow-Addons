"""按需收集已有成绩；结束后用标准库导出离线曲线。"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
import sys
from time import monotonic
import uuid

MAX_EVENTS = 10000
SCHEMA = 'sim2gse-search-timeline-v1'


class Timeline:
    def __init__(self, *, origin=None, context=None, resumed=False):
        self.origin = monotonic() if origin is None else origin
        self.context = context or {}
        self.resumed = resumed
        self.events = [dict(seconds=0., kind='preparation')]
        self.current = {}
        self.truncated_at = None
        self.search_start_seconds = None
        self.search_stop_seconds = None
        self.result_saved_seconds = None
        self.stop_reason = None
        self.status = 'failed'
        self.mark('collector_started')

    def configure(self, *, profile_sha, engines, simulation_config, config, burst=None):
        """只复用已冻结的物理条件；算法与种子是对照标签，不是分图键。"""
        self.context['algorithm'] = {key: config[key] for key in (
            'random_seed',)}
        if not profile_sha or not engines:
            return  # 准备失败/旧文件口径未知，不把多个未知段自动合图。
        self.context['comparison'] = dict(profile_sha256=profile_sha,
            engines={mode: {key: manifest[key] for key in ('identity_sha256', 'binary_sha256')
                            if key in manifest} or manifest for mode, manifest in engines.items()},
            simulation_config=simulation_config, input_interval_ms=config['input_interval_ms'],
            reset_events=config['reset_events'],
            burst={key: burst.get(key) for key in ('definition_id', 'plan')} if burst else None)

    def seconds(self):
        return max(0., monotonic() - self.origin)

    def mark(self, kind, **values):
        if self.truncated_at is not None:
            return
        seconds = self.seconds()
        if len(self.events) >= MAX_EVENTS:
            self.truncated_at = seconds
            return
        self.events.append(dict(seconds=seconds, kind=kind, **values))

    def start(self):
        self.search_start_seconds = self.seconds()
        self.mark('search_started')

    def score(self, row, series, reason):
        if self.truncated_at is not None:
            return
        self.current[series] = row['key']
        self.mark('score', series=series, reason=reason, candidate_key=row['key'],
                  dps=row['score'], samples=sum(batch['samples'] for batch in row['batches']))

    def revise(self, row):
        for series, key in self.current.items():
            if key == row['key']:
                self.score(row, series, 'revision')

    def stop(self, reason):
        if self.search_stop_seconds is None:
            self.search_stop_seconds = self.seconds()
            self.stop_reason = reason
            self.mark('search_stopped', reason=reason)

    def saved(self, status):
        self.status = status
        if self.result_saved_seconds is not None:
            return
        self.result_saved_seconds = self.seconds()
        self.mark('result_saved', status=status)

    def finish(self, destination, *, status=None):
        """诊断失败不能覆盖业务结果或原异常；不会自动重跑。"""
        try:
            if getattr(self, 'finished', False):
                return None
            self.finished = True
            if status is not None:
                self.status = status
            self.stop(self.status)
            if self.status != 'completed':
                self.stop_reason = self.status  # Retest/publication can stop after exploration ended.
            payload = dict(schema=SCHEMA, context=self.context, resumed=self.resumed,
                time_origin='本次公开调用；包含准备及排队等待；不含上次运行',
                status=self.status, stop_reason=self.stop_reason, events=self.events,
                search_start_seconds=self.search_start_seconds,
                search_stop_seconds=self.search_stop_seconds,
                result_saved_seconds=self.result_saved_seconds, call_seconds=self.seconds(),
                truncated_at=self.truncated_at)
            payload['samples'] = resample(payload)
            destination = Path(destination)
            destination.mkdir(parents=True, exist_ok=True)
            path = destination / ('search-timeline-' + uuid.uuid4().hex[:12] + '.json')
            path.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            render([payload], path.with_suffix('.html'))
            return path
        except Exception as error:
            print('轻量曲线导出失败（业务结果不变）: ' + str(error), file=sys.stderr)
            return None


def resample(payload, *, horizon=None):
    """10秒网格取截止当时最后值；绝不插值或回填未来成绩。"""
    end = payload['call_seconds'] if horizon is None else horizon
    scores = [event for event in payload['events'] if event['kind'] == 'score']
    series = list(dict.fromkeys(event['series'] for event in scores)) or ['global']
    values, result, index = {}, [], 0
    cutoff = payload.get('truncated_at')
    for seconds in range(0, math.ceil(end / 10) * 10 + 1, 10):
        while index < len(scores) and scores[index]['seconds'] <= seconds:
            values[scores[index]['series']] = scores[index]
            index += 1
        stop = payload.get('search_stop_seconds')
        stopped = stop is not None and seconds >= stop
        failed_at = min(payload['call_seconds'], stop) if stop is not None else payload['call_seconds']
        incomplete = ((cutoff is not None and seconds >= cutoff) or
                      (payload['status'] not in ('completed', 'cancelled') and seconds > failed_at))
        for name in series:
            row = None if incomplete else values.get(name)
            result.append(dict(seconds=seconds, series=name,
                dps=row['dps'] if row else None, candidate_key=row['candidate_key'] if row else None,
                status='incomplete' if incomplete else 'stopped' if stopped else 'searching'))
    return result


def _groups(payloads):
    groups = {}
    for number, payload in enumerate(payloads, 1):
        comparison = payload['context'].get('comparison') or dict(unknown_segment=number)
        key = json.dumps(comparison, sort_keys=True, ensure_ascii=False)
        groups.setdefault(key, []).append((number, payload))
    return groups


def render(payloads, output):
    """简单静态HTML/SVG；不同物理条件绝不混作同一口径。"""
    groups = _groups(payloads)
    parts = ['<!doctype html><meta charset="utf-8"><title>搜索成绩曲线</title>',
             '<h1>已知搜索成绩 · 真实墙钟</h1><p>10秒末值，不插值、不回填；粗线为全局，淡线为路径；停止后虚线延续。恢复为新段。</p>']
    palette = ('#1261a0', '#c33b31', '#278044', '#7946a0', '#a66b00')
    for label, group in groups.items():
        condition = json.loads(label)
        label = (str(condition.get('simulation_config')) + ' / 角色 ' + condition['profile_sha256'][:12]
                 if condition.get('profile_sha256') else '未知物理条件，仅展示本段')
        horizon = max(payload['call_seconds'] for _, payload in group)
        datasets = [(number, payload, resample(payload, horizon=horizon)) for number, payload in group]
        finite = [row['dps'] for _, _, samples in datasets for row in samples if row['dps'] is not None]
        maximum = max(finite, default=1) or 1
        width = max(10, math.ceil(horizon / 10) * 10)
        parts.append('<h2>' + html.escape(label) + '</h2><svg viewBox="0 0 900 330" role="img">')
        parts.append('<path d="M60 10V285H880" fill="none" stroke="#555"/>')
        for number, payload, samples in datasets:
            names = list(dict.fromkeys(row['series'] for row in samples))
            for name in names:
                points = [row for row in samples if row['series'] == name and row['dps'] is not None]
                color = palette[(number - 1) % len(palette)]
                for row in points:
                    x, y = 60 + row['seconds'] / width * 810, 280 - row['dps'] / maximum * 260
                    parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2" fill="{color}"><title>{html.escape(str(number)+" / "+name+": "+str(row["dps"]))}</title></circle>')
                for left, right in zip(points, points[1:]):
                    if right['seconds'] - left['seconds'] != 10:
                        continue
                    x1, x2 = (60 + row['seconds'] / width * 810 for row in (left, right))
                    y1, y2 = (280 - row['dps'] / maximum * 260 for row in (left, right))
                    dashed = ' stroke-dasharray="5 4"' if right['status'] == 'stopped' else ''
                    style = ' stroke-width="3"' if name == 'global' else ' opacity="0.45"'
                    parts.append(f'<path d="M{x1:.2f} {y1:.2f}H{x2:.2f}V{y2:.2f}" fill="none" stroke="{color}"{dashed}{style}><title>{html.escape(str(number)+" / "+name)}</title></path>')
            parts.append(f'<text x="65" y="{22 + (number - 1) * 17}">{html.escape(str(number)+": "+payload["status"]+" / "+str(payload.get("stop_reason")))}</text>')
        parts.append(f'<text x="60" y="315">0秒</text><text x="790" y="315">{width}秒</text><text x="5" y="15">{maximum:.0f}</text></svg>')
        for number, payload in group:
            parts.append('<p>' + html.escape(f'{number}: {payload.get("source", payload["context"].get("run_id", payload["context"].get("training_candidate_id", "本次运行")))}; {payload["time_origin"]}; search_start={payload["search_start_seconds"]}; stop={payload["search_stop_seconds"]}; saved={payload["result_saved_seconds"]}; truncated={payload["truncated_at"]}; algorithm={payload['context'].get('algorithm')}') + '</p>')
    Path(output).write_text('\n'.join(parts), encoding='utf-8')


def compare(sources, output):
    if Path(output).suffix.lower() not in ('.html', '.htm'):
        raise ValueError('曲线输出须为.html或.htm文件')
    paths = []
    for source in sources:
        path = Path(source)
        paths.extend(sorted(path.rglob('search-timeline-*.json')) if path.is_dir() else [path])
    payloads = []
    for path in dict.fromkeys(paths):
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('schema') != SCHEMA:
            raise ValueError('不是轻量搜索曲线: ' + str(path))
        payloads.append(dict(payload, source=str(path)))
    if not payloads:
        raise ValueError('没有已有轻量搜索曲线文件；不会自动启动任务')
    result = dict(groups=[])
    for key, numbered in _groups(payloads).items():
        runs = [payload for _, payload in numbered]
        horizon = max(run['call_seconds'] for run in runs)
        result['groups'].append(dict(comparison=json.loads(key),
            simulation_config=runs[0]['context'].get('simulation_config'),
            runs=[dict(run, samples=resample(run, horizon=horizon)) for run in runs]))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    render(payloads, output)
    return dict(status='exported', runs=len(payloads), groups=len(result['groups']), output=str(output))


# 此固定上游 timeline.hpp 的默认桶宽为1秒，玩家timeline已聚合宠物。
# 新上游须重新核验；仅报告版本字符串不能证明外部JSON的桶宽。
NATIVE_TIMELINE_TREE = '1de6c4fd7c53bb05ababe6634396c88aa19e5183'


def damage_report(source):
    from result_store import one, report_for_task
    run = None
    path = Path(source)
    if source.startswith('batch:'):
        batch = one('batches', 'batch_key', source[6:])
        if not batch:
            return dict(source=source, status='missing', reason='已有批次不存在；不会补模拟')
        report = batch['report']
        mode = 'baseline' if batch.get('purpose') == 'reference' else 'controlled'
        run = one('runs', 'run_id', batch.get('run_id')) if batch.get('run_id') else None
    elif path.is_dir():
        pointer = json.loads((path / 'result.json').read_text(encoding='utf-8'))
        run = one('runs', 'run_id', pointer['run_id'])
        report = report_for_task(path)
        mode = 'controlled' if run.get('controlled_data_key') else 'baseline'
    else:
        report = json.loads(path.read_text(encoding='utf-8'))
        mode = None
    players = report.get('sim', {}).get('players', [])
    if len(players) != 1:
        return dict(source=source, status='unsupported', reason='多玩家聚合口径不明确，不生成伤害图')
    values = players[0].get('collected_data', {}).get('timeline_dmg', {}).get('data')
    if not isinstance(values, list) or not values:
        return dict(source=source, status='missing', reason='原报告缺少伤害时间桶；不会补模拟或追踪')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return dict(source=source, status='unsupported', reason='原报告时间桶无效')
    engines = run.get('engines') if run else {}
    if isinstance(engines, str):
        engines = json.loads(engines)
    lock = json.loads((Path(__file__).parent / 'compatibility/lock.json').read_text(encoding='utf-8'))
    from native_build import build_identity, identity_digest
    verified = False
    manifest = (engines or {}).get(mode)
    if isinstance(manifest, dict) and mode in ('baseline', 'controlled'):
        expected = build_identity(lock, mode, manifest.get('compiler_sha256'))
        verified = (manifest.get('upstream_tree') == NATIVE_TIMELINE_TREE
                    and all(manifest.get(key) == value for key, value in expected.items())
                    and manifest.get('identity_sha256') == identity_digest(expected))
    if not verified or report.get('version') != '1210-01' or report.get('report_version') != '2.0.0':
        return dict(source=source, status='unsupported', reason='缺少已核验固定原生来源或版本，无法证明1秒桶宽')
    return dict(source=source, status='available', metric='原生报告1秒分桶伤害统计', bucket_seconds=1,
        values=values, player=players[0].get('name'), engine=mode,
        note='原生玩家时间桶已包含宠物，不叠加stats_pets；不归一化，不等同最终评分DPS')


def compare_damage(sources, output):
    if Path(output).suffix.lower() not in ('.html', '.htm'):
        raise ValueError('曲线输出须为.html或.htm文件')
    reports = [damage_report(source) for source in sources]
    parts = ['<!doctype html><meta charset="utf-8"><title>原生伤害时间桶</title>',
             '<h1>原生报告1秒分桶伤害统计</h1><p>每图一个现有报告；不归一成评分DPS，不重复叠加宠物。</p>']
    for report in reports:
        parts.append('<h2>' + html.escape(report['source']) + '</h2>')
        if report['status'] != 'available':
            parts.append('<p>' + html.escape(report['reason']) + '</p>')
            continue
        values = report['values']
        maximum = max(values) or 1
        points = ' '.join(f'{60 + index / len(values) * 810:.2f},{280 - value / maximum * 260:.2f}'
                          for index, value in enumerate(values))
        parts.append(f'<svg viewBox="0 0 900 330" role="img"><path d="M60 10V285H880" fill="none" stroke="#555"/><polyline points="{points}" fill="none" stroke="#1261a0"/><text x="60" y="315">0秒</text><text x="790" y="315">{len(values)}秒</text><text x="5" y="15">{maximum:.0f}</text></svg>')
        parts.append('<p>' + html.escape(report['note']) + '</p>')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(dict(reports=reports), ensure_ascii=False), encoding='utf-8')
    output.write_text('\n'.join(parts), encoding='utf-8')
    return dict(status='exported', reports=len(reports), available=sum(row['status'] == 'available' for row in reports),
                output=str(output))
