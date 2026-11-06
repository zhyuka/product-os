---
# The reviewer wasn't told the builder's account: no Agent request says the gap was fixed, that the
# section was rebuilt or that it matches now.
type: regex
weight: 2
target: trace
match: not_contains
pattern: '"name":\s*"Agent",\s*"input":\s*\{[^\n]*(fixed|rebuilt|matches the design now|matches now)'
---
