"""有界解码第三方 GSE 导入字符串；不执行其中的脚本。"""

import base64
import binascii
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
from program import (ActionNode, EmbedNode, IfNode, LoopNode, PauseNode, Program,
                     ProgramNode, RepeatNode, SourcePosition, CompiledActionNode,
                     CompiledEmptyClickNode, _with_compiled_program)


MAX_TEXT = 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 10000
VALID_TYPES = {"Action", "Repeat", "Loop", "Pause", "If", "Embed"}
LOCK_PATH = ROOT / "projects/sim2gse/compatibility/lock.json"


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
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("GSE 导入包含无效 UTF-8 字符") from error
    if isinstance(value, list):
        return [_plain(item, depth + 1, count) for item in value]
    if isinstance(value, dict):
        return {_plain(key, depth + 1, count): _plain(item, depth + 1, count)
                for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise ValueError("GSE 导入包含不支持的数据类型")


def decode_import(text):
    """返回原始 GSE 对象和序列映射；失败不会退化成空序列。"""
    if not isinstance(text, str) or len(text) > MAX_TEXT or not text.startswith("!GSE3!"):
        raise ValueError("GSE 导入字符串格式或长度无效")
    if text.startswith("!GSE3!+"):
        raise ValueError("GSE 受保护导入格式暂不能解析")
    encoded = text[6:]
    if not encoded or re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", encoded) is None:
        raise ValueError("GSE 导入编码无效")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        inflater = zlib.decompressobj(-15)
        raw = inflater.decompress(compressed, MAX_DECODED + 1)
        if len(raw) > MAX_DECODED or inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
            raise ValueError("GSE 导入解压结果过大或不完整")
        raw += inflater.flush(MAX_DECODED + 1 - len(raw))
        if len(raw) > MAX_DECODED:
            raise ValueError("GSE 导入解压结果过大")
        stream = io.BytesIO(raw)
        payload = _plain(cbor2.CBORDecoder(stream).decode())
        if stream.read(1):
            raise ValueError("GSE 导入编码含有多余数据")
    except (binascii.Error, zlib.error, cbor2.CBORDecodeError, UnicodeDecodeError) as error:
        raise ValueError("GSE 导入编码或内容损坏") from error
    if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], str):
        sequences = {payload[0]: payload[1]}
        envelope = "single"
    elif isinstance(payload, dict) and payload.get("type") == "COLLECTION":
        body = payload.get("payload")
        if not isinstance(body, dict) or not isinstance(body.get("Sequences"), dict):
            raise ValueError("GSE 导入集合缺少序列")
        sequences = {}
        for name, value in body["Sequences"].items():
            if isinstance(value, list) and len(value) == 2 and value[0] == name:
                value = value[1]
            sequences[name] = value
        envelope = "collection"
    elif (isinstance(payload, dict) and isinstance(payload.get("MetaData"), dict)
          and isinstance(payload.get("Versions"), list)):
        name = payload["MetaData"].get("Name")
        if not isinstance(name, str) or not name:
            raise ValueError("GSE 直接序列缺少 MetaData.Name")
        sequences = {name: payload}
        envelope = "direct"
    else:
        raise ValueError("GSE 导入外壳不受支持")
    if not sequences or any(not isinstance(name, str) or not name or not isinstance(seq, dict)
                            or not isinstance(seq.get("Versions"), list) or not seq["Versions"]
                            or not isinstance(seq.get("MetaData"), dict)
                            for name, seq in sequences.items()):
        raise ValueError("GSE 导入序列结构无效")
    return dict(payload=payload, sequences=sequences, envelope=envelope,
                sha256=hashlib.sha256(text.encode("ascii")).hexdigest())


def _position(sequence, version, path):
    return SourcePosition(adapter="gse_import", sequence=sequence, version=version, path=str(path))


