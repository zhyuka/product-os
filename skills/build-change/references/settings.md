# Settings build-change reads

All live in the project's `.claude/product-os.json`, under `app`, which the push check and the review and QA skills read too. `product-os kit_config` prints them merged with the person's own file. Each key
ending in `_cmd` runs a command, so from the project's file it counts only once the person accepts
it on their machine (`product-os kit_config accept app.<key>`); until then the listing marks it
NOT ACCEPTED and the skill skips that part and says so.

| Key | What it is | When it's unset |
|---|---|---|
| `app.widths` | the widths the project ships, in CSS px, widest first, such as `[1440, 390]` | ask the person |
| `app.dir` | the folder every command runs from, relative to the project root | the project root |
| `app.rules` | the project's build rules file or files, read before building | the project's `CLAUDE.md` alone |
| `app.decisions` | the file of recorded decisions to differ from the design, by component and topic | no decisions; ask before building a difference |
| `app.build_cmd` | builds the app as production does | the build can't be served: stop and say so |
| `app.serve_cmd` | serves the built app; `{port}` in it becomes the port | stop and say so |
| `app.check_cmd` | the project's own check command, such as its test and lint run | report "did not run" |
| `app.screenshot_cmd` | takes a full screenshot of a URL at a width: `{url}`, `{width}`, `{out}` | screenshot with Playwright |
| `app.measure_cmd` | measures an element's box and type on a URL at a width: `{url}`, `{width}`, `{selector}` | measure in the browser with Playwright |
| `app.contrast_cmd` | grades text contrast for a section at a width: `{url}`, `{width}`, `{selector}` | report the contrast grade as "did not run" |
| `app.component_lookup_cmd` | names the file that already draws a design component: `{node}`, its node id | search the code for the component's name |
| `app.plan_cmd` | writes a route's plan from its design: `{file_key}`, `{section}` | no route plans |
| `app.plan_stale_cmd` | checks a route's plan: `{route}`. Exit 0 current, 1 stale (it prints the command that re-plans), 2 didn't run | read the plan as it is |
| `app.frames` | the file that names each route's design frames when its plan doesn't, from the project root | ask for the frames |
| `tracker.server` | the MCP server the tracker goes through, such as `azure-devops` | the `ado` skill when `ado.project` is set, else no tracker |

Paths are from the project root, not from `app.dir`.
