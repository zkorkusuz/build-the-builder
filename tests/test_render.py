"""Render the Brief A fixture policy and check the workflow locally. Run: .venv/bin/python -m unittest tests.test_render"""
import json, pathlib, re, sys, unittest
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
        self.assertEqual([k for k, v in n.items() if v["node_type"] == "conversation"], ["opening", "opening_again", "third_party", "identity", "negotiate"])
        self.assertEqual(sorted(t["function"]["name"] for t in n["negotiate"]["tools"]), ["create_promise", "transfer_to_agent"])
        self.assertEqual(n["account"]["pre_actions"][0]["function"]["name"], "get_account")
        self.assertEqual(self.wf["tools"], [])
        self.assertEqual(n["close"]["pre_actions"][0]["function"]["name"], "close_call"); self.assertEqual(n["close"]["transitions"][-1]["target_node"], "hang_up_goodbye")
        for end in ("end_goodbye", "end_quiet", "end_deceased", "end_id_failed"):
            self.assertEqual(n[end]["transitions"][-1]["target_node"], "close")
        self.assertEqual(n["hang_up_goodbye"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"], "Thank you for your time. Goodbye.")
        self.assertEqual(n["hang_up_quiet"]["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"], "none")
        self.assertEqual(n["negotiate"]["on_enter"], {"type": "tts", "text": "{{debt_statement}}"})
        self.assertEqual(n["negotiate"]["extraction_schema"][0]["enum_values"], ["none", "refused", "hardship", "dispute", "paid", "service_error"])
        self.assertTrue(all("position" in v for v in n.values()))

    def test_no_brief_values_in_an_empty_policy_render(self):
        wf = render.render({}, SPEC)
        text = json.dumps(wf)
        for leaked in ("day_month_swapped", "10:00", "19:00", "mobile app", "collections", "restructuring", "Freya Bank", "2026-10-26"):
            self.assertNotIn(leaked, text, leaked)
        self.assertEqual([p for p in lint.check(wf) if "nothing sets" not in p], [])

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

    def test_account_facts_reads_flattened_result_keys(self):
        import datetime
        code = self.wf["nodes"]["account_facts"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        vars = {"now": "2026-10-14T11:00", "account_response.data.products.0.product_id": "p1", "account_response.data.products.0.type": "credit_card",
                "account_response.data.products.0.card_last4": "4821", "account_response.data.products.0.past_due": 420, "account_response.data.products.0.days_late": 6,
                "account_response.data.products.0.minimum_payment": 126, "account_response.data.products.1.product_id": "p2", "account_response.data.products.1.type": "car_loan",
                "account_response.data.products.1.past_due": 75.5, "account_response.data.products.1.days_late": 12, "account_response.data.products.1.instalment_amount": 25}
        exec(code, {"vars": vars, "json": json, "datetime": datetime})
        self.assertEqual(vars["product_count"], "2")
        self.assertIn("Your credit card ending 4821 is 420 past due and 6 days late. Your car loan is 75.50 past due and 12 days late.", vars["debt_statement"])
        self.assertTrue(vars["debt_statement"].startswith("I am calling from the collections team") and vars["debt_statement"].endswith("Can you make this payment today?"))
        facts = json.loads(vars["product_facts_json"])
        self.assertEqual([f["deadline"] for f in facts], ["2026-11-02", "2026-10-23"])

    def test_every_named_transition_tool_exists(self):
        text = json.dumps(self.wf)
        targets = {t["target_node"] for n in self.wf["nodes"].values() for t in n.get("transitions", []) if t.get("is_tool_call")}
        for name in set(re.findall(r"transition_to_(\w+)", text)):
            self.assertIn(name, targets, "prompt or hook names transition_to_" + name)

    def test_promise_pre_hook_blocks_bad_dates_and_amounts(self):
        import datetime
        pre = next(t for t in self.wf["nodes"]["negotiate"]["tools"] if t["function"]["name"] == "create_promise")["pre_process_code"]
        facts = json.dumps([{"product_id": "p1", "deadline": "2026-10-23", "floor": 126, "words": "credit card ending 4821"}])
        for date, amount, expect_block in (("2026-10-31", 200, "after the latest allowed date"), ("2026-10-17", 200, "not a business day"), ("2026-10-16", 50, "below the floor"), ("2026-10-16", 200, "")):
            vars = {"today": "2026-10-14", "product_facts_json": facts}
            config = {"body": {"customer_id": "c1", "product_id": "p1", "amount": amount, "date": date}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
            if expect_block:
                self.assertEqual(config["body"]["product_id"], "blocked", date); self.assertEqual(config["body"]["customer_id"], "c1"); self.assertIn(expect_block, vars["promise_block"])
            else:
                self.assertEqual(config["body"]["date"], date); self.assertEqual(vars["promise_block"], "")
        # an identical promise recorded earlier in the call is not sent again; a different date is
        for date, word in (("2026-10-16", "ALREADY recorded"), ("2026-10-19", "")):
            vars = {"today": "2026-10-14", "product_facts_json": facts, "promises_recorded": json.dumps([{"product_id": "p1", "amount": 200, "date": "2026-10-16"}])}
            config = {"body": {"customer_id": "c1", "product_id": "p1", "amount": 200.0, "date": date}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
            self.assertIn(word, vars["promise_block"], date); self.assertEqual(config["body"]["product_id"] == "blocked", bool(word))

    def test_verify_pre_hook_joins_partial_answers(self):
        import datetime
        pre = self.wf["nodes"]["identity"]["tools"][0]["pre_process_code"]
        vars = {}
        sent = []
        for field, answer in (("date_of_birth", "14 March"), ("date_of_birth", "1988"), ("phone_last4", "44"), ("phone_last4", "71"), ("phone_last4", "44"), ("phone_last4", "the last four are 4471"), ("phone_last4", "4"), ("phone_last4", "four"), ("phone_last4", "7"), ("phone_last4", "1"), ("phone_last4", "4"), ("phone_last4", "44"), ("phone_last4", "447"), ("phone_last4", "1"), ("date_of_birth", "0003-03-14"), ("date_of_birth", "1988-03-03"), ("date_of_birth", "-03-14"), ("date_of_birth", "the year is 1988")):
            config = {"body": {"field": field, "answer": answer}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
            sent.append("blocked: " + vars["id_block"][:10] if config["body"]["answer"] == "blocked" else config["body"]["answer"])
        self.assertEqual(sent, ["blocked: INCOMPLETE", "1988-03-14", "blocked: INCOMPLETE", "4471", "blocked: INCOMPLETE", "4471", "blocked: INCOMPLETE", "blocked: INCOMPLETE", "blocked: INCOMPLETE", "4471", "blocked: INCOMPLETE", "blocked: INCOMPLETE", "blocked: INCOMPLETE", "4471", "blocked: INCOMPLETE", "1988-03-14", "blocked: INCOMPLETE", "1988-03-14"])

    def test_asking_for_a_person_is_not_a_declined_check(self):
        n = self.wf["nodes"]["identity"]
        self.assertIn("wants_person", n["extraction_schema"][0]["enum_values"])
        routes = [t for t in n["transitions"] if "wants_person" in json.dumps(t)]
        self.assertEqual(routes, [])

    def test_callback_pre_hook_checks_the_window_and_counts(self):
        import datetime
        pre = self.wf["nodes"]["third_party"]["tools"][0]["pre_process_code"]
        base = {"today": "2026-10-14", "now_time": "11:00", "callback_next_business_day": "2026-10-15", "callback_text": "window"}
        for date, time, inside in (("2026-10-14", "21:00", False), ("2026-10-18", "10:00", False), ("2026-10-14", "10:30", False), ("2026-10-15", "11:00", True), ("2026-10-14", "15:00", True)):
            vars = dict(base); config = {"body": {"date": date, "time": time}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
            self.assertEqual(config["body"]["date"] != "blocked", inside, date + " " + time)
        # a day outside the window counts as an outside offer even without a time; a vague time on an allowed day is asked for
        for date, time, word in (("Sunday morning", "", "outside"), ("tomorrow morning", "", "could not be read"), ("2026-10-15", "morning", "could not be read"), ("2026-10-14", "", "could not be read")):
            vars = dict(base); config = {"body": {"date": date, "time": time}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
            self.assertIn(word, vars["callback_block"], date)
        vars = dict(base)
        for n in (1, 2):
            config = {"body": {"date": "2026-10-18", "time": "10:00"}}
            exec(pre, {"vars": vars, "config": config, "json": json, "datetime": datetime})
        self.assertIn("transition_to_outcome_no_callback_quiet", vars["callback_block"])

    def test_wrap_up_per_end_reason(self):
        n = self.wf["nodes"]
        self.assertTrue({"wrap_up", "wrap_up_refused", "wrap_up_dispute", "wrap_up_paid"} <= set(n))
        self.assertIn("transition_to_wrap_up_dispute when", n["negotiate"]["task_message"])
        self.assertIn("STOP", n["account_facts"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"])

    def test_close_call_recomputes_outcome_for_a_verified_call(self):
        pre = self.wf["nodes"]["close"]["pre_actions"][0]["pre_process_code"]
        vars = {"id_state": "verified", "outcome": "no_promise", "reason": "refused", "promises_recorded": json.dumps([{"product_id": "p1", "amount": 1, "date": "2026-10-14"}]), "transfer_state": "none"}
        config = {"body": {"outcome": "{{outcome}}", "reason": "{{reason}}"}}
        exec(pre, {"vars": vars, "config": config, "json": json})
        self.assertEqual(config["body"], {"outcome": "promise"})
        vars = {"id_state": "pending", "outcome": "not_reached", "reason": "callback"}
        config = {"body": {"outcome": "", "reason": ""}}
        exec(pre, {"vars": vars, "config": config, "json": json})
        self.assertEqual(config["body"], {"outcome": "not_reached", "reason": "callback"})

    def test_no_null_anywhere(self):
        self.assertNotIn("null", json.dumps(self.wf))

    def test_prompts_carry_policy_sentences(self):
        self.assertIn("You will receive a text message confirming this promise.", self.wf["nodes"]["negotiate"]["task_message"])
        self.assertIn("I am sorry for your loss.", self.wf["nodes"]["hang_up_deceased"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"])

    def test_lint_catches_breakage(self):
        wf = render.render(POLICY, SPEC)
        wf["nodes"]["negotiate"]["pre_actions"] = [{"x": 1}]
        wf["nodes"]["prepare"]["transitions"] = []
        wf["nodes"]["opening"]["task_message"] += " {{nothing_sets_this}}"
        problems = lint.check(wf)
        self.assertTrue(any("pre_actions" in p for p in problems) and any("always" in p for p in problems) and any("nothing_sets_this" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