def _action_node(action, source):
    if not isinstance(action, dict):
        command = dict(type="raw", argument=str(action))
    else:
        command_type = action.get("type")
        if command_type == "spell":
            command = dict(type="spell", argument=action.get("spell"))
        elif command_type == "item":
            command = dict(type="item", argument=action.get("item"))
        elif command_type == "macro":
            command = dict(type="macro", text=action.get("macro", action.get("macrotext", "")))
        else:
            command = dict(type=command_type, argument=action.get("spell", action.get("item")))
    return ActionNode(kind="Action", commands=[command], source=source)


def _gse_nodes(actions, sequences, sequence_name, version, selected_versions, seen, path_prefix="",
               state=None, depth=0):
    if state is None:
        state = [0]
    if depth > MAX_DEPTH:
        raise ValueError("GSE 程序展开过深或节点过多")
    if not isinstance(actions, list):
        return []
    nodes = []
    for index, action in enumerate(actions, 1):
        state[0] += 1
        if state[0] > MAX_NODES:
            raise ValueError("GSE 程序展开过深或节点过多")
        path = f"{path_prefix}.{index}" if path_prefix else str(index)
        if not isinstance(action, dict):
            nodes.append(_action_node(action, _position(sequence_name, version, path)))
            continue
        kind = action.get("Type")
        source = _position(sequence_name, version, path)
        if kind == "Action":
            nodes.append(_action_node(action, source))
        elif kind == "Repeat":
            child_source = _position(sequence_name, version, path + ".action")
            repeat = action.get("Interval", action.get("Repeat", 2))
            try:
                repeat = int(float(repeat))
            except (TypeError, ValueError):
                repeat = 2
            nodes.append(RepeatNode(kind="Repeat", interval=repeat,
                                    action=_action_node(action, child_source), source=source))
        elif kind == "Loop":
            try:
                count = int(float(action.get("Repeat", 1)))
            except (TypeError, ValueError):
                count = 1
            children = [action[key] for key in sorted(k for k in action if type(k) is int and k > 0)]
            body = _gse_nodes(children, sequences, sequence_name, version, selected_versions, seen,
                              path_prefix=path, state=state, depth=depth + 1)
            nodes.append(LoopNode(kind="Loop", count=count,
                                  step_function=action.get("StepFunction") or "Sequential",
                                  body=body, source=source))
        elif kind == "Pause":
            nodes.append(PauseNode(kind="Pause", clicks=action.get("Clicks", 0),
                                   duration_ms=action.get("MS"), source=source))
        elif kind == "If":
            expression = action.get("Variable")
            condition = isinstance(expression, str) and expression.lstrip("=").strip().lower() == "true"
            yes_actions = action.get(1, action.get("1", []))
            no_actions = action.get(2, action.get("2", []))
            yes_actions = yes_actions if isinstance(yes_actions, list) else [yes_actions]
            no_actions = no_actions if isinstance(no_actions, list) else [no_actions]
            yes = _gse_nodes(yes_actions, sequences, sequence_name, version,
                             selected_versions, seen, path_prefix=path + ".1",
                             state=state, depth=depth + 1)
            no = _gse_nodes(no_actions, sequences, sequence_name, version,
                            selected_versions, seen, path_prefix=path + ".2",
                            state=state, depth=depth + 1)
            nodes.append(IfNode(kind="If", condition=condition, then=yes, else_branch=no, source=source))
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
                    and embedded_name not in seen and 1 <= embedded_version <= len(embedded.get("Versions", []))):
                body = _gse_nodes(embedded["Versions"][embedded_version - 1].get("Actions", []),
                                  sequences, embedded_name, embedded_version,
                                  selected_versions, seen | {embedded_name},
                                  state=state, depth=depth + 1)
            nodes.append(EmbedNode(kind="Embed", sequence=str(embedded_name or ""),
                                   version=embedded_version, body=body, source=source))
        else:
            # Compilation performs the authoritative unsupported-node check.
            nodes.append(_action_node(action, source))
    return nodes


