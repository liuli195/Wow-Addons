"""只读核验指定训练、入选及页面重算证据；索引只定位真实记录。"""
import argparse
import json
import math
import hashlib
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import sqlite3
import sys

from precheck import prepare


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checkpoint(folder, fields, *, optional=()):
    path = Path(folder).resolve() / 'task.sqlite3'
    require(path.is_file(), '任务检查点不存在: ' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        seal = connection.execute("SELECT value FROM state_fields WHERE key='memory_checkpoint'").fetchone()
        if seal and decode(seal[0]).get('version') == 2:
            from search import TaskStore
            state = TaskStore.load_state(connection)
            require(set(fields) <= state.keys(), '任务检查点缺少核验字段')
            return {key: state[key] for key in [*fields, *optional] if key in state}
        scalar_fields = [key for key in [*fields, *optional] if key != 'archive']
        placeholders = ','.join('?' for _ in scalar_fields)
        rows = connection.execute('SELECT key,value FROM state_fields WHERE key IN (' +
                                  placeholders + ')', scalar_fields).fetchall()
        result = {key: json.loads(value) for key, value in rows}
        if 'archive' in fields:
            result['archive'] = [json.loads(value) for (value,) in connection.execute(
                'SELECT value FROM state_archive ORDER BY ordinal')]
        require(set(fields) <= set(result), '任务检查点缺少核验字段')
        return result
    finally:
        connection.close()


def batch_checkpoint(folder, key):
    """只读取得业务键的既有报告位置；旧单条可以没有组凭据。"""
    path = Path(folder).resolve() / 'task.sqlite3'
    require(path.is_file(), '任务检查点不存在: ' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        from search import checkpoint_batch
        return checkpoint_batch(connection, key)
    finally:
        connection.close()


def one(table, key, columns, filters=None):
    import result_store
    rows = result_store.read_records(table, key, columns=columns, filters=filters)
    require(len(rows) == 1, '指定记录缺失或不唯一: ' + table + '/' + key)
    return rows[0]


def check_scene(scene, ready):
    from program import canonicalize_search_program
    from search import digest, _validate_saved_batch
    from seed_training import shared_scope, template_character, SELECTED_V2_SCHEMA
    from population_training import ALGORITHM, _selected, _stage_plan
    from task import _rule_hashes, parse_character
    from engine import ROOT
    from formal_search import contract_for
    def selected_record(row):
        return {name: decode(value) if SELECTED_V2_SCHEMA.get(name) == 'JSON' else value
                for name, value in row.items()}

    targets, folder = scene['targets'], Path(scene['training_task'])
    manifest = json.loads((folder / 'identity.json').read_text(encoding='utf-8'))
    environment, key = manifest['environment'], scene['configuration_key']
    template = next((row for row in ready['templates']
                     if row['template_sha256'] == environment['template']), None)
    require(template is not None and any(group['configuration_key'] == key and
            group['template'] == template['template'] for group in ready['groups']),
            '训练模板或三元范围不属于当前受检构建')
    require(environment['engines'] == ready['engines'] and
            environment['rules'] == _rule_hashes(relative_to=ROOT) and
            environment['simulation']['target_count'] == targets and
            environment['simulation']['scene'] == key['target_type'] and
            environment['burst']['definition_id'] == template['burst_definition_id'],
            '训练引擎、规则、目标或爆发身份过期')
    text = (folder / 'standard.simc').read_text(encoding='utf-8')
    require(hashlib.sha256(text.encode()).hexdigest() == environment['template'], '训练角色副本变化')
    character = replace(template_character(text), spec_id=key['specialization_id'])
    state = checkpoint(folder, ['status', 'configuration_key', 'ga', 'archive', 'capabilities',
                                'starts', 'training_evaluation_plan', 'burst'],
                       optional=('execution_storage_version', 'evidence_storage'))
    ga = state['ga']
    require(state['status'] == 'completed' and ga['phase'] == 'published' and
            ga['algorithm'] == ALGORITHM and state['configuration_key'] == key and
            state['starts'] == manifest['starts'] and state['burst'] == environment['burst'] and
            state['training_evaluation_plan'] == manifest['stage_plan'] ==
            _stage_plan(manifest['training_config'], manifest['seed']) and
            ga['stagnant'] >= manifest['training_config']['stagnation_generations'],
            '训练检查点没有完成冻结GA收敛与发布')
    require(digest(manifest) == scene['training_condition'], '训练条件与原清单不一致')
    # Only existing read-only SQLite queries; never initialize TaskStore or invoke training.
    store = SimpleNamespace(state=state, batch=lambda batch_key: batch_checkpoint(folder, batch_key))
    expected = _selected(ga, store, manifest, character,
        dict(context=dict(capabilities=state['capabilities']), template_sha=environment['template'],
             engines=ready['engines'], simulation_config=environment['simulation']), key)
    require(len(scene['selected']) == 4 and set(scene['selected']) ==
            {row['candidate_id'] for row in expected}, '索引必须指向本次完整四条GA成果')
    selected = []
    for expected_row in expected:
        scope = shared_scope(key, state['capabilities']['search_syntax']) if state.get('execution_storage_version') == 3 else shared_scope(key)
        row = one('seed_selected', scope, list(SELECTED_V2_SCHEMA),
                  {'candidate_id': expected_row['candidate_id'], 'family': 'ga'})
        row = selected_record(row)
        require(row == expected_row, '入选四条与完整五场景复测和代表选择不一致')
        selected.append(row)
    if state.get('execution_storage_version') == 3:
        from population_training import verify_selected_evidence
        verify_selected_evidence(selected)

    run = one('runs', scene['run_id'], ['run_id', 'status', 'engines', 'condition_key',
              'simulation_config', 'config', 'batch_keys', 'burst', 'search_metrics'])
    require(run['status'] == 'completed' and decode(run['engines']) == ready['engines'] and
            decode(run['simulation_config'])['target_count'] == targets and
            decode(run['burst'])['definition_id'] == template['burst_definition_id'],
            '页面任务未完成或引擎、目标、爆发不一致')
    state = checkpoint(scene['page_task'], ['run_id', 'engines', 'condition', 'capabilities', 'phase',
        'seed_selected_snapshot', 'seed_adaptations', 'starts', 'formal_search', 'native'])
    require(state['phase'] == 'done' and state['run_id'] == run['run_id'] and
            state['engines'] == ready['engines'] and state['condition'] == run['condition_key'] and
            state['formal_search'] == contract_for(decode(run['config'])),
            '页面记录与冻结正式GA检查点不一致')
    character = replace(parse_character((Path(scene['page_task']) / 'input.simc').read_text(encoding='utf-8')),
        spec_id=state['native']['identity']['spec_id'], race=state['native']['identity']['race'])
    require(bool(scene['batches']), '缺少页面重新评分批次')
    scored = set()
    plan = state['formal_search']['stage_plan']['search']
    storage = (decode(run.get('search_metrics')) or {}).get('evidence_storage')
    archive = None
    if storage and storage.get('version') == 3:
        from result_store import read_search_records
        archive = read_search_records(storage, run['run_id'], condition=run['condition_key'])
        archived_batches = {batch['data_key']: (row, batch) for row in archive for batch in row['batches']}
    for locator in scene['batches']:
        saved = batch_checkpoint(scene['page_task'], locator['key'])
        if archive is not None:
            require(saved is not None and saved.get('status') == 'success' and
                    locator['group'] == storage['archive_group'] and locator['key'] in archived_batches,
                    '页面轻量成绩凭据或归档位置不一致')
            source, batch = archived_batches[locator['key']]
            request = saved['request']
            require(digest(request) == locator['key'] and batch['request'] == request and
                    all(batch[field] == saved[field] for field in ('dps', 'samples', 'variance')) and
                    request['condition'] == run['condition_key'] and request['purpose'] == 'search' and
                    request['iterations'] == plan['iterations'] and request['seed'] == plan['seeds'][0] and
                    request['program'] == canonicalize_search_program(source['program'], state['capabilities'])['form'] and
                    canonicalize_search_program(source['program'], state['capabilities'])['identity'] ==
                    request['behavior_identity'] and math.isfinite(batch['dps']) and batch['dps'] > 0,
                    '页面轻量成绩缺少冻结GA计划下的新条件评分')
            scored.add(request['behavior_identity'])
            continue
        require(saved is not None and saved.get('status') == 'success' and
                saved['storage_group_key'] == locator['group'], '页面可靠批次或存储组不一致')
        row = one('batches', locator['group'], None, {'batch_key': locator['key']})
        request = saved['request']
        require(digest(request) == locator['key'] and row['batch_key'] in run['batch_keys'] and
                row['run_id'] == run['run_id'] and request['condition'] == run['condition_key'] and
                request['purpose'] == 'search' and request['iterations'] == plan['iterations'] and
                request['seed'] == plan['seeds'][0] and math.isfinite(row['dps']) and row['dps'] > 0,
                '页面批次缺少冻结GA计划下的新条件评分')
        _validate_saved_batch(row, locator['key'], saved, character, 0, 'nominal',
                              decode(run['simulation_config']))
        scored.add(request['behavior_identity'])
    for row in selected:
        frozen = [selected_record(item) for item in state['seed_selected_snapshot']
                  if item['candidate_id'] == row['candidate_id']]
        require(frozen == [row], '页面未冻结本次入选记录')
        adaptations = [item for item in state['seed_adaptations'] if item['candidate_id'] == row['candidate_id']]
        require(len(adaptations) == 1 and adaptations[0]['status'] in ('accepted', 'duplicate'),
                '页面没有接受本次入选程序的当前适配')
        canonical = canonicalize_search_program(adaptations[0]['derived_program'], state['capabilities'])
        require(canonical['identity'] == adaptations[0]['behavior_identity'] and
                any(canonicalize_search_program(program, state['capabilities'])['identity'] == canonical['identity']
                    for program in state['starts']) and canonical['identity'] in scored,
                '页面未实际采用并按新条件重新评分派生起点')
    return {'targets': targets, 'generations': ga['generation'], 'selected': len(selected), 'run_id': run['run_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--data-project', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        index = json.loads(args.evidence.read_text(encoding='utf-8'))
        require(isinstance(index, dict) and isinstance(index.get('scenes'), list) and
                all(isinstance(scene, dict) for scene in index['scenes']) and
                sorted(scene.get('targets', 0) for scene in index['scenes']) == [1, 5],
                '证据索引必须包含单目标及五目标')
        require(all('processed' not in scene and 'training_task' in scene and
                    'configuration_key' in scene for scene in index['scenes']),
                '旧逐材料证据索引已退役；请指定GA任务与三元范围')
        prepare(args.project, args.data_project)
        from seed_training import check_training
        ready = check_training()
        scenes = [check_scene(scene, ready) for scene in index['scenes']]
        print(json.dumps({'status': 'passed', 'scenes': scenes}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, sqlite3.Error) as error:
        print('升级后核验未通过: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
