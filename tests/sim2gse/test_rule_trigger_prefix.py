"""前序触发关联的公开诊断契约；不依赖内部缓存或调用次数。"""
import copy
import pytest
from rule_config import validate
from rule_diagnostics import diagnose
from runtime import TaskRuntime
from search import digest
from test_rule_initialization import _opener_pack

def _invocation(exports, *, refs=None, read_refs=None, fields=None, query_input=0, read_source='evaluation.prior_rule_trigger_records', shadow=False):
    pack=_opener_pack({'tap':'outbreak'},[dict(action='tap',source_step=1)])
    priority=[]
    for index,records in enumerate(exports):
        name='rule '+str(index)
        pack['general']['templates'][name]=dict(application_phase='post_simulation_diagnosis_and_next_candidate',parameters={},reads=[],
          diagnose=dict(let=[],for_each=[],**{'as':'unused'},cases=[],export_trigger_records=records),edits=[])
        priority.append(dict(name=name,template=name,arguments={}))
    names=[r['name'] for r in priority]
    expression={'op':'any3','args':[{'op':'map','as':'ref','args':[{'arg':'refs'},
      {'op':'lookup_unique','args':[{'var':'prior'},{'op':'record','fields':{'input_index':{'var':'q.input_index'},'rule_name':{'var':'ref'}}}],
       'value_field':'trigger','duplicate':'error','missing':'unknown'}]}]}
    read=dict(**{'as':'prior','from':read_source},object={'arg':'read_refs'} if read_refs is not None else {'arg':'refs'},
      fields=['input_index','rule_name','trigger'] if fields is None else fields,same_run=True,on_declared_null_object='not_applicable_identity_rows')
    lets=[]
    if shadow:lets.append(dict(name='prior',value=[]))
    lets.append(dict(name='answers',value=dict(op='map',args=[[dict(input_index=query_input)],dict(op='record',fields={'answer':expression})],**{'as':'q'})))
    pack['general']['templates']['consumer']=dict(application_phase='post_simulation_diagnosis_and_next_candidate',
      parameters={'refs':dict(type='rule_ref_array'),**({'read_refs':dict(type='rule_ref_array')} if read_refs is not None else {})},reads=[read],
      diagnose=dict(let=lets,for_each={'var':'answers'},**{'as':'answer'},cases=[
       dict(kind=kind,when=condition,certainty='observed_fact',evidence={}) for kind,condition in [
        ('true',{'var':'answer.answer'}),('false',dict(op='not',args=[{'var':'answer.answer'}])),('unknown',dict(op='unknown',args=[{'var':'answer.answer'}]))]],export_trigger_records=[]),edits=[])
    priority.append(dict(name='consumer',template='consumer',arguments=dict(refs=names if refs is None else refs,**({'read_refs':read_refs} if read_refs is not None else {}))))
    pack['configurations'][0]['states']['only']['priority']=priority
    snapshot=dict(pack=pack,resolved=validate(pack),rule_config_digest=digest(pack))
    report=dict(sim=dict(players=[dict(sim2gse_rule_observations=dict(protocol=1,
      scope=dict(sample_selection='first_scored_complete',sample_id=1,start_ms=0,end_ms=200,complete=True),
      inputs=[dict(sample_id=1,input_index=0,event_index=0,time=0,source_step=0,input_source='loop')],
      action_observations=[],state_observations=[],effect_observations=[]))]))
    bindings = [dict(state=name, **binding)
                for name, state in snapshot['resolved'][0]['states'].items()
                for binding in state['priority']]
    return dict(program=[['outbreak']],capabilities={},initialization=dict(rule_snapshot=snapshot,configuration_key=snapshot['resolved'][0]['key'], bindings=bindings),
      report=report,task_run_id='fixture',batch_key='same-batch',behavior_identity='same-program',requested_iterations=2)


@pytest.mark.parametrize('exports, options, expected', [([[dict(input_index=0, trigger=False)]], {}, 'false'), ([[dict(input_index=0, trigger=True)]], {}, 'true'), ([[dict(input_index=0, trigger=1)]], {}, 'unknown'), ([[dict(input_index=0, trigger=False), dict(input_index=0, trigger=True)], [dict(input_index=0, trigger=True)]], {}, 'error')])
def test_diagnose_preserves_ordered_prior_trigger_truth_and_errors(exports, options, expected):
    result = diagnose(**_invocation(exports, **options), runtime=TaskRuntime())
    rule = result['rules'][-1]
    assert result['pool']['complete'] is True
    if expected == 'error':
        assert rule['reason'] == '同次事实关联不唯一'
        assert rule['findings'] == []
    else:
        assert [finding['kind'] for finding in rule['findings']] == [expected]


