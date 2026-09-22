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
    spells = {str(a['spell_id']): a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'spell'}
    spells.update({a['name']: a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'spell'})
    items = {str(a['slot']): a['simc_action'] for b in candidate['blocks'] for a in b if a['kind'] == 'item'}
    blocks = []
    for step in candidate['compiled_steps']:
        if step['type'] == 'spell':
            block = [spells[str(step['spell'])]]
        elif step['type'] == 'item':
            block = [items[str(step['item'])]]
        elif step['type'] == 'macro':
            block = []
            for line in step['macrotext'].splitlines():
                if line == '/startattack':
                    block.append(next(a['simc_action'] for b in candidate['blocks'] for a in b if a['kind']=='start_attack'))
                elif line.startswith('/cast '):
                    block.append(spells[re.sub(r'^\[[^]]+\] ', '', line[6:])])
                elif re.fullmatch(r'/use (?:\[[^]]+\] )?(13|14)', line):
                    block.append(items[line.split()[-1]])
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
             mode='controlled', input_times=None, runtime=None, simulation_config=None):
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
    generated.write_text(Path(profile).read_text(encoding='utf-8') + '\n'
                         + 'actions.sim2gse=' + '/'.join(pool) + '\n'
                         + f'sim2gse_steps={indices}\nsim2gse_trace={int(trace)}\n'
                         + 'sim2gse_times=' + '/'.join(map(str, input_times)) + '\n', encoding='utf-8')
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
            ms, event, origin, step, action, gcd, rp, health, cooldown, battle, signature, cast_ms = line.split('S2GSE\t', 1)[1].split('\t')
            events.append(dict(ms=float(ms), event=event, origin=int(origin), step=int(step), action=action,
                               gcd=float(gcd), rp=float(rp), health=float(health), cooldown_ms=float(cooldown),
                               battle=int(battle), signature=signature, cast_ms=float(cast_ms)))
    if trace:
        inputs = [e for e in events if e['event'] == 'input']
        executed = [e for e in events if e['event'] == 'native_execute']
        interrupted = [e for e in events if e['event'] == 'native_interrupt']
        if not inputs or inputs[0]['ms'] != input_times[0] or not executed:
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
    return dict(blocks=blocks, native_blocks=native_blocks, input_times=input_times, consistent=True, summary=summary, report=report, trace=events,
                game_validation='not_run', model='native_controlled')
