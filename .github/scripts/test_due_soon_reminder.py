"""Unit tests for the due-soon reminder logic. Run: python3 -m unittest discover -s .github/scripts"""

import datetime as dt
import unittest

import due_soon_reminder as m

TODAY = dt.date(2026, 8, 13)

# Verbatim body of Disasters-Learning-Portal/disasters-tracking#56.
REAL_BODY = (
    "**Smartsheet row:** `6.13`\n"
    "**Owner:** Disasters\n"
    "**Assigned to:** Ronan / Garrett\n"
    "**Smartsheet status:** Not Started\n"
    "**Schedule:** 23d — 2026-08-31 → 2026-09-30\n\n"
    "### Notes\n\nPORTAL 101 + potentially 1 more curated module.\n"
)

NO_DATES_BODY = (
    "**Smartsheet row:** `6.4`\n"
    "**Schedule:** _no dates in Smartsheet_\n\n"
    "⚠️ No start/end date in the Smartsheet — schedule fields left empty.\n"
)


class TestParseEndDate(unittest.TestCase):
    def test_real_issue_body(self):
        self.assertEqual(m.parse_end_date(REAL_BODY), dt.date(2026, 9, 30))

    def test_takes_end_not_start(self):
        body = "**Schedule:** 143d — 2026-02-12 → 2026-08-31"
        self.assertEqual(m.parse_end_date(body), dt.date(2026, 8, 31))

    def test_single_day_row(self):
        body = "**Schedule:** 1d — 2026-09-29 → 2026-09-29"
        self.assertEqual(m.parse_end_date(body), dt.date(2026, 9, 29))

    def test_no_dates_row(self):
        self.assertIsNone(m.parse_end_date(NO_DATES_BODY))

    def test_missing_schedule_line(self):
        self.assertIsNone(m.parse_end_date("Just some prose about 2026 deadlines."))

    def test_empty_and_none_body(self):
        self.assertIsNone(m.parse_end_date(""))
        self.assertIsNone(m.parse_end_date(None))

    def test_ignores_dates_outside_the_schedule_line(self):
        body = "Notes: slipped from 2026-01-01.\n**Schedule:** 5d — 2026-08-03 → 2026-08-07\n"
        self.assertEqual(m.parse_end_date(body), dt.date(2026, 8, 7))

    def test_ascii_arrow(self):
        body = "**Schedule:** 5d - 2026-08-03 -> 2026-08-07"
        self.assertEqual(m.parse_end_date(body), dt.date(2026, 8, 7))

    def test_impossible_date_is_not_a_crash(self):
        self.assertIsNone(m.parse_end_date("**Schedule:** 1d — 2026-02-30 → 2026-13-45"))


class TestIsDueSoon(unittest.TestCase):
    def test_exactly_three_days_out_fires(self):
        self.assertTrue(m.is_due_soon(dt.date(2026, 8, 16), TODAY, 3))

    def test_four_days_out_is_quiet(self):
        self.assertFalse(m.is_due_soon(dt.date(2026, 8, 17), TODAY, 3))

    def test_inside_window_still_fires(self):
        # A skipped cron run must not lose the reminder forever.
        for day in (14, 15):
            self.assertTrue(m.is_due_soon(dt.date(2026, 8, day), TODAY, 3))

    def test_due_today_fires(self):
        self.assertTrue(m.is_due_soon(TODAY, TODAY, 3))

    def test_overdue_is_quiet(self):
        self.assertFalse(m.is_due_soon(dt.date(2026, 8, 12), TODAY, 3))

    def test_far_future_is_quiet(self):
        self.assertFalse(m.is_due_soon(dt.date(2027, 1, 8), TODAY, 3))

    def test_lead_days_zero_is_due_date_only(self):
        self.assertTrue(m.is_due_soon(TODAY, TODAY, 0))
        self.assertFalse(m.is_due_soon(dt.date(2026, 8, 14), TODAY, 0))


class TestIdempotency(unittest.TestCase):
    def test_marker_matches_same_end_date(self):
        end = dt.date(2026, 9, 30)
        prior = [{"body": m.render_comment({}, end, TODAY, ["kyle-lesinger"])}]
        self.assertTrue(m.already_reminded(prior, end))

    def test_rescheduled_issue_gets_a_fresh_reminder(self):
        prior = [{"body": m.render_comment({}, dt.date(2026, 9, 30), TODAY, [])}]
        self.assertFalse(m.already_reminded(prior, dt.date(2026, 10, 30)))

    def test_unrelated_comments_do_not_suppress(self):
        prior = [{"body": "Any update on this?"}, {"body": None}, {}]
        self.assertFalse(m.already_reminded(prior, dt.date(2026, 9, 30)))

    def test_no_comments(self):
        self.assertFalse(m.already_reminded([], dt.date(2026, 9, 30)))


