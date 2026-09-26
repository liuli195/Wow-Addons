"""来源无关的序列树与逐次按键计划。"""

from typing import Literal, NotRequired, TypedDict

from codec import export


class SourcePosition(TypedDict):
    adapter: str
    path: str
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


class WaitClicksNode(TypedDict):
    kind: Literal["WaitClicks"]
    clicks: int
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


ProgramNode = ActionNode | EmptyClickNode | LoopNode | RepeatNode | WaitClicksNode | IfNode | EmbedNode


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


def _position(adapter, path, *, sequence=None, version=None):
    position = SourcePosition(adapter=adapter, path=str(path))
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


def from_gse_import(text, name, version, *, context=None, decoded=None):
    """解码 GSE 文本为共享 Program；原文只作为临时编译输入保留。"""
    from gse_import import program_from_import

    return program_from_import(text, name, version, context=context, decoded=decoded)


def _search_blocks(program):
    blocks = []
    for node in program["nodes"]:
        if node["kind"] == "Action":
            blocks.append(node["commands"])
        elif node["kind"] == "EmptyClick":
            blocks.append([])
        else:
            raise ValueError("搜索程序当前只支持简单动作块")
    if not blocks or any(not block for block in blocks):
        raise ValueError("搜索导出暂不支持空点击")
    return blocks


def _with_compiled_program(candidate, program, clicks):
    clean_program = Program(adapter=program["adapter"], nodes=program["nodes"],
                            metadata={key: value for key, value in program["metadata"].items()
                                      if key not in {"input_text"}})
    candidate["program"] = clean_program
    candidate["compiled_program"] = CompiledProgram(clicks=clicks)
    return candidate


def _search_clicks(candidate, program):
    nodes = [node for node in program["nodes"] if node["kind"] in {"Action", "EmptyClick"}]
    blocks = candidate["blocks"]
    if len(nodes) != len(blocks):
        raise ValueError("搜索程序与导出动作块数量不一致")
    clicks = []
    for node, block in zip(nodes, blocks):
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
    candidate = export(_search_blocks(program), folder, identity=identity, runtime=runtime)
    return _with_compiled_program(candidate, program, _search_clicks(candidate, program))
