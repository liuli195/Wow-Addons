"""遗漏入口或不互补的普通/原生选择必须使统一验证失败。"""
import ast
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[2]
HELPERS = {
    'tests/conftest.py': 'tests/sim2gse/test_search.py',
    'tests/sim2gse/conftest.py': 'tests/sim2gse/test_search.py',
    'tests/sim2gse/legacy_training_fixture.py': 'tests/sim2gse/test_training_champion.py',
    'tests/sim2gse/champion_evidence_fixture.py': 'tests/sim2gse/test_formal_champion.py',
    'tests/gear-planner/test-page.cjs': 'tests/gear-planner/check-async.js',
    'tests/gear-planner/check-browser.cjs': 'tests/gear-planner/test_real.py',
    'tests/sim2gse/research/prototype-export.lua': 'tests/sim2gse/research/prototype-export.py',
    'tests/addons/MYUI_CrosshairHUD/wowtest_projection.py': 'tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py',
    'tests/addons/MYUI_CrosshairHUD/.wow-test/adapter.lua': 'tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py',
}
LOCAL_ACCEPTANCE = {
    'tests/gear-planner/research/check-cn-reference.py',
    'tests/gear-planner/research/check-deathknight-raidbots.py',
    'tests/gear-planner/research/check-epic-catalog.py',
    'tests/gear-planner/research/check-priest-experimental.py',
    'tests/gear-planner/research/check-tooltip-data.py',
    'tests/gear-planner/research/manual-mistweaver-history.py',
}


def local_acceptance(path):
    relative = path.relative_to(ROOT).as_posix()
    return (relative in LOCAL_ACCEPTANCE
            or relative.startswith('tests/sim2gse/manual_')
            or relative.startswith('tests/sim2gse/research/'))


def check_layers(checks, directory, ordinary_id, native_id):
    """One real collection, with configuration selectors constrained to complements."""
    import pytest
    for check_id, selector in ((ordinary_id, 'not real'), (native_id, 'real')):
        check = checks[check_id]
        parts = shlex.split(check['command'].replace('\\', '/'))
        assert parts[1:3] == ['-m', 'pytest'] and directory in parts, check_id
        assert parts.count('-m') == 2 and parts[parts.index('-m', 2) + 1] == selector, check_id
        assert '--strict-markers' in parts, check_id
        assert not any(part == '-k' or part.startswith(('--ignore', '--deselect', '--pyargs'))
                       for part in parts), f'{check_id}: 不得隐藏收集范围'
        assert not any(part.startswith('tests/') and part != directory for part in parts), check_id
    class Collected:
        def __init__(self):
            self.items = []
        def pytest_collection_modifyitems(self, items):
            self.items = list(items)
    collector = Collected()
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(output):
        result = pytest.main([str(ROOT / directory), '--collect-only', '-q', '-s',
                              '-p', 'no:cacheprovider', '--strict-markers'], plugins=[collector])
    assert result == 0, output.getvalue()
    all_ids = {item.nodeid for item in collector.items}
    ordinary = {item.nodeid for item in collector.items
                if item.get_closest_marker('real') is None}
    native = {item.nodeid for item in collector.items
              if item.get_closest_marker('real') is not None}
    assert len(all_ids) == len(collector.items) and ordinary and native, directory
    assert not ordinary & native and ordinary | native == all_ids, directory
    print(f'{directory}: {len(all_ids)} = {len(ordinary)} ordinary + {len(native)} real')


def main(config_path=None):
    config = json.loads(Path(config_path or ROOT / '.build-and-verify/config.json').read_text())
    checks = {check['id']: check for check in config['verify']['checks']}
    assert len(checks) == len(config['verify']['checks']), '验证ID不能重复'
    commands = '\n'.join(str(check['command']).replace('\\', '/') for check in checks.values())
    assert {'verify.sim2gse-real', 'verify.gear-real'} <= set(config['verify']['realChecks'])
    assert not ({'verify.sim2gse-unit', 'verify.gear-unit'} & set(config['verify']['realChecks']))
    check_layers(checks, 'tests/sim2gse', 'verify.sim2gse-unit', 'verify.sim2gse-real')
    check_layers(checks, 'tests/gear-planner', 'verify.gear-unit', 'verify.gear-real')
    build_source = ast.parse((ROOT / 'scripts/dev/sim2gse/build.py').read_text())
    build_modes = [ast.literal_eval(node.iter) for node in ast.walk(build_source)
                   if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                   and node.target.id == 'mode']
    assert build_modes == [('original', 'baseline', 'controlled')]
    assert {check['id'] for check in config['build']['checks']} == {
        'build.sim2gse-product', 'build.assets'}
    local_checks = [check['id'] for check in checks.values()
                    if any(path in check['command'].replace('\\', '/') for path in LOCAL_ACCEPTANCE)
                    or 'tests/sim2gse/manual_' in check['command']
                    or 'tests/sim2gse/research/' in check['command']]
    assert not local_checks, '手工历史/私人验收不得冒充自动验证: ' + ', '.join(local_checks)
    missing = []
    for path in (ROOT / 'tests').rglob('*'):
        if path.suffix not in ('.py', '.js', '.cjs', '.lua') or '__pycache__' in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in HELPERS:
            assert (ROOT / HELPERS[relative]).is_file(), relative
            continue
        if local_acceptance(path):
            continue
        discovered = (path.parent in (ROOT / 'tests/sim2gse', ROOT / 'tests/gear-planner')
                      and path.match('test_*.py'))
        if relative not in commands and not discovered:
            missing.append(relative)
    assert not missing, '未接入统一验证的测试:\n' + '\n'.join(sorted(missing))
    print('PASS: 全部自动测试已登记；普通/原生全集互补，手工入口明确区分')


if __name__ == '__main__':
    main()
