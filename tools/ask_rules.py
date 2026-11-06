#!/usr/bin/env python3
"""ask_rules.py - do the settings ask rules prompt on every outward write, and on no read?

Reads the `permissions.ask` list of each settings file and tests it against two lists of commands:
WRITES, this plugin's commands that post, edit or delete something outside your machine (figma_post,
figma_attach, ado_write, ado.py new), which must each match an ask rule; and READS, which only read
or test and must match none. A read that prompts is the defect: a rule as broad as
`Bash(*figma_post*)` fires on --help, selftest and grep too, and once prompts fire on reads they get
clicked through, writes included.

    python tools/ask_rules.py [settings.json ...]   exit 1 on a write with no rule or a read with one
    python tools/ask_rules.py --selftest            planted rule lists, each break caught

WHICH FILES. The paths given, else the config key ask_rules.settings (kit_config.py): a list of
settings files, such as a project's .claude/settings.json or your user settings; ~ is expanded, and a
relative path is read from the folder you run in. With neither, it stops with exit 2 and names the
key. A file named and missing fails. Each of these must prompt every write and no read.
ask_rules.copies (optional) lists settings files that may still hold copies of the rules, such as a
project's settings after you moved the rules into your user settings: a copy may lack a write rule,
but it must not prompt a read. A copy that is missing is skipped.

YOUR USER SETTINGS (~/.claude/settings.json) can hold tokens as well as rules, and a settings.local.json
gathers the commands you approve, any of which may carry one. When such a file is named, only its
permissions.ask list is kept (the rest is dropped as soon as it is parsed), and only counts and this
file's own commands are printed: never a rule's text, a value from the file, or a parse error's text,
which can quote the line near the error. A project file is reported with the rule that fired.

OVERRIDE REASONS. Every flag that lifts one of the writing tools' refusals (ado.py new --force,
--figma-ok, --skip-figma; figma_post's --separate, --pin-ok, --own-last-ok, --multi-ok, --repost-ok,
--new-cause, --new-thread; figma_attach attach --again; ado_write comment --stack, field and batch
--replaces) takes a reason in plain words, PLAIN_WORDS or
more with letters, on the command that runs the write, where the ask rule's prompt shows it. plain()
and override() below are the one copy of that rule the tools import. A batch item that carries an
override is refused, because a batch file's prompt shows only the file's name, so nobody reads its
reason.

A rule is `Bash(<pattern>)`, `*` matching any run of characters, checked against each top-level command
as Claude Code splits a compound one (commands()): at `&&`, `||`, `;`, `|`, `|&`, `&`, parentheses and
newlines outside quotes, `$(...)` and backticks, with heredoc bodies, redirections and comments left out,
and no quote removed. The whole line is never tested: in `ado_write.py st''ate 101 x; echo ' state '`
the only " state " sits in the echo, so Claude Code doesn't prompt on it, and this check mustn't count it
as prompting. A heredoc body is text, not a command, until a later line runs the file it wrote. A quote
or `$(` that never closes matches nothing, since the shell won't run that line.

DISPATCH. Each run also reads each writing tool's own dispatch from its source in this folder, and
fails on a subcommand that no WRITES or READS command runs: a subcommand added to a tool and named in
neither list would otherwise go unchecked, whether it prompts or not. A tool whose dispatch no pattern
in DISPATCH reads any more (its code changed shape) prints DID NOT RUN and fails too, never a pass.

Blind to: a write whose command line names no tool (a script file that imports one, or the REST API
called directly with a token); rules in managed settings, which it doesn't read; a subcommand in a
dispatch shape DISPATCH's patterns don't know, beside ones they do.

Exit 0 when every write prompts, no read does and every dispatched subcommand is listed; 1 on a miss,
a missing file or a dispatch it could not read; 2 when no settings file is named or configured.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Every subcommand that writes, from each tool's own dispatch, in the shapes a command takes: a
# relative path, the plugin root, a login shell, a cd first, an import.
WRITES = [
    "python tools/figma_post.py new FILEKEY 1:2 hello --picture a.jpg",
    "python tools/figma_post.py reply FILEKEY 123 hello",
    "python tools/figma_post.py fixnote FILEKEY 123 hello",
    "python tools/figma_post.py delete FILEKEY 123",
    "python tools/figma_post.py batch posts.json",
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" attach FILEKEY 123 a.jpg',
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" edit FILEKEY 123 --text-file t.txt',
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" mention FILEKEY 123',
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" resolve FILEKEY 123 456',
    "zsh -lc 'python ~/tools/ado_write.py state 101 Resolved'",
    "python ado_write.py field 101 System.Title x",
    "python ado_write.py comment 101 hello",
    "python ado_write.py editcmt 101 9 hello",
    "python ado_write.py delcmt 101 9",
    "python ado_write.py parent 101 100",
    "python ado_write.py reparent 101 100",
    "python ado_write.py attach 101 a.png",
    "python ado_write.py delete 101:7",
    "python ado_write.py restore 101",
    "python ado_write.py batch b.json",
    "cd tools && python ado.py --rest new --type Task --title x",
    "python -c 'import figma_post; figma_post.new(1, 2, 3)'",
    "python -c 'from ado_write import state'",
]
# Reads and tests that mention the same tools and must not prompt.
READS = [
    "python tools/figma_post.py --help",
    "python tools/figma_post.py selftest",
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" selftest',
    "python ado_write.py --help",
    "python ado_write.py comments 101",
    "python ado_write.py --selftest",
    "grep -n figma_post drafts.md",
    "sed -n 1,40p tools/ado_write.py",
    "git -C tools diff figma_post.py",
    "python ado.py search hero",
    "python ado.py lint 101",
    "python ado.py selftest",
    "python tools/figma_post.py cause FILEKEY",   # writes its local causes file only
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" combine out.jpg a.jpg b.jpg',   # a local picture
    'python "${CLAUDE_PLUGIN_ROOT}/tools/figma_attach.py" probe FILEKEY 1:2',
]

# Each writing tool's subcommands, read from its own dispatch. Each must be one WRITES or READS runs, so a
# subcommand added to a tool and not here fails the run: until then nothing says whether it prompts. Group 1 is a
# word or a list of quoted words.
DISPATCH = {
    "ado_write.py": [r'\bcmd (?:==|in) \(?((?:"\w+",?\s*)+)'],
    "figma_post.py": [r'sys\.argv\[1:2\] == \["(\w+)"\]', r'^\s*\{?"(\w+)": lambda: '],
    "figma_attach.py": [r'\bargs\[0\] == "(\w+)"'],
    "ado.py": [r'\badd_parser\("(\w+)"'],
}


SEPARATORS = ("&&", "||", "|&", ";;", ";", "|", "&", "(", ")", "\n")
REDIRECTS = ("&>>", "&>", "<<<", "<<-", "<<", ">>", ">&", "<&", ">|", "<>", ">", "<")   # longest first


def _quoted(s, i):
    """The index just past the single-quoted, double-quoted or backtick run that opens at s[i]. A `$(...)` inside
    double quotes is read by _scan, heredocs and all. ValueError when it never closes."""
    q = s[i]
    if q == "'":
        j = s.find("'", i + 1)
        if j < 0:
            raise ValueError("an open single quote")
        return j + 1
    j = i + 1
    while j < len(s) and s[j] != q:
        if s[j] == "\\":
            j += 2
        elif q == '"' and s.startswith("$(", j):
            j = _scan(s, j + 2, nested=True)[1]
        else:
            j += 1
    if j >= len(s):
        raise ValueError(f"an open {q}")
    return j + 1


def _scan(s, i=0, nested=False):
    """(the commands of s from i, the index where the scan stopped). nested: s[i] follows a `$(`, `<(` or `>(`,
    and the scan stops past the `)` that closes it. ValueError on an open quote or `$(`."""
    n, out, words = len(s), [], []
    st = {"cur": None, "drop": False}   # the word being read; whether it is a redirection's target
    heredocs, depth = [], 0   # each `<<` delimiter on this line, in order; open `(` subshells inside a nested scan

    def word_end():
        cur = st["cur"]
        if cur is not None:
            if st["drop"]:
                st["drop"] = False
                if heredocs and heredocs[-1] is None:
                    heredocs[-1] = re.sub(r"[\"'\\]", "", cur)
            else:
                words.append(cur)
        st["cur"] = None

    def command_end():
        word_end()
        if words:
            out.append(" ".join(words))
        words.clear()

    def add(text):
        st["cur"] = (st["cur"] or "") + text

    while i < n:
        ch = s[i]
        if ch == "\\":
            if s.startswith("\\\n", i):   # a continued line
                word_end()
            else:
                add(s[i:i + 2])
            i += 2
        elif ch in "'\"`":
            j = _quoted(s, i)
            add(s[i:j])
            i = j
        elif ch in "$<>" and s.startswith("(", i + 1):   # $( ... ), <( ... ), >( ... ): one word, read whole
            j = _scan(s, i + 2, nested=True)[1]
            add(s[i:j])
            i = j
        elif ch in " \t\r":
            word_end()
            i += 1
        elif ch == "#" and st["cur"] is None:
            end = s.find("\n", i)
            i = n if end < 0 else end
        elif ch == "\n":
            command_end()
            i += 1
            for delim in [h for h in heredocs if h is not None]:   # each body, to its delimiter line, left out
                while i < n:
                    end = s.find("\n", i)
                    line = s[i:] if end < 0 else s[i:end]
                    i = n if end < 0 else end + 1
                    if line.lstrip("\t") == delim:
                        break
            heredocs.clear()
        elif ch == ")" and nested and depth == 0:
            command_end()
            return out, i + 1
        else:
            red = next((r for r in REDIRECTS if s.startswith(r, i)), None)
            sep = next((p for p in SEPARATORS if s.startswith(p, i)), None)
            if red and not (red.startswith("&") and st["cur"] is not None):
                if st["cur"] is not None and not st["cur"].isdigit():
                    word_end()
                st["cur"] = None   # an fd number written before it goes with it
                if red in ("<<", "<<-"):
                    heredocs.append(None)
                st["drop"] = True
                i += len(red)
                if red in (">&", "<&") and i < n and (s[i].isdigit() or s[i] == "-"):
                    while i < n and (s[i].isdigit() or s[i] == "-"):   # 2>&1, >&2, <&-: the target is here
                        i += 1
                    st["drop"] = False
            elif sep:
                command_end()
                if nested:
                    depth += {"(": 1, ")": -1}.get(sep, 0)
                i += len(sep)
            else:
                add(ch)
                i += 1
    if nested:
        raise ValueError("an open $(")
    command_end()
    return out, i


def commands(cmd):
    """Each top-level command of a Bash command line, as Claude Code splits a compound one: cut at SEPARATORS
    outside quotes, `$(...)` and backticks; heredoc bodies, redirections with their targets (2>&1, >out, <in,
    2>/dev/null) and comments left out; quotes kept as written; words joined by one space. [] when a quote or
    `$(` never closes, so no rule matches a line the shell won't run."""
    try:
        return _scan(cmd or "")[0]
    except ValueError:
        return []


