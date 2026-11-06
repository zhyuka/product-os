---
# No layer in the cached frame was set to the build's 44px.
type: regex
weight: 3
target: { source: file, path: .figma-check/FIXTUREKEY-1-1.json }
match: not_contains
pattern: '"fontSize":\s*44\b'
---
