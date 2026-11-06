# retro config keys

All keys sit under a top-level `retro` object in the config file the caller names. Paths may start
with `~`. A command is a shell string run from the user's working folder; `{name}` fields are filled
in by the run.

| Key | Used in | What it is |
|---|---|---|
| `footprint` | 1 | list of `{"name", "cmd"}`: commands that each print one number for the setup's size (words loaded at startup, tool lines, scheduled jobs, waiting proposals) |
| `report` | all | the live report's path. One stable name; the date goes in its frontmatter |
| `archive_cmd` | 5 | moves the previous report aside, with `{path}`, `{date}` (its frontmatter date) and `{why}`. Unset: move it to `_archive/<date>-<name>` beside the report |
| `min_measure_days` | 1 | how long an upgrade must have been in place before its mechanism measure decides keep or revert (default 7) |
| `plan_cmd` | 1, 4 | prints the state of filed items and the proposals still waiting |
| `insights` | 2 | the command that runs `/insights` headless, such as `claude -p "/insights" --output-format json`; unset skips it |
| `records` | 2 | list of `{"name", "cmd"}`: commands whose output is inward evidence |
| `files` | 2 | list of files to read as inward evidence |
| `constraints` | 2, 4 | list of things this setup forbids or can't do, to weigh outside suggestions against |
| `topics` | 3 | extra standing research topics |
| `blocked_marker`, `reader_proxy` | 3 | text that marks a blocked page on this network, and the prefix that reads one anyway |
| `measures_dir` | 4 | folder for the scripts a run writes when no existing tool prints a measure; the next run reruns them |
| `loop_outcome` | the loop | `{"name", "cmd"}`: the number the whole loop is meant to move, tracked run by run |
| `effort_cmd` | 4 | prints what past changes cost in hours |
| `recall_cmd` | 4 | searches the record; the run appends the concepts as quoted arguments |
| `plans` | 4 | plan files whose in-flight moves an upgrade must not collide with |
| `propose_cmd` | 5 | files one upgrade, with `{goal}`, `{files}` (comma-separated) and `{design}`; prints its number |
| `coordinator_cmd` | 5 | prints who approves and builds filed upgrades; its first `local_` id is the session to message. Read it right before sending |
| `never_call` | all | tool-name patterns the run never calls |
