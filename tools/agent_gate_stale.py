#!/usr/bin/env python3
"""agent_gate_stale.py - list each gated agent or skill whose last passing eval no longer matches what runs.

    python tools/agent_gate_stale.py [--suites DIR] [--project DIR]   one line per unit; exit 1 when any needs a re-run
    python tools/agent_gate_stale.py --selftest                       planted units: current, edited, model moved, none, gaps, accepted, version moved

WHY. A unit (an agent or a skill) is gated once by its eval suite. The result goes stale when the
unit's file changes, the model behind it moves, or Claude Code itself is updated. Agent files often
say `model: opus`, an alias, so a model rollout changes what runs with no file edit, and an update
changes what runs with no edit at all. Nothing re-runs a suite after any of these unless something
checks. Run this daily (from a scheduler of your own), so a stale unit shows without anyone
remembering.

WHERE THE SUITES ARE. --suites DIR, else the config key agent_gate.suites (kit_config.py). With
neither, it stops with exit 2 and names the key. Each suite is one folder under it, holding:
  unit.json       {"unit": "cold-reader", "file": "~/.claude/agents/cold-reader.md", "run": "<command>",
                   "suite": [<the files that define its cases and checks>],                 (optional)
                   "accepted": {"sha": "<unit sha>", "date": "<date>", "by": "<who>"},      (optional)
                   "cost": "running_total",                                                 (optional)
                   "draft_run": "<re-runs only the draft arm and writes a receipt>"}        (optional)
  receipts.jsonl  one line per gate run: {"date", "unit_sha", "model", "pass", "summary", "failed": [...],
                   "gaps": [...], "suite_sha", "cost_usd", "claude", "claude_by_arm": {"<arm>": [...]},
                   "draft": {"passed": n, "ran": n}}
Each line prices the unit's last run from cost_usd. By default a receipt's cost_usd is that run's own
cost. A runner that writes the unit's running total of spend instead (every run it ever had) sets
"cost": "running_total" in unit.json: its last run is the newest total minus the last earlier, lower one,
since a receipt written again without a run repeats the total. Reading a running total as one run's cost
prices every run the unit ever had.
The suite itself (whatever "run" names, e.g. a `claude plugin eval` suite) writes the receipts; this
tool only reads them. The unit's sha is sha1 of its file, first 7 hex digits; a skill is a folder, and
every file in it counts (see file_sha), so a suite runner must stamp receipts with the same hash, and
suite_sha with suite_sha() over the files "suite" names.

THE STATES. The newest receipt for the unit's (sha, model) pair decides: a pass is CURRENT, a fail
FAILED, which a person reads and nothing re-runs. STALE is the one state a re-run clears: no receipt,
a suite file changed after it (so a check edited after a fail can't pass clean), a receipt with
gaps (a case not run, a run unscored), where no verdict was read, or one made on another Claude Code
version than a re-run would launch. So one change costs at most one run, however many days it stays
red. A skill folder no suite names is UNTESTED, since a skill is live the moment its folder exists,
commit or not. A unit is ACCEPTED while its file keeps the sha its unit.json "accepted" names,
whatever its receipts say: a person accepts a skill without a suite, or as its suite measured it.
Once the file changes, one without a suite is UNTESTED and one with a suite is judged by its receipts
again. UNKNOWN: the version a re-run launches could not be read, so the receipt can't be vouched for.

THE VERSION. A receipt holds only on the Claude Code version a suite re-run would launch now, so a
re-run can always clear a version STALE. That version is what the config key agent_gate.version_cmd
prints, else `claude --version` (the claude on PATH); the command is run without a shell and must
print the version first, as `claude --version` does. Give a login shell (`zsh -lc 'claude --version'`)
when your suites run in one, since a scheduler's PATH can find another claude. Like any _cmd key, it
counts from a project's file only once accepted (kit_config.py), and a unit.json can't name one, so
a cloned suites folder can't choose what runs. A receipt names the versions its runs used, read from
each run's own session log rather than from `claude --version` when the receipt is written: per arm
in "claude_by_arm", or one "claude" for a runner that records only its draft arm. It holds when every
version it names is today's. It also holds when only its draft arm was re-run on today's version and
every draft run passed ("draft"): a unit whose unit.json names "draft_run" gets that draft-arm re-check named on a
version move, a fraction of a full run's cost (about a third with four arms), and a failed draft run
names the full suite. A receipt that names no version is STALE, and a version that can't be read is
UNKNOWN, never CURRENT. The receipt certifies the version a re-run launches, not the copy your own
sessions run, which can lag or lead it; when the newest session logs ran another version, a note line
says so.

THE LIVE MODEL. A full model id in the unit's frontmatter is the answer. Otherwise the model of that
agent type's newest launch in the project's session logs (--project, default the current project's
folder under ~/.claude/projects), else the most common id of its family across the newest main logs.

BLIND TO. A change in the settings or environment a suite runs in: only the unit's file, the model,
the Claude Code version and the suite's own files stale a receipt.

It reads only; it runs no suite and spends nothing. Running a stale suite is a separate step.
Exit 0 when every unit is CURRENT or ACCEPTED; 1 when any is STALE, FAILED or UNTESTED; 2 when it
can't tell (no suites folder set, no session log, an unreadable suite, a version it can't read).
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    if HERE not in sys.path: sys.path.append(HERE)


def default_logs(project=None):
    """The project's session-log folder: --project, else cc_logs.project_dir() for the current folder."""
    if project:
        return os.path.abspath(os.path.expanduser(project))
    import cc_logs
    return cc_logs.project_dir()


def default_skills():
    """Where a skill loads from in a session here: your skills, and the current project's own. A repo's
    .claude/skills loads only when work enters that repo, which is run from there. The project is
    kit_config.project_dir(): never the working folder inside the plugin's own folder."""
    try:
        import kit_config
    except ImportError:                      # a copy without kit_config beside it
        root = os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()
    else:
        root = kit_config.project_dir()
    return (os.path.join(os.path.expanduser('~'), '.claude', 'skills'), os.path.join(root, '.claude', 'skills'))


