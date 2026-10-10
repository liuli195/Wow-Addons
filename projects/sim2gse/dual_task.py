"""一份冻结输入、两场串行搜索和三个独立导出，复用现有单场任务。"""
import copy
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

import result_store
import task
from runtime import TaskRuntime, TaskCancelled
from search import config_for, digest
from simulation_config import config_for as simulation_config_for

SCENES = (('single_target', 1), ('aoe', 5))
PARENT_SCHEMA = dict(parent_id='VARCHAR', status='VARCHAR', phase='VARCHAR', error='VARCHAR',
    input_sha256='VARCHAR', definition_id='VARCHAR', spec_id='UBIGINT', config='JSON',
    simulation_config='JSON', rules='JSON', engines='JSON', preparation_seconds='DOUBLE',
    packaging_seconds='DOUBLE', single_target_status='VARCHAR', aoe_status='VARCHAR',
    single_target_export='VARCHAR', aoe_export='VARCHAR', burst_export='VARCHAR',
    collection_text='VARCHAR', burst_instructions='VARCHAR',
    single_target_path='VARCHAR', aoe_path='VARCHAR')
EXPORT_SCHEMA = dict(parent_id='VARCHAR', purpose='VARCHAR', behavior_identity='VARCHAR',
                     name='VARCHAR', text='VARCHAR', simulation='VARCHAR', game_validation='VARCHAR')


def _decode(value):
    return json.loads(value) if isinstance(value, str) else value


def _save(row):
    try:
        result_store.write('dual_tasks', row['parent_id'], [row], schema=PARENT_SCHEMA)
    except Exception as error:
        raise task.TaskError('共享存储写入失败，请恢复存储后继续任务') from error


def _load(destination):
    try:
        pointer = json.loads((destination / 'dual.json').read_text(encoding='utf-8'))
        rows = result_store.read_records('dual_tasks', pointer['parent_id'])
    except result_store.DataReadError as error:
        raise task.TaskError('共享存储不可读取，请恢复存储后重新读取任务') from error
    except (OSError, ValueError, KeyError) as error:
        raise task.TaskError('双场任务记录不可读取') from error
    if len(rows) != 1 or rows[0]['parent_id'] != pointer['parent_id']:
        raise task.TaskError('双场任务登记不完整')
    row = rows[0]
    for key in ('config', 'simulation_config', 'rules', 'engines'):
        row[key] = _decode(row[key])
    return row


def _verify(row, destination):
    from burst import load
    from engine import identity
    if hashlib.sha256((destination / 'input.original.simc').read_bytes()).hexdigest() != row['input_sha256']:
        raise task.TaskError('双场任务的冻结输入已变化，请创建新任务')
    if load(row['spec_id'])['definition_id'] != row['definition_id']:
        raise task.TaskError('双场任务的爆发定义已变化，请创建新任务')
    if row['rules'] != task._rule_hashes() or row['engines'] != {
            mode: identity(mode)[1] for mode in ('baseline', 'controlled')}:
        raise task.TaskError('双场任务的版本或规则已变化，请创建新任务')


def _export(candidate, purpose, native_identity, destination, runtime):
    from gse_import import decode_import
    from program import compile_program
    program = copy.deepcopy(candidate['program'])
    program['metadata']['purpose'] = purpose
    compiled = compile_program(program, destination, identity=native_identity, runtime=runtime)
    before = next(iter(decode_import(candidate['text'])['sequences'].values()))
    after = next(iter(decode_import(compiled['text'])['sequences'].values()))
    if before['Versions'] != after['Versions'] or before['Default'] != after['Default']:
        raise task.TaskError('独立用途名称改变了序列行为')
    compiled['simulation'] = candidate['simulation']
    return compiled


def _publish_export(row, purpose, compiled):
    from sequence import behavior_key
    behavior = behavior_key(compiled)
    key = digest(dict(parent=row['parent_id'], purpose=purpose, behavior=behavior))
    result_store.write('sequence_exports', key, [dict(parent_id=row['parent_id'], purpose=purpose,
        behavior_identity=behavior, name=compiled['name'], text=compiled['text'],
        simulation=compiled['simulation'], game_validation=compiled['game_validation'])], schema=EXPORT_SCHEMA)
    row[purpose + '_export'] = key
    _save(row)


def _child_matches(row, child, targets):
    if (child['profile']['input_original_sha256'] != row['input_sha256']
            or child['simulation_config'] != dict(row['simulation_config'], target_count=targets)
            or config_for(child['config']) != config_for(row['config'])
            or (child.get('burst') or {}).get('definition_id') != row['definition_id']):
        raise task.TaskError('父任务与子任务的冻结条件不一致')


