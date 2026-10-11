"""Date engine against the playbook's reference dates and other values of now. Run: .venv/bin/python -m unittest tests/test_dates.py"""
import datetime, pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from builder import dates

# Brief A's calendar as a test fixture. Only tests may hold brief values; the builder reads them from the brief.
POLICY = {
    "calendar": {"business_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]},
    "bands": [{"name": "early", "days_late_min": 1, "days_late_max": 7, "deadline_business_days": 12, "attempts": 1},
              {"name": "late", "days_late_min": 8, "days_late_max": 45, "deadline_business_days": 7, "attempts": 2}],
    "callback": {"days": ["today", "next_business_day"], "from": "10:00", "to": "19:00"},
    "attempt1_rule": {"rule": "last_business_day_of_week", "n": 0},
    "floor_field": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
    "product_words": {"credit_card": "credit card ending {card_last4}", "personal_loan": "personal loan", "car_loan": "car loan"},
}
NOW = "2026-10-14T11:00"


class ReferenceDates(unittest.TestCase):
    def setUp(self):
        self.f = dates.calendar_facts(NOW, POLICY)

    def test_today_is_wednesday(self):
        self.assertEqual(self.f["today"], "2026-10-14"); self.assertTrue(self.f["today_text"].startswith("Wednesday 14 October 2026"))

    def test_next_business_day(self):
        self.assertEqual(self.f["next_business_day"], "2026-10-15")

    def test_attempt1_is_this_friday(self):
        self.assertEqual(self.f["attempt1_date"], "2026-10-16")

    def test_deadlines(self):
        self.assertEqual(self.f["deadline_late"], "2026-10-23"); self.assertEqual(self.f["deadline_early"], "2026-11-02")

    def test_this_and_next_friday(self):
        self.assertIn("this Friday = 2026-10-16; next Friday = 2026-10-23", self.f["weekday_table"])

    def test_holiday_to_next_business_day(self):
        self.assertEqual(dates.next_business_day(datetime.date(2026, 10, 26), POLICY["calendar"], include_today=True), datetime.date(2026, 10, 27))

    def test_callback_window_today_and_tomorrow(self):
        self.assertEqual(self.f["callback_next_business_day"], "2026-10-15")
        self.assertIn("from 11:00 to 19:00", self.f["callback_text"]); self.assertIn("Thursday 15 October 2026", self.f["callback_text"])

    def test_business_days_text_skips_holiday(self):
        self.assertNotIn("2026-10-26", self.f["business_days_text"]); self.assertIn("2026-11-02", self.f["business_days_text"])


class DateAnswers(unittest.TestCase):
    def test_date_parts(self):
        for text, order, want in (("14-03-1988", "day_month_year", (14, 3, 1988)), ("3/14/1988", "month_day_year", (14, 3, 1988)), ("March 14th, 1988", "day_month_year", (14, 3, 1988)),
                                  ("0003-03-14", "day_month_year", (14, 3, None)), ("-03-14 1988", "day_month_year", (14, 3, 1988)), ("the 14th", "day_month_year", (14, None, None)),
                                  ("1988", "day_month_year", (None, None, 1988)), ("0000-00-00", "day_month_year", (None, None, None))):
            p = dates.date_parts(text, order)
            self.assertEqual((p["day"], p["month"], p["year"]), want, text)
        self.assertIsNone(dates.parse_full_date("31 February 1988"))
        self.assertEqual(dates.parse_full_date("14 March 1988"), datetime.date(1988, 3, 14))

    def test_weekday_with_a_day_number(self):
        today = datetime.date(2026, 10, 14)
        # the customer accepts an offered date with a weekday and a day number; a time of day is not a day number; a pair that never matches keeps the weekday
        for words, want in (("Monday 2", datetime.date(2026, 11, 2)), ("yes, Friday 16", datetime.date(2026, 10, 16)), ("Monday 2 November", datetime.date(2026, 11, 2)),
                            ("Friday at 10", datetime.date(2026, 10, 16)), ("Friday at 10:30", datetime.date(2026, 10, 16)), ("Monday at 2", datetime.date(2026, 10, 19)), ("Friday 10am", datetime.date(2026, 10, 16)),
                            ("Monday the 20th", datetime.date(2026, 10, 19)), ("next Monday 2", datetime.date(2026, 11, 2))):
            self.assertEqual(dates.parse_day_words(words, today), want, words)


class OtherDays(unittest.TestCase):
    def test_attempt1_said_on_friday_goes_to_next_week(self):
        self.assertEqual(dates.calendar_facts("2026-10-16T09:00", POLICY)["attempt1_date"], "2026-10-23")

    def test_attempt1_on_saturday(self):
        self.assertEqual(dates.calendar_facts("2026-10-17T12:00", POLICY)["attempt1_date"], "2026-10-23")

    def test_attempt1_before_holiday_week(self):
        self.assertEqual(dates.calendar_facts("2026-10-23T09:00", POLICY)["attempt1_date"], "2026-10-30")

    def test_next_friday_said_on_a_friday(self):
        self.assertIn("this Friday = 2026-10-16 (today); next Friday = 2026-10-23", dates.calendar_facts("2026-10-16T09:00", POLICY)["weekday_table"])

    def test_callback_after_window_closed(self):
        f = dates.calendar_facts("2026-10-14T19:30", POLICY)
        self.assertNotIn("today", f["callback_text"]); self.assertIn("Thursday 15 October 2026", f["callback_text"])

    def test_deadline_on_a_monday_skips_holiday(self):
        self.assertEqual(dates.calendar_facts("2026-10-19T10:00", POLICY)["deadline_late"], "2026-10-29")

    def test_bad_now_does_not_raise(self):
        self.assertIn("today", dates.calendar_facts("garbage", POLICY))

    def test_attempt1_by_other_rules(self):
        cal, today = POLICY["calendar"], datetime.date(2026, 10, 14)
        self.assertEqual(dates.attempt1_date(today, cal, {"rule": "next_business_day"}), datetime.date(2026, 10, 15))
        self.assertEqual(dates.attempt1_date(today, cal, {"rule": "nth_business_day", "n": 3}), datetime.date(2026, 10, 19))
        self.assertIsNone(dates.attempt1_date(today, cal, {"rule": "none"}))
        self.assertIsNone(dates.attempt1_date(today, cal, {}))

    def test_empty_policy_gives_facts_without_brief_values(self):
        f = dates.calendar_facts(NOW, {})
        self.assertEqual(f["attempt1_date"], ""); self.assertIn("no callback window", f["callback_text"])


class ProductFacts(unittest.TestCase):
    def test_credit_card_late_band(self):
        p = [{"product_id": "p1", "type": "credit_card", "card_last4": "4821", "past_due": 420, "days_late": 12, "minimum_payment": 50}]
        r = dates.product_facts(p, POLICY, NOW)
        f = r["facts"][0]
        self.assertEqual((f["words"], f["band"], f["deadline"], f["floor"], f["attempts"]), ("credit card ending 4821", "late", "2026-10-23", 50, 2))
        self.assertIn("Product 1: id p1, credit card ending 4821", r["summary"])

    def test_loan_early_band(self):
        p = [{"product_id": "p2", "type": "personal_loan", "past_due": 300, "days_late": 3, "instalment_amount": 150}]
        f = dates.product_facts(p, POLICY, NOW)["facts"][0]
        self.assertEqual((f["words"], f["band"], f["deadline"], f["floor"], f["attempts"]), ("personal loan", "early", "2026-11-02", 150, 1))

    def test_empty_products(self):
        self.assertEqual(dates.product_facts([], POLICY, NOW)["count"], 0)


class DayWords(unittest.TestCase):
    def test_phrases(self):
        wed, fri = datetime.date(2026, 10, 14), datetime.date(2026, 10, 16)
        for text, today, exp in [("next Friday", wed, "2026-10-23"), ("this Friday", wed, "2026-10-16"), ("Friday", wed, "2026-10-16"), ("next Friday", fri, "2026-10-23"),
                                 ("Saturday the 17th of October", wed, "2026-10-17"), ("Monday the 19th", wed, "2026-10-19"), ("20 November", wed, "2026-11-20"), ("November 6", wed, "2026-11-06"),
                                 ("tomorrow", wed, "2026-10-15"), ("the 30th", wed, "2026-10-30"), ("2026-10-23", wed, "2026-10-23"), ("next week", wed, None), ("when my salary comes", wed, None),
                                 # "next <weekday>" is the following calendar week even for a weekday earlier in the week than today
                                 ("next Monday", wed, "2026-10-19"), ("next Tuesday", wed, "2026-10-20"), ("next Sunday", wed, "2026-10-25"), ("next Monday", datetime.date(2026, 10, 15), "2026-10-19"),
                                 ("next Monday", datetime.date(2026, 10, 19), "2026-10-26"), ("Monday", wed, "2026-10-19"), ("Wednesday", wed, "2026-10-14")]:
            got = dates.parse_day_words(text, today)
            self.assertEqual(got.isoformat() if got else None, exp, text)

    def test_adjust_day_by_policy(self):
        cal, today, deadline = POLICY["calendar"], datetime.date(2026, 10, 14), datetime.date(2026, 10, 23)
        rules = {"non_business_day": "next_business_day", "after_deadline": "offer_deadline"}
        self.assertEqual(dates.adjust_day(datetime.date(2026, 10, 17), today, deadline, cal, rules)[0], datetime.date(2026, 10, 19))
        self.assertEqual(dates.adjust_day(datetime.date(2026, 10, 31), today, deadline, cal, rules)[0], datetime.date(2026, 10, 23))
        self.assertEqual(dates.adjust_day(datetime.date(2026, 10, 20), today, deadline, cal, rules), (datetime.date(2026, 10, 20), ""))
        self.assertIsNone(dates.adjust_day(datetime.date(2026, 10, 17), today, deadline, cal, {})[0])


class SandboxSafety(unittest.TestCase):
    def test_no_double_braces_in_source(self):
        src = pathlib.Path(dates.__file__).read_text()
        self.assertNotIn("{{", src); self.assertNotIn("}}", src)

    def test_only_allowed_imports(self):
        src = pathlib.Path(dates.__file__).read_text()
        for line in src.splitlines():
            if line.startswith(("import ", "from ")):
                self.assertIn(line.split()[1].split(".")[0], ("json", "re", "datetime"), line)


if __name__ == "__main__":
    unittest.main()
