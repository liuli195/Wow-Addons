"""Reference refresh is exercised through the material command."""
import json

import pytest
from test_seed_training import prepared_input


def test_refresh_preflight_lists_four_scopes_without_native_or_publication(monkeypatch, capsys):
    import result_store
    import seed_training as seeds
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(seeds, 'registry_rows', lambda: [])
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(status='ready', groups=[
        dict(configuration_key=dict(specialization_id=252, hero_talent=hero,
                                    target_type='single_target' if targets == 1 else 'aoe'))
        for hero in ('rider_of_the_apocalypse', 'sanlayn') for targets in (1, 5)]))
    monkeypatch.setattr(result_store, 'write', lambda *a, **kw: pytest.fail('preflight must not publish'))
    assert seeds.main(['--project', '/memory', 'refresh-references', '--workspace', '/memory/run',
                       '--simc-only', '--check-only']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'preflight'
    assert result['target'] == 30
    assert len(result['groups']) == 4
    assert result['native_starts'] == 0 and result['published'] is False


@pytest.mark.real
def test_plugin_preflight_exports_only_static_reference_and_preserves_duplicate_origins(tmp_path, monkeypatch, capsys):
    import result_store
    import seed_training as seeds
    plugin = tmp_path / 'GearInsight_Data'
    plugin.mkdir()
    source = plugin / 'RotationData.lua'
    source.write_text('GearInsightRotation = {["DEATHKNIGHT/UNHOLY"]={specID=252,'
        'raid={opener={{player="a",seq={77575,47541}},{player="b",seq={77575,47541}}}},'
        'mplus={st={opener={{player="c",seq={47541,77575}}}}}}}\n'
        'GearInsightRotation.notes = {[77575]={cn="疾病"}}', encoding='utf-8')
    (plugin / 'GearInsight_Data.toc').write_text('## Version: 1.0\n', encoding='utf-8')
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(groups=[]))
    monkeypatch.setattr(result_store, 'write', lambda *a, **kw: pytest.fail('preflight cannot publish'))
    args = ['--project', str(tmp_path), 'refresh-references', '--workspace', str(tmp_path / 'run'),
            '--plugin-dir', str(plugin), '--check-only']
    assert seeds.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['plugin']['raw_records'] == 3 and result['plugin']['distinct_sequences'] == 2
    assert sorted(len(r['origins']) for r in result['plugin']['records']) == [1, 2]
    assert source.read_text(encoding='utf-8').startswith('GearInsightRotation =')
    source.write_text('GearInsightRotation = {}; os.execute("invalid")', encoding='utf-8')
    assert seeds.main(args) == 2
    error = capsys.readouterr().err
    assert '静态' in error or '格式' in error


@pytest.mark.real
@pytest.mark.parametrize('limit', ['input', 'depth', 'records', 'output', 'instructions'])
def test_plugin_command_limits_fail_without_publication(tmp_path, monkeypatch, capsys, limit):
    import result_store, seed_training as seeds
    plugin = tmp_path / 'plugin'
    plugin.mkdir()
    if limit == 'input':
        text, message = ' ' * (2 * 1024 * 1024 + 1), '读取上限'
    elif limit == 'depth':
        text, message = 'GearInsightRotation={' + 'x={' * 33 + '}' * 34, '嵌套过深'
    elif limit == 'records':
        text = 'GearInsightRotation={["DEATHKNIGHT/UNHOLY"]={specID=252,opener={' + '{seq={77575}},' * 257 + '}}}'
        message = 'too many openers'
    elif limit == 'output':
        text = ('GearInsightRotation={["DEATHKNIGHT/UNHOLY"]={specID=252,large="'
                + 'x' * (1024 * 1024 + 100) + '",opener={{seq={77575}},{seq={47541}}}}}')
        message = 'json output limit'
    else:
        text = ('GearInsightRotation={["DEATHKNIGHT/UNHOLY"]={specID=252,opener={{seq={77575},tal={flat={'
                + '1,' * 300000 + '}}}}}}')
        message = 'reference instruction limit'
    (plugin / 'RotationData.lua').write_text(text, encoding='utf-8')
    (plugin / 'GearInsight_Data.toc').write_text('## Version: fixture\n', encoding='utf-8')
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(groups=[]))
    monkeypatch.setattr(result_store, 'write', lambda *a, **kw: pytest.fail('limits must not publish'))
    assert seeds.main(['--project', str(tmp_path), 'refresh-references', '--workspace', str(tmp_path / 'run'),
                       '--plugin-dir', str(plugin), '--check-only']) == 2
    assert message in capsys.readouterr().err


