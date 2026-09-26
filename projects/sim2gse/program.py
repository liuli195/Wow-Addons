"""来源无关的序列树与逐次按键计划。"""

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


def from_search_program(program, capabilities):
    """把搜索动作块、顺序 Loop 和 WaitClicks 转成共享的 Program。"""
    if not isinstance(program, list) or not program:
        raise ValueError("搜索程序必须包含动作块")
    if all(isinstance(segment, list) for segment in program):
        from sequence import select

        return from_action_blocks(select(capabilities, program))
    if len(program) > 128:
        raise ValueError("搜索程序超过 128 个顶层节点")

    flat_blocks = []
    segments = []
    for segment in program:
        if isinstance(segment, list):
            segments.append(("Action", 1))
            flat_blocks.append(segment)
        elif isinstance(segment, dict) and segment.get("kind") == "Loop":
            body = segment.get("blocks")
            count = segment.get("count")
            if (type(count) is not int or not 1 <= count <= 4096
                    or not isinstance(body, list) or not body or len(body) > 128
                    or any(not isinstance(block, list) for block in body)):
                raise ValueError("搜索 Loop 的重复次数或动作块无效")
            segments.append(("Loop", len(body), count))
            flat_blocks.extend(body)
        elif isinstance(segment, dict) and segment.get("kind") == "WaitClicks":
            clicks = segment.get("clicks")
            if type(clicks) is not int or not 2 <= clicks <= 4096:
                raise ValueError("搜索 WaitClicks 次数必须为 2 至 4096")
            segments.append(("WaitClicks", clicks))
        else:
            raise ValueError("搜索程序包含不支持的节点")

    from sequence import select

    selected = select(capabilities, flat_blocks)
    precombat_count = len(capabilities.get("precombat_actions", []))
    nodes = []
    for index, commands in enumerate(selected[:precombat_count]):
        nodes.append(ActionNode(kind="Action", commands=commands,
                                source=_position("search", f"blocks[{index}]",
                                                  gse_path=str(index + 1))))

    cursor = precombat_count
    top_index = precombat_count
    for segment, shape in zip(program, segments):
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
        if node["kind"] == "Action":
            if not node["commands"] or len(expanded) >= 4096:
                raise ValueError("搜索程序包含无效动作或超过 4096 次按键")
            expanded.append(node)
        elif node["kind"] == "Loop":
            body = node["body"]
            count = node["count"]
            if (node["step_function"] != "Sequential" or type(count) is not int
                    or count < 1 or not body
                    or any(child["kind"] != "Action" or not child["commands"] for child in body)):
                raise ValueError("搜索只支持带有效动作的 Sequential Loop")
            if len(expanded) + count * len(body) > 4096:
                raise ValueError("搜索程序展开超过 4096 次按键")
            expanded.extend(body * count)
        elif node["kind"] == "Pause":
            clicks = node["clicks"]
            if type(clicks) is not int or clicks < 2 or len(expanded) + clicks > 4096:
                raise ValueError("搜索 WaitClicks 无效或展开超过 4096 次按键")
            expanded.extend(EmptyClickNode(kind="EmptyClick", source=node["source"])
                            for _ in range(clicks))
        else:
            raise ValueError("搜索程序包含不支持的节点")
    if not expanded:
        raise ValueError("搜索程序没有可模拟动作")
    return expanded


def _search_blocks(program):
    return [node["commands"] if node["kind"] == "Action" else []
            for node in _search_expanded_nodes(program)]


def _with_compiled_program(candidate, program, clicks):
    clean_program = Program(adapter=program["adapter"], nodes=program["nodes"],
                            metadata={key: value for key, value in program["metadata"].items()
                                      if key not in {"input_text"}})
    candidate["program"] = clean_program
    candidate["compiled_program"] = CompiledProgram(clicks=clicks)
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
            clicks.append(CompiledActionNode(kind="Action",
                                             commands=[action["simc_action"] for action in block],
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
    if any(node["kind"] in {"Loop", "Pause"} for node in program["nodes"]):
        candidate = export(blocks, folder, identity=identity, runtime=runtime, program=program)
    else:
        candidate = export(blocks, folder, identity=identity, runtime=runtime)
    return _with_compiled_program(candidate, program, _search_clicks(candidate, program))
