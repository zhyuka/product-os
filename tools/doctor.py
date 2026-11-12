#!/usr/bin/env python3
"""doctor.py - is Product OS installed so its skills, hooks and git checks can run? N of M, and exit
0 only when every check passes.

    product-os doctor [--settings FILE]

WHAT IT CHECKS.
  - Python is 3.9 or later.
  - `product-os` on PATH is this checkout's launcher. Inside Claude Code the plugin's bin/ is on the
    Bash PATH anyway; the git hooks run outside it, and the push check refuses every push without it.
  - Claude Code loads this checkout as the plugin: CLAUDE_CODE_PLUGIN_DIRS names it, in the
    environment or in the `env` block of the settings file (`product-os enable` writes it there).
    When both are set to different folders, it names both and says the environment's wins, as
    `claude plugin list` showed. Only that key is read from the file, which can hold tokens. A
    marketplace install doesn't need the key, so when neither is set and `claude plugin list --json`
    shows product-os enabled from this folder, that counts instead.
  - In each skill this checkout ships: every `product-os <tool>` it calls is a tool here, and every
    `${CLAUDE_SKILL_DIR}/<path>` and relative link it names exists.
  - Run inside a project whose settings set `setup.min_version`: this checkout is that version or
    later. Only that key is read from the project's settings.
When the claude command is on PATH, `claude plugin list --json` must also show product-os enabled
from this folder; without it, that line says it didn't run, and the key check stands alone.

Exit 0 every check passed, 1 a miss, 2 could not run.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
KEY = "CLAUDE_CODE_PLUGIN_DIRS"
COMMANDS = {"check", "prove", "accept", "gates", "design", "demo"}
# Bare `product-os x`, or the launcher by its path, as in `"${CLAUDE_PLUGIN_ROOT}/bin/product-os" x`.
CALL = re.compile(r"(?<![\w-])product-os\"? ([a-z_][a-z0-9_]*)(?:\.py)?(?![\w-])")
SKILL_PATH = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_./-]*[A-Za-z0-9_])")
LINK = re.compile(r"\]\((?!https?:|#|mailto:)([^)\s]*[./][^)\s]*)\)")  # a path, not a placeholder like (url)
SKIP = {"__pycache__", ".DS_Store"}


def on_path(name, windows=os.name == "nt"):
    """The first file called name in a PATH folder, or None. On Windows shutil.which matches only names
    ending in a PATHEXT extension, and the launcher has none, so each folder is looked in instead."""
    if not windows:
        return shutil.which(name)
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        folder = folder.strip().strip('"')
        if folder and os.path.isfile(os.path.join(folder, name)):
            return os.path.join(folder, name)
    return None


def link_hint(launcher, windows=os.name == "nt"):
    """The command that links the launcher onto the PATH; in Git Bash, one that can't copy it instead."""
    if windows:
        return (f"in Git Bash, with Developer Mode on, MSYS=winsymlinks:nativestrict "
                f"ln -s \"{launcher.replace(os.sep, '/')}\" ~/.local/bin/product-os, since a copy runs from the wrong folder")
    return f"ln -s \"{launcher}\" ~/.local/bin/product-os (any folder on PATH)"


def settings_path():
    folder = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(folder, "settings.json")


