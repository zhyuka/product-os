#!/usr/bin/env python3
"""scheduled_audits.py - run the read-only workspace audits unattended and log one line per audit.

    python tools/scheduled_audits.py              run every audit, append to the log, print one summary line
    python tools/scheduled_audits.py --log PATH   append somewhere else (a scratch file, for a trial run)
    python tools/scheduled_audits.py --selftest   planted audits: clean, findings, can't-run, crash, hang, missing
    python tools/scheduled_audits.py --watchdog   what is meant to run by itself and has stopped; exit 1 if any
    python tools/scheduled_audits.py --figma-tokens   CI's and the local Figma token's days since saving
    python tools/scheduled_audits.py --unused     tools here with no session run in 30 days that nothing calls
    python tools/scheduled_audits.py --reds       the newest run's reds, each with its audit days red and owner

WHY THIS EXISTS. An audit that runs only when someone remembers to run it drifts: its argument
parser breaks, or a check keeps failing against a structure nobody has any more, and nobody notices.
Run this daily from a scheduler (templates/launchd/ has a macOS example), so the record of what each
audit returned builds up on its own.

WHAT IT RUNS. The AUDITS list below: the workspace_audit.py checks, `skill_lint.py`,
`agent_gate_stale.py`, `skill_use.py`, `tool_time.py --audit` and `--unused` (this script's own,
UNUSED TOOLS below), each with this tools folder as its working directory. Each reads and writes
nothing (tool_time keeps its own flags file). `scheduled_audits.extra` in the product-os config adds
your own: a list of [name, script, args...] with the script in this folder (or an absolute path), or
[name, script, args..., true] to run it in a login shell (for a token that only a login shell loads).
A whole number last is the row's own timeout in seconds, in place of TIMEOUT: [name, script, args...,
true, 3300], or false before it for no login shell. Give a row whose script gives its own child a
timeout a row timeout above that one, so the child's fires first and says why. Each audit runs as its
own process group, and a timeout kills the whole group, so no child it started writes after its row
is logged as did not run. For example
["figma pins", "figma_comments.py", "pins", "--new", "--lane", "batch", true] and the same with
`stale` list your open Figma threads pinned to a deleted or hidden node, or quiet 45 days, each red
once, ["drafts stale", "drafts_store.py", "stale", "--figma", true] tests every hold in your
drafts files against the release it names, and ["figma tokens", "scheduled_audits.py", "--figma-tokens"]
dates your Figma tokens (FIGMA TOKENS below). A .mjs or .js script runs under node: PATH first, then
fnm's default, Homebrew's or /usr/local's, since a scheduler's PATH often holds none of them. With no node it is "did not run (no
node)", and an uncaught node error reads as a crash, as a Python traceback does, never as findings.
An audit's output is kept only when its result is not 0 (see below).

FIGMA TOKENS. `--figma-tokens` warns before a Figma personal access token hits Figma's 90-day cap: a
token that runs out with no warning fails every job that uses it at once. It reads ADO and the OS
keychain, so it is an extra row (above; add true for a login shell when your ADO_PAT loads only
there), not in the default list. It dates two tokens from when each was last saved, reading neither
value:
  - CI's, when `scheduled_audits.figma_token_pipeline` names an ADO build definition by its id (with
    ado.org, ado.project and the ADO_PAT as kit_config.token reads it): its secret variable
    `scheduled_audits.figma_token_variable` (default FIGMA_TOKEN), dated from the newest revision of
    the definition that ADO commented "Update variables", the Variables pane's save. A secret comes
    back null, so the comment is all that tells a save from another edit. Unset, CI isn't checked.
  - the local one: the keychain item figma_auth.py reads it from (its service order, account
    FIGMA_TOKEN), dated from the item's modification date, read from its attributes alone
    (find-generic-password with neither -w nor -g, which the reader refuses). Only macOS's `security`
    reads that date without the value, so with no `security` it is DID NOT RUN.
Each is a finding (exit 1) from 76 days after its save (WARN) and at 90 (FAIL), and the line says
where to renew it. A date it can't read is DID NOT RUN (exit 2), never a pass: no ADO_PAT, no keychain
item, no variable save in the history, or another variable beside the token in the newest save or the
one before it, since then a save can't be told to be the token's. A pipeline holding no such variable
is quiet: nothing on it expires. Blind to: a token made days before it was saved, which expires that
much sooner than shown; a keychain edit that keeps the value, which restarts the count; a token in the
environment, which figma_auth.py reads before the keychain.

UNUSED TOOLS. `--unused`, in the list as `unused tools`, keeps tools from piling up again. It fails on
each tool directly in this folder that no session ran in UNUSED_DAYS (any place in a Bash command, by
tool_time.runs_in, in every session log modified in the window) and that nothing calls: no Python
here imports it or names it in a string that is not a docstring, no commit hook under githooks/, no
launchd plist (the plugin's templates/launchd and your installed LaunchAgents whose label starts
with `scheduled_audits.agent_prefix`), no scheduled task's SKILL.md under ~/.claude/scheduled-tasks,
and no file matched by `scheduled_audits.unused_callers` (globs of other files that run your tools,
such as another repo's hooks or CI config). Each failure is a candidate to archive or delete. A tool
you keep anyway goes in `scheduled_audits.keep_unused` ({"name.py": "why"}) and shows as a note. No
log in the window, or no caller file read, is exit 2, did not run. Blind to: a call built at run
time (a name joined to ".py"), which shows as a false candidate; a string or message that names a
tool without running it, which hides one; runs outside Claude Code sessions, such as your own
terminal.

WHAT IT WRITES. One line per audit, appended to the log and fsynced as each audit finishes. The log
is `scheduled_audits.log` in config, else ~/Library/Logs/WorkspaceAudits.log on macOS and
~/.local/state/product-os/WorkspaceAudits.log elsewhere:

    <run start, ISO time> TAB <audit> TAB <result>

<result> is the exit code when it is 0 (clean) or 1 (findings). Anything else is `did not run
(<why>)`: the script is missing, it timed out, it crashed (a Python traceback on stderr, which also
exits 1 and would otherwise read as findings), it exited 2, or it exited with any other code. A
check that did not run is never logged as clean. Every line of one run carries the same start time.

When an audit's result is not 0, its stdout and stderr also go to <audit>.last.txt in a folder beside
the log named after it (WorkspaceAudits/), written atomically and replaced on that audit's next
non-zero run. Spaces in the audit's name become underscores (workspace_audit_cites.last.txt). Its
first line repeats the log line, so the two can be matched. The log itself stays one line per audit.

NOT RUN. `workspace_audit.py secrets`, on purpose: an unattended run must never risk putting a
credential into a log. Run it by hand when you need it.

UPKEEP AND DIGEST. A log nobody reads fixes nothing. So the run also:
  - runs `upkeep.py cleanup` FIRST, the one step that writes (only what is merged, regenerable or
    backed up; upkeep.py says what and how it proves it), so the audits see the cleaned state;
  - rewrites today.md in the same folder: what is red with its failing lines (every line for the
    checks in UNCUT, the first six for the rest), each with its audit days red (each day's last result
    in the log, this run the newest; a day it didn't run on ends the streak) and its owner or hold: a
    question held open in the request ledger whose text names the audit by its full name, else "no
    owner", with the ledger named on the line when it could not be read, so a hold never reads as
    none; how many reds of RED_DAYS+ audit days have no owner; what the cleanup removed; the 15
    oldest requests from this machine the request ledger (ledger.py) still holds open, each line
    ending with the link of each work-item id it names, and one line pointing at other machines'
    open ones in DIGEST.md; then the last 7 days of push-back counts from pushback_score.py, the last
    7 days of Figma and ADO ids sessions showed you outside a link (bare_ids.py), and how many
    work-item ids docs and ADO still leave bare (ado_links.py census; "not run" without ado.org and
    ado.project). Read it first thing, or have a skill read it;
  - posts ONE desktop notification, only on a new red (clean or not run in the log's previous run) or
    on a red reaching RED_DAYS audit days with no owner, once a streak (red-alerts.json beside today.md
    keeps the first day of each streak it named). A notification on every red day gets tuned out, and
    then the new red in it goes unseen too.

WATCHDOG. A job that never starts writes no failure, so nothing notices one stopping. `--watchdog`
prints what has stopped: this log older than 26 hours; the mirror's log (`mirror.log` in config)
older than 3 hours, when one is configured; on macOS, any LaunchAgent whose label starts with
`scheduled_audits.agent_prefix` that is not loaded, a KeepAlive one not running, or one listed in
`scheduled_audits.exit_matters` whose last exit was not 0. desktop_mirror.py calls it every hour and
this script after each run, so each sees the other stop; both post one notification per problem a
day (watchdog.json beside the digest). An agent paused on purpose is disabled in launchd
(`launchctl disable gui/$UID/<label>`), and the watchdog skips it. Unloading alone is not a pause:
launchd loads every plist in ~/Library/LaunchAgents again at the next login.

Exit 0 when every audit was clean; 1 when any audit had findings; 2 when none had findings but at
least one did not run, or the log could not be written.
"""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import kit_config  # noqa: E402
from desktop_mirror import LOG_DIR, notify  # noqa: E402


def _cfg(key, default=None):
    v = kit_config.get("scheduled_audits", key)
    return default if v in (None, "", [], {}) else v


LOG = os.path.expanduser(_cfg("log", os.path.join(LOG_DIR, "WorkspaceAudits.log")))
TIMEOUT = 600

UNUSED = "unused tools"
UNCUT = (UNUSED,)          # today.md shows every line these fail on (every_line), not the first six
UNUSED_DAYS = 30
WORKSPACE_CHECKS = ("cites", "archive", "naming", "tools", "root", "xrefs", "map", "config")
AUDITS = [(f"workspace_audit {c}", ["workspace_audit.py", c]) for c in WORKSPACE_CHECKS] + [
    ("skill_lint", ["skill_lint.py"]),
    ("agent_gate_stale", ["agent_gate_stale.py"]),
    ("skill_use", ["skill_use.py"]),
    ("tool_time", ["tool_time.py", "--audit"]),
    # Tools here with no session run in UNUSED_DAYS that no tool, hook, job, scheduled task or listed file calls.
    (UNUSED, ["scheduled_audits.py", "--unused"]),
]


def extra_audits(rows):
    """scheduled_audits.extra as audit rows: [name, script, args..., (true or false = login shell), (whole
    number = the row's own timeout in seconds)] becomes (name, argv[, login[, timeout]])."""
    out = []
    for row in rows or []:
        row = list(row)
        own = row.pop() if row and isinstance(row[-1], int) and not isinstance(row[-1], bool) else None
        login = row.pop() if row and isinstance(row[-1], bool) else False
        if len(row) >= 2:
            out.append((str(row[0]), [str(x) for x in row[1:]]) + ((login, own) if own else (True,) if login else ()))
    return out


def configured_audits():
    """AUDITS plus scheduled_audits.extra (extra_audits)."""
    return list(AUDITS) + extra_audits(_cfg("extra", []))


CLEANUP_JSON, DIGEST = "upkeep-cleanup.json", "today.md"


def with_upkeep(audits, folder):
    """upkeep cleanup first, then the audits."""
    return [("upkeep cleanup", ["upkeep.py", "cleanup", "--json", os.path.join(folder, CLEANUP_JSON)])] + list(audits)


def find_node():
    """node on PATH, else fnm's default, Homebrew's or /usr/local's: a scheduler's PATH often holds none of them."""
    node = shutil.which("node")
    if node:
        return node
    for c in (os.path.join(os.environ.get("FNM_DIR", os.path.expanduser("~/.local/share/fnm")), "aliases", "default",
                           "bin", "node"), "/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if os.access(c, os.X_OK):
            return c
    return None


# Node's uncaught-error report: the error's line, then its stack.
NODE_CRASH = re.compile(r"(?m)^\w*Error\b.*\n\s+at ")


def run_one(argv, cwd, timeout, login=False):
    """(result, output) for one audit. result is '0', '1', or 'did not run (<why>)'; output is the
    audit's stdout and stderr, or None when it never finished. login runs it in `zsh -lc`. A .mjs or
    .js script runs under node, anything else under this Python."""
    script = os.path.join(cwd, argv[0])
    if not os.path.isfile(script):
        return f"did not run (missing {argv[0]})", None
    js = script.endswith((".mjs", ".js"))
    if js:
        node = find_node()
        if not node:
            return "did not run (no node)", None
        cmd = [node, script] + argv[1:]
    else:
        cmd = [sys.executable, script] + argv[1:]
    if login:
        cmd = ["/bin/zsh", "-lc", shlex.join(cmd)]
    try:
        # Its own session, so a timeout reaches what it started: a child whose output the audit captures holds
        # none of this row's pipes, and outlives a kill of the audit alone.
        p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, errors="replace", start_new_session=True)
    except OSError as e:
        return f"did not run (could not start: {type(e).__name__})", None
    try:
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(p)
        return f"did not run (timeout after {timeout}s)", None
    output = f"--- stdout\n{stdout}\n--- stderr\n{stderr}"
    if "Traceback (most recent call last)" in stderr or (js and NODE_CRASH.search(stderr)):
        return f"did not run (crashed, exit {p.returncode})", output
    if p.returncode in (0, 1):
        return str(p.returncode), output
    return f"did not run (exit {p.returncode})", output


