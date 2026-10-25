"""第二票：同一公开任务入口的序列模拟行为检查。"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import json
import pytest
from unittest.mock import Mock, patch

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from task import parse_character
from sequence import evaluate
from test_character_export import sample_profile


@pytest.mark.parametrize('enabled,outcome', [(False, 'without_trace'), (True, 'with_trace'), (True, 'invalid_trace')])
def test_evaluation_timing_preserves_report_and_trace_contract(monkeypatch, enabled, outcome):
    import runtime
    import sequence
    from test_search import _fast_report

    source = Path('unused-role.simc')
    character = parse_character(sample_profile())
    candidate = dict(blocks=[[dict(kind='spell', spell_id=77575, name='Outbreak', simc_action='outbreak')]],
                     compiled_steps=[dict(type='spell', spell=77575)])
    report = _fast_report(character, 100.0, 1)
    trace = '\n'.join('S2GSE\t' + '\t'.join(map(str, [ms, event, 1, 0, action, 0, 0, 100,
            0, 1, signature, 0, -1, -1])) for ms, event, action, signature in [
                (0, 'input', '-', '-'), (1, 'dispatch', 'outbreak', 'outbreak'),
                (2, 'native_execute', 'outbreak', 'outbreak')])
    monkeypatch.setattr(Path, 'mkdir', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'write_text', lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, 'read_text', Mock(
        side_effect=[sample_profile(), json.dumps(report), 'S2GSE\tinvalid' if outcome == 'invalid_trace' else trace]))
    monkeypatch.setattr(sequence, 'replace_file', lambda *args: None)
    monkeypatch.setattr(sequence, 'run', lambda *args, **kwargs: 'S2GBLOCK\t0\t0\toutbreak\n')
    task_runtime = runtime.TaskRuntime(diagnostic_logging=enabled)
    clocks = []
    def performance_clock():
        clocks.append(True)
        assert enabled, '默认关闭不得额外计时'
        return float(len(clocks))
    monkeypatch.setattr(runtime.time, 'perf_counter', performance_clock)
    arguments = dict(character=character, iterations=2, input_times=[0],
                     trace=outcome != 'without_trace', runtime=task_runtime)
    if outcome == 'invalid_trace':
        with pytest.raises(ValueError, match='原生来源轨迹字段数量不一致'):
            evaluate(source, candidate, Path('unused-result'), **arguments)
    else:
        result = evaluate(source, candidate, Path('unused-result'), **arguments)
        assert result['summary']['dps'] == 100.0
        assert result['report'] == report
        assert len(result['trace']) == (0 if outcome == 'without_trace' else 3)
    stages = runtime.diagnostic_summary(task_runtime)['stages']
    if enabled:
        assert stages['evaluation.report_read_validate']['calls'] == 1
        assert stages['evaluation.report_read_validate']['seconds'] == 1.0
        assert stages['evaluation.trace']['calls'] == 1
        assert stages['evaluation.trace']['seconds'] == 1.0
    else:
        assert clocks == []
        assert stages == {}


class NativeTraceContractTests(unittest.TestCase):
    """固定原生交换报告，检查公开评估入口的轨迹身份契约；不冒称引擎验收。"""

    def test_expanded_click_limit_applies_to_each_independent_sequence(self):
        """公开 sequence 接缝核验参数；模拟边界仅截获调用，不冒称原生执行。"""
        command = dict(kind='spell', spell_id=77575, name='Outbreak', simc_action='outbreak')
        def candidate(count):
            return dict(blocks=[[command]] * count,
                        compiled_steps=[dict(type='spell', spell=77575)] * count)
        root = Path('unused-trace')
        source = root / 'profile.simc'
        character = parse_character(sample_profile())
        with patch.object(Path, 'mkdir'), patch.object(Path, 'read_text', return_value=sample_profile()), \
                patch.object(Path, 'write_text', autospec=True) as write:
            for loop, burst in ((4096, 0), (4096, 4096)):
                with self.subTest(loop=loop, burst=burst):
                    def boundary(profile, folder, *args, **kwargs):
                        options = dict(line.split('=', 1) for line in write.call_args.args[1].splitlines()
                                       if line.startswith('sim2gse_'))
                        self.assertEqual(len(options['sim2gse_steps'].split('/')), loop + burst)
                        if burst:
                            self.assertEqual(options['sim2gse_burst_offset'], str(loop))
                            self.assertEqual(options['sim2gse_sources'], 'loop/burst')
                        raise RuntimeError('native boundary reached')
                    with patch('sequence.run', side_effect=boundary), self.assertRaisesRegex(
                            RuntimeError, 'native boundary reached'):
                        evaluate(source, candidate(loop), root / f'{loop}-{burst}', character=character,
                            input_times=[0, 300], burst_candidate=candidate(burst) if burst else None,
                            input_sources=['loop', 'burst'] if burst else None)
            for loop, burst in ((4097, 1), (1, 4097)):
                with self.subTest(loop=loop, burst=burst), patch('sequence.run') as native:
                    with self.assertRaisesRegex(ValueError, '4096'):
                        evaluate(source, candidate(loop), root / 'overflow', character=character,
                            input_times=[0, 300], burst_candidate=candidate(burst) if burst else None,
                            input_sources=['loop', 'burst'] if burst else None)
                    native.assert_not_called()

    def test_replacement_castsequence_keeps_issued_signature_and_actual_action(self):
        raw = sample_profile()
        character = parse_character(raw)
        commands = [dict(kind='spell', spell_id=63560, name='dark_transformation',
                         simc_action='dark_transformation'),
                    dict(kind='spell', spell_id=47541, name='death_coil', simc_action='death_coil')]
        candidate = dict(blocks=[commands], compiled_steps=[dict(type='macro',
            macrotext='/castsequence 63560,47541')], compiled_program=dict(
                clicks=[dict(kind='Action', source={}, commands=['dark_transformation', 'death_coil'])],
                castsequences=[dict(step=0, members=['dark_transformation', 'death_coil'], reset=None)]))
        player = dict(name=character.name, sim2gse_class=character.class_name, level=character.level,
            sim2gse_spec_id=252, sim2gse_class_id=6, sim2gse_spec='unholy', race=character.race,
            role='attack', sim2gse_resource='runic_power', talents=character.fields['talents'],
            gear={slot: dict(encoded_item=item.raw) for slot, item in character.equipment.items()},
            collected_data=dict(dps=dict(mean=100., count=1), fight_length=dict(mean=180.)))
        report = dict(sim=dict(players=[player], targets=[{}], options=dict(dbc=dict(
            Live=dict(build_level=69933, wow_version='12.1.0.69933'), version_used='Live'))))
        events = [
            (0, 'input', 1, '-', '-', 0), (1, 'dispatch', 1, 'dark_transformation', 'dark_transformation', 0),
            (2, 'native_execute', 1, 'blightfall', 'dark_transformation', 0),
            (2, 'native_derived', 1, 'disease_effect', '', 0),
            (2000, 'input', 2, '-', '-', 1), (2001, 'dispatch', 2, 'death_coil', 'death_coil', 1),
            (2050, 'native_interrupt', 2, 'replacement_cast', 'death_coil', 1)]
        root = Path('unused-exchange')
        source = root / 'input.simc'
        def native_exchange(profile, folder, *args, **kwargs):
            return 'S2GBLOCK\t0\t0\tdark_transformation\nS2GBLOCK\t0\t1\tdeath_coil\n'
        def read_native(path, **kwargs):
            if path.name == 'input.simc':
                return raw
            if path.name == 'native.pending.json':
                return json.dumps(report)
            if path.name != 'native.txt':
                raise AssertionError('unexpected read: ' + str(path))
            return '\n'.join(
                'S2GSE\t' + '\t'.join(map(str, [ms, event, origin, 0, action, 0, 0, 100, 0,
                                                0, signature, 0, 0, member]))
                for ms, event, origin, action, signature, member in events)
        with patch('sequence.run', side_effect=native_exchange), patch.object(Path, 'mkdir'), \
                patch.object(Path, 'write_text'), patch.object(Path, 'read_text', read_native), \
                patch('sequence.replace_file'):
            result = evaluate(source, candidate, root / 'result', character=character,
                              iterations=2, input_times=[0, 2000])
            original = list(events)
            events[2] = (2, 'native_derived', 1, 'blightfall', '', 0)
            events[6] = (2050, 'native_execute', 2, 'death_coil', 'death_coil', 1)
            with self.assertRaisesRegex(ValueError, '派发与实际执行轨迹不一致'):
                evaluate(source, candidate, root / 'derived', character=character,
                         iterations=2, input_times=[0, 2000])
            events[:] = original + [original[2]]
            with self.assertRaisesRegex(ValueError, '派发与实际执行轨迹不一致'):
                evaluate(source, candidate, root / 'duplicate', character=character,
                         iterations=2, input_times=[0, 2000])
            events[:] = original
            events[2] = (2, 'native_execute', 1, 'blightfall', 'other_command', 0)
            with self.assertRaisesRegex(ValueError, '不属于来源输入对应的编译块'):
                evaluate(source, candidate, root / 'wrong-signature', character=character,
                         iterations=2, input_times=[0, 2000])
            events[:] = original
            events[2] = (2, 'native_execute', 1, 'dark_transformation', 'dark_transformation', 0)
            events[6] = (2050, 'native_interrupt', 2, 'death_coil', 'death_coil', 1)
            direct = evaluate(source, candidate, root / 'direct', character=character,
                              iterations=2, input_times=[0, 2000])
            self.assertTrue(direct['consistent'])
        self.assertTrue(result['consistent'])
        self.assertEqual([(row['action'], row['signature']) for row in result['trace']
                          if row['event'] in {'native_execute', 'native_interrupt'}],
                         [('blightfall', 'dark_transformation'), ('replacement_cast', 'death_coil')])


if __name__ == "__main__":
    unittest.main()
