"""Sim2GSE（SimulationCraft 到 GSE 的离线任务入口）。

这个模块是后续界面和命令行共用的唯一本地入口。第一票先负责严格读取
单个角色文件；原生能力查询和导出步骤在同一入口中继续展开，失败时不会
留下看似成功的任务产物。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import string
import sqlite3
import argparse
import sys
import os
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
import msvcrt

from runtime import replace_file
from runtime import BudgetExceeded, TaskCancelled, TaskRuntime
from simulation_config import config_for as simulation_config_for, engine_options, load_config


class TaskError(ValueError):
    """用户输入或任务前置检查失败。"""


_CLASS_KEYS = {
    "deathknight",
    "demonhunter",
    "druid",
    "evoker",
    "hunter",
    "mage",
    "monk",
    "paladin",
    "priest",
    "rogue",
    "shaman",
    "warlock",
    "warrior",
}
_EQUIPMENT_SLOTS = {
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "shirt",
    "tabard",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
}
_ADDITIONAL_KEYS = {
    "catalyst_currencies",
    "upgrade_currencies",
    "slot_high_watermarks",
    "upgrade_achievements",
    "bonus_roll_currencies",
}
_ALLOWED_KEYS = {
    "allow_experimental_specializations",
    "level",
    "race",
    "region",
    "server",
    "role",
    "professions",
    "spec",
    "loot_spec",
    "talents",
    "omnium_talents",
    *_EQUIPMENT_SLOTS,
    *_ADDITIONAL_KEYS,
}
_TOKEN_FIELDS = {"race", "region", "role", "spec", "loot_spec"}
_OMNI_TALENTS_VALUE = r"(?:\d+:\d+|[a-z][a-z0-9_]*)(?:/(?:\d+:\d+|[a-z][a-z0-9_]*))*"
_OMNI_TALENTS_LINE = re.compile(
    rf"^[ \t]*omnium_talents=[ \t]*{_OMNI_TALENTS_VALUE}[ \t]*(?:\r\n|\n|\r)?$"
)
_ITEM_OPTIONS = {
    "id",
    "enchant_id",
    "bonus_id",
    "gem_id",
    "content_tuning",
    "redirected_base_stats",
    "crafted_stats",
    "crafting_quality",
    "ilevel",
    "embellishment",
    "enchant",
}


@dataclass(frozen=True)
class Equipment:
    slot: str
    item_id: int
    raw: str
    line_number: int


@dataclass(frozen=True)
class Character:
    name: str
    class_name: str
    level: int
    race: str
    spec: str
    spec_id: int | None
    fields: dict[str, str]
    equipment: dict[str, Equipment]
    bag_candidates: tuple[Equipment, ...]
    raw_text: str


def _parse_item(slot: str, value: str, line_number: int) -> Equipment | None:
    _validate_item_value(slot, value, line_number)
    match = re.search(r"(?:^|,)\s*id\s*=\s*(\d+)(?:,|$)", value)
    if not match:
        return None
    return Equipment(slot, int(match.group(1)), value, line_number)


def _validate_item_value(slot: str, value: str, line_number: int) -> None:
    if not value.startswith(","):
        raise TaskError(f"第 {line_number} 行 {slot} 装备字段格式错误")
    seen = set()
    for option in value[1:].split(","):
        if not option:
            raise TaskError(f"第 {line_number} 行 {slot} 装备字段含空选项")
        key, separator, option_value = option.partition("=")
        if separator != "=" or key not in _ITEM_OPTIONS or not option_value:
            raise TaskError(f"第 {line_number} 行 {slot} 装备选项格式错误")
        if key in seen:
            raise TaskError(f'第 {line_number} 行 {slot} 装备选项重复')
        seen.add(key)
        pattern = (r'[a-z][a-z0-9_]*' if key in ('embellishment', 'enchant') else
                   r'\d+' if key in ('id', 'ilevel', 'enchant_id', 'crafting_quality', 'content_tuning') else r'\d+(?:/\d+)*')
        if not re.fullmatch(pattern, option_value):
            raise TaskError(f"第 {line_number} 行 {slot} 装备选项值格式错误")
    if 'id' not in seen:
        raise TaskError(f'第 {line_number} 行 {slot} 缺少物品编号')


def precheck_burst(input_path, output_root, *, runtime=None, simulation_config=None, iterations=1,
                   failed_actions=None):
    """公开爆发预检查入口；未审核内容不得进入普通任务。"""
    from burst import load, prepare, input_times
    from engine import reference, inspect
    from program import compile_program, from_action_blocks
    from sequence import evaluate
    original_bytes, raw_text = _read_utf8(Path(input_path), description='角色输入')
    simulation_config = simulation_config_for(simulation_config)
    effective_bytes = _effective_input_bytes(original_bytes, raw_text, simulation_config)
    character = parse_character(effective_bytes.decode('utf-8'))
    runtime = runtime or TaskRuntime()
    folder = Path(output_root)
    effective_profile = folder / 'input.effective.simc'
    if effective_profile.resolve() == Path(input_path).resolve():
        raise TaskError('爆发预检查输出不能覆盖原始角色输入')
    folder.mkdir(parents=True, exist_ok=True)
    effective_profile.write_bytes(effective_bytes)
    try:
        native = reference(effective_profile, folder / 'reference', character, iterations=iterations,
                           runtime=runtime, simulation_config=simulation_config)
        definition = load(native['identity']['spec_id'])
        capabilities = inspect(native, folder / 'capabilities')
        blocks = prepare(definition, character, capabilities, native['identity'])
        program = from_action_blocks(blocks)
        program['metadata']['purpose'] = 'burst'
        program['metadata']['instructions'] = definition['instructions']
        candidate = compile_program(program, folder / 'export', identity=native['identity'], runtime=runtime)
        simulation = evaluate(effective_profile, candidate, folder / 'controlled', character=character,
                              iterations=iterations, runtime=runtime, simulation_config=simulation_config,
                              input_times=input_times(definition), failed_actions=failed_actions)
    except ValueError as error:
        raise TaskError(str(error)) from error
    return dict(definition=definition, candidate=candidate, simulation=simulation,
                native_reference=native, capabilities=capabilities)


def parse_character(raw_text: str) -> Character:
    """严格解析单角色 SimC（SimulationCraft）文本并保留原始内容。"""

    fields: dict[str, str] = {}
    class_rows: list[tuple[str, str, int]] = []
    equipment: dict[str, Equipment] = {}
    bags: list[Equipment] = []
    for line_number, line in enumerate(raw_text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            candidate = stripped[1:].strip() if stripped.startswith("#") else ""
            bag_key, separator, bag_value = candidate.partition('=')
            valid_bag_key = (separator == '=' and bag_key and bag_key[0] in string.ascii_lowercase
                             and all(char in string.ascii_lowercase + string.digits + '_' for char in bag_key))
            if valid_bag_key and bag_key in _EQUIPMENT_SLOTS:
                try:
                    parsed = _parse_item(bag_key, bag_value, line_number)
                except TaskError:
                    parsed = None  # Comments never become engine options.
                if parsed is not None:
                    bags.append(parsed)
            continue
        key, separator, value = stripped.partition('=')
        valid_key = (separator == '=' and key and key[0] in string.ascii_letters + '_'
                     and all(char in string.ascii_letters + string.digits + '_.' for char in key))
        if not valid_key:
            raise TaskError(f"第 {line_number} 行不是受支持的角色字段")
        if key in _CLASS_KEYS:
            class_rows.append((key, value, line_number))
            continue
        if key == "output":
            raise TaskError(f"第 {line_number} 行的 output 覆盖被禁止")
        if key == "copy" or key.startswith("actions"):
            raise TaskError(f"第 {line_number} 行的外部引用或动作列表覆盖被禁止")
        if key not in _ALLOWED_KEYS:
            raise TaskError(f"第 {line_number} 行包含未知字段 {key}")
        if key in fields:
            raise TaskError(f"字段 {key} 重复出现")
        fields[key] = value.strip()
        if key in _EQUIPMENT_SLOTS:
            parsed = _parse_item(key, value, line_number)
            if parsed is not None:
                equipment[key] = parsed

    if len(class_rows) != 1:
        raise TaskError("角色文件必须且只能包含一个角色")
    class_name, quoted_name, class_line = class_rows[0]
    quoted_match = re.fullmatch(r'"([^"\\\x00-\x1f]+)"', quoted_name)
    if quoted_match is None:
        raise TaskError(f"第 {class_line} 行角色名必须使用双引号")
    name = re.sub(r"\\([\\\"])", r"\1", quoted_match.group(1))
    if not name:
        raise TaskError("角色名不能为空")
    missing = [key for key in ("level", "race", "spec", "talents", "role", "main_hand") if key not in fields]
    if missing:
        raise TaskError("缺少角色字段: " + ", ".join(missing))
    try:
        level = int(fields["level"])
    except ValueError as exc:
        raise TaskError("level 必须是整数") from exc
    if not 1 <= level <= 100:
        raise TaskError("level 超出受支持范围")
    if 'server' in fields and not re.fullmatch(r'[\w-]+', fields['server']):
        raise TaskError('server 的值格式错误')
    for key in _TOKEN_FIELDS:
        if key in fields and not re.fullmatch(r"[a-z][a-z0-9_]*", fields[key].lower()):
            raise TaskError(f"字段 {key} 的值格式错误")
    if "professions" in fields and not re.fullmatch(
        r"[a-z][a-z0-9_]*=\d+(?:/[a-z][a-z0-9_]*=\d+)*", fields["professions"]
    ):
        raise TaskError("professions 的值格式错误")
    if "talents" in fields and not re.fullmatch(r"[A-Za-z0-9+/=]+", fields["talents"]):
        raise TaskError("talents 的值格式错误")
    if "omnium_talents" in fields and not re.fullmatch(_OMNI_TALENTS_VALUE, fields["omnium_talents"]):
        raise TaskError("omnium_talents 的值格式错误")
    for key in _ADDITIONAL_KEYS:
        if key in fields and not re.fullmatch(
            r"(?:[a-z][a-z0-9_]*:)?\d+(?::\d+)?(?:/(?:[a-z][a-z0-9_]*:)?\d+(?::\d+)?)*",
            fields[key],
        ):
            raise TaskError(f"字段 {key} 的值格式错误")
    spec = fields["spec"].lower()
    return Character(
        name=name,
        class_name=class_name,
        level=level,
        race=fields["race"].lower(),
        spec=spec,
        spec_id=None,
        fields=dict(fields),
        equipment=dict(equipment),
        bag_candidates=tuple(bags),
        raw_text=raw_text,
    )


def _profile(character: Character, raw_text: str, *, original_bytes: bytes | None = None,
             effective_bytes: bytes | None = None, run_id: str | None = None) -> dict:
    original_bytes = raw_text.encode("utf-8") if original_bytes is None else original_bytes
    effective_bytes = original_bytes if effective_bytes is None else effective_bytes
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()
    effective_sha256 = hashlib.sha256(effective_bytes).hexdigest()
    return {
        "identity": {
            "name": character.name,
            "class": character.class_name,
            "level": character.level,
            "race": character.race,
            "spec": character.spec,
            "spec_id": character.spec_id,
        },
        "fields": character.fields,
        "equipment": {
            slot: {"item_id": item.item_id, "raw": item.raw, "line": item.line_number}
            for slot, item in character.equipment.items()
        },
        "bag_candidates": [
            {"slot": item.slot, "item_id": item.item_id, "raw": item.raw, "line": item.line_number}
            for item in character.bag_candidates
        ],
        # 保留旧键供旧读者使用；恢复完整性以两份实际任务副本散列为准。
        "input_sha256": original_sha256,
        "input_original_sha256": original_sha256,
        "input_effective_sha256": effective_sha256,
        "run_id": run_id,
    }


def _write_json(path: Path, value: dict, *, atomic=False) -> None:
    target = path.with_suffix(path.suffix + ".tmp") if atomic else path
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if atomic:
        replace_file(target, path)


def _discard_native_exchange(folder: Path, *, keep_valid=False) -> None:
    for path in Path(folder).rglob('native.pending.json'):
        path.unlink(missing_ok=True)
    if not keep_valid:
        for path in Path(folder).rglob('native.json'):
            path.unlink(missing_ok=True)


def _store_candidate(run_id: str, candidate: dict, *, search_order=None) -> tuple[str, str]:
    from result_store import CANDIDATE_SCHEMA, write as write_records
    from search import digest

    program = candidate.get('program') or {}
    key = candidate.get('identity') or digest(program)
    data_key = digest(dict(run_id=run_id, candidate_key=key))
    write_records('candidates', data_key, [dict(
        run_id=run_id, candidate_key=key, candidate_data_key=data_key,
        source=candidate.get('source', 'search'), search_order=search_order, program=program,
        export_text=candidate.get('text', ''), simulation=candidate.get('simulation'),
        selected_sequence=candidate.get('selected_sequence'),
        selected_version=candidate.get('selected_version'),
        import_sha256=candidate.get('import_sha256'),
        game_validation=candidate.get('game_validation'))], schema=CANDIDATE_SCHEMA)
    return key, data_key


def _store_run(destination: Path, result: dict, *, state=None) -> dict:
    from result_store import RUN_SCHEMA, write as write_records

    profile_path = destination / 'profile.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    run_id = profile.get('run_id')
    if not isinstance(run_id, str) or not run_id:
        raise TaskError('任务缺少结果中心身份')
    burst_record = dict(result.get('burst') or (state or {}).get('burst') or {})
    burst_candidate = burst_record.pop('candidate', None)
    if burst_candidate is not None:
        burst_record['candidate_key'], burst_record['candidate_data_key'] = _store_candidate(run_id, burst_candidate)
    candidate = result.get('candidate')
    candidate_key = (candidate.get('identity') if isinstance(candidate, dict) else None)
    candidate_key = (candidate_key or result.get('locked_candidate_key')
                     or result.get('selected_candidate_key')
                     or (state or {}).get('locked_candidate_key'))
    candidate_data_key = None
    search_order = next((index for index, row in enumerate((state or {}).get('archive', []))
                         if row.get('key') == candidate_key), None)
    if isinstance(candidate, dict):
        candidate_key, candidate_data_key = _store_candidate(run_id, candidate, search_order=search_order)
    elif candidate_key:
        archived = next((row.get('candidate') for row in (state or {}).get('archive', [])
                         if row.get('key') == candidate_key and row.get('candidate')), None)
        if archived is not None:
            candidate_key, candidate_data_key = _store_candidate(run_id, archived, search_order=search_order)
    search = result.get('search') or state or {}
    native = result.get('native_reference') or (state or {}).get('native') or {}
    summary = result.get('search_result') or (state or {}).get('search_result') or {}
    locked_key = result.get('locked_candidate_key') or (state or {}).get('locked_candidate_key')
    if not summary and locked_key:
        locked = next((row for row in (state or {}).get('archive', [])
                       if row.get('key') == locked_key), None)
        if locked and isinstance(locked.get('score'), (int, float)):
            samples = sum(batch.get('samples', 0) for batch in locked.get('batches', []))
            summary = dict(dps=locked['score'], samples=samples,
                           reference_dps=native.get('dps'),
                           reference_ratio=(locked['score'] / native['dps']
                                            if native.get('dps') else None))
    final = result.get('final') or {}
    batch_keys = set()

    def collect_batch_keys(value):
        if isinstance(value, dict):
            data_key = value.get('data_key')
            if isinstance(data_key, str):
                batch_keys.add(data_key)
            for child in value.values():
                collect_batch_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_batch_keys(child)

    collect_batch_keys(result)
    collect_batch_keys((state or {}).get("archive", []))
    reference_data_key = result.get('reference_data_key') or (state or {}).get('reference_data_key')
    controlled_data_key = result.get('controlled_data_key')
    for data_key in (reference_data_key, controlled_data_key):
        if isinstance(data_key, str):
            batch_keys.add(data_key)
    search_metric_names = ('batch_requests', 'batch_cache_hits', 'native_batch_starts',
                           'canonicalized_duplicates', 'no_improvement_round_limit', 'rule_diagnostics',
                           'rule_diagnostics_version')
    search_metrics = {name: search[name] for name in search_metric_names if name in search}
    if state and state.get('rule_steps'):
        search_metrics['rule_steps'] = state['rule_steps']
    replays = {row['key']: dict(batch_key=row['batches'][0]['data_key'], diagnostic=row['rule_diagnostics'])
               for row in (state or {}).get('archive', []) if row.get('diagnostics_replayed')}
    if replays:
        search_metrics['rule_diagnostic_replays'] = replays
    initialization = result.get('rule_initialization') or (state or {}).get('rule_initialization')
    if initialization:
        search_metrics['rule_initialization_identity'] = (initialization['behavior_identity'] + ':' +
            initialization.get('compilation', 'pending'))
    if state is not None:
        for name in ('seed_adaptations', 'training_champion_snapshot',
                     'training_champion_adaptation', 'start_sources', 'formal_champion_snapshot',
                     'formal_champion_adaptation', 'formal_champion_publication',
                     'selection_feedback_incomplete'):
            if name in state:
                search_metrics[name] = state[name]
    cache_hit_keys = sorted({row['data_key'] for record in search.get('records', [])
                             for row in record.get('batches', [])
                             if row.get('cached') and isinstance(row.get('data_key'), str)})
    original = _read_utf8(destination / 'input.original.simc', description='原始输入副本')[1]
    effective = _read_utf8(destination / 'input.simc', description='任务输入副本')[1]
    record = dict(
        run_id=run_id, status=result.get('status', 'failed'), phase=result.get('phase', 'done'),
        burst=burst_record or None,
        rule_initialization=initialization,
        profile=profile, identity=profile.get('identity', {}),
        input_original=original, input_effective=effective,
        config=result.get('config') or (state or {}).get('config', {}),
        simulation_config=result.get('simulation_config') or (state or {}).get('simulation_config', {}),
        engines=result.get('engines') or (state or {}).get('engines', {}), condition_key=(state or {}).get('condition'),
        elapsed_seconds=float(result.get('elapsed_seconds', (state or {}).get('elapsed_seconds', 0)) or 0),
        candidate_key=candidate_key, candidate_data_key=candidate_data_key,
        reference_data_key=reference_data_key, controlled_data_key=controlled_data_key,
        batch_keys=sorted(batch_keys), cache_hit_keys=cache_hit_keys,
        completed_batches=result.get('completed_batches', (state or {}).get('completed_batches', 0)),
        reference_dps=native.get('dps'), reference_samples=native.get('samples'),
        reference_metric=native.get('metric'), reference_personal_dps=native.get('personal_dps'),
        reference_identity=native.get('identity', {}), reference_summary=native,
        search_dps=summary.get('dps'), search_samples=summary.get('samples'),
        search_reference_ratio=summary.get('reference_ratio'),
        search_candidate_count=search.get('candidate_count'),
        search_unique_candidates=search.get('unique_candidates'),
        search_rounds=search.get('rounds'), search_partial_round=search.get('partial_round'),
        search_stop_reason=search.get('stop_reason'), search_chains=search.get('chains', []),
        search_observability=(result.get('search_observability') or search.get('observability')),
        search_errors=search.get('errors', []), search_metrics=search_metrics,
        selected_candidate_key=(result.get('selected_candidate_key')
                                or (state or {}).get('selected_candidate_key') or locked_key),
        locked_candidate_key=locked_key,
        improvement=(result.get('improvement') or (state or {}).get('improvement')
                     or ('search_result' if summary else None)),
        independent_validation_complete=result.get('independent_validation_complete'),
        native_batch_starts=search.get('native_batch_starts',
                                       (state or {}).get('native_batch_starts', 0)),
        validation_summary=result.get('validation', {}),
        final_status=final.get('status'), final_scenarios=final.get('scenarios', {}),
        error=result.get('error'))
    write_records('runs', run_id, [record], schema=RUN_SCHEMA)
    return dict(run_id=run_id, status=record['status'], phase=record['phase'])


def _save_failure(destination: Path, result: dict, *, state=None) -> None:
    try:
        pointer = _store_run(destination, result, state=state)
    except Exception:
        run_id = json.loads((destination / 'profile.json').read_text(encoding='utf-8'))['run_id']
        pointer = dict(run_id=run_id, status=result.get('status', 'failed'),
                       phase=result.get('phase', 'done'), error=result.get('error'))
    _write_json(destination / 'result.json', pointer, atomic=True)


def _read_utf8(path: Path, *, description: str) -> tuple[bytes, str]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise TaskError(f"{description}不可读取: {path}") from error
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TaskError(f"{description}必须是 UTF-8 文本: {path}") from error


def _verify_task_inputs(destination: Path, saved: dict) -> tuple[bytes, bytes]:
    original, _ = _read_utf8(destination / "input.original.simc", description="原始输入副本")
    effective, _ = _read_utf8(destination / "input.simc", description="任务输入副本")
    expected_original = saved.get("input_original_sha256")
    expected_effective = saved.get("input_effective_sha256")
    if not expected_original or not expected_effective:
        raise TaskError("任务缺少完整输入散列，请创建新任务")
    if hashlib.sha256(original).hexdigest() != expected_original:
        raise TaskError("恢复任务的原始输入副本已变化，请创建新任务")
    if hashlib.sha256(effective).hexdigest() != expected_effective:
        raise TaskError("恢复任务的任务输入副本已变化，请创建新任务")
    return original, effective


def _effective_input_bytes(original_bytes: bytes, raw_text: str, simulation_config: dict) -> bytes:
    if simulation_config["enable_omnium_talents"]:
        return original_bytes
    return "".join(
        line for line in raw_text.splitlines(keepends=True)
        if not _OMNI_TALENTS_LINE.fullmatch(line)
    ).encode("utf-8")


def _prepare_task(input_path, output_root, *, resume=False, simulation_config=None):
    path = Path(input_path).resolve()
    simulation_config = simulation_config_for(simulation_config)
    if output_root is None:
        raise TaskError("任务输出目录尚未配置")
    destination = Path(output_root).resolve()
    if resume:
        if not destination.is_dir():
            raise TaskError(f"待恢复任务目录不存在: {destination}")
        saved = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
        original_bytes, _ = _verify_task_inputs(destination, saved)
        try:
            raw_text = original_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TaskError("原始输入副本必须是 UTF-8 文本") from error
        character = parse_character(raw_text)
        return destination / "input.simc", raw_text, character, destination
    if not path.is_file():
        raise TaskError(f"角色文件不存在: {path}")
    original_bytes, raw_text = _read_utf8(path, description="角色文件")
    character = parse_character(raw_text)
    effective_bytes = _effective_input_bytes(original_bytes, raw_text, simulation_config)
    if destination.exists():
        raise TaskError(f"任务输出目录已存在，不覆盖已有产物: {destination}")
    destination.mkdir(parents=True)
    (destination / "input.original.simc").write_bytes(original_bytes)
    (destination / "input.simc").write_bytes(effective_bytes)
    _write_json(destination / "profile.json", _profile(character, raw_text,
                                                         original_bytes=original_bytes,
                                                         effective_bytes=effective_bytes,
                                                         run_id=uuid.uuid4().hex))
    return path, raw_text, character, destination


def _run_single(input_path, destination, character, *, program, phase_ms, runtime, interval_ms=300,
                simulation_config, gse_program=None, gse_context=None, diagnostic_logging=False, use_burst=False):
    from engine import prepare_loop, reference, damage_statistics
    from sequence import select, evaluate
    from program import compile_program, from_action_blocks
    from gse_import import import_action_spell_ids, import_action_spell_names
    from result_store import write_batch
    from search import digest

    runtime.diagnostic_logging = diagnostic_logging
    run_id = json.loads((destination / 'profile.json').read_text(encoding='utf-8'))['run_id']

    if type(phase_ms) is not int or not 0 <= phase_ms < interval_ms:
        raise ValueError(f"起始相位必须在 0 至 {interval_ms - 1} 毫秒之间")
    if gse_program is not None:
        gse_context = dict(gse_context or {})
        if gse_context.get("click_ms") != interval_ms or gse_context.get("input_interval_ms", interval_ms) != interval_ms:
            raise ValueError("GSE 点击间隔必须与模拟按键间隔一致")
        gse_context["input_interval_ms"] = interval_ms
        gse_context.setdefault("pet_ready", True)
        gse_context.setdefault("enemy_target_ready", True)
    native = reference(destination / "input.simc", destination / "reference", character, runtime=runtime,
                       simulation_config=simulation_config,
                       import_spell_ids=(import_action_spell_ids(gse_program)
                                         if gse_program is not None else ()),
                       import_spell_names=(import_action_spell_names(gse_program)
                                           if gse_program is not None else ()))
    reference_report_path = destination / 'reference' / 'native.json'
    reference_valid = reference_stored = False
    try:
        reference_report = json.loads(reference_report_path.read_text(encoding='utf-8'))
        reference_key = digest(dict(run_id=run_id, purpose='reference',
                                    input_sha256=json.loads((destination / 'profile.json').read_text(encoding='utf-8'))['input_effective_sha256'],
                                    simulation_config=simulation_config))
        reference_damage = damage_statistics(reference_report, character)
        reference_valid = True
        write_batch(reference_key, dict(
            batch_key=reference_key, run_id=run_id, purpose='reference',
            seed=20260912, requested_iterations=100, samples=native['samples'],
            dps=native['dps'], variance=reference_damage.get('variance'), report=reference_report),
                    diagnostic_logging=diagnostic_logging, runtime=runtime)
        reference_stored = True
    finally:
        _discard_native_exchange(destination / 'reference', keep_valid=reference_valid and not reference_stored)
    character = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
    _write_json(
        destination / 'profile.json',
        _profile(character, character.raw_text,
                 original_bytes=(destination / 'input.original.simc').read_bytes(),
                 effective_bytes=(destination / 'input.simc').read_bytes(), run_id=run_id),
    )
    definition = None
    effective_character = character
    if use_burst:
        from burst import load
        definition = load(native['identity']['spec_id'])
        effective_character = parse_character(_read_utf8(destination / 'input.simc', description='任务输入副本')[1])
    _, capabilities, context = prepare_loop(native, effective_character, destination, runtime,
                                            definition=definition, interval_ms=interval_ms)
    if not diagnostic_logging:
        native.pop('action_sequence', None)
        native.pop('precombat_sequence', None)
    burst_result = None
    burst_candidate = None
    input_sources = None
    times = list(range(phase_ms, 180000, interval_ms))
    if use_burst:
        from burst import combined_inputs
        burst_candidate = context['candidate']
        times, input_sources = combined_inputs(times, definition, interval_ms)
        burst_result = dict(context, interval_ms=interval_ms)
    candidate = compile_program(gse_program or from_action_blocks(select(capabilities, program)),
                                destination / 'export', identity=native['identity'], runtime=runtime,
                                capabilities=capabilities, context=gse_context)
    burst_options = (dict(input_sources=input_sources, burst_candidate=burst_candidate)
                     if burst_candidate is not None else {})
    controlled = evaluate(destination / "input.simc", candidate, destination / "controlled", character=character,
                          input_times=times, runtime=runtime,
                          simulation_config=simulation_config, **burst_options)
    controlled_candidate_key = candidate.get('identity') or digest(candidate.get('program') or {})
    controlled_key = digest(dict(run_id=run_id, purpose='controlled',
                                 candidate_key=controlled_candidate_key, phase_ms=phase_ms,
                                 interval_ms=interval_ms,
                                 input_sha256=json.loads((destination / 'profile.json').read_text(encoding='utf-8'))['input_effective_sha256'],
                                 simulation_config=simulation_config,
                                 **(dict(burst_definition_id=burst_result['definition_id'],
                                         burst_program=burst_candidate['compiled_program'],
                                         burst_plan=burst_result['plan'], input_sources=input_sources)
                                    if burst_result else {})))
    controlled_damage = damage_statistics(controlled['report'], character)
    controlled_stored = False
    try:
        write_batch(controlled_key, dict(
            batch_key=controlled_key, run_id=run_id, purpose='controlled',
            candidate_key=controlled_candidate_key, seed=20260912, requested_iterations=100,
            samples=controlled['summary']['samples'], dps=controlled['summary']['dps'],
            variance=controlled_damage.get('variance'), report=controlled['report'],
            times=controlled['input_times'], phase_ms=phase_ms,
            reset_events=controlled.get('reset_events', [])), diagnostic_logging=diagnostic_logging, runtime=runtime)
        controlled_stored = True
    finally:
        _discard_native_exchange(destination / 'controlled',
                                 keep_valid=not controlled_stored and isinstance(controlled.get('report'), dict))
    if diagnostic_logging:
        from result_store import write_traces
        write_traces(controlled_key, run_id, controlled['trace'], batch_key=controlled_key)
    else:
        from engine import discard_diagnostic_files
        discard_diagnostic_files(destination / 'reference')
        discard_diagnostic_files(destination / 'controlled')
    controlled['data_key'] = controlled_key
    candidate["simulation"] = "passed_native_model"
    if burst_candidate is not None:
        burst_candidate['simulation'] = 'passed_native_model'
    result = {
        "status": "completed" if gse_program is not None else "offline_ready",
        "phase": "done" if gse_program is not None else "single",
        "character": character,
        "output_root": destination,
        "profile": json.loads((destination / "profile.json").read_text(encoding="utf-8")),
        "capabilities": capabilities,
        "native_reference": native,
        "reference_data_key": reference_key,
        "candidate": candidate,
        "controlled_simulation": controlled,
        "controlled_data_key": controlled_key,
        "simulation_config": simulation_config,
        "engines": {mode: entry[1] for mode, entry in runtime.identities.items()},
    }
    if burst_result is not None:
        result['burst'] = burst_result
    return result


def _rule_hashes(*, relative_to=None):
    """Hash all task rules; training may use portable keys without changing task identity."""
    from codec import SOURCE, LUA
    sources = [*Path(__file__).parent.glob('*.py'),
               *Path(__file__).with_name('compatibility').glob('*.json'),
               Path(__file__).with_name('codec.lua'), LUA, *sorted(SOURCE.rglob('*.lua'))]
    if relative_to is None:
        return {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    root = Path(relative_to).resolve()
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources}


def _seed_programs(starts, snapshot, *, character, targets, engines,
                   capabilities, runtime):
    """Append selected programs after role mapping and shared export checks."""
    if not snapshot:
        return starts, []
    from program import canonicalize_search_program
    from seed_training import filter_search_program
    from codec import load_targeting, prepare_block, prepare_castsequence

    def check_program(program, target_masks):
        for node in program['nodes']:
            if node['kind'] == 'Action':
                commands = node['commands']
                if (len(commands) == 1 and commands[0].get('kind') == 'castsequence'):
                    prepare_castsequence(commands[0])
                else:
                    prepare_block(commands, target_masks)
            elif node['kind'] == 'Loop':
                for child in node['body']:
                    prepare_block(child['commands'], target_masks)
            elif node['kind'] != 'Pause':
                raise ValueError('搜索节点无法导出')

    def check_original_limits(program):
        # 上限只看原结构，不把静态不可用动作映射成当前可执行按钮。
        if not isinstance(program, list):
            return  # 其余原结构错误仍由共享解析器拒绝。
        blocks = clicks = len(capabilities.get('precombat_actions', []))
        for segment in program:
            if isinstance(segment, list):
                blocks += 1
                clicks += 1
            elif isinstance(segment, dict):
                kind = segment.get('kind')
                if kind == 'Loop' and isinstance(segment.get('blocks'), list):
                    blocks += len(segment['blocks'])
                    count = segment.get('count')
                    if type(count) is int and count > 0:
                        clicks += count * len(segment['blocks'])
                elif kind == 'WaitClicks':
                    count = segment.get('clicks')
                    if type(count) is int and count > 0:
                        clicks += count
                elif kind == 'CastSequence':
                    clicks += 1
        if blocks > 128:
            raise ValueError('原搜索程序展开超过 128 个顶层动作块')
        if clicks > 4096:
            raise ValueError('原搜索程序展开超过 4096 次按键')

    identities = set()
    for program in starts:
        try:
            identities.add(canonicalize_search_program(program, capabilities)['identity'])
        except (TypeError, ValueError, KeyError):
            continue

    # 原生静态资格不读取冷却、资源或是否执行；同名当前可用按钮优先。
    known = {action['simc_action']: action for action in capabilities['actions']}
    available = {variant['simc_action'] for action in capabilities['actions']
                 for variant in action.get('variants', [action])}
    excluded = set()
    for row in capabilities.get('sources', []):
        if (row.get('catalogue') != 'apl' or row.get('status') != 'native_unavailable'
                or row.get('action_initialized') is not True or row.get('available') is not False):
            continue
        name = row.get('signature', '').split(',', 1)[0]
        if not name or name in available:
            continue
        excluded.add(name)
        if row.get('data_valid') is True and type(row.get('data_id')) is int and row['data_id'] > 0:
            known[name] = dict(kind='spell', simc_action=name, spell_id=row['data_id'],
                              name=row.get('name') or name, gcd_ms=row.get('gcd_ms', 0))
    validation_capabilities = dict(capabilities, actions=list(known.values()))
    target_masks = None
    added, decisions = [], []
    for row in snapshot:
        if len(added) >= 4:
            break
        if (not isinstance(row, dict) or row.get('class_name') != character.class_name
                or row.get('spec') != character.spec or row.get('targets') != targets):
            continue
        row_engines = row.get('engines')
        if isinstance(row_engines, str):
            try:
                row_engines = json.loads(row_engines)
            except ValueError:
                continue
        if row_engines != engines:
            continue
        program = row.get('program')
        if isinstance(program, str):
            try:
                program = json.loads(program)
            except ValueError:
                continue
        decision = dict(candidate_id=row.get('candidate_id'), original_program=program,
                        derived_program=None, removed=[], status='rejected', reason='')
        decisions.append(decision)
        try:
            check_original_limits(program)
            derived, removed = filter_search_program(program, excluded, validation_capabilities)
            decision.update(derived_program=derived, removed=[dict(item,
                reason='当前原生动作已初始化但种族、天赋或等级资格不可用') for item in removed])
            canonical = canonicalize_search_program(derived, capabilities)
        except (TypeError, ValueError, KeyError) as error:
            decision['reason'] = str(error)
            continue
        decision['behavior_identity'] = canonical['identity']
        if canonical['identity'] in identities:
            decision.update(status='duplicate', reason='适配后与已有起点行为相同')
            continue
        if target_masks is None:
            target_masks = load_targeting(runtime=runtime)['target_masks']
        try:
            check_program(canonical['program'], target_masks)
        except (TypeError, ValueError, KeyError) as error:
            decision['reason'] = str(error)
            continue
        # The normal optimizer compiles and identity-checks this start during its
        # first score, avoiding a duplicate Lua compiler launch at task startup.
        identities.add(canonical['identity'])
        decision['status'] = 'accepted'
        added.append(derived)
    return starts + added, decisions


def _validate_formal_source(record, state, character, *, run=None, candidate=None, verify_reports=True):
    """One source contract for live publication and immutable published evidence."""
    from result_store import one, read_many, report_locations, InvalidRecordError
    from seed_training import decode, search_program
    from program import canonicalize_search_program, canonical_behavior_key
    from search import digest, _validate_saved_batch, _score, input_times, STATS_VERSION, DEFAULT_SCENARIOS
    from sequence import compiled_identity
    binding = record['binding']
    if (digest(binding) != record['condition_key']
            or binding['input_effective_sha256'] != state['input_effective_sha256']
            or binding['class_name'] != character.class_name or binding['spec'] != character.spec
            or binding['spec_id'] != character.spec_id
            or binding['target_count'] != state['simulation_config']['target_count']):
        raise InvalidRecordError('正式冠军条件与当前冻结角色不符')
    if run is not None:
        profile = decode(run['profile']) or {}
        identity = profile.get('identity') or {}
        evidence = dict(status=run['status'], input_effective_sha256=profile.get('input_effective_sha256'),
                        class_name=identity.get('class'), spec=identity.get('spec'), spec_id=identity.get('spec_id'))
        if (run['run_id'] != record['source_run_id'] or run['condition_key'] != record['source_condition_key']
                or run['selected_candidate_key'] != record['behavior_identity']
                or run['locked_candidate_key'] != record['behavior_identity']
                or run['candidate_key'] != record['source_candidate_key']
                or run['candidate_data_key'] != record['source_candidate_data_key']
                or run['search_dps'] != record['score'] or run['search_samples'] != record['samples']
                or not set(record['batch_keys']) <= set(run['batch_keys'] or [])):
            raise InvalidRecordError('正式冠军的完整正式来源缺失或不符')
    else:
        evidence = record.get('source_evidence') or {}
    if (evidence.get('status') not in ('completed', 'cancelled')
            or any(evidence.get(key) != binding[key] for key in
                   ('input_effective_sha256', 'class_name', 'spec', 'spec_id'))
            or record['source_condition_key'] != binding['condition']
            or binding['condition'] != state['condition']):
        raise InvalidRecordError('正式冠军的来源状态、角色或条件不符')
    if candidate is None:
        candidate = one('candidates', 'candidate_data_key', record['source_candidate_data_key'],
            columns=['candidate_data_key', 'run_id', 'candidate_key', 'program', 'simulation', 'export_text', 'source'])
    if (candidate is None or candidate['run_id'] != record['source_run_id']
            or candidate['candidate_key'] != record['source_candidate_key']
            or candidate['source'] != 'search' or candidate['simulation'] != 'passed_native_model'
            or not candidate['export_text']
            or canonicalize_search_program(search_program(decode(candidate['program'])), state['capabilities'])['identity']
               != record['behavior_identity']
            or canonicalize_search_program(record['program'], state['capabilities'])['identity'] != record['behavior_identity']):
        raise InvalidRecordError('正式冠军程序、导出或正式来源行为不符')
    if not verify_reports:
        import math
        if (type(record.get('score')) not in (int, float) or not math.isfinite(record['score'])
                or type(record.get('samples')) is not int or record['samples'] < 1
                or not isinstance(record.get('batch_keys'), list) or not record['batch_keys']
                or any(not isinstance(key, str) or not key for key in record['batch_keys'])
                or len(set(record['batch_keys'])) != len(record['batch_keys'])):
            raise InvalidRecordError('正式冠军成绩或原报告引用格式不符')
        # Published evidence was verified before CAS; inheritance always scores the program anew.
        return evidence
    wanted = set(record['batch_keys'])
    locations = report_locations(record['batch_keys'])
    groups = list(dict.fromkeys(locations.get(key) or key for key in record['batch_keys']))
    batches = {row['batch_key']: row for row in read_many('batches', groups) if row['batch_key'] in wanted}
    if set(batches) != wanted or not wanted:
        raise InvalidRecordError('正式冠军原报告缺失')
    scored = []
    config = state['config']
    for row in batches.values():
        purpose, index, scenario = row['purpose'], row['batch_index'], row['scenario']
        if purpose not in ('search', 'validation') or type(index) is not int or index < 0:
            raise InvalidRecordError('正式冠军原报告批次身份不符')
        if purpose == 'search':
            if index >= len(config['batch_targets']) or scenario != 'nominal':
                raise InvalidRecordError('正式冠军评分批次不符')
            iterations = config['batch_targets'][index] - (config['batch_targets'][index - 1] if index else 0)
        else:
            if index >= config['validation_batches'] or scenario not in DEFAULT_SCENARIOS:
                raise InvalidRecordError('正式冠军晋级批次不符')
            iterations = config['iterations']
        seed = config['random_seed'] + (100000 if purpose == 'validation' else 0) + index + DEFAULT_SCENARIOS.index(scenario) * 1000
        times = input_times(scenario, seed + 500000, config['input_interval_ms'])
        form = decode(row['program_identity'])
        request = dict(condition=binding['condition'], program=form, behavior_identity=canonical_behavior_key(form),
            purpose=purpose, seed=seed, input_seed=seed + 500000, iterations=iterations,
            times=times, stats=STATS_VERSION, trace=row['trace'], reset_events=[list(item) for item in config['reset_events']])
        if row.get('rule_observations') is not None:
            from rule_diagnostics import observation_request, VERSION as RULE_DIAGNOSTICS_VERSION
            expected = dict(version=RULE_DIAGNOSTICS_VERSION, request=observation_request(state['rule_initialization']))
            if decode(row['rule_observations']) != expected:
                raise InvalidRecordError('正式冠军原报告规则观察请求不符')
            request['rule_observations'] = expected
        if state.get('burst'):
            from burst import combined_inputs
            context = state['burst']
            request['times'], sources = combined_inputs(times, context, config['input_interval_ms'])
            request['burst'] = dict(definition_id=context['definition_id'], program=compiled_identity(context['candidate']),
                                    plan=context['plan'], interval_ms=config['input_interval_ms'], sources=sources)
        receipt = dict(request=request, dps=row['dps'], samples=row['samples'], variance=row['variance'])
        if digest(request) != row['batch_key']:
            raise InvalidRecordError('正式冠军原报告请求身份不符')
        _validate_saved_batch(row, row['batch_key'], receipt, character, index, scenario, state['simulation_config'])
        if purpose == 'search' and row['candidate_key'] == record['behavior_identity']:
            scored.append(row)
    scored.sort(key=lambda row: row['batch_index'])
    if (not scored or [row['batch_index'] for row in scored] != list(range(len(scored)))
            or _score(scored) != record['score'] or sum(row['samples'] for row in scored) != record['samples']):
        raise InvalidRecordError('正式冠军分数或样本与原报告不符')
    return evidence


def _freeze_formal_champion(state, character, native, capabilities):
    from result_store import read_search_champion
    from search import digest
    binding = dict(condition=state['condition'], input_effective_sha256=state['input_effective_sha256'],
                   class_name=character.class_name, spec=character.spec,
                   spec_id=native['identity']['spec_id'], target_count=state['simulation_config']['target_count'])
    key = digest(binding)
    record = read_search_champion(key)
    snapshot = dict(status='absent', condition_key=key, binding=binding, version=0,
                    legacy_import_status='not_imported', target_count=binding['target_count'])
    if record is None:
        return snapshot
    if record['binding'] != binding:
        from result_store import InvalidRecordError
        raise InvalidRecordError('正式冠军条件绑定不符')
    checked = replace(character, spec_id=native['identity']['spec_id'], race=native['identity']['race'])
    _validate_formal_source(record, dict(state, capabilities=capabilities), checked, verify_reports=False)
    snapshot.update(record, status='selected', legacy_import_status='not_imported',
                    target_count=binding['target_count'])
    return snapshot


def _historical_formal_champion(state, character, native, capabilities, snapshot):
    """One explicit bounded management pass; never a routine historical scan."""
    import math
    from result_store import read_many, report_locations
    from seed_training import decode, search_program
    from search import digest, _validate_saved_batch, _score, STATS_VERSION, input_times, config_for
    from program import canonicalize_search_program
    if snapshot['status'] != 'absent':
        raise TaskError('已有正式冠军，历史导入不能覆盖')
    scope = state['formal_history_scope']
    columns = ['run_id', 'status', 'profile', 'config', 'simulation_config', 'engines', 'burst',
               'condition_key', 'candidate_key', 'candidate_data_key', 'selected_candidate_key',
               'locked_candidate_key', 'search_dps', 'search_samples', 'batch_keys']
    runs = read_many('runs', scope, columns=columns)
    if len(runs) != len(scope) or {run['run_id'] for run in runs} != set(scope):
        raise TaskError('明确历史来源缺失或不唯一')
    keys = [run['candidate_data_key'] for run in runs if run['candidate_data_key']]
    candidates = read_many('candidates', keys,
        columns=['run_id', 'candidate_key', 'candidate_data_key', 'program', 'simulation', 'export_text', 'source'])
    by_key = {row['candidate_data_key']: row for row in candidates}
    if len(by_key) != len(candidates):
        raise TaskError('明确历史候选身份不唯一')
    eligible = []
    for run in runs:
        profile, config = decode(run['profile']), decode(run['config'])
        candidate = by_key.get(run['candidate_data_key'])
        identity = (profile or {}).get('identity', {})
        config_without_logging = lambda value: {key: item for key, item in value.items()
            if key not in ('search_observability', 'diagnostics', 'diagnostic_logging')}
        source_burst, current_burst = decode(run['burst']) or {}, state.get('burst') or {}
        source_context = {key: item for key, item in source_burst.items()
                          if key not in ('candidate_key', 'candidate_data_key')}
        current_context = {key: item for key, item in current_burst.items() if key != 'candidate'}
        if (run['status'] != 'completed' or not isinstance(profile, dict) or not isinstance(config, dict)
                or profile.get('input_effective_sha256') != state['input_effective_sha256']
                or identity.get('class') != character.class_name or identity.get('spec') != character.spec
                or identity.get('spec_id') != native['identity']['spec_id']
                or decode(run['engines']) != state['engines']
                or decode(run['simulation_config']) != state['simulation_config']
                or set(config_without_logging(config)) != set(config_without_logging(state['config']))
                or config_without_logging(config_for(config)) != config_without_logging(state['config'])
                or source_context != current_context or not run['condition_key']
                or run['selected_candidate_key'] != run['locked_candidate_key']
                or not run['selected_candidate_key'] or candidate is None
                or candidate['run_id'] != run['run_id'] or candidate['candidate_key'] != run['candidate_key']
                or candidate['simulation'] != 'passed_native_model' or not candidate['export_text']
                or candidate['source'] != 'search'
                or type(run['search_dps']) not in (int, float) or not math.isfinite(run['search_dps'])
                or run['search_dps'] < 0 or type(run['search_samples']) is not int or run['search_samples'] < 1):
            raise TaskError('明确历史来源的角色、完整条件或正式成果无法核验: ' + run['run_id'])
        program = search_program(decode(candidate['program']))
        canonical = canonicalize_search_program(program, capabilities)
        if canonical['identity'] != run['selected_candidate_key']:
            raise TaskError('明确历史候选的程序与行为身份不符')
        eligible.append((run, program, canonical))
    run, program, canonical = min(eligible, key=lambda item:
        (-item[0]['search_dps'], item[2]['identity'], item[0]['run_id']))
    # Verify the selected old score's complete reports, but never import its cache.
    locations = report_locations(run['batch_keys'])
    wanted = set(run['batch_keys'])
    groups = list(dict.fromkeys(locations.get(key) or key for key in run['batch_keys']))
    batches = [row for row in read_many('batches', groups,
               filters={'candidate_key': canonical['identity'], 'purpose': 'search'})
               if row['batch_key'] in wanted]
    batches.sort(key=lambda row: row['batch_index'])
    scored = []
    config = state['config']
    for index, row in enumerate(batches):
        if index >= len(config['batch_targets']) or row['batch_index'] != index:
            raise TaskError('明确历史评分批次编号不符')
        seed = config['random_seed'] + index
        times = input_times('nominal', seed + 500000, config['input_interval_ms'])
        if state.get('burst'):
            from burst import combined_inputs
            times, _ = combined_inputs(times, state['burst'], config['input_interval_ms'])
        iterations = config['batch_targets'][index] - (config['batch_targets'][index - 1] if index else 0)
        request = dict(condition=run['condition_key'], program=canonical['form'], behavior_identity=canonical['identity'],
            purpose='search', seed=seed, input_seed=seed + 500000, iterations=iterations, times=times,
            stats=STATS_VERSION, trace=row['trace'], reset_events=[list(item) for item in config['reset_events']])
        receipt = dict(request=request, dps=row['dps'], samples=row['samples'], variance=row['variance'])
        _validate_saved_batch(row, row['batch_key'], receipt, character, index, 'nominal', state['simulation_config'])
        scored.append(receipt)
    if not scored or _score(scored) != run['search_dps'] or sum(row['samples'] for row in scored) != run['search_samples']:
        raise TaskError('明确历史评分报告或样本不完整')
    return dict(snapshot, status='selected', legacy_import_status='candidate_frozen', source_scope=scope,
                program=program, behavior_identity=canonical['identity'], source_run_id=run['run_id'],
                source_candidate_key=run['candidate_key'], source_candidate_data_key=run['candidate_data_key'],
                source_condition_key=run['condition_key'], score=run['search_dps'], samples=run['search_samples'])


def import_formal_champion(input_path, output_root, source_run_ids, *, search_config=None,
                           simulation_config=None, use_burst=False):
    """Explicit internal management entry; the supplied range is not all historical results."""
    if (not isinstance(source_run_ids, (list, tuple)) or not source_run_ids
            or any(not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key) for key in source_run_ids)):
        raise TaskError('历史导入需要明确有限的正式run_id范围')
    scope = list(dict.fromkeys(source_run_ids))
    if len(scope) > 64:
        raise TaskError('历史导入最多64个唯一正式来源，请缩小明确范围')
    from seed_activity import foreground_search
    with foreground_search():
        return _run_task(input_path, output_root, search_config=search_config,
            simulation_config=simulation_config, use_burst=use_burst, _formal_source_run_ids=scope)


def _prepare_formal_publication(store, result=None):
    """Freeze an intent only for a fully archived, export-verified winner."""
    import math
    from program import canonicalize_search_program
    from sequence import compiled_identity
    from search import digest
    state = store.state
    snapshot = state.get('formal_champion_snapshot')
    if snapshot is None:
        return
    key = state.get('locked_candidate_key')
    winner = next((row for row in state.get('archive', []) if row['key'] == key), None)
    if winner is None:
        state['formal_champion_publication'] = dict(status='not_eligible', reason='没有完整正式赢家')
        return
    canonical = canonicalize_search_program(winner['program'], state['capabilities'])
    candidate = winner.get('candidate') or {}
    if (canonical['identity'] != key or canonical['form'] != compiled_identity(candidate)
            or candidate.get('simulation') != 'passed_native_model' or not candidate.get('text')
            or not winner.get('batches') or not math.isfinite(winner['score'])
            or any(row.get('status') != 'success' or not row.get('data_key')
                   or row.get('samples', 0) < 1 for row in winner['batches'])):
        state['formal_champion_publication'] = dict(status='not_eligible', reason='正式赢家证据不完整')
        return
    evidence = []
    previous = state.get('formal_champion_last_published')
    baseline = (previous['behavior_identity'] if previous else
                snapshot.get('behavior_identity') if snapshot['status'] == 'selected' else None)
    if baseline and key != baseline:
        current = winner
        visited = set()
        while current['key'] != baseline:
            predecessor = current.get('global_predecessor_key')
            comparison = current.get('global_validation') or current.get('validation')
            ci = (comparison or {}).get('comparison', {}).get('ci95')
            if (current['key'] in visited or not predecessor or not ci or ci[0] <= 0
                    or len(comparison.get('candidate', [])) != state['config']['validation_batches']
                    or len(comparison.get('control', [])) != state['config']['validation_batches']):
                state['formal_champion_publication'] = dict(status='not_eligible', reason='缺少可信冠军晋级链')
                return
            visited.add(current['key'])
            evidence.append(dict(candidate_key=current['key'], predecessor_key=predecessor,
                                 comparison=comparison['comparison'],
                                 batch_keys=[row['data_key'] for side in ('candidate', 'control')
                                             for row in comparison[side]]))
            current = next((row for row in state['archive'] if row['key'] == predecessor), None)
            if current is None:
                state['formal_champion_publication'] = dict(status='not_eligible', reason='冠军晋级前序缺失')
                return
    # Persisted export identity and search behavior identity are intentionally distinct.
    source_key = candidate.get('identity') or digest(candidate['program'])
    record = dict(condition_key=snapshot['condition_key'], binding=snapshot['binding'], version=0,
                  program=winner['program'], behavior_identity=key, source_run_id=state['run_id'],
                  source_candidate_key=source_key,
                  source_candidate_data_key=digest(dict(run_id=state['run_id'], candidate_key=source_key)),
                  source_condition_key=state['condition'], score=winner['score'],
                  samples=sum(row['samples'] for row in winner['batches']),
                  batch_keys=list(dict.fromkeys([row['data_key'] for row in winner['batches']] +
                      [batch for item in evidence for batch in item['batch_keys']])), promotion_evidence=evidence)
    incumbent = previous or (dict(version=snapshot['version'], source_run_id=snapshot['source_run_id'],
        behavior_identity=snapshot['behavior_identity'])
        if snapshot['status'] == 'selected' and snapshot['version'] > 0 else None)
    fields = {name: result[name] for name in ('status', 'phase', 'elapsed_seconds', 'completed_batches',
        'final', 'independent_validation_complete', 'improvement') if result is not None and name in result}
    if result is not None:
        fields['search'] = {name: value for name, value in result['search'].items()
                            if name in ('candidate_count', 'unique_candidates', 'rounds', 'partial_round',
                                        'stop_reason', 'no_improvement_round_limit')}
    state['formal_champion_publication_intent'] = dict(record=record,
        expected_version=incumbent['version'] if incumbent else 0, expected_incumbent=incumbent, result_fields=fields)
    state['formal_champion_publication'] = dict(status='pending', source_run_id=state['run_id'],
                                              reason='正式结果保存后发布')


def _formal_publication_metadata(value):
    if (not isinstance(value, dict) or value.get('status') not in
            ('pending', 'published', 'unchanged', 'conflict', 'not_eligible')):
        raise ValueError('正式冠军发布状态格式无效')
    return value


def _restore_formal_result(store, destination, character):
    """Finish durable complete archives before any resume early return; never score."""
    from result_store import one, InvalidRecordError
    state = store.state
    intent = state.get('formal_champion_publication_intent')
    if not intent or state.get('formal_champion_publication', {}).get('status') != 'pending':
        return
    record = intent['record']
    run = one('runs', 'run_id', record['source_run_id'], columns=['run_id', 'status', 'profile',
        'condition_key', 'selected_candidate_key', 'locked_candidate_key', 'candidate_key',
        'candidate_data_key', 'search_dps', 'search_samples', 'batch_keys'])
    try:
        if run is None:
            raise InvalidRecordError('完整正式结果缺失')
        _validate_formal_source(record, state, character, run=run)
    except (InvalidRecordError, ValueError, KeyError, TypeError):
        winner = next((row for row in state.get('archive', []) if row['key'] == record['behavior_identity']), None)
        fields = intent.get('result_fields') or {}
        if (winner is None or fields.get('status') not in ('completed', 'cancelled')
                or winner['score'] != record['score']
                or sum(row['samples'] for row in winner['batches']) != record['samples']):
            raise TaskError('正式成果无法从完整归档补保存')
        from program import canonicalize_search_program
        from sequence import compiled_identity
        from search import digest
        compiled = winner.get('candidate') or {}
        canonical = canonicalize_search_program(winner['program'], state['capabilities'])
        if (canonical['identity'] != record['behavior_identity'] or compiled_identity(compiled) != canonical['form']
                or (compiled.get('identity') or digest(compiled['program'])) != record['source_candidate_key']
                or state['run_id'] != record['source_run_id']):
            raise TaskError('正式成果归档程序或产物身份不符')
        # Verify the complete archive and original reports before filling the missing artifact/result.
        _validate_formal_source(dict(record, source_evidence=dict(status=fields['status'],
            **{key: record['binding'][key] for key in ('input_effective_sha256', 'class_name', 'spec', 'spec_id')})),
            state, character, candidate=dict(run_id=state['run_id'], candidate_key=record['source_candidate_key'],
                program=compiled['program'], source=compiled.get('source', 'search'),
                simulation=compiled.get('simulation'), export_text=compiled.get('text')))
        result = dict(fields, locked_candidate_key=record['behavior_identity'], selected_candidate_key=record['behavior_identity'])
        result['search'] = dict(fields.get('search') or {}, records=state['archive'], chains=state['chains'], errors=state.get('errors', []))
        result['validation'] = dict(dataset='validation', records=[row[name] for row in state['archive']
            for name in ('validation', 'global_validation') if name in row])
        result['elapsed_seconds'] = max(fields.get('elapsed_seconds', 0), state.get('elapsed_seconds', 0))
        pointer = _store_run(destination, result, state=state)
        _write_json(destination / 'result.json', pointer, atomic=True)
    fields = intent.get('result_fields') or {}
    if fields.get('status') in ('completed', 'cancelled'):
        state.update(status=fields['status'], phase=fields['phase'])
        state.pop('error', None)
        store.save()  # A verified saved result also repairs a stale failed checkpoint without resetting elapsed time.
    if not (destination / 'result.json').is_file():
        _write_json(destination / 'result.json', dict(run_id=record['source_run_id'], status=state['status'], phase=state['phase']), atomic=True)


def _publish_formal_champion(store, destination):
    """Publication errors retain the reliable result and its retryable intent."""
    from result_store import one, publish_search_champion
    state = store.state
    intent = state.get('formal_champion_publication_intent')
    if not intent:
        return
    try:
        record = intent['record']
        native = state['native']['identity']
        character = replace(parse_character((destination / 'input.simc').read_text(encoding='utf-8-sig')),
                            spec_id=native['spec_id'], race=native['race'])
        if state.get('formal_champion_publication', {}).get('status') == 'pending':
            run = one('runs', 'run_id', record['source_run_id'], columns=['run_id', 'status', 'profile',
        'condition_key', 'selected_candidate_key', 'locked_candidate_key', 'candidate_key',
        'candidate_data_key', 'search_dps', 'search_samples', 'batch_keys'])
            if run is None:
                raise TaskError('完整正式结果尚未可靠保存，不能发布冠军')
            record['source_evidence'] = _validate_formal_source(record, state, character, run=run)
            state['formal_champion_publication'] = publish_search_champion(record, intent['expected_version'],
                expected_incumbent=intent.get('expected_incumbent'))
            publication = state['formal_champion_publication']
            if publication['status'] == 'published':
                state['formal_champion_last_published'] = dict(version=publication['version'],
                    source_run_id=publication['source_run_id'], behavior_identity=record['behavior_identity'])
    except Exception as error:
        state['formal_champion_publication'] = dict(status='pending', source_run_id=state['run_id'],
                                                  reason='结果已保存，正式冠军尚未更新', error=str(error))
    try:
        store.save()
        pointer_path = destination / 'result.json'
        pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
        pointer['formal_champion_publication'] = state['formal_champion_publication']
        _write_json(pointer_path, pointer, atomic=True)
    except Exception as error:
        state['formal_champion_publication'] = dict(status='pending', source_run_id=state['run_id'],
            reason='结果已保存，正式冠军发布状态尚待确认', error=str(error))
        try:
            store.save()
        except Exception:
            pass  # The already durable pending intent is enough for an idempotent retry.


def _run_optimize(destination, character, *, config, runtime, simulation_config, use_burst=False,
                  burst_identity=None, formal_source_run_ids=None, rule_snapshot=None, rule_step=None):
    from engine import identity, prepare_loop, reference, damage_statistics, COMMON
    from rule_config import load
    rule_snapshot = rule_snapshot or load()
    from search import TaskStore, _export_search_observability, digest, initial_programs, optimize
    store = TaskStore(destination)
    state = store.state
    try:
        run_id = json.loads((destination / 'profile.json').read_text(encoding='utf-8')).get('run_id')
    except BaseException:
        store.close()
        raise
    if not isinstance(run_id, str) or not run_id:
        store.close()
        raise TaskError('任务缺少结果中心身份，请创建新任务')
    if state.get('run_id') not in (None, run_id):
        store.close()
        raise TaskError('任务结果中心身份与检查点不符，请创建新任务')
    state['run_id'] = run_id
    if formal_source_run_ids is not None:
        state['formal_history_scope'] = formal_source_run_ids
    runtime.diagnostic_logging = config['diagnostic_logging']
    def reservation(key, allowance):
        with store.lock:
            inflight = state.setdefault('inflight', {})
            if allowance is None:
                inflight.pop(key,None)
            else:
                inflight[key] = dict(start=runtime.elapsed_seconds,allowance=allowance)
            state['elapsed_seconds'] = runtime.elapsed_seconds
            store.save_runtime()
    runtime.reservation = reservation
    try:
        original_bytes, _ = _read_utf8(destination / "input.original.simc", description="原始输入副本")
        effective_bytes, _ = _read_utf8(destination / "input.simc", description="任务输入副本")
        input_original_sha256 = hashlib.sha256(original_bytes).hexdigest()
        input_effective_sha256 = hashlib.sha256(effective_bytes).hexdigest()
        if (state.get("input_original_sha256") not in (None, input_original_sha256)
                or state.get("input_effective_sha256") not in (None, input_effective_sha256)):
            raise TaskError("恢复任务的输入副本已变化，请创建新任务")
        state.update(input_original_sha256=input_original_sha256,
                     input_effective_sha256=input_effective_sha256)
        state.setdefault('phase','initialize')
        with store.active(runtime):
            definition = None
            if use_burst:
                from burst import load, select_definition
                frozen = burst_identity or (dict(spec_id=state['burst_spec_id'],
                            definition_id=state['burst_definition_id']) if state.get('burst_definition_id') else None)
                if frozen:
                    definition = load(frozen['spec_id'])
                    if definition['definition_id'] != frozen['definition_id']:
                        raise TaskError('任务的爆发定义已变化，请创建新任务')
                    if state.get('burst_definition_id') and (state['burst_spec_id'] != frozen['spec_id'] or
                            state['burst_definition_id'] != frozen['definition_id']):
                        raise TaskError('任务的冻结爆发身份不符，请创建新任务')
                else:
                    definition = select_definition(parse_character(effective_bytes.decode('utf-8')))
                from program import BEHAVIOR_IDENTITY_VERSION
                state.update(use_burst=True, burst_definition_id=definition['definition_id'],
                             burst_spec_id=definition['spec_id'],
                             behavior_identity_version=BEHAVIOR_IDENTITY_VERSION)
                store.save()
            # 恢复核验先于任何模拟；程序及规则变化必须新建任务。
            identities = {mode: identity(mode, runtime)[1] for mode in ('baseline', 'controlled')}
            rules = _rule_hashes()
            import cbor2
            from importlib.metadata import version
            condition_config = {key: value for key, value in config.items()
                                if key not in ('search_observability', 'diagnostics', 'diagnostic_logging')}
            condition = digest(dict(fields=character.fields, class_name=character.class_name,
                                    engine=identities,
                                    options=[*COMMON, *engine_options(simulation_config)],
                                    config=condition_config, simulation_config=simulation_config,
                                    cbor2=version('cbor2'),
                                    rules=rules, rule_config_digest=rule_snapshot['rule_config_digest'], **(dict(task_category='burst_free_loop',
                                                        burst_definition_id=definition['definition_id'])
                                                   if use_burst else {})))
            base_condition = condition
            if use_burst and state.get('burst'):
                from burst import load, prepare
                current = load(state['native']['identity']['spec_id'])
                if current['definition_id'] != state['burst']['definition_id']:
                    raise TaskError('恢复任务的爆发定义已变化，请创建新任务')
                effective_character = parse_character(effective_bytes.decode('utf-8'))
                blocks = prepare(current, effective_character, state['all_capabilities'], state['native']['identity'])
                if blocks != state['burst']['candidate']['blocks']:
                    raise TaskError('恢复任务的爆发程序不符，请创建新任务')
                condition = digest(dict(base=base_condition, burst=state['burst']))
            if state.get('condition') and state['condition'] != condition:
                raise TaskError('恢复任务的版本、配置或角色身份已变化，请创建新任务')
            state.update(condition=condition, config=config, rules=rules, engines=identities,
                         rule_snapshot=rule_snapshot,
                         use_burst=use_burst,
                         simulation_config=simulation_config,
                         simulation_options=engine_options(simulation_config))
            state.setdefault('phase', 'initialize')
            if state['phase'] == 'initialize':
                if 'seed_selected_snapshot' not in state:
                    from result_store import read_records
                    scope = f"{character.class_name}-{character.spec}-{simulation_config['target_count']}"
                    if use_burst:
                        scope += '-burst'
                    state['seed_selected_snapshot'] = read_records('seed_selected', scope)
                if 'training_champion_snapshot' not in state:
                    from seed_training import training_champion
                    state['training_champion_snapshot'] = training_champion(
                        character.class_name, character.spec, simulation_config, engines=identities,
                        input_interval_ms=config['input_interval_ms'], use_burst=use_burst, rule_snapshot=rule_snapshot,
                        burst_identity=(dict(spec_id=definition['spec_id'],
                                             definition_id=definition['definition_id']) if definition else None))
                # 冠军与代表快照随 inflight 同一事务冻结，先于任何原生评分。
                # 初始化辅助进程也登记崩溃时最多单批的保守额度。
                state['inflight'] = {'initialize': dict(start=runtime.elapsed_seconds, allowance=min(30,runtime.remaining_seconds))}
                store.save()
                try:
                    native = reference(destination/'input.simc', destination/'reference', character, runtime=runtime,
                                       iterations=config['iterations'], seed=config['random_seed'],
                                       simulation_config=simulation_config)
                finally:
                    if not config['diagnostic_logging']:
                        from engine import discard_diagnostic_files
                        discard_diagnostic_files(destination/'reference')
                reference_report_path = destination / 'reference' / 'native.json'
                reference_valid = reference_stored = False
                try:
                    reference_report = json.loads(reference_report_path.read_text(encoding='utf-8'))
                    reference_key = digest(dict(run_id=run_id, purpose='reference',
                                                condition=condition, seed=config['random_seed'],
                                                iterations=config['iterations']))
                    reference_damage = damage_statistics(reference_report, character)
                    reference_valid = True
                    from result_store import write_batch
                    write_batch(reference_key, dict(
                        batch_key=reference_key, run_id=run_id, condition_key=condition,
                        purpose='reference', seed=config['random_seed'],
                        requested_iterations=config['iterations'], samples=native['samples'],
                        dps=native['dps'], variance=reference_damage.get('variance'),
                        report=reference_report), diagnostic_logging=config['diagnostic_logging'], runtime=runtime)
                    reference_stored = True
                finally:
                    _discard_native_exchange(destination / 'reference',
                                             keep_valid=reference_valid and not reference_stored)
                effective_character = parse_character(effective_bytes.decode('utf-8')) if use_burst else character
                all_capabilities, capabilities, context = prepare_loop(
                    native, effective_character, destination, runtime, definition=definition,
                    interval_ms=config['input_interval_ms'])
                if use_burst:
                    state['all_capabilities'] = all_capabilities
                    state['native'] = native
                    state['burst'] = context
                    condition = digest(dict(base=base_condition, burst=context))
                    state['condition'] = condition
                starts = initial_programs(capabilities, native, config['random_seed'],
                    input_interval_ms=config['input_interval_ms'],
                    target_count=simulation_config['target_count'], scene=simulation_config.get('scene'), burst=state.get('burst'),
                    initialization=state.setdefault('rule_initialization', {}), rule_snapshot=rule_snapshot)
                if use_burst:
                    from burst import refresh_context_instructions
                    refresh_context_instructions(state['burst'], native['identity'],
                        destination / 'aligned-burst-export', runtime)
                    condition = digest(dict(base=base_condition, burst=state['burst']))
                    state['condition'] = condition
                if 'formal_champion_snapshot' not in state:
                    snapshot = _freeze_formal_champion(state, character, native, capabilities)
                    if state.get('formal_history_scope'):
                        checked_character = replace(character, spec_id=native['identity']['spec_id'],
                                                    race=native['identity']['race'])
                        snapshot = _historical_formal_champion(state, checked_character, native, capabilities, snapshot)
                    state['formal_champion_snapshot'] = snapshot
                    store.save()
                state['starts'], state['seed_adaptations'] = _seed_programs(
                    starts, state['seed_selected_snapshot'], character=character,
                    targets=simulation_config['target_count'], engines=identities,
                    capabilities=capabilities, runtime=runtime)
                champion = state['training_champion_snapshot']
                state['starts'], adaptations = _seed_programs(
                    state['starts'], [champion] if champion.get('status') == 'selected' else [],
                    character=character, targets=simulation_config['target_count'], engines=identities,
                    capabilities=capabilities, runtime=runtime)
                state['training_champion_adaptation'] = adaptations[0] if adaptations else None
                from program import canonicalize_search_program
                sources = {}
                for index, program in enumerate(starts):
                    try:
                        key = canonicalize_search_program(program, capabilities)['identity']
                    except (TypeError, ValueError, KeyError):
                        continue  # 原优化器仍逐条记录无效起点，来源标记不改变失败语义。
                    sources.setdefault(key, []).append(dict(source_kind='native', index=index))
                for kind, decisions in [('seed_selected', state['seed_adaptations']),
                                        ('training_champion', adaptations)]:
                    for decision in decisions:
                        if decision['status'] in ('accepted', 'duplicate'):
                            sources.setdefault(decision['behavior_identity'], []).append(dict(
                                source_kind=kind, candidate_id=decision['candidate_id']))
                formal = state['formal_champion_snapshot']
                state['formal_champion_adaptation'] = None
                if formal['status'] == 'selected':
                    try:
                        canonical = canonicalize_search_program(formal['program'], capabilities)
                        if canonical['identity'] != formal['behavior_identity']:
                            raise ValueError('正式冠军行为身份不符')
                        from burst import check_loop
                        if use_burst:
                            check_loop(canonical['program'], capabilities)
                        key = canonical['identity']
                        remaining = []
                        for program in state['starts']:
                            try:
                                duplicate = canonicalize_search_program(program, capabilities)['identity'] == key
                            except (TypeError, ValueError, KeyError):
                                duplicate = False  # Keep the optimizer's per-native rejection semantics.
                            if not duplicate:
                                remaining.append(program)
                        state['starts'] = [formal['program']] + remaining
                        sources.setdefault(key, []).append(dict(source_kind='formal_champion',
                            source_run_id=formal['source_run_id'], version=formal['version']))
                        state['formal_champion_adaptation'] = dict(status='accepted',
                            behavior_identity=key, derived_program=formal['program'])
                    except (TypeError, ValueError, KeyError) as error:
                        state['formal_champion_adaptation'] = dict(status='rejected', reason=str(error))
                state['start_sources'] = sources
                if not state['starts']:
                    raise TaskError('当前爆发排除条件下没有有效搜索起点')
                if not config['diagnostic_logging']:
                    native.pop('action_sequence', None)
                    native.pop('precombat_sequence', None)
                state.update(capabilities=capabilities, native=native,
                             reference_data_key=reference_key, phase='search', inflight={})
                store.save()
            character = replace(character, spec_id=state['native']['identity']['spec_id'], race=state['native']['identity']['race'])
            store.recover_reports(character, simulation_config)
            _write_json(
                destination / 'profile.json',
                _profile(character, character.raw_text,
                         original_bytes=original_bytes, effective_bytes=effective_bytes,
                         run_id=run_id),
            )
            result = optimize(profile=destination/'input.simc', character=character,
                              capabilities=state['capabilities'], reference=state['native'],
                              destination=destination, runtime=runtime, config=config,
                              condition_key=condition, store=store,
                              simulation_config=simulation_config, rule_step=rule_step)
            result.update(config=config, simulation_config=simulation_config,
                              character=character, output_root=destination,capabilities=state['capabilities'],
                              profile=json.loads((destination/'profile.json').read_text(encoding='utf-8')),
                              reference_data_key=state.get('reference_data_key'),
                              rule_initialization=state.get('rule_initialization'))
            if state.get('burst'):
                result['burst'] = dict(state['burst'], candidate=dict(
                    state['burst']['candidate'], simulation='passed_native_model'))
            result['elapsed_seconds'] = runtime.elapsed_seconds
            for name in ('training_champion_adaptation', 'formal_champion_adaptation'):
                adaptation = state.get(name)
                if adaptation and adaptation.get('behavior_identity'):
                    scored = next((row for row in state.get('archive', [])
                                   if row['key'] == adaptation['behavior_identity']), None)
                    if scored:
                        adaptation.update(current_score=scored.get('score'),
                                          current_samples=sum(batch.get('samples', 0)
                                                              for batch in scored.get('batches', [])))
            _prepare_formal_publication(store, result)
            store.save()  # Intent freezes the completed archive while heartbeats remain nonterminal.
            pointer = _store_run(destination, result, state=state)
            _write_json(destination/'result.json', pointer, atomic=True)
            state.update(status=result['status'], phase=result['phase'])
            if not state.get('formal_champion_publication_intent'):
                store.save()
            _publish_formal_champion(store, destination)
            result['search'].update({name: state[name] for name in ('formal_champion_snapshot',
                'formal_champion_adaptation', 'formal_champion_publication') if name in state})
            return result
    except (TaskCancelled, BudgetExceeded) as error:
        try:
            store.flush_reports()
        except Exception as storage_error:
            store.discard_unsaved_reports()
            state.update(status='failed', elapsed_seconds=runtime.elapsed_seconds,
                         error=str(storage_error), inflight={})
            store.save()
            _save_failure(destination, dict(status='failed', phase=state.get('phase', 'done'),
                                          elapsed_seconds=runtime.elapsed_seconds,
                                          error=str(storage_error)), state=state)
            raise TaskError(str(storage_error)) from storage_error
        state.update(status='cancelled' if isinstance(error,TaskCancelled) else 'validation_incomplete',
                     elapsed_seconds=runtime.elapsed_seconds, error=str(error), inflight={})
        store.save()
        result = {k:state.get(k) for k in (
            'status', 'phase', 'elapsed_seconds', 'locked_candidate_key', 'completed_batches',
            'batch_requests', 'batch_cache_hits', 'native_batch_starts',
            'canonicalized_duplicates', 'error')}
        observation = state.get('search_observability')
        if observation and observation.get('mode') != 'off':
            with store.lock:
                result['search_observability'] = _export_search_observability(
                    observation, include_details=observation.get('mode') == 'full')
        _save_failure(destination, result, state=state)
        return result
    except Exception as error:
        store.discard_unsaved_reports()
        state.update(status='failed', elapsed_seconds=runtime.elapsed_seconds, error=str(error), inflight={})
        store.save()
        failure = dict(status='failed', phase=state.get('phase', 'done'),
                       elapsed_seconds=runtime.elapsed_seconds, error=str(error))
        _save_failure(destination, failure, state=state)
        raise TaskError(str(error)) from error
    finally:
        runtime.reservation = None
        try:
            store.publish()
        finally:
            store.close()


@contextmanager
def _task_lease(destination, *, lock_name='.runner.lock', conflict_message='任务正在运行，不能同时恢复'):
    with (destination/lock_name).open('a+b') as lock:
        if lock.tell()==0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as error:
            raise TaskError(conflict_message) from error
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


def _run_task(input_path: str | Path, output_root: str | Path | None = None, *, program=None, phase_ms=0,
             mode="optimize", search_config=None, simulation_config=None, cancel_event=None,
             resume=False, _runtime=None, _lease=False, gse_text=None, sequence_name=None,
             version=None, gse_context=None, use_burst=False, burst_identity=None,
             _formal_source_run_ids=None, _rule_snapshot=None, rule_step=None) -> dict:
    """执行角色任务；优化模式是产品默认，single 仅保留前两票快速回归。"""
    if type(use_burst) is not bool:
        raise TaskError('爆发开关必须为布尔值')
    if rule_step is not None and (mode != 'optimize' or not resume):
        raise TaskError('规则单步需要恢复已有已评分父任务')
    if burst_identity is not None:
        if not use_burst or mode != 'optimize' or resume:
            raise TaskError('冻结爆发身份仅用于新的爆发优化任务')
        if (not isinstance(burst_identity, dict) or set(burst_identity) != {'spec_id', 'definition_id'} or
                type(burst_identity['spec_id']) is not int or not isinstance(burst_identity['definition_id'], str)):
            raise TaskError('冻结爆发身份格式无效')
    if use_burst and (search_config is None or isinstance(search_config, dict) and 'input_interval_ms' not in search_config):
        search_config = dict(search_config or {}, input_interval_ms=200)
    if resume and not _lease:
        if mode!='optimize':
            raise TaskError('单次评估不支持恢复')
        destination=Path(output_root).resolve()
        input_path = Path(input_path).resolve()
        if input_path != (destination / 'input.simc').resolve():
            try:
                current_original = input_path.read_bytes()
                saved_original = (destination / 'input.original.simc').read_bytes()
            except OSError as error:
                raise TaskError('恢复任务的原始输入不可读取，请创建新任务') from error
            if current_original != saved_original:
                raise TaskError('恢复任务的原始输入已变化，请创建新任务')
        return resume_task(destination, search_config=search_config, simulation_config=simulation_config,
                           _runtime=_runtime, cancel_event=cancel_event, rule_step=rule_step)
    if mode=='optimize' and (program is not None or phase_ms!=0):
        raise TaskError('优化入口自动选择动作，手工程序仅用于单次评估')
    if mode not in ("optimize", "single", "import"):
        raise TaskError("任务模式必须是 optimize、single 或 import")
    if mode != "import" and any(value is not None for value in (gse_text, sequence_name, version, gse_context)):
        raise TaskError("GSE 导入参数只能用于导入模式")
    if mode == "import":
        from gse_import import decode_import
        from program import from_gse_import
        if program is not None or not isinstance(sequence_name, str) or not sequence_name:
            raise TaskError("GSE 导入模式需要明确选定序列")
        try:
            decoded = decode_import(gse_text)
        except ValueError as error:
            raise TaskError(str(error)) from error
        if sequence_name not in decoded["sequences"] or type(version) is not int:
            raise TaskError("GSE 选定的序列或版本无效")
        gse_program = from_gse_import(gse_text, sequence_name, version,
                                      context=gse_context, decoded=decoded)
    else:
        gse_program = None
    from search import config_for
    config = config_for(search_config)
    from result_store import ensure_available
    ensure_available()
    simulation_config = simulation_config_for(simulation_config)
    runtime = _runtime or TaskRuntime(config['total_budget_seconds'] if mode == 'optimize' else 600, cancel_event=cancel_event)
    path, raw_text, character, destination = _prepare_task(
        input_path, output_root, resume=resume, simulation_config=simulation_config
    )
    if gse_program is not None:
        (destination / "input.gse").write_text(gse_text, encoding="ascii", newline="")
    with nullcontext() if _lease else _task_lease(destination):
        if mode in ("single", "import"):
            try:
                result = _run_single(path, destination, character, program=program, phase_ms=phase_ms,
                                     runtime=runtime, interval_ms=config["input_interval_ms"],
                                     simulation_config=simulation_config, gse_program=gse_program,
                                     gse_context=gse_context, diagnostic_logging=config["diagnostic_logging"],
                                     use_burst=use_burst)
                result['config'] = config
                result['elapsed_seconds'] = runtime.elapsed_seconds
                pointer = _store_run(destination, result)
                _write_json(destination / "result.json", pointer, atomic=True)
                return result
            except TaskCancelled as error:
                failure = dict(status="cancelled", phase='done', elapsed_seconds=runtime.elapsed_seconds,
                               error=str(error))
                _save_failure(destination, failure)
                return failure
            except BudgetExceeded as error:
                failure = dict(status="budget_exhausted", phase='done', elapsed_seconds=runtime.elapsed_seconds,
                               error=str(error))
                _save_failure(destination, failure)
                return failure
            except (ValueError, OSError, KeyError, ImportError, StopIteration) as error:
                message = str(error) or "上游校验未返回预期结果"
                if isinstance(error, ImportError):
                    message = "缺少任务依赖，请按本机任务文档准备依赖: " + message
                failure = dict(status="failed", phase='done', elapsed_seconds=runtime.elapsed_seconds,
                               error=message)
                _save_failure(destination, failure)
                raise TaskError(message) from error
        try:
            return _run_optimize(destination, character, config=config, runtime=runtime,
                                 simulation_config=simulation_config, use_burst=use_burst, burst_identity=burst_identity,
                                 formal_source_run_ids=_formal_source_run_ids, rule_snapshot=_rule_snapshot,
                                 rule_step=rule_step)
        except TaskCancelled as error:
            state = {"status": "cancelled", "error": str(error), "elapsed_seconds": runtime.elapsed_seconds}
            _save_failure(destination, state)
            return state
        except BudgetExceeded as error:
            state = {"status": "budget_exhausted", "error": str(error), "elapsed_seconds": runtime.elapsed_seconds}
            _save_failure(destination, state)
            return state


def run_task(input_path: str | Path, output_root: str | Path | None = None, *, program=None, phase_ms=0,
             mode="optimize", search_config=None, simulation_config=None, cancel_event=None,
             resume=False, _runtime=None, _lease=False, gse_text=None, sequence_name=None,
             version=None, gse_context=None, use_burst=False, burst_identity=None, _rule_snapshot=None,
             rule_step=None) -> dict:
    if mode == 'optimize':
        from search import config_for
        _runtime = _runtime or TaskRuntime(config_for(search_config)['total_budget_seconds'],
                                           cancel_event=cancel_event)
        from rule_config import load
        try:
            _rule_snapshot = _rule_snapshot or load()
        except ValueError as error:
            raise TaskError(str(error)) from error
    if mode != 'optimize' or _lease:
        return _run_task(input_path, output_root, program=program, phase_ms=phase_ms, mode=mode,
                         search_config=search_config, simulation_config=simulation_config,
                         cancel_event=cancel_event, resume=resume, _runtime=_runtime, _lease=_lease,
                         gse_text=gse_text, sequence_name=sequence_name, version=version,
                         gse_context=gse_context, use_burst=use_burst, burst_identity=burst_identity,
                         _rule_snapshot=_rule_snapshot, rule_step=rule_step)
    from seed_activity import foreground_search
    with foreground_search():
        return _run_task(input_path, output_root, program=program, phase_ms=phase_ms, mode=mode,
                         search_config=search_config, simulation_config=simulation_config,
                         cancel_event=cancel_event, resume=resume, _runtime=_runtime, _lease=_lease,
                         gse_text=gse_text, sequence_name=sequence_name, version=version,
                         gse_context=gse_context, use_burst=use_burst, burst_identity=burst_identity,
                         _rule_snapshot=_rule_snapshot, rule_step=rule_step)


class TaskHandle:
    def __init__(self, thread, runtime, destination):
        self.thread = thread
        self.runtime = runtime
        self.output_root = Path(destination).resolve()
        self.result = None
        self.error = None

    def join(self, timeout=None):
        self.thread.join(timeout)
        return self.result

    @property
    def done(self):
        return not self.thread.is_alive()


_ACTIVE_TASKS = {}
_ACTIVE_LOCK = threading.RLock()


def start_task(input_path, output_root, **kwargs):
    """异步启动同一公开任务入口，返回可取消的任务句柄。"""
    config = kwargs.get("search_config")
    from search import config_for
    runtime = TaskRuntime(config_for(config)["total_budget_seconds"] if kwargs.get("mode", "optimize") == "optimize" else 600)
    if kwargs.get('mode', 'optimize') == 'optimize':
        from rule_config import load
        kwargs['_rule_snapshot'] = load()
    handle = TaskHandle(None, runtime, output_root)

    def worker():
        try:
            handle.result = run_task(input_path, output_root, _runtime=runtime, **kwargs)
        except BaseException as error:
            handle.error = error
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_TASKS.pop(handle.output_root, None)

    handle.thread = threading.Thread(target=worker, name="sim2gse-task", daemon=True)
    with _ACTIVE_LOCK:
        if handle.output_root in _ACTIVE_TASKS:
            raise TaskError(f"任务已在运行: {handle.output_root}")
        _ACTIVE_TASKS[handle.output_root] = handle
    handle.thread.start()
    return handle


def cancel_task(task):
    handle = task if isinstance(task, TaskHandle) else _ACTIVE_TASKS.get(Path(task).resolve())
    if handle is None:
        return read_task(task)
    handle.runtime.cancel()
    handle.join(2.5)
    if not handle.done:
        return {"status":"stopping"}
    return read_task(handle.output_root) if (handle.output_root / "result.json").exists() else {"status": "stopping"}


def _resume_task(output_root, **kwargs):
    destination = Path(output_root).resolve()
    simulation_config = simulation_config_for(kwargs.pop("simulation_config", None))
    from result_store import ensure_available
    ensure_available()
    with _task_lease(destination):
        try:
            profile = json.loads((destination / "profile.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaskError("恢复任务的角色档案不可读取，请创建新任务") from error
        if not isinstance(profile, dict):
            raise TaskError("恢复任务的角色档案格式无效，请创建新任务")
        _verify_task_inputs(destination, profile)
        from search import (TaskStore, _export_search_observability, config_for,
                            verify_behavior_identity_state)
        store = TaskStore(destination)
        try:
            state = store.state
            from rule_config import load
            try:
                current_rules = kwargs.pop('_rule_snapshot', None) or load()
            except ValueError as error:
                raise TaskError(str(error)) from error
            if ((state.get('rule_snapshot') or {}).get('rule_config_digest') !=
                    current_rules['rule_config_digest']):
                raise TaskError('恢复任务的规则配置已变化，请创建新任务')
            kwargs['_rule_snapshot'] = current_rules
            if 'formal_champion_publication' in state:
                try:
                    _formal_publication_metadata(state['formal_champion_publication'])
                except ValueError as error:
                    raise TaskError(str(error)) from error
            saved_burst_mode = state.get('use_burst', False)
            if 'use_burst' in kwargs and kwargs['use_burst'] != saved_burst_mode:
                raise TaskError('恢复任务的爆发模式发生变化，请创建新任务')
            kwargs['use_burst'] = saved_burst_mode
            if state.get('burst_definition_id'):
                from burst import load
                current = load(state['burst_spec_id'])
                if current['definition_id'] != state['burst_definition_id']:
                    raise TaskError('恢复任务的爆发定义已变化，请创建新任务')
            if state.get('burst'):
                from burst import load
                current = load(state['native']['identity']['spec_id'])
                if current['definition_id'] != state['burst']['definition_id']:
                    raise TaskError('恢复任务的爆发定义已变化，请创建新任务')
            try:
                verify_behavior_identity_state(state)
            except ValueError as error:
                raise TaskError(str(error)) from error
            _verify_task_inputs(destination, state)
            if not state.get('config'):
                raise TaskError('任务缺少恢复清单')
            if not state.get('simulation_config'):
                raise TaskError('任务缺少恢复模拟配置')
            if simulation_config != simulation_config_for(state['simulation_config']):
                raise TaskError('恢复模拟配置发生变化，请创建新任务')
            config = config_for(kwargs.pop('search_config', None) or state['config'])
            logging_keys = ('diagnostic_logging', 'diagnostics', 'search_observability')
            if ({key: value for key, value in config.items() if key not in logging_keys} !=
                    {key: value for key, value in config_for(state['config']).items()
                     if key not in logging_keys}):
                raise TaskError('恢复配置发生变化，请创建新任务')
            logging = kwargs.pop('diagnostic_logging', False)
            config = config_for(dict(config, diagnostic_logging=logging,
                diagnostics=(config['diagnostics'] if config['diagnostics'] != 'off' else 'summary')))
            state['config'] = config
            from engine import identity
            # 已验身份不提前触发预算/取消检查，保留完成与耗尽恢复的可靠补发顺序。
            verified = getattr(kwargs.get('_runtime'), 'identities', {})
            try:
                verified = {mode: verified[mode] if mode in verified else identity(mode)
                            for mode in ('baseline', 'controlled')}
                if (state.get('rules') != _rule_hashes() or
                        state.get('engines') != {mode: entry[1] for mode, entry in verified.items()}):
                    raise TaskError('恢复任务的版本或编译规则已变化，请创建新任务')
            except (ValueError, OSError) as error:
                raise TaskError(str(error)) from error
            used = float(state.get('elapsed_seconds',0))
            terminal_rule_step = False
            if kwargs.get('rule_step') is not None:
                from rule_diagnostics import enqueue
                try:
                    step_status = enqueue(state, kwargs['rule_step'], config, used)
                except ValueError as error:
                    raise TaskError(str(error)) from error
                store.save()
                terminal_rule_step = (step_status in ('scored', 'failed', 'duplicate') and not any(
                    work.get('rule_step', {}).get('request') == kwargs['rule_step']
                    for work in state.get('pending', [])))
            feedback_accounted_seconds = 0
            if state.get('native'):
                character = parse_character((destination / 'input.simc').read_text(encoding='utf-8-sig'))
                character = replace(character, spec_id=state['native']['identity']['spec_id'],
                                    race=state['native']['identity']['race'])
                store.recover_reports(character, simulation_config)
                from search import reconcile_selection_feedback
                reconcile_selection_feedback(store,
                    finalizing=used >= config['total_budget_seconds'] or state.get('stop_reason') == 'search_deadline',
                    cancel_event=kwargs.get('cancel_event') or getattr(kwargs.get('_runtime'), 'cancel_event', None))
                feedback_accounted_seconds = max(0, state.get('elapsed_seconds', used) - used)
            used = float(state.get('elapsed_seconds', used))
            if state.get('status') == 'running':
                penalty = max((max(0, r['allowance'] - max(0,used-r['start']))
                               for r in state.get('inflight',{}).values()),default=0)
                used += min(30, penalty, max(0, config['total_budget_seconds']-used))
                state.update(elapsed_seconds=used,status='interrupted',inflight={})
                store.save()  # 扣除与恢复标记同一事务，重复恢复不会再次扣除。
            if state.get('formal_champion_publication_intent'):
                _restore_formal_result(store, destination, character)
                _publish_formal_champion(store, destination)
            if terminal_rule_step:
                # 操作终态幂等仍须补发可靠结果；不能绕过上次中断后的中心/指针/进度同步。
                chosen = next((row for row in state.get('archive', [])
                               if row['key'] == state.get('locked_candidate_key', state.get('best'))), {})
                search = dict(state, records=state.get('archive', []),
                    candidate_count=len(state.get('evaluated_keys', [])),
                    unique_candidates=len(state.get('seen', [])),
                    partial_round=bool(state.get('pending')) or not state.get('full_round', True),
                    rule_diagnostics=chosen.get('rule_diagnostics'))
                if search['rule_diagnostics']:
                    search['rule_diagnostics_version'] = search['rule_diagnostics']['version']
                fields = (state.get('formal_champion_publication_intent') or {}).get('result_fields', {})
                search.update({key: value for key, value in fields.get('search', {}).items() if key == 'no_improvement_round_limit'})
                result = dict(fields, status=state['status'], phase=state['phase'], search=search,
                    validation=dict(dataset='validation', records=[row[name] for row in state.get('archive', [])
                        for name in ('validation', 'global_validation') if name in row]),
                    independent_validation_complete=False, improvement='search_result',
                    final=fields.get('final', dict(dataset='final', status='not_requested', scenarios={})))
                observation = state.get('search_observability')
                if observation and observation.get('mode') != 'off':
                    result['search_observability'] = _export_search_observability(
                        observation, include_details=observation.get('mode') == 'full')
                pointer = _store_run(destination, result, state=state)
                _write_json(destination/'result.json', pointer, atomic=True)
                store.publish()
                return read_task(destination)
            if (destination / 'result.json').is_file():
                if state.get('status') == 'completed':
                    from result_store import RUN_SCHEMA, one, write
                    started = time.monotonic()
                    try:
                        published = one('runs', 'run_id', state['run_id'])
                        if published is None:
                            raise TaskError('已完成任务的中心结果缺失')
                        published = {name: json.loads(value) if RUN_SCHEMA.get(name) == 'JSON'
                                     and isinstance(value, str) else value
                                     for name, value in published.items()}
                        metrics = dict(published.get('search_metrics') or {})
                        metrics.update(rule_steps=state.get('rule_steps', {}),
                            selection_feedback_incomplete=state.get('selection_feedback_incomplete', False))
                        if (metrics != published.get('search_metrics') or used != published['elapsed_seconds']
                                or published.get('config') != config):
                            published.update(search_metrics=metrics, config=config,
                                elapsed_seconds=used + time.monotonic()-started)
                            write('runs', state['run_id'], [published], schema=RUN_SCHEMA)
                    finally:
                        state['elapsed_seconds'] = used + time.monotonic()-started
                        store.save()
                    store.publish()
                    return read_task(destination)
            if used >= config['total_budget_seconds']:
                if state.get('status')!='completed':
                    state.update(status='validation_incomplete',elapsed_seconds=used,error='计算预算已耗尽')
                    store.save()
                    result = dict(state)
                    result['independent_validation_complete']=False
                    observation = state.get('search_observability')
                    if observation and observation.get('mode') != 'off':
                        result['search_observability'] = _export_search_observability(
                            observation, include_details=observation.get('mode') == 'full')
                    pointer = _store_run(destination, result, state=state)
                    _write_json(destination/'result.json',pointer,atomic=True)
                store.publish()
                return read_task(destination)
        finally:
            store.close()
        runtime = kwargs.pop('_runtime', None)
        if runtime is not None:
            # used已含补发实耗；外传时钟亦在运行，仅消除这一段重复计时。
            runtime.started += feedback_accounted_seconds
        else:
            runtime = TaskRuntime(config['total_budget_seconds'], cancel_event=kwargs.pop('cancel_event', None))
        kwargs.pop('cancel_event',None)
        runtime.identities.update(verified)
        runtime.used_seconds=used
        runtime.budget_seconds=config['total_budget_seconds']
        runtime.phase_limit=runtime.budget_seconds
        return run_task(destination/'input.simc', destination, resume=True, _runtime=runtime, _lease=True,
                        search_config=config, simulation_config=simulation_config, **kwargs)


def resume_task(output_root, **kwargs):
    from seed_activity import foreground_search
    with foreground_search():
        return _resume_task(output_root, **kwargs)


def read_task(output_root, *, include_search_records=False, include_reports=False,
              include_rule_initialization=True):
    from result_store import DataReadError
    try:
        return _read_task(output_root, include_search_records=include_search_records,
                          include_reports=include_reports,
                          include_rule_initialization=include_rule_initialization)
    except DataReadError as error:
        raise TaskError(str(error)) from error


def _batch_locations(destination, keys):
    """Read only requested batch locators from the existing read-only checkpoint."""
    from result_store import DataReadError, DATA_ROOT, report_locations
    keys = list(dict.fromkeys(key for key in keys if key))
    locations = {}
    database = destination / 'task.sqlite3'
    if keys and database.is_file():
        connection = None
        try:
            connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
            for offset in range(0, len(keys), 500):
                chunk = keys[offset:offset + 500]
                sql = 'SELECT key,value FROM batches WHERE key IN (' + ','.join('?' for _ in chunk) + ')'
                for key, payload in connection.execute(sql, chunk):
                    row = json.loads(payload)
                    if not isinstance(row, dict):
                        raise ValueError('批次位置记录必须是对象')
                    locations[key] = row.get('storage_group_key') or row.get('data_key') or key
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise DataReadError('任务批次位置不可读取') from error
        finally:
            if connection is not None:
                connection.close()
    missing = [key for key in keys if key not in locations]
    if missing and (DATA_ROOT / '.report-locations.jsonl').exists():
        locations.update({key: group for key, group in report_locations(missing).items() if group})
    return locations


def _read_task(output_root, *, include_search_records=False, include_reports=False,
               include_rule_initialization=True):
    destination = Path(output_root).resolve()
    progress_path = destination / 'progress.json'
    progress = None
    if progress_path.is_file():
        try:
            progress = json.loads(progress_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            progress = None
        if progress and progress.get('status') in ('running', 'stopping'):
            return progress

    pointer_path = destination / 'result.json'
    if not pointer_path.is_file():
        if progress_path.is_file() and progress is not None:
            return progress
        raise TaskError(f'任务结果不存在: {destination}')
    try:
        pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise TaskError(f'任务结果不可读取: {destination}') from error
    run_id = pointer.get('run_id')
    if not run_id:
        return pointer

    from result_store import RUN_SCHEMA, read_many, one as read_record

    columns = None if include_rule_initialization else [
        name for name in RUN_SCHEMA if name != 'rule_initialization']
    saved = read_record('runs', 'run_id', run_id, columns=columns)
    if saved is None:
        return pointer

    def decode(value):
        return json.loads(value) if isinstance(value, str) else value

    search = dict(
        candidate_count=saved['search_candidate_count'],
        unique_candidates=saved['search_unique_candidates'],
        rounds=saved['search_rounds'], partial_round=saved['search_partial_round'],
        stop_reason=saved['search_stop_reason'], chains=decode(saved['search_chains']) or [],
        errors=decode(saved['search_errors']) or [],
        batch_keys=saved['batch_keys'] or [])
    if saved['search_metrics']:
        search.update(decode(saved['search_metrics']))
    if pointer.get('formal_champion_publication'):
        search['formal_champion_publication'] = pointer['formal_champion_publication']
    checkpoint = destination / 'task.sqlite3'
    if checkpoint.is_file():
        database = None
        try:
            database = sqlite3.connect(checkpoint.as_uri() + '?mode=ro', uri=True)
            publication = (database.execute("SELECT value FROM state_fields WHERE key='formal_champion_publication'").fetchone()
                if database.execute("SELECT 1 FROM sqlite_master WHERE name='state_fields'").fetchone() else None)
            if publication:
                search['formal_champion_publication'] = _formal_publication_metadata(decode(publication[0]))
        except (sqlite3.Error, OSError, ValueError) as error:
            search['formal_champion_publication_verification'] = dict(status='unknown',
                reason='本地正式冠军发布状态不可核验，保留中心可靠结果', error=str(error))
        finally:
            if database is not None:
                database.close()
    if saved['search_observability']:
        search['observability'] = decode(saved['search_observability'])
    search['native_batch_starts_total'] = saved['native_batch_starts'] or 0
    task_result = dict(
        run_id=run_id, status=saved['status'], phase=saved['phase'],
        profile=decode(saved['profile']), identity=decode(saved['identity']),
        config=decode(saved['config']), simulation_config=decode(saved['simulation_config']),
        elapsed_seconds=saved['elapsed_seconds'], completed_batches=saved['completed_batches'],
        reference_data_key=saved['reference_data_key'], controlled_data_key=saved['controlled_data_key'],
        candidate_key=saved['candidate_key'], candidate_data_key=saved['candidate_data_key'],
        selected_candidate_key=saved['selected_candidate_key'],
        locked_candidate_key=saved['locked_candidate_key'], improvement=saved['improvement'],
        independent_validation_complete=saved['independent_validation_complete'],
        native_reference=decode(saved['reference_summary']), search=search,
        final=dict(dataset='final', status=saved['final_status'],
                   scenarios=decode(saved['final_scenarios']) or {}),
        error=saved['error'], output_root=destination)
    if include_rule_initialization:
        task_result['rule_initialization'] = decode(saved.get('rule_initialization'))
    initialization_identity = search.get('rule_initialization_identity')
    if not initialization_identity and task_result.get('rule_initialization'):
        initialization = task_result['rule_initialization']
        initialization_identity = (initialization['behavior_identity'] + ':' +
                                   initialization.get('compilation', 'pending'))
    task_result.update(has_rule_initialization=bool(initialization_identity),
                       rule_initialization_identity=initialization_identity)
    if saved['search_observability']:
        task_result['search_observability'] = decode(saved['search_observability'])
    if saved.get('burst'):
        burst_record = decode(saved['burst'])
        row = read_record('candidates', 'candidate_data_key', burst_record['candidate_data_key'])
        if row is None:
            raise TaskError('结果中心的爆发导出候选缺失')
        burst_record['candidate'] = dict(identity=row['candidate_key'], program=decode(row['program']),
                                          text=row['export_text'], simulation=row['simulation'],
                                          game_validation=row['game_validation'])
        task_result['burst'] = burst_record
    if saved['search_dps'] is not None:
        task_result['search_result'] = dict(
            dps=saved['search_dps'], samples=saved['search_samples'],
            reference_dps=saved['reference_dps'], reference_ratio=saved['search_reference_ratio'])
    if saved['validation_summary']:
        task_result['validation'] = decode(saved['validation_summary'])

    if saved['candidate_data_key']:
        candidate = read_record('candidates', 'candidate_data_key', saved['candidate_data_key'])
        if candidate is None:
            raise TaskError('结果中心的导出候选缺失')
        task_result['candidate'] = dict(
            identity=candidate['candidate_key'], source=candidate['source'],
            program=decode(candidate['program']), text=candidate['export_text'],
            simulation=candidate['simulation'], selected_sequence=candidate['selected_sequence'],
            selected_version=candidate['selected_version'], import_sha256=candidate['import_sha256'],
            game_validation=candidate['game_validation'])

    locations = _batch_locations(destination, [saved['controlled_data_key'],
                         *(search['batch_keys'] if include_search_records else [])])
    if saved['controlled_data_key']:
        controlled = read_record('batches', 'batch_key', saved['controlled_data_key'],
                                 group_key=locations.get(saved['controlled_data_key']),
                                 columns=None if include_reports else ['batch_key', 'dps', 'samples'])
        if controlled is None:
            raise TaskError('结果中心的受控模拟报告缺失')
        controlled_simulation = dict(summary=dict(dps=controlled['dps'], samples=controlled['samples']),
                                     data_key=saved['controlled_data_key'])
        if include_reports:
            controlled_simulation['report'] = controlled['report']
        task_result['controlled_simulation'] = controlled_simulation

    if include_search_records and search['batch_keys']:
        from search import digest
        wanted = set(search['batch_keys'])
        groups = list(dict.fromkeys(locations.get(key) or key for key in search['batch_keys']))
        columns = ['batch_key', 'candidate_key', 'purpose', 'condition_key', 'program_identity',
                   'batch_index', 'scenario', 'stats_version', 'seed', 'input_seed', 'iterations',
                   'times', 'trace', 'dps', 'samples', 'variance', 'requested_iterations']
        if search.get('rule_diagnostics_version'):
            columns += ['rule_diagnostics', 'rule_observations']
        batches = {row['batch_key']: row for row in read_many('batches', groups, columns=columns)
                   if row['batch_key'] in wanted}
        candidate_keys = list(dict.fromkeys(row['candidate_key'] for row in batches.values()
                              if row['purpose'] == 'search' and row['candidate_key']))
        candidates = {row['candidate_key']: row for row in read_many('candidates',
                      [digest(dict(run_id=run_id, candidate_key=key)) for key in candidate_keys],
                      columns=['run_id', 'candidate_key', 'search_order', 'program', 'source',
                               'export_text', 'simulation'], filters={'run_id': run_id})}
        grouped = {}
        for row in sorted(batches.values(), key=lambda row: (row['candidate_key'] or '', row['batch_index'] or 0)):
            if row['purpose'] != 'search' or not row['candidate_key']:
                continue
            key = row['candidate_key']
            candidate = candidates.get(key)
            request = dict(
                condition=row['condition_key'],
                program=decode(row['program_identity']), purpose=row['purpose'],
                behavior_identity=key, seed=row['seed'], input_seed=row['input_seed'],
                iterations=row['iterations'], times=row['times'], stats=row['stats_version'],
                trace=row['trace'],
                reset_events=[list(event) for event in task_result['config'].get('reset_events', [])])
            batch = dict(status='success', data_key=row['batch_key'], request=request,
                         dps=row['dps'], samples=row['samples'], variance=row['variance'],
                         requested_iterations=row['requested_iterations'], batch_index=row['batch_index'],
                         scenario=row['scenario'])
            if row.get('rule_observations') is not None:
                request['rule_observations'] = decode(row['rule_observations'])
            record = grouped.setdefault(key, dict(key=key, batches=[]))
            if row.get('rule_diagnostics') is not None:
                from rule_diagnostics import rebind
                record['rule_diagnostics'] = rebind(decode(row['rule_diagnostics']), run_id,
                    diagnostic_logging=task_result['config'].get('diagnostic_logging', False))
            if key in search.get('rule_diagnostic_replays', {}):
                replay = search['rule_diagnostic_replays'][key]
                if replay['batch_key'] == row['batch_key']:
                    record['rule_diagnostics'] = replay['diagnostic']
            for step in search.get('rule_steps', {}).values():
                if step.get('candidate_key') == key:
                    record['rule_step'] = step
            record['batches'].append(batch)
            if candidate is not None:
                record['program'] = decode(candidate['program'])
                record['candidate'] = dict(identity=key, source=candidate['source'],
                                           program=decode(candidate['program']),
                                           text=candidate['export_text'],
                                           simulation=candidate['simulation'])
        records = []
        for record in grouped.values():
            rows = record['batches']
            samples = sum(row['samples'] for row in rows)
            record['score'] = (sum(row['dps'] * row['samples'] for row in rows) / samples
                               if samples else 0.0)
            records.append(record)
        records.sort(key=lambda record: (
            candidates.get(record['key'], {}).get('search_order') is None,
            candidates.get(record['key'], {}).get('search_order') or 0,
            record['key']))
        search['records'] = records
    return task_result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('rules-check', 'rules-save'):
        parser = argparse.ArgumentParser(description='校验或保存两库规则；不启动模拟')
        parser.add_argument('command', choices=('rules-check', 'rules-save'))
        parser.add_argument('file', type=Path)
        parser.add_argument('--expected-digest', required=argv[0] == 'rules-save')
        args = parser.parse_args(argv)
        try:
            from rule_config import load, save
            if args.command == 'rules-save':
                result = save(args.file, args.expected_digest)
            else:
                snapshot = load(args.file)
                result = dict(status='valid', rule_config_digest=snapshot['rule_config_digest'], source=snapshot['source'])
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (TaskError, ValueError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 2
    parser = argparse.ArgumentParser(description='从单个角色文件生成本机离线序列')
    parser.add_argument('input',type=Path,nargs='?',help='角色导出文件')
    parser.add_argument('--resume',action='store_true',help='按原有清单和预算恢复任务')
    parser.add_argument('--diagnostic-logging', action='store_true',
                        help='本次开启全部性能诊断日志；新建和恢复默认均关闭')
    parser.add_argument('--output', type=Path, required=True, help='新任务目录（不会覆盖已有目录）')
    args = parser.parse_args(argv)
    try:
        simulation_config = load_config()
        if args.resume:
            result = resume_task(args.output, simulation_config=simulation_config,
                                 diagnostic_logging=args.diagnostic_logging)
        else:
            if args.input is None:
                parser.error('新任务需要角色文件')
            result = run_task(args.input, args.output, simulation_config=simulation_config,
                              search_config=dict(diagnostic_logging=args.diagnostic_logging,
                                                 diagnostics='summary'))
        print(json.dumps(dict(status=result['status'], result=str(args.output.resolve() / 'result.json')), ensure_ascii=False))
        return 0
    except (TaskError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


__all__ = ["Character", "Equipment", "TaskError", "parse_character", "run_task"]

if __name__ == '__main__':
    raise SystemExit(main())