class TestLabelGate(unittest.TestCase):
    def test_smartsheet_label_present(self):
        issue = {"labels": [{"name": "owner: Disasters"}, {"name": "smartsheet"}]}
        self.assertTrue(m.has_label(issue, "smartsheet"))

    def test_case_insensitive(self):
        self.assertTrue(m.has_label({"labels": [{"name": "Smartsheet"}]}, "smartsheet"))

    def test_label_absent(self):
        self.assertFalse(m.has_label({"labels": [{"name": "EPIC"}]}, "smartsheet"))

    def test_no_labels_key(self):
        self.assertFalse(m.has_label({}, "smartsheet"))

    def test_owner_label_is_not_a_substring_match(self):
        self.assertFalse(m.has_label({"labels": [{"name": "smartsheet-legacy"}]}, "smartsheet"))


ISSUE = {
    "number": 58,
    "labels": [{"name": "owner: Disasters"}, {"name": "smartsheet"}],
}


class TestHeadline(unittest.TestCase):
    def test_severity_escalates_as_the_date_approaches(self):
        self.assertEqual(m.headline_for(3), "🟡 3 days left")
        self.assertEqual(m.headline_for(1), "🟠 1 day left")
        self.assertEqual(m.headline_for(0), "🔴 Due today")

    def test_singular_day(self):
        self.assertNotIn("1 days", m.headline_for(1))


class TestOwners(unittest.TestCase):
    def test_prefix_stripped(self):
        self.assertEqual(m.owners_of(ISSUE), "Disasters")

    def test_joint_ownership(self):
        issue = {"labels": [{"name": "owner: Disasters"}, {"name": "owner: VEDA"}]}
        self.assertEqual(m.owners_of(issue), "Disasters, VEDA")

    def test_no_owner_label(self):
        self.assertEqual(m.owners_of({"labels": [{"name": "EPIC"}]}), "")


class TestRenderComment(unittest.TestCase):
    def test_three_days_layout(self):
        body = m.render_comment(ISSUE, dt.date(2026, 8, 16), TODAY, ["kyle-lesinger"])
        self.assertTrue(body.startswith(m.marker_for(dt.date(2026, 8, 16))))
        self.assertIn("## ⏳ 🟡 3 days left", body)
        self.assertIn("| Ticket | End date | Days left | Owner |", body)
        self.assertIn("| #58 | **2026-08-16 (Sun)** | **3** | Disasters |", body)
        self.assertIn("**@kyle-lesinger** — is this still on track?", body)

    def test_table_rows_have_matching_column_counts(self):
        body = m.render_comment(ISSUE, dt.date(2026, 8, 16), TODAY, [])
        rows = [ln for ln in body.splitlines() if ln.startswith("|")]
        self.assertEqual(len(rows), 3)  # header, alignment, one data row
        self.assertEqual(len({r.count("|") for r in rows}), 1)

    def test_tomorrow_and_today_wording(self):
        tomorrow = m.render_comment(ISSUE, dt.date(2026, 8, 14), TODAY, [])
        self.assertIn("🟠 1 day left", tomorrow)
        self.assertIn("tomorrow", tomorrow)
        self.assertIn("🔴 Due today", m.render_comment(ISSUE, TODAY, TODAY, []))

    def test_unassigned_issue_says_so(self):
        body = m.render_comment(ISSUE, dt.date(2026, 8, 16), TODAY, [])
        self.assertIn("**Unassigned**", body)
        self.assertNotIn("@", body.split("<sub>")[0].split("| #58")[1])

    def test_multiple_assignees(self):
        body = m.render_comment(ISSUE, dt.date(2026, 8, 16), TODAY, ["a-dev", "b-dev"])
        self.assertIn("**@a-dev** **@b-dev**", body)

    def test_missing_number_and_labels_do_not_crash(self):
        body = m.render_comment({}, dt.date(2026, 8, 16), TODAY, [])
        self.assertIn("| this ticket | **2026-08-16 (Sun)** | **3** | — |", body)


class TestPagination(unittest.TestCase):
    def test_next_link_extracted(self):
        header = '<https://api.github.com/x?page=2>; rel="next", <https://api.github.com/x?page=9>; rel="last"'
        self.assertEqual(m._next_link(header), "https://api.github.com/x?page=2")

    def test_last_page_has_no_next(self):
        self.assertIsNone(m._next_link('<https://api.github.com/x?page=1>; rel="prev"'))
        self.assertIsNone(m._next_link(None))


if __name__ == "__main__":
    unittest.main()
