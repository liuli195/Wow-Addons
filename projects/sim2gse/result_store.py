"""Sim2GSE adapter for the installed data-store skill."""

from __future__ import annotations

import runpy
from contextlib import contextmanager
import hashlib
import json
import msvcrt
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
    config="JSON", simulation_config="JSON", engines="JSON", condition_key="VARCHAR",
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
    promotion_evidence="JSON", source_evidence="JSON",
)
SEARCH_LEARNER_SCHEMA = dict(
    model_key='VARCHAR', version='UBIGINT', state_version='UBIGINT',
    feature_version='VARCHAR', reward_version='VARCHAR', coba_version='VARCHAR',
    numpy_version='VARCHAR', dimension='UBIGINT', alpha='DOUBLE', features='JSON',
    seed='BIGINT', rng_state='BIGINT', theta='DOUBLE[]', a_inv='DOUBLE[][]',
    reservations='JSON', settled='JSON',
)
SEARCH_LEARNER_CONTROL_SCHEMA = dict(
    **{name: kind for name, kind in SEARCH_LEARNER_SCHEMA.items() if name not in ('theta', 'a_inv')},
    base_version='UBIGINT', phase='VARCHAR',
)
_SKILL_API = None
_SKILL_LOCK = threading.Lock()
_PUBLICATION_LOCK = threading.RLock()
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
    return _SKILL_API


def ensure_available() -> None:
    """Fail before a simulation if the installed storage skill is unavailable."""
    _api()
    try:
        import duckdb  # noqa: F401
    except ImportError as error:
        raise RuntimeError("缺少 DuckDB，请使用 data-store 技能 requirements.txt 准备当前 Python 环境") from error


def write(table: str, key: str, rows: list[dict], *, schema=None) -> int:
    """Write caller-defined typed records through the installed skill."""
    return _api()["write"](DATA_ROOT, table, key, rows, schema=schema)



def read_search_champion(condition_key):
    """One small authoritative record; a read failure is never an empty champion."""
    rows = read_records('search_champions', condition_key)
    if not rows:
        return None
    if len(rows) != 1 or rows[0].get('condition_key') != condition_key:
        raise InvalidRecordError('正式冠军记录身份不唯一或不符')
    record = rows[0]
    for field in ('binding', 'program', 'promotion_evidence', 'source_evidence'):
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
def _search_champion_lock():
    # ponytail: one short global publication lock; split by condition only if contention matters.
    with _PUBLICATION_LOCK, (DATA_ROOT / '.search-champions.lock').open('a+b') as lease:
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
                    raise DataReadError('等待正式冠军发布锁超时')
                time.sleep(.05)
        try:
            yield
        finally:
            lease.seek(0)
            msvcrt.locking(lease.fileno(), msvcrt.LK_UNLCK, 1)


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


@contextmanager
def search_learner_lock(runtime=None):
    """One short cross-process lock protects the shared learner's atomic record."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 30
    while True:
        if runtime is not None:
            runtime.check()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DataReadError('等待共享选择器保存锁超时')
        if _PUBLICATION_LOCK.acquire(timeout=min(.05, remaining)):
            break
    try:
        with (DATA_ROOT / '.search-learners.lock').open('a+b') as lease:
            if lease.tell() == 0:
                lease.write(b'0')
                lease.flush()
            while True:
                if runtime is not None:
                    runtime.check()
                lease.seek(0)
                try:
                    msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise DataReadError('等待共享选择器保存锁超时')
                    time.sleep(.05)
            try:
                yield
            finally:
                lease.seek(0)
                msvcrt.locking(lease.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        _PUBLICATION_LOCK.release()


def read_search_learner_metadata(model_key):
    """Caller holds the shared lock; inspect the same record's version and parameters."""
    rows = read_records('search_learners', model_key, columns=[
        'model_key', 'version', 'state_version', 'feature_version', 'reward_version',
        'coba_version', 'numpy_version', 'dimension', 'alpha', 'features', 'seed'])
    if not rows:
        return None
    if (len(rows) != 1 or rows[0].get('model_key') != model_key
            or type(rows[0].get('version')) is not int or rows[0]['version'] < 0):
        raise InvalidRecordError('共享选择器记录身份或版本无效')
    record = rows[0]
    if isinstance(record.get('features'), str):
        try:
            record['features'] = json.loads(record['features'])
        except ValueError as error:
            raise InvalidRecordError('共享选择器元数据损坏') from error
    return record


