---
# The second command wrote a file in a folder mktemp made under $TMPDIR, as the
# review skill makes one, and copied it here.
type: regex
target: { source: file, path: probe-tmp.txt }
pattern: '^ok\r?\n$'
---
