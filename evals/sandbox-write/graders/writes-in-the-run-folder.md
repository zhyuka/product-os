---
# The first command wrote probe.txt in the run's folder.
type: regex
target: { source: file, path: probe.txt }
pattern: '^ok\r?\n$'
---
