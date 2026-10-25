"""导入检查在内存执行；本地服务仅验证必要任务接线。"""

from __future__ import annotations

import tempfile
from contextlib import nullcontext
from copy import deepcopy
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
import threading
import unittest
import json
import base64
import os
import subprocess
import pytest
import zlib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))

from gse_import import inspect_import  # noqa: E402
from test_population_training import memory_ga  # noqa: E402
from test_search import _fixed_search_population  # noqa: E402


def gse_fixture(payload):
    import cbor2
    from codec import wire_value
    return "!GSE3!" + base64.b64encode(zlib.compress(cbor2.dumps(wire_value(payload)), wbits=-15)).decode("ascii")


# 固定合成向量：用锁定的 GSE 密钥编号和 cryptography 50.0.1 封装 CBOR 序列。
GSE_PROTECTED_SEQUENCE_VECTOR = (
    "!GSE3!+1AAECAwQFBgcICQoLG3AsKkGhhV0N/HWzbc4GgaZF4hReCjduid5ThZ/TBlBgCNHrDpQx1J2iLtVdXEdO66EYA7hAvDDxuP9DAhKFhjMVEzQ3ozkJGC11ccmZccQGTFEh+sKMi6o+CLvZlhVYS8655pzOGq9yw4Jk7CRHgh4eA6vj8zZcJHh9bajv/WolLkgO+/daJ3D5eUT0ddHkPxlmWXvyew6e5yMXVgfHN0YDkPk6MN9zjy9FPxSkkV4WGxkSw2Y="
)
GSE_PROTECTED_VARIABLE_VECTOR = (
    "!GSE3!+1DA0ODxAREhMUFRYXYE5icaKm4dh0FkGCZl9rS0Ot/9b2WpiWY2xSmznyd8/6PXCbMq4B3rKmQe6NCY4s4Ys/vuKwrEiljk2q6Ead1S1Jv/R/t5LeNA=="
)
GSE_PROTECTED_MACRO_VECTOR = (
    "!GSE3!+1GBkaGxwdHh8gISIjITXl5rxvJIfGsh1W9faejI+hnlUimbME8ag7Z5QUpuBgQG4pwW6rzLr0Um/muYNGkQHukMPDGG9hvkrUbFL6wWMwRz+/XkNH"
)


def test_formal_search_rejects_missing_variance_without_failing_task(memory_ga):
    import engine
    from interface import _public_state
    from sequence import compiled_program
    from simulation_config import TRAINING_DEFAULTS
    from test_search import _fast_report

    initial = ("outbreak", "death_coil")
    better = ("death_coil", "outbreak")
    worse = ("death_coil", "outbreak", "death_coil")
    calls = []

    def evaluate(profile, candidate, folder, **options):
        actions = tuple(name for block in compiled_program(candidate) for name in block)
        wanted = {initial: 90, better: 120, worse: 80}[actions]
        report = _fast_report(options['character'], wanted, options['iterations'] - 1)
        if actions == worse:
            report['sim']['players'][0]['collected_data']['dps'].pop('variance')
        calls.append((actions, options['iterations'], options.get('burst_candidate')))
        summary = engine.check_report(report, options['character'], options['iterations'],
            simulation_config=options['simulation_config'], allow_zero=True)
        return dict(report=report, summary=summary, trace=[])

    # The same formal entry owns quarantine and full finalist retests. HTTP,
    # physical report groups and native execution retain separate real witnesses.
    with patch.dict(TRAINING_DEFAULTS, crossover_probability=0., mutation_probability=0.):
        case = memory_ga(formal=True, programs=[[[name] for name in actions]
            for actions in (initial, better, worse)], native=evaluate)
        result = case.run()
    state = _public_state(result, case.store.destination)
    assert state['status'] == 'completed'
    assert state['result_ready']
    coarse = [(actions, count) for actions, count, _ in calls if count == 32]
    assert [count for actions, count in coarse if actions == worse] == [32, 32]
    assert [count for actions, count in coarse if actions == better] == [32]
    assert state['search_result']['dps'] == 120
    assert result['search']['effective_population_size'] == 2
    rejected, = result['search']['coarse_rejections'].values()
    assert rejected['attempts'] == 2
    assert all(row['kind'] == 'candidate_score' for row in rejected['failures'])
    finalists = result['final']['scenarios']['nominal']['finalists']
    assert len(finalists) == 2
    assert {tuple(name for block in compiled_program(row['candidate']) for name in block)
            for row in result['search']['records']} == {initial, better}
    assert all(len(row['batches']) == 3 and row['samples'] == 381 for row in finalists)
    assert all(batch['requested_iterations'] == 128 for row in finalists for batch in row['batches'])
    assert all('rule_diagnostics' not in row for row in result['search']['records'])
    assert calls and all(burst is None for _, _, burst in calls)


