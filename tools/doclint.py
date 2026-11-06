#!/usr/bin/env python3
"""doclint.py - CLI, git pre-commit gate and commit-msg gate: refuse team-facing .md that names
people, cites meetings, or carries an email or an em dash. It also speaks the Claude Code PreToolUse
hook protocol, for setups where hooks run.

WHY A GATE AND NOT A RULE IN A MEMORY FILE. A writing rule that is read every session can still be
violated every session: a doc ships with a named addressee in its header, a colleague's address,
two references to a standup and four em dashes, while the rule sits in context. A correction that
keeps recurring becomes a tool or a gate.

WHAT IT BLOCKS, and why only these four. Every check is high-confidence and mechanical. Judgment
calls (is this date load-bearing? is this term coined?) are deliberately not here, because a linter
that false-positives gets switched off and then protects nothing.
    name      a person's name in prose. Attribute to the role instead.
    email     an address. Never needed in a doc the team reads.
    meeting   standup / transcript / "the call" / "9/17 sync". Reveals that a doc was built from
              meeting notes or transcripts.
    em-dash   a common tell of generated prose; use a period or a comma.
  And one more, in every .md, in scope or not, when ado.org and ado.project are set:
    ado-id    an ADO work item cited bare (#1234, "Story 1234") instead of as a link to its item.
              ADO links nothing by itself, so a bare id is plain text to the reader. ado_links.py
              holds the rule; `python tools/ado_links.py link <file>` fixes the file. It skips what
              ado_links leaves out (archives, records, stores, generated files) and the blockquotes
              of a file whose quotes post as plain text (ado_links.plain_quotes). With no ADO project
              set, or no ado_links.py, the check does not run, and each summary says so.

THE NAME LIST is yours, never built in. It is the union of:
  - every --names FILE given (one name per line, "#" starts a comment)
  - doclint.names in the product-os config (a list of names), and doclint.names_file (a path)
  - doclint.people_glob: a glob of files named <prefix><first>_<last>.md (e.g. memory cards
    "people_jane_doe.md"); tokens of 4+ characters become names. doclint.people_prefix sets the
    prefix (default "people_").
  - doclint.people_file: a markdown people directory whose entries start "- **First Last**"; each
    capitalised token of 4+ characters in the bold name becomes a name, so the list follows the
    directory instead of rotting in a config file.
With no list configured the name check runs on an empty list and every summary says so: a name not
on the list passes. Names shorter than 4 characters are never derived; list them explicitly.

FALSE POSITIVES ARE THE WHOLE DESIGN PROBLEM. Guards, in order:
  - fenced code, inline code spans, URLs and link targets are stripped before matching names and
    meeting references (not emails or dashes: an address inside backticks is still an address)
  - names match case-sensitively on word boundaries, so a slug `jane.doe--scheduler` and the word
    "Analytics" never trip "Jane" / "Ana"
  - a match adjacent to . - _ / is treated as part of an identifier and skipped

SCOPE. Only .md files. doclint.scope in config is a list of path fragments (e.g. "/repos/",
"/shareouts/"); a file is in scope when its path contains one. Unset, every .md is in scope.
Always exempt: CLAUDE.md, AGENTS.md, CHANGELOG.md, and anything under _archive/, node_modules/,
.git/, dist/, memory/, .claude/, or a plugin's skills/ folder (machine instructions, not prose), and
a skill's own files anywhere (skills/<name>/<file>.md). doclint.exempt_parts and
doclint.exempt_names add to those lists. Two keys narrow them: doclint.lint_names lists built-in
exempt names to lint anyway (e.g. ["AGENTS.md"]), and doclint.exempt_skill_files: false lints a
skill's files outside a plugin, for skills written for people to read. Findings in an out-of-scope
file are printed but never counted. A file whose whole job is naming people, such as a team list
(TEAM.md), belongs in doclint.exempt_names, or the name check would refuse every commit to it; a
name there matches the exact file name only, so myteam.md stays in scope.

PRE-COMMIT. A pre-commit hook passes cli() the lines each staged .md adds (added_lines()). A finding
blocks only on one of those lines; findings already in the file print as notes, so a two-line edit
to an old doc is not blocked by debt someone else wrote.

    python doclint.py --staged [--names FILE]     the pre-commit mode, from inside a checkout
    python doclint.py --commit-msg <message file> the commit-msg mode
    python doclint.py [--names FILE] <file.md> [...]
    python doclint.py --selftest

EXIT CODES (CLI and --staged):
  0  every named file was read, and none in scope has a finding
  1  a file in scope has a finding
  2  no finding in scope, but a named file could not be read, so it was not linted. A check that
     did not run is not a pass. The usual cause is one argument holding several newline-separated
     paths; zsh does not split an unquoted $var, so pass ${(f)var}.
--commit-msg: 0 clean, 1 a finding (it names each line), 2 the message could not be read.
With no arguments it reads a PreToolUse hook event on stdin and denies a Write/Edit that adds a
finding to an in-scope file.
"""
import glob
import json
import os
import re
import sys

