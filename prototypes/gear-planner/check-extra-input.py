import copy
import server
server.validate(server.BASE)
for value in ['9'*100000, '9'*2999+'!', '1:1/', '/1:1', '1::1', '1:1/2:', '１:1', 123, ['1:1'], 'rune:bad', 'rune\ninput=file', 'rune=1']:
    model=copy.deepcopy(server.BASE);model['character']['omnium_talents']=value
    try:server.validate(model)
    except ValueError:pass
    else:raise AssertionError(value)
for value in ['1:1','136814:1/136821:1','', '136814', 'rune_of_unleashed_fire/rune_of_selfmending', 'rune_of_lingering:1/136814:1']:
    model=copy.deepcopy(server.BASE);model['character']['omnium_talents']=value;server.validate(model)
for spec in ('blood', 'frost', 'unholy'):
    model=copy.deepcopy(server.BASE);model['character']['spec']=spec;server.validate(model)
for spec in ('holy', 'frost\ninput=file', ''):
    model=copy.deepcopy(server.BASE);model['character']['spec']=spec
    try:server.validate(model)
    except ValueError:pass
    else:raise AssertionError(spec)
print('PASS: bounded linear extra talent validation; valid lists and malformed/adversarial input')

for spec in ('havoc','vengeance','devourer'):
 model=copy.deepcopy(server.BASE);model['character'].update({'class':'demonhunter','spec':spec,'timeofday':'night'});server.validate(model)
model['character']['timeofday']='night\ninput=file'
try:server.validate(model)
except ValueError:pass
else:raise AssertionError('unsafe time of day')
assert server.gear_fields(',id=237840,embellishment=darkmoon_sigil_hunt')['embellishment']=='darkmoon_sigil_hunt'
for suffix in ('x\ninput=file','x,unknown=1'):
 try:server.gear_fields(',id=237840,embellishment='+suffix)
 except ValueError:pass
 else:raise AssertionError('unsafe embellishment')
print('PASS: demon hunter identity, day/night and embellishment validation')

for spec in server.CLASS_SPECS['warlock']:
 text='\n'.join(['warlock=test','level=90','race=Orc','spec='+spec,'talents='+server.BASE['character']['talents']])
 assert server.parse_import(text)['character']['race']=='orc'
 model=server.parse_import(text);model['character']['spec']='blood'
 try:server.validate(model)
 except ValueError:pass
 else:raise AssertionError('mismatched class/spec')
print('PASS: warlock three-spec import, case-insensitive upstream race and class/spec mismatch rejection')

for spec in server.CLASS_SPECS['mage']:
 text='\n'.join(['mage=test','level=90','race=Troll','spec='+spec,'talents='+server.BASE['character']['talents']])
 assert server.parse_import(text)['character']['class']=='mage'
print('PASS: mage three-spec import')

for spec in server.CLASS_SPECS['paladin']:
 assert server.parse_import('paladin=test\nlevel=90\nrace=tauren\nspec='+spec+'\ntalents='+server.BASE['character']['talents'])['character']['spec']==spec
print('PASS: paladin three-spec import')

for spec in server.CLASS_SPECS['hunter']:
 assert server.parse_import('hunter=test\nlevel=90\nrace=dwarf\nspec='+spec+'\ntalents='+server.BASE['character']['talents'])['character']['spec']==spec
print('PASS: hunter three-spec import')

for spec in server.CLASS_SPECS['shaman']:
 assert server.parse_import('shaman=test\nlevel=90\nrace=tauren\nspec='+spec+'\ntalents='+server.BASE['character']['talents'])['character']['spec']==spec
print('PASS: shaman three-spec import')

for cls,race in [('warrior','human'),('priest','human'),('druid','night_elf'),('monk','pandaren'),('evoker','dracthyr')]:
 for spec in server.CLASS_SPECS[cls]:
  c=server.parse_import(cls+'=test\nlevel=90\nrace='+race+'\nspec='+spec+'\ntalents='+server.BASE['character']['talents'])['character']
  assert c['class']==cls and c['spec']==spec
print('PASS: warrior, priest, druid, monk and evoker identity import')

# Experimental flags are selected by class and spec, never by user-supplied options.
from unittest.mock import patch
from types import SimpleNamespace
from copy import deepcopy
experimental={('priest','discipline'),('priest','holy'),('paladin','holy'),('monk','mistweaver'),('evoker','preservation')}
for cls,specs in server.CLASS_SPECS.items():
 for spec in specs:
  model=deepcopy(server.BASE);model['character'].update({'class':cls,'spec':spec})
  with patch.object(server.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='probe')) as call:
   assert server.calculate(model)['complete'] is False
   assert call.call_args.args[0][0]==str(server.HOLY_EXE if (cls,spec)==('paladin','holy') else server.EXE)
   assert ('allow_experimental_specializations=1' in call.call_args.args[0]) == ((cls,spec) in experimental)
print('PASS: experimental flag scoped to five authorized healer specs; no false success on rejection')

def empty_snapshot(args,**kwargs):
 (kwargs['cwd']/'result.json').write_text('{"sim":{"players":[{"collected_data":{"buffed_stats":{"stats":{},"attribute":{}}}}]}}')
 return SimpleNamespace(returncode=0,stdout='',stderr='')
with patch.object(server.subprocess,'run',side_effect=empty_snapshot):
 result=server.calculate(model)
 assert result['complete'] is False and 'values' not in result
print('PASS: exit zero with empty snapshot is not a successful zero-valued character')