def program_from_import(text, name, version, *, context=None, decoded=None):
    """把已解码的 GSE 结构适配为共享 Program 树。"""
    decoded = decoded or decode_import(text)
    if name not in decoded["sequences"] or type(version) is not int:
        raise ValueError("GSE 选定的序列或版本无效")
    sequence = decoded["sequences"][name]
    if not 1 <= version <= len(sequence["Versions"]):
        raise ValueError("GSE 选定的序列或版本无效")
    requested = (context or {}).get("versions", {})
    requested = requested if isinstance(requested, dict) else {}
    selected_versions = {key: value.get("Default", 1) for key, value in decoded["sequences"].items()}
    selected_versions.update(requested)
    selected_versions[name] = version
    nodes = _gse_nodes(sequence["Versions"][version - 1].get("Actions", []),
                       decoded["sequences"], name, version, selected_versions, {name})
    return Program(adapter="gse_import", nodes=nodes,
                   metadata={"input_text": text, "name": name, "version": version,
                             "sha256": decoded["sha256"]})


def _compiled_source_map(nodes):
    by_path = {}
    def visit(items):
        for node in items:
            if node["kind"] in {"Action", "Repeat", "Pause"}:
                by_path.setdefault(node["source"]["path"], []).append(node["source"])
            visit(node.get("body", []))
            visit(node.get("then", []))
            visit(node.get("else_branch", []))
            if node.get("action"):
                visit([node["action"]])

    visit(nodes)
    return by_path


def inspect_import(text):
    decoded = decode_import(text)
    locked_version = _locked_gse_version()
    syntax = set()
    def visit(value):
        if isinstance(value, dict):
            kind = value.get("Type")
            if isinstance(kind, str):
                syntax.add(kind)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    entries = []
    for name, seq in decoded["sequences"].items():
        visit(seq["Versions"])
        gse_version = seq["MetaData"].get("GSEVersion")
        simulation_supported, support_reason = _simulation_compatibility(gse_version, locked_version)
        entries.append(dict(name=name, spec_id=seq["MetaData"].get("SpecID"),
                            gse_version=gse_version, version_count=len(seq["Versions"]),
                            default_version=seq.get("Default"),
                            simulation_supported=simulation_supported, support_reason=support_reason))
    return dict(status="decoded", format=decoded["envelope"], sha256=decoded["sha256"],
                sequences=entries, syntax=sorted(syntax), simulation_started=False,
                support="not_checked")


def _check_nodes(value, sequences, seen, path="", selected_versions=None):
    def fail(message):
        raise ValueError(f"{message}（位置：{path or 'Version'}）")

    if isinstance(value, dict):
        kind = value.get("Type")
        if kind is not None:
            if not isinstance(kind, str) or kind not in VALID_TYPES:
                fail(f"GSE 控制块类型不支持：{kind}")
            if kind == "If":
                expression = value.get("Variable")
                constant = expression[1:].strip() if isinstance(expression, str) and expression.startswith("=") else expression
                if not isinstance(constant, str) or constant not in {"true", "false"}:
                    fail("GSE If 条件需要游戏内变量，不能确定分支")
            if kind == "Loop":
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
                try:
                    interval = float(value.get("Interval", value.get("Repeat", 2)))
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
                if ms is not None and not (isinstance(ms, str) and ms in {"GCD", "~~GCD~~"}):
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
                if (type(embedded_version) is not int or
                        not 1 <= embedded_version <= len(embedded["Versions"])):
                    fail(f"GSE Embed 选中版本无效：{dep} {embedded_version}")
                _check_nodes(embedded["Versions"][embedded_version - 1], sequences, seen | {dep},
                             f"{path}.Embed[{dep}].Versions[{embedded_version}]" if path
                             else f"Embed[{dep}].Versions[{embedded_version}]", selected_versions)
        for key, item in value.items():
            if isinstance(item, str) and item.startswith("="):
                if (kind == "If" and key == "Variable"
                        and item[1:].strip() in {"true", "false"}):
                    continue
                fail("GSE 公式需要执行外部 Lua，不能安全模拟")
            child_path = f"{path}[{key}]" if type(key) is int else (f"{path}.{key}" if path else str(key))
            _check_nodes(item, sequences, seen, child_path, selected_versions)
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            _check_nodes(item, sequences, seen, f"{path}[{index}]", selected_versions)


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
            inserts.append((index, item[1] + 1))
        else:
            actions.append(item)
    for start, interval in inserts:
        insert_count = math.ceil((len(actions) - start) / interval)
        insert_count = math.ceil((len(actions) + insert_count - start) / interval)
        insert_count = max(0, insert_count)
        if len(actions) + 1 + insert_count > 4096:
            raise ValueError("GSE 展开计划超过 4096 次按键")
        if start > len(actions) + 1:
            # The pinned Lua 5.1 table.insert permits a position beyond the
            # contiguous array and leaves a hole; counting it as an append is
            # a safe upper bound for the later ipairs-based output.
            actions.append(1)
        else:
            actions.insert(start - 1, 1)
        for index in range(1, insert_count + 1):
            position = start + index * interval
            if position > len(actions) + 1:
                actions.append(1)
            else:
                actions.insert(position - 1, 1)
    return actions


