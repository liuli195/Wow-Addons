"""Minimal real engine adapters and the one browser persistence round trip."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.real
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('gear_planner_real', ROOT / 'projects/gear-planner/server.py')
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def import_fixture(path):
    # Native-report settings are not accepted addon import fields.
    lines = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        if '=' not in raw or raw.lstrip().startswith('#'):
            continue
        key = raw.split('=', 1)[0]
        if key in server.CLASS_SPECS or key in server.SLOT_KEYS or key in server.ALIASES or key in {
            'level', 'spec', 'race', 'talents', 'omnium_talents', 'timeofday'}:
            lines.append(raw)
    return server.parse_import('\n'.join(lines))


def test_three_engine_routes_have_pinned_identity_and_complete_native_snapshots():
    server.load_data()
    identity = json.loads((server.RESEARCH / 'mistweaver-supported/manifest.json').read_text())['files']
    routes = [('official', server.EXE, server.BASE, 'c1935b9'),
              ('holy', server.HOLY_EXE, import_fixture(server.RESEARCH / 'holy-paladin-supported/holy.input.simc'), 'holy-gate1'),
              ('mistweaver', server.MISTWEAVER_EXE, import_fixture(server.RESEARCH / 'mistweaver-supported/mistweaver.input.simc'), 'mistweaver-attributes1')]
    for name, engine, model, version in routes:
        assert engine.is_file(), f'missing {name} engine: {engine}'
        with engine.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == identity[name]['sha256'], name
        result = server.calculate(model)  # LOCK serializes every native call.
        assert result['complete'], (name, result)
        assert version in result['version']
        assert result['items'] and result['values']['stamina'] > 0
        assert all(result['items'][slot]['ilevel'] is not None for slot in model['gear'] if slot in dict(server.SLOTS))
        if name == 'official':
            assert result['values']['strength'] == 2341 and result['values']['ilevel'] == 315.75
            assert result['items']['head']['raw']['strint'] == 152
            assert result['items']['head']['raw']['stamina'] == 3002
            assert result['items']['head']['raw']['crit_rating'] == 118
            assert result['items']['head']['sourceInfo']['details']
        elif name == 'holy':
            reference = json.loads((server.RESEARCH / 'holy-paladin-supported/manifest.json').read_text())['samples'][0]['snapshot']
            for key, value in reference['attribute'].items():
                assert result['values'][key] == value
            assert result['values']['armor'] == reference['stats']['armor']
        else:
            assert result['values']['intellect'] > result['values']['agility']
            assert result['values']['ilevel'] == 334 * 14 / 16
            assert '未计入罗盘' in result['calculationState']


def test_browser_import_edit_save_reload_compare_export_reimport():
    node = ROOT / '.local/verify-deps/node/node.exe'
    assert node.is_file(), f'missing frozen Node runtime: {node}'
    subprocess.run([sys.executable, str(ROOT / 'scripts/dev/run_browser_check.py'),
                    'tests/gear-planner/check-browser.cjs'], cwd=ROOT, check=True, timeout=180)
