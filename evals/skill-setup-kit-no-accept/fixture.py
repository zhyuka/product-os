"""Builds the workspace for skill-setup-kit-no-accept in the current folder: a git repo with a
package.json, push commands in .claude/product-os.json and one proven-shaped check, none accepted."""
import json
import os
import subprocess

GIT = ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


write("package.json", json.dumps({"name": "shop", "private": True, "scripts": {
    "build": "node -e \"console.log('built')\"", "check": "node -e \"console.log('checked')\""}}, indent=2) + "\n")
write("src/cart.js", "export function total(prices) {\n  return prices.reduce((a, b) => a + b, 0);\n}\n")
write("checks/no_todo.py", "import pathlib, sys\n"
      "hits = [p for p in pathlib.Path(sys.argv[1]).rglob('*') if p.is_file() and 'TODO' in p.read_text()]\n"
      "sys.exit(1 if hits else 0)\n")
write("checks/cases/no-todo/bad/a.js", "// TODO: remove\n")
write("checks/cases/no-todo/good/a.js", "// done\n")
write(".claude/product-os.json", json.dumps(
    {"app": {"build_cmd": "npm run build", "check_cmd": "npm run check"}}, indent=2) + "\n")
write(".claude/product-os-checks.json", json.dumps({"checks": [
    {"name": "no-todo", "run": "{python} checks/no_todo.py {target}", "target": "src",
     "bad": "checks/cases/no-todo/bad", "good": "checks/cases/no-todo/good"}]}, indent=2) + "\n")
subprocess.run(GIT + ["init", "-q", "-b", "main"], check=True)
subprocess.run(GIT + ["add", "-A"], check=True)
subprocess.run(GIT + ["commit", "-qm", "shop"], check=True)