def kill_group(p):
    """SIGKILL the audit's whole process group, then reap the child. Killing the child alone leaves a grandchild
    running, and it can write its output after the row is logged as did not run."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        p.communicate(timeout=10)
    except subprocess.TimeoutExpired:      # something that left the group still holds the pipes
        for s in (p.stdout, p.stderr):
            s.close()
        p.wait()


def output_path(log, name):
    """Where an audit's output from its last non-zero run goes: <log without .log>/<audit>.last.txt,
    or <log>.d/ when the log has no extension. A space or other character outside letters, digits
    and ._- in the audit's name becomes an underscore."""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    base, ext = os.path.splitext(log)
    return os.path.join(base if ext else log + ".d", safe + ".last.txt")


def write_atomic(path, text):
    """tmp file in the same folder, fsync, os.replace: a reader never sees half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(audits, log, cwd, timeout, alert=None):
    """Run each audit, appending its line as it finishes, then write the digest and post one
    notification through alert(message). Returns (results, exit code)."""
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    started = time.time()
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        os.makedirs(os.path.dirname(output_path(log, "x")), exist_ok=True)
        f = open(log, "a", encoding="utf-8")
    except OSError as e:
        print(f"scheduled_audits: DID NOT RUN, cannot write {log}: {type(e).__name__}")
        return [], 2
    results, outputs = [], {}
    with f:
        for name, argv, *opt in audits:
            result, output = run_one(argv, cwd, opt[1] if len(opt) > 1 else timeout, login=bool(opt and opt[0]))
            results.append((name, result))
            outputs[name] = output
            f.write(f"{stamp}\t{name}\t{result}\n")
            f.flush()
            os.fsync(f.fileno())
            if result != "0":
                out = output_path(log, name)
                try:
                    write_atomic(out, f"{stamp}\t{name}\t{result}\n"
                                 + (output if output is not None else "(no output: the audit did not finish or did not start)\n"))
                except OSError as e:
                    print(f"scheduled_audits: could not write {out}: {type(e).__name__}")
    found = sum(r == "1" for _, r in results)
    missed = [n for n, r in results if r not in ("0", "1")]
    rc = 1 if found else 2 if missed else 0
    home = os.path.expanduser("~") + os.sep
    shown = "~/" + log[len(home):] if log.startswith(home) else log
    print(f"scheduled_audits: {stamp} {len(results)} audits, {sum(r == '0' for _, r in results)} clean, "
          f"{found} with findings, {len(missed)} did not run"
          + (f" ({', '.join(missed)})" if missed else "") + f". Log {shown}")
    folder = os.path.dirname(output_path(log, "x"))
    try:
        text, message = digest(stamp, results, outputs, log, started)
        write_atomic(os.path.join(folder, DIGEST), text)
        if message and alert:
            alert(message)
    except OSError as e:
        print(f"scheduled_audits: could not write the digest: {type(e).__name__}")
    return results, rc


AGENTS = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
AGENT_PREFIX = _cfg("agent_prefix")              # None: no LaunchAgents are watched
EXIT_MATTERS = tuple(_cfg("exit_matters", []))    # agents whose non-zero last exit is a problem
STALE_HOURS = 26
MIRROR_LOG = os.path.expanduser(kit_config.get("mirror", "log") or "") or None
MIRROR_STALE_HOURS = 3   # the mirror runs every hour, one line each run
WATCH_STATE = "watchdog.json"


def last_run(log):
    """The newest run start in the log, as a datetime, or None."""
    newest = None
    try:
        with open(log, encoding="utf-8") as f:
            for line in f:
                try:
                    t = datetime.datetime.fromisoformat(line.split("\t", 1)[0])
                except ValueError:
                    continue
                newest = t if newest is None or t > newest else newest
    except OSError:
        pass
    return newest


def agent_state(label):
    """{"running": bool, "last_exit": int or None} from `launchctl print`, or None when launchd does
    not know the label (never loaded, or booted out)."""
    if sys.platform != "darwin":
        return None
    p = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True, text=True, timeout=20)
    if p.returncode:
        return None
    code = re.search(r"^\tlast exit code = (-?\d+)", p.stdout, re.M)
    return {"running": "\tstate = running" in p.stdout, "last_exit": int(code.group(1)) if code else None}


def our_agents(folder=AGENTS, prefix=None):
    """{label: keeps_alive} for every plist whose name starts with the prefix, so a new agent is watched
    without a list edit. No prefix configured: {}."""
    import plistlib
    prefix = prefix if prefix is not None else AGENT_PREFIX
    found = {}
    if not prefix:
        return found
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.startswith(prefix) and name.endswith(".plist"):
            try:
                with open(os.path.join(folder, name), "rb") as f:
                    found[name[:-6]] = plistlib.load(f).get("KeepAlive") is True
            except (OSError, ValueError, plistlib.InvalidFileException):
                found[name[:-6]] = False
    return found


def parse_disabled(text):
    """The labels `launchctl print-disabled` marks disabled (`"label" => disabled`, or `=> true`)."""
    return set(re.findall(r'^\s*"([^"]+)" => (?:disabled|true)\s*$', text, re.M))


def disabled_agents():
    """Labels disabled in the gui domain: paused on purpose, so not a stopped job."""
    if sys.platform != "darwin":
        return set()
    p = subprocess.run(["launchctl", "print-disabled", f"gui/{os.getuid()}"], capture_output=True, text=True, timeout=20)
    return parse_disabled(p.stdout) if p.returncode == 0 else set()


def watchdog(log, now, state=agent_state, mirror_log=None, agents=AGENTS, disabled=disabled_agents, prefix=None,
             exit_matters=None):
    """{key: problem} for the jobs that are meant to run by themselves; a job that never starts writes
    no failure anywhere. An agent disabled in launchd is paused on purpose and skipped."""
    problems = {}
    mirror_log = MIRROR_LOG if mirror_log is None else mirror_log
    prefix = AGENT_PREFIX if prefix is None else prefix
    exit_matters = EXIT_MATTERS if exit_matters is None else exit_matters
    newest = last_run(log)
    if newest is None or now - newest > datetime.timedelta(hours=STALE_HOURS):
        problems["daily-run"] = ("the daily audits have not run since "
                                 + (newest.strftime("%Y-%m-%d %H:%M") if newest else "the log began"))
    if mirror_log:
        try:
            mirrored = datetime.datetime.fromtimestamp(os.path.getmtime(mirror_log))
        except OSError:
            mirrored = None
        if mirrored is None or now - mirrored > datetime.timedelta(hours=MIRROR_STALE_HOURS):
            problems["desktop-mirror"] = ("the mirror has not run since "
                                          + (mirrored.strftime("%Y-%m-%d %H:%M") if mirrored else "its log began"))
    if not prefix:
        return problems
    found = our_agents(agents, prefix)
    if not found:
        problems["agents"] = f"no {prefix}* LaunchAgent found in {agents}"
    paused = disabled() if found else set()
    for label, keeps_alive in found.items():
        if label in paused:
            continue
        s = state(label)
        if s is None:
            problems[label] = f"{label} is not loaded"
        elif keeps_alive and not s["running"]:
            problems[label] = f"{label} is not running"
        elif label in exit_matters and s["last_exit"] not in (0, None):
            problems[label] = f"{label} last exited {s['last_exit']}"
    return problems


def watchdog_alert(log=LOG, alert=None, now=None, state=agent_state, mirror_log=None, agents=AGENTS,
                   disabled=disabled_agents, prefix=None, exit_matters=None):
    """Post one notification for problems not alerted in the last 24 hours; a problem that clears
    is forgotten, so it alerts again if it comes back. Returns the problems."""
    now = now or datetime.datetime.now()
    problems = watchdog(log, now, state, mirror_log, agents, disabled, prefix, exit_matters)
    path = os.path.join(os.path.dirname(output_path(log, "x")), WATCH_STATE)
    try:
        with open(path, encoding="utf-8") as f:
            sent = json.load(f)
    except (OSError, ValueError):
        sent = {}
    due = [k for k in problems if now.timestamp() - sent.get(k, 0) >= 86400]
    sent = {k: (now.timestamp() if k in due else v) for k, v in sent.items() if k in problems}
    sent.update({k: now.timestamp() for k in due})
    write_atomic(path, json.dumps(sent))
    if due and alert:
        alert("; ".join(problems[k] for k in due) + f". See {os.path.dirname(log)}")
    return problems


def failing_lines(output, limit=6):
    """The lines of an audit's output that say what failed: FAIL / N of M / DIFFERS / UNINDEXED and
    the `- ` detail lines under them."""
    keep = [l.rstrip() for l in (output or "").splitlines()
            if re.search(r"\bFAIL\b|\b\d+ of \d+\b|\bDIFFERS\b|\bUNINDEXED\b|\bMISMATCH\b|^\s+- ", l)
            and not re.match(r"\s*PASS\b", l)]
    return keep[:limit] + ([f"... {len(keep) - limit} more lines"] if len(keep) > limit else [])


def every_line(output):
    """Every line a check in UNCUT failed on. Each FAIL there names one tool, and one cut off here is seen nowhere
    until the next run; those checks keep their own output short."""
    return failing_lines(output, limit=len((output or "").splitlines()))


def fresh_json(path, started):
    """The JSON an upkeep step wrote during THIS run, or None (missing, stale, or unreadable)."""
    try:
        if os.path.getmtime(path) < started:
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


LEDGER_DIR = None          # None: ledger.py's folder (ledger.dir); the selftest plants its own
BARE_PROJECTS = None       # None: bare_ids.py's, ~/.claude/projects; the selftest plants its own
ADO_LINKS_ARGS = {}        # {}: ado_links.py's places and cache; the selftest plants its own
OPEN_SHOWN = 15


def open_requests_section(short, ledger_dir=None, limit=OPEN_SHOWN):
    """The oldest open requests from this machine in the request ledger (ledger.py, run on a schedule), for
    today.md, and one line pointing at other machines' open ones, which DIGEST.md lists in full at its end, so an
    older request from another machine never takes a line from this one's. A ledger that is missing or unreadable
    says so; it never reads as none open."""
    try:
        sys.path.insert(0, TOOLS)
        import ledger
        d = ledger_dir or LEDGER_DIR or ledger.LEDGER_DIR
        path = os.path.join(d, "requests.jsonl")
        if not os.path.isfile(path):
            return [f"- the request ledger did not run: there is no {short(path)} (tools/ledger.py writes it)"]
        rows = ledger.open_requests(d, source="this")
        far = ledger.open_requests(d, source="other")
        span = ledger.other_span(far + ledger.open_questions(d, source="other"))   # the span DIGEST.md's heading names
        written = int((time.time() - os.path.getmtime(path)) / 60)
    except Exception as e:       # a broken ledger is reported, and the rest of today.md still gets written
        return [f"- the request ledger could not be read ({type(e).__name__}), so open requests are unknown"]
    digest_md = short(os.path.join(d, "DIGEST.md"))
    out = [f"- {len(rows)} requests you typed on this machine that nothing has settled yet, oldest first (ledger "
           f"written {written} min ago). {digest_md} has them all, with your standing answers"]
    now = time.time()
    for e in rows[:limit]:
        t = ledger.parse_ts(e.get("ts") or "")
        days = f"{int((now - t.timestamp()) // 86400)}d" if t else "?"
        said = ledger.own_words(e.get("text") or "")
        said = said if len(said) <= 140 else said[:139] + "…"
        where = (e.get("title") or e["session"][:8])[:50]
        card = f" (card: {(e.get('question') or '')[:50]})" if e.get("source") == "card" else ""
        out.append(f"    {(e.get('ts') or '')[:10]} ({days}) {where}: \"{said}\"{card}")
    if len(rows) > limit:
        out.append(f"    and {len(rows) - limit} newer: python tools/ledger.py --open --source this")
    if far:
        out.append(f"- {len(far)} more from other machines' sessions, {span}: listed in full at the end of {digest_md}")
    return [kit_config.ado_linked(x) for x in out]      # a #1234 you typed ends its line with the item's link


def pushback_section(short, ledger_dir=None):
    """The last 7 days of push-back counts, from pushback_score.section() on the ledger. Its own lines say
    "did not run" for a missing or unreadable ledger; this catches the rest."""
    d = ledger_dir or LEDGER_DIR
    try:
        if d is None:
            import ledger
            d = ledger.LEDGER_DIR
        sys.path.insert(0, TOOLS)
        import pushback_score
        return pushback_score.section(short, ledger=os.path.join(d, "requests.jsonl"))
    except Exception as e:
        return [f"- did not run ({type(e).__name__})"]


RED_DAYS = 3                       # a red this many audit days running with no owner notifies, once a streak
RED_STATE = "red-alerts.json"      # beside today.md: {audit: first day of the red streak already notified}


def log_runs(log):
    """[(run start, {audit: result})] from the log, oldest first. A line that isn't an ISO time, an audit and a result
    is skipped; no log is []."""
    runs = {}
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3 and re.match(r"\d{4}-\d\d-\d\dT", parts[0]):
                    runs.setdefault(parts[0], {})[parts[1]] = parts[2]
    except OSError:
        pass
    return sorted(runs.items())


def streaks(stamp, results, log):
    """{audit: {"days", "first", "new"}} for each audit this run found red (any result but 0). days: the audit days
    running it has been red, ending with this run's (each day's last result counts, and a day it didn't run on
    ends the streak); first: the first of those days; new: the run before this one in the log had it clean or
    didn't run it."""
    runs = [(s, r) for s, r in log_runs(log) if s < stamp]
    days = {}
    for s, r in runs:
        days.setdefault(s[:10], {}).update(r)
    days.setdefault(stamp[:10], {}).update(dict(results))
    prev = runs[-1][1] if runs else {}
    out = {}
    for n, r in results:
        if r == "0":
            continue
        k, first = 0, None
        for d in sorted(days, reverse=True):
            if days[d].get(n, "0") in ("0", ""):
                break
            k, first = k + 1, d
        out[n] = {"days": k, "first": first, "new": prev.get(n, "0") in ("0", "")}
    return out


