"""真实角色经浏览器自然搜索、完整复测、复制和旧结果清理。"""
import argparse
import hashlib
import json
from pathlib import Path
from contextlib import ExitStack
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'projects/sim2gse'))
from interface import create_server
from runtime import TaskRuntime, run_command
from dual_task import cancel as cancel_task, read as read_task


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--profile',type=Path,help='固定角色文件；不修改原文件')
    parser.add_argument('--data-project',type=Path,help='明确使用已有数据中心所在项目')
    parser.add_argument('--smoke',action='store_true',help='内建起点取首个并冻结繁殖随机门；保外部起点和正常3×128复测，不是默认DPS对照')
    args=parser.parse_args()
    output=(args.output or ROOT/'.local/tests'/('界面验收 中文 空格 '+uuid.uuid4().hex[:10])).resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=args.profile or ROOT/'.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
    original=source.read_bytes()
    if args.data_project:
        import result_store
        result_store.bind_project(args.data_project)
    profile=source.read_text(encoding='utf-8')
    server=create_server(output)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    print(url,flush=True)
    script=r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const input=JSON.parse(fs.readFileSync(process.argv[1],'utf8')),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write'],viewport:{width:1100,height:1050}});
  const page=await context.newPage();let last,taskId;const events=[];
  page.on('response',async r=>{if(r.url().includes('/api/tasks')){const s=await r.json();if(s.task_id)taskId=s.task_id;
   if(s.phase){last=s;events.push({phase:s.phase,status:s.status,elapsed_seconds:s.elapsed_seconds,completed_batches:s.completed_batches});}}});
  await page.goto(input.url);assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.screenshot({path:path.join(input.output,'initial.png'),fullPage:true});
  await page.locator('#profile').fill(input.profile);await page.locator('#start').click();
  await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:1240000});
  assert.equal(await page.locator('#error').isVisible(),false,await page.locator('#error').textContent());
  assert.equal(await page.locator('#resultSection').isVisible(),true);
  const text=await page.locator('#result').inputValue();assert.match(text,/^!GSE3!/);assert.equal(text,last.exports.single_target);
  await page.locator('#copy').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),text);
  assert.equal(last.status,'completed');
  assert.equal(last.stop_policy.kind,'natural_stagnation');
  assert.match(await page.locator('#resultNote').innerText(),/两个循环均已完成正常场景独立复测/);
  assert.equal(Object.keys(last.exports).length,3);assert.ok(last.collection_ready);
  await page.locator('#copyCollection').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),last.collection_text);
  await page.screenshot({path:path.join(input.output,'result.png'),fullPage:true});
  await page.locator('#profile').fill(input.profile+'\n# changed');
  assert.equal(await page.locator('#resultSection').isVisible(),false);assert.equal(await page.locator('#result').inputValue(),'');
  fs.writeFileSync(path.join(input.output,'browser.json'),JSON.stringify({task_id:taskId,state:last,events,clipboard_matches:true,input_change_clears:true},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    started=time.monotonic()
    smoke_boundary=ExitStack()
    try:
        if args.smoke:
            import random
            from types import SimpleNamespace
            from unittest.mock import patch
            import population_training
            import search
            original_random=random.Random
            class NoVariationRandom(original_random):
                _randbelow=original_random._randbelow
                def random(self):
                    return .999999
            native_starts=search.initial_programs
            smoke_boundary.enter_context(patch.object(population_training,'random',SimpleNamespace(Random=NoVariationRandom)))
            smoke_boundary.enter_context(patch.object(search,'initial_programs',lambda *a,**k:native_starts(*a,**k)[:1]))
        payload=output/'browser-input.json'
        payload.write_text(json.dumps(dict(url=url,profile=profile,output=str(output))),encoding='utf-8')
        try:
            process=run_command([str(ROOT/'.local/verify-deps/node/node.exe'),'-e',script,str(payload)],ROOT,timeout_seconds=1260,
                                runtime=TaskRuntime(1260),output_dir=output)
        finally:
            payload.unlink(missing_ok=True)
        stdout,stderr=(process.stdout+process.stderr).decode('utf-8',errors='replace'),''
        (output/'browser.log').write_text(stdout+stderr,encoding='utf-8')
        assert process.returncode==0,stdout+stderr
        browser=json.loads((output/'browser.json').read_text(encoding='utf-8'))
        task=output/'tasks'/browser['task_id']
        result=read_task(task)
        from formal_search import STOP_POLICY
        assert result['status']=='completed' and result['stop_policy']==STOP_POLICY
        text=result['exports']['single_target']
        assert text==browser['state']['exports']['single_target']
        assert (task/'input.original.simc').read_bytes()==profile.encode('utf-8')
        assert len(result['exports'])==3 and result['collection_ready']
        assert source.read_bytes()==original
        from task import read_task as read_single
        from search import TaskStore
        from burst import check_loop
        import result_store
        from gse_import import decode_import
        members=decode_import(result['collection_text'])['sequences']
        assert len(members)==3
        source_counts=[]
        independent_results=[]
        for purpose, targets in [('single_target',1),('aoe',5)]:
            child=read_single(task/purpose,include_reports=False)
            assert child['stop_policy']==STOP_POLICY and child['independent_validation_complete'] is True
            assert child['final']['status']=='completed' and set(child['final']['scenarios'])=={'nominal'}
            finalists=child['final']['scenarios']['nominal']['finalists']
            assert finalists and all(len(row['batches'])==3 and row['samples']==381 and
                all(batch['requested_iterations']==128 for batch in row['batches']) for row in finalists)
            if args.smoke:
                assert child['search']['complete_generations']>=2 and not child['search']['partial_round']
            independent_results.append(child['independent_validation_complete'])
            assert child['simulation_config']['target_count']==targets
            assert child['burst']['definition_id']==result['definition_id']
            store=TaskStore(task/purpose)
            try:
                check_loop(child['candidate']['program'],store.state['capabilities'])
                assert store.state['burst']['candidate']['compiled_steps']
                batch=json.loads(store.db.execute(
                    "SELECT value FROM batches WHERE json_extract(value,'$.status')='success' LIMIT 1").fetchone()[0])
                request=batch['request']
                assert request['burst']['definition_id']==result['definition_id']
                assert set(request['burst']['sources'])=={'loop','burst'}
                assert len(request['burst']['sources'])==len(request['times'])
                native=result_store.one('batches','batch_key',batch['data_key'],group_key=batch['storage_group_key'])
                report=native['report']
                report=json.loads(report) if isinstance(report,str) else report
                assert len(report['sim']['players'])==1
            finally:
                store.close()
            source_counts.append(dict(purpose=purpose,target_count=targets,
                                      candidates=child['search']['candidate_count'],
                                      effective_population=child['search']['effective_population_size'],
                                      nominal_samples=child['search_result']['samples'],
                                      loop_exclusion_checked=True,same_actor_burst_checked=True))
        import dual_task
        parent=dual_task._load(task)
        for purpose in ('single_target','aoe','burst'):
            records=result_store.read_records('sequence_exports',parent[purpose+'_export'])
            assert records[0]['text']==result['exports'][purpose]
            assert records[0]['simulation']=='passed_native_model'
            assert records[0]['game_validation']=='not_run'

        evidence=dict(status=result['status'],elapsed_seconds=result['elapsed_seconds'],wall_seconds=time.monotonic()-started,
            scenes=result['scenes'],preparation_seconds=result['preparation_seconds'],packaging_seconds=result['packaging_seconds'],
            smoke=args.smoke,smoke_scope=(dict(builtin_starts=1,external_starts='preserved',variation='frozen_gate',
                nominal='3x128',default_comparison=False) if args.smoke else None),
            observation_timeout_seconds=1260,stop_policy=result['stop_policy'],
            source_counts=source_counts,input_unchanged=True,three_members=True,
            saved_results_reread=True,independently_tested=all(independent_results),
            clipboard_matches=True,input_change_clears=True,candidate_sha256=hashlib.sha256(text.encode()).hexdigest(),game_validation='not_run')
        (output/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
    finally:
        try:
            for _,handle in list(server.tasks.values()):
                if not handle.done:cancel_task(handle)
                handle.join()
            server.shutdown();server.server_close();thread.join(2)
        finally:
            smoke_boundary.close()


if __name__=='__main__':main()
