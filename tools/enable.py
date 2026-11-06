#!/usr/bin/env python3
"""enable.py - load this checkout as the product-os plugin in every Claude Code session, by setting
CLAUDE_CODE_PLUGIN_DIRS in the `env` block of the person's Claude Code settings.

    product-os enable [--settings FILE]          show the key's value before and after; write nothing
    product-os enable --yes [--settings FILE]    write it, once the person has said yes to that

WHY THE SETTINGS FILE. Claude Code reads CLAUDE_CODE_PLUGIN_DIRS from its settings' `env` block as
well as from the shell, so one key loads the plugin from a clone or an unzipped release, where an
organization allows plugins only from marketplaces it lists. Loaded that way it's the same plugin as
a marketplace install: its hooks run, `product-os:` names resolve, and bin/ is on the Bash PATH.

WHAT IT WRITES. Only that key, in FILE (default: settings.json in $CLAUDE_CONFIG_DIR, else
~/.claude), keeping every other key; the file is rewritten atomically. Without --yes it writes
nothing and shows the key's value before and after, for the person to say yes to; it changes what
loads in every session. It never prints or copies any other key from the file, which can hold tokens.

THE ENVIRONMENT WINS. A CLAUDE_CODE_PLUGIN_DIRS set in the environment Claude Code starts with (a
shell profile, or the desktop app's environment) is read before the settings key: with the two
naming different folders, `claude plugin list` loaded the environment's. So when the environment
names another folder, it says so: this checkout loads only once that's unset or names it.

IT REFUSES, writing nothing: the file isn't a JSON object, its `env` isn't an object, or the key
already names other folders (it prints that value, and the person adds this folder themselves).

Exit 0 previewed, set or already set, 1 refused, 2 could not run.
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "CLAUDE_CODE_PLUGIN_DIRS"


def settings_path():
    folder = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(folder, "settings.json")


def read(path):
    """The settings as a dict ({} when the file is missing), or raise ValueError naming the problem."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        raise ValueError(f"{path} isn't valid JSON, so it wasn't changed; fix it, then run this again") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} doesn't hold a JSON object, so it wasn't changed")
    return data


def same_folder(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def environment_note():
    """A line when the environment's value, which wins over the settings key, names another folder."""
    value = os.environ.get(KEY, "")
    parts = [p for p in value.split(os.pathsep) if p.strip()]
    if parts and not any(same_folder(os.path.expanduser(p), ROOT) for p in parts):
        return (f"note: {KEY} is also set in the environment Claude Code starts with, to {json.dumps(value)}. "
                "That value wins over the settings key, so this checkout loads only once it's unset or names it.")
    return ""


def enable(path, yes):
    try:
        data = read(path)
    except ValueError as e:
        print(f"refused: {e}")
        return 1
    except OSError as e:
        print(f"could not run: {path} couldn't be read ({e.strerror})")
        return 2
    env = data.setdefault("env", {})
    if not isinstance(env, dict):
        print(f"refused: the env in {path} isn't an object, so it wasn't changed")
        return 1
    current = env.get(KEY)
    note = environment_note()
    if isinstance(current, str) and current.strip() and same_folder(current, ROOT):
        print(f"{KEY} in {path} already names {ROOT}; nothing to change")
        if note:
            print(note)
        return 0
    if current not in (None, ""):
        print(f"refused: {KEY} in {path} is already {json.dumps(current)}. Add {ROOT} to it yourself, "
              "or leave Product OS out of that list; nothing was changed")
        return 1
    print(f"{KEY} in {path}:")
    print("  before: unset")
    print(f"  after:  {json.dumps(ROOT)}")
    print("Every other key in the file stays as it is.")
    if note:
        print(note)
    if not yes:
        print("Nothing written. Once the person says yes to this change, run: product-os enable --yes")
        return 0
    env[KEY] = ROOT
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(path):
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)
    print("Written. Restart Claude Code, then run product-os doctor.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--settings", default=settings_path(), help="the settings file; yours by default")
    ap.add_argument("--yes", action="store_true", help="write it; only after the person has said yes")
    a = ap.parse_args(argv)
    return enable(os.path.expanduser(a.settings), a.yes)


if __name__ == "__main__":
    sys.exit(main())
