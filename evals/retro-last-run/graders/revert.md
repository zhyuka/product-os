---
# The new report recommends reverting upgrade 1: its mechanism didn't work and it loads every session.
type: regex
weight: 2
target: { source: file, path: reports/retro.md }
flags: i
pattern: 'revert[^#]{0,300}?(database|CLAUDE\.md|-1\b|\ba1\b)|(database|CLAUDE\.md|-1\b|\ba1\b)[^#]{0,600}?revert'
---
