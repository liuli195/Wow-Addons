"""仓库升级入口的轻量公开命令检查，不启动模拟或训练。"""
import json
import contextlib
import io
import runpy
from pathlib import Path
import sys
import unittest
import pytest
from test_population_training import memory_ga
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/sim2gse-upgrade/scripts'


class UpgradeSkillTests(unittest.TestCase):
    def test_postcheck_rejects_old_material_index_before_loading_project(self):
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
        error = io.StringIO()
        old = {'scenes': [{'targets': count, 'processed': ['old']} for count in (1, 5)]}
        with patch.object(Path, 'read_text', return_value=json.dumps(old)), \
                patch.object(sys, 'argv', ['postcheck.py', '--project', 'unused',
                                          '--data-project', 'unused', '--evidence', 'index.json']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(postcheck['main'](), 2)
        self.assertIn('旧逐材料证据索引已退役', error.getvalue())

    def test_postcheck_rejects_incomplete_index_before_loading_project(self):
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'read_text', return_value=json.dumps({'scenes': []})), \
                patch.object(sys, 'argv', ['postcheck.py', '--project', 'unused',
                                          '--data-project', 'unused', '--evidence', 'index.json']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(postcheck['main'](), 2)
        self.assertIn('证据索引必须包含单目标及五目标', error.getvalue())

    def test_precheck_rejects_missing_project_without_creating_it(self):
        precheck = runpy.run_path(str(SCRIPTS / 'precheck.py'))
        missing = Path('missing-project')
        with patch.object(Path, 'is_dir', return_value=False), patch.object(Path, 'mkdir') as mkdir, \
                self.assertRaisesRegex(ValueError, '项目目录不存在'):
            precheck['prepare'](missing, missing)
        mkdir.assert_not_called()

    def test_precheck_rejects_foreign_repository(self):
        precheck = runpy.run_path(str(SCRIPTS / 'precheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'is_dir', return_value=True), \
                patch.object(Path, 'is_file', return_value=False), \
                patch.object(sys, 'argv', ['precheck.py', '--project', 'foreign', '--data-project', 'foreign']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(precheck['main'](), 2)
        self.assertIn('不是本仓库', error.getvalue())

    def test_postcheck_rejects_unreadable_index(self):
        with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
            postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
        error = io.StringIO()
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError('absent.json')), \
                patch.object(sys, 'argv', ['postcheck.py', '--project', 'unused',
                                          '--data-project', 'unused', '--evidence', 'absent.json']), \
                contextlib.redirect_stderr(error):
            self.assertEqual(postcheck['main'](), 2)
        self.assertIn('升级后核验未通过', error.getvalue())


if __name__ == '__main__':
    unittest.main()


def test_postcheck_reads_the_real_incremental_archive_layout_without_writing(monkeypatch):
    import sqlite3
    import search
    with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
        postcheck = runpy.run_path(str(SCRIPTS / 'postcheck.py'))
    source = search.TaskStore('/memory/source', connection=sqlite3.connect(':memory:'),
                              reusable_database=':memory:', report_locations={})
    source.state.update(status='completed', archive=[dict(key='winner', program=[['outbreak']], score=100.)])
    source.checkpoint()
    reader = sqlite3.connect(':memory:')
    source.db.backup(reader)
    source.close()
    statements = []
    reader.set_trace_callback(statements.append)
    monkeypatch.setattr(Path, 'is_file', lambda path: True)
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: reader)
    state = postcheck['checkpoint']('/memory/task', ['status', 'archive'])
    assert state == dict(status='completed', archive=[dict(key='winner', program=[['outbreak']], score=100.)])
    assert statements and all(sql.lstrip().upper().startswith('SELECT ') for sql in statements)


@pytest.mark.parametrize('tamper_plan', [False, True])
def test_postcheck_verifies_current_ga_to_page_evidence_and_rejects_changed_plan(memory_ga, monkeypatch, tamper_plan):
    from copy import deepcopy
    import hashlib
    import sqlite3
    import result_store
    import task
    from population_training import _selected
    from program import canonicalize_search_program
    from test_character_export import sample_profile
    raw = sample_profile()
    template_sha = hashlib.sha256(raw.encode()).hexdigest()
    key = dict(specialization_id=252, hero_talent='rider_of_the_apocalypse', target_type='single_target')
    programs = [[['outbreak']], [['death_coil']], [['scourge_strike']], [['outbreak'], ['death_coil']]]
    environment = dict(template=template_sha, engines={}, rules={},
        simulation=dict(target_count=1, scene='single_target'), burst=dict(definition_id='verified'))
    trained = memory_ga(programs=programs, manifest_fields=dict(environment=environment,
        starts=programs, seed=20260912))
    ga = trained.run()
    trained.ready.update(template_sha=template_sha)
    selected = _selected(ga, trained.store, trained.manifest, trained.character, trained.ready, key)
    trained.store.state.update(status='completed', configuration_key=key, capabilities=trained.capabilities,
                               burst=environment['burst'])
    ga['phase'] = 'published'
    trained.store.checkpoint()
    page = memory_ga(programs=[row['program'] for row in selected], formal=True)
    page.run()
    page.store.state.update(phase='done', engines={}, capabilities=page.capabilities,
        native=dict(identity=dict(spec_id=252, race=page.character.race)),
        seed_selected_snapshot=selected, seed_adaptations=[dict(candidate_id=row['candidate_id'],
            derived_program=row['program'], behavior_identity=canonicalize_search_program(
                row['program'], page.capabilities)['identity'], status='accepted') for row in selected])
    coarse = [row for row in page.reports.values() if row['purpose'] == 'search']
    for row in coarse:
        cached = page.store.batch(row['batch_key'])
        cached['storage_group_key'] = row['batch_key']
        page.store.put_batch(row['batch_key'], cached, verified=True)
    page.store.checkpoint()
    scene = dict(targets=1, training_task='/memory/training', configuration_key=key,
        training_condition=trained.condition, selected=[row['candidate_id'] for row in selected],
        page_task='/memory/page', run_id='memory',
        batches=[dict(key=row['batch_key'], group=row['batch_key']) for row in coarse])
    ready = dict(templates=[dict(template='/memory/template', template_sha256=template_sha,
        burst_definition_id='verified')], groups=[dict(template='/memory/template', configuration_key=key)], engines={})
    run = dict(run_id='memory', status='completed', engines={}, condition_key=page.condition,
        simulation_config=page.ready['simulation_config'], config=page.search_config,
        batch_keys=list(page.reports), burst=environment['burst'])
    reports = {**trained.reports, **page.reports}
    monkeypatch.setattr(result_store, 'read_many', lambda table, keys, **kwargs:
                        [deepcopy(reports[value]) for value in keys if value in reports])
    original_connect = sqlite3.connect
    def connect(path, **kwargs):
        assert path.endswith('?mode=ro') and kwargs == {'uri': True}
        connection = original_connect(':memory:')
        (trained if '/training/' in path else page).store.db.backup(connection)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(Path, 'is_file', lambda path: True)
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs:
        json.dumps(trained.manifest) if path.name == 'identity.json' else raw)
    monkeypatch.setattr(task, '_rule_hashes', lambda **kwargs: {})
    with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
        check = runpy.run_path(str(SCRIPTS / 'postcheck.py'))['check_scene']
    def one(table, key, columns, filters=None):
        if table == 'runs':
            return deepcopy(run)
        if table == 'seed_selected':
            return deepcopy(next(row for row in selected if row['candidate_id'] == filters['candidate_id']))
        return deepcopy(reports[filters['batch_key']])
    monkeypatch.setitem(check.__globals__, 'one', one)
    if tamper_plan:
        run['config'] = dict(run['config'], random_seed=1)
        with pytest.raises(ValueError, match='冻结正式GA检查点不一致'):
            check(scene, ready)
    else:
        assert check(scene, ready) == dict(targets=1, generations=2, selected=4, run_id='memory')
