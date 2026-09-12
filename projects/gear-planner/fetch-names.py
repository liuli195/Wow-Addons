"""Fetch public Simplified Chinese names only; no character data leaves this machine."""
import concurrent.futures
from datetime import datetime,timezone
import json,re,time,urllib.request
from pathlib import Path
import server
DEST=Path(__file__).with_name('names-zhCN.json')
cache=json.loads(DEST.read_text(encoding='utf-8')) if DEST.exists() else {'locale':'zhCN','items':{}}
ids=sorted({g['id'] for g in server.GEMS}|{x['id'] for rows in server.CATALOG.values() for x in rows}|{int(server.gear_fields(v)['id']) for v in server.BASE['gear'].values()})
def fetch(iid):
 url=f'https://nether.wowhead.com/tooltip/item/{iid}?dataEnv=1&locale=4'
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
   with urllib.request.urlopen(req,timeout=20) as response:data=json.load(response)
   name=data.get('name','').strip()
   if not name or (not re.search('[\u4e00-\u9fff]',name) and not (iid==268477 and name=='P.O.W. x3' and '物品等级' in data.get('tooltip',''))):raise ValueError('No Simplified Chinese name')
   return str(iid),{'name':name,'source':url,'checkedAt':datetime.now(timezone.utc).isoformat()}
  except Exception as exc:
   if attempt==2:return str(iid),{'error':str(exc)}
   time.sleep(attempt+1)
def save():
 tmp=DEST.with_suffix('.tmp');tmp.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(DEST)
pending=[iid for iid in ids if not cache['items'].get(str(iid),{}).get('name')]
# ponytail: four concurrent public lookups; persistent cache avoids repeat downloads.
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for n,(iid,record) in enumerate(pool.map(fetch,pending),1):
  cache['items'][iid]=record
  if n%40==0:save();print(f'Fetched {n}/{len(pending)}',flush=True)
cache['missing']=[i for i in ids if not cache['items'].get(str(i),{}).get('name')];save()
print(json.dumps({'requested':len(ids),'named':len(ids)-len(cache['missing']),'missing':cache['missing']},ensure_ascii=False),flush=True)