def matches(rule, cmd):
    """Does rule `Bash(<pattern>)` match one of cmd's top-level commands (commands())? Never the whole line."""
    m = re.fullmatch(r"Bash\((.*)\)", rule, re.S)
    if not m:
        return False
    rx = ".*".join(re.escape(s) for s in m.group(1).split("*"))
    return any(re.fullmatch(rx, p, re.S) for p in commands(cmd))


PLAIN_WORDS = 3   # an override's reason: this many words with letters, or it is no reason


def plain(reason):
    """None when reason is plain words, PLAIN_WORDS or more with letters; else what is wrong."""
    if reason is None:
        return f"needs its reason after it. Say why in plain words, {PLAIN_WORDS} words or more"
    words = [w for w in str(reason).split() if re.search(r"[A-Za-z]{2}", w)]
    if len(words) >= PLAIN_WORDS:
        return None
    return f"{reason!r} gives no reason. Say why in plain words, {PLAIN_WORDS} words or more"


def override(flag, reason, in_batch=False):
    """None when an override flag may lift its refusal: its reason is plain words (plain()). Else the refusal line.
    A batch item is refused on that alone, since a batch file's permission prompt shows only the file's name.
    Blind to a command run from inside a script, whose prompt shows the script, not the reason."""
    if in_batch:
        return (f"REFUSED: {flag} can't come from a batch file, since the prompt shows only the file's name. Post that "
                f"item on its own command line with {flag} \"<why>\".")
    bad = plain(reason)
    return f"REFUSED: {flag} {bad}." if bad else None


