"""来源无关的序列树与逐次按键计划。"""

import hashlib
import json
from typing import Literal, NotRequired, TypedDict

from codec import export


class SourcePosition(TypedDict):
    adapter: str
    path: str
    gse_path: NotRequired[str]
    sequence: NotRequired[str]
    version: NotRequired[int]


class ActionNode(TypedDict):
    kind: Literal["Action"]
    commands: list[dict[str, object]]
    source: SourcePosition


class EmptyClickNode(TypedDict):
    kind: Literal["EmptyClick"]
    source: SourcePosition


class LoopNode(TypedDict):
    kind: Literal["Loop"]
    count: int
    step_function: str
    body: list["ProgramNode"]
    source: SourcePosition


class RepeatNode(TypedDict):
    kind: Literal["Repeat"]
    interval: int
    action: ActionNode
    source: SourcePosition


class PauseNode(TypedDict):
    kind: Literal["Pause"]
    clicks: int
    duration_ms: int | float | str | None
    source: SourcePosition


class IfNode(TypedDict):
    kind: Literal["If"]
    condition: bool
    expression: NotRequired[object]
    then: list["ProgramNode"]
    else_branch: list["ProgramNode"]
    source: SourcePosition


class EmbedNode(TypedDict):
    kind: Literal["Embed"]
    sequence: str
    version: int
    body: list["ProgramNode"]
    source: SourcePosition


ProgramNode = ActionNode | EmptyClickNode | LoopNode | RepeatNode | PauseNode | IfNode | EmbedNode


class Program(TypedDict):
    adapter: Literal["search", "gse_import"]
    nodes: list[ProgramNode]
    metadata: dict[str, object]


class CompiledActionNode(TypedDict):
    kind: Literal["Action"]
    commands: list[str]
    source: SourcePosition


class CompiledEmptyClickNode(TypedDict):
    kind: Literal["EmptyClick"]
    source: SourcePosition


CompiledClick = CompiledActionNode | CompiledEmptyClickNode


class CompiledProgram(TypedDict):
    clicks: list[CompiledClick]
    castsequences: NotRequired[list[dict[str, object]]]


def _position(adapter, path, *, gse_path=None, sequence=None, version=None):
    position = SourcePosition(adapter=adapter, path=str(path))
    if gse_path is not None:
        position["gse_path"] = str(gse_path)
    if sequence is not None:
        position["sequence"] = sequence
    if version is not None:
        position["version"] = version
    return position


def from_action_blocks(blocks):
    """把搜索动作块适配成与导入共用的 Program 节点。"""
    nodes = []
    for index, block in enumerate(blocks):
        source = _position("search", f"blocks[{index}]")
        if block:
            nodes.append(ActionNode(kind="Action", commands=list(block), source=source))
        else:
            nodes.append(EmptyClickNode(kind="EmptyClick", source=source))
    return Program(adapter="search", nodes=nodes, metadata={})


def _mapped_search_blocks(capabilities, blocks, sources):
    from sequence import select

    precombat = capabilities.get("precombat_actions", [])
    if len(precombat) + len(blocks) > 128:
        raise ValueError("搜索程序展开超过 128 个顶层动作块")
    selected = [[dict(action, condition="nocombat")] for action in precombat]
    for block, source in zip(blocks, sources):
        try:
            selected.append(select(capabilities, [block])[-1])
        except ValueError as error:
            raise ValueError(f"{source}: {error}") from error
    return selected


