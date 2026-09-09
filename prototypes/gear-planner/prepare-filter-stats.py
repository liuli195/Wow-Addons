"""Refresh the Blood prototype's permanent equipment stat filter with pinned SimC."""
import copy
import json
import server
stats={}
for slot,rows in server.CATALOG.items():
    for row in rows:
        key=str(row['id'])
        if key in stats or row['reason'] or row['fitReason'] or row['conversion']:continue
        model=copy.deepcopy(server.BASE);model['gear'][slot]=row['value']
        result=server.calculate(model)
        if not result['complete']:raise ValueError((key,result.get('diagnostic')))
        raw=result['items'][slot]['raw']
        stats[key]=[k for k in ('crit','haste','mastery','versatility') if raw.get(k+'_rating',0)>0]
(server.HERE/'filter-stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared permanent equipment stats:',len(stats),server.VERSION)