def audit_named(name):
    """A pattern for text that names the audit: its words in order, with a space, - or _ between them and .py allowed
    after the first ('workspace_audit.py naming', 'drafts-headings'). Never one of its words alone: a helper
    called naming() is not the naming audit."""
    words = name.split()
    body = re.escape(words[0]) + r"(?:\.py)?" + "".join(r"[\s_-]+" + re.escape(w) for w in words[1:])
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.I)


def owner_texts(ledger_dir=None):
    """([(owner, text)], [what could not be read]): each question held open in the request ledger, with its text.
    A ledger that can't be read is named, so a hold never reads as none."""
    texts, unread = [], []
    try:
        sys.path.insert(0, TOOLS)
        import ledger
        d = ledger_dir or LEDGER_DIR or ledger.LEDGER_DIR
        if not os.path.isfile(os.path.join(d, "requests.jsonl")):
            unread.append("the request ledger (no requests.jsonl)")
        else:
            texts += [(f"held {e.get('qid') or e.get('id')}", f"{e.get('question') or ''} {e.get('text') or ''}")
                      for e in ledger.open_questions(d)]
    except Exception as e:      # the rest of today.md is still written
        unread.append(f"the request ledger ({type(e).__name__})")
    return texts, unread


def red_rows(stamp, results, log, ledger_dir=None):
    """({audit: {"days", "first", "new", "owners"}} for each red audit of this run, [sources not read])."""
    rows = streaks(stamp, results, log)
    texts, unread = owner_texts(ledger_dir) if rows else ([], [])
    for n, row in rows.items():
        pat = audit_named(n)
        row["owners"] = [o for o, text in texts if pat.search(text)]
    return rows, unread


def red_line(n, r, row, unread):
    """today.md's line for one red audit: its result, its audit days red and its owner or hold."""
    k = row["days"]
    who = ("owner: " + ", ".join(row["owners"]) if row["owners"] else
           "no owner" + (f" found, but {' and '.join(unread)} could not be read" if unread else ""))
    return (f"- **{n}**: {'findings' if r == '1' else r}; red {k} audit day{'' if k == 1 else 's'}"
            f"{' (new)' if row['new'] else ''}; {who}")


def unowned_count(rows):
    """(reds of RED_DAYS+ audit days, those with no owner)."""
    long = [n for n, row in rows.items() if row["days"] >= RED_DAYS]
    return long, [n for n in long if not rows[n]["owners"]]


def reds_report(log=LOG):
    """--reds: the newest run's red lines as today.md shows them, and how many reds of RED_DAYS+ audit days have
    no owner. Reads only. Exit 2 when the log holds no run."""
    runs = log_runs(log)
    if not runs:
        print(f"reds: did not run, no audit line in {log}")
        return 2
    stamp, res = runs[-1]
    rows, unread = red_rows(stamp, list(res.items()), log)
    print(f"reds: run {stamp}, {len(rows)} red of {len(res)}")
    for n, r in res.items():
        if n in rows:
            print(red_line(n, r, rows[n], unread))
    long, bare = unowned_count(rows)
    print(f"{len(bare)} of {len(long)} red {RED_DAYS}+ audit days have no owner"
          + (f": {', '.join(bare)}" if bare else ""))
    return 0


def digest(stamp, results, outputs, log, started):
    """(today.md text, notification message or None)."""
    folder = os.path.dirname(output_path(log, "x"))
    home = os.path.expanduser("~") + os.sep
    short = lambda p: "~/" + p[len(home):] if p.startswith(home) else p
    got = dict(results)
    audits = [(n, r) for n, r in results if not n.startswith("upkeep ")]
    red = [(n, r) for n, r in results if r != "0"]
    # Each red's audit days and owner. The notification names a red unowned RED_DAYS+ days once a streak:
    # RED_STATE keeps the first day of each streak it named, so a later run that day or the next stays quiet.
    rows, unread = red_rows(stamp, results, log)
    long, bare = unowned_count(rows)
    state = os.path.join(folder, RED_STATE)
    try:
        with open(state, encoding="utf-8") as f:
            told = json.load(f)
        told = told if isinstance(told, dict) else {}
    except (OSError, ValueError):
        told = {}
    due = [n for n in bare if told.get(n) != rows[n]["first"]]
    try:
        write_atomic(state, json.dumps({n: row["first"] for n, row in rows.items()
                                        if n in due or told.get(n) == row["first"]}))
        unsaved = None
    except OSError as e:
        unsaved = f"- could not save which reds were notified ({type(e).__name__}), so the next run may name them again"
    out = [f"# Workspace audits: {stamp}", "",
           f"{len(audits)} audits: {sum(r == '0' for _, r in audits)} clean, {sum(r == '1' for _, r in audits)} "
           f"with findings, {sum(r not in ('0', '1') for _, r in audits)} did not run. "
           + "; ".join(f"{n}: {'ran' if got[n] == '0' else got[n]}" for n in got if n.startswith("upkeep ")), ""]
    out.append("## Needs a look")
    if not red:
        out.append("- nothing: every audit was clean and every upkeep step ran")
    if long:
        out.append(f"- {len(bare)} of {len(long)} red {RED_DAYS}+ audit days have no owner"
                   + (f": {', '.join(bare)}" if bare else ""))
    if unsaved:
        out.append(unsaved)
    for n, r in red:
        out.append(red_line(n, r, rows[n], unread))
        out += [f"    {l.strip()}" for l in (every_line if n in UNCUT else failing_lines)(outputs.get(n))]
        out.append(f"    full output: {short(output_path(log, n))}")
    cleanup = fresh_json(os.path.join(folder, CLEANUP_JSON), started)
    out += ["", "## Cleaned up"]
    if cleanup is None:
        out.append("- upkeep cleanup did not run, so nothing was cleaned")
    else:
        for st in cleanup:
            out.append(f"- {st['line']}")
            out += [f"    kept {k}" for k in st.get("kept", [])[:3]]
            if len(st.get("kept", [])) > 3:
                out.append(f"    and {len(st['kept']) - 3} more kept")
    out += ["", "## Open requests"] + open_requests_section(short)
    try:
        out += ["", "## Push-backs, last 7 days"] + pushback_section(short)
    except Exception as e:      # a broken ledger module is reported, and the rest of today.md still gets written
        out += ["", "## Push-backs, last 7 days", f"- did not run ({type(e).__name__})"]
    try:
        sys.path.insert(0, TOOLS)
        import bare_ids
        out += ["", "## Bare ids, last 7 days"] + bare_ids.section(**({"projects": BARE_PROJECTS} if BARE_PROJECTS else {}))
    except Exception as e:      # its own section says "did not run" for no readable log; this catches the rest
        out += ["", "## Bare ids, last 7 days", f"- did not run ({type(e).__name__})"]
    try:
        import ado_links
        out += ["", "## Bare ADO ids in docs and ADO"] + (
            ado_links.section(**ADO_LINKS_ARGS) if all(kit_config.ado()) else
            ["- not run: ado.org or ado.project is unset, so no id has an item to link to"])
    except Exception as e:      # its own section says "did not run" for an unread cache; this catches the rest
        out += ["", "## Bare ADO ids in docs and ADO", f"- did not run ({type(e).__name__})"]
    out += ["", f"Log: {short(log)}. Written by scheduled_audits.py; the next run replaces it.", ""]
    # Only a new red, or a red reaching RED_DAYS audit days with no owner, posts it.
    new = [n for n, _ in red if rows[n]["new"]]
    late = [n for n in due if n not in new]
    label = lambda n: n + ("" if got[n] == "1" else " (did not run)")
    parts = ([f"new red: {', '.join(map(label, new))}"] if new else []) + (
        [f"red {RED_DAYS}+ audit days with no owner: {', '.join(map(label, late))}"] if late else [])
    message = ("; ".join(parts) + f". See {short(os.path.join(folder, DIGEST))}") if parts else None
    return "\n".join(out), message


# FIGMA TOKENS. Figma caps a personal access token at 90 days, and one that runs out with no warning fails every job
# that uses it at once. Neither token's value is ever read: each is dated from when it was last saved.
TOKEN_CAP_DAYS, TOKEN_WARN_DAYS = 90, 76        # Figma's cap, and 14 days before it
# The comment ADO gives a build-definition revision saved from the pipeline's Variables pane. A secret's value comes
# back null, so a save that only pastes a new token leaves a body identical to the revision before: the comment is
# all that tells a variable save from another edit.
VARIABLE_SAVE = "Update variables"
SECURITY = "/usr/bin/security"
RENEW_FIGMA = "make a new token in Figma: Settings, then Security, then Personal access tokens"


class Unreadable(Exception):
    """A date the token check needs could not be read, so it did not run."""


def ado_time(s):
    """ADO's ISO time ('2026-01-10T08:03:00.45Z': any number of fraction digits, Z for UTC) as an aware datetime;
    fromisoformat before Python 3.11 reads neither."""
    s = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), str(s).strip().replace("Z", "+00:00"))
    t = datetime.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def ado_reader(pat, org, project):
    """get(path, query) -> the JSON ADO answers under <org>/<project>/_apis, read with the PAT. An answer that is not
    JSON (a proxy's or a sign-in page can answer 200) raises Unreadable."""
    import base64
    import urllib.parse
    import urllib.request
    auth = "Basic " + base64.b64encode((":" + pat).encode()).decode()
    base = f"{org.rstrip('/')}/{urllib.parse.quote(project)}/_apis/"

    def get(path, query):
        url = base + path + "?" + urllib.parse.urlencode({**query, "api-version": "7.1"})
        req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
        if not body.lstrip().startswith("{"):
            raise Unreadable(f"ADO answered {path} with a page that is not JSON (a proxy or sign-in page?)")
        return json.loads(body)
    return get


def ci_token_saved(get, pipeline, variable):
    """(when, how) CI's token was last saved, read from build definition `pipeline`'s revision history, or (None,
    why) when the pipeline holds no `variable`, so nothing on it expires. A secret's value never shows in a revision,
    so a save is told by its comment, VARIABLE_SAVE; any other edit is not a save. The newest save dates the token
    only while `variable` is the one variable in that revision and the one before it: beside another variable, a
    save can't be told to be the token's, which raises Unreadable."""
    path = f"build/definitions/{pipeline}"
    if variable not in (get(path, {}).get("variables") or {}):
        return None, f"pipeline {pipeline} holds no {variable} variable, so nothing on it expires"
    revs = get(path + "/revisions", {}).get("value")
    if not isinstance(revs, list):
        raise Unreadable(f"pipeline {pipeline}'s revision history came back without a list of revisions")
    saves = [r for r in revs if (r.get("comment") or "").strip() == VARIABLE_SAVE]
    if not saves:
        raise Unreadable(f"no revision of pipeline {pipeline} is a variable save (comment '{VARIABLE_SAVE}'), so none "
                         f"dates {variable}")
    newest = max(saves, key=lambda r: r["revision"])
    n = newest["revision"]
    for m in (n, n - 1):
        if m < 1:
            continue
        names = set(get(path, {"revision": m}).get("variables") or {})
        if m == n and variable not in names:
            raise Unreadable(f"revision {n}, the newest variable save, holds no {variable}")
        if names - {variable}:
            raise Unreadable(f"revision {m} holds {', '.join(sorted(names - {variable}))} beside {variable}, and a "
                             f"secret's value never shows, so revision {n}'s save can't be told to be {variable}'s")
    return ado_time(newest["changedDate"]), f"revision {n}"


