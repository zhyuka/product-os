#!/usr/bin/env python3
"""open_items.py - every open item, from each source the project lists, in one run.

    python3 open_items.py [--project DIR] [--surfaces FILE] [--all] [--source NAME] [--mark TEXT] [--top N]
                          [--since DATE]
    python3 open_items.py --probe [--project DIR] [--surfaces FILE]   does each source see a planted item?
    python3 open_items.py wrap [--items RE] [--drop RE] [--ok CODES] [--mark RE=MARK] [--age FILE]
                               [--max-age HOURS] [--with RE] -- <command> [<arg> ...]
    python3 open_items.py ado --assigned NAME [--state S,S] [--cache FILE] [--max-age HOURS]
    python3 open_items.py --selftest

THE SOURCES are the reconcile skill's `rebase.surfaces` list, the same setting and the same shape
(skills/reconcile/references/surfaces.md): `{"name", "cmd", "pass"}`, plus three keys only this
runner reads: `mark`, the mark an item of that source gets when its line carries none; `top`, how
many of its items to print (default 5); and `probe`, a command that runs the same source on planted
data holding one item. Entries whose `pass` is `catch-up` or unset run; `--all` adds the `full` ones.
From the project's file the list counts only once accepted (`product-os kit_config accept
rebase.surfaces`); until then nothing runs and the run says so. Yours, in ~/.claude, always counts.
`--surfaces FILE` reads the list from FILE instead, a JSON list or {"rebase": {"surfaces": [...]}}, one
you hand it yourself, so it needs no accept.

THE PROTOCOL, as reconcile runs a surface. Each `cmd` runs through a POSIX shell in the project
folder: /bin/sh, or on Windows Git Bash, found the way Claude Code finds it for a hook command
(CLAUDE_CODE_GIT_BASH_PATH, Git for Windows' own folder, then a Git bash on PATH; with none, each
source did not run and says what to set). `RECONCILE_SINCE` is set to a YYYY-MM-DD date
(`--since`, a date or an ISO date-time, whose day it takes; default 7 days ago). Exit 0: no
items. Exit 1: each line it prints is an item. Any other exit, exit 1 with no line, or no exit
within 5 minutes: DID NOT RUN, with the first line of its error. All sources run at once.

MARKS. Each item is one of: `start now`, `running (<holder>)`, `waits on <who> (<for what>)` or
`paused`. A line marks itself by starting with the mark in brackets, `[start now] plan:s12 ...`;
else it takes its entry's `mark`; else it is `unmarked`. `--mark TEXT` keeps the items whose mark
starts with TEXT.

THE COUNTS. total: the items of every source that ran. listed: the ones printed. skipped: the ones
not printed (past a source's top, or another mark than --mark). uncovered: the sources that did not
run, named, since nothing they hold is in the total.

WRAP turns a tool that doesn't speak the protocol into one that does, so a list entry stays one
line: it runs the command (no shell; on Windows found with PATHEXT, so `az` starts az.cmd), takes
the lines matching --items (default every non-blank line) less those matching --drop as items, and
exits 1 with them, 0 with none. An exit code outside --ok (default 0) exits 2 quoting its error.
`--mark RE=MARK` marks an item RE matches (the first that matches wins; MARK may use \\1). `--age
FILE` adds FILE's age to each item and exits 2 when the file is missing or older than --max-age
hours. `--with RE` puts the last line before an item that matches RE (a thread's header, say) in
front of it.

ADO lists the tracker items assigned to NAME (display or sign-in name) in the given states (default
New,Active), from the cache `ado_rest.py pull` writes, with the cache's age on each line. A cache it
can't read, or older than --max-age hours (default 24), exits 2.

PROBE. A source that prints nothing with exit 0 looks the same as one that can't see its items. An
entry's `probe` runs it on planted data holding one item; `--probe` passes it only when it exits 1
and prints a line, and says how many entries have no probe.

Exit 0 no items, 1 items, 2 when a source did not run or the list is not set up or not accepted.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))


def _tools_dir(start=HERE):
    """The plugin's tools folder: this file's own, or the nearest tools/ above it holding kit_config.py, so the
    runner works from tools/ or from a skill's scripts/ folder."""
    d = start
    while True:
        for cand in (d, os.path.join(d, "tools")):
            if os.path.exists(os.path.join(cand, "kit_config.py")):
                return cand
        if os.path.dirname(d) == d:
            return start
        d = os.path.dirname(d)


