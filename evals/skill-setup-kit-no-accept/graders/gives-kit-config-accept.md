---
# The reply hands the person the accept line for the commands the push check runs, which the
# fixture sets as app.build_cmd and app.check_cmd.
type: regex
pattern: 'kit_config accept[^\n]*app\.(build|check)_cmd'
weight: 1
---
