"""从暴雪生成接口文档产出 LuaLS 注解。

输入是 `.tools/wow-ui-source` 里随客户端发布的 `Blizzard_APIDocumentationGenerated`
数据表；输出是供语言服务器使用的 `---@class` / `---@param` / `---@return` 注解。

转换规则取自上游 `Ketho/vscode-wow-api` 的 `luasrc/annotate/init.lua`：那是个定值
映射（`bool`→`boolean`、`cstring`→`string`、`luaIndex`→`number`，其余原样透传）。
上游生成器要求 Lua 5.4 与 5 个需编译的 C 模块，其 `setup/README.md` 明确劝阻在
Windows 上安装；这里用标准库复刻同一套规则，产出与上游一致，不引入那套工具链。

只覆盖 `Annotations/Core/Blizzard_APIDocumentationGenerated` 这一个目录；`Libraries`、
`Lua`、`Type`、`Data`、`Widget`、`ScriptObject` 属上游手工知识，不在本脚本范围内。
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".tools/wow-ui-source/Interface/AddOns/Blizzard_APIDocumentationGenerated"
TOC = SOURCE / "Blizzard_APIDocumentationGenerated.toc"
OUTPUT = ROOT / "scripts/dev/annotations/api/Blizzard_APIDocumentationGenerated"
# 部件方法单独输出：上游 `Widget/` 已声明这些类（`---@class Frame : Region, ScriptObject`）
# 及其 1127 个方法，这里只补上游没有的方法，不重复声明类。
SCRIPT_OUTPUT = ROOT / "scripts/dev/annotations/scriptobject"
WIDGET_DOCS = ROOT / ".tools/wow-api/Annotations/Core/Widget"
UPSTREAM_DOC_WIDGETS = ROOT / ".tools/wow-api/wowdoc/loader/doc_widgets.lua"
METHOD_NAME = re.compile(r"^function [A-Za-z0-9_]+[.:]([A-Za-z0-9_]+)\(", re.M)
WIDGET_MAPPING = re.compile(r'^\t([A-Za-z0-9_]+) = "([A-Za-z0-9_]+)"', re.M)

# 上游仓库里由人手维护的类型定义所在目录；这些类型名在生成产出里要保留原样，
# 降级成 any 会丢掉本可用的精度。
HANDWRITTEN_DIRS = ("Data", "Type", "Widget", "ScriptObject", "FrameXML")
DECLARATION = re.compile(r"^---@(?:alias|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)

# 枚举名清单。暴雪文档从不给枚举名加 `Enum.` 前缀，是上游查 `Enum` 表后补的；
# 该表来自 BlizzardInterfaceResources，而它在本仓库又只以生成产物的形式存在，
# 所以这里以上游 `Data/Enum.lua` 的枚举名为准，再并入文档自身声明的枚举。
ENUM_DATA = "Data/Enum.lua"
ENUM_NAME = re.compile(r"^Enum\.([A-Za-z_][A-Za-z0-9_]*) = ", re.M)

# 上游 loader/patches.lua：暴雪文档里缺失或不准的类型，由上游手工修正。
# 形如 {文件名: {函数名: {Arguments|Returns: {参数名: {字段: 值}}}}}。
PATCHES = {
    "AddOnsDocumentation.lua": {
        "GetAddOnMetadata": {"Returns": {"value": {"Nilable": True}}},
    },
    "ClassColorDocumentation.lua": {
        "GetClassColor": {"Arguments": {"className": {"Type": "ClassFile"}}},
    },
    "CVarDocumentation.lua": {
        "GetCVar": {"Arguments": {"name": {"Type": "CVar"}}},
        "GetCVarBitfield": {"Arguments": {"name": {"Type": "CVar"}}},
        "GetCVarBool": {"Arguments": {"name": {"Type": "CVar"}}},
        "GetCVarDefault": {"Arguments": {"name": {"Type": "CVar"}}},
        "RegisterCVar": {"Arguments": {"value": {"Type": "string|number"}}},
        "SetCVar": {"Arguments": {"name": {"Type": "CVar"}, "value": {"Type": "string|number"}}},
        "SetCVarBitfield": {"Arguments": {"name": {"Type": "CVar"}}},
    },
}

# 上游 loader/init.lua 跳过的系统；这些文件依赖登录界面环境。
GLUES_SYSTEMS = {"ConfigurationWarningsDocumentation.lua"}

# 上游 luasrc/annotate/init.lua 的类型替换表。
TYPE_MAP = {"bool": "boolean", "cstring": "string", "luaIndex": "number"}

# LuaLS 直接认识、无需定义的类型。
BUILTIN_TYPES = {
    "number", "string", "boolean", "table", "nil", "any",
    "function", "userdata", "thread", "integer",
}

TOKEN = re.compile(r"""
    (?P<space>\s+)
  | (?P<comment>--\[\[.*?\]\]|--[^\n]*)
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<number>-?(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<symbol>[{}\[\]=.,;()\-+:])
""", re.X | re.S)

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
           "f": "\f", "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def tokenize(text):
    """把 Lua 源码切成记号；注释与空白丢弃。"""
    pos, out = 0, []
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise ValueError(f"无法识别的字符：{text[pos:pos + 40]!r}")
        pos = match.end()
        kind = match.lastgroup
        if kind not in ("space", "comment"):
            out.append((kind, match.group()))
    return out


def unquote(raw):
    """把 Lua 字符串字面量还原成文本。"""
    body, out, i = raw[1:-1], [], 0
    while i < len(body):
        char = body[i]
        if char != "\\":
            out.append(char)
            i += 1
            continue
        i += 1
        if i >= len(body):
            break
        if body[i] == "x":
            out.append(chr(int(body[i + 1:i + 3], 16)))
            i += 3
        elif body[i].isdigit():
            digits = body[i:i + 3]
            out.append(chr(int(digits)))
            i += len(digits)
        else:
            out.append(ESCAPES.get(body[i], body[i]))
            i += 1
    return "".join(out)


class Table(dict):
    """一张 Lua 表：具名键存进字典本身，数组部分存进 `entries`。

    不用特殊键名存数组部分，否则它会作为字段混进注解产出。
    """

    def __init__(self):
        super().__init__()
        self.entries = []

    def __bool__(self):
        # 字典部分常为空而数组部分非空；沿用 dict 的默认真值会让
        # `if node.get("Documentation")` 这类守卫误判为假。
        return True


class Parser:
    """只解析暴雪文档用到的 Lua 子集：表字面量、标量、字段访问。"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset=0):
        index = self.pos + offset
        return self.tokens[index] if index < len(self.tokens) else (None, None)

    def take(self, value=None):
        kind, text = self.peek()
        if kind is None:
            raise ValueError("输入意外结束")
        if value is not None and text != value:
            raise ValueError(f"期望 {value!r}，实到 {text!r}")
        self.pos += 1
        return kind, text

    @staticmethod
    def parse_number(text):
        lowered = text.lower()
        if lowered.lstrip("-").startswith("0x"):
            return int(text, 16)
        if "." in text or "e" in lowered:
            return float(text)
        return int(text)

    def parse_value(self):
        kind, text = self.peek()
        if text == "{":
            return self.parse_table()
        if kind == "string":
            self.take()
            return unquote(text)
        if kind == "number":
            self.take()
            return self.parse_number(text)
        if kind == "name":
            if text == "true":
                self.take()
                return True
            if text == "false":
                self.take()
                return False
            if text == "nil":
                self.take()
                return None
            # 形如 Enum.Foo.Bar / Constants.Foo 的引用：按点分路径取出，
            # 再用运算符串起来（`Value` 字段里出现过 `A - B + 1`）。
            path = [self.take()[1]]
            while self.peek()[1] == ".":
                self.take(".")
                path.append(self.take()[1])
            value = ("ref", ".".join(path))
            while self.peek()[1] in ("-", "+"):
                op = self.take()[1]
                operand = self.parse_value()
                value = ("expr", value, op, operand)
            return value
        raise ValueError(f"无法解析的值：{text!r}")

    def parse_table(self):
        self.take("{")
        entries, fields = [], {}
        while self.peek()[1] != "}":
            if self.peek()[1] == "[":
                raise ValueError("暂不支持 [表达式] 形式的键")
            if self.peek()[0] == "name" and self.peek(1)[1] == "=":
                key = self.take()[1]
                self.take("=")
                fields[key] = self.parse_value()
            else:
                entries.append(self.parse_value())
            if self.peek()[1] in (",", ";"):
                self.take()
            elif self.peek()[1] != "}":
                raise ValueError(f"表内期望分隔符，实到 {self.peek()[1]!r}")
        self.take("}")
        table = Table()
        table.update(fields)
        table.entries = entries
        return table


