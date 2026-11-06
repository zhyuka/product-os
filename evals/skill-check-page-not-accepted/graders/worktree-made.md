---
# Precondition for worktree-removed: a detached worktree was made for the agent.
type: regex
target: trace
pattern: '"name":\s*"Bash",\s*"input":\s*\{[^\n]*worktree add --detach'
---
