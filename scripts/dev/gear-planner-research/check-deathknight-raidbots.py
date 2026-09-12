"""Replay three pinned Raidbots stat snapshots without changing the application."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'projects/gear-planner/fixtures/raidbots-deathknight'


def leaves(value, prefix=''):
    result = {}
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            result.update(leaves(item, path))
        else:
            result[path] = item
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures',type=Path,default=FIXTURES)
    args = parser.parse_args()
    fixtures = args.fixtures.resolve()
    engine = args.engine.resolve(strict=True)
    manifest = json.loads((fixtures / 'manifest.json').read_text(encoding='utf-8'))
    app = runpy.run_path(str(ROOT / 'projects/gear-planner/server.py'))
    results = []
    for sample in manifest['samples']:
        spec = sample['spec']
        source = fixtures / f'{spec}.input.simc'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == sample['input_sha256'], spec
        with tempfile.TemporaryDirectory(prefix='dk-reference-') as folder:
            report = Path(folder) / 'result.json'
            run = subprocess.run(
                [str(engine), str(source), 'item_db_source=local', 'threads=1',
                 f'json={report},version=2', f'output={Path(folder) / "output.txt"}'],
                cwd=folder, capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=30,
            )
            if run.returncode or not report.exists():
                results.append({'spec': spec, 'engine_pass': False,
                                'error': (run.stderr + run.stdout)[-2000:]})
                continue
            data = json.loads(report.read_text(encoding='utf-8'))
        actor = data['sim']['players'][0]
        actual = leaves(actor['collected_data']['buffed_stats'])
        expected = leaves(sample['snapshot'])
        passed, failed = [], []
        for field in sorted(expected.keys() | actual.keys()):
            if field in expected and field in actual and expected[field] == actual[field]:
                passed.append(field)
            else:
                failed.append({'field': field, 'expected': expected.get(field),
                               'actual': actual.get(field)})
        dbc = data['sim']['options']['dbc']
        identity_ok = all(actor[key] == sample['identity'][key] for key in sample['identity'])
        dbc_ok = dbc['version_used'] == 'Live' and dbc['Live'] == sample['dbc_live']
        gear_ok = actor['gear'] == sample['gear']

        # Native report settings are not addon import fields. Extract only character
        # and gear fields; preserve the symbolic rune configuration without rewriting it.
        import_lines = []
        for line in source.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.startswith('#'):
                continue
            key, value = line.split('=', 1)
            key = app['ALIASES'].get(key, key)
            if key in ('deathknight', 'demonhunter', 'rogue', 'warlock', 'mage', 'paladin', 'hunter', 'shaman', 'warrior', 'priest','druid','monk','evoker', 'level', 'spec', 'race', 'talents', 'omnium_talents', 'timeofday') or key in app['SLOT_KEYS']:
                import_lines.append(key + '=' + value)
        try:
            model = app['parse_import']('\n'.join(import_lines))
            preview = app['calculate'](model)
            wanted = dict(sample['snapshot']['attribute'])
            wanted['armor'] = sample['snapshot']['stats']['armor']
            reference_gear = sample['gear']
            main_item = app['ITEMS'].get(int(app['gear_fields'](reference_gear['main_hand']['encoded_item'])['id']), {})
            two_handed = main_item.get('inventoryType') == 17 or (main_item.get('itemClass') == 2 and main_item.get('itemSubClass') in (2, 3, 18))
            wanted['ilevel'] = (sum(item['ilevel'] for item in reference_gear.values()) + (reference_gear['main_hand']['ilevel'] if 'off_hand' not in reference_gear and two_handed and not (model['character']['class']=='warrior' and spec=='fury') else 0)) / 16
            for stat in ('crit', 'haste', 'mastery', 'versatility'):
                wanted[stat] = sample['snapshot']['stats'][stat + '_rating']
                wanted[stat + '_pct'] = sample['snapshot']['stats'][stat + '_pct'] * 100
            values = preview.get('values') or {}
            differences = [{'field': key, 'expected': value, 'actual': values.get(key)}
                           for key, value in wanted.items() if values.get(key) != value]
            application = {'computed': preview['complete'],
                           'pass': preview['complete'] and not differences,
                           'failed_fields': differences, 'values': values,
                           'error': preview.get('error')}
        except ValueError as error:
            application = {'computed': False, 'pass': False, 'error': str(error)}
        results.append({
            'spec': spec, 'report_url': sample['report_url'],
            'engine_pass': not failed and identity_ok and dbc_ok and gear_ok,
            'reported_git_revision': data.get('git_revision'),
            'identity_pass': identity_ok, 'dbc_pass': dbc_ok, 'gear_pass': gear_ok,
            'passed_fields': passed, 'failed_fields': failed,
            'application': application,
        })
    output = {'engine': str(engine),
              'engine_sha256': hashlib.sha256(engine.read_bytes()).hexdigest(),
              'samples': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    for row in results:
        print(json.dumps(row, ensure_ascii=False))
    # This command verifies the whole path; refusal is a failed result, not an expected pass.
    return 0 if all(row['engine_pass'] and row.get('application', {}).get('pass')
                    for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())