def from_search_program(program, capabilities):
    """把搜索动作块、顺序 Loop 和 WaitClicks 转成共享的 Program。"""
    if not isinstance(program, list) or not program:
        raise ValueError("搜索程序必须包含动作块")
    if all(isinstance(segment, list) for segment in program):
        sources = [f"segments[{index}]" for index in range(len(program))]
        return from_action_blocks(_mapped_search_blocks(capabilities, program, sources))
    if len(program) > 128:
        raise ValueError("搜索程序超过 128 个顶层节点")

    flat_blocks = []
    flat_sources = []
    segments = []
    for segment_index, segment in enumerate(program):
        if isinstance(segment, list):
            segments.append(("Action", 1))
            flat_blocks.append(segment)
            flat_sources.append(f"segments[{segment_index}]")
        elif isinstance(segment, dict) and segment.get("kind") == "Loop":
            body = segment.get("blocks")
            count = segment.get("count")
            if (type(count) is not int or not 1 <= count <= 4096
                    or not isinstance(body, list) or not body or len(body) > 128
                    or any(not isinstance(block, list) for block in body)):
                raise ValueError(f"segments[{segment_index}]: 搜索 Loop 的重复次数或动作块无效")
            for block_index, block in enumerate(body):
                if not block:
                    raise ValueError(f"segments[{segment_index}].blocks[{block_index}]: Loop 动作块为空")
            segments.append(("Loop", len(body), count))
            flat_blocks.extend(body)
            flat_sources.extend(f"segments[{segment_index}].blocks[{index}]"
                                for index in range(len(body)))
        elif isinstance(segment, dict) and segment.get("kind") == "WaitClicks":
            clicks = segment.get("clicks")
            if type(clicks) is not int or not 2 <= clicks <= 4096:
                raise ValueError(f"segments[{segment_index}]: 搜索 WaitClicks 次数必须为 2 至 4096")
            segments.append(("WaitClicks", clicks))
        elif isinstance(segment, dict) and segment.get("kind") == "CastSequence":
            members = segment.get("members")
            reset = segment.get("reset")
            if (not isinstance(members, list) or not 2 <= len(members) <= 4
                    or any(not isinstance(member, str) or not member for member in members)):
                raise ValueError(f"segments[{segment_index}]: 搜索 /castsequence 必须包含 2 至 4 个技能成员")
            segments.append(("CastSequence", list(members), reset))
        else:
            raise ValueError(f"segments[{segment_index}]: 搜索程序包含不支持的节点")

    selected = _mapped_search_blocks(capabilities, flat_blocks, flat_sources)
    precombat_count = len(capabilities.get("precombat_actions", []))
    nodes = []
    for index, commands in enumerate(selected[:precombat_count]):
        nodes.append(ActionNode(kind="Action", commands=commands,
                                source=_position("search", f"blocks[{index}]",
                                                  gse_path=str(index + 1))))

    cursor = precombat_count
    top_index = precombat_count
    for segment_index, (segment, shape) in enumerate(zip(program, segments)):
        if shape[0] == "Action":
            nodes.append(ActionNode(kind="Action", commands=selected[cursor],
                                    source=_position("search", f"blocks[{top_index}]",
                                                      gse_path=str(top_index + 1))))
            cursor += 1
            top_index += 1
            continue
        if shape[0] == "WaitClicks":
            nodes.append(PauseNode(kind="Pause", clicks=shape[1], duration_ms=None,
                                   source=_position("search", f"blocks[{top_index}]",
                                                    gse_path=str(top_index + 1))))
            top_index += 1
            continue
        if shape[0] == "CastSequence":
            from macro_interpreter import parse_castsequence

            _, members, reset = shape
            by_name = {action["simc_action"]: action for action in capabilities["actions"]
                       if action.get("kind") == "spell"}
            for member_index, member in enumerate(members):
                if member not in by_name:
                    raise ValueError(f"segments[{segment_index}].members[{member_index}]: "
                                     "技能不受当前角色支持")
            reset_text = ""
            if reset:
                if not isinstance(reset, dict):
                    raise ValueError(f"segments[{segment_index}].reset: /castsequence reset 定义无效")
                parts = []
                timeout = reset.get("timeout_seconds")
                if timeout is not None:
                    parts.append(str(timeout).rstrip("0").rstrip(".") if isinstance(timeout, float) else str(timeout))
                parts.extend(reset.get("flags") or [])
                if parts:
                    reset_text = " reset=" + "/".join(parts)
            macro = "/castsequence" + reset_text + " " + ",".join(
                str(by_name[member]["spell_id"]) for member in members)
            try:
                parsed = parse_castsequence(macro, f"blocks[{top_index}]", capabilities["actions"])
            except ValueError as error:
                raise ValueError(f"segments[{segment_index}]: {error}") from error
            parsed["macro"] = macro
            parsed["macrotext"] = "/castsequence" + reset_text + " " + ", ".join(parsed["display_names"])
            nodes.append(ActionNode(kind="Action", commands=[parsed],
                                    source=_position("search", f"blocks[{top_index}]",
                                                     gse_path=str(top_index + 1))))
            top_index += 1
            continue
        _, body_count, repeat_count = shape
        body = []
        loop_path = f"blocks[{top_index}]"
        for index in range(body_count):
            body.append(ActionNode(
                kind="Action", commands=selected[cursor],
                source=_position("search", f"{loop_path}.loop[{index}]",
                                  gse_path=f"{top_index + 1}.{index + 1}")))
            cursor += 1
        nodes.append(LoopNode(kind="Loop", count=repeat_count, step_function="Sequential",
                              body=body,
                              source=_position("search", loop_path, gse_path=str(top_index + 1))))
        top_index += 1
    if cursor != len(selected):
        raise ValueError("搜索程序与已选动作数量不一致")
    return Program(adapter="search", nodes=nodes, metadata={})