class DualHandle:
    def __init__(self, destination):
        self.output_root = destination
        self.cancel_event = threading.Event()
        self.thread = None
        self.error = None

    @property
    def done(self):
        return not self.thread.is_alive()

    def join(self, timeout=None):
        self.thread.join(timeout)


def _worker(handle):
    destination = handle.output_root
    try:
        row = _load(destination)
    except BaseException as error:
        handle.error = error
        return
    lease = task._task_lease(destination)
    try:
        lease.__enter__()
    except BaseException as error:
        handle.error = error
        return
    try:
        from seed_activity import foreground_search
        with foreground_search():
            _verify(row, destination)
            row.update(status='running', error=None)
            _save(row)
            compiled_exports = {}
            native_identity = None
            for purpose, targets in SCENES:
                if handle.cancel_event.is_set():
                    raise TaskCancelled('已取消；等待的场景未启动')
                _verify(row, destination)
                child_path = destination / row[purpose + '_path']
                row['phase'] = purpose
                row[purpose + '_status'] = 'running'
                _save(row)
                if (child_path / 'result.json').exists():
                    child = task.read_task(child_path)
                    if child.get('status') != 'completed':
                        child = task.resume_task(child_path, cancel_event=handle.cancel_event,
                            simulation_config=dict(row['simulation_config'], target_count=targets))
                elif (child_path / 'task.sqlite3').exists():
                    child = task.resume_task(child_path, cancel_event=handle.cancel_event,
                        simulation_config=dict(row['simulation_config'], target_count=targets))
                else:
                    if child_path.exists():
                        # Preparation stopped before the durable search state existed. Preserve its files.
                        attempt = 1
                        while (destination / f'{purpose[0]}-{attempt}').exists():
                            attempt += 1
                        row[purpose + '_path'] = f'{purpose[0]}-{attempt}'
                        _save(row)
                        child_path = destination / row[purpose + '_path']
                    child = task.run_task(destination / 'input.original.simc', child_path,
                        use_burst=True, cancel_event=handle.cancel_event, search_config=row['config'],
                        simulation_config=dict(row['simulation_config'], target_count=targets))
                if child.get('status') == 'cancelled':
                    raise TaskCancelled('已取消；已完成的场景保留')
                if child.get('status') != 'completed' or not child.get('candidate'):
                    raise task.TaskError('当前场景尚未完成有效搜索')
                _child_matches(row, child, targets)
                row[purpose + '_status'] = 'completed'
                _save(row)
                runtime = TaskRuntime(600, cancel_event=handle.cancel_event)
                native_identity = child['native_reference']['identity']
                started = time.monotonic()
                compiled = _export(child['candidate'], purpose, native_identity,
                                   destination / 'exports' / purpose, runtime)
                _publish_export(row, purpose, compiled)
                compiled_exports[purpose] = compiled
                if 'burst' not in compiled_exports:
                    compiled = _export(child['burst']['candidate'], 'burst', native_identity,
                                       destination / 'exports' / 'burst', runtime)
                    _publish_export(row, 'burst', compiled)
                    compiled_exports['burst'] = compiled
                row['packaging_seconds'] += time.monotonic() - started
                _save(row)
            if handle.cancel_event.is_set():
                raise TaskCancelled('已取消；三个单份结果已保留')
            _verify(row, destination)
            row['phase'] = 'package'
            _save(row)
            from codec import collection
            started = time.monotonic()
            row['collection_text'] = collection([compiled_exports[key] for key in ('single_target', 'aoe', 'burst')],
                destination / 'collection', identity=native_identity,
                runtime=TaskRuntime(600, cancel_event=handle.cancel_event))
            row['packaging_seconds'] += time.monotonic() - started
            row.update(status='completed', phase='done')
            _save(row)
    except TaskCancelled as error:
        row.update(status='cancelled', error=str(error))
        try:
            _save(row)
        except BaseException as storage_error:
            handle.error = storage_error
    except BaseException as error:
        row.update(status='partial' if any(row[purpose + '_status'] == 'completed'
                   for purpose, _ in SCENES) else 'failed', error=str(error))
        try:
            _save(row)
        except BaseException as storage_error:
            handle.error = storage_error
    finally:
        lease.__exit__(None, None, None)


