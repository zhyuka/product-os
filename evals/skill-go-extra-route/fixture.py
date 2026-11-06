"""The workspace for skill-go-extra-route. scaffold.sh runs this in the empty run folder.

A small site whose .claude/product-os.json adds one go route: a design link or frame to build goes
to the project's own page skill, site-pages, not to the plugin's build-change. An eval run never
loads skills from the workspace's .claude/ folder, and a case's plugins list replaces the plugin
under test, so site-pages can't be loaded here. The case checks the step before it: go reads the
route, reports that site-pages isn't loaded, and loads no built-in row in its place. The name
site-pages appears only in the settings, so a reply that names it read go.routes. The graders read
these names, so change them together.
"""
import subprocess
from pathlib import Path

GIT = ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false",
       "-c", "init.defaultBranch=main"]

SETTINGS = """{
  "go": {
    "routes": [
      {"when": "a design link or frame to build, or a page to build or restyle",
       "skill": "site-pages",
       "done": "the page is built with this site's components and passes site-pages's own check"}
    ]
  }
}
"""

INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Home</title><link rel="stylesheet" href="site.css"></head>
<body><main><h1>Home</h1><p><a href="pricing.html">Pricing</a></p></main></body>
</html>
"""

CSS = "body { font-family: system-ui, sans-serif; margin: 0; }\nmain { max-width: 60rem; margin: 0 auto; padding: 2rem; }\n"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    subprocess.run(GIT + ["init", "-q"], check=True)
    write(".claude/product-os.json", SETTINGS)
    write("index.html", INDEX)
    write("site.css", CSS)
    subprocess.run(GIT + ["add", "-A"], check=True)
    subprocess.run(GIT + ["commit", "-q", "-m", "Add the home page"], check=True)


if __name__ == "__main__":
    main()
