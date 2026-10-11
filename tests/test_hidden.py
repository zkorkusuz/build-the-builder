"""The checks tools/hidden.py runs on a hidden-brief build: what must make us build again, what is only noted."""
import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import hidden

RESULT = {"workflow_id": "w1", "agent_id": "a1", "steps": 2, "tools": 3, "export": "x.json"}
EXPORT = {"workflow_id": "w1", "workflow": {"nodes": {"a": {"tools": [1, 2]}, "b": {"pre_actions": [1]}}}}
GOOD = ["start 2026 | briefs h.md", "builder: commit abc", "model call: m | normalize", "dry run: the platform accepted the workflow",
        "freya: workflow w1 agent a1", "export: x.json", "self-test: chat probe: the agent answered 'Hello?' after 2 s, names the customer: yes, said: Hi", "end 2026"]


class Check(unittest.TestCase):
    def test_clean_build(self):
        self.assertEqual(hidden.check(GOOD, RESULT, EXPORT, {}), ([], False))

    def test_crash_and_fallbacks_mean_rerun(self):
        self.assertTrue(hidden.check([], None, None, {})[1])
        for line in ("render: FAILED on this policy, x; rendering the bare template", "save: the platform rejected the workflow (x); saving the bare template"):
            problems, rerun = hidden.check(GOOD + [line], RESULT, EXPORT, {})
            self.assertTrue(rerun, line); self.assertTrue(any("trace:" in p for p in problems))

    def test_notes_are_kept(self):
        problems, rerun = hidden.check(GOOD + ["normalize: repairing bands"], RESULT, EXPORT, {})
        self.assertFalse(rerun); self.assertEqual(len(problems), 1)

    def test_export_must_match_trace(self):
        self.assertIn("export: 2 steps and 3 tools, the trace says 2 and 4", hidden.check(GOOD, {**RESULT, "tools": 4}, EXPORT, {})[0])
        self.assertIn("export: workflow id differs from the trace", hidden.check(GOOD, RESULT, {**EXPORT, "workflow_id": "w2"}, {})[0])
        self.assertIn("export: file missing or not JSON", hidden.check(GOOD, RESULT, None, {})[0])

    def test_missing_lines_and_secrets(self):
        problems, _ = hidden.check(GOOD[:-1], RESULT, EXPORT, {"FREYA_API_KEY": "fak_secret_value"})
        self.assertIn("trace: no 'end' line", problems)
        problems, _ = hidden.check(GOOD + ["Authorization fak_secret_value"], RESULT, EXPORT, {"FREYA_API_KEY": "fak_secret_value"})
        self.assertIn("secret FREYA_API_KEY appears in the trace or the export", problems)


if __name__ == "__main__":
    unittest.main()


class Anchoring(unittest.TestCase):
    """The brief's own words in a policy line never trigger a rebuild; the markers bind to the stage that wrote the line."""

    def test_policy_lines_with_brief_words_do_not_rerun(self):
        lines = GOOD + ["20:05:12 policy: end reasons: refused -> no_promise/refused; FAILED -> id_failed", "20:05:12 policy: outcomes: offer rejected -> declined"]
        self.assertEqual(hidden.check(lines, RESULT, EXPORT, {}), ([], False))

    def test_timestamped_lines_count_as_required(self):
        lines = ["20:05:10 " + l for l in GOOD]
        self.assertEqual(hidden.check(lines, RESULT, EXPORT, {}), ([], False))
        self.assertIn("trace: no 'end' line", hidden.check(["20:05:10 policy: end reasons: x"] + lines[:-1], RESULT, EXPORT, {})[0])

    def test_probe_without_the_name_is_a_note(self):
        lines = GOOD[:-2] + ["self-test: chat probe: the agent answered 'Hello?' after 2 s, names the customer: no, said: Hi", "end 2026"]
        problems, rerun = hidden.check(lines, RESULT, EXPORT, {})
        self.assertFalse(rerun); self.assertEqual(len(problems), 1)

    def test_relative_paths(self):
        self.assertEqual(hidden.relative(str(hidden.ROOT / "briefs" / "x.md")), "briefs/x.md")
        self.assertIsNone(hidden.relative("/tmp/elsewhere/x.md"))
