"""Isolated experiment checks: constructed native boundaries never supply real results."""
import json
import os
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import runpy
from copy import deepcopy
from unittest.mock import patch, Mock
ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / 'scripts/dev/sim2gse/population_ab.py'

def module():
    sys.path.append(str(ROOT / '.local/population-mvp/venv/lib/python3.12/site-packages'))
    return runpy.run_path(str(CLI))

class PilotCheck(unittest.TestCase):
    def test_windows_public_preflight_preserves_native_lock_module_without_native(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
            code = (
                "import subprocess,sys,types,runpy,shutil,importlib.metadata;"
                "locks=types.ModuleType('msvcrt');locks.LK_NBLCK=2;locks.LK_UNLCK=0;"
                "original=lambda *args:None;locks.locking=original;sys.modules['msvcrt']=locks;"
                "sys.platform='win32';sys.argv=" + repr([str(CLI),'--three-strategy','--materials',
                    str(ROOT/'.local/population-mvp/materials.json'),'--output',tmp,'--check-only']) + ";"
                "runpy.run_path(" + repr(str(CLI)) + ",run_name='__main__');"
                "assert sys.modules['msvcrt'] is locks and locks.locking is original"
            )
            result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['native_starts'],0)

    def test_windows_parent_uses_existing_job_runner_and_fresh_arm_directory(self):
        m=module();values=m['run_three'].__globals__
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['three_manifest_for'](source)
        manifest['slots']=manifest['slots'][:3]
        manifest['blocks']=manifest['blocks'][:1]
        for outcome in ('success','exit_failure','timeout'):
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
                output=Path(tmp)
                def prepare(source,output,manifest,deadline):
                    m['write'](output/'context.json',{})
                    return {}
                def worker(command,cwd,*,timeout_seconds,runtime,output_dir):
                    folder=Path(command[command.index('--output')+1])
                    self.assertFalse(folder.exists(),'Driver logs must not create the fresh arm output')
                    self.assertNotIn('--parent-death-exec',command)
                    self.assertEqual(output_dir,output/'worker-logs'/folder.name)
                    self.assertGreater(timeout_seconds,0)
                    self.assertLessEqual(timeout_seconds,200)
                    if outcome=='timeout':raise m['runtime'].ProcessTimeout('constructed Job timeout')
                    m['write'](folder/'arm.json',dict(compliant=True,complete_generations=1,
                        winner=None,errors=[],budget_met=True,endpoint=[dict(dps=100.)]*4))
                    return m['runtime'].ProcessResult(0 if outcome=='success' else 7,b'done',b'',0.01)
                native=Mock(side_effect=AssertionError('native forbidden'))
                with patch.object(values['sys'],'platform','win32'), \
                     patch.dict(values,ENTRY=time.monotonic(),prepare_three=prepare), \
                     patch.object(m['runtime'],'_create_process',native), \
                     patch.object(m['runtime'],'run_command',side_effect=worker) as launch, \
                     patch.object(values['subprocess'],'Popen',side_effect=AssertionError('Windows must use Job runner')), \
                     patch.object(values['os'],'killpg',create=True,side_effect=AssertionError('No Linux groups on Windows')):
                    result=m['run_three'](source,output,deepcopy(manifest))
                    self.assertIs(m['runtime']._create_process,native)
                self.assertEqual(launch.call_count,3)
                self.assertNotIn('preparation_error',result)
                self.assertEqual(result['slots'][0]['compliant'],outcome=='success')
                self.assertTrue((output/'0-console.log').exists())

    def test_equivalent_parent_trees_rebind_feedback_for_each_mutation(self):
        import random
        from types import SimpleNamespace
        m=module();sys.path.insert(0,str(ROOT/'tests/sim2gse'))
        from test_search import _fast_capabilities
        from search import _parent_positions
        from deap import algorithms
        caps=_fast_capabilities()
        flat=[['outbreak'],['death_coil'],['outbreak'],['death_coil']]
        loop=[dict(kind='Loop',count=2,blocks=[['outbreak'],['death_coil']])]
        key=m['canonicalize_search_program'](flat,caps)['identity']
        self.assertEqual(key,m['canonicalize_search_program'](loop,caps)['identity'])
        state=dict(evidence_kind='constructed_native_boundary',archive=[],seen=[])
        store=SimpleNamespace(state=state,checkpoint=lambda:None)
        positions=[dict(click_position=3,action_position=0,unresolved_inputs=1,ambiguous=False)]
        bindings=[]
        def feedback(program):
            bound=_parent_positions(program,caps,positions)
            bindings.append(bound[0]['source_position'])
            return dict(positions=bound)
        def score(program,stage,index):
            if not state['archive']:
                state['archive'].append(dict(key=key,program=deepcopy(program),batches=[dict(dps=100.)]))
            return dict(candidate_key=key,cached=False,dps=100.)
        def generation(population,toolbox,**kwargs):
            for program in (flat,loop):
                parent=deepcopy(population[0]);parent[:]=deepcopy(program)
                member=toolbox.clone(parent)
                random.seed(4)  # Exercises feedback-directed repair, not a random structural edit.
                toolbox.mutate(member)
            raise m['runtime'].BudgetExceeded('constructed generation end')
        run=m['ExperimentRuntime'](200,time.monotonic()+200)
        runner=m['three_evolution']('A',[dict(key=key,id='original',program=flat,lineage=['original'],original=True)],
            caps,store,run,dict(search_seed=400000000),run.deadline)
        with patch.object(algorithms,'eaSimple',side_effect=generation):
            runner(evaluate=score,feedback=feedback)
        self.assertEqual(bindings,[{'segment':3},{'segment':0,'loop_block':1}])

    def test_summary_budget_includes_final_atomic_save(self):
        m=module();values=m['run_three'].__globals__;clock=[0.]
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['three_manifest_for'](source)
        original_write=m['write']
        def write(path,value):
            original_write(path,value)
            if Path(path).name=='summary.json' and clock[0]==7799:
                clock[0]=7801
        def prepare(source,output,manifest,deadline):
            original_write(output/'context.json',{})
            clock[0]=7799
            return {}
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(values['time'],'monotonic',side_effect=lambda:clock[0]), \
             patch.dict(values,ENTRY=0,prepare_three=prepare,write=write):
            result=m['run_three'](source,Path(tmp),manifest)
            saved=json.loads((Path(tmp)/'summary.json').read_text())
        self.assertFalse(result['budget_met'])
        self.assertFalse(saved['budget_met'])
        self.assertEqual(saved['elapsed_seconds'],7801)
        self.assertEqual(saved['statistics']['status'],'incomplete_budget')
        self.assertIsNone(saved['statistics']['winner'])

    def test_parent_termination_reaps_worker_and_constructed_native(self):
        import signal
        def alive(pid):
            try:return Path(f'/proc/{pid}/stat').read_text().split()[2]!='Z'
            except FileNotFoundError:return False
        for stop_signal in (signal.SIGTERM,signal.SIGKILL):
            with self.subTest(signal=stop_signal),tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
                root=Path(tmp);ready=root/'worker.pid';native=root/'native.pid'
                worker_code=("import runpy,time;from pathlib import Path;"
                    f"m=runpy.run_path({str(CLI)!r});"
                    f"p=m['CloudProcess']([{sys.executable!r},'-c','import time;time.sleep(60)'],Path({str(ROOT)!r}),Path({tmp!r}));"
                    f"Path({str(native)!r}).write_text(str(p.process.pid));time.sleep(60)")
                driver_code=f'''
import runpy,sys,subprocess,time
from pathlib import Path
sys.path.append({str(ROOT / '.local/population-mvp/venv/lib/python3.12/site-packages')!r})
m=runpy.run_path({str(CLI)!r});v=m['run_three'].__globals__
source=m['load_materials'](Path({str(ROOT / '.local/population-mvp/materials.json')!r}))
manifest=m['three_manifest_for'](source)
real_popen=subprocess.Popen
def launch(command,**kwargs):
    prefix=command[:command.index('--parent-death-exec')+2] if '--parent-death-exec' in command else []
    child=real_popen(prefix+[sys.executable,'-c',{worker_code!r}],**kwargs)
    Path({str(ready)!r}).write_text(str(child.pid))
    return child
def prepare(source,output,manifest,deadline):
    m['write'](output/'context.json',{{}})
    return {{}}
v['prepare_three']=prepare
subprocess.Popen=launch
m['run_three'](source,Path({tmp!r}),manifest)
'''
                driver=subprocess.Popen([sys.executable,'-c',driver_code],cwd=ROOT,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                owned=[]
                try:
                    until=time.monotonic()+10
                    while not native.exists() and time.monotonic()<until and driver.poll() is None:time.sleep(.02)
                    self.assertTrue(native.exists(),'Constructed worker/native did not start')
                    owned=[int(ready.read_text()),int(native.read_text())]
                    os.kill(driver.pid,stop_signal);driver.wait(timeout=5)
                    until=time.monotonic()+5
                    while any(alive(pid) for pid in owned) and time.monotonic()<until:time.sleep(.02)
                    self.assertFalse(any(alive(pid) for pid in owned),'Owned worker/native outlived parent')
                finally:
                    for pid in owned:
                        try:os.kill(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    if driver.poll() is None:driver.kill()
                    driver.wait(timeout=5)

    def test_heartbeat_threadpool_native_launch_uses_no_preexec_python(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        m=module();values=m['CloudProcess'].__init__.__globals__
        real_popen=subprocess.Popen
        starts=[]
        def launch(*args,**kwargs):
            self.assertNotIn('preexec_fn',kwargs,'Threaded launches must do parent binding after exec')
            starts.append(threading.active_count())
            return real_popen(*args,**kwargs)
        code=('import ctypes,signal,sys;value=ctypes.c_int();'
              'result=ctypes.CDLL(None).prctl(2,ctypes.byref(value),0,0,0);'
              'sys.exit(0 if result==0 and value.value==signal.SIGKILL else 2)')
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
            route=m['isolate_center'](Path(tmp));folder=route/'task';folder.mkdir()
            store=m['TaskStore'](folder)
            try:
                with store.active(m['runtime'].TaskRuntime(10)),                      patch.object(values['subprocess'],'Popen',side_effect=launch),                      ThreadPoolExecutor(max_workers=2) as pool:
                    def native(index):
                        child=m['CloudProcess']([sys.executable,'-c',code],ROOT,route)
                        try:return child.wait(5)
                        finally:child.terminate();child.close()
                    self.assertEqual(list(pool.map(native,range(6))),[0]*6)
            finally:store.close()
        self.assertTrue(all(count>=3 for count in starts))

    def test_three_strategy_public_preflight_without_native(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.local/population-mvp') as tmp:
            result = subprocess.run([sys.executable, str(CLI), '--three-strategy', '--materials',
                '.local/population-mvp/materials.json', '--output', tmp, '--check-only'],
                cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['native_starts'], 0)
            manifest = data['manifest']
            self.assertEqual([b['order'] for b in manifest['blocks']], ['ABC', 'BCA', 'CAB'] * 4)
            self.assertEqual(len(manifest['slots']), 36)
            self.assertEqual(manifest['total_seconds'], 7800)
            self.assertEqual(manifest['arm_seconds'], 200)
            self.assertEqual(manifest['statistical_plan']['correction'], 'Holm')
            self.assertEqual(manifest['statistical_plan']['required_complete_arms'], 36)
            self.assertEqual(data['input_freeze'], 'pending_real_preparation')
            for block in manifest['blocks']:
                stages = block['stages']
                self.assertEqual([stages[x]['iterations'] for x in ('search', 'selection', 'endpoint')], [32, 128, 128])
                self.assertEqual([len(stages[x]['seeds']) for x in ('search', 'selection', 'endpoint')], [1, 2, 4])
                seeds = [seed for stage in stages.values() for seed in stage['seeds']]
                self.assertEqual(len(seeds), len(set(seeds)))

    @classmethod
    def three_cli_fixture(cls):
        if not hasattr(cls, '_three_fixture'):
            temporary = tempfile.TemporaryDirectory(dir=ROOT / '.local/population-mvp')
            cls.addClassCleanup(temporary.cleanup)
            output = Path(temporary.name) / 'run'
            result = subprocess.run([sys.executable, str(CLI), '--three-strategy', '--materials',
                '.local/population-mvp/materials.json', '--output', str(output),
                '--constructed-native-adapter', str(ROOT / 'tests/sim2gse/research/three_strategy_native_adapter.py')],
                cwd=ROOT, text=True, capture_output=True, timeout=300)
            if result.returncode != 0:
                raise AssertionError(result.stderr[-4000:])
            cls._three_fixture = output, json.loads(result.stdout)
        return cls._three_fixture

    def test_three_strategy_cli_runs_official_generations_and_independent_endpoint(self):
        output, data = self.three_cli_fixture()
        self.assertEqual(data['evidence_kind'], 'constructed_native_boundary')
        self.assertEqual([slot['index'] for slot in data['slots']], list(range(36)))
        self.assertEqual(data['attempted'], 36)
        self.assertEqual(data['compliant_arms'], 36, data)
        frozen = json.loads((output / 'inputs.json').read_text())
        self.assertEqual(len(frozen['rows']), 8)
        self.assertEqual(len({r['key'] for r in frozen['rows']}), 8)
        self.assertEqual([r['lineage'] for r in frozen['rows'][:4]], [r['lineage'] for r in frozen['rows'][4:]])
        processes, caches, duplicate_slots, cache_hits = set(), set(), False, 0
        for slot in data['slots']:
            arm = json.loads((output / slot['result_path']).read_text())
            processes.add(arm['worker_pid']); caches.add(arm['cache_root'])
            cache_hits += arm['search_cache_hits']
            duplicate_slots |= any(len(set(gen['population_slots'])) < 8 for gen in arm['generations'])
            self.assertGreater(arm['complete_generations'], 0, arm)
            self.assertEqual(len(arm['population_slots']), 8)
            self.assertEqual(len(arm['selection']), 2)
            self.assertTrue(all(len(row['scores']) == 2 for row in arm['selection']))
            self.assertEqual(len(arm['endpoint']), 4)
            self.assertEqual(arm['winner']['selection_mean_dps'], max(r['mean_dps'] for r in arm['selection']))
            self.assertTrue(all(row['candidate_key'] == arm['winner']['key'] for row in arm['endpoint']))
            self.assertEqual({row['iterations'] for row in arm['search_scores']}, {32})
            self.assertFalse({row['seed'] for row in arm['endpoint']} &
                             {row['seed'] for choice in arm['selection'] for row in choice['scores']})
            observed = json.loads((output / str(slot['index']) / 'constructed-algorithm-observations.json').read_text())
            if slot['strategy'] in 'AB':
                self.assertTrue(observed)
                self.assertEqual({r['name'] for r in observed}, {'eaSimple' if slot['strategy']=='A' else 'eaMuPlusLambda'})
                self.assertTrue(all(r['population'] == 8 and r['ngen'] == 1 for r in observed))
                if slot['strategy'] == 'B':
                    self.assertTrue(all((r['mu'],r['lambda_'],r['cxpb'],r['mutpb']) == (8,16,.5,.5) for r in observed))
            else:
                self.assertFalse(observed)
                original_keys = {r['key'] for r in frozen['rows'] if r['original']}
                self.assertTrue(all(len(gen['reserved_originals']) == 2 and set(gen['reserved_originals']) <= original_keys
                                    for gen in arm['generations']))
        self.assertEqual(len(processes), 36)
        self.assertEqual(len(caches), 36)
        self.assertTrue(duplicate_slots, 'Official duplicate population slots must not be filtered')
        self.assertGreater(cache_hits, 0)
        self.assertEqual(data['statistics']['winner'], 'A')
        self.assertEqual(data['conclusion'], 'statistical_winner')
        for comparison in data['statistics']['comparisons']:
            self.assertEqual((comparison['wins'],comparison['losses'],comparison['ties']), (12,0,0))
            self.assertEqual(comparison['raw_p'], .00048828125)
            self.assertEqual(comparison['holm_p'], .00146484375)

    def test_three_strategy_cli_failure_preservation_and_exact_deadline(self):
        output, _ = self.three_cli_fixture()
        adapter = str(ROOT / 'tests/sim2gse/research/three_strategy_native_adapter.py')
        def worker(name, environment=None, deadline=None):
            folder = output / name
            result = subprocess.run([sys.executable, str(CLI), '--three-strategy', '--materials',
                str(output / 'materials.json'), '--output', str(folder), '--manifest', str(output / 'manifest.json'),
                '--arm', '1', '--deadline', str(time.monotonic()+200 if deadline is None else deadline),
                '--constructed-native-adapter', adapter], cwd=ROOT, text=True, capture_output=True,
                timeout=30, env=dict(os.environ, **(environment or {})))
            return result, folder
        result, folder = worker('failed-endpoint', {'THREE_TEST_ENDPOINT_FAILURE':'1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        arm = json.loads((folder / 'arm.json').read_text())
        self.assertFalse(arm['compliant'])
        self.assertEqual(len(arm['endpoint']), 3)
        self.assertIsNotNone(arm['winner'])
        self.assertTrue(arm['search_scores'])
        self.assertEqual(arm['errors'][0]['stage'], 'endpoint')
        result, folder = worker('partial-generation', {'THREE_TEST_SEARCH_BATCHES':'9'})
        self.assertEqual(result.returncode, 0, result.stderr)
        arm = json.loads((folder / 'arm.json').read_text())
        self.assertFalse(arm['compliant'])
        self.assertEqual(arm['complete_generations'], 0)
        self.assertTrue(arm['partial_generation'])
        self.assertGreater(len(arm['search_scores']), 8)
        self.assertEqual(len(arm['population_slots']), 8)
        result, folder = worker('expired-before-search', deadline=time.monotonic()-1)
        self.assertEqual(result.returncode, 0, result.stderr)
        arm = json.loads((folder / 'arm.json').read_text())
        self.assertFalse(arm['compliant'])
        self.assertFalse(arm['budget_met'])
        self.assertEqual(arm['search_scores'], [])
        self.assertEqual(arm['complete_generations'], 0)
        result, folder = worker('failed-save', {'THREE_TEST_SEARCH_BATCHES':'9','THREE_TEST_SAVE_FAILURE':'1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('constructed final save failure', result.stderr)
        self.assertFalse((folder / 'arm.json').exists())
        progress = json.loads((folder / 'task/progress.json').read_text())
        self.assertGreater(progress['completed_batches'], 8)

    def test_three_strategy_cli_freeze_failure_and_global_deadline_keep_all_slots(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / '.local/population-mvp')
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / 'input'
        output.mkdir()
        (output / 'materials.json').write_text((ROOT / '.local/population-mvp/materials.json').read_text())
        adapter = str(ROOT / 'tests/sim2gse/research/three_strategy_native_adapter.py')
        folder = output.parent / 'global-deadline'
        result = subprocess.run([sys.executable, str(CLI), '--three-strategy', '--materials',
            str(output / 'materials.json'), '--output', str(folder), '--constructed-native-adapter', adapter],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
            env=dict(os.environ, THREE_TEST_GLOBAL_DEADLINE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report['budget_met'])
        self.assertEqual(report['attempted'], 0)
        self.assertEqual(len(report['slots']), 36)
        self.assertEqual(report['conclusion'], 'confirmation_incomplete')
        # A source at the 128-block limit makes its one fixed duplication illegal. Reject, never retry.
        m=module()
        caps=json.loads((ROOT / '.local/population-mvp/pilot-rebuilt-01/0/prepare/capabilities/catalogue.json').read_text())
        source=json.loads((output / 'materials.json').read_text())
        row=source['material_snapshot']['materials'][0]
        row['program']=[['outbreak'] for _ in range(128-len(caps['precombat_actions']))]
        row['program_sha256']=m['digest'](row['program'])
        row['behavior_id']=m['canonicalize_search_program'](row['program'],caps)['identity']
        materials=output.parent/'single-action.json';materials.write_text(json.dumps(source))
        folder=output.parent/'freeze-failure'
        result=subprocess.run([sys.executable,str(CLI),'--three-strategy','--materials',str(materials),
            '--output',str(folder),'--constructed-native-adapter',adapter],cwd=ROOT,text=True,
            capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertIn('128',report['preparation_error'])
        self.assertEqual(report['attempted'],0)
        self.assertEqual(len(report['slots']),36)
        self.assertFalse((folder/'inputs.json').exists())

    def test_confirmatory_summary_keeps_ties_and_missing_blocks(self):
        # Deterministic arithmetic supplement to the actual CLI end-to-end confirmation report.
        output, _ = self.three_cli_fixture()
        manifest = json.loads((output / 'manifest.json').read_text())
        m = module()
        def slots_with_ties(tie_blocks):
            return [dict(slot, status='finished', compliant=True, exit_code=0,
                endpoint_mean_dps=(1 if slot['block'] >= 12-tie_blocks else {'A':3,'B':2,'C':1}[slot['strategy']]))
                for slot in manifest['slots']]
        tied = m['summarize_three'](slots_with_ties(2), manifest)
        self.assertEqual(tied['conclusion'], 'unable_to_determine_winner')
        for comparison in tied['statistics']['comparisons']:
            self.assertEqual((comparison['wins'],comparison['losses'],comparison['ties']), (10,0,2))
            self.assertEqual(comparison['planned_n'], 12)
            self.assertEqual(comparison['raw_p'], .03857421875)
            self.assertEqual(comparison['holm_p'], .11572265625)
        missing = slots_with_ties(0);missing[0]['compliant']=False
        report = m['summarize_three'](missing,manifest)
        self.assertEqual(report['statistics']['status'], 'incomplete')
        self.assertIsNone(report['statistics']['winner'])
        self.assertEqual(report['conclusion'], 'confirmation_incomplete')
        self.assertTrue(all(row['holm_p'] is None for row in report['statistics']['comparisons']))
        self.assertEqual(len(report['slots']),36)

    def test_public_cli_manifest_without_native(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.local/population-mvp') as tmp:
            result = subprocess.run([sys.executable, str(CLI), '--materials',
                '.local/population-mvp/materials.json', '--output', tmp, '--check-only'],
                cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['native_starts'], 0)
            self.assertEqual(len(data['manifest']['trials']), 8)
            self.assertEqual(data['manifest']['total_seconds'], 4800)
            self.assertTrue(all(data['checks'].values()), data['checks'])

    def test_manifest_collision_change_balance_and_failure_slots(self):
        m = module()
        source = m['load_materials'](ROOT / '.local/population-mvp/materials.json')
        manifest = m['manifest_for'](source)
        for i in range(4):
            self.assertNotEqual(manifest['trials'][i]['order'], manifest['trials'][i+4]['order'])
            self.assertEqual(manifest['trials'][i]['material_ids'], manifest['trials'][i+4]['material_ids'])
        for key, value in [('search_seed', 200000001), ('endpoint_seeds', [200000000]*4), ('order','BA')]:
            changed = deepcopy(manifest)
            changed['trials'][0][key] = value
            with self.assertRaises(ValueError): m['validate_manifest'](changed, source)
        slots = [dict(index=i,status='not_started') for i in range(8)]
        slots[0] = dict(index=0,status='failed',result={'status':'failed'})
        slots[1] = dict(index=1,status='finished',result={'status':'complete_pair','log_ratio':.01})
        result = m['summarize'](slots)
        self.assertEqual((result['attempted'],result['complete_pairs'],len(result['slots'])),(2,1,8))
        self.assertIsNone(result['conditional_log_ratio_sd'])

    def test_common_pool_original_structures_and_private_rng_restore(self):
        m = module()
        sys.path.insert(0,str(ROOT/'tests/sim2gse'))
        from test_search import _fast_capabilities
        import random
        caps = _fast_capabilities()
        programs = [[['outbreak']], [['death_coil']], [['scourge_strike']], [['dark_transformation']]]
        rows = [dict(id=str(i),program=p) for i,p in enumerate(programs)]
        supplier = m['JointPopulation'](rows,caps,{'unit':'identity'})
        archive = [dict(key=m['canonicalize_search_program'](p,caps)['identity'],program=p,
                        batches=[dict(requested_iterations=32,samples=31,dps=10+i)])
                   for i,p in enumerate(programs)]
        # Strong nonpromoted descendants share ancestry; exact original structure still reserved.
        for i in range(6):
            p = [['outbreak']]*(i+2)
            archive.append(dict(key=m['canonicalize_search_program'](p,caps)['identity'],program=p,
                training_lineage=['0','1','2','3'],batches=[dict(requested_iterations=32,samples=31,dps=100+i)]))
        original=deepcopy(archive); state={};rng=random.Random(123)
        output=supplier(archive=archive,seen=set(),rng=rng,state=state,feedback_for=lambda r:{})
        self.assertEqual(archive,original)
        self.assertEqual(len(state['pool']),8)
        self.assertTrue(set(state['reserved_originals']).issubset(state['pool']))
        self.assertLessEqual(len(output),16)
        self.assertEqual(len({r['key'] for r in output}),len(output))
        self.assertTrue(any(len(r['lineage'])>1 for r in output))
        saved_state=json.loads(json.dumps(state));saved_rng=rng.getstate()
        a=supplier(archive=archive,seen=set(),rng=rng,state=state,feedback_for=lambda r:{})
        restored=random.Random();restored.setstate(saved_rng)
        b=supplier(archive=archive,seen=set(),rng=restored,state=saved_state,feedback_for=lambda r:{})
        self.assertEqual(a,b);self.assertEqual(state,saved_state);self.assertEqual(rng.getstate(),restored.getstate())
        self.assertNotEqual(state['reserved_originals'],list(supplier.original)[:2])

    def test_native_score_reset_list_contract_without_native(self):
        m=module();v=m['native_score'].__globals__
        import program, sequence, burst
        score=Mock(return_value={'summary':{}})
        context=dict(capabilities={},native={'identity':{}},character=None,burst={'candidate':{}},
                     config={'reset_events':()},simulation_config={})
        with patch.object(program,'from_search_program',return_value={}), \
             patch.object(program,'compile_program',return_value={}), \
             patch.object(burst,'combined_inputs',return_value=([],[])),patch.object(sequence,'evaluate',score):
            m['native_score'](None,[],Path('unit'),context,None,123,128)
        self.assertIsInstance(score.call_args.kwargs['reset_events'],list)

    def test_single_loop_and_castsequence_cross_only_complete_blocks(self):
        import random
        m=module()
        sequence=dict(kind='CastSequence',members=['outbreak','death_coil'],reset={'flags':[]})
        left=[dict(kind='Loop',count=2,blocks=[['outbreak'],sequence])]
        right=[dict(kind='Loop',count=3,blocks=[['scourge_strike'],['death_coil'],['outbreak']])]
        self.assertTrue(m['crossover_blocks'](left,right,random.Random(1)))
        self.assertEqual((left[0]['count'],right[0]['count']),(2,3))
        self.assertEqual(right[0]['blocks'][-1],sequence)
        sequence['members'].append('scourge_strike')
        self.assertEqual(len(right[0]['blocks'][-1]['members']),2) # Detached complete block.
        self.assertFalse(m['crossover_blocks']([['outbreak']],[['death_coil']],random.Random(1)))

    def test_hard_runtime_deadlines_and_no_made_up_winner(self):
        m=module();v=m['ExperimentRuntime'].__init__.__globals__;clock=[0.]
        with patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]):
            run=m['ExperimentRuntime'](180,100)
            clock[0]=99;run.check()
            clock[0]=100
            with self.assertRaises(m['runtime'].BudgetExceeded):run.check()
        self.assertIsNone(m['usable_winner']({'best':'missing','archive':[]}))

    def test_arm_centers_and_adjacent_caches_are_actually_distinct(self):
        m=module();shared=[];roots=[]
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
            for name in 'AB':
                route=m['isolate_center'](Path(tmp)/name)
                folder=route/'tasks/0';folder.mkdir(parents=True)
                store=m['TaskStore'](folder)
                try:
                    shared.append(next(r[2] for r in store.db.execute('PRAGMA database_list') if r[1]=='shared'))
                    roots.append(str(m['result_store'].DATA_ROOT))
                finally:store.close()
        self.assertNotEqual(shared[0],shared[1]);self.assertNotEqual(roots[0],roots[1])

    def test_training_supplier_original_scoring_and_atomic_abort(self):
        m=module();sys.path.insert(0,str(ROOT/'tests/sim2gse'))
        from test_search import _fast_capabilities,_fast_reference,_fast_evaluate,_fast_search_boundary,sample_profile
        from task import parse_character
        import sequence
        caps=_fast_capabilities()
        rows=[dict(id=x,program=[[x]]) for x in ('outbreak','death_coil','scourge_strike','dark_transformation')]
        supplier=m['JointPopulation'](rows,caps,{'unit':'native-boundary'})
        class Once:
            identity=supplier.identity
            calls=0
            def __call__(self,**kw):
                self.calls+=1
                return supplier(**kw) if self.calls==1 else []
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp:
            route=m['isolate_center'](Path(tmp));profile=route/'unit.simc';profile.write_text(sample_profile())
            character=parse_character(profile.read_text());folder=route/'tasks/one';folder.mkdir(parents=True)
            store=m['TaskStore'](folder);store.state.update(run_id='unit-only',starts=[r['program'] for r in rows])
            config=m['config_for'](dict(batch_targets=(32,),round_candidate_limit=16,max_processes=2,
                rule_initialization_enabled=False,adaptive_selector_enabled=False),training=True)
            calls=[]
            def boundary(*a,**kw):
                calls.append((kw['seed'],kw['iterations']))
                score=100.0
                if len(a[1]['blocks'])>1:score=1000 if kw['seed']<config['random_seed']+100000 else 1
                return _fast_evaluate(*a,**kw,score=score)
            args=dict(profile=profile,character=character,capabilities=caps,destination=folder,config=config,
                condition_key='unit',store=store,training=True,simulation_config={'target_count':1,'scene':'single_target'})
            try:
                with _fast_search_boundary(),patch.object(sequence,'evaluate',side_effect=boundary):
                    args['reference']=_fast_reference(profile,route/'reference',character)
                    result=m['optimize'](**args,runtime=m['runtime'].TaskRuntime(15),training_candidate_supplier=Once())
                self.assertEqual(len(store.state['training_candidate_supplier']['state']['pool']),4)
                self.assertTrue(any(it==100 for seed,it in calls))
                self.assertTrue(any(r['batches'][0]['dps']==1000 for r in result['search']['records']))
                best=m['usable_winner'](store.state)
                self.assertIsNotNone(best)
                self.assertLess(best['score'],1000)
                store.state.update(phase='search',pending=[],no_improvement=config['no_improvement_rounds'])
                exhausted=Mock(return_value=[]);exhausted.identity=supplier.identity
                with _fast_search_boundary(),patch.object(sequence,'evaluate',side_effect=boundary):
                    m['optimize'](**args,runtime=m['runtime'].TaskRuntime(15),training_candidate_supplier=exhausted)
                exhausted.assert_not_called()
                self.assertEqual(store.state['stop_reason'],'no_improvement')
                saved=deepcopy(store.state['training_candidate_supplier']);saved_rng=deepcopy(store.state['rng'])
                class Interrupted:
                    identity=supplier.identity
                    def __call__(self,**kw):
                        kw['rng'].random();kw['state']['uncommitted']=True
                        raise m['runtime'].BudgetExceeded('constructed interruption')
                store.state.update(phase='search',pending=[],no_improvement=0)
                with _fast_search_boundary(),patch.object(sequence,'evaluate',side_effect=boundary):
                    m['optimize'](**args,runtime=m['runtime'].TaskRuntime(15),training_candidate_supplier=Interrupted())
                self.assertEqual(store.state['training_candidate_supplier'],saved)
                self.assertEqual(store.state['rng'],saved_rng)
                with self.assertRaises(ValueError):m['optimize'](**args,runtime=None)
                with self.assertRaises(ValueError):
                    m['optimize'](**dict(args,training=False),runtime=None,training_candidate_supplier=Once())
            finally:store.close()
            # Default non-training path remains the original optimizer, with no supplier state.
            folder=route/'tasks/default';folder.mkdir()
            store=m['TaskStore'](folder)
            store.state.update(run_id='unit-formal',starts=[rows[0]['program']])
            config=m['config_for'](dict(candidate_limit=2,batch_targets=(32,),round_candidate_limit=2,
                rule_initialization_enabled=False,adaptive_selector_enabled=False,diagnostic_logging=False))
            try:
                with _fast_search_boundary():
                    m['optimize'](**dict(args,store=store,destination=folder,config=config,training=False),
                                  runtime=m['runtime'].TaskRuntime(10))
                self.assertNotIn('training_candidate_supplier',store.state)
            finally:store.close()

    def test_route_coverage_is_not_output_failure_and_setup_counts_in_deadline(self):
        m=module();v=m['run_route'].__globals__;clock=[0.]
        from contextlib import contextmanager
        class Store:
            def __init__(self,path):self.state={};clock[0]+=.1
            @contextmanager
            def active(self,run):yield;clock[0]+=.1
            def close(self):clock[0]+=.1
        row=dict(key='actual',score=100.,program=[['outbreak']],
                 batches=[dict(dps=100.,samples=31,requested_iterations=32)])
        def optimizer(**kw):
            clock[0]=kw['runtime'].deadline
            kw['store'].state.update(archive=[deepcopy(row)],best='actual',rounds=0)
        def isolate(path):clock[0]+=2;return path
        context=dict(config={},capabilities={},native={},character=None,burst={},simulation_config={})
        rows=[dict(id=str(i),program=[['outbreak']]) for i in range(4)]
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]), \
             patch.dict(v,ExperimentStore=Store,optimize=optimizer,isolate_center=isolate,
                        JointPopulation=lambda *a:None,write=lambda *a:None):
            for name in 'AB':
                clock[0]=0
                result=m['run_route'](name,rows,None,context,Path(tmp),600,{})
                self.assertFalse(result['coverage'])
                self.assertEqual(result['winner']['key'],'actual')
                self.assertTrue(result['budget_met'])
                self.assertLessEqual(clock[0],180)
            def overrun(path):clock[0]+=181;return path
            clock[0]=0
            with patch.dict(v,isolate_center=overrun):
                result=m['run_route']('B',rows,None,context,Path(tmp),600,{})
                self.assertFalse(result['budget_met']);self.assertIsNone(result['winner'])

    def test_trial_freezes_winners_four_endpoints_even_without_coverage(self):
        m=module();v=m['run_trial'].__globals__
        import engine,seed_training
        from task import parse_character
        sys.path.insert(0,str(ROOT/'tests/sim2gse'))
        from test_search import sample_profile
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['manifest_for'](source);trial=manifest['trials'][0]
        character=parse_character(sample_profile())
        definition={'definition_id':source['material_snapshot']['condition']['burst_definition_id']}
        inputs=dict(character=character,definition=definition,config={},simulation_config={})
        rows=source['material_snapshot']['materials'];seen=[];arms=[];omit_a=[False];fail_seed=[None]
        def route(name,*a):
            arms.append(name)
            if name=='A' and omit_a[0]:return dict(winner=None,coverage=False,budget_met=True,status='no_usable_output')
            return dict(winner=dict(program=deepcopy(rows[0]['program']),key=name),coverage=False,budget_met=True)
        def score(profile,program,folder,context,run,seed,iterations):
            seen.append((str(folder),seed,iterations))
            if seed==fail_seed[0]:raise m['runtime'].BudgetExceeded('constructed endpoint timeout')
            return {'summary':{'dps':100 if '/B/' not in str(folder) else 101,'samples':iterations-1}}
        def canonical(program,caps):return {'identity':next(r['behavior_id'] for r in rows if r['program']==program)}
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(engine,'reference',return_value={'identity':{'spec_id':252,'race':character.race}}), \
             patch.object(engine,'prepare_loop',return_value=(None,{},{})), \
             patch.object(seed_training,'_training_inputs',return_value=inputs), \
             patch.dict(v,prepare_burst_source=lambda *a:None,run_route=route,native_score=score,
                        canonicalize_search_program=canonical,CloudProcess=Mock(side_effect=AssertionError('native forbidden'))):
            result=m['run_trial'](source,Path(tmp),trial,manifest,v['time'].monotonic()+600)
            omit_a[0]=True;fail_seed[0]=trial['endpoint_seeds'][-1]
            partial=m['run_trial'](source,Path(tmp)/'partial',trial,manifest,v['time'].monotonic()+600)
        self.assertEqual(arms,['A','B','A','B'])
        self.assertEqual(result['status'],'complete_pair',result)
        self.assertFalse(result['arms']['A']['coverage'])
        self.assertEqual(result['fixed_winners']['A']['key'],'A')
        for name in ('A','B','initial'):
            self.assertEqual([s['seed'] for s in result['endpoint'][name]['scores']],trial['endpoint_seeds'])
            self.assertEqual(len(result['endpoint'][name]['scores']),4)
        self.assertEqual(partial['status'],'incomplete_pair')
        self.assertNotIn('A',partial['fixed_winners'])
        self.assertNotIn('A',partial['endpoint'])
        self.assertEqual(len(partial['endpoint']['B']['scores']),3)
        self.assertEqual(partial['endpoint']['B']['status'],'incomplete')

    def test_parent_preserves_all_slots_launch_failure_and_global_deadline(self):
        m=module();v=m['run_pilot'].__globals__;clock=[0.];calls=[]
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['manifest_for'](source)
        def failed_launch(*a,**kw):
            calls.append(a[0]);clock[0]+=601
            raise OSError('constructed worker launch failure')
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]), \
             patch.dict(v,ENTRY=0),patch.object(v['subprocess'],'Popen',side_effect=failed_launch):
            result=m['run_pilot'](source,Path(tmp),manifest)
        self.assertEqual(len(calls),8)
        self.assertEqual([t['index'] for t in result['slots']],list(range(8)))
        self.assertEqual(result['complete_pairs'],0)
        self.assertFalse(result['budget_met']) # Deliberately broken external launch fixture.
        self.assertTrue(all(t['status']=='failed' for t in result['slots']))
        clock[0]=4799;calls.clear()
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]), \
             patch.dict(v,ENTRY=0),patch.object(v['subprocess'],'Popen',side_effect=failed_launch):
            result=m['run_pilot'](source,Path(tmp),manifest)
        self.assertFalse(calls)
        self.assertEqual(result['attempted'],0)
        self.assertEqual(len(result['slots']),8)

    def test_parent_timeout_owns_entire_worker_group(self):
        m=module();v=m['run_pilot'].__globals__;clock=[0.]
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['manifest_for'](source);process=Mock(pid=123)
        def wait(timeout=None):
            if timeout is not None:
                clock[0]=4799
                raise subprocess.TimeoutExpired('constructed worker',timeout)
            return -9
        process.wait.side_effect=wait;process.poll.return_value=-9
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]),patch.dict(v,ENTRY=0), \
             patch.object(v['subprocess'],'Popen',return_value=process) as launch, \
             patch.object(v['os'],'killpg') as kill:
            result=m['run_pilot'](source,Path(tmp),manifest)
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        kill.assert_any_call(123,v['signal'].SIGKILL)
        self.assertEqual(result['attempted'],1)
        self.assertEqual(result['slots'][0]['exit_code'],-9)
        self.assertEqual(len(result['slots']),8)

    def test_exited_worker_group_cleanup_and_pair_budget_include_launch(self):
        m=module();v=m['run_pilot'].__globals__;clock=[0.];remaining=[];child_alive=[True]
        source=m['load_materials'](ROOT/'.local/population-mvp/materials.json')
        manifest=m['manifest_for'](source);process=Mock(pid=321)
        process.poll.return_value=-9
        def launch(*a,**kw):clock[0]+=10;return process
        def wait(timeout=None):
            if timeout is not None:remaining.append(timeout);clock[0]=4799
            return -9
        process.wait.side_effect=wait
        def kill(*a):child_alive[0]=False
        with tempfile.TemporaryDirectory(dir=ROOT/'.local/population-mvp') as tmp, \
             patch.object(v['time'],'monotonic',side_effect=lambda:clock[0]),patch.dict(v,ENTRY=0), \
             patch.object(v['subprocess'],'Popen',side_effect=launch),patch.object(v['os'],'killpg',side_effect=kill):
            result=m['run_pilot'](source,Path(tmp),manifest)
        with self.subTest('pair deadline includes launch'):
            self.assertEqual(remaining,[589])
        with self.subTest('exited worker leaves no owned children'):
            self.assertFalse(child_alive[0])
        self.assertEqual(result['slots'][0]['exit_code'],-9)

    def test_equal_suffix_is_not_crossover_and_mutation_keeps_parent_feedback(self):
        import random
        m=module();sys.path.insert(0,str(ROOT/'tests/sim2gse'))
        from test_search import _fast_capabilities
        caps=_fast_capabilities()
        programs=[[[x],['death_coil']] for x in ('outbreak','death_coil','scourge_strike','dark_transformation')]
        left,right=deepcopy(programs[0]),deepcopy(programs[1])
        self.assertFalse(m['crossover_blocks'](left,right,random.Random(1)))
        self.assertEqual((left,right),(programs[0],programs[1]))
        rows=[dict(id=str(i),program=p) for i,p in enumerate(programs)]
        archive=[dict(key=m['canonicalize_search_program'](p,caps)['identity'],program=p,
                      batches=[dict(requested_iterations=32,samples=31,dps=100+i)]) for i,p in enumerate(programs)]
        supplier=m['JointPopulation'](rows,caps,{'test':'same-suffix'});feedback=[]
        def mutation(program,caps,rng,*,feedback=None):
            self.assertIsNotNone(feedback)
            return deepcopy(list(program))+[['outbreak']]
        def parent(row):feedback.append(row['key']);return {'parent':row['key']}
        with patch.dict(m['JointPopulation'].__call__.__globals__,mutate=mutation):
            proposals=supplier(archive=archive,seen={r['key'] for r in archive},rng=random.Random(3),
                               feedback_for=parent,state={})
        self.assertTrue(proposals)
        self.assertTrue(all(not p['crossed'] and len(p['parents'])==1 and len(p['lineage'])==1 for p in proposals))
        self.assertTrue(feedback)

if __name__ == '__main__': unittest.main()
