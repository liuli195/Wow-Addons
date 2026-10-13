"""网页双场每次启动/恢复完整验一次引擎，不共享两场计算预算。"""
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from test_burst import page_task_engine, reviewed_fixture
from test_seed_training import memory_result_center
from test_training_champion import REAL_CHECK_REPORT, completed_training, dual_result


@pytest.fixture
def small_verified_engines(tmp_path, monkeypatch):
    """微型产物仍通过真实构建清单、路径、源码标记和二进制 SHA 核验。"""
    import engine
    from native_build import build_identity, identity_digest, source_directory

    root = tmp_path / 'engine'
    lock = dict(build_protocol=2, upstream_commit='a' * 40, upstream_tree='b' * 40,
                build_options=[], baseline_patches=[], patches=[], sources=[])
    lock_path = root / 'projects/sim2gse/compatibility/lock.json'
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock), encoding='utf-8')
    executables = {}
    for mode in ('baseline', 'controlled'):
        executable = root / '.local/sim2gse/build' / mode / 'simc.exe'
        executable.parent.mkdir(parents=True)
        contents = ('verified test engine: ' + mode).encode()
        executable.write_bytes(contents)
        identity = build_identity(lock, mode, 'c' * 64)
        manifest = dict(identity, identity_sha256=identity_digest(identity), exit_code=0,
                        executable=executable.relative_to(root).as_posix(), command=['make', '-j4'],
                        binary_sha256=hashlib.sha256(contents).hexdigest())
        (executable.parent / 'build.json').write_text(json.dumps(manifest), encoding='utf-8')
        executables[mode] = executable
        if mode == 'baseline':
            source = source_directory(root, identity)
            template = source / 'profiles/MID2/MID2_Death_Knight_Unholy.simc'
            template.parent.mkdir(parents=True)
            (source / 'source-identity.json').write_text(json.dumps(identity), encoding='utf-8')
            template.write_text(reviewed_fixture()[1], encoding='utf-8')
    monkeypatch.setattr(engine, 'ROOT', root)
    return executables


def test_dual_verifies_engines_once_per_start_and_resume_with_separate_scene_budgets(
        tmp_path, memory_result_center, page_task_engine, small_verified_engines):
    import burst
    import engine
    import result_store

    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    with patch.object(engine, 'check_report', REAL_CHECK_REPORT):
        winners = []
        for targets in (1, 5):
            _, rows = completed_training(tmp_path, targets, [
                ([['outbreak'], ['death_coil'], ['outbreak']], [190., 200., 210.])])
            winners.append(rows[0]['candidate_id'])

        reads = dict(baseline=0, controlled=0)
        paths = {path: mode for mode, path in small_verified_engines.items()}
        read_bytes = Path.read_bytes
        reference = engine.reference
        runtimes = {}

        def observed_read(path):
            if path in paths:
                reads[paths[path]] += 1
            return read_bytes(path)

        def observed_reference(*args, **kwargs):
            runtimes[kwargs['simulation_config']['target_count']] = kwargs['runtime']
            return reference(*args, **kwargs)

        def before_resume(state):
            assert reads == {'baseline': 1, 'controlled': 1}
            assert [scene['training_champion_snapshot']['candidate_id'] for scene in state['scenes']] == winners
            assert [scene['total_budget_seconds'] for scene in state['scenes']] == [600., 600.]
            assert set(runtimes) == {1, 5}
            assert runtimes[1] is not runtimes[5]
            assert [runtimes[targets].budget_seconds for targets in (1, 5)] == [600., 600.]

        with patch.object(Path, 'read_bytes', observed_read), \
                patch.object(engine, 'reference', observed_reference):
            state = dual_result(tmp_path, raw, candidate_limit=1, before_resume=before_resume)
            assert reads == {'baseline': 2, 'controlled': 2}
            assert state['collection_ready']
            # 独立新任务不能沿用上一任务已经验证的内存结果。
            fresh = dual_result(tmp_path / 'fresh', raw, candidate_limit=1)
            assert fresh['collection_ready']
            assert reads == {'baseline': 3, 'controlled': 3}


def test_dual_rejects_changed_engine_on_first_verification(
        tmp_path, memory_result_center, page_task_engine, small_verified_engines):
    import burst
    import result_store

    definition, raw = reviewed_fixture()
    burst.publish(definition)
    result_store.DATA_ROOT.mkdir(exist_ok=True)
    read_bytes = Path.read_bytes
    executable = small_verified_engines['baseline']

    def corrupt_read(path):
        contents = read_bytes(path)
        return contents + b'changed' if path == executable else contents

    with patch.object(Path, 'read_bytes', corrupt_read), pytest.raises(HTTPError) as rejected:
        dual_result(tmp_path, raw, candidate_limit=1)
    assert rejected.value.code == 500
    with rejected.value as response:
        assert json.load(response)['error'] == '引擎计算失败，请检查本机模拟环境后重试。'
