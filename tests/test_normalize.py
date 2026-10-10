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


if __name__ == "__main__":
    unittest.main()