def test_preparation_filters_new_sources_by_actual_group_before_dedup(prepared_input):
    import seed_training as seeds
    shared = prepared_input.source('legacy', [['outbreak']])
    other = prepared_input.source('other', [['death_coil']])
    other['allowed_groups'] = [dict(specialization_id=252, hero_talent='sanlayn',
                                    target_type='single_target', target_count=1)]
    ready = seeds.ensure_prepared('/profile', 1, '/memory', sources=[shared, other],
                                  inputs=prepared_input.inputs)
    assert [row['source_id'] for row in ready['entries']] == ['legacy']


def test_prepared_cache_roundtrip_decodes_scope_without_rebuilding_reference(prepared_input, monkeypatch):
    from copy import deepcopy
    import result_store, seed_training as seeds
    row = prepared_input.source('scoped', [['outbreak']])
    row['allowed_groups'] = [dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                                 target_type='single_target', target_count=1)]
    seeds.ensure_prepared('/profile', 1, '/memory', sources=[row], inputs=prepared_input.inputs)
    disk = deepcopy(prepared_input.writes[-1][2])
    for record in disk:
        for key, kind in seeds.PREPARED_SCHEMA.items():
            if kind == 'JSON' and record[key] is not None:
                record[key] = json.dumps(record[key])
    monkeypatch.setattr(result_store, 'read_records', lambda *a, **kw: deepcopy(disk))
    ready = seeds.ensure_prepared('/profile', 1, '/memory', sources=[row], inputs=prepared_input.inputs)
    assert ready['preparation']['context_rebuilt'] is False
    assert ready['preparation']['sources_rebuilt'] == 0
    assert ready['queue'][0]['sources'][0]['allowed_groups'] == row['allowed_groups']


def test_weighted_generator_matches_frozen_legacy_output_and_resumes():
    import hashlib
    import random
    from weighted_seeds import generate
    capabilities = dict(actions=[dict(kind='spell', spell_id=i, simc_action=name)
                                for i, name in ((1, 'a'), (2, 'b'))], precombat_actions=[0] * 121)
    reference = dict(successes={'spell:1': 3, 'spell:2': 1})
    rng = random.Random(20261110)
    state = generate(capabilities, reference, rng, count=32, excluded=set(),
                     legal=lambda p: json.dumps(p), check=lambda: None)
    assert len(state['programs']) == 32
    assert state['attempts'] == 41 and state['duplicates'] == 9
    assert hashlib.sha256(json.dumps(state['programs'], sort_keys=True).encode()).hexdigest() == '4c487877f77493565180ec167da80fd8f041756601268c8b329fb807af22fb26'
    assert hashlib.sha256(repr(rng.getstate()).encode()).hexdigest() == '84ffeb133154d382ce0c0a31e4c7c7b367700442f58b412d211e445e56ed801f'
    saved = {}
    def checkpoint(progress):
        saved.update(json.loads(json.dumps(progress)))
        if progress['attempts'] == 9:
            raise InterruptedError('cancel')
    with pytest.raises(InterruptedError):
        generate(capabilities, reference, random.Random(20261110), count=32, excluded=set(),
                 legal=lambda p: json.dumps(p), check=lambda: None, checkpoint=checkpoint)
    resumed = generate(capabilities, reference, random.Random(0), count=32, excluded=set(),
                       legal=lambda p: json.dumps(p), check=lambda: None, progress=saved)
    assert resumed['programs'] == state['programs'] and resumed['attempts'] == 41