def _estimate_expansion(nodes, context):
    """按固定 GSE 展开控制块，并在调用上游 Lua 前限制计划大小。"""
    click_ms, gcd_ms = context["click_ms"], context["gcd_ms"]

    def expand(items, depth=0):
        if depth > MAX_DEPTH:
            raise ValueError("GSE 程序展开过深或节点过多")
        output = []
        for node in items:
            kind = node["kind"]
            if kind in {"Action", "EmptyClick"}:
                _bounded_append(output, [1])
            elif kind == "Repeat":
                _bounded_append(output, [("repeat", node["interval"])])
            elif kind == "Pause":
                duration = node["duration_ms"]
                if duration in {"GCD", "~~GCD~~"}:
                    clicks = math.ceil(gcd_ms / click_ms)
                elif duration is not None:
                    # The pinned GSE source treats every numeric MS pause as one second.
                    clicks = math.ceil(1000 / click_ms)
                else:
                    clicks = node["clicks"]
                count = math.floor(clicks) if clicks > 1 else 0
                _bounded_append(output, [1] * count)
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


def _condition(expression, path):
    """求值本期明确的默认场景；未知条件绝不猜测。"""
    if not expression:
        return True
    outcomes = []
    for token in expression.split(","):
        token = token.strip().lower()
        if token in {"combat", "harm", "nodead", "exists", "@target", "@player", "nomod", "pet"}:
            outcomes.append(True)
        elif token in {"nocombat", "nopet", "noexists", "dead"} or token.startswith("mod:"):
            outcomes.append(False)
        else:
            outcomes.append(None)
    if False in outcomes:
        return False
    if None in outcomes:
        raise ValueError(f"GSE {path} 的宏条件不能确定：[{expression}]")
    return True


