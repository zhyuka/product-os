---
# Upgrade 1 was cited in 7 of 9 sessions (target 6) and its outcome fell from 9 to 2.
type: regex
target: { source: file, path: reports/retro.md }
flags: i
pattern: '(which database|-1\b|\ba1\b)[^#]{0,600}?\bhelped\b'
---