def version():
    with open(os.path.join(ROOT, "product_os", "__init__.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split('"')[1]
    return "unknown"


def names_root(value):
    """True when the folder list value names this checkout."""
    if not isinstance(value, str):
        return False
    for part in re.split(r"[" + re.escape(os.pathsep) + r"]", value):
        part = part.strip()
        if part and os.path.normcase(os.path.realpath(os.path.expanduser(part))) == \
                os.path.normcase(os.path.realpath(ROOT)):
            return True
    return False


def from_settings(path):
    """(the key's value in the settings file, problem). Only that one key is read from the file."""
    if not os.path.exists(path):
        return None, ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, f"{path} couldn't be read as JSON"
    env = data.get("env") if isinstance(data, dict) else None
    return (env.get(KEY) if isinstance(env, dict) else None), ""


def plugin_setting(path, listed, list_detail):
    """(ok, detail) for whether Claude Code loads this checkout. The environment's value wins over
    the settings key: with the two naming different folders, `claude plugin list` loaded the
    environment's."""
    env_value = os.environ.get(KEY) or None
    file_value, problem = from_settings(path)
    if problem:
        return False, problem
    if env_value and file_value and names_root(env_value) != names_root(file_value):
        loses = "the settings key" if names_root(env_value) else "this checkout"
        return names_root(env_value), (
            f"{KEY} is {json.dumps(env_value)} in the environment and {json.dumps(file_value)} in {path}. "
            f"The environment's value wins, so {loses} doesn't load"
            + ("" if names_root(env_value) else ": unset it, or make it name this folder"))
    if env_value:
        return (names_root(env_value), f"{KEY} in the environment names this folder" if names_root(env_value)
                else f"{KEY} in the environment is {json.dumps(env_value)}, which doesn't name {ROOT}")
    if file_value:
        return (names_root(file_value), f"{KEY} in {path} names this folder" if names_root(file_value)
                else f"{KEY} in {path} is {json.dumps(file_value)}, which doesn't name {ROOT}")
    if listed:
        return True, "installed from a marketplace: " + list_detail
    return False, (f"Claude Code doesn't load this folder: {KEY} isn't set in {path} or the environment. "
                   "Run product-os enable, and product-os enable --yes on the person's yes")


def plugin_listed():
    """(True, False or None for didn't run, detail) from `claude plugin list --json`."""
    claude = shutil.which("claude")
    if not claude:
        return None, "the claude command isn't on PATH, so the plugin list didn't run"
    try:
        p = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, text=True, timeout=60)
        plugins = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return None, f"claude plugin list --json didn't give a list ({type(e).__name__}), so it didn't count"
    for plugin in plugins if isinstance(plugins, list) else []:
        if str(plugin.get("id", "")).startswith("product-os@") and plugin.get("enabled") \
                and names_root(plugin.get("installPath", "")):
            return True, f"claude plugin list shows {plugin['id']} enabled from this folder"
    return False, "claude plugin list doesn't show product-os enabled from this folder"


def version_key(v):
    """(major, minor, patch) from a version such as 0.6.0 or v0.6.0rc1; missing parts are 0."""
    nums = [int(n) for n in re.findall(r"\d+", str(v))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def min_version():
    """(the project's setup.min_version or None, a problem or ""), from the folder this runs in."""
    tools_dir = os.path.join(ROOT, "tools")
    sys.path.insert(0, tools_dir)
    try:
        import kit_config
    finally:
        sys.path.remove(tools_dir)
    try:
        loaded = kit_config.load()
    except kit_config.NotConfigured:  # run inside the plugin's own folder, which isn't a project
        return None, ""
    except (OSError, ValueError) as e:
        return None, f"the project's settings couldn't be read ({type(e).__name__})"
    setup = loaded.get("settings", {}).get("setup")
    want = setup.get("min_version") if isinstance(setup, dict) else None
    return (want if isinstance(want, str) and want.strip() else None), ""


def tools():
    return {n[:-3] for n in os.listdir(os.path.join(ROOT, "tools")) if n.endswith(".py") and not n.startswith("_")}


def skill_misses():
    """Each line in a shipped skill that names a tool, a skill file or a link that isn't there."""
    known = tools() | COMMANDS
    out = []
    skills_root = os.path.join(ROOT, "skills")
    for name in sorted(os.listdir(skills_root)):
        folder = os.path.join(skills_root, name)
        if not os.path.isdir(folder):
            continue
        for d, subdirs, files in os.walk(folder):
            subdirs[:] = sorted(s for s in subdirs if s not in SKIP)
            for fname in sorted(f for f in files if f.endswith(".md")):
                path = os.path.join(d, fname)
                rel = os.path.relpath(path, folder).replace(os.sep, "/")
                fenced = False
                with open(path, encoding="utf-8") as f:
                    for no, line in enumerate(f, 1):
                        where = f"skills/{name}/{rel}:{no}"
                        if line.lstrip().startswith("```"):
                            fenced = not fenced
                            continue
                        code = line if fenced else "\n".join(re.findall(r"`([^`]+)`", line))
                        for tool in CALL.findall(code):
                            if tool not in known:
                                out.append(f"{where}: calls product-os {tool}, which isn't a tool here")
                        for p in SKILL_PATH.findall(line):
                            if not os.path.exists(os.path.join(folder, p)):
                                out.append(f"{where}: names {p} in the skill's folder, which isn't there")
                        for p in LINK.findall(line):
                            target = p.split("#")[0]
                            if target and not os.path.exists(os.path.normpath(os.path.join(d, target))):
                                out.append(f"{where}: links {p}, which isn't there")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--settings", default=settings_path(), help="the settings file; yours by default")
    a = ap.parse_args(argv)
    results = []  # (name, ok, detail)

    results.append(("python", sys.version_info >= (3, 9), f"Python {sys.version.split()[0]}; 3.9 or later is needed"))

    found = on_path("product-os")
    launcher = os.path.realpath(os.path.join(ROOT, "bin", "product-os"))
    if not found:
        results.append(("runner", False, f"product-os isn't on PATH, so the git hooks can't run it. Link it: "
                        f"{link_hint(launcher)}"))
    else:
        ok = os.path.normcase(os.path.realpath(found)) == os.path.normcase(launcher)
        results.append(("runner", ok, f"product-os on PATH is {found}" + ("" if ok else
                        f", not this checkout's launcher {launcher}; link that one instead: {link_hint(launcher)}")))

    listed, list_detail = plugin_listed()
    ok, detail = plugin_setting(os.path.expanduser(a.settings), listed, list_detail)
    results.append(("plugin", ok, detail))
    if listed is not None:
        results.append(("plugin list", listed, list_detail))

    misses = skill_misses()
    results.append(("skill paths", not misses, f"{len(misses)} line(s) name something that isn't there"
                    if misses else "every product-os call, skill-folder path and link resolves"))

    want, problem = min_version()
    if problem:
        results.append(("version", False, problem))
    elif want:
        ok = version_key(version()) >= version_key(want)
        results.append(("version", ok, f"product-os {version()}; this project needs {want} or later"
                        + ("" if ok else ". Upgrade: the Upgrading section of INSTALL.md")))

    passed = sum(ok for _, ok, _ in results)
    print(f"product-os doctor: {passed} of {len(results)} checks pass (product-os {version()}, {ROOT})")
    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'MISS'} {name}: {detail}")
    if listed is None:
        print(f"       ({list_detail})")
    for m in misses:
        print(f"       {m}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
