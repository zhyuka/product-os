#!/usr/bin/env python3
"""triage_lists.py - the opening lines of a triage reply: each list a card draws on, and whether it ran.

    python3 triage_lists.py [--from FILE] [--project DIR]   one line per list, to paste first, word for word
    python3 triage_lists.py --selftest                      planted lists in a temporary folder

The project is --project, else $CLAUDE_PROJECT_DIR, else the working folder, never the working folder
inside the plugin's own folder: there it refuses in one line, exit 2 (kit_config.project_dir()).

The lists are triage's: the tracker (`ado_rest.py decisions` when `ado.project` is set, or
`ado_rest.py decisions --from FILE` for a tracker file someone handed over; with neither, its line
says it isn't set up and names `--from`, so the card never leaves it out unsaid), the ledger file
`.claude/open-questions.md` in this folder, the request ledger (`ledger.py --questions`), and each
`triage.sources` command once it is accepted. A list ran when its tool exits 0 (the ledger file: when
it reads), and its line gives the count. Otherwise it did not run, and its line quotes what the tool
printed: its REFUSED line, else its error line, else its last line. A closing line says to paste
these lines first.

WHY. The reply that holds a triage card opens with each list that did not run. Written by hand, that
opening was dropped; printed by a tool, it is pasted. Since a session may run it before its recall
searches, its own last line says where the lines go.

Exit 0 when every list ran, 1 when one did not, 2 when a tool could not be started.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import os
import re
import subprocess
import sys
import tempfile

try:
    import kit_config                       # beside this file: the project comes from its project_dir()
except ImportError:
    kit_config = None

HERE = os.path.dirname(os.path.realpath(__file__))
LEDGER_FILE = os.path.join('.claude', 'open-questions.md')
# The closing line. A session that ran this before its recall searches pasted the lines first in 7 of 12
# runs on the triage eval with it, 3 of 18 without.
PASTE = ('Paste these lines first, word for word, at the top of the message that holds the card, before '
         'any summary or search status.')


def quoted(out):
    lines = [ln.strip() for ln in (out or '').splitlines() if ln.strip()]
    for pick in (lambda ln: ln.startswith('REFUSED'),
                 lambda ln: ln.lower().startswith(('error', 'fatal', 'not accepted')) or 'Error:' in ln):
        hit = next((ln for ln in lines if pick(ln)), None)
        if hit:
            return hit
    return lines[-1] if lines else '(it printed nothing)'


def run_list(label, argv, shown, cwd, timeout=180):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as e:
        return (label, False, f'{label}: did not run. `{shown}` could not be started ({type(e).__name__}).'), 2
    if p.returncode == 0:
        first = next((ln.strip() for ln in (p.stdout or '').splitlines() if ln.strip()), '(no output)')
        return (label, True, f'{label}: ran. `{shown}` printed: {first}'), 0
    return (label, False, f'{label}: did not run. `{shown}` exited {p.returncode}: '
                          f'{quoted((p.stdout or "") + chr(10) + (p.stderr or ""))}'), 1


def ledger_file(cwd):
    path = os.path.join(cwd, LEDGER_FILE)
    try:
        text = open(path, encoding='utf-8').read()
    except OSError as e:
        return ('Ledger file', False, f'Ledger file: did not run. {LEDGER_FILE} could not be read '
                                      f'({type(e).__name__}).'), 1
    n = len(re.findall(r'(?im)^\s*-?\s*Status:\s*open\b', text))
    return ('Ledger file', True, f'Ledger file: ran. {LEDGER_FILE} holds {n} open question(s).'), 0


def config(tools, cwd):
    """(ado.project, triage.sources, why sources are withheld or None), read through kit_config for
    the project at or above cwd."""
    sys.path.insert(0, tools)
    try:
        import kit_config
        c = kit_config.load(cwd)
        withheld = next((why for k, why in c.get('withheld', []) if k == 'triage.sources'), None)
        return (kit_config.get('ado', 'project', start=cwd), kit_config.get('triage', 'sources', start=cwd),
                withheld)
    except Exception:                       # no kit_config beside it: the tracker and sources aren't set up
        return None, None, None
    finally:
        sys.path.remove(tools)


def project(explicit=None):
    """The project folder: kit_config.project_dir(), which never takes the working folder inside the
    plugin's own folder. With no kit_config beside this file: --project, $CLAUDE_PROJECT_DIR, the
    working folder."""
    if kit_config is None:
        return os.path.abspath(explicit or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    return kit_config.project_dir(explicit)


def read(tools=HERE, cwd=None, from_file=None, cfg=None):
    cwd = cwd or project()
    project, sources, withheld = cfg if cfg is not None else config(tools, cwd)
    py = sys.executable
    rows, code = [], 0

    def add(row_code):
        nonlocal code
        row, c = row_code
        rows.append(row)
        code = max(code, c)

    if from_file:
        add(run_list('Tracker', [py, os.path.join(tools, 'ado_rest.py'), 'decisions', '--from', from_file],
                     f'ado_rest.py decisions --from {from_file}', cwd))
    elif project:
        add(run_list('Tracker', [py, os.path.join(tools, 'ado_rest.py'), 'decisions'], 'ado_rest.py decisions', cwd))
    else:                                   # said, never left out: a handed-over file run without --from showed nothing
        add((('Tracker', None, 'Tracker: not set up here (no `ado.project`), and no `--from` file was given. '
                               'For a tracker file someone handed you, run this again with `--from <file>`.'), 0))
    add(ledger_file(cwd))
    add(run_list('Request ledger', [py, os.path.join(tools, 'ledger.py'), '--questions'], 'ledger.py --questions', cwd))
    if withheld:
        add((('Project sources', False, 'Project sources: did not run. triage.sources is NOT ACCEPTED on this '
                                        'machine; the person reads it and runs `product-os kit_config accept '
                                        'triage.sources`.'), 1))
    elif sources:
        for s in sources:
            name, cmd = s.get('name', 'source'), s.get('cmd', '')
            add(run_list(f'Source "{name}"', ['/bin/sh', '-c', cmd], cmd, cwd))
    return rows, code


def output(rows):
    """What the command prints: one line per list, then the closing line."""
    return [line for _, _, line in rows] + [PASTE]


def selftest():
    ok = True

    def check(name, cond, got=''):
        nonlocal ok
        ok &= bool(cond)
        print(('PASS' if cond else 'FAIL') + f' {name}' + ('' if cond else f'  ({got})'))

    with tempfile.TemporaryDirectory() as d:
        tools, proj = os.path.join(d, 'tools'), os.path.join(d, 'proj')
        os.makedirs(tools)
        os.makedirs(os.path.join(proj, '.claude'))
        open(os.path.join(tools, 'ado_rest.py'), 'w').write(
            'import sys\nsys.exit("REFUSED: tracker-cache.json was pulled 180 minutes ago (limit 30m).\\n'
            '  The tracker list did not run.")\n')
        open(os.path.join(tools, 'ledger.py'), 'w').write('print("0 open questions (0 from this machine)")\n')
        open(os.path.join(proj, LEDGER_FILE), 'w').write('## Q-1: a\n- Status: open\n## Q-2: b\n- Status: resolved\n')
        rows, code = read(tools, proj, 'tracker-cache.json', cfg=(None, None, None))
        check('a handed-over file that refuses is the first line, quoting REFUSED',
              code == 1 and rows[0][2].startswith('Tracker: did not run.') and 'REFUSED: tracker-cache.json' in rows[0][2]
              and 'did not run.")' not in rows[0][2], rows)
        check('the ledger file counts its open entries', rows[1] == ('Ledger file', True,
              'Ledger file: ran. .claude/open-questions.md holds 1 open question(s).'), rows)
        out = output(rows)
        check('the output is the list lines, then the closing line to paste them first',
              out[:-1] == [r[2] for r in rows] and out[-1] == PASTE and len(out) == len(rows) + 1, out)
        rows, code = read(tools, proj, None, cfg=(None, None, 'its command changed'))
        check('sources NOT ACCEPTED is did not run, after a tracker line that names --from',
              [r[0] for r in rows] == ['Tracker', 'Ledger file', 'Request ledger', 'Project sources']
              and code == 1 and rows[3][1] is False, rows)
        rows, code = read(tools, proj, None, cfg=(None, None, None))
        check('no tracker set up and the rest ran: exit 0, and the tracker line says so and names --from',
              code == 0 and rows[0][0] == 'Tracker' and rows[0][1] is None and '`--from <file>`' in rows[0][2], rows)
        # A session that changed into the plugin's own folder to run this, as runs on the triage eval did.
        if kit_config is None:
            check('the plugin-folder cases ran', False, 'DID NOT RUN: kit_config.py is not beside this file')
        else:
            import contextlib
            import io
            plug = os.path.join(d, 'plugin')
            os.makedirs(os.path.join(plug, '.claude-plugin'))
            os.makedirs(os.path.join(plug, 'tools'))
            open(os.path.join(plug, '.claude-plugin', 'plugin.json'), 'w').write('{"name": "product-os"}')
            saved = (kit_config.PLUGIN, os.getcwd(), os.environ.pop('CLAUDE_PROJECT_DIR', None))
            kit_config.PLUGIN = plug
            runs = []
            try:
                os.chdir(os.path.join(plug, 'tools'))
                for argv in ([], ['--project', proj], ['--project', plug]):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        c = main(argv, tools, cfg=(None, None, None))
                    runs.append((c, buf.getvalue().splitlines()))
            finally:
                kit_config.PLUGIN = saved[0]
                os.chdir(saved[1])
                if saved[2] is not None:
                    os.environ['CLAUDE_PROJECT_DIR'] = saved[2]
            check('started inside the plugin, no project named: one REFUSED line, exit 2, and no list read',
                  runs[0][0] == 2 and len(runs[0][1]) == 1 and runs[0][1][0].startswith('REFUSED:'), runs[0])
            check("started inside the plugin with --project: the project's ledger file is read",
                  runs[1][0] == 0
                  and 'Ledger file: ran. .claude/open-questions.md holds 1 open question(s).' in runs[1][1], runs[1])
            check("--project naming the plugin's own folder: one REFUSED line, exit 2, naming a --project to use",
                  runs[2][0] == 2 and len(runs[2][1]) == 1 and runs[2][1][0].startswith('REFUSED: --project ')
                  and 'Run it again with --project ' in runs[2][1][0], runs[2])
        os.remove(os.path.join(proj, LEDGER_FILE))
        rows, code = read(tools, proj, None, cfg=(None, None, None))
        check('a missing ledger file did not run', code == 1 and rows[1][0] == 'Ledger file' and rows[1][1] is False,
              rows)
    print('ALL PASS' if ok else 'FAILED')
    return 0 if ok else 1


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def main(argv, tools=HERE, cfg=None):
    if '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0
    if '--selftest' in argv:
        return __import__("kit_config").run_isolated(selftest)
    try:
        cwd = project(arg(argv, '--project'))
    except (kit_config.InPluginFolder if kit_config else ()) as e:
        print(e)
        return 2
    rows, code = read(tools, cwd, arg(argv, '--from'), cfg)
    print('\n'.join(output(rows)))
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
