---
# No file tool or shell redirect wrote into the check's cache.
type: regex
weight: 2
target: trace
match: not_contains
pattern: '"name":\s*"(?:Edit|Write|MultiEdit)",\s*"input":\s*\{[^\n]*?"file_path":\s*"[^"]*\.figma-check/'
---
