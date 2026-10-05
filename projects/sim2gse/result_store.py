"""Sim2GSE adapter for the installed data-store skill."""

from __future__ import annotations

import runpy
from pathlib import Path
import threading


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
CANDIDATE_SCHEMA = dict(
    run_id="VARCHAR", candidate_key="VARCHAR", candidate_data_key="VARCHAR",
    source="VARCHAR", search_order="UBIGINT", program="JSON", export_text="VARCHAR", simulation="VARCHAR",
    selected_sequence="VARCHAR", selected_version="UBIGINT", import_sha256="VARCHAR",
    game_validation="VARCHAR",
)
RUN_SCHEMA = dict(
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
_SKILL_API = None
_SKILL_LOCK = threading.Lock()


class DataReadError(RuntimeError):
    """The data-store query boundary could not read a logical record."""


class InvalidRecordError(DataReadError):
    """The selected record is definitely corrupt, rather than temporarily unavailable."""


def _skill_root() -> Path:
    return Path.home() / ".agents" / "skills" / "data-store"


def _api():
    global _SKILL_API
    if _SKILL_API is None:
        with _SKILL_LOCK:
            if _SKILL_API is None:
                script = _skill_root() / "scripts" / "data_store.py"
                if not script.is_file():
                    raise RuntimeError(
                        "未找到已安装的 data-store 技能，请检查 ~/.agents/skills/data-store 联接"
                    )
                functions = runpy.run_path(str(script))
                required = ("write", "query", "read_key", "MissingKeyError", "CorruptDataError")
                if any(name not in functions for name in required):
                    raise RuntimeError("data-store 技能缺少逻辑键点读能力，请同步已安装的技能")
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



def _report_columns(value):
    # SimC emits empty objects for absent statistics; Parquet represents these as NULL.
    if isinstance(value, dict):
        return {name: _report_columns(item) for name, item in value.items()} or None
    if isinstance(value, list):
        return [_report_columns(item) for item in value]
    return value


def write_batch(key: str, row: dict, *, diagnostic_logging=False) -> int:
    """Persist normal report columns; sampled action traces follow the diagnostic switch."""
    if not diagnostic_logging:
        report = row['report']
        players = [dict(player, collected_data={name: value for name, value
                    in player.get('collected_data', {}).items()
                    if name not in {'action_sequence', 'action_sequence_precombat'}})
                   for player in report['sim']['players']]
        row = dict(row, report=dict(report, sim=dict(report['sim'], players=players)))
    return write('batches', key, [dict(row, report=_report_columns(row['report']))])

def write_traces(key: str, run_id: str, events: list[dict], *, batch_key=None) -> int:
    if not events:
        return 0
    return write("traces", key, [dict(run_id=run_id, batch_key=batch_key,
                                      event_index=index, **event)
                                  for index, event in enumerate(events)])


def query(sql: str, parameters=None):
    """Return the installed skill's DuckDB cursor for bounded reads."""
    return _api()["query"](DATA_ROOT, sql, parameters)


def one(table: str, field: str, value):
    """Read at most two matching rows, returning a named record if unique."""
    if table not in {"runs", "candidates", "batches"} or field not in {
        "run_id", "candidate_key", "candidate_data_key", "batch_key"
    }:
        raise ValueError("不支持的数据中心读取键")
    api = _api()
    stored_key = {"runs": "run_id", "candidates": "candidate_data_key", "batches": "batch_key"}
    try:
        cursor = (api["read_key"](DATA_ROOT, table, value) if field == stored_key[table]
                  else query(f"SELECT * FROM {table} WHERE {field} = ?", [value]))
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
    return record if record.get(field) == value else None


def iter_rows(sql: str, parameters=None, *, batch_size: int = 500):
    """Yield named rows from a center query using bounded cursor reads."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size 必须大于零")
    try:
        with query(sql, parameters) as cursor:
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