def suite_sha(paths):
    """sha1, first 7 hex digits, over a suite's own files (cases, checks, harness), each by its path as
    written in unit.json. None when the unit names none."""
    if not paths:
        return None
    h = hashlib.sha1()
    for rel in paths:
        p = os.path.expanduser(rel)
        h.update(rel.encode('utf-8') + b'\0')
        if os.path.exists(p):
            with open(p, 'rb') as f:
                h.update(f.read())
        h.update(b'\0')
    return h.hexdigest()[:7]


def file_sha(path):
    """sha1, first 7 hex digits, of a unit's file. A skill is a folder: every file in it counts, by
    its path inside the folder, so an edit to a reference file stales the receipt as an edit to
    SKILL.md does."""
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        with open(path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()[:7]
    h = hashlib.sha1()
    texts = []

    def add(folder, prefix=''):
        for root, dirs, files in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if d not in ('__pycache__', '.git'))
            for n in sorted(f for f in files if f != '.DS_Store'):
                p = os.path.join(root, n)
                h.update((prefix + os.path.relpath(p, folder)).encode('utf-8') + b'\0')
                with open(p, 'rb') as f:
                    data = f.read()
                h.update(data + b'\0')
                texts.append(data.decode('utf-8', 'replace'))
    add(path)
    # A shared folder beside the skills (one with no SKILL.md of its own) counts for every skill whose
    # files name it: those skills read it, so an edit there changes them.
    parent = os.path.dirname(path.rstrip('/'))
    for shared in sorted(os.listdir(parent)):
        sp = os.path.join(parent, shared)
        if (os.path.isdir(sp) and sp.rstrip('/') != path.rstrip('/') and shared not in ('synced', '.git')
                and not os.path.exists(os.path.join(sp, 'SKILL.md')) and any(shared + '/' in t for t in texts)):
            add(sp, shared + '/')
    return h.hexdigest()[:7]


def models_in(path, tail_bytes=2_000_000):
    """Counter of the model ids assistant messages used in one log (its last tail_bytes)."""
    seen = collections.Counter()
    with open(path, 'rb') as f:
        f.seek(max(0, os.path.getsize(path) - tail_bytes))
        lines = f.read().decode('utf-8', 'replace').splitlines()[1:]
    for line in lines:
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = (o.get('message') or {}).get('model') if o.get('type') == 'assistant' else None
        if m and m.startswith('claude-'):
            seen[m] += 1
    return seen


def frontmatter_model(path):
    path = os.path.expanduser(path)
    if os.path.isdir(path):     # a skill: it runs on the main session's model unless it names one
        path = os.path.join(path, 'SKILL.md')
    text = open(path, encoding='utf-8').read()
    m = re.search(r'^model:\s*(\S+)', text.split('\n---', 1)[0], re.M)
    return m.group(1) if m else 'inherit'


def live_model(unit=None, alias='opus', logs=None, sessions=60, mains=30):
    """The model id a unit runs on today, or None.

    A full id in the unit's frontmatter is the answer. Otherwise: the model of the newest launch of
    that agent type (subagents/*.meta.json names the type, its .jsonl the model). With no launch
    on record, the most common id of that family (opus, sonnet, haiku) across the newest main logs.
    One log is never enough: a single session run on another model would read as a rollout."""
    if alias.startswith('claude-'):
        return alias
    logs = logs or default_logs()
    dirs = sorted((d for d in glob.glob(os.path.join(logs, '*', 'subagents')) if os.path.isdir(d)),
                  key=os.path.getmtime, reverse=True)[:sessions]
    if unit:
        launches = []
        for d in dirs:
            for meta in glob.glob(os.path.join(d, '*.meta.json')):
                try:
                    if json.load(open(meta)).get('agentType') == unit:
                        launches.append(meta)
                except (OSError, ValueError):
                    continue
        for meta in sorted(launches, key=os.path.getmtime, reverse=True)[:3]:
            log = meta[:-len('.meta.json')] + '.jsonl'
            seen = models_in(log) if os.path.exists(log) else None
            if seen:
                return seen.most_common(1)[0][0]
    family = alias if alias in ('opus', 'sonnet', 'haiku') else ''
    seen = collections.Counter()
    for path in sorted(glob.glob(os.path.join(logs, '*.jsonl')), key=os.path.getmtime, reverse=True)[:mains]:
        seen.update({m: n for m, n in models_in(path, 500_000).items() if family in m})
    return seen.most_common(1)[0][0] if seen else None


VERSION_CMD = 'claude --version'
VERSION_RE = re.compile(r'\s*(\d+\.\d+\.\d+)\b')


def default_version_cmd():
    """The config key agent_gate.version_cmd, else `claude --version`."""
    try:
        import kit_config
        return kit_config.get('agent_gate', 'version_cmd', default=None) or VERSION_CMD
    except ImportError:
        return VERSION_CMD


def launch_version(cmd=None, timeout=120):
    """The Claude Code version a suite re-run would launch now, as `cmd` prints it first (default:
    default_version_cmd()), or None when it doesn't answer. A receipt holds only on the version its
    runner launches, so a re-run can clear a version STALE."""
    import shlex
    import subprocess
    try:
        p = subprocess.run(shlex.split(cmd or default_version_cmd()), capture_output=True, text=True, timeout=timeout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    m = VERSION_RE.match(p.stdout or '')
    return m.group(1) if p.returncode == 0 and m else None


def live_versions(logs=None, n=30):
    """Counter of the Claude Code version the newest n main session logs ran, each log's last stated one."""
    logs = logs or default_logs()
    seen = collections.Counter()
    for path in sorted(glob.glob(os.path.join(logs, '*.jsonl')), key=os.path.getmtime, reverse=True)[:n]:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - 200_000))
            found = re.findall(r'"version":"(\d+\.\d+\.\d+)"', f.read().decode('utf-8', 'replace'))
        if found:
            seen[found[-1]] += 1
    return seen