if __name__ == "__main__" and any(_a in ("-h", "--help") for _a in sys.argv[1:]):
    print((__doc__ or "").strip())
    raise SystemExit(0)

if os.path.dirname(os.path.realpath(__file__)) not in sys.path: sys.path.append(os.path.dirname(os.path.realpath(__file__)))
try:
    import kit_config
except ImportError:          # the linter must still run where the config module is absent
    kit_config = None
try:
    import ado_links         # the ado-id check: what a bare work-item id is
except ImportError:          # it needs kit_config too; without it, ado-id does not run and says so
    ado_links = None


def _cfg(*keys, default=None):
    if kit_config is None:
        return default
    v = kit_config.get("doclint", *keys)
    return default if v in (None, "", [], {}) else v


# --- scope -------------------------------------------------------------------------------------
EXEMPT_PARTS = (
    "/_archive/", "/_retired/", "/node_modules/", "/.git/", "/dist/", "/memory/", "/.claude/",
)
EXEMPT_NAMES = ("claude.md", "agents.md", "changelog.md")
PLUGIN_SKILLS = re.compile(r"/plugins/[^/]+/skills/")
SKILL_FILES = re.compile(r"/skills/[^/]+/[^/]+\.md$")   # a skill's own files, outside a plugin too
# The marker a generator writes in a file's first lines, e.g. "GENERATED by `tools/x.py` -- do not
# hand-edit" or "<!-- GENERATED by ... -->".
GENERATED = re.compile(r"^\s*(?:<!--\s*)?GENERATED by ", re.M)