sys.path.insert(0, _tools_dir())
import kit_config  # noqa: E402

CAP = 300                   # seconds a source may take (reconcile's 5 minutes)
TOP = 5
MARK = re.compile(r"^\[(start now|paused|running(?: \([^\]]*\))?|waits on [^\]]+)\]\s*(.*)$")


def kind(mark):
    """The mark's kind: start now, running, waits, paused or unmarked."""
    for k in ("start now", "running", "waits", "paused"):
        if mark.startswith(k):
            return k
    return "unmarked"


def first_error(out, err):
    lines = [ln.strip() for ln in ((err or "") + "\n" + (out or "")).splitlines() if ln.strip()]
    hit = next((ln for ln in lines if re.match(r"(?i)(refused|error|fatal|not configured|not accepted|"
                                                 r"traceback|did not run)", ln) or "Error:" in ln), None)
    return (hit or (lines[-1] if lines else "it printed nothing"))[:240]


def shell(env):
    """The POSIX shell a source's cmd runs in, found as Claude Code finds one for a hook's shell command: /bin/sh,
    or on Windows Git Bash at CLAUDE_CODE_GIT_BASH_PATH, in Git for Windows' folder under ProgramFiles, or a Git
    bash on PATH (not System32's, which is WSL's), each read from env alone. None when Windows has no Git Bash."""
    if os.name != "nt":
        return "/bin/sh"
    var = {k.upper(): v for k, v in env.items()}  # Windows reads its variable names in any case
    on_path = shutil.which("bash", path=var.get("PATH", "")) or ""
    for cand in (var.get("CLAUDE_CODE_GIT_BASH_PATH", ""),
                 os.path.join(var["PROGRAMFILES"], "Git", "bin", "bash.exe") if var.get("PROGRAMFILES") else "",
                 on_path if "git" in on_path.lower() else ""):
        if cand and os.path.isfile(cand):
            return cand
    return None


