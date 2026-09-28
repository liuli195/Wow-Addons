"""同一编译动作块的原生评估，不复制伤害模型。"""
import json
import os
from pathlib import Path
import re
from collections import Counter
from engine import run, check_report, player_report, CandidateError
from runtime import replace_file
from runtime import TaskRuntime
from simulation_config import config_for


def select(capabilities, program=None):
    available = {a['simc_action']: a for a in capabilities['actions']}
    program = program if program is not None else [[name] for name in available]
    if not isinstance(program, list) or not 1 <= len(program) <= 128:
        raise ValueError('程序必须包含 1 至 128 个动作块')
    blocks = [[dict(action, condition='nocombat')] for action in capabilities.get('precombat_actions', [])]
    for block in program:
        if not isinstance(block, list) or not block or len(block) > 16:
            raise ValueError('动作块必须包含 1 至 16 个命令')
        if any(not isinstance(name, str) or name not in available for name in block):
            raise ValueError('程序包含当前角色不支持的动作')
        commands = [a for name in block for a in available[name].get('variants', [available[name]])]
        if len(commands) > 16:
            raise ValueError('展开后的动作块超过 16 个命令')
        if len({a.get('base_spell_id', a['simc_action']) for a in commands if a.get('gcd_ms',0)>0}) > 1:
            raise ValueError('同块多个公共冷却动作尚不支持')
        blocks.append(commands)
    return blocks


def compiled_program(candidate):
    """解释已通过上游编译检查的命令，核对实际消费顺序。"""
    shared = candidate.get("compiled_program")
    if shared is not None:
        clicks = []
        for node in shared.get("clicks", []):
            if not isinstance(node, dict) or not isinstance(node.get("source"), dict):
                raise ValueError("共享编译计划缺少来源位置")
            if node.get("kind") == "EmptyClick":
                clicks.append([])
            elif (node.get("kind") == "Action" and isinstance(node.get("commands"), list)
                  and node["commands"]
                  and all(isinstance(command, str) and command for command in node["commands"])):
                clicks.append(node["commands"])
            else:
                raise ValueError("共享编译计划包含无效点击")
        if len(clicks) != len(candidate.get("compiled_steps", [])):
            raise ValueError("共享编译计划与上游步骤数量不一致")
        if "mapped_blocks" in candidate:
            if clicks != candidate["mapped_blocks"]:
                raise ValueError("共享编译计划与导入动作映射不一致")
        else:
            verified = _search_compiled_blocks(candidate)
            if clicks != verified:
                raise ValueError("共享编译计划与搜索编译步骤不一致")
        if not any(clicks):
            raise ValueError("序列没有可模拟动作")
        return clicks
    return _search_compiled_blocks(candidate)


def compiled_identity(candidate):
    """批次缓存身份；有状态宏必须带完整定义，避免不同规则复用成绩。"""
    blocks = compiled_program(candidate)
    castsequences = candidate.get("compiled_program", {}).get("castsequences", [])
    from program import canonical_behavior_form
    return canonical_behavior_form(blocks, castsequences)


def behavior_key(candidate):
    """给已编译的行为计划生成版本化、忽略来源位置的身份。"""
    identity = compiled_identity(candidate)
    from program import canonical_behavior_key
    return canonical_behavior_key(identity)


def _search_compiled_blocks(candidate):
    spells = {str(a['spell_id']): a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'spell'}
    spells.update({a['name']: a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'spell'})
    items = {str(a['slot']): a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'item'}
    blocks = []
    for step in candidate['compiled_steps']:
        if step['type'] == 'spell':
            block = [spells[str(step['spell'])]]
        elif step['type'] == 'item':
            block = [items[str(step['item'])]]
        elif step['type'] == 'click':
            block = []
        elif step['type'] == 'macro':
            block = []
            for line in step['macrotext'].splitlines():
                if line == '/startattack':
                    block.append(next(a['simc_action'] for b in candidate['blocks'] for a in b if a['kind']=='start_attack'))
                elif line.startswith('/cast '):
                    block.append(spells[re.sub(r'^\[[^]]+\] ', '', line[6:])])
                elif re.fullmatch(r'/use (?:\[[^]]+\] )?(13|14)', line):
                    block.append(items[line.split()[-1]])
                elif line.startswith('/castsequence '):
                    from macro_interpreter import parse_castsequence
                    actions = [action for candidate_block in candidate['blocks'] for action in candidate_block]
                    block.extend(parse_castsequence(line, 'compiled_steps', actions)['members'])
                else:
                    raise ValueError('上游编译产生了不支持的宏命令')
        else:
            raise ValueError('上游编译产生了不支持的步骤类型')
        blocks.append(block)
    expected = [[a['simc_action'] for a in b] for b in candidate['blocks']]
    if blocks != expected:
        raise ValueError('编译与模拟动作块顺序不一致')
    return blocks


