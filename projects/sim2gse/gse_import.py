"""有界解码第三方 GSE 导入字符串；不执行其中的脚本。"""

import base64
import binascii
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import tempfile
import zlib

import cbor2
from codec import LUA, ROOT, SOURCE, lua_literal, wire_value
from runtime import ProcessTimeout, TaskRuntime, run_command
from program import (ActionNode, EmbedNode, IfNode, LoopNode, WaitClicksNode, Program,
                     ProgramNode, RepeatNode, SourcePosition, CompiledActionNode,
                     CompiledEmptyClickNode, _with_compiled_program)
from macro_interpreter import (macro_spell_ids, macro_spell_names, map_action, map_macro,
                               preflight_macro)


MAX_TEXT = 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 10000
VALID_TYPES = {"Action", "Repeat", "Loop", "Pause", "If", "Embed"}
LOCK_PATH = ROOT / "projects/sim2gse/compatibility/lock.json"
_PROTECTED_KEYS = {
    "1": bytes((62, 219, 34, 238, 241, 49, 89, 6, 129, 129, 249, 22, 151, 152, 36, 30,
                 140, 98, 198, 223, 66, 41, 211, 84, 233, 92, 232, 202, 56, 248, 123, 37)),
}


class _GSEResourceLimit(ValueError):
    """A hard import budget was exceeded and must not become a recoverable member warning."""


class _RawCBORBytes(bytes):
    """CBOR 字节串无法按 UTF-8 解码时仍保留其原始内容。"""


def _locked_gse_version():
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))["gse_version"]


def _gse_version_label(value):
    return f"{value // 1000}.{value // 100 % 10}.{value % 100:02d}"


def _simulation_compatibility(gse_version, locked_version):
    if type(gse_version) is not int or gse_version <= 3200:
        return False, "GSE 元数据版本缺失或低于当前可识别范围"
    if gse_version > locked_version:
        return False, (f"GSE 元数据版本 {gse_version} 高于锁定的 GSE "
                       f"{_gse_version_label(locked_version)}（{locked_version}），可解析但不能模拟")
    return True, None


