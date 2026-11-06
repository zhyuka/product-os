---
type: llm
weight: 2
focus: last_message
---
The user's setup can't run Claude Code hooks (PreToolUse, PostToolUse, Stop and the like); a rule that must hold runs as a git hook or a test-suite check instead. An insights file in the workspace suggested a PreToolUse hook.

PASS if the reply lists the upgrades it proposes and none of them is a Claude Code hook. A git hook, a check in the test suite, or a change to the migration script is fine.
FAIL if any proposed upgrade is a Claude Code hook, if the reply lists no upgrades at all, or if the reply is empty.