def in_scope(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if not p.endswith(".md"):
        return False
    scope = [s.lower() for s in (_cfg("scope", default=[]) or [])]
    if scope and not any(g in p for g in scope):
        return False
    parts = EXEMPT_PARTS + tuple(s.lower() for s in _cfg("exempt_parts", default=[]))
    lint = {s.lower() for s in _cfg("lint_names", default=[])}
    names = tuple(n for n in EXEMPT_NAMES if n not in lint) + tuple(s.lower() for s in _cfg("exempt_names", default=[]))
    if any(part in p for part in parts) or PLUGIN_SKILLS.search(p):
        return False
    if _cfg("exempt_skill_files", default=True) is not False and SKILL_FILES.search(p):
        return False
    return os.path.basename(p) not in names


# --- names -------------------------------------------------------------------------------------
STOPWORDS = {"is", "and", "the", "of"}
NAME_FILES = []        # --names FILE arguments
_NAME_CACHE = []


def _read_names(path):
    out = set()
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        for raw in f:
            s = raw.split("#", 1)[0].strip()
            if s:
                out.add(s)
    return out


def people_file_names(path):
    """Name tokens from each entry's bold name ("- **First Last**") in a markdown people directory.
    Capitalised, length >= 4 only. A missing file gives none."""
    out = set()
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        m = re.match(r"- \*\*([^*]+)\*\*", line)
        for tok in re.findall(r"[A-Za-z]+", m.group(1)) if m else []:
            if len(tok) >= 4 and tok.lower() not in STOPWORDS and tok[0].isupper():
                out.add(tok)
    return out


def derived_names():
    """First/last name tokens from files matching doclint.people_glob, and from the entries of
    doclint.people_file, so the list follows your notes instead of rotting in a config file.
    Length >= 4 only."""
    out = set()
    if _cfg("people_file"):
        out |= people_file_names(_cfg("people_file"))
    pattern = _cfg("people_glob")
    if not pattern:
        return out
    prefix = _cfg("people_prefix", default="people_")
    for p in glob.glob(os.path.expanduser(pattern)):
        base = os.path.basename(p)
        if not base.startswith(prefix) or not base.endswith(".md"):
            continue
        for tok in base[len(prefix):-len(".md")].split("_"):
            if len(tok) >= 4 and tok not in STOPWORDS:
                out.add(tok.capitalize())
    return out


def name_list():
    """The names the linter hunts, longest first. ONE definition: the clean-file summary quotes this
    list's size as the denominator, and the two must not disagree."""
    if not _NAME_CACHE:
        names = set(_cfg("names", default=[]) or [])
        files = list(NAME_FILES)
        if _cfg("names_file"):
            files.append(_cfg("names_file"))
        for f in files:
            names |= _read_names(f)
        names |= derived_names()
        _NAME_CACHE.extend(sorted(names, key=len, reverse=True))
    return _NAME_CACHE


def name_pattern():
    names = name_list()
    if not names:
        return re.compile(r"(?!x)x")      # matches nothing
    return re.compile(r"(?<![\w.\-/])(" + "|".join(map(re.escape, names)) + r")(?![\w.\-/])")


# --- other checks ------------------------------------------------------------------------------
# The last label of a domain starts with a letter, so sharp@0.35.5 and #000000@0.97 are not addresses.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z][\w-]*")
MEETING = re.compile(
    r"\b(?:stand-?up|transcript|all-hands|retro)\b"
    r"|\b\d{1,2}/\d{1,2}\s+(?:stand-?up|call|sync|meeting|review)\b"
    r"|\b(?:on|during|in)\s+(?:the|our|yesterday's|today's)\s+(?:call|sync|meeting|stand-?up)\b"
    r"|\bas\s+(?:I|we)\s+said\s+(?:in|at|on)\s+(?:the\s+)?(?:call|sync|stand-?up|meeting)\b",
    re.I,
)
EM_DASH = re.compile("—")

FIXES = {
    "name": "Name the role or the decision instead (\"the API owner\", \"the design track\"), or "
            "state the fact flatly with no attribution at all.",
    "email": "Drop it. A doc the team reads never needs an address; put it in your own working "
             "notes if you need it to send something.",
    "meeting": "State the decision or fact on its own. A reader with no context should read it as "
               "ordinary product thinking, not as minutes from a call.",
    "em-dash": "Use a period or a comma. Not parentheses or an en dash, which just trade one tell "
               "for another.",
}


def _blank_fences(text: str) -> str:
    """Drop fenced blocks, preserving line count so reported line numbers stay true."""
    return re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def strip_noise(text: str) -> str:
    """Fully stripped: fences, inline code, URLs, link targets."""
    text = _blank_fences(text)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\]\([^)\n]*\)", "]()", text)    # a link target never spans a line break
    return text


_KNOWN = []


def known_ids():
    """The project's item ids, read once from the ADO cache; None (every id-shaped match) when unread."""
    if not _KNOWN:
        _KNOWN.append(ado_links.known_ids())
    return _KNOWN[0]


