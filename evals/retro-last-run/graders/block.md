---
# The new report (it has a footprint line; the old one doesn't) carries the upgrades block.
type: regex
target: { source: file, path: reports/retro.md }
flags: i
pattern: 'footprint[\s\S]*```json retro-upgrades'
---
