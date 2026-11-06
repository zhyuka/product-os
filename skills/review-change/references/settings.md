# Settings review-change reads

All of them live in the project's `.claude/product-os.json`, or the person's own
`~/.claude/product-os.json`. Every key is optional. A key ending in `_cmd` from the project's file
runs only once the person accepts it on their machine with `product-os kit_config accept <key>`.

| Key | What it holds | Without it |
|---|---|---|
| `app.dir` | folder the build, serve and compare commands run from, relative to the project root | the project root |
| `app.widths` | the widths the project ships, in CSS px, such as `[1440, 390]` | the widths the design has frames for, named in the report |
| `app.build_cmd` | the production build | no fresh build: the review uses pictures the person gives, or doesn't run |
| `app.serve_cmd` | serves the build like production; `{port}` is filled with a free port | as above |
| `app.compare_cmd` | pairs each section with its design frame, then writes a design picture, a build picture and a numbers file per section; `{url}`, `{width}`, `{out}` and `{frame}`, the design frame's link for that page and width, are filled in | screenshots and design pictures only, and the reviewer judges sizes by eye |
| `app.decisions` | the file of design decisions the reviewer may cite as DECIDED, with an id each | none; nothing counts as DECIDED |
| `app.plan_stale_cmd` | checks a route's plan against its design: `{route}`. Exit 1 stale, printing the command that re-plans; 2 didn't run | the plan is read as it is |
| `app.frames` | the file that names each route's design frames when its plan doesn't | the person's pictures |

Paths are from the project root, not from `app.dir`.

The numbers file explains its own columns: build boxes against design boxes, with the rows over
the project's limits flagged.
