"""SimC（模拟器）导入动作查询配置测试。"""

from pathlib import Path
import sys
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "projects" / "sim2gse"))

from engine import _profile_with_import_queries, inspect, reference  # noqa: E402


class ImportQueryProfileTests(unittest.TestCase):
    def test_queries_are_appended_to_a_copy_not_the_original_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "input.simc"
            original.write_text("deathknight=Probe\nspec=unholy\n", encoding="utf-8")

            result = _profile_with_import_queries(original, folder / "reference", [1247378, 316239])

            self.assertEqual(result.read_text(encoding="utf-8"),
                             "deathknight=Probe\nspec=unholy\n"
                             "sim2gse_action_ids=316239,1247378\n")
            self.assertEqual(original.read_text(encoding="utf-8"),
                             "deathknight=Probe\nspec=unholy\n")

    def test_queries_reject_invalid_ids_and_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "input.simc"
            original.write_text("deathknight=Probe\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "法术编号无效"):
                _profile_with_import_queries(original, folder / "reference", [True])
            with self.assertRaisesRegex(ValueError, "法术编号无效"):
                _profile_with_import_queries(original, folder / "reference", list(range(1, 258)))

    def test_name_queries_are_hex_encoded_without_changing_spell_names(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "input.simc"
            original.write_text("deathknight=Probe\n", encoding="utf-8")
            result = _profile_with_import_queries(original, folder / "reference", [], ["Epidemic", "Mind Freeze"])
            self.assertEqual(result.read_text(encoding="utf-8"),
                             "deathknight=Probe\nsim2gse_action_names_hex=45706964656d6963,4d696e6420467265657a65\n")

    def test_import_inventory_adds_native_query_and_real_items_without_widening_search(self):
        native = dict(
            actions_protocol=1,
            active_items=[dict(slot='trinket1', id=250245, driver_spell_id=43265, name='active trinket')],
            executed_actions=[dict(name='outbreak', signature='outbreak', player_owned=True,
                                   background=False, quiet=False, passive=False, type='spell',
                                   precombat=False, data_id=77575, data_valid=True,
                                   base_spell_id=77575, gcd_ms=1500)],
            import_action_candidates=[dict(kind='spell', spell_id=316239, native_spell_id=1247378,
                                           name='festering_strike', simc_action='festering_strike',
                                           data_valid=True, action_initialized=True, available=True, background=False,
                                           passive=False, quiet=False, gcd_ms=1500),
                                      dict(kind='spell', spell_id=999001, native_spell_id=999001,
                                           name='not_available', simc_action='not_available',
                                           data_valid=True, available=False, background=False,
                                           passive=False, quiet=False),
                                      dict(kind='spell', spell_id=999002, native_spell_id=999002,
                                           name='background', simc_action='background',
                                           data_valid=True, available=True, background=True,
                                           passive=False, quiet=False)],
        )
        with tempfile.TemporaryDirectory() as directory:
            capabilities = inspect(native, Path(directory) / 'capabilities')

        self.assertEqual([action['simc_action'] for action in capabilities['actions']], ['outbreak'])
        self.assertIn(('spell', 316239, 'festering_strike'),
                      {(action['kind'], action.get('spell_id'), action['simc_action'])
                       for action in capabilities['import_actions']})
        self.assertEqual({action['spell_id'] for action in capabilities['import_actions']
                          if action['kind'] == 'spell'}, {77575, 316239})
        self.assertIn(('item', 250245, 'use_item,slot=trinket1'),
                      {(action['kind'], action.get('item_id'), action['simc_action'])
                       for action in capabilities['import_actions']})

    def test_reference_runs_action_query_separately_from_dps_profile(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import json

        calls = []
        character = SimpleNamespace(name="Probe", class_name="death_knight")
        query_candidates = [dict(spell_id=316239, simc_action="festering_strike", action_initialized=True)]

        def fake_run(profile, folder, mode="baseline", options=(), **kwargs):
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=True)
            calls.append(dict(profile=Path(profile), folder=folder, options=list(options)))
            is_probe = folder.name == "import_action_probe"
            player = dict(name="Probe", sim2gse_class="death_knight",
                          collected_data={"dps": {"mean": 1 if is_probe else 42}},
                          sim2gse_import_actions=(query_candidates if is_probe else
                              [dict(spell_id=999999, simc_action="must_not_leak_from_dps")] ))
            report_path = folder / ("native.json" if is_probe else "native.pending.json")
            report_path.write_text(json.dumps({"sim": {"players": [player]}}), encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.simc"
            source.write_text("deathknight=Probe\nspec=unholy\n", encoding="utf-8")
            with patch("engine.run", side_effect=fake_run), \
                    patch("engine.check_report", return_value={"dps": 42, "samples": 7}):
                result = reference(source, Path(directory) / "reference", character, iterations=8,
                                  import_spell_ids=[316239], import_spell_names=["Epidemic"])
            query_text = calls[1]["profile"].read_text(encoding="utf-8")

        self.assertEqual(result["dps"], 42)
        self.assertEqual(result["import_action_candidates"], query_candidates)
        self.assertEqual(calls[0]["profile"], source)
        self.assertEqual(calls[0]["folder"], Path(directory) / "reference")
        self.assertEqual(calls[1]["profile"], Path(directory) / "reference" / "import-action-query.simc")
        self.assertEqual(calls[1]["folder"], Path(directory) / "reference" / "import_action_probe")
        self.assertIn("sim2gse_action_ids=316239", query_text)
        self.assertIn("sim2gse_action_names_hex=45706964656d6963", query_text)
        self.assertIn("iterations=1", calls[1]["options"])
        self.assertIn("max_time=1", calls[1]["options"])

    def test_import_probe_action_is_initialized_for_mage_pet_setup(self):
        import json
        from engine import run

        profile = """mage=Sim2GSE_Mage_Pet_Probe
spec=frost
level=90
race=tauren
role=spell
talents=CAEAAAAAAAAAAAAAAAAAAAAAAYGGLzMzsMmZmYmZGjZMziZmZmZMDEAAYmZmllZm2AAAAAAgNA2WGzMzAbzYmZYBAAgZ2AmBGwADD
omnium_talents=136822:1/136816:1/136817:1/136815:1/136814:1
use_item_verification=0
report_details=0
"""
        with tempfile.TemporaryDirectory(prefix="sim2gse-mage-pet-query-", dir=REPOSITORY) as directory:
            root = Path(directory)
            source = root / "mage.simc"
            source.write_text(profile, encoding="utf-8")
            query = _profile_with_import_queries(source, root / "query", [55342])
            run(query, root / "result", options=["iterations=1", "max_time=1", "json2=native.json"])
            report = json.loads((root / "result" / "native.json").read_text(encoding="utf-8"))

        candidates = report["sim"]["players"][0]["sim2gse_import_actions"]
        mirror_image = next(candidate for candidate in candidates if candidate["spell_id"] == 55342)
        self.assertTrue(mirror_image["selected_talent"])
        self.assertTrue(mirror_image["action_initialized"])
        self.assertGreater(mirror_image["owner_pet_count"], 0)

    def test_import_probe_resolves_name_form_action_outside_executed_subset(self):
        import json
        from engine import run
        from test_character_export import sample_profile

        with tempfile.TemporaryDirectory(prefix="sim2gse-name-action-query-", dir=REPOSITORY) as directory:
            root = Path(directory)
            source = root / "dk.simc"
            source.write_text(sample_profile(), encoding="utf-8")
            query = _profile_with_import_queries(source, root / "query", [], ["Epidemic"])
            run(query, root / "result", options=["iterations=1", "max_time=1", "json2=native.json"])
            report = json.loads((root / "result" / "native.json").read_text(encoding="utf-8"))

        player = report["sim"]["players"][0]
        epidemic = next(candidate for candidate in player["sim2gse_import_actions"]
                         if candidate["simc_action"] == "epidemic")
        self.assertTrue(epidemic["available"])
        self.assertTrue(epidemic["action_initialized"])
        self.assertNotIn("epidemic", {row["signature"] for row in player["sim2gse_actions"]})


if __name__ == "__main__":
    unittest.main()
