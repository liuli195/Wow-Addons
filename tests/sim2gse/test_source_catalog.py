"""来源命令的完整读写；存储边界为内存替身，不声称物理验收。"""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path

import pytest


@pytest.fixture
def catalog_cli(monkeypatch):
    import result_store
    import seed_training as seeds
    old = dict.fromkeys(seeds.CANDIDATE_SCHEMA)
    old.update(candidate_id='archived', source_id='archived', source_revision='original-revision',
               label='归档', class_name='deathknight', spec='unholy', source='retained',
               original='旧原文必须保留', instructions='不能训练', semantic='unsupported',
               changes=['日志不是按键'], family='archive', core='[]', program='[]',
               active=False, unavailable_reason='仅留证据')
    records = {('seed_candidates', 'registry'): [old]}
    def read(table, key, **kwargs):
        rows = deepcopy(records.get((table, key), []))
        rows = [row for row in rows if all(row.get(name) == value
                for name, value in kwargs.get('filters', {}).items())]
        return [{name: row[name] for name in kwargs['columns']} for row in rows] if kwargs.get('columns') else rows
    def write(table, key, rows, **kwargs):
        records[table, key] = deepcopy(rows)
        return len(rows)
    monkeypatch.setattr(result_store, 'bind_project', lambda project: None)
    monkeypatch.setattr(result_store, 'ensure_available', lambda: None)
    monkeypatch.setattr(result_store, 'read_records', read)
    monkeypatch.setattr(result_store, 'iter_group', lambda table, key, **kwargs: iter(read(table, key)))
    monkeypatch.setattr(result_store, 'write', write)
    monkeypatch.setattr(seeds, 'writer_lock', nullcontext)
    material = dict(label='新来源', class_name='deathknight', spec='unholy', source='manual',
                    original='新原文', instructions='重复', semantic='preserved', changes=[],
                    family='plain', core=[], program=[['outbreak']],
                    allowed_groups=[dict(specialization_id=252, hero_talent='rider_of_the_apocalypse',
                                         target_type='single_target', target_count=1)])
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs: json.dumps(material, ensure_ascii=False))
    return records, material


def test_register_and_list_preserve_originals_without_copying_them_into_catalog(catalog_cli, capsys):
    import seed_training as seeds
    from search import digest
    import hashlib
    records, material = catalog_cli
    retained = deepcopy(records['seed_candidates', 'registry'])
    text = '旧原文必须保留'
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    entry = dict(retained[0])
    entry.pop('original')
    entry['original_ref'] = dict(version=1, sha256=sha, characters=len(text), parts=1)
    records['seed_originals', sha + '_0'] = [dict(version=1, index=0, text=text)]
    records['seed_catalog', 'current'] = [dict(version=1, revision=digest([entry]), entries=[entry])]
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered['status'] == 'registered'
    assert records['seed_candidates', 'registry'] == retained
    current = records['seed_catalog', 'current']
    assert '旧原文必须保留' not in json.dumps(current, ensure_ascii=False)
    assert '新原文' not in json.dumps(current, ensure_ascii=False)
    assert seeds.main(['--project', '/memory', 'list', '--state', 'unsupported', '--legacy']) == 0
    archived = json.loads(capsys.readouterr().out)
    assert len(archived) == 1 and archived[0]['original'] == '旧原文必须保留'
    assert archived[0]['unavailable_reason'] == '仅留证据'
    assert seeds.main(['--project', '/memory', 'list', '--state', 'pending', '--legacy']) == 0
    active = json.loads(capsys.readouterr().out)
    assert len(active) == 1 and active[0]['original'] == material['original']


def test_register_does_not_activate_catalog_without_explicit_conversion(catalog_cli, capsys):
    import seed_training as seeds
    records, _ = catalog_cli
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    assert ('seed_catalog', 'current') not in records
    assert len(records['seed_candidates', 'registry']) == 2
    assert records['seed_candidates', 'registry'][0]['original'] == '旧原文必须保留'


def test_corrupt_reference_is_an_error_not_an_empty_source_library(catalog_cli, capsys):
    import seed_training as seeds
    from search import digest
    records, _ = catalog_cli
    entry = dict(records['seed_candidates', 'registry'][0])
    entry.pop('original')
    entry['original_ref'] = dict(version=1, sha256='bad', characters=8, parts=0)
    records['seed_catalog', 'current'] = [dict(version=1, entries=[entry], revision=digest([entry]))]
    before = deepcopy(records['seed_catalog', 'current'])
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 2
    assert records['seed_catalog', 'current'] == before


