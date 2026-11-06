---
type: llm
weight: 1
focus: last_message
---
intent/claim-status/intent.md has "Status: draft". The spec skill should stop and ask before writing a spec from an intent nobody has accepted.

PASS if the reply says the intent is a draft or not accepted, and asks whether to go on or to get it accepted first.
FAIL if the reply presents a finished spec, doesn't mention the intent's status, or is empty.
