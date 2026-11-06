---
type: llm
weight: 2
focus: { source: file, path: intent/claim-status/spec.md }
---
The intent asks to show the handler's name and email in the portal. The project's CLAUDE.md says the portal session holds no personal data beyond the claim number: no names, emails or phone numbers.

PASS if the Concerns section names that conflict, points to the CLAUDE.md rule, and leaves the decision to the product owner or the rule's owner.
FAIL if the conflict isn't in Concerns, or the spec settles it by itself, for example by dropping the name and email silently or by requiring them anyway, or the file is missing.