def ado_off():
    """None when the ado-id check runs, else why not: it needs ado_links.py and an ADO project, since a
    project that tracks work elsewhere has no item to link a #1234 to."""
    if ado_links is None:
        return "ado_links.py could not be imported"
    if not all(kit_config.ado()):
        return "ado.org or ado.project is unset"
    return None


def lint(text: str, only=None, path=None, ado=True):
    """[(kind, line, hit, context)]. Two passes, because the guards that prevent false positives on
    names cause false negatives on emails: names and meetings are matched on fully stripped text,
    emails and em dashes on text with only fenced blocks removed.

    `ado` adds the ado-id check when it runs here (ado_off()); off for commit messages, where Azure
    Repos links #1234 itself, and for the hook. `path` says whether the file's blockquotes post as plain
    text (ado_links.plain_quotes).

    `only`, a set of 1-based line numbers, keeps only the findings on those lines. It filters before
    de-duplication, so a name already higher in the file cannot hide the same name on an added line."""
    prose = strip_noise(text)
    semi = _blank_fences(text)
    findings = []
    checks = (
        ("name", name_pattern(), prose),
        ("email", EMAIL, semi),
        ("meeting", MEETING, prose),
        ("em-dash", EM_DASH, semi),
    )
    for kind, rx, hay in checks:
        seen = set()
        rows = hay.splitlines()
        for m in rx.finditer(hay):
            line = hay[: m.start()].count("\n") + 1
            if only is not None and line not in only:
                continue
            key = (kind, m.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            ctx = rows[line - 1].strip()[:90] if line - 1 < len(rows) else ""
            findings.append((kind, line, m.group(0), ctx))
    if ado and ado_off() is None:
        seen = set()
        rows = text.splitlines()
        for h in ado_links.md_scan(text, known_ids(), bool(path) and ado_links.plain_quotes(path)):
            hit = text[h["start"]:h["end"]]
            if h["status"] != "bare" or (only is not None and h["line"] not in only) or hit.lower() in seen:
                continue
            seen.add(hit.lower())
            findings.append(("ado-id", h["line"], hit, rows[h["line"] - 1].strip()[:90]))
    return sorted(findings, key=lambda f: (f[1], f[0]))


def hook() -> int:
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0                                  # never break the session on a malformed event
    if ev.get("tool_name") not in ("Write", "Edit"):
        return 0
    ti = ev.get("tool_input") or {}
    raw = ti.get("file_path") or ""
    if not raw:
        return 0
    path = raw if os.path.isabs(raw) else os.path.join(ev.get("cwd") or "", raw)
    if not in_scope(path):
        return 0
    # Write replaces the file, so judge the whole thing. Edit only adds new_string, so judging the
    # whole file would punish pre-existing debt on an unrelated edit.
    content = ti.get("content") if ev["tool_name"] == "Write" else ti.get("new_string")
    if not content:
        return 0
    findings = lint(content, ado=False)
    if not findings:
        return 0
    by_kind = {}
    for kind, line, hit, ctx in findings:
        by_kind.setdefault(kind, []).append((line, hit, ctx))
    out = [f"Blocked: {os.path.basename(path)} is a doc the team reads, and this write adds "
           f"{len(findings)} thing(s) that do not belong in one.", ""]
    for kind, items in by_kind.items():
        out.append(f"  {kind} ({len(items)}):")
        for line, hit, ctx in items[:6]:
            out.append(f"    L{line}  {hit!r}  in: {ctx}")
        if len(items) > 6:
            out.append(f"    ... and {len(items) - 6} more")
        out.append(f"    -> {FIXES[kind]}")
        out.append("")
    out.append("Provenance belongs in your own working notes, not here. If this file is genuinely "
               "not team-facing, it is in the wrong directory rather than needing an exception.")
    # The reason names the fix: a block that only says no gets retried verbatim.
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "\n".join(out),
    }}))
    return 0


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_added(diff_text):
    """{path: set of added line numbers} from `git diff -U0` output."""
    added, cur = {}, None
    for row in diff_text.splitlines():
        if row.startswith("+++ "):
            cur = row[len("+++ b/"):] if row.startswith("+++ b/") else None
            if cur is not None:
                added.setdefault(cur, set())
        elif row.startswith("@@") and cur is not None:
            m = _HUNK.match(row)
            if m:
                start, count = int(m.group(1)), int(m.group(2) or 1)
                added[cur].update(range(start, start + count))
    return added


