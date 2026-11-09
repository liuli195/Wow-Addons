"""Read only the installed reference data contract; never load addon entry points."""
import hashlib
import json
from pathlib import Path
import re

from runtime import TaskRuntime, run_command

VERSION = 'gearinsight-openers-v1'
FAMILY = 'gearinsight-library-v1'
PREFIX = 'gearinsight:unholy:'
MAX_INPUT = 2 * 1024 * 1024
TOKEN = re.compile(r'''\s+|--[^\r\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[A-Za-z_]\w*|[{}\[\]=,.]''')


def static_table(text):
    """A narrow literal gate, not a general Lua parser or an OS sandbox."""
    tokens, offset = [], 0
    for match in TOKEN.finditer(text):
        if match.start() != offset:
            raise ValueError('参考库不是支持的静态资料表格式')
        offset = match.end()
        value = match.group()
        if not value.isspace() and not value.startswith('--'):
            tokens.append(value)
    if offset != len(text) or tokens[:3] != ['GearInsightRotation', '=', '{'] or tokens[-1:] != ['}']:
        raise ValueError('参考库不是支持的静态资料表格式')
    def literal(start):
        stack = []
        for index in range(start, len(tokens)):
            token = tokens[index]
            if token in ('{', '['):
                stack.append(token)
                if len(stack) > 32:
                    raise ValueError('静态资料表嵌套过深')
            elif token in ('}', ']'):
                if not stack or stack.pop() != ('{' if token == '}' else '['):
                    raise ValueError('静态资料表括号不匹配')
                if not stack:
                    return index + 1
            elif token == '.':
                raise ValueError('静态资料表不能调用外部变量')
            elif re.fullmatch(r'[A-Za-z_]\w*', token) and token not in ('true', 'false', 'nil'):
                if index + 1 >= len(tokens) or tokens[index + 1] != '=':
                    raise ValueError('静态资料表不能读取或调用外部变量')
        raise ValueError('静态资料表没有结束')
    end = literal(2)
    seen = set()
    while (end < len(tokens) and tokens[end:end + 2] == ['GearInsightRotation', '.']
           and tokens[end + 2:end + 3] in (['notes'], ['sources'])
           and tokens[end + 3:end + 5] == ['=', '{']):
        if tokens[end + 2] in seen:
            raise ValueError('静态附表重复赋值')
        seen.add(tokens[end + 2])
        end = literal(end + 4)
    if end != len(tokens):
        raise ValueError('静态资料表后存在额外逻辑')


def read(plugin_dir, destination, *, runtime=None):
    from codec import LUA
    plugin_dir, destination = Path(plugin_dir).resolve(), Path(destination).resolve()
    if (plugin_dir / 'GearInsight_Data').is_dir():
        plugin_dir /= 'GearInsight_Data'
    source, toc = plugin_dir / 'RotationData.lua', plugin_dir / 'GearInsight_Data.toc'
    if source.stat().st_size > MAX_INPUT or toc.stat().st_size > 128 * 1024:
        raise ValueError('参考库文件超过读取上限')
    raw, toc_raw = source.read_bytes(), toc.read_bytes()
    if len(raw) > MAX_INPUT or len(toc_raw) > 128 * 1024:
        raise ValueError('参考库文件超过读取上限')
    text = raw.decode('utf-8-sig')
    static_table(text)
    file_sha = hashlib.sha256(raw).hexdigest()
    snapshot = destination / file_sha
    snapshot.mkdir(parents=True, exist_ok=True)
    frozen = snapshot / 'RotationData.lua'
    frozen.write_text(text, encoding='utf-8')
    (snapshot / 'GearInsight_Data.toc').write_bytes(toc_raw)
    runtime = runtime or TaskRuntime(15)
    result = run_command([str(LUA), str(Path(__file__).with_name('gearinsight_reference.lua')), str(frozen)],
                         snapshot, runtime=runtime, timeout_seconds=min(15, runtime.remaining_seconds),
                         output_dir=snapshot / 'export')
    if result.returncode:
        raise ValueError('静态参考库导出失败: ' + result.stderr.decode('utf-8', errors='replace')[-500:])
    if len(result.stdout) > MAX_INPUT:
        raise ValueError('参考库导出超过上限')
    records = json.loads(result.stdout)
    if not isinstance(records, list) or not 1 <= len(records) <= 256:
        raise ValueError('新版邪恶参考库为空或记录过多')
    merged = {}
    for row in records:
        seq = row.get('record', {}).get('seq')
        if (not isinstance(seq, list) or not 1 <= len(seq) <= 128
                or any(type(value) is not int or value <= 0 for value in seq)):
            raise ValueError('新版参考库技能顺序格式无效')
        merged.setdefault(tuple(seq), dict(seq=seq, origins=[]))['origins'].append(row)
    version = re.search(r'^## Version:\s*(.+)$', toc_raw.decode('utf-8-sig'), re.MULTILINE)
    return dict(version=VERSION, addon_version=version[1].strip() if version else None,
                source=str(source), source_sha256=file_sha, toc=str(toc),
                toc_sha256=hashlib.sha256(toc_raw).hexdigest(),
                raw_records=len(records), distinct_sequences=len(merged), records=list(merged.values()))


def sources(plugin, definition, groups):
    """Reviewed old cleaning map, with explicit rejection of new unknown buttons."""
    from search import digest
    mapping = {77575: 'outbreak', 85948: 'festering_strike', 458128: 'festering_strike',
        316239: 'festering_strike', 1242174: 'death_coil', 47541: 'death_coil',
        433895: 'scourge_strike', 55090: 'scourge_strike', 1247378: 'putrefy',
        1233448: 'dark_transformation', 42650: 'army_of_the_dead', 343294: 'soul_reaper',
        207317: 'epidemic', 43265: 'death_and_decay'}
    removed = {1297761: '装备项', 444347: '移动', 48265: '移动', 48707: '防御',
               49039: '防御', 48792: '防御', 49576: '死亡之握'}
    removed.update({spell: '已审核独立爆发' for spell in definition['excluded_spell_ids']})
    output = []
    identity = {k: v for k, v in plugin.items() if k != 'records'}
    for index, record in enumerate(plugin['records']):
        program, changes, unknown = [], [], []
        for position, spell in enumerate(record['seq']):
            if spell in removed:
                changes.append(f'{position}:移除{spell}（{removed[spell]}）')
            elif spell in mapping:
                program.append([mapping[spell]])
                changes.append(f'{position}:{spell}→{mapping[spell]}（已审清洗映射）')
            else:
                unknown.append(spell)
                changes.append(f'{position}:未知按钮{spell}，整条材料不准入')
        source_id = PREFIX + digest(record['seq'])
        row = dict(candidate_id=digest(source_id), source_id=source_id,
            label=f'GearInsight新版起手 {index + 1}', class_name='deathknight', spec='unholy',
            source='GearInsight RotationData / WCL reference library',
            original=json.dumps(dict(dataset=identity, **record), ensure_ascii=False),
            instructions='成功施放起手改写为重复单动作列表；不是原玩家完整按键或循环宏',
            semantic='unsupported' if unknown or not program else 'rewritten', changes=changes,
            family=FAMILY, core=[], program=program, active=bool(program and not unknown),
            unavailable_reason=('未知按钮:' + ','.join(map(str, sorted(set(unknown))))) if unknown
                               else '' if program else '清洗后无普通动作', allowed_groups=groups)
        output.append(dict(row, source_revision=digest(row)))
    return output