def evaluate(profile, candidate, folder, *, character, iterations=100, seed=20260912, trace=True,
             mode='controlled', input_times=None, gcd_states=None, failed_actions=None,
             failure_events=None, reset_events=None,
             runtime=None, simulation_config=None):
    runtime = runtime or TaskRuntime()
    simulation_config = config_for(simulation_config)
    runtime.check()
    if mode != 'controlled':
        raise ValueError('原版引擎不兼容受控序列')
    input_times = list(range(0, 180000, 300)) if input_times is None else input_times
    if (not isinstance(input_times, list) or not 1 <= len(input_times) <= 4096 or
            any(type(t) is not int or not 0 <= t < 180000 for t in input_times) or
            any(b <= a for a, b in zip(input_times, input_times[1:]))):
        raise ValueError('输入时刻必须是战斗范围内递增的整数毫秒')
    if gcd_states is not None and (
            not isinstance(gcd_states, list) or len(gcd_states) != len(input_times) or
            any(not isinstance(state, tuple) or len(state) != 2 or
                any(type(value) is not int or value < 0 for value in state)
                for state in gcd_states)):
        raise ValueError('GCD 反馈必须与输入时刻一一对应，并使用非负整数毫秒')
    if failed_actions is not None and (
            not isinstance(failed_actions, list) or len(failed_actions) != len(input_times) or
            any(value is not None and (not isinstance(value, str) or not value)
                for value in failed_actions)):
        raise ValueError('失败反馈必须与输入时刻一一对应，并使用动作名或空值')
    if failure_events is not None and (
            failed_actions is not None or not isinstance(failure_events, list) or
            any(not isinstance(event, tuple) or len(event) != 3 or
                type(event[0]) is not int or not 0 <= event[0] < 180000 or
                type(event[1]) is not int or not 1 <= event[1] <= len(input_times) or
                not isinstance(event[2], str) or
                re.fullmatch(r'[a-z0-9_]+', event[2]) is None
                for event in failure_events)):
        raise ValueError('失败事件必须使用真实时刻、输入序号和动作名，且不能与旧式反馈混用')
    reset_kinds = {'target', 'combat', 'shift', 'ctrl', 'alt', 'death'}
    if reset_events is not None and (
            not isinstance(reset_events, list) or
            any(not isinstance(event, tuple) or len(event) != 2 or
                type(event[0]) is not int or not 0 <= event[0] < 180000 or
                event[1] not in reset_kinds or
                (event[1] in {'shift', 'ctrl', 'alt'} and event[0] not in input_times)
                for event in reset_events)):
        raise ValueError('/castsequence Reset 事件必须使用有效时刻和类型；修饰键须对应点击')
    blocks = compiled_program(candidate)
    precombat_count = candidate.get('precombat_count', 0)
    if not 0 <= precombat_count < len(blocks):
        raise ValueError('战前动作块数量无效')
    runtime_blocks = [[] if index < precombat_count else block for index, block in enumerate(blocks)]
    pool = list(dict.fromkeys(name for block in runtime_blocks for name in block))
    indices = '/'.join('0' if not block else '+'.join(str(pool.index(name) + 1) for name in block)
                       for block in runtime_blocks)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    generated = folder / 'input.simc'
    feedback = ('' if gcd_states is None else
                'sim2gse_gcd_states=' + '/'.join(f'{start},{duration}'
                                                  for start, duration in gcd_states) + '\n')
    feedback += ('' if failed_actions is None else
                 'sim2gse_failed_actions=' + '/'.join(value or '-' for value in failed_actions) + '\n')
    feedback += ('' if failure_events is None else
                 'sim2gse_timed_feedback=1\n'
                 + 'sim2gse_failure_events=' + '/'.join(f'{ms},{origin},{action}'
                                                     for ms, origin, action in failure_events) + '\n')
    castsequences = candidate.get('compiled_program', {}).get('castsequences', [])
    castsequence_option = ''
    if castsequences:
        rows = []
        seen_steps = set()
        for row in castsequences:
            step = row.get('step')
            members = row.get('members')
            if (type(step) is not int or not 0 <= step < len(runtime_blocks) or step in seen_steps
                    or not isinstance(members, list) or not 2 <= len(members) <= 32
                    or any(member not in pool for member in members)
                    or runtime_blocks[step] != members):
                raise ValueError('/castsequence 编译定义与按键计划不一致')
            seen_steps.add(step)
            reset = row.get('reset') or {}
            timeout = reset.get('timeout_seconds')
            timeout_ms = ''
            if timeout is not None:
                if type(timeout) is not int or not 1 <= timeout <= 2147483647:
                    raise ValueError('/castsequence reset 时间必须是正整数秒')
                timeout_ms = f':{timeout * 1000}'
            flags = reset.get('flags') or []
            flag_bits = {'target': 1, 'combat': 2, 'shift': 4, 'ctrl': 8, 'alt': 16}
            if (not isinstance(flags, list) or len(set(flags)) != len(flags) or
                    any(flag not in flag_bits for flag in flags)):
                raise ValueError('/castsequence reset 标志无效')
            if flags:
                timeout_ms = f':{timeout * 1000 if timeout is not None else 0}:' + str(
                    sum(flag_bits[flag] for flag in flags))
            rows.append(f"{step}:" + ','.join(str(pool.index(member) + 1) for member in members)
                        + timeout_ms)
        castsequence_option = 'sim2gse_castsequences=' + '/'.join(rows) + '\n'
    generated.write_text(Path(profile).read_text(encoding='utf-8') + '\n'
                         + 'actions.sim2gse=' + '/'.join(pool) + '\n'
                         + f'sim2gse_steps={indices}\nsim2gse_trace={int(trace)}\n'
                         + castsequence_option
                         + ('' if not reset_events else 'sim2gse_castsequence_events=' +
                            '/'.join(f'{ms},{kind}' for ms, kind in reset_events) + '\n')
                         + 'sim2gse_times=' + '/'.join(map(str, input_times)) + '\n'
                         + feedback, encoding='utf-8')
    pending_report = folder / 'native.pending.json'
    log = run(generated, folder, mode,
              [f'iterations={iterations}', f'seed={seed}', 'json2=native.pending.json'], runtime=runtime,
              simulation_config=simulation_config)
    native_blocks = []
    for line in log.splitlines():
        if not line.startswith('S2GBLOCK\t'):
            continue
        _, block, position, signature = line.split('\t')
        block, position = int(block), int(position)
        if position == -1 and signature == '-' and block == len(native_blocks):
            native_blocks.append([])
            continue
        if block == len(native_blocks) and position == 0:
            native_blocks.append([])
        if not native_blocks or block != len(native_blocks) - 1 or position != len(native_blocks[-1]):
            raise ValueError('原生动作块回报结构不符')
        native_blocks[block].append(signature)
    if native_blocks != runtime_blocks:
        raise ValueError('原生实际解析的动作块与编译结果不一致')
    try:
        pending_report = json.loads(pending_report.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('原生报告缺失或不是有效 JSON') from error
    # 只有完整解析成功的报告才进入正式名称；任务恢复时不会把半份文件当成成功批次。
    report = pending_report
    measured = (report['sim']['statistics']['raid_dps'] if len(report['sim']['players']) > 1
                else player_report(report, character)['collected_data']['dps'])
    if measured['mean'] == 0:
        raise CandidateError('合法候选没有有效伤害')
    summary = check_report(report, character, iterations, simulation_config=simulation_config)
    events = []
    if trace:
        for line in (folder / 'native.txt').read_text(encoding='utf-8').splitlines():
            if 'S2GSE\t' not in line:
                continue
            (ms, event, origin, step, action, gcd, rp, health, cooldown, battle, signature,
             cast_ms, sequence_step, sequence_member) = line.split('S2GSE\t', 1)[1].split('\t')
            events.append(dict(ms=float(ms), event=event, origin=int(origin), step=int(step), action=action,
                               gcd=float(gcd), rp=float(rp), health=float(health), cooldown_ms=float(cooldown),
                               battle=int(battle), signature=signature, cast_ms=float(cast_ms),
                               sequence_step=int(sequence_step), sequence_member=int(sequence_member)))
    if trace:
        inputs = [e for e in events if e['event'] == 'input']
        executed = [e for e in events if e['event'] == 'native_execute']
        interrupted = [e for e in events if e['event'] == 'native_interrupt']
        rolled_back = any(e['event'] == 'queue_rollback' for e in events)
        if any(e['event'] == 'late_negative_feedback' for e in events):
            raise ValueError('已执行后收到否定反馈，原生轨迹不可信')
        if not inputs or inputs[0]['ms'] != input_times[0] or (not executed and not rolled_back):
            raise ValueError('缺少原生输入或执行轨迹')
        if any(e['origin'] < 1 or e['origin'] > len(input_times) or e['ms'] != input_times[e['origin'] - 1]
               or e['step'] != (e['origin'] - 1) % len(blocks) for e in inputs):
            raise ValueError('原生输入轨迹的时刻、起点或步进不一致')
        dispatches = [e for e in events if e['event'] == 'dispatch']
        if any(not 1 <= e['origin'] <= len(input_times)
               or e['step'] != (e['origin'] - 1) % len(blocks)
               or e['signature'] not in runtime_blocks[e['step']]
               for e in dispatches + executed + interrupted):
            raise ValueError('原生动作不属于来源输入对应的编译块')
        by_step = {row['step']: row['members'] for row in castsequences}
        if any((e['sequence_step'] != e['step'] or
                not 0 <= e['sequence_member'] < len(by_step[e['step']]) or
                (e['event'] in {'dispatch', 'native_execute', 'native_interrupt'} and
                 e['action'] != by_step[e['step']][e['sequence_member']]))
               for e in events if e['step'] in by_step):
            raise ValueError('/castsequence 原生成员轨迹与编译定义不一致')
        expected_precombat = [block[0] for block in blocks[:precombat_count]]
        if expected_precombat:
            battles = {e['battle'] for e in events if e['event'] == 'input'}
            for battle in battles:
                observed = [e['action'] for e in events
                            if e['battle'] == battle and e['event'] == 'explicit_precombat'
                            and e['action'] in expected_precombat]
                if observed != expected_precombat:
                    raise ValueError('原生战前动作没有对应 GSE 战前步骤')
        def key(e):
            return e['battle'], e['origin'], e['step'], e['signature']
        starts = {key(e): e for e in dispatches}
        completed = executed + interrupted
        finishes = Counter(map(key, completed))
        pending = [e for e in dispatches if key(e) not in finishes and e['ms'] + e['cast_ms'] >= 180000]
        if (Counter(map(key, completed + pending)) != Counter(map(key, dispatches)) or
                any(e['ms'] < starts[key(e)]['ms'] for e in completed)):
            raise ValueError('原生派发与实际执行轨迹不一致')
    replace_file(folder / 'native.pending.json', folder / 'native.json')
    return dict(blocks=blocks, native_blocks=native_blocks, input_times=input_times,
                gcd_states=gcd_states, failed_actions=failed_actions,
                failure_events=failure_events, consistent=True,
                reset_events=reset_events,
                castsequences=castsequences,
                summary=summary, report=report, trace=events,
                game_validation='not_run', model='native_controlled')
