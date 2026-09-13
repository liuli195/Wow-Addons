"""遗漏测试入口必须使统一验证失败；辅助模块显式列出调用者。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = {
    'tests/gear-planner/test-page.cjs': 'tests/gear-planner/check-async.js',
    'tests/sim2gse/research/prototype-export.lua': 'tests/sim2gse/research/prototype-export.py',
}


def main():
    config = json.loads((ROOT / '.build-and-verify/config.json').read_text())
    commands = '\n'.join(str(c['command']).replace('\\', '/') for c in config['verify']['checks'])
    missing = []
    for path in (ROOT / 'tests').rglob('*'):
        if path.suffix not in ('.py', '.js', '.cjs', '.lua') or '__pycache__' in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in HELPERS:
            assert (ROOT / HELPERS[relative]).is_file(), relative
            continue
        discovered = (path.parent == ROOT / 'tests/sim2gse' and path.match('test_*.py')
                      and '-m unittest discover -s tests/sim2gse -p test_*.py' in commands)
        if relative not in commands and not discovered:
            missing.append(relative)
    assert not missing, '未接入统一验证的测试：\n' + '\n'.join(sorted(missing))
    for manifest in (ROOT / 'projects/gear-planner/fixtures').glob('raidbots-*/manifest.json'):
        name = manifest.parent.name
        # 治疗/实验资料由各自专用检查解释，不套用常规职业回放协议。
        if name.endswith(('-healer', '-experimental')):
            continue
        fixture = manifest.parent.relative_to(ROOT).as_posix()
        for engine in ('simc-1210.01.c1935b9-win64/simc.exe',
                       'simulationcraft-simc-b845947/engine/simc.exe'):
            assert any('--fixtures ' + fixture in str(c['command']) and engine in str(c['command'])
                       for c in config['verify']['checks']), (fixture, engine)
        assert any('run_browser_check.py tests/gear-planner/check-deathknight.cjs fixtures/' + name
                   in str(c['command']) for c in config['verify']['checks']), fixture
    print('PASS: 所有测试入口均已登记')


if __name__ == '__main__':
    main()
