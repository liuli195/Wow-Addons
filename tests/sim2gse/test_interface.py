"""任务四：三步界面通过本地服务接入真实任务入口。"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import json
import os
import subprocess
from contextlib import nullcontext
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))

from interface import _friendly_error, _public_state, create_server  # noqa: E402
from task import run_task  # noqa: E402
from test_character_export import sample_profile  # noqa: E402
from test_search import _fast_search_boundary  # noqa: E402


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="sim2gse-ui-")
        self.server = create_server(Path(self.directory.name) / "输出", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self) -> None:
        from task import cancel_task
        for _,handle in list(self.server.tasks.values()):
            if not handle.done:
                cancel_task(handle)
                handle.join(5)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def test_homepage_is_the_real_three_step_shell(self) -> None:
        with urlopen(self.url, timeout=2) as response:
            page = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn('id="profile"', page)
        self.assertIn('id="progressText"', page)
        self.assertIn('id="resultSection"', page)
        self.assertIn('id="copy"', page)
        self.assertIn('hidden', page.split('id="resultSection"', 1)[1].split(">", 1)[0])
        self.assertNotIn("演示进度", page)
        self.assertNotIn("原型尚未连接", page)

    def _json_request(self, method: str, path: str, value: dict | None = None) -> dict:
        body = None if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
        request = Request(self.url + path, data=body, method=method,
                          headers={"Content-Type": "application/json"} if body else {})
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_empty_submission_is_rejected_without_creating_a_task(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {"profile": "  "})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("粘贴", json.loads(raised.exception.read())['error'])
        self.assertEqual(list((Path(self.directory.name) / "输出" / "tasks").iterdir()), [])

    def test_real_task_reaches_candidate_through_the_same_public_service(self) -> None:
        self.server.task_options = {
            "search_config": {
                "total_budget_seconds": 20,
                "search_budget_seconds": 8,
                "candidate_limit": 2,
                "round_candidate_limit": 1,
                "batch_targets": (2,),
                "validation_batches": 1,
                "final_batches": 1,
                "iterations": 2,
                "final_iterations": 2,
                "scenarios": ("nominal",),
                "max_processes": 1,
            }
        }
        with _fast_search_boundary():
            created = self._json_request("POST", "/api/tasks", {"profile": sample_profile()})
            self.assertEqual(created["status"], "starting")
            task_id = created["task_id"]
            deadline = time.monotonic() + 30
            state = {}
            while time.monotonic() < deadline:
                state = self._json_request("GET", f"/api/tasks/{task_id}")
                if state["status"] in {"completed", "validation_incomplete", "failed", "cancelled"}:
                    break
                time.sleep(0.1)
        self.assertEqual(state["status"], "validation_incomplete")
        self.assertTrue(state["result_ready"])
        self.assertEqual(state["evidence_status"], "insufficient_validation")
        self.assertTrue(state["candidate_text"].startswith("!GSE3!"))
        self.assertIn("复测未完成", state["result_note"])
        self.assertIn("锁定候选", state["result_note"])
        self.assertEqual(state["phase"], "done")
        self.assertGreater(state["elapsed_seconds"], 0)

    def test_old_incomplete_result_still_reports_the_seed_it_selected(self) -> None:
        destination = Path(self.directory.name) / "旧任务"
        destination.mkdir()
        (destination / "candidate.txt").write_text("!GSE3!seed", encoding="ascii")
        state = {
            "status": "validation_incomplete",
            "phase": "done",
            "improvement": "not_proven_better",
            "locked_candidate_key": "locked",
            "selected_candidate_key": "seed",
            "candidate": {"text": "!GSE3!seed"},
        }

        self.assertIn("初始序列", _public_state(state, destination)["result_note"])

    def test_browser_computes_copies_and_clears_real_candidate(self, profile_text=None, expected_spec=252, interval_ms=300):
        self.server.task_options = {'search_config': dict(total_budget_seconds=20,
            search_budget_seconds=8,candidate_limit=2,batch_targets=(2,),
            validation_batches=1,final_batches=1,iterations=2,final_iterations=2,
            scenarios=('nominal','jitter','slow','pause','phase') if interval_ms != 300 else ('nominal',),max_processes=1)}
        env=os.environ.copy()
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        script=r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(); let state;
  page.on('response',async response=>{if(response.url().includes('/api/tasks/')&&response.request().method()==='GET')state=await response.json();});
  await page.goto(input.url);
  assert.equal(await page.locator('#interval').inputValue(),'300');
  await page.locator('#interval').fill(String(input.interval_ms));
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.locator('#start').click();
  assert.match(await page.locator('#error').innerText(),/请先粘贴/);
  await page.locator('#profile').fill('mage=test\nlevel=80\nspec=frost');
  await page.locator('#start').click();
  await page.waitForFunction(()=>!document.querySelector('#start').disabled);
  const asyncError=await page.locator('#error').innerText();
  assert.match(asyncError,/请检查角色导出内容/);
  assert.ok(!asyncError.includes('\\'));
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  let dropped=false;
  await page.route('**/api/tasks/*',async route=>{if(!dropped){dropped=true;await route.abort();}else await route.continue();});
  const disconnected=page.waitForEvent('requestfailed');
  await page.locator('#profile').fill(input.profile);await page.locator('#start').click();
  await disconnected;await page.waitForTimeout(700);
  assert.equal(await page.locator('#start').isDisabled(),true,'瞬时断连不能结束后台任务');
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:35000});
  assert.equal(await page.locator('#resultSection').isVisible(),true,await page.locator('#error').textContent());
  const text=await page.locator('#result').inputValue();assert.match(text,/^!GSE3!/);
  assert.equal(state.input_interval_ms,input.interval_ms);
  assert.equal(text,state.candidate_text);assert.equal(state.evidence_status,'insufficient_validation');
  assert.match(await page.locator('#resultNote').innerText(),/复测未完成/);
  await page.locator('#copy').click();
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),text);
  assert.match(await page.locator('#resultNote').innerText(),/复测未完成/);
  await page.locator('#profile').fill(input.profile+'\n# changed');
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  assert.equal(await page.locator('#result').inputValue(),'');
  console.log(JSON.stringify({candidate:text}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],input=json.dumps(dict(url=self.url,profile=profile_text or sample_profile(),interval_ms=interval_ms)),
            text=True,encoding='utf-8',capture_output=True,env=env,timeout=50)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self._decode_candidate(json.loads(result.stdout)['candidate'], expected_spec)

    def _decode_candidate(self, candidate, expected_spec):
        import base64, zlib, cbor2
        # 游戏 12.1 实际编码 {1,"test"} 的输出；不由产品编码器生成预期值。
        self.assertEqual(zlib.decompress(base64.b64decode('a2J0KUktLgEA'), -15), b'\x82\x01\x44test')
        wire = cbor2.loads(zlib.decompress(base64.b64decode(candidate[6:]), -15))
        self.assertIsInstance(wire[0], bytes)
        self.assertIn(b'MetaData', wire[1])
        def text(value):
            if isinstance(value, bytes): return value.decode('utf-8')
            if isinstance(value, list): return [text(v) for v in value]
            if isinstance(value, dict): return {text(k): text(v) for k,v in value.items()}
            return value
        payload = text(wire)
        self.assertEqual(payload[1]['MetaData']['SpecID'], expected_spec)
        self.candidate_payload = payload

    def _export_candidate(self, profile, expected_spec, *, simulate=False):
        root = Path(self.directory.name) / 'direct'
        source = root / 'input.simc'
        root.mkdir()
        source.write_text(profile, encoding='utf-8')
        from unittest.mock import patch
        boundary = nullcontext() if simulate else patch(
            'sequence.evaluate', return_value={'trace': [], 'model': 'constructed-test-boundary'})
        with boundary:
            result = run_task(source, root / 'task', mode='single')
        self._decode_candidate(result['candidate']['text'], expected_spec)
        self.native_report = json.loads((root / 'task/reference/native.json').read_text(encoding='utf-8'))
        self.native_reference = result['native_reference']
        self.controlled = result['controlled_simulation']

    def test_invalid_interval_is_rejected_before_creating_task(self):
        for value in (0, 49, 2001, True, 180.5, "180"):
            with self.subTest(value=value), self.assertRaises(HTTPError) as raised:
                self._json_request("POST", "/api/tasks", {"profile": sample_profile(), "input_interval_ms": value})
            self.assertEqual(raised.exception.code, 400)
        self.assertEqual(list(self.server.tasks), [])

    def test_browser_uses_adjustable_input_interval(self):
        with _fast_search_boundary():
            self.test_browser_computes_copies_and_clears_real_candidate(interval_ms=180)
        from task import read_task
        destination, _ = next(iter(self.server.tasks.values()))
        result = read_task(destination)
        for row in result['final']['scenarios']['nominal']['candidate']:
            self.assertEqual(row['request']['times'], list(range(0, 180000, 180)))
        scenarios = result['final']['scenarios']
        self.assertEqual(set(scenarios), {'nominal','jitter','slow','pause','phase'})
        for name in ('slow','phase','pause','jitter'):
            times = scenarios[name]['candidate'][0]['request']['times']
            if name == 'slow': self.assertEqual(times, list(range(0,180000,240)))
            elif name == 'phase': self.assertEqual(times, list(range(90,180000,180)))
            elif name == 'pause':
                self.assertTrue(all(t % 180 == 0 for t in times))
                self.assertFalse(any(60000 <= t < 62000 or 120000 <= t < 122000 for t in times))
            else: self.assertTrue(all(162 <= b-a <= 198 for a,b in zip(times,times[1:])))

    def test_game_export_with_death_pact_and_asphyxiate_reaches_result(self):
        import re
        talents='CwPAkXBWxkyfx9CbGaHonEAhLBYmhZMjBzyMzMTjZmxMzYAAAAAAAAYmxwAglZMzsZmxMzA2MbGGyAzGDNWwAmBgxMzYGgZmxMG'
        profile=re.sub(r'^talents=.*$', 'talents='+talents,sample_profile(),flags=re.MULTILINE)
        self._export_candidate(profile, 252)

    def test_baseline_unused_racial_does_not_block_browser_result(self):
        self._export_candidate(sample_profile().replace('highmountain_tauren', 'undead'), 252)

    def test_tank_profile_reaches_damage_candidate(self):
        import re
        profile = sample_profile().replace('role=attack', 'role=tank').replace('spec=unholy', 'spec=blood')
        profile = re.sub(r'^talents=.*$', 'talents=CoPAkXBWxkyfx9CbGaHonEAhLxMz2MzwMmZmhZbmZmmZxMjZmxAAAAAmhZmZmZMzYAAzMzMzAAAYgBmxiGLbgsNgNAzYAAAmZAMA', profile, flags=re.MULTILINE)
        self._export_candidate(profile, 250)
        actions = self.candidate_payload[1]['Versions'][0]['Actions']
        self.assertTrue(any(a.get('macro') == '/cast [@player] 43265' for a in actions), '地面技能必须直接在脚下释放')

    def test_caster_profile_reaches_damage_candidate(self):
        # 固定上游 MID2_Mage_Frost 的角色字段；默认动作由引擎生成。
        self._export_candidate('''mage="Frost caster"
level=90
race=tauren
role=spell
spec=frost
talents=CAEAAAAAAAAAAAAAAAAAAAAAAYGGLzMzsMmZmYmZGjZMziZmZmZMDEAAYmZmllZm2AAAAAAgNA2WGzMzAbzYmZYBAAgZ2AmBGwADD
main_hand=,id=271092,bonus_id=13662/13848,enchant_id=8689
''', 64)

    def test_native_item_group_reaches_damage_candidate(self):
        self._export_candidate('''mage="Arcane items"
level=90
race=tauren
role=spell
spec=arcane
talents=C4DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMDamZGAAAGAAEwMzMLLzMxCAAwMzMjNLzMzsMjxYmZwCzYmZGAgBAAYmZBAMDAGmZG
main_hand=,id=271092,bonus_id=13335/13848,ilevel=344,enchant_id=8689
trinket1=,id=250215,ilevel=344
''', 62)

    def test_native_empower_and_race_alias_reach_candidate(self):
        self._export_candidate('''evoker="Empower caster"
level=90
race=dracthyr
role=spell
spec=devastation
talents=CsbBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzMDMDzgBmZGjZaYmpZMWmxMzMz8AzMzAmxMGzMLzMDMwYwCsMGN2GQmBBbYGMzghB
main_hand=,id=249283,ilevel=289,enchant_id=8039
''', 1467)

    def test_healer_profile_reaches_damage_candidate(self):
        self._export_candidate('''druid="Restoration healer"
level=90
race=night_elf
role=heal
spec=restoration
talents=CkGAAAAAAAAAAAAAAAAAAAAAAMjxMbzMjZmxsNMGzwYjZAAAAAAAAAAwygmNzYamxwYWmZmZGGmBAAAAAAAAAQAAAz2MLNbzsZjxMDmZAaGAgZGAGA
main_hand=,id=271092,ilevel=311
''', 105)
        player = self.native_report['sim']['players'][0]
        self.assertEqual(player['role'], 'heal')
        self.assertGreater(player['collected_data']['dps']['mean'], 0)

    def test_explicit_native_experimental_option_reaches_candidate(self):
        self._export_candidate(
            'allow_experimental_specializations=1\n'+(REPOSITORY/'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8'), 256)

    def test_native_restoration_shaman_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/restoration-shaman.simc').read_text(encoding='utf-8'), 264)

    def test_native_augmented_party_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/augmentation.simc').read_text(encoding='utf-8'), 1473)
        self.assertGreater(len(self.native_report['sim']['players']), 1)
        self.assertEqual(self.native_reference['dps'], self.native_report['sim']['statistics']['raid_dps']['mean'])

    def test_native_cast_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/devourer.simc').read_text(encoding='utf-8'), 1480, simulate=True)
        self.assertTrue(any(row['event'] == 'native_execute' and row.get('cast_ms', 0) > 0
                            for row in self.controlled['trace']))

    def test_replacement_forms_remain_one_button(self):
        self._export_candidate('''warrior="Fury buttons"
level=90
race=dwarf
role=attack
spec=fury
talents=CgEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgGDzMmZ2MzMzMDjZmZGzMzsMzMmZmZzYmBAAixy2ALgJYGmAzwGwMDjNAAYmhxYYMYM
main_hand=,id=268213,bonus_id=13335/13848,ilevel=344,enchant_id=8689
off_hand=,id=237847,bonus_id=8793/8960/13751/13771/13836/12497,enchant_id=8689
''', 72)
        actions = self.candidate_payload[1]['Versions'][0]['Actions']
        self.assertTrue(any('/cast 335097' in a.get('macro','') and '/cast 85288' in a.get('macro','') for a in actions))
        self.assertFalse(any(a.get('spell') in (335097,85288) for a in actions))

    def test_interface_reports_native_and_export_failures_without_internal_paths(self):
        from task import TaskError
        native_cases = [
            ('native_default', (REPOSITORY / 'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8')),
            ('native_disabled', 'allow_experimental_specializations=0\n' +
             (REPOSITORY / 'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8')),
            ('native_unsupported', (REPOSITORY / 'tests/sim2gse/fixtures/holy-paladin.simc').read_text(encoding='utf-8')),
        ]
        for failure, profile in native_cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'input.simc'
                source.write_text(profile, encoding='utf-8')
                with self.assertRaisesRegex(TaskError, '原生未提供'):
                    run_task(source, Path(directory) / 'task', mode='single')
                if failure == 'native_default':
                    invocation = json.loads((Path(directory) / 'task/reference/invocation.json').read_text(encoding='utf-8'))
                    self.assertFalse(any(arg.startswith('allow_experimental_specializations=')
                                         for arg in invocation['command']))
        cases = [
            ('主动能力不完整，停止模拟与导出: invalid_action', '尚未支持的主动能力'),
            ('原生引擎失败: C:\\private\\simc.exe', '引擎'),
            ('固定上游编译器失败: C:\\private\\lua.exe', '导出'),
            ('结果文件缺失，未生成可复制文本', '结果'),
        ]
        for failure, expected in cases:
            with self.subTest(failure=failure):
                message = _friendly_error(TaskError(failure))
                self.assertIn(expected, message)
                self.assertNotIn('\\', message)
                self.assertLess(len(message), 161)
        self.assertFalse(_public_state({'status': 'completed'}, Path(self.directory.name))['result_ready'])

    def test_manual_browser_timeout_cleans_process_tree(self):
        from unittest.mock import patch
        import ctypes
        from ctypes import wintypes
        import manual_interface
        original_communicate=subprocess.Popen.communicate
        original_read=Path.read_text
        held=[]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        class Entry(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                      ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                      ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                      ('exe',wintypes.WCHAR*260)]
        kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        def edge_ids(parent_id):
            snapshot=kernel.CreateToolhelp32Snapshot(2,0)
            row=Entry();row.size=ctypes.sizeof(row)
            found=set()
            try:
                more=kernel.Process32FirstW(snapshot,ctypes.byref(row))
                while more:
                    if row.parent==parent_id and row.exe.lower()=='msedge.exe':found.add(row.pid)
                    more=kernel.Process32NextW(snapshot,ctypes.byref(row))
                return found
            finally:kernel.CloseHandle(snapshot)
        def deadline(process,input=None,timeout=None):
            if isinstance(process.args,list) and process.args[0]=='node':
                held.append(kernel.OpenProcess(0x100000,False,process.pid))
                process.stdin.write(input)
                process.stdin.close()
                process.stdin=None
                child_ids=[]
                until=time.monotonic()+10
                while time.monotonic()<until and not child_ids:
                    child_ids=edge_ids(process.pid)
                    if not child_ids:time.sleep(0.05)
                for pid in child_ids:
                    handle=kernel.OpenProcess(0x100000,False,int(pid))
                    self.assertTrue(handle,'无法打开 Edge 浏览器进程')
                    self.assertEqual(kernel.WaitForSingleObject(handle,0),258,'捕获的 Edge 浏览器进程已经退出')
                    held.append(handle)
                return original_communicate(process,timeout=0.1)
            return original_communicate(process,input,timeout)
        def profile_input(path,*args,**kwargs):
            if path.name=='unholy-20260912-0240.simc':return sample_profile()
            return original_read(path,*args,**kwargs)
        destination=Path(self.directory.name)/'超时 界面'
        try:
            with patch.object(sys,'argv',['manual_interface.py','--output',str(destination)]),patch.object(Path,'read_text',profile_input),patch.object(subprocess.Popen,'communicate',deadline):
                with self.assertRaises(subprocess.TimeoutExpired):manual_interface.main()
            self.assertGreaterEqual(sum(bool(handle) for handle in held),2,'必须观察到 Node 及浏览器子进程')
            for handle in held:
                if handle:self.assertEqual(kernel.WaitForSingleObject(handle,5000),0,'浏览器进程未被清理')
        finally:
            for handle in held:
                if handle:kernel.CloseHandle(handle)

    def test_browser_waits_for_result_publication_before_finishing(self):
        from unittest.mock import patch
        original = os.replace
        def delayed_result(source, destination):
            if Path(destination).name == 'result.json':
                time.sleep(1.5)  # 模拟真实报告落盘期间的多个进度轮询。
            return original(source, destination)
        with _fast_search_boundary(), patch.object(os, 'replace', side_effect=delayed_result):
            self.test_browser_computes_copies_and_clears_real_candidate()

    def test_browser_survives_transient_windows_report_sharing_conflicts(self):
        from unittest.mock import patch
        original=os.replace
        failures=set()
        conflicts=[]
        readers=[]
        def sharing_conflict(source,destination):
            name=Path(destination).name
            if name in ('progress.json','result.json') and name not in failures:
                failures.add(name)
                if not Path(destination).exists():Path(destination).write_text('{"status":"starting"}',encoding='utf-8')
                reader=open(destination,'rb')
                release=threading.Timer(0.08,reader.close);release.start();readers.append(release)
            try:return original(source,destination)
            except PermissionError as error:
                conflicts.append(error.winerror)
                raise
        with _fast_search_boundary(), patch.object(os,'replace',side_effect=sharing_conflict):
            self.test_browser_computes_copies_and_clears_real_candidate()
        self.assertEqual(failures,{'progress.json','result.json'})
        for reader in readers:reader.join()
        self.assertTrue(set(conflicts)&{5,32},'必须触发真实 Windows 文件占用冲突')


if __name__ == "__main__":
    unittest.main()
