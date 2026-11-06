# Product OS

[![tests](https://github.com/zhyuka/product-os/actions/workflows/tests.yml/badge.svg)](https://github.com/zhyuka/product-os/actions/workflows/tests.yml)

Product OS is a Claude Code plugin for building a product with agents, from the first ask to keeping it running. Nothing an agent built counts until something other than that agent has checked it. That means a reviewer that can't edit files, a check proven on a planted bad case, and a builder that can't stop until QA passes. Each stage of the work leaves a file the next stage reads, so you review files instead of watching edits.

It holds 21 skills, 6 agents, 54 Python tools (`product-os --list` names them), a `product-os` command, and hooks for Claude Code.

## Install

<!-- install:start -->
There are three ways in. The first updates itself; the other two need no plugin marketplace. All
three load the same plugin, with its hooks and its `product-os:` skills and agents.

1. **From the marketplace.** In a Claude Code session, run `/plugin marketplace add
   zhyuka/product-os`, then `/plugin install product-os@product-os`. Where your organization allows
   plugins only from marketplaces it lists, use 2 or 3.
2. **Point your agent at the repo.** Tell Claude Code: "Fetch and follow
   https://raw.githubusercontent.com/zhyuka/product-os/main/INSTALL.md". It clones the latest
   release and, on your yes, sets `CLAUDE_CODE_PLUGIN_DIRS` in your Claude Code settings so the
   plugin loads from the clone. It puts the `product-os` command on your PATH for the git hooks,
   and ends with `product-os doctor`, which has to pass.
3. **From the release zip.** Download `product-os-<version>.zip` from the
   [latest release](https://github.com/zhyuka/product-os/releases/latest) and unzip it. Have your
   agent follow `INSTALL.md` inside it from step 3, or start Claude Code with `--plugin-dir` set to
   the unzipped folder for one session.

The tools and checks need Python 3.9 or later. The commands that drive a browser also need
Playwright: `pip install playwright`, then `playwright install chromium`.
<!-- install:end -->

The exact wording lives in [docs/install.md](docs/install.md).

## The stages

The six stages, and the files that pass between them, come from Anthropic's [AI-native SDLC playbook](https://claude.com/resources/articles/the-ai-native-sdlc-playbook). Product OS adds the hooks and checks an agent can't pass for itself, described after this table.

| Stage | Skills and agents | Commands |
|---|---|---|
| Plan | `intent` writes the ask down as `intent.md`, in the asker's words, with what's unsettled kept as open questions. `recall` answers "have we seen this before?" over your session logs, git, notes and trackers. `open-question` files a question only you can answer, and `triage` works them down up to four decisions a card. `ambition` rewrites a prompt into a deeper version of the task | |
| Design | `spec` turns an accepted intent into `spec.md`: requirements and design for this codebase, concerns flagged first. `figma-writes` says what can go wrong in a Figma write, before any write | `product-os design import`, `design drift`, `design states` |
| Build | Plan mode writes `plan.md` from [`templates/plan.md`](templates/plan.md). `setup-kit` puts the push and commit checks in place and checks the setup. `build-change` builds or changes part of a page from a design, a picture or words, and isn't done until the design check, `section-reviewer` and `check-page` all agree. With a design file it calls `build-from-design`, which measures the build against the design with a check proven on planted mistakes. A builder agent can't stop until the QA command passes after its last edit | `product-os design exercise` |
| Test | `check` runs the project's own checks. `check-page` has a fresh `page-qa` agent measure a built page at one commit, and the run doesn't count if the agent changed anything it judged. `miss-to-check` turns a defect that got through into a check, proven both ways | `product-os check`, `prove`, `accept`, `gates` |
| Deploy | `review` hands the change to the `reviewer` agent, which didn't write it and can only read, with the spec and the project's `REVIEW.md` ([template](templates/REVIEW.md)). `review-change` has a fresh `section-reviewer` compare each section with its design, from pictures and numbers alone. `deliver-change` commits, pushes on your yes and moves the tracker item to Resolved. `ado` runs the Azure DevOps item from search to resolve | |
| Maintain | `reconcile` brings a workspace back to a clean baseline and does only what you approve. `retro` runs every two weeks, by hand or on a schedule: it reads your own records and what changed in Claude Code, files at most five upgrades for your approval, and measures the last run's | `product-os scheduled_audits` |
| Any | `go` maps a request to its stage and loads the one skill that owns it. `humanize` cuts AI tells from prose. The `challenger` agent tries to beat a recommendation before you see it, `blind-grader` grades anonymised work against controls, and `cold-reader` reads a draft as one first-time reader | |

Each change keeps its files in the project's `intent/<name>/` folder: `intent.md`, then `spec.md`, then `plan.md`, each committed before the next stage starts, so git history shows who asked for what and what was decided.

## Checks that an agent can't pass for itself

The hooks and the `product-os` checks are described in full in [docs/checks.md](docs/checks.md). In short:

- A reviewer can't write files. When an agent your config names as a reviewer calls Edit or Write, or runs a shell command that writes, the hook denies the call.
- A builder can't stop early. If it edited files after its last passing QA command, the stop hook sends it back.
- A project's checks count only once proven. `product-os prove` records that each check failed a planted bad case and passed a good one.
- A build has to respond in every state its design draws. `product-os design` records the Figma design as a baseline and drives the build into each state.

Hooks don't run where an organization allows only its own managed hooks. There, run `product-os check` in a git hook or CI instead. The templates are in [`ci/`](ci).

## Agents

| Agent | What it does |
|---|---|
| `reviewer` | Reviews a change it didn't write. It has only Read, Grep and Glob |
| `challenger` | Tries to beat a recommendation before the user sees it. Give it the problem, the hard rules and the recommendation, not your reasoning |
| `blind-grader` | Grades shuffled, anonymised items against a rubric. Mix in a known-good and a known-bad control |
| `cold-reader` | Reads a draft as one named first-time reader and says where they got lost |
| `page-qa` | Runs the `check-page` pass on one built page, report-only. It has no file-writing tool, and check-page compares what it could change before and after it runs |
| `section-reviewer` | Reviews one built section against its design frame, the way the designer would |

## Tools

All of them are in [`tools/`](tools). By area:

- **Claude Code logs and memory.** `cc_logs` finds every session log on the machine, backups included. `log_extract` pulls out everything you typed, with a real denominator. `session_close` says whether a session can be archived: what blocks it, and what it only lists. `ledger` and `digest` track every request you made and its state, this machine's first. `triage_lists` prints the first lines of a triage card: each list it draws on, and whether it ran, quoting each refusal. `bare_ids` counts the design-node and work-item ids sessions hand you without a link. `card_check` checks a question card before you see it: bare ids, paths you can't open, its shape, and past cards and records that may already answer it. Also `tool_time`, `skill_use`, `skill_lint`, `recall`, `recall_index`, `seals`, `pushback_score`, `weekly_metrics`, `agent_gate_stale` and `statusline_model`.
- **Checks that report N of M.** `class_check` counts how many files in a class got a shared change. `qa_snapshot` proves a QA agent changed nothing it could have used to pass. `verify_ledger` answers "was it verified?" from a file. `kb` keeps what is known about each body of work as cited entries, and `kb check` reports how many still hold, naming each whose source moved. Also `workspace_audit`, and `doclint`, a docs linter and pre-commit gate.
- **Figma.** `figma_client` is one REST client with a shared budget and a pause on 429. `figma_comments` reads a thread before you write to it. `figma_variants` lists a component set's variant matrix, its properties and its variable bindings per mode. Also `figma_post`, `figma_attach`, `figma_family`, `figma_evidence`, `figma_auth` and `drafts_store`.
- **Page checks.** `backdrop_group_check` finds frosted elements an ancestor's opacity breaks, and dead tap spots in cards. `sliver_sweep` finds rounded boxes whose fill leaks as a ring at the corners. `structure_check` checks that every instance of a class in the built HTML has the same shape. `shot_gpu` takes a GPU-on full-page screenshot.
- **Azure DevOps.** `ado` refuses a create that hasn't searched for duplicates. `ado_rest` and `ado_write` use REST with a PAT, so nothing waits on an `az` prompt. `ado_write delete` sends a Removed item to the recycle bin and `restore` brings it back. `ado_links` finds the work-item ids a doc leaves bare and links them.
- **Upkeep.** `scheduled_audits` runs the read-only audits daily. Also `upkeep`, `backup_cc_logs`, `desktop_mirror`, `archive`, `pw_temp`, `signed_in_browser`, `html_clip` and `transcript_check`.

The tools that grade something share one exit-code rule: 0 clean, 1 findings, 2 could not run. A tool that couldn't run never reports clean.

### The product-os command

While the plugin is enabled, Claude Code puts its [`bin/`](bin) folder on the Bash PATH. So a skill or script in your own project can run a check or any tool without knowing where the plugin is installed:

    product-os check --base origin/main
    product-os class_check 'SiteFooter' --glob '**/*.astro' --expect all
    product-os --list

`product-os check`, `prove`, `accept`, `gates`, `design` and `demo` run the checks. `product-os <tool> [args...]` runs `tools/<tool>.py` with `python3`, or `python` if there's no `python3`, and exits with the tool's own code. An unknown tool exits 2 with a one-line message. In CI, `pip install "product-os @ git+https://github.com/zhyuka/product-os@v0.1.1"` installs the checks command alone.

## Settings

Two files per project, each committed with it:

- `.claude/product-os.json` holds the project's values, such as an Azure DevOps project or a Figma file key, so no tool carries one. Every key is listed in [docs/config.md](docs/config.md). A tool that needs a key you haven't set stops and names it.
- `.claude/product-os-checks.json` lists the project's checks and who counts as a reviewer or a builder. On your machine a check runs only once you accept it with `product-os accept`.

Tokens come from environment variables or the OS keychain, never from these files.

The Figma and Azure DevOps tools that write take a reason in plain words on any flag that lifts one of their refusals, so you read why in the permission prompt. For that prompt to fire, give each write command an ask rule in your settings, in the form `Bash(*figma_post* new *)`. `python tools/ask_rules.py <settings.json>` checks that every write prompts and no read does.

## Templates

- [`templates/CLAUDE.md`](templates/CLAUDE.md) holds working agreements to copy into `~/.claude/CLAUDE.md`. Edit them to fit how you work.
- [`templates/machine.md`](templates/machine.md) starts the notes on your machine that a session reads on demand: file traps and a proxy's block page.
- [`templates/REVIEW.md`](templates/REVIEW.md) is a project's review rules for the reviewer: what it checks, what blocks and what is POLISH.
- [`templates/writing-instructions.md`](templates/writing-instructions.md) is how to write a skill, an agent or a rule so a model follows it.
- [`templates/launchd/`](templates/launchd) has a macOS example that runs the daily audits at login and at 08:00.

## Maintenance

Product OS is the source of these skills and tools. The setup it came from adds only its own settings and private parts on top. [`scripts/leak_scan.py`](scripts/leak_scan.py) runs before every commit and refuses token shapes and a private list of names, hosts and file ids, kept outside the repo. The same hook refuses a commit whose author isn't a GitHub noreply address.

[PRIVACY.md](PRIVACY.md) says what the plugin reads, writes and sends. [CHANGELOG.md](CHANGELOG.md) lists each release.

Product OS has one maintainer, [@zhyuka](https://github.com/zhyuka). Nobody else can merge or release. Issues are welcome. MIT licensed.