# The user settings file can hold tokens: from it, only counts and this file's own commands are printed.
USER = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
PRIVATE = {os.path.abspath(USER)}
# A settings.local.json gathers the commands you approve, and one may carry a token: none of its text is printed
# either, wherever it sits.
LOCAL = "settings.local.json"


def private_file(path):
    """Is path a file whose text is never printed: your user settings, or any settings.local.json?"""
    return os.path.abspath(path) in PRIVATE or os.path.basename(path) == LOCAL


def problems(ask, private=False):
    """Each write no rule prompts and each read one does. private: name the command only, never the rule
    (its text came from a file that may hold tokens)."""
    out = [f"a write does not prompt: {c}" for c in WRITES if not any(matches(r, c) for r in ask)]
    out += [f"a read prompts{'' if private else ' (' + next(r for r in ask if matches(r, c)) + ')'}: {c}"
            for c in READS if any(matches(r, c) for r in ask)]
    return out


def ask_of(path):
    """The permissions.ask list of a settings file, its strings only. The rest of the file is dropped here."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    ask = ((doc.get("permissions") or {}).get("ask") if isinstance(doc, dict) else None) or []
    del doc
    return [r for r in ask if isinstance(r, str)] if isinstance(ask, list) else []


def _paths(paths):
    paths = [paths] if isinstance(paths, str) else list(paths or [])
    return [os.path.abspath(os.path.expanduser(p)) for p in paths]


def settings_files(paths=None):
    """The paths given, else ask_rules.settings; NotConfigured (exit 2 through kit_config.run) when
    neither names one."""
    if not paths:
        import kit_config
        paths = kit_config.need("ask_rules", "settings")
    return _paths(paths)


def copy_files():
    """ask_rules.copies: settings files that may still hold copies of the rules; none when unset."""
    import kit_config
    return _paths(kit_config.get("ask_rules", "copies"))


def report_one(path, required, out=print):
    """Problems found in one settings file, printed as counts and this file's own commands. required: it
    must prompt every write; otherwise (a copy) only a read that prompts counts, and a missing file is
    skipped."""
    private = private_file(path)
    if not os.path.isfile(path):
        out(f"MISSING {path}" + ("" if required else " (a copy: skipped)"))
        return 1 if required else 0
    try:
        ask = ask_of(path)
    except (OSError, ValueError) as e:
        out(f"UNREADABLE {path}: {type(e).__name__}")   # the class only: a parse error's text quotes the file
        return 1
    every = problems(ask, private)
    found = [f for f in every if required or f.startswith("a read")]
    writes = sum(f.startswith("a write") for f in every)
    out(f"{path}: {len(ask)} ask rule(s); {len(WRITES) - writes} of {len(WRITES)} writes prompt, "
        f"{sum(f.startswith('a read') for f in found)} of {len(READS)} reads prompt"
        + ("" if required else " (a copy: a missing write rule is not a fault here)"))
    for f in found:
        out(f"  FAIL {f}")
    return len(found)


def subcommands(name, root=HERE):
    """The subcommands tool `name` dispatches, read from its source; None when the file can't be read or no
    pattern finds one (its dispatch changed shape)."""
    try:
        with open(os.path.join(root, name), encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return None
    found = set()
    for rx in DISPATCH[name]:
        for m in re.finditer(rx, src, re.M):
            found |= set(re.findall(r'"(\w+)"', m.group(1))) or {m.group(1)}
    return found or None


def listed(cmds):
    """(tool file, subcommand) for each command in cmds that runs `<tool>.py [--flags] <subcommand>`, the
    tool's path quoted or not."""
    return {(m.group(1), m.group(2)) for c in cmds
            for m in re.finditer(r"(\w+\.py)[\"']?(?:\s+--?[\w-]+)*\s+([A-Za-z]\w*)", c)}