def kill_tree(p):
    """Kill p and what it started: its process group on POSIX, its process tree on Windows."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def run_cmd(cmd, cwd, env, cap=CAP):
    """(exit code or None on timeout, stdout, stderr) for cmd through shell(); a timeout kills its tree."""
    sh = shell(env)
    if not sh:
        return -1, "", ("could not start: no Git Bash for its POSIX shell; install Git for Windows or set "
                        "CLAUDE_CODE_GIT_BASH_PATH to its bash.exe")
    try:
        p = subprocess.Popen([sh, "-c", cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as e:
        return -1, "", f"could not start: {type(e).__name__}: {e}"
    try:
        out, err = p.communicate(timeout=cap)
        return p.returncode, out, err
    except subprocess.TimeoutExpired:
        kill_tree(p)
        try:
            out, err = p.communicate(timeout=30)  # a child that left the group can still hold the pipes
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return None, out, err


def items_of(out, default_mark):
    """[(mark, text)] for each non-blank line of out."""
    got = []
    for ln in (out or "").splitlines():
        if not ln.strip():
            continue
        m = MARK.match(ln.strip())
        got.append((m.group(1), m.group(2)) if m else (default_mark or "unmarked", ln.rstrip()))
    return got


def since_date(text):
    """RECONCILE_SINCE as the protocol gives it, YYYY-MM-DD, from a date or an ISO date-time (a Z allowed; its own
    date, so the window opens at that day's start); None when it is neither. A source's own date parser gets one
    form: BSD find's -newermt can't read 2026-11-05T22:17:00Z."""
    try:
        return dt.datetime.fromisoformat((text or "").strip().replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def run_source(entry, cwd, since, cap=CAP):
    """{"name", "ran", "items": [(mark, text)], "why", "secs"} for one rebase.surfaces entry."""
    name, cmd = entry.get("name") or "(no name)", entry.get("cmd") or ""
    res = {"name": name, "ran": False, "items": [], "why": "", "secs": 0.0}
    if not cmd:
        res["why"] = "its entry has no cmd"
        return res
    env = dict(os.environ, RECONCILE_SINCE=since)
    t = time.monotonic()
    code, out, err = run_cmd(cmd, cwd, env, cap)
    res["secs"] = time.monotonic() - t
    if code is None:
        res["why"] = f"no exit within {cap} s"
    elif code == 0:
        res["ran"] = True
    elif code == 1:
        res["items"] = items_of(out, entry.get("mark"))
        res["ran"] = bool(res["items"])
        res["why"] = "" if res["items"] else f"exit 1 but it printed no item ({first_error('', err)})"
    else:
        res["why"] = f"exit {code}: {first_error(out, err)}"
    return res


def sources(project, all_passes=False, path=None):
    """(entries to run, why none can run or None), from the settings or, with path, from that file."""
    if path:
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as f:
                got = json.load(f)
        except (OSError, ValueError) as e:
            return [], f"{path} can't be read as JSON ({type(e).__name__})"
        if isinstance(got, dict):
            got = (got.get("rebase") or {}).get("surfaces")
        if not got or not isinstance(got, list) or not all(isinstance(e, dict) for e in got):
            return [], f'{path} holds no list of {{"name", "cmd", "pass"}} objects'
        return [e for e in got if all_passes or (e.get("pass") or "catch-up") == "catch-up"], None
    c = kit_config.load(project)
    withheld = next((why for k, why in c.get("withheld", []) if k in ("rebase", "rebase.surfaces")), None)
    if withheld:
        return [], (f"rebase.surfaces is NOT ACCEPTED: it is in {c['project']} but {withheld}. Read it there, "
                    f"then run: product-os kit_config accept rebase.surfaces")
    got = kit_config.get("rebase", "surfaces", start=project)
    if not got:
        return [], f"rebase.surfaces is not set in {c['project'] or 'the project'} or {c['user']}"
    if not isinstance(got, list) or not all(isinstance(e, dict) for e in got):
        return [], 'rebase.surfaces must be a list of {"name", "cmd", "pass"} objects'
    return [e for e in got if all_passes or (e.get("pass") or "catch-up") == "catch-up"], None


def sweep(entries, cwd, since, cap=CAP):
    """run_source for every entry at once, in the list's order."""
    if not entries:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16, len(entries))) as ex:
        return list(ex.map(lambda e: run_source(e, cwd, since, cap), entries))


def report(results, entries, mark=None, top=None, now=None):
    """(lines, exit code): per source ran or DID NOT RUN, its count, marks and top items, then the counts."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = [f"open items, {now:%Y-%m-%dT%H:%MZ}: {len(results)} source(s)" + (f", marks starting {mark!r}" if mark else "")]
    total = listed = 0
    missed = []
    for r, e in zip(results, entries):
        if not r["ran"]:
            missed.append(r["name"])
            out.append(f"DID NOT RUN  {r['name']}: {r['why']}")
            continue
        its = r["items"]
        total += len(its)
        keep = [i for i in its if not mark or i[0].startswith(mark)]
        n = top if top is not None else int(e.get("top") or TOP)
        shown = keep[:n]
        listed += len(shown)
        counts = {}
        for m, _ in its:
            counts[kind(m)] = counts.get(kind(m), 0) + 1
        out.append(f"ran          {r['name']}: {len(its)} item(s)"
                   + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ")" if its else "")
                   + f", {r['secs']:.1f} s")
        out += [f"    [{m}] {t.strip()[:220]}" for m, t in shown]
        if len(keep) > len(shown):
            out.append(f"    ... {len(keep) - len(shown)} more")
    out.append(f"total {total}, listed {listed}, skipped {total - listed}, uncovered {len(missed)}"
               + (f" ({', '.join(missed)})" if missed else ""))
    return out, 2 if missed else (1 if listed else 0)


def probe(entries, cwd, since, cap=CAP):
    """(lines, exit code): each entry's probe passes only when it exits 1 and prints a line."""
    with_probe = [e for e in entries if e.get("probe")]
    results = sweep([{"name": e.get("name"), "cmd": e["probe"]} for e in with_probe], cwd, since, cap)
    out, bad = [], 0
    for r in results:
        if r["ran"] and r["items"]:
            out.append(f"PASS  {r['name']}: saw the planted item ({len(r['items'])} line(s))")
        else:
            bad += 1
            why = r["why"] or "exit 0 with nothing printed: it can't see a planted item"
            out.append(f"FAIL  {r['name']}: {why}")
    none = [e.get("name") or "(no name)" for e in entries if not e.get("probe")]
    out.append(f"probes: {len(results) - bad} of {len(results)} passed; {len(none)} of {len(entries)} source(s) have "
               f"no probe" + (f" ({', '.join(none)})" if none else ""))
    return out, 1 if bad else 0