def from_gse_import(text, name, version, *, context=None, decoded=None):
    """解码 GSE 文本为共享 Program；原文只作为临时编译输入保留。"""
    from gse_import import program_from_import

    return program_from_import(text, name, version, context=context, decoded=decoded)


def _search_expanded_nodes(program):
    expanded = []
    for node in program["nodes"]:
        source = node.get("source", {}).get("path", "搜索程序")
        if node["kind"] == "Action":
            if not node["commands"] or len(expanded) >= 4096:
                raise ValueError(f"{source}: 搜索程序包含无效动作或超过 4096 次按键")
            expanded.append(node)
        elif node["kind"] == "Loop":
            body = node["body"]
            count = node["count"]
            if (node["step_function"] != "Sequential" or type(count) is not int
                    or count < 1 or not body
                    or any(child["kind"] != "Action" or not child["commands"] for child in body)):
                raise ValueError(f"{source}: 搜索只支持带有效动作的 Sequential Loop")
            if len(expanded) + count * len(body) > 4096:
                raise ValueError(f"{source}: 搜索程序展开超过 4096 次按键")
            expanded.extend(body * count)
        elif node["kind"] == "Pause":
            clicks = node["clicks"]
            if type(clicks) is not int or clicks < 2 or len(expanded) + clicks > 4096:
                raise ValueError(f"{source}: 搜索 WaitClicks 无效或展开超过 4096 次按键")
            expanded.extend(EmptyClickNode(kind="EmptyClick", source=node["source"])
                            for _ in range(clicks))
        else:
            raise ValueError(f"{source}: 搜索程序包含不支持的节点")
    if not expanded:
        raise ValueError("搜索程序没有可模拟动作")
    return expanded


BEHAVIOR_IDENTITY_VERSION = "sim2gse-search-behavior-v1"


def canonical_behavior_form(clicks, castsequences=()):
    """生成不包含来源位置和展示信息的版本化点击行为。"""
    return {
        "version": BEHAVIOR_IDENTITY_VERSION,
        "clicks": clicks,
        "castsequences": [
            {"step": row["step"], "members": list(row["members"]), "reset": row.get("reset")}
            for row in castsequences
        ],
    }


