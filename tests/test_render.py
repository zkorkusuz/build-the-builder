"""Render the Brief A fixture policy and check the workflow locally. Run: .venv/bin/python -m unittest tests.test_render"""
import json, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import render, lint

POLICY = json.loads((ROOT / "tests" / "fixtures" / "policy-a.json").read_text())
SPEC = json.loads((ROOT / "tools" / "openapi.json").read_text())


class Rendered(unittest.TestCase):
    def setUp(self):
        self.wf = render.render(POLICY, SPEC)

    def test_lint_clean(self):
        self.assertEqual(lint.check(self.wf), [])

    def test_shape(self):
        n = self.wf["nodes"]
        self.assertEqual(self.wf["initial_node"], "prepare")
        self.assertEqual([k for k, v in n.items() if v["node_type"] == "conversation"], ["opening", "third_party", "identity", "negotiate"])
        self.assertEqual(sorted(t["function"]["name"] for t in n["negotiate"]["tools"]), ["create_promise", "transfer_to_agent"])
        self.assertEqual(n["account"]["pre_actions"][0]["function"]["name"], "get_account")
        self.assertEqual(self.wf["tools"][0]["config"]["alwaysRunsAt"], ["end_of_call"])

    def test_tool_fields_come_from_the_api_file(self):
        verify = n = self.wf["nodes"]["identity"]["tools"][0]
        body = verify["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(body["field"]["enum"], ["date_of_birth", "phone_last4"])
        self.assertEqual(body["customer_id"]["default"], "{{customer_id}}")
        self.assertEqual(verify["function"]["parameters"]["properties"]["url"]["default"], "https://freya-bank-mock.freyavoice.workers.dev/v1/verify_identity")

    def test_multi_product_adds_notes(self):
        p = dict(POLICY, multi_product={"enabled": True, "rules": "x"})
        wf = render.render(p, SPEC)
        self.assertIn("add_note", [t["function"]["name"] for t in wf["nodes"]["negotiate"]["tools"]])
        self.assertEqual(lint.check(wf), [])

    def test_no_null_anywhere(self):
        self.assertNotIn("null", json.dumps(self.wf))

    def test_prompts_carry_policy_sentences(self):
        self.assertIn("You will receive a text message confirming this promise.", self.wf["nodes"]["negotiate"]["task_message"])
        self.assertIn("I am sorry for your loss.", self.wf["nodes"]["end_deceased"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"])

    def test_lint_catches_breakage(self):
        wf = render.render(POLICY, SPEC)
        wf["nodes"]["negotiate"]["pre_actions"] = [{"x": 1}]
        wf["nodes"]["prepare"]["transitions"] = []
        wf["nodes"]["opening"]["task_message"] += " {{nothing_sets_this}}"
        problems = lint.check(wf)
        self.assertTrue(any("pre_actions" in p for p in problems) and any("always" in p for p in problems) and any("nothing_sets_this" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
