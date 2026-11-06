# Report format

````markdown
---
title: Setup retro
date: YYYY-MM-DD
window: YYYY-MM-DD to YYYY-MM-DD
cc_version: installed X.Y.Z, newest X.Y.Z
insights: ran, N sessions analysed (M total) | did not run: <why>
run: <session id>
---

# Setup retro

<One paragraph: what to do next, in plain words. The upgrades filed, the reverts and drops
recommended, and what needs the user's go.>

**Footprint**: <name> N (last run M), ... Each number names its command in `footprint`.

## Last run's upgrades

| Upgrade | Filed as | Landed | Measure | Kind | Baseline | Now | Target | Verdict |
|---|---|---|---|---|---|---|---|---|

Kind is mechanism or outcome, one row each. The verdict column holds one of: helped, no change,
worse, not landed, too early, did not run, in those words. Say which ones you recommend reverting,
and why.

## What the records show

Each finding: one line, its number, the command or file it came from.

## What changed outside

### Claude Code releases (versions A to B)
Only the items that bear on a finding or replace something the setup built.

### Practice
Each source: [title](url) (its date): one-line claim. Measured, or a vendor's claim.

### Watched, not proposed
Ideas with a source that answer no finding yet.

## Upgrades

### 1. <what changes>
- **Evidence**: the inward number and its command; the outside source if any.
- **Cost**: hours and any spend, and where the estimate comes from.
- **Replaces**: what it retires, or why nothing can go, and its effect on the footprint.
- **Mechanism measure**: the command, baseline now, target, read after <date>.
- **Outcome measure**: the command, baseline now, the spread of the weeks before, target; or how it
  was judged before landing (a replay, a planted case).
- **Challenger**: its verdict in one line, and what changed because of it.
- **Filed**: proposal number; local and reversible, or needs the user's go.

## Waiting proposals

Each waiting proposal a new candidate beats, or that no finding supports any more: its number and
why to drop it.

## The loop

| Run | Proposed | Accepted | Landed | Kept | Footprint | Loop outcome |
|---|---|---|---|---|---|---|

## Did not run

Each part that didn't run, and why.

```json retro-upgrades
[
  {
    "id": "YYYY-MM-DD-1",
    "what": "one line",
    "filed": "proposal or item id",
    "class": "local | needs-go",
    "files": ["path"],
    "mechanism": {"cmd": "shell command that prints the number", "read": "what in its output is the number",
                  "baseline": "the number now", "target": "the number that means it works"},
    "outcome": {"cmd": "...", "read": "...", "baseline": "...", "spread": "the range over the weeks before",
                "target": "...", "readings": []},
    "read_after": "YYYY-MM-DD",
    "revert_of": null
  }
]
```
````

The next run reads only the `retro-upgrades` block to find what to measure, so keep its fields
exact. `outcome` may be null. Each run appends its outcome reading to `readings`, carried forward
from the last block, so two readings in a row can be compared. An upgrade that was not filed still
goes in the block, with `"filed": null`, and so does one carried from an earlier run that hasn't
landed.
