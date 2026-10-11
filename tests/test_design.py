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

    def test_pre_hook_epilogue_restores_a_field_the_engine_dropped(self):
        """A hook sets the variable of a baked field; the engine removed the field before the hook ran; the epilogue puts it back."""
        tool = {"type": "function", "function": {"name": "lookup", "handler": "__function__:api_call", "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "default": "https://x/y"}, "method": {"type": "string", "default": "POST"},
            "body": {"type": "object", "properties": {"data": {"type": "object", "properties": {"ref": {"type": "string", "default": "{{chosen_ref}}"}, "kind": {"type": "string", "default": "A"}}},
                                                       "call": {"type": "object", "properties": {"lang": {"type": "string", "default": "tr"}}}}}}}},
                "pre_process_code": "vars['chosen_ref'] = 'r-7'"}
        wf = design.tidy({"initial_node": "n", "nodes": {"n": {"name": "n", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "n", "pre_actions": [tool], "transitions": [{"target_node": "n", "description": "always", "condition": {"operator": "always"}}]}}})
        hook = wf["nodes"]["n"]["pre_actions"][0]["pre_process_code"]
        self.assertNotIn("{{", hook)
        vars, config = {}, {"body": {"call": {"lang": "tr"}}}          # the engine dropped data.ref and with it the empty data object
        exec(hook, {"vars": vars, "config": config, "json": json})
        self.assertEqual(config["body"]["data"]["ref"], "r-7"); self.assertEqual(config["body"]["call"]["lang"], "tr")
        vars, config = {}, {"body": {"data": {"ref": "already"}}}      # a field the engine did fill is left alone
        exec(hook.replace("vars['chosen_ref'] = 'r-7'", "pass"), {"vars": vars, "config": config, "json": json})
        self.assertEqual(config["body"]["data"]["ref"], "already")
        self.assertEqual(lint.check(wf), [])

    def test_reference_holds_both_platform_docs(self):
        text = design.reference()
        self.assertIn("workflow-format.md", text); self.assertIn("tools-and-code.md", text); self.assertIn("response_mapping", text)
        self.assertNotIn("Brief A", text)


if __name__ == "__main__":
    unittest.main()