def version_state(r, today, draft_run=False):
    """How a receipt stands against `today`, the version its runner launches: (state, note, rerun).
    state None: it holds (note says how, for a draft re-check). Else 'stale', the reason, and which re-run
    clears it: 'draft' (the unit's draft arm on today's version, when unit.json names a draft_run) or 'full'
    (its whole suite). A receipt names each arm's versions (claude_by_arm), or one (claude) for a runner
    that records only its draft arm; one that names none can't hold. A draft re-check costs a fraction of
    every arm, so a version move asks for it first, and for the whole suite only when a draft run fails."""
    by_arm = r.get('claude_by_arm') or ({'*': [r['claude']]} if r.get('claude') else {})
    allv = sorted({v for vs in by_arm.values() for v in vs})
    if not allv:
        return 'stale', 'the receipt records no Claude Code version', 'full'
    if allv == [today]:
        return None, '', None
    older = ', '.join(v for v in allv if v != today)
    d = r.get('draft') or {}
    if by_arm.get('draft') == [today] and d.get('ran'):
        if d.get('passed') == d['ran']:
            return None, f'; draft re-checked on Claude Code {today} ({d["passed"]}/{d["ran"]}), the other arms ran on {older}', None
        return 'stale', (f'a draft run failed on Claude Code {today} ({d.get("passed")}/{d["ran"]}) after the move from '
                         f'{older}, so the whole suite runs on it'), 'full'
    return ('stale', f'the receipt of {r.get("date")} ran on Claude Code {", ".join(allv)}, and a re-run now launches {today}',
            'draft' if draft_run else 'full')


def version_note(launch, live):
    """A line when live sessions run another Claude Code version than a suite re-run launches, else None.
    The receipts certify the version a re-run launches; your own sessions can run another copy, which can
    lag or lead it."""
    if not launch or not live or set(live) == {launch}:
        return None
    return (f'note: a suite re-run launches Claude Code {launch}; the {sum(live.values())} newest session '
            f'logs ran ' + ', '.join(f'{v} ({n})' for v, n in live.most_common())
            + '. A receipt covers the version a re-run launches, not the ones live sessions run.')


def last_run_cost(receipts, running_total):
    """Dollars the unit's last run cost, from its receipts in file order. With running_total (unit.json
    "cost": "running_total") the newest cost_usd minus the last earlier one below it, None when there is
    none to subtract; otherwise the newest cost_usd as it stands."""
    costs = [r['cost_usd'] for r in receipts if isinstance(r.get('cost_usd'), (int, float))]
    if not costs:
        return None
    if not running_total:
        return round(costs[-1], 2)
    lower = [t for t in costs[:-1] if t < costs[-1]]
    return round(costs[-1] - lower[-1], 2) if lower else None


def priced(detail, cost):
    """The detail with the last run's cost before its run command, so the command stays last."""
    if cost is None:
        return detail
    note = f'last run cost ${cost:.2f}'
    head, sep, tail = detail.rpartition('; run: ')
    return f'{head}; {note}{sep}{tail}' if sep else f'{detail}; {note}'


def check(suites, model_of=None, skills=None, logs=None, versions=None):
    """[(unit, status, detail)], one per unit; status is current, stale, failed, untested, accepted or
    unknown, by the states the module docstring names. A commit hook alone can't keep an untested
    skill out, so it is listed here. `skills` is one folder or several; a skill outside the first is
    named with its folder. `versions()` gives the Claude Code version a re-run launches (default
    launch_version, read once, and only when a unit has a receipt to judge)."""
    model_of = model_of or (lambda unit: live_model(unit['unit'], frontmatter_model(unit['file']), logs=logs))
    skills = default_skills() if skills is None else skills
    cache = {}

    def version_now():
        if 'v' not in cache:
            cache['v'] = versions() if versions else launch_version()
        return cache['v']
    rows = []
    covered = set()
    for unit_json in glob.glob(os.path.join(suites, '*', 'unit.json')):
        try:
            covered.add(os.path.realpath(os.path.expanduser(json.load(open(unit_json, encoding='utf-8'))['file'])))
        except (OSError, ValueError, KeyError):
            pass
    roots = (skills,) if isinstance(skills, str) else tuple(skills)
    for i, root in enumerate(roots):
        for skill_md in sorted(glob.glob(os.path.join(root, '*', 'SKILL.md'))):
            folder = os.path.dirname(skill_md)
            if os.path.realpath(folder) not in covered:
                where = '' if i == 0 else f' ({root.replace(os.path.expanduser("~"), "~")})'
                rows.append((os.path.basename(folder), 'untested', 'no suite names this skill folder' + where))
    for unit_json in sorted(glob.glob(os.path.join(suites, '*', 'unit.json'))):
        folder = os.path.dirname(unit_json)
        try:
            unit = json.load(open(unit_json, encoding='utf-8'))
            sha = file_sha(unit['file'])
            acc = unit.get('accepted')
            model = None if acc and not unit.get('suite') else model_of(unit)
        except (OSError, ValueError, KeyError) as e:
            rows.append((os.path.basename(folder), 'unknown', f'unreadable: {e}'))
            continue
        name, run = unit['unit'], unit.get('run', '?')
        if acc and (acc.get('sha') == sha or not unit.get('suite')):
            if acc.get('sha') == sha:
                how, then = ('as its suite measured it', 'STALE') if unit.get('suite') else ('without a suite', 'UNTESTED')
                rows.append((name, 'accepted', f'{sha} accepted {how} on {acc.get("date")} '
                                               f'({acc.get("by", "?")}); a change to the file makes it {then}'))
            else:
                rows.append((name, 'untested', f'accepted at {acc.get("sha")}, now {sha}: it needs a suite or a new '
                                               f'acceptance'))
            continue
        if not model:
            rows.append((name, 'unknown', 'no session log names the model it runs on'))
            continue
        receipts = []
        path = os.path.join(folder, 'receipts.jsonl')
        if os.path.exists(path):
            receipts = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
        pair = [r for r in receipts if r.get('unit_sha') == sha and r.get('model') == model]
        ssha = suite_sha(unit.get('suite'))
        r = pair[-1] if pair else None
        after = ' after a FAIL; a person reads that change before a re-run counts' if r and not r.get('pass') else ''
        gaps = (r.get('gaps') or []) if r else []
        if r and ssha and r.get('suite_sha') != ssha:
            rows.append((name, 'stale', f'{sha} on {model}: the suite\'s cases or checks changed since the receipt of '
                                        f'{r.get("date")}{after}; run: {run}'))
        elif gaps:
            rows.append((name, 'stale', f'{sha} on {model}: the receipt of {r.get("date")} has a gap, so no verdict '
                                        f'was read ({"; ".join(gaps)}); run: {run}'))
        elif r and not version_now():
            rows.append((name, 'unknown', f'{sha} on {model}: the Claude Code version a re-run launches could not be '
                                          f'read (`{default_version_cmd()}` did not answer)'))
        elif r and version_state(r, version_now(), bool(unit.get('draft_run')))[0]:
            _, why, rerun = version_state(r, version_now(), bool(unit.get('draft_run')))
            cmd = unit['draft_run'] if rerun == 'draft' else run
            rows.append((name, 'stale', f'{sha} on {model}: {why}{after}; run: {cmd}'))
        elif r and r.get('pass'):
            note = version_state(r, version_now(), bool(unit.get('draft_run')))[1]
            rows.append((name, 'current', f'{sha} passed on {r.get("date")} with {model}: {r.get("summary", "")}{note}'))
        elif r:
            rows.append((name, 'failed', f'{sha} on {model} failed on {r.get("date")} ({", ".join(r.get("failed", []))}); '
                                         f'a person decides; nothing re-runs it'))
        else:
            last = receipts[-1] if receipts else {}
            was = f'last receipt {last.get("unit_sha")} on {last.get("model")}' if last else 'no receipt'
            rows.append((name, 'stale', f'{sha} on {model} has never run ({was}); run: {run}'))
        rows[-1] = rows[-1][:2] + (priced(rows[-1][2], last_run_cost(receipts, unit.get('cost') == 'running_total')),)
    return rows


