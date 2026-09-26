"""按游戏实测编码向量导出并核对上游编译；完整游戏导入仍须验收。"""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import zlib
import cbor2
from runtime import BudgetExceeded, ProcessTimeout, TaskCancelled, TaskRuntime, run_command

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.tools/sim2gse-research/gse-f225d4c'
LUA = ROOT / '.tools/lua-5.1.5/src/lua.exe'


def wire_value(value):
    """游戏 Lua 字符串对应 CBOR 字节串，包含表的字符串键。"""
    if isinstance(value, str):
        return value.encode('utf-8')
    if isinstance(value, list):
        return [wire_value(v) for v in value]
    if isinstance(value, dict):
        return {wire_value(k): wire_value(v) for k, v in value.items()}
    return value


def lua_literal(value):
    if isinstance(value, str):
        return '"' + ''.join(f'\\{byte:03d}' for byte in value.encode('utf-8')) + '"'
    if type(value) is bool:
        return str(value).lower()
    if type(value) in (int, float):
        return str(value)
    items = enumerate(value, 1) if isinstance(value, list) else value.items()
    return '{' + ','.join(f'[{lua_literal(k)}]={lua_literal(v)}' for k, v in items) + '}'


def export(blocks, folder, *, identity, runtime=None, program=None):
    """同一动作块产生编码对象和编译断言，不改变块顺序。"""
    runtime = runtime or TaskRuntime()
    runtime.check()
    lock = json.loads((ROOT / 'projects/sim2gse/compatibility/lock.json').read_text())
    for path, expected_hash in lock['gse_sources'].items():
        runtime.check()
        source = (SOURCE / path).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(source).hexdigest() != expected_hash:
            raise ValueError('固定上游编译器源码已变化')
    target_source = lock['client_targeting']
    target_path = ROOT / target_source['path']
    if hashlib.sha256(target_path.read_bytes()).hexdigest() != target_source['sha256']:
        raise ValueError('客户端目标数据与兼容锁不符')
    targeting = json.loads(target_path.read_text(encoding='utf-8'))
    def ground(command):
        spell = command.get('spell_id') if command['kind'] == 'spell' else command.get('driver_spell_id')
        return bool(targeting['target_masks'].get(str(spell), 0) & 64)
    def encode_block(block):
        if not block:
            raise ValueError('动作块不能为空')
        if len(block) > 1 or any(ground(c) or c.get('condition') for c in block):
            lines, translated = [], []
            for command in block:
                if command['kind'] == 'spell':
                    conditions = [*(['@player'] if ground(command) else []),
                                  *([command['condition']] if command.get('condition') else [])]
                    prefix = '/cast ' + (f"[{','.join(conditions)}] " if conditions else '')
                    lines.append(prefix + str(command['spell_id']))
                    translated.append(prefix + command['name'])
                elif command['kind'] == 'item':
                    conditions = [*(['@player'] if ground(command) else []),
                                  *([command['condition']] if command.get('condition') else [])]
                    lines.append('/use ' + (f"[{','.join(conditions)}] " if conditions else '') + str(command['slot']))
                    translated.append(lines[-1])
                elif command['kind'] == 'start_attack':
                    lines.append('/startattack')
                    translated.append(lines[-1])
                else:
                    raise ValueError('无法导出的同块动作')
            macro = '\n'.join(lines)
            if max(len(macro.encode('utf-8')), len('\n'.join(translated).encode('utf-8'))) > 255:
                raise ValueError('同块宏文本超过 255 字节')
            return dict(Type='Action', type='macro', macro=macro), \
                dict(type='macro', macrotext='\n'.join(translated))
        command = block[0]
        if command['kind'] == 'spell':
            action = dict(type='spell', spell=command['spell_id'])
            step = dict(action)
        elif command['kind'] == 'item':
            action = dict(type='item', item=command['slot'])
            step = dict(action)
        elif command['kind'] == 'start_attack':
            action = dict(type='macro', macro='/startattack')
            step = dict(type='macro', macrotext='/startattack')
        else:
            raise ValueError('无法导出的动作')
        return dict(Type='Action', **action), step

    actions, steps, upstream_steps = [], [], []
    if program is None:
        for index, block in enumerate(blocks, 1):
            action, step = encode_block(block)
            actions.append(action)
            steps.append(step)
            upstream_steps.append(dict(step, blockPath=str(index)))
    else:
        if program.get('adapter') != 'search' or not isinstance(program.get('nodes'), list):
            raise ValueError('搜索导出程序结构无效')
        expanded_count = 0
        for index, node in enumerate(program['nodes'], 1):
            runtime.check()
            source = node.get('source')
            if not isinstance(source, dict):
                raise ValueError('搜索导出节点缺少来源位置')
            if node.get('kind') == 'Action':
                action, step = encode_block(node.get('commands'))
                actions.append(action)
                steps.append(step)
                upstream_steps.append(dict(step, blockPath=source.get('gse_path', str(index))))
            elif node.get('kind') == 'Loop':
                body = node.get('body')
                count = node.get('count')
                if (node.get('step_function') != 'Sequential' or type(count) is not int
                        or count < 1 or not isinstance(body, list) or not body):
                    raise ValueError('搜索只支持有效的 Sequential Loop')
                if expanded_count + count * len(body) > 4096:
                    raise ValueError('搜索程序展开超过 4096 次按键')
                loop = dict(Type='Loop', Repeat=str(count), StepFunction='Sequential')
                body_steps = []
                for child_index, child in enumerate(body, 1):
                    if child.get('kind') != 'Action' or not isinstance(child.get('source'), dict):
                        raise ValueError('搜索 Loop 只支持有来源位置的动作块')
                    action, step = encode_block(child.get('commands'))
                    loop[child_index] = action
                    body_steps.append((step, child['source'].get(
                        'gse_path', f"{source.get('gse_path', index)}.{child_index}")))
                actions.append(loop)
                for _ in range(count):
                    for step, gse_path in body_steps:
                        steps.append(step)
                        upstream_steps.append(dict(step, blockPath=gse_path))
                expanded_count += count * len(body)
            else:
                raise ValueError('搜索导出包含不支持的节点')
        if len(steps) != len(blocks):
            raise ValueError('搜索导出计划与动作块数量不一致')
    if not 1 <= len(actions) <= 128:
        raise ValueError('动作块数量必须在 1 至 128 之间')
    name_basis = blocks if program is None else actions
    name = 'S2G_' + hashlib.sha256(cbor2.dumps(name_basis)).hexdigest()[:12].upper()
    sequence = dict(MetaData=dict(Name=name, SpecID=identity['spec_id'], GSEVersion=3332,
                                 Help='地面技能在角色脚下释放，目标须在范围内；目标数据 '+targeting['client_build']+'，模拟数据 12.1.0.69587。游戏效果尚待验证。'),
                    Default=1, Versions=[dict(Actions=actions, InbuiltVariables={})])
    payload = [name, sequence]
    expected = dict(name=name, help=sequence['MetaData']['Help'], steps=upstream_steps, identity=identity,
                    spells={c['spell_id']: c['name'] for b in blocks for c in b if c['kind'] == 'spell'})
    folder.mkdir(parents=True, exist_ok=True)

    def compile(mode):
        runtime.check()
        input_data = cbor2.dumps(wire_value(payload))
        expected_text = 'return ' + lua_literal(dict(expected, payload=payload))
        (folder / 'input.cbor').write_bytes(input_data)
        (folder / 'expected.lua').write_text(expected_text, encoding='utf-8')
        staging_root = ROOT / '.local/sim2gse/codec'
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='gse-', dir=staging_root) as temporary:
            staging = Path(temporary)
            (staging / 'input.cbor').write_bytes(input_data)
            (staging / 'expected.lua').write_text(expected_text, encoding='utf-8')
            relative = lambda path: path.relative_to(ROOT).as_posix()
            try:
                proc = run_command([str(LUA), relative(Path(__file__).with_suffix('.lua')), relative(SOURCE),
                                    relative(staging / 'input.cbor'), relative(staging / 'expected.lua'), mode],
                                   ROOT, timeout_seconds=20, runtime=runtime, output_dir=folder)
            except ProcessTimeout as error:
                raise ValueError('上游编译校验超时，任务已停止') from error
            except (TaskCancelled, BudgetExceeded):
                raise
        log = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
        (folder / (mode + '.log')).write_text(log, encoding='utf-8')
        if proc.returncode:
            raise ValueError('上游编译校验失败，参见 ' + str(folder / (mode + '.log')))
        return log

    sequence['MetaData']['Checksum'] = next(row.split('\t')[1] for row in compile('checksum').splitlines()
                                            if row.startswith('CHECKSUM\t'))
    encoded = cbor2.dumps(wire_value(payload))
    text = '!GSE3!' + base64.b64encode(zlib.compress(encoded, wbits=-15)).decode('ascii')
    if cbor2.loads(zlib.decompress(base64.b64decode(text[6:], validate=True), -15)) != wire_value(payload):
        raise ValueError('编码往返改变了序列')
    if 'PASS\t' not in compile('compile'):
        raise ValueError('上游编译校验没有成功记录')
    return dict(text=text, blocks=blocks, compiled_steps=steps,
                precombat_count=sum(all(c.get('condition') == 'nocombat' for c in block) for block in blocks),
                simulation='not_run', game_validation='not_run',
                targeting_build=targeting['client_build'], ground_location='player',
                encoding='raw_deflate_cbor_bytes_client_vector', upstream_compilation='passed_with_client_boundary_stubs')