@pytest.mark.real
def test_joint_apply_command_is_one_write_recovers_lost_receipt_and_refuses_conflicts(tmp_path, monkeypatch, capsys):
    import hashlib
    from pathlib import Path
    from copy import deepcopy
    from contextlib import nullcontext
    import burst, result_store, seed_training as seeds, simulation_config, task
    import reference_seeds as refresh
    from search import digest
    config = tmp_path / 'config.toml'
    config.write_text('[training]\nreference_seed_mode="weighted-v1"\n', encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    setup = dict(groups=[dict(configuration_key=dict(specialization_id=252,
        hero_talent=hero, target_type=target)) for hero in ('rider_of_the_apocalypse', 'sanlayn')
        for target in ('single_target', 'aoe')])
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: deepcopy(setup))
    monkeypatch.setattr(seeds, 'writer_lock', nullcontext)
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(task, '_rule_hashes', lambda **kw: {})
    monkeypatch.setattr(burst, 'load', lambda spec: dict(spec_id=252))
    old = [dict(source_id='unrelated', active=True, allowed_groups=None)]
    final = [*old, dict(source_id='managed', active=True, allowed_groups=None)]
    registry = deepcopy(old)
    monkeypatch.setattr(seeds, 'registry_rows', lambda: deepcopy(registry))
    writes = []
    def write(table, key, rows, **kw):
        assert (table, key) == ('seed_candidates', 'registry')
        writes.append(deepcopy(rows))
        registry[:] = deepcopy(rows)
    monkeypatch.setattr(result_store, 'write', write)
    plugin_source, toc = tmp_path / 'RotationData.lua', tmp_path / 'addon.toc'
    plugin_source.write_text('fixture', encoding='utf-8')
    toc.write_text('1.0', encoding='utf-8')
    plugin = dict(source=str(plugin_source), toc=str(toc),
        source_sha256=hashlib.sha256(plugin_source.read_bytes()).hexdigest(),
        toc_sha256=hashlib.sha256(toc.read_bytes()).hexdigest())
    root = tmp_path / 'refresh'
    root.mkdir()
    state = dict(status='prepared', published=False, final_sources=final,
        final_digest=refresh.source_digest(final), final_groups=[dict(group=dict(r['configuration_key'],
            target_count=1 if r['configuration_key']['target_type'] == 'single_target' else 5),
            simc_behaviors=30, plugin_sources=1) for r in setup['groups']],
        adoption=json.loads(refresh.ADOPTION_PATH.read_text(encoding='utf-8')), plugin=plugin,
        manifest=dict(configuration=simulation_config._load_document(), setup=setup,
            policy=simulation_config.load_reference_seed_config(), sources=refresh.source_digest(old),
            burst_definition=dict(spec_id=252), rules={},
            implementation={name: hashlib.sha256(Path(refresh.__file__).with_name(name).read_bytes()).hexdigest()
                for name in ('reference_seeds.py', 'weighted_seeds.py', 'gearinsight_reference.lua')}))
    def restore_plan():
        state['checksum'] = digest({k: v for k, v in state.items() if k != 'checksum'})
        refresh.write_json(root / 'plan.json', state)
    restore_plan()
    args = ['--project', str(tmp_path), 'refresh-references', '--workspace', str(root), '--apply-plan']
    registry.append(dict(source_id='concurrent', active=True))
    assert seeds.main(args) == 2
    assert '拒绝覆盖' in capsys.readouterr().err and not writes
    registry[:] = deepcopy(old)
    toc.write_text('2.0', encoding='utf-8')
    assert seeds.main(args) == 2
    assert '插件资料' in capsys.readouterr().err and not writes
    toc.write_text('1.0', encoding='utf-8')
    assert seeds.main(args) == 0
    assert json.loads(capsys.readouterr().out)['already_published'] is False
    assert len(writes) == 1 and registry == final and registry[0] == old[0]
    # Simulate a lost publication receipt: the old prepared plan survives, registry is already new.
    restore_plan()
    assert seeds.main(args) == 0
    assert json.loads(capsys.readouterr().out)['already_published'] is True and len(writes) == 1


def test_explicit_other_group_material_is_rejected(prepared_input):
    import seed_training as seeds
    row = prepared_input.source('other', [['outbreak']])
    row['allowed_groups'] = [dict(specialization_id=252, hero_talent='sanlayn',
                                 target_type='single_target', target_count=1)]
    with pytest.raises(ValueError, match='适用范围'):
        seeds.ensure_prepared('/profile', 1, '/memory', sources=[row], materials=[row],
                              inputs=prepared_input.inputs)


