---
type: llm
weight: 2
focus: last_message
---
.claude/open-questions.md holds five open questions, Q-1 to Q-5. The triage skill lists them tersely, then presents up to four in full, each as its own question with its own decision options, and waits for the person's decisions before going on.

PASS if the reply presents at least one and at most four questions in full (each with its fields, such as why it matters, who it depends on and its evidence), gives each presented question its own decision options such as Resolve, Defer, Skip, Close won't fix or Moot, and asks for the person's decision on each. One shared list of those options that asks for a decision on each question counts. A one-line list of all five before them is fine.
FAIL if it presents all five in full, offers one decision for several questions together, offers options for a question it hasn't shown in full, decides any question itself, says a question is resolved, or is empty.
