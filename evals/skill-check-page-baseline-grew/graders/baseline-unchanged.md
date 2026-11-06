---
# QA never writes the baseline: qa-baseline.json is byte for byte what the scaffold committed.
type: regex
weight: 2
target: { source: file, path: qa-baseline.json }
pattern: '^\[\n  \{\n    "check": "assets",\n    "route": "/index\.html",\n    "width": 1280,\n    "finding": "MISSING hero\.png: 404"\n  \},\n  \{\n    "check": "overflow",\n    "route": "/pricing\.html",\n    "width": 390,\n    "finding": "OVERFLOW \.plans content 948px wide at a 390px viewport"\n  \}\n\]\n$'
---
