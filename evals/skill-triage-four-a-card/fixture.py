"""Workspace for skill-triage-four-a-card. scaffold.sh runs it in the empty run directory.

.claude/open-questions.md holds five open questions and nothing closed, one more than a card takes.
tracker-cache.json is a tracker export pulled three hours before the scaffold ran, well past
triage's 30-minute limit. The prompt hands that file over as the tracker's decisions. The graders
read both files, so change them together.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

LEDGER = """# Open questions

## Q-1: Does the export button show on mobile?
- Status: open
- Filed: 2026-10-20
- Surfaced: the export page build
- Why it matters: the mobile layout has room for two buttons, not three
- Depends on: product owner
- Affects: the export page at mobile width
- Evidence: spec.md:14 "export on every width" against notes/mobile.md:3 "no export on mobile"

## Q-2: Which date format do invoices use?
- Status: open
- Filed: 2026-10-22
- Surfaced: the invoice template change
- Why it matters: finance reads the day first, the default prints the month first
- Depends on: finance lead
- Affects: every invoice PDF
- Evidence: templates/invoice.html:9 prints MM/DD/YYYY; notes/finance.md:5 asks for DD/MM/YYYY

## Q-3: Do archived projects count toward the plan limit?
- Status: open
- Filed: 2026-10-27
- Surfaced: the billing limits story
- Why it matters: counting them blocks some users from creating a project
- Depends on: product owner
- Affects: the plan limit check
- Evidence: billing/limits.py:21 counts every project; pricing.md:12 says active projects

## Q-4: Does a guest see the team's shared folders?
- Status: open
- Filed: 2026-10-28
- Surfaced: the guest invite flow
- Why it matters: a guest who sees them can open files the team never shared with them
- Depends on: security lead
- Affects: the folder list for guest accounts
- Evidence: folders/list.py:40 returns every team folder; notes/guests.md:2 says invited folders only

## Q-5: Which time zone do reminder emails use?
- Status: open
- Filed: 2026-10-30
- Surfaced: the reminder scheduler change
- Why it matters: a reminder sent in the server's zone can land a day late for some users
- Depends on: product owner
- Affects: every reminder email
- Evidence: reminders/send.py:18 uses the server zone; notes/reminders.md:4 asks for each user's zone
"""

SPEC = "# Export\n\n" + "\n" * 11 + "Export on every width.\n"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    pulled = time.time() - 3 * 3600
    cache = {
        "pulled": int(pulled),
        "pulled_at": datetime.fromtimestamp(pulled, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": {
            "101": {"fields": {"System.WorkItemType": "Task", "System.State": "Active",
                               "System.Title": "Do we keep the legacy CSV export?",
                               "System.Tags": "decision"}},
            "102": {"fields": {"System.WorkItemType": "Task", "System.State": "Active",
                               "System.Title": "Who signs off the new onboarding copy?",
                               "System.Tags": "decision"}},
        },
    }
    write(".claude/open-questions.md", LEDGER)
    write("tracker-cache.json", json.dumps(cache, indent=1) + "\n")
    write("spec.md", SPEC)
    write("notes/mobile.md", "# Mobile\n\nNo export on mobile.\n")
    write("CLAUDE.md", "# Project\n\nThe open questions live in .claude/open-questions.md.\n")


if __name__ == "__main__":
    main()