def _plain(value, depth=0, count=None):
    if count is None:
        count = [0]
    count[0] += 1
    if depth > MAX_DEPTH or count[0] > MAX_NODES:
        raise ValueError("GSE 导入结构过深或节点过多")
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            return _RawCBORBytes(value)
    if isinstance(value, list):
        return [_plain(item, depth + 1, count) for item in value]
    if isinstance(value, dict):
        return {_plain(key, depth + 1, count): _plain(item, depth + 1, count)
                for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise ValueError("GSE 导入包含不支持的数据类型")


_NUMBER_KEY = re.compile(r"^[\t ]*[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[\t ]*$")


def _numeric_key(key):
    if type(key) is int:
        return key
    if type(key) is float and math.isfinite(key):
        return int(key) if key.is_integer() else key
    if isinstance(key, str) and _NUMBER_KEY.fullmatch(key):
        number = float(key)
        if math.isfinite(number):
            return int(number) if number.is_integer() else number
    return None


def _fix_container(value, path="GSE"):
    """Mirror GSE fixContainer: numeric string keys holding tables become numbers."""
    if isinstance(value, list):
        return [_fix_container(item, f"{path}[{index}]") for index, item in enumerate(value, 1)]
    if not isinstance(value, dict):
        return value
    fixed = {}
    for key, item in value.items():
        child_path = f"{path}[{key}]"
        normalized_item = _fix_container(item, child_path)
        numeric_key = _numeric_key(key) if isinstance(item, (dict, list)) else None
        normalized_key = numeric_key if numeric_key is not None else key
        if normalized_key in fixed:
            raise ValueError(f"GSE 数值字段键归一后重复（位置：{child_path}）")
        fixed[normalized_key] = normalized_item
    return fixed


def _indexed_items(value):
    """Return numeric table entries in source-index order, keeping sparse indices."""
    if isinstance(value, list):
        return list(enumerate(value, 1))
    if isinstance(value, dict):
        items = []
        seen = set()
        for key, item in value.items():
            index = _numeric_key(key)
            if index is None:
                continue
            if index in seen:
                raise ValueError(f"GSE 数值字段键归一后重复（位置：[{key}]）")
            seen.add(index)
            items.append((index, item))
        return sorted(items, key=lambda pair: pair[0])
    return None


def _version_items(value, path):
    items = _indexed_items(value)
    if items is None or not items:
        raise ValueError(f"GSE 导入版本结构无效（位置：{path}）")
    for index, version in items:
        if not isinstance(version, dict):
            raise ValueError(f"GSE 导入版本必须为映射（位置：{path}[{index}]）")
    return items


def _sequence_versions(value, name, source_path=None):
    """Validate version mappings without compacting or rejecting sparse upstream keys."""
    path = f"{source_path or f'Sequences[{name}]'}.Versions" if name else "Versions"
    _version_items(value, path)
    return value


def _version_get(sequence, version):
    return dict(_version_items(sequence.get("Versions"), "Versions")).get(version)


def _version_runtime_issue(sequence, version):
    items = _version_items(sequence.get("Versions"), "Versions")
    indexes = [index for index, _ in items]
    if type(version) is not int or version < 1:
        return "GSE 运行时只读取从 1 开始的整数版本索引"
    if any(index <= 0 for index in indexes):
        return "版本包含 0 或非正数索引，GSE 结构扫描会重排版本"
    if not all(index in indexes for index in range(1, version + 1)):
        return "版本索引有空洞，GSE 当前序列运行时无法按该索引读取"
    return None


def _sequence_warnings(sequence, name, source_path=None):
    path = f"{source_path or f'Sequences[{name}]'}.Versions"
    items = _version_items(sequence["Versions"], path)
    indexes = [index for index, _ in items]
    warnings = []
    if 0 in indexes:
        warnings.append(f"{path} contains index 0; GSE repairs it during structural scan")
    positive = [index for index in indexes if type(index) is int and index > 0]
    if positive and positive != list(range(1, max(positive) + 1)):
        warnings.append(f"{path} has sparse indexes; GSE reports gaps and may require repair")

    def visit_action(action, action_path):
        if not isinstance(action, dict):
            return
        kind = action.get("Type")
        if kind == "Loop":
            visit_collection(action, action_path)
        elif kind == "If":
            for branch_index in (1, 2):
                branch = action.get(branch_index, action.get(str(branch_index)))
                if branch is not None:
                    visit_collection(branch, f"{action_path}[{branch_index}]")

    def visit_collection(value, collection_path):
        entries = _indexed_items(value)
        if entries is None:
            return
        indexes = [index for index, _ in entries]
        expected = list(range(1, len(indexes) + 1))
        if indexes != expected:
            mismatch = next((actual for actual, wanted in zip(indexes, expected)
                             if actual != wanted), None)
            if mismatch is None:
                mismatch = expected[len(indexes)] if len(indexes) < len(expected) else indexes[-1]
            warnings.append(
                f"GSE sparse action indexes; ipairs stops at the gap before {collection_path}[{mismatch}]")
        for index, action in entries:
            visit_action(action, f"{collection_path}[{index}]")

    for version, record in items:
        actions_path = f"{path}[{version}].Actions"
        if "Actions" in record:
            visit_collection(record["Actions"], actions_path)
        else:
            warnings.append(
                f"GSE 版本缺少 Actions 数组；版本级数字块已保留，不能模拟（位置：{actions_path}）")
    return warnings


def _action_collection(value, path):
    entries = _indexed_items(value)
    if entries is None:
        raise ValueError(f"GSE 动作列表必须是数组或数字键映射（位置：{path}）")
    for index, action in entries:
        if not isinstance(action, dict):
            raise ValueError(f"GSE 控制块必须为映射（位置：{path}[{index}]）")
    return entries


def _check_runtime_action_indexes(value, path):
    """Keep sparse tables parseable, but do not simulate past Lua ipairs gaps."""
    entries = _indexed_items(value)
    if entries is None:
        return
    indexes = [index for index, _ in entries]
    expected = list(range(1, len(indexes) + 1))
    if indexes != expected:
        mismatch = next((actual for actual, wanted in zip(indexes, expected)
                         if actual != wanted), None)
        if mismatch is None:
            mismatch = expected[len(indexes)] if len(indexes) < len(expected) else indexes[-1]
        raise ValueError(f"GSE 动作索引有空洞或非连续索引（位置：{path}[{mismatch}]）")


def _parse_block(action, sequence_name, version, path, syntax):
    kind = action.get("Type")
    if not isinstance(kind, str) or kind not in VALID_TYPES:
        raise ValueError(f"GSE 控制块类型无法解析：{kind}（位置：{sequence_name} v{version} {path}.Type）")
    syntax.append(dict(sequence=sequence_name, version=version, type=kind, path=path))

    if kind in {"Loop", "If"}:
        for key, child in action.items():
            index = _numeric_key(key)
            if index is None or (kind == "If" and index not in (1, 2)):
                continue
            child_path = f"{path}[{index}]"
            if isinstance(child, list):
                for child_index, nested in _action_collection(child, child_path):
                    _parse_block(nested, sequence_name, version,
                                 f"{child_path}[{child_index}]", syntax)
            elif isinstance(child, dict) and "Type" in child:
                _parse_block(child, sequence_name, version, child_path, syntax)
            else:
                _action_collection(child, child_path)
                for child_index, nested in _action_collection(child, child_path):
                    _parse_block(nested, sequence_name, version,
                                 f"{child_path}[{child_index}]", syntax)


def _parse_sequences(sequences, source_paths=None):
    syntax = []
    for sequence_name, sequence in sequences.items():
        sequence_path = (source_paths or {}).get(sequence_name, f"Sequences[{sequence_name}]")
        for version, record in _version_items(sequence["Versions"],
                                               f"{sequence_path}.Versions"):
            actions_path = f"{sequence_path}.Versions[{version}].Actions"
            if "Actions" not in record:
                version_path = f"{sequence_path}.Versions[{version}]"
                for index, action in _indexed_items(record) or []:
                    if not isinstance(action, dict):
                        raise ValueError(
                            f"GSE 版本级数字块必须为映射（位置：{version_path}[{index}]）")
                    _parse_block(action, sequence_name, version,
                                 f"{version_path}[{index}]", syntax)
                continue
            for index, action in _action_collection(record["Actions"], actions_path):
                _parse_block(action, sequence_name, version, f"{actions_path}[{index}]", syntax)
    return syntax


def _decompress_cbor(compressed):
    inflater = zlib.decompressobj(-15)
    raw = inflater.decompress(compressed, MAX_DECODED + 1)
    if len(raw) > MAX_DECODED or inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
        raise ValueError("GSE 导入解压结果过大或不完整")
    raw += inflater.flush(MAX_DECODED + 1 - len(raw))
    if len(raw) > MAX_DECODED:
        raise ValueError("GSE 导入解压结果过大")
    stream = io.BytesIO(raw)
    payload = _plain(cbor2.CBORDecoder(stream, allow_duplicate_keys=False).decode())
    if stream.read(1):
        raise ValueError("GSE 导入编码含有多余数据")
    return raw, payload


def _decrypt_protected(key_id, packed):
    key = _PROTECTED_KEYS.get(key_id)
    if key is None:
        raise ValueError(f"GSE 受保护导入密钥编号不受锁定上游支持：{key_id!r}")
    if len(packed) < 12:
        raise ValueError("GSE 受保护导入缺少 12 字节随机数")
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
    except ImportError as error:
        raise ValueError("GSE 受保护导入解码依赖缺失：cryptography==50.0.1") from error
    nonce, ciphertext = packed[:12], packed[12:]
    cipher = Cipher(algorithms.ChaCha20(key, bytes(4) + nonce), mode=None)
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def _decode_gse_message(text):
    """读取一个普通或受保护的 GSE 消息，返回 CBOR 原字节、对象和外壳标志。"""
    if not isinstance(text, str) or len(text) > MAX_TEXT or not text.startswith("!GSE3!"):
        raise ValueError("GSE 导入字符串格式或长度无效")
    protected = text.startswith("!GSE3!+")
    key_id = text[7:8] if protected else None
    encoded = text[8:] if protected else text[6:]
    if not encoded:
        raise ValueError("GSE 导入编码无效")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        # Base64 handles validation; this error-only scan preserves the prior public diagnostic.
        padding = len(encoded) - len(encoded.rstrip("="))
        body = encoded[:-padding] if padding else encoded
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        invalid_alphabet = any(character not in alphabet for character in body)
        if padding > 2 or "=" in body or invalid_alphabet:
            raise ValueError("GSE 导入编码无效") from error
        raise ValueError("GSE 导入编码或内容损坏") from error
    try:
        if protected:
            compressed = _decrypt_protected(key_id, compressed)
        raw, payload = _decompress_cbor(compressed)
    except cbor2.CBORDecodeError as error:
        duplicate = re.search(r"Duplicate map key: (.+)", str(error))
        if duplicate:
            raise ValueError(f"GSE 导入 CBOR 含重复字段键，无法无损解析：{duplicate.group(1)}") from error
        reason = "受保护导入解密后内容损坏" if protected else "编码或内容损坏"
        raise ValueError(f"GSE 导入{reason}") from error
    except (binascii.Error, zlib.error, UnicodeDecodeError) as error:
        reason = "受保护导入解密后内容损坏" if protected else "编码或内容损坏"
        raise ValueError(f"GSE 导入{reason}") from error
    return raw, payload, protected


def _delta_indexed_items(value, path):
    if isinstance(value, list):
        return list(enumerate(value, 1))
    if not isinstance(value, dict):
        raise ValueError(f"GSE Delta 动作列表必须为数组或映射（位置：{path}）")
    items = []
    for key, item in value.items():
        if type(key) is int and key >= 1:
            items.append((key, item))
        elif type(key) is float and math.isfinite(key) and key >= 1 and key.is_integer():
            items.append((int(key), item))
    return sorted(items)


def _delta_list(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    return [item for _, item in _delta_indexed_items(value, "GSE Delta")]


def _delta_action_list(base, overlay, path):
    base_blocks = _delta_list(base)
    result = []
    for index, operation in _delta_indexed_items(overlay, path):
        operation_path = f"{path}[{index}]"
        if not isinstance(operation, dict):
            raise ValueError(f"GSE Delta 动作操作必须为映射（位置：{operation_path}）")
        if operation.get("new") is not None:
            block = deepcopy(operation["new"])
        else:
            source_index = operation.get("from", 0)
            if type(source_index) is not int or source_index < 0:
                raise ValueError(f"GSE Delta from 索引无效（位置：{operation_path}.from）")
            block = deepcopy(base_blocks[source_index]) if source_index < len(base_blocks) else {}
            if not isinstance(block, dict):
                raise ValueError(f"GSE Delta 基础动作必须为映射（位置：{operation_path}.from）")
            fields = operation.get("set")
            if fields is not None:
                if not isinstance(fields, dict):
                    raise ValueError(f"GSE Delta set 必须为映射（位置：{operation_path}.set）")
                block.update(deepcopy(fields))
            removed = operation.get("unset")
            if removed is not None:
                if not isinstance(removed, list) or not all(isinstance(field, str) for field in removed):
                    raise ValueError(f"GSE Delta unset 必须为字段名数组（位置：{operation_path}.unset）")
                for field in removed:
                    block.pop(field, None)
            children = operation.get("children")
            if children is not None:
                rows = _delta_action_list(block, children, f"{operation_path}.children")
                for key in tuple(block):
                    if type(key) is int and key >= 1:
                        del block[key]
                block.update({child_index: child for child_index, child in enumerate(rows, 1)})
            for branch_name, branch_index in (("branch1", 1), ("branch2", 2)):
                branch = operation.get(branch_name)
                if branch is not None:
                    existing = block.get(branch_index, block.get(str(branch_index), []))
                    block[branch_index] = _delta_action_list(
                        existing, branch, f"{operation_path}.{branch_name}")
                    block.pop(str(branch_index), None)
        if not isinstance(block, dict):
            raise ValueError(f"GSE Delta new 动作必须为映射（位置：{operation_path}.new）")
        result.append(block)
    return result


def _apply_delta(base, delta):
    """按锁定 GSE 版本的 Delta 结构合并基础序列与改动。"""
    if not isinstance(base, dict) or not isinstance(delta, dict):
        raise ValueError("GSE Delta 基础序列或覆盖项必须为映射")
    result = deepcopy(base)
    version_changes = delta.get("versions")
    if version_changes is not None:
        if not isinstance(version_changes, dict):
            raise ValueError("GSE Delta versions 必须为映射（位置：delta.versions）")
        current_versions = result.get("Versions")
        if current_versions is None:
            current_versions = {}
        elif isinstance(current_versions, list):
            current_versions = dict(enumerate(current_versions, 1))
        elif not isinstance(current_versions, dict):
            raise ValueError("GSE Delta 基础 Versions 必须为映射或数组")
        result["Versions"] = current_versions
        for key, change in version_changes.items():
            version_key = _numeric_key(key)
            if version_key is None:
                version_key = key
            change_path = f"delta.versions[{key}]"
            if not isinstance(change, dict):
                raise ValueError(f"GSE Delta 版本操作必须为映射（位置：{change_path}）")
            if change.get("op") == "remove":
                current_versions.pop(version_key, None)
                continue
            if change.get("op") == "add":
                current_versions[version_key] = deepcopy(change.get("value"))
                continue
            version = deepcopy(current_versions.get(version_key) or {"Actions": []})
            if not isinstance(version, dict):
                raise ValueError(f"GSE Delta 版本必须为映射（位置：{change_path}）")
            if change.get("actions") is not None:
                version["Actions"] = _delta_action_list(
                    version.get("Actions", []), change["actions"], f"{change_path}.actions")
            if change.get("inbuiltVariables") is not None:
                version["InbuiltVariables"] = deepcopy(change["inbuiltVariables"])
            fields = change.get("set")
            if fields is not None:
                if not isinstance(fields, dict):
                    raise ValueError(f"GSE Delta set 必须为映射（位置：{change_path}.set）")
                version.update(deepcopy(fields))
            removed = change.get("unset")
            if removed is not None:
                if not isinstance(removed, list) or not all(isinstance(field, str) for field in removed):
                    raise ValueError(f"GSE Delta unset 必须为字段名数组（位置：{change_path}.unset）")
                for field in removed:
                    version.pop(field, None)
            current_versions[version_key] = version
    top = delta.get("top")
    if top is not None:
        if not isinstance(top, dict):
            raise ValueError("GSE Delta top 必须为映射（位置：delta.top）")
        result.update(deepcopy(top))
    top_unset = delta.get("topUnset")
    if top_unset is not None:
        if not isinstance(top_unset, list) or not all(isinstance(field, str) for field in top_unset):
            raise ValueError("GSE Delta topUnset 必须为字段名数组（位置：delta.topUnset）")
        for field in top_unset:
            result.pop(field, None)
    return result


def _collection_delta_fork(name, fork, path, warnings, *, expected_type="sequence",
                           account_decoded_bytes=None):
    content_type = fork.get("contentType")
    if not content_type:
        content_type = "sequence"
    if content_type != expected_type:
        raise ValueError(f"GSE Delta 内容类型 {content_type!r} 与 {expected_type} 分类不符（位置：{path}.contentType）")
    platform_id = fork.get("platformId")
    if not isinstance(platform_id, str) or not platform_id:
        raise ValueError(f"GSE Delta 缺少 platformId，GSE 不会载入该对象（位置：{path}.platformId）")
    base_text = fork.get("base")
    if not isinstance(base_text, str):
        raise ValueError(f"GSE Delta 缺少编码基础序列（位置：{path}.base）")
    try:
        base_raw, payload, _ = _decode_gse_message(base_text)
    except ValueError as error:
        raise ValueError(f"GSE Delta 基础消息无法读取（位置：{path}.base）：{error}") from error
    if account_decoded_bytes is not None:
        account_decoded_bytes(base_raw, f"{path}.base")
    if expected_type == "sequence" and isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], dict):
        base = payload[1]
    elif isinstance(payload, dict):
        base = payload
    else:
        raise ValueError(f"GSE Delta 基础消息不是可解析的 {expected_type} 对象（位置：{path}.base）")
    delta_text = fork.get("delta")
    delta = None
    if isinstance(delta_text, str) and delta_text:
        try:
            encoded = base64.b64decode(delta_text, validate=True)
        except binascii.Error:
            encoded = None
        if encoded is not None and len(encoded) <= MAX_DECODED:
            if account_decoded_bytes is not None:
                account_decoded_bytes(encoded, f"{path}.delta")
            try:
                stream = io.BytesIO(encoded)
                decoded_delta = _plain(cbor2.CBORDecoder(
                    stream, allow_duplicate_keys=False).decode())
                if not stream.read(1) and isinstance(decoded_delta, dict):
                    delta = decoded_delta
            except (cbor2.CBORDecodeError, ValueError):
                delta = None
    if delta is None:
        warnings.append(f"{path}.delta cannot be decoded; upstream keeps the base sequence")
        effective = deepcopy(base)
    else:
        effective = _apply_delta(base, delta)
    metadata = effective.get("MetaData")
    if metadata is None or metadata is False:
        metadata = {}
        effective["MetaData"] = metadata
    if not isinstance(metadata, dict):
        raise ValueError(f"GSE Delta 基础对象元数据必须为映射（位置：{path}.base.MetaData）")
    metadata["PlatformID"] = platform_id
    stored_name = effective.get("name") or metadata.get("Name")
    if not isinstance(stored_name, str) or not stored_name:
        raise ValueError(f"GSE Delta 基础对象缺少可载入名称（位置：{path}.base.name）")
    if isinstance(name, str) and stored_name != name:
        raise ValueError(f"GSE Delta 对象名与集合键不一致（位置：{path}: {stored_name}）")
    return effective


