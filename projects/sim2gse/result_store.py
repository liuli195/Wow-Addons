"""Sim2GSE adapter for the installed data-store skill."""

from __future__ import annotations

import runpy
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import threading
import time


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
CANDIDATE_SCHEMA = dict(
    run_id="VARCHAR", candidate_key="VARCHAR", candidate_data_key="VARCHAR",
    source="VARCHAR", search_order="UBIGINT", program="JSON", export_text="VARCHAR", simulation="VARCHAR",
    selected_sequence="VARCHAR", selected_version="UBIGINT", import_sha256="VARCHAR",
    game_validation="VARCHAR",
)
RUN_SCHEMA = dict(
    burst="JSON", rule_initialization="JSON",
    run_id="VARCHAR", status="VARCHAR", phase="VARCHAR", profile="JSON",
    identity="JSON", input_original="VARCHAR", input_effective="VARCHAR",
    config="JSON", syntax="JSON", simulation_config="JSON", engines="JSON", condition_key="VARCHAR",
    elapsed_seconds="DOUBLE", candidate_key="VARCHAR", candidate_data_key="VARCHAR",
    reference_data_key="VARCHAR", controlled_data_key="VARCHAR", batch_keys="VARCHAR[]",
    cache_hit_keys="VARCHAR[]", completed_batches="UBIGINT",
    reference_dps="DOUBLE", reference_samples="UBIGINT", reference_metric="VARCHAR",
    reference_personal_dps="DOUBLE", reference_identity="JSON", reference_summary="JSON",
    search_dps="DOUBLE", search_samples="UBIGINT", search_reference_ratio="DOUBLE",
    search_candidate_count="UBIGINT", search_unique_candidates="UBIGINT", search_rounds="UBIGINT",
    search_partial_round="BOOLEAN", search_stop_reason="VARCHAR", search_chains="JSON",
    search_observability="JSON",
    search_errors="JSON", search_metrics="JSON", selected_candidate_key="VARCHAR",
    locked_candidate_key="VARCHAR", improvement="VARCHAR", independent_validation_complete="BOOLEAN",
    native_batch_starts="UBIGINT", validation_summary="JSON", final_status="VARCHAR",
    final_scenarios="JSON", error="VARCHAR",
)
SEARCH_CHAMPION_SCHEMA = dict(
    condition_key="VARCHAR", binding="JSON", version="UBIGINT", program="JSON",
    behavior_identity="VARCHAR", source_run_id="VARCHAR", source_candidate_key="VARCHAR",
    source_candidate_data_key="VARCHAR",
    source_condition_key="VARCHAR", score="DOUBLE", samples="UBIGINT", batch_keys="VARCHAR[]",
    promotion_evidence="JSON", source_evidence="JSON", contract_version="UBIGINT", evaluation="JSON",
)
_SKILL_API = None
_SKILL_LOCK = threading.Lock()
_PUBLICATION_LOCK = threading.RLock()
_SCOPE_LOCKS = {}
_BOUND_PROJECT = None
_REPORT_LOCATIONS = None


