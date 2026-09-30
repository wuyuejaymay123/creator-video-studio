"""Portable behavior checks for the plan exporter. Python stdlib only."""
import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("studio_plan", PACKAGE / "scripts" / "plan.py")
plan_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_module)


def fixture(name="workflow"):
    return json.loads((PACKAGE / "examples" / (name + ".plan.json")).read_text(encoding="utf-8-sig"))


class PlanTests(unittest.TestCase):
    def test_both_versions_export_exact_narration_and_rows(self):
        for name in ("weekly-report", "workflow"):
            with self.subTest(name=name):
                plan = fixture(name)
                self.assertEqual(plan_module.validate(plan), [])
                speech, shoot = plan_module.render(plan)
                self.assertEqual(speech.split("\n\n", 1)[1].strip(),
                                 "\n\n".join(s["speech"] for s in plan["segments"]))
                rows = [line for line in shoot.splitlines() if re.match(r"^\| \d+ \|", line)]
                spoken_rows = [row for row in rows if "| 露脸 |" in row or "| 仅声音 |" in row]
                self.assertEqual([row.split("|")[2].strip() for row in spoken_rows],
                                 [s["speech"] for s in plan["segments"]])

    def test_semantic_plan_and_capture_fallback_reach_output(self):
        plan = fixture()
        _, shoot = plan_module.render(plan)
        for segment in plan["segments"]:
            if segment["visibility"] == "voice" and segment["visual"]["relation"] != "hold":
                for field in ("before", "change", "after", "cue", "hold"):
                    self.assertIn(segment["visual"][field], shoot)
        for transition in plan["transitions"]:
            for field in ("reason", "outgoing", "incoming", "audio", "fallback"):
                self.assertIn(transition[field], shoot)

    def test_user_output_has_plain_labels_and_hides_generation_details(self):
        _, shoot = plan_module.render(fixture())
        visible = shoot.split("<details>", 1)[0]
        self.assertIn("你怎么说、怎么做", visible)
        self.assertIn("前一段怎么拍或准备", visible)
        self.assertIn("如果接不上", visible)
        self.assertNotRegex(visible, r"\b(s\d{2}|t\d{2}|graphic_handoff|occlusion|contrast|planned|hybrid)\b")
        self.assertIn("<summary>给 Codex 的制图说明（拍摄时不用看）</summary>", shoot)

    def test_missing_asset_rejected(self):
        plan = fixture()
        plan["assets"] = []
        self.assertTrue(any("missing asset" in e for e in plan_module.validate(plan)))

    def test_required_speech_and_visibility(self):
        for field, value in (("speech", ""), ("visibility", "face+voice")):
            with self.subTest(field=field):
                plan = fixture()
                plan["segments"][0][field] = value
                self.assertTrue(any("." + field in e for e in plan_module.validate(plan)))

    def test_visual_plan_needs_trigger_and_reading_window(self):
        for field in ("cue", "hold"):
            plan = fixture()
            del plan["segments"][1]["visual"][field]
            self.assertTrue(any("visual." + field in e for e in plan_module.validate(plan)))

    def test_adjacent_forward_transition_required(self):
        for start, end in (("s03", "s05"), ("s04", "s03"), ("s03", "s03")):
            plan = fixture()
            plan["transitions"][0].update({"from": start, "to": end})
            self.assertTrue(any("adjacent forward" in e for e in plan_module.validate(plan)))

    def test_missing_transition_target_rejected(self):
        plan = fixture()
        plan["transitions"][0]["to"] = "unknown"
        self.assertTrue(any("missing segment" in e for e in plan_module.validate(plan)))

    def test_transition_needs_both_ends_audio_and_fallback(self):
        for field in ("outgoing", "incoming", "audio", "fallback"):
            plan = fixture()
            del plan["transitions"][0][field]
            self.assertTrue(any("." + field in e for e in plan_module.validate(plan)))

    def test_ready_status_needs_actual_inspection_record(self):
        plan = fixture()
        plan["transitions"][0]["status"] = "ready"
        self.assertTrue(any("checked_media" in e for e in plan_module.validate(plan)))
        plan["transitions"][0]["checked_media"] = "TEST RECORD ONLY: A.mp4 00:03, B.png; not actual production evidence"
        self.assertEqual(plan_module.validate(plan), [])

    def test_one_execution_card_per_boundary(self):
        plan = fixture()
        extra = copy.deepcopy(plan["transitions"][0])
        extra["id"] = "another"
        plan["transitions"].append(extra)
        self.assertTrue(any("duplicates a boundary" in e for e in plan_module.validate(plan)))

    def test_duplicate_identifiers(self):
        for collection in ("segments", "assets", "transitions"):
            plan = fixture()
            plan[collection][1]["id"] = plan[collection][0]["id"]
            self.assertTrue(any("Duplicate" in e for e in plan_module.validate(plan)))

    def test_animation_requires_trigger(self):
        plan = fixture()
        del plan["assets"][0]["motion"]["cue"]
        self.assertTrue(any("motion.cue" in e for e in plan_module.validate(plan)))

    def test_promise_and_takeaway_reference_real_rows(self):
        plan = fixture()
        plan["promises"][0]["payoff"] = ["unknown"]
        plan["takeaway"]["segment"] = "unknown"
        errors = plan_module.validate(plan)
        self.assertTrue(any("payoff references missing" in e for e in errors))
        self.assertTrue(any("takeaway.segment" in e for e in errors))

    def test_payoff_cannot_precede_setup(self):
        plan = fixture()
        plan["promises"][0].update({"setup": "s08", "payoff": ["s01"]})
        self.assertTrue(any("before setup" in e for e in plan_module.validate(plan)))

    def test_table_escaping_does_not_alter_narration(self):
        plan = fixture()
        special = "A | B\n下一句 <示意>"
        plan["segments"][0]["speech"] = special
        speech, shoot = plan_module.render(plan)
        self.assertIn(special, speech)
        self.assertIn("A &#124; B<br>下一句 &lt;示意&gt;", shoot)

    def test_malformed_values_report_errors(self):
        for path, value in (("transitions", [{}]), ("segments", [None]), ("assets", [False]),
                            ("brief", "bad"), ("schema_version", True)):
            plan = fixture()
            plan[path] = value
            self.assertTrue(plan_module.validate(plan))
        plan = fixture()
        plan["segments"][0]["visual"]["relation"] = []
        plan["transitions"][0]["from"] = {}
        self.assertTrue(plan_module.validate(plan))

    def test_v2_can_choose_no_special_transitions(self):
        plan = fixture()
        plan["transitions"] = []
        self.assertEqual(plan_module.validate(plan), [])
        del plan["transitions"]
        self.assertTrue(any("transitions must" in e for e in plan_module.validate(plan)))

    def test_cli_writes_two_files_and_protects_existing_work(self):
        with tempfile.TemporaryDirectory(prefix="studio-test-") as temporary:
            output = Path(temporary) / "output"
            command = [sys.executable, "-X", "utf8", str(PACKAGE / "scripts" / "plan.py"),
                       str(PACKAGE / "examples" / "workflow.plan.json"), "--out", str(output)]
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(sorted(p.name for p in output.iterdir()), ["口播稿.md", "拍摄与后期.md"])
            (output / "拍摄与后期.md").unlink()
            narration = output / "口播稿.md"
            narration.write_text("user changes", encoding="utf-8")
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 1)
            self.assertEqual(narration.read_text(encoding="utf-8"), "user changes")
            self.assertFalse((output / "拍摄与后期.md").exists())

    def test_internal_links_resolve(self):
        for doc in PACKAGE.rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8-sig")):
                if "://" not in link and not link.startswith("#"):
                    self.assertTrue((doc.parent / link.split("#")[0]).is_file(), str(doc) + ": " + link)


if __name__ == "__main__":
    unittest.main(verbosity=2)