def _parse_collection_objects(body, category, blockers, warning_map, location_map,
                              source_root="payload", account_decoded_bytes=None):
    raw_objects = body.get(category)
    if raw_objects is None or raw_objects is False:
        return None
    if isinstance(raw_objects, list):
        entries = list(enumerate(raw_objects, 1))
    elif isinstance(raw_objects, dict):
        entries = list(raw_objects.items())
    else:
        raise ValueError(f"GSE 集合 {category} 必须为表格（位置：payload.{category}）")
    parsed = {}
    warning_map[category] = {}
    location_map[category] = {}
    for name, raw_value in entries:
        path = f"{source_root}.{category}[{name}]" if source_root else f"{category}[{name}]"
        location_map[category][str(name)] = path
        valid_name = ((isinstance(name, str)) or
                      (type(name) is int) or
                      (type(name) is float and math.isfinite(name)))
        if not valid_name:
            blockers.append(dict(category=category, name=str(name), source_path=path,
                                 reason=f"GSE 集合对象名称无效（位置：{path}）",
                                 raw_value=raw_value))
            continue
        warnings = []
        try:
            if isinstance(raw_value, dict) and raw_value.get("GSEDeltaFork"):
                value = _collection_delta_fork(name, raw_value, path, warnings,
                                                expected_type=category[:-1].lower(),
                                                account_decoded_bytes=account_decoded_bytes)
            elif isinstance(raw_value, str) and raw_value.startswith("!GSE3!"):
                if raw_value.startswith("!GSE3!+") and not isinstance(name, str):
                    raise ValueError(f"受保护 {category} 的存储键必须是文本名称（位置：{path}）")
                encoded_raw, value, _ = _decode_gse_message(raw_value)
                if account_decoded_bytes is not None:
                    account_decoded_bytes(encoded_raw, path)
                if not isinstance(value, (dict, list)):
                    raise ValueError(f"GSE 编码对象不是 table（位置：{path}）")
            elif isinstance(raw_value, dict):
                value = deepcopy(raw_value)
                if value.get("name") is None or value.get("name") is False:
                    value["name"] = name
            elif isinstance(raw_value, list):
                value = {index: deepcopy(item) for index, item in enumerate(raw_value, 1)}
                value["name"] = name
            else:
                raise ValueError(f"GSE 集合对象必须是表格或 GSE 编码字符串（位置：{path}）")
            value = _fix_container(value, path)
        except _GSEResourceLimit:
            raise
        except ValueError as error:
            blockers.append(dict(category=category, name=name, source_path=path,
                                 reason=str(error), raw_value=raw_value))
            continue
        parsed[name] = value
        if warnings:
            warning_map[category][name] = warnings
    return parsed


