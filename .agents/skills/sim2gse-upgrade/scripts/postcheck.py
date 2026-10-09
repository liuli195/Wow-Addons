"""只读核验指定训练、入选及页面重算证据；索引只定位真实记录。"""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import sys

from precheck import prepare


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checkpoint(folder, fields):
    path = Path(folder).resolve() / 'task.sqlite3'
    require(path.is_file(), '任务检查点不存在: ' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        placeholders = ','.join('?' for _ in fields)
        rows = connection.execute('SELECT key,value FROM state_fields WHERE key IN (' +
                                  placeholders + ')', fields).fetchall()
        result = {key: json.loads(value) for key, value in rows}
        require(set(result) == set(fields), '任务检查点缺少核验字段')
        return result
    finally:
        connection.close()


def one(table, key, columns, filters=None):
    import result_store
    rows = result_store.read_records(table, key, columns=columns, filters=filters)
    require(len(rows) == 1, '指定记录缺失或不唯一: ' + table + '/' + key)
    return rows[0]


def valid_scores(values):
    return (isinstance(values, list) and len(values) == 3 and
            all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
                for value in values))


def check_scene(scene, ready):
    from program import canonicalize_search_program
    from search import digest
    from task import _rule_hashes
    from engine import COMMON, ROOT
    from seed_training import RETEST_SEEDS, TRAINING_VERSION, search_program
    targets = scene['targets']
    scope = f'deathknight-unholy-{targets}-burst'
    run = one('runs', scene['run_id'], ['run_id', 'status', 'engines', 'condition_key',
              'simulation_config', 'batch_keys', 'burst'])
    require(decode(run['engines']) == ready['engines'], '页面引擎身份过期')
    require(len(scene['processed']) == 3 and len(set(scene['processed'])) == 3,
            '每场必须指定两类合法材料及一类拒绝材料')
    completed = {}
    rejected = 0
    for candidate_id in scene['processed']:
        row = one('seed_processed', scope,
                  ['candidate_id', 'condition', 'status', 'stop_reason', 'scores',
                   'initial_scores', 'task_path', 'initial_program', 'program', 'family', 'error'],
                  {'candidate_id': candidate_id, 'condition': scene['training_condition']})
        if row['status'] == 'rejected':
            require(bool(row['error']), '拒绝材料缺少原因')
            rejected += 1
            continue
        require(row['status'] == 'completed' and row['stop_reason'] in ('no_improvement', 'space_stalled'),
                '训练没有正式收敛')
        require(valid_scores(row['scores']) and valid_scores(row['initial_scores']), '独立复测成绩缺项')
        state = checkpoint(row['task_path'], ['config', 'training_condition',
                           'training_candidate_id', 'burst'])
        current_condition = digest(dict(version=TRAINING_VERSION, template=ready['template_sha256'],
            engines=ready['engines'], config=state['config'],
            simulation={'target_count': targets, 'enable_omnium_talents': True},
            retest=RETEST_SEEDS, effective_options=COMMON, rules=_rule_hashes(relative_to=ROOT),
            task_category='burst_free_training', burst=state['burst']))
        require(row['condition'] == current_condition, '训练引擎身份或条件过期')
        require(state['training_condition'] == row['condition'] and
                state['training_candidate_id'] == candidate_id, '训练记录与检查点不一致')
        require(state['burst']['definition_id'] == ready['burst_definition_id'], '训练爆发定义过期')
        for name, scores in [('retest-initial', row['initial_scores']), ('retest-final', row['scores'])]:
            for seed, score in zip(RETEST_SEEDS, scores):
                key = digest(dict(folder=str(Path(row['task_path']) / name), seed=seed))
                batch = one('batches', key, ['purpose', 'seed', 'samples', 'dps'])
                require(batch['purpose'] == 'seed_retest' and batch['seed'] == seed and
                        batch['samples'] >= 2 and batch['dps'] == score, '独立复测真实批次缺失或不一致')
        completed[candidate_id] = row
    require(len(completed) == 2 and rejected == 1, '缺少两类成功材料或拒绝材料')
    require(len({row['family'] for row in completed.values()}) == 2, '成功材料须属于两类')
    require(bool(scene['selected']), '缺少指定入选记录')
    selected = []
    for candidate_id in scene['selected']:
        require(candidate_id in completed, '入选材料不属于本次成功训练')
        row = one('seed_selected', scope,
                  ['candidate_id', 'condition', 'class_name', 'spec', 'targets', 'program',
                   'scores', 'template_sha256', 'engines'], {'candidate_id': candidate_id})
        require(decode(row['engines']) == ready['engines'], '入选引擎身份过期')
        require(row['condition'] == scene['training_condition'] and row['targets'] == targets and
                row['class_name'] == 'deathknight' and row['spec'] == 'unholy' and
                row['template_sha256'] == ready['template_sha256'], '入选角色或条件不一致')
        trained = completed[candidate_id]
        require(any(decode(row['program']) == decode(trained[program]) and row['scores'] == trained[scores]
                    for program, scores in [('program', 'scores'), ('initial_program', 'initial_scores')]),
                '入选程序与独立复测不一致')
        selected.append(row)
    require(run['status'] == 'offline_ready' and
            decode(run['simulation_config'])['target_count'] == targets, '页面任务未完成或目标数不一致')
    require(decode(run['burst'])['definition_id'] == ready['burst_definition_id'], '页面爆发定义过期')
    state = checkpoint(scene['page_task'], ['run_id', 'engines', 'condition', 'capabilities',
                       'seed_selected_snapshot', 'starts'])
    require(state['run_id'] == run['run_id'] and state['engines'] == ready['engines'] and
            state['condition'] == run['condition_key'], '页面记录与检查点不一致')
    require(bool(scene['batches']), '缺少页面重新评分批次')
    scored = set()
    for locator in scene['batches']:
        path = Path(scene['page_task']).resolve() / 'task.sqlite3'
        connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            saved = connection.execute('SELECT value FROM batches WHERE key=?', (locator['key'],)).fetchone()
            require(saved is not None, '页面本地批次缺失')
            group = json.loads(saved[0])['storage_group_key']
        finally:
            connection.close()
        require(group == locator['group'], '批次存储组与任务记录不一致')
        row = one('batches', group, ['batch_key', 'run_id', 'condition_key',
                  'candidate_key', 'program_identity', 'purpose', 'dps', 'samples'],
                  {'batch_key': locator['key']})
        require(row['batch_key'] in run['batch_keys'] and row['run_id'] == run['run_id'] and
                row['condition_key'] == run['condition_key'] and row['purpose'] == 'search' and
                row['samples'] >= 2 and math.isfinite(row['dps']) and row['dps'] > 0,
                '页面批次缺少有效的新条件评分')
        scored.add((row['candidate_key'], json.dumps(decode(row['program_identity']), sort_keys=True)))
    for row in selected:
        frozen = [item for item in state['seed_selected_snapshot']
                  if item['candidate_id'] == row['candidate_id']]
        require(len(frozen) == 1 and all(decode(frozen[0][key]) == decode(value)
                    for key, value in row.items()), '页面未冻结本次入选记录')
        canonical = canonicalize_search_program(decode(row['program']), state['capabilities'])
        candidate_key = canonical['identity']
        data_key = digest(dict(run_id=run['run_id'], candidate_key=candidate_key))
        candidate = one('candidates', data_key, ['run_id', 'candidate_key', 'program'])
        require(candidate['run_id'] == run['run_id'] and candidate['candidate_key'] == candidate_key and
                canonicalize_search_program(search_program(decode(candidate['program'])), state['capabilities'])['identity'] == candidate_key,
                '页面实际候选记录与入选程序不一致')
        require(any(canonicalize_search_program(program, state['capabilities'])['identity'] == canonical['identity']
                    for program in state['starts']), '页面未实际采用入选起点')
        require((canonical['identity'], json.dumps(canonical['form'], sort_keys=True)) in scored,
                '页面没有按新条件重新评分入选程序')
    return {'targets': targets, 'trained': len(completed), 'rejected': rejected,
            'selected': len(selected), 'run_id': run['run_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--data-project', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        index = json.loads(args.evidence.read_text(encoding='utf-8'))
        require(isinstance(index, dict) and isinstance(index.get('scenes'), list) and
                sorted(scene.get('targets', 0) for scene in index['scenes']) == [1, 5],
                '证据索引必须包含单目标及五目标')
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