def keychain_services():
    """The keychain services figma_auth.py reads the local token from: $FIGMA_KEYCHAIN_SERVICE when set, else its
    default service."""
    import figma_auth
    svc = os.environ.get("FIGMA_KEYCHAIN_SERVICE")
    return [svc] if svc else [figma_auth.DEFAULT_SERVICE]


def keychain_argv(service):
    """The one keychain read this check makes per service: the item's attributes, with neither -w nor -g, so its value
    never leaves the keychain and reading attributes asks for no access."""
    import figma_auth
    return [SECURITY, "find-generic-password", "-s", service, "-a", figma_auth.ACCOUNT]


def keychain_saved(run=None, services=None):
    """(when, service): the modification date (mdat) of the first keychain item figma_auth.py would read the local
    token from, as an aware UTC datetime. run None is the real `security`, and with none here (only macOS's reads an
    item's date without its value) it raises Unreadable; so do no item, no date, and a read that fails or hangs. An
    argv asking for the value is refused before it runs."""
    import figma_auth
    if run is None:
        if sys.platform != "darwin" or not os.path.exists(SECURITY):
            raise Unreadable(f"no macOS {SECURITY} here, and no other keychain tool reads an item's date without its "
                             "value")
        run = subprocess.run
    missed = []
    for service in services or keychain_services():
        argv = keychain_argv(service)
        if {"-w", "-g"} & set(argv):
            raise Unreadable("refused: a keychain read with -w or -g prints the token's value")
        try:
            r = run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Unreadable(f"could not read the {service}/{figma_auth.ACCOUNT} item's attributes ({type(e).__name__})")
        if r.returncode != 0:
            missed.append(f"{service}/{figma_auth.ACCOUNT} ({os.path.basename(SECURITY)} exit {r.returncode})")
            continue
        text = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
        m = re.search(r'"mdat"<timedate>=\S+\s+"(\d{14})Z', text)
        if not m:
            raise Unreadable(f"the {service}/{figma_auth.ACCOUNT} item shows no modification date")
        return datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=datetime.timezone.utc), service
    raise Unreadable(f"no keychain item: {', '.join(missed)}")


def renew_ci(pipeline, variable):
    """Where CI's token is renewed: Figma, then the pipeline's Variables pane, with its link when ado is set."""
    import urllib.parse
    org, project = kit_config.ado()
    link = f" ({org}/{urllib.parse.quote(project)}/_build?definitionId={pipeline})" if org and project else ""
    return (f"{RENEW_FIGMA}; paste it in ADO the same day: Pipelines, then pipeline {pipeline}, then Edit, then "
            f"Variables, then {variable}, and save{link}")


def renew_local(service):
    """Where the local token is renewed: Figma, then the keychain item figma_auth.py reads (security asks for the
    value, so it never sits in a command line)."""
    import figma_auth
    return (f"{RENEW_FIGMA}; store it the same day in a terminal with `security add-generic-password -U -s {service} "
            f"-a {figma_auth.ACCOUNT} -w`, which asks for the value")


def token_row(label, saved, how, now, renew):
    """(status, line) for one token: ok under TOKEN_WARN_DAYS whole days since its save, WARN from it, FAIL from
    Figma's TOKEN_CAP_DAYS. saved None is a token that isn't there, with how saying why: ok, nothing expires."""
    if saved is None:
        return "ok", f"    ok    {label}: {how}"
    saved = saved.astimezone(datetime.timezone.utc)
    days = int((now - saved).total_seconds() // 86400)
    ends = (saved + datetime.timedelta(days=TOKEN_CAP_DAYS)).date()
    said = f"{label}: saved {saved:%Y-%m-%d %H:%MZ} ({how}), {days} days ago"
    if days >= TOKEN_CAP_DAYS:
        return "FAIL", f"  - FAIL  {said}: past Figma's {TOKEN_CAP_DAYS}-day cap, expired {ends}. Renew: {renew}"
    if days >= TOKEN_WARN_DAYS:
        return "WARN", (f"  - WARN  {said}: Figma's {TOKEN_CAP_DAYS}-day cap ends it {ends}, "
                        f"{TOKEN_CAP_DAYS - days} days left. Renew: {renew}")
    warns = (saved + datetime.timedelta(days=TOKEN_WARN_DAYS)).date()
    return "ok", f"    ok    {said}; expires {ends}, {TOKEN_CAP_DAYS - days} days left, warns from {warns}"


def figma_tokens_check(get=None, keychain=None, now=None, pipeline=None, variable=None):
    """Print each Figma token's age; exit 1 when either is at TOKEN_WARN_DAYS or past the cap, else 2 when either
    could not be dated (DID NOT RUN, never a pass), else 0. pipeline and variable None read
    scheduled_audits.figma_token_pipeline and .figma_token_variable ('' is unset: CI isn't checked); get reads ADO
    (ado_reader with kit_config's org, project and ADO_PAT when None); keychain returns the local token's (save time,
    service) (keychain_saved when None)."""
    import urllib.error
    now = now or datetime.datetime.now(datetime.timezone.utc)
    pipeline = _cfg("figma_token_pipeline") if pipeline is None else pipeline
    variable = variable or _cfg("figma_token_variable", "FIGMA_TOKEN")
    rows, notes = [], []
    if not pipeline:
        notes.append("    note  CI's token: not checked, scheduled_audits.figma_token_pipeline is unset")
    else:
        ci_label = f"CI's {variable} (pipeline {pipeline} secret)"
        try:
            if not str(pipeline).isdigit():
                raise Unreadable(f"scheduled_audits.figma_token_pipeline is {pipeline!r}, not a build definition's id")
            if get is None:
                org, project = kit_config.ado()
                if not (org and project):
                    raise Unreadable("ado.org or ado.project is unset, so there is no project to read the pipeline in")
                pat = kit_config.token("ADO_PAT", "AZURE_DEVOPS_EXT_PAT")
                if not pat:
                    raise Unreadable("no ADO_PAT in the environment or the OS keychain (kit_config.token)")
                get = ado_reader(pat, org, project)
            rows.append(token_row(ci_label, *ci_token_saved(get, pipeline, variable), now, renew_ci(pipeline, variable)))
        except (Unreadable, urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
            why = str(e) if isinstance(e, Unreadable) else f"{type(e).__name__}: {e}"
            rows.append(("DID NOT RUN", f"  - DID NOT RUN  {ci_label}: {why}"))
    local_label = "the local Figma token (the keychain item figma_auth.py reads)"
    try:
        saved, service = (keychain or keychain_saved)()
        rows.append(token_row(local_label, saved, f"keychain item {service} modified", now, renew_local(service)))
    except (Unreadable, OSError, ValueError) as e:
        why = str(e) if isinstance(e, Unreadable) else f"{type(e).__name__}: {e}"
        rows.append(("DID NOT RUN", f"  - DID NOT RUN  {local_label}: {why}"))
    count = {s: sum(r[0] == s for r in rows) for s in ("WARN", "FAIL", "DID NOT RUN")}
    due = count["WARN"] + count["FAIL"]
    print(f"figma tokens: {due} of {len(rows)} to renew ({count['WARN']} WARN, {count['FAIL']} FAIL), "
          f"{count['DID NOT RUN']} DID NOT RUN; warns {TOKEN_WARN_DAYS} days after a save, fails at Figma's "
          f"{TOKEN_CAP_DAYS}-day cap")
    print("\n".join([r[1] for r in rows] + notes))
    return 1 if due else 2 if count["DID NOT RUN"] else 0


def caller_files(tools=TOOLS, home=os.path.expanduser("~")):
    """{kind: [path]}: every file that can call a tool in `tools` (UNUSED TOOLS above). py: the Python under it,
    hooks and job scripts included; hooks: the non-Python commit hooks under its githooks/; jobs: the launchd
    plists in the plugin's templates/launchd and your installed LaunchAgents whose label starts with
    scheduled_audits.agent_prefix; tasks: each scheduled task's SKILL.md; listed: the files the globs in
    scheduled_audits.unused_callers match. _archive/, __pycache__/, out/ and node_modules/ are left out."""
    import glob
    skip = re.compile(r"/(_archive|__pycache__|out|node_modules)/")
    walk = lambda pat: sorted(p for p in glob.glob(pat, recursive=True) if os.path.isfile(p) and not skip.search(p))
    prefix = AGENT_PREFIX
    return {
        "py": walk(os.path.join(tools, "**", "*.py")),
        "hooks": [p for p in walk(os.path.join(tools, "githooks", "**", "*")) if not p.endswith(".py")],
        "jobs": walk(os.path.join(os.path.dirname(tools), "templates", "launchd", "*.plist"))
                + (walk(os.path.join(home, "Library", "LaunchAgents", glob.escape(prefix) + "*.plist")) if prefix else []),
        "tasks": walk(os.path.join(home, ".claude", "scheduled-tasks", "*", "SKILL.md")),
        "listed": [p for pat in _cfg("unused_callers", []) for p in walk(os.path.expanduser(pat))],
    }


NAMED_PY = re.compile(r"([A-Za-z_]\w*)\.py\b")
NAMED_IMPORT = re.compile(r"(?:^|[\s;'\"(])(?:import|from)\s+([A-Za-z_]\w*)")


def py_callees(src):
    """The tool names a Python file calls: what it imports (import, from, importlib.import_module("x"),
    __import__("x")) and each <name>.py or `import <name>` inside a string that is not a docstring. Comments and
    docstrings are prose about a tool, not a call; a bare word in a string is not one either, since "archive" or
    "review" is a word before it is a tool. Falls back to the whole text when the file does not parse."""
    import ast
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return set(NAMED_PY.findall(src)) | set(NAMED_IMPORT.findall(src))
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            docs.add(id(n.body[0].value))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module.split(".")[0])
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str) \
                and getattr(n.func, "attr", getattr(n.func, "id", "")) in ("import_module", "__import__"):
            out.add(n.args[0].value.split(".")[0])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            out |= set(NAMED_PY.findall(n.value)) | set(NAMED_IMPORT.findall(n.value))
    return out