def decode_import(text):
    """返回原始 GSE 对象和序列映射；失败不会退化成空序列。"""
    raw, payload, protected = _decode_gse_message(text)

    object_type = payload.get("objectType") if isinstance(payload, dict) else None
    protected_object_type = object_type if protected else None
    if object_type in {"VARIABLE", "MACRO"}:
        object_name = payload.get("name")
        if not isinstance(object_name, str) or not object_name:
            raise ValueError(f"GSE {object_type} 对象缺少 name 字段（位置：name）")
        return dict(payload=payload, sequences={},
                    envelope="protected" if protected else "direct", content_envelope="object",
                    raw_sequences={}, raw_sequence_objects={}, syntax_locations=[], parse_warnings={},
                    collection_objects={}, collection_object_warnings={},
                    collection_object_locations={}, collection_blockers=[],
                    protected_object_type=protected_object_type,
                    object_type=object_type,
                    payload_cbor=raw, raw_import=text,
                    sha256=hashlib.sha256(text.encode("ascii")).hexdigest())
    collection_member_warnings = {}
    collection_wire_values = {}
    collection_blockers = []
    collection_objects = {}
    collection_object_warnings = {}
    collection_object_locations = {}
    collection_sequence_locations = {}
    collection_sequence_trajectories = {}
    collection_blocker_trajectories = {}
    unimportable_sequences = {}
    if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], str):
        sequences = {payload[0]: payload[1]}
        envelope = "single"
    elif isinstance(payload, dict) and payload.get("type") == "COLLECTION":
        body = payload.get("payload") or {}
        if not isinstance(body, dict):
            raise ValueError("GSE 导入集合载荷必须为映射（位置：payload）")
        sequences = {}
        sequence_paths = {}
        sequence_sources = {}
        ambiguous_sequences = set()
        ambiguous_objects = {"Variables": set(), "Macros": set()}
        object_sources = {"Variables": {}, "Macros": {}}
        seen_members = [0]
        decoded_bytes = [len(raw)]

        def public_path(path):
            return path[len("payload."):] if path.startswith("payload.") else path

        def visit_member(path, depth):
            if depth > MAX_DEPTH:
                raise ValueError(f"GSE 集合递归过深（位置：{public_path(path)}）")
            seen_members[0] += 1
            if seen_members[0] > MAX_NODES:
                raise ValueError(f"GSE 集合成员过多（位置：{public_path(path)}）")

        def account_decoded_bytes(decoded_raw, path):
            decoded_bytes[0] += len(decoded_raw)
            if decoded_bytes[0] > MAX_DECODED:
                raise _GSEResourceLimit(
                    f"GSE 集合递归解码数据总量超过限制（位置：{public_path(path)}）")

        def collection_items(value, category, path):
            if value is None or value is False:
                return []
            if category == "Sequences" and not isinstance(value, dict):
                raise ValueError(f"GSE 导入集合序列必须为映射（位置：{public_path(path)}）")
            if isinstance(value, list):
                return list(enumerate(value, 1))
            if isinstance(value, dict):
                return list(value.items())
            raise ValueError(f"GSE 集合 {category} 必须为表格（位置：{public_path(path)}）")

        def mark_sequence_collision(name, path, raw_value):
            sources = sequence_sources.setdefault(name, [])
            current_path = public_path(path)
            if not sources or sources[-1]["source_path"] != current_path:
                sources.append({"source_path": current_path, "raw_value": raw_value})
            source_paths = [source["source_path"] for source in sources]
            previous_path = source_paths[0] if source_paths else current_path
            previous_raw = sources[0]["raw_value"] if sources else raw_value
            collection_blockers.append(dict(
                category="Sequences", name=name, source_path=current_path,
                reason=(f"GSE 集合序列名称有歧义；上游 pairs 遍历顺序不确定，不能选择覆盖结果 "
                        f"（来源：{'、'.join(source_paths)}）"),
                raw_value=raw_value, conflicting_source_path=public_path(previous_path or path),
                conflicting_raw_value=previous_raw, source_paths=source_paths))
            sequences.pop(name, None)
            sequence_paths.pop(name, None)
            collection_sequence_locations.pop(name, None)
            collection_sequence_trajectories.pop(name, None)
            collection_wire_values.pop(name, None)
            collection_member_warnings.pop(name, None)
            ambiguous_sequences.add(name)

        def add_collection_object_value(category, name, value, original_value, path):
            source_path = path
            if not isinstance(name, str) or not name:
                collection_blockers.append(dict(
                    category=category, name=str(name), source_path=source_path,
                    reason=f"GSE {category} 对象缺少有效 name 字段（位置：{source_path}.name）",
                    raw_value=original_value))
                return
            try:
                parsed_value = _fix_container(deepcopy(value), source_path)
            except _GSEResourceLimit:
                raise
            except ValueError as error:
                collection_blockers.append(dict(category=category, name=name,
                                                source_path=public_path(path), reason=str(error),
                                                raw_value=original_value))
                return
            target = collection_objects.setdefault(category, {})
            locations = collection_object_locations.setdefault(category, {})
            warnings = collection_object_warnings.setdefault(category, {})
            source_key = str(name)
            if name in target or name in ambiguous_objects[category]:
                sources = object_sources[category].setdefault(name, [])
                if not sources:
                    sources.append({"source_path": locations.get(source_key, public_path(path)),
                                    "raw_value": target.get(name)})
                current_path = source_path
                if sources[-1]["source_path"] != current_path:
                    sources.append({"source_path": current_path, "raw_value": original_value})
                source_paths = [source["source_path"] for source in sources]
                previous_path = source_paths[0] if source_paths else current_path
                previous_value = sources[0]["raw_value"] if sources else original_value
                collection_blockers.append(dict(
                    category=category, name=name, source_path=current_path,
                    reason=(f"GSE 集合 {category} 对象名称有歧义；上游 pairs 遍历顺序不确定，"
                            f"不能选择覆盖结果（来源：{'、'.join(source_paths)}）"),
                    raw_value=original_value, conflicting_source_path=previous_path,
                    conflicting_raw_value=previous_value, source_paths=source_paths))
                target.pop(name, None)
                locations.pop(source_key, None)
                warnings.pop(source_key, None)
                ambiguous_objects[category].add(name)
                return
            target[name] = parsed_value
            object_sources[category][name] = [{"source_path": source_path,
                                               "raw_value": original_value}]
            locations[source_key] = source_path

        def add_sequence(name, original_value, path, depth, trajectory, *, decoded_message=None,
                         already_counted=False, raw_table_origin=False):
            if not already_counted:
                visit_member(path, depth)
            value = original_value
            member_warnings = []
            encoded = isinstance(value, str) and value.startswith("!GSE3!")
            is_delta_fork = isinstance(value, dict) and bool(value.get("GSEDeltaFork"))
            unimportable_raw_pair = False
            raw_pair_wrapper = False
            sequence_name = name
            if isinstance(value, dict) and value.get("type") == "COLLECTION":
                nested_body = value.get("payload") or {}
                if not isinstance(nested_body, dict):
                    raise ValueError(f"GSE 导入集合载荷必须为映射（位置：{public_path(path)}.payload）")
                visit_collection(nested_body, f"{path}.payload", depth + 1, trajectory)
                return
            if encoded:
                if decoded_message is None:
                    try:
                        encoded_raw, encoded_payload, protected_member = _decode_gse_message(value)
                    except ValueError as error:
                        raise ValueError(f"{error}（位置：{public_path(path)}）") from error
                    account_decoded_bytes(encoded_raw, path)
                else:
                    encoded_raw, encoded_payload, protected_member = decoded_message
                if (not protected_member and isinstance(encoded_payload, dict)
                        and encoded_payload.get("type") == "COLLECTION"):
                    nested_body = encoded_payload.get("payload") or {}
                    if not isinstance(nested_body, dict):
                        raise ValueError(f"GSE 导入集合载荷必须为映射（位置：{public_path(path)}.payload）")
                    visit_collection(nested_body, f"{path}.payload", depth + 1, trajectory)
                    return
                if (not protected_member and isinstance(encoded_payload, dict)
                        and encoded_payload.get("objectType") in {"VARIABLE", "MACRO"}):
                    category = "Variables" if encoded_payload["objectType"] == "VARIABLE" else "Macros"
                    add_collection_object_value(category, encoded_payload.get("name"),
                                                encoded_payload, original_value, path)
                    return
                if (isinstance(encoded_payload, list) and len(encoded_payload) == 2
                        and isinstance(encoded_payload[0], str) and encoded_payload[0]
                        and isinstance(encoded_payload[1], dict)):
                    if not protected_member:
                        sequence_name = encoded_payload[0]
                    value = encoded_payload[1]
                elif (isinstance(encoded_payload, dict)
                      and isinstance(encoded_payload.get("MetaData"), dict)
                      and "Versions" in encoded_payload):
                    value = encoded_payload
                    if not protected_member:
                        sequence_name = encoded_payload["MetaData"].get("Name")
                        if not isinstance(sequence_name, str) or not sequence_name:
                            raise ValueError(
                                f"GSE 集合序列编码对象缺少 MetaData.Name（位置：{public_path(path)}）")
                else:
                    raise ValueError(f"GSE 集合序列编码成员无效（位置：{public_path(path)}）")
            elif isinstance(value, dict) and value.get("objectType") in {"VARIABLE", "MACRO"}:
                category = "Variables" if value["objectType"] == "VARIABLE" else "Macros"
                add_collection_object_value(category, value.get("name"), value,
                                            original_value, path)
                return
            elif isinstance(value, dict) and value.get("GSEDeltaFork"):
                try:
                    value = _collection_delta_fork(
                        name, value, public_path(path), member_warnings,
                        account_decoded_bytes=account_decoded_bytes)
                except _GSEResourceLimit:
                    raise
                except ValueError as error:
                    collection_blockers.append(dict(category="Sequences", name=name,
                                                    source_path=public_path(path),
                                                    reason=str(error), raw_value=original_value))
                    return
            elif isinstance(value, dict):
                metadata = value.get("MetaData")
                if isinstance(metadata, dict) and isinstance(metadata.get("Name"), str) \
                        and metadata["Name"]:
                    sequence_name = metadata["Name"]
                elif raw_table_origin:
                    raise ValueError(
                        f"GSE 原始序列 table 缺少 MetaData.Name（位置：{public_path(path)}.MetaData.Name）")
                if raw_table_origin:
                    gse_version = metadata.get("GSEVersion") if isinstance(metadata, dict) else None
                    if ("Versions" not in value or type(gse_version) not in (int, float)
                            or not math.isfinite(gse_version) or gse_version <= 3200):
                        raise ValueError(
                            f"GSE 原始序列 table 缺少可导入的 Versions 或 GSEVersion "
                            f"（位置：{public_path(path)}）")
            elif isinstance(value, list):
                if (len(value) != 2 or not isinstance(value[0], str) or not value[0]
                        or not isinstance(value[1], dict)):
                    raise ValueError(f"GSE 集合原始序列成员无效（位置：{public_path(path)}）")
                if raw_table_origin:
                    sequence_name = value[0]
                    metadata = value[1].get("MetaData")
                    gse_version = metadata.get("GSEVersion") if isinstance(metadata, dict) else None
                    if ("Versions" not in value[1] or type(gse_version) not in (int, float)
                            or not math.isfinite(gse_version) or gse_version <= 3200):
                        raise ValueError(
                            f"GSE 原始序列 pair 缺少可导入的 Versions 或 GSEVersion "
                            f"（位置：{public_path(path)}）")
                    value = value[1]
                    raw_pair_wrapper = True
                else:
                    value = value[1]
                    unimportable_raw_pair = True
                    reason = ("锁定 GSE 3.3.32 会给原始数组成员注入外层 MetaData.Name，"
                              "再把完整数组作为序列载荷；顶层 MetaData.GSEVersion 缺失，"
                              f"上游会拒绝导入（位置：{public_path(path)}）")
                    collection_blockers.append(dict(category="Sequences", name=sequence_name,
                                                    source_path=public_path(path), reason=reason,
                                                    raw_value=original_value, blocks_import=True))
                    unimportable_sequences[sequence_name] = reason
            if sequence_name in sequences or sequence_name in ambiguous_sequences:
                mark_sequence_collision(sequence_name, path, original_value)
                return
            sequences[sequence_name] = value
            sequence_paths[sequence_name] = public_path(path)
            sequence_sources[sequence_name] = [{"source_path": public_path(path),
                                                "raw_value": original_value}]
            collection_sequence_locations[sequence_name] = public_path(path)
            collection_sequence_trajectories[sequence_name] = trajectory
            if encoded or is_delta_fork or unimportable_raw_pair or raw_pair_wrapper:
                collection_wire_values[sequence_name] = original_value
            if member_warnings:
                collection_member_warnings[sequence_name] = member_warnings

        def add_collection_object(category, name, original_value, path, depth, source_root,
                                  trajectory):
            visit_member(path, depth)
            value = original_value
            if isinstance(value, dict) and value.get("type") == "COLLECTION":
                nested_body = value.get("payload") or {}
                if not isinstance(nested_body, dict):
                    raise ValueError(f"GSE 导入集合载荷必须为映射（位置：{public_path(path)}.payload）")
                visit_collection(nested_body, f"{path}.payload", depth + 1, trajectory)
                return
            if isinstance(value, str) and value.startswith("!GSE3!"):
                try:
                    encoded_raw, encoded_payload, is_protected = _decode_gse_message(value)
                except ValueError as error:
                    collection_blockers.append(dict(category=category, name=name,
                                                    source_path=public_path(path), reason=str(error),
                                                    raw_value=original_value))
                    return
                if (not is_protected and isinstance(encoded_payload, dict)
                        and encoded_payload.get("type") == "COLLECTION"):
                    account_decoded_bytes(encoded_raw, path)
                    nested_body = encoded_payload.get("payload") or {}
                    if not isinstance(nested_body, dict):
                        raise ValueError(f"GSE 导入集合载荷必须为映射（位置：{public_path(path)}.payload）")
                    visit_collection(nested_body, f"{path}.payload", depth + 1, trajectory)
                    return
                if not is_protected:
                    account_decoded_bytes(encoded_raw, path)
                    add_sequence(name, original_value, path, depth,
                                 trajectory,
                                 decoded_message=(encoded_raw, encoded_payload, False),
                                 already_counted=True)
                    return
            if isinstance(value, dict) and value.get("objectType") in {"VARIABLE", "MACRO"}:
                object_name = value.get("name")
                if object_name is None or object_name is False:
                    object_name = name
                actual_category = "Variables" if value["objectType"] == "VARIABLE" else "Macros"
                add_collection_object_value(actual_category, object_name, value,
                                            original_value, path)
                return
            if not (isinstance(value, dict) and value.get("GSEDeltaFork")) \
                    and (isinstance(value, list)
                         or (isinstance(value, dict)
                             and ("MetaData" in value or "Versions" in value))):
                add_sequence(name, original_value, path, depth,
                             trajectory,
                             already_counted=True, raw_table_origin=True)
                return
            if isinstance(value, dict) and not value.get("GSEDeltaFork"):
                reason = (
                    f"锁定 GSE 3.3.32 的集合 {category} 原始 table 缺少 "
                    "objectType=VARIABLE/MACRO，且不是带 MetaData/Versions 的序列或数组 pair；"
                    f"上游 ImportSerialisedSequence 无法识别该对象（位置：{public_path(path)}）")
                blocker = dict(
                    category=category, name=name, source_path=public_path(path),
                    reason=reason, raw_value=original_value, blocks_import=True)
                collection_blockers.append(blocker)
                collection_blocker_trajectories[id(blocker)] = trajectory
                return
            body = {category: {name: original_value}}
            local_blockers = []
            local_warnings = {}
            local_locations = {}
            parsed = _parse_collection_objects(
                body, category, local_blockers, local_warnings,
                local_locations, source_root=source_root,
                account_decoded_bytes=account_decoded_bytes)
            collection_blockers.extend(local_blockers)
            if not parsed:
                return
            target = collection_objects.setdefault(category, {})
            locations = collection_object_locations.setdefault(category, {})
            warnings = collection_object_warnings.setdefault(category, {})
            for parsed_name, parsed_value in parsed.items():
                source_key = str(parsed_name)
                if parsed_name in target or parsed_name in ambiguous_objects[category]:
                    sources = object_sources[category].setdefault(parsed_name, [])
                    if not sources:
                        sources.append({"source_path": locations.get(source_key, public_path(path)),
                                        "raw_value": target.get(parsed_name)})
                    current_path = public_path(path)
                    if sources[-1]["source_path"] != current_path:
                        sources.append({"source_path": current_path, "raw_value": original_value})
                    source_paths = [source["source_path"] for source in sources]
                    previous_path = source_paths[0] if source_paths else current_path
                    previous_value = sources[0]["raw_value"] if sources else original_value
                    collection_blockers.append(dict(
                        category=category, name=parsed_name, source_path=current_path,
                        reason=(f"GSE 集合 {category} 对象名称有歧义；上游 pairs 遍历顺序不确定，"
                                f"不能选择覆盖结果（来源：{'、'.join(source_paths)}）"),
                        raw_value=original_value, conflicting_source_path=previous_path,
                        conflicting_raw_value=previous_value, source_paths=source_paths))
                    target.pop(parsed_name, None)
                    locations.pop(source_key, None)
                    warnings.pop(source_key, None)
                    ambiguous_objects[category].add(parsed_name)
                    continue
                target[parsed_name] = parsed_value
                object_sources[category][parsed_name] = [{"source_path": public_path(path),
                                                           "raw_value": original_value}]
                locations[source_key] = local_locations.get(category, {}).get(source_key, path)
                parsed_warnings = local_warnings.get(category, {}).get(parsed_name)
                if parsed_warnings:
                    warnings[source_key] = parsed_warnings

        def visit_collection(collection_body, source_root, depth, trajectory=()):
            if depth > MAX_DEPTH:
                raise ValueError(f"GSE 集合递归过深（位置：{public_path(source_root)}）")
            if not isinstance(collection_body, dict):
                raise ValueError(f"GSE 导入集合载荷必须为映射（位置：{public_path(source_root)}）")
            for category in ("Variables", "Sequences", "Macros"):
                category_path = f"{source_root}.{category}"
                raw_members = collection_body.get(category)
                if category in {"Variables", "Macros"} and raw_members is not None \
                        and raw_members is not False:
                    collection_objects.setdefault(category, {})
                    collection_object_warnings.setdefault(category, {})
                    collection_object_locations.setdefault(category, {})
                for name, value in collection_items(raw_members, category, category_path):
                    member_path = f"{category_path}[{name}]"
                    member_trajectory = trajectory + ((category, name),)
                    if category == "Sequences":
                        add_sequence(name, value, member_path, depth, member_trajectory)
                    else:
                        add_collection_object(category, name, value, member_path, depth,
                                              source_root, member_trajectory)

        visit_collection(body, "payload", 0)
        blocking_object_members = [
            blocker for blocker in collection_blockers
            if blocker.get("blocks_import") and blocker.get("category") in {"Variables", "Macros"}
        ]
        category_order = {"Variables": 0, "Sequences": 1, "Macros": 2}

        def blocker_precedes_sequence(blocker_trajectory, sequence_trajectory):
            for (blocker_category, blocker_key), (sequence_category, sequence_key) in zip(
                    blocker_trajectory, sequence_trajectory):
                if blocker_category != sequence_category:
                    return (category_order[blocker_category] < category_order[sequence_category],
                            "category")
                if blocker_key != sequence_key:
                    return True, "pairs"
            if len(blocker_trajectory) != len(sequence_trajectory):
                return True, "nested"
            return True, "same_member"

        for blocker in blocking_object_members:
            source_path = blocker["source_path"]
            blocker_trajectory = collection_blocker_trajectories.get(id(blocker), ())
            for sequence_name, sequence_trajectory in collection_sequence_trajectories.items():
                precedes, order_kind = blocker_precedes_sequence(
                    blocker_trajectory, sequence_trajectory)
                if not precedes:
                    continue
                if order_kind == "category":
                    first_shared = next(
                        index for index, (blocker_node, sequence_node) in enumerate(
                            zip(blocker_trajectory, sequence_trajectory))
                        if blocker_node[0] != sequence_node[0])
                    blocker_category = blocker_trajectory[first_shared][0]
                    reason = (f"GSE 集合 {blocker_category} 阶段先于目标序列所属阶段导入；"
                              f"上游无法导入该对象（来源：{source_path}）")
                elif order_kind == "pairs":
                    shared_category = next(
                        category for (category, blocker_key), (sequence_category, sequence_key)
                        in zip(blocker_trajectory, sequence_trajectory)
                        if category == sequence_category and blocker_key != sequence_key)
                    reason = (f"GSE 集合同一层 {shared_category} 的 pairs 遍历顺序不确定；"
                              f"坏对象可能先于目标序列导入，保守阻断（来源：{source_path}）")
                else:
                    reason = ("GSE 集合递归轨迹无法确定坏对象与目标序列的先后，"
                              f"保守阻断模拟预检（来源：{source_path}）")
                existing_reason = unimportable_sequences.get(sequence_name)
                unimportable_sequences[sequence_name] = (
                    f"{existing_reason}；{reason}" if existing_reason else reason)
        envelope = "collection"
    elif (isinstance(payload, dict) and isinstance(payload.get("MetaData"), dict)
          and "Versions" in payload):
        name = payload["MetaData"].get("Name")
        if not isinstance(name, str) or not name:
            raise ValueError("GSE 直接序列缺少 MetaData.Name")
        sequences = {name: payload}
        envelope = "direct"
    else:
        raise ValueError("GSE 导入外壳不受支持")
    if not sequences and envelope != "collection":
        raise ValueError("GSE 导入序列结构无效（位置：Sequences）")
    raw_sequences = {}
    raw_sequence_objects = {}
    normalized_sequences = {}
    for name, sequence in sequences.items():
        if not isinstance(name, str) or not name or not isinstance(sequence, dict):
            raise ValueError(f"GSE 导入序列结构无效（位置：Sequences[{name}]）")
        sequence_path = collection_sequence_locations.get(name, f"Sequences[{name}]")
        raw_sequence = collection_wire_values.get(name, sequence)
        source_sequence = sequence
        source_metadata = sequence.get("MetaData")
        if envelope == "collection" and (source_metadata is None or source_metadata is False):
            sequence = dict(sequence)
            source_metadata = {}
        if envelope == "collection" and isinstance(source_metadata, dict) and not source_metadata.get("Name"):
            sequence = dict(sequence)
            source_metadata = dict(source_metadata)
            source_metadata["Name"] = name
        if envelope == "collection" and ("MetaData" not in sequence or sequence.get("MetaData") is None
                                           or sequence.get("MetaData") is False
                                           or isinstance(sequence.get("MetaData"), dict)):
            sequence["MetaData"] = source_metadata
        if not isinstance(sequence.get("MetaData"), dict):
            raise ValueError(f"GSE 导入序列缺少元数据（位置：{sequence_path}.MetaData）")
        normalized = _fix_container(sequence, sequence_path)
        versions = _sequence_versions(normalized.get("Versions"), name, sequence_path)
        raw_sequences[name] = raw_sequence
        raw_sequence_objects[name] = source_sequence
        normalized["Versions"] = versions
        normalized_sequences[name] = normalized
    syntax_locations = _parse_sequences(normalized_sequences, collection_sequence_locations)
    warnings = {name: _sequence_warnings(sequence, name,
                                         collection_sequence_locations.get(name))
                + collection_member_warnings.get(name, [])
                for name, sequence in normalized_sequences.items()}
    content_envelope = envelope
    if protected:
        envelope = "protected"
    return dict(payload=payload, sequences=normalized_sequences, envelope=envelope,
                content_envelope=content_envelope,
                protected_object_type=protected_object_type,
                object_type=object_type,
                raw_sequences=raw_sequences, raw_sequence_objects=raw_sequence_objects,
                sequence_source_paths=collection_sequence_locations,
                unimportable_sequences=unimportable_sequences,
                collection_blockers=collection_blockers,
                collection_objects=collection_objects,
                collection_object_warnings=collection_object_warnings,
                collection_object_locations=collection_object_locations,
                syntax_locations=syntax_locations, parse_warnings=warnings,
                payload_cbor=raw, raw_import=text,
                sha256=hashlib.sha256(text.encode("ascii")).hexdigest())