def test_lost_write_response_is_confirmed_by_readback(catalog_cli, capsys, monkeypatch):
    import result_store
    import seed_training as seeds
    from search import digest
    records, _ = catalog_cli
    records['seed_catalog', 'current'] = [dict(version=1, revision=digest([]), entries=[])]
    save = result_store.write
    def lost_reply(table, key, rows, **kwargs):
        save(table, key, rows, **kwargs)
        raise RuntimeError('写入已经完成，回复丢失')
    monkeypatch.setattr(result_store, 'write', lost_reply)
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    capsys.readouterr()
    assert seeds.main(['--project', '/memory', 'list', '--state', 'pending', '--legacy']) == 0
    assert json.loads(capsys.readouterr().out)[0]['original'] == '新原文'


def test_legacy_revision_without_field_keeps_its_original_content_identity(catalog_cli):
    import hashlib
    import seed_training as seeds
    records, _ = catalog_cli
    row = records['seed_candidates', 'registry'][0]
    row.pop('source_revision')
    expected = dict(row, core=[], program=[])
    checksum = hashlib.sha256(json.dumps(expected, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    assert records['seed_candidates', 'registry'][0]['source_revision'] == checksum


def test_repeated_registration_does_not_reorder_the_active_catalog(catalog_cli, capsys):
    import seed_training as seeds
    from search import digest
    import source_catalog
    records, _ = catalog_cli
    # 激活属于本次隔离数据的明确维护动作，不修改正式中心。
    source_catalog.activate()
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    current = records['seed_catalog', 'current'][0]
    current['entries'].reverse()
    current['revision'] = digest(current['entries'])
    frozen = deepcopy(records['seed_catalog', 'current'])
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 0
    assert records['seed_catalog', 'current'] == frozen


def test_existing_registry_consumers_keep_complete_legacy_rows(catalog_cli):
    import seed_training as seeds
    records, _ = catalog_cli
    rows = seeds.registry_rows()
    assert rows[0]['original'] == '旧原文必须保留'
    assert set(rows[0]) == set(seeds.CANDIDATE_SCHEMA)
    assert rows[0]['program'] == []


@pytest.mark.parametrize('failure', ['missing', 'damaged', 'unavailable'])
def test_original_read_failure_preserves_the_catalog(catalog_cli, capsys, monkeypatch, failure):
    import result_store
    import seed_training as seeds
    import source_catalog
    records, _ = catalog_cli
    source_catalog.activate()
    frozen = deepcopy(records['seed_catalog', 'current'])
    part = next(key for key in records if key[0] == 'seed_originals')
    if failure == 'missing':
        records.pop(part)
    elif failure == 'damaged':
        records[part][0]['text'] = '损坏原文'
    else:
        read = result_store.read_records
        def unavailable(table, key, **kwargs):
            if table == 'seed_originals':
                raise result_store.DataReadError('暂时不可读取')
            return read(table, key, **kwargs)
        monkeypatch.setattr(result_store, 'read_records', unavailable)
    assert seeds.main(['--project', '/memory', 'list', '--state', 'unsupported', '--legacy']) == 2
    assert records['seed_catalog', 'current'] == frozen
    assert records['seed_candidates', 'registry'][0]['original'] == '旧原文必须保留'


def test_registration_rejects_a_concurrent_catalog_revision(catalog_cli, capsys, monkeypatch):
    import result_store
    import seed_training as seeds
    import source_catalog
    from search import digest
    records, _ = catalog_cli
    source_catalog.activate()
    save = result_store.write
    changed = []
    def concurrent_writer(table, key, rows, **kwargs):
        result = save(table, key, rows, **kwargs)
        if table == 'seed_originals' and not changed:
            current = records['seed_catalog', 'current'][0]
            current['entries'][0]['label'] = '另一更新已发布'
            current['revision'] = digest(current['entries'])
            changed.append(deepcopy(records['seed_catalog', 'current']))
        return result
    monkeypatch.setattr(result_store, 'write', concurrent_writer)
    assert seeds.main(['--project', '/memory', 'register', '/material.json']) == 2
    assert records['seed_catalog', 'current'] == changed[0]