@pytest.fixture
def refresh_environment(tmp_path, monkeypatch, prepared_input):
    """Use the real command/preparer; only filesystem/catalogue/storage boundaries are supplied."""
    import burst
    import engine
    import result_store
    import seed_training as seeds
    import simulation_config
    from search import digest
    from pathlib import Path
    root = tmp_path / 'refresh'
    template = tmp_path / 'role.simc'
    template.write_text(prepared_input.inputs['text'], encoding='utf-8')
    config = tmp_path / 'config.toml'
    original_config = ('[training]\nreference_seed_mode="weighted-v1"\nreference_seed_target=3\n'
        '[syntax]\nmulti_command_blocks=false\nloop=false\nwait_clicks=false\ncastsequence=false\n')
    config.write_text(original_config, encoding='utf-8')
    monkeypatch.setattr(simulation_config, 'DEFAULT_PATH', config)
    monkeypatch.setattr(engine, 'identity', lambda mode: (Path('/fake-engine'), {'mode': mode}))
    monkeypatch.setattr(burst, 'load', lambda spec: dict(spec_id=252, excluded_spell_ids=[]))
    monkeypatch.setattr(burst, 'select_definition', lambda character: None)
    inputs = seeds._training_inputs(template, 1, use_burst=True)
    key = digest(dict(version=seeds.PREPARATION_VERSION, template=inputs['template_sha'],
        engines=inputs['engines'], simulation=inputs['simulation_config'], definition=None,
        semantics=seeds.semantic_versions(), config=seeds._identity_config(inputs['config'])))
    header = prepared_input.header
    header['config_key'] = key
    native = header['context']['native']
    native.update(samples=1, action_summary=dict(version=1, samples=1, duration_ms=180000,
        successes={'spell:1001': 1}, pairs={}, outgoing={}, positions={}, witnesses={},
        scope=dict(allowed={'spell:1001': True}, excluded={}, windows='none', policy='fixture', controlled=False)))
    header['checksum'] = digest([{k: v for k, v in header.items() if k != 'checksum'}])
    source = prepared_input.source('old', [['outbreak']])
    source['source_id'] = 'manual:simc-sanlayn-a1-20261012'
    sources = [source]
    monkeypatch.setattr(seeds, 'registry_rows', lambda: sources)
    monkeypatch.setattr(seeds, 'check_training', lambda **kw: dict(
        templates=[dict(template=str(template), template_sha256=inputs['template_sha'])],
        engines=inputs['engines'], training_config=simulation_config.load_training_config(),
        groups=[dict(template=str(template),
        configuration_key=dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                               target_type='single_target'))]))
    monkeypatch.setattr(result_store, 'bind_project', lambda path: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    writes = []
    def store_write(table, key, rows, **kw):
        assert table != 'seed_candidates', 'preparation cannot publish the registry'
        assert json.loads((root / 'plan.json').read_text(encoding='utf-8'))['status'] == 'preparing'
        writes.append(table)
    monkeypatch.setattr(result_store, 'write', store_write)
    arguments = ['--project', str(tmp_path), 'refresh-references', '--workspace', str(root), '--simc-only']
    from types import SimpleNamespace
    return SimpleNamespace(root=root, config=config, original_config=original_config, arguments=arguments,
                           sources=sources, writes=writes, write=store_write, source=prepared_input.source)


@pytest.mark.real
@pytest.mark.parametrize('case', ['valid_with_unknown', 'old_revision', 'all_unknown'])
def test_joint_preparation_command_cleans_real_records_and_keeps_registry_on_failure(
        refresh_environment, tmp_path, monkeypatch, capsys, case):
    import hashlib
    from copy import deepcopy
    import reference_seeds as refresh
    import seed_training as seeds
    from search import digest
    env = refresh_environment
    legacy = []
    for number in range(28):
        row = env.source('plugin-old-' + str(number), [['outbreak']])
        row['source_revision'] = 'revision-' + str(number)
        env.sources.append(row)
        legacy.append(dict(source_id=row['source_id'], candidate_id=row['candidate_id'],
            source_revision=row['source_revision'], original_sha256=hashlib.sha256(row['original'].encode()).hexdigest(),
            program_sha256=digest(row['program'])))
    protected = [env.source('protected-' + str(n), [['outbreak']]) for n in range(2)]
    env.sources.extend(protected)
    adoption = tmp_path / 'adoption.json'
    adoption.write_text(json.dumps(dict(legacy_sources=legacy,
        protected_manual_source_ids=[r['source_id'] for r in protected])), encoding='utf-8')
    monkeypatch.setattr(refresh, 'ADOPTION_PATH', adoption)
    if case == 'old_revision':
        env.sources[1]['source_revision'] = 'not-approved'
    before = deepcopy(env.sources)
    plugin = tmp_path / 'plugin'
    plugin.mkdir()
    first = '999999999' if case == 'all_unknown' else '77575,47541'
    (plugin / 'RotationData.lua').write_text('GearInsightRotation={["DEATHKNIGHT/UNHOLY"]={specID=252,'
        'opener={{seq={' + first + '}},{seq={999999998,77575}}}}}', encoding='utf-8')
    (plugin / 'GearInsight_Data.toc').write_text('## Version: 1.0\n', encoding='utf-8')
    args = [v for v in env.arguments if v != '--simc-only'] + ['--plugin-dir', str(plugin)]
    status = seeds.main(args)
    result = capsys.readouterr()
    assert env.sources == before and 'seed_candidates' not in env.writes
    state = json.loads((env.root / 'plan.json').read_text(encoding='utf-8'))
    if case != 'valid_with_unknown':
        assert status == 2 and state['status'] == 'paused'
        assert ('精确接管清单' if case == 'old_revision' else '四组材料未齐') in result.err
        return
    assert status == 0 and state['status'] == 'prepared'
    final = {r['source_id']: r for r in state['final_sources']}
    assert all(final[r['source_id']] == r for r in protected)
    assert all(final[r['source_id']]['active'] is False for r in legacy)
    new = [r for r in final.values() if r['family'] == 'gearinsight-library-v1']
    assert sum(r['active'] for r in new) == 1
    assert any('未知按钮' in r['unavailable_reason'] for r in new if not r['active'])
    assert state['final_groups'][0]['simc_behaviors'] == 3 and state['final_groups'][0]['plugin_sources'] == 1

    # A second command wins the lock between stages. The stale caller must use its latest result.
    from contextlib import contextmanager
    import task
    winner = deepcopy(state)
    winner.update(used_seconds=200., winner='other-command')
    winner['checksum'] = digest({k: v for k, v in winner.items() if k != 'checksum'})
    stale = deepcopy(state)
    stale['status'] = 'simc_prepared'
    stale['checksum'] = digest({k: v for k, v in stale.items() if k != 'checksum'})
    refresh.write_json(env.root / 'plan.json', stale)
    original_lease = task._task_lease
    calls = []
    @contextmanager
    def handoff(*a, **kw):
        with original_lease(*a, **kw):
            calls.append(1)
            if len(calls) == 2:
                refresh.write_json(env.root / 'plan.json', winner)
            yield
    monkeypatch.setattr(task, '_task_lease', handoff)
    assert seeds.main(args) == 0
    latest = json.loads(capsys.readouterr().out)
    assert latest['winner'] == 'other-command' and latest['used_seconds'] == 200.


@pytest.mark.real
def test_refresh_command_recovers_storage_failure_and_rejects_drift_corruption_and_exhaustion(
        refresh_environment, monkeypatch, capsys):
    import result_store, seed_training as seeds
    from search import digest
    env = refresh_environment
    root, config, original_config, arguments, writes = (env.root, env.config, env.original_config,
                                                       env.arguments, env.writes)
    def fail_once(table, key, rows, **kw):
        env.write(table, key, rows, **kw)
        if table == 'seed_prepared' and writes.count('seed_prepared') == 2:
            raise OSError('constructed write failure')
    monkeypatch.setattr(result_store, 'write', fail_once)
    assert seeds.main(arguments) == 2
    assert 'constructed write failure' in capsys.readouterr().err
    plan_path = root / 'plan.json'
    paused = json.loads(plan_path.read_text(encoding='utf-8'))
    assert paused['status'] == 'paused' and len(paused['groups'][0]['generation']['programs']) == 2
    assert seeds.main(arguments) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed['status'] == 'simc_prepared' and completed['groups'][0]['simc_behaviors'] == 3
    assert [r['program'] for r in completed['generated']] == paused['groups'][0]['generation']['programs']
    assert completed['requested_iterations'] == paused['requested_iterations'] == 0
    assert result_store.DATA_ROOT != root / 'data'
    config.write_text(original_config.replace('loop=false', 'loop=true'), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '配置' in capsys.readouterr().err
    config.write_text(original_config, encoding='utf-8')
    plan_path.write_text(json.dumps(dict(completed, checksum='broken')), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '校验损坏' in capsys.readouterr().err
    completed['status'] = 'preparing'
    completed['checksum'] = digest({k: v for k, v in completed.items() if k != 'checksum'})
    plan_path.write_text(json.dumps(completed), encoding='utf-8')
    before = list(writes)
    assert seeds.main(arguments) == 2
    assert '非正常退出' in capsys.readouterr().err and writes == before
    completed.update(status='paused', used_seconds=300)
    completed['groups'][0]['status'] = 'preparing'
    completed['checksum'] = digest({k: v for k, v in completed.items() if k != 'checksum'})
    plan_path.write_text(json.dumps(completed), encoding='utf-8')
    assert seeds.main(arguments) == 2
    assert '预算' in capsys.readouterr().err


@pytest.mark.real
def test_refresh_command_stops_at_workspace_space_line(refresh_environment, monkeypatch, capsys):
    import os
    from pathlib import Path
    import seed_training as seeds
    env = refresh_environment
    env.root.mkdir()
    evidence = env.root / 'existing-evidence'
    evidence.write_bytes(b'x')
    stat = Path.stat
    def size_boundary(path, *a, **kw):
        value = stat(path, *a, **kw)
        if path == evidence:
            values = list(value)
            values[6] = 1024 ** 3
            return os.stat_result(values)
        return value
    monkeypatch.setattr(Path, 'stat', size_boundary)
    assert seeds.main(env.arguments) == 2
    assert '1GiB' in capsys.readouterr().err
    assert not env.writes and evidence.read_bytes() == b'x'