def unlisted(root=HERE, writes=None, reads=None, names=None):
    """(missing [(tool, subcommand)], unread [tool], dispatched count): each subcommand a writing tool
    dispatches that no WRITES or READS command runs, and each tool whose dispatch couldn't be read."""
    have = listed((WRITES if writes is None else writes) + (READS if reads is None else reads))
    missing, unread, n = [], [], 0
    for name in names or DISPATCH:
        subs = subcommands(name, root)
        if subs is None:
            unread.append(name)
            continue
        n += len(subs)
        missing += [(name, s) for s in sorted(subs) if (name, s) not in have]
    return missing, unread, n


def report(files, copies=()):
    bad = sum(report_one(p, True) for p in files) + sum(report_one(p, False) for p in copies)
    missing, unread, n = unlisted()
    print(f"dispatch: {n - len(missing)} of {n} subcommands of {len(DISPATCH) - len(unread)} writing tools are run "
          f"by a WRITES or READS command")
    for name, sub in missing:
        print(f"  FAIL {name} {sub}: in its dispatch, in neither WRITES nor READS, so nothing here says whether "
              f"it prompts")
    for name in unread:
        print(f"  DID NOT RUN {name}: no DISPATCH pattern finds a subcommand in it")
    return 1 if bad or missing or unread else 0


