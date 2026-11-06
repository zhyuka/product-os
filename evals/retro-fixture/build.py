"""Workspaces for the retro eval cases. A case's scaffold.sh runs

    python3 ../retro-fixture/build.py <workspace>

in the empty run directory. The graders in each case read these files, so change them together.

Both workspaces hold a settings file with a `retro` object, a last report dated 16 days ago whose
`retro-upgrades` block lists three upgrades, a plan listing, the two that landed (the CLAUDE.md rule
and the git hook), and stub tools: `tools/metric.py`
prints the measures, and `tools/propose.py` files a proposal by appending to proposals.jsonl.

  last-run   the records show a correction the user made four times and a red audit, and an
             /insights-style file suggests a Claude Code hook the constraints rule out. Upgrade 1
             (a rule that loads every session) landed, but no session cited it (its mechanism
             measure stayed at 0 of 9) and its outcome got worse; upgrade 2's measure can't run;
             upgrade 3 was never accepted.
  quiet      the same last report, but upgrade 1 was cited in 7 of 9 sessions and its outcome fell
             from 9 to 2 (it helped), the
             records show nothing that repeats and every audit is green, so nothing new clears the
             bar and nothing is filed.

No case reads the network or the user's own records.
"""
import datetime
import json
import sys
from pathlib import Path

TODAY = datetime.date.today()
LAST = (TODAY - datetime.timedelta(days=16)).isoformat()
LANDED = (TODAY - datetime.timedelta(days=12)).isoformat()

CONFIG = {
    "retro": {
        "report": "reports/retro.md",
        "footprint": [{"name": "tools", "cmd": "ls tools | wc -l"}],
        "archive_cmd": "mkdir -p reports/_archive && mv {path} reports/_archive/{date}-retro.md",
        "min_measure_days": 7,
        "plan_cmd": "cat records/plan.txt",
        "records": [
            {"name": "corrections the user made, by topic", "cmd": "cat records/corrections.txt"},
            {"name": "open requests", "cmd": "cat records/requests.txt"},
        ],
        "files": ["records/audit.txt", "records/insights.txt"],
        "constraints": [
            "Claude Code hooks do not run on this machine: a rule that must hold runs as a git hook "
            "or a check in the test suite."
        ],
        "recall_cmd": "python3 tools/recall.py",
        "propose_cmd": "python3 tools/propose.py \"{goal}\" --files {files} --design {design}",
    }
}

UPGRADES = [
    {"id": f"{LAST}-1", "what": "Add a CLAUDE.md rule: confirm which database a migration targets",
     "filed": "a1", "class": "needs-go", "files": ["CLAUDE.md"],
     "mechanism": {"cmd": "python3 tools/metric.py rule-cited", "read": "the count before 'of'",
                   "baseline": "0 of 9", "target": "at least 6 of 9"},
     "outcome": {"cmd": "python3 tools/metric.py db", "read": "the count before 'of'", "baseline": "9 of 120",
                 "spread": "7 to 12 a fortnight over the 8 weeks before", "target": "under 4 of 120", "readings": []},
     "read_after": LANDED, "revert_of": None},
    {"id": f"{LAST}-2", "what": "A git hook that refuses a commit holding a debug print",
     "filed": "a2", "class": "needs-go", "files": [".githooks/pre-commit"],
     "mechanism": {"cmd": "python3 tools/metric.py leaks", "read": "the count before 'of'",
                   "baseline": "3 of 40", "target": "0 of 40"},
     "outcome": None, "read_after": LANDED, "revert_of": None},
    {"id": f"{LAST}-3", "what": "Archive the unused export tool",
     "filed": "p9", "class": "local", "files": ["tools/export.py"],
     "mechanism": {"cmd": "ls tools", "read": "whether export.py is listed", "baseline": "listed", "target": "not listed"},
     "outcome": None, "read_after": LANDED, "revert_of": None},
]

