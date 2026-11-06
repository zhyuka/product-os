---
type: llm
weight: 1
focus: { source: file, path: intent/claim-status/intent.md }
---
An intent says what is wanted, why and under which constraints. It holds no solution.

PASS if intent.md has no implementation plan: no list of files or functions to change, no data model, no API design and no task list.
FAIL if it contains any of those, or the file is missing.
