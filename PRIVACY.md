# Privacy

Product OS runs on your machine, inside Claude Code, or as the `product-os` command in a shell, a git hook or CI. It has no server of its own and collects nothing. It opens a connection only when you run a part that needs one:

- The Figma tools call Figma's REST API, `api.figma.com`, with the token you set. The Azure DevOps tools call `dev.azure.com` with your PAT. `recall` asks both only when their token is set. Each sends what its command names: a file key and node ids to read, or the comment or work item you wrote.
- The browser tools (`figma_attach`, `signed_in_browser`, `shot_gpu`, `backdrop_group_check`, `sliver_sweep`, `pw_temp`) and the `product-os design exercise` and `product-os gates` commands start Chromium through Playwright. It opens the page you name, along with whatever that page loads.
- Nothing else connects anywhere. The hooks and the checks below make no network call.

Tokens come from environment variables or your OS keychain. The tools read them into the process that needs them and never print, log or write them.

The rest of this page covers the hooks and checks, which run in every session once the plugin is enabled: what they read, what they write, and what they send.

## What the hooks and checks read

- The reviewer hook reads the tool call Claude Code is about to make, such as the file an Edit changes or the command a Bash call runs, the project's `.claude/product-os-checks.json`, and your own `product-os-checks.json` in your Claude Code config folder, which lists the QA commands you accepted for each project folder.
- The QA hook reads the session transcript file that Claude Code passes to Stop and SubagentStop hooks. The transcript can hold anything you or the agent typed. The hook reads only the tool calls and, for each result, whether it failed and the start of its text, to decide whether the QA command passed after the last file write. It keeps nothing from them.
- The line at session start reads the same two files and the plugin options you set with `/plugin configure`.
- `product-os check` and `product-os prove` read the checks listed in those two files, the files each check's command names and each check's cases, and `.claude/product-os-checks-proofs.json`. `prove --check FILE` also reads the checks in that file. With `--base`, they read the project file and the cases at that git ref through `git`.

## What the hooks and checks write

`product-os prove` writes `.claude/product-os-checks-proofs.json` in the project: for each check it proved, a hash of the check, and each case's path, hash and exit code. `product-os accept` writes the same records to `product-os-checks-accepted.json` in your Claude Code config folder, under the project's folder path. The hooks write only empty files, named by hashes:

- one per project in the plugin's data folder under `~/.claude/plugins/data/`, so the line at session start shows once
- one per stop the QA hook blocks once, and one per change to a file the QA command runs that it tells you about, in the same folder, or in the temp folder when there is none. The hook deletes its own files there after 30 days.
- one per session in the temp folder when no Python is found, so that warning shows once

Claude Code deletes the plugin's data folder when you uninstall the plugin.

## What the hooks and checks send

Nothing. The hooks' Python code imports no network module, and the hooks start no other program. To find Python, each hook runs `sh`, or Windows PowerShell on Windows without Git Bash, and `hooks/run.sh` calls `dirname`, `uname`, `sed`, `head` and `printf`, and `xcode-select -p` on macOS.

`product-os check` and `product-os prove` start the commands your project's checks name, and `git` for `--base`. What those commands do is up to the project. Read a project's checks before you run them, as you would its tests.

The `product-os design` commands don't call Figma. `design import` and `design drift` read answers from Figma's REST API that you saved, and write the baseline folder you name. `design exercise` is the only part that opens a connection, and only when you run it. It starts Chromium through Playwright and opens the URL you give it, which loads whatever that page loads. With `--serve`, it serves the folder you name on 127.0.0.1, which only this computer can reach, while it runs. `--evidence` writes screenshots of the page to the folder you name.

`product-os gates` opens a connection the same way, and only when you run it: Chromium through Playwright, to the URL you give it, or to the folder `--serve` serves on 127.0.0.1. Before the page's own scripts, it adds one that notes which events each element listens for. It presses keys, clicks, drags, turns the mouse wheel and types single letters into up to 5 text fields, each time on a fresh load, so point it at a build, not at a live site where those do something. It stops a click or a key from loading another site in the page's own window. A link that opens a new window or tab isn't stopped yet, so that window can load another site. A file picker a click opens is given no file, and a browser dialog is dismissed and a download cancelled before it's saved. `--json` writes its findings to the file you name.

The files under `.github/` are this repository's CI on GitHub. They don't run on your machine. The templates under `ci/` run only where you copy them, and install product-os from GitHub there.

## Questions

Open an issue at https://github.com/zhyuka/product-os/issues.
