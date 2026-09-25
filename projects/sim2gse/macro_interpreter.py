"""有限的宏解释器；只模拟已明确覆盖的命令和场景条件。"""

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def _condition(expression, path, *, pet_ready=True, enemy_target_ready=True):
    """求值本期明确的默认场景；未知条件绝不猜测。"""
    if not expression:
        return True
    outcomes = []
    for token in expression.split(","):
        token = token.strip().lower()
        if token in {"nomod", "@player"}:
            outcomes.append(True)
        elif token in {"combat", "nocombat"}:
            outcomes.append(None)
        elif token == "dead" or token.startswith("mod:"):
            outcomes.append(False)
        elif token in {"harm", "nodead", "exists", "@target"}:
            outcomes.append(enemy_target_ready)
        elif token == "noharm":
            outcomes.append(not enemy_target_ready)
        elif token == "pet":
            outcomes.append(pet_ready)
        elif token == "nopet":
            outcomes.append(not pet_ready)
        elif token == "noexists":
            outcomes.append(not enemy_target_ready)
        else:
            outcomes.append(None)
    if False in outcomes:
        return False
    if None in outcomes:
        raise ValueError(f"GSE {path} 的宏条件不能确定：[{expression}]")
    return True


def _macro_commands(text, path, *, pet_ready=True, enemy_target_ready=True):
    """按运行顺序解析可达宏行；预检和编译共用大小写及 stopmacro 规则。"""
    if not isinstance(text, str):
        raise ValueError(f"GSE {path} 的宏文本无效")
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        line_path = f"{path}[行 {line_number}]"
        if line.casefold().startswith("/targetenemy"):
            if not re.fullmatch(r"/targetenemy \[noharm\]\[dead\]", line, re.IGNORECASE):
                raise ValueError(f"GSE {line_path} 的 targetenemy 写法不能忠实模拟：{line[:80]}")
            yield "targetenemy", None, "", line_path, line
            continue
        match = re.fullmatch(
            r"/(cast|use|startattack|petattack|petassist|stopmacro)\s*(?:\[([^]]+)\])?\s*(.*)",
            line, re.IGNORECASE)
        if not match:
            raise ValueError(f"GSE {line_path} 的宏命令不能忠实模拟：{line[:80]}")
        command, condition, argument = match.groups()
        command = command.lower()
        if condition and not _condition(condition, line_path, pet_ready=pet_ready,
                                        enemy_target_ready=enemy_target_ready):
            continue
        yield command, condition, argument, line_path, line
        if command == "stopmacro" and not argument:
            break


def preflight_macro(text, source_path):
    """检查可静态判断的宏语法；角色技能是否可用留给启动时核验。"""
    for command, condition, argument, line_path, line in _macro_commands(text, source_path):
        if command == "targetenemy":
            continue
        if command == "stopmacro" and not argument:
            continue
        if command == "cast" and argument:
            continue
        if command == "use" and argument in {"13", "14"}:
            continue
        if command == "startattack" and not argument:
            continue
        if command in {"petattack", "petassist"} and not argument:
            raise ValueError(f"GSE /{command} 命令不能忠实模拟（位置：{line_path}）")
        raise ValueError(f"GSE {line_path} 的宏命令不能忠实模拟：{line[:80]}")


def _spell_name_key(name):
    return re.sub(r"\s+", "_", str(name).strip()).casefold()


def map_action(kind, value, actions, source_path):
    def matches(action):
        if action.get("kind") != kind:
            return False
        if kind == "spell":
            values = {_spell_name_key(action[key]) for key in
                      ("spell_id", "native_spell_id", "name", "native_name", "simc_action")
                      if action.get(key) is not None}
            return _spell_name_key(value) in values
        normalized = value.casefold()
        slots = {"13": 13, "14": 14, "trinket1": 13, "trinket2": 14}
        if normalized in slots:
            return action.get("slot") == slots[normalized]
        if normalized.isdecimal():
            return str(action.get("item_id", "")).casefold() == normalized
        return normalized == str(action.get("name", "")).casefold()

    found = [action["simc_action"] for action in actions if matches(action)]
    if kind == "spell":
        # A numeric GSE spell may compile to its SimC alias, which is also
        # present in the baseline catalogue under the native spell ID.
        # Multiple rows are still unambiguous when all resolve to one action.
        found = list(dict.fromkeys(found))
    if len(found) == 1:
        return found
    raise ValueError(f"GSE {source_path} 的 {kind} {value} 不能映射到当前角色")


def map_macro(text, source_path, scenario, actions):
    """将宏原文按给定场景映射到角色动作目录。"""
    pet_ready = scenario.get("pet_ready", True)
    enemy_target_ready = scenario.get("enemy_target_ready", False)
    block = []
    for command, condition, argument, line_path, line in _macro_commands(
            text, source_path, pet_ready=pet_ready,
            enemy_target_ready=enemy_target_ready):
        if command == "targetenemy":
            if not enemy_target_ready:
                raise ValueError(f"GSE {line_path} 的敌方目标状态未确认，不能跳过 targetenemy")
            continue
        if command == "stopmacro" and not argument:
            continue
        if command in {"petattack", "petassist"} and not argument:
            raise ValueError(f"GSE /{command} 命令不能忠实模拟（位置：{line_path}）")
        if command == "cast" and argument:
            if condition and "@player" in condition.lower():
                spell = next((action for action in actions
                              if str(action.get("spell_id")) == argument or
                              str(action.get("native_spell_id")) == argument or
                              _spell_name_key(action.get("name", "")) == _spell_name_key(argument) or
                              _spell_name_key(action.get("simc_action", "")) == _spell_name_key(argument)), None)
                targeting = json.loads((ROOT / "projects/sim2gse/compatibility/spell-target-masks.json")
                                       .read_text(encoding="utf-8"))
                if spell is None or not (targeting["target_masks"].get(str(spell.get("spell_id")), 0) & 64):
                    raise ValueError(f"GSE {line_path} 的 @player 目标不能按当前角色验证")
            block += map_action("spell", argument, actions, source_path)
            continue
        if command == "use" and argument in {"13", "14"}:
            block += map_action("item", argument, actions, source_path)
            continue
        if command == "startattack" and not argument:
            found = [action["simc_action"] for action in actions
                     if action.get("kind") == "start_attack"]
            if len(found) == 1:
                block += found
                continue
        raise ValueError(f"GSE {line_path} 的宏命令不能忠实模拟：{line[:80]}")
    return block


def macro_spell_ids(text):
    if not isinstance(text, str):
        return []
    return sorted({spell_id for match in re.finditer(
        r"(?im)^\s*/cast\b(?:(?:\s*\[[^]\r\n]*\]))*\s+(\d+)(?=\s|$)", text)
                   if (spell_id := int(match.group(1))) > 0})


def macro_spell_names(text):
    if not isinstance(text, str):
        return []
    names = {}
    for match in re.finditer(
            r"(?im)^\s*/cast\b(?:(?:\s*\[[^]\r\n]*\]))*\s+([^\r\n]+?)\s*$", text):
        name = match.group(1).strip()
        if (not name or name.isdecimal() or len(name) > 128
                or any(ord(character) < 32 or ord(character) == 127 for character in name)):
            continue
        names.setdefault(name.casefold(), name)
    return sorted(names.values(), key=str.casefold)
