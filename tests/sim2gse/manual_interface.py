"""真实角色经三步浏览器界面完成默认预算计算、复制和旧结果清理。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'projects/sim2gse'))
from interface import create_server
from task import cancel_task


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    output=(args.output or ROOT/'.local/tests'/('界面验收 中文 空格 '+uuid.uuid4().hex[:10])).resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=ROOT/'.local/sim2gse/target-evidence/task-05/unholy-20260912-0240.simc'
    profile=source.read_text(encoding='utf-8')
    server=create_server(output)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    print(url,flush=True)
    env=os.environ.copy()
    env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
    script=r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const input=JSON.parse(fs.readFileSync(0,'utf8')),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write'],viewport:{width:1100,height:1050}});
  const page=await context.newPage();let last,taskId;const events=[];
  page.on('response',async r=>{if(r.url().includes('/api/tasks')){const s=await r.json();if(s.task_id)taskId=s.task_id;
   if(s.phase){last=s;events.push({phase:s.phase,status:s.status,elapsed_seconds:s.elapsed_seconds,completed_batches:s.completed_batches});}}});
  await page.goto(input.url);assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.screenshot({path:path.join(input.output,'initial.png'),fullPage:true});
  await page.locator('#profile').fill(input.profile);await page.locator('#start').click();
  await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:620000});
  assert.equal(await page.locator('#error').isVisible(),false,await page.locator('#error').textContent());
  assert.equal(await page.locator('#resultSection').isVisible(),true);
  const text=await page.locator('#result').inputValue();assert.match(text,/^!GSE3!/);assert.equal(text,last.candidate_text);
  await page.locator('#copy').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),text);
  if(last.evidence_status!=='complete')assert.match(await page.locator('#resultNote').innerText(),/复测未完成/);
  await page.screenshot({path:path.join(input.output,'result.png'),fullPage:true});
  await page.locator('#profile').fill(input.profile+'\n# changed');
  assert.equal(await page.locator('#resultSection').isVisible(),false);assert.equal(await page.locator('#result').inputValue(),'');
  fs.writeFileSync(path.join(input.output,'browser.json'),JSON.stringify({task_id:taskId,state:last,events,clipboard_matches:true,input_change_clears:true},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    started=time.monotonic()
    try:
        process=subprocess.Popen(['node','-e',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            stdout,stderr=process.communicate(json.dumps(dict(url=url,profile=profile,output=str(output))),timeout=640)
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            process.wait()
        (output/'browser.log').write_text(stdout+stderr,encoding='utf-8')
        assert process.returncode==0,stdout+stderr
        browser=json.loads((output/'browser.json').read_text(encoding='utf-8'))
        task=output/'tasks'/browser['task_id']
        result=json.loads((task/'result.json').read_text(encoding='utf-8'))
        text=(task/'candidate.txt').read_text(encoding='ascii')
        assert text==browser['state']['candidate_text']==result['candidate']['text']
        assert (task/'input.original.simc').read_bytes()==profile.encode('utf-8')
        assert result['candidate']['simulation']=='passed_native_model'
        assert result['candidate']['game_validation']=='not_run'
        evidence=dict(status=result['status'],elapsed_seconds=result['elapsed_seconds'],wall_seconds=time.monotonic()-started,
            completed_batches=result['completed_batches'],independently_tested=result['independent_validation_complete'],
            clipboard_matches=True,input_change_clears=True,candidate_sha256=hashlib.sha256(text.encode()).hexdigest(),game_validation='not_run')
        (output/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
    finally:
        for _,handle in list(server.tasks.values()):
            if not handle.done:cancel_task(handle);handle.join(5)
        server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__':main()