def added_lines(top, paths, revs=("--cached",)):
    """{path: set of line numbers the change adds}, from `git diff -U0` in the checkout `top`.
    The default reads the staged change; revs=(A, B) reads a commit range. A path git reports no
    hunk for is left out, and cli() then judges that file whole. Raises CalledProcessError when git
    cannot answer, so the hook can say the check did not run."""
    import subprocess
    if not paths:
        return {}
    out = subprocess.run(["git", "-c", "core.quotePath=false", "-C", top, "diff", *revs, "-U0",
                          "--no-color", "--no-ext-diff", "--", *paths],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return parse_added(out)


def cli(paths, added=None) -> int:
    # `added` ({path: set of line numbers}) is the pre-commit mode: a finding blocks only on a line
    # the commit adds; findings already in the file print as notes.
    # Printing an em dash to a non-UTF-8 console must not crash the linter.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bad = 0
    unread = []
    for p in paths:
        try:
            text = open(p, encoding="utf-8").read()
        except Exception as e:
            # An unread file was not linted, whatever the linter would have made of it.
            print(f"{p}: cannot read ({e})")
            unread.append(p)
            continue
        # A generated file quotes its source as it is (a design tool's node names, say), and
        # escaping a character there breaks the generator's own check. Its findings print as
        # notes; fix them at the source the generator reads.
        generated = bool(GENERATED.search("\n".join(text.splitlines()[:5])))
        scoped = in_scope(os.path.abspath(p)) and not generated
        # The ado-id check holds in every .md that isn't an archive, a record, a store or generated.
        off = ado_off()
        ado_scoped = off is None and ado_links.left_out(os.path.abspath(p), text) is None and not generated
        old = []
        added_here = None if added is None else added.get(p)
        if added_here is None:
            findings = lint(text, path=p)
        else:
            findings = lint(text, added_here, path=p)
            old = [f for f in lint(text, path=p) if f[1] not in added_here]
        counted = [f for f in findings if scoped or (ado_scoped and f[0] == "ado-id")]
        tag = "" if scoped else ("  [generated file, reported but not blocking]" if generated
                                 else "  [ado-id blocks here; the other checks are reported, not blocking]"
                                 if counted else "  [out of scope, reported but not blocking]")
        # The exit code follows scope, not findings: refuse only what the gate governs.
        if counted:
            bad = 1
        if findings or old:
            print(f"\n{p}{tag}")
            for kind, line, hit, ctx in findings:
                print(f"  {kind:8} L{line:<5} {hit!r}  in: {ctx}")
            if any(f[0] == "ado-id" for f in findings):
                print(f"  ado-id: link each one to its item; python "
                      f"{os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ado_links.py')} link {p}")
            if old:
                print(f"  {len(old)} finding(s) on lines this commit does not add, so not blocking"
                      f"{'' if findings else '; none on the lines it adds'}:")
                for kind, line, hit, ctx in old:
                    print(f"    {kind:8} L{line:<5} {hit!r}")
        else:
            # Not "clean": this is a fail-open check against a maintained list. Say what was checked.
            print(f"{p}: no hits against the {4 if off else 5} checks "
                  f"(name list = {len(name_list())} entries; a name not on it passes"
                  f"{f'; ado-id did not run: {off}' if off else ''}){tag}")
    if unread:
        print(f"\ndoclint did not run on {len(unread)} of {len(paths)} named file(s): "
              f"they could not be read. That is not a pass.")
    # A finding outranks a file that did not run: 1 says fix something.
    return bad or (2 if unread else 0)


def staged() -> int:
    """Pre-commit mode: lint the staged .md files, blocking only on the lines they add."""
    import subprocess
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             check=True).stdout.strip()
        names = subprocess.run(["git", "-C", top, "diff", "--cached", "--name-only", "--diff-filter=ACMR",
                                "-z"], capture_output=True, text=True, check=True).stdout
        paths = [p for p in names.split("\0") if p.lower().endswith(".md")]
        added = added_lines(top, paths)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"doclint: git could not list the staged change ({e}); the check did not run")
        return 2
    if not paths:
        return 0
    os.chdir(top)
    return cli(paths, added)


