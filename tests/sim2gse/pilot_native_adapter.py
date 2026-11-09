"""Constructed external inputs/scores for the actual pilot CLI, never DPS evidence."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
import os
import runpy
from pathlib import Path
import sys
from unittest.mock import patch


@contextmanager
def boundary(root, output):
    sys.path.insert(0, str(root / 'tests/sim2gse'))
    import engine
    import burst
    import result_store
    import sequence
    from search import digest
    import test_search as fast
    from test_character_export import sample_profile

    profile = output / 'constructed-role.simc'
    profile.write_text(sample_profile(), encoding='utf-8')
    programs = [[['outbreak']], [['death_coil']], [['scourge_strike']],
                [['outbreak'], ['death_coil']], [['scourge_strike'], ['outbreak']],
                [['death_coil'], ['scourge_strike'], ['outbreak']]]
    sources = [dict(candidate_id=str(i), source_id=str(i), source_revision=digest(program),
        label='constructed', class_name='deathknight', spec='unholy', source='constructed',
        active=True, unavailable_reason='', original='constructed', instructions='constructed',
        semantic='preserved', changes=[], family='manual', core=[], program=program)
        for i, program in enumerate(programs)]
    read = result_store.read_records
    installed = Path(os.environ['DATA_STORE_TEST_SKILL'])
    api = runpy.run_path(str(installed / 'scripts/data_store.py'))
    select_definition = burst.select_definition
    definition = json.loads((root / 'projects/sim2gse/burst/unholy.json').read_text(encoding='utf-8'))
    definition['definition_id'] = burst.definition_id(definition)

    def select(character):
        return deepcopy(definition) if result_store.DATA_ROOT == root / 'data' else select_definition(character)

    def read_records(table, key):
        return deepcopy(sources) if table == 'seed_candidates' else read(table, key)

    def run(profile, folder, mode='baseline', options=(), **kwargs):
        if kwargs.get('on_start'):
            kwargs['on_start']()

    def reference(*args, **kwargs):
        engine.run(args[0], Path(args[1]), options=[f"iterations={kwargs.get('iterations', 100)}"])
        native = fast._fast_reference(*args, **kwargs)
        if "San'layn" in Path(args[0]).read_text(encoding='utf-8'):
            native['static_snapshot']['hero_subtree_ids'] = [31]
        return native

    def evaluate(*args, **kwargs):
        engine.run(args[0], Path(args[2]), mode='controlled',
                   options=[f"iterations={kwargs['iterations']}"], on_start=kwargs.get('on_native_start'))
        kwargs.pop('on_native_start', None)
        kwargs.pop('burst_candidate', None)
        kwargs.pop('input_sources', None)
        # Independent confirmation has a different landscape: do not assert only coarse scores.
        clicks = args[1]['compiled_program']['clicks']
        score = 1000 + len(clicks) if kwargs['seed'] % 2 else 1200 - len(clicks)
        return fast._fast_evaluate(*args, **kwargs, score=score)

    with ExitStack() as stack:
        stack.enter_context(fast._fast_initialization())
        stack.enter_context(patch.object(engine, 'training_template', return_value=profile))
        stack.enter_context(patch.object(engine, 'run', side_effect=run))
        stack.enter_context(patch.object(engine, 'reference', side_effect=reference))
        stack.enter_context(patch.object(engine, 'prepare_loop', side_effect=lambda *a, **k:
                            (fast._fast_capabilities(), fast._fast_capabilities(), None)))
        stack.enter_context(patch.object(result_store, 'read_records', side_effect=read_records))
        stack.enter_context(patch.object(result_store, '_SKILL_API', api))
        stack.enter_context(patch.object(burst, 'select_definition', side_effect=select))
        stack.enter_context(patch.object(sequence, 'evaluate', side_effect=evaluate))
        yield dict(data_root=output.parent / 'data')