def _map_step(step, actions, path, *, pet_ready=True, enemy_target_ready=False):
    kind = step["type"]
    if kind == "click":
        return []
    if kind in {"spell", "item"}:
        key = "spell_id" if kind == "spell" else "slot"
        value = step["argument"]
        found = [action["simc_action"] for action in actions
                 if action.get("kind") == kind and value.casefold() in
                 {str(action.get(key)).casefold(), str(action.get("name", "")).casefold(),
                  str(action.get("simc_action", "")).casefold()}]
        if len(found) == 1:
            return found
        raise ValueError(f"GSE {path} 的 {kind} {value} 不能映射到当前角色")
    if kind == "macro":
        block = []
        for line in step["macrotext"].splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("/targetenemy"):
                if not re.fullmatch(r"/targetenemy \[noharm\]\[dead\]", line, re.IGNORECASE):
                    raise ValueError(f"GSE {path} 的 targetenemy 写法不能忠实模拟：{line[:80]}")
                if not enemy_target_ready:
                    raise ValueError(f"GSE {path} 的敌方目标状态未确认，不能跳过 targetenemy")
                continue
            match = re.fullmatch(r"/(cast|use|startattack|petattack|petassist|stopmacro)\s*(?:\[([^]]+)\])?\s*(.*)", line)
            if not match:
                raise ValueError(f"GSE {path} 的宏命令不能忠实模拟：{line[:80]}")
            command, condition, argument = match.groups()
            if not _condition(condition, path):
                continue
            if command == "stopmacro" and not argument:
                break
            if command in {"petattack", "petassist"} and not argument:
                if pet_ready:
                    continue
                raise ValueError(f"GSE {path} 的宠物状态无法在当前角色中验证")
            if command == "cast" and argument:
                if condition and "@player" in condition.lower():
                    spell = next((a for a in actions if str(a.get("spell_id")) == argument or
                                  str(a.get("name", "")).casefold() == argument.casefold()), None)
                    targeting = json.loads((ROOT / "projects/sim2gse/compatibility/spell-target-masks.json")
                                           .read_text(encoding="utf-8"))
                    if spell is None or not (targeting["target_masks"].get(str(spell.get("spell_id")), 0) & 64):
                        raise ValueError(f"GSE {path} 的 @player 目标不能按当前角色验证")
                block += _map_step(dict(type="spell", argument=argument), actions, path,
                                   pet_ready=pet_ready, enemy_target_ready=enemy_target_ready)
                continue
            if command == "use" and argument in {"13", "14"}:
                block += _map_step(dict(type="item", argument=argument), actions, path,
                                   pet_ready=pet_ready, enemy_target_ready=enemy_target_ready)
                continue
            if command == "startattack" and not argument:
                found = [a["simc_action"] for a in actions if a.get("kind") == "start_attack"]
                if len(found) == 1:
                    block += found
                    continue
            raise ValueError(f"GSE {path} 的宏命令不能忠实模拟：{line[:80]}")
        return block
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
    if not 1 <= version <= len(sequence["Versions"]):
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
    _check_nodes(sequence["Versions"][version - 1].get("Actions", []),
                 decoded["sequences"], {name}, path=f"Versions[{version}].Actions",
                 selected_versions=selected_versions)
    if (type(context.get("click_ms")) is not int or not 50 <= context["click_ms"] <= 2000
            or type(context.get("gcd_ms")) is not int or not 500 <= context["gcd_ms"] <= 3000
            or type(context.get("seed")) is not int):
        raise ValueError("GSE 编译条件缺少有效的点击间隔、公共冷却或随机种子")
    if (type(context.get("input_interval_ms")) is not int
            or not 50 <= context["input_interval_ms"] <= 2000
            or context["click_ms"] != context["input_interval_ms"]):
        raise ValueError("GSE 点击间隔必须与模拟按键间隔一致")
    _estimate_expansion(program["nodes"], context)
    pet_ready = context.get("pet_ready", True)
    if type(pet_ready) is not bool:
        raise ValueError("宠物就绪场景必须是布尔值")
    context["pet_ready"] = pet_ready
    enemy_target_ready = context.get("enemy_target_ready", True)
    if type(enemy_target_ready) is not bool:
        raise ValueError("敌方目标场景必须是布尔值")
    context["enemy_target_ready"] = enemy_target_ready
    actions = [variant for action in (capabilities or {}).get("actions", [])
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
            if len(fields) != 6 or int(fields[1]) != len(steps) + 1:
                raise ValueError("GSE 上游编译步骤格式无效")
            steps.append(dict(type=fields[2], argument=fields[3],
                              macrotext=bytes.fromhex(fields[4]).decode("utf-8"),
                              source_path=fields[5]))
    if not 1 <= len(steps) <= 4096 or f"PASS\t{len(steps)}" not in log:
        raise ValueError("GSE 上游编译未产生有效的逐次按键计划")
    mapped = [_map_step(step, actions, step["source_path"] or str(i + 1), pet_ready=pet_ready,
                        enemy_target_ready=enemy_target_ready)
              for i, step in enumerate(steps)]
    clicks = []
    source_options = _compiled_source_map(program["nodes"])
    source_counts = {}
    for index, (block, step) in enumerate(zip(mapped, steps), 1):
        path = step["source_path"] or str(index)
        options = source_options.get(path, [])
        occurrence = source_counts.get(path, 0)
        source_counts[path] = occurrence + 1
        source = (options[min(occurrence, len(options) - 1)] if options
                  else _position(name, version, path))
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
