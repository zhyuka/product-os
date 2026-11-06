---
# Upgrade 2's measure exits 2, so its verdict is "did not run", never "no change".
type: regex
weight: 2
target: { source: file, path: reports/retro.md }
flags: i
pattern: '(debug print|-2\b|\ba2\b)[^#]{0,600}?did not run'
---
