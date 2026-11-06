---
# Nothing cleared the bar, so propose_cmd never ran and proposals.jsonl was never created.
type: regex
weight: 2
target: files
match: not_contains
pattern: 'proposals\.jsonl'
---
