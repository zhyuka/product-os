# Builders and reviewers

The plugin's Claude Code hooks read these from `.claude/product-os-checks.json`, where they run.

- Builders: agents that must pass the QA command after their last edit before they stop. The main
  session is `main`; the default is agents whose names match `*builder*`.
- Reviewers: agents that may not write files. The default is `*reviewer*` and `*page-qa`. Ask
  whether a reviewer may still run shell commands that don't write files (`block-writes`, the
  default) or no shell commands at all (`block-all`).

An agent's name is the `name` in its frontmatter, and a plugin's agent is `plugin-name:agent-name`.
Patterns are shell-style globs, matched without case.

The project file takes only `reviewer_agents`, `reviewer_shell`, `builder_agents`, `qa_commands`
and `checks`. It can add reviewers and builders and make `reviewer_shell` stricter, but can't take
any away from the person's plugin options, and its `qa_commands` only propose a command:

```json
{"builder_agents": ["main", "*builder*"], "qa_commands": ["<the check command>"]}
```

The person's own file holds only `projects`, keyed by the project's absolute path. A key covers
the folders under it and can start with `~`. A `*` matches any characters, slashes included, so
`~/code/shop*` also covers worktrees such as `~/code/shop-fix`; offer that when the project has
worktrees. When several keys match, the longest wins. A builder that runs the QA command through a
pipe or with `|| true` doesn't count as having run it.
