"""第三票：通过同一任务入口驱动搜索、复测与结果隔离。"""

from __future__ import annotations

import tempfile
import time
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))
from test_character_export import sample_profile
from task import cancel_task, read_task, resume_task, run_task, start_task, TaskError


def _fast_evaluate(profile, candidate, folder, *, character, iterations=100,
                   seed=20260912, trace=True, mode="controlled", input_times=None,
                   runtime=None):
    """构造稳定报告，保留 search.optimize 的选择、缓存和发布逻辑。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    input_times = list(range(0, 180000, 300)) if input_times is None else list(input_times)
    score = 100.0 + sum(
        command.get("spell_id", command.get("item_id", 0))
        for block in candidate["blocks"] for command in block
    ) / 1000.0
    samples = max(1, iterations - 1)
    report = json.loads((Path(profile).parent / "reference/native.json").read_text(encoding="utf-8"))
    player = next(row for row in report["sim"]["players"] if row["name"] == character.name)
    player["collected_data"]["dps"].update(mean=score, count=samples)
    player["collected_data"].setdefault("resource_overflowed", {}) \
        .setdefault(player["sim2gse_resource"], {})["mean"] = 0
    report["sim"]["statistics"]["raid_dps"].update(mean=score, count=samples)
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


@contextmanager
def _fast_search_boundary():
    """仅替换搜索结果生产；任务入口、TaskStore 和搜索状态机仍走真实代码。"""
    import codec
    import sequence

    def compiler(command, *args, **kwargs):
        output = b"CHECKSUM\ttest\n" if command[-1] == "checksum" else b"PASS\ttest\n"
        return SimpleNamespace(returncode=0, stdout=output, stderr=b"")

    with patch.object(codec, "run_command", side_effect=compiler), \
         patch.object(sequence, "evaluate", side_effect=_fast_evaluate):
        yield


class SearchAndValidationTests(TestCase):
    def test_public_entry_runs_multi_start_search_with_isolated_validation(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-search-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            result = run_task(
                source,
                destination,
                mode="optimize",
                search_config={
                    "total_budget_seconds": 20,
                    "search_budget_seconds": 8,
                    "candidate_limit": 4,
                    "batch_targets": (2,),
                    "validation_batches": 2,
                    "final_batches": 1,
                    "iterations": 2,
                    "scenarios": ("nominal",),
                    "max_processes": 1,
                },
            )

            self.assertEqual(result["status"], "validation_incomplete")
            self.assertGreaterEqual(len(result["search"]["starts"]), 2)
            self.assertIn("validation", result)
            self.assertIn("final", result)
            self.assertEqual(result["selected_candidate_key"], result["locked_candidate_key"])
            self.assertEqual((destination / "candidate.txt").read_text(encoding="ascii"), result["candidate"]["text"])
            self.assertNotEqual(result["search"]["dataset"], result["validation"]["dataset"])
            self.assertNotEqual(result["validation"]["dataset"], result["final"]["dataset"])

            search_seeds={row['request']['seed'] for record in result['search']['records'] for row in record['batches']}
            validation_seeds={row['request']['seed'] for record in result['validation']['records'] for row in record['candidate']+record['control']}
            final_seeds={row['request']['seed'] for scenario in result['final']['scenarios'].values() for row in scenario['candidate']+scenario['seed']}
            self.assertTrue(search_seeds and validation_seeds and final_seeds)
            self.assertFalse(search_seeds & validation_seeds or search_seeds & final_seeds or validation_seeds & final_seeds)

    def test_reference_start_keeps_executed_active_items(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-item-start-") as directory:
            source = Path(directory) / "角色.simc"
            source.write_text(sample_profile().replace('trinket1=,id=250245',
                              'trinket1=,id=273797,ilevel=311'), encoding='utf-8')
            with _fast_search_boundary():
                result = run_task(source, Path(directory)/'任务', search_config=dict(
                    total_budget_seconds=20, search_budget_seconds=8, candidate_limit=2,
                    batch_targets=(2,), iterations=2, final_iterations=2,
                    validation_batches=1, final_batches=1, scenarios=('nominal',), max_processes=1))
            self.assertIn('use_item,slot=trinket1',
                          [name for block in result['search']['starts'][1] for name in block])

    def test_complete_validation_without_proven_gain_keeps_the_seed(self):
        import search
        from unittest.mock import patch
        summarize_pairs = search.summarize_pairs

        def reject_final_gain(candidate, seed):
            comparison = summarize_pairs(candidate, seed)
            if len(candidate) == 1:
                comparison["status"] = "not_proven_better"
            return comparison

        with tempfile.TemporaryDirectory(prefix="sim2gse-no-gain-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary(), \
                    patch.object(search, "DEFAULT_SCENARIOS", ("nominal",)), \
                    patch.dict(search.DEFAULT_CONFIG, final_batches=1, final_iterations=2), \
                    patch.object(search, "summarize_pairs", side_effect=reject_final_gain):
                result = run_task(source, destination, search_config={
                    "total_budget_seconds": 20,
                    "search_budget_seconds": 8,
                    "candidate_limit": 4,
                    "batch_targets": (2,),
                    "validation_batches": 2,
                    "final_batches": 1,
                    "iterations": 2,
                    "final_iterations": 2,
                    "scenarios": ("nominal",),
                    "max_processes": 1,
                })

            seed_key = result["search"]["records"][0]["key"]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["improvement"], "not_proven_better")
            self.assertNotEqual(result["locked_candidate_key"], seed_key)
            self.assertEqual(result["selected_candidate_key"], seed_key)
            self.assertEqual((destination / "candidate.txt").read_text(encoding="ascii"), result["candidate"]["text"])

    def test_search_batch_targets_add_independent_requested_iterations(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-batches-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            with _fast_search_boundary():
                result = run_task(
                    source,
                    destination,
                    mode="optimize",
                    search_config={
                        "total_budget_seconds": 10,
                        "search_budget_seconds": 4,
                        "candidate_limit": 2,
                        "round_candidate_limit": 1,
                        "batch_targets": (2, 4, 8),
                        "validation_batches": 1,
                        "final_batches": 1,
                        "iterations": 2,
                        "final_iterations": 2,
                        "scenarios": ("nominal",),
                        "max_processes": 1,
                    },
                )
            batches = result["search"]["records"][0]["batches"]
            self.assertEqual([row["target"] for row in batches], [2, 4, 8])
            self.assertEqual([row["requested_iterations"] for row in batches], [2, 2, 4])
            self.assertEqual([row["samples"] for row in batches], [1, 1, 3])

    def test_public_task_can_be_cancelled_and_read_after_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-cancel-") as directory:
            source = Path(directory) / "角色.simc"
            destination = Path(directory) / "任务"
            source.write_text(sample_profile(), encoding="utf-8")
            handle = start_task(
                source,
                destination,
                search_config={
                    "total_budget_seconds": 30,
                    "search_budget_seconds": 20,
                    "candidate_limit": 1000,
                    "final_batches": 20,
                    "scenarios": ("nominal",),
                    "max_processes": 1,
                },
            )
            time.sleep(0.2)
            cancel_task(handle)
            handle.join(5)
            self.assertTrue(handle.done)
            state = read_task(destination)
            self.assertEqual(state["status"], "cancelled")

    def test_locked_candidate_resumes_without_resetting_budget_or_batches(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-resume-") as directory:
            source = Path(directory) / "role.simc"
            destination = Path(directory) / "task"
            source.write_text(sample_profile(), encoding="utf-8")
            config = dict(total_budget_seconds=40, search_budget_seconds=4,
                          candidate_limit=2, batch_targets=(2,), validation_batches=2,
                          final_batches=3, final_iterations=2, iterations=2, max_processes=2)
            with _fast_search_boundary():
                handle = start_task(source, destination, search_config=config)
                deadline = time.monotonic() + 20
                observed = {}
                while time.monotonic() < deadline and not handle.done:
                    try:
                        observed = read_task(destination)
                    except TaskError:
                        pass
                    if observed.get("phase") == "final" and observed.get("completed_batches", 0) > 0:
                        break
                    time.sleep(0.05)
                self.assertEqual(observed.get("phase"), "final")
                cancelled = cancel_task(handle)
                handle.join(5)
                self.assertTrue(handle.done)
                self.assertEqual(cancelled["status"], "cancelled")
                resumed = run_task(destination/"input.simc",destination,resume=True)
            self.assertEqual(resumed["locked_candidate_key"], cancelled["locked_candidate_key"])
            self.assertGreater(resumed["elapsed_seconds"], cancelled["elapsed_seconds"])
            self.assertGreaterEqual(resumed["completed_batches"], cancelled["completed_batches"])
            self.assertFalse(resumed["independent_validation_complete"])
            self.assertEqual(set(resumed["final"]["scenarios"]), {"nominal", "jitter", "slow", "pause", "phase"})

    def test_corrupt_success_report_is_recomputed_and_changed_config_rejected(self):
        with tempfile.TemporaryDirectory(prefix="sim2gse-cache-") as directory:
            source = Path(directory)/'role.simc'
            destination = Path(directory)/'task'
            source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=25,search_budget_seconds=3,candidate_limit=2,
                        batch_targets=(2,),validation_batches=2,final_batches=2,
                        iterations=2,final_iterations=2,scenarios=('nominal',),max_processes=1)
            with _fast_search_boundary():
                first=run_task(source,destination,search_config=config)
                row=first['final']['scenarios']['nominal']['candidate'][0]
                report=destination/row['artifact']/'native.json'
                data=json.loads(report.read_text(encoding='utf-8'))
                data['sim']['players'][0]['collected_data']['dps']['mean']=1
                report.write_text(json.dumps(data),encoding='utf-8')
                resumed=resume_task(destination)
                self.assertGreater(resumed['final']['scenarios']['nominal']['candidate'][0]['dps'],1)
                self.assertFalse(resumed['final']['scenarios']['nominal']['candidate'][0].get('cached',False))
                with self.assertRaises(TaskError):
                    resume_task(destination,search_config=dict(config,max_processes=2))
                self.assertFalse(resumed['independent_validation_complete'])

    def test_task_hard_exit_preserves_checkpoint_and_cleans_owned_engine(self):
        import ctypes
        from ctypes import wintypes
        import subprocess
        import json
        class Entry(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                      ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                      ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                      ('exe',wintypes.WCHAR*260)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        def children(pid):
            snapshot=kernel.CreateToolhelp32Snapshot(2,0)
            row=Entry();row.size=ctypes.sizeof(row)
            found=[]
            try:
                more=kernel.Process32FirstW(snapshot,ctypes.byref(row))
                while more:
                    if row.parent==pid:
                        found.append(row.pid)
                    more=kernel.Process32NextW(snapshot,ctypes.byref(row))
                return found
            finally:
                kernel.CloseHandle(snapshot)
        with tempfile.TemporaryDirectory(prefix='sim2gse-crash-') as directory:
            source=Path(directory)/'role.simc';destination=Path(directory)/'task'
            source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=45,search_budget_seconds=8,candidate_limit=4,
                        batch_targets=(32,),validation_batches=2,final_batches=2,iterations=32,
                        final_iterations=32,max_processes=2)
            code="import sys,json;sys.path.insert(0,sys.argv[1]);from task import run_task;run_task(sys.argv[2],sys.argv[3],search_config=json.loads(sys.argv[4]))"
            process=subprocess.Popen([sys.executable,'-c',code,str(REPOSITORY/'projects/sim2gse'),str(source),str(destination),json.dumps(config)])
            held=None
            try:
                deadline=time.monotonic()+20
                state={}
                while time.monotonic()<deadline and process.poll() is None:
                    try: state=read_task(destination)
                    except TaskError: pass
                    if state.get('phase')=='final':
                        for pid in children(process.pid):
                            held=kernel.OpenProcess(0x100000,False,pid)
                            if held: break
                    if held: break
                    time.sleep(0.02)
                self.assertIsNotNone(held,'没有观察到真实引擎进程')
                process.kill();process.wait(timeout=5)
                self.assertEqual(kernel.WaitForSingleObject(held,2000),0,'任务退出后仍有所属模拟进程')
                before=state['elapsed_seconds']
                resumed=resume_task(destination)
                self.assertGreaterEqual(resumed['elapsed_seconds'],before)
                self.assertEqual(resumed['locked_candidate_key'],state['locked_candidate_key'])
            finally:
                if held:kernel.CloseHandle(held)
                if process.poll() is None:process.kill();process.wait(timeout=5)

    def test_budget_cannot_exceed_contract_even_when_cancelled(self):
        import threading
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            cancelled=threading.Event();cancelled.set()
            for value in (601,float('nan'),-1):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    run_task(source,Path(directory)/str(value),search_config={'total_budget_seconds':value},cancel_event=cancelled)

    def test_owned_process_tree_hard_exit_does_not_stop_other_owner(self):
        # 补充进程系统边界检查；产品恢复仍由上方 run_task 测试覆盖。
        import ctypes
        from ctypes import wintypes
        import subprocess,json
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        with tempfile.TemporaryDirectory(prefix='sim2gse-ownership-') as directory:
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

    def test_same_conditions_reuse_search_but_never_old_final_samples(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-cache-reuse-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=25,search_budget_seconds=3,candidate_limit=2,batch_targets=(2,),
                        validation_batches=2,final_batches=2,iterations=2,final_iterations=2,
                        scenarios=('nominal',),max_processes=1)
            with _fast_search_boundary():
                first=run_task(source,Path(directory)/'first',search_config=config)
                source.write_text(sample_profile()+'\n# display note\n',encoding='utf-8')
                second=run_task(source,Path(directory)/'second',search_config=config)
            self.assertTrue(second['search']['records'][0]['batches'][0].get('cached'))
            one=first['final']['scenarios']['nominal']['candidate'][0]
            two=second['final']['scenarios']['nominal']['candidate'][0]
            self.assertNotEqual(one['request']['seed'],two['request']['seed'])
            self.assertFalse(two.get('cached',False))

    def test_native_global_failure_stops_task(self):
        import ctypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        def process_boundary(*args):
            if 'batches' in str(args[7]):
                args=list(args)
                args[0]=str(Path(sys.executable).resolve())
                args[1]=ctypes.create_unicode_buffer('"'+args[0]+'" -c "import sys;sys.exit(9)"')
            return original(*args)
        with tempfile.TemporaryDirectory(prefix='sim2gse-engine-error-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            with patch.object(runtime._kernel32,'CreateProcessW',side_effect=process_boundary):
                with self.assertRaisesRegex(TaskError,'原生引擎失败'):
                    run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=8,search_budget_seconds=3,candidate_limit=2))

    def test_multiple_local_chains_use_their_own_observed_feedback(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-local-search-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            with _fast_search_boundary():
                result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=60,
                    search_budget_seconds=50,candidate_limit=19,round_candidate_limit=4,batch_targets=(2,),
                    validation_batches=2,iterations=2,final_batches=2,final_iterations=2,scenarios=('nominal',)))
            self.assertEqual(result['search']['candidate_count'],19)
            self.assertTrue(result['search']['partial_round'])
            chains=result['search']['chains']
            self.assertGreaterEqual(sum(chain['rounds']>0 for chain in chains),2)
            for chain in chains:
                if chain['rounds']:
                    self.assertTrue(chain['feedback']['attempts'])
                    self.assertIn(chain['feedback_source'],chain['visited'])
            self.assertIn(result['search']['stop_reason'],{'candidate_limit','no_improvement','search_deadline','space_stalled'})

    def test_malformed_shared_cache_record_is_ignored(self):
        import sqlite3
        with tempfile.TemporaryDirectory(prefix='sim2gse-malformed-cache-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            config=dict(total_budget_seconds=15,search_budget_seconds=3,candidate_limit=2,batch_targets=(2,),
                        validation_batches=2,final_batches=2,iterations=2,final_iterations=2,scenarios=('nominal',))
            with _fast_search_boundary():
                run_task(source,Path(directory)/'first',search_config=config)
                with sqlite3.connect(Path(directory)/'cache.sqlite3') as database:
                    database.execute("UPDATE reusable SET value='broken-json'")
                database.close()
                result=run_task(source,Path(directory)/'second',search_config=config)
            self.assertTrue(result['candidate']['text'].startswith('!GSE3!'))
            self.assertFalse(result['search']['records'][0]['batches'][0].get('cached',False))

    def test_busy_and_dispatch_failure_are_counted_as_attempts(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-feedback-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            with _fast_search_boundary():
                result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=12,
                    search_budget_seconds=3,candidate_limit=2,batch_targets=(2,),iterations=2,
                    validation_batches=2,final_batches=1,final_iterations=2,scenarios=('nominal',)))
            feedback=result['search']['records'][0]['batches'][0]['feedback']
            self.assertEqual(feedback['attempts'].get('feedback_probe'),2)

    def test_running_task_cannot_be_resumed_by_another_runner(self):
        with tempfile.TemporaryDirectory(prefix='sim2gse-runner-lock-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            destination=Path(directory)/'task'
            handle=start_task(source,destination,search_config=dict(total_budget_seconds=30,search_budget_seconds=4,
                candidate_limit=2,batch_targets=(2,),iterations=2,validation_batches=2,final_batches=10,final_iterations=2))
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    try:
                        if read_task(destination).get('phase')=='final':break
                    except TaskError:pass
                    time.sleep(0.02)
                with self.assertRaisesRegex(TaskError,'正在运行'):
                    resume_task(destination)
            finally:
                cancel_task(handle);handle.join(5)

    def test_crash_allowance_exhaustion_is_published_once(self):
        import sqlite3,json
        with tempfile.TemporaryDirectory(prefix='sim2gse-exhaustion-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            destination=Path(directory)/'task'
            with _fast_search_boundary():
                run_task(source,destination,search_config=dict(total_budget_seconds=10,search_budget_seconds=3,
                    candidate_limit=2,batch_targets=(2,),iterations=2,validation_batches=2,final_batches=1,
                    final_iterations=2,scenarios=('nominal',)))
            database=sqlite3.connect(destination/'task.sqlite3')
            try:
                state=json.loads(database.execute('SELECT value FROM state').fetchone()[0])
                state.update(status='running',phase='final',elapsed_seconds=9,inflight={'batch':dict(start=9,allowance=1)})
                database.execute('UPDATE state SET value=?',(json.dumps(state),));database.commit()
            finally:database.close()
            (destination/'progress.json').write_text(json.dumps(dict(status='running',phase='final',elapsed_seconds=9)))
            resumed=resume_task(destination)
            self.assertEqual(resumed['status'],'validation_incomplete')
            self.assertEqual(resumed['elapsed_seconds'],10)
            self.assertEqual(read_task(destination)['status'],'validation_incomplete')
            self.assertEqual(resume_task(destination)['elapsed_seconds'],10)

    def test_process_creation_failure_releases_thread_and_temporary_files(self):
        import ctypes
        from ctypes import wintypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        runtime._kernel32.GetHandleInformation.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        held=[]
        def interrupted_create(*args):
            result=original(*args)
            if result:
                info=ctypes.cast(args[9],ctypes.POINTER(runtime._PROCESS_INFORMATION)).contents
                held.append(info.hThread)
                raise OSError('injected after process creation')
            return result
        with tempfile.TemporaryDirectory(prefix='sim2gse-create-failure-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            destination=Path(directory)/'task'
            with patch.object(runtime._kernel32,'CreateProcessW',side_effect=interrupted_create):
                with self.assertRaises(TaskError):run_task(source,destination)
            flags=wintypes.DWORD()
            leaked=[]
            for handle in held:
                if runtime._kernel32.GetHandleInformation(handle,ctypes.byref(flags)):
                    leaked.append(handle);runtime._kernel32.CloseHandle(handle)
            self.assertFalse(leaked,'创建中断泄漏线程句柄')
            self.assertFalse(list(destination.rglob('.stdout-*.tmp'))+list(destination.rglob('.stderr-*.tmp')))

    def test_search_deadline_terminates_a_hung_native_batch(self):
        import ctypes
        from ctypes import wintypes
        from unittest.mock import patch
        import runtime
        original=runtime._kernel32.CreateProcessW
        runtime._kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        runtime._kernel32.OpenProcess.restype=wintypes.HANDLE
        held=[]
        def hanging_engine(*args):
            batch='batches' in str(args[7])
            if batch:
                args=list(args)
                args[0]=str(Path(sys.executable).resolve())
                args[1]=ctypes.create_unicode_buffer('"'+args[0]+'" -c "import time;time.sleep(10)"')
            success=original(*args)
            if success and batch:
                info=ctypes.cast(args[9],ctypes.POINTER(runtime._PROCESS_INFORMATION)).contents
                held.append(runtime._kernel32.OpenProcess(0x100000,False,info.dwProcessId))
            return success
        with tempfile.TemporaryDirectory(prefix='sim2gse-deadline-') as directory:
            source=Path(directory)/'role.simc';source.write_text(sample_profile(),encoding='utf-8')
            started=time.monotonic()
            try:
                with patch.object(runtime._kernel32,'CreateProcessW',side_effect=hanging_engine):
                    result=run_task(source,Path(directory)/'task',search_config=dict(total_budget_seconds=5,search_budget_seconds=3,
                        candidate_limit=2,batch_targets=(2,),iterations=2,validation_batches=2))
                self.assertTrue(held,'未触发原生批次超时路径')
                self.assertEqual(result['status'],'validation_incomplete')
                self.assertLess(time.monotonic()-started,5)
                for handle in held:self.assertEqual(runtime._kernel32.WaitForSingleObject(handle,0),0)
            finally:
                for handle in held:runtime._kernel32.CloseHandle(handle)


if __name__ == "__main__":
    import unittest

    unittest.main()
