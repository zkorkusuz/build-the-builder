"""The design stage: mechanical tidying of a model-written workflow and the reference it shows the model."""
import json, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import design, lint


class Design(unittest.TestCase):
    def test_tidy_fixes_what_the_platform_drops_silently(self):
        wf = {"initial_node": "a", "agent_config": {"x": 1}, "nodes": {
            "a": {"name": "wrong", "node_type": "conversation", "pre_actions": [{}], "note": None, "transitions": [{"target_node": "b", "description": "d", "condition": {"operator": "always"}}]},
            "b": {"name": "b", "node_type": "code", "tools": [{}], "passthrough": True, "passthrough_default_transition": "c", "pre_actions": [], "transitions": [{"target_node": "c", "description": "always", "condition": {"operator": "always"}}]},
            "c": {"name": "c", "node_type": "end_call", "transitions": [{"target_node": "a"}], "terminal": {"type": "function", "function": {"name": "done", "handler": "__function__:end_call", "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}}}
        out = design.tidy(wf)
        self.assertNotIn("agent_config", out)
        self.assertEqual(out["nodes"]["a"]["name"], "a"); self.assertNotIn("pre_actions", out["nodes"]["a"]); self.assertNotIn("note", out["nodes"]["a"])
        self.assertNotIn("tools", out["nodes"]["b"]); self.assertEqual(out["nodes"]["c"]["transitions"], [])
        self.assertNotIn("null", json.dumps(out))
        self.assertEqual(lint.check(out), [])

    def test_reference_holds_both_platform_docs(self):
        text = design.reference()
        self.assertIn("workflow-format.md", text); self.assertIn("tools-and-code.md", text); self.assertIn("response_mapping", text)
        self.assertNotIn("Brief A", text)


if __name__ == "__main__":
    unittest.main()
