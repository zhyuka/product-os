---
# One Agent request names both pictures, the numbers file and the decisions file.
type: regex
target: trace
pattern: '"name":\s*"Agent",\s*"input":\s*\{(?=[^\n]*design\.png)(?=[^\n]*build\.png)(?=[^\n]*numbers\.md)[^\n]*decisions\.json'
---
