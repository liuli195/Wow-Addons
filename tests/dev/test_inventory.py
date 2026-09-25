"""遗漏测试入口必须使统一验证失败；辅助模块显式列出调用者。"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = {
    'tests/gear-planner/test-page.cjs': 'tests/gear-planner/check-async.js',
    'tests/sim2gse/research/prototype-export.lua': 'tests/sim2gse/research/prototype-export.py',
    'tests/addons/MYUI_CrosshairHUD/wowtest_projection.py': 'tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py',
    'tests/addons/MYUI_CrosshairHUD/.wow-test/adapter.lua': 'tests/addons/MYUI_CrosshairHUD/test_wowtest_dk.py',
}
LOCAL_ACCEPTANCE = {
    'tests/gear-planner/check-add-socket.py',
    'tests/gear-planner/check-browser.cjs',
    'tests/gear-planner/check-bulk-levels.py',
    'tests/gear-planner/check-catalog.py',
    'tests/gear-planner/check-deathknight.cjs',
    'tests/gear-planner/check-effects.py',
    'tests/gear-planner/check-enchants.py',
    'tests/gear-planner/check-extra-input.py',
    'tests/gear-planner/check-fit.py',
    'tests/gear-planner/check-gems.py',
    'tests/gear-planner/check-item-stats.py',
    'tests/gear-planner/check-levels.py',
    'tests/gear-planner/check-merge-selection.py',
    'tests/gear-planner/check-merge-slots.py',
    'tests/gear-planner/check-mistweaver.py',
    'tests/gear-planner/check-names.py',
    'tests/gear-planner/check-option-labels.py',
    'tests/gear-planner/check-original-item.py',
    'tests/gear-planner/check-replace-level.py',
    'tests/gear-planner/check-replace.py',
    'tests/gear-planner/check-sets.py',
    'tests/gear-planner/check-sources.py',
    'tests/gear-planner/check.py',
}


def local_acceptance(path):
    relative = path.relative_to(ROOT).as_posix()
    return (relative in LOCAL_ACCEPTANCE
            or relative.startswith('tests/sim2gse/manual_')
            or relative.startswith('tests/sim2gse/research/')
            or relative.startswith('tests/gear-planner/research/'))


def main():
    config = json.loads((ROOT / '.build-and-verify/config.json').read_text())
    commands = '\n'.join(str(c['command']).replace('\\', '/') for c in config['verify']['checks'])
    sim2gse = next(check for check in config['verify']['checks'] if check['id'] == 'verify.sim2gse')
    sim2gse_command = str(sim2gse['command']).replace('\\', '/')
    sim2gse_pytest = '-m pytest' in sim2gse_command and 'tests/sim2gse' in sim2gse_command
    assert sim2gse_pytest, 'Sim2GSE 必须由 pytest 自动发现'
    assert '-k "not test_tc_"' in sim2gse_command, 'PR 默认验证不得运行 TC 专属测试'
    build_source = ast.parse((ROOT / 'scripts/dev/sim2gse/build.py').read_text())
    build_modes = [
        ast.literal_eval(node.iter)
        for node in ast.walk(build_source)
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == 'mode'
    ]
    assert build_modes == [('baseline', 'controlled')], '默认构建只准备基准与受控引擎'
    local_checks = []
    for check in config['verify']['checks']:
        command = str(check['command']).replace('\\', '/')
        if (any(path in command for path in LOCAL_ACCEPTANCE)
                or 'tests/sim2gse/manual_' in command
                or 'tests/sim2gse/research/' in command
                or 'tests/gear-planner/research/' in command):
            local_checks.append(check['id'])
    assert not local_checks, '本机验收不得进入 PR 统一验证：\n' + '\n'.join(local_checks)
    assert {c['id'] for c in config['build']['checks']} == {
        'build.sim2gse-product', 'build.assets',
    }, '统一构建只保留产品目标'
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
        discovered = path.parent == ROOT / 'tests/sim2gse' and path.match('test_*.py') and sim2gse_pytest
        if relative not in commands and not discovered:
            missing.append(relative)
    assert not missing, '未接入统一验证的测试：\n' + '\n'.join(sorted(missing))
    print('PASS: 所有测试入口均已登记')


if __name__ == '__main__':
    main()
