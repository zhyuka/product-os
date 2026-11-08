---
name: retro
description: "Every two weeks, improve how you work with Claude Code: read your own records (/insights, corrections, open requests, audits) and what changed outside (Claude Code releases, current practice for agent-built software), pick at most five upgrades with evidence, cost and a measure, file them for approval, and measure the last run's. Run it by hand as /product-os:retro, or have a scheduled task read and follow this file."
argument-hint: "[settings file]"
disable-model-invocation: true
---

# Retro: improve how you work with Claude Code, on a cycle

If you're reading this, the retro has started, from `/product-os:retro` or from a task that read
this file: carry it out here. Don't call the Skill tool for retro. That tool refuses a skill only a
person may start, and its refusal doesn't end a run that has already started.

A run ends with one report that does three things. It says whether the last run's upgrades are
working, each by its own measure. It names at most five new upgrades, each tied to a number in the
user's own records and, when the idea comes from outside, to a cited source. And it files each one
where the setup takes changes, so building it is someone's next step rather than a line in a file.

The loop also has to keep the setup from growing. Each report opens with the setup's footprint
against the last run, and a run whose upgrades would grow it needs a measured gain that pays for the
growth. Zero upgrades is a good result when nothing clears the bar, and dropping or retiring
something counts as an upgrade.

Every machine-specific value (paths, commands, who approves) comes from the `retro` object in the
settings, which `"${CLAUDE_PLUGIN_ROOT}/bin/product-os" kit_config` prints merged from the user's and
the project's `.claude/product-os.json`; a caller may name another file. Run it in the session's
working folder as it is, with no `cd` first. If the path before `/bin/product-os` still starts with
`$`, it wasn't filled in: put the folder above `skills/` in this skill's path in its place, and run
plain `product-os` only if no launcher is there. `references/config.md` lists
the keys. When a step needs a key the settings lack, say so in the report and skip that part rather
than guess a path. A command the listing marks NOT ACCEPTED came from the project's file and hasn't
been accepted on this machine. Skip its part, and name it and its accept line in the report: the
person runs that line after reading the command, so never run it yourself.

## Before you start

Read the settings, then the last report at `report`, including its `retro-upgrades` block. The
window runs from that report's `date` to now; with no last report, the last 14 days. The setup's own
rules apply. Ask before anything paid beyond this session (an API key, credits, an eval run), and
never call a tool `never_call` names.

The reading is long (a release window can hold hundreds of notes), so hand it to two read-only
subagents and keep this session for judging. One reads inward (step 2), one outward (step 3). Brief
each with absolute paths and the window, and ask for findings with their numbers and sources in at
most 1,500 words, each source that couldn't be read marked "did not run".

## 1. Footprint and the last run's upgrades

Run each command in `footprint` and set each number beside the last report's.

Each upgrade carries two measures:
- **Mechanism**: did it do its job? It fired, it was used, it caught its planted case, what it costs
  in time. This decides keep or revert, once it has been in place `min_measure_days`.
- **Outcome**: did the number it was meant to move, move? Outcome numbers are noisy over two weeks
  and many changes land at once, so read them as a trend across runs, against the spread of the
  weeks before.

For each upgrade in the last report's block, find whether it landed: its item is done in what
`plan_cmd` prints, or its commit is in. Then run its measures. The verdict is one of helped, no
change, worse, not landed, too early, or did not run, written in those words, since the loop's counts
across runs read them; a measure that can't run is "did not run", never "no change".
Recommend reverting an upgrade whose mechanism didn't work, or whose outcome got worse on two
readings in a row, when it costs something to keep: a rule that loads every session, a gate that
slows each commit, a scheduled job. Reverts are filed as in step 5 and don't count toward the five.

## 2. Look inward

Run `/insights` headless with the `insights` command (unset means skip it), from a scratch folder,
in the background. It writes an HTML report and prints its path; read it with the tags stripped, and
note the session count its header gives. It analyses only sessions it hasn't seen before, so it
describes recent work plus its own cache. If it fails, say so and rely on the records.

Run each command in `records` and read each file in `files`. These are the evidence, and `/insights`
is a lead: a friction it names counts once a record confirms it with a number. Weigh each of its
suggestions against `constraints` before it goes further, since it doesn't know what this setup
forbids.

Look for these, strongest first:
- a correction the user had to make more than once;
- pushes for more depth, research or proof;
- requests open longer than one cycle;
- an audit red on two runs in a row that nobody acted on;
- a skill or check that didn't load or fire where it should;
- where time went: slow tools, waiting, reruns;
- what the setup carries that nothing uses, and filed proposals that have waited longer than a
  cycle, which are candidates to drop.

Carry only findings about the work and the setup. Leave personal topics out of the report even when
`/insights` mentions them.

## 3. Look outward