def start(input_path, destination, *, search_config=None, simulation_config=None):
    started = time.monotonic()
    from burst import select_definition
    from engine import identity
    destination = Path(destination).resolve()
    original, text = task._read_utf8(Path(input_path), description='角色输入')
    simulation_config = simulation_config_for(simulation_config)
    config = config_for(dict(search_config or {}, input_interval_ms=(search_config or {}).get('input_interval_ms', 200)))
    effective = task._effective_input_bytes(original, text, simulation_config)
    definition = select_definition(task.parse_character(effective.decode('utf-8')))
    row = dict(parent_id=uuid.uuid4().hex, status='starting', phase='prepare', error=None,
               input_sha256=hashlib.sha256(original).hexdigest(), definition_id=definition['definition_id'],
               spec_id=definition['spec_id'], config=config, simulation_config=simulation_config,
               rules=task._rule_hashes(), engines={mode: identity(mode)[1] for mode in ('baseline', 'controlled')},
               preparation_seconds=time.monotonic() - started, packaging_seconds=0., collection_text=None,
               burst_instructions=definition['instructions'], single_target_path='single_target', aoe_path='aoe',
               single_target_status='pending', aoe_status='pending', single_target_export=None,
               aoe_export=None, burst_export=None)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'input.original.simc').write_bytes(original)
    task._write_json(destination / 'dual.json', dict(parent_id=row['parent_id']), atomic=True)
    _save(row)
    return _launch(destination)


def _launch(destination):
    handle = DualHandle(destination)
    handle.thread = threading.Thread(target=_worker, args=(handle,), daemon=True, name='sim2gse-dual')
    handle.thread.start()
    return handle


def resume(destination):
    destination = Path(destination).resolve()
    with task._task_lease(destination):
        _verify(_load(destination), destination)
    return _launch(destination)


def _is_running(destination):
    try:
        with task._task_lease(destination):
            return False
    except task.TaskError:
        return True


def cancel_saved(destination):
    destination = Path(destination).resolve()
    with task._task_lease(destination):
        row = _load(destination)
        if row['status'] in ('starting', 'running', 'stopping'):
            row.update(status='cancelled', error='执行进程已退出，已保留完成结果')
            _save(row)
    return read(destination)


def read(destination, *, active=None):
    destination = Path(destination).resolve()
    row = _load(destination)
    recoverable = row['status'] in ('cancelled', 'partial', 'failed', 'interrupted')
    if row['status'] in ('starting', 'running', 'stopping') and not (active if active is not None else _is_running(destination)):
        row.update(status='interrupted', error='执行进程已退出，可以继续未完成的任务')
        recoverable = True
    scenes, exports = [], {}
    elapsed, completed, active_progress = 0., 0, 0.
    for purpose, targets in SCENES:
        child_path = destination / row[purpose + '_path']
        status = row[purpose + '_status']
        if status == 'running' and row['status'] in ('failed', 'interrupted', 'cancelled', 'partial'):
            status = 'failed' if row['status'] == 'failed' else 'incomplete'
        scene = dict(purpose=purpose, target_count=targets, status=status,
                     input_sha256=row['input_sha256'], total_budget_seconds=row['config']['total_budget_seconds'],
                     elapsed_seconds=0., progress=0.)
        if (child_path / 'profile.json').exists():
            child = task.read_task(child_path)
            scene['elapsed_seconds'] = float(child.get('elapsed_seconds', 0))
            scene['progress'] = min(1., scene['elapsed_seconds'] / scene['total_budget_seconds'])
            if child.get('search_result'):
                scene['search_result'] = child['search_result']
        if status == 'completed':
            completed += 1
            scene['progress'] = 1.
        elif status == 'running':
            active_progress = scene['progress']
        elapsed += scene['elapsed_seconds']
        scenes.append(scene)
    for purpose in ('single_target', 'aoe', 'burst'):
        key = row[purpose + '_export']
        if key:
            records = result_store.read_records('sequence_exports', key)
            if len(records) != 1 or records[0]['parent_id'] != row['parent_id'] or records[0]['purpose'] != purpose:
                raise task.TaskError('双场导出记录缺失或身份不符')
            exports[purpose] = records[0]['text']
    return dict(status=row['status'], phase=row['phase'], error=row['error'], scenes=scenes,
                exports=exports, recoverable=recoverable, collection_text=row['collection_text'], collection_ready=bool(row['collection_text']),
                result_ready=bool(exports), input_interval_ms=row['config']['input_interval_ms'],
                progress=1. if row['status'] == 'completed' else (completed + active_progress) / 2,
                elapsed_seconds=elapsed + row['preparation_seconds'] + row['packaging_seconds'],
                preparation_seconds=row['preparation_seconds'], packaging_seconds=row['packaging_seconds'],
                definition_id=row['definition_id'], total_budget_seconds=2 * row['config']['total_budget_seconds'],
                burst_instructions=row['burst_instructions'], evidence_status='search_result',
                result_note='未进行最终独立复测；两个循环分别搜索，爆发独立按键。已通过本机导入编译，游戏效果尚待验证。')


def cancel(handle):
    handle.cancel_event.set()
    handle.join(2.5)
    state = read(handle.output_root)
    if not handle.done:
        state['status'] = 'stopping'
    return state