def _json_value(value):
    """以 JSON 可传输形式展示已解码值；CBOR 原字节另由 payload_cbor 保存。"""
    if isinstance(value, _RawCBORBytes):
        return {"$cbor_bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(_json_value(key)): _json_value(item) for key, item in value.items()}
    return value


def _position(sequence, version, path):
    return SourcePosition(adapter="gse_import", sequence=sequence, version=version, path=str(path))


def _gse_action_type(action):
    kind = action.get("type")
    if kind == "spell" and action.get("spell") in (None, ""):
        return "macro"
    if kind not in (None, ""):
        return kind
    for key, inferred in (("macro", "macro"), ("macrotext", "macro"), ("item", "item"),
                          ("action", "pet"), ("toy", "toy"), ("spell", "spell")):
        if action.get(key) not in (None, ""):
            return inferred
    return "macro"


def _action_node(action, source):
    if not isinstance(action, dict):
        command = dict(type="raw", argument=str(action))
    else:
        command_type = _gse_action_type(action)
        if command_type == "spell":
            command = dict(type="spell", argument=action.get("spell"))
        elif command_type == "item":
            command = dict(type="item", argument=action.get("item"))
        elif command_type == "macro":
            command = dict(type="macro", text=action.get("macro", action.get("macrotext", "")))
        elif command_type == "pet":
            command = dict(type="pet", argument=action.get("action"))
        elif command_type == "toy":
            command = dict(type="toy", argument=action.get("toy"))
        else:
            command = dict(type=command_type, raw=_json_value(action))
    return ActionNode(kind="Action", commands=[command], source=source, raw=_json_value(action))


def _gse_nodes(actions, sequences, sequence_name, version, selected_versions, seen, path_prefix="",
               state=None, depth=0, context=None):
    if state is None:
        state = [0]
    if depth > MAX_DEPTH:
        raise ValueError("GSE 程序展开过深或节点过多")
    entries = _indexed_items(actions)
    if entries is None:
        return []
    nodes = []
    for index, action in entries:
        state[0] += 1
        if state[0] > MAX_NODES:
            raise ValueError("GSE 程序展开过深或节点过多")
        path = f"{path_prefix}.{index}" if path_prefix else str(index)
        if action.get("Disabled") is True:
            continue
        kind = action.get("Type")
        source = _position(sequence_name, version, path)
        if kind == "Action":
            nodes.append(_action_node(action, source))
        elif kind == "Repeat":
            child_source = source
            repeat = action.get("Interval")
            if repeat is None or repeat == "":
                repeat = action.get("Repeat", 2)
            if repeat is None or repeat == "":
                repeat = 2
            try:
                repeat = int(float(repeat))
            except (TypeError, ValueError):
                repeat = 2
            nodes.append(RepeatNode(kind="Repeat", interval=repeat,
                                    action=_action_node(action, child_source), source=source,
                                    raw=_json_value(action)))
        elif kind == "Loop":
            try:
                count = int(float(action.get("Repeat", 1)))
            except (TypeError, ValueError):
                count = 1
            body = _gse_nodes(action, sequences, sequence_name, version, selected_versions, seen,
                              path_prefix=path, state=state, depth=depth + 1, context=context)
            nodes.append(LoopNode(kind="Loop", count=count,
                                  step_function=action.get("StepFunction") or "Sequential",
                                  body=body, source=source, raw=_json_value(action)))
        elif kind == "Pause":
            duration_ms = action.get("MS")
            clicks = action.get("Clicks", 0)
            if duration_ms in (None, ""):
                wait_clicks = (int(clicks) if type(clicks) in (int, float)
                               and math.isfinite(clicks) and clicks > 1 else 0)
            elif isinstance(duration_ms, str) and duration_ms in {"GCD", "~~GCD~~"}:
                click_ms = (context or {}).get("click_ms")
                gcd_ms = (context or {}).get("gcd_ms")
                if type(click_ms) is not int or click_ms <= 0 or type(gcd_ms) is not int:
                    raise ValueError("GSE GCD 暂停转换缺少有效的点击间隔或公共冷却")
                gcd_clicks = gcd_ms / click_ms
                wait_clicks = math.floor(gcd_clicks) if gcd_clicks > 1 else 0
            else:
                click_ms = (context or {}).get("click_ms")
                if type(click_ms) is not int or click_ms <= 0:
                    raise ValueError("GSE 毫秒暂停转换缺少有效的点击间隔")
                milliseconds_clicks = math.ceil(1000 / click_ms)
                wait_clicks = milliseconds_clicks if milliseconds_clicks > 1 else 0
            nodes.append(WaitClicksNode(kind="WaitClicks", clicks=wait_clicks, source=source))
        elif kind == "If":
            expression = action.get("Variable")
            condition = isinstance(expression, str) and expression.lstrip("=").strip().lower() == "true"
            yes_actions = action.get(1, action.get("1", []))
            no_actions = action.get(2, action.get("2", []))
            yes = _gse_nodes(yes_actions, sequences, sequence_name, version,
                             selected_versions, seen, path_prefix=path + ".1",
                             state=state, depth=depth + 1, context=context)
            no = _gse_nodes(no_actions, sequences, sequence_name, version,
                            selected_versions, seen, path_prefix=path + ".2",
                            state=state, depth=depth + 1, context=context)
            node = IfNode(kind="If", condition=condition, then=yes, else_branch=no,
                          source=source, raw=_json_value(action))
            if "Variable" in action:
                node["expression"] = _json_value(expression)
            nodes.append(node)
        elif kind == "Embed":
            embedded_name = action.get("Sequence")
            embedded = sequences.get(embedded_name)
            embedded_version = selected_versions.get(embedded_name) if isinstance(embedded_name, str) else None
            if embedded_version is None and isinstance(embedded, dict):
                embedded_version = embedded.get("Default", 1)
            if type(embedded_version) is not int:
                embedded_version = 1
            body = []
            if (isinstance(embedded_name, str) and isinstance(embedded, dict)
                    and embedded_name not in seen and
                    isinstance(_version_get(embedded, embedded_version), dict)):
                body = _gse_nodes(_version_get(embedded, embedded_version).get("Actions", []),
                                  sequences, embedded_name, embedded_version,
                                  selected_versions, seen | {embedded_name},
                                  state=state, depth=depth + 1, context=context)
            nodes.append(EmbedNode(kind="Embed", sequence=str(embedded_name or ""),
                                   version=embedded_version, body=body, source=source,
                                   raw=_json_value(action)))
        else:
            raise ValueError(f"GSE 控制块类型无法展开：{kind}（位置：{sequence_name} v{version} {path}.Type）")
    return nodes


def program_from_import(text, name, version, *, context=None, decoded=None):
    """把已解码的 GSE 结构适配为共享 Program 树。"""
    decoded = decoded or decode_import(text)
    if name not in decoded["sequences"] or type(version) is not int:
        raise ValueError("GSE 选定的序列或版本无效")
    sequence = decoded["sequences"][name]
    version_value = _version_get(sequence, version)
    if not isinstance(version_value, dict):
        raise ValueError("GSE 选定的序列或版本无效")
    requested = (context or {}).get("versions", {})
    requested = requested if isinstance(requested, dict) else {}
    selected_versions = {key: value.get("Default", 1) for key, value in decoded["sequences"].items()}
    selected_versions.update(requested)
    selected_versions[name] = version
    nodes = _gse_nodes(version_value.get("Actions", []),
                       decoded["sequences"], name, version, selected_versions, {name},
                       context=context)
    return Program(adapter="gse_import", nodes=nodes,
                   metadata={"input_text": text, "name": name, "version": version,
                             "sha256": decoded["sha256"],
                             "raw_sequence": _json_value(decoded["raw_sequences"][name]),
                             "raw_version": _json_value(_version_get(
                                 decoded["raw_sequence_objects"][name], version))})


def import_action_spell_ids(program):
    """收集本次导入实际引用的法术编号，供固定 SimC 核对角色动作工厂。"""
    spell_ids = set()

    def add_numeric(value):
        if type(value) is int and value > 0:
            spell_ids.add(value)
        elif isinstance(value, str) and value.isdecimal() and int(value) > 0:
            spell_ids.add(int(value))

    def visit(nodes):
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("kind") == "Action":
                for command in node.get("commands", []):
                    if not isinstance(command, dict):
                        continue
                    if command.get("type") == "spell":
                        add_numeric(command.get("argument"))
                    elif command.get("type") == "macro":
                        spell_ids.update(macro_spell_ids(command.get("text", "")))
            visit(node.get("body"))
            visit(node.get("then"))
            visit(node.get("else_branch"))
            action = node.get("action")
            if isinstance(action, dict):
                visit([action])

    visit(program.get("nodes", []))
    if len(spell_ids) > 256:
        raise ValueError("GSE 导入包含超过 256 个不同法术编号")
    return sorted(spell_ids)


def import_action_spell_names(program):
    """收集按名称写出的法术，交由固定 SimC 逐字查询角色动作工厂。"""
    names = {}

    def add_name(value):
        if not isinstance(value, str):
            return
        name = value.strip()
        if (not name or name.isdecimal() or len(name) > 128
                or any(ord(character) < 32 or ord(character) == 127 for character in name)):
            return
        names.setdefault(name.casefold(), name)

    def visit(nodes):
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("kind") == "Action":
                for command in node.get("commands", []):
                    if not isinstance(command, dict):
                        continue
                    if command.get("type") == "spell":
                        add_name(command.get("argument"))
                    elif command.get("type") == "macro":
                        for name in macro_spell_names(command.get("text", "")):
                            add_name(name)
            visit(node.get("body"))
            visit(node.get("then"))
            visit(node.get("else_branch"))
            action = node.get("action")
            if isinstance(action, dict):
                visit([action])

    visit(program.get("nodes", []))
    if len(names) > 256:
        raise ValueError("GSE 导入包含超过 256 个不同法术名称")
    return sorted(names.values(), key=str.casefold)


def _compiled_source_map(nodes):
    by_path = {}

    def add(source):
        identity = (source["sequence"], source["version"], source["path"])
        if identity in by_path and by_path[identity] != source:
            raise ValueError("GSE Program 含有重复来源身份")
        by_path[identity] = source

    def visit(items):
        for node in items:
            if node["kind"] in {"Action", "WaitClicks"}:
                add(node["source"])
            elif node["kind"] == "Repeat":
                # GSE emits the repeated action, whose source is the Repeat block's location.
                add(node["action"]["source"])
            visit(node.get("body", []))
            visit(node.get("then", []))
            visit(node.get("else_branch", []))

    visit(nodes)
    return by_path


def _contains_random_loop(nodes):
    for node in nodes:
        if node.get("kind") == "Loop" and node.get("step_function") == "Random":
            return True
        for field in ("body", "then", "else_branch"):
            if _contains_random_loop(node.get(field, [])):
                return True
        if node.get("action") and _contains_random_loop([node["action"]]):
            return True
    return False


def inspect_import(text, *, decoded=None):
    decoded = decoded or decode_import(text)
    locked_version = _locked_gse_version()
    syntax_locations = decoded["syntax_locations"]
    syntax = sorted({location["type"] for location in syntax_locations})
    entries = []
    for name, seq in decoded["sequences"].items():
        version_items = _version_items(seq["Versions"], f"Sequences[{name}].Versions")
        indexes = [version for version, _ in version_items]
        version_support = [
            _version_preflight(decoded["sequences"], name, seq, version, locked_version)
            for version in indexes
        ]
        import_block_reason = decoded.get("unimportable_sequences", {}).get(name)
        if import_block_reason:
            version_support = [dict(item, simulation_supported=False,
                                    simulation_preflight_passed=False,
                                    support_status="unsupported",
                                    support_reason=import_block_reason)
                               for item in version_support]
        raw_default_version = seq.get("Default", 1)
        default_version = (raw_default_version if type(raw_default_version) is int and
                           raw_default_version in indexes else indexes[0])
        default_support = next(item for item in version_support
                               if item["version"] == default_version)
        raw_sequence = decoded["raw_sequences"][name]
        sequence_source_path = decoded.get("sequence_source_paths", {}).get(
            name, f"Sequences[{name}]")
        versions = [dict(version=version,
                         source_path=f"{sequence_source_path}.Versions[{version}]",
                         raw_version=_json_value(_version_get(
                             decoded["raw_sequence_objects"][name], version)),
                         parsed_version=_json_value(record))
                    for version, record in version_items]
        entries.append(dict(name=name, spec_id=seq["MetaData"].get("SpecID"),
                            gse_version=seq["MetaData"].get("GSEVersion"),
                            version_count=len(version_items), default_version=default_version,
                            raw_default_version=_json_value(raw_default_version),
                            raw_sequence=_json_value(raw_sequence), versions=versions,
                            parse_warnings=decoded["parse_warnings"][name],
                            version_support=version_support,
                            simulation_supported=default_support["simulation_supported"],
                            simulation_preflight_passed=default_support["simulation_preflight_passed"],
                            support_status=default_support["support_status"],
                            support_reason=default_support["support_reason"]))
    content_envelope = decoded.get("content_envelope", decoded["envelope"])
    collection_body = (decoded["payload"].get("payload") or {}
                       if content_envelope == "collection" else {})
    object_type = decoded.get("object_type", decoded.get("protected_object_type"))
    standalone_object = (_json_value(decoded["payload"])
                         if object_type in {"VARIABLE", "MACRO"} else None)
    protected_object = (standalone_object
                        if decoded.get("protected_object_type") in {"VARIABLE", "MACRO"} else None)
    raw_variables = (_json_value(collection_body.get("Variables"))
                     if content_envelope == "collection" else None)
    raw_macros = (_json_value(collection_body.get("Macros"))
                  if content_envelope == "collection" else None)
    variables = (_json_value(decoded.get("collection_objects", {}).get("Variables"))
                 if content_envelope == "collection" else None)
    macros = (_json_value(decoded.get("collection_objects", {}).get("Macros"))
              if content_envelope == "collection" else None)
    if object_type == "VARIABLE":
        variables = {decoded["payload"]["name"]: standalone_object}
    elif object_type == "MACRO":
        macros = {decoded["payload"]["name"]: standalone_object}
    return dict(status="decoded", format=decoded["envelope"], sha256=decoded["sha256"],
                raw_import=decoded["raw_import"], raw_payload=_json_value(decoded["payload"]),
                payload_cbor_base64=base64.b64encode(decoded["payload_cbor"]).decode("ascii"),
                sequences=entries,
                content_format=content_envelope,
                protected_object_type=decoded.get("protected_object_type"),
                object_type=object_type,
                protected_object=protected_object,
                raw_variables=raw_variables, raw_macros=raw_macros,
                variables=variables, macros=macros,
                collection_parse_warnings=decoded.get("collection_object_warnings", {}),
                collection_object_locations=decoded.get("collection_object_locations", {}),
                collection_compatibility_blocks=[
                    dict(block,
                         raw_value=_json_value(block["raw_value"]),
                         **({"conflicting_raw_value": _json_value(block["conflicting_raw_value"])}
                            if "conflicting_raw_value" in block else {}))
                    for block in decoded.get("collection_blockers", [])
                ],
                syntax=syntax, syntax_locations=syntax_locations, simulation_started=False,
                support="not_checked")


def _check_nodes(value, sequences, seen, path="", selected_versions=None):
    def fail(message):
        raise ValueError(f"{message}（位置：{path or 'Version'}）")

    if isinstance(value, dict):
        if value.get("Disabled") is True:
            return
        kind = value.get("Type")
        if path.endswith(".Actions"):
            _check_runtime_action_indexes(value, path)
        if kind is not None:
            if not isinstance(kind, str) or kind not in VALID_TYPES:
                fail(f"GSE 控制块类型不支持：{kind}")
            if kind in {"Action", "Repeat"}:
                action_kind = _gse_action_type(value)
                if action_kind not in {"spell", "item", "macro"}:
                    fail(f"GSE 动作类型无法模拟：{action_kind}")
                if action_kind == "macro":
                    preflight_macro(value.get("macro", value.get("macrotext", "")),
                                    f"{path}.macro" if path else "macro")
            if kind == "If":
                for branch_index in (1, 2):
                    branch = value.get(branch_index, value.get(str(branch_index)))
                    if branch is not None:
                        _check_runtime_action_indexes(branch, f"{path}[{branch_index}]")
                expression = value.get("Variable")
                constant = expression[1:].strip() if isinstance(expression, str) and expression.startswith("=") else expression
                if not isinstance(constant, str) or constant not in {"true", "false"}:
                    fail("GSE If 条件需要游戏内变量，不能确定分支")
            if kind == "Loop":
                _check_runtime_action_indexes(value, path)
                try:
                    repeats = float(value.get("Repeat", 1))
                except (TypeError, ValueError) as error:
                    raise ValueError(f"GSE Loop 次数无效（位置：{path or 'Version'}）") from error
                if not math.isfinite(repeats) or not 1 <= repeats <= 128 or repeats % 1:
                    fail("GSE Loop 次数必须为 1 至 128 的整数")
                step_function = value.get("StepFunction", "Sequential") or "Sequential"
                if (not isinstance(step_function, str) or
                        step_function not in {"Sequential", "Priority", "ReversePriority", "Random"}):
                    fail(f"GSE Loop 次序方式不支持：{step_function}")
            if kind == "Repeat":
                interval_value = value.get("Interval")
                if interval_value is None or interval_value == "":
                    interval_value = value.get("Repeat", 2)
                if interval_value is None or interval_value == "":
                    interval_value = 2
                try:
                    interval = float(interval_value)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"GSE Repeat 间隔无效（位置：{path or 'Version'}）") from error
                if not math.isfinite(interval) or not 1 <= interval <= 4096 or interval % 1:
                    fail("GSE Repeat 间隔必须为 1 至 4096 的整数")
            if kind == "Pause":
                clicks = value.get("Clicks", 0)
                ms = value.get("MS")
                if (type(clicks) not in (int, float) or not math.isfinite(clicks) or
                        clicks < 0 or clicks > 4096 or clicks % 1):
                    fail("GSE Pause 点击数无效")
                if ms not in (None, "") and not (isinstance(ms, str) and ms in {"GCD", "~~GCD~~"}):
                    try:
                        duration = float(ms)
                    except (TypeError, ValueError) as error:
                        raise ValueError(f"GSE Pause 时长无效（位置：{path or 'Version'}）") from error
                    if not math.isfinite(duration) or not 0 <= duration <= 60000:
                        fail("GSE Pause 时长无效")
            if kind == "Embed":
                dep = value.get("Sequence")
                if not isinstance(dep, str) or dep not in sequences:
                    fail(f"GSE Embed 引用缺失：{dep}")
                if dep in seen:
                    fail(f"GSE Embed 循环引用：{dep}")
                embedded = sequences[dep]
                embedded_version = (selected_versions or {}).get(dep, embedded.get("Default", 1))
                embedded_record = _version_get(embedded, embedded_version)
                if not isinstance(embedded_record, dict):
                    fail(f"GSE Embed 选中版本无效：{dep} {embedded_version}")
                runtime_issue = _version_runtime_issue(embedded, embedded_version)
                if runtime_issue:
                    fail(f"GSE Embed 子序列 {dep}：{runtime_issue}")
                supported, reason = _simulation_compatibility(
                    embedded["MetaData"].get("GSEVersion"), _locked_gse_version())
                if not supported:
                    fail(f"GSE Embed 子序列 {dep}：{reason}")
                _check_nodes(embedded_record, sequences, seen | {dep},
                             f"{path}.Embed[{dep}].Versions[{embedded_version}]" if path
                             else f"Embed[{dep}].Versions[{embedded_version}]", selected_versions)
        for key, item in value.items():
            if isinstance(item, str) and item.startswith("="):
                if (kind == "If" and key == "Variable"
                        and item[1:].strip() in {"true", "false"}):
                    continue
                fail("GSE 公式需要执行外部 Lua，不能安全模拟")
            child_path = f"{path}[{key}]" if type(key) is int else (f"{path}.{key}" if path else str(key))
            if key == "Actions":
                _check_runtime_action_indexes(item, child_path)
            _check_nodes(item, sequences, seen, child_path, selected_versions)
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            _check_nodes(item, sequences, seen, f"{path}[{index}]", selected_versions)