# COMMIT MESSAGES. The team reads the commit log. --commit-msg runs the four checks above, plus the
# part of "leave out how the text was made" that is never the subject of a commit: /loop, an
# autonomous run, and a path under one person's home folder. Words like "Claude" are not checked: a
# repo that ships Claude Code setup has commits about it. Trailers and git's comment lines are exempt.
MADE_BY = re.compile(r"\bautonomous run\b|(?<![\w/])/loop\b|/Users/[A-Za-z][\w.-]*/|/home/[a-z][\w.-]*/")
TRAILER = re.compile(r"^(Co-Authored-By|Signed-off-by|Reviewed-by|Generated-by):|^\W*Generated with \[?Claude",
                     re.I)


def commit_message_findings(text):
    """[(kind, line, hit, context)] for a commit message. Trailer and comment lines are blanked, so
    line numbers stay true; everything after git's scissors line is dropped."""
    keep = []
    for row in text.split("\n"):
        if re.match(r"^# -+ >8 -+$", row):
            break
        keep.append("" if row.startswith("#") or TRAILER.search(row) else row)
    body = "\n".join(keep)
    found = lint(body, ado=False)
    prose = strip_noise(body)
    seen = set()
    for m in MADE_BY.finditer(prose):
        line = prose[: m.start()].count("\n") + 1
        if m.group(0).lower() not in seen:
            seen.add(m.group(0).lower())
            found.append(("made-by", line, m.group(0), keep[line - 1].strip()[:90]))
    return sorted(found, key=lambda f: (f[1], f[0]))


def commit_msg(path) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as e:
        print(f"commit-msg: doclint could not read the message ({e}); that is not a pass")
        return 2
    found = commit_message_findings(text)
    if not found:
        return 0
    print("commit-msg: REFUSED. The team reads this message. Fix these lines (trailers are exempt):")
    for kind, line, hit, ctx in found:
        print(f"  {kind:8} L{line:<4} {hit!r}  in: {ctx}")
    print("Attribute to a role, drop the meeting, use a period or comma for the dash, and say what "
          "changed rather than how it was made.")
    return 1