def parse_documentation(text):
    """从一个文档文件里取出它注册的那张表。

    文件结构为 `local <Name> = {...}`，其后是 `APIDocumentation:AddDocumentationTable(<Name>)`；
    只取顶层表，尾部注册调用不参与解析。
    """
    tokens = tokenize(text)
    while tokens and tokens[0][1] != "=":
        tokens.pop(0)
    if not tokens:
        raise ValueError("文档里找不到顶层表")
    parser = Parser(tokens)
    parser.take("=")
    return parser.parse_value()


def toc_files():
    """按清单顺序列出文档文件，与上游 loader 的遍历顺序一致。"""
    lines = TOC.read_text(encoding="utf-8-sig").splitlines()
    return [line.strip() for line in lines
            if line.strip().endswith(".lua") and not line.lstrip().startswith("#")]


class Generator:
    def __init__(self, systems, handwritten_types=(), enums=(), widgets=None, covered_methods=()):
        self.systems = systems
        self.widgets = widgets if widgets is not None else widget_mapping()
        self.covered_methods = set(covered_methods)
        self.system_by_name = {}
        for name, system in systems.items():
            self.system_by_name.setdefault(system.get("Name"), system)
        # 类型名的来源有三处：LuaLS 内置、暴雪文档里定义的结构体与枚举、
        # 上游手工维护的类型别名。三者之外的名字一律降级。
        self.declared_types = set(BUILTIN_TYPES) | set(handwritten_types)
        self.enums = set(enums)
        for system in systems.values():
            for table in system.get("Tables", Table()).entries:
                if not isinstance(table, Table) or not table.get("Name"):
                    continue
                self.declared_types.add(table["Name"])
                if table.get("Type") == "Enumeration":
                    self.enums.add(table["Name"])

    def resolve_type(self, raw):
        """映射类型名；解析不到的降级为 any。

        暴雪文档从不给枚举名加前缀，是上游查 `Enum` 表后补的；这里用文档自身
        声明的枚举名判定，效果一致。

        LuaLS 把未定义的类型名当成独立类型，任何实参都对不上，会产生满屏误报；
        `any` 与所有类型兼容，是安全的降级。
        """
        parts = [part.strip() for part in raw.split("|")]
        resolved = []
        for part in parts:
            name = TYPE_MAP.get(part, part)
            if name in self.enums:
                resolved.append("Enum." + name)
            elif name in self.declared_types:
                resolved.append(name)
            else:
                # 联合类型里只要有一支解析不到，整体就退回 any：`any` 覆盖其余分支，
                # 保留 `A|any` 既无意义又会误导。
                return "any"
        return "|".join(resolved)

    def full_name(self, system, node, wiki=False):
        if system.get("Type") == "ScriptObject":
            sep = "_" if wiki else ":"
            return f"{self.widget_name(system['Name'])}{sep}{node['Name']}"
        if system.get("Namespace"):
            return f"{system['Namespace']}.{node['Name']}"
        return node["Name"]

    def widget_name(self, name):
        """内部名 → 公开部件名；映射表没有的去掉 API 后缀。"""
        if name in self.widgets:
            return self.widgets[name]
        return name[:-3] if name.endswith("API") else name

    def field_type(self, node):
        if "InnerType" in node:
            return self.resolve_type(node["InnerType"]) + "[]"
        return self.resolve_type(node.get("Type", "any"))

    def annotation(self, kind, node):
        param_type = self.field_type(node)
        nilable = "?" if node.get("Nilable") or node.get("Default") is not None else ""
        name = "..." if "StrideIndex" in node else node.get("Name", "?")
        if kind == "param":
            line = f"---@param {name}{nilable} {param_type}"
        elif kind == "return":
            line = f"---@return {param_type}{nilable} {name}"
        else:
            line = f"---@field {name} {param_type}{nilable}"
        if "StrideIndex" in node:
            line += f" {node.get('Name', '')}"
        if node.get("Default") is not None:
            line += f" Default = {json.dumps(node['Default'], ensure_ascii=False)}".replace('"', "")
        return line

    def function_block(self, system, node):
        lines = []
        if node.get("Documentation") and node["Documentation"].entries:
            # 文档里含 `\n`、`\t` 这类转义；直接铺开会让注释断行、产出行外文本，
            # 使文件不再是合法 Lua。这里把控制字符写回转义形式，保持单行注释。
            lines.append("---" + "; ".join(
                text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
                for text in node["Documentation"].entries))
            lines.append("---")
        lines.append(f"---[Documentation](https://warcraft.wiki.gg/wiki/API_{self.full_name(system, node, True)})")
        for arg in node.get("Arguments", Table()).entries:
            lines.append(self.annotation("param", arg))
        for ret in node.get("Returns", Table()).entries:
            lines.append(self.annotation("return", ret))
        args = ["..." if "StrideIndex" in a else a.get("Name", "?")
                for a in node.get("Arguments", Table()).entries]
        lines.append(f"function {self.full_name(system, node)}({', '.join(args)}) end")
        return "\n".join(lines)

    def structure_block(self, node):
        lines = [f"---@class {node['Name']}"]
        for field in node.get("Fields", Table()).entries:
            lines.append(self.annotation("field", field))
        return "\n".join(lines)

    def callback_block(self, node):
        params = []
        for arg in node.get("Arguments", Table()).entries:
            nilable = "?" if arg.get("Nilable") or arg.get("Default") is not None else ""
            params.append(f"{arg.get('Name', '?')}{nilable}: {self.resolve_type(arg.get('Type', 'any'))}")
        return f"---@alias {node['Name']} FunctionContainer|fun({', '.join(params)})"

    def system_block(self, system):
        blocks = []
        functions = system.get("Functions", Table()).entries
        if functions:
            if system.get("Namespace"):
                blocks.append(f"{system['Namespace']} = {{}}")
            for node in functions:
                blocks.append(self.function_block(system, node))
        for table in system.get("Tables", Table()).entries:
            if table.get("Type") == "Structure":
                blocks.append(self.structure_block(table))
            elif table.get("Type") == "CallbackType":
                blocks.append(self.callback_block(table))
        return "\n\n".join(blocks)

    def script_methods(self):
        """部件方法产出：只写上游 `Widget/` 没有的方法。

        上游已声明部件类及其 1127 个方法；重复声明类会让 LuaLS 报重复定义，
        所以这里只产出方法本体，类由上游提供。
        """
        outputs, skipped = {}, []
        for name, system in sorted(self.systems.items()):
            if system.get("Type") != "ScriptObject":
                continue
            blocks = []
            for node in system.get("Functions", Table()).entries:
                if node.get("Name") in self.covered_methods:
                    continue
                blocks.append(self.function_block(system, node))
            if not blocks:
                skipped.append(name)
                continue
            outputs[name] = "---@meta _\n" + "\n\n".join(blocks) + "\n"
        return outputs, skipped

    def build(self):
        """返回 {输出文件名: 内容}，以及被跳过的文件名清单。

        跳过两类，与上游 loader 一致：登录界面专用系统；以及转换后为空的文件
        （暴雪文档里有大量只含枚举或空 Functions 的文件，产出空注解没有意义）。
        `ScriptObject` 类型上游写到部件目录而非此处，本脚本不覆盖部件层。
        """
        outputs, skipped = {}, []
        for name in toc_files():
            if name in GLUES_SYSTEMS:
                skipped.append(name)
                continue
            system = self.systems.get(name)
            if system is None:
                raise ValueError(f"清单里的文件没有对应文档表：{name}")
            apply_patches(name, system)
            kind = system.get("Type")
            if kind not in (None, "System"):
                skipped.append(name)
                continue
            text = self.system_block(system)
            if not text:
                skipped.append(name)
                continue
            outputs[name] = "---@meta _\n" + text + "\n"
        return outputs, skipped


