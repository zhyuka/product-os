---
# Upgrade 3 was never accepted, so it reads "not landed".
type: regex
target: { source: file, path: reports/retro.md }
flags: i
pattern: '(export tool|-3\b|\bp9\b)[^#]{0,600}?not landed'
---
