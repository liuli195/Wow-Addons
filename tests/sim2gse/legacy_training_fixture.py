"""仅构造已完成v1历史凭据，不供新任务执行或加载current规则。"""

def _minimal_rule_pack():
    """构造报告只覆盖这份有序起手，不冒充完整指南角色。"""
    from copy import deepcopy

    names = ('outbreak', 'scourge_strike', 'death_coil', 'epidemic')
    pack = dict(schema_version=2,
        identity_mappings=dict(hero_talents={'rider_of_the_apocalypse': 32}),
        general=dict(templates={}), execution_evidence={},
        object_sets={'sample': {name: dict(kind='action', native_action=name,
            base_button=name, native_forms=[name]) for name in names}},
        configurations=[dict(key=dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
            target_type='single_target'), objects_ref='sample', execution_ref=None,
            states={'only': dict(effect=None, expected=True, priority=[])},
            opener=dict(source_basis='fixture: ordered task boundary', source_steps=list(names[:3]),
                precombat=[], burst_anchor=None, independent_burst_source_steps=[],
                ordinary_steps=[dict(action=name, source_step=index, source_form=name,
                    attribute_query=dict(native_form=name, base_button=name,
                                         missing='unknown_no_base_cost_fallback'))
                    for index, name in enumerate(names[:3], 1)]))])
    aoe = deepcopy(pack['configurations'][0])
    aoe['key']['target_type'] = 'aoe'
    pack['configurations'].append(aoe)
    return pack