def selftest() -> int:
    """Plant known-bad and known-good text and check each verdict, offline."""
    global _cfg
    import tempfile
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    NAME_FILES.clear()
    _NAME_CACHE.clear()
    with tempfile.TemporaryDirectory() as d:
        nf = os.path.join(d, "names.txt")
        with open(nf, "w", encoding="utf-8") as f:
            f.write("# people\nJane\nDoe\n")
        NAME_FILES.append(nf)
        bad = ("# Notes\n\nJane decided this in the standup.\nMail jane@example.org for it.\n"
               "One thing — another.\n")
        kinds = {k for k, *_ in lint(bad)}
        check("each of the four checks catches its planted case",
              kinds == {"name", "email", "meeting", "em-dash"})
        good = ("# Notes\n\nThe API owner decided this.\nSlug `jane.doe--scheduler` and "
                "Analytics are fine.\nsharp@0.35.5 is a version.\n```\nJane in a fence\n```\n")
        check("a clean doc, a slug in backticks, a version pin and a fenced block pass",
              lint(good) == [])
        check("an address inside backticks is still an address",
              [k for k, *_ in lint("Write to `x.y@example.com`.\n")] == ["email"])
        check("--names drives the list (2 entries from the file)", len(name_list()) == 2)
        pf = os.path.join(d, "people.md")
        with open(pf, "w", encoding="utf-8") as f:
            f.write("# People\n\n- **Robin Okafor-Hale**: the design lead\n- **Al Ng**: too short\n"
                    "Robin Free is not an entry.\n")
        check("a people directory gives each entry's bold-name tokens of 4+ letters, nothing else",
              people_file_names(pf) == {"Robin", "Okafor", "Hale"})
        check("only= keeps findings on added lines; the same name on an added line is not hidden",
              [f[1] for f in lint("Jane one.\nJane two.\n", {2})] == [2])
        diff = "+++ b/a.md\n@@ -3,0 +4,2 @@\n+x\n+y\n+++ b/b.md\n@@ -1 +1 @@\n"
        check("parse_added reads hunk headers", parse_added(diff) == {"a.md": {4, 5}, "b.md": {1}})
        p = os.path.join(d, "doc.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(bad)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            r_bad = cli([p])
            r_old = cli([p], {p: {1}})
            r_missing = cli([os.path.join(d, "missing.md")])
            mf = os.path.join(d, "msg")
            with open(mf, "w", encoding="utf-8") as f:
                f.write("Fix the header\n\nRan as an autonomous run in /Users/someone/x\n\n"
                        "Co-Authored-By: Jane <jane@example.org>\n")
            r_msg = commit_msg(mf)
            with open(mf, "w", encoding="utf-8") as f:
                f.write("Fix the header\n\nCo-Authored-By: Jane <jane@example.org>\n")
            r_msg_ok = commit_msg(mf)
        check("CLI exits 1 on a file with findings", r_bad == 1)
        check("pre-commit mode exits 0 when findings are only on lines the commit does not add", r_old == 0)
        check("an unreadable file exits 2, not 0", r_missing == 2)
        check("--commit-msg refuses a made-by line and exempts the trailer", r_msg == 1 and r_msg_ok == 0)
        check("scope: CLAUDE.md, memory/ and a skill file are exempt; a README is in scope",
              not in_scope("/x/CLAUDE.md") and not in_scope("/x/memory/a.md")
              and not in_scope("/p/skills/foo/SKILL.md") and in_scope("/x/docs/README.md"))
        real_cfg = _cfg
        narrow = {("lint_names",): ["AGENTS.md"], ("exempt_skill_files",): False}
        _cfg = lambda *keys, default=None: narrow.get(keys, default)
        try:
            check("scope: lint_names and exempt_skill_files: false lint AGENTS.md and a skill's files; "
                  "a plugin's skills/ folder and CLAUDE.md stay exempt",
                  in_scope("/x/AGENTS.md") and in_scope("/p/skills/foo/SKILL.md")
                  and not in_scope("/x/plugins/k/skills/foo/SKILL.md") and not in_scope("/x/CLAUDE.md"))
        finally:
            _cfg = real_cfg

        # A team list in doclint.exempt_names: the same row naming a planted person, run through
        # cli() as the CLI and the hooks run it. Config is stubbed so only exempt_names is set.
        real_cfg = _cfg
        _cfg = lambda *keys, default=None: ["team.md"] if keys == ("exempt_names",) else default
        try:
            team = os.path.join(d, "team")
            os.makedirs(team)
            for fname, want, why in (
                    ("TEAM.md", 0, "a team list in exempt_names names people by design: reported, never counted"),
                    ("README.md", 1, "the same row in the README beside it is still refused"),
                    ("myteam.md", 1, "only the exact name team.md is exempt"),
                    ("CLAUDE.md", 0, "CLAUDE.md stays exempt")):
                tp = os.path.join(team, fname)
                with open(tp, "w", encoding="utf-8") as f:
                    f.write("| Jane | Design |\n")
                with contextlib.redirect_stdout(io.StringIO()):
                    got = cli([tp])
                check(f"scope: {fname} exits {want} ({why}; got {got})", got == want)
        finally:
            _cfg = real_cfg

        # The ado-id check, in every doc but an archive, a record, a generated file and a plain-quotes
        # file's quotes. Config is stubbed: docs/ is the scope, and ado_links reads a planted root.
        if ado_links is None:
            check("ado-id cases: did not run, ado_links.py could not be imported", False)
    NAME_FILES.clear()
    _NAME_CACHE.clear()
    if ado_links is None:
        print(f"{sum(results)} of {len(results)} checks passed")
        return 1
    with tempfile.TemporaryDirectory() as d:
        import contextlib, io
        real_cfg = _cfg
        u = kit_config.ado_url(9811, "https://dev.azure.com/o", "p")
        id_cases = [  # (path under the planted root, text, exit, why)
            ("notes/notes.md", "Closed #9811 today.\n", 1, "a working doc outside the scope still counts a bare id"),
            ("notes/notes2.md", f"Closed [#9811]({u}) today.\n", 0, "the same id as a link passes"),
            ("notes/notes3.md", "Story 9811 carries it.\n", 1, "a number a work-item word marks is an id too"),
            ("reviews/drafts.md", "### Ask, held until #9811 has an owner\n\n> FIX: use #9811's types\n", 1,
             "a plain-quotes file: its heading counts"),
            ("reviews/drafts.md", f"### Ask, held until [#9811]({u})\n\n> FIX: use #9811's types\n", 0,
             "a plain-quotes file: its quoted comment text posts as plain text, so it is left"),
            ("notes/_archive/old.md", "Closed #9811.\n", 0, "an archive is history"),
            ("runs/records/out.md", "Closed #9811.\n", 0, "a record is evidence"),
            ("docs/X.md", "Closed #9811, colour #333333, PR #9811.\n", 1, "a doc in scope counts"),
        ]
        root = os.path.join(d, "ws")
        kept = (ado_links.ROOT, ado_links.RECORDS, ado_links.PLAIN_QUOTES, ado_off)
        ado_links.ROOT, ado_links.RECORDS, ado_links.PLAIN_QUOTES = root, ("/records/",), ("reviews/drafts.md",)
        _KNOWN[:] = [{9811}]
        _cfg = lambda *keys, default=None: ["/docs/"] if keys == ("scope",) else default
        globals()["ado_off"] = lambda: None
        try:
            for rel, text, want, why in id_cases:
                path = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                with contextlib.redirect_stdout(io.StringIO()):
                    got = cli([path])
                check(f"ado-id {rel}: exits {want} ({why}; got {got})", got == want)
            check("ado-id is not checked in a commit message: Azure Repos links #9811 there",
                  not commit_message_findings("Fix the card gap (#9811)\n"))
            globals()["ado_off"] = lambda: "ado.org or ado.project is unset"
            path = os.path.join(root, "notes", "notes.md")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                got = cli([path])
            check("with no ADO project set, a bare id is not checked, and the summary says ado-id did not run",
                  got == 0 and "ado-id did not run: ado.org or ado.project is unset" in buf.getvalue())
        finally:
            ado_links.ROOT, ado_links.RECORDS, ado_links.PLAIN_QUOTES, off = kept
            globals()["ado_off"] = off
            _KNOWN[:] = []
            _cfg = real_cfg
    NAME_FILES.clear()
    _NAME_CACHE.clear()
    print(f"{sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


def main(argv):
    args = list(argv)
    while "--names" in args:
        i = args.index("--names")
        if i + 1 >= len(args):
            print("--names needs a file")
            return 2
        NAME_FILES.append(args[i + 1])
        del args[i:i + 2]
    if args[:1] == ["--selftest"]:
        return __import__("kit_config").run_isolated(selftest)
    if args[:1] == ["--commit-msg"]:
        return commit_msg(args[1]) if len(args) > 1 else 2
    if args[:1] == ["--staged"]:
        return staged()
    return cli(args) if args else hook()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