def read_search_learner(model_key):
    """Read the complete matrix snapshot; selector composes its newer control state."""
    rows = read_records('search_learners', model_key)
    if not rows:
        return None
    if len(rows) != 1 or rows[0].get('model_key') != model_key:
        raise InvalidRecordError('共享选择器记录身份不唯一或不符')
    record = rows[0]
    for field in ('features', 'reservations', 'settled'):
        if isinstance(record.get(field), str):
            try:
                record[field] = json.loads(record[field])
            except ValueError as error:
                raise InvalidRecordError('共享选择器元数据损坏') from error
    return record


def write_search_learner(record, *, runtime=None):
    """Caller holds the shared lock; this full commit absorbs older control state."""
    logging = runtime is not None and runtime.diagnostic_logging
    if logging:
        from runtime import diagnostic_start, diagnostic_finish
        started = diagnostic_start()
    else:
        started = None
    try:
        return write('search_learners', record['model_key'], [record], schema=SEARCH_LEARNER_SCHEMA)
    finally:
        if logging:
            try:
                diagnostic_finish(runtime, 'model.full_write', started, rows=1, dimension=record['dimension'], matrix_values=(record['dimension'] * (record['dimension'] + 1) if record.get('theta') is not None else 0), reservations=len(record['reservations']), settled=len(record['settled']))
            except Exception:
                pass


def read_search_learner_control(model_key):
    """Read the mandatory small v2 control record, including publication phase."""
    rows = read_records('search_learner_controls', model_key)
    if not rows:
        return None
    if len(rows) != 1 or rows[0].get('model_key') != model_key:
        raise InvalidRecordError('共享选择器控制记录身份不唯一或不符')
    record = rows[0]
    for field in ('features', 'reservations', 'settled'):
        if isinstance(record.get(field), str):
            try:
                record[field] = json.loads(record[field])
            except ValueError as error:
                raise InvalidRecordError('共享选择器控制记录损坏') from error
    return record


def write_search_learner_control(record, *, runtime=None):
    """Caller holds the shared lock; reserve/no-learn commit without copying matrices."""
    logging = runtime is not None and runtime.diagnostic_logging
    if logging:
        from runtime import diagnostic_start, diagnostic_finish
        started = diagnostic_start()
    else:
        started = None
    try:
        return write('search_learner_controls', record['model_key'], [record],
                     schema=SEARCH_LEARNER_CONTROL_SCHEMA)
    finally:
        if logging:
            try:
                diagnostic_finish(runtime, 'model.control_write', started, rows=1, reservations=len(record['reservations']), settled=len(record['settled']), **{record['phase'] + '_writes': 1})
            except Exception:
                pass


def _report_columns(value):
    # SimC emits empty objects for absent statistics; Parquet represents these as NULL.
    if isinstance(value, dict):
        return {name: _report_columns(item) for name, item in value.items()} or None
    if isinstance(value, list):
        return [_report_columns(item) for item in value]
    return value


def _state_value_report(report, *, restore=False):
    """仅适配规则观察的异构值与费用映射；统计空对象仍沿原约定。"""
    players = []
    fields = {'boolean': bool, 'integer': int, 'number': float, 'record': dict}
    for player in report['sim']['players']:
        payload = player.get('sim2gse_rule_observations')
        if not isinstance(payload, dict):
            players.append(player)
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
            states.append(row)
        observed = dict(payload)
        if isinstance(original_states, list):
            observed['state_observations'] = states
        for collection in ('action_observations', 'action_events'):
            if isinstance(payload.get(collection), list):
                observed[collection] = [_resource_cost_row(row, restore=restore) for row in payload[collection]]
        players.append(dict(player, sim2gse_rule_observations=observed))
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


def _restore_batch(row):
    return dict(row, report=_state_value_report(row['report'], restore=True)) if isinstance(row.get('report'), dict) else row


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
        return dict(row, report=_report_columns(_state_value_report(row['report'])))
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
