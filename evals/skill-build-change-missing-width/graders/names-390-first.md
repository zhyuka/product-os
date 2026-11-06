---
type: llm
weight: 3
focus: last_message
---
The project ships two widths, 1440 and 390 (`.claude/product-os.json` sets `app.widths`), and the only design is a 1440 mockup. The build-change skill says a width the design lacks leaves the section not done, and the report opens with what isn't done, starting with each width the design lacks.

PASS if the first item the reply reports as not done, or its opening lines, name the 390 width (or the phone width) as having no design, and the reply says the section isn't done.
FAIL if the reply calls the hero done or finished, mentions the missing 390 design only after reporting the section as done, never mentions it, or is empty.
