"""第三票：通过同一任务入口驱动搜索、复测与结果隔离。"""

from __future__ import annotations

import tempfile
import time
import shutil
import os
from contextlib import contextmanager, nullcontext, ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import pytest
from test_population_training import memory_ga

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))
from test_character_export import sample_profile
from test_engine import apl_pool_reference, static_snapshot
from task import run_task
from search import initial_programs, TaskStore


def test_mutate_fetches_parent_feedback_only_after_its_usage_gate():
    import random
    from search import mutate
    program = [['outbreak'], ['death_coil'], ['scourge_strike']]
    feedback = dict(positions=[dict(source_position=dict(segment=0), unresolved_inputs=1)])
    calls = []
    def get_feedback():
        calls.append('feedback')
        return feedback

    observation = {}
    mutate(program, _fast_capabilities(), random.Random(0),
           feedback_getter=get_feedback, observation=observation)
    assert observation['sampled_mutation'] == 'loop'
    assert calls == []

    mutate(program, _fast_capabilities(), random.Random(1),
           feedback_getter=get_feedback, observation=observation)
    assert observation['sampled_mutation'] == 'insert'  # Its feedback gate is above .5.
    assert calls == []

    rng = random.Random(2)
    child = mutate(program, _fast_capabilities(), rng,
                   feedback_getter=get_feedback, observation=observation)
    assert calls == ['feedback']
    assert child == [['death_coil'], ['scourge_strike'], ['outbreak']]
    assert observation == dict(sampled_mutation='swap', actual_mutation='move',
                               modification_position=dict(segment=0, repair=True, target=2))
    assert rng.random() == 0.25158329759496567


def test_mutate_keeps_legacy_feedback_truthiness_and_random_consumption():
    import random
    from search import mutate
    program = [['outbreak'], ['death_coil'], ['scourge_strike']]
    for feedback in (None, {}):
        rng = random.Random(2)
        assert mutate(program, _fast_capabilities(), rng, feedback=feedback) == [
            ['scourge_strike'], ['death_coil'], ['outbreak']]
        assert rng.random() == 0.3610574739836072
    rng = random.Random(2)
    feedback = dict(positions=[dict(source_position=dict(segment=0), unresolved_inputs=1)])
    assert mutate(program, _fast_capabilities(), rng, feedback=feedback) == [
        ['death_coil'], ['scourge_strike'], ['outbreak']]
    assert rng.random() == 0.25158329759496567


def _fast_capabilities():
    actions = [
        dict(kind="spell", spell_id=1001, simc_action="outbreak", name="outbreak", gcd_ms=1500, base_spell_id=1001),
        dict(kind="spell", spell_id=1002, simc_action="death_coil", name="death_coil", gcd_ms=1500, base_spell_id=1002),
        dict(kind="spell", spell_id=1003, simc_action="scourge_strike", name="scourge_strike", gcd_ms=1500, base_spell_id=1003),
        dict(kind="spell", spell_id=1004, simc_action="dark_transformation", name="dark_transformation", gcd_ms=1500, base_spell_id=1004),
        dict(kind="item", slot=13, item_id=250245, driver_spell_id=1005,
             simc_action="use_item,slot=trinket1", name="使用trinket1", gcd_ms=0),
    ]
    return dict(actions=actions, precombat_actions=[], sources=[], protocol=3,
                scope="test", coverage="constructed-test-boundary")


def _fast_reference(profile, folder, character, *, runtime=None, iterations=100, seed=20260912,
                    simulation_config=None, import_spell_ids=(), import_spell_names=()):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "native.json").write_text(json.dumps(_fast_report(character, 100.0, max(1, iterations-1))),
                                         encoding="utf-8")
    return dict(static_snapshot=static_snapshot(), dps=100.0, metric="dps", personal_dps=100.0, samples=max(1, iterations-1), seconds=180,
                identity=dict(class_id=6, spec_id=252, spec=character.spec, race=character.race,
                              role=character.fields.get("role", "attack"), resource="runic_power"),
                action_sequence=[{"name": "use_item,slot=trinket1", "queue_failed": False}],
                precombat_sequence=[], actions_protocol=1, executed_actions=[], precombat_definitions=[],
                active_items=[{"slot": "trinket1", "id": 250245, "driver_spell_id": 1005}])


