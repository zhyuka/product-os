---
name: recall
description: "Have we seen this before? One search over every session log here, git, notes and memory. Use before calling anything new, before asking the user, before filing, and for 'did we ever', 'what did we decide', 'search the logs'."
---

# Recall: search everything this workspace remembers

`recall.py` is the one search that covers every log copy and every outside record in one pass; a
grep of one folder is a partial answer. `--help` is the spec for every flag and lists the sources
this copy has.

```
product-os recall "<concept>" ["<concept>" ...]
```

Sources that read a remote service (design comments, a tracker) run only when configured in
`product-os.json`, and need their token in the environment (`FIGMA_TOKEN`, `ADO_PAT`); without it
that source prints DID NOT RUN. A full search can take a minute or two,
so background it when the next step doesn't depend on it.

Before answering on a topic, run `--brief "<topic>"` first. It returns the user's own words on it
from the request ledger, the live sessions working on it with their plans, and matching earlier
work. Its NARROWED line names what it left out, so run the full search when that could hold the
answer.

## Query

Each argument is one concept, and all concepts must match the same record. Inside a concept, `|`
separates alternatives. Give every name the thing has had (`"mobile card|MobileCard|browse card"`),
plus ids: a design node or comment id, a work-item number, or a URL. Use few concepts: two that
never share a record print as SPLIT, so search each alone.

| flag | use |
|---|---|
| `--source logs,git` | narrow to some sources |
| `--since <date>` | only records on or after it (UTC unless it ends in Z or an offset) |
| `--before <time>` | "could we have known then": only records before it |
| `--max N` | how many sessions and records to print |
| `--out FILE` | also write the full, uncapped report to a file |
| `--last /<command>` | every invocation of a command or skill, and the logs since the last one |
| `--selftest` | run the tool's own planted-case test |

## Read the answer

- Exit 0 is hits; 1 is every source ran and nothing matched; 2 is a source DID NOT RUN, so its zero
  clears nothing. Name that source when you report.
- Quote COVERAGE (copies scanned of copies found, folders not searched) with the answer.
- `near` and `fuzzy` hits are leads, not matches, and an earlier recall run is not evidence. Open
  the record a hit names before quoting it.
- `--before` cannot cut notes or memory: a file has no history, so each is searched as it is today.
- Not covered: Downloads, mail, chat apps, browser history, anything outside the configured
  folders. If the answer could live there, say so instead of "never discussed".
- Never extract a log to read around a redaction. After changing recall.py, run `--selftest` and
  quote it.
