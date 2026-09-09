import json,re
from pathlib import Path
import server
cache=json.loads(Path(__file__).with_name('names-zhCN.json').read_text(encoding='utf-8'))
records=[x for rows in server.CATALOG.values() for x in rows]
ids={x['id'] for x in records}
assert len(ids)==523
assert not cache['missing'],cache['missing']
for x in records:
 assert re.search('[\u4e00-\u9fff]',x['name']) or (x['id']==268477 and x['name']=='P.O.W. x3'),x['id']
 assert not x['missingName'],x['id']
 assert x['english']==server.ITEMS[x['id']]['name'],x['id']
neck=next(x for x in records if x['id']==273781)
assert neck['name']=='护卫之牙束带'
assert neck['english']=='Strand of Warding Fangs'
print('PASS: all 523 catalog names localized (one verified Latin name); English and IDs retained; 273781 verified')