def wrap(argv):
    """The wrap subcommand: run a tool, keep its item lines, speak the protocol."""
    if "--" not in argv:
        print("wrap: give the command after --", file=sys.stderr)
        return 2
    i = argv.index("--")
    opts, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="open_items.py wrap")
    ap.add_argument("--items", default=r"\S")
    ap.add_argument("--drop", action="append", default=[])
    ap.add_argument("--ok", default="0")
    ap.add_argument("--mark", action="append", default=[])
    ap.add_argument("--age")
    ap.add_argument("--max-age", type=float)
    ap.add_argument("--with", dest="with_", help="prefix each item with the last line before it matching this")
    a = ap.parse_args(opts)
    if not cmd:
        print("wrap: no command after --", file=sys.stderr)
        return 2
    tail = ""
    if a.age:
        path = os.path.expanduser(a.age)
        try:
            hours = (time.time() - os.path.getmtime(path)) / 3600
        except OSError:
            print(f"wrap: no file {path}, so its result can't be read", file=sys.stderr)
            return 2
        if a.max_age is not None and hours > a.max_age:
            print(f"wrap: {path} is {hours:.1f} h old, past --max-age {a.max_age:g}", file=sys.stderr)
            return 2
        tail = f" ({os.path.basename(path)} written {hours:.1f} h ago)"
    name = cmd[0]  # each message names the tool as the entry gave it, not the file PATHEXT found
    if os.name == "nt":  # CreateProcess adds only .exe; PATHEXT finds az.cmd for az
        cmd = [shutil.which(name) or name] + cmd[1:]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=CAP - 10)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"wrap: {name} could not run: {type(e).__name__}", file=sys.stderr)
        return 2
    ok = {int(c) for c in a.ok.split(",") if c.strip()}
    if p.returncode not in ok:
        print(f"wrap: {os.path.basename(name)} exited {p.returncode}: {first_error(p.stdout, p.stderr)}", file=sys.stderr)
        return 2
    keep = re.compile(a.items)
    drops = [re.compile(d) for d in a.drop]
    marks = []
    for m in a.mark:
        rx, sep, label = m.rpartition("=")
        if not sep or not rx:
            print(f"wrap: --mark takes RE=MARK, not {m!r}", file=sys.stderr)
            return 2
        marks.append((re.compile(rx), label))
    found, ctx = [], ""
    head = re.compile(a.with_) if a.with_ else None
    for ln in p.stdout.splitlines():
        if head and head.search(ln):
            ctx = ln.strip()
            continue
        if not ln.strip() or not keep.search(ln) or any(d.search(ln) for d in drops):
            continue
        text = (ctx + "  " if ctx else "") + ln.strip()
        for rx, label in marks:
            hit = rx.search(text)
            if hit:
                text = f"[{hit.expand(label).strip()}] {text}"
                break
        found.append(text + tail)
    print("\n".join(found))
    return 1 if found else 0


