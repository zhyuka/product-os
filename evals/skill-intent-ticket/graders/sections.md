---
# The playbook's intent template, its section names in order.
type: regex
target:
  source: file
  path: intent/claim-status/intent.md
pattern: '## Problem[\s\S]*## Proposed outcome[\s\S]*## Affected users and systems[\s\S]*## Constraints[\s\S]*## Open questions'
---
