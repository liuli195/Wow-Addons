"""固定原文与轻量来源清单；所有持久读写沿用既有数据中心。"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator

import result_store
from search import digest

VERSION = 1
CHUNK_CHARS = 4 * 1024 * 1024


def _json_chunks(value):
    # 与 search.digest 的编码完全相同，但大字符串不会生成同样大的转义副本。
    if isinstance(value, str):
        yield '"'
        for index in range(0, len(value), CHUNK_CHARS):
            yield json.dumps(value[index:index + CHUNK_CHARS], ensure_ascii=False)[1:-1]
        yield '"'
    elif isinstance(value, dict):
        yield '{'
        for index, key in enumerate(sorted(value)):
            if index: yield ','
            yield json.dumps(key, ensure_ascii=False)
            yield ':'
            yield from _json_chunks(value[key])
        yield '}'
    elif isinstance(value, (list, tuple, Iterator)):
        yield '['
        for index, item in enumerate(value):
            if index: yield ','
            yield from _json_chunks(item)
        yield ']'
    else:
        yield json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def bounded_digest(value):
    checksum = hashlib.sha256()
    for chunk in _json_chunks(value):
        checksum.update(chunk.encode('utf-8'))
    return checksum.hexdigest()


def digest_rows(rows):
    """逐条校验同一个规范JSON数组，保留旧摘要及顺序。"""
    checksum = hashlib.sha256(b'[')
    for index, row in enumerate(rows):
        if index: checksum.update(b',')
        for chunk in _json_chunks(row):
            checksum.update(chunk.encode('utf-8'))
    checksum.update(b']')
    return checksum.hexdigest()


class Sources(list):
    def __init__(self, rows, revision):
        super().__init__(rows)
        self.revision = revision


def _text_identity(text):
    checksum = hashlib.sha256()
    for index in range(0, len(text), CHUNK_CHARS):
        checksum.update(text[index:index + CHUNK_CHARS].encode('utf-8'))
    return dict(version=VERSION, sha256=checksum.hexdigest(), characters=len(text),
                parts=max(1, (len(text) + CHUNK_CHARS - 1) // CHUNK_CHARS))


def _current():
    rows = result_store.read_records('seed_catalog', 'current')
    if not rows:
        return None
    if len(rows) != 1 or type(rows[0].get('version')) is not int or rows[0]['version'] != VERSION:
        raise result_store.InvalidRecordError('来源清单版本或数量无效')
    record = dict(rows[0])
    entries = record.get('entries')
    entries = json.loads(entries) if isinstance(entries, str) else entries
    if (not isinstance(entries, list) or record.get('revision') != digest(entries)
            or any(not isinstance(row, dict) or not row.get('source_id') for row in entries)
            or len({row['source_id'] for row in entries}) != len(entries)):
        raise result_store.InvalidRecordError('来源清单身份或内容无效')
    for row in entries:
        _check_reference(row.get('original_ref'))
    return dict(record, entries=entries)


def _check_reference(ref):
    if (not isinstance(ref, dict) or type(ref.get('version')) is not int or ref['version'] != VERSION
            or not isinstance(ref.get('sha256'), str) or re.fullmatch('[0-9a-f]{64}', ref['sha256']) is None
            or type(ref.get('characters')) is not int or ref['characters'] < 0
            or type(ref.get('parts')) is not int
            or ref['parts'] != max(1, (ref['characters'] + CHUNK_CHARS - 1) // CHUNK_CHARS)):
        raise result_store.InvalidRecordError('来源原件引用缺失或无效')
    if 'legacy_field' in ref and (ref['legacy_field'] not in ('source_id', 'candidate_id')
                                 or not isinstance(ref.get('legacy_id'), str)):
        raise result_store.InvalidRecordError('旧来源原件引用无效')


def _legacy():
    try:
        for row in result_store.iter_group('seed_candidates', 'registry'):
            value = dict(row)
            text = value.pop('original', None)
            if isinstance(text, str):
                field = 'source_id' if value.get('source_id') else 'candidate_id'
                value['original_ref'] = dict(_text_identity(text), legacy_field=field,
                                             legacy_id=value[field])
            else:
                value['original'] = text
            value.setdefault('source_id', value['candidate_id'])
            yield value
    except result_store.DataReadError as error:
        if not isinstance(error.__cause__, result_store._api()['MissingKeyError']):
            raise


def read_sources(*, originals=False):
    current = _current()
    rows = current['entries'] if current else list(_legacy())
    revision = current['revision'] if current else 'legacy:' + digest(rows)
    result = Sources((dict(row) for row in rows), revision)
    if originals:
        for row in result:
            row['original'] = original(row)
            row.pop('original_ref', None)
    return result


def original(row):
    if isinstance(row.get('original'), str):
        return row['original']
    ref = row.get('original_ref')
    _check_reference(ref)
    if 'legacy_field' in ref:
        matches = result_store.read_records('seed_candidates', 'registry',
            columns=['original'], filters={ref['legacy_field']: ref['legacy_id']})
        if len(matches) != 1 or not isinstance(matches[0].get('original'), str):
            raise result_store.InvalidRecordError('旧来源原件缺失或不唯一')
        text = matches[0]['original']
    else:
        chunks = []
        for index in range(ref.get('parts', 0)):
            values = result_store.read_records('seed_originals', f"{ref['sha256']}_{index}")
            if (len(values) != 1 or values[0].get('index') != index
                    or values[0].get('version') != VERSION or not isinstance(values[0].get('text'), str)):
                raise result_store.InvalidRecordError('来源原件分段缺失或损坏')
            chunks.append(values[0]['text'])
        text = ''.join(chunks)
    if _text_identity(text) != {key: ref.get(key) for key in ('version', 'sha256', 'characters', 'parts')}:
        raise result_store.InvalidRecordError('来源原件内容与冻结身份不符')
    return text


def _store_original(text):
    ref = _text_identity(text)
    for index in range(ref['parts']):
        key = f"{ref['sha256']}_{index}"
        expected = [dict(version=VERSION, index=index,
                         text=text[index * CHUNK_CHARS:(index + 1) * CHUNK_CHARS])]
        saved = result_store.read_records('seed_originals', key)
        if saved and saved != expected:
            raise result_store.InvalidRecordError('固定原件分段内容冲突')
        if not saved:
            try:
                result_store.write('seed_originals', key, expected,
                    schema=dict(version='UINTEGER', index='UINTEGER', text='VARCHAR'))
            except Exception:
                if result_store.read_records('seed_originals', key) != expected:
                    raise
        if result_store.read_records('seed_originals', key) != expected:
            raise result_store.InvalidRecordError('来源原件保存读回不符')
    return ref


def freeze(row):
    """冻结单条来源；调用方不会把完整原文带入准备队列和恢复计划。"""
    value = dict(row)
    if isinstance(value.get('original'), str):
        value['original_ref'] = _store_original(value['original'])
    else:
        _check_reference(value.get('original_ref'))
        if 'legacy_field' in value['original_ref']:
            value['original_ref'] = _store_original(original(value))
    value.pop('original', None)
    return value



def same_source(left, right):
    return _comparable(left) == _comparable(right)


def _comparable(row):
    value = dict(row)
    ref = value.pop('original_ref', None)
    text = value.pop('original', None)
    value['original_identity'] = (_text_identity(text) if isinstance(text, str) else
        {key: ref.get(key) for key in ('version', 'sha256', 'characters', 'parts')} if ref else None)
    for field in ('program', 'core', 'allowed_groups'):
        if isinstance(value.get(field), str):
            value[field] = json.loads(value[field])
    return value

def publish(rows, *, expected_revision, activate=False):
    """原件先验真，锁内只核对当前清单并切换；旧原件总表不再覆盖。"""
    from seed_training import writer_lock
    base = _current()
    if base is None and not activate:
        from seed_training import CANDIDATE_SCHEMA
        with writer_lock():
            previous = list(_legacy())
            if _current() is not None or 'legacy:' + digest(previous) != expected_revision:
                raise ValueError('来源清单已被其他操作更新，拒绝覆盖')
            if [_comparable(row) for row in previous] == [_comparable(row) for row in rows]:
                return
            legacy = []
            for row in rows:
                value = {key: row.get(key) for key in CANDIDATE_SCHEMA}
                value['original'] = original(row)
                legacy.append(value)
            result_store.write('seed_candidates', 'registry', legacy, schema=CANDIDATE_SCHEMA)
        return
    entries = []
    known = {digest(row['original_ref']) for row in base['entries']} if base else set()
    for row in rows:
        entry = dict(row)
        ref = entry.get('original_ref')
        if not isinstance(ref, dict) or 'legacy_field' in ref or isinstance(entry.get('original'), str):
            ref = _store_original(original(entry))
        elif digest(ref) not in known:
            # 新引入的引用须验真；未变的固定原件沿可信清单复用，不重读全部归档。
            original(entry)
        entry.pop('original', None)
        entry['original_ref'] = ref
        entries.append(entry)
    record = dict(version=VERSION, revision=digest(entries), entries=entries)
    with writer_lock():
        current = _current()
        revision = current['revision'] if current else 'legacy:' + digest(list(_legacy()))
        if revision != expected_revision:
            raise ValueError('来源清单已被其他操作更新，拒绝覆盖')
        if current and [_comparable(row) for row in current['entries']] == [_comparable(row) for row in rows]:
            return current['revision']
        try:
            result_store.write('seed_catalog', 'current', [record],
                schema=dict(version='UINTEGER', revision='VARCHAR', entries='JSON'))
        except Exception:
            saved = _current()
            if saved is None or saved['revision'] != record['revision']:
                raise
        saved = _current()
        if saved is None or saved['revision'] != record['revision']:
            raise result_store.InvalidRecordError('来源清单发布读回不符')
    return record['revision']


def activate():
    """仅供明确批准的资料切换；普通读取与登记不自动迁移旧中心。"""
    rows = read_sources()
    return publish(rows, expected_revision=rows.revision, activate=True)


def print_sources(*, unsupported):
    """公开列表保留原字段及完整原文，逐条输出同一个JSON数组。"""
    print('[', end='')
    separator = ''
    for row in read_sources():
        if (row['semantic'] == 'unsupported' or row.get('active') is False) != unsupported:
            continue
        value = dict(row, original=original(row))
        value.pop('original_ref', None)
        for field in ('program', 'core', 'allowed_groups'):
            if isinstance(value.get(field), (list, dict)):
                value[field] = json.dumps(value[field], ensure_ascii=False)
        print(separator + json.dumps(value, ensure_ascii=False), end='')
        separator = ', '
    print(']')
