"""任务四：三步界面通过本地服务接入真实任务入口。"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import json
import base64
import os
import subprocess
import zlib
from contextlib import nullcontext
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import sys

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))
sys.path.insert(0, str(REPOSITORY / "tests" / "sim2gse"))

from interface import _friendly_error, _public_state, create_server  # noqa: E402
from task import TaskError, run_task  # noqa: E402
from test_character_export import sample_profile  # noqa: E402
from test_search import _fast_search_boundary  # noqa: E402


def gse_fixture(payload):
    import cbor2
    from codec import wire_value
    return "!GSE3!" + base64.b64encode(zlib.compress(cbor2.dumps(wire_value(payload)), wbits=-15)).decode("ascii")


def gse_cbor_text_fixture(payload):
    import cbor2
    return "!GSE3!" + base64.b64encode(zlib.compress(cbor2.dumps(payload), wbits=-15)).decode("ascii")


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
GSE_PROTECTED_COLLECTION_SEQUENCE_VECTOR = (
    "!GSE3!+1ICEiIyQlJicoKSorMoOFyqPhNN1YfERp5oUsrO/2zVKXHka7E/VPMT1L9LD845xEagPNMvtXVhv0CqeNYpewT5FQaKmK8Qru9EVVETd2suCP9MToI6W7BLmLzaZb4HoF4ewOXE5gNBupjzZhAZEpY6VrFHj6fA=="
)


class InterfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="sim2gse-ui-")
        self.server = create_server(Path(self.directory.name) / "输出", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self) -> None:
        from task import cancel_task
        for _,handle in list(self.server.tasks.values()):
            if not handle.done:
                cancel_task(handle)
                handle.join(5)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def test_homepage_is_the_real_three_step_shell(self) -> None:
        with urlopen(self.url, timeout=2) as response:
            page = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn('id="profile"', page)
        self.assertIn('id="progressText"', page)
        self.assertIn('id="resultSection"', page)
        self.assertIn('id="copy"', page)
        self.assertIn('hidden', page.split('id="resultSection"', 1)[1].split(">", 1)[0])
        self.assertNotIn("演示进度", page)
        self.assertNotIn("原型尚未连接", page)
        self.assertIn('id="gseImport"', page)
        self.assertIn('id="inspectImport"', page)
        self.assertIn('id="importSequence"', page)
        self.assertIn('id="importStart"', page)
        self.assertIn('importStart.disabled=running||!preflightPassed', page)
        self.assertIn('simulation_preflight_passed===true', page)
        self.assertIn('角色技能和物品映射尚未核对', page)
        self.assertIn('selected.support_reason', page)
        self.assertIn('importStart.disabled=true', page)
        self.assertNotIn('id="gseClick"', page)
        self.assertIn('gse_click_ms:Number(interval.value)', page)

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

    def test_empty_submission_is_rejected_without_creating_a_task(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {"profile": "  "})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("粘贴", json.loads(raised.exception.read())['error'])
        self.assertEqual(list((Path(self.directory.name) / "输出" / "tasks").iterdir()), [])

    def test_import_inspection_lists_versions_and_nested_syntax_without_simulating(self) -> None:
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [
                {"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]},
                {"Actions": [{"Type": "Loop", "Repeat": "2", 1: {"Type": "Pause", "Clicks": 2}}]},
            ],
        }])
        try:
            result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        except HTTPError as error:
            self.fail(error.read().decode("utf-8"))
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["sequences"][0]["name"], "THIRD_PARTY")
        self.assertEqual(result["sequences"][0]["version_count"], 2)
        self.assertEqual(set(result["syntax"]), {"Action", "Loop", "Pause"})
        self.assertFalse(result["simulation_started"])
        self.assertEqual(list((Path(self.directory.name) / "输出" / "tasks").iterdir()), [])

    def test_import_inspection_accepts_direct_sequence_object(self) -> None:
        imported = gse_fixture({
            "MetaData": {"Name": "DIRECT_SEQUENCE", "SpecID": 252, "GSEVersion": 3331},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]}],
        })
        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["format"], "direct")
        self.assertEqual(result["sequences"][0]["name"], "DIRECT_SEQUENCE")

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

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["raw_import"], imported)
        self.assertEqual(result["raw_payload"], payload)
        self.assertEqual(result["payload_cbor_base64"], base64.b64encode(
            cbor2.dumps(wire_value(payload))).decode("ascii"))
        self.assertFalse(result["simulation_started"])

    def test_import_inspection_accepts_upstream_cbor_text_strings(self) -> None:
        payload = ["TEXT_CBOR", {
            "MetaData": {"Name": "TEXT_CBOR", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                          "macro": "/cast 77575"}]}],
        }]

        try:
            result = self._json_request("POST", "/api/gse/inspect", {
                "gse": gse_cbor_text_fixture(payload),
            })
        except HTTPError as error:
            self.fail(error.read().decode("utf-8"))

        self.assertEqual(result["raw_payload"], payload)
        self.assertEqual(result["sequences"][0]["name"], "TEXT_CBOR")
        self.assertEqual(result["status"], "decoded")

    def test_import_inspection_decodes_fixed_protected_sequence_vector(self) -> None:
        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": GSE_PROTECTED_SEQUENCE_VECTOR,
        })

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

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("密钥编号", error)
        self.assertIn("2", error)

    def test_import_inspection_decodes_fixed_protected_variable_and_macro_vectors(self) -> None:
        variable = self._json_request("POST", "/api/gse/inspect", {
            "gse": GSE_PROTECTED_VARIABLE_VECTOR,
        })
        macro = self._json_request("POST", "/api/gse/inspect", {
            "gse": GSE_PROTECTED_MACRO_VECTOR,
        })

        self.assertEqual(variable["format"], "protected")
        self.assertEqual(variable["protected_object_type"], "VARIABLE")
        self.assertEqual(variable["variables"]["PVAR"]["funct"], "return GSE.V.Other()")
        self.assertEqual(variable["variables"]["PVAR"]["CustomField"], [1, None])
        self.assertEqual(variable["sequences"], [])
        self.assertEqual(macro["format"], "protected")
        self.assertEqual(macro["protected_object_type"], "MACRO")
        self.assertEqual(macro["macros"]["PMAC"]["macro"], "/cast 77575\n/use 13")
        self.assertEqual(macro["macros"]["PMAC"]["CustomField"], "kept")

    def test_import_inspection_decodes_unprotected_standalone_variable_and_macro(self) -> None:
        variable_payload = {"objectType": "VARIABLE", "name": "PLAIN_VARIABLE",
                            "funct": "return 7", "Custom": None}
        macro_payload = {"objectType": "MACRO", "name": "PLAIN_MACRO",
                         "macro": "/cast 77575", "Custom": "kept"}
        variable_import = gse_fixture(variable_payload)
        macro_import = gse_fixture(macro_payload)

        variable = self._json_request("POST", "/api/gse/inspect", {
            "gse": variable_import,
        })
        macro = self._json_request("POST", "/api/gse/inspect", {
            "gse": macro_import,
        })

        self.assertEqual(variable["status"], "decoded")
        self.assertEqual(variable["format"], "direct")
        self.assertEqual(variable["content_format"], "object")
        self.assertIsNone(variable["protected_object_type"])
        self.assertEqual(variable["object_type"], "VARIABLE")
        self.assertEqual(variable["raw_import"], variable_import)
        self.assertEqual(variable["raw_payload"], variable_payload)
        self.assertEqual(variable["variables"]["PLAIN_VARIABLE"]["funct"], "return 7")
        self.assertIsNone(variable["variables"]["PLAIN_VARIABLE"]["Custom"])
        self.assertEqual(variable["sequences"], [])
        self.assertEqual(macro["status"], "decoded")
        self.assertEqual(macro["format"], "direct")
        self.assertEqual(macro["content_format"], "object")
        self.assertIsNone(macro["protected_object_type"])
        self.assertEqual(macro["object_type"], "MACRO")
        self.assertEqual(macro["raw_import"], macro_import)
        self.assertEqual(macro["raw_payload"], macro_payload)
        self.assertEqual(macro["macros"]["PLAIN_MACRO"]["macro"], "/cast 77575")
        self.assertEqual(macro["macros"]["PLAIN_MACRO"]["Custom"], "kept")
        self.assertEqual(macro["sequences"], [])

    def test_import_inspection_reports_missing_protected_decoder_dependency_as_bad_request(self) -> None:
        import builtins
        from unittest.mock import patch

        original_import = builtins.__import__
        def without_cryptography(name, *args, **kwargs):
            if name == "cryptography" or name.startswith("cryptography."):
                raise ModuleNotFoundError("test simulated missing cryptography")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_cryptography):
            with self.assertRaises(HTTPError) as raised:
                self._json_request("POST", "/api/gse/inspect", {
                    "gse": GSE_PROTECTED_SEQUENCE_VECTOR,
                })

        self.assertEqual(raised.exception.code, 400)
        self.assertIn("cryptography==50.0.1", json.loads(raised.exception.read())["error"])

    def test_import_inspection_accepts_numeric_string_version_map(self) -> None:
        sequence = {
            "MetaData": {"Name": "DRUSS_ST", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": {"1": {"Actions": [{"Type": "Action", "type": "macro",
                                                "macro": "/cast 77575"}]}},
        }
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"DRUSS_ST": sequence}, "Variables": {}, "Macros": {},
        }}

        try:
            result = self._json_request("POST", "/api/gse/inspect", {
                "gse": gse_cbor_text_fixture(payload),
            })
        except HTTPError as error:
            self.fail(error.read().decode("utf-8"))

        self.assertEqual(result["sequences"][0]["name"], "DRUSS_ST")
        self.assertEqual(result["sequences"][0]["version_count"], 1)
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["DRUSS_ST"]["Versions"],
                         {"1": {"Actions": [{"Type": "Action", "type": "macro",
                                               "macro": "/cast 77575"}]}})

    def test_import_inspection_preserves_sparse_version_map_indexes(self) -> None:
        sequence = {
            "MetaData": {"Name": "SPARSE", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": {
                "1": {"Actions": [{"Type": "Action", "type": "macro", "macro": "/cast 77575"}]},
                "3": {"Actions": [{"Type": "Pause", "Clicks": 2}]},
            },
        }
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"SPARSE": sequence}, "Variables": {}, "Macros": {},
        }}

        try:
            result = self._json_request("POST", "/api/gse/inspect", {
                "gse": gse_cbor_text_fixture(payload),
            })
        except HTTPError as error:
            self.fail(error.read().decode("utf-8"))

        member = result["sequences"][0]
        self.assertEqual(member["version_count"], 2)
        self.assertEqual([version["version"] for version in member["versions"]], [1, 3])
        self.assertEqual(member["versions"][1]["raw_version"]["Actions"][0]["Type"], "Pause")
        self.assertTrue(any("gap" in reason.lower() for reason in member["parse_warnings"]))

    def test_import_inspection_preserves_sparse_actions_but_blocks_simulation(self) -> None:
        action = {"Type": "Action", "type": "spell", "spell": 77575}
        cases = [
            ("TOP_GAP", {"1": action, "3": action},
             "Sequences[TOP_GAP].Versions[1].Actions[3]"),
            ("LOOP_GAP", [{"Type": "Loop", "Repeat": 2,
                           "1": action, "3": action}],
             "Sequences[LOOP_GAP].Versions[1].Actions[1][3]"),
            ("IF_GAP", [{"Type": "If", "Variable": "=true",
                         "1": {"1": action, "3": action}}],
             "Sequences[IF_GAP].Versions[1].Actions[1][1][3]"),
        ]
        for name, actions, expected_path in cases:
            payload = [name, {"MetaData": {"Name": name, "SpecID": 252, "GSEVersion": 3332},
                              "Default": 1, "Versions": [{"Actions": actions}]}]
            with self.subTest(name=name):
                result = self._json_request("POST", "/api/gse/inspect", {
                    "gse": gse_cbor_text_fixture(payload),
                })
                member = result["sequences"][0]
                self.assertEqual(member["versions"][0]["raw_version"]["Actions"], actions)
                support = member["version_support"][0]
                self.assertFalse(support["simulation_preflight_passed"])
                self.assertIn(expected_path, support["support_reason"])
                self.assertTrue(any(expected_path in warning for warning in member["parse_warnings"]))

    def test_import_start_rejects_sparse_actions_before_creating_a_task(self) -> None:
        payload = ["TOP_GAP", {
            "MetaData": {"Name": "TOP_GAP", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": {"1": {"Type": "Action", "type": "spell", "spell": 77575},
                                        "3": {"Type": "Action", "type": "spell", "spell": 49998}}}],
        }]

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import",
                "gse": gse_cbor_text_fixture(payload), "sequence_name": "TOP_GAP", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500,
            })

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("动作索引有空洞", error)
        self.assertIn("Sequences[TOP_GAP].Versions[1].Actions[3]", error)
        self.assertEqual(list((Path(self.directory.name) / "输出" / "tasks").iterdir()), [])

    def test_import_start_uses_actual_sparse_version_ids_without_index_errors(self) -> None:
        payload = {"type": "COLLECTION", "payload": {"Sequences": {"SPARSE": {
            "MetaData": {"Name": "SPARSE", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": {
                "1": {"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]},
                "3": {"Actions": [{"Type": "Pause", "Clicks": 2}]},
            },
        }}}}
        imported = gse_cbor_text_fixture(payload)
        base = {"profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "SPARSE", "gse_click_ms": 300, "gcd_ms": 1500}

        with self.assertRaises(HTTPError) as sparse:
            self._json_request("POST", "/api/tasks", dict(base, version=3))
        self.assertEqual(sparse.exception.code, 400)
        self.assertIn("版本索引有空洞", json.loads(sparse.exception.read())["error"])

        with self.assertRaises(HTTPError) as absent:
            self._json_request("POST", "/api/tasks", dict(base, version=2))
        self.assertEqual(absent.exception.code, 400)
        self.assertIn("版本无效", json.loads(absent.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})
        self.assertEqual(list(self.server.task_root.iterdir()), [])

    def test_import_inspection_reports_each_known_block_field_path(self) -> None:
        actions = [
            {"Type": "Action", "type": "pet", "action": "Assist", "macro": "raw pet macro"},
            {"Type": "Repeat", "Interval": "4", "spell": 77575, "macro": "/cast 77575"},
            {"Type": "Loop", "Repeat": "2", "StepFunction": "ReversePriority",
             "1": {"Type": "Pause", "Clicks": 2, "MS": "GCD"}},
            {"Type": "If", "Variable": "=GSE.V.CustomFlag()", "1": [
                {"Type": "Action", "type": "toy", "toy": 123, "macro": "=GSE.V.Macro()"}],
             "2": [{"Type": "Embed", "Sequence": "CHILD"}]},
        ]
        payload = {"type": "COLLECTION", "payload": {"Sequences": {
            "MATRIX": {"MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
                       "Versions": [{"Actions": actions}]},
            "CHILD": {"MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
                      "Versions": [{"Actions": [{"Type": "Action", "type": "spell",
                                                   "spell": 77575}]}]},
        }, "Variables": {"CustomFlag": {"name": "CustomFlag", "funct": "return true",
                                             "Dependencies": {"Variables": ["Other"]},
                                             "ExplicitNull": None}},
            "Macros": {"Burst": {"name": "Burst", "macro": "/cast 77575\n/use 13",
                                   "UnknownMacroField": [1, "two"]}}}}
        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_cbor_text_fixture(payload),
        })

        member = next(row for row in result["sequences"] if row["name"] == "MATRIX")
        self.assertEqual(member["versions"][0]["source_path"], "Sequences[MATRIX].Versions[1]")
        self.assertEqual(member["versions"][0]["raw_version"]["Actions"], actions)
        self.assertEqual(member["raw_sequence"]["Versions"][0]["Actions"], actions)
        self.assertEqual(result["raw_variables"], payload["payload"]["Variables"])
        self.assertEqual(result["raw_macros"], payload["payload"]["Macros"])
        self.assertEqual(result["variables"], {})
        self.assertEqual(result["macros"], {})
        self.assertEqual({block["source_path"] for block in result["collection_compatibility_blocks"]}, {
            "Variables[CustomFlag]", "Macros[Burst]",
        })
        self.assertFalse(member["version_support"][0]["simulation_preflight_passed"])
        locations = {(row["type"], row["path"]) for row in result["syntax_locations"]}
        self.assertEqual(locations, {
            ("Action", "Sequences[MATRIX].Versions[1].Actions[1]"),
            ("Repeat", "Sequences[MATRIX].Versions[1].Actions[2]"),
            ("Loop", "Sequences[MATRIX].Versions[1].Actions[3]"),
            ("Pause", "Sequences[MATRIX].Versions[1].Actions[3][1]"),
            ("If", "Sequences[MATRIX].Versions[1].Actions[4]"),
            ("Action", "Sequences[MATRIX].Versions[1].Actions[4][1][1]"),
            ("Embed", "Sequences[MATRIX].Versions[1].Actions[4][2][1]"),
            ("Action", "Sequences[CHILD].Versions[1].Actions[1]"),
        })
        self.assertEqual(member["versions"][0]["raw_version"]["Actions"][3]["Variable"],
                         "=GSE.V.CustomFlag()")

    def test_import_inspection_preserves_every_action_subtype_and_raw_macro_text(self) -> None:
        actions = [
            {"Type": "Action", "type": "spell", "spell": 77575},
            {"Type": "Action", "type": "item", "item": 13},
            {"Type": "Action", "type": "pet", "action": "Assist"},
            {"Type": "Action", "type": "toy", "toy": 12345},
            {"Type": "Action", "type": "macro", "macro": "#showtooltip\n/cast [combat] 77575"},
            {"Type": "Action", "macro": "inferred macro text"},
            {"Type": "Action"},
            {"Type": "Repeat", "type": "pet", "action": "Attack", "Interval": "3"},
        ]
        payload = ["ACTION_FIELDS", {
            "MetaData": {"Name": "ACTION_FIELDS", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1, "Versions": [{"Actions": actions}],
        }]

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["sequences"][0]["versions"][0]["raw_version"]["Actions"], actions)
        self.assertEqual([row["path"] for row in result["syntax_locations"]], [
            f"Sequences[ACTION_FIELDS].Versions[1].Actions[{index}]"
            for index in range(1, len(actions) + 1)
        ])

    def test_import_inspection_blocks_untyped_variable_and_macro_tables_without_sequences(self) -> None:
        payload = {"type": "COLLECTION", "payload": {
            "Variables": {"V": {"name": "V", "funct": "return 7", "Custom": None}},
            "Macros": {"M": {"name": "M", "macro": "/cast 77575"}},
        }}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_cbor_text_fixture(payload),
        })

        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["sequences"], [])
        self.assertEqual(result["raw_variables"], payload["payload"]["Variables"])
        self.assertEqual(result["raw_macros"], payload["payload"]["Macros"])
        self.assertEqual(result["variables"], {})
        self.assertEqual(result["macros"], {})
        self.assertEqual({block["source_path"] for block in result["collection_compatibility_blocks"]}, {
            "Variables[V]", "Macros[M]",
        })
        blocks_by_path = {
            block["source_path"]: block
            for block in result["collection_compatibility_blocks"]
        }
        self.assertEqual(blocks_by_path["Variables[V]"]["raw_value"],
                         payload["payload"]["Variables"]["V"])
        self.assertEqual(blocks_by_path["Macros[M]"]["raw_value"],
                         payload["payload"]["Macros"]["M"])

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

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        self.assertEqual(result["raw_variables"], payload["payload"]["Variables"])
        self.assertEqual(result["raw_macros"], payload["payload"]["Macros"])
        self.assertEqual(result["variables"]["PVAR"]["funct"], "return GSE.V.Other()")
        self.assertEqual(result["variables"]["V_DELTA"]["funct"], "return 2")
        self.assertEqual(result["variables"]["V_DELTA"]["Added"], "kept")
        self.assertNotIn("Drop", result["variables"]["V_DELTA"])
        self.assertEqual(result["macros"]["PMAC"]["macro"], "/cast 77575\n/use 13")
        self.assertEqual(result["macros"]["M_DELTA"]["macro"], "/cast updated")
        self.assertEqual(result["collection_compatibility_blocks"], [])

    def test_import_inspection_reports_unloadable_variable_and_macro_forks_with_category(self) -> None:
        variable = {"GSEDeltaFork": True, "platformId": "variable-id",
                    "contentType": "variable"}
        macro = {"GSEDeltaFork": True, "platformId": "macro-id",
                 "contentType": "macro"}
        payload = {"type": "COLLECTION", "payload": {
            "Variables": {"V_BLOCKED": variable},
            "Macros": {"M_BLOCKED": macro},
        }}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        blocks = {(item["category"], item["name"]): item
                  for item in result["collection_compatibility_blocks"]}
        self.assertEqual(result["raw_variables"]["V_BLOCKED"], variable)
        self.assertEqual(result["raw_macros"]["M_BLOCKED"], macro)
        self.assertEqual(blocks[("Variables", "V_BLOCKED")]["raw_value"], variable)
        self.assertEqual(blocks[("Macros", "M_BLOCKED")]["raw_value"], macro)
        self.assertIn("payload.Variables[V_BLOCKED]", blocks[("Variables", "V_BLOCKED")]["source_path"])
        self.assertIn("payload.Macros[M_BLOCKED]", blocks[("Macros", "M_BLOCKED")]["source_path"])
        self.assertIn("base", blocks[("Variables", "V_BLOCKED")]["reason"])
        self.assertIn("base", blocks[("Macros", "M_BLOCKED")]["reason"])

    def test_import_inspection_accepts_synthetic_empty_array_collection_containers(self) -> None:
        # Synthetic shape matching the real collection's decoded empty Variables/Macros arrays.
        sequence = {"MetaData": {"Name": "SYNTH_ST", "SpecID": 252, "GSEVersion": 3332},
                    "Default": 1, "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 1}]}]}
        second = dict(sequence, MetaData=dict(sequence["MetaData"], Name="SYNTH_AOE"))
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"SYNTH_ST": sequence, "SYNTH_AOE": second},
            "Variables": [], "Macros": [],
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["status"], "decoded")
        self.assertEqual([item["name"] for item in result["sequences"]],
                         ["SYNTH_ST", "SYNTH_AOE"])
        self.assertEqual(result["raw_variables"], [])
        self.assertEqual(result["raw_macros"], [])
        self.assertEqual(result["variables"], {})
        self.assertEqual(result["macros"], {})
        self.assertEqual(result["collection_compatibility_blocks"], [])

    def test_import_inspection_preserves_numeric_collection_member_keys_and_paths(self) -> None:
        variables = [{"name": "V_ARRAY", "funct": "return 4"}]
        macros = {1: {"name": "M_NUMERIC", "macro": "/cast 77575"}}
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {}, "Variables": variables, "Macros": macros,
        }}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        self.assertEqual(result["raw_variables"], variables)
        self.assertEqual(result["raw_macros"], {"1": macros[1]})
        self.assertEqual(result["variables"], {})
        self.assertEqual(result["macros"], {})
        self.assertEqual(result["collection_object_locations"], {"Variables": {}, "Macros": {}})
        self.assertEqual({block["source_path"] for block in result["collection_compatibility_blocks"]}, {
            "Variables[1]", "Macros[1]",
        })

    def test_import_inspection_parses_numeric_version_blocks_without_actions(self) -> None:
        # Synthetic malformed-but-importable shape: GSE retains version-level blocks,
        # while its structure checker reports the missing Actions table.
        sequence = {
            "MetaData": {"Name": "SYNTH_NUMERIC_VERSION", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": {"1": {
                "1": {"Type": "Repeat", "Interval": 2, "spell": 77575},
                "2": {"Type": "Action", "type": "spell", "spell": 77575},
                "3": {"Type": "Pause", "Clicks": 0},
            }},
        }
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"SYNTH_NUMERIC_VERSION": sequence},
            "Variables": [], "Macros": [],
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        member = result["sequences"][0]
        self.assertEqual(member["versions"][0]["raw_version"], sequence["Versions"]["1"])
        self.assertEqual(member["versions"][0]["parsed_version"]["1"]["Type"], "Repeat")
        self.assertEqual(result["syntax_locations"], [
            {"sequence": "SYNTH_NUMERIC_VERSION", "version": 1, "type": "Repeat",
             "path": "Sequences[SYNTH_NUMERIC_VERSION].Versions[1][1]"},
            {"sequence": "SYNTH_NUMERIC_VERSION", "version": 1, "type": "Action",
             "path": "Sequences[SYNTH_NUMERIC_VERSION].Versions[1][2]"},
            {"sequence": "SYNTH_NUMERIC_VERSION", "version": 1, "type": "Pause",
             "path": "Sequences[SYNTH_NUMERIC_VERSION].Versions[1][3]"},
        ])
        self.assertTrue(any("缺少 Actions" in warning for warning in member["parse_warnings"]))
        self.assertFalse(member["version_support"][0]["simulation_preflight_passed"])
        self.assertIn("Versions[1].Actions", member["version_support"][0]["support_reason"])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "SYNTH_NUMERIC_VERSION", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("Versions[1].Actions", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})

    def test_import_inspection_preserves_collection_sequences_with_missing_or_null_metadata(self) -> None:
        sequence = {"Default": 1, "Versions": [{"Actions": [{"Type": "Pause"}]}],
                    "Custom": None}
        null_metadata_sequence = dict(sequence, MetaData=None)
        payload = {"type": "COLLECTION", "payload": {"Sequences": {
            "NO_META": sequence, "NULL_META": null_metadata_sequence,
        }}}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_cbor_text_fixture(payload),
        })

        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(members["NO_META"]["raw_sequence"], sequence)
        self.assertEqual(members["NULL_META"]["raw_sequence"], null_metadata_sequence)
        self.assertNotIn("MetaData", members["NO_META"]["raw_sequence"])
        self.assertIsNone(members["NULL_META"]["raw_sequence"]["MetaData"])
        for member in members.values():
            self.assertEqual(member["versions"][0]["parsed_version"]["Actions"],
                             sequence["Versions"][0]["Actions"])
            self.assertFalse(member["version_support"][0]["simulation_preflight_passed"])
            self.assertIn("元数据版本缺失", member["support_reason"])

    def test_import_inspection_decodes_protected_sequence_string_inside_collection(self) -> None:
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"NESTED_PROTECTED": GSE_PROTECTED_COLLECTION_SEQUENCE_VECTOR},
        }}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        member = result["sequences"][0]
        self.assertEqual(member["name"], "NESTED_PROTECTED")
        self.assertEqual(member["raw_sequence"], GSE_PROTECTED_COLLECTION_SEQUENCE_VECTOR)
        self.assertEqual(member["versions"][0]["parsed_version"]["Actions"][0]["spell"], 77575)
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["NESTED_PROTECTED"],
                         GSE_PROTECTED_COLLECTION_SEQUENCE_VECTOR)

    def test_import_inspection_decodes_unprotected_sequence_string_inside_collection(self) -> None:
        sequence = {
            "MetaData": {"Name": "NESTED_PLAIN", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]}],
        }
        nested_import = gse_fixture(["NESTED_PLAIN", sequence])
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"NESTED_PLAIN": nested_import},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        member = result["sequences"][0]
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["NESTED_PLAIN"],
                         nested_import)
        self.assertEqual(member["name"], "NESTED_PLAIN")
        self.assertEqual(member["raw_sequence"], nested_import)
        self.assertEqual(member["versions"][0]["parsed_version"]["Actions"][0]["spell"], 77575)
        self.assertEqual(member["versions"][0]["source_path"],
                         "Sequences[NESTED_PLAIN].Versions[1]")

    def test_import_inspection_uses_inner_sequence_identity_for_plain_members(self) -> None:
        pair_sequence = {
            "MetaData": {"Name": "INNER_PAIR", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "spell": 101}]}],
        }
        metadata_sequence = {
            "MetaData": {"Name": "INNER_METADATA", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 2}]}],
        }
        encoded_metadata_sequence = {
            "MetaData": {"Name": "INNER_ENCODED_METADATA", "SpecID": 252,
                         "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 3}]}],
        }
        pair_wire = gse_fixture(["INNER_PAIR", pair_sequence])
        encoded_metadata_wire = gse_fixture(encoded_metadata_sequence)
        payload = {"type": "COLLECTION", "payload": {"Sequences": {
            "OUTER_PAIR": pair_wire,
            "OUTER_METADATA": metadata_sequence,
            "OUTER_ENCODED_METADATA": encoded_metadata_wire,
        }}}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(set(members), {
            "INNER_PAIR", "INNER_METADATA", "INNER_ENCODED_METADATA",
        })
        self.assertEqual(members["INNER_PAIR"]["raw_sequence"], pair_wire)
        self.assertEqual(members["INNER_PAIR"]["versions"][0]["source_path"],
                         "Sequences[OUTER_PAIR].Versions[1]")
        self.assertEqual(members["INNER_METADATA"]["raw_sequence"], metadata_sequence)
        self.assertEqual(members["INNER_METADATA"]["versions"][0]["source_path"],
                         "Sequences[OUTER_METADATA].Versions[1]")
        self.assertEqual(members["INNER_ENCODED_METADATA"]["raw_sequence"],
                         encoded_metadata_wire)
        self.assertEqual(members["INNER_ENCODED_METADATA"]["versions"][0]["source_path"],
                         "Sequences[OUTER_ENCODED_METADATA].Versions[1]")

    def test_import_inspection_reports_gse_rejection_of_raw_collection_sequence_pair(self) -> None:
        sequence = {
            "MetaData": {"Name": "INNER_RAW_PAIR", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 1}]}],
        }
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"RAW_PAIR": ["RAW_PAIR", sequence]},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["status"], "decoded")
        self.assertFalse(result["simulation_started"])
        member = result["sequences"][0]
        self.assertEqual(member["name"], "RAW_PAIR")
        self.assertEqual(member["raw_sequence"], ["RAW_PAIR", sequence])
        self.assertEqual(member["versions"][0]["source_path"],
                         "Sequences[RAW_PAIR].Versions[1]")
        self.assertFalse(member["version_support"][0]["simulation_preflight_passed"])
        self.assertEqual(member["version_support"][0]["support_status"], "unsupported")
        self.assertIn("上游会拒绝导入", member["version_support"][0]["support_reason"])
        blockers = result["collection_compatibility_blocks"]
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["source_path"], "Sequences[RAW_PAIR]")
        self.assertIn("GSEVersion", blockers[0]["reason"])
        self.assertEqual(blockers[0]["raw_value"], ["RAW_PAIR", sequence])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "RAW_PAIR", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("上游会拒绝导入", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})

    def test_import_inspection_dispatches_plain_encoded_collection_members_by_object_type(self) -> None:
        variable_from_sequence = {"objectType": "VARIABLE", "name": "INNER_SEQUENCE_VARIABLE",
                                  "funct": "return 11"}
        macro_from_variable = {"objectType": "MACRO", "name": "INNER_VARIABLE_MACRO",
                               "macro": "/cast 101"}
        variable_from_macro = {"objectType": "VARIABLE", "name": "INNER_MACRO_VARIABLE",
                               "funct": "return 12"}
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"OUTER_SEQUENCE_VARIABLE": gse_fixture(variable_from_sequence)},
            "Variables": {"OUTER_VARIABLE_MACRO": gse_fixture(macro_from_variable)},
            "Macros": {"OUTER_MACRO_VARIABLE": gse_fixture(variable_from_macro)},
        }}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        self.assertEqual(result["sequences"], [])
        self.assertEqual(set(result["variables"]), {
            "INNER_SEQUENCE_VARIABLE", "INNER_MACRO_VARIABLE",
        })
        self.assertEqual(set(result["macros"]), {"INNER_VARIABLE_MACRO"})
        self.assertEqual(result["variables"]["INNER_SEQUENCE_VARIABLE"]["funct"], "return 11")
        self.assertEqual(result["macros"]["INNER_VARIABLE_MACRO"]["macro"], "/cast 101")
        self.assertEqual(result["collection_object_locations"], {
            "Variables": {
                "INNER_SEQUENCE_VARIABLE": "payload.Sequences[OUTER_SEQUENCE_VARIABLE]",
                "INNER_MACRO_VARIABLE": "payload.Macros[OUTER_MACRO_VARIABLE]",
            },
            "Macros": {
                "INNER_VARIABLE_MACRO": "payload.Variables[OUTER_VARIABLE_MACRO]",
            },
        })

    def test_import_inspection_blocks_raw_variable_macro_tables_without_upstream_shape(self) -> None:
        sequence = {
            "MetaData": {"Name": "BLOCKED_COLLECTION", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Pause", "Clicks": 1}]}],
        }
        raw_variable = {"funct": "return 7", "CustomField": {"preserved": True}}
        raw_macro = {"macro": "/cast 101", "CustomField": [1, 2]}
        payload = {"type": "COLLECTION", "payload": {
            "Sequences": {"BLOCKED_COLLECTION": sequence},
            "Variables": {"RAW_VARIABLE": raw_variable},
            "Macros": {"RAW_MACRO": raw_macro},
        }}
        imported = gse_fixture(payload)

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["status"], "decoded")
        self.assertFalse(result["simulation_started"])
        self.assertEqual(result["raw_payload"], payload)
        self.assertEqual(result["raw_variables"], payload["payload"]["Variables"])
        self.assertEqual(result["raw_macros"], payload["payload"]["Macros"])
        self.assertNotIn("RAW_VARIABLE", result["variables"])
        self.assertNotIn("RAW_MACRO", result["macros"])
        member = result["sequences"][0]
        self.assertEqual(member["name"], "BLOCKED_COLLECTION")
        self.assertFalse(member["version_support"][0]["simulation_preflight_passed"])
        self.assertEqual(member["version_support"][0]["support_status"], "unsupported")
        self.assertIn("Variables[RAW_VARIABLE]", member["support_reason"])
        self.assertNotIn("Macros[RAW_MACRO]", member["support_reason"])
        blockers = {block["source_path"]: block
                    for block in result["collection_compatibility_blocks"]}
        self.assertEqual(set(blockers), {"Variables[RAW_VARIABLE]", "Macros[RAW_MACRO]"})
        self.assertTrue(all(block["blocks_import"] for block in blockers.values()))
        self.assertEqual(blockers["Variables[RAW_VARIABLE]"]["raw_value"], raw_variable)
        self.assertEqual(blockers["Macros[RAW_MACRO]"]["raw_value"], raw_macro)
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "BLOCKED_COLLECTION", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("Variables[RAW_VARIABLE]", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})

    def test_import_inspection_does_not_let_bad_macro_block_preceding_sequence(self) -> None:
        sequence = {
            "MetaData": {"Name": "INDEPENDENT_SEQUENCE", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]}],
        }
        bad_macro = {"name": "UNSUPPORTED_MACRO", "macro": "/cast unknown"}
        macro_import = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"INDEPENDENT_SEQUENCE": sequence},
            "Macros": {"UNSUPPORTED_MACRO": bad_macro},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": macro_import})

        self.assertEqual(result["status"], "decoded")
        member = result["sequences"][0]
        self.assertTrue(member["version_support"][0]["simulation_preflight_passed"],
                        member["version_support"][0]["support_reason"])
        self.assertNotIn("Macros[UNSUPPORTED_MACRO]", member["version_support"][0]["support_reason"])
        blocker = next(block for block in result["collection_compatibility_blocks"]
                       if block["category"] == "Macros")
        self.assertEqual(blocker["source_path"], "Macros[UNSUPPORTED_MACRO]")
        self.assertEqual(blocker["raw_value"], bad_macro)
        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": macro_import,
            "sequence_name": "INDEPENDENT_SEQUENCE", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        self.assertEqual(created["status"], "starting")

        bad_variable_import = gse_fixture({"type": "COLLECTION", "payload": {
            "Variables": {"UNSUPPORTED_VARIABLE": {"funct": "return true"}},
            "Sequences": {"INDEPENDENT_SEQUENCE": sequence},
        }})
        variable_result = self._json_request("POST", "/api/gse/inspect", {
            "gse": bad_variable_import,
        })
        blocked_member = variable_result["sequences"][0]
        self.assertFalse(blocked_member["version_support"][0]["simulation_preflight_passed"])
        self.assertIn("Variables[UNSUPPORTED_VARIABLE]",
                      blocked_member["version_support"][0]["support_reason"])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": bad_variable_import,
                "sequence_name": "INDEPENDENT_SEQUENCE", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("Variables[UNSUPPORTED_VARIABLE]",
                      json.loads(raised.exception.read())["error"])

    def test_import_inspection_does_not_let_bad_nested_macro_block_preceding_sequence(self) -> None:
        def sequence(name: str) -> dict:
            return {
                "MetaData": {"Name": name, "SpecID": 252, "GSEVersion": 3332},
                "Default": 1,
                "Versions": [{"Actions": [{"Type": "Action", "type": "spell",
                                              "spell": 77575}]}],
            }

        nested_collection = {"type": "COLLECTION", "payload": {
            "Sequences": {"NESTED_SEQUENCE": sequence("NESTED_SEQUENCE")},
            "Macros": {"BAD_NESTED_MACRO": {"macro": "/cast unknown"}},
        }}
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"OUTER_SEQUENCE": sequence("OUTER_SEQUENCE")},
            "Macros": {"OUTER_MACRO": nested_collection},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        members = {member["name"]: member for member in result["sequences"]}
        self.assertTrue(members["OUTER_SEQUENCE"]["version_support"][0]
                        ["simulation_preflight_passed"])
        nested_support = members["NESTED_SEQUENCE"]["version_support"][0]
        self.assertTrue(nested_support["simulation_preflight_passed"],
                        nested_support["support_reason"])
        self.assertNotIn("Macros[OUTER_MACRO].payload.Macros[BAD_NESTED_MACRO]",
                         nested_support["support_reason"])

        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "OUTER_SEQUENCE", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        self.assertEqual(created["status"], "starting")
        nested_created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "NESTED_SEQUENCE", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        self.assertEqual(nested_created["status"], "starting")

    def test_import_inspection_uses_member_keys_not_display_paths_for_order(self) -> None:
        def sequence(name: str) -> dict:
            return {
                "MetaData": {"Name": name, "SpecID": 252, "GSEVersion": 3332},
                "Default": 1,
                "Versions": [{"Actions": [{"Type": "Action", "type": "spell",
                                              "spell": 77575}]}],
            }

        def nested_collection(sequence_name: str, *, bad_variable: bool = False) -> dict:
            body = {"Sequences": {sequence_name: sequence(sequence_name)}}
            if bad_variable:
                body["Variables"] = {"BAD_VARIABLE": {"funct": "return true"}}
            return {"type": "COLLECTION", "payload": body}

        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"OUTER_SEQUENCE": sequence("OUTER_SEQUENCE")},
            "Macros": {
                "OUTER.payload.WRAPPER_A": nested_collection("INNER_A", bad_variable=True),
                "OUTER.payload.WRAPPER_B": nested_collection("INNER_B"),
            },
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        members = {member["name"]: member for member in result["sequences"]}
        self.assertFalse(members["INNER_A"]["version_support"][0]
                         ["simulation_preflight_passed"])
        self.assertIn("Macros[OUTER.payload.WRAPPER_A].payload.Variables[BAD_VARIABLE]",
                      members["INNER_A"]["version_support"][0]["support_reason"])
        self.assertFalse(members["INNER_B"]["version_support"][0]
                         ["simulation_preflight_passed"])
        self.assertIn("pairs 遍历顺序不确定",
                      members["INNER_B"]["version_support"][0]["support_reason"])
        self.assertTrue(members["OUTER_SEQUENCE"]["version_support"][0]
                        ["simulation_preflight_passed"])

        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "OUTER_SEQUENCE", "version": 1,
            "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
        })
        self.assertEqual(created["status"], "starting")
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "INNER_B", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("pairs 遍历顺序不确定", json.loads(raised.exception.read())["error"])

    def test_import_inspection_dispatches_raw_sequence_tables_from_variables_and_macros(self) -> None:
        def sequence(name: str, click: int) -> dict:
            return {
                "MetaData": {"Name": name, "SpecID": 252, "GSEVersion": 3332},
                "Default": 1,
                "Versions": [{"Actions": [{"Type": "Pause", "Clicks": click}]}],
            }

        variable_pair = ["INNER_VARIABLE_PAIR", sequence("INNER_VARIABLE_PAIR", 1)]
        macro_pair = ["INNER_MACRO_PAIR", sequence("INNER_MACRO_PAIR", 2)]
        payload = {"type": "COLLECTION", "payload": {
            "Variables": {
                "OUTER_VARIABLE_SEQUENCE": sequence("INNER_VARIABLE_SEQUENCE", 3),
                "OUTER_VARIABLE_PAIR": variable_pair,
                "OUTER_PROTECTED_VARIABLE": GSE_PROTECTED_VARIABLE_VECTOR,
            },
            "Macros": {
                "OUTER_MACRO_SEQUENCE": sequence("INNER_MACRO_SEQUENCE", 4),
                "OUTER_MACRO_PAIR": macro_pair,
                "OUTER_PROTECTED_MACRO": GSE_PROTECTED_MACRO_VECTOR,
            },
        }}
        imported = gse_fixture(payload)

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(set(members), {
            "INNER_VARIABLE_SEQUENCE", "INNER_VARIABLE_PAIR",
            "INNER_MACRO_SEQUENCE", "INNER_MACRO_PAIR",
        })
        self.assertEqual(members["INNER_VARIABLE_SEQUENCE"]["versions"][0]["source_path"],
                         "Variables[OUTER_VARIABLE_SEQUENCE].Versions[1]")
        self.assertEqual(members["INNER_VARIABLE_PAIR"]["raw_sequence"], variable_pair)
        self.assertEqual(members["INNER_VARIABLE_PAIR"]["versions"][0]["source_path"],
                         "Variables[OUTER_VARIABLE_PAIR].Versions[1]")
        self.assertEqual(members["INNER_MACRO_SEQUENCE"]["versions"][0]["source_path"],
                         "Macros[OUTER_MACRO_SEQUENCE].Versions[1]")
        self.assertEqual(members["INNER_MACRO_PAIR"]["raw_sequence"], macro_pair)
        self.assertEqual(members["INNER_MACRO_PAIR"]["versions"][0]["source_path"],
                         "Macros[OUTER_MACRO_PAIR].Versions[1]")
        self.assertEqual(result["variables"]["OUTER_PROTECTED_VARIABLE"]["funct"],
                         "return GSE.V.Other()")
        self.assertEqual(result["macros"]["OUTER_PROTECTED_MACRO"]["macro"],
                         "/cast 77575\n/use 13")
        self.assertEqual(result["raw_payload"], payload)

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

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

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

    def test_import_inspection_rejects_bad_encoded_member_in_nested_collection_with_path(self) -> None:
        nested_wire = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"BROKEN": "!GSE3!not-base64!"},
        }})
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"WRAPPER": nested_wire},
        }})

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("Sequences[WRAPPER].payload.Sequences[BROKEN]", error)
        self.assertIn("编码无效", error)

    def test_import_inspection_rejects_nested_collection_depth_over_limit(self) -> None:
        nested = {"type": "COLLECTION", "payload": {"Sequences": {
            "LEAF": {"MetaData": {"Name": "LEAF", "SpecID": 252,
                                    "GSEVersion": 3332}, "Default": 1,
                     "Versions": [{"Actions": []}]},
        }}}
        for index in range(40):
            nested = {"type": "COLLECTION", "payload": {
                "Sequences": {f"LEVEL_{index}": gse_fixture(nested)},
            }}
        imported = gse_fixture(nested)

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("递归过深", error)
        self.assertIn("Sequences[LEVEL_", error)

    def test_import_inspection_marks_nested_sequence_name_collision_ambiguous(self) -> None:
        sequence = {"MetaData": {"Name": "DUP", "SpecID": 252, "GSEVersion": 3332},
                    "Default": 1, "Versions": [{"Actions": []}]}
        nested_wire = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"DUP": sequence},
        }})
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": {"DUP": sequence, "WRAPPER": nested_wire},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["sequences"], [])
        collision = next(block for block in result["collection_compatibility_blocks"]
                         if block["category"] == "Sequences" and block["name"] == "DUP")
        self.assertIn("歧义", collision["reason"])
        self.assertIn("pairs", collision["reason"])
        self.assertEqual({collision["source_path"], collision["conflicting_source_path"]}, {
            "Sequences[WRAPPER].payload.Sequences[DUP]", "Sequences[DUP]",
        })
        self.assertIsNotNone(collision["conflicting_raw_value"])
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["DUP"], sequence)
        self.assertEqual(result["raw_payload"]["payload"]["Sequences"]["WRAPPER"], nested_wire)

    def test_import_inspection_enforces_total_decoded_bytes_across_nested_members(self) -> None:
        padding = "x" * 2_200_000
        nested_wires = {}
        for suffix in ("A", "B"):
            nested_wires[f"WRAPPER_{suffix}"] = gse_fixture({"type": "COLLECTION", "payload": {
                "Variables": {f"V_{suffix}": {"name": f"V_{suffix}",
                                               "funct": "return 1", "Padding": padding}},
            }})
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Sequences": nested_wires,
        }})

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("递归解码数据总量", error)
        self.assertIn("Sequences[WRAPPER_", error)

    def test_import_inspection_counts_plain_encoded_object_once_within_total_budget(self) -> None:
        padding = "x" * 2_200_000
        variable_wire = gse_fixture({"objectType": "VARIABLE", "name": "BIG_VARIABLE",
                                     "funct": "return 1", "Padding": padding})
        imported = gse_fixture({"type": "COLLECTION", "payload": {
            "Variables": {"BIG_VARIABLE": variable_wire},
        }})

        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(result["status"], "decoded")
        self.assertEqual(len(result["variables"]["BIG_VARIABLE"]["Padding"]), len(padding))

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
            result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        except HTTPError as error:
            self.fail(error.read().decode("utf-8"))

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

    def test_import_inspection_preserves_delta_forks_that_upstream_cannot_load(self) -> None:
        base = {"MetaData": {"Name": "BASE", "SpecID": 252, "GSEVersion": 3332},
                "Default": 1, "Versions": [{"Actions": []}]}
        no_base = {"GSEDeltaFork": True, "platformId": "missing-base-id"}
        no_platform_id = {"GSEDeltaFork": True, "base": gse_fixture(["NO_PLATFORM", base])}
        payload = {"type": "COLLECTION", "payload": {"Sequences": {
            "NO_BASE": no_base, "NO_PLATFORM": no_platform_id,
        }}}

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        blockers = {item["name"]: item for item in result["collection_compatibility_blocks"]}
        self.assertEqual(result["status"], "decoded")
        self.assertEqual(result["sequences"], [])
        self.assertEqual(blockers["NO_BASE"]["raw_value"], no_base)
        self.assertEqual(blockers["NO_PLATFORM"]["raw_value"], no_platform_id)
        self.assertIn("base", blockers["NO_BASE"]["reason"])
        self.assertIn("platformId", blockers["NO_PLATFORM"]["reason"])
        self.assertIn("NO_BASE", blockers["NO_BASE"]["source_path"])

    def test_import_inspection_keeps_raw_nulls_while_applying_upstream_empty_defaults(self) -> None:
        actions = [
            {"Type": "Repeat", "type": "spell", "spell": 77575,
             "Interval": None, "Repeat": "3"},
            {"Type": "Pause", "Clicks": 2, "MS": ""},
        ]
        payload = ["EMPTY_DEFAULTS", {
            "MetaData": {"Name": "EMPTY_DEFAULTS", "SpecID": 252, "GSEVersion": 3332},
            "Default": 1, "Versions": [{"Actions": actions}],
        }]

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_cbor_text_fixture(payload),
        })

        member = result["sequences"][0]
        self.assertEqual(member["versions"][0]["raw_version"]["Actions"], actions)
        self.assertTrue(member["version_support"][0]["simulation_preflight_passed"],
                        member["version_support"][0]["support_reason"])

    def test_import_inspection_rejects_unknown_block_with_member_version_and_path(self) -> None:
        imported = gse_fixture(["UNKNOWN", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "FutureBlock", "Disabled": True}]}],
        }])

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("FutureBlock", error)
        self.assertIn("UNKNOWN", error)
        self.assertIn("Versions[1].Actions[1]", error)

    def test_import_inspection_rejects_scalar_nested_block_with_exact_path(self) -> None:
        imported = gse_fixture(["BAD_CHILD", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Loop", "Repeat": 1, 1: "not a block"}]}],
        }])

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("BAD_CHILD", error)
        self.assertIn("Versions[1].Actions[1][1]", error)

    def test_import_inspection_parses_known_blocks_with_upstream_optional_fields_missing(self) -> None:
        payload = ["OPTIONAL_FIELDS", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3332}, "Default": 1,
            "Versions": [
                {"Actions": [{"Type": "Pause"}]},
                {"Actions": [{"Type": "If"}]},
                {"Actions": [{"Type": "Embed"}]},
            ],
        }]

        result = self._json_request("POST", "/api/gse/inspect", {
            "gse": gse_fixture(payload),
        })

        self.assertEqual(result["status"], "decoded")
        member = result["sequences"][0]
        self.assertEqual([version["version"] for version in member["versions"]], [1, 2, 3])
        self.assertEqual([row["type"] for row in result["syntax_locations"]], ["Pause", "If", "Embed"])
        supports = {row["version"]: row for row in member["version_support"]}
        self.assertTrue(supports[1]["simulation_preflight_passed"])
        self.assertIn("If", supports[2]["support_reason"])
        self.assertIn("Embed", supports[3]["support_reason"])

    def test_import_inspection_marks_newer_gse_members_as_not_simulatable(self) -> None:
        imported = gse_fixture({"type": "COLLECTION", "payload": {"Sequences": {
            "LOCKED": {"MetaData": {"Name": "LOCKED", "SpecID": 252, "GSEVersion": 3332},
                       "Default": 1, "Versions": [{"Actions": []}]},
            "FUTURE": {"MetaData": {"Name": "FUTURE", "SpecID": 252, "GSEVersion": 3333},
                       "Default": 1, "Versions": [{"Actions": []}]},
        }}})
        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        members = {member["name"]: member for member in result["sequences"]}
        self.assertEqual(result["status"], "decoded")
        self.assertIsNone(members["LOCKED"]["simulation_supported"])
        self.assertTrue(members["LOCKED"]["simulation_preflight_passed"])
        self.assertFalse(members["FUTURE"]["simulation_supported"])
        self.assertFalse(members["FUTURE"]["simulation_preflight_passed"])
        self.assertIn("3333", members["FUTURE"]["support_reason"])
        self.assertIn("3332", members["FUTURE"]["support_reason"])

    def test_import_inspection_reports_known_macro_and_block_rejections_per_version(self) -> None:
        imported = gse_fixture(["PREFLIGHT", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [
                {"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]},
                {"Actions": [{"Type": "Action", "type": "macro",
                               "macro": "/cast [nochanneling] Epidemic"}]},
                {"Actions": [{"Type": "If", "Variable": "=GSE.V.ExternalFlag()",
                               1: [{"Type": "Action", "type": "spell", "spell": 77575}]}]},
                {"Actions": [{"Type": "Action", "type": "macro", "macro": "/petattack [pet]"}]},
                {"Actions": [{"Type": "Action", "type": "macro",
                               "macro": "/petassist [@target,harm,nodead]"}]},
            ],
        }])
        result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        member = result["sequences"][0]
        versions = {item["version"]: item for item in member["version_support"]}

        self.assertTrue(versions[1]["simulation_preflight_passed"])
        self.assertEqual(versions[1]["support_status"], "requires_character_validation")
        self.assertIsNone(versions[1]["simulation_supported"])
        self.assertIn("尚未核对", versions[1]["support_reason"])
        self.assertFalse(versions[2]["simulation_preflight_passed"])
        self.assertFalse(versions[2]["simulation_supported"])
        self.assertIn("nochanneling", versions[2]["support_reason"])
        self.assertIn("Versions[2].Actions[1]", versions[2]["support_reason"])
        self.assertFalse(versions[3]["simulation_preflight_passed"])
        self.assertIn("GSE If 条件需要游戏内变量", versions[3]["support_reason"])
        self.assertFalse(versions[4]["simulation_preflight_passed"])
        self.assertIn("petattack", versions[4]["support_reason"])
        self.assertFalse(versions[5]["simulation_preflight_passed"])
        self.assertIn("petassist", versions[5]["support_reason"])
        self.assertFalse(result["simulation_started"])

    def test_inspection_and_task_share_case_and_stopmacro_reachability(self) -> None:
        imported = gse_fixture(["MACRO_REACHABILITY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "\n".join(("/CAST 77575", "/stopmacro",
                                                                "/not-a-supported-command"))}]}],
        }])
        inspection = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        member = inspection["sequences"][0]
        self.assertTrue(member["simulation_preflight_passed"], member["support_reason"])

        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "MACRO_REACHABILITY", "version": 1,
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
        self.assertGreater(state["dps"], 0)

    def test_repeat_macro_is_rejected_before_task_creation(self) -> None:
        imported = gse_fixture(["REPEAT_PET_COMMAND", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Repeat", "Interval": 2,
                                         "type": "macro", "macro": "/petattack [pet]"}]}],
        }])
        inspection = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        member = inspection["sequences"][0]
        self.assertFalse(member["simulation_preflight_passed"])
        self.assertIn("petattack", member["support_reason"])
        self.assertIn("Versions[1].Actions[1]", member["support_reason"])

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "REPEAT_PET_COMMAND", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("petattack", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})
        self.assertEqual(list(self.server.task_root.iterdir()), [])

    def test_false_conditional_stopmacro_does_not_hide_reachable_lines(self) -> None:
        imported = gse_fixture(["CONDITIONAL_STOPMACRO", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "\n".join(("/stopmacro [mod:shift]",
                                                                "/not-a-supported-command"))}]}],
        }])
        inspection = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        member = inspection["sequences"][0]
        self.assertFalse(member["simulation_preflight_passed"])
        self.assertIn("not-a-supported-command", member["support_reason"])
        self.assertIn("[行 2]", member["support_reason"])

    def test_inspection_rejects_unknown_combat_macro_conditions(self) -> None:
        for condition in ("combat", "nocombat"):
            with self.subTest(condition=condition):
                imported = gse_fixture(["UNKNOWN_COMBAT", {
                    "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
                    "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                                 "macro": f"/cast [{condition}] 77575"}]}],
                }])
                result = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
                member = result["sequences"][0]

                self.assertFalse(member["simulation_preflight_passed"], member)
                self.assertIn("宏条件不能确定", member["support_reason"])
                self.assertIn(f"[{condition}]", member["support_reason"])
                self.assertIn(
                    "Sequences[UNKNOWN_COMBAT].Versions[1].Actions[1].macro[行 1]",
                    member["support_reason"],
                )

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

    def test_known_false_macro_condition_still_skips_its_unreachable_command(self) -> None:
        imported = gse_fixture(["KNOWN_FALSE_CONDITION", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "/cast [combat,nopet] 99999999\n/cast 77575"}]}],
        }])
        inspection = self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        member = inspection["sequences"][0]
        self.assertTrue(member["simulation_preflight_passed"], member["support_reason"])

        created = self._json_request("POST", "/api/tasks", {
            "profile": sample_profile(), "mode": "import", "gse": imported,
            "sequence_name": "KNOWN_FALSE_CONDITION", "version": 1,
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
        self.assertGreater(state["dps"], 0)

    def test_task_api_rejects_known_unsupported_macro_before_creating_task(self) -> None:
        imported = gse_fixture(["KAREN_MPLUS", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3313}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "/cast [nochanneling] Epidemic"}]}],
        }])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "KAREN_MPLUS", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("nochanneling", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})
        self.assertEqual(list(self.server.task_root.iterdir()), [])

    def test_task_api_rejects_active_pet_command_before_creating_task(self) -> None:
        imported = gse_fixture(["PET_COMMAND", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "/petassist [pet]"}]}],
        }])
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/tasks", {
                "profile": sample_profile(), "mode": "import", "gse": imported,
                "sequence_name": "PET_COMMAND", "version": 1,
                "gse_click_ms": 300, "gcd_ms": 1500, "input_interval_ms": 300,
            })
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("petassist", json.loads(raised.exception.read())["error"])
        self.assertEqual(self.server.tasks, {})
        self.assertEqual(list(self.server.task_root.iterdir()), [])

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
                with self.assertRaises(HTTPError) as raised:
                    self._json_request("POST", "/api/gse/inspect", {"gse": "!GSE3!" + encoded})
                self.assertEqual(raised.exception.code, 400)
                self.assertIn(expected_error, json.loads(raised.exception.read())["error"])

    def test_import_inspection_rejects_duplicate_cbor_map_keys_without_silent_loss(self) -> None:
        import cbor2

        duplicate = b"\xa2" + cbor2.dumps("Name") + cbor2.dumps("first") \
            + cbor2.dumps("Name") + cbor2.dumps("second")
        variables = b"\xa1" + cbor2.dumps("V") + duplicate
        collection = b"\xa2" + cbor2.dumps("type") + cbor2.dumps("COLLECTION") \
            + cbor2.dumps("payload") + b"\xa1" + cbor2.dumps("Variables") + variables
        imported = "!GSE3!" + base64.b64encode(zlib.compress(collection, wbits=-15)).decode("ascii")

        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})

        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())["error"]
        self.assertIn("重复字段键", error)
        self.assertIn("Name", error)

    def test_import_inspection_rejects_trailing_cbor_data(self) -> None:
        import cbor2
        from codec import wire_value
        payload = ["THIRD_PARTY", {
            "MetaData": {"SpecID": 252},
            "Versions": [{"Actions": [{"Type": "Action", "type": "spell", "spell": 77575}]}],
        }]
        raw = cbor2.dumps(wire_value(payload)) + b"\x00"
        imported = "!GSE3!" + base64.b64encode(zlib.compress(raw, wbits=-15)).decode("ascii")
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("编码", json.loads(raised.exception.read())["error"])

    def test_import_inspection_rejects_decompression_over_limit(self) -> None:
        from gse_import import MAX_DECODED
        imported = gse_fixture("A" * (MAX_DECODED + 1))
        with self.assertRaises(HTTPError) as raised:
            self._json_request("POST", "/api/gse/inspect", {"gse": imported})
        self.assertEqual(raised.exception.code, 400)
        self.assertIn("过大", json.loads(raised.exception.read())["error"])

    def test_import_inspection_rejects_nested_or_excessive_cbor_nodes(self) -> None:
        deep = None
        for _ in range(40):
            deep = [deep]
        cases = [deep, [0] * 10001]
        for payload in cases:
            with self.subTest(nodes=len(payload) if isinstance(payload, list) else 1):
                with self.assertRaises(HTTPError) as raised:
                    self._json_request("POST", "/api/gse/inspect", {"gse": gse_fixture(payload)})
                self.assertEqual(raised.exception.code, 400)
                self.assertIn("过深或节点过多", json.loads(raised.exception.read())["error"])

    def test_public_service_simulates_selected_import_and_returns_dps(self) -> None:
        imported = gse_fixture(["THIRD_PARTY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{"Type": "Action", "type": "macro",
                                         "macro": "/targetenemy [noharm][dead]\n/cast 77575"}]}],
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
        self.assertEqual(state["status"], "completed", state)
        self.assertEqual(state["selected_sequence"], "THIRD_PARTY")
        self.assertGreater(state["dps"], 0)
        self.assertFalse(state["result_ready"])

    def test_run_task_import_uses_gse_integer_gcd_pause_steps(self) -> None:
        imported = gse_fixture(["GCD_PAUSE", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [
                {"Type": "Pause", "MS": "GCD"},
                {"Type": "Action", "type": "spell", "spell": 77575},
            ]}],
        }])
        source = Path(self.directory.name) / "gcd-pause.simc"
        source.write_text(sample_profile(), encoding="utf-8")

        result = run_task(
            source, Path(self.directory.name) / "gcd-pause-task", mode="import",
            gse_text=imported, sequence_name="GCD_PAUSE", version=1,
            search_config={"input_interval_ms": 400},
            gse_context={"click_ms": 400, "gcd_ms": 1500, "seed": 1},
        )

        self.assertEqual(result["status"], "completed")
        wait, = result["candidate"]["program"]["nodes"][:1]
        self.assertEqual((wait["kind"], wait["clicks"]), ("WaitClicks", 3))
        controlled = result["controlled_simulation"]
        self.assertEqual(controlled["blocks"], [[], [], [], ["outbreak"]])
        self.assertEqual(controlled["native_blocks"], [[], [], [], ["outbreak"]])

    def test_run_task_import_turns_one_gcd_click_into_zero_wait_steps(self) -> None:
        imported = gse_fixture(["GCD_BOUNDARY", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [
                {"Type": "Pause", "MS": "GCD"},
                {"Type": "Action", "type": "spell", "spell": 77575},
            ]}],
        }])
        source = Path(self.directory.name) / "gcd-boundary.simc"
        source.write_text(sample_profile(), encoding="utf-8")

        result = run_task(
            source, Path(self.directory.name) / "gcd-boundary-task", mode="import",
            gse_text=imported, sequence_name="GCD_BOUNDARY", version=1,
            search_config={"input_interval_ms": 1500},
            gse_context={"click_ms": 1500, "gcd_ms": 1500, "seed": 1},
        )

        wait, = result["candidate"]["program"]["nodes"][:1]
        self.assertEqual((wait["kind"], wait["clicks"]), ("WaitClicks", 0))
        self.assertEqual(result["controlled_simulation"]["blocks"], [["outbreak"]])
        self.assertEqual(result["controlled_simulation"]["native_blocks"], [["outbreak"]])

    def test_run_task_import_expands_sequential_loop_and_pause_clicks(self) -> None:
        imported = gse_fixture(["LOOP_PAUSE", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [{
                "Type": "Loop", "Repeat": "2",
                1: {"Type": "Action", "type": "spell", "spell": 77575},
                2: {"Type": "Pause", "Clicks": 1},
                3: {"Type": "Action", "type": "spell", "spell": 49998},
                4: {"Type": "Pause", "Clicks": 2},
            }]}],
        }])
        source = Path(self.directory.name) / "loop-pause.simc"
        source.write_text(sample_profile(), encoding="utf-8")

        result = run_task(
            source, Path(self.directory.name) / "loop-pause-task", mode="import",
            gse_text=imported, sequence_name="LOOP_PAUSE", version=1,
            search_config={"input_interval_ms": 300},
            gse_context={"click_ms": 300, "gcd_ms": 1500, "seed": 1},
        )

        loop, = result["candidate"]["program"]["nodes"]
        self.assertEqual(loop["count"], 2)
        self.assertEqual([(node["kind"], node.get("clicks")) for node in loop["body"]], [
            ("Action", None), ("WaitClicks", 0), ("Action", None), ("WaitClicks", 2),
        ])
        expected_blocks = [["outbreak"], ["death_strike"], [], [],
                           ["outbreak"], ["death_strike"], [], []]
        controlled = result["controlled_simulation"]
        self.assertEqual(controlled["blocks"], expected_blocks)
        self.assertEqual(controlled["native_blocks"], expected_blocks)
        self.assertEqual(
            [click["source"]["path"] for click in result["candidate"]["compiled_program"]["clicks"]],
            ["1.1", "1.3", "1.4", "1.4", "1.1", "1.3", "1.4", "1.4"],
        )

    def test_run_task_import_converts_nonempty_ms_using_gse_fixed_second(self) -> None:
        for interval_ms, duration, empty_clicks in (
            (300, 250, 4), (400, 1200, 3), (1000, 250, 0),
        ):
            with self.subTest(interval_ms=interval_ms, duration=duration):
                imported = gse_fixture(["MS_PAUSE", {
                    "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
                    "Versions": [{"Actions": [
                        {"Type": "Pause", "MS": duration},
                        {"Type": "Action", "type": "spell", "spell": 77575},
                    ]}],
                }])
                source = Path(self.directory.name) / f"ms-pause-{interval_ms}.simc"
                source.write_text(sample_profile(), encoding="utf-8")

                result = run_task(
                    source, Path(self.directory.name) / f"ms-pause-task-{interval_ms}", mode="import",
                    gse_text=imported, sequence_name="MS_PAUSE", version=1,
                    search_config={"input_interval_ms": interval_ms},
                    gse_context={"click_ms": interval_ms, "gcd_ms": 1500, "seed": 1},
                )

                expected_blocks = [[] for _ in range(empty_clicks)] + [["outbreak"]]
                wait, = result["candidate"]["program"]["nodes"][:1]
                self.assertEqual((wait["kind"], wait["clicks"]), ("WaitClicks", empty_clicks))
                controlled = result["controlled_simulation"]
                self.assertEqual(controlled["blocks"], expected_blocks)
                self.assertEqual(controlled["native_blocks"], expected_blocks)

    def test_run_task_import_rejects_plan_over_4096_steps(self) -> None:
        imported = gse_fixture(["TOO_MANY_STEPS", {
            "MetaData": {"SpecID": 252, "GSEVersion": 3331}, "Default": 1,
            "Versions": [{"Actions": [
                {"Type": "Pause", "Clicks": 4096},
                {"Type": "Action", "type": "spell", "spell": 77575},
            ]}],
        }])
        source = Path(self.directory.name) / "too-many-steps.simc"
        source.write_text(sample_profile(), encoding="utf-8")

        with self.assertRaisesRegex(TaskError, "展开.*4096"):
            run_task(
                source, Path(self.directory.name) / "too-many-steps-task", mode="import",
                gse_text=imported, sequence_name="TOO_MANY_STEPS", version=1,
                search_config={"input_interval_ms": 300},
                gse_context={"click_ms": 300, "gcd_ms": 1500, "seed": 1},
            )

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

    def test_real_task_reaches_candidate_through_the_same_public_service(self) -> None:
        self.server.task_options = {
            "search_config": {
                "total_budget_seconds": 20,
                "search_budget_seconds": 8,
                "candidate_limit": 2,
                "round_candidate_limit": 1,
                "batch_targets": (2,),
                "validation_batches": 1,
                "final_batches": 1,
                "iterations": 2,
                "final_iterations": 2,
                "scenarios": ("nominal",),
                "max_processes": 1,
            }
        }
        with _fast_search_boundary():
            created = self._json_request("POST", "/api/tasks", {"profile": sample_profile()})
            self.assertEqual(created["status"], "starting")
            task_id = created["task_id"]
            deadline = time.monotonic() + 30
            state = {}
            while time.monotonic() < deadline:
                state = self._task_state_request(task_id, deadline)
                if state["status"] in {"completed", "validation_incomplete", "failed", "cancelled"}:
                    break
                time.sleep(0.1)
        self.assertEqual(state["status"], "validation_incomplete")
        self.assertTrue(state["result_ready"])
        self.assertEqual(state["evidence_status"], "insufficient_validation")
        self.assertTrue(state["candidate_text"].startswith("!GSE3!"))
        self.assertIn("复测未完成", state["result_note"])
        self.assertIn("锁定候选", state["result_note"])
        self.assertEqual(state["phase"], "done")
        self.assertGreater(state["elapsed_seconds"], 0)

    def test_old_incomplete_result_still_reports_the_seed_it_selected(self) -> None:
        destination = Path(self.directory.name) / "旧任务"
        destination.mkdir()
        (destination / "candidate.txt").write_text("!GSE3!seed", encoding="ascii")
        state = {
            "status": "validation_incomplete",
            "phase": "done",
            "improvement": "not_proven_better",
            "locked_candidate_key": "locked",
            "selected_candidate_key": "seed",
            "candidate": {"text": "!GSE3!seed"},
        }

        self.assertIn("初始序列", _public_state(state, destination)["result_note"])

    def test_browser_computes_copies_and_clears_real_candidate(self, profile_text=None, expected_spec=252, interval_ms=300):
        self.server.task_options = {'search_config': dict(total_budget_seconds=120,
            search_budget_seconds=90,candidate_limit=2,batch_targets=(2,),
            validation_batches=1,final_batches=1,iterations=2,final_iterations=2,
            scenarios=('nominal','jitter','slow','pause','phase') if interval_ms != 300 else ('nominal',),max_processes=1)}
        env=os.environ.copy()
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        script=r'''
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(); let state;
  page.on('response',async response=>{if(response.url().includes('/api/tasks/')&&response.request().method()==='GET')state=await response.json();});
  await page.goto(input.url);
  assert.equal(await page.locator('#interval').inputValue(),'300');
  await page.locator('#interval').fill(String(input.interval_ms));
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.locator('#start').click();
  assert.match(await page.locator('#error').innerText(),/请先粘贴/);
  await page.locator('#profile').fill('mage=test\nlevel=80\nspec=frost');
  await page.locator('#start').click();
  await page.waitForFunction(()=>!document.querySelector('#start').disabled);
  const asyncError=await page.locator('#error').innerText();
  assert.match(asyncError,/请检查角色导出内容/);
  assert.ok(!asyncError.includes('\\'));
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  let dropped=false;
  await page.route('**/api/tasks/*',async route=>{if(!dropped){dropped=true;await route.abort();}else await route.continue();});
  const disconnected=page.waitForEvent('requestfailed');
  await page.locator('#profile').fill(input.profile);await page.locator('#start').click();
  await disconnected;await page.waitForTimeout(700);
  assert.equal(await page.locator('#start').isDisabled(),true,'瞬时断连不能结束后台任务');
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  await page.waitForFunction(()=>!document.querySelector('#start').disabled,{},{timeout:35000});
  assert.equal(await page.locator('#resultSection').isVisible(),true,await page.locator('#error').textContent());
  const text=await page.locator('#result').inputValue();assert.match(text,/^!GSE3!/);
  assert.equal(state.input_interval_ms,input.interval_ms);
  assert.equal(text,state.candidate_text);assert.equal(state.evidence_status,'insufficient_validation');
  assert.match(await page.locator('#resultNote').innerText(),/复测未完成/);
  await page.locator('#copy').click();
  assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),text);
  assert.match(await page.locator('#resultNote').innerText(),/复测未完成/);
  await page.locator('#profile').fill(input.profile+'\n# changed');
  assert.equal(await page.locator('#resultSection').isVisible(),false);
  assert.equal(await page.locator('#result').inputValue(),'');
  console.log(JSON.stringify({candidate:text}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run(['node','-e',script],input=json.dumps(dict(url=self.url,profile=profile_text or sample_profile(),interval_ms=interval_ms)),
            text=True,encoding='utf-8',capture_output=True,env=env,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self._decode_candidate(json.loads(result.stdout)['candidate'], expected_spec)

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

    def _export_candidate(self, profile, expected_spec, *, simulate=False):
        root = Path(self.directory.name) / 'direct'
        source = root / 'input.simc'
        root.mkdir()
        source.write_text(profile, encoding='utf-8')
        from unittest.mock import patch
        boundary = nullcontext() if simulate else patch(
            'sequence.evaluate', return_value={'trace': [], 'model': 'constructed-test-boundary'})
        with boundary:
            result = run_task(source, root / 'task', mode='single')
        self._decode_candidate(result['candidate']['text'], expected_spec)
        self.native_report = json.loads((root / 'task/reference/native.json').read_text(encoding='utf-8'))
        self.native_reference = result['native_reference']
        self.controlled = result['controlled_simulation']

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

    def test_browser_uses_adjustable_input_interval(self):
        with _fast_search_boundary():
            self.test_browser_computes_copies_and_clears_real_candidate(interval_ms=180)
        from task import read_task
        destination, _ = next(iter(self.server.tasks.values()))
        result = read_task(destination)
        for row in result['final']['scenarios']['nominal']['candidate']:
            self.assertEqual(row['request']['times'], list(range(0, 180000, 180)))
        scenarios = result['final']['scenarios']
        self.assertEqual(set(scenarios), {'nominal','jitter','slow','pause','phase'})
        for name in ('slow','phase','pause','jitter'):
            times = scenarios[name]['candidate'][0]['request']['times']
            if name == 'slow': self.assertEqual(times, list(range(0,180000,240)))
            elif name == 'phase': self.assertEqual(times, list(range(90,180000,180)))
            elif name == 'pause':
                self.assertTrue(all(t % 180 == 0 for t in times))
                self.assertFalse(any(60000 <= t < 62000 or 120000 <= t < 122000 for t in times))
            else: self.assertTrue(all(162 <= b-a <= 198 for a,b in zip(times,times[1:])))

    def test_game_export_with_death_pact_and_asphyxiate_reaches_result(self):
        import re
        talents='CwPAkXBWxkyfx9CbGaHonEAhLBYmhZMjBzyMzMTjZmxMzYAAAAAAAAYmxwAglZMzsZmxMzA2MbGGyAzGDNWwAmBgxMzYGgZmxMG'
        profile=re.sub(r'^talents=.*$', 'talents='+talents,sample_profile(),flags=re.MULTILINE)
        self._export_candidate(profile, 252)

    def test_baseline_unused_racial_does_not_block_browser_result(self):
        self._export_candidate(sample_profile().replace('highmountain_tauren', 'undead'), 252)

    def test_tank_profile_reaches_damage_candidate(self):
        import re
        profile = sample_profile().replace('role=attack', 'role=tank').replace('spec=unholy', 'spec=blood')
        profile = re.sub(r'^talents=.*$', 'talents=CoPAkXBWxkyfx9CbGaHonEAhLxMz2MzwMmZmhZbmZmmZxMjZmxAAAAAmhZmZmZMzYAAzMzMzAAAYgBmxiGLbgsNgNAzYAAAmZAMA', profile, flags=re.MULTILINE)
        self._export_candidate(profile, 250)
        actions = self.candidate_payload[1]['Versions'][0]['Actions']
        self.assertTrue(any(a.get('macro') == '/cast [@player] 43265' for a in actions), '地面技能必须直接在脚下释放')

    def test_caster_profile_reaches_damage_candidate(self):
        # 固定上游 MID2_Mage_Frost 的角色字段；默认动作由引擎生成。
        self._export_candidate('''mage="Frost caster"
level=90
race=tauren
role=spell
spec=frost
talents=CAEAAAAAAAAAAAAAAAAAAAAAAYGGLzMzsMmZmYmZGjZMziZmZmZMDEAAYmZmllZm2AAAAAAgNA2WGzMzAbzYmZYBAAgZ2AmBGwADD
main_hand=,id=271092,bonus_id=13662/13848,enchant_id=8689
''', 64)

    def test_native_item_group_reaches_damage_candidate(self):
        self._export_candidate('''mage="Arcane items"
level=90
race=tauren
role=spell
spec=arcane
talents=C4DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMDamZGAAAGAAEwMzMLLzMxCAAwMzMjNLzMzsMjxYmZwCzYmZGAgBAAYmZBAMDAGmZG
main_hand=,id=271092,bonus_id=13335/13848,ilevel=344,enchant_id=8689
trinket1=,id=250215,ilevel=344
''', 62)

    def test_native_empower_and_race_alias_reach_candidate(self):
        self._export_candidate('''evoker="Empower caster"
level=90
race=dracthyr
role=spell
spec=devastation
talents=CsbBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzMDMDzgBmZGjZaYmpZMWmxMzMz8AzMzAmxMGzMLzMDMwYwCsMGN2GQmBBbYGMzghB
main_hand=,id=249283,ilevel=289,enchant_id=8039
''', 1467)

    def test_healer_profile_reaches_damage_candidate(self):
        self._export_candidate('''druid="Restoration healer"
level=90
race=night_elf
role=heal
spec=restoration
talents=CkGAAAAAAAAAAAAAAAAAAAAAAMjxMbzMjZmxsNMGzwYjZAAAAAAAAAAwygmNzYamxwYWmZmZGGmBAAAAAAAAAQAAAz2MLNbzsZjxMDmZAaGAgZGAGA
main_hand=,id=271092,ilevel=311
''', 105)
        player = self.native_report['sim']['players'][0]
        self.assertEqual(player['role'], 'heal')
        self.assertGreater(player['collected_data']['dps']['mean'], 0)

    def test_explicit_native_experimental_option_reaches_candidate(self):
        self._export_candidate(
            'allow_experimental_specializations=1\n'+(REPOSITORY/'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8'), 256)

    def test_native_restoration_shaman_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/restoration-shaman.simc').read_text(encoding='utf-8'), 264)

    def test_native_augmented_party_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/augmentation.simc').read_text(encoding='utf-8'), 1473)
        self.assertGreater(len(self.native_report['sim']['players']), 1)
        self.assertEqual(self.native_reference['dps'], self.native_report['sim']['statistics']['raid_dps']['mean'])

    def test_native_cast_reaches_candidate(self):
        self._export_candidate(
            (REPOSITORY/'tests/sim2gse/fixtures/devourer.simc').read_text(encoding='utf-8'), 1480, simulate=True)
        self.assertTrue(any(row['event'] == 'native_execute' and row.get('cast_ms', 0) > 0
                            for row in self.controlled['trace']))

    def test_replacement_forms_remain_one_button(self):
        self._export_candidate('''warrior="Fury buttons"
level=90
race=dwarf
role=attack
spec=fury
talents=CgEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgGDzMmZ2MzMzMDjZmZGzMzsMzMmZmZzYmBAAixy2ALgJYGmAzwGwMDjNAAYmhxYYMYM
main_hand=,id=268213,bonus_id=13335/13848,ilevel=344,enchant_id=8689
off_hand=,id=237847,bonus_id=8793/8960/13751/13771/13836/12497,enchant_id=8689
''', 72)
        actions = self.candidate_payload[1]['Versions'][0]['Actions']
        self.assertTrue(any('/cast 335097' in a.get('macro','') and '/cast 85288' in a.get('macro','') for a in actions))
        self.assertFalse(any(a.get('spell') in (335097,85288) for a in actions))

    def test_interface_reports_native_and_export_failures_without_internal_paths(self):
        from task import TaskError
        native_cases = [
            ('native_default', (REPOSITORY / 'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8')),
            ('native_disabled', 'allow_experimental_specializations=0\n' +
             (REPOSITORY / 'tests/sim2gse/fixtures/discipline.simc').read_text(encoding='utf-8')),
            ('native_unsupported', (REPOSITORY / 'tests/sim2gse/fixtures/holy-paladin.simc').read_text(encoding='utf-8')),
        ]
        for failure, profile in native_cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'input.simc'
                source.write_text(profile, encoding='utf-8')
                with self.assertRaisesRegex(TaskError, '原生未提供'):
                    run_task(source, Path(directory) / 'task', mode='single')
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

    def test_manual_browser_cancellation_cleans_process_tree(self):
        from unittest.mock import patch
        import ctypes
        from ctypes import wintypes
        import manual_interface
        import runtime
        from runtime import TaskCancelled, TaskRuntime
        original_read=Path.read_text
        original_create=runtime._kernel32.CreateProcessW
        held=[];node_ids=[];watch_errors=[]
        created=threading.Event();task_runtime=TaskRuntime(30)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        class Entry(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                      ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                      ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
                      ('exe',wintypes.WCHAR*260)]
        kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        def edge_ids(parent_id):
            snapshot=kernel.CreateToolhelp32Snapshot(2,0)
            row=Entry();row.size=ctypes.sizeof(row)
            found=set()
            try:
                more=kernel.Process32FirstW(snapshot,ctypes.byref(row))
                while more:
                    if row.parent==parent_id and row.exe.lower()=='msedge.exe':found.add(row.pid)
                    more=kernel.Process32NextW(snapshot,ctypes.byref(row))
                return found
            finally:kernel.CloseHandle(snapshot)
        def create_process(*args):
            result=original_create(*args)
            if result:
                info=ctypes.cast(args[9],ctypes.POINTER(runtime._PROCESS_INFORMATION)).contents
                node_ids.append(info.dwProcessId)
                held.append(kernel.OpenProcess(0x100000,False,info.dwProcessId))
                created.set()
            return result
        def cancel_after_edge():
            try:
                if not created.wait(10):raise AssertionError('Node 进程未启动')
                child_ids=[]
                until=time.monotonic()+10
                while time.monotonic()<until and not child_ids:
                    child_ids=edge_ids(node_ids[0])
                    if not child_ids:time.sleep(0.05)
                if not child_ids:raise AssertionError('Edge 浏览器进程未启动')
                for pid in child_ids:
                    handle=kernel.OpenProcess(0x100000,False,int(pid))
                    if not handle or kernel.WaitForSingleObject(handle,0)!=258:
                        raise AssertionError('无法捕获仍在运行的 Edge 浏览器进程')
                    held.append(handle)
            except BaseException as error:
                watch_errors.append(error)
            finally:task_runtime.cancel()
        def profile_input(path,*args,**kwargs):
            if path.name=='unholy-20260912-0240.simc':return sample_profile()
            return original_read(path,*args,**kwargs)
        destination=Path(self.directory.name)/'取消 界面'
        watcher=threading.Thread(target=cancel_after_edge,daemon=True)
        try:
            watcher.start()
            with patch.object(sys,'argv',['manual_interface.py','--output',str(destination)]), \
                 patch.object(Path,'read_text',profile_input), \
                 patch.object(manual_interface,'TaskRuntime',return_value=task_runtime), \
                 patch.object(runtime._kernel32,'CreateProcessW',side_effect=create_process):
                with self.assertRaises(TaskCancelled):manual_interface.main()
            watcher.join(20)
            self.assertFalse(watcher.is_alive(),'浏览器启动观察线程未结束')
            if watch_errors:raise watch_errors[0]
            self.assertGreaterEqual(sum(bool(handle) for handle in held),2,'必须观察到 Node 及浏览器子进程')
            for handle in held:
                if handle:self.assertEqual(kernel.WaitForSingleObject(handle,5000),0,'浏览器进程未被清理')
        finally:
            task_runtime.cancel();watcher.join(1)
            for handle in held:
                if handle:kernel.CloseHandle(handle)

    def test_browser_waits_for_result_publication_before_finishing(self):
        from unittest.mock import patch
        original = os.replace
        def delayed_result(source, destination):
            if Path(destination).name == 'result.json':
                time.sleep(1.5)  # 模拟真实报告落盘期间的多个进度轮询。
            return original(source, destination)
        with _fast_search_boundary(), patch.object(os, 'replace', side_effect=delayed_result):
            self.test_browser_computes_copies_and_clears_real_candidate()

    def test_browser_survives_transient_windows_report_sharing_conflicts(self):
        from unittest.mock import patch
        original=os.replace
        failures=set()
        conflicts=[]
        readers=[]
        def sharing_conflict(source,destination):
            name=Path(destination).name
            if name in ('progress.json','result.json') and name not in failures:
                failures.add(name)
                if not Path(destination).exists():Path(destination).write_text('{"status":"starting"}',encoding='utf-8')
                reader=open(destination,'rb')
                release=threading.Timer(0.08,reader.close);release.start();readers.append(release)
            try:return original(source,destination)
            except PermissionError as error:
                conflicts.append(error.winerror)
                raise
        with _fast_search_boundary(), patch.object(os,'replace',side_effect=sharing_conflict):
            self.test_browser_computes_copies_and_clears_real_candidate()
        self.assertEqual(failures,{'progress.json','result.json'})
        for reader in readers:reader.join()
        self.assertTrue(set(conflicts)&{5,32},'必须触发真实 Windows 文件占用冲突')


if __name__ == "__main__":
    unittest.main()
