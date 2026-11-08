"""check.py - the setup check. Prints N of M required with the fix for each miss. It changes nothing.

    python3 check.py [--check "label|command|fix"]... [--optional "label|command|fix"]...
                     [--token "NAME|fix"]... [--managed-settings FILE] [--plugin-root DIR]
    python3 check.py selftest

Run it from anywhere in the project. It checks:
  - git, and the push and commit checks in the folder git runs hooks from (core.hooksPath, else
    .git/hooks): the plugin's pre-push and pre-commit, each executable. Either the short ones from
    ci/shim/, which run the installed plugin's, or full copies with scan_keys.py beside them;
  - the runner: `product-os` on PATH, the plugin's own launcher, which the push check needs;
  - the settings (.claude/product-os.json through the plugin's kit_config): app.build_cmd and
    app.check_cmd accepted on this machine when the project's file sets them, the plugin's version
    against setup.min_version when it's set, and every setup.checks line, each run in app.dir and
    passing on exit 0;
  - at least one check listed in .claude/product-os-checks.json, since the push check refuses a
    push with none, and each accepted on this machine as it is now, since it runs no other;
  - each token setup.tokens or --token names: set or not, judged by its length only. Never printed;
  - whether Claude Code runs the plugin's hooks here, from the managed settings file. A note, never
    a miss: where policy runs no plugin hooks, the git hooks carry the rules.
An "optional": true entry, or --optional, is reported the same way but never fails the run.
A command setting the project's file has and this machine hasn't accepted is a miss whose fix is
the accept line for the person to run. This script never accepts anything.

Exit 0 when every required row passes, 1 when one doesn't.
BLIND TO: hook policy delivered other than by the managed settings file (MDM, server-managed), and a
disableAllHooks in your own settings, which it doesn't read.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PUSH_MARK = "# product-os: push check"
COMMIT_MARK = "# product-os: commit check"
# A hook that runs the installed plugin's own (ci/shim/), so the project keeps no copy and needs no
# scanner beside it.
SHIM_MARK = "# product-os: runs the installed plugin's hook"
PLUGIN_ID = "product-os@product-os"
MANAGED = {"darwin": "/Library/Application Support/ClaudeCode/managed-settings.json",
           "linux": "/etc/claude-code/managed-settings.json",
           "win32": r"C:\Program Files\ClaudeCode\managed-settings.json"}


def sh(cmd, cwd, env=None, shell=False, timeout=180):
    try:
        # No stdin: a setup line that waits for input would hang the check.
        r = subprocess.run(cmd, cwd=cwd, env=env, shell=shell, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    return r.returncode == 0, out


def plugin_root(arg=None):
    if arg:
        return Path(arg).resolve()
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return Path(os.environ["CLAUDE_PLUGIN_ROOT"]).resolve()
    return Path(__file__).resolve().parents[3]


def load_settings(root, cwd):
    """kit_config.load() from the plugin's tools, run in cwd, or (None, why)."""
    tools = root / "tools"
    if not (tools / "kit_config.py").is_file():
        return None, f"no tools/kit_config.py in {root}"
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import kit_config as k; c = k.load(); "
            "print(json.dumps({'settings': c['settings'], 'problems': c['problems'], "
            "'withheld': [list(w) for w in c['withheld']]}))")
    ok, out = sh([sys.executable, "-c", code, str(tools)], cwd)
    if not ok:
        return None, (out.splitlines() or ["kit_config failed"])[-1]
    try:
        return json.loads(out.splitlines()[-1]), None
    except (ValueError, IndexError):
        return None, "kit_config printed no settings"


def unaccepted_checks(root, top, env=None):
    """(the names of the checks the project lists that this machine hasn't accepted as they are
    now, None) from the plugin's own product_os, or (None, why). The push check runs none of them."""
    code = ("import json, os, sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
            "from product_os import project as p; top = Path(sys.argv[2]).resolve(); "
            "acc = p.read_accepted(top, os.environ); "
            "print(json.dumps([c.name for c in p.project_checks(top) "
            "if p.stale(c, top, acc.get(c.name), accepted=True)]))")
    ok, out = sh([sys.executable, "-c", code, str(root), str(top)], top, env=env)
    if not ok:
        return None, (out.splitlines() or ["it printed nothing"])[-1][:160]
    try:
        return json.loads(out.splitlines()[-1]), None
    except (ValueError, IndexError):
        return None, "it printed no list"


