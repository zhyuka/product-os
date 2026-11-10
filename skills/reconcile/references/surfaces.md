# reconcile: the project's own surfaces (`rebase.surfaces`)

The plugin's tools cover what every project has: the last pass, transcripts, the tracker, session
logs and the working folder. Anything else a project checks on each pass is a surface in its
`.claude/product-os.json`, or in your own `~/.claude/product-os.json`:

```json
{"rebase": {"surfaces": [
  {"name": "call captures", "cmd": "<cleans each new raw capture into a file beside it, prints each new file>", "pass": "catch-up"},
  {"name": "design board", "cmd": "<prints what changed on the board since $RECONCILE_SINCE>", "pass": "full"},
  {"name": "shared component repo", "cmd": "git -C <path> log --since=\"$RECONCILE_SINCE\" --oneline", "pass": "full"}
]}}
```

- `name` is the label in the report. `cmd` runs in the project folder. `pass` is `catch-up` (every
  pass, §1) or `full` (a tripwire, §2); unset means `catch-up`.
- Run each `cmd` as written, with `RECONCILE_SINCE` set in its environment to the last pass's date
  (`YYYY-MM-DD`). Don't edit the command to make it run: a changed command is a new one, and it needs
  accepting again.
- Exit 0: nothing changed. Exit 1: each line it prints is a candidate, checked in §4 like any other.
  Any other exit, or no exit within 5 minutes: "did not run", with the first line of its error.
- A surface reads, or adds files beside what it reads, such as a cleaned capture next to its raw
  one. A step that moves, edits or deletes belongs in the approved list (§9), not in a surface.
- A surface behind a sign-in, such as a chat app: start one signed-in browser for the pass with
  `signed_in_browser.py serve <url>` in the background. It prints `SERVING <address>` once single
  sign-on finishes on its own; read it with `chromium.connect_over_cdp("<address>")`, never
  `browser.close()`, and run `signed_in_browser.py stop --port <its port>` when the pass is done. If
  it ends with NEEDS SIGN-IN, ask once: sign in through one `--headed` run, or skip. A skipped surface is "did not run", never skipped silently.

The whole list is one command setting. From the project's file it counts only once the person has
read it there and run `product-os kit_config accept rebase.surfaces` on this machine, and again after
any entry changes. Until then `kit_config.py` marks it NOT ACCEPTED and the pass runs none of it.
The same list in your own file always counts.