def canonical_behavior_key(form):
    payload = json.dumps(form, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{BEHAVIOR_IDENTITY_VERSION}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def canonicalize_search_program(search_program, capabilities):
    """映射角色动作后返回行为身份、标准点击计划及保留来源的程序树。"""
    mapped = from_search_program(search_program, capabilities)
    expanded = _search_expanded_nodes(mapped)
    clicks = []
    castsequences = []
    has_action = False
    for step, node in enumerate(expanded):
        if node["kind"] == "EmptyClick":
            clicks.append([])
            continue
        commands = node.get("commands")
        if not isinstance(commands, list) or not commands:
            raise ValueError(f"clicks[{step}] 没有已映射动作")
        if (len(commands) == 1 and isinstance(commands[0], dict)
                and commands[0].get("kind") == "castsequence"):
            command = commands[0]
            members = command.get("members")
            actions = command.get("actions")
            if (not isinstance(members, list) or not members
                    or not isinstance(actions, list)):
                raise ValueError(f"clicks[{step}] 的 /castsequence 映射无效")
            available = {action.get("simc_action") for action in actions if isinstance(action, dict)}
            for index, member in enumerate(members):
                if not isinstance(member, str) or member not in available:
                    raise ValueError(f"clicks[{step}].members[{index}] 无法映射")
            click_commands = list(members)
            castsequences.append({"step": step, "members": list(members),
                                  "reset": command.get("reset")})
        else:
            click_commands = []
            for index, command in enumerate(commands):
                if (not isinstance(command, dict) or command.get("kind") not in {"spell", "item"}
                        or not isinstance(command.get("simc_action"), str)
                        or not command["simc_action"]):
                    raise ValueError(f"clicks[{step}].actions[{index}] 无法映射或导出")
                click_commands.append(command["simc_action"])
        if not click_commands:
            raise ValueError(f"clicks[{step}] 没有可执行动作")
        clicks.append(click_commands)
        has_action = True
    if not has_action:
        source = expanded[0].get("source", {}).get("path", "clicks[0]")
        raise ValueError(f"{source}: 候选仅含空点击，没有可执行动作")
    form = canonical_behavior_form(clicks, castsequences)
    return {"identity": canonical_behavior_key(form), "form": form, "program": mapped}


def _search_blocks(program):
    blocks = []
    for node in _search_expanded_nodes(program):
        if node["kind"] != "Action":
            blocks.append([])
            continue
        commands = node["commands"]
        if len(commands) == 1 and commands[0].get("kind") == "castsequence":
            members = set(commands[0]["members"])
            actions = [action for action in commands[0].get("actions", [])
                       if action.get("simc_action") in members]
            if not actions:
                raise ValueError("搜索 /castsequence 缺少已映射动作")
            by_name = {action["simc_action"]: action for action in actions}
            blocks.append([by_name[name] for name in commands[0]["members"]])
        else:
            blocks.append(commands)
    return blocks


def _with_compiled_program(candidate, program, clicks):
    clean_program = Program(adapter=program["adapter"], nodes=program["nodes"],
                            metadata={key: value for key, value in program["metadata"].items()
                                      if key not in {"input_text"}})
    candidate["program"] = clean_program
    castsequences = []
    for step, node in enumerate(_search_expanded_nodes(program)) if program["adapter"] == "search" else []:
        if (node["kind"] == "Action" and len(node["commands"]) == 1
                and node["commands"][0].get("kind") == "castsequence"):
            command = node["commands"][0]
            castsequences.append({
                "step": step,
                "members": list(command["members"]),
                "reset": command.get("reset"),
                "source": node["source"],
            })
    candidate["compiled_program"] = CompiledProgram(clicks=clicks,
                                                      **({"castsequences": castsequences}
                                                         if castsequences else {}))
    return candidate


def _search_clicks(candidate, program):
    nodes = _search_expanded_nodes(program)
    blocks = candidate["blocks"]
    if len(nodes) != len(blocks):
        raise ValueError("搜索程序与导出动作块数量不一致")
    clicks = []
    for node, block in zip(nodes, blocks):
        if node["kind"] == "EmptyClick":
            if block:
                raise ValueError("空点击不能包含动作")
            clicks.append(CompiledEmptyClickNode(kind="EmptyClick", source=node["source"]))
        else:
            commands = ([action["simc_action"] for action in block]
                        if not (len(node["commands"]) == 1
                                and node["commands"][0].get("kind") == "castsequence")
                        else list(node["commands"][0]["members"]))
            clicks.append(CompiledActionNode(kind="Action", commands=commands,
                                             source=node["source"]))
    return clicks


def compile_program(program, folder, *, identity, runtime=None, capabilities=None, context=None):
    """经同一 Program 接口编译；适配器只负责各来源的编码和上游校验。"""
    if not isinstance(program, dict) or not isinstance(program.get("nodes"), list):
        raise ValueError("序列程序结构无效")
    if program.get("adapter") == "gse_import":
        from gse_import import compile_import

        return compile_import(program, folder, identity=identity, runtime=runtime,
                              capabilities=capabilities, context=context)
    if program.get("adapter") != "search":
        raise ValueError("未知的序列程序适配器")
    blocks = _search_blocks(program)
    if any(node["kind"] in {"Loop", "Pause"} or
           (node["kind"] == "Action" and len(node["commands"]) == 1
            and node["commands"][0].get("kind") == "castsequence")
           for node in program["nodes"]):
        candidate = export(blocks, folder, identity=identity, runtime=runtime, program=program)
    else:
        candidate = export(blocks, folder, identity=identity, runtime=runtime)
    return _with_compiled_program(candidate, program, _search_clicks(candidate, program))