def selftest():
    good = ["Bash(*figma_post* new *)", "Bash(*figma_post* reply *)", "Bash(*figma_post* fixnote *)",
            "Bash(*figma_post* delete *)", "Bash(*figma_post* batch *)",
            "Bash(*figma_attach* attach *)", "Bash(*figma_attach* edit *)", "Bash(*figma_attach* mention *)",
            "Bash(*figma_attach* resolve *)", "Bash(*ado_write* state *)", "Bash(*ado_write* field *)", "Bash(*ado_write* comment *)",
            "Bash(*ado_write* editcmt *)", "Bash(*ado_write* delcmt *)", "Bash(*ado_write* parent *)",
            "Bash(*ado_write* reparent *)", "Bash(*ado_write* attach *)", "Bash(*ado_write* batch *)",
            "Bash(*ado_write* delete *)", "Bash(*ado_write* restore *)",
            "Bash(*ado.py*new*)",
            "Bash(*import figma_post*)", "Bash(*import figma_attach*)", "Bash(*import ado_write*)",
            "Bash(*from figma_post*)", "Bash(*from figma_attach*)", "Bash(*from ado_write*)"]
    broad = ["Bash(*figma_post*)", "Bash(*figma_attach*)", "Bash(*ado.py*new*)", "Bash(*ado_write*)"]
    cases = [
        ("the narrowed rules: every write prompts, no read does", good, 0),
        ("one broad rule per tool: reads prompt too", broad, None),
        ("a write subcommand dropped (ado_write state)", [r for r in good if "state" not in r], 1),
        ("a write subcommand dropped (ado_write delete)", [r for r in good if r != "Bash(*ado_write* delete *)"], 1),
        ("a write subcommand dropped (ado_write restore)", [r for r in good if r != "Bash(*ado_write* restore *)"], 1),
        ("the import rules dropped: python -c writes don't prompt", [r for r in good if "import" not in r and "from" not in r], 2),
        ("'comment' without its space after: 'comments' prompts", [r.replace("comment *", "comment*") for r in good], 1),
        ("no rules at all: every write fails", [], len(WRITES)),
    ]
    fails = 0
    for name, ask, want in cases:
        got = problems(ask)
        writes = sum(g.startswith("a write") for g in got)
        reads = sum(g.startswith("a read") for g in got)
        ok = (not got) if want == 0 else (reads > 0 and writes == 0) if want is None else len(got) == want
        print(f"  {'PASS' if ok else 'MISS'}  {name}: {writes} write(s) unprompted, {reads} read(s) prompted")
        fails += not ok
    # The files: a planted settings file read end to end, a missing one, and none configured.
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for name, rules in (("good.json", good), ("broad.json", broad)):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                json.dump({"permissions": {"ask": rules}}, f)
        env = dict(os.environ, HOME=os.path.join(tmp, "home"), PYTHONPATH=HERE)
        env.pop("PRODUCT_OS_CONFIG", None)
        runs = [("a planted file whose rules hold: exit 0", ["good.json"], 0, ""),
                ("a planted file with broad rules: exit 1", ["broad.json"], 1, ""),
                ("a named file that is missing: exit 1", ["none.json"], 1, ""),
                ("no file named or configured: exit 2, naming the key", [], 2, "ask_rules.settings")]
        for name, args, want, says in runs:
            r = subprocess.run([sys.executable, os.path.abspath(__file__), *args], cwd=tmp, env=env,
                               capture_output=True, text=True)
            ok = r.returncode == want and says in r.stderr
            print(f"  {'PASS' if ok else 'MISS'}  {name} (got {r.returncode})")
            fails += not ok
        cases += runs

    # A planted user file: what report_one() prints must hold no value from it, the token or a rule.
    secret, odd = "tok-PLANTED-0123456789", "Bash(*figma_post*selftest*)"
    with tempfile.TemporaryDirectory() as td:
        def planted(name, doc, private=True, required=True):
            p = os.path.join(td, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(doc if isinstance(doc, str) else json.dumps(doc))
            (PRIVATE.add if private else PRIVATE.discard)(os.path.abspath(p))
            lines = []
            return report_one(p, required, lines.append), "\n".join(lines)
        doc = {"env": {"FIGMA_TOKEN": secret}, "permissions": {"ask": good + [odd], "allow": [secret]}}
        n, text = planted("user.json", doc)
        more = [
            ("the user file: its read-prompting rule is counted, the token and the rule text are not printed",
             n == 1 and secret not in text and odd not in text and "1 of" in text),
            ("the same file as a project file names the rule (it holds no token by design)",
             odd in planted("copy.json", doc, private=False)[1]),
            ("the same file as a settings.local.json, never marked private: the rule text and token are not printed",
             (lambda t: odd not in t and secret not in t and "1 of" in t)(planted(LOCAL, doc, private=False)[1])),
            ("a user file that won't parse prints its error class, not the text near the error",
             planted("bad.json", '{"env": {"T": "' + secret + '" ')[1].count(secret) == 0),
            ("a user file whose ask is not a list counts as no rules",
             ask_of(os.path.join(td, "user.json")) and planted("odd.json", {"permissions": {"ask": {"a": secret}}})[0]
             == len(WRITES)),
            ("a copy with no write rules is not a fault; a read it prompts is",
             planted("copy-none.json", {"permissions": {"ask": []}}, private=False, required=False)[0] == 0
             and planted("copy-broad.json", {"permissions": {"ask": broad}}, private=False, required=False)[0] > 0),
            ("a copy that is missing is skipped",
             report_one(os.path.join(td, "absent.json"), False, lambda _: None) == 0),
        ]
        # The dispatch check: planted tool files hold one subcommand named nowhere, or a dispatch no pattern reads.
        src = os.path.join(td, "tools")
        os.makedirs(src)
        for name, text in (("ado_write.py", '    if cmd == "state":\n        pass\n    elif cmd == "purge":\n'),
                           ("figma_attach.py", '    if sub == "attach":\n')):
            with open(os.path.join(src, name), "w", encoding="utf-8") as f:
                f.write(text)
        more += [
            ("dispatch: every subcommand of the writing tools here is run by a WRITES or READS command",
             unlisted()[:2] == ([], [])),
            ("dispatch known-bad: WRITES without its reparent line misses ado_write reparent",
             ("ado_write.py", "reparent") in unlisted(writes=[w for w in WRITES if "ado_write.py reparent" not in w])[0]),
            ("dispatch: a planted subcommand named nowhere fails, a listed one doesn't",
             unlisted(src, names=["ado_write.py"])[0] == [("ado_write.py", "purge")]),
            ("dispatch: a tool whose dispatch no pattern reads is did-not-run, not a pass",
             unlisted(src, names=["figma_attach.py"])[1:] == (["figma_attach.py"], 0)),
        ]
    # Override reasons: plain words pass; no reason, one word, ids or a batch item do not.
    more += [
        ("an override reason in plain words passes", override("--pin-ok", "the whole band is the subject") is None),
        ("an override with no reason, one word, or three ids is refused",
         all(override("--pin-ok", r) for r in (None, "", "ok", "1111111111 2222222222 33333"))),
        ("an override from a batch item is refused, whatever its reason, naming the flag",
         "--pin-ok can't come from a batch file" in (override("--pin-ok", "the whole band is the subject", True) or "")),
    ]
    # The split: a rule meets each top-level command as Claude Code splits the line, never the whole line.
    st, decoy = "Bash(*ado_write* state *)", "python tools/ado_write.py st''ate 101 Resolved"
    more += [(f"split: {name}", matches(st, cmd) is want) for name, cmd, want in [
        ("st''ate, then echo ' state ' after ; matches nothing", f"{decoy}; echo ' state '", False),
        ("... after a newline", f"{decoy}\necho ' state '", False),
        ("... after &", f"{decoy} & echo ' state '", False),
        ("st\\ate, then echo ' state '", "python tools/ado_write.py st\\ate 101 Resolved; echo ' state '", False),
        ("a zsh -lc whose subcommand is quoted, then echo ' state '",
         "zsh -lc 'python tools/ado_write.py \"state\" 101 Resolved'; echo ' state '", False),
        ("a heredoc writes the write into a file that `.` runs",
         "cat > /tmp/w.sh <<'EOF'\npython tools/ado_write.py state 101 Resolved\nEOF\n. /tmp/w.sh", False),
        ("a quote that never closes matches nothing", "python tools/ado_write.py state 101 'Resolved", False),
        ("still matches: cd, the write, 2>&1 | tail",
         "cd ~/project && python tools/ado_write.py state 101 Resolved 2>&1 | tail -3", True),
        ("still matches: the zsh -lc form", "zsh -lc 'python ~/tools/ado_write.py state 101 Resolved'", True),
        ("still matches: a write after a commit whose $(heredoc) holds an apostrophe, a ; and parentheses",
         "git commit -m \"$(cat <<'EOF'\nit's done; (all)\nEOF\n)\" && python tools/ado_write.py state 101 Resolved",
         True),
    ]]
    more.append(("split: redirections and their targets leave the command; a quoted '>' stays",
                 commands("python x.py a 2>&1 >out.txt 2>/dev/null < in.txt 'b > c' >&2") == ["python x.py a 'b > c'"]))
    for name, ok in more:
        print(f"  {'PASS' if ok else 'MISS'}  {name}")
        fails += not ok
    total = len(cases) + len(more)
    print(f"{total - fails} of {total} planted cases behave as expected.")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="settings files (default: the config key ask_rules.settings)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    import kit_config
    return kit_config.run(lambda: report(settings_files(a.files), copy_files()))


if __name__ == "__main__":
    sys.exit(main())