def session_runs(start, names, pattern=None):
    """({tool: newest run time}, logs read): every tool a session's Bash command runs, at any place in the command
    (tool_time.runs_in), in the session logs modified since `start`."""
    import glob
    import tool_time
    last, n = {}, 0
    for f in glob.glob(pattern or tool_time.LOGS, recursive=True):
        try:
            if os.path.getmtime(f) < start:
                continue
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        n += 1
        with fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    r = json.loads(line)
                    t = tool_time._ts(r["timestamp"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if t < start:
                    continue
                for x in (r.get("message") or {}).get("content") or []:
                    if isinstance(x, dict) and x.get("type") == "tool_use" and x.get("name") == "Bash":
                        for tool in tool_time.runs_in((x.get("input") or {}).get("command") or "", names):
                            last[tool] = max(last.get(tool, 0), t)
    return last, n


def unused_check(tools=TOOLS, files=None, pattern=None, now=None, days=UNUSED_DAYS, keep=None):
    """Print each tool directly in `tools` with no session run in `days` that no caller file names, as a candidate
    to archive or delete; exit 0 none, 1 some, 2 no log or no caller file could be read (did not run)."""
    now = time.time() if now is None else now
    start = now - days * 86400
    keep = (_cfg("keep_unused", {}) or {}) if keep is None else keep
    files = caller_files(tools) if files is None else files
    names = {os.path.basename(p)[:-3] for p in os.listdir(tools) if p.endswith(".py") and os.path.isfile(os.path.join(tools, p))}
    since = datetime.datetime.fromtimestamp(start).strftime("%Y-%m-%d")
    if not names:
        print(f"{UNUSED}: DID NOT RUN, no tool in {tools}")
        return 2
    ran, nlogs = session_runs(start, names, pattern)
    if not nlogs:
        print(f"{UNUSED}: DID NOT RUN, no session log modified since {since}, so no run could be counted")
        return 2
    called, unread = {}, []
    for kind, paths in files.items():
        for p in paths:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except OSError:
                unread.append(p)
                continue
            found = py_callees(src) if kind == "py" else set(NAMED_PY.findall(src)) | set(NAMED_IMPORT.findall(src))
            own = os.path.dirname(os.path.abspath(p)) == os.path.abspath(tools)
            for name in found & names:
                if not (own and os.path.basename(p) == name + ".py"):    # a tool naming itself is no caller
                    called.setdefault(name, p)
    read = {k: len(v) for k, v in files.items()}
    if not sum(read.values()) or len(unread) == sum(read.values()):
        print(f"{UNUSED}: DID NOT RUN, none of the caller files could be read")
        return 2
    idle = sorted(n for n in names if n not in ran and n not in called)
    fails = [n for n in idle if n + ".py" not in keep]
    print(f"{UNUSED}: {len(fails)} of {len(names)} tools in {tools} have no session run since {since} and no caller "
          f"(read {nlogs} logs; callers: " + ", ".join(f"{v} {k}" for k, v in read.items()) + " files"
          + (f"; {len(unread)} could not be read" if unread else "") + ")")
    for n in fails:
        try:
            with open(os.path.join(tools, n + ".py"), encoding="utf-8", errors="replace") as f:
                lines = sum(1 for _ in f)
        except OSError:
            lines = "?"
        print(f"FAIL {n}.py ({lines} lines): no session run since {since}, and no tool, hook, job, scheduled task or "
              f"listed file calls it. Archive or delete it, or list it in scheduled_audits.keep_unused with your reason")
    for n in idle:
        if n + ".py" in keep:
            print(f"note: {n}.py has no run or caller, kept on purpose: {keep[n + '.py']}")
    for p in unread:
        print(f"note: could not read {p}")
    return 1 if fails else 0


def unused_selftest(check):
    """The unused-tools check, offline: a planted tools folder, its caller files and one session log."""
    import contextlib
    import io
    now = datetime.datetime(2026, 10, 30, 9, 0).timestamp()
    with tempfile.TemporaryDirectory(prefix="unused-") as t:
        tools = os.path.join(t, "tools")
        for d in ("", "githooks"):
            os.makedirs(os.path.join(tools, d), exist_ok=True)
        for d in ("launchd", "tasks", "logs", "other-repo"):
            os.makedirs(os.path.join(t, d), exist_ok=True)

        def put(path, text):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        plants = {
            "unused": '"""unused.py - nothing runs or calls this."""\n',
            "called": "x = 1\n",
            "user": "import called\n",
            "ran": "x = 1\n",
            "second": "x = 1\n",
            "old": "x = 1\n",
            "hooked": "x = 1\n",
            "jobbed": "x = 1\n",
            "tasked": "x = 1\n",
            "listed": "x = 1\n",
            "doc": "x = 1\n",
            "self_named": 'import sys\nUSAGE = "python self_named.py --help"\n',
            "kept": "x = 1\n",
            "by_string": "x = 1\n",
            "caller": '"""caller.py - unlike doc.py, which this docstring only names."""\n'
                      '# doc.py is named in this comment too\nimport importlib\nimport subprocess\n'
                      'subprocess.run(["python", "by_string.py"])\nlib = importlib.import_module("dynamic")\n'
                      'CHECKS = ("word", "other")\n',
            "dynamic": "x = 1\n",
            "word": "x = 1\n",
        }
        for n, src in plants.items():
            put(os.path.join(tools, n + ".py"), src)
        put(os.path.join(tools, "README.md"), "| doc.py | named in the README only |\n")
        put(os.path.join(tools, "githooks", "pre-commit"), '#!/bin/sh\npython "$TOOLS/hooked.py" || exit 1\n')
        plist = os.path.join(t, "launchd", "local.planted.job.plist")
        put(plist, "<plist><dict><key>ProgramArguments</key><array><string>/x/jobbed.py</string></array></dict></plist>\n")
        task = os.path.join(t, "tasks", "SKILL.md")
        put(task, "Run `python ~/tools/tasked.py` and report.\n")
        other = os.path.join(t, "other-repo", "ci.yml")
        put(other, "steps:\n  - run: python ~/tools/listed.py --check\n")

        def use(cmd, when):
            stamp = datetime.datetime.fromtimestamp(when, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
            return json.dumps({"timestamp": stamp, "type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": f"t{when}", "name": "Bash", "input": {"command": cmd}}]}}) + "\n"
        log = os.path.join(t, "logs", "s.jsonl")
        put(log, use("cd ~/tools && python ran.py --x", now - 86400)
            + use("python user.py && python second.py", now - 2 * 86400)
            + use("python old.py", now - 40 * 86400)
            + use("grep -n unused.py README.md", now - 3600)
            + use("python caller.py", now - 5 * 3600))
        files = {"py": sorted(os.path.join(tools, n + ".py") for n in plants),
                 "hooks": [os.path.join(tools, "githooks", "pre-commit")], "jobs": [plist], "tasks": [task],
                 "listed": [other]}

        def judge(**kw):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = unused_check(tools, kw.get("files", files), os.path.join(t, "logs", "*.jsonl"), now,
                                  keep=kw.get("keep", {"kept.py": "planted keep"}))
            return rc, buf.getvalue()
        rc, out = judge()
        failed = set(re.findall(r"^FAIL (\w+)\.py", out, re.M))
        check("unused: a planted tool nothing runs or calls fails; one only named in a docstring, a comment or the README "
              "fails; one that names only itself fails; one last run 40 days ago fails; one whose name is only a bare "
              "word in another tool's string fails",
              rc == 1 and failed == {"unused", "doc", "self_named", "old", "word"} and "5 of 17 tools" in out)
        check("unused: an imported tool, one importlib loads, one a session ran, one run second in a chained command, one "
              "a subprocess list names, one a commit hook runs, one a launchd job runs, one a scheduled task runs and "
              "one a listed file runs each pass",
              not failed & {"called", "dynamic", "user", "ran", "second", "by_string", "hooked", "jobbed", "tasked",
                            "listed", "caller"})
        check("unused: a grep naming a tool is not a run of it", "unused" in failed)
        check("unused: a tool kept on purpose is a note with its reason, not a failure",
              "kept" not in failed and "note: kept.py has no run or caller, kept on purpose: planted keep" in out)
        rc, out = judge(keep={})
        check("unused: the same tool not in the keep list fails", rc == 1 and "FAIL kept.py" in out)
        rc, out = judge(files=dict(files, listed=[]))
        check("unused: the same tool with no listed file naming it fails", rc == 1 and "FAIL listed.py" in out)
        os.utime(log, (now - 40 * 86400, now - 40 * 86400))
        rc, out = judge()
        check("unused: no session log modified in the window did not run, exit 2, never clean",
              rc == 2 and "DID NOT RUN" in out and "FAIL" not in out)
        os.utime(log, (now, now))
        rc, out = judge(files={"py": [os.path.join(t, "gone.py")]})
        check("unused: no readable caller file did not run, exit 2", rc == 2 and "DID NOT RUN" in out)
        for n in plants:
            if n not in ("called", "user"):
                os.unlink(os.path.join(tools, n + ".py"))
        rc, out = judge(files={"py": [os.path.join(tools, "user.py")]})
        check("unused: a folder whose every tool runs or is called is clean, exit 0",
              rc == 0 and "0 of 2 tools" in out and "FAIL" not in out)
    row = [a for a in AUDITS if a[1] == ["scheduled_audits.py", "--unused"]]
    check("unused: the daily list runs it once, not in a login shell (it reads no token)",
          len(row) == 1 and row[0][0] == UNUSED and row[0][2:] == ())


