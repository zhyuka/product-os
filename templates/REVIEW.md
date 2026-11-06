# Review rules for <project>

The reviewer reads this file before it reviews a change here. Keep it short: a rule that a check
already enforces belongs in the check, not here. Replace each `<...>` and delete what doesn't apply.

## What a reviewer checks

- The change does what its spec, or the ask, says, and nothing it doesn't.
- <the behaviour that must never break, such as sign-in, payments or saved data>
- <the inputs and paths nobody tries: empty, missing, very large, another language, offline>
- <the project's rules on security, privacy and personal data, with where they're written>
- <the parts that must stay one copy, such as shared components or one source for each value>
- Tests or checks cover what changed, and each new check has failed a planted bad case.

## What blocks a change

A finding blocks the change until it's fixed, or until <who decides> says it ships with the finding
filed as its own item.

- It doesn't do what the spec or the ask says.
- It breaks something that worked, or fails on an input in the list above.
- <a rule above whose breach blocks, such as personal data in a log>
- The reviewer isn't sure whether it's a defect. Unsure counts as blocking until someone checks.

## What is POLISH

Listed and never blocking: the author may fix it now or later.

- <naming, wording and comments>
- <style that no linter enforces>
- <a simpler way to write code that works>

## Out of scope

- <what reviewers here don't judge, such as visual match to the design, which has its own review>
