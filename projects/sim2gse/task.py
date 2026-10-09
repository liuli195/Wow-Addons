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


def _json_result(result: dict) -> dict:
    return {key: value for key, value in result.items() if key not in ("character", "output_root")}


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
                           'canonicalized_duplicates', 'no_improvement_round_limit')
    search_metrics = {name: search[name] for name in search_metric_names if name in search}
    cache_hit_keys = sorted({row['data_key'] for record in search.get('records', [])
                             for row in record.get('batches', [])
                             if row.get('cached') and isinstance(row.get('data_key'), str)})
    original = _read_utf8(destination / 'input.original.simc', description='原始输入副本')[1]
    effective = _read_utf8(destination / 'input.simc', description='任务输入副本')[1]
    record = dict(
        run_id=run_id, status=result.get('status', 'failed'), phase=result.get('phase', 'done'),
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
                simulation_config, gse_program=None, gse_context=None, diagnostic_logging=False):
    from engine import inspect, reference, damage_statistics
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
                    diagnostic_logging=diagnostic_logging)
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
    capabilities = inspect(native, destination / "capabilities")
    if not diagnostic_logging:
        native.pop('action_sequence', None)
        native.pop('precombat_sequence', None)
    candidate = compile_program(gse_program or from_action_blocks(select(capabilities, program)),
                                destination / "export", identity=native['identity'], runtime=runtime,
                                capabilities=capabilities, context=gse_context)
    controlled = evaluate(destination / "input.simc", candidate, destination / "controlled", character=character,
                          input_times=list(range(phase_ms, 180000, interval_ms)), runtime=runtime,
                          simulation_config=simulation_config)
    controlled_candidate_key = candidate.get('identity') or digest(candidate.get('program') or {})
    controlled_key = digest(dict(run_id=run_id, purpose='controlled',
                                 candidate_key=controlled_candidate_key, phase_ms=phase_ms,
                                 interval_ms=interval_ms,
                                 input_sha256=json.loads((destination / 'profile.json').read_text(encoding='utf-8'))['input_effective_sha256'],
                                 simulation_config=simulation_config))
    controlled_damage = damage_statistics(controlled['report'], character)
    controlled_stored = False
    try:
        write_batch(controlled_key, dict(
            batch_key=controlled_key, run_id=run_id, purpose='controlled',
            candidate_key=controlled_candidate_key, seed=20260912, requested_iterations=100,
            samples=controlled['summary']['samples'], dps=controlled['summary']['dps'],
            variance=controlled_damage.get('variance'), report=controlled['report'],
            times=controlled['input_times'], phase_ms=phase_ms,
            reset_events=controlled.get('reset_events', [])), diagnostic_logging=diagnostic_logging)
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
        return starts
    from program import canonicalize_search_program
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

    identities = set()
    for program in starts:
        try:
            identities.add(canonicalize_search_program(program, capabilities)['identity'])
        except (TypeError, ValueError, KeyError):
            continue

    target_masks = None
    added = []
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
        try:
            canonical = canonicalize_search_program(program, capabilities)
        except (TypeError, ValueError, KeyError):
            continue
        if canonical['identity'] in identities:
            continue
        if target_masks is None:
            target_masks = load_targeting(runtime=runtime)['target_masks']
        try:
            check_program(canonical['program'], target_masks)
        except (TypeError, ValueError, KeyError):
            continue
        # The normal optimizer compiles and identity-checks this start during its
        # first score, avoiding a duplicate Lua compiler launch at task startup.
        identities.add(canonical['identity'])
        added.append(program)
    return starts + added


