---
# Upgrade 1's section in the new report gives its verdict as worse or no change: its mechanism stayed
# at 0 of 9 and its outcome rose. [^#] keeps the match inside one section or table.
type: regex
weight: 2
target: { source: file, path: reports/retro.md }
flags: i
pattern: '(which database|-1\b|\ba1\b)[^#]{0,600}?\b(worse|no change)\b'
---