def _version_preflight(sequences, sequence_name, sequence, version, locked_version):
    """只报告静态预检；角色技能/物品映射尚未核验时不宣称已受支持。"""
    version_record = _version_get(sequence, version)
    if not isinstance(version_record, dict):
        return dict(version=version, simulation_supported=False,
                    simulation_preflight_passed=False, support_status="unsupported",
                    support_reason=f"所选版本不存在（位置：Sequences[{sequence_name}].Versions[{version}]）")
    runtime_issue = _version_runtime_issue(sequence, version)
    if runtime_issue:
        return dict(version=version, simulation_supported=False,
                    simulation_preflight_passed=False, support_status="unsupported",
                    support_reason=f"GSE {runtime_issue}（位置：Sequences[{sequence_name}].Versions[{version}]）")
    gse_version = sequence["MetaData"].get("GSEVersion")
    supported, reason = _simulation_compatibility(gse_version, locked_version)
    if not supported:
        return dict(version=version, simulation_supported=False,
                    simulation_preflight_passed=False, support_status="unsupported",
                    support_reason=reason)
    if "Actions" not in version_record:
        actions_path = f"Sequences[{sequence_name}].Versions[{version}].Actions"
        return dict(version=version, simulation_supported=False,
                    simulation_preflight_passed=False, support_status="unsupported",
                    support_reason=f"GSE 版本缺少 Actions 数组（位置：{actions_path}）")

    selected_versions = {name: value.get("Default", 1) for name, value in sequences.items()}
    selected_versions[sequence_name] = version
    try:
        _check_nodes(version_record.get("Actions", []), sequences,
                     {sequence_name},
                     path=f"Sequences[{sequence_name}].Versions[{version}].Actions",
                     selected_versions=selected_versions)
    except ValueError as error:
        return dict(version=version, simulation_supported=False,
                    simulation_preflight_passed=False, support_status="unsupported",
                    support_reason=str(error))

    return dict(version=version, simulation_supported=None,
                simulation_preflight_passed=True,
                support_status="requires_character_validation",
                support_reason=("语法和版本预检通过；当前角色的法术与物品映射尚未核对，"
                                "启动时会继续严格核验，未能映射时不会返回 DPS。"))


