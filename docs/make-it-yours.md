# Make it yours

Product OS gives a change the same path in every project: intent, spec, plan, build-change,
check, review, deliver-change. You fit that path to your team and your own way of working through
settings and a few files you own. None of it needs an edit to the plugin, so an upgrade keeps it.

## Four places hold your settings

- The project's `.claude/product-os.json` is committed, so the whole team gets it. It wins over
  yours key by key. A blank value wins too, so leave a key out rather than writing it empty.
- Your own `~/.claude/product-os.json` is for you in every project. It holds folders on your
  machine and where your OS keychain keeps your tokens.
- The project's `.claude/product-os-checks.json` lists the project's checks. It can add builders
  and reviewers to yours.
- Your own `~/.claude/product-os-checks.json` and the plugin options say who builds, who reviews
  and what QA a builder passes on your machine. A project can propose a QA command but can't
  choose one for you.

Every key is in [config.md](config.md). Tokens never go in these files. They come from your
environment or your OS keychain.

## Settings change what each stage reads

| To change | Set | What it does |
|---|---|---|
| Where a change's files live | `intent.dir` | each change gets one folder under it for its `intent.md`, `spec.md` and `plan.md`, by default `intent/` |
| How the app builds and checks | `app.dir`, `app.build_cmd`, `app.check_cmd` | the push check, the git pre-push hook setup-kit installs, runs them before every push. A command from the project's file runs only after you accept it with `product-os kit_config accept <key>`, and again after it changes |
| The widths a page ships at | `app.widths` | check-page and review-change measure and compare every section at each one |
| What a push must pass | `checks` in `.claude/product-os-checks.json` | `product-os check` runs each one, and the push check refuses a push when one fails. `/product-os:miss-to-check` writes one from a defect that got through. `product-os accept` proves it fails on the defect and passes on the fix, then lets it run on your machine |
| Who builds and who reviews | the `builder_agents` and `reviewer_agents` plugin options; `qa_commands` in your own checks file | a reviewer can't write files. A builder has to pass your QA command after its last edit before it stops |
| Where work is tracked | `tracker.server`; for Azure DevOps also `ado.org`, `ado.project` | `tracker.server` is the MCP server your tracker goes through, as Claude Code names it. deliver-change resolves the item through it, each person signed in with their own account. Azure DevOps with no server set goes through the ado skill and your token. With no tracker set, deliver-change writes the comment for you to paste |
| The design files | `figma.files`; `figma.read_only` | the Figma tools search only the files named. `read_only: true` makes deliver-change draft the reply to design for you to post |
| Where a delivery goes | `deliver.remote`, `deliver.branch` | deliver-change pushes there. By default that's `origin` and the branch's upstream, and with no upstream it asks |
| Which skill takes a request | `go.routes`, `[{"when", "skill", "done"}]` | `/product-os:go` sends a request that matches `when` to your skill, even where a built-in route also matches. It states `done` as the finish line. A route naming a skill that isn't installed stops `go`, and it says so |

Run `/product-os:setup-kit` after a change to any of these. It prints how many setup checks pass,
and asks in one message for each setting a stage needs that isn't set yet.

## Copy a template and edit the copy

The plugin's `templates/` folder holds these. Edit your copy, never the plugin's, so an upgrade
doesn't replace your changes.

- `REVIEW.md` goes in the project root. The reviewer reads it before every review. Put in what
  must never break, the inputs nobody tries and the rules a reviewer holds you to. A rule a check
  already enforces belongs in the check.
- `CLAUDE.md` goes into your `~/.claude/CLAUDE.md`. Every session reads these working agreements.
- `machine.md` goes next to your `CLAUDE.md`. A session reads it only when it needs a fact about
  your machine, such as a file trap or a proxy's block page.

## Route a request to your own skill to change a stage

A team with its own intake form, its own spec sections or an extra sign-off step does it this way.
A setting changes what a stage reads. To change what a stage does, write a skill and route to it.

The shapes of `intent.md`, `spec.md` and `plan.md` are part of the plugin. The intent and spec
skills set the first two, and the build step writes each plan from `templates/plan.md` in plan
mode. An edit to any of them is lost on upgrade, so change them with a skill of your own:

1. Write it as the plugin's `templates/writing-instructions.md` says, so a model follows it.
2. Put it in `<project>/.claude/skills/<name>/SKILL.md` for the team, or
   `~/.claude/skills/<name>/SKILL.md` for yourself.
3. Add a route in `go.routes` naming it, with the words a request for it contains and what
   finished means.
4. Run `/product-os:go` on such a request and check it names your skill.

Your skill can hand on to the next stage by naming it. A sign-off skill routed from "ship this"
can run the sign-off, then hand on to `/product-os:deliver-change`.
