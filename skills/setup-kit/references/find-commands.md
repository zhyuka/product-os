# Finding a project's build and check commands

Use these only when `.claude/product-os.json` doesn't set `app.build_cmd` and `app.check_cmd`.
Note the file each candidate came from, and offer them to the person; they choose.

- `package.json` scripts named `build`, and for the check `check`, `verify`, `test`, `lint` or
  `typecheck`. Use `npm run <name>`, or `pnpm` or `yarn` when the project has `pnpm-lock.yaml` or
  `yarn.lock`. A `package.json` below the root is the app folder: set `app.dir` to it.
- `Makefile` targets named `build`, `check` or `test`: `make <target>`.
- `tox.ini`: `tox`. A pytest setup (`pytest.ini`, `[tool.pytest` in `pyproject.toml`,
  `[tool:pytest]` in `setup.cfg`, or `test_*.py` files): `python -m pytest`.
- `Cargo.toml`: `cargo build`, `cargo test`. `go.mod`: `go build ./...`, `go test ./...`.
- A step in `.github/workflows/*.yml` or a pipeline file that runs one of the above.

Prefer the one command that runs the whole check, such as a `check` script that runs lint and
tests, over `test` alone. The push check runs each command in `app.dir` without a shell, so a
pipe, a redirect or `|| true` in it is just a word, and the command has to exit non-zero on a
failure. A gate that prints a line with DID NOT RUN fails the push even when it exits 0.

The settings keys, in `.claude/product-os.json`:

```json
{"app": {"dir": "web", "build_cmd": "npm run build", "check_cmd": "npm run check"},
 "setup": {"checks": [{"label": "Playwright", "cmd": "python -c \"import playwright\"",
                       "fix": "python -m pip install playwright"}],
           "tokens": [{"name": "FIGMA_TOKEN", "fix": "make a read-only token in Figma's settings",
                       "optional": true}]}}
```

`setup.checks` are extra lines for the setup check; each runs in `app.dir` and passes on exit
0, and an `"optional": true` one never fails the run. `setup.tokens` names the tokens the project's
tools read; the check says only whether each is set. The `_cmd` keys and `setup.checks` run
commands, so from the project's file they count only once the person accepts them.
