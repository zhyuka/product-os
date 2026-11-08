# Register the design check with product-os check

`figma_check.py` becomes one of the project's own checks, so `product-os check` runs it on every
push and in CI, `unproven` stops it when someone edits the script, its cached design values or its
cases, and `removed` (with `--base`) fails a change that drops it or one of its cases. The format of
the checks file, and `prove`, `accept`, `unproven` and `removed`, are in the plugin's
`docs/checks.md`, "A project's own checks".

## 1. Put the check and its design values in the project

- Copy `scripts/figma_check.py` from this skill's folder (the base directory shown when the skill
  loaded) to `checks/figma_check.py`, unchanged. The fingerprint covers the files a check's
  command names, so the copy in the project is what makes an edit to the check show as `unproven`.
- Run the check once live with `--cache .figma-check/<section>`, so the frames it read are saved in
  that folder. Commit the folder. Those files are the design values the check compares against,
  and the command names the folder, so an edit to them also shows as `unproven`. A folder per
  section keeps a design refresh on one section from unproving the others.

## 2. Make the cases

Under `checks/cases/figma-check-<section>/`:

- `good/index.html`: the section as built and passing, saved so it loads from disk.
- `bad/index.html`: the same file with one planted miss the check has to catch. Use a miss the
  build really had in step 4 of the skill, such as the heading at the wrong size or
  `-webkit-font-smoothing: antialiased` taken off `html`. Change nothing else.

The check opens the target and the cases from disk. A page whose links start with `/` loads no
styles from a file, so save each case with its styles inline or its links relative. A case that
loads without its styles fails both ways and proves nothing.

## 3. The entry

Write it to `checks/figma-check-<section>.json`:

```json
{
  "checks": [
    {
      "name": "figma-check-<section>",
      "run": ["{python}", "checks/figma_check.py", "{target}", "--file", "<file key>",
              "--frame", "<desktop id>", "--frame", "<phone id>",
              "--root", "<css selector for the section>", "--cache", ".figma-check/<section>"],
      "target": "<the built page, a file or a folder holding index.html>",
      "bad": "checks/cases/figma-check-<section>/bad",
      "good": "checks/cases/figma-check-<section>/good",
      "timeout": 300
    }
  ]
}
```

Pass every frame the section has, the same list as the live run. Leave out `--root` when the page
is the section. `{python}` is the Python that runs product-os, so it needs Playwright and Chromium;
without them the good case fails and the check isn't proven.

## 4. Prove it, then list it

```
"<plugin root>/bin/product-os" prove --check checks/figma-check-<section>.json
```

`<plugin root>` is the folder above `skills/` in this file's path. Run it in the session's working
folder with no `cd` first. It has to print `1 of 1` bad cases caught and `1 of 1` good cases passed. If it doesn't, fix the
case, never the check or its cache. Then add the entry, unchanged, to the `checks` list of
`.claude/product-os-checks.json`. That write is the person's to approve; if it's refused, show them
the file as it should read. On their machine it runs once they accept it (`product-os accept
<name>`), on their yes.

## What a proof run looked like

On a scratch project made from `scripts/selftest/`, with the selftest page as the good case and a
copy whose heading is 44px instead of 48px as the bad case, the entry above was proven 1 of 1 both
ways and `check --run-listed` passed. Changing the heading's size in the cached frame, and
separately loosening a tolerance in `checks/figma_check.py`, each turned the row to
`unproven ... the check changed since it was proven, so it didn't run`; restoring the file turned
it back to `pass`.

## When the design changes

New design values mean a new cache. Refreshing it (delete `.figma-check/<section>/` and run the
check live) is the person's call, never a way to get a pass: it leaves the check `unproven` until
it's proven again on the same cases and accepted again.
