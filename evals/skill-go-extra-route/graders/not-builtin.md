---
# The project's route wins over the built-in row it overlaps, so neither built-in build skill loads.
type: regex
target: trace
match: not_contains
pattern: '"name":\s*"Skill",\s*"input":\s*\{[^\n]*"skill":\s*"(?:product-os:)?(?:build-change|build-from-design)"'
---