def load_systems():
    systems = {}
    for name in toc_files():
        if name in GLUES_SYSTEMS:
            continue
        systems[name] = parse_documentation((SOURCE / name).read_text(encoding="utf-8-sig"))
    return systems


def handwritten_types(root):
    """收集上游手工类型定义的声明名，供类型解析使用。

    输入目录缺失时返回空集：那时生成产出会退化为全部降级，但不会产出错误注解。
    """
    names = set()
    for folder in HANDWRITTEN_DIRS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.lua"):
            names.update(DECLARATION.findall(path.read_text(encoding="utf-8", errors="replace")))
    return names


def enum_names(root):
    """收集枚举名，供 `Enum.` 前缀判定使用。"""
    path = root / ENUM_DATA
    if not path.is_file():
        return set()
    return set(ENUM_NAME.findall(path.read_text(encoding="utf-8", errors="replace")))


def widget_mapping():
    """上游 `doc_widgets.lua` 的「内部名 → 公开部件名」映射。

    暴雪文档里部件系统叫 `SimpleFrameAPI`、`FrameAPICooldown`，公开名是 `Frame`、
    `Cooldown`。这份对应关系是上游手工维护的，无法从文档推导。
    """
    if not UPSTREAM_DOC_WIDGETS.is_file():
        return {}
    return dict(WIDGET_MAPPING.findall(UPSTREAM_DOC_WIDGETS.read_text(encoding="utf-8", errors="replace")))


