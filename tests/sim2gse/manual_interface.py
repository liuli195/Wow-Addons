"""真实角色经三步浏览器界面完成默认预算计算、复制和旧结果清理。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
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
    parser.add_argument('--smoke',action='store_true',help='每场600秒预算，缩小候选和样本进行完整链冒烟')
    args=parser.parse_args()
    output=(args.output or ROOT/'.local/tests'/('界面验收 中文 空格 '+uuid.uuid4().hex[:10])).resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=args.profile or ROOT/'.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
    original=source.read_bytes()
    if args.data_project:
        import result_store
        result_store.bind_project(args.data_project)
    profile=source.read_text(encoding='utf-8')
    options=dict(search_config=dict(candidate_limit=5,round_candidate_limit=1,batch_targets=(2,),
        iterations=2,validation_batches=2)) if args.smoke else None
    server=create_server(output,task_options=options)
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
  assert.match(await page.locator('#resultNote').innerText(),/未进行最终独立复测/);
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
    try:
        payload=output/'browser-input.json'
        payload.write_text(json.dumps(dict(url=url,profile=profile,output=str(output))),encoding='utf-8')
        try:
            process=run_command([shutil.which('node') or 'node','-e',script,str(payload)],ROOT,timeout_seconds=1260,
                                runtime=TaskRuntime(1260),output_dir=output)
        finally:
            payload.unlink(missing_ok=True)
        stdout,stderr=(process.stdout+process.stderr).decode('utf-8',errors='replace'),''
        (output/'browser.log').write_text(stdout+stderr,encoding='utf-8')
        assert process.returncode==0,stdout+stderr
        browser=json.loads((output/'browser.json').read_text(encoding='utf-8'))
        task=output/'tasks'/browser['task_id']
        result=read_task(task)
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
        for purpose, targets in [('single_target',1),('aoe',5)]:
            child=read_single(task/purpose,include_reports=False)
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
            smoke=args.smoke,source_counts=source_counts,input_unchanged=True,three_members=True,
            saved_results_reread=True,independently_tested=False,
            clipboard_matches=True,input_change_clears=True,candidate_sha256=hashlib.sha256(text.encode()).hexdigest(),game_validation='not_run')
        (output/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
    finally:
        for _,handle in list(server.tasks.values()):
            if not handle.done:cancel_task(handle);handle.join(5)
        server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__':main()