def _fast_inspect(reference, folder, *, include_item=True):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    capabilities = _fast_capabilities()
    if not include_item:
        capabilities["actions"] = [row for row in capabilities["actions"]
                                   if row["kind"] != "item" and row["simc_action"] != "dark_transformation"]
        spell_ids = {"outbreak": 77575, "death_coil": 47541, "scourge_strike": 55090}
        for row in capabilities["actions"]:
            row["spell_id"] = row["base_spell_id"] = spell_ids[row["simc_action"]]
    (folder / "catalogue.json").write_text(json.dumps(capabilities), encoding="utf-8")
    return capabilities


def _fast_report(character, score, samples):
    player = {
        "name": character.name, "sim2gse_class": character.class_name, "level": character.level,
        "sim2gse_class_id": 6, "sim2gse_spec": character.spec,
        "role": character.fields.get('role', 'attack'),
        "sim2gse_spec_id": character.spec_id or 252, "race": character.race,
        "talents": character.fields["talents"], "sim2gse_resource": "runic_power",
        "gear": {{'shoulder': 'shoulders', 'wrist': 'wrists'}.get(slot, slot):
                 {'encoded_item': item.raw} for slot, item in character.equipment.items()},
        "collected_data": {"dps": {"mean": score, "count": samples, "variance": 0}, "fight_length": {"mean": 180},
                           "resource_overflowed": {"runic_power": {"mean": 0}}},
    }
    return {"sim": {"players": [player], "targets": [{"name": "Damage_Dummy", "level": 90}],
                    "statistics": {"raid_dps": {"mean": score, "count": samples}},
                    "options": {"dbc": {"Live": {"build_level": 69587, "wow_version": "12.1.0.69587"}, "version_used": "Live"}}}}