def figma_tokens_selftest(check):
    """The Figma token check, offline: a planted pipeline's revision history in the shape ADO answers it (variable
    saves at revisions 2 and 3, the token pasted at 07:40Z) and a keychain item's attributes in the shape `security`
    prints them, then planted ages and breaks. Nothing here reads ADO, your keychain or your settings."""
    global keychain_argv, SECURITY
    import contextlib
    import io
    import urllib.error
    import figma_auth
    now = datetime.datetime(2026, 11, 5, 12, 0, tzinfo=datetime.timezone.utc)
    pipe, var, svc, old = 7, "FIGMA_TOKEN", figma_auth.DEFAULT_SERVICE, "planted-second-service"
    secret = {var: {"value": None, "allowOverride": True, "isSecret": True}}
    ago = lambda d: now - datetime.timedelta(days=d, hours=1)    # d whole days back
    stamp = lambda d: ago(d).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def answers(rev3=None, extra=(), bodies=None, current=None, comments=None, fault=None, calls=None):
        revs = [{"revision": 1, "changeType": "add", "changedDate": "2026-01-10T08:00:00.123Z"},
                {"revision": 2, "changeType": "update", "changedDate": "2026-01-10T08:03:00.456Z", "comment": VARIABLE_SAVE},
                {"revision": 3, "changeType": "update", "changedDate": rev3 or "2026-11-05T07:40:12.5Z",
                 "comment": VARIABLE_SAVE}] + list(extra)
        for r, c in zip(revs, comments or ()):
            r["comment"] = c
        body = bodies or {1: {}, 2: dict(secret), 3: dict(secret)}
        body.update({r["revision"]: dict(secret) for r in extra if r["revision"] not in body})

        def get(path, query):
            if calls is not None:
                calls.append(path)
            if fault:
                raise fault
            if path.endswith("/revisions"):
                return {"count": len(revs), "value": revs}
            if "revision" in query:
                return {"variables": body[int(query["revision"])]}
            return {"variables": body[max(body)] if current is None else current}
        return get

    def judge(get, kc, pipeline=pipe):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = figma_tokens_check(get, kc, now, pipeline, var)
        return rc, buf.getvalue()

    touched = ("ADO_PAT", "AZURE_DEVOPS_EXT_PAT", "PRODUCT_OS_NO_KEYCHAIN", "FIGMA_KEYCHAIN_SERVICE")
    kept_ado, kept_security, kept_env = kit_config.ado, SECURITY, {n: os.environ.get(n) for n in touched}
    kit_config.ado = lambda: ("https://dev.azure.com/Org", "Proj")
    try:
        fresh = lambda: (ago(0), svc)
        rc, out = judge(answers(), fresh)
        check("figma tokens: known good, CI's saved today (revision 3, 07:40Z) and the local one saved today are "
              "quiet, exit 0, with no line today.md would list",
              rc == 0 and "0 of 2 to renew" in out and out.count("    ok    ") == 2 and "- " not in out
              and "saved 2026-11-05 07:40Z (revision 3), 0 days ago; expires 2027-02-03, 90 days left" in out)
        rc, out = judge(answers(stamp(80)), fresh)
        check("figma tokens: known bad, CI's saved 80 days ago WARNs, exit 1, naming 10 days left, the ADO path "
              "Pipelines, the pipeline, Edit, Variables, the variable, and the pipeline's link",
              rc == 1 and "  - WARN  CI's FIGMA_TOKEN (pipeline 7 secret)" in out and "80 days ago" in out
              and "10 days left" in out
              and "Pipelines, then pipeline 7, then Edit, then Variables, then FIGMA_TOKEN, and save "
                  "(https://dev.azure.com/Org/Proj/_build?definitionId=7)" in out
              and "Settings, then Security, then Personal access tokens" in out
              and any("WARN" in ln for ln in failing_lines(out)))
        rc, out = judge(answers(), lambda: (ago(91), svc))
        check("figma tokens: known bad, the local one saved 91 days ago FAILs as expired, exit 1, naming Figma's "
              "Settings, Security, Personal access tokens and the keychain item to update",
              rc == 1 and "  - FAIL  the local Figma token" in out and "91 days ago" in out
              and "past Figma's 90-day cap" in out and "Settings, then Security, then Personal access tokens" in out
              and f"security add-generic-password -U -s {svc} -a FIGMA_TOKEN -w" in out
              and "1 of 2 to renew (0 WARN, 1 FAIL)" in out)
        rc, out = judge(answers(stamp(91)), lambda: (ago(80), svc))
        check("figma tokens: the other way round, CI's at 91 FAILs and the local one at 80 WARNs, exit 1",
              rc == 1 and "  - FAIL  CI's" in out and "  - WARN  the local" in out and "2 of 2 to renew" in out)
        edges = {d: judge(answers(), lambda d=d: (ago(d), svc))[1] for d in (75, 76, 89, 90)}
        check("figma tokens: 75 days is quiet, 76 and 89 WARN, 90 FAILs",
              "    ok    the local" in edges[75] and "- WARN  the local" in edges[76] and "- WARN  the local" in edges[89]
              and "1 days left" in edges[89] and "- FAIL  the local" in edges[90])
        later = [{"revision": 4, "changeType": "update", "changedDate": stamp(0), "comment": "Updated triggers"}]
        rc, out = judge(answers(stamp(80), extra=later), fresh)
        check("figma tokens: a newer edit that is not a variable save (revision 4, today) doesn't date the token: "
              "revision 3 at 80 days still WARNs", rc == 1 and "(revision 3), 80 days ago" in out)
        rc, out = judge(answers(current={}), fresh)
        check("figma tokens: a pipeline holding no FIGMA_TOKEN is quiet: nothing on it expires",
              rc == 0 and "holds no FIGMA_TOKEN variable, so nothing on it expires" in out)
        calls = []
        rc, out = judge(answers(calls=calls), fresh, pipeline="")
        check("figma tokens: with figma_token_pipeline unset, CI is a note, not a row, and ADO is never read",
              rc == 0 and "note  CI's token: not checked, scheduled_audits.figma_token_pipeline is unset" in out
              and "0 of 1 to renew" in out and not calls)
        # Each date the check can't read is DID NOT RUN, exit 2 beside a quiet token, and never a pass.
        other = {"OTHER": {"value": "x"}}
        blind = {
            "ADO answers a page that is not JSON": (answers(fault=Unreadable("ADO answered with a page that is not JSON")), pipe),
            "ADO is unreachable": (answers(fault=urllib.error.URLError("no route")), pipe),
            "no revision is a variable save": (answers(comments=(None, "Saved", "Saved")), pipe),
            "another variable sits beside FIGMA_TOKEN in the newest save": (answers(
                bodies={1: {}, 2: dict(secret), 3: {**secret, **other}}), pipe),
            "another variable sat beside it in the revision before the save": (answers(
                bodies={1: {}, 2: {**secret, **other}, 3: dict(secret)}), pipe),
            "a pipeline set by name, not by id": (answers(), "my pipeline"),
        }
        for why, (get, p) in blind.items():
            rc, out = judge(get, fresh, pipeline=p)
            check(f"figma tokens: {why} is DID NOT RUN for CI, exit 2", rc == 2 and "  - DID NOT RUN  CI's" in out
                  and "1 DID NOT RUN" in out)
        for n in ("ADO_PAT", "AZURE_DEVOPS_EXT_PAT"):
            os.environ.pop(n, None)
        os.environ["PRODUCT_OS_NO_KEYCHAIN"] = "1"      # your keychain's ADO_PAT is never read here
        rc, out = judge(None, fresh)
        check("figma tokens: no ADO_PAT is DID NOT RUN for CI, exit 2", rc == 2 and "no ADO_PAT" in out)
        kit_config.ado = lambda: (None, None)
        rc, out = judge(None, fresh)
        check("figma tokens: no ado.org or ado.project is DID NOT RUN for CI, exit 2",
              rc == 2 and "ado.org or ado.project is unset" in out)
        kit_config.ado = lambda: ("https://dev.azure.com/Org", "Proj")

        # The keychain read: attributes only, in the shape `security` prints them, with a planted -g style password
        # line that must never reach the report.
        attrs = (f'keychain: "/Users/me/Library/Keychains/login.keychain-db"\nversion: 512\nclass: "genp"\n'
                 f'attributes:\n    "acct"<blob>="FIGMA_TOKEN"\n'
                 f'    "cdat"<timedate>=0x32303236303930313132303030305A00  "20260901120000Z\\000"\n'
                 f'    "mdat"<timedate>=0x32303236313130323036333031305A00  "20261102063010Z\\000"\n'
                 f'    "svce"<blob>="{svc}"\npassword: "planted token value"\n').encode()
        seen = []

        def security(code=0, out=attrs, fault=None, codes=None):
            def fake(argv, **kw):
                seen.append(list(argv))
                if fault:
                    raise fault
                c = (codes or {}).get(argv[argv.index("-s") + 1], code)
                return subprocess.CompletedProcess(argv, c, out if c == 0 else b"", b"")
            return fake
        got = keychain_saved(security(), [svc, old])
        rc, out = judge(answers(), lambda: keychain_saved(security(), [svc, old]))
        check("figma tokens: the keychain's mdat reads as 2026-11-02 06:30:10Z, through one read naming the service "
              "and account FIGMA_TOKEN with neither -w nor -g, and a password line in its answer never reaches the "
              "report",
              got == (datetime.datetime(2026, 11, 2, 6, 30, 10, tzinfo=datetime.timezone.utc), svc)
              and all(a == [SECURITY, "find-generic-password", "-s", svc, "-a", "FIGMA_TOKEN"] for a in seen)
              and len(seen) == 2 and "planted token value" not in out and rc == 0
              and f"saved 2026-11-02 06:30Z (keychain item {svc} modified)" in out)
        got = keychain_saved(security(codes={svc: 44}), [svc, old])
        check("figma tokens: with more than one service, no item under the first dates the next one",
              got[1] == old and seen[-2][3] == svc and seen[-1][3] == old)
        os.environ["FIGMA_KEYCHAIN_SERVICE"] = "planted-service"
        named = keychain_services()
        os.environ.pop("FIGMA_KEYCHAIN_SERVICE")
        check("figma tokens: the services follow figma_auth.py: $FIGMA_KEYCHAIN_SERVICE when set, else its default",
              named == ["planted-service"] and keychain_services() == [svc])
        kblind = {"no item under either service (exit 44)": security(44),
                  "no mdat in the answer": security(0, b'class: "genp"\n'),
                  "a read that hangs on a prompt": security(fault=subprocess.TimeoutExpired("security", 10))}
        for why, fake in kblind.items():
            rc, out = judge(answers(), lambda fake=fake: keychain_saved(fake, [svc, old]))
            check(f"figma tokens: the keychain giving {why} is DID NOT RUN for the local token, exit 2",
                  rc == 2 and "  - DID NOT RUN  the local Figma token" in out)
        SECURITY = os.path.join(tempfile.gettempdir(), "no-such-folder", "security")
        rc, out = judge(answers(), lambda: keychain_saved(None, [svc]))
        SECURITY = kept_security
        check("figma tokens: no `security` here is DID NOT RUN for the local token, exit 2, never read another way",
              rc == 2 and "  - DID NOT RUN  the local Figma token" in out and "no macOS" in out)
        rc, out = judge(answers(stamp(80)), lambda: keychain_saved(security(44), [svc]))
        check("figma tokens: a DID NOT RUN beside a WARN still exits 1 and lists both", rc == 1
              and "  - WARN  CI's" in out and "  - DID NOT RUN  the local" in out)
        real, n = keychain_argv, len(seen)
        keychain_argv = lambda service: real(service) + ["-w"]
        try:
            refused = None
            keychain_saved(security(), [svc])
        except Unreadable as e:
            refused = str(e)
        finally:
            keychain_argv = real
        check("figma tokens: a keychain read asking for the value (-w) is refused before it runs",
              refused is not None and "refused" in refused and len(seen) == n)
    finally:
        kit_config.ado, SECURITY = kept_ado, kept_security
        for n, v in kept_env.items():
            os.environ.pop(n, None) if v is None else os.environ.update({n: v})
    rows = [json.loads(m) for m in re.findall(r'\["figma tokens", [^\]]*\]', __doc__)]
    check("figma tokens: the default list never runs it (it reads ADO and a keychain); the extra row the help gives "
          "runs it once",
          not any("--figma-tokens" in argv for _, argv, *_ in AUDITS)
          and extra_audits(rows) == [("figma tokens", ["scheduled_audits.py", "--figma-tokens"])])


def reds_selftest(check):
    """Each red line's audit days and owner or hold, the notification only on a new red or one unowned RED_DAYS
    audit days, a row's own timeout, and a slow child killed with its group."""
    global LEDGER_DIR, BARE_PROJECTS, ADO_LINKS_ARGS
    kept = (LEDGER_DIR, BARE_PROJECTS, ADO_LINKS_ARGS)
    zdotdir = os.environ.get("ZDOTDIR")
    with tempfile.TemporaryDirectory() as t:
        try:
            plants = {"finds.py": "import sys; print('1 of 2'); sys.exit(1)\n", "clean.py": "import sys; sys.exit(0)\n",
                      "sleeps.py": "import time; time.sleep(5)\n",
                      # A grandchild whose output the child captures, so it holds none of the row's pipes, and
                      # which would outlive the row's timeout by far.
                      "slow.py": "import subprocess, sys, time\n"
                                 "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
                                 "stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                                 "open(sys.argv[1], 'w').write(str(c.pid))\ntime.sleep(60)\n",
                      ".zprofile": ""}
            for name, src in plants.items():
                with open(os.path.join(t, name), "w", encoding="utf-8") as f:
                    f.write(src)
            # Owners: questions held open in the request ledger. Held ones name the slow census, skill_use and
            # drafts-headings, and one names only a helper called naming(); an answered one names setup_drift.
            led = os.path.join(t, "ledger")
            os.makedirs(led)
            q = {"ts": "2026-11-01T09:00:00Z", "session": "sh", "source": "card", "kind": "question", "text": "Later"}
            held = [("qh", "q-5k1110", "open", "Retire skill_use's share check?"),
                    ("qc", "q-5k1112", "open", "Should the slow census row get a timeout above its child's?"),
                    ("qd", "q-5k1113", "open", "Date the undated headings the drafts-headings audit names?"),
                    ("qn", "q-5k1114", "open", "Match each rule only against the command naming() found?"),
                    ("qa", "q-5k1111", "answered", "Is setup_drift red on purpose?")]
            with open(os.path.join(led, "requests.jsonl"), "w", encoding="utf-8") as f:
                f.write("".join(json.dumps(dict(q, id=i, qid=qid, state=st, question=text)) + "\n"
                                for i, qid, st, text in held))
            os.makedirs(os.path.join(t, "projects"))
            LEDGER_DIR, BARE_PROJECTS = led, os.path.join(t, "projects")
            os.makedirs(os.path.join(t, "adoempty"))
            ADO_LINKS_ARGS = {"known": set(), "places": (os.path.join(t, "adoempty"),), "root": t,
                              "cache": os.path.join(t, "none")}
            # Two earlier audit days in the log; this run is the third.
            log = os.path.join(t, "logs", "audits.log")
            os.makedirs(os.path.dirname(log))
            day = lambda k: (datetime.date.today() - datetime.timedelta(days=k)).isoformat()
            hist = {"workspace_audit naming": ("1", "1"), "slow census": ("did not run (timeout after 600s)", "1"),
                    "setup_drift": ("1", "1"), "skill_use": ("1", "1"), "drafts headings": ("1", "1"),
                    "workspace_audit archive": ("0", "1"), "clean one": ("1", "1"),
                    # Red, then clean the day before this run: a clean day ends the streak, so it is 1 day and new.
                    "back again": ("1", "0")}
            with open(log, "w", encoding="utf-8") as f:
                for i, d in enumerate((day(2), day(1))):
                    f.write("".join(f"{d}T08:00:00\t{n}\t{v[i]}\n" for n, v in hist.items()))
            audits = [(n, ["clean.py" if n == "clean one" else "finds.py"]) for n in list(hist) + ["planted new"]]
            md_at = os.path.join(os.path.dirname(output_path(log, "x")), DIGEST)
            sent = []
            run(audits, log, t, timeout=20, alert=sent.append)
            md = open(md_at, encoding="utf-8").read() if os.path.isfile(md_at) else ""
            first = sent[0] if sent else ""
            check("reds: a planted red 3 audit days with no owner notifies (known bad): the naming audit, which a "
                  "question naming only naming() doesn't own, and setup_drift, which only an answered question names",
                  len(sent) == 1 and "red 3+ audit days with no owner: workspace_audit naming, setup_drift" in first)
            check("reds: an owned red 3 audit days doesn't notify (known good): a held question owns each",
                  bool(first) and not any(n in first for n in ("slow census", "skill_use", "drafts headings")))
            check("reds: an unowned red 2 audit days doesn't notify yet, and a clean audit gets no line (known good)",
                  bool(first) and "archive" not in first and "**clean one**" not in md)
            check("reds: a red the previous run didn't have notifies as new (known bad)",
                  "new red: back again, planted new" in first)
            check("reds: today.md shows each red's audit days and its owner or hold, else no owner, and the count",
                  all(x in md for x in (
                      "- 2 of 5 red 3+ audit days have no owner: workspace_audit naming, setup_drift\n",
                      "- **workspace_audit naming**: findings; red 3 audit days; no owner\n    1 of 2\n",
                      "- **slow census**: findings; red 3 audit days; owner: held q-5k1112\n",
                      "- **setup_drift**: findings; red 3 audit days; no owner\n",
                      "- **skill_use**: findings; red 3 audit days; owner: held q-5k1110\n",
                      "- **drafts headings**: findings; red 3 audit days; owner: held q-5k1113\n",
                      "- **workspace_audit archive**: findings; red 2 audit days; no owner\n",
                      "- **back again**: findings; red 1 audit day (new); no owner\n",
                      "- **planted new**: findings; red 1 audit day (new); no owner\n"))
                  and md.index("## Needs a look") < md.index("have no owner") < md.index("**workspace_audit naming**"))
            time.sleep(1.1)                     # a later run start the same day
            run(audits, log, t, timeout=20, alert=sent.append)
            md2 = open(md_at, encoding="utf-8").read()
            check("reds: a second run the same day notifies nothing already named and adds no audit day (known good)",
                  len(sent) == 1 and "- **workspace_audit naming**: findings; red 3 audit days; no owner\n" in md2
                  and "- **planted new**: findings; red 1 audit day; no owner\n" in md2)
            LEDGER_DIR = os.path.join(t, "gone")
            later = (datetime.datetime.now() + datetime.timedelta(seconds=2)).isoformat(timespec="seconds")
            text, msg = digest(later, [(n, "1") for n, _ in audits if n != "clean one"], {}, log, time.time())
            check("reds: an unreadable request ledger says so on the line and notifies, never reads as owned or as none",
                  "- **slow census**: findings; red 3 audit days; no owner found, but the request ledger (no "
                  "requests.jsonl) could not be read\n" in text
                  and "with no owner: slow census, skill_use, drafts headings" in (msg or ""))
            LEDGER_DIR = led
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc, rc_none = reds_report(log), reds_report(os.path.join(t, "none.log"))
            said = buf.getvalue()
            check("reds: --reds prints the newest run's lines and the unowned count; no log is did not run",
                  rc == 0 and "2 of 5 red 3+ audit days have no owner: workspace_audit naming, setup_drift" in said
                  and "- **slow census**: findings; red 3 audit days; owner: held q-5k1112" in said and rc_none == 2
                  and "reds: did not run" in said)
            check("extra rows: a trailing true or false is the login shell, a whole number after it the row's own "
                  "timeout",
                  extra_audits([["a", "x.py", "--y", True, 3300], ["b", "x.py", False, 60], ["c", "x.py", "7", True],
                                ["d", "x.py"], ["e"]])
                  == [("a", ["x.py", "--y"], True, 3300), ("b", ["x.py"], False, 60), ("c", ["x.py", "7"], True),
                      ("d", ["x.py"])])
            got = dict(run([("own timeout", ["sleeps.py"], False, 1)], os.path.join(t, "own", "audits.log"), t,
                           timeout=20)[0])
            check("a row's own timeout is the one run() applies", got.get("own timeout") == "did not run (timeout after 1s)")
            # A slow child killed with its group, in a login shell where there is one, as a token-reading row runs.
            # A login shell and two Pythons can take over 10 s to start on a loaded machine, so a grandchild not yet
            # started at 10 s gets one more try at 30 s; one never started fails the check, never passes it.
            login = os.path.exists("/bin/zsh")
            os.environ["ZDOTDIR"] = t            # zsh -l reads the planted empty .zprofile, not yours
            for limit in (10, 30):
                pidf = os.path.join(t, f"grandchild-{limit}.pid")
                t0 = time.time()
                res = run_one(["slow.py", pidf], t, limit, login=login)[0]
                took = time.time() - t0
                pid = int(open(pidf).read() or 0) if os.path.isfile(pidf) else 0
                if pid > 0:
                    break

            def alive(pid):
                for _ in range(10):              # a killed one is reaped within milliseconds; it would live 30 s
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        return False
                    except PermissionError:
                        return True
                    time.sleep(0.1)
                return True
            check("a slow child is killed with its group (known bad when only the child is killed): the row is did "
                  "not run at its timeout, and the grandchild it started doesn't live on",
                  res == f"did not run (timeout after {limit}s)" and took < limit + 10 and pid > 0 and not alive(pid))
        finally:
            LEDGER_DIR, BARE_PROJECTS, ADO_LINKS_ARGS = kept
            os.environ.pop("ZDOTDIR", None) if zdotdir is None else os.environ.update(ZDOTDIR=zdotdir)


