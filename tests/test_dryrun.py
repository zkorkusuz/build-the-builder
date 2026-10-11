"""The data-path dry run: baking, deterministic routing and the walk, without a network."""
import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder import dryrun

CODE = {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": "vars['route'] = 'go' if vars.get('customer') else 'stop'"}}}}}


def node(key, target_ok, target_bad):
    return {"name": key, "node_type": "code", "passthrough": True, "passthrough_default_transition": target_bad, "pre_actions": [CODE],
            "transitions": [{"target_node": target_ok, "description": "ok", "condition": {"logic": "or", "conditions": [{"variable": "route", "operator": "equals", "operand": "go"}]}},
                            {"target_node": target_bad, "description": "always", "condition": {"operator": "always"}}]}


class DryRun(unittest.TestCase):
    def test_bake_fills_and_drops_placeholders_like_the_engine(self):
        schema = {"type": "object", "properties": {"data": {"type": "object", "properties": {"id": {"type": "string", "default": "{{customer}}"}, "ref": {"type": "string", "default": "{{nothing}}"}, "kind": {"type": "string", "default": "A"}}}}}
        self.assertEqual(dryrun.bake(schema, {"customer": "c1"}), {"data": {"id": "c1", "kind": "A"}})

    def test_walk_reaches_a_conversation_or_reports_the_early_end(self):
        wf = {"initial_node": "start", "test_variables": {"customer": "c1"}, "nodes": {
            "start": node("start", "talk", "bye"), "talk": {"name": "talk", "node_type": "conversation", "transitions": []},
            "bye": {"name": "bye", "node_type": "end_call", "transitions": [], "terminal": {}}}}
        problems, trail = dryrun.walk(wf)
        self.assertEqual(problems, []); self.assertIn("talk: conversation step reached", trail)
        wf["test_variables"] = {}
        problems, trail = dryrun.walk(wf)
        self.assertEqual(len(problems), 1); self.assertIn("before any conversation step", problems[0])

    def test_conditions(self):
        v = {"n": "3", "s": "ready"}
        self.assertTrue(dryrun.holds({"logic": "or", "conditions": [{"logic": "and", "conditions": [{"variable": "n", "operator": "greater_than", "operand": 2}, {"variable": "s", "operator": "equals", "operand": "ready"}]}]}, v))
        self.assertFalse(dryrun.holds({"variable": "x", "operator": "is_set"}, v)); self.assertTrue(dryrun.holds({"operator": "always"}, v))


if __name__ == "__main__":
    unittest.main()