# 上游声明部件与脚本对象方法的两个目录；只扫 `Widget/` 会漏掉
# `ScriptObject/` 里的同类方法，导致重复产出。
METHOD_DIRS = ("Widget", "ScriptObject")


def collect_upstream_methods(root):
    """收集上游已声明的部件方法名，用于避免重复产出。"""
    methods = set()
    for folder in METHOD_DIRS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.lua"):
            methods.update(METHOD_NAME.findall(path.read_text(encoding="utf-8", errors="replace")))
    return methods


def apply_patches(name, system):
    """按上游 loader/patches.lua 的规则修正文档里的类型。"""
    file_patches = PATCHES.get(name)
    if not file_patches:
        return
    for node in system.get("Functions", Table()).entries:
        target = file_patches.get(node.get("Name"))
        if not target:
            continue
        for section, by_name in target.items():
            for param in node.get(section, Table()).entries:
                fix = by_name.get(param.get("Name"))
                if fix:
                    param.update(fix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="只校验产出与磁盘一致，不写文件")
    parser.add_argument("--report", action="store_true",
                        help="输出覆盖率报告")
    args = parser.parse_args()

    systems = load_systems()
    upstream = ROOT / ".tools/wow-api/Annotations/Core"
    generator = Generator(systems, handwritten_types(upstream), enum_names(upstream),
                          widget_mapping(), collect_upstream_methods(upstream))
    outputs, skipped = generator.build()
    scripts, _ = generator.script_methods()

    for name in toc_files():
        if name not in outputs and name not in skipped:
            raise ValueError(f"清单文件未产出也未跳过：{name}")

    if args.report:
        covered = len(outputs) + len(skipped)
        methods = sum(len(generator.systems[n].get("Functions", Table()).entries)
                      for n in scripts)
        print(f"清单文件 {len(toc_files())}；产出 {len(outputs)}；跳过 {len(skipped)}；合计 {covered}")
        print(f"部件方法额外产出 {len(scripts)} 个文件，覆盖上游未收录的方法 {methods} 个")
        return

    for folder, produced in ((OUTPUT, outputs), (SCRIPT_OUTPUT, scripts)):
        if args.check:
            problems = [name for name, text in produced.items()
                        if not (folder / name).is_file()
                        or (folder / name).read_text(encoding="utf-8") != text]
            if problems:
                raise ValueError(f"注解产出与磁盘不一致，请重新生成：{problems[:5]}")
            continue
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.glob("*.lua"):
            if stale.name not in produced:
                stale.unlink()
        for name, text in produced.items():
            (folder / name).write_text(text, encoding="utf-8", newline="\n")

    if args.check:
        print(f"注解产出已是最新：{len(outputs)} + {len(scripts)} 个文件")
        return
    print(f"已生成 {len(outputs)} 个 API 注解、{len(scripts)} 个部件方法文件")


if __name__ == "__main__":
    main()
