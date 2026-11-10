"""正式冠军来源与恢复决策的内存规则检查。"""
import pytest


def test_public_formal_evidence_validates_reports_without_bulk_loading(monkeypatch):
    import formal_search, result_store
    from champion_evidence_fixture import formal_cohort
    record, state, character, _, _, reports = formal_cohort()
    monkeypatch.setattr(result_store, 'read_many', lambda *a, **k: pytest.fail('正式验真不能整组装入报告'))
    monkeypatch.setattr(result_store, 'iter_group', lambda table, group: iter(reports))
    formal_search.validate_evidence(record, state, character, verify_reports=True)


def test_public_formal_champion_rejects_a_truncated_finalist_cohort_before_scoring():
    from copy import deepcopy
    import result_store
    import task
    from champion_evidence_fixture import formal_cohort
    record, state, character, run, candidate, _ = formal_cohort()
    task._validate_formal_source(record, state, character, run=run, candidate=candidate,
        verify_reports=False)
    truncated = deepcopy(record)
    removed = truncated['evaluation']['finalists'].pop(0)
    truncated['evaluation']['finalist_keys'].remove(removed['key'])
    removed_batches = {batch['data_key'] for batch in removed['batches']}
    truncated['batch_keys'] = [key for key in truncated['batch_keys'] if key not in removed_batches]
    with pytest.raises(result_store.InvalidRecordError, match='完整正式来源'):
        task._validate_formal_source(truncated, state, character, run=run,
            candidate=candidate, verify_reports=False)
    assert len(run['final_scenarios']['nominal']['finalists']) == 2
