# triage: the project's decision sources, and the tracker's recycle bin

## `triage.sources`

A project lists anything else that holds pending decisions in its `.claude/product-os.json`, or you
in your own `~/.claude/product-os.json`:

```json
{"triage": {"sources": [
  {"name": "review page", "cmd": "<prints the answers recorded on the review page, not yet applied>"},
  {"name": "design questions", "cmd": "<prints the open questions on the design board>"}
]}}
```

- `name` labels the list in step 2. `cmd` runs in the project folder, as written; a changed command
  is a new one and needs accepting again.
- It prints one line per item: `<id>  <what is pending>`. An item the person already decided
  elsewhere reads `<id>  decided: <the decision>  <where to apply it>`, and step 1 applies it without
  asking again. Indented lines under an item are its detail.
- Exit 0 with its list, empty when nothing is pending. Any other exit means it did not run: say so
  with the first line of its error, never "nothing pending".
- A source that reads the tracker reads it live, or from a cache it refuses past 30 minutes, as
  `ado_rest.py` does. A line that says its cache is older is treated as did not run.

The whole list is one command setting. From the project's file it counts only once the person has
read it there and run `product-os kit_config accept triage.sources` on this machine, and again after
any entry changes. Until then `kit_config.py` marks it NOT ACCEPTED and triage runs none of it. The
same list in your own file always counts.

## Moot tracker items go to the recycle bin

Azure DevOps keeps a deleted work item in its recycle bin, where it can be restored, unless the
delete destroys it. Never a raw REST call: it would skip the ask rule that makes every other tracker
write prompt. After the person's yes for that item:

1. `ado_write.py state <id> Removed`, which reads the state back.
2. `ado_rest.py pull`, then `ado_rest.py show <id>` for its rev now.
3. `ado_write.py delete <id>:<rev>`. It refuses an item not in Removed or at another rev, a test
   artifact (the API deletes those for good) and an item with a child not in Removed. It writes an
   undo file first and reads back that the item is gone and in the recycle bin. Anything but its
   confirmed line means the move didn't land: say so, and the item stays open.

`ado_write.py restore <id>` brings it back.

In the ledger file, a moot entry is marked `Status: moot` and stays in the file.