def selftest():
    global LEDGER_DIR, BARE_PROJECTS, ADO_LINKS_ARGS
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(("PASS " if cond else "FAIL ") + label)

    plants = {
        "clean.py": "import sys; sys.exit(0)\n",
        "finds.py": "import sys; print('1 of 2'); sys.exit(1)\n",
        "cant.py": "import sys; print('nothing to audit', file=sys.stderr); sys.exit(2)\n",
        "crash.py": "raise RuntimeError('boom')\n",
        "hang.py": "import time; time.sleep(30)\n",
        "odd.py": "import sys; sys.exit(3)\n",
    }
    with tempfile.TemporaryDirectory() as t:
        # No digest here walks your workspace or reads your ADO cache for the bare ADO id section.
        os.makedirs(os.path.join(t, "adoempty"))
        ADO_LINKS_ARGS = {"known": set(), "places": (os.path.join(t, "adoempty"),), "root": t,
                          "cache": os.path.join(t, "no-cache.json")}
        for name, src in plants.items():
            with open(os.path.join(t, name), "w", encoding="utf-8") as f:
                f.write(src)
        log = os.path.join(t, "logs", "audits.log")
        audits = [(n[:-3], [n]) for n in plants] + [("gone", ["gone.py"])]
        results, rc = run(audits, log, t, timeout=2)
        got = dict(results)
        check("exit 0 is logged as 0", got["clean"] == "0")
        check("exit 1 is logged as 1", got["finds"] == "1")
        check("exit 2 is logged as did not run", got["cant"] == "did not run (exit 2)")
        check("a traceback is did not run, not findings", got["crash"] == "did not run (crashed, exit 1)")
        check("a hang is cut off and logged as did not run", got["hang"] == "did not run (timeout after 2s)")
        check("an unknown exit code is did not run", got["odd"] == "did not run (exit 3)")
        check("a missing script is did not run", got["gone"] == "did not run (missing gone.py)")
        check("findings outrank did-not-run in the exit code", rc == 1)
        with open(log, encoding="utf-8") as f:
            lines = f.read().splitlines()
        check("one tab-separated line per audit, one start time",
              len(lines) == 7 and all(len(l.split("\t")) == 3 for l in lines)
              and len({l.split("\t")[0] for l in lines}) == 1)
        kept = output_path(log, "finds")
        text = open(kept, encoding="utf-8").read() if os.path.isfile(kept) else ""
        check("a non-zero audit's output is kept beside the log", "1 of 2" in text)
        check("a clean audit's output is not kept", not os.path.exists(output_path(log, "clean")))
        # A node script: run under node, a finding and an uncaught error read as Python's do.
        node_plants = {"n_clean.mjs": "process.exit(0);\n", "n_finds.mjs": "console.log('1 of 2'); process.exit(1);\n",
                       "n_crash.mjs": "throw new Error('boom');\n"}
        for name, src in node_plants.items():
            with open(os.path.join(t, name), "w", encoding="utf-8") as f:
                f.write(src)
        got_n = {n: run_one([n], t, 20)[0] for n in node_plants}
        if find_node():
            check("a .mjs audit runs under node: exit 0 is 0, exit 1 is 1, an uncaught error is did not run",
                  got_n == {"n_clean.mjs": "0", "n_finds.mjs": "1", "n_crash.mjs": "did not run (crashed, exit 1)"})
        else:
            check("with no node installed, every .mjs audit is did not run (no node), never clean (the node cases "
                  "need node to run)", set(got_n.values()) == {"did not run (no node)"})

        _, rc = run([("clean", ["clean.py"]), ("cant", ["cant.py"])], log, t, timeout=2)
        check("no findings plus a did-not-run exits 2", rc == 2)
        _, rc = run([("clean", ["clean.py"])], log, t, timeout=2)
        check("all clean exits 0", rc == 0)
        with open(log, encoding="utf-8") as f:
            check("later runs append, earlier lines stay", len(f.read().splitlines()) == 10)

        blocked = os.path.join(t, "clean.py", "audits.log")
        _, rc = run([("clean", ["clean.py"])], blocked, t, timeout=2)
        check("an unwritable log exits 2", rc == 2)

        # The digest and the notification, with a planted upkeep step that writes its JSON.
        plants2 = {"up_clean.py": "import sys, json; json.dump([{'line': 'worktree-prune: removed 1 of 2', "
                                  "'kept': ['wt-a (uncommitted changes)']}], open(sys.argv[2], 'w'))\n",
                   "up_none.py": "import sys; sys.exit(0)\n",
                   # Exits 3 unless a login shell read the planted .zprofile below.
                   "up_login.py": "import os, sys\nsys.exit(0 if os.environ.get('PLANTED_LOGIN') == '1' else 3)\n"}
        for name, src in plants2.items():
            with open(os.path.join(t, name), "w", encoding="utf-8") as f:
                f.write(src)
        log2 = os.path.join(t, "logs2", "audits.log")
        folder = os.path.dirname(output_path(log2, "x"))
        sent = []
        led = os.path.join(t, "ledger")
        os.makedirs(led)
        planted = [{"id": f"q{i}", "ts": f"2026-10-{1 + i:02d}T09:00:00Z", "session": f"s{i}", "title": f"Planted {i}",
                    "source": "typed", "kind": "request", "state": "open", "text": f"planted open ask {i}."}
                   for i in range(17)]
        planted.append({"id": "qd", "ts": "2026-10-01T08:00:00Z", "session": "sd", "source": "typed",
                        "kind": "request", "state": "done", "ref": "1234abc", "text": "planted done ask"})
        # Requests from another machine's sessions, older than every local one, and a question: none takes a line
        # from this machine's.
        winw = {"worktree": "C:\\Users\\x\\Desktop"}
        planted += [{"id": f"w{i}", "ts": f"2026-06-{1 + i:02d}T09:00:00Z", "session": "sw", "title": f"Far {i}",
                     "source": "typed", "kind": "request", "state": "open", "text": f"planted far ask {i}.",
                     "state_refs": winw} for i in range(20)]
        planted.append({"id": "wq", "ts": "2026-06-21T09:00:00Z", "session": "sw", "source": "card", "kind": "question",
                        "qid": "q-9c9c9c", "state": "open", "text": "Later", "question": "Planted far question?",
                        "state_refs": winw})
        with open(os.path.join(led, "requests.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in planted) + "\n")
        LEDGER_DIR = led
        # One planted session log for bare_ids.section(): a bare work-item id and a linked Figma node, written now.
        os.makedirs(os.path.join(t, "projects", "p"))
        with open(os.path.join(t, "projects", "p", "s.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": datetime.datetime.now().astimezone().isoformat(),
                                "message": {"content": [{"type": "text", "text": "Closed #4567; see https://www.figma.com/"
                                                         "design/K/W?node-id=1-2"}]}}) + "\n")
        BARE_PROJECTS = os.path.join(t, "projects")
        login_ok = None
        if os.path.exists("/bin/zsh"):
            with open(os.path.join(t, ".zprofile"), "w", encoding="utf-8") as f:
                f.write("export PLANTED_LOGIN=1\n")
            zdotdir = os.environ.get("ZDOTDIR")
            os.environ["ZDOTDIR"] = t          # zsh -l reads this .zprofile, not yours
            try:
                login_ok = dict(run([("login", ["up_login.py"], True)], os.path.join(t, "logs3", "a.log"), t,
                                    timeout=20)[0]).get("login") == "0"
            finally:
                if zdotdir is None:
                    os.environ.pop("ZDOTDIR", None)
                else:
                    os.environ["ZDOTDIR"] = zdotdir
            check("a login-shell step runs in zsh -l (it read the planted .zprofile)", login_ok)
        # One planted doc for ado_links.section(): a bare ADO id; the ADO cache is missing on purpose.
        os.makedirs(os.path.join(t, "adodocs"))
        with open(os.path.join(t, "adodocs", "a.md"), "w", encoding="utf-8") as f:
            f.write("Closed #9811.\n")
        ADO_LINKS_ARGS = {"known": {9811}, "places": (os.path.join(t, "adodocs"),), "root": t,
                          "cache": os.path.join(t, "no-cache.json")}
        kept_ado = kit_config.ado
        kit_config.ado = lambda: ("https://dev.azure.com/Org", "Proj")
        try:
            results, _ = run([("upkeep cleanup", ["up_clean.py", "--json", os.path.join(folder, CLEANUP_JSON)]),
                              ("finds", ["finds.py"]), ("cant", ["cant.py"])],
                             log2, t, timeout=20, alert=sent.append)
            kit_config.ado = lambda: (None, None)
            no_ado = digest("2026-11-01T08:00:00", [("clean", "0")], {}, os.path.join(t, "noado.log"), time.time())[0]
        finally:
            kit_config.ado = kept_ado
        md = open(os.path.join(folder, DIGEST), encoding="utf-8").read() if os.path.isfile(os.path.join(folder, DIGEST)) else ""
        check("the digest names a red audit with its audit days, owner and failing line",
              "**finds**: findings; red 1 audit day (new); no owner\n    1 of 2" in md)
        check("the digest names an audit that did not run", "**cant**: did not run (exit 2)" in md)
        check("the digest carries the cleanup lines and what was kept",
              "worktree-prune: removed 1 of 2" in md and "kept wt-a (uncommitted changes)" in md)
        check("one notification names each new red, a did-not-run among them",
              len(sent) == 1 and "new red: finds, cant (did not run)" in sent[0])
        check("the digest lists this machine's 15 oldest open requests with your words, counts the rest, skips a done "
              "one; 20 older requests from another machine take none of its lines and get one line pointing at "
              "DIGEST.md",
              "## Open requests\n- 17 requests you typed on this machine" in md
              and 'Planted 0: "planted open ask 0."' in md and 'Planted 14: "planted open ask 14."' in md
              and "planted open ask 15" not in md and "and 2 newer: python tools/ledger.py --open --source this" in md
              and "planted done ask" not in md and "planted far ask" not in md
              and "\n- 20 more from other machines' sessions, 6/1 to 6/21: listed in full at the end of " in md
              and md.index("## Open requests") < md.index("more from other machines") < md.index("## Push-backs")
              and md.index("## Open requests") < md.index("Log: "))
        check("the push-back section follows Open requests",
              "## Push-backs, last 7 days\n" in md
              and md.index("## Open requests") < md.index("## Push-backs") < md.index("Log: "))
        check("the bare-id section follows Push-backs and counts the planted log: 1 bare of 2 ids",
              "## Bare ids, last 7 days\n" in md and
              f"- {datetime.date.today():%m-%d} (so far): 1 bare of 2 ids, 50% bare (Figma 0 of 1, ADO 1 of 1), in 1 sessions" in md
              and md.index("## Push-backs") < md.index("## Bare ids") < md.index("Log: "))
        check("the bare ADO id section counts the planted doc, and says the unread cache did not run",
              "## Bare ADO ids in docs and ADO\n- adodocs: 1 bare of 1 ids, 0 linked\n" in md
              and "- ADO: did not run" in md and md.index("## Bare ids") < md.index("## Bare ADO ids") < md.index("Log: "))
        check("with no ADO project set, the bare ADO id section says not run and counts no doc",
              "## Bare ADO ids in docs and ADO\n- not run: ado.org or ado.project is unset" in no_ado
              and "bare of" not in no_ado.split("## Bare ADO ids", 1)[1])
        import bare_ids
        led_ado = os.path.join(t, "ledger-ado")
        os.makedirs(led_ado)
        with open(os.path.join(led_ado, "requests.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(planted[0], text="close #2820 when the footer ships")) + "\n")
        kept_ado, kept_linked = kit_config.ado, kit_config.ado_linked
        kit_config.ado = lambda: ("https://dev.azure.com/Org", "Proj")
        try:
            cited = "\n".join(open_requests_section(lambda p: p, led_ado))
            kit_config.ado_linked = lambda text, org=None, project=None: text
            bare = "\n".join(open_requests_section(lambda p: p, led_ado))
        finally:
            kit_config.ado, kit_config.ado_linked = kept_ado, kept_linked
        check("an open request that cites #2820 ends its line with the item's link; printed without links it is bare",
              "#2820" in cited and not bare_ids.unlinked(cited) and "/_workitems/edit/2820/" in cited
              and [i for _, i in bare_ids.unlinked(bare)] == ["#2820"])
        # The unused-tools check names one line per tool; today.md keeps every one, past the six-line cut.
        with open(os.path.join(t, "many.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nprint('unused tools: 9 of 40 tools have no session run and no caller')\n"
                    "for i in range(9):\n    print(f'FAIL planted_{i}.py (3 lines): no session run')\nsys.exit(1)\n")
        run([(UNUSED, ["many.py"])], log2, t, timeout=20)
        md_u = open(os.path.join(folder, DIGEST), encoding="utf-8").read()
        check("the digest lists every tool the unused check names, past the six-line cut",
              all(f"FAIL planted_{i}.py" in md_u for i in range(9)) and "more lines" not in md_u)
        LEDGER_DIR = os.path.join(t, "no-ledger")
        sent.clear()
        sys.path.insert(0, TOOLS)
        import bare_ids
        real_section = bare_ids.section

        def broken(**kw):
            raise RuntimeError("planted")
        bare_ids.section = broken
        try:
            run([("upkeep cleanup", ["up_none.py"]), ("clean", ["clean.py"])], log2, t, timeout=20, alert=sent.append)
        finally:
            bare_ids.section = real_section
        md = open(os.path.join(folder, DIGEST), encoding="utf-8").read()
        check("a bare-id count that raises is a did-not-run line, and the rest of today.md is still written",
              "## Bare ids, last 7 days\n- did not run (RuntimeError)" in md and "Log: " in md)
        check("a step that wrote no JSON this run shows as did not run, not last run's numbers",
              "upkeep cleanup did not run" in md)
        check("a missing request ledger reads as did not run, not as no open requests or no push-backs",
              "## Open requests\n- the request ledger did not run" in md
              and "## Push-backs, last 7 days\n- did not run" in md)
        LEDGER_DIR = BARE_PROJECTS = None
        ADO_LINKS_ARGS = {"known": set(), "places": (os.path.join(t, "adoempty"),), "root": t,
                          "cache": os.path.join(t, "no-cache.json")}
        check("all clean posts no notification", not sent)

        # The watchdog: a stale log, a stale mirror or a stopped keep-alive agent alerts once a day.
        wlog = os.path.join(t, "wd", "audits.log")
        os.makedirs(os.path.dirname(wlog))
        with open(wlog, "w", encoding="utf-8") as f:
            f.write("2026-10-18T08:00:05\tskill_lint\t0\n")
        mlog = os.path.join(t, "wd", "mirror.out.log")
        open(mlog, "w").close()
        import plistlib
        plists = os.path.join(t, "wd", "LaunchAgents")
        os.makedirs(plists)
        P = "local.me."
        for label, extra in ((P + "serve", {"KeepAlive": True}), (P + "planted-exit", {"StartInterval": 300}),
                             (P + "daily", {"StartCalendarInterval": {"Hour": 8}}), ("com.other.thing", {"KeepAlive": True})):
            with open(os.path.join(plists, label + ".plist"), "wb") as f:
                plistlib.dump({"Label": label, **extra}, f)

        def at(when, mirrored_minutes_ago=10):
            stamp = (when - datetime.timedelta(minutes=mirrored_minutes_ago)).timestamp()
            os.utime(mlog, (stamp, stamp))
            return when

        def states(**over):
            base = {"serve": {"running": True, "last_exit": None},
                    "planted_exit": {"running": False, "last_exit": 0},
                    "daily": {"running": False, "last_exit": 1}}
            base.update(over)
            return lambda label: base.get(label.replace(P, "").replace("-", "_"))
        up = states()
        got = []

        def wd(when, state=up, minutes=10):
            return watchdog_alert(wlog, got.append, at(when, minutes), state, mlog, plists, set, P,
                                  (P + "planted-exit",))
        p = wd(datetime.datetime(2026, 10, 20, 9, 0))
        check("watchdog: a log 49 hours old alerts",
              set(p) == {"daily-run"} and len(got) == 1 and "2026-10-18 08:00" in got[0])
        wd(datetime.datetime(2026, 10, 20, 11, 0))
        check("watchdog: the same problem does not alert again within a day", len(got) == 1)
        wd(datetime.datetime(2026, 10, 21, 9, 30))
        check("watchdog: it alerts again after a day", len(got) == 2)
        with open(wlog, "a", encoding="utf-8") as f:
            f.write("2026-10-21T08:00:05\tskill_lint\t0\n")
        p = wd(datetime.datetime(2026, 10, 21, 10, 0))
        check("watchdog: a fresh log, a recent mirror, every agent loaded and a daily job that exited 1 is quiet",
              not p and len(got) == 2)
        p = wd(datetime.datetime(2026, 10, 21, 10, 0),
               states(serve={"running": False, "last_exit": -9}, daily=None, planted_exit={"running": False, "last_exit": 1}))
        check("watchdog: a stopped keep-alive agent, an unloaded agent and an exit_matters agent exiting 1 each alert",
              set(p) == {P + "serve", P + "daily", P + "planted-exit"} and len(got) == 3
              and "serve is not running" in got[2] and "daily is not loaded" in got[2] and "last exited 1" in got[2])
        check("watchdog: only plists with the configured prefix are watched, and KeepAlive is read from each",
              our_agents(plists, P) == {P + "daily": False, P + "planted-exit": False, P + "serve": True})
        p = wd(datetime.datetime(2026, 10, 21, 10, 0), minutes=210)
        check("watchdog: a mirror log 210 minutes old alerts",
              set(p) == {"desktop-mirror"} and len(got) == 4 and "mirror has not run since 2026-10-21 06:30" in got[3])
        p = watchdog(wlog, datetime.datetime(2026, 10, 21, 10, 0), up, mlog, os.path.join(t, "wd", "none"), set, P)
        check("watchdog: no LaunchAgents folder is a problem, not a clean bill", "agents" in p)
        p = watchdog(wlog, datetime.datetime(2026, 10, 21, 10, 0), up, "", plists, set, "")
        check("watchdog: with no mirror log and no agent prefix configured, only the daily log is watched",
              not p)
        unloaded = states(daily=None)
        check("watchdog: an unloaded agent disabled in launchd is paused, not a problem",
              not watchdog(wlog, at(datetime.datetime(2026, 10, 21, 10, 0)), unloaded, mlog, plists,
                           lambda: {P + "daily"}, P))
        check("watchdog: an unloaded agent alerts when only another one is disabled",
              set(watchdog(wlog, at(datetime.datetime(2026, 10, 21, 10, 0)), unloaded, mlog, plists,
                           lambda: {P + "serve"}, P)) == {P + "daily"})
        check("watchdog: print-disabled is read for disabled and true, never enabled or false",
              parse_disabled('\tdisabled services = {\n\t\t"local.me.a" => disabled\n\t\t"local.me.b" => enabled\n'
                             '\t\t"local.me.c" => true\n\t\t"local.me.d" => false\n\t}\n')
              == {"local.me.a", "local.me.c"})

    figma_tokens_selftest(check)
    unused_selftest(check)
    reds_selftest(check)
    check("secrets is never in the scheduled list", not any("secrets" in a for _, argv, *_ in AUDITS for a in argv))
    plan = with_upkeep([("an audit", ["a.py"])], "")
    check("the daily plan is cleanup, then the audits", [s[0] for s in plan] == ["upkeep cleanup", "an audit"])
    check("every scheduled script exists here",
          all(os.path.isfile(os.path.join(TOOLS, argv[0])) for _, argv, *_ in with_upkeep(AUDITS, "")))
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="scheduled_audits.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=LOG, help=f"file to append to (default {LOG})")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help=f"seconds per audit (default {TIMEOUT})")
    ap.add_argument("--selftest", action="store_true",
                    help="planted audits: clean, findings, can't-run, crash, hang, missing")
    ap.add_argument("--watchdog", action="store_true",
                    help="print what is meant to run by itself and has stopped; exit 1 if anything has")
    ap.add_argument("--figma-tokens", action="store_true",
                    help=f"CI's and the local Figma token's days since saving: WARN at {TOKEN_WARN_DAYS}, FAIL at "
                         f"{TOKEN_CAP_DAYS}; exit 1 on either, 2 when a date can't be read")
    ap.add_argument("--unused", action="store_true",
                    help=f"tools here with no session run in {UNUSED_DAYS} days that nothing calls; exit 1 on any")
    ap.add_argument("--reds", action="store_true",
                    help=f"the newest run's red lines with their audit days and owner, and how many red {RED_DAYS}+ "
                         "audit days have no owner; reads only")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(kit_config.run_isolated(selftest))
    if a.reds:
        sys.exit(reds_report(a.log))
    if a.figma_tokens:
        sys.exit(figma_tokens_check())
    if a.unused:
        sys.exit(unused_check())
    if a.watchdog:
        found = watchdog(a.log, datetime.datetime.now())
        agents = our_agents()
        paused = sorted(set(agents) & disabled_agents())
        print("\n".join(found.values())
              or "watchdog: the daily run is current"
                 + (" and so is the mirror" if MIRROR_LOG else "")
                 + (f"; {len(agents) - len(paused)} agents loaded, each keep-alive one running" if AGENT_PREFIX else "")
                 + (f"; paused on purpose: {', '.join(paused)}" if paused else ""))
        sys.exit(1 if found else 0)
    rc = run(with_upkeep(configured_audits(), os.path.dirname(output_path(a.log, "x"))), a.log, TOOLS, a.timeout,
             alert=lambda m: notify(m, "Workspace audits"))[1]
    # After the run, so its own fresh line is in the log: this call watches the mirror and the agents.
    try:
        for problem in watchdog_alert(a.log, alert=lambda m: notify(m, "Workspace watchdog")).values():
            print(f"watchdog: {problem}")
    except Exception as e:
        print(f"watchdog: DID NOT RUN ({type(e).__name__}: {e})")
    sys.exit(rc)