def token_set(name, root):
    """True when the token is set, judged by length only. The value is never printed or kept."""
    if len(os.environ.get(name, "")) > 0:
        return True
    tools = root / "tools"
    if not (tools / "kit_config.py").is_file():
        return False
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import kit_config as k; "
            "sys.exit(0 if len(k.token(sys.argv[2]) or '') > 0 else 1)")
    ok, _ = sh([sys.executable, "-c", code, str(tools), name], None)
    return ok


def parse_line(s):
    parts = [p.strip() for p in (s or "").split("|")]
    parts += [""] * (3 - len(parts))
    return parts[0], parts[1], parts[2] or "see the project's README"


def version_key(v):
    """(major, minor, patch) from a version such as 0.6.0 or v0.6.0rc1; missing parts are 0."""
    import re
    nums = [int(n) for n in re.findall(r"\d+", str(v))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def plugin_version(root):
    """The plugin's __version__, from product_os/__init__.py, or None."""
    try:
        with open(Path(root) / "product_os" / "__init__.py", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split('"')[1]
    except (OSError, IndexError):
        pass
    return None


def hook_row(add, hooks, top, have_path, name, mark, root, extra=()):
    f = hooks / name
    label = "push check" if name == "pre-push" else "commit check"
    copy = f"mkdir -p .githooks && cp \"{root}/ci/shim/{name}\" .githooks/"
    if have_path and hooks.resolve() != (top / ".githooks").resolve():
        fix = (f"core.hooksPath is {have_path}; those may be your own hooks, so don't replace them: have "
               f"their {name} run .githooks/{name} (after: {copy})")
    elif have_path:
        fix = copy
    else:
        fix = f"{copy}, then: git config core.hooksPath .githooks"
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        add(True, False, label, f"no {name} in {hooks}", fix)
        return
    if mark not in text:
        add(True, False, label, f"{hooks / name} isn't the plugin's {name}, so its rules don't run", fix)
        return
    missing = [] if SHIM_MARK in text else [e for e in extra if not (hooks / e).is_file()]
    if missing:
        add(True, False, label, f"{', '.join(missing)} missing beside {name}, which is a full copy; "
            f"the short one runs the installed plugin's and needs none", copy)
        return
    if os.name != "nt" and not os.access(f, os.X_OK):
        add(True, False, label, f"{f} isn't executable", f"chmod +x \"{f}\"")
        return
    add(True, True, label, f"{f}")


def claude_hooks(add, root, managed):
    path = Path(managed or MANAGED.get(sys.platform, ""))
    names = []
    try:
        events = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("hooks", {})
        for event, groups in events.items():
            for g in groups:
                for h in g.get("hooks", []):
                    word = h.get("command", "").split("\n")[0].split('"')[-1].strip()
                    names.append(f"{event} {word}" if word else event)
    except (OSError, ValueError, AttributeError):
        add(False, False, "Claude Code hooks", f"did not run: no readable hooks/hooks.json in {root}", "")
        return
    policy = {}
    if path.is_file():
        try:
            policy = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            add(False, False, "Claude Code hooks", f"did not run: {path} isn't readable JSON", "")
            return
    forced = (policy.get("enabledPlugins") or {}).get(PLUGIN_ID) is True
    if policy.get("disableAllHooks") is True or (policy.get("allowManagedHooksOnly") is True and not forced):
        why = "disableAllHooks" if policy.get("disableAllHooks") is True else "allowManagedHooksOnly"
        add(False, False, "Claude Code hooks", f"off: managed policy sets {why}, so Claude Code runs none of "
            "the plugin's hooks here. The git hooks carry the rules", "nothing to fix here; an admin can "
            f"enable {PLUGIN_ID} in the managed settings")
        return
    where = f"{path}" if path.is_file() else "no managed settings file"
    add(False, True, "Claude Code hooks", f"on ({where}): {', '.join(names)}")


def run(argv, cwd=None, env=None):
    cwd = cwd or os.getcwd()
    rows = []

    def add(need, ok, label, detail, fix=""):
        rows.append({"need": need, "ok": ok, "label": label, "detail": detail, "fix": fix})

    def opt(name):
        return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == name]

    root = plugin_root((opt("--plugin-root") or [None])[-1])
    ok, out = sh(["git", "rev-parse", "--show-toplevel"], cwd)
    if not ok:
        add(True, False, "git repository", "not inside a git checkout", "run this from the project's repo")
        return rows
    top = Path(out.splitlines()[-1])
    add(True, True, "git repository", str(top))
    ok, have = sh(["git", "config", "--get", "core.hooksPath"], top)
    have = have if ok else ""
    ok, out = sh(["git", "rev-parse", "--git-path", "hooks"], top)
    hooks = (top / out.splitlines()[-1]) if ok else top / ".git" / "hooks"
    hook_row(add, hooks, top, have, "pre-push", PUSH_MARK, root)
    hook_row(add, hooks, top, have, "pre-commit", COMMIT_MARK, root, extra=("scan_keys.py",))

    path_env = (env or os.environ).get("PATH", "")
    po = shutil.which("product-os", path=path_env)
    link = f"ln -s \"{root}/bin/product-os\" ~/.local/bin/product-os (any folder on PATH), or add {root}/bin to PATH"
    if not po:
        add(True, False, "runner", "product-os isn't on PATH, so the push check refuses every push", link)
    else:
        ok, out = sh([po, "--list"], top, env=env)
        if ok and "kit_config" in out.split():
            add(True, True, "runner", po)
        else:
            add(True, False, "runner", f"{po} isn't the plugin's launcher, so the push check can't read settings", link)

    loaded, why = load_settings(root, str(top))
    settings = {}
    if loaded is None:
        add(True, False, "settings", f"did not run: {why}", "run this from the plugin's skills/setup-kit/scripts")
    elif loaded["problems"]:
        add(True, False, "settings", "; ".join(loaded["problems"]), f"python3 \"{root}/tools/kit_config.py\" shows it")
    else:
        settings = loaded["settings"]
        add(True, True, "settings", "readable")
    withheld = {k: w for k, w in (loaded or {}).get("withheld", [])}
    appcfg = settings.get("app") if isinstance(settings.get("app"), dict) else {}
    setup = settings.get("setup") if isinstance(settings.get("setup"), dict) else {}
    for key in ("app.build_cmd", "app.check_cmd"):
        short = key.split(".")[1]
        if key in withheld:
            add(True, False, key, f"set in the project's file but {withheld[key]}, so the push check refuses",
                f"read it in .claude/product-os.json, then run: product-os kit_config accept {key}")
        elif isinstance(appcfg.get(short), str) and appcfg[short].strip():
            add(True, True, key, f"runs: {appcfg[short]}")
        elif loaded is not None:
            add(False, False, key, "not set, so the push check runs only product-os check",
                "set it in .claude/product-os.json if the project has one")

    try:
        checks = json.loads((top / ".claude" / "product-os-checks.json").read_text(encoding="utf-8")).get("checks", [])
        checks = checks if isinstance(checks, list) else []
    except (OSError, ValueError, AttributeError):
        checks = []
    if checks:
        listed = ", ".join(str(c.get("name")) for c in checks if isinstance(c, dict))
        pending, why = unaccepted_checks(root, top, env)
        accept = "read each check's run command in .claude/product-os-checks.json, then run: product-os accept"
        if pending is None:
            add(True, False, "project checks", f"{len(checks)} listed: {listed}; whether this machine "
                f"accepted them did not run ({why})", accept)
        elif pending:
            add(True, False, "project checks", f"{len(checks)} listed, and this machine hasn't accepted "
                f"{', '.join(pending)}, so the push check refuses", accept)
        else:
            add(True, True, "project checks", f"{len(checks)} listed, each accepted here: {listed}")
    else:
        add(True, False, "project checks", "none listed in .claude/product-os-checks.json, so the push check "
            "refuses every push", "write one, proven on a planted bad case and a good one: /product-os:miss-to-check")

    want = setup.get("min_version")
    if isinstance(want, str) and want.strip():
        have_v = plugin_version(root)
        if have_v is None:
            add(True, False, "version", f"the project needs Product OS {want} or later, and {root} names no version",
                "install Product OS again: its INSTALL.md")
        elif version_key(have_v) < version_key(want):
            add(True, False, "version", f"Product OS {have_v} is older than the {want} the project needs",
                "upgrade it: the Upgrading section of its INSTALL.md, then restart Claude Code")
        else:
            add(True, True, "version", f"Product OS {have_v}; the project needs {want} or later")

    app = top / appcfg["dir"] if isinstance(appcfg.get("dir"), str) and appcfg["dir"].strip() else top
    lines = [(True,) + parse_line(s) for s in opt("--check")] + [(False,) + parse_line(s) for s in opt("--optional")]
    if "setup.checks" in withheld:
        add(True, False, "setup.checks", f"set in the project's file but {withheld['setup.checks']}, so they did not run",
            "read them in .claude/product-os.json, then run: product-os kit_config accept setup.checks")
    for c in setup.get("checks", []) if isinstance(setup.get("checks"), list) else []:
        if isinstance(c, dict) and c.get("cmd"):
            lines.append((not c.get("optional"), c.get("label") or c["cmd"], c["cmd"], c.get("fix") or "see the project's README"))
    for need, label, command, fix in lines:
        ok, out = sh(command, str(app), env=env, shell=True)
        last = (out.splitlines() or [""])[-1][:160]
        add(need, ok, label, "ok" if ok else f"failed: {last}", fix)

    tokens = [(True,) + tuple(parse_line(t)[:1]) + (parse_line(t)[1] or "set it in your shell profile",) for t in opt("--token")]
    for t in setup.get("tokens", []) if isinstance(setup.get("tokens"), list) else []:
        if isinstance(t, dict) and t.get("name"):
            tokens.append((not t.get("optional"), t["name"], t.get("fix") or "set it in your shell profile"))
    for need, name, fix in tokens:
        present = token_set(name, root)
        add(need, present, f"token {name}", "set" if present else "not set",
            f"{fix}; never paste it into a file or this chat")

    claude_hooks(add, root, (opt("--managed-settings") or [None])[-1])
    return rows


def show(rows):
    need = [r for r in rows if r["need"]]
    passed = sum(r["ok"] for r in need)
    print(f"setup check: {passed} of {len(need)} required{', ready' if passed == len(need) else ''}")
    for r in rows:
        tag = "ok      " if r["ok"] else "MISSING " if r["need"] else "note    "
        fix = f"\n           fix: {r['fix']}" if not r["ok"] and r["fix"] else ""
        print(f"  {tag} {r['label']}: {r['detail']}{fix}")
    return 0 if passed == len(need) else 1


def selftest():
    import tempfile
    cases, passed = [], 0

    def expect(name, ok):
        nonlocal passed
        cases.append(name)
        passed += bool(ok)
        if not ok:
            print(f"  FAILED  {name}")

    def write(p, text, mode=None):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        if mode:
            os.chmod(p, mode)

    secret = "Zq" + "9x" * 12
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plug, proj, bin_ = tmp / "plugin", tmp / "proj", tmp / "path"
        # A stand-in plugin: kit_config reads a JSON file the test plants; the launcher lists it.
        write(plug / "tools" / "kit_config.py",
              "import json, os\n"
              "def load():\n"
              "    return json.load(open(os.path.join(os.getcwd(), 'planted-settings.json')))\n"
              "def token(name):\n"
              "    return None\n")
        write(plug / "bin" / "product-os", "#!/bin/sh\necho kit_config\n", 0o755)
        # A stand-in product_os: a listed check counts as accepted when planted-settings.json names it.
        write(plug / "product_os" / "__init__.py", "")
        write(plug / "product_os" / "project.py",
              "import json\n"
              "class Check:\n"
              "    def __init__(self, name):\n"
              "        self.name = name\n"
              "def project_checks(top):\n"
              "    return [Check(c['name']) for c in json.load(open(top / '.claude' / 'product-os-checks.json'))['checks']]\n"
              "def read_accepted(top, environ):\n"
              "    return {n: {} for n in json.load(open(top / 'planted-settings.json')).get('accepted', [])}\n"
              "def stale(check, top, proof, accepted=False):\n"
              "    return '' if proof is not None else 'not accepted on this machine'\n")
        write(plug / "hooks" / "hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": [
            {"command": 'exec sh "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh" qa_before_done'}]}]}}))
        write(plug / "ci" / "pre-push", f"#!/bin/sh\n{PUSH_MARK}\n", 0o755)
        write(plug / "ci" / "pre-commit", f"#!/bin/sh\n{COMMIT_MARK}\n", 0o755)
        write(plug / "ci" / "scan_keys.py", "")
        proj.mkdir()
        sh(["git", "init", "-q"], proj)
        (proj / "web").mkdir()
        write(proj / "web" / "marker", "")
        settings = {"settings": {"app": {"check_cmd": "true", "dir": "web"}}, "problems": [],
                    "withheld": [["app.build_cmd", "not accepted on this machine"]]}
        write(proj / "planted-settings.json", json.dumps(settings))
        no_policy = tmp / "none.json"
        # This machine may be slow to start a shell, so only the first two runs carry setup lines.
        base = ["--plugin-root", str(plug), "--managed-settings", str(no_policy),
                "--token", "PLANTED_TOKEN|make one in the tool"]
        lines = ["--check", "passes|exit 0|none", "--check", "fails|exit 3|do the fix",
                 "--check", "in app.dir|test -f marker|run it in app.dir",
                 "--optional", "maybe|exit 1|later"]
        env = dict(os.environ, PATH=str(bin_) + os.pathsep + os.environ.get("PATH", ""))
        env.pop("PLANTED_TOKEN", None)
        os.environ.pop("PLANTED_TOKEN", None)
        rows = run(base + lines, str(proj), env)
        by = lambda label: next((r for r in rows if r["label"] == label), None)  # noqa: E731
        expect("no hooks installed: the push check is a miss", by("push check") and not by("push check")["ok"])
        expect("no hooks installed: the commit check is a miss", by("commit check") and not by("commit check")["ok"])
        expect("no runner on PATH is a miss", by("runner") and not by("runner")["ok"])
        expect("an unaccepted app.build_cmd is a miss whose fix is the accept line",
               by("app.build_cmd") and not by("app.build_cmd")["ok"]
               and "product-os kit_config accept app.build_cmd" in by("app.build_cmd")["fix"])
        expect("an accepted app.check_cmd passes", by("app.check_cmd") and by("app.check_cmd")["ok"])
        expect("no listed check is a miss", by("project checks") and not by("project checks")["ok"])
        expect("a failing --check is a miss with its fix", not by("fails")["ok"] and by("fails")["fix"] == "do the fix")
        expect("a passing --check passes", by("passes")["ok"])
        expect("a setup line runs in app.dir", by("in app.dir")["ok"])
        expect("an --optional miss isn't required", not by("maybe")["ok"] and not by("maybe")["need"])
        expect("an unset token is a miss", not by("token PLANTED_TOKEN")["ok"])
        expect("hooks with no policy file are on, and named", by("Claude Code hooks")["ok"]
               and "qa_before_done" in by("Claude Code hooks")["detail"])

        # Now plant the good case: hooks on, runner on PATH, a check listed, the token set.
        write(proj / ".githooks" / "pre-push", f"#!/bin/sh\n{PUSH_MARK}\n", 0o755)
        write(proj / ".githooks" / "pre-commit", f"#!/bin/sh\n{COMMIT_MARK}\n", 0o755)
        write(proj / ".githooks" / "scan_keys.py", "")
        write(bin_ / "product-os", "#!/bin/sh\necho kit_config\n", 0o755)
        write(proj / ".claude" / "product-os-checks.json", json.dumps({"checks": [{"name": "no-print"}]}))
        sh(["git", "config", "core.hooksPath", ".githooks"], proj)
        os.environ["PLANTED_TOKEN"] = secret
        settings["withheld"] = []
        settings["settings"]["app"]["build_cmd"] = "true"
        write(proj / "planted-settings.json", json.dumps(settings))
        rows = run(base, str(proj), env)
        expect("a listed check this machine hasn't accepted is a miss whose fix is product-os accept",
               by("project checks") and not by("project checks")["ok"]
               and "no-print" in by("project checks")["detail"] and "product-os accept" in by("project checks")["fix"])
        settings["accepted"] = ["no-print"]
        write(proj / "planted-settings.json", json.dumps(settings))
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rows = run(base + lines, str(proj), env)
            code = show(rows)
        expect("hooks on .githooks pass", by("push check")["ok"] and by("commit check")["ok"])
        expect("the launcher on PATH passes", by("runner")["ok"])
        expect("a listed check passes", by("project checks")["ok"])
        expect("a set token passes", by("token PLANTED_TOKEN")["ok"])
        expect("the output never holds the token or its length",
               secret not in out.getvalue() and str(len(secret)) not in out.getvalue())
        expect("one required miss left, the failing --check", code == 1
               and [r["label"] for r in rows if r["need"] and not r["ok"]] == ["fails"])

        os.chmod(proj / ".githooks" / "pre-push", 0o644)
        rows = run(base, str(proj), env)
        expect("a push hook that isn't executable is a miss", os.name == "nt" or not by("push check")["ok"])
        os.chmod(proj / ".githooks" / "pre-push", 0o755)
        (proj / ".githooks" / "scan_keys.py").unlink()
        rows = run(base, str(proj), env)
        expect("a commit hook without scan_keys.py is a miss", not by("commit check")["ok"])
        expect("its fix is the short hook, not a full copy", "ci/shim/pre-commit" in by("commit check")["fix"])
        write(proj / ".githooks" / "pre-commit", f"#!/bin/sh\n{COMMIT_MARK}\n{SHIM_MARK}\n", 0o755)
        rows = run(base, str(proj), env)
        expect("the short commit hook needs no scan_keys.py beside it", by("commit check")["ok"])

        expect("no setup.min_version, no version row", by("version") is None)
        write(plug / "product_os" / "__init__.py", '__version__ = "0.5.2"\n')
        for want, ok in (("0.6.0", False), ("0.5.2", True), ("0.5", True), ("1.0.0", False)):
            settings["settings"]["setup"] = {"min_version": want}
            write(proj / "planted-settings.json", json.dumps(settings))
            rows = run(base, str(proj), env)
            expect(f"Product OS 0.5.2 against setup.min_version {want}: {'passes' if ok else 'a miss'}",
                   by("version") and by("version")["ok"] == ok and by("version")["need"])
        settings["settings"].pop("setup")
        write(proj / "planted-settings.json", json.dumps(settings))

        write(proj / "own" / "pre-push", "#!/bin/sh\nexit 0\n", 0o755)
        sh(["git", "config", "core.hooksPath", "own"], proj)
        rows = run(base, str(proj), env)
        expect("someone else's hooks folder is a miss that says not to replace it",
               not by("push check")["ok"] and "don't replace" in by("push check")["fix"])
        write(bin_ / "product-os", "#!/bin/sh\necho usage\n", 0o755)
        rows = run(base, str(proj), env)
        expect("a product-os that isn't the plugin's launcher is a miss", not by("runner")["ok"])

        write(no_policy, json.dumps({"allowManagedHooksOnly": True}))
        rows = run(base, str(proj), env)
        expect("managed-hooks-only policy turns the hooks off and says the git hooks carry the rules",
               not by("Claude Code hooks")["ok"] and not by("Claude Code hooks")["need"]
               and "git hooks carry the rules" in by("Claude Code hooks")["detail"])
        write(no_policy, json.dumps({"allowManagedHooksOnly": True, "enabledPlugins": {PLUGIN_ID: True}}))
        rows = run(base, str(proj), env)
        expect("a policy that force-enables the plugin leaves its hooks on", by("Claude Code hooks")["ok"])
        os.environ.pop("PLANTED_TOKEN", None)
    rows = run([], tempfile.gettempdir())
    expect("outside a repo is a miss", len(rows) == 1 and not rows[0]["ok"])
    print(f"check.py selftest: {passed} of {len(cases)} {'PASS' if passed == len(cases) else 'FAIL'}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    if sys.argv[1:2] in (["selftest"], ["--selftest"]):
        sys.exit(selftest())
    sys.exit(show(run(sys.argv[1:])))
