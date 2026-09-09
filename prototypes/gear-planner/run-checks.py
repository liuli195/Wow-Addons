"""Run current prototype checks; browser storage is disposable. Start the local app first."""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

root=Path(__file__).resolve().parent
# Do not start/stop or replace an existing user service.
with urllib.request.urlopen('http://127.0.0.1:8765/api/bootstrap',timeout=10) as response:
    assert json.load(response).get('version'), 'Start the local app before running checks'
env=os.environ.copy()
if not env.get('NODE_PATH'):
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
    if bundled.is_dir():env['NODE_PATH']=str(bundled)
results=[]
for script in sorted(root.glob('check*')):
    if script.suffix not in ('.py','.js','.cjs'):continue
    start=time.monotonic()
    try:
        run=subprocess.run([sys.executable if script.suffix=='.py' else 'node',str(script)],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=240)
        entry={'file':script.name,'code':run.returncode,'seconds':round(time.monotonic()-start,2),'output':run.stdout,'error':run.stderr}
    except subprocess.TimeoutExpired:
        entry={'file':script.name,'code':'timeout','seconds':240,'output':'','error':'Timeout; not passed'}
    results.append(entry)
    print(script.name, 'PASS' if entry['code']==0 else 'FAIL',flush=True)
    (root/'coverage-repair-run.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
failed=[x for x in results if x['code']!=0]
print(f'{len(results)-len(failed)}/{len(results)} passed')
for entry in failed:print(entry['file'],entry['error'][-2000:])
sys.exit(bool(failed))
