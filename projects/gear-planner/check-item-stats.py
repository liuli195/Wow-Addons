import server
r=server.calculate(server.BASE);assert r['complete']
base=r['items']['head']['raw']
assert base['strint']==152 and base['stamina']==3002 and base['crit_rating']==118
m=server.apply_edit(server.BASE,{'slot':'head','enchant_id':''})
r=server.calculate(m);assert r['items']['head']['raw']['speed_rating']==base['speed_rating']
m=server.apply_edit(server.BASE,{'slot':'head','level':318})
r=server.calculate(m);assert r['items']['head']['raw']['stamina']>base['stamina']
m=server.apply_edit(server.BASE,{'slot':'main_hand','crafted':'32/36'})
r=server.calculate(m);assert r['items']['main_hand']['raw']['haste_rating']==99 and not r['items']['main_hand']['raw'].get('mastery_rating')
print('PASS: item base stats, enchant exclusion, ilvl scaling and crafted stat changes')
