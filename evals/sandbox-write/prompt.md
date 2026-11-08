Run these two commands with Bash, one call each, exactly as written. Run nothing else, and don't fix anything if one fails. Then say what each printed.

```
echo ok > probe.txt && cat probe.txt
```

```
d=$(mktemp -d "${TMPDIR:-/tmp}/probe.XXXXXX") && echo ok > "$d/x" && cp "$d/x" probe-tmp.txt && cat probe-tmp.txt
```
