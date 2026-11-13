# Product OS checks

These are the parts of Product OS that check an agent built what a Figma design draws, and keep the agent from passing its own work along the way. They run as hooks in Claude Code and as the `product-os` command, which also runs in a git hook or CI.

- A build has to respond in every state its design draws. `product-os design` records the Figma design as a baseline in the repo, lists each hover, focus, press and open state its frames draw, and drives the build into each one to see whether it responds. `design drift` says when someone edited the design after the baseline. See [Check a build in every state its Figma design draws](#check-a-build-in-every-state-its-figma-design-draws).
- A reviewer can't write files. When an agent your config names as a reviewer calls Edit or Write, or runs a shell command that writes, such as `sed -i`, `rm` or a `>` redirect, the hook denies the call and tells the agent to put the change in its review.
- A builder can't stop early. If it edited files after its last passing QA command, the stop hook sends it back to run QA, and if QA can't pass, to tell you why. A QA run piped into `tail` or ended with `|| true` doesn't count, because its exit code is hidden.
- A project's checks count only once proven. `product-os check` runs the checks a project lists, from a skill, a git hook or CI. `product-os prove` records that each one failed a planted bad case and passed a good one, and a check without that record doesn't count. A project can add checks but can't remove one or change its cases. See [A project's own checks](#a-projects-own-checks).
- `/product-os:review` has the change reviewed by a fresh reviewer that didn't write it and can't edit files. `/product-os:miss-to-check` turns a defect that got through into a check, proven both ways.

<!-- github-only -->
Install from a Claude Code session:

```
/plugin marketplace add zhyuka/product-os
/plugin install product-os@product-os
```

<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
Install it by having your agent follow `INSTALL.md` in this folder.

-->
Then run `/product-os:setup-kit` to choose your QA command. The hooks and checks need Python 3.9 or later and nothing else, and make no network calls. The rest of Product OS is in the [README](../README.md). `product-os design exercise` also needs Playwright and Chromium: `pip install playwright`, then `playwright install chromium`.

## Install

<!-- github-only -->
Each of these adds the `product-os` marketplace and installs the plugin for your user:

| Where | Command | Claude Code |
| --- | --- | --- |
| In a session | `/plugin install product-os --marketplace zhyuka/product-os` | 2.1.275 or later |
| In a shell | `claude plugin install product-os --marketplace zhyuka/product-os` | 2.1.292 or later |
| Either, on an older version | `/plugin marketplace add zhyuka/product-os`, then `/plugin install product-os@product-os` | |
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
`INSTALL.md` in this folder has the steps. For one session only, start Claude Code with
`--plugin-dir` set to this folder.
-->

The hooks need Claude Code 2.1.69 or later, the first version that tells hooks which subagent is acting. They also need Python 3.9 or later as `python3` or `python`, or as `py -3` on Windows. Git Bash is optional on Windows.

### Other agent tools

The repo root also holds an [Agent Plugins](https://agent-plugins.org) 1.0 `plugin.json`, the manifest that VS Code, GitHub Copilot, Cursor and Codex read. Through it they load the skills. The skills run the plugin's copy of product-os by its path, `${CLAUDE_PLUGIN_ROOT}/bin/product-os`, which Claude Code fills in when a skill loads. Those tools may leave that path unfilled. The skills then call the `bin/product-os` in the plugin's folder, above the skill's own, so nothing more needs installing.
<!-- github-only -->
Where that file isn't there, install the command with `pip install git+https://github.com/zhyuka/product-os`, and the skills run `product-os` instead.
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
Where that file isn't there, install the command with `pip install` on this folder, and the skills run `product-os` instead.
-->
Hooks and agents aren't part of that format. So in those tools the review skill falls back to a new chat, and a check holds only where `product-os check` runs in a git hook or CI.

### What happens on first run

1. Hooks load when a session starts. After the install, start a new session or run `/reload-plugins`.
2. The session opens with one line from the plugin: `product-os is on. Reviewers (*reviewer*) can't write files. The QA check is off until you set a QA command: run /product-os:setup-kit.` It shows once per project, and again when the settings change.
3. From then on, an agent whose name matches `*reviewer*` can't write files. The QA check stays off until you accept a QA command for the project, so nothing else changes until you run the setup skill.

An install in a session can show the plugin's options with their defaults filled in. Keep them or change them; [Configure it](#configure-it) says what each one does.

## Examples

1. Keep a reviewer read-only. Ask: "Use the code-reviewer agent to review build/app.js and list what to fix." If the reviewer tries `sed -i` on the file, Claude Code cancels the call and tells it to put the change in its review instead.
2. Make "done" mean QA passed. Run `/product-os:setup-kit` and pick the main session as the builder and `npm run check` as the QA command. Then ask: "Fix the failing test in src/cart.js and tell me when it's done." If Claude edits, runs `npm run check | tail -5` and tries to stop, the hook sends it back to run `npm run check` on its own. It can stop once that passes after its last edit.
3. Check a finished build. From the plugin's folder, run `/product-os:check examples/runs/cheap-builder`. It prints pass, fail or skip for each check. Here "step ran" fails because `npm run check` never ran, and the command exits 1.
4. Make a missed bug a check. Ask: "A debug print got into the release in src/cart.py. Make sure that can't get through again." `/product-os:miss-to-check` writes a check with a bad case that has the print and a good case without it, and `product-os prove` has to see the check fail the first and pass the second before it counts.

## Configure it

Every setting is optional. The setup skill writes the project's, and they live in three places.

- **The setup skill.** `/product-os:setup-kit` finds the project's check command in `package.json`, a `Makefile`, pytest, tox, Cargo or Go, asks which agents are builders and reviewers, and once you confirm writes `.claude/product-os-checks.json`. It shows the entry for your own `product-os-checks.json` and leaves that edit to you, since that file decides what counts as QA on your machine.
- **The project file.** `.claude/product-os-checks.json` holds the settings for one project, and you can commit it for your team. It can add reviewers and builders and make `reviewer_shell` stricter, but it can't take any of your settings away, and its `qa_commands` only propose a QA command:

  ```json
  {
    "reviewer_agents": ["*reviewer*"],
    "reviewer_shell": "block-writes",
    "builder_agents": ["main", "page-builder"],
    "qa_commands": ["npm run check"]
  }
  ```

- **Your own file.** `product-os-checks.json` in your Claude Code config folder, `~/.claude` or `CLAUDE_CONFIG_DIR`, lists the QA commands you accepted for each project. Only these count:

  ```json
  {
    "projects": {
      "~/code/shop*": {"qa_commands": ["npm run check"]}
    }
  }
  ```

  A key covers the folders under it. A `*` matches any characters, slashes included, so `~/code/shop*` also covers a worktree such as `~/code/shop-fix`. When several keys match, the longest wins.

- **Plugin options.** These are yours, for every project. Set them with `/plugin configure product-os@product-os` or in `/config` in a session, or from a shell with `--config builder_agents=main` on `claude plugin install`. Claude Code 2.1.285 or later also has `claude plugin configure product-os@product-os --values-stdin`. Lists are names separated by commas.

| Setting | Default | What it does | Where |
| --- | --- | --- | --- |
| `reviewer_agents` | `*reviewer*` | Agents that may not write files | Option; the project file can add names |
| `reviewer_shell` | `block-writes` | `block-writes` denies shell commands that write files. `block-all` denies every shell command | Option; the project file can make it `block-all` |
| `builder_agents` | `*builder*` | Agents that have to pass QA after their last edit before they stop | Option; the project file can add names |
| `qa_commands` | none | Commands that count as the QA step. The QA check stays off until you accept one | Your own file; the project file can propose one |
| `session_status` | `once` | The line at session start. `once` shows it the first time in a project and when it changes, `always` in every session, `off` never | Option only |

A repo you clone can't turn a check off. Its file only adds to your settings, and a QA command it proposes counts once you accept it. The line at session start names a proposed command that doesn't count yet.

The hooks tell agents apart by the `agent_type` field that Claude Code puts in each hook input. For a custom subagent that is the `name` in its frontmatter. For a plugin's subagent it is `plugin-name:agent-name`, and for a session started with `--agent` it is that agent's name. Patterns are shell-style globs, matched without case. `main` stands for the main session when it runs without `--agent`.

A project file with bad JSON, an unknown field or a wrong type makes the hooks fall back to the defaults, and every hook answer then carries a warning that names the problem. A mistake in your own file means no QA command counts until you fix it, with the same warning. A bad option value is ignored and named in the line at session start.

## A project's own checks

A check is a command that exits 0 when what it inspects passes and non-zero when it doesn't. The project lists its checks in `.claude/product-os-checks.json`, with at least one planted bad case the check has to fail and one good case it has to pass:

```json
{
  "checks": [
    {
      "name": "no-print",
      "run": "{python} checks/no_print.py {target}",
      "target": "src",
      "bad": "checks/cases/no-print/bad",
      "good": "checks/cases/no-print/good"
    }
  ]
}
```

- `run` is a command line, split into words as a POSIX shell splits them, or a list of words. It runs from the project root without a shell, so a pipe or a redirect in it is just a word. `{target}` becomes the path the check inspects and has to appear, so `prove` can point the check at its cases. `{python}` becomes the Python that runs product-os.
- `target` is the file or folder the check inspects in the project. It defaults to `.`.
- `bad` and `good` are each a path or a list of paths, to files or folders.
- `timeout` is in seconds and defaults to 900.

`examples/project/` is a project with this check, its cases and its proof.

### Prove a check, then run it

```
$ product-os prove --project examples/project
Proving the checks in /home/sam/product-os/examples/project
  check     bad cases caught  good cases passed  result
  no-print  1 of 1            1 of 1             proven
  1 of 1 checks proven. Records: .claude/product-os-checks-proofs.json.
  On this machine a check runs only once it is accepted. That's the person's step, never an agent's, even on their yes: read its command, then run product-os accept in a terminal of your own.

$ product-os accept --project examples/project
Accepting the checks in /home/sam/product-os/examples/project. These are the commands that now run on this machine:
  no-print: {python} checks/no_print.py {target}
  check     bad cases caught  good cases passed  result
  no-print  1 of 1            1 of 1             proven and accepted
  1 of 1 checks proven. Records: .claude/product-os-checks-proofs.json.
  Accepted on this machine: /home/sam/.claude/product-os-checks-accepted.json.

$ product-os check --project examples/project
Checks for /home/sam/product-os/examples/project
  check     result  detail
  no-print  pass    exit 0 on src
  1 of 1 checks passed.
```

On your own machine a check runs only once you accept it. A project's file can list any command as a check, and its proof records are files anyone can write, so neither makes a command run here. `product-os accept` prints each check's command, proves it, and keeps the proof in `product-os-checks-accepted.json` beside your own config, for that project's repository: it counts in every git worktree of the repository, and not in a separate clone, which needs its own accept. A check that changes after that, or whose cases change, stops running until you accept it again. Accepting is yours, never an agent's, even on your yes: `product-os accept` refuses to run in an agent's shell in Claude Code, and the hooks refuse an agent's `accept` and its edits to that file. CI has no accepted checks, so the CI templates pass `--run-listed`, which runs every listed check and counts the project's own records; the code owner's review of `.claude/` stands in for accepting.

`product-os prove` runs each check on its cases. A check is proven when it exits non-zero on every bad case and 0 on every good one. A case where the command didn't start or timed out proves nothing. A check that passes its bad case would miss the defect, and one that fails its good case is a false alarm, so neither is proven. The record goes in `.claude/product-os-checks-proofs.json`, which you commit with the check. Proving runs the check's command, so in Claude Code the hooks ask you before an agent proves a listed check you haven't accepted here as it is now, or the checks in a file the repository committed, and name each command.

`product-os prove --check checks/<name>.json` proves a check before it's listed, from a file that holds its entry. Except in bypass and auto mode, Claude Code asks you before an agent writes in `.claude/`, and refuses the write in a session that can't ask. So `/product-os:miss-to-check` proves the new check this way first and then asks you to list it. The same entry, listed unchanged, counts as proven. `--check` refuses a name the project already lists for a different check, since records are kept by name.

`product-os check` runs every check on its target and prints one row each. Only `pass` passes:

- `fail`: the check ran and found a problem. Its last 20 lines of output follow the table.
- `unproven`: on your machine, the check isn't accepted as it is now, so it didn't run. Or it has no record, or something that defines it changed since the record was made: the check itself, a case, or a file or folder its command names. For `design states`, `design exercise` or `design drift` without `--baseline`, that includes the baseline in `design/`. A folder that is or holds the check's target isn't counted, since that's what the check inspects. Run `product-os prove` again.
- `removed`: with `--base`, the change took away a check or one of its cases that the base has.
- `error`: the command wasn't found, couldn't start or timed out.

The exit code is 0 when every check passed, 1 when one didn't or there are no checks, and 2 when the checks or a git ref can't be read. `--project` names the project folder; by default it is the nearest folder up from `$CLAUDE_PROJECT_DIR`, else from where you run it, that has a `.claude/product-os-checks.json`. A folder inside the plugin's own folder counts only when it has a `.claude` folder of its own, as `examples/project` does; otherwise it refuses with exit 2.

A record shows that `prove` ran on these files. An agent could also write one by hand. That's why the project's records count only with `--run-listed`. `product-os check --prove` runs every check's cases again instead of trusting the record, and fails a check whose record is missing or out of date. CI should use both. In Claude Code, the hooks ask you before any agent edits `.claude/product-os-checks-proofs.json`, as they do for `.claude/product-os-checks.json`.

### A project can add checks, never remove one or change its proof

The same rule as the hook settings holds for checks:

- Your own `product-os-checks.json` can list checks for a project next to its QA commands, as `{"projects": {"~/code/shop": {"checks": [...]}}}`. Those always run. A project check with the same name is left out, and `product-os check` says so when the two differ.
- With `--base REF`, every check the project file had at that git ref has to stay, and so does each of its cases, unchanged. A change can add checks and cases. It can rewrite a check's command, but the new command has to be proven on the same cases. Leaving a check out, or dropping or editing one of its cases, comes out `removed`. CI passes the branch the change would merge into, such as `origin/main`.

To remove a check, a maintainer merges the change past the failing job, which a protected branch lets an admin do.

### Where a check can't be skipped

- **Through a skill.** `/product-os:check` runs `product-os check` and reports the table. A skill leaves the call to the agent: it decides whether to run it, and it can stop without running it.
- **In a git hook.** `ci/pre-push` runs the project's `app.build_cmd` and `app.check_cmd`, refuses a DID NOT RUN line, and runs `product-os check --base` before each push. It refuses the push when `product-os` isn't on PATH. `ci/pre-commit` refuses a commit that stages a key or a token. `/product-os:setup-kit` puts two short files from `ci/shim/` in `.githooks/`, which run the installed plugin's hooks, so the project keeps no copy. `git push --no-verify` skips them.
<!-- github-only -->
- **In CI on a protected branch.** This is where a check can't be skipped. `ci/github-actions.yml` and `ci/azure-pipelines.yml` install a fixed product-os release from outside the repository and run `product-os check --prove --run-listed --base` on each pull request. A pull request runs its own copy of the workflow, so also require a code owner's or a required reviewer's approval for the workflow file and for `.claude/`, and require the job to pass before merging. The comments at the top of each template say where to set this.
<!-- /github-only -->

### When a check can't pass

When a check fails, its output ends with a way out. If the check can't pass for a reason outside the change, such as a service the machine can't reach, the agent should stop and say it's blocked. It names the check, gives the output and says why. It doesn't edit the check, its cases, the files it runs or the two `.claude/` files to get a pass. `/product-os:check` says the same.

That way out matters. In [ImpossibleBench](https://arxiv.org/abs/2510.20270), where a task can only pass by breaking its tests, letting the agent flag the task for a person cut GPT-5's cheating from 54% to 9%. The paper found the effect much smaller for Claude Opus 4.1, so don't count on the message alone. Run the checks in CI too.

## Check a build in every state its Figma design draws

`product-os design` records a Figma design as a baseline in the repo, lists every state the design draws, and exercises a build in each one to see whether it responds. An agent's build often has the default look of a component and none of its hover, focus or open states, and a screenshot of the page at rest can't show that.

The baseline is a record of the design the build was checked against. It doesn't stand in for Figma: check it against the live file before you rely on it (step 4).

1. **Record a baseline.** Save three answers from Figma's REST API: `GET /v1/files/:key/meta` first, then `GET /v1/files/:key/nodes?ids=<frame ids>`, then the same call for the component sets that answer lists. Run `product-os design import nodes.json --sets sets.json --meta meta.json`. It writes each frame's node tree to `design/`, without hidden layers. `design/index.json` holds a SHA-256 for each frame and each component set, and the file's last edit, which step 4 compares. product-os doesn't call Figma itself, so your token stays with whatever reads the API. Positions are measured from each frame's corner, so moving a frame on the canvas leaves its hash alone, and any other edit changes it.
2. **List the states.** `product-os design states` lists each prototype reaction (hover, press, click, a key, a timeout) and each drawn variant whose value names a state, such as `State=Hover` or `Open=True`. A state no input reaches, such as Disabled, is listed as not exercised, with the reason.
3. **Exercise the build.** `product-os design exercise http://localhost:3000/` opens the build as wide as each frame and drives it into each state from a fresh load. Hover moves the mouse onto the node, focus presses Tab until focus reaches it, and press, click, a key and a timeout do what they say. A state passes when the node's pixels or computed style changed. Each picture is taken once transitions have finished, with looping animations held at their start, so a pulse elsewhere on the page doesn't count as a response. A timeout is the design drawing motion, so it passes when the node or something inside it animates, or its look changes during the wait. A link passes when it goes where the design says. A click that opens another site, on a scheme or host other than the URL's, passes and is reported, and the site isn't loaded in the page's own window. A link that opens a new window or tab isn't stopped yet. `--serve dist` serves a built folder instead. `--evidence DIR` saves each state's before and after screenshots. A node is found by a selector you give in `--selectors` (for its id, or its component set's name), by a `data-figma-node` attribute, or by its text.
4. **Check for drift.** `product-os design drift --meta meta.json` takes a fresh answer to `GET /v1/files/:key/meta`, one call, and exits 1 when the file was edited since the baseline last matched it. Then `product-os design drift nodes.json` with a fresh read of the frames says which frames moved. Run it before an approval and in CI.

To make the exercise a check, list it with a planted build as its bad case, such as one with a hover rule deleted, and the approved build as its good case:

```json
{
  "name": "designed-states",
  "run": ["{python}", "-m", "product_os", "design", "exercise", "/", "--serve", "{target}"],
  "target": "dist",
  "bad": "checks/cases/no-hover/dist",
  "good": "checks/cases/approved/dist"
}
```

What it doesn't do:

- A state that responds isn't a state that matches. A hover that turns the wrong colour passes. Compare the evidence screenshots with the design for that.
- A state the design doesn't draw isn't checked. Neither is a mix of states, such as one card focused while another is hovered.
- A prototype link the team built differently on purpose fails until it's recorded. List it in a file passed with `--accept`, each entry `{"node", "state", "why"}` with the state as `design states` prints it and a why that says what was decided and where. It's then reported as accepted, with its why, and an entry that's no longer needed is printed.
- Finding a node by its text fails when the build's copy differs from Figma's. The result says `not found`, so the difference shows up instead of passing. A node with no text, such as an icon or a dot, needs a selector in `--selectors`.
- Motion a script draws frame by frame, without CSS or the Web Animations API, isn't held. On a page with such motion, a click or a key can pass on it.
- A timeout is looked at from about a third of a second after the page loads. A one-off change a script makes before then isn't seen. An animation is seen whenever it runs.

## Gates: what a build has to get right that a design rarely draws

A design seldom draws a focus ring, a phone width for every block, or how sharp an image is on a 2x screen, and an agent's build often gets those wrong. `product-os gates` opens the build at each width the baseline's frames have, or 1280 and 390 px without one, and fails what it can measure:

| Gate | Fails |
| --- | --- |
| `keyboard` | what a mouse can use and a keyboard can't |
| `focus` | a Tab stop that doesn't show it has focus |
| `overflow` | anything that runs past the right edge |
| `images` | a picture that doesn't show, or is blurry at 2x |
| `motion` | motion that keeps on with reduced motion asked for |

`keyboard` fails when:

- something a mouse can click or drag (a pointer, grab or move cursor, an `onclick`, `draggable="true"` or a button-like role) has nothing Tab can reach in or around it.
- a control has `tabindex="-1"` outside a widget that moves focus with the arrow keys, or an element takes focus but Tab never reaches it. Tab reaching one radio button in a group is enough, since the arrow keys move between them.
- Neither of those two counts a link that goes where a link Tab reaches goes, as a card's picture often repeats its title link, or a control that a box hiding its overflow hides all of, as a carousel hides the slides not showing. Nor do they count a control that can't take focus at all: one that's disabled, by itself or by a disabled fieldset, one inside `inert`, or one outside an open modal dialog, a `<dialog>` opened with `showModal()` or a shown element with `aria-modal="true"`.
- Tab reaches a control inside `aria-hidden="true"`, which hides it from a screen reader.
- Tab can't leave an element, or goes round a few and never on, and no key gets out either. Escape, Shift+Tab, or the key the page's own text names, as in "Press Ctrl+M to leave the editor", gets out, since the W3C's ACT rules on keyboard traps ask for one direction only. Past a loop only Shift+Tab leaves, the stops are those Shift+Tab reaches going on backwards. Tab moving on inside a frame, through its own links, or through a date field's day, month and year, isn't a trap until it's back where it was in there. A frame from another site can't be read from outside, so it gets 50 presses, and a date or time field 8.
- a link or control that a hover shows never shows with Tab, or with Enter or Space on a Tab stop in the same box, such as a menu's disclosure button.
- a click or a double-click works an element and Enter, Space and the down arrow don't, or a click follows a link and Enter doesn't. Opening a file picker, a browser dialog, a popup or a download counts as working.
- in a widget Tab reaches once, such as tabs, a menu, a toolbar or a list box, a click on an item changes the page, and an arrow key followed by Enter or Space doesn't.
- Enter opens a dialog that no key closes, or opens links that neither Tab, Shift+Tab nor the down arrow reaches.
- typing in a field shows choices that neither the down arrow nor Tab gets to.
- a drag moves a handle, and the arrow, Page, Home and End keys don't.
- a mouse wheel scrolls a box that holds nothing Tab can reach, so no key scrolls it.
- a control stays disabled until a mouse moves.

`focus` fails when a Tab stop looks the same with focus as with nothing focused, judged on its pixels, or when it's off the screen or covered all over, by a sticky bar say, while it has focus. That is judged where it ends up, once a transition it starts on focus has ended, any smooth scroll to it has stopped, and it and the boxes around it have held still and stopped fading for 3 frames, as a carousel's slide does once it has slid in. Something on top covers a stop only if it paints there, so a see-through layer or a card's stretched link doesn't. When focus changes a box around the stop instead, as `:focus-within` does, that box is compared. When focus resizes the stop, or brings it into the window, as a skip link hidden in a 1 px box or above the page does, the same part of the page is compared with focus and without, as WCAG 2.4.13 compares them. It also fails when what focus changed reaches less than 3:1 against the colours beside it, the contrast WCAG 1.4.11 asks at AA. As that criterion's Understanding page measures it, a ring outside the stop is held against the background, and a change inside it, such as a border or an inset ring, against every colour it touches there. A ring in two colours, as the browser's own is, passes on either one. A change that reaches 3:1 against how the stop looked without focus, over at least a 2 px ring, passes too, since that is what WCAG 2.4.13 asks at AAA. A stop that passes AA but not that, or whose ring shows on fewer than four sides, is listed as weak. The detail counts weak stops, `--json` names each with why, and they don't fail. A control you can't see, such as a checkbox with `opacity: 0` under a drawn box, is judged by the label or the box around it that shows it. One that shows once it has focus, as a carousel's slide does when Tab scrolls to it, is judged by itself.

`overflow` fails when an element starts on the screen and runs past its right edge, outside any box that scrolls or clips, or when the page scrolls sideways.

`images` fails when a picture is drawn more than 10% larger than its pixels allow at `--scale`, 2 by default. That covers an `<img>`, a CSS background and a picture inside an SVG, the part cut off an image cropped to cover its box, a `<canvas>`, whose pixels are its buffer, and a fixed background, which is sized against the screen. It also fails when a picture doesn't show:

- it doesn't load, or the file an `image-set()` picks at that density doesn't, or the file of a mask over it doesn't.
- an SVG drawn as an image links to it, and the browser never loads that.
- it loads but stays at opacity 0, with nothing shown over the same spot and no hover that shows it.
- a later background in the same block replaces it.
- CSS that isn't valid drops it, or leaves its box with no height, as `aspect-ratio: 2:1` does.
- it's the background of an element laid out inline, such as a `<span>`, where the width and height its CSS sets don't apply, so the box is less than half that size.

An SVG's own shapes scale, so they pass.

`motion` fails when, with reduced motion asked for:

- a CSS, Web Animations API or SVG `<animate>` animation runs forever or for more than 5 seconds, one in a component's shadow root included.
- in the 6 seconds after that, a script changes an element's style or class twice or more.
- in those 6 seconds, pixels on the first screen keep changing with nothing in the page's code to show why, as a `<marquee>`, a GIF, a video or a `<canvas>` does.

```
$ product-os gates / --serve dist --width 390
Gates for / on dist, at 390 px
  width  gate      result  detail
  390    keyboard  pass    Tab reached 4 elements, and all of them can be left with Tab
  390    focus     fail    4 of 4 Tab stops don't show focus
  390    overflow  pass    everything fits in 390 px
  390    images    pass    every image is sharp at 2x
  390    motion    pass    with reduced motion, nothing runs on
  4 of 5 gates passed.

--- focus at 390 px
  body > main > nav > a:nth-of-type(1): it looks the same with focus as without
  body > main > nav > a:nth-of-type(2): it looks the same with focus as without
  body > main > button: it looks the same with focus as without
  body > main > div:nth-of-type(1) > a: it looks the same with focus as without
```

The exit code is 0 when every gate passed at every width, 1 when one didn't, and 2 when the build can't be opened or Playwright is missing.

`--only GATE` runs some of them, and `--json FILE` keeps every finding. Each probe starts from a fresh load as a first visit, with the cookies and the local and session storage of the probe before cleared. On a URL with a `#` the page isn't loaded again, so its own state can carry over from one probe to the next. It stays on the build's own site in the page's own window; a link that opens a new window or tab isn't stopped yet. To make the gates a check, list them like the exercise, with a planted build as the bad case:

```json
{
  "name": "gates",
  "run": ["{python}", "-m", "product_os", "gates", "/", "--serve", "{target}"],
  "target": "dist",
  "bad": "checks/cases/no-focus-style/dist",
  "good": "checks/cases/approved/dist"
}
```

What the gates don't do:

- They measure, they don't judge. A focus ring that reaches 3:1 but is hard to notice, such as a 2 px dot, passes `focus` as weak, and an image that's the wrong picture passes `images`.
- They look inside a component's open shadow root, and name what's in it by its host, `>>>`, and its path inside. A closed shadow root is seen only by the pixels `motion` watches.
- `keyboard` sees a click handler through a pointer cursor, an `on` attribute, a role, or a listener a script adds, which a small script run before the page's own notes. A handler on a box around the element, as React puts every handler on its root, isn't tied to the element.
- `keyboard` hovers up to 20 closed boxes and presses Enter and Space on up to 20 buttons and button-like elements per width. In a box a hover opens, it presses keys on up to 3 of the box's Tab stops, buttons first: Enter on each, and Space on a button. It tries Enter on a link only under a key listener, types in up to 5 text fields, trying common first letters, and drags only a handle with a resize, grab or move cursor or a slider's role. It unlocks a disabled control with a mouse but never with touch. It counts a key as working when the page's address changes, an element changes and stays changed, it starts a navigation, or it opens a file picker, a dialog, a popup or a download, so a key that only plays a sound looks dead. A scroll isn't a change, since Space scrolls a long page whatever has focus. Neither is a change to an element that changes by itself in the second after the page loads, such as a clock; one that changes by itself less often than that can make a dead key look like it works. A key after which the page can't be read, as when the navigation it started replaced the page, is never reported. In up to 5 widgets per width it clicks one item and tries the arrow keys, Enter and Space from the item that has focus.
- `focus` compares up to 80 Tab stops per width, and says how many it left out. A frame is one stop, pictured as Tab enters it, so focus on the stops inside it isn't compared. It holds animations as Playwright's screenshot does, one that ends at its end and one that loops taken off, so a focus style that shows only while an animation loops isn't seen. It waits up to 1.5 s for a stop to hold still, so one that keeps moving, as in a carousel that plays by itself, is pictured wherever it is then. It pictures each stop with 8 px around it, so a ring drawn further out than that is seen only when a box around the stop draws it. A stop that focus resizes, or that shows only with focus, is pictured without focus on a fresh load, scrolled to where it was with focus. So what a fresh load shows differently there counts as a change, and so does what a skip link pushes down when it opens above the page.
- `images` judges a CSS background by its first layer with a picture, at that layer's `background-size`. It reads the CSS as written in `style` attributes, `<style>` elements and stylesheets from the build's own site, and not CSS a script adds.
- `motion` watches pixels on the first screen only, one picture a second, so motion further down shows only through its animation, style or class. Text a script rewrites, such as a clock, doesn't count as motion, and neither does a change slower than one every 3 seconds.

## Skills

A skill runs when you type its name, or when the agent decides the task calls for it.

- `/product-os:check [folder]` runs `product-os check` and reports the table as printed, with every result that isn't a pass.
- `/product-os:review [what to review]` writes the change to a diff file outside the project, and gives `product-os:reviewer` three things: the spec, or what the change is meant to do in your words; the project's `REVIEW.md`; and the diff file. It leaves out the agent's own account of the change. The reviewer can only read, search and list files, and the reviewer hook covers it too, since its name matches `*reviewer*`. In a tool without subagents, the skill writes the reviewer's prompt for you to paste into a new chat, so the review still comes from a fresh context.
- `/product-os:review-change [pages or sections]` has a fresh `product-os:section-reviewer` compare each section the change can move with its design, at every width, from the pictures, the numbers and the decisions file alone. New misses are reported apart from ones the base already had.
- `/product-os:miss-to-check [what was missed]` turns a defect that got through into a check: a bad case with the defect, a good case with the fix, a command that tells them apart, and a passing `product-os prove`. You approve the write that lists the check. If you decline, or the session can't ask, it gives you the entry to add instead.
- `/product-os:setup-kit` puts the push and commit checks in place, asks for the QA command, the builders and the reviewers, as in [Configure it](#configure-it), and checks the setup, printing N of M with a fix for each miss. Accepting the project's commands is left to you.

## Turn it off

- In one project, for you: `claude plugin disable product-os@product-os --scope local`. For everyone on the project: `--scope project`.
- Everywhere: `/plugin disable product-os@product-os` in a session, or `claude plugin disable product-os@product-os`. `claude plugin uninstall product-os@product-os` removes it.
- One check only: remove the project's entry from your own `product-os-checks.json`, or set its `qa_commands` to `[]`, to turn off the QA check. Set the `reviewer_agents` option to an empty value to turn off the reviewer check.
- The line at session start: set the `session_status` option to `off`. Problems still show.

## Troubleshooting

**"product-os is off: it needs Python 3.9 or later, and none ran."** The hooks found no Python that could run them, so they let every call through and say so once per session. They try `python3` and then `python`, and on Windows `py -3`, `python` and `python3`. Install Python 3.9 or later, or set `PRODUCT_OS_PYTHON` to its full path in the `env` block of your Claude Code settings. A path inside the project is skipped, so a repo can't choose the program that runs its own checks. On Windows, a `python` or `python3` that opens the Microsoft Store is an app execution alias, not Python, and the hooks move past it. On macOS without the command line tools, `/usr/bin/python3` only offers to install them, and the hooks skip it.

**Nothing happens, and `/hooks` says "Only hooks from managed settings run here".** Your organization set `allowManagedHooksOnly` in its managed settings. Claude Code then runs no plugin hooks, these included, unless the managed settings force-enable the plugin.
<!-- github-only -->
To run these hooks, an admin has to register the `zhyuka` marketplace under `extraKnownMarketplaces` and set `"product-os@product-os": true` under `enabledPlugins`, both in the managed settings.
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
To run these hooks, ask whoever manages your Claude Code settings to enable the plugin there.
-->
The skills and the `product-os check` command work either way.

**Windows without Git Bash.** Claude Code runs hook commands in PowerShell there. Each command in `hooks/hooks.json` has two lines. sh runs the first and never reads the second. PowerShell skips the first, since `exec` isn't a PowerShell command, and runs the second, which starts `hooks/run.ps1` in Windows PowerShell to find Python the same way. It passes `-ExecutionPolicy Bypass` for that one script, but an execution policy your organization sets through Group Policy still wins, and then the hooks don't run. Since Claude Code 2.1.299, a PreToolUse hook that fails there blocks the call, so the hooks exit 0 in every case and set `"onFailure": "continue"`.

**A warning on every call that names `.claude/product-os-checks.json` or your own `product-os-checks.json`.** The file has a mistake. For the project file the hooks use the defaults until you fix it; for your own, no QA command counts. Run `/product-os:setup-kit` to rewrite it.

**See what a hook did.** Start Claude Code with `claude --debug` and read `~/.claude/debug/<session-id>.txt`, which has each hook's output and errors.

## What it reads, runs and sends

- The reviewer hook reads the tool call Claude Code is about to make, the project's `.claude/product-os-checks.json` and your own `product-os-checks.json`. It runs before Edit, Write, MultiEdit, NotebookEdit, Bash, PowerShell and Agent calls.
- The QA hook reads the session transcript file that Claude Code passes to Stop and SubagentStop hooks, to find which tool calls ran and whether the QA command passed. It reads only the tool calls and, for each result, whether it failed and the start of its text. It doesn't run the QA command itself.
- At session start, the hook also tells Claude the project's folder and the plugin's folder, every time, whatever `session_status` says. Claude Code names the plugin's folder above each skill it loads, and runs have taken that folder for the project. When one folder holds the other, as when you work on the plugin itself, it names neither.
- The line at session start reads the same settings. To show only once per project, it writes an empty marker file under the plugin's data folder in `~/.claude/plugins/data/`. The QA hook writes one there when it blocks a stop after QA failed, so it blocks that stop only once, and one when it tells you about a change to a file QA runs. With no data folder from Claude Code, it writes the file in the temp folder. If it can't write the file, it blocks every such stop. Each time it writes one, it deletes its own marker files in that folder that are older than 30 days. When no Python is found, the hooks write an empty marker file in the temp folder so the warning shows once per session.
- Each hook runs `sh`, or on Windows without Git Bash runs `hooks/run.ps1` in Windows PowerShell, to find Python, and then runs this plugin's scripts with it. To find Python, `hooks/run.sh` also calls `dirname`, `uname`, `sed`, `head` and `printf`, and `xcode-select -p` on macOS. The hook scripts start no other program, and nothing leaves the machine.
- `product-os check`, `prove` and `accept` run only when you, a skill, a git hook or CI start them. They start the commands the project's checks name, and `git` for `--base`. On your machine `check` starts only the checks you accepted. `prove` writes `.claude/product-os-checks-proofs.json`, and `accept` also writes `product-os-checks-accepted.json` beside your own config. Read a project's checks before you prove or accept them, as you would its tests.
- `product-os gates` runs only when you, a skill, a git hook or CI start it. It opens the build in Chromium and stays on the build's own site in the page's own window. A link that opens a new window or tab isn't stopped yet, so that window can load another site. It presses keys, clicks, drags, turns the mouse wheel and types single letters into a few text fields, so point it at a build, not at a live site where those do something. Before the page's own scripts, it adds one that notes which events each element listens for.
- A hook acts only on the agents your settings name. Every other agent is left alone.

[Privacy](PRIVACY.md) says the same on one page.

## What each hook blocks

`hooks/reviewer_readonly.py` runs before Edit, Write, MultiEdit, NotebookEdit, Bash, PowerShell and Agent calls. When the acting agent is a reviewer, it denies:

- every Edit, Write, MultiEdit and NotebookEdit call
- Bash commands that write files. The hook reads the command the way the shell would, including `bash -c` strings, `eval`, command substitutions, heredocs fed to a shell, `xargs` and `find -exec`. Writes include redirects to files, `rm`, `mv`, `cp`, `touch`, `tee`, `sed -i` and other file tools, git commands that change the worktree, index or refs (including `git fetch`), package installs and build steps such as `npm run build`, formatters run with `--write` or `--fix`, downloads to a file, and inline `python -c`, `node -e`, `ruby -e`, `perl -e` or `php -r` code that writes. A script counts when its flags say so, such as `--write`, `--fix` or `--out FILE`. A command the hook can't parse counts as a write.
- every PowerShell command, because the hook can't parse PowerShell
- spawning a subagent that is not a reviewer, since it could write on the reviewer's behalf

A reviewer may still write to a temp folder outside the project, such as a scratch file in `/tmp`. The hook lets an Edit, a Write or a Bash command through only when every place it can change is in `/tmp`, `/private/tmp`, `/var/folders`, `$TMPDIR`, `%TEMP%` or a user's `AppData\Local\Temp`. A place it can change is more than the path the command names. It counts the source of a link (`ln`, `cp -l`, `cp -s`, `os.symlink` and the like), since the reviewer could write through the link to it; the source a move or an archiver takes away (`mv`, `rsync --remove-source-files`, `tar --remove-files`, `shutil.move`); and the git dir, work tree and index of a git command, so `git worktree add /tmp/w` from the project is denied while `git -C /tmp/w --git-dir=.git checkout .` is allowed. Before it allows a temp target that already exists, it resolves symlinks in the target and its parents, and it denies a target file with more than one hard link, since that link may lead out of temp. `mount` and `bindfs` are denied, since they can map a folder under a temp path. It denies a write anywhere else, in a temp folder inside the project, or in a place the command line doesn't show.

For every agent, reviewer or not, the hook asks you before a call that changes the config file, whether an Edit or Write of it or a shell command that writes, moves or deletes it or its `.claude` folder. That file decides who is a reviewer and which QA commands must pass, so an agent could turn the checks off by editing it. Reads aren't asked about. The setup skill's write shows the same prompt, and you approve it there.

`hooks/qa_before_done.py` runs on Stop and SubagentStop. When the agent is a builder, it reads the session transcript, or the subagent's own transcript, and blocks the stop if the agent wrote files in the project after the last QA command that passed. The project is the folder in `CLAUDE_PROJECT_DIR`, or the hook input's `cwd` when that isn't set. A write counts when any place it lands is inside the project, or when the hook can't tell where it lands, as with a build step, a PowerShell command, or code it can't read. For inline Python (`python -c` or a heredoc fed to python) it reads the code and places a literal target the same way it places a shell redirect, so a write that only lands under `/tmp` or `~/.claude` doesn't count. Relative paths start where the call ran and follow `cd` in the command. So notes in `/tmp` or `~/.claude` don't send a builder back, and a builder that wrote nothing in the project can stop.

A QA run doesn't count when a pipe, `|| true`, a later command or a background run hid its exit code. Most agents pipe QA output. In real transcripts, 96% of QA runs were piped or chained. When the last run was, the hook asks for one unpiped run. That is expected, and costs one extra QA run.

When QA ran on its own after the last write and failed, the hook blocks the first stop. The reason tells the agent to fix the cause and run QA again. If a check can't pass here, such as one that needs a server the session can't reach, it tells the agent to stop and tell you which check fails and why, and not to edit the QA command, the files it runs or `.claude/product-os-checks.json` to get it to pass. The next stop with no new write goes through, and you see a message that QA failed. Running QA again doesn't change that. A new write does, and QA has to run after it.

The files a QA command runs are its words that name a file in the project, such as `qa.py` in `python3 qa.py`. If the builder changes one of them after QA failed, a pass after that doesn't count. The hook blocks the first stop and asks the agent to undo the change, or to stop and tell you what it changed and why. The next stop with no new write goes through, with a message that names the file. That message ends it, so a later pass counts again, and a later failure starts over as above. Changing those files before QA has failed, or after it passed, is normal work.

Both hooks leave every other agent alone. In this example, run from the repo root, a `code-reviewer` subagent tries `sed -i 's/console.log(.*);//' build/app.js`:

```
$ python3 hooks/reviewer_readonly.py < tests/fixtures/hooks/deny-reviewer-bash-write.json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "product-os blocked this Bash call: it runs sed -i. The project config lists code-reviewer as a reviewer, and reviewers are read-only, so don't try it another way. Finish the review: in your answer, name each problem you found and the change you would make, for the person to apply."}}
```

Claude Code cancels the call and gives the reason to the agent. In the next one, the main session is a builder. It edited a page, ran `npm run check 2>&1 | tail -5`, and is about to report that QA passed:

```
$ python3 hooks/qa_before_done.py < tests/fixtures/hooks/block-main-qa-piped.json
{"decision": "block", "reason": "product-os: QA output went through a pipe or into another command, so its exit code was not seen. The project config lists the main session as a builder, so run `npm run check` after your last edit and get it to pass before you stop. Run it on its own, not through a pipe or with || true, so its exit code counts."}
```

Claude Code keeps the agent working and hands it the reason as its next instruction.

## How this compares

- [Superpowers](https://github.com/obra/superpowers) has a `verification-before-completion` skill that asks the agent to check its work before it says it's done. This plugin's stop hook refuses the stop when the agent didn't. The two work together.
- [TDD Guard](https://github.com/nizos/tdd-guard) is a PreToolUse hook that blocks code written before a failing test, with a model judging each change. This plugin makes no model calls, and it checks that QA passed after the last edit rather than test-first order.
- [CC Safety Net](https://github.com/kenryu42/cc-safety-net) blocks destructive git and file commands for every agent. This plugin blocks every write, but only for the agents you name as reviewers, and leaves builders free.
- In a subagent's frontmatter, `tools` or `disallowedTools` can take the write tools away from an agent you wrote. This plugin also covers agents you didn't write, such as other plugins' agents, and lets a reviewer keep a shell for reading.

## Limitations

- The read-only hook reads the command line, not what programs do. It reads inline code given with `python -c`, a heredoc or `node -e`, and counts it only when it writes; for inline Python it places a literal target and counts a write whose target it can't place, a subprocess, `exec` or `eval` it can't read, or code that doesn't parse. A script file, a `make` target or a program whose name is built at run time can still write unseen. For a strict reviewer, set `reviewer_shell` to `block-all`, or leave write tools out of the subagent's `tools` list.
- The config ask matches the file by path. A command that changes every file without naming one, such as `git checkout -- .` or `rm -rf .`, doesn't trigger it.
- The QA hook trusts the QA command's exit code. A QA command that checks nothing will pass. Point `qa_commands` at something that refuses empty builds, such as `product-os check build`.
- The QA hook counts Edit, Write, MultiEdit and NotebookEdit calls, and recognizable shell and PowerShell writes, as edits. An Edit or Write that failed, and a command Claude Code refused to run, did not change anything, so they don't count. Neither does a git command that changes only refs, the index or a remote, such as `git fetch`, `git commit` or `git push`. A pre-commit hook that rewrites files is the exception it can't see. Files written by a subagent the builder starts, or by an MCP tool, don't count either.
- Claude Code documents where the transcript is, not its format. The QA hook reads the format Claude Code 2.1.136 to 2.1.288 writes, and reads it from the end, so a stop on a transcript of hundreds of megabytes takes well under a second. If it finds nothing it can read, or reading takes longer than 15 seconds, it lets the agent stop and shows a warning that the check did not run. Claude Code writes the transcript asynchronously, so the hook waits up to a second for a QA result that is not in the file yet. If the result still isn't there, it blocks once.
- A shell command longer than 128 KB counts as a write and never as the QA step, because reading it would take the shell parser too long.
- On a transcript over 64 MB, a block may say the QA command did not run after the last file write instead of saying whether it ever ran.
- After QA fails, the hook blocks one stop per write, so a builder that keeps editing and failing QA goes back after each edit. Claude Code's own cap of eight stop-hook blocks in a row doesn't end that, since the count starts over each time the agent calls a tool. Press Esc to stop it, or take the command out of `qa_commands`.
- The hook finds the files a QA command runs only in the command's own words. `npm run check` and `make check` name none, and a file that `qa.py` imports isn't one. It sees a change to them through an Edit or Write call, or a shell command or inline Python that names the file. It doesn't see a change through a glob, a path built at run time or a PowerShell command, and on a transcript over 64 MB it looks back at most 64 MB for the QA failure before the change.
- The plugin fails open. When no Python runs it or a hook crashes, the call goes through and you see a warning. Failing closed would block every agent's writes whenever Python is missing, so the plugin doesn't set `"onFailure": "block"`.
- Plugin options are per user and apply to every project, so the QA commands you accept live in your own `product-os-checks.json`, keyed by project folder. A key for a repository's main checkout also covers its git worktrees. A clone in a folder no key covers needs the setup skill once.
- A project's `.claude/product-os-checks.json` can only add reviewers and builders, which makes the checks stricter. A project's own Claude Code settings can do more: they can turn any plugin off. Read them in a repo you don't trust.
- The build scorer reads static HTML, CSS and JS only. Any other build comes out UNSCORABLE.
- A proof is only as good as its cases. A bad case that doesn't hold the real defect proves a check that would miss it. `--base` keeps a change from dropping or editing the cases the base has, but it can't judge a new case.
- With `--run-listed` and without `--prove`, `product-os check` trusts the project's stored record, which an agent could write by hand. On your machine it trusts only what you accepted. In Claude Code the hooks ask you first when an agent edits the record with a file tool or a shell command that names it, or runs `--run-listed`, however it is shortened, or `prove` on a check you haven't accepted, and refuse an agent's `accept` and its edits to what you accepted. They can't see code they can't read writing either file.
- A check's fingerprint covers the files its command names, such as `checks/no_print.py`, but not what those files import or call. A change to a module the script imports doesn't make the check unproven.
- `--base` reads the base from the local git history. In CI, the checkout needs that history: `fetch-depth: 0` in GitHub Actions, `fetchDepth: 0` in Azure Pipelines. The templates set it.
- A check's command runs without a shell. For a pipe or a redirect, put it in a script and name the script.

## Use the checks without Claude Code

<!-- github-only -->
```
pip install git+https://github.com/zhyuka/product-os
product-os accept
product-os check
product-os check path/to/folder
```
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
From this folder:

```
pip install .
product-os accept
product-os check
product-os check path/to/folder
```
-->

With no folder, `product-os check` runs the project's own checks you accepted, as in [A project's own checks](#a-projects-own-checks). With a folder, it runs three built-in checks on it. The folder is a build folder or a run folder. A run folder holds a `run.json` that records one agent run, and can hold an `artifacts/qa_report.json` in the format `product_os/step_ran.py` writes:

```json
{
  "agent": "page-builder",
  "role": "builder",
  "build": "build",
  "claims": ["QA passed"],
  "qa_commands": ["npm run check"],
  "tool_calls": [
    {"tool": "Write", "input": {"file_path": "build/index.html"}},
    {"tool": "Bash", "input": {"command": "npm run check"}, "ok": true}
  ]
}
```

`role` is `builder` or `reviewer` and is the only required field. `build` is the build folder, relative to `run.json`, and defaults to `build`. `tool_calls` use Claude Code's tool names and input fields, so you can copy them out of a transcript. `ok` is `false` for a failed call and `null` when the result is unknown. A reviewer run can add `build_sha256_before`, the build's hash before the review.

The command runs three checks and prints pass, fail or skip for each, with the reason.

- **build score.** The guarded score of the build has to exist and reach 0.75.
- **read-only.** For a reviewer, no tool call may write files, and the build hash has to match `build_sha256_before` when it is given.
- **step ran.** A "QA passed" claim needs evidence. That is a QA report that names this build, or a QA command that succeeded after the last file write with its exit code in plain view. Every piece of evidence given has to hold, and a claim with none fails.

A check with nothing to read is skipped and says why. A skip never counts as a pass. The exit code is 0 when no check failed, 1 when one did, and 2 when the input can't be read. `examples/runs/` has a passing and a failing run for each of the last two checks:

```
$ product-os check examples/runs/cheap-builder
Release checks for examples/runs/cheap-builder
  check        result  detail
  build score  pass    1.00
  read-only    skip    role is builder, not reviewer
  step ran     fail    QA command 'npm run check' never ran
  2 of 3 checks ran: 1 passed, 1 failed.
```

## Why these checks

Each check here answers a way coding agents fail when they build from a design:

- A rule-based scorer can rank an empty build above real ones, because most of its rules only look for problems.
- A reviewer agent told to stay read-only can edit code anyway.
- A cheaper model can skip the QA step and report success.
- A build can match its design at rest and have none of the states the design draws for it.

## The three failures, as a demo

<!-- github-only -->
```
git clone https://github.com/zhyuka/product-os
cd product-os
python -m product_os demo
```
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
From this folder:

```
python -m product_os demo
```
-->

The demo runs each check with stub agents: small deterministic Python functions that stand in for a model, with no LLM calls and no network. It reads the example builds in the plugin's folder, and exits non-zero if any check fails calibration. Every number it prints comes from the stubs and the four example builds. Its 2 of 91 comes from a seeded edit rate, not from a model.

1. **An empty build passes most rules.** `product_os/vacuous.py` scores a static web build against eight rules, such as hex colors, image alt text and heading order. Seven of them only look for problems, so the empty build passes them and scores 0.88, above the mediocre build at 0.62 and the broken one at 0.25. `guarded_score()` refuses to score a build with no visible HTML text, and says why.
2. **A read-only reviewer edits code.** `product_os/readonly.py` runs a stub reviewer on fresh copies of a workspace and hashes every file before and after. Its prompt says not to write, and in a small seeded share of runs it writes anyway. Giving the same reviewer a tool layer whose write raises an error stops it. An instruction is not a permission, and the plugin's PreToolUse hook applies the same idea in Claude Code.
3. **A step reports success without running.** `product_os/step_ran.py` accepts "QA passed" only when the QA report names the SHA-256 of the exact build it checked and is not older than that build. The verifier rejects the stub that only says it passed, in every run, and accepts the one that ran QA.

```
1. Vacuous pass: naive score vs guarded score
  build     naive  rules that inspected nothing  guarded
  good      1.00   0 of 8                        1.00
  empty     0.88   8 of 8                        UNSCORABLE (no HTML files)
  mediocre  0.62   2 of 8                        0.62
  broken    0.25   0 of 8                        0.25
  Naive scorer ranks 'empty' above 2 of 3 real builds (mediocre, broken). The guard refuses to score it.

2. Read-only audit: 91 runs of a stub reviewer told to stay read-only
  2 of 91 runs edited files despite a read-only instruction:
    run 36: added REVIEW_NOTES.md
    run 40: changed index.html
  tools given      runs that edited files  writes blocked
  read and write   2 of 91                 0 of 91
  read-only layer  0 of 91                 2 of 91
  Same prompt both times. The instruction did not stop the writes; the tool layer did.

3. Step-ran verification: 33 runs per stub agent
  agent        claimed QA passed  accepted  rejected  verifier reason
  qa_agent     33 of 33           33 of 33  0 of 33   report matches this build
  cheap_agent  33 of 33           0 of 33   33 of 33  no QA report

4. Calibration: one planted bad case and one known-good case per check
  check              planted bad caught  known good passed
  vacuous guard      1 of 1              1 of 1
  read-only audit    1 of 1              1 of 1
  step-ran verifier  1 of 1              1 of 1
  3 of 3 checks passed calibration.
```

<!-- github-only -->
## Testing

A check counts only after it catches a planted bad case and passes a known-good one. Each one reports counts, not a verdict. Run the tests with `python .github/run_tests.py`, which runs them in one process per CPU, up to eight. On your machine it skips a test that passed before when nothing its module's tests read has changed since, and says so on its line. From Python 3.12, an edit to a function those tests never ran doesn't count, except in a file a browser test runs through, which counts whole. A test that starts a program always runs. Playwright's driver, which runs the browser, doesn't count. Pass `--no-cache` to run every test, as CI does.

- `product_os/calibrate.py` plants one bad case and one good case for each demo check, and demo part 4 prints the result. The tests show that a check which never objects, or always objects, fails calibration.
- `tests/test_check.py` calibrates `product-os check` on the four runs in `examples/runs/`. CI also runs the command on them, and fails if a good run doesn't pass or a bad run doesn't fail.
- `tests/test_design.py` checks the baseline: a frame moved on the canvas keeps its hash, any other edit changes it, and hidden layers are left out. `tests/test_exercise.py` exercises a page that has every state its design draws, and planted copies that each lack one. The full page has to pass, and each planted copy has to fail on its own state and no other. It needs Playwright and Chromium and is skipped without them, and CI doesn't install them yet.
- `tests/test_gates.py` serves a good page and planted copies that each break one gate. The good page, and copies that are still good, such as one with a field that takes focus as it loads or a clock a script rewrites, have to pass, and each planted copy has to fail its own gate and no other. It needs Playwright and Chromium too.
- `tests/test_project.py` holds `product-os prove` to the same rule. It fails a check that never objects and one that always does, and proves the example's. It also covers the add-never-remove rule, with your own checks and with `--base` on real git history. CI runs `product-os check --prove --run-listed` on `examples/project/`, and fails if a copy with the planted bad case passes.
- Each hook fixture's name starts with the answer it should get, such as deny, block or allow. `tests/test_hooks.py` pipes every fixture through its hook script, and fails unless each hook both blocks and allows something across the set.
- `tests/test_launcher.py` runs every command in `hooks/hooks.json` on every fixture, from a plugin folder with spaces in its path, in each shell it finds: sh, dash and bash, Git Bash, pwsh and Windows PowerShell. It also checks that a Store alias or an old Python is skipped, and that with no Python the call goes through with one warning per session. CI runs it on Ubuntu, macOS and Windows.
- `tests/test_frontmatter.py` fails if git would check a text file out with CRLF, or if a skill's or agent's frontmatter holds a value YAML reads only when the lines end in LF, such as an unquoted description with `: ` in it. Claude Code drops every field of such a frontmatter on a Windows clone. CI also runs `claude plugin validate` on a Windows checkout.
- `tests/test_readonly.py` lists shell commands that write files and commands that don't. The classifier has to catch every one of the first and pass every one of the second.
- These tests feed recorded inputs to the scripts and don't start Claude Code. `evals/` runs with and without the plugin through `claude plugin eval`, and `.github/workflows/live.yml` runs it in CI on each release tag, as the next section says.
- A skill ships only if it beats the same frontmatter with a one-line body, or ties it at lower cost. `evals/shipping_rule.py` runs the cases tagged `skill` on the plugin and on a copy whose skill bodies are one line, and prints both. The review and miss-to-check skills each have a case with a planted defect and one without.
- `evals/triggers.py` runs about 20 queries per skill, half that should fire it and half near misses that shouldn't, 3 times each. The queries are split into train and test, and a description is tuned only on the train half. The runs leave out your own user settings, skills and CLAUDE.md, so the score doesn't depend on what else you have installed. Claude Code's built-in skills, such as code-review, still compete. A Skill call that Claude Code refused doesn't count as firing. A skill that sets `disable-model-invocation`, such as `retro`, is named as not run, since only a person may start it.

### CI and what it costs

Two workflows make paid model calls, and both run only when a tag starting with `v` is pushed. They never run on a branch push, on a pull request (a fork's included) or by hand. `release.yml` runs only on a release tag such as `v0.1.4`. A probe tag such as `v0.1.4-probe.1` runs only `live.yml`'s Ubuntu probe, for up to $0.25. The other two runners start, post a notice and spend nothing.

- `live.yml` runs the evals on three runners, each capped by `--max-cost-usd`. macOS runs every case for up to $8.25. Ubuntu 24.04 runs only `sandbox-write`, a probe that checks Bash can write in the run's folder and in a `mktemp` folder, for up to $0.25. In v0.1.4 the probe wrote neither file on `ubuntu-latest`, which has been moving to Ubuntu 26, so the job pins 24.04. Windows runs the `no-shell` cases for up to $0.50. That's at most $9 a tag. On Linux, `claude plugin eval` denies sandboxed writes under the temp folder that holds its runs, so every case that writes a file measured the sandbox there instead of the plugin ([anthropics/claude-code#104631](https://github.com/anthropics/claude-code/issues/104631)). On macOS it exempts the runs' folder, and shell writes worked there in every run of v0.1.2 and v0.1.3. When the probe passes on Ubuntu, Ubuntu can run every case again. Each job's step summary gives every case's score with and without the plugin, why each grader failed, and what each failed run did: its tool calls, the calls it was denied and the end of its last reply. It also counts the runs with the plugin that took the plugin's own folder for the project. On Windows, Claude Code turns off the cache that lets its processes share one exchanged token, so every process presents the same single-use GitHub token and only the first is accepted. Until that changes, a Windows job where no run signed in passes with a notice saying so. On Ubuntu and macOS the same outcome means the federation rule is wrong, and the job fails.
- `release.yml` has one agent follow `INSTALL.md`, capped at $1 by `--max-budget-usd`.

So a release tag costs at most $10. `tests.yml` and `install.yml` run on every push and pull request and make no model call. Every job runs on GitHub's standard hosted runners, never larger ones. `tests/test_workflows.py` fails if a job that asks for an id token can run on a pull request, if a workflow names an API key, or if a job asks for a runner outside the standard set. It also fails if a probe tag could start `release.yml` or a paid step anywhere but Ubuntu.

The paid jobs sign in through [Anthropic workload identity federation](https://platform.claude.com/docs/en/manage-claude/wif-providers/github-actions), so no key is stored. Each job asks GitHub for an OIDC token with the audience `https://api.anthropic.com` and writes it to the file `ANTHROPIC_IDENTITY_TOKEN_FILE` names, and Claude Code exchanges it. A token lasts about 5 minutes and can be exchanged once. All the Claude Code processes one `claude plugin eval` starts share one exchanged token, which lasts about 10 minutes. A process still running after that exchanges again, and another may present the same token, which fails as `jti_reused`. So `live.yml` runs each case as its own `claude plugin eval`, through `evals/live.py`. Before each case it writes a new token and gives the case an empty federation cache folder. `release.yml` runs a single process, so it writes a fresh token every 2 minutes while that runs. Each write prints when its token was issued and expires, and whether it changed. A write that gets no token keeps the last one and warns. The rule, organization, service account and workspace come from four repository variables: `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID`, `ANTHROPIC_SERVICE_ACCOUNT_ID` and `ANTHROPIC_WORKSPACE_ID`. With any of them unset, the paid jobs are skipped with a notice. On Anthropic's side, the federation rule accepts only a push of a `v` tag from this repository.

The rule's `subject_prefix` has to match how the token's `sub` claim starts, and GitHub writes `sub` in one of two formats. Read your repository's format before you write the rule:

```bash
gh api repos/OWNER/REPO/actions/oidc/customization/sub
```

- With `use_immutable_subject` false or absent, `sub` starts with the names alone. A tag push gives `repo:OWNER/REPO:ref:refs/tags/v0.1.1`.
- With `use_immutable_subject` true, each name carries its numeric ID, and the response's `sub_claim_prefix` is how `sub` starts. A tag push gives `repo:OWNER@OWNER-ID/REPO@REPO-ID:ref:refs/tags/v0.1.1`.

GitHub gives the second format to repositories created since mid-2026, and an older one can opt in. This repository uses it. With `use_default` false, `include_claim_keys` lists the claims `sub` is built from instead. Each paid job's "Fetch GitHub OIDC token" step prints the token's `sub`, `ref` and `event_name`, never the token, so a mismatch shows in the job log. On a refused sign-in, the Console's authentication history names the check that failed, such as `match_subject_prefix`.

Where federation isn't available, as in a fork, an API key works instead. Store it as a repository secret named `ANTHROPIC_API_KEY`, and set `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` in the env of the step that runs `claude`. This repository doesn't, and its workflow test refuses it. An API key, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` or an `apiKeyHelper` each outranks federation, so a job that sets one isn't federated. `claude --bare` doesn't read the federation variables either.

<!-- /github-only -->
## License

MIT. See `LICENSE`.
