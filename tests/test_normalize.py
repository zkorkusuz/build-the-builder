"""Policy validation and model-answer parsing, with no model call. Run: .venv/bin/python -m unittest tests.test_normalize"""
import json, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import llm, normalize

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "policy-a.json").read_text())


class Problems(unittest.TestCase):
    def test_fixture_is_complete(self):
        self.assertEqual(normalize.problems(json.loads(json.dumps(FIXTURE))), [])

    def test_missing_outcome_and_band_integers(self):
        p = json.loads(json.dumps(FIXTURE))
        del p["outcomes"]["deceased"]
        p["bands"][0]["attempts"] = "one"
        out = normalize.problems(p)
        self.assertTrue(any("deceased" in x for x in out) and any("attempts" in x for x in out))

    def test_string_numbers_and_booleans_are_coerced(self):
        p = json.loads(json.dumps(FIXTURE))
        p["bands"][0]["deadline_business_days"] = "12"
        p["multi_product"]["enabled"] = "true"
        self.assertEqual(normalize.problems(p), [])
        self.assertEqual(p["bands"][0]["deadline_business_days"], 12)
        self.assertIs(p["multi_product"]["enabled"], True)

    def test_schema_has_every_situation(self):
        schema = json.loads(normalize.SCHEMA.replace("<integer>", "0").replace("<true when customers can have several late products>", "false"))
        self.assertEqual(sorted(schema["outcomes"]), sorted(normalize.SITUATIONS))

    def test_prompt_contains_whole_brief(self):
        text = "rule 1\nrule 2\n" * 50
        self.assertIn(text, normalize.prompt([("b.md", text)], "{}"))


class ParseJson(unittest.TestCase):
    def test_fenced(self):
        self.assertEqual(llm.parse_json("x ```json\n{\"a\": 1}\n``` y"), {"a": 1})

    def test_bare(self):
        self.assertEqual(llm.parse_json("here: {\"a\": {\"b\": [1]}} done"), {"a": {"b": [1]}})


class Incomplete(unittest.TestCase):
    """A policy that is still incomplete after the repair is used, not thrown away: the bare template would score nothing."""

    def test_fraction_floor_needs_no_floor_field(self):
        p = json.loads(json.dumps(FIXTURE))
        p["floor_field"], p["floor_fraction"] = {}, 0.5
        self.assertEqual(normalize.problems(p), [])
        p["floor_fraction"] = ""
        self.assertIn("missing floor_field (or floor_fraction)", normalize.problems(p))

    def test_still_incomplete_after_repair_is_kept(self):
        p = json.loads(json.dumps(FIXTURE)); del p["outcomes"]["deceased"]
        answers, lines = iter(["```json\n" + json.dumps(p) + "\n```"] * 2), []
        policy = normalize.normalize([("b.md", "brief")], "{}", None, lines.append, lambda prompt, wd, tr, purpose: next(answers), llm.parse_json)
        self.assertEqual(policy["bands"], p["bands"])
        self.assertTrue(any(l.startswith("normalize: repairing") for l in lines) and any("still incomplete" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
