---
# go hands off and does no building itself, and site-pages stops at once.
type: regex
target: trace
match: not_contains
pattern: '"name":\s*"(?:Write|Edit|MultiEdit|NotebookEdit)"'
---
