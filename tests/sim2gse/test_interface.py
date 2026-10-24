"""导入检查在内存执行；本地服务仅验证必要任务接线。"""

from __future__ import annotations

import tempfile
import threading
import time
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
from test_seed_training import memory_result_center  # noqa: E402


def _coarse_batch_keys(result):
    return {batch['data_key'] for record in result['search']['records']
            for batch in record['batches'] if batch['request']['purpose'] == 'search'}


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
        global sample_profile, _fast_evaluate, _fast_search_boundary, _initialized_starts
        from interface import _friendly_error, _public_state, create_server
        from task import run_task
        from test_character_export import sample_profile
        from test_search import _fast_evaluate, _fast_search_boundary, _initialized_starts

        self.directory = tempfile.TemporaryDirectory(prefix="sim2gse-ui-")
        self.server = create_server(Path(self.directory.name) / "输出", port=0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self) -> None:
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
        _, destination = self.server.task_paths(task_id)
        destination.mkdir()
        (destination / 'dual.json').write_text(json.dumps(dict(parent_id=task_id)), encoding='utf-8')
        checkpoint = destination / 'single_target' / 'checkpoint.json'
        checkpoint.parent.mkdir()
        checkpoint.write_bytes(b'{"preserved":true}')
        row = dict.fromkeys(PARENT_SCHEMA)
        row.update(parent_id=task_id, status='failed', phase='single_target', error='native trace failed',
                   input_sha256='frozen', definition_id='reviewed', spec_id=252,
                   config=dict(total_budget_seconds=600, input_interval_ms=200), simulation_config={},
                   rules={}, engines={}, preparation_seconds=1., packaging_seconds=0.,
                   single_target_path='single_target', aoe_path='aoe',
                   single_target_status='running', aoe_status='pending', burst_instructions='')
        for status, scene_status in [('failed', 'failed'), ('interrupted', 'incomplete')]:
            row['status'] = status
            result_store.write('dual_tasks', task_id, [row], schema=PARENT_SCHEMA)
            state = self._json_request('GET', '/api/tasks/' + task_id)
            self.assertEqual(state['status'], status)
            self.assertEqual(state['scenes'][0]['status'], scene_status)
            self.assertEqual(state['scenes'][1]['status'], 'pending')
            self.assertTrue(state['recoverable'])
            self.assertFalse(state['result_ready'])
            self.assertEqual(checkpoint.read_bytes(), b'{"preserved":true}')

    def test_legacy_dual_without_rule_snapshot_remains_readable_but_cannot_resume(self):
        import result_store
        from dual_task import PARENT_SCHEMA
        from test_search import _apl_task_boundary
        from urllib.error import HTTPError
        task_id = 'b' * 32
        _, destination = self.server.task_paths(task_id)
        destination.mkdir()
        pointer = json.dumps(dict(parent_id=task_id))
        (destination / 'dual.json').write_text(pointer, encoding='utf-8')
        schema = {key: value for key, value in PARENT_SCHEMA.items() if key != 'rule_snapshot'}
        row = dict.fromkeys(schema)
        row.update(parent_id=task_id, status='cancelled', phase='single_target', error='old cancellation',
                   input_sha256='frozen', definition_id='reviewed', spec_id=252,
                   config=dict(total_budget_seconds=600, input_interval_ms=200), simulation_config={},
                   rules={}, engines={}, preparation_seconds=1., packaging_seconds=0.,
                   single_target_path='single_target', aoe_path='aoe',
                   single_target_status='cancelled', aoe_status='pending', burst_instructions='')
        result_store.write('dual_tasks', task_id, [row], schema=schema)
        state = self._json_request('GET', '/api/tasks/' + task_id)
        self.assertEqual(state['status'], 'cancelled')
        self.assertEqual(state['total_budget_seconds'], 1200)
        self.assertEqual(state['scenes'][0]['total_budget_seconds'], 600)
        self.assertFalse(state.get('stop_policy'))
        self.assertIn('未进行最终独立复测', state['result_note'])
        self.assertEqual(state['scenes'][0]['status'], 'cancelled')
        self.assertEqual(state['scenes'][1]['status'], 'pending')
        with _apl_task_boundary(), self.assertRaises(HTTPError) as raised:
            self._json_request('POST', '/api/tasks/' + task_id + '/resume', {})
        failure = json.loads(raised.exception.read().decode('utf-8'))
        self.assertIn('身份不兼容', failure['error'])
        self.assertEqual((destination / 'dual.json').read_text(encoding='utf-8'), pointer)
        self.assertEqual(self._json_request('GET', '/api/tasks/' + task_id)['status'], 'cancelled')

    def _json_request(self, method: str, path: str, value: dict | None = None,
                      timeout: float = 3) -> dict:
        body = None if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
        request = Request(self.url + path, data=body, method=method,
                          headers={"Content-Type": "application/json"} if body else {})
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _task_state_request(self, task_id: str, deadline: float) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Task polling reached its overall test deadline")
        state = self._json_request("GET", f"/api/tasks/{task_id}", timeout=remaining)
        if time.monotonic() >= deadline:
            raise TimeoutError("Task polling reached its overall test deadline")
        return state

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
        self.assertEqual(list(self.server.task_root.iterdir()), [])

    def test_empty_submission_is_rejected_without_creating_a_task(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {"profile": "  "})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("粘贴", json.loads(raised.exception.read())['error'])
        self.assertEqual(list((Path(self.directory.name) / "输出" / "tasks").iterdir()), [])


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
        self.assertEqual(list(self.server.task_root.iterdir()), [])


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
                self.assertEqual(list(self.server.task_root.iterdir()), [])

    @pytest.mark.usefixtures('memory_result_center')
    def test_public_service_simulates_selected_import_and_returns_dps(self) -> None:
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "/targetenemy [noharm][dead]\n/cast 77575"}]}],
        }])
        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported, "target_count": 5,
            "sequence_name": "THIRD_PARTY", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        deadline = time.monotonic() + 30
        state = {}
        while time.monotonic() < deadline:
            state = self._task_state_request(created["task_id"], deadline)
            if state["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.1)
        self.assertEqual(state["status"], "completed", state)
        self.assertEqual(state["selected_sequence"], "THIRD_PARTY")
        self.assertGreater(state["dps"], 0)
        self.assertFalse(state["result_ready"])
        destination, _ = self.server.tasks[created["task_id"]]
        from task import read_task
        self.assertEqual(read_task(destination)["simulation_config"]["target_count"], 5)

    def test_public_service_reports_unmapped_import_skill_without_dps(self) -> None:
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 99999999}]}],
        }])
        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "THIRD_PARTY", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        deadline = time.monotonic() + 30
        state = {}
        while time.monotonic() < deadline:
            state = self._task_state_request(created["task_id"], deadline)
            if state["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.1)
        self.assertEqual(state["status"], "failed", state)
        self.assertIn("99999999", state["error"])
        self.assertNotIn("dps", state)

    def test_published_report_group_is_reused_after_registration_interruption(self) -> None:
        self._check_published_report_group_recovery(use_burst=False)

    def test_published_burst_report_group_is_reused_after_registration_interruption(self) -> None:
        self._check_published_report_group_recovery(use_burst=True)

    def _check_published_report_group_recovery(self, *, use_burst):
        import result_store
        import sequence
        from task import resume_task

        self.server.task_options = {'use_burst': use_burst, 'search_config': dict(
            total_budget_seconds=30, search_budget_seconds=15, candidate_limit=1,
            round_candidate_limit=1, batch_targets=tuple(range(2, 30, 2)),
            validation_batches=1, final_batches=1, iterations=2, final_iterations=2,
            scenarios=('nominal',), max_processes=1, diagnostic_logging=True)}
        original_write = result_store.write
        interrupted = False
        evaluated, published, uncommitted_at_interrupt = [], [], set()
        burst_calls = []
        profile = sample_profile()
        boundary = _fast_search_boundary
        if use_burst:
            import burst
            from test_burst import page_task_boundary, reviewed_fixture
            definition, profile = reviewed_fixture()
            result_store.DATA_ROOT.mkdir(exist_ok=True)
            burst.publish(definition)
            boundary = page_task_boundary

        def publish_then_interrupt(table, key, rows, **kwargs):
            nonlocal interrupted
            result = original_write(table, key, rows, **kwargs)
            if table == 'batches' and len(rows) == 12 and not interrupted:
                interrupted = True
                published.extend(row['batch_key'] for row in rows)
                uncommitted_at_interrupt.update(set(evaluated) - set(published))
                raise OSError('published group before registration')
            return result

        def evaluate(*args, **kwargs):
            evaluated.append(Path(args[2]).name)
            burst_calls.append(kwargs.get('burst_candidate') is not None)
            return boundary_evaluate(*args, **kwargs)

        with boundary():
            boundary_evaluate = sequence.evaluate
            with patch.object(sequence, 'evaluate', side_effect=evaluate), patch.object(
                    result_store, 'write', side_effect=publish_then_interrupt):
                created = self._json_request('POST', '/api/tasks', {
                    'profile': profile, 'target_count': 1, 'scene': 'single_target',
                    'diagnostic_logging': True})
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    state = self._task_state_request(created['task_id'], deadline)
                    if state['status'] == 'failed':
                        break
                    time.sleep(0.02)
                self.assertEqual(state['status'], 'failed', state)
                self.assertIn('published group before registration', state['error'])
            _, handle = self.server.tasks[created['task_id']]
            handle.join(5)
            with patch.object(sequence, 'evaluate', side_effect=evaluate):
                resumed = resume_task(handle.output_root, diagnostic_logging=True)
        self.assertEqual(resumed['status'], 'completed')
        self.assertTrue(_public_state(resumed, handle.output_root)['result_ready'])
        self.assertEqual(resumed['search']['native_batch_starts'], len(evaluated))
        self.assertTrue(interrupted)
        self.assertTrue(burst_calls)
        self.assertTrue(all(enabled == use_burst for enabled in burst_calls))
        self.assertEqual(len(published), 12)
        self.assertEqual(len(set(published)), 12)
        self.assertTrue(all(evaluated.count(key) == 1 for key in published))
        # 故障时尚未提交的内存尾部可重算，可靠发布的12条绝不重算。
        repeated = {key for key in evaluated if evaluated.count(key) > 1}
        self.assertLessEqual(repeated, uncommitted_at_interrupt)
        with result_store.query("SELECT batch_key FROM batches WHERE purpose = 'search'", tables=['batches']) as cursor:
            keys = [row[0] for row in cursor.fetchall()]
        self.assertEqual(set(keys), _coarse_batch_keys(resumed))
        self.assertEqual(len(keys), len(set(keys)))
        with result_store.query(
            "SELECT storage_group_key, count(*) FROM batches "
            "WHERE purpose IN ('search', 'feedback', 'nominal') GROUP BY storage_group_key"
        , tables=['batches']) as cursor:
            groups = cursor.fetchall()
        self.assertGreater(sum(row[1] for row in groups), 12)
        self.assertTrue(all(key and 1 <= count <= 12 for key, count in groups))
        self.assertTrue(any(count > 1 for _, count in groups), '同一阶段仍应批量保存报告')
        with result_store.query(
            "SELECT batch_key, report.sim.statistics.raid_dps.mean FROM batches "
            "WHERE purpose IN ('search', 'feedback', 'nominal')"
        , tables=['batches']) as cursor:
            reports = cursor.fetchall()
        self.assertEqual(len(reports), sum(row[1] for row in groups))
        self.assertEqual(len({key for key, _ in reports}), len(reports))
        self.assertTrue(all(score > 0 for _, score in reports))


    def test_resume_after_partial_group_commit_uses_unused_group_number(self) -> None:
        import sqlite3
        import shutil
        import result_store
        import sequence
        from search import TaskStore
        from task import resume_task
        self.server.task_options = {'search_config': dict(
            total_budget_seconds=30, search_budget_seconds=15, candidate_limit=1,
            round_candidate_limit=1, batch_targets=tuple(range(2, 30, 2)),
            validation_batches=1, final_batches=1, iterations=2, final_iterations=2,
            scenarios=('nominal',), max_processes=1, diagnostic_logging=True)}
        original_stage = TaskStore.stage_report
        original_commit = TaskStore._commit_report_group
        snapshot = Path(self.directory.name) / 'partial-commit.sqlite3'
        interrupted = False
        evaluated = []

        def evaluate(*args, **kwargs):
            evaluated.append(Path(args[2]).name)
            return _fast_evaluate(*args, **kwargs)

        def seed_legacy_last_report(store, key, row, stored, **kwargs):
            if len(store.report_buffer) == 11 and not interrupted:
                result_store.write_batch(key, stored,
                                         diagnostic_logging=kwargs.get('diagnostic_logging', False))
            return original_stage(store, key, row, stored, **kwargs)

        def interrupt_after_commit(store, *args, **kwargs):
            nonlocal interrupted
            original_commit(store, *args, **kwargs)
            if not kwargs.get('checkpoint', True) and not interrupted:
                interrupted = True
                with sqlite3.connect(snapshot) as target:
                    store.db.backup(target)
                target.close()
                raise OSError('stop after partial group commit')

        with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
            with patch.object(TaskStore, 'stage_report', seed_legacy_last_report), patch.object(
                    TaskStore, '_commit_report_group', interrupt_after_commit):
                created = self._json_request('POST', '/api/tasks', {
                    'profile': sample_profile(), 'target_count': 1, 'scene': 'single_target', 'diagnostic_logging': True})
                _, handle = self.server.tasks[created['task_id']]
                handle.join(30)
                self.assertTrue(interrupted)
                self.assertIsNotNone(handle.error)
            # Restore the exact durable task image at the stop, before error handling.
            shutil.copyfile(snapshot, handle.output_root / 'task.sqlite3')
            resumed = resume_task(handle.output_root, diagnostic_logging=True)
        self.assertEqual(resumed['status'], 'completed')
        self.assertEqual(resumed['search']['native_batch_starts'], len(evaluated))
        with result_store.query("SELECT batch_key FROM batches WHERE purpose='search'", tables=['batches']) as cursor:
            keys = [row[0] for row in cursor.fetchall()]
        self.assertEqual(set(keys), _coarse_batch_keys(resumed))
        self.assertEqual(len(keys), len(set(keys)))

    def test_simultaneous_identical_tasks_keep_one_logical_report_per_batch(self) -> None:
        self._assert_simultaneous_identical_tasks()

    def test_lost_report_locations_reject_duplicate_publication(self) -> None:
        import result_store
        self.server.task_options = {'search_config': dict(
            total_budget_seconds=30, search_budget_seconds=15, candidate_limit=1,
            round_candidate_limit=1, batch_targets=tuple(range(2, 30, 2)),
            validation_batches=1, final_batches=1, iterations=2, final_iterations=2,
            scenarios=('nominal',), max_processes=1)}
        original_url = self.url
        with _fast_search_boundary():
            created = self._json_request('POST', '/api/tasks', {
                'profile': sample_profile(), 'target_count': 1, 'scene': 'single_target'})
            _, handle = self.server.tasks[created['task_id']]
            handle.join(30)
            self.assertIsNone(handle.error)
            from task import read_task
            expected = _coarse_batch_keys(read_task(handle.output_root, include_search_records=True))
            self.assertTrue(expected)
            journal = result_store.DATA_ROOT / '.report-locations.jsonl'
            original = journal.read_bytes()
            for damage in ('missing', 'truncated'):
                with self.subTest(damage=damage):
                    journal.write_bytes(original)
                    if damage == 'missing':
                        journal.unlink()
                    else:
                        journal.write_bytes(original.splitlines(keepends=True)[0])
                    server = create_server(Path(self.directory.name) / damage, port=0,
                                           task_options=self.server.task_options)
                    thread = threading.Thread(target=server.serve_forever,
                                              kwargs={'poll_interval': .01}, daemon=True)
                    thread.start()
                    try:
                        self.url = f'http://127.0.0.1:{server.server_port}/'
                        created = self._json_request('POST', '/api/tasks', {
                            'profile': sample_profile(), 'target_count': 1, 'scene': 'single_target'})
                        _, second = server.tasks[created['task_id']]
                        second.join(30)
                        state = self._json_request('GET', '/api/tasks/' + created['task_id'])
                        self.assertEqual(state['status'], 'failed', state)
                        self.assertEqual(state['phase'], 'storage_unavailable', state)
                        self.assertTrue(state['storage_unavailable'] and state['recoverable'])
                        self.assertFalse(state['result_ready'])
                        self.assertIn('共享存储', state['error'])
                        self.assertIsInstance(second.error.__cause__, result_store.DataReadError)
                        self.assertIn('报告位置清单', str(second.error))
                    finally:
                        self.url = original_url
                        server.shutdown(); server.server_close(); thread.join(2)
                    with result_store.query("SELECT batch_key FROM batches WHERE purpose='search'", tables=['batches']) as cursor:
                        keys = [row[0] for row in cursor.fetchall()]
                    self.assertEqual(set(keys), expected)
                    self.assertEqual(len(keys), len(set(keys)))
            journal.write_bytes(original)

    def _assert_simultaneous_identical_tasks(self) -> None:
        import result_store
        import sequence
        from task import read_task

        self.server.task_options = {'search_config': dict(
            total_budget_seconds=30, search_budget_seconds=15, candidate_limit=1,
            round_candidate_limit=1, batch_targets=tuple(range(2, 30, 2)),
            validation_batches=1, final_batches=1, iterations=2, final_iterations=2,
            scenarios=('nominal',), max_processes=1)}
        first_reports = threading.Barrier(2)
        started = set()
        started_lock = threading.Lock()

        def evaluate(*args, **kwargs):
            destination = Path(args[2]).parents[1]
            with started_lock:
                first = destination not in started
                started.add(destination)
            if first:
                first_reports.wait(self.server.task_options['search_config']['search_budget_seconds'])
            return _fast_evaluate(*args, **kwargs)

        with _fast_search_boundary(), patch.object(sequence, 'evaluate', side_effect=evaluate):
            created = []
            for _ in range(2):
                created.append(self._json_request('POST', '/api/tasks', {
                    'profile': sample_profile(), 'target_count': 1, 'scene': 'single_target'}))
            deadline = time.monotonic() + 30
            for task in created:
                while time.monotonic() < deadline:
                    state = self._task_state_request(task['task_id'], deadline)
                    if state['status'] in {'completed', 'failed'}:
                        break
                    time.sleep(.02)
                error = self.server.tasks[task['task_id']][1].error
                self.assertEqual(state['status'], 'completed', dict(state, task_error=repr(error),
                    task_error_cause=repr(getattr(error, '__cause__', None)),
                    task_error_context=repr(getattr(error, '__context__', None))))
        with result_store.query("SELECT batch_key FROM batches WHERE purpose = 'search'", tables=['batches']) as cursor:
            keys = [row[0] for row in cursor.fetchall()]
        expected = set().union(*(_coarse_batch_keys(read_task(
            self.server.tasks[row['task_id']][1].output_root, include_search_records=True)) for row in created))
        self.assertTrue(expected)
        self.assertEqual(set(keys), expected)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIsNotNone(result_store.one('batches', 'batch_key', keys[0]))



    def test_public_search_rejects_missing_variance_without_failing_task(self) -> None:
        self._check_native_round(invalid_variance=True)

    def _check_native_round(self, *, invalid_variance=False):
        import random
        import population_training
        from types import SimpleNamespace
        from task import read_task
        from test_search import _fast_evaluate
        from test_search import _prepared_search_boundary

        calls = []
        initial = ("outbreak", "death_coil")
        better = ("death_coil", "outbreak")
        worse = ("death_coil", "outbreak", "death_coil")
        original_random = random.Random
        class NoVariationRandom(original_random):
            _randbelow = original_random._randbelow
            def random(self):
                return .999999  # This case isolates score quarantine, not the variation sampler.

        def evaluate(profile, candidate, folder, **kwargs):
            actions = tuple(action["simc_action"] for block in candidate["blocks"] for action in block)
            wanted = {initial: 90, better: 120, worse: 80}[actions]
            result = _fast_evaluate(profile, candidate, folder, **kwargs)
            damage = result["report"]["sim"]["players"][0]["collected_data"]["dps"]
            damage.update(mean=wanted, variance=1)
            result["report"]["sim"]["statistics"]["raid_dps"]["mean"] = wanted
            if invalid_variance and actions == worse:
                damage.pop("variance")
            result["summary"]["dps"] = wanted
            (Path(folder) / "native.json").write_text(json.dumps(result["report"]), encoding="utf-8")
            calls.append((actions, kwargs["iterations"], kwargs["seed"]))
            return result

        self.server.task_options = {"search_config": dict(
            total_budget_seconds=60, candidate_limit=3, round_candidate_limit=2,
            no_improvement_rounds=1, batch_targets=(32, 128, 512),
            input_interval_ms=200, iterations=2, validation_batches=2, max_processes=2)}
        with _prepared_search_boundary(self.directory.name,
                [[[name] for name in actions] for actions in (initial, better, worse)], evaluate=evaluate), \
                patch.object(population_training, 'random', SimpleNamespace(Random=NoVariationRandom)):
            created = self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "target_count": 1, "scene": "single_target",
                "input_interval_ms": 200})
            deadline = time.monotonic() + 30
            while True:
                state = self._task_state_request(created["task_id"], deadline)
                if state["status"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(.02)
        self.assertEqual(state["status"], "completed", state)
        self.assertTrue(state["result_ready"])
        search_calls = [(actions, count) for actions, count, _ in calls if count == 32]
        self.assertEqual([n for a, n in search_calls if a == worse], [32, 32])
        self.assertEqual([n for a, n in search_calls if a == better], [32])
        self.assertEqual(state["search_result"]["dps"], 120)
        _, handle = self.server.tasks[created["task_id"]]
        handle.join(5)
        result = read_task(handle.output_root, include_search_records=True)
        self.assertEqual(result['search']['effective_population_size'], 2)
        rejected, = result['search']['coarse_rejections'].values()
        self.assertEqual(rejected['attempts'], 2)
        self.assertTrue(all(row['kind'] == 'candidate_score' for row in rejected['failures']))
        self.assertEqual(len(result['final']['scenarios']['nominal']['finalists']), 2)
        self.assertTrue(all('rule_diagnostics' not in row for row in result['search']['records']))




    @pytest.mark.usefixtures('memory_result_center')
    def test_public_search_reduces_wait_clicks_and_native_evaluates_selected_candidate(self) -> None:
        import cbor2
        import codec
        import engine
        import search
        import sequence
        from task import read_task
        from test_search import _fast_initialization

        real_evaluate = sequence.evaluate
        capabilities = {
            "actions": [
                dict(kind="spell", spell_id=77575, simc_action="outbreak", name="Outbreak",
                     gcd_ms=1500, base_spell_id=77575),
                dict(kind="spell", spell_id=47541, simc_action="death_coil", name="Death Coil",
                     gcd_ms=1500, base_spell_id=47541),
                dict(kind="spell", spell_id=55090, simc_action="scourge_strike", name="Scourge Strike",
                     gcd_ms=1500, base_spell_id=55090),
            ],
            "precombat_actions": [], "sources": [], "protocol": 3,
            "scope": "test", "coverage": "constructed-test-boundary",
        }

        def inspect(_reference, folder):
            # Constructed static GCD supports the requested interval without one-empty-click syntax.
            for action in _reference['static_snapshot']['actions']:
                action['gcd_ms'] = 1500
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "catalogue.json").write_text(json.dumps(capabilities), encoding="utf-8")
            return capabilities

        initial = [["outbreak"], dict(kind="WaitClicks", clicks=3), ["death_coil"]]

        wait_candidates = {300: {}}
        native_evaluations = []
        active_interval = 300

        def evaluate(profile, candidate, folder, **kwargs):
            blocks = [[action["simc_action"] for action in block]
                      for block in candidate["blocks"]]
            clicks = sequence.compiled_program(candidate)
            self.assertEqual([click or [] for click in clicks], blocks)
            waits = [node for node in candidate["program"]["nodes"] if node["kind"] == "Pause"]
            if waits:
                interval = active_interval
                counts = tuple(node["clicks"] for node in waits)
                wait_candidates[interval].setdefault(counts, candidate)
                if counts == (2,) and interval not in {row[0] for row in native_evaluations}:
                    self.assertEqual(kwargs["input_times"][:3], [0, interval, interval * 2])
                    result = real_evaluate(profile, candidate, folder, **kwargs)
                    native_evaluations.append((interval, candidate, result))
                    self.assertEqual(result["blocks"], blocks)
                    self.assertEqual(result["native_blocks"], blocks)
                score_offset = 1000 if any(
                    native_interval == interval and native_candidate["text"] == candidate["text"]
                    for native_interval, native_candidate, _ in native_evaluations
                ) else 0
                # 与原用例相同：实际原生核回放，搜索分差由构造评分边界控制。
                result = _fast_evaluate(profile, candidate, folder, score_offset=score_offset, **kwargs)
            else:
                result = _fast_evaluate(profile, candidate, folder, **kwargs)
            return result

        self.server.task_options = {
            "search_config": {
                "total_budget_seconds": 60,
                "search_budget_seconds": 30,
                "candidate_limit": 3,
                "round_candidate_limit": 2,
                "batch_targets": (2,),
                "validation_batches": 2,
                "final_batches": 20,
                "iterations": 2,
                "final_iterations": 100,
                "scenarios": ("nominal", "jitter", "slow", "pause", "phase"),
                "max_processes": 1,
                "random_seed": 20260926,
            }
        }
        real_gse_runner = codec.run_command
        with _fast_initialization(real_engine=True), \
             patch.object(codec, "run_command", side_effect=real_gse_runner), \
             patch.object(engine, "inspect", side_effect=inspect), \
             patch.object(sequence, "check_report", new=engine.check_report), \
             _initialized_starts([initial, [["outbreak"], dict(kind="WaitClicks", clicks=2), ["death_coil"]]]), \
             patch.object(sequence, "evaluate", side_effect=evaluate):
            interval = 300
            active_interval = interval
            created = self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "target_count": 1, "scene": "single_target",
                "input_interval_ms": interval,
            })
            deadline = time.monotonic() + 45
            state = {}
            while time.monotonic() < deadline:
                state = self._task_state_request(created["task_id"], deadline)
                if state["status"] in {"completed", "validation_incomplete", "failed", "cancelled"}:
                    break
                time.sleep(0.05)
            handle = self.server.tasks[created["task_id"]][1]
            handle.join(5)
            saved = read_task(handle.output_root, include_search_records=True)

        self.assertEqual(state["status"], "completed", state)
        self.assertEqual(state["evidence_status"], "search_result")
        self.assertEqual(state["input_interval_ms"], interval)
        self.assertEqual(saved['candidate']['text'], state['candidate_text'])
        self.assertTrue(wait_candidates[interval], f"搜索未在 {interval} 毫秒间隔评价空点击候选")
        self.assertGreaterEqual(len(wait_candidates[interval]), 2,
                                "不同 WaitClicks 次数未作为不同候选评价")
        self.assertEqual(len({candidate["text"] for candidate in wait_candidates[interval].values()}),
                         len(wait_candidates[interval]))
        selected_wait = next((candidate for candidate in wait_candidates[interval].values()
                              if candidate["text"] == state["candidate_text"]), None)
        self.assertIsNotNone(selected_wait,
                             f"公开任务在 {interval} 毫秒间隔没有选择 WaitClicks 候选")
        self.assertEqual(saved['candidate']['program'], selected_wait['program'])
        native_wait = next((candidate for native_interval, candidate, _ in native_evaluations
                            if native_interval == interval), None)
        self.assertIsNotNone(native_wait,
                             f"{interval} 毫秒间隔没有真实评价的 WaitClicks 候选")
        self.assertEqual(selected_wait["text"], native_wait["text"],
                         f"{interval} 毫秒间隔最终候选没有经过真实原生评价")
        payload = cbor2.loads(zlib.decompress(base64.b64decode(state["candidate_text"][6:]), -15))
        actions = payload[1][b"Versions"][0][b"Actions"]
        exported_waits = [action for action in actions if action[b"Type"] == b"Pause"]
        expected_clicks = [node["clicks"] for node in selected_wait["program"]["nodes"]
                           if node["kind"] == "Pause"]
        self.assertEqual([action[b"Clicks"] for action in exported_waits], expected_clicks)
        self.assertTrue(exported_waits and all(action[b"Clicks"] >= 2 for action in exported_waits))
        self.assertTrue(all(all(count >= 2 for count in counts)
                            for counts in wait_candidates[interval]))
        self.assertTrue(next(iter(wait_candidates[interval].values()))["text"].startswith("!GSE3!"))

        self.assertEqual({row[0] for row in native_evaluations}, {300},
                         "空点击候选必须进入真实原生评价")
        for interval, candidate, result in native_evaluations:
            self.assertEqual(result["input_times"][:3], [0, interval, interval * 2])
            self.assertEqual(candidate["precombat_count"], 0)
            wait = next(node for node in candidate["program"]["nodes"] if node["kind"] == "Pause")
            empty_clicks = [click for click in candidate["compiled_program"]["clicks"]
                            if click["kind"] == "EmptyClick"
                            and click["source"]["path"] == wait["source"]["path"]]
            self.assertEqual(len(empty_clicks), wait["clicks"])
            self.assertTrue(all(click["source"] == wait["source"] for click in empty_clicks))

            payload = cbor2.loads(zlib.decompress(base64.b64decode(candidate["text"][6:]), -15))
            actions = payload[1][b"Versions"][0][b"Actions"]
            pause_index = int(wait["source"]["gse_path"]) - 1
            self.assertEqual(actions[pause_index][b"Type"], b"Pause")
            self.assertEqual(actions[pause_index][b"Clicks"], wait["clicks"])
            all_empty = [step for step in candidate["compiled_steps"] if step["type"] == "click"]
            self.assertEqual(len(all_empty), sum(node["clicks"] for node in candidate["program"]["nodes"]
                                                if node["kind"] == "Pause"))
            compiled_empty = [step for step in all_empty if step["blockPath"] == wait["source"]["gse_path"]]
            self.assertEqual(len(compiled_empty), wait["clicks"])
            self.assertEqual([step["blockPath"] for step in compiled_empty],
                             [wait["source"]["gse_path"]] * wait["clicks"])


    def test_completed_task_is_not_visible_before_its_result_is_reliably_saved(self) -> None:
        import search
        import task

        waiting, heartbeat, release = threading.Event(), threading.Event(), threading.Event()
        store_run, publish = task._store_run, search.TaskStore.publish
        self.server.task_options = {"search_config": dict(
            total_budget_seconds=60, search_budget_seconds=30, candidate_limit=1,
            batch_targets=(2,), iterations=2, validation_batches=1, final_batches=1,
            final_iterations=2, scenarios=("nominal",), max_processes=1, random_seed=37,
        )}

        def held_result(destination, result, *, state=None):
            if result.get("status") == "completed":
                waiting.set()
                if not release.wait(5):
                    raise AssertionError("result persistence was not released")
            return store_run(destination, result, state=state)

        def published_heartbeat(store):
            publish(store)
            if waiting.is_set():
                heartbeat.set()

        with _fast_search_boundary(), _initialized_starts([[['outbreak']]]), \
                patch.object(task, "_store_run", side_effect=held_result), \
                patch.object(search.TaskStore, "publish", published_heartbeat):
            created = self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "target_count": 1, "scene": "single_target"})
            handle = self.server.tasks[created["task_id"]][1]
            try:
                self.assertTrue(waiting.wait(5), "task never reached result persistence")
                self.assertTrue(heartbeat.wait(5), "held task did not publish a heartbeat")
                pending = self._json_request("GET", "/api/tasks/" + created["task_id"])
                self.assertEqual(pending["status"], "running", pending)
                self.assertFalse(pending["result_ready"], pending)
            finally:
                release.set()
                handle.join(5)
            self.assertTrue(handle.done)
            completed = self._json_request("GET", "/api/tasks/" + created["task_id"])
        self.assertEqual(completed["status"], "completed", completed)
        self.assertTrue(completed["result_ready"], completed)

    def test_browser_computes_copies_and_clears_real_candidate(self):
        # 极小合法种群保留真实180ms双场原生/复测/编译/复制链；不为UI烟测运行长探索。
        import sequence
        evaluate = sequence.evaluate
        evaluated_inputs = set()

        def observe_evaluation(*args, **kwargs):
            evaluated_inputs.add((kwargs['simulation_config']['target_count'],
                                  tuple(kwargs['input_times'][:2])))
            return evaluate(*args, **kwargs)

        self.server.task_options = {'search_config': dict(total_budget_seconds=120,
            search_budget_seconds=90,candidate_limit=1,batch_targets=(2,),
            validation_batches=1,final_batches=1,iterations=2,final_iterations=2,
            scenarios=('nominal',),max_processes=1)}
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
        import random
        import population_training
        from types import SimpleNamespace
        original_random = random.Random
        class NoVariationRandom(original_random):
            _randbelow = original_random._randbelow
            def random(self):
                return .999999  # Only freeze the random gate; real GA still commits its two complete generations.
        with _initialized_starts([[['outbreak'], ['death_coil']]]), \
                patch.object(population_training, 'random', SimpleNamespace(Random=NoVariationRandom)), \
                patch.object(sequence, 'evaluate', observe_evaluation):
            result=subprocess.run(['node','-e',script],input=json.dumps(dict(url=self.url,profile=reviewed_profile)),
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

    @staticmethod
    def _ui_score(profile, candidate, folder, *, burst_candidate=None, input_sources=None, **kwargs):
        """Construct scores only; browser, preparation, compiler and Windows IO stay real."""
        from test_search import _fast_evaluate
        result = _fast_evaluate(profile, candidate, folder, **kwargs)
        targets = (kwargs.get('simulation_config') or {}).get('target_count', 1)
        report = result['report']['sim']
        report['targets'] = [dict(report['targets'][0]) for _ in range(targets)]
        for event in result['trace'] if input_sources is not None else []:
            source = input_sources[event['origin'] - 1]
            event.update(source=source, source_origin=input_sources[:event['origin']].count(source))
        (Path(folder) / 'native.json').write_text(json.dumps(result['report']), encoding='utf-8')
        return result


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
        native_cases = [
            ('native_default', (REPOSITORY / 'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8')),
            ('native_unsupported', (REPOSITORY / 'tests/sim2gse/fixtures/holy-paladin.simc').read_text(encoding='utf-8')),
        ]
        for failure, profile in native_cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'input.simc'
                source.write_text(profile, encoding='utf-8')
                with self.assertRaisesRegex(TaskError, '原生未提供'):
                    run_task(source, Path(directory) / 'task', mode='single',
                             search_config={'diagnostic_logging': True})
                if failure == 'native_default':
                    invocation = json.loads((Path(directory) / 'task/reference/invocation.json').read_text(encoding='utf-8'))
                    self.assertFalse(any(arg.startswith('allow_experimental_specializations=')
                                         for arg in invocation['command']))
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
        self.assertFalse(_public_state({'status': 'completed'}, Path(self.directory.name))['result_ready'])


    def test_dual_freezes_timeline_setting_and_preserves_storage_failure_recovery(self):
        import os
        import result_store
        result_store.DATA_ROOT.mkdir(exist_ok=True)
        import sequence
        import burst
        from test_burst import page_task_boundary, reviewed_fixture
        from test_search import _fast_initialization
        definition, profile = reviewed_fixture()
        burst.publish(definition)
        import simulation_config
        path = Path(self.directory.name) / 'settings.toml'
        path.write_text('[search]\nsearch_timeline=true\n', encoding='utf-8')
        self.server.task_options = {'search_config': dict(candidate_limit=1, batch_targets=(2,),
            iterations=2, validation_batches=1, input_interval_ms=200)}
        edited = []
        with patch.object(simulation_config, 'DEFAULT_PATH', path), _fast_initialization(), page_task_boundary():
            evaluate = sequence.evaluate
            def edit_after_start(*args, **kwargs):
                if not edited:
                    path.write_text('[search]\nsearch_timeline=false\n', encoding='utf-8')
                    edited.append(True)
                return evaluate(*args, **kwargs)
            with patch.object(sequence, 'evaluate', side_effect=edit_after_start):
                created = self._json_request('POST', '/api/tasks', {'profile':profile, 'mode':'dual',
                    'input_interval_ms':200})
                handle = self.server.tasks[created['task_id']][1]
                handle.join(20)
                self.assertTrue(handle.done)
                detail = self._json_request('GET', '/api/tasks/' + created['task_id'])
        self.assertEqual(detail['status'], 'completed', detail)
        self.assertTrue(edited)
        curves = [json.loads(next((handle.output_root / scene).glob('search-timeline-*.json')).read_text(encoding='utf-8'))
                  for scene in ('single_target', 'aoe')]
        self.assertGreater(curves[1]['search_start_seconds'], curves[0]['call_seconds'])
        self.assertEqual([curve['context']['simulation_config']['target_count'] for curve in curves], [1, 5])
        from task import read_task
        self.assertTrue(all(read_task(handle.output_root / scene)['config']['search_timeline']
                            for scene in ('single_target', 'aoe')))
        moved = result_store.DATA_ROOT.with_name('temporarily-unavailable')
        result_store.DATA_ROOT.rename(moved)
        try:
            state = self._json_request('GET', '/api/tasks/' + created['task_id'])
            self.assertEqual(state['status'], 'failed')
            self.assertTrue(state['recoverable'])
            self.assertIn('存储', state['error'])
            self.assertFalse(state['result_ready'])
        finally:
            moved.rename(result_store.DATA_ROOT)
        restored = self._json_request('GET', '/api/tasks/' + created['task_id'])
        self.assertEqual(restored['status'], 'completed')
        self.assertTrue(restored['collection_ready'])


if __name__ == "__main__":
    unittest.main()
