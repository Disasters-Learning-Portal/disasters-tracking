#!/usr/bin/env python3
"""Comment on tracking issues whose scheduled end date is nearly here.

Reads the ``**Schedule:** 23d — 2026-08-31 → 2026-09-30`` line that the
Smartsheet migration writes into every issue body, and posts a one-time
heads-up comment once the end date is within ``--lead-days`` (default 3).

Idempotency is carried by an HTML marker embedded in the comment
(``<!-- due-soon-reminder end=YYYY-MM-DD -->``): one reminder per issue per
end date, so a re-scheduled ticket gets a fresh reminder while a re-run of the
workflow on the same day does not double-post.

Stdlib only -- no pip install on the runner.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MARKER_PREFIX = "<!-- due-soon-reminder"

# The Schedule line as written by the Smartsheet migration. Dates are ISO;
# the end date is the last ISO date on that line (rows with no dates render
# "_no dates in Smartsheet_" and simply yield nothing).
SCHEDULE_LINE = re.compile(r"^\s*\**Schedule:?\**\s*:?.*$", re.MULTILINE | re.IGNORECASE)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --------------------------------------------------------------------------
# pure logic (unit-tested in test_due_soon_reminder.py)
# --------------------------------------------------------------------------
def parse_end_date(body):
    """Return the scheduled end date from an issue body, or None."""
    if not body:
        return None
    for line in SCHEDULE_LINE.findall(body):
        dates = ISO_DATE.findall(line)
        if not dates:
            continue
        try:
            return dt.date.fromisoformat(dates[-1])
        except ValueError:
            continue
    return None


def marker_for(end_date):
    return "{} end={} -->".format(MARKER_PREFIX, end_date.isoformat())


def already_reminded(comments, end_date):
    """True if a reminder for this exact end date was already posted."""
    marker = marker_for(end_date)
    return any(marker in (c.get("body") or "") for c in comments)


def days_until(end_date, today):
    return (end_date - today).days


def is_due_soon(end_date, today, lead_days):
    """Fire inside the window, including the end date itself.

    Uses ``<= lead_days`` rather than ``== lead_days`` so a day when the
    scheduled run is skipped (GitHub drops cron runs under load) still gets
    its reminder the next day instead of losing it forever.
    """
    remaining = days_until(end_date, today)
    return 0 <= remaining <= lead_days


def has_label(issue, wanted):
    """True if the issue carries this label (case-insensitive)."""
    return any(
        (label.get("name") or "").lower() == wanted.lower()
        for label in issue.get("labels") or []
    )


BOARD_URL = "https://github.com/orgs/Disasters-Learning-Portal/projects/5"
WORKFLOW_URL = (
    "https://github.com/Disasters-Learning-Portal/disasters-tracking"
    "/blob/main/.github/workflows/due-soon-reminder.yml"
)


def headline_for(remaining):
    """Severity dot + headline. Read in an email subject-line glance."""
    if remaining <= 0:
        return "🔴 Due today"
    if remaining == 1:
        return "🟠 1 day left"
    if remaining <= 3:
        return "🟡 {} days left".format(remaining)
    return "🟢 {} days left".format(remaining)


def owners_of(issue):
    """The `owner: VEDA` / `owner: Disasters` labels, stripped of the prefix."""
    names = [
        (label.get("name") or "")
        for label in issue.get("labels") or []
        if (label.get("name") or "").lower().startswith("owner:")
    ]
    return ", ".join(n.split(":", 1)[1].strip() for n in names)


def render_comment(issue, end_date, today, assignees):
    """Build the reminder comment.

    Markdown only -- GitHub's notification email renders headings, tables and
    <sub>, but strips arbitrary HTML/CSS, so the layout has to survive as
    plain markdown in a mail client.
    """
    remaining = days_until(end_date, today)
    pretty_date = "{} ({})".format(end_date.isoformat(), end_date.strftime("%a"))
    if remaining == 1:
        pretty_date += " — tomorrow"

    number = issue.get("number")
    ticket = "#{}".format(number) if number else "this ticket"
    owners = owners_of(issue)

    lines = [
        marker_for(end_date),
        "## ⏳ {}".format(headline_for(remaining)),
        "",
        "| Ticket | End date | Days left | Owner |",
        "| :--- | :--- | :---: | :--- |",
        "| {} | **{}** | **{}** | {} |".format(ticket, pretty_date, remaining, owners or "—"),
        "",
    ]

    if assignees:
        lines.append(
            "{} — is this still on track?".format(" ".join("**@" + a + "**" for a in assignees))
        )
    else:
        lines.append("**Unassigned** — no one is currently on this ticket.")

    lines += [
        "",
        "If the date has moved, edit the `**Schedule:**` line in the issue body — "
        "that line is what this reminder reads. Closing the issue stops the reminders.",
        "",
        "<sub>Automated by [`due-soon-reminder`]({}) · "
        "[project board]({})</sub>".format(WORKFLOW_URL, BOARD_URL),
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# GitHub REST
# --------------------------------------------------------------------------
class GitHub:
    def __init__(self, token, repo, api=None):
        self.token = token
        self.repo = repo
        self.api = (api or "https://api.github.com").rstrip("/")

    def _request(self, method, path, payload=None):
        url = path if path.startswith("http") else "{}{}".format(self.api, path)
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "disasters-tracking-due-soon-reminder")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode() or "null"), resp.headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise SystemExit(
                "GitHub API {} {} failed: {} {}\n{}".format(
                    method, url, exc.code, exc.reason, detail
                )
            )

    def paginate(self, path):
        out = []
        url = "{}{}".format(self.api, path)
        while url:
            page, headers = self._request("GET", url)
            out.extend(page or [])
            url = _next_link(headers.get("Link"))
        return out

    def open_issues(self):
        issues = self.paginate("/repos/{}/issues?state=open&per_page=100".format(self.repo))
        return [i for i in issues if "pull_request" not in i]

    def issue(self, number):
        data, _ = self._request("GET", "/repos/{}/issues/{}".format(self.repo, number))
        return data

    def comments(self, number):
        return self.paginate(
            "/repos/{}/issues/{}/comments?per_page=100".format(self.repo, number)
        )

    def comment(self, number, body):
        self._request(
            "POST", "/repos/{}/issues/{}/comments".format(self.repo, number), {"body": body}
        )


def _next_link(link_header):
    """Extract rel="next" from a Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        if 'rel="next"' in section[1]:
            return section[0].strip().strip("<>")
    return None


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    ap.add_argument("--lead-days", type=int, default=int(os.environ.get("LEAD_DAYS", "3")))
    ap.add_argument(
        "--label",
        default=os.environ.get("REQUIRED_LABEL", "smartsheet"),
        help="only remind on issues carrying this label",
    )
    ap.add_argument(
        "--today",
        default=os.environ.get("TODAY", ""),
        help="override today's date (YYYY-MM-DD) -- for testing",
    )
    ap.add_argument(
        "--issue",
        type=int,
        default=None,
        help="only consider this issue number -- for testing",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
        help="print what would be posted, post nothing",
    )
    args = ap.parse_args(argv)

    if not args.repo:
        raise SystemExit("--repo (or GITHUB_REPOSITORY) is required")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    if args.lead_days < 0:
        raise SystemExit("--lead-days must be >= 0")

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    gh = GitHub(token, args.repo)

    issues = [gh.issue(args.issue)] if args.issue else gh.open_issues()
    print(
        "checked {} open issue(s) labelled '{}' against {} (lead {}d)".format(
            len(issues), args.label, today, args.lead_days
        )
    )

    posted = skipped = 0
    for issue in issues:
        number = issue["number"]
        if not has_label(issue, args.label):
            continue
        end_date = parse_end_date(issue.get("body"))
        if end_date is None:
            continue
        if not is_due_soon(end_date, today, args.lead_days):
            continue
        if already_reminded(gh.comments(number), end_date):
            print("  #{} ends {} -- already reminded, skipping".format(number, end_date))
            skipped += 1
            continue

        # Reminder goes to the individual doing the work.
        assignees = [a["login"] for a in issue.get("assignees") or []]
        body = render_comment(issue, end_date, today, assignees)
        if args.dry_run:
            print("  #{} ends {} -- DRY RUN, would post:".format(number, end_date))
            print("    " + body.replace("\n", "\n    "))
        else:
            gh.comment(number, body)
            print(
                "  #{} ends {} ({}d) -- commented".format(
                    number, end_date, days_until(end_date, today)
                )
            )
        posted += 1

    print("done: {} reminder(s) {}, {} already reminded".format(
        posted, "planned (dry run)" if args.dry_run else "posted", skipped
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