def test_diagnose_keeps_states_and_separate_reports_independent():
    invocation = _invocation([[dict(input_index=0, trigger=True)]])
    snapshot = invocation['initialization']['rule_snapshot']
    pack = snapshot['pack']
    second = copy.deepcopy(pack['configurations'][0]['states']['only'])
    first_template = pack['general']['templates']['rule 0']
    pack['general']['templates']['other facts'] = copy.deepcopy(first_template)
    pack['general']['templates']['other facts']['diagnose']['export_trigger_records'][0]['trigger'] = False
    second['priority'][0]['template'] = 'other facts'
    pack['configurations'][0]['states']['second'] = second
    snapshot.update(resolved=validate(pack), rule_config_digest=digest(pack))
    invocation['initialization']['bindings'] = [dict(state=name, **binding)
        for name, state in snapshot['resolved'][0]['states'].items()
        for binding in state['priority']]
    result = diagnose(**invocation, runtime=TaskRuntime())
    consumers = [row for row in result['rules'] if row['name'] == 'consumer']
    assert [(row['state'], row['findings'][0]['kind']) for row in consumers] == [('only', 'true'), ('second', 'false')]

    invocation = copy.deepcopy(invocation)
    snapshot = invocation['initialization']['rule_snapshot']
    snapshot['pack']['general']['templates']['rule 0']['diagnose']['export_trigger_records'][0]['trigger'] = False
    snapshot.update(resolved=validate(snapshot['pack']), rule_config_digest=digest(snapshot['pack']))
    result = diagnose(**invocation, runtime=TaskRuntime())
    assert [row['findings'][0]['kind'] for row in result['rules'] if row['name'] == 'consumer'] == ['false', 'false']


def test_diagnose_reports_incomplete_after_runtime_stop():
    runtime = TaskRuntime(600)
    runtime.cancel()
    result = diagnose(**_invocation([[dict(input_index=0, trigger=True)]]), runtime=runtime)
    assert result['pool']['complete'] is False
    assert result['pool']['incomplete_reason'] == 'cancelled'
    assert result['pool']['operations'] == []
    assert all(rule['reason'] == 'cancelled' for rule in result['rules'])

def test_diagnose_preserves_map_alias_shadowing_of_its_prior_source():
    invocation = _invocation([[dict(input_index=0, trigger=True)]])
    snapshot = invocation['initialization']['rule_snapshot']
    template = snapshot['pack']['general']['templates']['consumer']
    expression = template['diagnose']['let'][0]['value']['args'][1]['fields']['answer']
    mapping = expression['args'][0]
    mapping['as'] = 'prior'
    mapping['args'][1]['args'][1]['fields']['rule_name'] = dict(var='prior')
    snapshot.update(resolved=validate(snapshot['pack']), rule_config_digest=digest(snapshot['pack']))
    result = diagnose(**invocation, runtime=TaskRuntime())
    assert [row['kind'] for row in result['rules'][-1]['findings']] == ['unknown']

def test_diagnose_preserves_partial_facts_when_budget_ends_midway(monkeypatch):
    import runtime as runtime_module
    invocation = _invocation([[dict(input_index=0, trigger=True)]])
    snapshot = invocation['initialization']['rule_snapshot']
    template = snapshot['pack']['general']['templates']['rule 0']['diagnose']
    template['for_each'] = [{}]
    template['cases'] = [dict(kind='finished_fact', when=True, certainty='observed_fact', evidence={})]
    snapshot.update(resolved=validate(snapshot['pack']), rule_config_digest=digest(snapshot['pack']))
    ticks = iter([0.0, 0.0])
    monkeypatch.setattr(runtime_module.time, 'monotonic', lambda: next(ticks, 2.0))
    result = diagnose(**invocation, runtime=TaskRuntime(1))
    assert [row['kind'] for row in result['rules'][0]['findings']] == ['finished_fact']
    assert result['pool']['complete'] is False
    assert result['pool']['incomplete_reason'] == 'budget_exhausted'
    assert result['rules'][-1]['reason'] == 'budget_exhausted'
    assert result['pool']['operations'] == []