class ImportInspectionTests(unittest.TestCase):
    """直接执行生产解码和静态预检，不启动服务或创建临时数据。"""

    def test_import_inspection_lists_versions_and_nested_syntax_without_simulating(self) -> None:
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [
                {"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]},
                {"Actions": [{"Type": "Loop", "Repeat": "2", 1: {"Type": "Pause", "Clicks": 2}}]},
            ],
        }])
        try:
            result = inspect_import(imported)
        except ValueError as error:
            self.fail(str(error))
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["sequences"][0]["name"], "THIRD_PARTY")
        self.assertEqual(result["sequences"][0]["version_count"], 2)
        self.assertEqual(set(result["syntax"]), {"Action", "Loop", "Pause"})
        self.assertFalse(result["simulation_started"])


    def test_import_inspection_returns_the_full_decoded_payload(self) -> None:
        import cbor2
        from codec import wire_value

        payload = ["LOSSLESS", {
            "MetaData": {"Name": "LOSSLESS", "SpecID": 252, "GSEVersion": 3332,
                         "ExplicitNull": None},
            "Default": 1,
            "UnknownSequenceField": {"ordered": ["first", "second"], "enabled": False},
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                          "macro": "/cast 77575\n/use 13",
                                          "UnknownBlockField": 17}]}],
        }]
        imported = gse_fixture(payload)

        result = inspect_import(imported)

        self.assertEqual(result["raw_import"], imported)
        self.assertEqual(result["raw_payload"], payload)
        self.assertEqual(result["payload_cbor_base64"], base64.b64encode(
            cbor2.dumps(wire_value(payload))).decode("ascii"))
        self.assertFalse(result["simulation_started"])


    def test_import_inspection_decodes_fixed_protected_sequence_vector(self) -> None:
        result = inspect_import(GSE_PROTECTED_SEQUENCE_VECTOR)

        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["format"], "protected")
        self.assertEqual(result["content_format"], "direct")
        self.assertEqual(result["protected_object_type"], "SEQUENCE")
        self.assertEqual(result["raw_import"], GSE_PROTECTED_SEQUENCE_VECTOR)
        member = result["sequences"][0]
        self.assertEqual(member["name"], "PROTECTED")
        self.assertEqual(member["raw_sequence"]["UnknownSequenceField"], {
            "ordered": ["a", "b"], "ExplicitNull": None,
        })
        action = member["versions"][0]["raw_version"]["Actions"][0]
        self.assertEqual(action["macro"], "/cast 77575\n/use 13")
        self.assertEqual(action["Vendor"], 17)
        self.assertEqual(result["syntax_locations"][0]["path"],
                         "Sequences[PROTECTED].Versions[1].Actions[1]")


    def test_import_inspection_reports_unknown_protected_key_without_dropping_raw_input(self) -> None:
        imported = GSE_PROTECTED_SEQUENCE_VECTOR.replace("!GSE3!+1", "!GSE3!+2", 1)

        with self.assertRaises(ValueError) as raised:
            inspect_import(imported)
        error = str(raised.exception)
        self.assertIn("密钥编号", error)
        self.assertIn("2", error)


    def test_import_inspection_parses_collection_variable_and_macro_encodings(self) -> None:
        import cbor2

        def delta_fork(name, kind, base, delta):
            return {"GSEDeltaFork": True, "platformId": f"{name}-platform-id",
                    "contentType": kind, "base": gse_fixture(base),
                    "delta": base64.b64encode(cbor2.dumps(delta)).decode("ascii")}

        variable_fork = delta_fork(
            "V_DELTA", "variable", {"name": "V_DELTA", "funct": "return 1", "Drop": True},
            {"top": {"funct": "return 2", "Added": "kept"}, "topUnset": ["Drop"]})
        macro_fork = delta_fork(
            "M_DELTA", "macro", {"name": "M_DELTA", "macro": "/cast old"},
            {"top": {"macro": "/cast updated"}})
        payload = {"type": "COLLECTION", "payload": {
            "Variables": {"PVAR": GSE_PROTECTED_VARIABLE_VECTOR, "V_DELTA": variable_fork},
            "Macros": {"PMAC": GSE_PROTECTED_MACRO_VECTOR, "M_DELTA": macro_fork},
        }}

        result = inspect_import(gse_fixture(payload))

        self.assertEqual(result["raw_variables"], payload["payload"]["Variables"])
        self.assertEqual(result["raw_macros"], payload["payload"]["Macros"])
        self.assertEqual(result["variables"]["PVAR"]["funct"], "return GSE.V.Other()")
        self.assertEqual(result["variables"]["V_DELTA"]["funct"], "return 2")
        self.assertEqual(result["variables"]["V_DELTA"]["Added"], "kept")
        self.assertNotIn("Drop", result["variables"]["V_DELTA"])
        self.assertEqual(result["macros"]["PMAC"]["macro"], "/cast 77575\n/use 13")
        self.assertEqual(result["macros"]["M_DELTA"]["macro"], "/cast updated")
        self.assertEqual(result["collection_compatibility_blocks"], [])


    def test_import_inspection_recursively_expands_plain_nested_collection_members(self) -> None:
        nested = {"type": "COLLECTION", "payload": {
            "Sequences": {
                "INNER_A": {"MetaData": {"Name": "INNER_A", "SpecID": 252,
                                           "GSEVersion": 3332}, "Default": 1,
                             "Versions": [{"Actions": [{"Type": "Action", "spell": 101}]}]},
                "INNER_B": {"MetaData": {"Name": "INNER_B", "SpecID": 252,
                                           "GSEVersion": 3332}, "Default": 1,
                             "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 2}]}]},
            },
            "Variables": {"INNER_V": {"name": "INNER_V", "funct": "return 9"}},
            "Macros": {"INNER_M": {"name": "INNER_M", "macro": "/cast 77575"}},
        }}
        nested_wire = gse_fixture(nested)
        outer_payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"WRAPPER": nested_wire},
        }}
        imported = gse_fixture(outer_payload)

        result = inspect_import(imported)

        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(set(members), {"INNER_A", "INNER_B"})
        self.assertEqual(members["INNER_A"]["versions"][0]["source_path"],
                         "Sequences[WRAPPER].payload.Sequences[INNER_A].Versions[1]")
        self.assertEqual(members["INNER_B"]["versions"][0]["parsed_version"]["Actions"][0],
                         {"Type": "Pause", "Clicks": 2})
        self.assertIn(("Action", "Sequences[WRAPPER].payload.Sequences[INNER_A].Versions[1].Actions[1]"),
                      {(row["type"], row["path"]) for row in result["syntax_locations"]})
        self.assertEqual(result["variables"], {})
        self.assertEqual(result["macros"], {})
        self.assertFalse(members["INNER_A"]["version_support"][0]["simulation_preflight_passed"])
        self.assertIn("Variables 阶段先于目标序列所属阶段导入",
                      members["INNER_A"]["version_support"][0]["support_reason"])
        self.assertEqual({block["source_path"] for block in result["collection_compatibility_blocks"]}, {
            "Sequences[WRAPPER].payload.Variables[INNER_V]",
            "Sequences[WRAPPER].payload.Macros[INNER_M]",
        })
        self.assertEqual(result["raw_payload"], outer_payload)


    def test_import_inspection_reconstructs_self_contained_collection_delta_fork(self) -> None:
        import cbor2

        base = {
            "MetaData": {"Name": "DELTA_FORK", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Help": "old help", "OldTop": True,
            "Versions": {
                1: {"Label": "old label", "DropVersionField": True,
                      "InbuiltVariables": {"old": True},
                      "Actions": [
                          {"Type": "Action", "type": "macro", "macro": "/cast old",
                           "DropBlockField": True},
                          {"Type": "Loop", "Repeat": 2,
                           1: {"Type": "Action", "type": "spell", "spell": 100}},
                          {"Type": "If", "Variable": "=true",
                           1: [{"Type": "Action", "type": "spell", "spell": 101}],
                           2: [{"Type": "Pause", "Clicks": 1}]},
                      ]},
                2: {"Actions": [{"Type": "Pause", "Clicks": 2}]},
                3: {"Actions": [{"Type": "Pause", "Clicks": 3}]},
            },
        }
        delta = {
            "versions": {
                "1": {
                    "actions": [
                        {"from": 0, "set": {"macro": "/cast updated"},
                         "unset": ["DropBlockField"]},
                        {"from": 1, "children": [
                            {"from": 0, "set": {"spell": 104}},
                            {"new": {"Type": "Pause", "Clicks": 4}},
                        ]},
                        {"from": 2,
                         "branch1": [{"from": 0, "set": {"spell": 105}}],
                         "branch2": [{"new": {"Type": "Action", "type": "spell",
                                               "spell": 106}}]},
                        {"new": {"Type": "Action", "type": "spell", "spell": 107}},
                    ],
                    "inbuiltVariables": {"new": "value"},
                    "set": {"Label": "new label"},
                    "unset": ["DropVersionField"],
                },
                "4": {"op": "add", "value": {
                    "Actions": [{"Type": "Pause", "Clicks": 5}],
                }},
                "3": {"op": "remove"},
            },
            "top": {"Help": "updated help", "AddedTop": "kept"},
            "topUnset": ["OldTop"],
        }
        fork = {"GSEDeltaFork": True, "platformId": "fork-platform-id",
                "base": gse_fixture(["DELTA_FORK", base]),
                "delta": base64.b64encode(cbor2.dumps(delta)).decode("ascii"),
                "contentType": "sequence", "upstreamId": "source-platform-id"}
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"DELTA_FORK": fork},
        }})

        try:
            result = inspect_import(imported)
        except ValueError as error:
            self.fail(str(error))

        member = result["sequences"][0]
        self.assertEqual(member["raw_sequence"], fork)
        self.assertEqual([row["version"] for row in member["versions"]], [1, 2, 4])
        parsed = member["versions"][0]["parsed_version"]
        self.assertEqual(parsed["Label"], "new label")
        self.assertNotIn("DropVersionField", parsed)
        self.assertEqual(parsed["InbuiltVariables"], {"new": "value"})
        self.assertEqual(parsed["Actions"][0]["macro"], "/cast updated")
        self.assertNotIn("DropBlockField", parsed["Actions"][0])
        self.assertEqual(parsed["Actions"][1]["1"]["spell"], 104)
        self.assertEqual(parsed["Actions"][1]["2"], {"Type": "Pause", "Clicks": 4})
        self.assertEqual(parsed["Actions"][2]["1"][0]["spell"], 105)
        self.assertEqual(parsed["Actions"][2]["2"][0]["spell"], 106)
        self.assertEqual(parsed["Actions"][3]["spell"], 107)
        self.assertEqual(member["versions"][2]["parsed_version"]["Actions"][0]["Clicks"], 5)
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["DELTA_FORK"], fork)
        self.assertEqual(result["syntax_locations"][0]["sequence"], "DELTA_FORK")
        from gse_import import decode_import
        parsed_sequence = decode_import(imported)["sequences"]["DELTA_FORK"]
        self.assertEqual(parsed_sequence["Help"], "updated help")
        self.assertEqual(parsed_sequence["AddedTop"], "kept")
        self.assertNotIn("OldTop", parsed_sequence)


    def test_import_inspection_rejects_unknown_block_with_member_version_and_path(self) -> None:
        imported = gse_fixture(["UNKNOWN", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "FutureBlock", "Disabled": True}]}],
        }])

        with self.assertRaises(ValueError) as raised:
            inspect_import(imported)
        error = str(raised.exception)
        self.assertIn("FutureBlock", error)
        self.assertIn("UNKNOWN", error)
        self.assertIn("Versions[1].Actions[1]", error)


    def test_import_inspection_marks_newer_gse_members_as_not_simulatable(self) -> None:
        imported = gse_fixture({"type": "COLLECTION", "payload": {"Sequences": {
            "LOCKED": {"MetaData": {"Name": "LOCKED", "SpecID": 252, "GSEVersion": 3332},
                       "Default": 1, "Versions": [{"Actions": []}]},
            "FUTURE": {"MetaData": {"Name": "FUTURE", "SpecID": 252, "GSEVersion": 3333},
                       "Default": 1, "Versions": [{"Actions": []}]},
        }}})
        result = inspect_import(imported)
        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(result["status"], "decoded")
        self.assertIsNone(members["LOCKED"]["simulation_supported"])
        self.assertTrue(members["LOCKED"]["simulation_preflight_passed"])
        self.assertFalse(members["FUTURE"]["simulation_supported"])
        self.assertFalse(members["FUTURE"]["simulation_preflight_passed"])
        self.assertIn("3333", members["FUTURE"]["support_reason"])
        self.assertIn("3332", members["FUTURE"]["support_reason"])


    def test_import_inspection_preserves_empty_and_corrupt_encoding_diagnostics(self) -> None:
        cases = [
            ("", "GSE 导入编码无效"),
            ("bad!", "GSE 导入编码无效"),
            ("badé", "GSE 导入编码无效"),
            ("ba=d", "GSE 导入编码无效"),
            ("bad===", "GSE 导入编码无效"),
            ("bad", "GSE 导入编码或内容损坏"),
        ]
        for encoded, expected_error in cases:
            with self.subTest(encoded=encoded):
                with self.assertRaises(ValueError) as raised:
                    inspect_import("!GSE3!" + encoded)
                self.assertIn(expected_error, str(raised.exception))


    def test_import_inspection_rejects_duplicate_cbor_map_keys_without_silent_loss(self) -> None:
        import cbor2

        duplicate = b"\xa2" + cbor2.dumps("Name") + cbor2.dumps("first") \
            + cbor2.dumps("Name") + cbor2.dumps("second")
        variables = b"\xa1" + cbor2.dumps("V") + duplicate
        collection = b"\xa2" + cbor2.dumps("type") + cbor2.dumps("COLLECTION") \
            + cbor2.dumps("payload") + b"\xa1" + cbor2.dumps("Variables") + variables
        imported = "!GSE3!" + base64.b64encode(zlib.compress(collection, wbits=-15)).decode("ascii")

        with self.assertRaises(ValueError) as raised:
            inspect_import(imported)
        error = str(raised.exception)
        self.assertIn("重复字段键", error)
        self.assertIn("Name", error)


    def test_import_inspection_rejects_decompression_over_limit(self) -> None:
        from gse_import import MAX_DECODED
        imported = gse_fixture("A" * (MAX_DECODED + 1))
        with self.assertRaises(ValueError) as raised:
            inspect_import(imported)
        self.assertIn("过大", str(raised.exception))


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        global _friendly_error, _public_state, create_server, run_task
        global sample_profile
        from interface import _friendly_error, _public_state, create_server
        from task import run_task
        from test_character_export import sample_profile

        self.real = any(mark.name == 'real' for mark in
                        getattr(getattr(type(self), self._testMethodName), 'pytestmark', []))
        if not self.real:
            # 不构造HTTP服务器：真实Handler读取BytesIO，服务数据IO逐例显式提供。
            from interface import InterfaceServer
            self.server = object.__new__(InterfaceServer)
            self.server.output_root = REPOSITORY / '.local' / 'unused-interface-unit'
            self.server.task_root = self.server.output_root / 'tasks'
            self.server.input_root = self.server.output_root / 'inputs'
            self.server.server_port = 0
            self.server.tasks, self.server.task_options = {}, {}
            self.server.tasks_lock = threading.RLock()
            self.input_write = self.enterContext(patch.object(
                Path, 'write_text', side_effect=AssertionError('校验失败前不得写入任务输入')))
            self.file_changes = [self.enterContext(patch.object(
                Path, name, side_effect=AssertionError('状态读取/拒绝不得改动检查点')))
                for name in ('write_bytes', 'unlink', 'mkdir')]
            return
        self.directory = tempfile.TemporaryDirectory(prefix="sim2gse-ui-")
        self.server = create_server(Path(self.directory.name) / "输出", port=0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self) -> None:
        if not self.real:
            self.input_write.assert_not_called()
            for changed in self.file_changes:
                changed.assert_not_called()
            return
        from task import cancel_task
        from dual_task import DualHandle, cancel as cancel_dual
        unfinished = []
        try:
            for _, handle in list(self.server.tasks.values()):
                if not handle.done:
                    (cancel_dual if isinstance(handle, DualHandle) else cancel_task)(handle)
                    handle.join(5)
                    if not handle.done:
                        unfinished.append(handle.output_root)
        finally:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.directory.cleanup()
        self.assertFalse(unfinished, '本次任务未完成取消清理: ' + repr(unfinished))

    def test_terminal_parent_does_not_show_stale_scene_as_running(self):
        import result_store
        from dual_task import PARENT_SCHEMA
        task_id = 'a' * 32
        row = dict.fromkeys(PARENT_SCHEMA)
        row.update(parent_id=task_id, formal_search_version=1, status='failed',
                   phase='single_target', error='native trace failed',
                   input_sha256='frozen', definition_id='reviewed', spec_id=252,
                   config=dict(input_interval_ms=200), simulation_config={},
                   rules={}, engines={}, preparation_seconds=1., packaging_seconds=0.,
                   single_target_path='single_target', aoe_path='aoe',
                   single_target_status='running', aoe_status='pending', burst_instructions='')
        with patch.object(result_store, 'read_records', side_effect=lambda *a, **k: [dict(row)]), \
                patch.object(Path, 'read_text', return_value=json.dumps(dict(parent_id=task_id))), \
                patch.object(Path, 'exists', lambda path: path.name == 'dual.json'):
            for status, scene_status in [('failed', 'failed'), ('interrupted', 'incomplete')]:
                row['status'] = status
                state = self._json_request('GET', '/api/tasks/' + task_id)
                self.assertEqual(state['status'], status)
                self.assertEqual(state['scenes'][0]['status'], scene_status)
                self.assertEqual(state['scenes'][1]['status'], 'pending')
                self.assertTrue(state['recoverable'])
                self.assertFalse(state['result_ready'])
        self.input_write.assert_not_called()

    def test_legacy_dual_without_rule_snapshot_remains_readable_but_cannot_resume(self):
        import engine
        import result_store
        import task
        from dual_task import PARENT_SCHEMA
        task_id = 'b' * 32
        row = dict.fromkeys(key for key in PARENT_SCHEMA if key != 'rule_snapshot')
        row.update(parent_id=task_id, status='cancelled', phase='single_target', error='old cancellation',
                   input_sha256='frozen', definition_id='reviewed', spec_id=252,
                   config=dict(total_budget_seconds=600, input_interval_ms=200), simulation_config={},
                   rules={}, engines={}, preparation_seconds=1., packaging_seconds=0.,
                   single_target_path='single_target', aoe_path='aoe',
                   single_target_status='cancelled', aoe_status='pending', burst_instructions='')
        # 仅替换持久数据/文件锁/原生身份IO，读取、旧身份拒绝和HTTP错误映射均为生产实现。
        with patch.object(result_store, 'read_records', side_effect=lambda *a, **k: [dict(row)]), \
                patch.object(Path, 'read_text', return_value=json.dumps(dict(parent_id=task_id))), \
                patch.object(Path, 'exists', lambda path: path.name == 'dual.json'), \
                patch.object(task, '_task_lease', side_effect=lambda *a, **k: nullcontext()), \
                patch.object(engine, 'identity', return_value=('unused.exe', {})):
            state = self._json_request('GET', '/api/tasks/' + task_id)
            self.assertEqual(state['status'], 'cancelled')
            self.assertEqual(state['total_budget_seconds'], 1200)
            self.assertEqual(state['scenes'][0]['total_budget_seconds'], 600)
            self.assertFalse(state.get('stop_policy'))
            self.assertFalse(state['recoverable'])
            self.assertIn('已退役', state['result_note'])
            self.assertIn('未进行最终独立复测', state['result_note'])
            self.assertEqual(state['scenes'][0]['status'], 'cancelled')
            self.assertEqual(state['scenes'][1]['status'], 'pending')
            with self.assertRaises(HTTPError) as raised:
                self._json_request('POST', '/api/tasks/' + task_id + '/resume', {})
            self.assertIn('身份不兼容', json.loads(raised.exception.read())['error'])
            self.assertEqual(self._json_request('GET', '/api/tasks/' + task_id)['status'], 'cancelled')

    def _json_request(self, method: str, path: str, value: dict | None = None,
                      timeout: float = 3) -> dict | str:
        body = None if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
        if not self.real:
            from interface import InterfaceHandler
            handler = object.__new__(InterfaceHandler)
            handler.server, handler.path = self.server, path
            handler.request_version, handler.requestline = 'HTTP/1.1', method + ' ' + path
            handler.command = method
            handler.headers = Message()
            handler.headers['Host'] = '127.0.0.1:0'
            handler.headers['Content-Length'] = str(len(body or b''))
            handler.rfile, handler.wfile = BytesIO(body or b''), BytesIO()
            getattr(handler, 'do_' + method)()
            headers, response = handler.wfile.getvalue().split(b'\r\n\r\n', 1)
            status = int(headers.split(b' ', 2)[1])
            if status >= 400:
                raise HTTPError(path, status, 'interface response', None, BytesIO(response))
            return response.decode('utf-8') if path == '/' else json.loads(response)
        request = Request(self.url + path, data=body, method=method,
                          headers={"Content-Type": "application/json"} if body else {})
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
            return body if path == '/' else json.loads(body)


    def test_import_inspection_http_wiring(self) -> None:
        payload = ["HTTP_IMPORT", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3332},
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]}],
        }]
        result = self._json_request("POST", "/api/gse/inspect", {"gse": gse_fixture(payload)})
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["raw_payload"], payload)
        self.assertFalse(result["simulation_started"])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": "!GSE3!bad!"})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("编码无效", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})
        self.input_write.assert_not_called()

    def test_empty_submission_is_rejected_without_creating_a_task(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {"profile": "  "})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("粘贴", json.loads(raised.exception.read())['error'])
        self.input_write.assert_not_called()


    def test_http_rejects_retired_formal_settings_before_start_or_resume(self):
        from simulation_config import RETIRED_SEARCH_SETTINGS
        for path in ('/api/tasks', '/api/tasks/' + 'a' * 32 + '/resume'):
            for key in RETIRED_SEARCH_SETTINGS:
                with self.subTest(path=path, key=key), self.assertRaises(HTTPError) as raised:
                    self._json_request('POST', path, {key: False})
                self.assertIn('已退役', json.loads(raised.exception.read())['error'])
        self.input_write.assert_not_called()

    def test_http_rejects_removed_settings_before_start_or_resume(self) -> None:
        for path in ('/api/tasks', '/api/tasks/' + 'a' * 32 + '/resume'):
            for key in ('adaptive_selector_enabled', 'rule_initialization_enabled', 'rule_diagnostics_policy', 'rule_step', 'diagnostic_candidate_key'):
                for value in (False, True):
                    with self.subTest(path=path, key=key, value=value):
                        with self.assertRaises(HTTPError) as raised:
                            self._json_request('POST', path, {'profile': sample_profile(), key: value})
                        self.assertEqual(raised.exception.code, 400)
                        self.assertIn('已移除', json.loads(raised.exception.read())['error'])
        self.assertEqual(self.server.tasks, {})
        self.input_write.assert_not_called()


    def test_task_api_rejects_unknown_combat_macro_condition_before_creating_task(self) -> None:
        for condition in ("combat", "nocombat"):
            with self.subTest(condition=condition):
                imported = gse_fixture(["UNKNOWN_COMBAT", {
                    "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
                    "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                                 "macro": f"/cast [{condition}] 77575"}]}],
                }])

                with self.assertRaises(HTTPError) as raised:
                    self._json_request("POST", "/api/tasks", {
                        "profile": sample_profile(), "mode": "import", "gse": imported,
                        "sequence_name": "UNKNOWN_COMBAT", "version": 1,
                        "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
                    })

                self.assertEqual(raised.exception.code, 400)
                error = json.loads(raised.exception.read())["error"]
                self.assertIn("宏条件不能确定", error)
                self.assertIn(
                    f"Sequences[UNKNOWN_COMBAT].Versions[1].Actions[1].macro[行 1]",
                    error,
                )
                self.assertEqual(self.server.tasks, {})
                self.input_write.assert_not_called()


    def test_unmapped_import_error_is_reported_without_dps(self) -> None:
        from gse_import import import_action_spell_ids, program_from_import
        from macro_interpreter import map_action
        from task import TaskError
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 99999999}]}],
        }])
        program = program_from_import(imported, 'THIRD_PARTY', 1)
        spell_id, = import_action_spell_ids(program)
        with self.assertRaises(ValueError) as raised:
            map_action('spell', str(spell_id), [], 'Sequences[THIRD_PARTY].Versions[1].Actions[1]')
        task_id = 'c' * 32
        _, destination = self.server.task_paths(task_id)
        handle = SimpleNamespace(done=True, error=TaskError(str(raised.exception)))
        self.server.tasks[task_id] = destination, handle
        state = self._json_request('GET', '/api/tasks/' + task_id)
        self.assertEqual(state['status'], 'failed', state)
        self.assertIn('99999999', state['error'])
        self.assertIn('不能映射', state['error'])
        self.assertNotIn('dps', state)
        self.assertFalse(state['result_ready'])

    def test_plain_search_request_preserves_disabled_burst_option(self) -> None:
        import interface

        writes = []
        source = SimpleNamespace(write_text=lambda text, **options: writes.append((text, options)))
        destination = self.server.task_root / ('d' * 32)
        handle = SimpleNamespace(done=False, error=None)
        self.server.task_options = {'use_burst': False}
        # Keep the plain request/switch at the real Handler boundary. The
        # plain × full HTTP/GA/physical recovery cross is deliberately retired;
        # the burst representative below retains the complete twelve-report fault.
        with patch.object(self.server, 'task_paths', return_value=(source, destination)), \
                patch.object(interface, 'start_task', return_value=handle) as start:
            created = self._json_request('POST', '/api/tasks', {
                'profile': sample_profile(), 'target_count': 1, 'scene': 'single_target'})
        self.assertEqual(created['status'], 'starting')
        self.assertEqual(self.server.tasks[created['task_id']], (destination, handle))
        self.assertEqual(writes, [(sample_profile(), {'encoding': 'utf-8', 'newline': ''})])
        start.assert_called_once()
        self.assertEqual(start.call_args.args, (source, destination))
        self.assertIs(start.call_args.kwargs['use_burst'], False)
        self.assertEqual(start.call_args.kwargs['simulation_config']['target_count'], 1)
        self.assertEqual(start.call_args.kwargs['simulation_config']['scene'], 'single_target')

    def test_task_logging_choice_overrides_only_this_request(self):
        import interface
        import dual_task

        source = SimpleNamespace(write_text=lambda *args, **kwargs: None)
        destination = self.server.task_root / ('d' * 32)
        handle = SimpleNamespace(done=True, error=None)
        imported = gse_fixture(['LOGGING', {
            'MetaData': {'SpecID': 252, 'GSEVersion': 3331}, 'Default': 1,
            'Versions': [{'Actions': [{'Type': 'Action', 'type': 'spell', 'spell': 77575}]}],
        }])
        with patch.object(self.server, 'task_paths', return_value=(source, destination)), \
                patch.object(interface, 'start_task', return_value=handle) as single, \
                patch.object(dual_task, 'start', return_value=handle) as dual:
            for default in (False, True):
                original = dict(search_config=dict(diagnostic_logging=default, diagnostics='summary',
                                                   search_timeline=True))
                self.server.task_options = deepcopy(original)
                previous = []
                for mode in ('optimize', 'import', 'dual'):
                    for choice in ('omitted', True, False):
                        with self.subTest(default=default, mode=mode, choice=choice):
                            request = dict(profile=sample_profile(), mode=mode, gse=imported,
                                sequence_name='LOGGING', version=1, gse_click_ms=300, gcd_ms=1500,
                                input_interval_ms=300)
                            if choice != 'omitted':
                                request['diagnostic_logging'] = choice
                            created = self._json_request('POST', '/api/tasks', request)
                            self.assertEqual(created['status'], 'starting')
                            options = (dual if mode == 'dual' else single).call_args.kwargs['search_config']
                            expected = default if choice == 'omitted' else choice
                            self.assertIs(options['diagnostic_logging'], expected)
                            self.assertEqual(options['diagnostics'], 'summary')
                            self.assertIs(options['search_timeline'], True)
                            self.assertEqual(self.server.task_options, original)
                            previous.append((options, expected))
                for options, expected in previous:
                    self.assertIs(options['diagnostic_logging'], expected)

    def test_served_page_uses_service_logging_only_as_initial_selection(self):
        for default in (False, True):
            self.server.task_options = dict(search_config=dict(diagnostic_logging=default))
            page = self._json_request('GET', '/')
            self.assertIn('diagnosticLogging.checked=' + str(default).lower(), page)
            self.assertNotIn('diagnosticLogging.disabled=true', page)
            self.assertIn('本次任务', page)

    def test_resume_logging_choice_inherits_default_and_rejects_invalid_or_running_requests(self):
        import dual_task
        task_id = 'e' * 32
        _, destination = self.server.task_paths(task_id)
        handle = SimpleNamespace(done=True, error=None)
        path = '/api/tasks/' + task_id + '/resume'
        with patch.object(Path, 'exists', lambda value: value.name == 'dual.json'), \
                patch.object(dual_task, 'resume', return_value=handle) as resume:
            for default in (False, True):
                self.server.task_options = dict(search_config=dict(diagnostic_logging=default))
                for body, expected in ((None, default), ({}, default),
                                       ({'diagnostic_logging': True}, True),
                                       ({'diagnostic_logging': False}, False)):
                    with self.subTest(default=default, body=body):
                        self.assertEqual(self._json_request('POST', path, body)['status'], 'starting')
                        self.assertIs(resume.call_args.kwargs['diagnostic_logging'], expected)
                        self.assertIs(self.server.task_options['search_config']['diagnostic_logging'], default)
            resume.reset_mock()
            for invalid in (None, 0, 1, 'true', [], {}):
                for endpoint in ('/api/tasks', path):
                    with self.subTest(invalid=invalid, endpoint=endpoint), self.assertRaises(HTTPError) as caught:
                        self._json_request('POST', endpoint, dict(profile=sample_profile(), diagnostic_logging=invalid))
                    self.assertEqual(caught.exception.code, 400)
                    self.assertIn('布尔值', json.loads(caught.exception.read())['error'])
            handle.done = False
            with self.assertRaises(HTTPError) as caught:
                self._json_request('POST', path, {'diagnostic_logging': False})
            self.assertIn('仍在运行', json.loads(caught.exception.read())['error'])
            resume.assert_not_called()
            self.assertEqual(self.server.tasks[task_id], (destination, handle))


    @pytest.mark.real
    def test_browser_computes_copies_and_clears_real_candidate(self):
        # 极小合法种群保留真实180ms双场原生/复测/编译/复制链；不为UI烟测运行长探索。
        import sequence
        evaluate = sequence.evaluate
        evaluated_inputs = set()

        def observe_evaluation(*args, **kwargs):
            evaluated_inputs.add((kwargs['simulation_config']['target_count'],
                                  tuple(kwargs['input_times'][:2])))
            return evaluate(*args, **kwargs)

        self.server.task_options = {'search_config': dict(iterations=2, max_processes=1)}
        from test_burst import reviewed_fixture
        import burst
        definition, reviewed_profile = reviewed_fixture()
        import result_store
        result_store.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        burst.publish(definition)
        env=os.environ.copy()
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        script=r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  // 浏览器只拦截计算请求；真实页面的可操作状态、点击和请求正文均实际执行。
  {
   const context=await browser.newContext();
   try{
    const page=await context.newPage(),submitted=[];let finishPolling=Promise.resolve(),releasePolling;
    await page.route('**/api/**',async route=>{
     const request=route.request(),path=new URL(request.url()).pathname;
     let body;
     if(path==='/api/gse/inspect')body={syntax:['Action'],sequences:[{name:'LOGGING',version_count:1,default_version:1,version_support:[{version:1,simulation_preflight_passed:true,support_status:'requires_character_validation'}]}]};
     else if(request.method()==='POST'){
      submitted.push({path,body:request.postDataJSON()});
      if(path.endsWith('/resume')){await route.fulfill({status:400,json:{error:'本次恢复未启动'}});return;}
      body={task_id:'a'.repeat(32),status:'starting'};
     }else{await finishPolling;body={status:'cancelled',phase:'done',recoverable:true,error:'本次计算已停止'};}
     await route.fulfill({json:body});
    });
    await page.goto(input.url);
    const checkbox=page.locator('#diagnosticLogging');
    assert.equal(await checkbox.isDisabled(),false);
    assert.equal(await checkbox.isChecked(),false);
    for(const selected of [true,false]){
     await checkbox.setChecked(selected);
     await page.locator('#profile').fill(input.profile);
     finishPolling=new Promise(resolve=>{releasePolling=resolve;});
     await page.locator('#start').click();
     await page.locator('#cancel').waitFor({state:'visible'});
     assert.equal(submitted.at(-1).body.mode,'dual');
     assert.equal(submitted.at(-1).body.diagnostic_logging,selected);
     const count=submitted.length;
     await checkbox.setChecked(!selected);
     assert.equal(submitted.length,count,'勾选不应修改正在运行的任务');
     assert.equal(submitted.at(-1).body.diagnostic_logging,selected);
     releasePolling();
     await page.waitForFunction(()=>!document.querySelector('#start').disabled);
     await page.locator('#resume').click();
     await page.waitForFunction(()=>!document.querySelector('#start').disabled);
     assert.ok(submitted.at(-1).path.endsWith('/resume'));
     assert.equal(submitted.at(-1).body.diagnostic_logging,!selected);
     assert.equal(await page.locator('#resume').isVisible(),true,'失败后仍可继续');
     await checkbox.setChecked(selected);
     await page.locator('#gseImport').fill('!GSE3!browser-fixture');
     await page.locator('#inspectImport').click();
     await page.locator('#importStart').click();
     await page.waitForFunction(()=>!document.querySelector('#start').disabled);
     assert.equal(submitted.at(-1).body.mode,'import');
     assert.equal(submitted.at(-1).body.diagnostic_logging,selected);
    }
    assert.equal(submitted.length,6);
   }finally{await context.close();}
  }
  // END_DIAGNOSTIC_SELECTION
  {
   const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
   try{
    const page=await context.newPage(); let state, submitted;
    page.on('request',request=>{if(request.url().endsWith('/api/tasks')&&request.method()==='POST')submitted=request.postDataJSON();});
    page.on('response',async response=>{if(response.url().includes('/api/tasks/')&&response.request().method()==='GET')state=await response.json();});
    await page.goto(input.url);
    assert.equal(await page.locator('#interval').inputValue(),'200');
    assert.equal(await page.locator('#resultSection').isVisible(),false);
    await page.locator('#interval').fill('180');
    await page.locator('#profile').fill(input.profile);
    await page.locator('#start').click();
    await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:35000});
    assert.equal(await page.locator('#resultSection').isVisible(),true,await page.locator('#error').textContent());
    const text=await page.locator('#result').inputValue();assert.match(text,/^!GSE3!/);
    assert.equal(state.input_interval_ms,180);
    assert.equal(submitted.mode,'dual');assert.equal(submitted.target_count,undefined);
    assert.equal(text,state.exports.single_target);assert.equal(state.evidence_status,'search_result');
    assert.match(await page.locator('#resultNote').innerText(),/正常场景独立复测/);
    assert.equal(Object.keys(state.exports).length,3);assert.ok(state.collection_ready);
    await page.locator('#copy').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),text);
    await page.locator('#copyCollection').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),state.collection_text);
    await page.locator('#profile').fill(input.profile+'\n# changed');
    assert.equal(await page.locator('#resultSection').isVisible(),false);
    assert.equal(await page.locator('#result').inputValue(),'');
    console.log(JSON.stringify({candidate:text,state}));
   }finally{await context.close();}
  }

 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        with _fixed_search_population([[['outbreak'], ['death_coil']]]), \
                patch.object(sequence, 'evaluate', observe_evaluation):
            result=subprocess.run([str(REPOSITORY / '.local/verify-deps/node/node.exe'),'-e',script],input=json.dumps(dict(url=self.url,profile=reviewed_profile)),
                text=True,encoding='utf-8',capture_output=True,env=env,timeout=120)
        from task import read_task
        failures = [read_task(path) for destination, handle in self.server.tasks.values()
                    for path in (destination, destination / 'single_target', destination / 'aoe')
                    if handle.done and (path / 'result.json').exists()] if result.returncode else []
        if result.returncode:
            failures.extend(str(handle.error) for _, handle in self.server.tasks.values()
                            if handle.error is not None)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr+repr(failures))
        self.assertEqual({targets for targets, _ in evaluated_inputs}, {1, 5})
        self.assertEqual({targets for targets, times in evaluated_inputs if times == (0, 180)}, {1, 5})
        self.assertEqual(len(self.server.tasks), 1, '一次开始只创建一个双场任务')
        from task import read_task
        destination, _ = next(iter(self.server.tasks.values()))
        saved = read_task(destination / 'aoe', include_search_records=True)
        self.assertEqual(saved['simulation_config']['target_count'], 5)
        self.assertEqual(saved['config']['input_interval_ms'], 180)
        self.assertTrue(saved['burst']['definition_id'])
        self.assertEqual(set(saved['final']['scenarios']), {'nominal'})
        output = json.loads(result.stdout)
        self._decode_candidate(output['candidate'], 252)
        from gse_import import decode_import
        state = output['state']
        self.assertEqual(state['status'], 'completed', state)
        self.assertEqual([scene['target_count'] for scene in state['scenes']], [1, 5])
        self.assertTrue(all(scene['total_budget_seconds'] is None for scene in state['scenes']))
        self.assertTrue(all(scene['generation'] == 2 for scene in state['scenes']))
        self.assertTrue(all(scene['search_result']['samples'] == 381 for scene in state['scenes']))
        self.assertEqual(len({scene['input_sha256'] for scene in state['scenes']}), 1)
        self.assertEqual(set(state['exports']), {'single_target', 'aoe', 'burst'})
        names = [decode_import(value)['sequences'] for value in state['exports'].values()]
        self.assertEqual(len({name for member in names for name in member}), 3)
        collection = decode_import(state['collection_text'])
        self.assertEqual(collection['payload']['type'], 'COLLECTION')
        self.assertEqual(set(collection['sequences']), {name for member in names for name in member})


    def _decode_candidate(self, candidate, expected_spec):
        import base64, zlib, cbor2
        # 游戏 12.1 实际编码 {1,"test"} 的输出；不由产品编码器生成预期值。
        self.assertEqual(zlib.decompress(base64.b64decode('a2J0KUktLgEA'), -15), b'\x82\x01\x44test')
        wire = cbor2.loads(zlib.decompress(base64.b64decode(candidate[6:]), -15))
        self.assertIsInstance(wire[0], bytes)
        self.assertIn(b'MetaData', wire[1])
        def text(value):
            if isinstance(value, bytes): return value.decode('utf-8')
            if isinstance(value, list): return [text(v) for v in value]
            if isinstance(value, dict): return {text(k): text(v) for k,v in value.items()}
            return value
        payload = text(wire)
        self.assertEqual(payload[1]['MetaData']['SpecID'], expected_spec)
        self.candidate_payload = payload

    def test_invalid_interval_is_rejected_before_creating_task(self):
        for value in (0, 49, 2001, True, 180.5, "180"):
            with self.subTest(value=value), self.assertRaises(HTTPError) as raised:
                self._json_request("POST", "/api/tasks", {"profile": sample_profile(), "input_interval_ms": value})
            self.assertEqual(raised.exception.code, 400)
        self.assertEqual(list(self.server.tasks), [])

    def test_import_rejects_gse_click_rate_that_differs_from_simulation_interval(self):
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Pause", "MS": "GCD"}]}],
        }])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "THIRD_PARTY", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 400,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("点击间隔", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})

    def test_interface_reports_native_and_export_failures_without_internal_paths(self):
        from task import TaskError
        cases = [
            ('主动能力不完整，停止模拟与导出: invalid_action', '尚未支持的主动能力'),
            ('原生引擎失败: C:\\private\\simc.exe', '引擎'),
            ('固定上游编译器失败: C:\\private\\lua.exe', '导出'),
            ('结果文件缺失，未生成可复制文本', '结果'),
        ]
        for failure, expected in cases:
            with self.subTest(failure=failure):
                message = _friendly_error(TaskError(failure))
                self.assertIn(expected, message)
                self.assertNotIn('\\', message)
                self.assertLess(len(message), 161)
        self.assertFalse(_public_state({'status': 'completed'}, self.server.output_root)['result_ready'])


if __name__ == "__main__":
    unittest.main()