Releases: run `python3 "${CLAUDE_SKILL_DIR}/scripts/releases.py" --since <window
start>`; exit 2 means it couldn't read a source, so releases did not run. Keep the items that bear on
a finding from step 2, or that replace something the setup built for itself; a built-in that retires
a home-made tool is a strong upgrade because it removes code. Note the installed version
(`claude --version`) against the newest.

Practice: what changed in the window in building software with agents: specs in and checked code
out, agents in gated loops, reviewers that can't edit, evals, background and scheduled agents, plus
any standing `topics`. Search for vendor engineering posts and docs (Anthropic's first), practitioner
write-ups with numbers, and papers. For each source keep its URL, its date, a one-line claim, and
whether it measured something or is a vendor's claim. Read the page itself and check the text is
the real page: when it holds `blocked_marker`, read it through `reader_proxy`.

An outside idea becomes an upgrade only when it answers an inward finding or replaces something that
costs the user time now. The rest go in the report as watched, with their source.

## 4. Pick at most five

Rank the new candidates together with the proposals already waiting (`plan_cmd`): a waiting one that
a new candidate beats, or that no finding supports any more, is recommended for dropping.

For each candidate, write what changes; its evidence (the inward number with the command that gave
it, and any outside source); its cost (hours, from `effort_cmd` when set, and any spend); what it
replaces or removes, and its effect on the footprint; and its measures, each a command that prints a
number, with the baseline you ran now, the target, and when to read it. A measure no existing tool
prints goes in a script in `measures_dir`, one subcommand each, so the next run can rerun it. Judge
an outcome before the upgrade lands where you can, on a replay of past corrections or a planted
case, rather than waiting on the live number. Then cut:
- The bar is a finding that repeated in the window (a correction made twice or more, an audit red on
  two runs in a row, a request open past one cycle) or a measured cost in time. A single correction
  or a fresh request doesn't clear it, and an ordinary request is the user's work, not an upgrade.
- Drop one below the bar, with no mechanism measure, or with no baseline run now.
- Prefer removing or replacing over adding. One that grows the footprint names what it retires, or
  carries a measured gain that pays for the growth.
- Search the record with `recall_cmd` for each. Skip one the user already rejected or parked unless
  new evidence changes the case, and say which.
- No two upgrades touch the same files. One that touches files a plan in `plans` is moving goes to
  that plan's owner as an amendment, not as an item of its own.
- Rank by expected gain on the measured number against cost, and keep at most five.

## 5. Write the report, then file

Move the previous report aside with `archive_cmd`, so the live file keeps one name. Write the new
one at `report` in the format in `references/report.md`: frontmatter with `date`, `window`,
`cc_version` and how `/insights` ran, the footprint line, the sections, and the `retro-upgrades`
block, each upgrade with an id. Every number names the command that produced it, and every outside
claim links its source.

For each kept upgrade (and each revert from step 1), spawn a fresh `challenger` agent with only the
problem, the setup's hard rules and the recommendation, never your reasoning, and name in its prompt
every file the upgrade would change and the report's path. Fold in its verdict and record what
changed because of it. If no challenger can run, file the upgrade anyway and mark it unchallenged, so
the approval step sees that.

An upgrade that answers a repeated correction or a defect that got through is a miss: say in its
goal that it is built with `/product-os:miss-to-check`, so the check is proven on a planted bad case
before it counts.

File each with `propose_cmd`, with its id in the goal and the report as its design, and write the
number it returns into the report and its block. Class each one:
- **Local and reversible**: a new read-only tool, a report, a check that only reads, a fix inside
  one tool. The coordinator accepts it and has it built in its own session.
- **Needs the user's go**: it touches settings, instructions, gates, hooks or outward tools, deletes
  anything, or spends.

Send the coordinator one message, reading who it is from `coordinator_cmd` right before you send,
since it can change during a run. The message holds the report's path, each filed number with its
class, cost and challenger verdict, the waiting proposals recommended for dropping, and for each
item that needs the user's go, a question ready for a card with two to four options, the
recommended one first. With no coordinator configured, ask the user on one card.

This run doesn't edit setup files, start build sessions or push. The coordinator does that through
the setup's own process, so every change still passes its gates.

## The loop itself

Keep a table, read from the archived reports: upgrades proposed, accepted, landed and kept, the
footprint, and the number `loop_outcome` prints (the outcome the whole loop is meant to move, such as
how often the user corrects a session), run by run. When three runs in a row land nothing, or what
lands doesn't keep, or the footprint keeps growing without that outcome moving, say the loop isn't
paying for itself and recommend running it less often or stopping it.

## Done when

- The report is at `report` with its footprint line and `retro-upgrades` block, and the previous one
  is archived.
- Each upgrade has evidence, cost, what it replaces, a mechanism measure with a baseline run in this
  run, a challenger verdict or "unchallenged", and a filed number, or the report says why it has
  none.
- The coordinator has the message, or the user has the card.
- Every part that didn't run is named as "did not run", with the reason.

Reply with the report's path, its opening paragraph, a line per verdict from step 1, and a line per
upgrade with its filed number, or "no new upgrade cleared the bar".