def _run_optimize(destination, character, *, config, runtime, simulation_config):
    from engine import identity, inspect, reference, damage_statistics, COMMON
    from search import TaskStore, _export_search_observability, digest, initial_programs, optimize
    store = TaskStore(destination)
    state = store.state
    run_id = json.loads((destination / 'profile.json').read_text(encoding='utf-8')).get('run_id')
    if not isinstance(run_id, str) or not run_id:
        store.close()
        raise TaskError('任务缺少结果中心身份，请创建新任务')
    if state.get('run_id') not in (None, run_id):
        store.close()
        raise TaskError('任务结果中心身份与检查点不符，请创建新任务')
    state['run_id'] = run_id
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
                                    rules=rules))
            if state.get('condition') and state['condition'] != condition:
                raise TaskError('恢复任务的版本、配置或角色身份已变化，请创建新任务')
            state.update(condition=condition, config=config, rules=rules, engines=identities,
                         simulation_config=simulation_config,
                         simulation_options=engine_options(simulation_config))
            state.setdefault('phase', 'initialize')
            if state['phase'] == 'initialize':
                if 'seed_selected_snapshot' not in state:
                    from result_store import read_records
                    scope = f"{character.class_name}-{character.spec}-{simulation_config['target_count']}"
                    state['seed_selected_snapshot'] = read_records('seed_selected', scope)
                    store.save()
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
                        report=reference_report), diagnostic_logging=config['diagnostic_logging'])
                    reference_stored = True
                finally:
                    _discard_native_exchange(destination / 'reference',
                                             keep_valid=reference_valid and not reference_stored)
                capabilities = inspect(native, destination/'capabilities')
                starts = initial_programs(capabilities, native, config['random_seed'])
                state['starts'] = _seed_programs(
                    starts, state['seed_selected_snapshot'], character=character,
                    targets=simulation_config['target_count'], engines=identities,
                    capabilities=capabilities, runtime=runtime)
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
                              simulation_config=simulation_config)
            result.update(config=config, simulation_config=simulation_config,
                              character=character, output_root=destination,capabilities=state['capabilities'],
                              profile=json.loads((destination/'profile.json').read_text(encoding='utf-8')),
                              reference_data_key=state.get('reference_data_key'))
            result['elapsed_seconds'] = runtime.elapsed_seconds
            pointer = _store_run(destination, result, state=state)
            _write_json(destination/'result.json', pointer, atomic=True)
            state.update(status=result['status'], phase=result['phase'])
            store.save()
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
        store.publish()
        store.close()


@contextmanager
def _task_lease(destination):
    with (destination/'.runner.lock').open('a+b') as lock:
        if lock.tell()==0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as error:
            raise TaskError('任务正在运行，不能同时恢复') from error
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)


def _run_task(input_path: str | Path, output_root: str | Path | None = None, *, program=None, phase_ms=0,
             mode="optimize", search_config=None, simulation_config=None, cancel_event=None,
             resume=False, _runtime=None, _lease=False, gse_text=None, sequence_name=None,
             version=None, gse_context=None) -> dict:
    """执行角色任务；优化模式是产品默认，single 仅保留前两票快速回归。"""
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
                           _runtime=_runtime, cancel_event=cancel_event)
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
                                     gse_context=gse_context, diagnostic_logging=config["diagnostic_logging"])
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
                                 simulation_config=simulation_config)
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
             version=None, gse_context=None) -> dict:
    if mode != 'optimize' or _lease:
        return _run_task(input_path, output_root, program=program, phase_ms=phase_ms, mode=mode,
                         search_config=search_config, simulation_config=simulation_config,
                         cancel_event=cancel_event, resume=resume, _runtime=_runtime, _lease=_lease,
                         gse_text=gse_text, sequence_name=sequence_name, version=version,
                         gse_context=gse_context)
    from seed_activity import foreground_search
    with foreground_search():
        return _run_task(input_path, output_root, program=program, phase_ms=phase_ms, mode=mode,
                         search_config=search_config, simulation_config=simulation_config,
                         cancel_event=cancel_event, resume=resume, _runtime=_runtime, _lease=_lease,
                         gse_text=gse_text, sequence_name=sequence_name, version=version,
                         gse_context=gse_context)


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
            config = config_for(kwargs.pop('search_config',None) or state['config'])
            if config != config_for(state['config']):
                raise TaskError('恢复配置发生变化，请创建新任务')
            from engine import identity
            try:
                if (state.get('rules') != _rule_hashes() or
                        state.get('engines') != {mode: identity(mode)[1] for mode in ('baseline', 'controlled')}):
                    raise TaskError('恢复任务的版本或编译规则已变化，请创建新任务')
            except (ValueError, OSError) as error:
                raise TaskError(str(error)) from error
            used = float(state.get('elapsed_seconds',0))
            if state.get('native'):
                character = parse_character((destination / 'input.simc').read_text(encoding='utf-8-sig'))
                character = replace(character, spec_id=state['native']['identity']['spec_id'],
                                    race=state['native']['identity']['race'])
                store.recover_reports(character, simulation_config)
            if state.get('status') == 'running':
                penalty = max((max(0, r['allowance'] - max(0,used-r['start']))
                               for r in state.get('inflight',{}).values()),default=0)
                used = min(config['total_budget_seconds'],used+min(30,penalty))
                state.update(elapsed_seconds=used,status='interrupted',inflight={})
                store.save()  # 扣除与恢复标记同一事务，重复恢复不会再次扣除。
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
        runtime = kwargs.pop('_runtime',None) or TaskRuntime(config['total_budget_seconds'],cancel_event=kwargs.pop('cancel_event',None))
        kwargs.pop('cancel_event',None)
        runtime.used_seconds=used
        runtime.budget_seconds=config['total_budget_seconds']
        runtime.phase_limit=runtime.budget_seconds
        return run_task(destination/'input.simc', destination, resume=True, _runtime=runtime, _lease=True,
                        search_config=config, simulation_config=simulation_config, **kwargs)