def _bounded_append(target, values):
    if len(target) + len(values) > 4096:
        raise ValueError("GSE 展开计划超过 4096 次按键")
    target.extend(values)


def _process_repeat_nodes(nodes):
    """按锁定 GSE 的 processRepeats 规则计数，避免先生成超大计划。"""
    inserts = []
    actions = []
    for index, item in enumerate(nodes, 1):
        if isinstance(item, tuple) and item[0] == "repeat":
            inserts.append((index, item[1] + 1, item[2]))
        else:
            actions.append(item)
    for start, interval, action in inserts:
        insert_count = math.ceil((len(actions) - start) / interval)
        insert_count = math.ceil((len(actions) + insert_count - start) / interval)
        insert_count = max(0, insert_count)
        if len(actions) + 1 + insert_count > 4096:
            raise ValueError("GSE 展开计划超过 4096 次按键")
        if start <= len(actions) + 1:
            actions.insert(start - 1, action)
        for index in range(1, insert_count + 1):
            position = start + index * interval
            if position <= len(actions) + 1:
                actions.insert(position - 1, action)
    return actions


def _compiled_source_plan(nodes):
    """按固定 GSE 展开控制块，保留每次按键的来源身份并限制计划大小。"""

    def expand(items, depth=0):
        if depth > MAX_DEPTH:
            raise ValueError("GSE 程序展开过深或节点过多")
        output = []
        for node in items:
            kind = node["kind"]
            if kind in {"Action", "EmptyClick"}:
                _bounded_append(output, [node["source"]])
            elif kind == "Repeat":
                _bounded_append(output, [("repeat", node["interval"], node["action"]["source"])])
            elif kind == "WaitClicks":
                _bounded_append(output, [node["source"]] * node["clicks"])
            elif kind == "Loop":
                body = expand(node["body"], depth + 1)
                step_function = node["step_function"]
                count = node["count"]
                if step_function in {"Priority", "ReversePriority"}:
                    base_count = len(body)
                    repeated_size = count * base_count * (base_count + 1) // 2
                    if repeated_size > 4096:
                        raise ValueError("GSE 展开计划超过 4096 次按键")
                    repeated = []
                    for _ in range(count):
                        step, limit = 1, 1
                        for _ in range(base_count * (base_count + 1) // 2):
                            repeated.append(body[step - 1])
                            if step_function == "Priority":
                                if step == limit:
                                    limit = limit % base_count + 1
                                    step = 1
                                else:
                                    step += 1
                            else:
                                if step == 1:
                                    limit = limit % base_count + 1
                                    step = limit
                                else:
                                    step -= 1
                elif step_function == "Random":
                    # GSE removes each selected action from the local list; after the first
                    # pass further Repeat iterations therefore emit no additional actions.
                    repeated = [item for item in body if not (isinstance(item, tuple)
                                                               and item[0] == "repeat")]
                    repeat_tokens = [item for item in body if isinstance(item, tuple)
                                     and item[0] == "repeat"]
                    repeated = repeat_tokens + repeated
                else:
                    repeated_size = len(body) * count
                    if repeated_size > 4096:
                        raise ValueError("GSE 展开计划超过 4096 次按键")
                    repeated = body * count
                _bounded_append(output, _process_repeat_nodes(repeated))
            elif kind == "If":
                branch = node["then"] if node["condition"] else node["else_branch"]
                _bounded_append(output, expand(branch, depth + 1))
            elif kind == "Embed":
                _bounded_append(output, _process_repeat_nodes(expand(node["body"], depth + 1)))
            else:
                raise ValueError(f"GSE 程序节点不能展开：{kind}")
        return output

    return _process_repeat_nodes(expand(nodes))


def _map_step(step, actions, path, *, pet_ready=True, enemy_target_ready=False):
    kind = step["type"]
    if kind == "click":
        return []
    if kind == "macro":
        return map_macro(step["macrotext"], path,
                         dict(pet_ready=pet_ready,
                              enemy_target_ready=enemy_target_ready), actions)
    if kind in {"spell", "item"}:
        return map_action(kind, step["argument"], actions, path)
    raise ValueError(f"GSE {path} 的步骤类型不能模拟：{kind}")


def compile_import(program, folder, *, identity, runtime=None, capabilities=None, context=None):
    """固定上游展开全部控制块；仅将可表达的步骤交给原生伤害引擎。"""
    runtime = runtime or TaskRuntime()
    runtime.check()
    metadata = program.get("metadata", {})
    text = metadata.get("input_text")
    name, version = metadata.get("name"), metadata.get("version")
    decoded = decode_import(text)
    if name not in decoded["sequences"] or type(version) is not int:
        raise ValueError("GSE 选定的序列或版本无效")
    sequence = decoded["sequences"][name]
    version_record = _version_get(sequence, version)
    if not isinstance(version_record, dict):
        raise ValueError("GSE 选定的序列或版本无效")
    expected_nodes = program_from_import(text, name, version, context=context, decoded=decoded)["nodes"]
    if program.get("adapter") != "gse_import" or program.get("nodes") != expected_nodes:
        raise ValueError("GSE Program 与原始导入结构不一致")
    context = dict(context or {})
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    gse_version = sequence["MetaData"].get("GSEVersion")
    supported, reason = _simulation_compatibility(gse_version, lock["gse_version"])
    if not supported:
        raise ValueError(reason)
    if sequence["MetaData"].get("SpecID") != identity["spec_id"]:
        raise ValueError("GSE 导入序列与当前角色专精不符")
    requested_versions = context.get("versions", {})
    if not isinstance(requested_versions, dict):
        raise ValueError("GSE 子序列版本选择无效")
    selected_versions = {key: value.get("Default", 1)
                         for key, value in decoded["sequences"].items()}
    selected_versions.update(requested_versions)
    selected_versions[name] = version
    _check_nodes(version_record.get("Actions", []),
                 decoded["sequences"], {name},
                 path=f"Sequences[{name}].Versions[{version}].Actions",
                 selected_versions=selected_versions)
    if (type(context.get("click_ms")) is not int or not 50 <= context["click_ms"] <= 2000
            or type(context.get("gcd_ms")) is not int or not 500 <= context["gcd_ms"] <= 3000
            or type(context.get("seed")) is not int):
        raise ValueError("GSE 编译条件缺少有效的点击间隔、公共冷却或随机种子")
    if (type(context.get("input_interval_ms")) is not int
            or not 50 <= context["input_interval_ms"] <= 2000
            or context["click_ms"] != context["input_interval_ms"]):
        raise ValueError("GSE 点击间隔必须与模拟按键间隔一致")
    source_plan = _compiled_source_plan(program["nodes"])
    has_random_loop = _contains_random_loop(program["nodes"])
    pet_ready = context.get("pet_ready", True)
    if type(pet_ready) is not bool:
        raise ValueError("宠物就绪场景必须是布尔值")
    context["pet_ready"] = pet_ready
    enemy_target_ready = context.get("enemy_target_ready", True)
    if type(enemy_target_ready) is not bool:
        raise ValueError("敌方目标场景必须是布尔值")
    context["enemy_target_ready"] = enemy_target_ready
    capability_data = capabilities or {}
    # GSE imports can name actions outside the baseline's executed subset.
    # The task supplies the separately verified import action inventory when available.
    import_actions = capability_data.get("import_actions", capability_data.get("actions", []))
    actions = [variant for action in import_actions
               for variant in action.get("variants", [action])]
    spells = {action["spell_id"]: action["name"] for action in actions
              if action.get("kind") == "spell"}
    normalized = decoded["payload"]
    if decoded["envelope"] == "collection":
        normalized = dict(normalized, payload=dict(normalized["payload"], Sequences=decoded["sequences"]))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    # The existing export lock also pins the exact upstream Lua sources.
    for relative, expected in lock["gse_sources"].items():
        actual = hashlib.sha256((SOURCE / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            raise ValueError("固定上游 GSE 编译器源码已变化")
    staging_root = ROOT / ".local/sim2gse/codec"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="import-", dir=staging_root) as temporary:
        staging = Path(temporary)
        (staging / "input.cbor").write_bytes(cbor2.dumps(wire_value(normalized)))
        lua_context = dict(name=name, version=version, identity=identity, spells=spells,
                           gse_version=lock["gse_version"],
                           gse_version_string=_gse_version_label(lock["gse_version"]),
                           click_ms=context["click_ms"], gcd_ms=context["gcd_ms"],
                           seed=context["seed"], versions=selected_versions)
        (staging / "context.lua").write_text("return " + lua_literal(lua_context), encoding="utf-8")
        relative = lambda path: path.relative_to(ROOT).as_posix()
        try:
            proc = run_command([str(LUA), relative(Path(__file__).with_name("gse_import.lua")),
                                relative(SOURCE), relative(staging / "input.cbor"),
                                relative(staging / "context.lua")], ROOT, timeout_seconds=20,
                               runtime=runtime, output_dir=folder)
        except ProcessTimeout as error:
            raise ValueError("GSE 上游编译超时，序列可能过大") from error
    log = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    (folder / "compile.log").write_text(log, encoding="utf-8")
    if proc.returncode:
        raise ValueError("GSE 上游编译失败，参见 " + str(folder / "compile.log"))
    steps = []
    for line in log.splitlines():
        if line.startswith("STEP\t"):
            fields = line.split("\t")
            if len(fields) != 8 or int(fields[1]) != len(steps) + 1:
                raise ValueError(f"GSE 上游编译步骤格式无效（字段数：{len(fields)}）")
            steps.append(dict(type=fields[2], argument=fields[3],
                              macrotext=bytes.fromhex(fields[4]).decode("utf-8"),
                              source_path=bytes.fromhex(fields[5]).decode("utf-8"),
                              source_sequence=bytes.fromhex(fields[6]).decode("utf-8"),
                              source_version=int(fields[7])))
    if not 1 <= len(steps) <= 4096 or f"PASS\t{len(steps)}" not in log:
        raise ValueError("GSE 上游编译未产生有效的逐次按键计划")
    if not has_random_loop and len(source_plan) != len(steps):
        raise ValueError("GSE 上游编译步骤数量与来源计划不一致")

    source_map = _compiled_source_map(program["nodes"])
    sources = []
    for step in steps:
        identity = (step["source_sequence"], step["source_version"], step["source_path"])
        source = source_map.get(identity)
        if source is None:
            raise ValueError("GSE 上游编译来源身份与 Program 不一致")
        sources.append(source)
    if not has_random_loop:
        expected_identities = [(source["sequence"], source["version"], source["path"])
                               for source in source_plan]
        actual_identities = [(step["source_sequence"], step["source_version"], step["source_path"])
                             for step in steps]
        if actual_identities != expected_identities:
            raise ValueError("GSE 上游编译来源路径与 Program 不一致")
    mapped = [_map_step(step, actions,
                        f"{step['source_sequence']} v{step['source_version']} {step['source_path']}",
                        pet_ready=pet_ready,
                        enemy_target_ready=enemy_target_ready)
              for i, step in enumerate(steps)]
    clicks = []
    for source, block in zip(sources, mapped):
        if block:
            clicks.append(CompiledActionNode(kind="Action", commands=block, source=source))
        else:
            clicks.append(CompiledEmptyClickNode(kind="EmptyClick", source=source))
    candidate = dict(source="gse", text=text, import_sha256=decoded["sha256"],
                     selected_sequence=name, selected_version=version, compiled_steps=steps,
                     mapped_blocks=mapped, source_paths=[s["source_path"] for s in steps],
                     precombat_count=0, blocks=[], simulation="not_run", game_validation="not_run",
                     compile_context=dict(context, scene="no_modifiers_" +
                                          ("enemy_target_ready_" if enemy_target_ready else
                                           "no_enemy_target_") +
                                          ("pet_ready" if pet_ready else "pet_not_ready")),
                     upstream_compilation="passed_with_client_boundary_stubs")
    return _with_compiled_program(candidate, program, clicks)
