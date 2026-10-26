"""Constructed native boundary for the actual experiment CLI, never real evidence."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

@contextmanager
def boundary(root, output):
    sys.path.insert(0, str(root / 'tests/sim2gse'))
    import engine, sequence, runtime
    import test_search as fast
    from deap import algorithms
    calls, seen = [], [0]
    original_simple, original_plus = algorithms.eaSimple, algorithms.eaMuPlusLambda
    def observed(function, name):
        def call(population, toolbox, *args, **kwargs):
            calls.append(dict(name=name, population=len(population),
                              cxpb=kwargs['cxpb'], mutpb=kwargs['mutpb'], ngen=kwargs['ngen'],
                              mu=kwargs.get('mu'), lambda_=kwargs.get('lambda_')))
            return function(population, toolbox, *args, **kwargs)
        return call
    def evaluate(*args, **kwargs):
        iterations = kwargs['iterations']
        if iterations == 32:
            seen[0] += 1
            if seen[0] > int(os.environ.get('THREE_TEST_SEARCH_BATCHES', '26')):
                raise runtime.BudgetExceeded('constructed search cutoff')
        if iterations == 128 and os.environ.get('THREE_TEST_ENDPOINT_FAILURE') and kwargs['seed'] % 1000000 == 300002:
            raise ValueError('constructed endpoint failure')
        # Constructed, preregistered A > B > C endpoint ordering, unrelated to selection scores.
        seed = kwargs['seed']
        score = 1000.0 - len(args[1]['compiled_program']['clicks'])
        if iterations == 128 and seed % 1000000 >= 300000:
            slot = int(sys.argv[sys.argv.index('--arm') + 1])
            strategy = ('ABC', 'BCA', 'CAB')[(slot // 3) % 3][slot % 3]
            score = {'A':3000.0, 'B':2000.0, 'C':1000.0}[strategy]
        if kwargs.get('burst_candidate') is not None:
            kwargs = {key: value for key, value in kwargs.items() if key not in ('burst_candidate', 'input_sources')}
        return fast._fast_evaluate(*args, **kwargs, score=score)
    def reference(*args, **kwargs):
        result = fast._fast_reference(*args, **kwargs)
        definition = json.loads((root / 'projects/sim2gse/burst/unholy.json').read_text())
        result['identity']['data_version'] = definition['data_version']
        return result
    def inspect(reference, folder):
        # Frozen real catalogue only supplies actions, not scores or current legality claims.
        caps = json.loads((root / '.local/population-mvp/pilot-rebuilt-01/0/prepare/capabilities/catalogue.json').read_text())
        Path(folder).mkdir(parents=True, exist_ok=True)
        return caps
    replace_file, monotonic = os.replace, time.monotonic
    def replace(source, destination):
        if Path(destination).name == 'arm.json' and os.environ.get('THREE_TEST_SAVE_FAILURE'):
            raise OSError('constructed final save failure')
        return replace_file(source, destination)
    with ExitStack() as stack:
        stack.enter_context(fast._fast_initialization())
        profile = engine.training_template()
        stack.enter_context(patch.object(os, 'replace', side_effect=replace))
        if os.environ.get('THREE_TEST_GLOBAL_DEADLINE'):
            stack.enter_context(patch.object(time, 'monotonic', side_effect=lambda: monotonic() + 7801))
        stack.enter_context(patch.object(engine, 'training_template', return_value=profile))
        stack.enter_context(patch.object(engine, 'reference', side_effect=reference))
        stack.enter_context(patch.object(engine, 'inspect', side_effect=inspect))
        stack.enter_context(patch.object(sequence, 'evaluate', side_effect=evaluate))
        stack.enter_context(patch.object(algorithms, 'eaSimple', observed(original_simple, 'eaSimple')))
        stack.enter_context(patch.object(algorithms, 'eaMuPlusLambda', observed(original_plus, 'eaMuPlusLambda')))
        try:
            yield
        finally:
            if output.exists():
                (output / 'constructed-algorithm-observations.json').write_text(json.dumps(calls))
