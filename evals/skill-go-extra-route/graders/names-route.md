---
type: llm
weight: 2
focus: last_message
---
The project's .claude/product-os.json adds a go route that sends a design link or frame to build to the project's own skill, site-pages. site-pages isn't loaded in this workspace. The name site-pages appears only in that settings file, so a reply that names it read the project's routes.

PASS if the reply names site-pages as where the project routes this request, and says it isn't loaded, isn't available or wasn't found.
FAIL if the reply never names site-pages, or says it loaded or ran build-change or build-from-design instead, or is empty.