def report(rows, note=None):
    print(f'{len(rows)} gated unit(s)')
    for unit, status, detail in rows:
        print(f'{status.upper():8} {unit}: {detail}')
    if note:
        print(note)
    if any(s == 'unknown' for _, s, _ in rows):
        return 2
    return 1 if any(s in ('stale', 'failed', 'untested') for _, s, _ in rows) else 0


def suites_folder(arg=None):
    """--suites, else the config key agent_gate.suites; NotConfigured (exit 2 through kit_config.run)
    when neither is set."""
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    import kit_config
    return os.path.abspath(os.path.expanduser(kit_config.need('agent_gate', 'suites')))


def selftest():
    """Plant one unit per state and check each is read right, both ways."""
    V = lambda: 'v1'  # noqa: E731  the version a re-run launches, planted
    with tempfile.TemporaryDirectory() as tmp:
        def unit(name, body, receipts):
            folder = os.path.join(tmp, 'suites', name)
            os.makedirs(folder)
            agent = os.path.join(tmp, name + '.md')
            open(agent, 'w', encoding='utf-8').write(body)
            json.dump({'unit': name, 'file': agent, 'run': 'x'}, open(os.path.join(folder, 'unit.json'), 'w'))
            with open(os.path.join(folder, 'receipts.jsonl'), 'w') as f:
                for r in receipts:
                    f.write(json.dumps(r) + '\n')
            return hashlib.sha1(body.encode()).hexdigest()[:7]

        good = unit('good', 'A', [])
        with open(os.path.join(tmp, 'suites', 'good', 'receipts.jsonl'), 'w') as f:
            f.write(json.dumps({'unit_sha': good, 'model': 'm1', 'claude': 'v1', 'pass': True, 'date': 'd'}) + '\n')
        unit('edited', 'B', [{'unit_sha': 'old', 'model': 'm1', 'claude': 'v1', 'pass': True, 'date': 'd'}])
        moved = unit('moved', 'C', [])
        with open(os.path.join(tmp, 'suites', 'moved', 'receipts.jsonl'), 'w') as f:
            f.write(json.dumps({'unit_sha': moved, 'model': 'm0', 'claude': 'v1', 'pass': True, 'date': 'd'}) + '\n')
        failed = unit('failed', 'D', [])
        with open(os.path.join(tmp, 'suites', 'failed', 'receipts.jsonl'), 'w') as f:
            f.write(json.dumps({'unit_sha': failed, 'model': 'm1', 'claude': 'v1', 'pass': False, 'date': 'd'}) + '\n')
        unit('none', 'E', [])
        # The newest receipt for the pair decides: a fail after a pass is FAILED, a pass after a fail CURRENT.
        nf = unit('newest-fail', 'F', [])
        with open(os.path.join(tmp, 'suites', 'newest-fail', 'receipts.jsonl'), 'w') as f:
            f.write(json.dumps({'unit_sha': nf, 'model': 'm1', 'claude': 'v1', 'pass': True, 'date': 'd1'}) + '\n')
            f.write(json.dumps({'unit_sha': nf, 'model': 'm1', 'claude': 'v1', 'pass': False, 'date': 'd2'}) + '\n')
        np_ = unit('newest-pass', 'G', [])
        with open(os.path.join(tmp, 'suites', 'newest-pass', 'receipts.jsonl'), 'w') as f:
            f.write(json.dumps({'unit_sha': np_, 'model': 'm1', 'claude': 'v1', 'pass': False, 'date': 'd1'}) + '\n')
            f.write(json.dumps({'unit_sha': np_, 'model': 'm1', 'claude': 'v1', 'pass': True, 'date': 'd2'}) + '\n')
        # A unit that names its suite files: a receipt holds for the checks it ran under, not edited ones.
        cases_py = os.path.join(tmp, 'cases.py')
        open(cases_py, 'w').write('checks v1')
        for name, ok_ in (('suite-pass', True), ('suite-fail', False)):
            sha_ = unit(name, 'H' + name, [])
            uj = os.path.join(tmp, 'suites', name, 'unit.json')
            json.dump({**json.load(open(uj)), 'suite': [cases_py]}, open(uj, 'w'))
            with open(os.path.join(tmp, 'suites', name, 'receipts.jsonl'), 'w') as f:
                f.write(json.dumps({'unit_sha': sha_, 'model': 'm1', 'claude': 'v1', 'pass': ok_, 'date': 'd',
                                    'suite_sha': suite_sha([cases_py])}) + '\n')
        # A skill is a folder: its receipt is for the whole folder, and an edit to a reference stales it.
        # A shared folder it names (no SKILL.md of its own) counts too. A skill no suite names is UNTESTED.
        skills = os.path.join(tmp, 'skills')
        skill = os.path.join(skills, 'skill-x')
        os.makedirs(os.path.join(skill, 'references'))
        os.makedirs(os.path.join(skills, 'shared-refs'))
        os.makedirs(os.path.join(skills, 'skill-y'))
        open(os.path.join(skill, 'SKILL.md'), 'w').write('---\nname: x\n---\nRead shared-refs/s.md first.\n')
        open(os.path.join(skill, 'references', 'r.md'), 'w').write('one')
        open(os.path.join(skills, 'shared-refs', 's.md'), 'w').write('one')
        open(os.path.join(skills, 'skill-y', 'SKILL.md'), 'w').write('---\nname: y\n---\nno suite\n')
        for name in ('skill-kept', 'skill-edited'):
            os.makedirs(os.path.join(tmp, 'suites', name))
            json.dump({'unit': name, 'file': skill, 'run': 'x'}, open(os.path.join(tmp, 'suites', name, 'unit.json'), 'w'))
            with open(os.path.join(tmp, 'suites', name, 'receipts.jsonl'), 'w') as f:
                f.write(json.dumps({'unit_sha': file_sha(skill), 'model': 'm1', 'claude': 'v1', 'pass': True, 'date': 'd'}) + '\n')
        run = lambda: {u: s for u, s, _ in check(os.path.join(tmp, 'suites'), model_of=lambda unit: 'm1', versions=V, skills=skills)}
        got1 = run()
        open(cases_py, 'w').write('checks v2')
        got_edit = {u: (st, d) for u, st, d in check(os.path.join(tmp, 'suites'), model_of=lambda unit: 'm1', versions=V, skills=skills)}
        open(cases_py, 'w').write('checks v1')
        y_before = file_sha(os.path.join(skills, 'skill-y'))
        open(os.path.join(skills, 'shared-refs', 's.md'), 'w').write('two')
        got_shared = run()
        y_after = file_sha(os.path.join(skills, 'skill-y'))
        open(os.path.join(skills, 'shared-refs', 's.md'), 'w').write('one')
        open(os.path.join(skill, 'references', 'r.md'), 'w').write('two')
        got2 = run()
        got = {k: v for k, v in got1.items() if not k.startswith('skill-')}
        want = {'good': 'current', 'edited': 'stale', 'moved': 'stale', 'failed': 'failed', 'none': 'stale',
                'newest-fail': 'failed', 'newest-pass': 'current', 'suite-pass': 'current', 'suite-fail': 'failed'}
        ok = got == want
        print(('PASS' if ok else 'FAIL') + f' states: got {got}')
        se_ok = (got_edit['suite-pass'][0] == 'stale' and got_edit['suite-fail'][0] == 'stale'
                 and 'after a FAIL' in got_edit['suite-fail'][1] and 'after a FAIL' not in got_edit['suite-pass'][1]
                 and got_edit['good'][0] == 'current')
        print(('PASS' if se_ok else 'FAIL') + f' suite edited after the receipt: after a pass '
              f'{got_edit["suite-pass"][0]}, after a fail {got_edit["suite-fail"][0]} (flagged '
              f'{"after a FAIL" in got_edit["suite-fail"][1]}); a unit naming no suite unchanged {got_edit["good"][0]}')
        ok &= se_ok
        sk_ok = got1.get('skill-kept') == 'current' and got2.get('skill-edited') == 'stale'
        print(('PASS' if sk_ok else 'FAIL') + f' a skill folder: current {got1.get("skill-kept")}, '
              f'stale after a reference edit {got2.get("skill-edited")}')
        sh_ok = got_shared.get('skill-kept') == 'stale' and y_before == y_after
        print(('PASS' if sh_ok else 'FAIL') + f' a shared folder it names: stale after an edit there '
              f'{got_shared.get("skill-kept")}; a skill that does not name it unchanged {y_before == y_after}')
        un_ok = got1.get('skill-y') == 'untested' and 'skill-x' not in got1 and 'shared-refs' not in got1
        print(('PASS' if un_ok else 'FAIL') + f' a skill no suite names is untested: {got1.get("skill-y")}; '
              f'a covered skill and a shared folder are not listed')
        # A project skill (the project's .claude/skills) is listed too; reading your folder alone misses it.
        proj = os.path.join(tmp, 'project', '.claude', 'skills')
        os.makedirs(os.path.join(proj, 'skill-p'))
        open(os.path.join(proj, 'skill-p', 'SKILL.md'), 'w').write('---\nname: p\n---\nproject skill\n')
        both = {u: (s, d) for u, s, d in check(os.path.join(tmp, 'suites'), model_of=lambda unit: 'm1', versions=V, skills=(skills, proj))}
        one = {u for u, _, _ in check(os.path.join(tmp, 'suites'), model_of=lambda unit: 'm1', versions=V, skills=skills)}
        pr_ok = both.get('skill-p', ('',))[0] == 'untested' and '/project/.claude/skills' in both['skill-p'][1] and 'skill-p' not in one
        print(('PASS' if pr_ok else 'FAIL') + f' a project skill is untested: {both.get("skill-p", ("missing",))[0]}; '
              f'your folder alone misses it: {"skill-p" not in one}')
        sk_ok &= frontmatter_model(skill) == 'inherit' and sh_ok and un_ok and pr_ok
        ok &= sk_ok

        # A gap is not a verdict; an accepted unit holds only at the sha it was accepted at.
        gs = os.path.join(tmp, 'gap-suites')
        gsk = os.path.join(tmp, 'gap-skills')

        def gunit(name, receipt=None, **extra):
            os.makedirs(os.path.join(gs, name))
            f = os.path.join(gsk, name)
            os.makedirs(f)
            open(os.path.join(f, 'SKILL.md'), 'w').write(f'---\nname: {name}\n---\nbody {name}\n')
            json.dump({'unit': name, 'file': f, 'run': 'x', **extra}, open(os.path.join(gs, name, 'unit.json'), 'w'))
            if receipt is not None:
                with open(os.path.join(gs, name, 'receipts.jsonl'), 'w') as fh:
                    fh.write(json.dumps({'unit_sha': file_sha(f), 'model': 'm1', 'claude': 'v1', 'date': 'd', **receipt}) + '\n')
            return f
        gunit('gap', {'pass': False, 'gaps': ['every arm ran every case'], 'failed': []})
        gunit('real-fail', {'pass': False, 'gaps': [], 'failed': ['draft passes 75% of runs']})
        gunit('clean-pass', {'pass': True, 'gaps': [], 'failed': []})
        acc = gunit('accepted')
        json.dump({'unit': 'accepted', 'file': acc, 'accepted': {'sha': file_sha(acc), 'date': 'd', 'by': 'record'}},
                  open(os.path.join(gs, 'accepted', 'unit.json'), 'w'))
        acs = gunit('accepted-suite', {'pass': False, 'gaps': [], 'failed': ['draft passes 75% of runs']}, suite=['x'])
        unit_acs = json.load(open(os.path.join(gs, 'accepted-suite', 'unit.json')))
        json.dump(dict(unit_acs, accepted={'sha': file_sha(acs), 'date': 'd', 'by': 'record'}),
                  open(os.path.join(gs, 'accepted-suite', 'unit.json'), 'w'))
        gr = lambda: {u: (s, d) for u, s, d in check(gs, model_of=lambda unit: 'm1', versions=V, skills=gsk)}  # noqa: E731
        got_r = gr()
        got_g = {u: s for u, (s, _) in got_r.items()}
        open(os.path.join(acc, 'SKILL.md'), 'a').write('upstream change\n')
        open(os.path.join(acs, 'SKILL.md'), 'a').write('an edit\n')
        after = gr()
        got_acc2, got_acs2 = after.get('accepted', ('',))[0], after.get('accepted-suite', ('',))[0]
        want_g = {'gap': 'stale', 'real-fail': 'failed', 'clean-pass': 'current', 'accepted': 'accepted',
                  'accepted-suite': 'accepted'}
        g_ok = (got_g == want_g and got_acc2 == 'untested' and got_acs2 == 'stale'
                and 'without a suite' in got_r['accepted'][1] and 'as its suite measured it' in got_r['accepted-suite'][1])
        print(('PASS' if g_ok else 'FAIL') + f' gaps and acceptance: got {got_g}; after a change, accepted '
              f'{got_acc2} and accepted with a failed suite {got_acs2}')
        ok &= g_ok

        # A running-total receipt's cost_usd is the unit's spend so far, and a receipt written again
        # without a run repeats it: the last run costs the newest total less the last lower one, not
        # the total (25.23) and not the newest less the one before (0.00). A per-run receipt's cost_usd
        # is its run's own (7.99, not 7.99 less 8.15).
        ps = os.path.join(tmp, 'price-suites')
        pk = os.path.join(tmp, 'price-skills')
        hx = 'python run_suite.py x'

        def punit(name, costs, total=True, current=True):
            os.makedirs(os.path.join(ps, name))
            f = os.path.join(pk, name)
            os.makedirs(f)
            open(os.path.join(f, 'SKILL.md'), 'w').write(f'---\nname: {name}\n---\nbody {name}\n')
            json.dump(dict({'unit': name, 'file': f, 'run': hx}, **({'cost': 'running_total'} if total else {})),
                      open(os.path.join(ps, name, 'unit.json'), 'w'))
            with open(os.path.join(ps, name, 'receipts.jsonl'), 'w') as fh:
                for c in costs:
                    fh.write(json.dumps({'unit_sha': file_sha(f) if current else 'old', 'model': 'm1', 'claude': 'v1', 'pass': True,
                                         'date': 'd', 'gaps': [], 'failed': [], 'cost_usd': c}) + '\n')
        punit('rewritten', [19.38, 22.31, 25.23, 25.23])
        punit('stale-priced', [1.0, 3.5], current=False)
        punit('one-receipt', [7.0])
        punit('never-rose', [5.0, 5.0])
        punit('per-run', [2.88, 8.15, 7.99], total=False)
        pr = {u: (s, d) for u, s, d in check(ps, model_of=lambda unit: 'm1', versions=V, skills=pk)}
        p_ok = ('last run cost $2.92' in pr['rewritten'][1] and pr['rewritten'][0] == 'current'
                and pr['stale-priced'][1].endswith(f'; last run cost $2.50; run: {hx}')
                and 'last run cost' not in pr['one-receipt'][1] and 'last run cost' not in pr['never-rose'][1]
                and pr['per-run'][1].endswith('; last run cost $7.99'))
        print(('PASS' if p_ok else 'FAIL') + ' last run cost, with cost_usd a running total or one run\'s: '
              + '; '.join(f'{u} {d!r}' for u, (_, d) in sorted(pr.items())))
        ok &= p_ok

        # The Claude Code version: a receipt holds only on the version a re-run launches. Known-bad: after
        # an update, receipts made on the older version still read CURRENT; and a receipt made from mixed
        # versions (one arm on the new one, the rest on the old) named that one arm's version.
        import shlex
        vs, vk = os.path.join(tmp, 'ver-suites'), os.path.join(tmp, 'ver-skills')
        vfull = 'python run_suite.py {u} --arms draft,plain,bad,ablate'
        vdraft = 'python run_suite.py {u} --arms draft'
        vone = 'python run_agent_suite.py {u}'

        def vunit(name, receipt, run=vfull, draft=vdraft, root=vs, model='m1'):
            os.makedirs(os.path.join(root, name))
            f = os.path.join(vk, name)
            os.makedirs(f)
            open(os.path.join(f, 'SKILL.md'), 'w').write(f'---\nname: {name}\nmodel: {model}\n---\nbody {name}\n')
            json.dump(dict({'unit': name, 'file': f, 'run': run.format(u=name)},
                           **({'draft_run': draft.format(u=name)} if draft else {})),
                      open(os.path.join(root, name, 'unit.json'), 'w'))
            with open(os.path.join(root, name, 'receipts.jsonl'), 'w') as fh:
                fh.write(json.dumps({'unit_sha': file_sha(f), 'model': model, 'date': 'd', 'pass': True, 'gaps': [],
                                     'failed': [], **receipt}) + '\n')
        new, old = '3.0.2', '3.0.1'
        every = lambda v: {a: [v] for a in ('ablate', 'bad', 'draft', 'plain')}  # noqa: E731
        four = {'passed': 4, 'ran': 4}
        vunit('v-same', {'claude': new, 'claude_by_arm': every(new), 'draft': four})
        vunit('v-old', {'claude': old, 'claude_by_arm': every(old), 'draft': four})
        vunit('v-legacy-old', {'claude': old})
        vunit('v-legacy-same', {'claude': new})
        vunit('v-mixed', {'claude': None, 'claude_by_arm': {**every(old), 'ablate': [new]}, 'draft': four})
        vunit('v-draft-ok', {'claude': None, 'claude_by_arm': {**every(old), 'draft': [new]}, 'draft': four})
        vunit('v-draft-fail', {'claude': None, 'claude_by_arm': {**every(old), 'draft': [new]},
                               'draft': {'passed': 3, 'ran': 4}, 'pass': False, 'failed': ['draft passes 75% of runs']})
        vunit('v-draft-ok-failed', {'claude': None, 'claude_by_arm': {**every(old), 'draft': [new]}, 'draft': four,
                                    'pass': False, 'failed': ['a weaker body fails at least one case']})
        vunit('v-none', {})
        vunit('v-agent-old', {'claude': '3.0.0'}, run=vone, draft=None)
        vunit('v-agent-same', {'claude': new}, run=vone, draft=None)

        def vr(launch):
            return {u: (s, d) for u, s, d in check(vs, model_of=lambda unit: 'm1', skills=vk, versions=lambda: launch)}
        got_v = vr(new)
        want_v = {'v-same': 'current', 'v-old': 'stale', 'v-legacy-old': 'stale', 'v-legacy-same': 'current',
                  'v-mixed': 'stale', 'v-draft-ok': 'current', 'v-draft-fail': 'stale', 'v-draft-ok-failed': 'failed',
                  'v-none': 'stale', 'v-agent-old': 'stale', 'v-agent-same': 'current'}
        got_vs = {u: s for u, (s, _) in got_v.items()}
        runs_named = {
            'a version move re-checks the draft arm': got_v['v-old'][1].endswith('run: ' + vdraft.format(u='v-old')),
            'so does a mixed receipt': got_v['v-mixed'][1].endswith('run: ' + vdraft.format(u='v-mixed')),
            'a draft fail on the new version runs the whole suite': (
                got_v['v-draft-fail'][1].endswith('run: ' + vfull.format(u='v-draft-fail'))
                and f'draft run failed on Claude Code {new}' in got_v['v-draft-fail'][1]),
            'a unit with no draft_run runs whole': got_v['v-agent-old'][1].endswith('run: ' + vone.format(u='v-agent-old')),
            'a draft re-check says what it holds on': f'draft re-checked on Claude Code {new} (4/4), the other arms ran on {old}' in got_v['v-draft-ok'][1],
            'no version recorded is named': 'records no Claude Code version' in got_v['v-none'][1],
        }
        v_ok = got_vs == want_v and all(runs_named.values())
        right = sum(got_vs.get(u) == s for u, s in want_v.items())
        wrong_runs = [k for k, v in runs_named.items() if not v]
        print(('PASS' if v_ok else 'FAIL') + f' the Claude Code version, launching {new}: {right} of {len(want_v)} states '
              f'right, {len(runs_named) - len(wrong_runs)} of {len(runs_named)} re-runs named right'
              + (f'; got {got_vs}; wrong: {wrong_runs}' if not v_ok else ''))
        got_u = vr(None)
        n_unknown = sum(s == 'unknown' for s, _ in got_u.values())
        u_ok = n_unknown == len(got_u) == len(want_v)
        print(('PASS' if u_ok else 'FAIL') + f' a version that can\'t be read is UNKNOWN, never CURRENT: {n_unknown} of '
              f'{len(got_u)} receipted units unknown')
        got_o = vr(old)
        o_ok = (got_o['v-old'][0] == 'current' and got_o['v-legacy-old'][0] == 'current' and got_o['v-same'][0] == 'stale'
                and got_o['v-agent-old'][0] == 'stale')
        print(('PASS' if o_ok else 'FAIL') + f' launching {old} instead: the {old} receipt holds ({got_o["v-old"][0]}), the '
              f'{new} one does not ({got_o["v-same"][0]})')
        # The version a re-run launches is the first thing the command prints; one that fails, can't be found,
        # can't be parsed or prints something else first is unread (None), never a guess.
        py = lambda code: shlex.join([sys.executable, '-c', code])  # noqa: E731
        lv = {'prints it': launch_version(py(f'print("{new} (Claude Code)")')),
              'exits 1': launch_version(py(f'import sys; print("{new}"); sys.exit(1)')),
              'not found': launch_version('no-such-claude-here --version'),
              'a banner first': launch_version(py(f'print("hello {new}")')),
              'unparseable': launch_version('claude "--version')}
        l_ok = lv == {'prints it': new, 'exits 1': None, 'not found': None, 'a banner first': None, 'unparseable': None}
        print(('PASS' if l_ok else 'FAIL') + f' reading the version a re-run launches: {lv}')
        vlogs = os.path.join(tmp, 'vlogs')
        os.makedirs(vlogs)
        for i, v in enumerate([old, old, '2.9.0']):
            open(os.path.join(vlogs, f'{i}.jsonl'), 'w').write(f'{{"version":"2.8.0"}}\n{{"version":"{v}"}}\n')
        live = live_versions(vlogs)
        note = version_note(new, live) or ''
        n_ok = (live == collections.Counter({old: 2, '2.9.0': 1})
                and note.startswith(f'note: a suite re-run launches Claude Code {new}; the 3 newest session logs ran '
                                    f'{old} (2), 2.9.0 (1)')
                and version_note(new, collections.Counter({new: 3})) is None and version_note(None, live) is None)
        print(('PASS' if n_ok else 'FAIL') + f' live sessions on another version get a note: {note[:100]!r}')
        ok &= v_ok and u_ok and o_ok and l_ok and n_ok

        # The model a unit runs on: its own newest launch first; else the family's most common id
        # across main logs, so one session on another model doesn't read as a rollout; a full id is the answer.
        logs = os.path.join(tmp, 'logs')
        sub = os.path.join(logs, 'sess1', 'subagents')
        os.makedirs(sub)

        def log(path, models):
            with open(path, 'w') as f:
                f.write('{"first line may be cut"}\n')
                for m in models:
                    f.write(json.dumps({'type': 'assistant', 'message': {'model': m}}) + '\n')
        log(os.path.join(logs, 'a.jsonl'), ['claude-opus-9', 'claude-opus-9'])
        log(os.path.join(logs, 'b.jsonl'), ['claude-opus-9', '<synthetic>'])
        log(os.path.join(logs, 'c.jsonl'), ['claude-haiku-1', 'claude-haiku-1', 'claude-haiku-1'])
        json.dump({'agentType': 'reader'}, open(os.path.join(sub, 'agent-x.meta.json'), 'w'))
        log(os.path.join(sub, 'agent-x.jsonl'), ['claude-opus-10'])
        cases = [(('reader', 'opus'), 'claude-opus-10'), (('nobody', 'opus'), 'claude-opus-9'),
                 (('nobody', 'claude-opus-7'), 'claude-opus-7'), (('nobody', 'haiku'), 'claude-haiku-1')]
        lm_ok = True
        for (u, alias), want_m in cases:
            got_m = live_model(u, alias, logs=logs)
            lm_ok &= got_m == want_m
            print(('PASS' if got_m == want_m else 'FAIL') + f' live model {u}/{alias}: got {got_m}, want {want_m}')

        # No suites folder set anywhere: exit 2 naming the key, never a clean 0.
        import subprocess
        import kit_config
        env = dict(os.environ, **kit_config.home_env(os.path.join(tmp, 'home')),
                   PYTHONPATH=HERE + os.pathsep + os.environ.get('PYTHONPATH', ''))
        env.pop('PRODUCT_OS_CONFIG', None)
        bare = os.path.join(tmp, 'bare')
        os.makedirs(bare)
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], cwd=bare, env=env, capture_output=True, text=True)
        nc_ok = r.returncode == 2 and 'agent_gate.suites' in r.stderr
        print(('PASS' if nc_ok else 'FAIL') + f' no suites folder configured: exit {r.returncode}, names the key: '
              f'{"agent_gate.suites" in r.stderr}')
        # End to end: the config key agent_gate.version_cmd names what to run, and a receipt made on another
        # version reads STALE, with the note line for sessions on yet another, exit 1.
        home2, e2e = os.path.join(tmp, 'home2'), os.path.join(tmp, 'e2e-suites')
        os.makedirs(os.path.join(home2, '.claude'))
        vunit('v-e2e', {'claude': old}, root=e2e, model='claude-opus-9')
        json.dump({'agent_gate': {'suites': e2e, 'version_cmd': py(f'print("{new} (Claude Code)")')}},
                  open(os.path.join(home2, '.claude', 'product-os.json'), 'w'))
        env2 = dict(env, **kit_config.home_env(home2))
        env2.pop('CLAUDE_PROJECT_DIR', None)
        r2 = subprocess.run([sys.executable, os.path.abspath(__file__), '--project', vlogs], cwd=bare, env=env2,
                            capture_output=True, text=True)
        e_ok = (r2.returncode == 1 and f'ran on Claude Code {old}, and a re-run now launches {new}' in r2.stdout
                and f'note: a suite re-run launches Claude Code {new}' in r2.stdout)
        print(('PASS' if e_ok else 'FAIL') + f' agent_gate.version_cmd from your config, end to end: exit {r2.returncode}, '
              f'the receipt on {old} read STALE: {"STALE    v-e2e" in r2.stdout}' + ('' if e_ok else f'; {r2.stdout}{r2.stderr}'))
        return 0 if ok and lm_ok and nc_ok and e_ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--suites', help='the suites folder (default: the config key agent_gate.suites)')
    ap.add_argument('--project', help="the project's session-log folder under ~/.claude/projects (default: the current project's)")
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    import kit_config

    def go():
        suites, logs = suites_folder(a.suites), default_logs(a.project)
        launch = launch_version()
        return report(check(suites, logs=logs, versions=lambda: launch), version_note(launch, live_versions(logs)))
    return kit_config.run(go)


if __name__ == '__main__':
    sys.exit(main())