def ado(argv):
    """The ado subcommand: the tracker items assigned to a person in some states, from ado_rest's cache."""
    ap = argparse.ArgumentParser(prog="open_items.py ado")
    ap.add_argument("--assigned", required=True, help="the assignee's display name or sign-in name")
    ap.add_argument("--state", default="New,Active", help="comma-separated states (default New,Active)")
    ap.add_argument("--cache", help="the cache file (default: ado_rest.py's for ado.org and ado.project)")
    ap.add_argument("--max-age", type=float, default=24, help="hours before the cache is too old (default 24)")
    a = ap.parse_args(argv)
    path = a.cache
    if not path:
        import ado_rest
        path = ado_rest.CACHE
    path = os.path.expanduser(path)
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        pulled, items = float(d["pulled"]), d["items"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ado: the cache {path} can't be read ({type(e).__name__}); run ado_rest.py pull", file=sys.stderr)
        return 2
    hours = (time.time() - pulled) / 3600
    if hours > a.max_age:
        print(f"ado: the cache is {hours:.1f} h old, past --max-age {a.max_age:g}; run ado_rest.py pull", file=sys.stderr)
        return 2
    states = {x.strip() for x in a.state.split(",") if x.strip()}
    org, project = kit_config.ado()
    found = []
    for it in (items.values() if isinstance(items, dict) else items):
        f = it.get("fields") or {}
        who = f.get("System.AssignedTo") or {}
        if a.assigned not in (who.get("displayName"), who.get("uniqueName")) or f.get("System.State") not in states:
            continue
        url = kit_config.ado_url(it.get("id"), org, project) or ""
        found.append((int(it.get("id") or 0), f"#{it.get('id')}  {f.get('System.WorkItemType')}  {f.get('System.State')}  "
                                              f"{f.get('System.Title')}  {url}  (cache {hours:.1f} h old)"))
    print("\n".join(t for _, t in sorted(found)))
    return 1 if found else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["wrap"]:
        return wrap(argv[1:])
    if argv[:1] == ["ado"]:
        return ado(argv[1:])
    if argv[:1] == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(prog="open_items.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project")
    ap.add_argument("--surfaces", help="read the list from this JSON file, not the settings")
    ap.add_argument("--all", action="store_true", help="add the entries whose pass is full")
    ap.add_argument("--source", action="append", help="run only the entry so named (repeatable)")
    ap.add_argument("--mark", help="keep only items whose mark starts with this")
    ap.add_argument("--top", type=int, help="items to print per source (default: its entry's top, else 5)")
    ap.add_argument("--since", help="RECONCILE_SINCE for the sources (default: 7 days ago)")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args(argv)
    project = kit_config.project_dir(a.project)
    entries, why = sources(project, a.all or a.probe, a.surfaces)
    if why:
        print(f"open items: did not run: {why}")
        return 2
    if a.source:
        names = set(a.source)
        entries = [e for e in entries if e.get("name") in names]
        if not entries:
            print(f"open items: did not run: no rebase.surfaces entry is named {', '.join(sorted(names))}")
            return 2
    since = since_date(a.since) if a.since else (dt.date.today() - dt.timedelta(days=7)).isoformat()
    if not since:
        print(f"open items: did not run: --since takes a date (2026-11-05) or an ISO date-time, not {a.since!r}")
        return 2
    if a.probe:
        lines, code = probe(entries, project, since)
    else:
        lines, code = report(sweep(entries, project, since), entries, a.mark, a.top)
    print("\n".join(lines))
    return code


def selftest():
    ok = []

    def check(what, good, got=""):
        ok.append(bool(good))
        print(("PASS " if good else "FAIL ") + what + ("" if good else f"\n     got: {got}"))

    py = sys.executable
    me = os.path.realpath(__file__)
    # Python as a source's cmd names it, quoted for its shell; Git Bash starts a program by a path with a forward slash.
    shpy = shlex.quote(py.replace("\\", "/") if os.name == "nt" else py)

    def body():
        work = os.getcwd()
        plan = os.path.join(work, "plan.md")
        with open(plan, "w", encoding="utf-8") as f:
            f.write("---\nstatus: accepted\n---\n# A plan\n")
        # A planted source that lists a planted accepted plan no item names, as the setup plan's source does.
        lister = os.path.join(work, "plans.py")
        with open(lister, "w", encoding="utf-8") as f:
            f.write("import re, sys\nitems = set(sys.argv[2:])\n"
                    "txt = open(sys.argv[1], encoding='utf-8').read()\n"
                    "if re.search(r'(?m)^status: accepted', txt) and sys.argv[1] not in items:\n"
                    "    print('[start now] plan file ' + sys.argv[1] + ': accepted, no item names it'); sys.exit(1)\n")
        surfaces = [
            {"name": "erroring", "cmd": f"{shpy} -c \"import sys; sys.stderr.write('Error: no store here\\n'); sys.exit(2)\""},
            {"name": "plans", "cmd": f"{shpy} {shlex.quote(lister)} {shlex.quote(plan)}",
             "probe": f"{shpy} {shlex.quote(lister)} {shlex.quote(plan)}"},
            {"name": "blind", "cmd": "true", "probe": "true"},
            {"name": "quiet", "cmd": "true"},
            {"name": "held", "cmd": "printf 'a\\nb\\n'; exit 1", "mark": "waits on the owner (an answer)"},
            {"name": "slow", "cmd": "sleep 5", "pass": "full"},
        ]
        with open(os.path.join(os.environ["HOME"], ".claude", "product-os.json"), "w", encoding="utf-8") as f:
            json.dump({"rebase": {"surfaces": surfaces}}, f)
        kit_config.reset()
        entries, why = sources(work)
        check("the full-pass entry is left out unless --all", why is None and [e["name"] for e in entries] ==
              ["erroring", "plans", "blind", "quiet", "held"], [e["name"] for e in entries])
        results = sweep(entries, work, "2026-11-01")
        lines, code = report(results, entries)
        text = "\n".join(lines)
        check("known bad: a planted erroring source prints DID NOT RUN with its error, and is uncovered",
              "DID NOT RUN  erroring: exit 2: Error: no store here" in text and "uncovered 1 (erroring)" in text
              and code == 2, text)
        check("known good: a planted accepted plan with no item is listed as start now",
              f"\n    [start now] plan file {plan}: accepted, no item names it\n" in text, text)
        check("an unmarked line takes its entry's mark, and the counts add up",
              "    [waits on the owner (an answer)] a" in text and "total 3, listed 3, skipped 0, uncovered 1" in text, text)
        plines, pcode = probe(entries, work, "2026-11-01")
        ptext = "\n".join(plines)
        check("known bad: a source that prints zero with exit 0 on a planted item fails its probe",
              "FAIL  blind: exit 0 with nothing printed" in ptext and pcode == 1, ptext)
        check("known good: a source that lists the planted item passes, and the entries with no probe are named",
              "PASS  plans: saw the planted item" in ptext and "3 of 5 source(s) have no probe (erroring, quiet, held)"
              in ptext, ptext)
        lines, _ = report(results, entries, mark="start now")
        check("--mark keeps one mark; the rest are skipped, not listed",
              "listed 1, skipped 2" in "\n".join(lines) and "[waits on" not in "\n".join(lines), "\n".join(lines))
        r = run_source({"name": "lying", "cmd": "exit 1"}, work, "x")
        check("exit 1 with nothing printed did not run", not r["ran"] and "printed no item" in r["why"], r)
        r = run_source({"name": "slow", "cmd": "sleep 5"}, work, "x", cap=1)
        check("a source past the cap did not run", not r["ran"] and "no exit within 1 s" in r["why"], r)
        r = run_source({"name": "since", "cmd": 'echo "$RECONCILE_SINCE"; exit 1'}, work, "2026-11-01")
        check("RECONCILE_SINCE reaches the source", r["items"] == [("unmarked", "2026-11-01")], r)
        dated = os.path.join(work, "dated.json")
        with open(dated, "w", encoding="utf-8") as f:
            json.dump([{"name": "since", "cmd": 'echo "$RECONCILE_SINCE"; exit 1'}], f)
        got = [subprocess.run([py, me, "--surfaces", dated, "--since", s], capture_output=True, text=True, cwd=work)
               for s in ("2026-11-05T22:17:00Z", "2026-11-05 16:17", "2026-11-05", "last tuesday")]
        check("known bad fixed: --since as an ISO date-time reaches a source as its YYYY-MM-DD date (BSD find's "
              "-newermt can't read 2026-11-05T22:17:00Z); one that is no date did not run",
              all("    [unmarked] 2026-11-05\n" in g.stdout for g in got[:3]) and got[3].returncode == 2
              and "--since takes a date" in got[3].stdout, [g.stdout for g in got])
        src = os.path.join(work, "drafts.md")
        with open(src, "w", encoding="utf-8") as f:
            f.write("# Drafts\n### To A. NOT SENT. Held until q-1 (the call).\n### To B. NOT SENT. READY.\n### To C. Sent.\n")
        w = subprocess.run([py, me, "wrap", "--items", "NOT SENT", "--mark", r"Held until ([^ .(]+)=waits on \1 (release)",
                            "--", "cat", src], capture_output=True, text=True)
        check("wrap keeps the matching lines, marks by RE, and exits 1",
              w.returncode == 1 and w.stdout.splitlines() == ["[waits on q-1 (release)] ### To A. NOT SENT. Held until q-1 "
                                                              "(the call).", "### To B. NOT SENT. READY."], w.stdout + w.stderr)
        w = subprocess.run([py, me, "wrap", "--items", "NOT SENT", "--", "cat", src + ".gone"], capture_output=True, text=True)
        check("wrap: a tool exiting outside --ok exits 2, quoting it", w.returncode == 2 and "cat exited 1" in w.stderr,
              w.stderr)
        w = subprocess.run([py, me, "wrap", "--items", "NOT SENT", "--drop", "READY|Held", "--", "cat", src],
                           capture_output=True, text=True)
        check("wrap: no item left after --drop exits 0", w.returncode == 0 and not w.stdout.strip(), w.stdout)
        w = subprocess.run([py, me, "wrap", "--age", src, "--max-age", "1", "--", "cat", src], capture_output=True, text=True)
        check("wrap --age adds the file's age to each item", w.returncode == 1 and "(drafts.md written 0.0 h ago)" in w.stdout,
              w.stdout)
        os.utime(src, (time.time() - 7200, time.time() - 7200))
        w = subprocess.run([py, me, "wrap", "--age", src, "--max-age", "1", "--", "cat", src], capture_output=True, text=True)
        check("wrap --age past --max-age exits 2", w.returncode == 2 and "past --max-age" in w.stderr, w.stderr)
        fixture = os.path.join(work, "surfaces.json")
        with open(fixture, "w", encoding="utf-8") as f:
            json.dump(surfaces, f)
        os.remove(os.path.join(os.environ["HOME"], ".claude", "product-os.json"))
        kit_config.reset()
        r = subprocess.run([py, me, "--surfaces", fixture, "--source", "plans", "--source", "held"],
                           capture_output=True, text=True, cwd=work)
        check("--surfaces FILE runs a fixture's list with no settings file, and --source keeps the named entries",
              r.returncode == 1 and "ran          plans: 1 item(s)" in r.stdout and "ran          held: 2 item(s)" in r.stdout
              and "erroring" not in r.stdout and "total 3, listed 3, skipped 0, uncovered 0" in r.stdout, r.stdout + r.stderr)
        r = subprocess.run([py, me, "--surfaces", fixture + ".gone"], capture_output=True, text=True, cwd=work)
        check("--surfaces with a missing file did not run", r.returncode == 2 and "can't be read" in r.stdout, r.stdout)
        proj = os.path.join(work, "proj")
        os.makedirs(os.path.join(proj, ".claude"))
        with open(os.path.join(proj, ".claude", "product-os.json"), "w", encoding="utf-8") as f:
            json.dump({"rebase": {"surfaces": [{"name": "x", "cmd": "true"}]}}, f)
        entries, why = sources(proj)
        check("a project's list not accepted runs nothing, and says so", not entries and why and "NOT ACCEPTED" in why, why)

    kit_config.run_isolated(body)
    print(f"selftest: {sum(ok)} of {len(ok)} checks passed")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(kit_config.run(main))