def resume_task(output_root, **kwargs):
    from seed_activity import foreground_search
    with foreground_search():
        return _resume_task(output_root, **kwargs)


def read_task(output_root, *, include_search_records=False, include_reports=False):
    from result_store import DataReadError
    try:
        return _read_task(output_root, include_search_records=include_search_records,
                          include_reports=include_reports)
    except DataReadError as error:
        raise TaskError(str(error)) from error


def _read_task(output_root, *, include_search_records=False, include_reports=False):
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

    from result_store import iter_rows, one as read_record

    saved = read_record('runs', 'run_id', run_id)
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
    if saved['search_observability']:
        task_result['search_observability'] = decode(saved['search_observability'])
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

    if saved['controlled_data_key']:
        controlled = read_record('batches', 'batch_key', saved['controlled_data_key'])
        if controlled is None:
            raise TaskError('结果中心的受控模拟报告缺失')
        controlled_simulation = dict(summary=dict(dps=controlled['dps'], samples=controlled['samples']),
                                     data_key=saved['controlled_data_key'])
        if include_reports:
            controlled_simulation['report'] = controlled['report']
        task_result['controlled_simulation'] = controlled_simulation

    if include_search_records and search['batch_keys']:
        candidates = {}
        for row in iter_rows('SELECT * FROM candidates WHERE run_id = ?', [run_id]):
            candidates[row['candidate_key']] = row
        sql = ("SELECT batch_key, candidate_key, purpose, condition_key, program_identity, "
               "batch_index, scenario, stats_version, seed, input_seed, iterations, times, "
               "trace, dps, samples, variance, requested_iterations "
               "FROM batches WHERE list_contains(?, batch_key) ORDER BY candidate_key, batch_index")
        grouped = {}
        for row in iter_rows(sql, [search['batch_keys']]):
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
            record = grouped.setdefault(key, dict(key=key, batches=[]))
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


def main():
    parser = argparse.ArgumentParser(description='从单个角色文件生成本机离线序列')
    parser.add_argument('input',type=Path,nargs='?',help='角色导出文件')
    parser.add_argument('--resume',action='store_true',help='按原有清单和预算恢复任务')
    parser.add_argument('--output', type=Path, required=True, help='新任务目录（不会覆盖已有目录）')
    args = parser.parse_args()
    try:
        simulation_config = load_config()
        if args.resume:
            result = resume_task(args.output, simulation_config=simulation_config)
        else:
            if args.input is None:
                parser.error('新任务需要角色文件')
            result = run_task(args.input, args.output, simulation_config=simulation_config)
        print(json.dumps(dict(status=result['status'], result=str(args.output.resolve() / 'result.json')), ensure_ascii=False))
        return 0
    except (TaskError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


__all__ = ["Character", "Equipment", "TaskError", "parse_character", "run_task"]

if __name__ == '__main__':
    raise SystemExit(main())