def _fast_evaluate(profile, candidate, folder, *, character, iterations=100,
                   seed=20260912, trace=True, mode="controlled", input_times=None,
                   runtime=None, score_offset=0, simulation_config=None, reset_events=None,
                   on_native_start=None, score=None, rule_observation_request=None, allow_zero=False):
    """构造稳定报告，保留 search.optimize 的选择、缓存和发布逻辑。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if on_native_start is not None:
        on_native_start()
    input_times = list(range(0, 180000, 300)) if input_times is None else list(input_times)
    if score is None:
        # Finite native-boundary landscape: repeating an action is not endless improvement.
        score = score_offset + 100.0 + sum({
            command.get("spell_id", command.get("item_id", 0))
            for block in candidate["blocks"] for command in block
        }) / 1000.0
    samples = max(1, iterations - 1)
    report = _fast_report(character, score, samples)
    targets = (simulation_config or {}).get('target_count', 1)
    report['sim']['targets'] = [dict(report['sim']['targets'][0]) for _ in range(targets)]
    (folder / "native.json").write_text(json.dumps(report), encoding="utf-8")
    trace_rows = []
    if trace:
        trace_rows = [
            dict(ms=0, event="input", origin=1, step=0, action="-", signature="-",
                 battle=1, rp=0, health=100, gcd=0, cooldown=0, cast_ms=0),
            dict(ms=0, event="busy", origin=1, step=0, action="feedback_probe",
                 signature="feedback_probe", battle=9001, rp=0, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
            dict(ms=0, event="dispatch_failed", origin=1, step=0, action="feedback_probe",
                 signature="feedback_probe", battle=9002, rp=0, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
            dict(ms=0, event="native_execute", origin=1, step=0, action="outbreak",
                 signature="outbreak", battle=1, rp=1, health=100, gcd=0,
                 cooldown=0, cast_ms=0),
        ]
    return dict(blocks=[[a["simc_action"] for a in block] for block in candidate["blocks"]],
                native_blocks=[[a["simc_action"] for a in block] for block in candidate["blocks"]],
                input_times=input_times, consistent=True,
                summary={"dps": score, "samples": samples}, report=report,
                trace=trace_rows, game_validation="not_run", model="constructed-test-boundary")


def _fast_training_template(_manifest):
    """只取固定上游模板作构造输入，不认证或执行旧构建。真实构建门禁另测。"""
    import engine
    from native_build import source_directory
    manifest = json.loads((engine.ROOT / '.local/sim2gse/build/baseline/build.json').read_text())
    fields = ('protocol', 'source_line_endings', 'mode', 'upstream_commit', 'upstream_tree',
              'patches', 'sources', 'build_options', 'compiler_sha256')
    source = source_directory(engine.ROOT, {name: manifest[name] for name in fields})
    return source / 'profiles/MID2/MID2_Death_Knight_Unholy.simc'


def _fast_identity(mode, runtime=None):
    return Path('simc-test.exe'), dict(mode=mode, upstream_commit='test', build_options=[])


@contextmanager
def _fast_initialization(*, real_engine=False):
    """提供明确单目标测试配置，跳过与状态、缓存和进程故障断言无关的原生初始化。"""
    import codec
    import engine
    import simulation_config

    def compiler(command, *args, **kwargs):
        if kwargs.get("on_start") is not None:
            kwargs["on_start"]()
        output = (b"PASS\tcollection_import_compile\n" if command[-1] == "collection"
                  else b"CHECKSUM\ttest\nPASS\ttest\n")
        return SimpleNamespace(returncode=0, stdout=output, stderr=b"")

    def check_report(report, character, iterations, **kwargs):
        damage = report["sim"]["statistics"]["raid_dps"]
        return dict(dps=damage["mean"], metric="dps", personal_dps=damage["mean"],
                    samples=damage["count"], seconds=180, metadata_only=[], notices=[],
                    identity={"spec_id": character.spec_id or 252, "race": character.race,
                              "resource": "runic_power"})

    identity = _fast_identity
    identity_boundary = nullcontext() if real_engine else patch.object(engine, "identity", side_effect=identity)
    with ExitStack() as boundary:
        boundary.enter_context(patch.dict(simulation_config.DEFAULT_CONFIG, scene='single_target'))
        with identity_boundary, \
             patch.object(engine, "_training_template", side_effect=_fast_training_template), \
             patch.object(engine, "reference", side_effect=_fast_reference), \
             patch.object(engine, "inspect", side_effect=lambda reference, folder:
                          _fast_inspect(reference, folder, include_item=not real_engine)), \
             patch.object(engine, "check_report", side_effect=check_report), \
             patch.object(codec, "run_command", side_effect=compiler):
            yield


@contextmanager
def _captured_task_connections():
    import search

    original_connect = search.sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    try:
        with patch.object(search.sqlite3, 'connect', side_effect=connect):
            yield connections
    finally:
        for connection in connections:
            connection.close()


@contextmanager
def _initialized_starts(starts):
    """指定起点仍由真实初始化先冻结对应配置与来源证据。"""
    import search
    original = search.initial_programs

    def initialized(*args, **kwargs):
        original(*args, **kwargs)
        return starts

    with patch.object(search, 'initial_programs', side_effect=initialized):
        yield


@contextmanager
def _fixed_search_population(starts):
    """非变异代表仅固定测试工作量；真实两代、复测和持久化契约不变。"""
    from copy import deepcopy
    import population_training
    with _initialized_starts(starts), \
            patch.object(population_training, '_cross', return_value=False), \
            patch.object(population_training, 'mutate', side_effect=lambda program, *a, **k: deepcopy(list(program))):
        yield


class SearchAndValidationTests(TestCase):
    @pytest.fixture(autouse=True)
    def _explicit_search_inputs(self, request):
        if request.node.get_closest_marker('real') is None:
            self.memory_ga = request.getfixturevalue('memory_ga')

    def test_task_store_initialization_failure_closes_connection(self):
        import sqlite3
        with _captured_task_connections() as connections:
            database=sqlite3.connect(':memory:')
            database.execute('CREATE TABLE state (id INTEGER PRIMARY KEY,value TEXT NOT NULL)')
            database.execute('INSERT INTO state VALUES (1,?)',('{invalid-state',))
            database.commit()
            with self.assertRaises(json.JSONDecodeError) as caught:
                TaskStore(Path('/memory/init-failure'), connection=database,
                          reusable_database=':memory:', report_locations={})
            self.assertEqual(caught.exception.doc,'{invalid-state')
            self.assertEqual(len(connections),1)
            with self.assertRaisesRegex(sqlite3.ProgrammingError,'closed'):
                connections[0].execute('SELECT 1')


    def test_normal_task_and_dual_scene_still_refuse_four_processes(self):
        from io import StringIO
        import dual_task
        from simulation_config import load_search_config
        from search import config_for
        self.assertEqual(config_for()['max_processes'],2)
        with patch('simulation_config.load_search_config', side_effect=lambda **values:
                   load_search_config(StringIO(''), **values)), \
                patch.object(Path,'read_bytes',return_value=sample_profile().encode('utf-8')):
            for entry in (run_task,dual_task.start):
                with self.subTest(entry=entry.__name__),self.assertRaisesRegex(ValueError,'max_processes'):
                    entry(Path('/absent/role.simc'),Path('/absent/task'),search_config={'max_processes':4})

    def test_task_uses_full_apl_pool_without_changing_baseline_starts(self):
        import engine
        from sequence import select
        native=apl_pool_reference()
        capabilities=engine.inspect(native)  # No folder: the existing data-only seam.
        self.assertEqual([row['simc_action'] for row in capabilities['actions']],
                         ['outbreak','death_coil','scourge_strike','death_and_decay','epidemic'])
        self.assertEqual(initial_programs(capabilities,native,scene='single_target')[1:],[
            [['outbreak'],['outbreak'],['death_coil']],
            [['outbreak'],['death_coil'],['outbreak'],['death_coil']],
            [['scourge_strike'],['death_coil'],['outbreak']],
        ])
        self.assertEqual([[row['simc_action'] for row in block] for block in select(capabilities)],
                         [['outbreak'],['death_coil'],['scourge_strike']])


    def test_formal_nominal_retest_selects_from_all_finalists_without_paired_ci(self):
        import search
        from program import canonicalize_search_program
        from simulation_config import TRAINING_DEFAULTS
        preferred=[['outbreak']]
        def score(candidate,options):
            blocks=[[row['simc_action'] for row in block] for block in candidate['blocks']]
            return (200. if blocks==preferred else 100.) if options['iterations']==32 else (50. if blocks==preferred else 150.)
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=[preferred,[['death_coil']]],score_for=score)
            result=case.run()
        preferred_key=canonicalize_search_program(preferred,case.capabilities)['identity']
        finalists=result['final']['scenarios']['nominal']['finalists']
        self.assertIn(preferred_key,[row['key'] for row in finalists])
        self.assertNotEqual(result['selected_candidate_key'],preferred_key)
        self.assertEqual(result['search_result']['dps'],150.)
        self.assertEqual(result['search_result']['samples'],381)
        self.assertTrue(all(len(row['batches'])==3 for row in finalists))
        self.assertTrue(all(batch['requested_iterations']==32 for row in result['search']['records'] for batch in row['batches']))
        saved=TaskStore.load_state(case.store.db)
        self.assertEqual(saved['search_result'],result['search_result'])
        self.assertEqual(saved['formal_winner']['candidate']['text'],result['candidate']['text'])


    def test_formal_initial_scores_overlap_with_at_most_two_engines(self):
        import threading
        from simulation_config import TRAINING_DEFAULTS
        barrier,lock=threading.Barrier(2,timeout=2),threading.Lock()
        active,peak,initial_calls=0,0,[]
        starts=[[['outbreak']],[['death_coil']]]
        def score(candidate,options):
            nonlocal active,peak
            blocks=[[row['simc_action'] for row in block] for block in candidate['blocks']]
            with lock:
                active+=1
                peak=max(peak,active)
            try:
                if options['iterations']==32 and blocks in starts:
                    initial_calls.append(blocks)
                    barrier.wait()
                return 100.
            finally:
                with lock: active-=1
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=starts,score_for=score,search_settings=dict(max_processes=2))
            result=case.run()
        self.assertEqual(result['status'],'completed')
        self.assertEqual(peak,2)
        self.assertCountEqual(initial_calls,starts)
        self.assertEqual(result['search']['starts'],starts)


    def test_cancelled_formal_batches_resume_without_repeating_successful_native_requests(self):
        import threading
        from runtime import TaskRuntime,TaskCancelled
        from simulation_config import TRAINING_DEFAULTS
        cancel=threading.Event()
        interrupted=[False]
        def score(candidate,options):
            if not interrupted[0]:
                interrupted[0]=True
                cancel.set()
            return 100.
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=[[['outbreak']],[['death_coil']]],score_for=score)
            with self.assertRaises(TaskCancelled):
                case.run(runtime=TaskRuntime(float('inf'),cancel_event=cancel))
            self.assertIsNone(case.store.state.get('selected_candidate_key'))
            self.assertTrue(case.calls)
            first=case.calls[0][0]
            first_key=Path(first).name
            saved=case.store.batch(first_key)
            self.assertEqual((saved['status'],saved['dps'],saved['samples']),('success',100.,31))
            self.assertIn('report',case.reports[first_key])
            case.store.checkpoint()
            case.store.state=TaskStore.load_state(case.store.db)
            case.store.verified_batches.clear()
            self.assertEqual(case.store.batch(first_key),saved)
            cancel.clear()
            resumed=case.run(runtime=TaskRuntime(float('inf'),cancel_event=cancel))
        calls=[row[0] for row in case.calls]
        self.assertEqual(resumed['status'],'completed')
        self.assertEqual(calls.count(first),1)
        self.assertEqual(len(calls),len(set(calls)))
        self.assertEqual(resumed['search_result']['samples'],381)


    def test_run_task_deduplicates_equivalent_programs_before_native_evaluation(self):
        import program
        import sequence
        from formal_search import freeze_starts
        from runtime import TaskRuntime
        from simulation_config import TRAINING_DEFAULTS
        action='use_item,slot=trinket1'
        equivalents=[[dict(kind='Loop',count=2,blocks=[[action]])],[[action],[action]]]
        compiles=[]
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=equivalents)
            starts,_=freeze_starts(case.starts,case.capabilities,TaskRuntime(float('inf')))
            case.store.state['starts']=starts
            compiler=program.compile_program
            def compiled(mapped,folder,**options):
                compiles.append(str(folder))
                return compiler(mapped,folder,**options)
            with patch.object(program,'compile_program',side_effect=compiled):
                result=case.run()
        expected=[[action],[action]]
        records=[row for row in result['search']['records'] if sequence.compiled_program(row['candidate'])==expected]
        evaluations=[row for row in case.calls if row[2]['iterations']==32 and sequence.compiled_program(row[1])==expected]
        self.assertEqual((len(records),len(evaluations)),(1,1))
        self.assertEqual(len([folder for folder in compiles if folder.endswith(records[0]['key'])]),1)

    def test_search_observability_is_off_by_default_and_preserves_selection(self):
        import sequence
        import result_store
        from task import _freeze_formal_champion
        from runtime import diagnostic_summary
        def run(mode=None):
            options={} if mode is None else dict(search_observability=mode,diagnostic_logging=True,diagnostics='summary')
            case=self.memory_ga(formal=True,programs=[[['outbreak']]],search_settings=options)
            result=case.run()
            requests=[(sequence.behavior_key(candidate),settings['seed'],settings['iterations'],settings['trace'])
                      for _,candidate,settings in case.calls]
            progress=diagnostic_summary(case.store)['candidate_progress']
            binding_state=dict(condition=case.condition,input_effective_sha256='fixed-role-bytes',
                               simulation_config=case.ready['simulation_config'])
            native=dict(identity=dict(spec_id=252))
            with patch.object(result_store,'read_search_champion',return_value=None):
                champion=_freeze_formal_champion(binding_state,case.character,native,case.capabilities)
            return result,requests,champion,progress
        baseline,baseline_requests,baseline_condition,_=run()
        observed,observed_requests,observed_condition,progress=run('full')
        self.assertEqual(baseline['search']['starts'],observed['search']['starts'])
        self.assertNotIn('observability',baseline['search'])
        self.assertEqual(baseline['selected_candidate_key'],observed['selected_candidate_key'])
        self.assertEqual(baseline_requests,observed_requests)
        self.assertEqual(baseline_condition['status'],'absent')
        self.assertEqual(observed_condition['status'],'absent')
        self.assertEqual(baseline_condition['binding']['condition'],observed_condition['binding']['condition'])
        def score_snapshot(result):
            records=[]
            for record in result['search']['records']:
                validations={}
                for name in ('validation','global_validation'):
                    comparison=record.get(name)
                    if comparison:
                        validations[name]=tuple(tuple((row['dps'],row['samples'],row['request']['seed'])
                            for row in comparison[side]) for side in ('candidate','control'))
                records.append((record['key'],record['program'],record['score'],
                    tuple((row['dps'],row['samples'],row['request']['seed']) for row in record['batches']),validations))
            return records
        self.assertEqual(sorted(score_snapshot(baseline)),sorted(score_snapshot(observed)))
        summary=observed['search']['observability']['summary']
        self.assertEqual(summary['initial_candidates'],1)
        self.assertGreater(summary['mutation_attempts'],0)
        self.assertEqual(summary['score_completed'],len(observed['search']['records']))
        self.assertTrue(observed['search']['observability']['details'])
        actual_coarse={key for key,_,iterations,_ in observed_requests if iterations==32}
        self.assertEqual({row['behavior_identity'] for row in progress['screening_archived']},actual_coarse)
        # Physical champion binding/read-through is retained by the real public
        # persistence representative; this case compares the executor's frozen condition.


    def test_resume_rejects_checkpoint_from_an_old_behavior_identity_version(self):
        from copy import deepcopy
        from simulation_config import TRAINING_DEFAULTS
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=[[['outbreak']],[['death_coil']]])
            result=case.run()
            before=deepcopy(result['search_result'])
            state=TaskStore.load_state(case.store.db)
            state['behavior_identity_version']='obsolete-version'
            state['elapsed_seconds']=601.
            case.store.state=state
            case.store.checkpoint()
            with self.assertRaisesRegex(ValueError,'候选行为身份版本已变化'):
                case.run()
        self.assertEqual(TaskStore.load_state(case.store.db)['search_result'],before)

    def test_run_task_rejects_canonical_compiler_mismatch_before_native_evaluation(self):
        import program
        import sequence
        from engine import CandidateError
        from simulation_config import TRAINING_DEFAULTS
        canonicalize=program.canonicalize_search_program
        def wrong_form(search_program,capabilities):
            result=canonicalize(search_program,capabilities)
            if search_program==[['outbreak']]:
                result['form']=dict(result['form'],clicks=[['death_coil']])
            return result
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=[[['outbreak']],[['death_coil']]])
            with patch.object(program,'canonicalize_search_program',side_effect=wrong_form):
                with self.assertRaisesRegex(CandidateError,'标准形式与编译计划不一致'):
                    case.run()
        self.assertNotIn([['outbreak']],[sequence.compiled_program(row[1]) for row in case.calls])

    def test_canonical_identity_expands_repeat_once_and_preserves_source_tree(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        loop = canonicalize_search_program(
            [dict(kind="Loop", count=1, blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
            capabilities,
        )
        expanded = canonicalize_search_program(
            [["outbreak"], ["use_item,slot=trinket1"]], capabilities
        )

        self.assertEqual(loop["identity"], expanded["identity"])
        repeated = canonicalize_search_program(
            [dict(kind="Loop", count=2, blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
            capabilities,
        )
        self.assertNotEqual(loop["identity"], repeated["identity"])
        self.assertEqual(loop["form"]["clicks"],
                         [["outbreak"], ["use_item,slot=trinket1"]])
        self.assertEqual(loop["form"]["version"], "sim2gse-search-behavior-v2")
        self.assertEqual(loop["form"]["precombat_count"], 0)
        self.assertEqual(loop["program"]["nodes"][0]["kind"], "Loop")
        self.assertNotEqual(loop["program"]["nodes"][0]["source"],
                            expanded["program"]["nodes"][0]["source"])

    def test_canonical_identity_keeps_action_block_boundaries_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        item = "use_item,slot=trinket1"
        one_block = canonicalize_search_program([["outbreak", item]], capabilities)
        two_blocks = canonicalize_search_program([["outbreak"], [item]], capabilities)

        self.assertNotEqual(one_block["identity"], two_blocks["identity"])

    def test_canonical_identity_keeps_castsequence_reset_distinct(self):
        from program import canonicalize_search_program

        capabilities = _fast_capabilities()
        without_reset = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"], reset=None)],
            capabilities,
        )
        with_reset = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3, "flags": ["target"]})], capabilities
        )

        self.assertNotEqual(without_reset["identity"], with_reset["identity"])
        changed_member = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "scourge_strike"], reset=None)],
            capabilities,
        )
        self.assertNotEqual(without_reset["identity"], changed_member["identity"])
        duplicate_flag = canonicalize_search_program(
            [dict(kind="CastSequence", members=["outbreak", "death_coil"],
                  reset={"timeout_seconds": 3, "flags": ["target", "target"]})], capabilities
        )
        self.assertEqual(with_reset["identity"], duplicate_flag["identity"])
        self.assertEqual(duplicate_flag["form"]["castsequences"][0]["reset"]["flags"], ["target"])

    def test_canonical_identity_rejects_invalid_wait_click_counts_with_location(self):
        from program import canonicalize_search_program

        for clicks in (1, 4097):
            with self.subTest(clicks=clicks), self.assertRaisesRegex(
                    ValueError, r"segments\[0\].*WaitClicks"):
                canonicalize_search_program(
                    [dict(kind="WaitClicks", clicks=clicks), ["outbreak"]], _fast_capabilities()
                )

    def test_canonical_identity_rejects_expansion_over_4096_with_location(self):
        from program import canonicalize_search_program

        with self.assertRaisesRegex(ValueError, r"blocks\[0\].*4096"):
            canonicalize_search_program(
                [dict(kind="Loop", count=4096,
                      blocks=[["outbreak"], ["use_item,slot=trinket1"]])],
                _fast_capabilities(),
            )

    def test_search_starts_match_fixed_baseline_golden(self):
        """导入专用动作目录不改变基线搜索起点或顺序。"""
        capabilities = dict(
            actions=[
                dict(kind="spell", spell_id=77575, simc_action="outbreak"),
                dict(kind="spell", spell_id=47541, simc_action="death_coil"),
                dict(kind="spell", spell_id=55090, simc_action="scourge_strike"),
            ],
            import_actions=[dict(kind="spell", spell_id=316239, simc_action="import_only")],
        )
        reference = dict(identity={"spec_id": 252}, static_snapshot=static_snapshot(), action_sequence=[
            dict(name="outbreak"), dict(name="death_coil"), dict(name="outbreak"),
            dict(name="scourge_strike", queue_failed=True), dict(name="unknown_action"),
        ])
        expected = [
            [["outbreak"], ["outbreak"], ["death_coil"]],
            [["outbreak"], ["death_coil"], ["outbreak"], ["death_coil"]],
            [["scourge_strike"], ["death_coil"], ["outbreak"]],
        ]

        starts = initial_programs(capabilities, reference, seed=20260912, scene='single_target')
        self.assertEqual(starts[1:], expected)
        from search import input_times
        first = input_times("jitter", seed=20260912)
        self.assertEqual(first, input_times("jitter", seed=20260912))
        self.assertNotEqual(first, input_times("jitter", seed=20260913))


    @pytest.mark.real
    def test_owned_process_tree_hard_exit_does_not_stop_other_owner(self):
        # 真实进程所有权边界；本节点不证明任务状态恢复。
        import ctypes
        from ctypes import wintypes
        import subprocess,json
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        directory=tempfile.mkdtemp(prefix='sim2gse-ownership-')
        try:
            owners=[];held=[]
            child="import subprocess,sys,time,os,json;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(60)"
            owner="import sys;sys.path.insert(0,sys.argv[1]);from runtime import run_command;run_command([sys.executable,'-c',sys.argv[2],sys.argv[3]],sys.argv[4],timeout_seconds=60)"
            try:
                for index in range(2):
                    folder=Path(directory)/str(index);folder.mkdir()
                    pids=folder/'pids.json'
                    process=subprocess.Popen([sys.executable,'-c',owner,str(REPOSITORY/'projects/sim2gse'),child,str(pids),str(folder)],creationflags=subprocess.CREATE_NO_WINDOW)
                    owners.append(process)
                    deadline=time.monotonic()+8
                    while not pids.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    ids=json.loads(pids.read_text())
                    handles=[kernel.OpenProcess(0x100000,False,pid) for pid in ids]
                    self.assertTrue(all(handles));held.append(handles)
                owners[0].kill();owners[0].wait(timeout=3)
                for handle in held[0]:self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
                for handle in held[1]:self.assertEqual(kernel.WaitForSingleObject(handle,0),258)
            finally:
                for owner_process in owners:
                    if owner_process.poll() is None:owner_process.kill();owner_process.wait(timeout=3)
                for handles in held:
                    for handle in handles:
                        self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
                        kernel.CloseHandle(handle)
        finally:
            for attempt in range(21):
                try:
                    shutil.rmtree(directory)
                    break
                except FileNotFoundError:
                    break
                except PermissionError:
                    if attempt==20:raise
                    time.sleep(0.05)


    def test_formal_deduplicates_legal_starts_and_stops_on_complete_generation_stagnation(self):
        from formal_search import freeze_starts
        from runtime import TaskRuntime
        from simulation_config import TRAINING_DEFAULTS
        starts=[[['outbreak']],[['death_coil']]]
        with patch.dict(TRAINING_DEFAULTS,crossover_probability=0.,mutation_probability=0.):
            case=self.memory_ga(formal=True,programs=starts+[starts[0],[['missing_action']]])
            frozen,decisions=freeze_starts(case.starts,case.capabilities,TaskRuntime(float('inf')))
            case.store.state.update(starts=frozen,start_adaptations=decisions)
            result=case.run()
        saved=TaskStore.load_state(case.store.db)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['search']['starts'],starts)
        self.assertEqual(result['search']['stop_reason'],'stagnation')
        self.assertGreaterEqual(result['search']['complete_generations'],2)
        self.assertEqual(result['search']['formal_search']['config']['stagnation_generations'],2)
        self.assertFalse(result['search']['partial_round'])
        self.assertEqual(saved['ga']['generation'],result['search']['complete_generations'])
        self.assertEqual(saved['search_result']['samples'],381)
        self.assertEqual([row['status'] for row in saved['start_adaptations']],['accepted','accepted','duplicate','rejected'])


if __name__ == "__main__":
    import unittest

    unittest.main()
