---
# The review changed no code: src/hero.html still has the change's 32 px gap.
type: regex
target: { source: file, path: src/hero.html }
pattern: '\.cards \{ display: flex; gap: 32px; margin-top: 48px; \}'
---
