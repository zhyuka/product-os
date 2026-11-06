"""Workspace for skill-check-page-baseline-grew, built in the current folder by scaffold.sh.

A git repository on branch page/pricing, one commit past main. main's qa-baseline.json holds one
known finding on the home page. The pricing commit adds pricing.html, whose plan row is 948px wide
and overflows a 390px phone, and adds that overflow to qa-baseline.json, so the new defect reads
as a known one. .claude/product-os.json names the baseline, the base and the widths, and no
command, so the build can't run. The graders read qa-baseline.json byte for byte, so change them
together.
"""
import json
import subprocess
from pathlib import Path

GIT = ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]
HERE = Path.cwd().resolve()

INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Home</title></head>
<body><h1>Home</h1><img src="hero.png" alt=""><a href="pricing.html">Pricing</a></body></html>
"""

PRICING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Pricing</title>
<style>.plans { display: flex; gap: 24px } .plan { width: 300px; flex: none }</style></head>
<body><h1>Pricing</h1>
<div class="plans">
  <div class="plan"><h2>Starter</h2><p>$9</p><button>Buy</button></div>
  <div class="plan"><h2>Team</h2><p>$29</p><button>Buy</button></div>
  <div class="plan"><h2>Scale</h2><p>$99</p><button>Buy</button></div>
</div></body></html>
"""

OLD = {"check": "assets", "route": "/index.html", "width": 1280,
       "finding": "MISSING hero.png: 404"}
NEW = {"check": "overflow", "route": "/pricing.html", "width": 390,
       "finding": "OVERFLOW .plans content 948px wide at a 390px viewport"}

SETTINGS = {"app": {"baseline": "qa-baseline.json", "base": "main", "widths": [1280, 390]}}


def write(path, text):
    p = HERE / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def git(*args):
    subprocess.run(GIT + list(args), cwd=HERE, check=True, stdout=subprocess.DEVNULL)


def main():
    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    write("site/index.html", INDEX)
    write("qa-baseline.json", json.dumps([OLD], indent=2) + "\n")
    write(".claude/product-os.json", json.dumps(SETTINGS, indent=2) + "\n")
    git("add", "-A")
    git("commit", "-q", "-m", "Home page and its QA baseline")
    git("checkout", "-q", "-b", "page/pricing")
    write("site/pricing.html", PRICING)
    write("qa-baseline.json", json.dumps([OLD, NEW], indent=2) + "\n")
    git("add", "-A")
    git("commit", "-q", "-m", "Add the pricing page")


if __name__ == "__main__":
    main()
