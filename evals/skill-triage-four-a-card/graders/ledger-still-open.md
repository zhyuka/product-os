---
# Nobody answers in an eval run, so no decision exists: all five questions are still open, and
# none was resolved, closed or marked moot.
type: regex
weight: 2
target: { source: file, path: .claude/open-questions.md }
pattern: '^(?![\s\S]*Status: (?:resolved|won.t fix|moot))(?=[\s\S]*Q-1:[^#]*Status: open)(?=[\s\S]*Q-2:[^#]*Status: open)(?=[\s\S]*Q-3:[^#]*Status: open)(?=[\s\S]*Q-4:[^#]*Status: open)(?=[\s\S]*Q-5:[^#]*Status: open)'
---