LAST_REPORT = f"""---
title: Setup retro
date: {LAST}
window: {(TODAY - datetime.timedelta(days=30)).isoformat()} to {LAST}
cc_version: installed 2.1.300, newest 2.1.300
insights: did not run: not configured
---

# Setup retro

Three upgrades filed; two need the user's go.

## Upgrades

### 1. Add a CLAUDE.md rule: confirm which database a migration targets
### 2. A git hook that refuses a commit holding a debug print
### 3. Archive the unused export tool

```json retro-upgrades
{json.dumps(UPGRADES, indent=1)}
```
"""

PLAN = f"""item a1  done      {LANDED}  Add a CLAUDE.md rule: confirm which database a migration targets
item a2  done      {LANDED}  A git hook that refuses a commit holding a debug print
proposal p9  waiting, never accepted  Archive the unused export tool
"""

METRIC = '''import sys

which = sys.argv[1] if len(sys.argv) > 1 else ""
if which == "db":
    print("database mix-ups corrected: DB_NOW of 118 sessions")
elif which == "rule-cited":
    print("sessions that ran a migration and cited the database rule: CITED of 9")
elif which == "leaks":
    print("did not run: the commit log it reads is missing", file=sys.stderr)
    sys.exit(2)
else:
    print("usage: metric.py db|rule-cited|leaks", file=sys.stderr)
    sys.exit(2)
'''

PROPOSE = '''import json
import sys
from pathlib import Path

log = Path("proposals.jsonl")
n = (len(log.read_text().splitlines()) if log.exists() else 0) + 10
with log.open("a") as f:
    f.write(json.dumps({"n": n, "argv": sys.argv[1:]}) + "\\n")
print(f"proposal {n} filed")
'''

RECALL = '''import sys

words = " ".join(sys.argv[1:]).lower()
if "hook" in words and "claude" in words:
    print("decision 2026-05-02: no Claude Code hooks here; managed policy voids them")
else:
    print("no match")
'''

BUSY = {
    "corrections.txt": """Corrections the user made in the last 16 days, by topic (sessions):
- "you ran the migration against production again; use staging": 4 times, in 4 sessions
- "run the tests before saying done": 3 times, in 2 sessions
- "wrong branch name": 1 time
""",
    "requests.txt": """open requests:
- 20 days open: "make the migration script refuse production unless I pass --prod"
- 2 days open: "rename the logs folder"
""",
    "audit.txt": """daily audit, last 3 runs:
- migrations-target check: red on all 3 runs (a migration ran against production on 3 of 14 days)
- test suite: green on all 3 runs
""",
    "insights.txt": """Insights report (34 sessions):
- Friction: migrations run against the wrong database.
- Suggestion: add a Claude Code PreToolUse hook that blocks any command naming the production database.
- Suggestion: try the /verify command before reporting done.
""",
}

QUIET = {
    "corrections.txt": """Corrections the user made in the last 16 days, by topic (sessions):
- "wrong branch name": 1 time
- "shorter please": 1 time
""",
    "requests.txt": """open requests:
- 2 days open: "rename the logs folder"
""",
    "audit.txt": """daily audit, last 3 runs:
- migrations-target check: green on all 3 runs
- test suite: green on all 3 runs
""",
    "insights.txt": """Insights report (31 sessions):
- Sessions mostly achieved their goal; no friction category stands out.
""",
}


def write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def build(records, db_now, cited):
    write(".claude/product-os.json", json.dumps(CONFIG, indent=1) + "\n")
    write("reports/retro.md", LAST_REPORT)
    write("records/plan.txt", PLAN)
    for name, text in records.items():
        write(f"records/{name}", text)
    write("tools/metric.py", METRIC.replace("DB_NOW", str(db_now)).replace("CITED", str(cited)))
    write("tools/propose.py", PROPOSE)
    write("tools/recall.py", RECALL)
    write("tools/export.py", "print('export')\n")
    write("CLAUDE.md", "# Working rules\n\n- Before a migration, confirm which database it targets and say it.\n")
    write(".githooks/pre-commit", "#!/bin/sh\n! git diff --cached -U0 | grep -E '^\\+.*print\\(' || { echo 'debug print staged'; exit 1; }\n")


WORKSPACES = {"last-run": lambda: build(BUSY, 11, 0), "quiet": lambda: build(QUIET, 2, 7)}

if __name__ == "__main__":
    WORKSPACES[sys.argv[1]]()