class ReportLocations:
    """Small shared location journal; complete reports remain in the logical table."""
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / '.report-locations.jsonl'
        self.entries = {}
        self.groups = set()
        self.offset = 0

    @contextmanager
    def locked(self):
        import msvcrt
        with _PUBLICATION_LOCK, (self.root / '.report-publish.lock').open('a+b') as lease:
            if lease.tell() == 0:
                lease.write(b'0')
                lease.flush()
            deadline = time.monotonic() + 30
            while True:
                lease.seek(0)
                try:
                    msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise DataReadError('等待报告保存锁超时')
                    time.sleep(.05)
            try:
                self.refresh()
                yield self
            finally:
                lease.seek(0)
                msvcrt.locking(lease.fileno(), msvcrt.LK_UNLCK, 1)

    def refresh(self):
        if not self.path.exists():
            if self.offset or self._unindexed_groups():
                raise DataReadError('报告位置清单缺失，已有报告组不能重新发布')
            return
        with self.path.open('rb') as stream:
            if stream.seek(0, os.SEEK_END) < self.offset:
                raise DataReadError('报告位置清单被截短')
            stream.seek(self.offset)
            for line in stream:
                if not line.endswith(b'\n'):
                    break  # An unfinished reservation cannot precede publication.
                try:
                    record = json.loads(line)
                    payload = dict(group=record['group'], keys=record['keys'])
                    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
                    if (not isinstance(payload['group'], str) or not isinstance(payload['keys'], list)
                            or not all(isinstance(key, str) for key in payload['keys'])
                            or hashlib.sha256(encoded).hexdigest() != record['sha256']):
                        raise ValueError('位置清单校验不符')
                except (ValueError, KeyError, TypeError) as error:
                    raise DataReadError('报告位置清单损坏') from error
                self.entries.update((key, payload['group']) for key in payload['keys'])
                self.groups.add(payload['group'])
                self.offset += len(line)
        if self._unindexed_groups():
            raise DataReadError('报告位置清单不完整，已有报告组不能重新发布')

    def _unindexed_groups(self):
        return any(path.stem not in self.groups
                   for path in (self.root / 'batches').glob('*_g*.parquet')
                   if re.search(r'_g\d+$', path.stem))

    def reserve(self, group, keys):
        payload = dict(group=group, keys=list(keys))
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        record = dict(payload, sha256=hashlib.sha256(encoded).hexdigest())
        line = (json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n').encode()
        with self.path.open('a+b') as stream:
            stream.truncate(self.offset)
            stream.seek(self.offset)
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        self.offset += len(line)
        self.entries.update((key, group) for key in keys)
        self.groups.add(group)


class DataReadError(RuntimeError):
    """The data-store query boundary could not read a logical record."""


class InvalidRecordError(DataReadError):
    """The selected record is definitely corrupt, rather than temporarily unavailable."""


def _skill_root() -> Path:
    return (_BOUND_PROJECT or Path(__file__).resolve().parents[2]) / ".local" / "skills" / "data-store"


def bind_project(project):
    """Use an explicitly chosen, already connected project center; never create another."""
    global DATA_ROOT, _BOUND_PROJECT, _SKILL_API
    project = Path(project).resolve()
    if not (project / 'data').is_dir() or not (
            project / '.local/skills/data-store/scripts/data_store.py').is_file():
        raise ValueError('指定项目缺少既有数据中心或数据存储接入')
    DATA_ROOT, _BOUND_PROJECT, _SKILL_API = project / 'data', project, None
    ensure_available()


def _api():
    global _SKILL_API
    if _SKILL_API is None:
        with _SKILL_LOCK:
            if _SKILL_API is None:
                script = _skill_root() / "scripts" / "data_store.py"
                if not script.is_file():
                    raise RuntimeError(
                        "数据中心尚未接入本项目，请从已安装技能入口运行 project_binding.py connect --project <仓库>"
                    )
                functions = runpy.run_path(str(script))
                if functions.get("DATA_STORE_API_VERSION") != 2:
                    raise DataReadError("data-store 接口版本不支持，请同步具备 API 版本 2 的技能后重启")
                required = ("write", "query", "read_key", "read_keys", "MissingKeyError", "CorruptDataError")
                if any(name not in functions for name in required):
                    raise DataReadError("data-store 技能缺少逻辑键点读能力，请同步已安装的技能后重启")
                _SKILL_API = {name: functions[name] for name in required}
                _SKILL_API["DATA_STORE_CAPABILITIES"] = functions.get("DATA_STORE_CAPABILITIES", ())
    return _SKILL_API


def ensure_available() -> None:
    """Fail before a simulation if the installed storage skill is unavailable."""
    _api()
    try:
        import duckdb  # noqa: F401
    except ImportError as error:
        raise RuntimeError("缺少 DuckDB，请使用 data-store 技能 requirements.txt 准备当前 Python 环境") from error


def write(table: str, key: str, rows: list[dict], *, schema=None, binary=False) -> int:
    """Write caller-defined typed records through the installed skill."""
    api = _api()
    if binary:
        if "binary-write-v1" not in api.get("DATA_STORE_CAPABILITIES", ()):
            raise DataReadError("data-store 缺少 binary-write-v1 能力，请更新技能并重启当前进程")
        return api["write"](DATA_ROOT, table, key, rows, schema=schema, binary=True)
    return api["write"](DATA_ROOT, table, key, rows, schema=schema)



def read_search_champion(condition_key):
    """One small authoritative record; a read failure is never an empty champion."""
    rows = read_records('search_champions', condition_key)
    if not rows:
        return None
    if len(rows) != 1 or rows[0].get('condition_key') != condition_key:
        raise InvalidRecordError('正式冠军记录身份不唯一或不符')
    record = rows[0]
    for field in ('binding', 'program', 'promotion_evidence', 'source_evidence', 'evaluation'):
        if isinstance(record.get(field), str):
            try:
                record[field] = json.loads(record[field])
            except ValueError as error:
                raise InvalidRecordError('正式冠军记录损坏') from error
    if (type(record.get('version')) is not int or record['version'] < 1
            or not isinstance(record.get('binding'), dict)
            or not isinstance(record.get('program'), list)
            or not record['program'] or not isinstance(record.get('behavior_identity'), str)):
        raise InvalidRecordError('正式冠军记录缺少完整身份')
    return record


@contextmanager
def _publication_lock(name):
    import msvcrt
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', name):
        raise ValueError('成果切换锁名称无效')
    with _PUBLICATION_LOCK:
        process_lock = _SCOPE_LOCKS.setdefault(name, threading.RLock())
    with process_lock, (DATA_ROOT / ('.' + name + '.lock')).open('a+b') as lease:
        if lease.tell() == 0:
            lease.write(b'0')
            lease.flush()
        deadline = time.monotonic() + 30
        while True:
            lease.seek(0)
            try:
                msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise DataReadError('等待当前成果切换锁超时')
                time.sleep(.05)
        try:
            yield
        finally:
            lease.seek(0)
            msvcrt.locking(lease.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def _search_champion_lock():
    with _publication_lock('search-champions'):
        yield


def _seed_rows_digest(rows):
    from search import digest
    normalized = []
    for row in rows:
        row = dict(row)
        for key in ('configuration_key', 'program', 'engines', 'evaluation'):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        normalized.append(row)
    return digest(sorted(normalized, key=lambda row: row['candidate_id']))


def seed_selected_revision(scope):
    return _seed_rows_digest(read_records('seed_selected', scope))


def publish_seed_selected(scope, rows, expected_revision, *, schema):
    """完整证据已验真后，只在同一范围的短锁内比较旧版并切换。"""
    revision = _seed_rows_digest(rows)
    with _publication_lock('seed-selected-' + scope):
        current = seed_selected_revision(scope)
        if current == revision:
            return
        if current != expected_revision:
            raise ValueError('当前训练成果已经变化，本次完整证据保留，未替换现有四条')
        write('seed_selected', scope, rows, schema=schema)
        if seed_selected_revision(scope) != revision:
            raise DataReadError('训练四条切换后读回不一致')


def publish_search_champion(record, expected_version, *, expected_incumbent=None):
    """CAS protects a new incumbent; equivalent publication preserves its original source."""
    with _search_champion_lock():
        current = read_search_champion(record['condition_key'])
        if current and current['behavior_identity'] == record['behavior_identity']:
            same = all(current.get(key) == value for key, value in record.items() if key != 'version')
            return dict(status='published' if same else 'unchanged', version=current['version'],
                        source_run_id=current['source_run_id'])
        if expected_incumbent and (current is None or any(current.get(key) != value
                for key, value in expected_incumbent.items())):
            return dict(status='conflict', version=current['version'] if current else 0,
                        source_run_id=current['source_run_id'] if current else None,
                        reason='正式冠军已变化，本次结果保留但未接班')
        version = current['version'] if current else 0
        if version != expected_version:
            return dict(status='conflict', version=version,
                        source_run_id=current['source_run_id'] if current else None,
                        reason='正式冠军已变化，本次结果保留但未接班')
        record = dict(record, version=version + 1)
        write('search_champions', record['condition_key'], [record], schema=SEARCH_CHAMPION_SCHEMA)
        return dict(status='published', version=record['version'], source_run_id=record['source_run_id'])














def _report_columns(value):
    # SimC emits empty objects for absent statistics; Parquet represents these as NULL.
    if isinstance(value, dict):
        return {name: _report_columns(item) for name, item in value.items()} or None
    if isinstance(value, list):
        return [_report_columns(item) for item in value]
    return value


def _state_value_report(report, *, restore=False, normalize=False):
    """仅适配规则观察的异构值与费用映射；统计空对象仍沿原约定。"""
    players = []
    fields = {'boolean': bool, 'integer': int, 'number': float, 'record': dict}
    columns = _report_columns if normalize else lambda value: value
    for player in report['sim']['players']:
        payload = player.get('sim2gse_rule_observations')
        if not isinstance(payload, dict):
            players.append(columns(player))
            continue
        states = []
        original_states = payload.get('state_observations')
        for original in original_states if isinstance(original_states, list) else []:
            row = dict(original)
            stored = row.pop('value_storage', None)
            if stored is not None:
                if isinstance(stored, dict) and type(stored.get('version')) is int and stored['version'] > 2:
                    raise DataReadError('状态值存储版本尚未支持，保留原成功记录')
                if (not isinstance(stored, dict) or type(stored.get('version')) is not int
                        or stored['version'] not in (1, 2) or not isinstance(stored.get('kind'), str)
                        or stored['kind'] not in {*fields, 'unknown', 'missing', 'empty_record'}
                        or stored['kind'] == 'empty_record' and stored['version'] != 2
                        or set(stored) - {'version', 'kind', *fields} or row.get('value') is not None):
                    raise InvalidRecordError('状态值存储版本、标签或原值冲突')
                kind = stored['kind']
                value = stored.get(kind) if kind in fields else None
                if (kind in fields and type(value) is not fields[kind]
                        or any(stored.get(name) is not None for name in fields if name != kind)):
                    raise InvalidRecordError('状态值存储类型或占位字段无效')
                if restore:
                    if kind == 'missing': row.pop('value', None)
                    else: row['value'] = {} if kind == 'empty_record' else value
                else:
                    row.pop('value', None)  # 混读旧分片时DuckDB可能补出该NULL列。
                    row['value_storage'] = stored
            elif not restore:
                missing = 'value' not in row
                value = row.pop('value', None)
                kind = ('empty_record' if type(value) is dict and not value else
                        next((name for name, expected in fields.items() if type(value) is expected), None))
                if value is not None and kind is None:
                    raise ValueError('不支持的状态值存储类型')
                stored = dict(version=2 if kind == 'empty_record' else 1,
                              kind='missing' if missing else kind or 'unknown', **dict.fromkeys(fields))
                if kind in fields: stored[kind] = value
                row['value_storage'] = stored
            states.append(columns(row))
        # 按行转换后即形成最终列，避免先攒全量中间集合再递归复制一遍。
        collections = {'state_observations', 'action_observations', 'action_events'}
        observed = {name: columns(value) for name, value in payload.items()
                    if name not in collections or not isinstance(value, list)}
        if isinstance(original_states, list):
            observed['state_observations'] = states
        for collection in ('action_observations', 'action_events'):
            if isinstance(payload.get(collection), list):
                observed[collection] = [columns(_resource_cost_row(row, restore=restore))
                                        for row in payload[collection]]
        if normalize and not observed:
            observed = None
        players.append({name: observed if name == 'sim2gse_rule_observations' else columns(value)
                        for name, value in player.items()})
    if normalize:
        simulation = {name: players if name == 'players' else columns(value)
                      for name, value in report['sim'].items()}
        return {name: simulation if name == 'sim' else columns(value)
                for name, value in report.items()}
    return dict(report, sim=dict(report['sim'], players=players))


def _resource_cost_row(original, *, restore):
    row = dict(original)
    stored = row.pop('resource_costs_storage', None)
    if stored is None:
        if not restore:
            value = row.get('resource_costs')
            if (value is not None and not isinstance(value, dict)
                    or isinstance(value, dict) and any(not isinstance(key, str) or not key for key in value)):
                raise ValueError('费用映射存储类型无效')
            row['resource_costs_storage'] = dict(version=1,
                kind='missing' if 'resource_costs' not in row else 'unknown' if value is None else 'record',
                keys=list(value) if isinstance(value, dict) else [])
        return row
    if isinstance(stored, dict) and type(stored.get('version')) is int and stored['version'] > 1:
        raise DataReadError('费用映射存储版本尚未支持，保留原成功记录')
    if (not isinstance(stored, dict) or set(stored) != {'version', 'kind', 'keys'}
            or type(stored['version']) is not int or stored['version'] != 1
            or stored['kind'] not in ('record', 'unknown', 'missing')
            or not isinstance(stored['keys'], list)
            or any(not isinstance(key, str) or not key for key in stored['keys'])
            or len(set(stored['keys'])) != len(stored['keys'])
            or stored['kind'] != 'record' and stored['keys']):
        raise InvalidRecordError('费用映射存储版本、标签或键无效')
    value = row.get('resource_costs')
    if stored['kind'] == 'record':
        if value is None and not stored['keys']: value = {}
        if (not isinstance(value, dict) or any(key not in value for key in stored['keys'])
                or any(item is not None for key, item in value.items() if key not in stored['keys'])):
            raise InvalidRecordError('费用映射存储键或原值冲突')
        if restore: row['resource_costs'] = {key: value[key] for key in stored['keys']}
    elif value is not None:
        raise InvalidRecordError('费用映射存储标签与原值冲突')
    elif restore:
        if stored['kind'] == 'missing': row.pop('resource_costs', None)
        else: row['resource_costs'] = None
    if not restore:
        row['resource_costs_storage'] = stored
    return row


def _action_summary_report(report, *, restore=False):
    """变长按钮映射作为已有报告内的小段JSON文本保存，避免分组列合并补空值。"""
    players = []
    for original in report['sim']['players']:
        player = dict(original)
        summary = player.get('sim2gse_action_summary')
        if summary is not None:
            if restore and isinstance(summary, str):
                from action_summary import checked
                try:
                    decoded = json.loads(summary)
                    player['sim2gse_action_summary'] = checked(decoded, decoded.get('samples'))
                except (ValueError, TypeError, AttributeError) as error:
                    raise InvalidRecordError('报告成功摘要存储损坏') from error
            elif not restore and isinstance(summary, dict):
                player['sim2gse_action_summary'] = json.dumps(summary, ensure_ascii=False,
                    sort_keys=True, separators=(',', ':'), allow_nan=False)
        elif restore:
            player.pop('sim2gse_action_summary', None)  # Historical report without the field.
        players.append(player)
    return dict(report, sim=dict(report['sim'], players=players))


def _restore_batch(row):
    return dict(row, report=_action_summary_report(_state_value_report(row['report'], restore=True), restore=True)) if isinstance(row.get('report'), dict) else row


def write_batch(key: str, row: dict, *, diagnostic_logging=False, runtime=None) -> int:
    """Persist normal report columns; sampled action traces follow the diagnostic switch."""
    prepared = prepare_batch(row, diagnostic_logging=diagnostic_logging, runtime=runtime)
    logging = runtime is not None and runtime.diagnostic_logging
    if logging:
        from runtime import diagnostic_start, diagnostic_finish
        started = diagnostic_start()
    else:
        started = None
    try:
        return write('batches', key, [prepared])
    finally:
        if logging:
            diagnostic_finish(runtime, 'report.write', started, rows=1, groups=1)


def prepare_batch(row: dict, *, diagnostic_logging=False, runtime=None) -> dict:
    """Normalize a complete report before bounded group publication."""
    if runtime is not None:
        diagnostic_logging = runtime.diagnostic_logging
    logging = runtime is not None and runtime.diagnostic_logging
    if logging:
        from runtime import diagnostic_start, diagnostic_finish
        started = diagnostic_start()
    else:
        started = None
    try:
        if not diagnostic_logging:
            report = row['report']
            players = [dict(player, collected_data={name: value for name, value
                        in player.get('collected_data', {}).items()
                        if name not in {'action_sequence', 'action_sequence_precombat'}})
                       for player in report['sim']['players']]
            row = dict(row, report=dict(report, sim=dict(report['sim'], players=players)))
        return dict(row, report=_state_value_report(_action_summary_report(row['report']), normalize=True))
    finally:
        if logging:
            diagnostic_finish(runtime, 'report.prepare', started, rows=1)

def write_traces(key: str, run_id: str, events: list[dict], *, batch_key=None) -> int:
    if not events:
        return 0
    return write("traces", key, [dict(run_id=run_id, batch_key=batch_key,
                                      event_index=index, **event)
                                  for index, event in enumerate(events)])


def query(sql: str, parameters=None, *, tables):
    """Return a cursor limited to the caller's explicit logical tables."""
    try:
        return _api()["query"](DATA_ROOT, sql, parameters, tables=tables)
    except (DataReadError, ValueError, TypeError):
        raise
    except Exception as error:
        raise DataReadError('数据中心查询不可读') from error


def read_records(table: str, key: str, *, columns=None, filters=None):
    """Point-read a caller-defined record group; only a missing key is empty."""
    return _read_records("read_key", table, key, columns=columns, filters=filters)


def read_many(table: str, keys, *, columns=None, filters=None):
    """Read only known groups, retaining the public multi-key failure boundary."""
    if not keys:
        return []
    return _read_records("read_keys", table, keys, columns=columns, filters=filters)


def iter_group(table, key):
    """只读取明确指定的一组，逐条交出完整报告，避免整组读回峰值。"""
    yield from _iter_groups(table, [key])


def _iter_groups(table, keys):
    """已知分片共用一次公开批量读取，仍逐条交出，不扫描历史库。"""
    api = _api()
    try:
        operation, argument = ('read_key', keys[0]) if len(keys) == 1 else ('read_keys', keys)
        with api[operation](DATA_ROOT, table, argument) as cursor:
            names = [column[0] for column in cursor.description]
            while values := cursor.fetchone():
                row = dict(zip(names, values))
                yield _restore_batch(row) if table == 'batches' else row
    except api['MissingKeyError'] as error:
        raise DataReadError('指定报告组缺失') from error
    except api['CorruptDataError'] as error:
        raise InvalidRecordError('指定报告组损坏') from error


def _ordered_search_records(groups):
    """已知分组逐行取入紧凑内存排序区，不新增磁盘或改变对外保存格式。"""
    from contextlib import closing
    import pickle
    import sqlite3
    with closing(sqlite3.connect(':memory:')) as ordered:
        ordered.execute('PRAGMA temp_store=MEMORY')
        ordered.execute('CREATE TABLE records (ordinal INTEGER PRIMARY KEY, payload BLOB NOT NULL)')
        groups = [groups] if isinstance(groups, str) else groups
        source = iter_group('search_records', groups[0]) if len(groups) == 1 else _iter_groups('search_records', groups)
        with closing(source):
            def packed():
                for row in source:
                    ordinal = row.get('search_order')
                    if not isinstance(ordinal, int) or ordinal < 0:
                        raise InvalidRecordError('搜索摘要数量、顺序或总摘要不符')
                    # 仅本进程把自己刚编码的记录放入内存排序区，绝不读外部pickle文件。
                    yield ordinal, pickle.dumps(row, protocol=5)
            try:
                ordered.executemany('INSERT INTO records VALUES (?,?)', packed())
            except (sqlite3.Error, OverflowError) as error:
                raise InvalidRecordError('搜索摘要数量、顺序或总摘要不符') from error
        for (payload,) in ordered.execute('SELECT payload FROM records ORDER BY ordinal'):
            yield pickle.loads(payload)


def _validate_search_record(row, run_id, condition):
    import math
    from search import digest
    if (row['run_id'] != run_id or digest(row['program']) != row['program_digest']
            or not isinstance(row['batches'], list) or not row['batches']):
        raise InvalidRecordError('搜索摘要的任务或程序身份不符')
    for batch in row['batches']:
        request = batch.get('request') or {}
        if (request.get('purpose') != 'search' or request.get('behavior_identity') != row['candidate_key']
                or condition is not None and request.get('condition') != condition
                or digest(request) != batch.get('data_key') or batch.get('status') != 'success'
                or type(batch.get('samples')) is not int or batch['samples'] < 1
                or type(batch.get('dps')) not in (int, float)
                or not math.isfinite(batch['dps']) or batch['dps'] < 0):
            raise InvalidRecordError('搜索轻量成绩凭据身份或数值不符')
    samples = sum(batch['samples'] for batch in row['batches'])
    if sum(batch['dps'] * batch['samples'] for batch in row['batches']) / samples != row['score']:
        raise InvalidRecordError('搜索摘要成绩不符')


def read_search_records(storage, run_id, *, condition=None, columns=None):
    """完整验真全部历史后才交出结果；可只保留消费者需要的字段。"""
    from contextlib import closing
    from source_catalog import digest_rows
    fields = {'run_id', 'candidate_key', 'search_order', 'program', 'program_digest', 'score', 'batches', 'candidate'}
    if columns is not None and (not isinstance(columns, (list, tuple)) or not columns
            or any(not isinstance(name, str) or name not in fields for name in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError('搜索摘要选择字段无效')
    if (not isinstance(storage, dict) or storage.get('version') != 3
            or not isinstance(storage.get('archive_group'), str)
            or not isinstance(storage.get('archive_digest'), str)
            or type(storage.get('archive_count')) is not int or storage['archive_count'] < 1):
        raise InvalidRecordError('搜索摘要位置或版本缺失')
    archive_format = storage.get('archive_format', 1)
    groups = storage.get('archive_groups', [storage['archive_group']])
    if (type(archive_format) is not int or archive_format not in (1, 2)
            or archive_format == 1 and 'archive_groups' in storage
            or not isinstance(groups, list) or not groups
            or any(not isinstance(group, str) or not group for group in groups)
            or len(set(groups)) != len(groups) or groups[0] != storage['archive_group']
            or archive_format == 2 and 'archive_groups' not in storage):
        raise InvalidRecordError('搜索摘要分片位置或版本无效')
    rows, identities, count, ordinals_contiguous, first_error = [], set(), 0, True, None
    def checked(source):
        nonlocal count, ordinals_contiguous, first_error
        for row in source:
            try:
                for key in ('program', 'batches', 'candidate'):
                    if isinstance(row.get(key), str):
                        row[key] = json.loads(row[key])
                ordinals_contiguous = ordinals_contiguous and row['search_order'] == count
                identities.add(row['candidate_key'])
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise InvalidRecordError('搜索摘要字段缺失或损坏') from error
            try:
                _validate_search_record(row, run_id, condition)
            except InvalidRecordError as error:
                if first_error is None:
                    first_error = str(error)
            except (KeyError, TypeError, ValueError, AttributeError):
                if first_error is None:
                    first_error = '搜索摘要字段缺失或损坏'
            yield row
            rows.append({name: row.get(name) for name in columns} if columns is not None else row)
            count += 1
    with closing(_ordered_search_records(groups)) as source:
        checksum = digest_rows(checked(source))
    if (count != storage['archive_count'] or checksum != storage['archive_digest']
            or not ordinals_contiguous or len(identities) != count):
        raise InvalidRecordError('搜索摘要数量、顺序或总摘要不符')
    if first_error is not None:
        raise InvalidRecordError(first_error)
    return rows


def publish_search_records(state):
    """完成或主动暂停时保存一份轻量归档；普通运行不调用。"""
    from search import digest
    rows = []
    for index, record in enumerate(state.get('archive', [])):
        candidate = record.get('candidate')
        if candidate is not None:
            candidate = {key: candidate.get(key) for key in ('source', 'program', 'text', 'simulation')}
            candidate['identity'] = record['key']
        rows.append(dict(run_id=state['run_id'], candidate_key=record['key'], search_order=index,
            program=record['program'], program_digest=digest(record['program']), score=float(record['score']),
            batches=record['batches'], candidate=candidate))
    if not rows:
        return
    previous = state.get('evidence_storage') or {}
    if previous.get('archive_group'):
        saved = read_search_records(previous, state['run_id'], condition=state.get('condition'),
                                    columns=['candidate_key', 'program_digest', 'score', 'batches'])
        def core(record):
            return (record['candidate_key'], record['program_digest'], record['score'],
                    [{key: batch.get(key) for key in ('data_key', 'request', 'dps', 'samples', 'variance')}
                     for batch in record['batches']])
        if len(saved) > len(rows) or any(core(left) != core(right) for left, right in zip(saved, rows)):
            raise InvalidRecordError('已保存搜索摘要与当前冻结成绩冲突')
        if len(saved) == len(rows):
            return  # 恢复时少了历史编译对象，不改变已验证的来源身份。
        del saved
    from source_catalog import digest_rows
    checksum = digest_rows(iter(rows))
    group = state['run_id'] + '_a' + checksum[:20]
    storage = dict(state.get('evidence_storage') or dict(version=3, report_groups={}),
        archive_group=group, archive_digest=checksum, archive_count=len(rows))
    plans = [(group, rows)]
    if len(rows) > 512:
        plans = [(group + '_p' + str(index // 512), rows[index:index + 512])
                 for index in range(0, len(rows), 512)]
        storage.update(archive_format=2, archive_group=plans[0][0],
                       archive_groups=[key for key, _ in plans])
    else:
        storage.pop('archive_format', None)
        storage.pop('archive_groups', None)
    schema = dict(run_id='VARCHAR', candidate_key='VARCHAR', search_order='UBIGINT', program='JSON',
        program_digest='VARCHAR', score='DOUBLE', batches='JSON', candidate='JSON')
    try:
        read_search_records(storage, state['run_id'], condition=state.get('condition'), columns=['candidate_key'])
    except DataReadError as error:
        if error.__cause__ is None or not isinstance(error.__cause__, _api()['MissingKeyError']):
            raise
        for key, part in plans:
            if len(plans) == 1:
                write('search_records', key, part, schema=schema)
                continue
            try:
                with _api()['read_key'](DATA_ROOT, 'search_records', key, columns=['candidate_key']):
                    pass
            except _api()['MissingKeyError']:
                write('search_records', key, part, schema=schema)
            else:
                receipt = dict(version=3, archive_group=key, archive_count=len(part), archive_digest=digest_rows(part))
                read_search_records(receipt, state['run_id'], condition=state.get('condition'), columns=['candidate_key'])
        read_search_records(storage, state['run_id'], condition=state.get('condition'), columns=['candidate_key'])
    state['evidence_storage'] = storage


def _read_records(operation, table, keys, *, columns, filters):
    api = _api()
    try:
        options = {}
        if columns is not None:
            options['columns'] = columns
        if filters is not None:
            options['filters'] = filters
        with api[operation](DATA_ROOT, table, keys, **options) as cursor:
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor.fetchall()]
            return [_restore_batch(row) for row in rows] if table == 'batches' else rows
    except api['MissingKeyError'] as error:
        if operation == "read_key":
            return []
        raise DataReadError('数据中心指定记录组缺失') from error
    except api['CorruptDataError'] as error:
        raise InvalidRecordError('数据中心目标记录损坏') from error
    except InvalidRecordError:
        raise
    except Exception as error:
        raise DataReadError(f'数据中心记录不可读: {error}') from error


def report_locations(keys):
    """Reuse the verified journal and refresh its delta once for a set of keys."""
    global _REPORT_LOCATIONS
    try:
        with _PUBLICATION_LOCK:
            if _REPORT_LOCATIONS is None or _REPORT_LOCATIONS.root != Path(DATA_ROOT):
                _REPORT_LOCATIONS = ReportLocations(DATA_ROOT)
            with _REPORT_LOCATIONS.locked() as locations:
                return {key: locations.entries.get(key) for key in keys}
    except OSError as error:
        raise DataReadError('报告位置清单不可读取') from error


def one(table: str, field: str, value, *, group_key=None, columns=None):
    """Read at most two matching rows, returning a named record if unique."""
    if table not in {"runs", "candidates", "batches"} or field not in {
        "run_id", "candidate_key", "candidate_data_key", "batch_key"
    }:
        raise ValueError("不支持的数据中心读取键")
    api = _api()
    stored_key = {"runs": "run_id", "candidates": "candidate_data_key", "batches": "batch_key"}
    try:
        if table == 'batches' and group_key is None and (DATA_ROOT / '.report-locations.jsonl').exists():
            group_key = report_locations([value]).get(value)
        options = {'columns': columns} if columns is not None else {}
        cursor = (api["read_key"](DATA_ROOT, table, group_key, filters={field: value}, **options) if group_key else
                  api["read_key"](DATA_ROOT, table, value, **options) if field == stored_key[table]
                  else query(f"SELECT * FROM {table} WHERE {field} = ?", [value], tables=[table]))
        with cursor:
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchmany(2)
    except api["MissingKeyError"]:
        return None
    except api["CorruptDataError"] as error:
        raise InvalidRecordError("结果中心目标记录损坏") from error
    except Exception as error:
        raise DataReadError(f"结果中心记录不可读: {error}") from error
    if len(rows) != 1:
        return None
    record = dict(zip(columns, rows[0]))
    if record.get(field) != value: return None
    return _restore_batch(record) if table == 'batches' else record


def iter_rows(sql: str, parameters=None, *, tables, batch_size: int = 500):
    """Yield named rows from a center query using bounded cursor reads."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size 必须大于零")
    try:
        with query(sql, parameters, tables=tables) as cursor:
            columns = [column[0] for column in cursor.description]
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    yield dict(zip(columns, row))
    except Exception as error:
        raise DataReadError("结果中心查询失败") from error


def report_for_task(directory: Path):
    """Read the normal simulation report behind a task's small identity pointer."""
    import json
    pointer = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    run = one('runs', 'run_id', pointer['run_id'])
    if run is None:
        raise DataReadError('结果中心任务缺失')
    key = run.get('controlled_data_key') or run.get('reference_data_key')
    batch = one('batches', 'batch_key', key)
    if batch is None:
        raise DataReadError('结果中心模拟报告缺失')
    return batch['report']
