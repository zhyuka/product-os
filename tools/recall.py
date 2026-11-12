#!/usr/bin/env python3
"""recall.py - have we seen this before? One search over everything your setup remembers.

    recall.py <concept> [<concept> ...] [flags]

Each argument is one CONCEPT. Inside a concept, `|` separates alternatives:
    recall.py "mobile card|MobileCard" "123:456|789:1011"
Every concept has to match the same record: a log record, a Figma thread, an ADO item with its
comments, a transcript paragraph, a commit, or a paragraph of a note. Flags work anywhere.

SOURCES (all by default; --source logs,git narrows)
  logs         every Claude Code log on this machine, on disk or inside a backup zip (cc_logs.py):
               sessions, subagents, history.jsonl, VS Code chat, this session included. Read through
               recall_index.py's index: each call first indexes what changed (up to CONFIG
               index_budget; the rest is read whole that call while a background update catches up),
               the index returns every record that could match, and each is decoded and matched here
               on its content, never on metadata such as cwd or file paths, as when every byte was
               read. A query the index cannot answer is read whole, and COVERAGE says why: an
               alternative under 3 characters or over 200, one with a quote or backslash, or text
               redaction rewrites (the index holds redacted text only). --scan reads every copy whole.
  git          commit messages on every branch of each clone, and `git log -S` on the diffs. The
               clones are recall.repos in kit_config; unset, the git repo you run in.
  notes        md/txt/json under the notes folders (recall.notes, else seen_before.notes), the single
               files recall.notes_files names (paths or globs; a file with the same bytes as one already
               taken is read once), and the request ledger ledger.py writes
               (<ledger.dir>/requests.jsonl), one paragraph per request: your words, its state, why and
               the session's title; the reply it was settled on is left to the logs source
  memory       memory cards (~/.claude*/projects/*/memory, or --memory DIR), skills, agent definitions
               (~/.claude*/agents) and CLAUDE.md files; recall.memory_globs replaces that list, for a
               setup whose memory cards are history and shouldn't be served as current
  transcripts  meeting transcripts in recall.transcripts (else seen_before.transcripts): the cleaned
               .md by paragraph, a .txt only when it has no .md, with close spellings
  figma        OPTIONAL: every comment on the files in kit_config figma.files, resolved included,
               through figma_comments.py; a node id also finds threads pinned to an ancestor with an
               offset inside that node. Also the words on each file's canvas (text, stickies, shapes,
               table cells, code blocks; hidden layers skipped) from figma_family.py's whole-file
               index: a board's is rebuilt once a day old, a design file's read as cached
               (figma_family.py build <key> makes it). Words only, the file as it is now, so --since
               and --before do not apply. Needs FIGMA_TOKEN (environment or keychain).
  ado          OPTIONAL: every work item in kit_config ado.org/ado.project, closed and removed
               included, with its comments, through ado_rest.py's cache; #N finds item N.
  A source with nothing configured prints NOT CONFIGURED with the key to set. That is not a search
  that found nothing, and it does not change the exit code. A source that is configured and cannot
  run (a folder missing, no token, a crash) prints DID NOT RUN and makes the exit 2.

kit_config keys read (all optional):
  recall.notes, recall.transcripts   a folder or a list of folders (else seen_before.notes/.transcripts)
  recall.repos                       a list of git clones to search
  recall.index_dir                   the folder of the logs index (recall_index.py), default
                                     ~/.cache/product-os/recall_logs; keep it outside any synced folder
  ledger.dir                         where ledger.py keeps requests.jsonl (notes and --brief read it)
  recall.aliases                     the alias list (form named below), default
                                     ~/.local/share/product-os/aliases.md; no file, no alias
  figma.files, ado.org, ado.project  turn the optional sources on

HOW A CONCEPT MATCHES, strongest first; every hit names its form
  exact    as typed, any case
  variant  the same words with any separator: mobile card = mobile-card = MobileCard = mobile\\ncard
  near     every word of a multi-word alternative within 120 characters, any order
  stem     a plural single word's singular, at a word start, when it is 5 letters or more:
           widgets finds widget, entries finds entry; notes does not find not. Not in git -S.
  named    an alias from the alias list (recall.aliases), one line per name:
               alias: Atlas = Project Atlas | #4242  (since 2025-01-06, the item that renamed it)
           A search --before that date does not get it, since the record did not hold the name yet.
           Not in git -S.
  fuzzy    a close spelling found in the transcripts (transcripts only): captions mishear names
  some     at least half the terms of an alternative of 3 to 8 terms (2 at least), each within 120
           characters of one place, so a query that names a tool or two beside its topic still finds the
           words that name only the topic. A term is a piece between spaces with its edge punctuation cut
           (claude.ai, signed_in_browser, #1234), matched as an alternative of its own would be; common
           words (the, and), the word after not, no, without, never or except ("not Edge"), and pieces with
           no run of 3 characters are not terms. A lead, not a match: every source prints its some hits
           after its others, --brief marks each, a search holding only leads exits 1 and says it holds
           leads, and --calibrate does not count one found. The command line, --brief and --calibrate use
           it; a tool calling search() or compile_query() gets it by putting "some": True in the query.
           Not in git -S, and in git a commit whose diff holds the text beats a lead in its message.
  Each source prints its hits newest first, some hits after the rest; in the logs, sessions where you
  typed it come first.
  A node id matches as 123:456, 123-456 and 123%3A456, never inside a longer number. A layer inside
  an instance is one id, I10:20;30:40, and matches in the form a Figma URL writes it too,
  I10-20%3B30-40. #1234 also matches _workitems/edit/1234 and "item 1234". A Figma URL becomes its
  node id and its comment id.

SEALED  A folder under the notes folders that holds a `.recall-sealed` marker is searched by no source,
  and neither is any log one of its `logs` patterns names. The marker is JSON: reason, owner, until (an
  ISO date; the seal holds through that day, then is ignored and COVERAGE says it expired) and logs, a
  list of patterns such as agent-<id>, a session id or a project-folder name. A pattern matches one whole
  component of a log copy's path, with or without its extension, on disk, in a zip or in a zip inside a
  zip; * and ? work inside a component. A session id seals its subagents too. When any copy of a log
  matches, every copy of it is skipped, and so is a log copy on disk inside the sealed folder. The
  markers are found before any source runs, in the one walk of the notes folders the notes source uses.
  A marker that will not parse still seals its folder. Use it to keep an experiment's held-out material
  away from the agents it tests. A seal never reads as a clean zero: SUMMARY says one is in force, and
  COVERAGE prints one line per seal with its folder, reason, until date and what it held back from each
  source, and names a logs pattern that matched no log copy. The exit codes do not change: a seal is a
  deliberate exclusion, not a source that did not run. --include-sealed searches sealed material anyway,
  for the experiment's owner, and COVERAGE says so. --last skips sealed logs too. seals.py holds this
  rule, and log_extract.py uses it too.

OUTPUT  SUMMARY first, then COVERAGE, then the hits, then RECAP. A NARROWED line under SUMMARY says
  what --source or --since left out, so a narrow search's zero is not read as a clear. In the logs,
  sessions where you typed the term come first, newest first. A prompt a script sent into a session
  (its turnOrigin set and not "human") reads as "script: prompt", never as you, and so does its queued
  copy; a claude -p capture's reads as "claude -p: prompt". A SPLIT session holds every concept, never
  in one record. A record another session holds a copy of (a fork, the app's continuation, a resume, the
  last under new ids) prints once, under the session whose own records start first, and that session's
  header names the others on "also in".
  In git, a commit whose only -S matches are in files the clone ignores now (a cache once committed, then
  untracked) is dropped, and COVERAGE counts those.
  Each printed line ends in the link of every tracker item (#1234, with ado.org and ado.project set) and
  Figma node it names that it doesn't link already: a node in a Figma hit links into that hit's file, any
  other into figma.default_file; with neither it stays bare. --out and --brief print links the same way.
  Long token-like strings are redacted in everything printed; logs hold pasted credentials.

EXIT  0 hits.  1 every source that is configured ran and nothing matched: leads (form some) may still be
  printed, and SUMMARY says how many to open.  2 a source, or part of one, DID NOT RUN; hits are still
  printed, but a zero from that source is not a clear.

DATES  --since and --before are UTC: --before 2026-01-05T15:39 means 15:39 UTC, and a date alone is
  midnight UTC. A value ending in Z or an offset is read in that zone, so 2026-01-05T10:39-05:00 is the
  same cutoff. Each source's time is turned into UTC before the compare: logs, Figma and ADO write UTC,
  git writes the author's offset, a transcript's file name (..._YYYY-MM-DD_HHMM...) holds the local time
  it began, read in this machine's zone, and notes and memory use the file's last-modified time for
  --since. The report header prints the cutoff in UTC.
  --before does not cut notes or memory: a file has no history, so each is searched as it is today,
  and COVERAGE says so. In ADO it reads each item as ADO held it at the cutoff (asOf, about 4 calls per
  cutoff, saved gzip in ~/.cache/recall_ado_asof/ and read from there next time; past 50 MB, CONFIG
  ado_asof_max_mb, the least recently used cutoff is dropped), and leaves out comments written after
  it. When that lookup cannot run, item fields are today's, COVERAGE says so, exit 2.

  recall.py --brief <concept>   what to read before answering: your words on it from the request ledger
                                (rulings first), the sessions live on it in the last 48 h with their task
                                lists and recaps (and every other live one in a line), and earlier work
                                in notes, git, ADO (read as cached, with its age) and transcripts as one
                                list of 12: each source's strongest hit, then each one's next. Strength
                                counts the rarer query words a hit holds, its match form, a title or file
                                name match and a decision record. A NARROWED line says what it leaves out.
                                A concept of 3 or more terms gets a SOME line, and each line or session
                                matched only as form some comes after the full matches, marked [some: the
                                terms it holds]: a lead to open, not a match. This session, headless runs,
                                sealed logs and archived sessions are left out. With --before, as it stood
                                then. Not Figma or older logs. Exit 0 something matched, 1 nothing matched
                                (with leads listed, a LEADS ONLY line says so), 2 a part DID NOT RUN: with no request
                                ledger (ledger.py writes it) or no notes folder set, that part says so and
                                the exit is 2; ADO or transcripts not configured is said, not exit 2.
                                Live sessions are found under
                                <root>/.claude/projects; the desktop app's session files give titles and
                                archived state, and its task-list and wrap-up tools give plans and recaps.
  recall.py --last /rebase      every invocation of a command or skill, and the logs since the last;
                                a prompt a script sent is not counted, nor is this session's own run
  recall.py --calibrate FILE    re-run a set of past misses and print N of M found; exit 1 on a miss
                                in a source that ran, 2 when every miss is in a source that DID NOT RUN.
                                FILE is JSON: [{"id", "terms": [...], "expect": [...], "before"}], each
                                expect one of: an 8-hex session id, figma:<comment id>, ado:<id>,
                                git:<sha>, memory:<card stem>, file:<path>, transcript:<words>.
                                A session a header names on "also in" counts, marked (copy). An answer
                                found only as a lead (form some) does not count: it is marked ~ and
                                counted apart
  recall.py --selftest          planted tree, every source, then each rule broken on purpose

NO POOL. Notes, memory, transcripts and the logs scan run in a process pool. Where none can start (a sandbox
  that denies multiprocessing's semaphores, a platform with no sem_open), the search runs in this process with
  the same results, slower, and says so in one line on stderr.

ENCODING GUARD. A UnicodeEncodeError on a star or an arrow in a snippet would exit non-zero
  mid-report, and non-zero reads as "nothing found". stdout and stderr are reconfigured below so that
  cannot happen.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse, bisect, collections, datetime, difflib, glob, gzip, hashlib, io, itertools, json, math, os, re
import subprocess, sys, sqlite3, tempfile, time, urllib.parse, zipfile, zlib
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = os.path.dirname(os.path.realpath(__file__))
if TOOLS not in sys.path:
    if TOOLS not in sys.path: sys.path.append(TOOLS)
import cc_logs  # noqa: E402
import seals as sealing  # noqa: E402  the .recall-sealed rule, shared with log_extract.py
import kit_config  # noqa: E402
import recall_index  # noqa: E402  the logs source's index

HOME = os.path.expanduser("~")
SOURCES = ("logs", "figma", "ado", "transcripts", "git", "notes", "memory")
OPTIONAL = ("figma", "ado")                 # run only when configured
STAMP = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")   # a transcript's [hh:mm:ss] time stamp

# Where each source reads. None: from kit_config at run time. The selftest points every entry at a
# planted tree.
CONFIG = {
    "root": HOME,
    "cache": cc_logs.CACHE,
    "transcripts": None,    # [folder, ...]: the first that exists is read
    "repos": None,          # [clone, ...]
    "notes_dirs": None,     # [folder, ...]
    "notes_files": [],      # single files searched as notes
    "memory_globs": [os.path.join(HOME, ".claude*", "projects", "*", "memory", "*.md"),
                     os.path.join(HOME, ".claude*", "skills", "**", "*.md"),
                     os.path.join(HOME, ".claude*", "CLAUDE.md"),
                     os.path.join(HOME, ".claude*", "agents", "*.md")],
    "aliases": None,        # the alias list named() reads; None: recall.aliases in kit_config, else ALIASES
    "ado": None,            # (org, project)
    "ado_cache": None,  # None: the cache ado_rest.py keeps (ado_rest.CACHE); the selftest plants one
    "ado_pull": [sys.executable, os.path.join(TOOLS, "ado_rest.py"), "pull"],
    "ado_asof": None,  # cutoff -> {id: {"fields"}} as ADO held them then; None reads ADO (the selftest plants one)
    "ado_asof_cache": os.path.join(HOME, ".cache", "recall_ado_asof"),
    "ado_asof_max_mb": 50,  # saved cutoffs past this are dropped, least recently used first
    "figma_files": None,    # {file key: (kind, name)}
    "figma_default": None,  # the file a bare node id links into when printed; None: figma.default_file in kit_config
    "figma_token": None,    # None: kit_config.token("FIGMA_TOKEN") decides whether figma can run
    "figma_canvas": "auto",  # figma_family.load mode for a board's canvas text; a design file's is read as cached
    "ledger": None,         # None: <ledger.dir>/requests.jsonl, where ledger.py writes it (notes and --brief)
    "app_sessions": os.path.join(HOME, "Library", "Application Support", "Claude", "claude-code-sessions"),
    "workers": min(os.cpu_count() or 4, 12),
    "index": recall_index.PATH,      # the logs index; None reads every copy whole on each call
    "index_budget": 256 << 20,      # bytes of log one call indexes; past it, the rest are read whole this call
    "index_spawn": True,            # ...and a background `recall_index.py update` catches up
}
MUT = set()  # selftest only: the rule being broken on purpose


def _folders(v):
    """A kit_config value that is a folder or a list of folders -> [expanded absolute paths]."""
    v = [v] if isinstance(v, str) else (v if isinstance(v, (list, tuple)) else [])
    return [os.path.abspath(os.path.expanduser(x)) for x in v if isinstance(x, str) and x.strip()]


def _setting(key):
    """recall.<key>, else seen_before.<key> (the folder another tool reads too), as a list of folders."""
    return _folders(kit_config.get("recall", key)) or _folders(kit_config.get("seen_before", key))


def notes_dirs():
    return CONFIG["notes_dirs"] if CONFIG["notes_dirs"] is not None else _setting("notes")


def ledger_path():
    """The request ledger, as ledger.py finds it: ledger.dir in kit_config, else its default folder."""
    if CONFIG["ledger"] is not None:
        return CONFIG["ledger"]
    d = kit_config.get("ledger", "dir")
    d = d if isinstance(d, str) and d.strip() else kit_config.home_dir(os.path.join(".local", "share"), "ledger")
    return os.path.join(os.path.abspath(os.path.expanduser(d)), "requests.jsonl")


def _note_files():
    """The single files searched as notes: CONFIG notes_files; each path or glob in recall.notes_files, where a
    file holding the same bytes as one already taken is left out (a test-run folder can hold hundreds of copies
    of one write-up); and the request ledger when there is one. A .jsonl, so the walk's extensions never take
    it."""
    out, seen = list(CONFIG["notes_files"]), set()
    for pat in _folders(kit_config.get("recall", "notes_files")):
        for p in sorted(glob.glob(pat, recursive=True)) if glob.has_magic(pat) else [pat]:
            if p in out or not os.path.isfile(p):
                continue
            try:
                with open(p, "rb") as fh:
                    h = hashlib.sha1(fh.read()).hexdigest()
            except OSError:
                continue
            if h not in seen:
                seen.add(h)
                out.append(p)
    led = ledger_path()
    return out + ([led] if os.path.isfile(led) and led not in out else [])


def memory_globs():
    """recall.memory_globs (globs, ~ expanded) when set, in place of CONFIG memory_globs: a setup whose memory
    cards are history leaves ~/.claude*/projects/*/memory out, so a card isn't served as current."""
    return _folders(kit_config.get("recall", "memory_globs")) or CONFIG["memory_globs"]


def transcript_dirs():
    return CONFIG["transcripts"] if CONFIG["transcripts"] is not None else _setting("transcripts")


ALIASES = kit_config.home_dir(os.path.join(".local", "share"), "aliases.md")


def aliases_path():
    """The alias list named() reads: CONFIG aliases, else recall.aliases in kit_config, else ALIASES. A file
    that does not exist means no alias applies."""
    if CONFIG.get("aliases") is not None:
        return CONFIG["aliases"]
    v = kit_config.get("recall", "aliases")
    return os.path.abspath(os.path.expanduser(v)) if isinstance(v, str) and v.strip() else ALIASES


def figma_files():
    return CONFIG["figma_files"] if CONFIG["figma_files"] is not None else kit_config.figma_files()


def ado_target():
    """(org, project), each None when unset."""
    return CONFIG["ado"] if CONFIG["ado"] is not None else kit_config.ado()


def _off(name):
    """Why an optional or folder source is not configured, naming the key to set; None when it is."""
    if name == "figma" and not figma_files():
        return "set figma.files in kit_config to search Figma comments"
    if name == "ado" and not all(ado_target()):
        return "set ado.org and ado.project in kit_config to search ADO"
    if name == "notes" and not notes_dirs() and not _note_files():
        return "set recall.notes in kit_config to a notes folder"
    if name == "transcripts" and not transcript_dirs():
        return "set recall.transcripts in kit_config to a transcripts folder"
    return None

# --------------------------------------------------------------------------------------------- matching

FORMS = ("exact", "variant", "near", "stem", "named", "fuzzy", "some")
RANK = {f: i for i, f in enumerate(FORMS)}
NEAR = 120
# Form some: an alternative of SOME_MIN or more terms also matches where at least half of them, 2 at least, sit
# within NEAR of one place. On 2026-11-11 --brief "claude.ai Safari not Edge signed_in_browser" found none of the
# three messages where the user had said to read claude.ai in Safari, as near needs every word, and
# --brief "claude.ai safari" found all three.
SOME_MIN = 3
SOME_MAX = 8         # more terms is a pasted sentence: its C(n, n/2) index groups grow past 70
NEGATE = frozenset({"not", "no", "without", "never", "except"})   # "not Edge": Edge is not a term
STOP = frozenset("a an and any are as at be but by can did do does for from had has have how i if in into is it "
                 "its just me my no nor not of off on or our out so than that the their them then there these they "
                 "this those to too up us vs was we were what when where which who why will with would you your"
                 .split())
SEP = r"(?:[ \t\n\r_\-/]|\\+[nrt])*"
RAW_SEP = rb"(?:[ \t_\-/]|\\+[nrt])*"
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
PAIR = r"(\d+)(?::|-|%3[aA])(\d+)"
# A layer inside an instance is one id: the instance, then the layer's id in its main component,
# joined by ; (%3B in a URL). Figma writes it I10900:71900;5900:52900.
INST = r"I\d+(?::|-|%3[aA])\d+(?:(?:;|%3[bB])\d+(?::|-|%3[aA])\d+)+"
NODE = re.compile(rf"^(?:{INST}|\d+(?::|-|%3[aA])\d+)$")
FIG_URL = re.compile(rf"figma\.com/\S*?node-id=({INST}|\d+(?::|-|%3[aA])\d+)(?:\S*?#(\d+))?")


def _parts(s):
    """Words of an alternative: split on separators, then on camelCase."""
    out = []
    for w in re.split(r"[ \t\n\r_\-/]+", s):
        out += [p for p in CAMEL.split(w) if p]
    return out


def _safe(s):
    """Printable ASCII that JSON writes verbatim, so it can be searched for in the raw log bytes."""
    return bool(re.fullmatch(r"[\x20-\x7e]+", s)) and '"' not in s and "\\" not in s


def _bound(s, pat):
    """Alternatives of 4 characters or fewer get word edges, so ADO does not match inside shadow."""
    if len(s) <= 4:
        if s[:1].isalnum():
            pat = r"(?<![A-Za-z0-9])" + pat
        if s[-1:].isalnum():
            pat += r"(?![A-Za-z0-9])"
    return pat


def _raw(s):
    """[(literal, regex or None)] that find s in a LOWERCASED log line, JSON-escaped or not.

    A superset: the decoded record decides. Safe text is its own literal. Otherwise the longest safe
    run inside one word (3+ characters) stands in. With no such run, the longest word in UTF-8 and in
    JSON's \\u escapes, in its given, lower and upper case."""
    if _safe(s):
        return [(s.lower().encode(), None)]
    runs = [r for p in _parts(s) for r in re.findall(r"[\x21\x23-\x5b\x5d-\x7e]+", p)]
    best = max(runs, key=len, default="")
    if len(best) >= 3:
        return [(best.lower().encode(), None)]
    part = max(_parts(s) or [s], key=len)
    lits = set()
    for v in (part, part.lower(), part.upper()):
        lits.add(v.encode("utf-8").lower())
        if "no_decode_path" not in MUT:
            lits.add(json.dumps(v)[1:-1].encode().lower())
    return [(lit, None) for lit in sorted(lits)]


def _node(s):
    """A node id in any form it is written -> 123:456 or I10900:71900;5900:52900; else None."""
    if not NODE.match(s) or ("no_instance_id" in MUT and s.startswith("I")):
        return None
    return ("I" if s.startswith("I") else "") + ";".join(f"{a}:{b}" for a, b in re.findall(PAIR, s))


def _alt(text):
    """One alternative -> its kind, decoded-text forms, raw prefilters and near words."""
    n = _node(text)
    if n:
        pairs = re.findall(PAIR, n)
        pat = "(?:;|%3[bB])".join(f"{a}(?::|-|%3[aA]){b}" for a, b in pairs)
        lead = "I" if n[0] == "I" else r"(?<!\d)"
        # The raw prefilter starts at the first number, on lowercased bytes.
        raw = rb"(?:;|%3b)".join(a.encode() + rb"(?::|-|%3a)" + b.encode() for a, b in pairs)
        return {"text": n, "kind": "node",
                "forms": [("exact", re.compile(rf"{lead}{pat}(?!\d)"))],
                "raw": [(pairs[0][0].encode(), re.compile(raw))],
                "near": None, "near_raw": None}
    m = re.fullmatch(r"#(\d+)", text)
    if m:
        n = m.group(1)
        return {"text": text, "kind": "ado", "id": n,
                "forms": [("exact", re.compile(rf"(?<![&\w])#{n}(?!\d)")),
                          ("variant", re.compile(rf"_workitems/edit/{n}(?!\d)")),
                          ("variant", re.compile(rf"\b(?:item|ticket|bug|story|task|feature|ado)\s*#?\s*{n}(?!\d)",
                                                 re.I))],
                "raw": [(n.encode(), None)], "near": None, "near_raw": None}
    if text.isdigit():
        return {"text": text, "kind": "digits", "id": text,
                "forms": [("exact", re.compile(rf"(?<!\d){text}(?!\d)"))],
                "raw": [(text.encode(), None)], "near": None, "near_raw": None}
    parts = _parts(text)
    forms = [("exact", re.compile(_bound(text, re.escape(text)), re.I))]
    raw = _raw(text)
    if len(parts) >= 2 and "no_variants" not in MUT:
        forms.append(("variant", re.compile(_bound(text, SEP.join(re.escape(p) for p in parts)), re.I)))
        if all(_safe(p) for p in parts):
            raw.append((parts[0].lower().encode(),
                        re.compile(RAW_SEP.join(re.escape(p.lower()).encode() for p in parts))))
    words = sorted({w.lower() for w in re.findall(r"\w+", text) if len(w) >= 3})
    near = near_raw = None
    if len(words) >= 2:
        near = [re.compile(re.escape(w), re.I) for w in words]
        near_raw = [_raw(w) for w in words]
    return {"text": text, "kind": "text", "forms": forms, "raw": raw, "near": near, "near_raw": near_raw,
            "some": _some_terms(text)}


def _alt_sets(a):
    """The word lists the logs index looks an alternative up by, each list all in one row: what every exact or
    variant match holds, then, with near words, every near word."""
    t = a["text"]
    if a["kind"] == "node":
        return [re.findall(r"\d+", t)]
    if a["kind"] in ("ado", "digits"):
        return [[a["id"]]]
    words = sorted({w.lower() for w in re.findall(r"\w+", t) if len(w) >= 3})
    return [_parts(t)] + ([words] if a["near"] else [])


def _some_terms(text):
    """Form some's terms for an alternative of SOME_MIN to SOME_MAX terms, else None: {"terms", "subs" (each term
    as an alternative of its own, _alt), "rxs" (each one's forms), "k" (how many must sit together: half, rounded
    up, 2 at least)}. A term is a piece between spaces with its edge punctuation cut, once however often it is
    written. A common word (STOP) is not one, nor the piece a NEGATE word rules out ("not Edge": a record holding
    Edge is not nearer the topic for it), nor a piece the logs index can't look up (no part of 3 characters)."""
    pieces = text.split()
    if len(pieces) < SOME_MIN or "no_some" in MUT:
        return None
    subs, seen, negated = [], set(), False
    for p in pieces:
        t = p.strip(".,;:!?()[]{}<>\"'`")
        w = t.lower()
        if w in NEGATE:
            negated = True
            continue
        if not t or w in STOP:
            continue
        if negated:
            negated = False
            continue
        sub = _alt(t)
        if w in seen or recall_index.all_of(_alt_sets(sub)[0]) is None:
            continue
        seen.add(w)
        subs.append(sub)
    if not SOME_MIN <= len(subs) <= SOME_MAX:
        return None
    return {"terms": [s["text"] for s in subs], "subs": subs, "rxs": [[rx for _, rx in s["forms"]] for s in subs],
            "k": max(2, -(-len(subs) // 2))}


def _some_pos(s, text, cap=400, low=None):
    """Each term's places in text, sorted: each of its forms' first cap matches, as match_concept reads a record;
    cap 0, every place one can start (_starts), as a paragraph's prefilter needs. low: text.lower() with no
    FOLD_ODD in it, where an ASCII text term's forms run lowercased (_lowered), faster."""
    out = []
    for sub, rxs in zip(s["subs"], s["rxs"]):
        fast = low is not None and sub["kind"] == "text" and sub["text"].isascii()
        on, ps = (low if fast else text), set()
        for rx in rxs:
            rx = _lowered(rx) if fast else rx
            ps.update(_starts(rx, on) if not cap else (m.start() for _, m in zip(range(cap), rx.finditer(on))))
        out.append(sorted(ps))
    return out


def _some_at(s, pos):
    """[(place, the numbers of the terms within NEAR of it)] for each place of a term where k or more terms are."""
    out = []
    for ps in pos:
        for p in ps:
            held = [j for j, qs in enumerate(pos)
                    if qs and (i := bisect.bisect_left(qs, p - NEAR)) < len(qs) and qs[i] <= p + NEAR]
            if len(held) >= s["k"]:
                out.append((p, held))
    return out


def _some(s, text):
    """(place, [the terms there]) for a some alternative in text: the place with the most terms within NEAR of it,
    the first on a tie; None with fewer than k near one another. Each form's first 400 places, as _near."""
    pos = _some_pos(s, text)
    if sum(1 for ps in pos if ps) < s["k"]:
        return None
    best = None
    for p, held in _some_at(s, pos):
        if best is None or (len(held), -p) > (len(best[1]), -best[0]):
            best = (p, held)
    return best and (best[0], [s["terms"][j] for j in best[1]])


def _some_ready(s, low):
    """Whether k of a some alternative's terms can be in low, lowercased text with no FOLD_ODD: each term's words
    (_needs) all there. A plain substring test, many times faster than the forms."""
    n = 0
    for sub in s["subs"]:
        need = dict(_needs(sub) or ())
        words = need.get("variant") or need.get("forms")
        n += words is None or all(w in low for w in words)
    return n >= s["k"]


def _alts(label):
    out = []
    for alt in (x.strip() for x in label.split("|")):
        if not alt:
            continue
        m = FIG_URL.search(alt)
        n = m and _node(m.group(1))
        if n:
            out.append(n)
            if m.group(2):
                out.append(m.group(2))
        else:
            out.append(alt)
    return out


def utc(ts, local=False):
    """ts as UTC text in the form Claude Code logs write, 2026-10-05T16:00:55.000Z, so any two compare and
    sort as strings; "" when it will not parse. Takes ISO 8601 with Z or an offset (git's %aI writes the
    author's, 2026-10-05T11:00:55-05:00), epoch milliseconds, or a datetime. A time with no zone is UTC,
    or with local=True this Mac's local time (a transcript's file name)."""
    if "no_utc" in MUT:  # selftest: the plain string compare this replaced
        if isinstance(ts, datetime.datetime):
            return ts.astimezone().strftime("%Y-%m-%dT%H:%M:%S")
        return ts if isinstance(ts, str) else ""
    try:
        if isinstance(ts, datetime.datetime):
            d = ts
        elif isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts > 0:
            d = datetime.datetime.fromtimestamp(ts / 1000, datetime.timezone.utc)
        elif isinstance(ts, str) and ts.strip():
            d = datetime.datetime.fromisoformat(re.sub(r"[zZ]$", "+00:00", ts.strip()))
        else:
            return ""
        if d.tzinfo is None:
            d = d.astimezone() if local else d.replace(tzinfo=datetime.timezone.utc)
        d = d.astimezone(datetime.timezone.utc)
    except (ValueError, OverflowError, OSError):
        return ""
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def _cut(v):
    """A --since or --before value as UTC text; one with no zone is UTC."""
    if not v:
        return v
    t = utc(v)
    if not t:
        raise ValueError(f"{v!r} is not a time: give YYYY-MM-DD[THH:MM[:SS]], UTC unless it ends in Z or an "
                         f"offset such as -05:00")
    return t


def s_stem(word):
    """Harman's S-stemmer, plural removal only, as Lucene's EnglishMinimalStemmer: widgets ->
    widget, entries -> entry. '' when nothing changes or the stem is under 5 letters, so notes and
    modes stay as typed (a 4-letter stem such as "not" matches far too much)."""
    w = word.lower()
    if not re.fullmatch(r"[a-z]{4,}", w) or not w.endswith("s") or w.endswith(("us", "ss")):
        return ""
    if w.endswith("ies") and not w.endswith(("eies", "aies")):
        st = w[:-3] + "y"
    elif w.endswith(("aes", "ees", "oes", "ies")):
        return ""
    else:
        st = w[:-1]
    return st if len(st) >= 5 else ""


NAMED_RX = re.compile(r"^\s*[-*]?\s*alias:\s*(.+?)\s*=\s*(.+?)\s*\(since (\d{4}-\d{2}-\d{2})[^)]*\)\s*$", re.I | re.M)


def named():
    """{term: [(alias, since)]} from the alias list's lines (aliases_path()), each with the date of the record
    it cites: `alias: Atlas = Project Atlas | #4242  (since 2025-01-06, the item that renamed it)`. A query
    before that date doesn't get the alias, so a search as of an earlier time can't credit a name the record
    didn't hold yet. {} with no file."""
    path = aliases_path()
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, TypeError):
        return {}
    out = {}
    for term, alts, since in NAMED_RX.findall(text):
        for a in (x.strip() for x in alts.split("|")):
            if a:
                out.setdefault(term.strip().lower(), []).append((a, since))
    return out


def _extra_alts(alts, cut):
    """A plural single word's stem (form stem, at a word start) and a listed name's aliases (form named)."""
    have = {a["text"].lower() for a in alts}
    out = []
    names = {} if "no_named" in MUT else named()
    for a in alts:
        if a["kind"] != "text":
            continue
        st = "" if "no_stem" in MUT or " " in a["text"] else s_stem(a["text"])
        if st and st not in have:
            have.add(st)
            out.append({"text": st, "kind": "stem", "forms": [("stem", re.compile(r"(?<![A-Za-z0-9])" + re.escape(st), re.I))],
                        "raw": _raw(st), "near": None, "near_raw": None})
        for alias, since in names.get(a["text"].lower(), ()):
            if (cut and since >= cut[:10]) or alias.lower() in have:
                continue
            have.add(alias.lower())
            b = _alt(alias)
            out.append(dict(b, forms=[("named", rx) for _, rx in b["forms"]], named=True, near=None, near_raw=None,
                            some=None))
    return out


def compile_query(q):
    """{"labels": [...], "since", "before", "some"} -> the same with "concepts": [{"label", "alts": [...]}], and
    since and before as UTC text. Each concept also gets its plural words' stems and its listed aliases, and with
    "some" true its long alternatives' form some."""
    before = _cut(q.get("before"))
    cons = []
    for lb in q["labels"]:
        alts = [_alt(a) for a in _alts(lb)]
        if not q.get("some"):     # form some only when the query asks, as the command line does: a tool that imports
            alts = [dict(a, some=None) for a in alts]     # recall keeps the matches it was built and measured on
        cons.append({"label": lb, "alts": alts + _extra_alts(alts, before)})
    return dict(q, concepts=[c for c in cons if c["alts"]], since=_cut(q.get("since")), before=before)


def _near(rxs, text):
    """The first of the first word's first 400 places with each other word's first 400 places within
    NEAR of it; by bisect, as the pairwise test was a large share of a logs scan."""
    pos = [[m.start() for _, m in zip(range(400), rx.finditer(text))] for rx in rxs]
    if not all(pos):
        return None
    rest = [sorted(qs) for qs in pos[1:]]
    for p in pos[0]:
        if all((i := bisect.bisect_left(qs, p - NEAR)) < len(qs) and qs[i] <= p + NEAR for qs in rest):
            return p
    return None


def match_concept(con, text, extra=()):
    """(rank, form, position, alternative) of the strongest way the concept matches text, or None."""
    best = None
    for a in con["alts"]:
        for form, rx in a["forms"]:
            m = rx.search(text)
            if m:
                got = (RANK[form], form, m.start(), a["text"])
                if best is None or got[0] < best[0]:
                    best = got
                break
        if best and best[0] == 0:
            return best
        if a["near"] and (best is None or best[0] > RANK["near"]):
            p = _near(a["near"], text)
            if p is not None:
                best = (RANK["near"], "near", p, a["text"])
        if a.get("some") and best is None:
            got = _some(a["some"], text)
            if got:
                best = (RANK["some"], "some", got[0], a["text"])
    for form, rx, alt in extra:
        if best is not None and best[0] <= RANK[form]:
            break
        m = rx.search(text)
        if m:
            best = (RANK[form], form, m.start(), alt)
    return best


def _which(q, texts):
    """The alternatives of q that match any of texts, by their text: what a hit holds, for its strength."""
    got = set()
    for con in q["concepts"]:
        for a in con["alts"]:
            if any(t and rx.search(t) for t in texts for _, rx in a["forms"]) or \
                    (a["near"] and any(t and _near(a["near"], t) is not None for t in texts)) or \
                    (a.get("some") and any(t and _some(a["some"], t) for t in texts)):
                got.add(a["text"].lower())
    return sorted(got)


def _held(q, best, segs):
    """The terms of each concept match_record's best matched as form some, as the query writes them: [] when
    every concept matched in full."""
    out = []
    for b, con in zip(best, q["concepts"]):
        if not b or b[1] != "some":
            continue
        a = next((a for a in con["alts"] if a.get("some") and a["text"] == b[3]), None)
        got = a and _some(a["some"], segs[b[4]][1] if b[4] >= 0 else "")
        out += got[1] if got else []
    return out


# A file that holds rulings or decisions, so a hit in it outranks one of the same strength elsewhere.
DECISION_FILES = {"rulings.json", "decisions.md", "decisions.json"}
FORM_W = {"exact": 1.0, "variant": 0.95, "item id": 1.0, "diff": 0.8, "near": 0.7, "pinned here": 1.0,
          "stem": 0.6, "named": 0.6, "fuzzy": 0.5, "some": 0.4}


def _form_w(h):
    """Its strongest form's weight; a hit where any concept matched as form some only weighs as some."""
    forms = [f.split(" ")[0].split(",")[0] for f in h.get("forms") or re.split(r"/", h.get("form") or "") if f]
    if "some" in forms:
        return FORM_W["some"]
    return max((FORM_W.get(f, 0.7) for f in forms), default=0.7)


def _partial(h):
    """A hit where a concept matched only as form some: a lead, printed after the source's other hits."""
    return h.get("rank", 0) >= RANK["some"] and "no_some_tier" not in MUT


def order_hits(hits):
    """Sort one source's hits newest first, each with its match strength: the sum, over the alternatives a hit
    holds, of their rarity among this source's hits (1 + ln((H + 1) / (df + 1))), times its match form's
    weight, times 1.5 when a title, subject, heading or file name holds one, and 1.5 for a ruling or decision
    record. Only --brief's ranked list orders by strength (ranked()): in the full search, strength order put
    no better answer higher and pushed down the log sessions where you typed it. Hits matched only as form
    some go after the rest, newest first, so a long query's leads never push its matches past a cap."""
    if "no_strength" in MUT:
        return hits
    df = collections.Counter(a for h in hits for a in h.get("alts") or ())
    n = len(hits)
    for h in hits:
        idf = sum(1 + math.log((n + 1) / (df[a] + 1)) for a in h.get("alts") or ())
        h["strength"] = round(idf * _form_w(h) * (1.5 if h.get("title") else 1) * (1.5 if h.get("decision") else 1), 4)
    hits.sort(key=lambda h: h.get("ts") or "", reverse=True)
    hits.sort(key=_partial)
    return hits


def log_groups(hits):
    """[(session, its hits)] in the order recall prints them: sessions where you typed it first, then the
    newest. Strength order here buried the sessions where you typed it. A session holding only form some hits
    goes after every session holding a full one, in the same order among themselves; a session's some hits
    don't move it up among the others."""
    groups = collections.defaultdict(list)
    for h in hits:
        groups[skey(h["key"])].append(h)

    def tier(s):
        full = [h for h in groups[s] if not _partial(h)]
        hs = full or groups[s]
        return (not full, not any(h["role"].startswith("you") for h in hs),
                all(h["role"].endswith("search run") for h in hs))
    order = sorted(groups, key=lambda s: max(h["ts"] or "" for h in groups[s]), reverse=True)
    order.sort(key=tier)
    return [(s, groups[s]) for s in order]


CAPS = {"logs": 8}          # sessions; every other source prints 5 unless --max says otherwise


def ranked(qr, top=0, caps=None):
    """[{"place", "src", "hit"} or {"place", "src": "logs", "sid", "hits"}] in the order recall prints: with
    top (--brief), a ranked list first (each source's strongest entry, sources ordered by their strongest, then
    each source's next, round-robin), then each source's section in SOURCES order, an entry already in the
    list not placed again. A place is None past a section's cap. The full search prints sections only: a
    ranked list above them pushed log sessions out of the first five. In the ranked list every full match
    places before any lead (form some only), whatever their strength: a lead under a heading in a decisions
    file weighs 0.4 x 1.5 x 1.5, more than a full near match."""
    caps = dict(CAPS, **(caps or {}))
    lists = {}

    def lead(e):
        return all(_partial(h) for h in e["hits"]) if e["src"] == "logs" else _partial(e["hit"])
    for n, r in qr["src"].items():
        if not r["ran"]:
            continue
        if n == "logs":
            lists[n] = [{"src": "logs", "sid": sid, "hits": hs} for sid, hs in log_groups(r["hits"])]
        else:
            lists[n] = [{"src": n, "hit": h} for h in r["hits"]]
            if top:
                lists[n].sort(key=lambda e: (lead(e), -e["hit"].get("strength", 0)))

    def strength(e):
        return max(h.get("strength", 0) for h in e["hits"]) if e["src"] == "logs" else e["hit"].get("strength", 0)
    out, seen = [], set()
    for tier in (False, True):                  # the full matches' round-robin, then the leads'
        part = {n: [e for e in lists[n] if lead(e) == tier] for n in lists}
        heads = sorted((n for n in part if part[n]), key=lambda n: -strength(part[n][0]))
        i = 0
        while len(out) < top and any(i < len(part[n]) for n in heads):
            for n in heads:
                if i < len(part[n]) and len(out) < top:
                    out.append(dict(part[n][i], place=len(out) + 1))
                    seen.add(id(part[n][i]))
            i += 1
    place = len(out)
    for n in SOURCES:
        for j, e in enumerate(lists.get(n, ())):
            if id(e) in seen:
                continue
            within = j < caps.get(n, 5)
            if within:
                place += 1
            out.append(dict(e, place=place if within else None))
    return out


def excerpt(text, pos, width=220):
    text = text or ""
    lo = max(0, min(pos - width // 3, len(text) - width))
    s = " ".join(text[lo:lo + width + 40].split())[:width]
    s = ("…" if lo else "") + s + ("…" if lo + width < len(text) else "")
    return s if "no_redact" in MUT else cc_logs.redact(s)


def match_record(q, segs, aside=()):
    """segs: [(role, text)]. -> (per-concept matches or None, set aside?, concepts seen in segs)."""
    best = []
    for con in q["concepts"]:
        got = None
        for si, (role, txt) in enumerate(segs):
            m = match_concept(con, txt, con.get("extra", ()))
            if m and (got is None or m[0] < got[0]):
                got = m + (si,)
                if m[0] == 0:
                    break
        best.append(got)
    seen = {i for i, g in enumerate(best) if g}
    if len(seen) == len(best):
        return best, False, seen
    if aside:
        at = "\n".join(aside)
        side = [g or (lambda m: m and m + (-1,))(match_concept(con, at)) for g, con in zip(best, q["concepts"])]
        if all(side):
            return side, True, seen
    return None, False, seen


# -------------------------------------------------------------------------------------- log records

HARNESS_TYPES = {"last-prompt", "custom-title", "agent-name", "atis-latch", "cost-state", "system",
                 "file-history-delta", "file-history-snapshot"}
CONTENT = ("message", "attachment", "content", "summary", "display", "pastedContents", "error",
           "hookAdditionalContext")
HARNESS_KEYS = CONTENT + ("lastPrompt", "customTitle", "agentName")
KEEP_ATT = {"edited_text_file": "you (edited file)", "queued_command": "you (queued)", "file": "attached file",
            "task_status": "task status", "hook_additional_context": "hook context"}
REMIND = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
TAG = "<system-reminder>"   # REMIND only where it can match: a sub on every text was a large share of a scan
NOISE = ("<task-notification", "<system-reminder", "<local-command", "Caveat:",
         "Another Claude session sent a message", "<cross-session-message", "<agent-message",
         "This session is being continued from a previous conversation")
CMD = re.compile(r"<command-name>(.*?)</command-name>", re.S)
ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SEARCH_RUN = re.compile(r"\b(?:recall|prior_art)\.py\b(?!\s+--selftest)")
SEARCH_OUT = re.compile(r"searching \d+ log\(s\) for:|recall  |SUMMARY  exit")
SKIP_KEYS = {"type", "source", "signature", "id", "tool_use_id", "uuid", "parentUuid", "media_type"}


def _strs(o):
    """Every string in o except ids, block types, signatures and image data."""
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in SKIP_KEYS:
                yield from _strs(v)
    elif isinstance(o, list):
        for v in o:
            if not (isinstance(v, dict) and v.get("type") == "image"):
                yield from _strs(v)


def _join(o):
    return "\n".join(_strs(o))


def typed(rec):
    """What was typed into this record, or None. Tool results carry role=user too; they are not prompts."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return None
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    content = (REMIND.sub("", content) if TAG in content else content).strip()
    if not content or any(s in content[:400] for s in NOISE):
        return None
    m = CMD.search(content)
    if m:
        args = ARGS.search(content)
        return (m.group(1).strip() + " " + (args.group(1).strip() if args else "")).strip()
    return content


def scripted(rec):
    """A prompt a script sent into a desktop session (a pre-review brief, a probe, a bench run): no origin
    and turnOrigin "sdk". Your own turns there carry turnOrigin "human"; older logs carry none."""
    return rec.get("turnOrigin") not in (None, "human")


def _unremind(t):
    """-> (t without its <system-reminder> blocks, the blocks). The app queues a message behind its reminders
    ("Linked sessions now": one peer tag sat at character 1,365 of its queue entry) and delivers it
    as a user turn, whose blocks segments sets aside; a queued copy read whole kept them, and read as you."""
    if TAG not in t or "queued_reminders" in MUT:
        return t, []
    return REMIND.sub("", t), [m.group(0) for m in REMIND.finditer(t)]


def _user_role(t):
    s = _unremind(t)[0].lstrip()[:400]
    # a subagent's hand-back is its final report, like a task notice; its progress notes stay peer messages
    if s.startswith("<task-notification") or re.match(r'<agent-message from="a[0-9a-f]{8,}">\n\[Subagent hand-back\]', s):
        return "agent result"
    if any(k in s for k in ("<cross-session-message", "Another Claude session sent a message", "<agent-message")):
        return "peer message"
    if s.startswith(("<local-command", "Caveat:")):
        return "command output"
    if s.startswith("This session is being continued"):
        return "summary"
    return "you"


def _queued(t):
    r = _user_role(t)
    return "you (queued)" if r == "you" else r


ONCE = ("peer message", "agent result")  # with "you": a queued copy and its delivered copy are one hit


def segments(rec, kind):
    """-> (kept [(role, text)], aside [text]). Metadata (cwd, ids, branch, paths) is in neither."""
    if "meta_counts" in MUT:
        return [("record", "\n".join(cc_logs.strings(rec)))], []
    if kind == "history":
        return [("you (history)", _join([rec.get("display"), rec.get("pastedContents")]))], []
    if kind == "vscode":
        return [("vscode", _join(rec))], []
    t = rec.get("type")
    if t in HARNESS_TYPES or rec.get("isMeta"):
        return [], [_join([rec.get(k) for k in HARNESS_KEYS])]
    if t == "queue-operation":  # the queue also carries peer messages, agent messages and task results
        txt = _join(rec.get("content"))
        if rec.get("operation") == "enqueue" and txt.strip():
            txt, aside = _unremind(txt)    # aside as its delivered copy has them, so the two read and fold alike
            return ([(_queued(txt), txt)] if txt.strip() else []), aside
        return [], [txt]
    if t == "attachment":
        att = rec.get("attachment") or {}
        role = KEEP_ATT.get(att.get("type"))
        txt = _join(att)
        if att.get("type") == "queued_command":
            txt, aside = _unremind(_join(att.get("prompt")))
            return [(_queued(txt), txt)], aside
        return ([(role, txt)], []) if role else ([], [txt])
    if t == "summary":
        return [("summary", _join(rec.get("summary")))], []
    kept, aside = [], []
    if rec.get("toolUseResult") is not None:
        aside.append(_join(rec["toolUseResult"]))
    content = (rec.get("message") or {}).get("content")
    if t == "user" and rec.get("isCompactSummary"):
        return [("summary", _join(content))], aside
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else \
        content if isinstance(content, list) else []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        bt = b.get("type")
        if bt in ("text", "thinking"):
            txt = b.get("text") or b.get("thinking") or ""
            if t == "user":
                if TAG in txt:
                    aside += [m.group(0) for m in REMIND.finditer(txt)]
                    txt = REMIND.sub("", txt)
                if txt.strip():
                    kept.append((_user_role(txt), txt))
            elif txt:
                kept.append(("assistant", txt))
        elif bt == "tool_use":
            inp = json.dumps(b.get("input", {}), ensure_ascii=False)
            run = b.get("name") == "Bash" and SEARCH_RUN.search(inp)
            kept.append(("search run" if run else "tool call", f"{b.get('name', '')} {inp}"))
        elif bt == "tool_result":
            txt = _join(b.get("content"))
            if TAG in txt:
                aside += [m.group(0) for m in REMIND.finditer(txt)]
                txt = REMIND.sub("", txt)
            kept.append(("search run" if SEARCH_OUT.match(txt.lstrip()) else "tool result", txt))
    if not blocks and t not in ("user", "assistant"):
        kept.append((t or "record", _join([rec.get(k) for k in CONTENT])))
    return kept, aside


def _ts(rec):
    t = rec.get("timestamp")
    if isinstance(t, (int, float)) and t > 0:  # history.jsonl: epoch milliseconds
        return datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return t if isinstance(t, str) else ""


def skey(key):
    """The session a log belongs to: a subagent groups under its parent."""
    if re.match(r"[0-9a-f]{8}-", key):
        return key[:36]
    return "history" if key.endswith("history.jsonl") else key


# ----------------------------------------------------------------------------------------- log worker

def _lines(low, pat, d, qi):
    """Add {line start: [line end, {query}]} for every line of low where pat matches."""
    lit, rx = pat
    i, n = 0, len(low)
    while True:
        j = low.find(lit, i)
        if j < 0:
            return
        if rx is not None and not rx.match(low, j):
            i = j + 1
            continue
        s = low.rfind(b"\n", 0, j) + 1
        e = low.find(b"\n", j)
        e = n if e < 0 else e
        got = d.get(s)
        if got:
            got[1].add(qi)
        else:
            d[s] = [e, {qi}]
        i = e + 1


_CACHE = {}


def _compiled(spec):
    if spec not in _CACHE:
        sp = json.loads(spec)
        MUT.clear()
        MUT.update(sp.get("mut", ()))
        _CACHE.clear()
        _CACHE[spec] = (sp, [compile_query(q) for q in sp.get("queries", ())])
    return _CACHE[spec]


def _scan(data, kind, Q, r):
    low = data.lower()
    cand = {}
    for qi, q in enumerate(Q):
        for con in q["concepts"]:
            for a in con["alts"]:
                for pat in a["raw"]:
                    _lines(low, pat, cand, qi)
                if a["near_raw"]:
                    sets = []
                    for word in a["near_raw"]:
                        d = {}
                        for pat in word:
                            _lines(low, pat, d, qi)
                        sets.append(d)
                    for s in set(sets[0]).intersection(*sets[1:]):
                        got = cand.setdefault(s, [sets[0][s][0], set()])
                        got[1].add(qi)
                sm = a.get("some")
                if sm and "no_some_raw" not in MUT:     # a line holding k of the terms' raw forms
                    held, ends = collections.Counter(), {}
                    for sub in sm["subs"]:
                        d = {}
                        for pat in sub["raw"]:
                            _lines(low, pat, d, qi)
                        held.update(d.keys())
                        ends.update((s, v[0]) for s, v in d.items())
                    for s, n in held.items():
                        if n >= sm["k"]:
                            cand.setdefault(s, [ends[s], set()])[1].add(qi)
    del low
    for s in sorted(cand):
        e, qis = cand[s]
        line = data[s:e]
        try:
            rec = json.loads(line)
        except Exception:
            r["bad"] += 1
            continue
        if not isinstance(rec, dict):
            continue
        raw = _ts(rec)
        ts = utc(raw)
        segs, aside = segments(rec, kind)
        sub = kind == "subagent" or bool(rec.get("isSidechain"))
        for qi in sorted(qis):
            q = Q[qi]
            if q.get("since") or q.get("before"):
                if not ts:
                    r["undated"][qi] = r["undated"].get(qi, 0) + 1
                    continue
                if (q.get("since") and ts < q["since"]) or (q.get("before") and ts >= q["before"]):
                    continue
            best, side, seen = match_record(q, segs, aside)
            if seen:
                r["seen"].setdefault(qi, set()).update(seen)
            if best is None:
                if not seen:
                    r["meta"][qi] = r["meta"].get(qi, 0) + 1
                continue
            first = best[0]
            if first[4] >= 0:
                role, txt = segs[first[4]]
            else:
                role, txt = "set aside", "\n".join(aside)
            if kind == "headless":       # a claude -p capture: its prompt came from a script, not from you
                role = "claude -p: prompt" if role.startswith("you") else "claude -p: " + role
            elif role.startswith("you") and scripted(rec):
                role = "script: prompt"
            elif sub:
                role = "agent: task" if role == "you" else "agent: " + role
            # A record with no uuid is named by its line as the index stores it, so a copy read whole and one
            # read through the index fold into one hit.
            rid = rec.get("uuid") or hashlib.sha1((recall_index.canonical(line, "no_redact" not in MUT)
                                                   or (line,))[0]).hexdigest()
            h = {"q": qi, "id": rid, "sid": rec.get("sessionId") or rec.get("session_id") or "", "ts": ts or raw,
                 "role": role,
                 "forms": [b[1] for b in best], "rank": max(b[0] for b in best), "aside": side,
                 "excerpt": excerpt(txt, first[2])}
            if role.startswith("you") or role in ONCE or role == "script: prompt":
                h["typed"] = hashlib.sha1(" ".join(txt.split()).encode("utf-8", "replace")).hexdigest()[:16]
            h["alts"] = _which(q, [t for _, t in segs] or [txt])
            r["hits"].append(h)


def _command(rec, name):
    """The command line if rec is the user's own /name command, else None. The harness writes one as the
    whole message, opening with its tags. Tool results, compaction summaries, skill expansions, subagent
    records and pasted excerpts can quote the tags too, and counting those inflates the invocations
    several times over. A record with <skill-format> is a load Claude Code made (_autoload)."""
    t = typed(rec)
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if t is None or rec.get("isSidechain") or scripted(rec) or not isinstance(content, str) or \
            "<skill-format>" in content or \
            not REMIND.sub("", content).lstrip().startswith(("<command-message>", "<command-name>")):
        return None
    return t if re.match(r"/?%s(?:\s|$)" % re.escape(name), t) else None


# Claude Code's own record for a skill it loads rather than one typed.
SKILL_LOAD = "<command-message>%s</command-message>\n<command-name>%s</command-name>\n<skill-format>true</skill-format>"
AUTOLOAD = {"ultra_effort_enter": "ultra effort", "workflow_keyword_request": "workflow keyword"}


def _record(data, uid):
    """The record in data whose uuid is uid, or None."""
    for m in re.finditer(rb'"uuid":\s*"%s"' % re.escape(uid.encode()), data):
        e = data.find(b"\n", m.end())
        try:
            p = json.loads(data[data.rfind(b"\n", 0, m.start()) + 1: e if e >= 0 else len(data)])
        except Exception:
            continue
        if isinstance(p, dict) and p.get("uuid") == uid:
            return p
    return None


def _autoload(data, rec, name):
    """'autoload (<trigger>)' if rec is Claude Code loading skill `name` by itself, else None. It writes
    SKILL_LOAD for its bundled workflow-authoring when a prompt enters ultra effort or names a workflow,
    and for a skill the model calls. That one counts as its Skill call, so a Skill call up the parent chain makes it None."""
    content = (rec.get("message") or {}).get("content")
    if rec.get("isSidechain") or not isinstance(content, str) or \
            REMIND.sub("", content).strip() != SKILL_LOAD % (name, name):
        return None
    why, uid = "", rec.get("parentUuid")
    for _ in range(6):
        p = _record(data, uid) if uid else None
        if p is None:
            break
        c = (p.get("message") or {}).get("content")
        if p.get("type") == "assistant" and isinstance(c, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill" for b in c):
            return None
        if p.get("type") == "attachment":
            why = why or AUTOLOAD.get((p.get("attachment") or {}).get("type"), "")
        elif typed(p) is not None:
            break
        uid = p.get("parentUuid")
    return "autoload" + (f" ({why})" if why else "")


def _last_scan(data, kind, name, r):
    d = {}
    _lines(data.lower(), (name.lower().encode(), None), d, 0)
    want = re.compile(r"<command-name>/?%s</command-name>" % re.escape(name))
    for s in sorted(d):
        try:
            rec = json.loads(data[s:d[s][0]])
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        ts, how = _ts(rec), None
        m = rec.get("message")
        content = m.get("content") if isinstance(m, dict) else None     # a denied tool call writes a string
        if kind == "history":
            disp = rec.get("display") or ""
            if re.match(r"/%s(?:\s|$)" % re.escape(name), disp):
                how = disp
        elif kind not in ("subagent", "headless") and rec.get("type") == "user" and want.search(json.dumps(content)):
            how = _command(rec, name)
            auto = None if how else _autoload(data, rec, name)
            if auto and ts:
                r["auto"].append((ts, auto))
        elif rec.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                inp = b.get("input")
                sk = str(inp.get("skill", "")) if isinstance(inp, dict) else ""
                if b.get("type") == "tool_use" and b.get("name") == "Skill" and sk.split(":")[-1] == name:
                    how = "Skill tool, args: " + str((b.get("input") or {}).get("args", ""))
            if how and ts and (kind in ("subagent", "headless") or rec.get("isSidechain")):  # listed apart, not counted
                r["sub"].append((ts, ("claude -p " if kind == "headless" else "subagent ") + how))
                how = None
        if how and ts:
            r["calls"].append((ts, how))


SCAN_STOPPED = "scan stopped partway: "   # a record the scan did not expect names its copy; it never ends the run


def _result(c, lines=0, error=None):
    """A copy's result, as work() and work_index() fill it."""
    return {"key": c.key, "kind": c.kind, "via": c.via, "where": cc_logs.where(c.path), "label": c.label(),
            "live": os.sep + ".claude" + os.sep in c.path,
            "path": c.path, "size": c.size, "lines": lines, "error": error, "hits": [], "seen": {}, "undated": {},
            "meta": {}, "bad": 0, "calls": [], "auto": [], "sub": []}


def work(spec, copies):
    """Process-pool entry point. copies: plain tuples of cc_logs.Copy fields. One result per copy."""
    sp, Q = _compiled(spec)
    out, zfs, outer = [], {}, {}
    try:
        for t in copies:
            c = cc_logs.Copy(*t)
            r = _result(c)
            try:
                if c.via == "disk":
                    with open(c.path, "rb") as fh:
                        data = fh.read()
                else:
                    if c.path not in zfs:
                        zfs[c.path] = zipfile.ZipFile(c.path)
                    if c.via == "zip":
                        data = zfs[c.path].read(c.member)
                    else:
                        k = (c.path, c.member)
                        if k not in outer:
                            outer.clear()
                            outer[k] = zfs[c.path].read(c.member)
                        with zipfile.ZipFile(io.BytesIO(outer[k])) as inner:
                            data = inner.read(c.inner)
            except FileNotFoundError:                    # gone since the inventory listed it
                r["error"] = cc_logs.VANISHED
                out.append(r)
                continue
            except Exception as e:
                r["error"] = f"{type(e).__name__}: {e}"[:200]
                out.append(r)
                continue
            r["lines"] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
            try:
                if sp.get("mode") == "last":
                    _last_scan(data, c.kind, sp["name"], r)
                else:
                    _scan(data, c.kind, Q, r)
            except Exception as e:  # a record the scan did not expect: name this copy and read the rest
                r["error"] = f"{SCAN_STOPPED}{type(e).__name__}: {e}"[:200]
            out.append(r)
    finally:
        for z in zfs.values():
            z.close()
    return out


# ------------------------------------------------------------------------------------------ log source

def _tasks(copies, size=64 << 20):
    """Copies grouped by file, about 64 MB a task, largest first."""
    by = collections.defaultdict(list)
    for c in copies:
        by[c.path].append(c)
    tasks, small, acc = [], [], 0
    for path, cs in by.items():
        cs.sort(key=lambda c: (c.member or "", c.inner or ""))
        cur, n = [], 0
        for c in cs:
            if cur and n + c.size > size:
                tasks.append(cur)
                cur, n = [], 0
            cur.append(c)
            n += c.size
        if n >= size or cs[0].via != "disk":
            tasks.append(cur)
        else:
            small += cur
    small.sort(key=lambda c: c.path)
    cur = []
    for c in small:
        if cur and acc + c.size > size:
            tasks.append(cur)
            cur, acc = [], 0
        cur.append(c)
        acc += c.size
    if cur:
        tasks.append(cur)
    tasks.sort(key=lambda t: -sum(c.size for c in t))
    return [[tuple(c) for c in t] for t in tasks]


# Why no process pool can start here, once one has failed to; None until then. A sandbox can deny the
# semaphores multiprocessing needs (os.sysconf("SC_SEM_NSEMS_MAX") raises PermissionError), and some platforms
# have no sem_open. After the first failure no pool is tried again: the work runs in this process, with the
# same results.
NO_POOL = None
POOL_ERRORS = (PermissionError, OSError, NotImplementedError, ImportError)


def _start_pool(size):
    """A spawn pool of size workers, started; or None when a pool can't start here. The first failure prints
    one line on stderr naming why and sets NO_POOL; the caller then runs the work in this process."""
    global NO_POOL
    if NO_POOL is not None:
        return None
    ex = None
    try:
        import multiprocessing
        ex = ProcessPoolExecutor(size, mp_context=multiprocessing.get_context("spawn"))
        for _ in range(size):
            ex.submit(os.getpid)
        return ex
    except POOL_ERRORS as e:
        if "no_pool_fallback" in MUT:
            raise
        if ex is not None:
            ex.shutdown(wait=False, cancel_futures=True)
        NO_POOL = _why(e)
        print(f"recall: ran without the process pool, in this process ({NO_POOL}); same results, slower",
              file=sys.stderr)
        return None


def _map(fn, spec, tasks, ex=None):
    """fn over tasks in ex, the pool search() started, else in a pool of CONFIG["workers"] made for it, else,
    when no pool can start (_start_pool), in this process."""
    if ex is not None:
        return [r for rs in ex.map(fn, [spec] * len(tasks), tasks) for r in rs]
    ex = _start_pool(CONFIG["workers"])
    if ex is None:
        return [r for t in tasks for r in fn(spec, t)]
    with ex:
        return [r for rs in ex.map(fn, [spec] * len(tasks), tasks) for r in rs]


def _pool(spec, copies, serial=False, ex=None):
    tasks = _tasks(copies)
    if serial or CONFIG["workers"] <= 1 or len(tasks) <= 1:
        return [r for t in tasks for r in work(spec, t)]
    return _map(work, spec, tasks, ex)


def _inventory(opts, seals=None):
    """-> (inventory, the copies to read, (what each seal held back, its logs patterns that matched nothing))."""
    early, opts.inventory = getattr(opts, "inventory", None), None   # search() started it; used once
    inv = early.result() if early else cc_logs.Inventory(CONFIG["root"], refresh=getattr(opts, "refresh", False),
                                                         cache=CONFIG["cache"])
    copies = inv.to_read()
    if "no_zip" in MUT:
        copies = [c for c in copies if c.via == "disk"]
    copies, held, nomatch = _seal_logs(inv, copies, seals or [])
    return inv, copies, (held, nomatch)


def _prefer(h):
    # The label last, so two copies that tie fold to the same one however the copies were read.
    return (0 if h["key"][:36] == h["sid"] else 1, 0 if h["via"] == "disk" else 1, 0 if h.get("live") else 1,
            h.get("label", ""))


UUID_B, TS_B = re.compile(rb'"uuid":\s*"([^"]+)"'), re.compile(rb'"timestamp":\s*"([^"]+)"')
_RECORDS = {}


def _records(inv, h):
    """{uuid: time} of every record in the copy hit h came from, read once per run."""
    k = (h["key"], h.get("label", ""))
    if k not in _RECORDS:
        out = {}
        c = next((c for c in inv.logs.get(h["key"], ()) if c.label() == h.get("label")), None)
        try:
            with c.open() as fh:
                for line in fh:
                    u, ts = UUID_B.search(line), TS_B.search(line)
                    if u:
                        out[u.group(1).decode()] = ts.group(1).decode() if ts else ""
        except Exception:  # noqa: BLE001 -- a copy that can't be read has no records of its own to weigh
            pass
        _RECORDS[k] = out
    return _RECORDS[k]


def _times(inv, h):
    """The record times of the copy hit h came from: what a copy keeps even when it rewrites the ids."""
    return set(_records(inv, h).values()) - {""}


def _origin(hs, inv):
    """Of the hits holding one record, the one to print. Copies within one session fold by _prefer. When
    sessions differ (the app's continuation, or a fork, rewrites sessionId and keeps each record's uuid and
    time; an older resume rewrote the uuid too), it goes to the session whose own records, those no other
    session here holds, start first. Records are told apart by time, which every kind of copy keeps. A pure
    copy has none of its own, so it never takes the record; with none on either side, _prefer decides. The
    whole log is weighed, not only what precedes a --before cut: the cut decides which records print, not
    whose they are, and a fork copied before the cut has no own record there either."""
    by = collections.defaultdict(list)
    for h in hs:
        by[skey(h["key"])].append(h)
    if len(by) < 2 or "no_origin" in MUT:
        return min(hs, key=_prefer)
    times = {s: _times(inv, min(v, key=_prefer)) for s, v in by.items()}
    start = {}
    for s, t in times.items():
        others = set().union(*(x for o, x in times.items() if o != s))
        own = [ts for ts in t if ts not in others]
        start[s] = min(own) if own else None
    have = [s for s in by if start[s]]
    return min(by[min(have, key=lambda s: start[s])] if have else hs, key=_prefer)


COPY_MIN = 2        # record times two sessions share before a same-time, same-role, same-text record is one


def _merge_copies(groups, inv):
    """Groups of hits, one per record id, joined where a copy rewrote the ids: an older resume copied a
    session's past into a new log under new uuids, keeping each record's time, role and text. Two groups join
    when those match in different sessions that share at least COPY_MIN record times; a resumed pair shares
    many, and no id. One message that reached two sessions at the same instant shares one time, so it stays
    apart, as does a record with the same time and other text."""
    if "no_rewrite" in MUT:
        return groups
    by = collections.defaultdict(list)
    for i, g in enumerate(groups):
        h = g[0]
        if h["ts"]:
            text = "" if "copy_any_text" in MUT else hashlib.sha1((h.get("excerpt") or "").encode()).hexdigest()
            by[(h["ts"], h.get("role", ""), text)].append(i)
    parent = list(range(len(groups)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    shared = {}
    for ids in by.values():
        if len(ids) < 2:
            continue
        for a in ids:
            for b in ids:
                sa, sb = skey(groups[a][0]["key"]), skey(groups[b][0]["key"])
                if a >= b or sa == sb:
                    continue
                k = tuple(sorted((sa, sb)))
                if k not in shared:
                    ta = _times(inv, min(groups[a], key=_prefer))
                    tb = _times(inv, min(groups[b], key=_prefer))
                    shared[k] = len(ta & tb) >= (1 if "copy_one_time" in MUT else COPY_MIN)
                if shared[k]:
                    parent[find(a)] = find(b)
    out = collections.defaultdict(list)
    for i, g in enumerate(groups):
        out[find(i)] += g
    return list(out.values())


def _fold(hits, inv):
    """One hit per record, and with it, as "also", any other session that holds the record: a copy that kept
    the record's id, or one that rewrote it (_merge_copies)."""
    groups = collections.defaultdict(list)
    for h in hits:
        groups[h["id"]].append(h)
    out = []
    for hs in _merge_copies(list(groups.values()), inv):
        pick = hs[0] if len(hs) == 1 else _origin(hs, inv)
        also = sorted({skey(h["key"]) for h in hs} - {skey(pick["key"])})
        out.append(dict(pick, also=also) if also else pick)
    return out


def _drop_repeats(hits):
    """One hit per text typed, peer message or agent result in a session: a queued copy and its delivered copy
    read alike. The repeat dropped hands its "also" to the hit kept, so a session that holds only the repeat is
    still named."""
    seen, keep = {}, []
    for h in sorted(hits, key=lambda h: h["ts"] or ""):
        k = (skey(h["key"]), h.get("typed"))
        if h.get("typed") and k in seen:
            kept = seen[k]
            if h["role"] == "script: prompt":     # its queued copy reads as typed; the delivered one knows
                kept["role"] = h["role"]
            more = set(h.get("also") or ()) - set(kept.get("also") or ()) - {k[0]}
            if more and "no_also_keep" not in MUT:
                kept["also"] = sorted(set(kept.get("also") or ()) | more)
            continue
        seen[k] = h
        keep.append(h)
    return keep


def _gaps(inv, failed):
    """One line per part of the logs not read: a copy that failed to open, a file gone since the walk
    (once, however many copies it held), a zip not read, a folder not searched or not opened."""
    gone = collections.Counter(r["path"] for r in failed if r["error"] == cc_logs.VANISHED)
    unread = inv.did_not_read + [(p, f"{cc_logs.VANISHED}; {n} cop{'y' if n == 1 else 'ies'} not read")
                                 for p, n in gone.items()]
    return ([f"copy {'not fully read' if r['error'].startswith(SCAN_STOPPED) else 'failed to open'}: {r['label']}: "
             f"{r['error'].removeprefix(SCAN_STOPPED)}" for r in failed if r["path"] not in gone]
            + [f"{'zip' if p.lower().endswith('.zip') else 'log'} DID NOT READ: {p.replace(HOME, '~')}: {why}"
               for p, why in unread]
            + [f"folder {d.replace(HOME, '~')}" for d in inv.not_searched]
            + [f"folder could not be opened: {d.removeprefix('find: ').replace(HOME, '~')}" for d in inv.not_opened])


# The words after which redact rewrites the value that follows (cc_logs.SECRET_CTX): text there is not in
# the index, so an alternative holding one is read whole.
CTX_KEY = re.compile("(?i)" + re.search(r"\(\?:[^)]*\)", cc_logs.SECRET_CTX.pattern).group(0))
INDEX_BLIND = ("logs: through the index, text inside a string redaction rewrote is not found: a word of 32+ "
               "characters such as a long mcp__ tool name, a long base64-like run, a token; --scan reads every copy "
               "whole")


def _index_expr(q):
    """(the FTS lookup that returns every record q can match in, "") or (None, why the index cannot answer
    q). Every concept goes in, ORed, so a record holding one concept is read too, as the scan reads it."""
    out = []
    for con in q["concepts"]:
        for a in con["alts"]:
            t = a["text"]
            if len(t) > recall_index.MAX_ALT:
                return None, f"{t[:40]!r}... is longer than {recall_index.MAX_ALT} characters"
            if '"' in t or "\\" in t:
                return None, f"{t!r} holds a quote or a backslash, which a log writes escaped"
            if cc_logs.redact(t) != t or CTX_KEY.search(t):
                return None, f"{t!r} is text redaction rewrites, and the index holds redacted text only"
            exprs = [recall_index.all_of(s) for s in _alt_sets(a)]   # exact and variant, then near (_alt)
            if exprs[0] is None:
                return None, f"{t!r} has no run of 3 characters to look up"
            out += [e for e in exprs if e]
            if a.get("some") and "no_some_index" not in MUT:
                out.append(_some_expr(a["some"]))
    return (" OR ".join(dict.fromkeys(out)), "") if out else (None, "no concept to look up")


def _some_expr(s):
    """The FTS lookup for the records where k of a some alternative's n terms can sit together: each group of k
    terms all in one row, ORed; at most C(8, 4) = 70 groups (SOME_MAX). A some match spans at most 2 * NEAR and a
    term, under the overlap of two rows, so its terms share one."""
    each = [recall_index.all_of(_alt_sets(sub)[0]) for sub in s["subs"]]   # each term can be looked up (_some_terms)
    return "(" + " OR ".join("(" + " AND ".join(g) + ")" for g in itertools.combinations(each, s["k"])) + ")"


def _spec(plain, keep=None):
    """The scan's spec for the queries in plain, the ones not in keep blanked (no concept, so no hit)."""
    qs = [p if keep is None or i in keep else {"labels": [], "since": None, "before": None} for i, p in enumerate(plain)]
    return json.dumps({"mode": "search", "mut": sorted(MUT), "queries": qs})


def _merge(results):
    """One result per copy: a copy can be read through the index for some queries and whole for others."""
    by = {}
    for r in results:
        m = by.setdefault(r["label"], r)
        if m is r:
            continue
        m["hits"] += r["hits"]
        for qi, s in r["seen"].items():
            m["seen"].setdefault(qi, set()).update(s)
        for f in ("undated", "meta"):
            for qi, n in r[f].items():
                m[f][qi] = m[f].get(qi, 0) + n
        m["bad"] += r["bad"]
        m["lines"] = max(m["lines"], r["lines"])
        m["error"] = m["error"] or r["error"]
    return list(by.values())


def work_index(spec, items):
    """Process-pool entry point for copies read through the index. items: (cc_logs.Copy fields, its line
    count, its candidate records compressed, in log order). One result per copy, as work() makes."""
    _, Q = _compiled(spec)
    out = []
    for t, n, zs in items:
        c = cc_logs.Copy(*t)
        r = _result(c, n)
        if zs:
            try:
                _scan(b"\n".join(zlib.decompress(z) for z in zs), c.kind, Q, r)
            except Exception as e:   # as in work(): name this copy and read the rest
                r["error"] = f"{SCAN_STOPPED}{type(e).__name__}: {e}"[:200]
        out.append(r)
    return out


def _pool_index(spec, items, serial=False, size=8 << 20, ex=None):
    """work_index over items: in this process for a few candidates, else in the pool, about 8 MB a task."""
    total = sum(len(z) for _, _, zs in items for z in zs)
    if serial or CONFIG["workers"] <= 1 or total <= 2 * size:
        return work_index(spec, items)
    tasks, cur, n = [], [], 0
    for it in sorted(items, key=lambda it: -sum(len(z) for z in it[2])):
        cur.append(it)
        n += sum(len(z) for z in it[2])
        if n >= size:
            tasks.append(cur)
            cur, n = [], 0
    if cur:
        tasks.append(cur)
    return _map(work_index, spec, tasks, ex)


def _logs_index(queries, plain, copies, inv, seals, opts):
    """The queries the index answers, read through it. -> (results of the copies read through it, the copies
    those queries still read whole, the query numbers answered, {qi or "all": COVERAGE lines}). A sealed log
    is never written to the index, lifted seals included, and one a newer seal holds is deleted from it."""
    path = CONFIG.get("index")
    notes = collections.defaultdict(list)
    if not path:
        return [], [], set(), notes
    if getattr(opts, "scan", False):
        notes["all"].append("logs: --scan: every copy read whole, not through the index")
        return [], [], set(), notes
    exprs = {}
    for qi, q in enumerate(queries):
        e, why = _index_expr(q)
        if e:
            exprs[qi] = e
        else:
            notes[qi].append(f"logs: every copy read whole, not through the index: {why}")
    if not exprs:
        return [], [], set(), notes
    t0, short = time.time(), path.replace(HOME, "~")
    lock = recall_index.Lock(path)
    try:
        conn = recall_index.connect(path)
    except recall_index.Unusable as e:
        moved = ""
        if lock.try_acquire():   # a cache: set it aside and build it again, unless a writer has it open
            try:
                for ext in ("", "-wal", "-shm"):
                    if os.path.exists(path + ext):
                        os.replace(path + ext, path + ".corrupt" + ext)
                moved = f"; moved to {short}.corrupt, and a new one is built"
            finally:
                lock.release()
            if CONFIG.get("index_spawn"):
                recall_index.spawn_update(path)
        notes["all"].append(f"logs: the index {short} could not be read, so every copy was read whole: "
                            f"{_why(e)}{moved}")
        return [], [], set(), notes
    try:
        held, held_keys = recall_index.sealed_keys(inv, conn, seals)
        if "index_writes_sealed" in MUT:   # selftest: the rule broken on purpose
            held, held_keys = [], set()
        indexable = {recall_index.ident(c) for c in sealing.hold_logs(inv, copies, held)[0]}   # never a sealed log
        todo = [c for c in copies if recall_index.ident(c) in indexable]
        wrote, st = lock.try_acquire(), None
        try:
            if wrote:
                recall_index.purge(conn, held_keys)
                status, st = recall_index.sync(conn, todo, CONFIG["index_budget"], "no_redact" not in MUT,
                                               1 if getattr(opts, "serial", False) or NO_POOL else CONFIG["workers"])
            else:   # another run is writing it: what it holds now is used, the rest is read whole
                status, waiting = recall_index.plan(conn, todo)
                status.update({recall_index.ident(w[0]): ("pending", None) for w in waiting})
        finally:
            lock.release()
        conn.execute("begin")   # one snapshot for the copies and their records
        have = recall_index.rows(conn)
        results, direct, ok = [], [], {}
        for c in copies:
            k = recall_index.ident(c)
            s = status.get(k, ("sealed", None))
            if s[0] == "error":
                results.append(_result(c, error=s[1]))
            elif s[0] == "ok" and k in have:
                ok[have[k]["id"]] = (c, have[k])
            else:
                direct.append(c)
        got, nrec = recall_index.lookup(conn, list(exprs.values()), set(ok), path,
                                        1 if getattr(opts, "serial", False) else 8)
        conn.execute("commit")
        items = [(tuple(c), row["lines"], [z for _, z in got.get(cid, ())]) for cid, (c, row) in ok.items()]
        results += _pool_index(_spec(plain, set(exprs)), items, getattr(opts, "serial", False), ex=getattr(opts, "pool", None))
    except sqlite3.DatabaseError as e:
        notes["all"].append(f"logs: the index {short} failed partway, so every copy was read whole: {_why(e)}")
        return [], [], set(), notes
    finally:
        conn.close()
    waiting = [c for c in direct if status.get(recall_index.ident(c), ("",))[0] == "pending"]
    spawned = bool(waiting) and CONFIG.get("index_spawn") and recall_index.spawn_update(path)
    line = (f"logs: index {short}: {len(ok)} of {len(copies)} copies read through it, {nrec:,} candidate records"
            + (f"; {st['copies']} brought up to date ({st['bytes'] / 1e6:.0f} MB) in {st['seconds']:.1f}s" if st else
               "; another run was updating it")
            + (f"; {len(waiting)} not yet indexed ({sum(c.size for c in waiting) / 1e9:.2f} GB) read whole"
               + (", and a background update is catching up" if spawned else "") if waiting else "")
            + (f"; {len(direct) - len(waiting)} sealed cop{'y' if len(direct) - len(waiting) == 1 else 'ies'}"
               f" read whole, never indexed" if len(direct) > len(waiting) else "")
            + f"; {time.time() - t0:.1f}s")
    for qi in exprs:
        notes[qi] += [line, INDEX_BLIND]
    return results, direct, set(exprs), notes


def src_logs(queries, opts):
    t0 = time.time()
    seals = _seals(opts)
    inv, copies, (held, nomatch) = _inventory(opts, seals)
    lifted = {s["dir"] for s in seals if s["state"] == "lifted"}
    kept_out = sum(h.get("log copies", 0) for d, h in held.items() if d not in lifted)
    plain = [{k: q.get(k) for k in ("labels", "since", "before", "some")} for q in queries]
    serial, pool = getattr(opts, "serial", False), getattr(opts, "pool", None)
    via_index, direct, answered, notes = _logs_index(queries, plain, copies, inv, seals, opts)
    if answered:
        rest = set(range(len(queries))) - answered
        read = {r["label"] for r in via_index if not r["error"]}
        results = _merge(via_index + (_pool(_spec(plain), direct, serial, pool) if direct else [])
                         + (_pool(_spec(plain, rest), [c for c in copies if c.label() in read], serial, pool)
                            if rest else []))
    else:
        results = _pool(_spec(plain), copies, serial, pool)
    lines = sum(r["lines"] for r in results)
    failed = [r for r in results if r["error"]]
    partial = _gaps(inv, failed)
    base_cov = inv.coverage()
    me = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    out = []
    for qi, q in enumerate(queries):
        hits, seen = [], collections.defaultdict(set)
        undated = meta = 0
        for r in results:
            for h in r["hits"]:
                if h["q"] == qi:
                    hits.append(dict(h, key=r["key"], via=r["via"], where=r["where"], label=r["label"], kind=r["kind"],
                                     live=r["live"]))
            seen_q = r["seen"].get(qi)
            if seen_q:
                seen[skey(r["key"])] |= seen_q
            undated += r["undated"].get(qi, 0)
            meta += r["meta"].get(qi, 0)
        before_dedup = len(hits)
        if "no_dedup" not in MUT:
            hits = _drop_repeats(_fold(hits, inv))
        main = [h for h in hits if not h["aside"]]
        aside = [h for h in hits if h["aside"]]
        with_hits = {skey(h["key"]) for h in main}
        n = len(q["concepts"])
        split = sorted(s for s, cs in seen.items() if len(cs) == n and n > 1 and s not in with_hits)
        cov = [f"logs: {ln}" for ln in base_cov]
        cov.append(f"logs: scanned {len(copies) - len(failed)} of {len(copies)} copies, "
                   f"{sum(c.size for c in copies) / 1e9:.2f} GB, {lines:,} lines, in {time.time() - t0:.0f}s; "
                   f"{before_dedup - len(hits)} duplicate records (copies of one record) folded"
                   + (f"; {kept_out} sealed cop{'y' if kept_out == 1 else 'ies'} not read (the seal line above)"
                      if kept_out else ""))
        cov += notes["all"] + notes[qi]
        shared = sum(1 for h in hits if h.get("also"))
        if shared:
            cov.append(f"logs: {shared} record(s) held by more than one session (a continuation, a fork or a resume "
                       "copies them, the last under new ids) print once, under the session whose own records "
                       "start first; its header names the others (also in)")
        if meta:
            cov.append(f"logs: {meta} line(s) matched only in metadata (cwd, paths, ids) and are not hits")
        if undated:
            cov.append(f"logs: {undated} undated record(s) left out by the date window")
        out.append({"ran": True, "why": "", "cov": cov, "hits": main, "aside": aside, "split": split,
                    "partial": list(partial), "me": me, "inv": inv, "sealed": held, "nomatch": nomatch})
    return out


def _title(inv, sid):
    """Custom title, else the first prompt typed in the session's main log."""
    copies = sorted((c for c in inv.logs.get(f"{sid}.jsonl", []) if c.path not in inv.cloud),   # a placeholder downloads
                    key=lambda c: (cc_logs.PREFER[c.via], c.path))
    if not copies:
        return ""
    try:
        with copies[0].open() as fh:
            data = fh.read()
    except Exception:
        return ""
    i = data.rfind(b'"type":"custom-title"')
    if i >= 0:
        s, e = data.rfind(b"\n", 0, i) + 1, data.find(b"\n", i)
        try:
            t = json.loads(data[s:e if e >= 0 else len(data)]).get("customTitle")
            if t:
                return t
        except Exception:
            pass
    for line in data.split(b"\n"):
        if b'"type":"user"' in line:
            try:
                p = typed(json.loads(line))
            except Exception:
                continue
            if p and not p.startswith("/model"):
                return p
    return ""


# ---------------------------------------------------------------------------------------- other sources

def _why(e):
    if isinstance(e, SystemExit):
        return cc_logs.redact(str(e.code)).splitlines()[0][:200] if e.code else "exited"
    return cc_logs.redact(f"{type(e).__name__}: {e}").splitlines()[0][:200]


def _dnr(why, n):
    return [{"ran": False, "why": why, "cov": [], "hits": [], "partial": []} for _ in range(n)]


def _paragraphs(text, by_line=False):
    """[(first line number, text)]: blank-line paragraphs, or single lines for JSON."""
    if by_line:
        return [(i, ln) for i, ln in enumerate(text.splitlines(), 1) if ln.strip()]
    out, buf, start = [], [], 1
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.strip():
            if not buf:
                start = i
            buf.append(ln)
        elif buf:
            out.append((start, "\n".join(buf)))
            buf = []
    if buf:
        out.append((start, "\n".join(buf)))
    return out


def _in_window(q, ts):
    """Whether ts is in the query's window, compared in UTC; q's since and before already are."""
    if not (q.get("since") or q.get("before")):
        return True
    ts = utc(ts)
    if not ts:
        return False
    return not ((q.get("since") and ts < q["since"]) or (q.get("before") and ts >= q["before"]))


# Comment fields, read here so the figma source needs only figma_comments.fetch (and, for offset pins,
# figma_comments.ancestry) from the module beside this file.

def _fflat(c):
    return re.sub(r"\s+", " ", c.get("message", "")).strip()


def _fnode(c):
    return ((c.get("client_meta") or {}).get("node_id")) or ""


def _fstate(c):
    return f"RESOLVED {c['resolved_at'][:10]}" if c.get("resolved_at") else "OPEN"


def _fhandle(c):
    return (c.get("user") or {}).get("handle", "?")


def _flink(key, kind, name, c):
    """The link that opens the THREAD, not just its frame: ...?node-id=<node, dashed>#<root id>."""
    node = _fnode(c).replace(":", "-")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name or "File").strip("-") or "File"
    return (f"https://www.figma.com/{'board' if kind == 'board' else 'design'}/{key}/{slug}"
            + (f"?node-id={node}" if node else "") + f"#{c['id']}")


def _how_on(c, path):
    """"direct" if c is pinned to the node at the end of path ([(id, absoluteBoundingBox)] from the page
    down), "offset on <id>" if it is pinned to an ancestor with node_offset inside the node's box, else None.
    A comment re-pinned to a parent frame keeps its offset from that frame's top-left."""
    m = c.get("client_meta") or {}
    pin = (m.get("node_id") or "").replace("-", ":")
    nid, box = path[-1]
    if pin == nid:
        return "direct"
    off = m.get("node_offset")
    if not pin or not off or not box:
        return None
    for aid, abox in path[:-1]:
        if aid == pin and abox:
            x, y = abox["x"] + off.get("x", 0), abox["y"] + off.get("y", 0)
            if box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]:
                return f"offset on {pin}"
    return None


def _figma_token():
    if CONFIG["figma_token"] is not None:
        return CONFIG["figma_token"]
    return kit_config.token("FIGMA_TOKEN")


def src_figma(queries, opts):
    files = figma_files()
    if not _figma_token():
        return _dnr("no FIGMA_TOKEN in the environment or the keychain (kit_config.token), though figma.files "
                     "is set", len(queries))
    import figma_comments as fc
    data, cov, partial = {}, [], []
    keys = list(files)
    with ThreadPoolExecutor(len(keys) or 1) as ex:   # one round trip each, at once, not one after another
        futs = [ex.submit(fc.fetch, key) for key in keys]
    for key, f in zip(keys, futs):
        kind, name = files[key]
        try:
            data[key] = f.result()
        except BaseException as e:  # a fetch may sys.exit on an HTTP error or a missing token
            if isinstance(e, KeyboardInterrupt):
                raise
            partial.append(f"figma {name} ({key}) DID NOT RUN: {_why(e)}")
    if not data:
        return [{"ran": False, "why": "; ".join(partial), "cov": [], "hits": [], "partial": []} for _ in queries]
    nodes = sorted({a["text"] for q in queries for c in q["concepts"] for a in c["alts"] if a["kind"] == "node"})
    paths = {}
    for key, cs in data.items():
        roots = [c for c in cs if not c.get("parent_id")]
        cov.append(f"figma: {files[key][1]} ({key}): {len(cs)} comments in {len(roots)} threads, "
                   f"{sum(1 for r in roots if r.get('resolved_at'))} resolved, all read")
        if nodes:
            if not hasattr(fc, "ancestry"):
                partial.append(f"figma {key}: figma_comments has no ancestry(); offset pins not checked")
                continue
            try:
                paths[key] = fc.ancestry(key, nodes)
            except BaseException as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                partial.append(f"figma {key}: node ancestry DID NOT RUN ({_why(e)}); offset pins not checked")
    # The words on each canvas (SOURCES above). A design file's index is read as cached: rebuilding a large
    # design file takes minutes and gigabytes. A board's is rebuilt once a day old (CONFIG figma_canvas).
    canvas = {}
    import figma_family
    for key in data:
        kind, name = files[key]
        mode = CONFIG["figma_canvas"] if kind == "board" else "cache"
        try:
            ix, note = figma_family.load(key, mode=mode)
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            ix, note = None, _why(e)
        if ix is not None and ix.text:
            canvas[key] = ix
            pages = {ix.idx[n][figma_family.PAGE] for n in ix.text if n in ix.idx}
            cov.append(f"figma canvas: {name} ({key}): {len(ix.text):,} text layers on {len(pages)} pages, index "
                       f"{ix.age_h():.0f} h old" + (f" ({note})" if note else "") + "; hidden layers skipped; the "
                       "file as it is now, so --since and --before do not apply")
        elif kind == "board":
            partial.append(f"figma canvas {name} ({key}) DID NOT RUN: "
                           + (note or "its index holds no text; python tools/figma_family.py build " + key))
        else:
            cov.append(f"figma canvas: {name} ({key}) not searched: "
                       + (note or "its cached index predates text, which the next figma_family.py build adds"))
    out = []
    for q in queries:
        hits = []
        for key, ix in canvas.items():
            kind, name = files[key]
            slug = re.sub(r"[^A-Za-z0-9]+", "-", name or "File").strip("-") or "File"
            for nid, words in ix.text.items():
                v = ix.idx.get(nid)
                if not v or v[figma_family.HID]:
                    continue
                flat = " ".join(words.split())
                best = [match_concept(con, flat) for con in q["concepts"]]
                if all(best):
                    where = " > ".join(ix.idx[c][figma_family.NAME].strip()[:50] for c in ix.chain(nid)[:-1]
                                       if ix.idx[c][figma_family.T] in ("CANVAS", "SECTION"))
                    # A table cell's id, T<table>;<row>;<column>, opens nothing in a link; link its table.
                    at = nid.split(";")[0][1:] if nid.startswith("T") else nid
                    hits.append({"ts": "", "form": "/".join(sorted({b[1] for b in best})), "alts": _which(q, [flat]),
                                 "rank": max(b[0] for b in best), "open": False, "canvas": True,
                                 "head": f"canvas  {where}  https://www.figma.com/{'board' if kind == 'board' else 'design'}"
                                         f"/{key}/{slug}?node-id={at.replace(':', '-')}",
                                 "excerpt": excerpt(flat, best[0][2], 200), "ids": [f"figma:{nid}"]})
        for key, cs in data.items():
            roots = {c["id"]: c for c in cs if not c.get("parent_id")}
            kids = collections.defaultdict(list)
            for c in cs:
                if c.get("parent_id"):
                    kids[c["parent_id"]].append(c)
            for rid, r in roots.items():
                thread = [c for c in [r] + sorted(kids.get(rid, []), key=lambda c: c.get("created_at", ""))
                          if not q.get("before") or utc(c.get("created_at", "")) < q["before"]]
                if not thread or thread[0] is not r:
                    continue
                if q.get("since") and max(utc(c.get("created_at", "")) for c in thread) < q["since"]:
                    continue
                best = []
                for con in q["concepts"]:
                    got = None
                    for c in thread:
                        m = match_concept(con, _fflat(c))
                        if m and (got is None or m[0] < got[0]):
                            got = (m[0], m[1], m[2], c)
                    for a in con["alts"]:
                        if a["kind"] in ("digits", "ado"):
                            c = next((c for c in thread if str(c.get("id")) == a["id"]), None)
                            if c:
                                got = (0, "comment id", 0, c)
                        elif a["kind"] == "node" and (got is None or got[0] > 0):
                            pin = _fnode(r).replace("-", ":")
                            if pin == a["text"]:
                                got = (0, "pinned here", 0, r)
                            elif (paths.get(key) or {}).get(a["text"]):
                                how = _how_on(r, paths[key][a["text"]])
                                if how:
                                    got = (1, how, 0, r)
                    best.append(got)
                if all(best):
                    c = best[0][3]
                    hits.append({"ts": r.get("created_at", ""), "form": "/".join(sorted({b[1] for b in best})),
                                 "alts": _which(q, [_fflat(x) for x in thread]),
                                 "rank": max(b[0] for b in best), "open": not r.get("resolved_at"),
                                 "head": f"{r.get('created_at', '')[:10]}  {_fstate(r):19} {len(thread) - 1:>2} repl."
                                         f"  {_fhandle(r)}  {_flink(key, *files[key], r)}",
                                 "excerpt": excerpt(_fflat(c), best[0][2], 200),
                                 "ids": [f"figma:{c['id']}" for c in thread]})
        hits.sort(key=lambda h: h["ts"], reverse=True)
        out.append({"ran": True, "why": "", "cov": list(cov), "hits": hits, "partial": list(partial)})
    return out


ADO_SKIP = ("System.AreaPath", "System.IterationPath", "System.TeamProject", "System.State", "System.Reason",
            "System.WorkItemType", "System.BoardColumn", "System.BoardLane", "Microsoft.VSTS.Common.ValueArea")


ADO_MAX_AGE = 30 * 60   # older than this, the cache is pulled again first (ado_rest.MAX_CACHE_AGE when set)


def _strip_html(s):
    if not s:
        return ""
    import html
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s).strip()


def src_ado(queries, opts):
    org, project = ado_target()
    if CONFIG["ado_cache"]:
        path, max_age = CONFIG["ado_cache"], ADO_MAX_AGE
    else:
        import ado_rest
        path, max_age = ado_rest.CACHE, getattr(ado_rest, "MAX_CACHE_AGE", ADO_MAX_AGE)
    age = time.time() - os.path.getmtime(path) if os.path.exists(path) else None
    note = ""
    if (age is None or age > max_age) and not getattr(opts, "no_pull", False):
        try:
            p = subprocess.run(CONFIG["ado_pull"], capture_output=True, text=True, timeout=900)
            note = "pulled now" if p.returncode == 0 else \
                "pull FAILED: " + cc_logs.redact((p.stderr or p.stdout).strip().splitlines()[-1:][0]
                                                 if (p.stderr or p.stdout).strip() else f"exit {p.returncode}")
        except Exception as e:
            note = "pull FAILED: " + _why(e)
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        return _dnr(f"no readable ADO cache at {path}: {_why(e)}" + (f"; {note}" if note else ""), len(queries))
    age = time.time() - d.get("pulled", 0)
    if note.startswith("pull FAILED") and age > 24 * 3600:
        return _dnr(f"{note}; the cache is {age / 3600:.0f}h old", len(queries))
    items, comments = d.get("items") or {}, d.get("comments") or {}
    n_com = sum(len(v) for v in comments.values())
    if not items or not n_com:
        return _dnr(f"the cache holds {len(items)} items and {n_com} comments; an empty answer is an error",
                    len(queries))
    stale = age > max_age
    cov = [f"ado: {len(items)} work items (closed and removed included), {n_com} comments; cache "
           f"{age / 60:.0f} min old{' (STALE: --no-pull or a failed pull)' if stale else ''}"
           + (f"; {note}" if note else "")]
    url = f"{org}/{urllib.parse.quote(project)}/_workitems/edit/"

    def records(slim):
        return [(wid, it["head"], [(lb, t, "") for lb, t in it["segs"]]
                 + [(f"comment by {c.get('by', '?')}", _strip_html(c.get("text", "")), c.get("on", ""))
                    for c in comments.get(wid, [])]) for wid, it in slim.items()]
    today, then = records(_ado_slim(items)), {}
    now = utc(datetime.datetime.now(datetime.timezone.utc))
    out = []
    for q in queries:
        cut, recs, qcov, part = q.get("before"), today, list(cov), []
        if cut and cut < now and "no_asof" not in MUT:
            if cut not in then:
                try:
                    then[cut] = _ado_then(cut)
                except BaseException as e:  # ado_rest sys.exits on an HTTP error or a missing token
                    if isinstance(e, KeyboardInterrupt):
                        raise
                    then[cut] = (None, _why(e))
            got, how = then[cut]
            if got is not None:
                recs = records(got)
                qcov.append(f"ado: item fields as they were at {cut}, {len(got)} items then (ADO asOf, {how}); "
                            f"comments written after it are left out, and one edited since shows its new text")
            else:
                part.append(f"asOf lookup DID NOT RUN ({how}); item fields are matched as they are today")
        if cut and cut < now and recs is today:
            qcov.append("ado: NOT LIMITED by --before for item fields: title, description, tags and state are "
                        "matched and shown as they are today; items created after the cutoff and comments "
                        "written after it are left out")
        hits = []
        for wid, f, segs in recs:
            created = utc(f.get("System.CreatedDate", ""))
            if q.get("before") and created >= q["before"]:
                continue
            live = [(lb, t) for lb, t, on in segs if not on or _in_window(q, on) or not q.get("before")]
            best = []
            for con in q["concepts"]:
                got = None
                for si, (lb, t) in enumerate(live):
                    m = match_concept(con, t)
                    if m and (got is None or m[0] < got[0]):
                        got = (m[0], m[1], m[2], si)
                if any(a["kind"] in ("ado", "digits") and a["id"] == wid and not a.get("named") for a in con["alts"]):
                    got = (0, "item id", 0, 0)
                elif got is None and any(a["kind"] == "ado" and a["id"] == wid for a in con["alts"]):
                    got = (RANK["named"], "named", 0, 0)
                best.append(got)
            if all(best):
                lb, t = live[best[0][3]] if live else ("", "")
                hits.append({"ts": f.get("System.ChangedDate", ""), "rank": max(b[0] for b in best),
                             "alts": _which(q, [t for _, t in live]),
                             "title": bool(_which(q, [f.get("System.Title", "")])),
                             "decision": any(lb == "Tags" and "decision" in t.lower() for lb, t in live),
                             "form": "/".join(sorted({b[1] for b in best})),
                             "head": f"#{wid} {f.get('System.State', '?')} {f.get('System.WorkItemType', '')}: "
                                     f"{f.get('System.Title', '')[:90]}  {url}{wid}/  "
                                     f"changed {f.get('System.ChangedDate', '')[:10]}",
                             "excerpt": f"{lb}: " + excerpt(t, best[0][2], 200), "ids": [f"ado:{wid}"]})
        hits.sort(key=lambda h: h["ts"], reverse=True)
        out.append({"ran": True, "why": "", "cov": qcov, "hits": hits, "partial": part})
    return out


def _ado_asof(cut):
    """{work item id: {"fields": ...}} as ADO held the project at cut (UTC text): WIQL ASOF names the items
    that existed then, and workitemsbatch asOf reads their fields as they were. Raises when ADO cannot be read."""
    import ado_rest as a
    org, project = ado_target()
    wiql = {"query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}' ASOF '{cut}'"}
    ids = [w["id"] for w in a._req(f"{org}/{urllib.parse.quote(project)}/_apis/wit/wiql?{a.API}", wiql)["workItems"]]
    items = {}
    for i in range(0, len(ids), 190):
        d = a._req(f"{org}/_apis/wit/workitemsbatch?{a.API}",
                   {"ids": ids[i:i + 190], "asOf": cut, "errorPolicy": "omit"})
        for w in d.get("value") or ():
            if not w:  # omitted: destroyed since
                continue
            f = w.get("fields") or {}
            keep = {k: v for k, v in f.items() if isinstance(v, str)}
            who = f.get("System.AssignedTo")
            if isinstance(who, dict) and who.get("displayName"):
                keep["System.AssignedTo"] = {"displayName": who["displayName"]}
            items[str(w["id"])] = {"fields": keep}
    return items


ADO_HEAD = ("System.Title", "System.State", "System.WorkItemType", "System.CreatedDate", "System.ChangedDate")


def _ado_slim(items):
    """{id: {"head": the fields a hit shows, "segs": [[label, plain text]]}}: only what src_ado reads, with
    each searchable field already stripped of HTML: saved this way, gzip, a cutoff takes a fraction of
    what every field as plain JSON would."""
    out = {}
    for wid, it in items.items():
        f = it.get("fields") or {}
        segs = [[k.split(".")[-1], _strip_html(v)] for k, v in f.items()
                if isinstance(v, str) and k not in ADO_SKIP and not k.endswith("Date")]
        who = f.get("System.AssignedTo")
        if isinstance(who, dict) and who.get("displayName"):
            segs.append(["AssignedTo", who["displayName"]])
        out[str(wid)] = {"head": {k: f[k] for k in ADO_HEAD if isinstance(f.get(k), str)}, "segs": segs}
    return out


def _ado_then(cut):
    """(items as ADO held them at cut, slimmed, and how they were got). A past state does not change, so each
    cutoff is saved, gzip, once it is 15 minutes old, when edits made around it have landed, and read from disk
    after. A read counts as a use, and _ado_prune keeps the folder under CONFIG["ado_asof_max_mb"]."""
    d = CONFIG["ado_asof_cache"]
    path = os.path.join(d, cut.replace(":", "-") + ".json.gz")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            items = json.load(fh)["items"]
    except (OSError, EOFError, ValueError, KeyError):
        items = None
    if items is not None:
        try:
            os.utime(path)
        except OSError:
            pass
        return items, "saved"
    old = path[:-3]  # a cutoff saved whole, as plain JSON, by an older version
    try:
        with open(old, encoding="utf-8") as fh:
            items, how = _ado_slim(json.load(fh)["items"]), "saved, now rewritten as gzip"
    except (OSError, ValueError, KeyError):
        items, how = _ado_slim((CONFIG["ado_asof"] or _ado_asof)(cut)), "read from ADO now"
    if cut < utc(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)):
        os.makedirs(d, exist_ok=True)
        write_atomic(path, gzip.compress(json.dumps({"cutoff": cut, "items": items}).encode("utf-8")))
        try:
            os.remove(old)
        except OSError:
            pass
        _ado_prune(d, path)
    return items, how


def _ado_prune(d, keep):
    """Drop saved cutoffs, least recently written or read first, until the folder is under
    CONFIG["ado_asof_max_mb"]. keep, the one just saved, always stays."""
    files = []
    for n in os.listdir(d):
        if n.endswith((".json.gz", ".json")):
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
    files.sort()
    total, cap = sum(f[1] for f in files), CONFIG["ado_asof_max_mb"] * 1e6
    for _, size, p in files:
        if total <= cap:
            break
        if p == keep:
            continue
        try:
            os.remove(p)
        except FileNotFoundError:  # another run removed it first
            pass
        except OSError:
            continue
        total -= size


def _word_rx(w):
    p = re.escape(w)
    if w[:1].isalnum():
        p = r"\b" + p
    if w[-1:].isalnum():
        p += r"\b"
    return re.compile(p, re.I)


def src_transcripts(queries, opts):
    dirs = transcript_dirs()
    d = next((p for p in dirs if os.path.isdir(p)), None)
    if not d:
        return _dnr("no transcript folder at " + " or ".join(p.replace(HOME, "~") for p in dirs), len(queries))
    md, txt = {}, {}
    for name in os.listdir(d):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".md":
            md[stem] = os.path.join(d, name)
        elif ext.lower() == ".txt":
            txt[stem] = os.path.join(d, name)
    files = [(s, p, False) for s, p in md.items()] + [(s, p, True) for s, p in txt.items() if s not in md]
    files, held = sealing.hold_files(files, _seals(opts), "transcripts", path=lambda f: f[1])
    n_md = sum(1 for _, _, raw in files if not raw)
    paras, vocab, unread = [], set(), []
    for stem, p, raw in sorted(files):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:     # one file, not the source: a cloud-synced read can time out
            unread.append(f"file DID NOT READ: {p.replace(HOME, '~')}: {cc_logs.why_unread(e)}")
            continue
        vocab.update(w.lower() for w in re.findall(r"[A-Za-z]{5,}", text))
        m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})", stem)  # local time, as a capture names it
        when = utc(f"{m.group(1)}T{m.group(2)}:{m.group(3)}", local=True) if m else ""
        stamp = ""
        for ln, para in _paragraphs(text):
            paras.append((stem, raw, when, stamp, ln, para))
            st = STAMP.findall(para)
            if st:
                stamp = st[-1]
    vocab = sorted(vocab)
    cov = [f"transcripts: {n_md} cleaned .md and {len(files) - n_md} raw .txt with no .md "
           f"({sum(1 for s in txt if s in md)} .txt skipped: a cleaned .md exists) in {d.replace(HOME, '~')}"
           + (f"; {len(unread)} could not be read" if unread else "")]
    out = []
    for q in queries:
        cons = []
        for con in q["concepts"]:
            extra = []
            for a in con["alts"]:
                if a["kind"] != "text":
                    continue
                if " " not in a["text"] and len(a["text"]) >= 5:
                    known = {x.lower() for _, _, x in extra} | {a["text"].lower()}
                    extra += [("fuzzy", _word_rx(w), w) for w in
                              difflib.get_close_matches(a["text"].lower(), vocab, n=8, cutoff=0.8) if w not in known]
            extra.sort(key=lambda e: RANK[e[0]])
            cons.append(dict(con, extra=extra))
        qq = dict(q, concepts=cons)
        hits = []
        for stem, raw, when, stamp, ln, para in paras:
            if q.get("before") and when and when >= q["before"]:
                continue
            if q.get("since") and when and when < q["since"]:
                continue
            best, _, _ = match_record(qq, [("transcript", para)])
            if best:
                st = STAMP.findall(para[:best[0][2] + 1]) or ([stamp] if stamp else [])
                hits.append({"ts": when, "rank": max(b[0] for b in best), "alts": _which(qq, [para]),
                             "form": "/".join(sorted({f"{b[1]} '{b[3]}'" if b[1] == "fuzzy"
                                                      else b[1] for b in best})),
                             "head": f"{stem}{'  (raw .txt, no cleaned .md)' if raw else ''}  line {ln}"
                                     + (f"  [{st[-1]}]" if st else ""),
                             "excerpt": excerpt(para, best[0][2], 200), "ids": [f"transcript:{stem}"]})
        hits.sort(key=lambda h: (h["rank"], h["ts"]))
        hits.sort(key=lambda h: h["ts"], reverse=True)
        out.append({"ran": True, "why": "", "cov": cov, "hits": hits, "partial": list(unread), "sealed": held})
    return out


def _repos():
    if CONFIG["repos"] is not None:
        return CONFIG["repos"]
    rs = _folders(kit_config.get("recall", "repos"))
    if rs:
        return rs
    try:                                     # unset: the git repo you run in
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return [p.stdout.strip()] if p.returncode == 0 and p.stdout.strip() else []


def _literals(a):
    if a["kind"] == "stem" or a.get("named"):   # matched in the message only: a git -S run per stem costs minutes
        return []
    if a["kind"] == "node":
        d = a["text"].replace(":", "-")
        return list(dict.fromkeys([a["text"], d, d.replace(";", "%3B")]))
    if a["kind"] != "text":
        return [a["text"]]
    parts, out = _parts(a["text"]), [a["text"]]
    if len(parts) >= 2:
        out += [j.join(parts) for j in (" ", "-", "_", "")]
    seen, keep = set(), []
    for x in out:
        if x.lower() not in seen:
            seen.add(x.lower())
            keep.append(x)
    return keep


def _picked(out):
    """{sha: [path, as bytes]} from `git log --format=%x01%H --name-only -z -S...`: each commit and the files whose
    count of the text changed. A record starts with \\x01 and the hash, so a path of 40 hex digits isn't one."""
    hits, cur = {}, None
    for tok in out.split(b"\0"):
        t = tok.lstrip(b"\n")
        if re.fullmatch(rb"\x01[0-9a-f]{40}(?:[0-9a-f]{24})?", t):
            cur = t[1:].decode()
            hits[cur] = []
        elif t and cur:
            hits[cur].append(t)
    return hits


def _ignored(repo, paths):
    """The paths of a clone its own ignore rules match now: git check-ignore with the index read, so a tracked file is
    never ignored (--no-index would call a force-added one ignored), and core.excludesFile off, so a rule in the
    user's global ignore file doesn't count. Exit 1 means none is ignored; any other code raises."""
    if not paths:
        return set()
    p = subprocess.run(["git", "-c", "core.excludesFile=", "-C", repo, "check-ignore", "-z", "--stdin"],
                       input=b"\0".join(sorted(paths)) + b"\0", capture_output=True, timeout=180)
    if p.returncode not in (0, 1):
        raise RuntimeError(p.stderr.decode("utf-8", "replace").strip()[:160] or f"exit {p.returncode}")
    return {x for x in p.stdout.split(b"\0") if x}


def _unignored(found, partial):
    """found {(repo, literal): {sha: [path]}} -> ({(repo, literal): {sha}} keeping a commit only when one of the files
    it matched in is not ignored now, the commits no literal keeps, {repo: (ignored paths, matched paths)}). A commit
    that added a cache file, and the one that untracked it, match every text the cache held, and can push the
    answer past the cap on git hits. A clone whose check can't run keeps its hits and says DID NOT RUN."""
    paths = collections.defaultdict(set)
    for (r, _), d in found.items():
        for ps in d.values():
            paths[r].update(ps)
    ign = {}
    for r, ps in paths.items():
        try:
            ign[r] = _ignored(r, ps)
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            partial.append(f"git check-ignore DID NOT RUN on {os.path.basename(r)}: {_why(e)}")
            ign[r] = set()
    out, gone, kept = {}, collections.defaultdict(set), collections.defaultdict(set)
    for (r, lit), d in found.items():
        keep = {sha for sha, ps in d.items() if not ps or any(x not in ign[r] for x in ps)}
        out[r, lit] = keep
        gone[r] |= set(d) - keep
        kept[r] |= keep
    return out, sum(len(gone[r] - kept[r]) for r in gone), {r: (len(ign[r]), len(ps)) for r, ps in paths.items()}


def src_git(queries, opts):
    repos = _repos()
    if not repos:
        return _dnr("no git clone: set recall.repos in kit_config, or run inside a repo", len(queries))
    commits, partial = {}, []

    def log(repo):
        p = subprocess.run(["git", "-C", repo, "log", "--all", "--format=%H%x1f%aI%x1f%an%x1f%D%x1f%B%x1e"],
                           capture_output=True, timeout=180)
        if p.returncode:
            raise RuntimeError(p.stderr.decode("utf-8", "replace").strip()[:160])
        return repo, p.stdout.decode("utf-8", "replace")

    def pick(job):
        repo, shas, lit = job
        p = subprocess.run(["git", "-C", repo, "log", "--no-walk", "--stdin", "--format=%x01%H", "--regexp-ignore-case",
                            "--name-only", "-z", "-S" + lit], input="\n".join(shas).encode(), capture_output=True,
                           timeout=180)
        if p.returncode:
            raise RuntimeError(p.stderr.decode("utf-8", "replace").strip()[:160])
        return _picked(p.stdout)

    t0 = time.time()
    with ThreadPoolExecutor(os.cpu_count() or 8) as ex:
        futs = [ex.submit(log, r) for r in repos]
        mine = {}   # repo -> its commits, in the order git log gave them
        for r, f in zip(repos, futs):
            try:
                _, text = f.result()
            except Exception as e:
                partial.append(f"git log DID NOT RUN on {os.path.basename(r)}: {_why(e)}")
                continue
            mine[r] = []
            for rec in text.split("\x1e"):
                bits = rec.strip("\n").split("\x1f")
                if len(bits) < 5:
                    continue
                sha, date, author, refs, msg = bits[0].strip(), bits[1], bits[2], bits[3], "\x1f".join(bits[4:])
                c = commits.setdefault(sha, {"date": date, "utc": utc(date) or date, "author": author, "refs": refs,
                                             "msg": msg, "repos": []})
                c["repos"].append(os.path.basename(r))
                mine[r].append(sha)
        # A commit's diff is the same in every clone that holds it, so -S reads each commit once, in the
        # clone holding the most (clones of one project share most of their commits, and -S over every
        # clone's whole history repeats that work). Fed by sha to --no-walk, in chunks across threads.
        lits = sorted({lit for q in queries for con in q["concepts"] for a in con["alts"] for lit in _literals(a)})
        owner, seen = {}, set()
        for r in sorted(mine, key=lambda r: -len(mine[r])):
            owner[r] = [s for s in mine[r] if s not in seen]
            seen.update(owner[r])
        size = max(100, -(-len(seen) // (os.cpu_count() or 8)))
        jobs = [(r, tuple(shas[i:i + size]), lit) for r, shas in owner.items() for i in range(0, len(shas), size)
                for lit in lits]
        found, failed, ran = collections.defaultdict(dict), set(), 0
        for job, f in zip(jobs, [ex.submit(pick, j) for j in jobs]):
            try:
                found[job[0], job[2]].update(f.result())
                ran += 1
            except Exception as e:
                if (job[0], job[2]) not in failed:
                    partial.append(f"git log -S DID NOT RUN on {os.path.basename(job[0])} for {job[2]!r}: {_why(e)}")
                failed.add((job[0], job[2]))
    found, dropped, ign = _unignored(found, partial)
    cov = [f"git: {len(commits)} commits on every branch of {len(repos)} clones "
           f"({', '.join(os.path.basename(r) for r in repos)}); `git log -S` read each commit once for each of "
           f"{len(lits)} spellings, {ran} of {len(jobs)} "
           f"searches ran, in {time.time() - t0:.0f}s (-S finds a commit that changes how often the text occurs); "
           f"{dropped} commit(s) dropped whose only matches are in files their clone now ignores ("
           + (", ".join(f"{os.path.basename(r)} {n} of {m} paths" for r, (n, m) in sorted(ign.items())) or "none matched")
           + ")"]
    out = []
    for q in queries:
        diff = []
        for con in q["concepts"]:
            s = set()
            for a in con["alts"]:
                for lit in _literals(a):
                    for r in repos:
                        s |= found.get((r, lit), set())
            diff.append(s)
        hits = []
        for sha, c in commits.items():
            if not _in_window(q, c["utc"]):
                continue
            best = []
            for con, ds in zip(q["concepts"], diff):
                m = match_concept(con, c["msg"])
                if m and (m[1] != "some" or sha not in ds or "some_beats_diff" in MUT):   # a diff holding it in full
                    best.append(m)                                                         # beats a lead in the message
                elif sha in ds:
                    best.append((0, "diff", -1, ""))
                else:
                    best.append(None)
            if all(best):
                b = next((b for b in best if b[2] >= 0), None)
                subj = c["msg"].strip().splitlines()[0] if c["msg"].strip() else ""
                hits.append({"ts": c["utc"], "rank": max(x[0] for x in best), "alts": _which(q, [c["msg"]]),
                             "title": bool(_which(q, [subj])),
                             "form": "/".join(sorted({x[1] for x in best})),
                             "head": f"{sha[:8]} {c['date'][:10]} {','.join(sorted(set(c['repos'])))}"
                                     f"{' (' + c['refs'][:60] + ')' if c['refs'] else ''}  {cc_logs.redact(subj)[:100]}",
                             "excerpt": excerpt(c["msg"], b[2], 200) if b else "the diff adds or removes it",
                             "ids": [f"git:{sha}"]})
        hits.sort(key=lambda h: h["ts"], reverse=True)
        out.append({"ran": True, "why": "", "cov": cov, "hits": hits, "partial": list(partial)})
    return out


PRUNE = {".venv", "node_modules", ".git", "dist", ".astro"}
NOTE_EXTS = (".md", ".txt", ".json")


def _text_files(dirs, files, exts=NOTE_EXTS):
    out = [f for f in files if os.path.isfile(f)]
    for d in dirs:
        for root, dn, fn in os.walk(d):
            dn[:] = [x for x in dn if x not in PRUNE]
            out += [os.path.join(root, f) for f in fn if f.lower().endswith(exts)]
    return sorted(set(out))


# ------------------------------------------------------------------------------------------------ seals
# A search must not hand an agent an experiment's sealed predictions or held-out checks. The rule (what a
# marker says, when it expires, what a logs pattern matches, the COVERAGE line) is seals.py's, shared with
# log_extract.py; this keeps recall's own parts: the notes walk and the self-test's broken rules (MUT).

SEAL = sealing.SEAL


def find_seals(opts):
    """Every .recall-sealed marker in the notes folders, found before any source runs, in one walk with the
    notes source's PRUNE set. That walk keeps the note files, so the notes source does not walk again.
    -> {"seals": [seal], "notes": [the note files to search]}; each seal's "notes" holds the files it seals."""
    lift, today = getattr(opts, "include_sealed", False), datetime.date.today()
    seals, notes = [], set()
    for root, fn, s in sealing.walk(notes_dirs(), seals, PRUNE, today, lift, markers="no_seal" not in MUT,
                                    threads=4):
        if s:
            s.setdefault("notes", set())
        for f in fn:
            if f.lower().endswith(NOTE_EXTS):
                p = os.path.join(root, f)
                if s:
                    s["notes"].add(p)
                if not s or s["state"] == "lifted" or "no_seal_notes" in MUT:
                    notes.add(p)
    for s in seals:
        s.setdefault("notes", set())
    for f in _note_files():
        if os.path.isfile(f):
            s = sealing.sealed_at(f, seals)
            if s:
                s["notes"].add(f)
            if not s or s["state"] == "lifted" or "no_seal_notes" in MUT:
                notes.add(f)
    return {"seals": seals, "notes": sorted(notes)}


def _seals(opts):
    return (getattr(opts, "sealed", None) or {}).get("seals") or []


def _seal_logs(inv, copies, seals):
    """seals.hold_logs: the log copies less those a seal holds, with what each seal held and its logs
    patterns that matched no copy; unless the self-test breaks the rule (no_seal_logs)."""
    if "no_seal_logs" in MUT:
        return copies, {}, {}
    return sealing.hold_logs(inv, copies, seals)


def _seal_lines(qr):
    """One COVERAGE line per seal (seals.line), with what it held back from each source that ran, so a seal
    never reads as a clean zero."""
    held, nomatch = collections.defaultdict(collections.Counter), {}
    for r in qr["src"].values():
        for d, c in (r.get("sealed") or {}).items():
            held[d].update(c)
        nomatch.update(r.get("nomatch") or {})
    ran = {n for n, r in qr["src"].items() if r.get("ran")}
    out = []
    for s in qr.get("seals") or ():
        h = held[s["dir"]]
        what = ([sealing.plural(h["notes"], "note file", "note files")] * ("notes" in ran)
                + [sealing.plural(h["memory"], "memory file", "memory files")] * ("memory" in ran)
                + [sealing.plural(h["transcripts"], "transcript", "transcripts")] * ("transcripts" in ran)
                + [sealing.logs_part(h)] * ("logs" in ran))
        out.append(sealing.line(s, what, nomatch.get(s["dir"]) if "logs" in ran else None))
    return out


def _ledger_paras(text):
    """The request ledger: one paragraph per request, your words with its state, the session's title and
    why. The reply it was settled on (ev) is left out: the logs source already searches that text."""
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("text"):
            out.append((i, f"{(r.get('ts') or '')[:16]} request, {r.get('state') or '?'}: \"{r['text']}\" "
                           f"({r.get('title') or 'untitled session'}; {r.get('why') or 'no reason given'})"))
    return out


# The line breaks str.splitlines() splits on, so a file with them changed to \n holds every paragraph
# _paragraphs makes as a run of its text.
LINE_BREAK = re.compile("\r\n|[\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
BREAKS = "\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"


# The characters re.IGNORECASE matches to an ASCII letter that str.lower() does not turn into it (\u0130, \u0131,
# \u017f; found by testing every code point against every ASCII letter and digit).
FOLD_ODD = "\u0130\u0131\u017f"


def _needs(a):
    """[(way, the lowercased words that way cannot match without)] for an ASCII alternative, else None.
    Lowercased text holding none of FOLD_ODD holds a match's letters lowercased, so a missing word rules
    that way out with a plain substring search, which runs many times faster than a case-blind regex."""
    t = a["text"]
    if not t.isascii():
        return None
    if a["kind"] == "node":
        return [("forms", sorted(set(re.findall(r"\d+", t))))]
    if a["kind"] in ("ado", "digits"):
        return [("forms", [a["id"]])]
    parts = [x.lower() for x in _parts(t)]
    words = sorted({w.lower() for w in re.findall(r"\w+", t) if len(w) >= 3})
    return [("exact", [t.lower()]), ("variant", parts or [t.lower()])] + ([("near", words)] if a["near"] else [])


def _could_match(con, text, low=None):
    """Whether a paragraph of text can match con: one of its forms, or every near word, or an extra form,
    is somewhere in text. A superset of match_concept on any paragraph, so a file failing it for one
    concept holds no paragraph that matches the query. Every form's edge test looks for a letter, digit
    or &, and a paragraph's edges in text are a line break or the file's ends (matching every paragraph of
    every note one by one was most of a notes search).

    low: text.lower() when text holds none of FOLD_ODD. Then each way is tried only where its words are,
    and an ASCII alternative's forms run lowercased and case-sensitive on low: a case-blind regex scans
    several times slower, and with no FOLD_ODD character each matches at the same places as the other."""
    for a in con["alts"]:
        need = dict(_needs(a) or ()) if low is not None else {}

        def has(way):
            return way not in need or all(w in low for w in need[way])
        if a["kind"] == "text":
            on, lower = (low, _lowered) if need else (text, lambda rx: rx)
            if has("exact") and lower(a["forms"][0][1]).search(on):
                return True
            if has("variant") and any(lower(rx).search(on) for _, rx in a["forms"][1:]):
                return True
            if a["near"] and has("near") and _near_anywhere([lower(rx) for rx in a["near"]], on):
                return True
            sm = a.get("some")
            if sm and (low is None or _some_ready(sm, low)) and _some_at(sm, _some_pos(sm, text, 0, low)):
                return True
        elif has("forms") and any(rx.search(text) for _, rx in a["forms"]):
            return True
    return any(rx.search(text) for _, rx, _ in con.get("extra", ()))


def _places(con, text, low=None):
    """Every place in text where a paragraph's match of con can start (as _could_match tries it): each start
    of each form, found by searching again from one past the last, so none is hidden inside an earlier
    match; each place of the first near word with the others within NEAR; each start of an extra form.
    A paragraph holding none of them cannot match con."""
    out = set()
    for a in con["alts"]:
        need = dict(_needs(a) or ()) if low is not None else {}

        def has(way):
            return way not in need or all(w in low for w in need[way])
        if a["kind"] == "text":
            on, lower = (low, _lowered) if need else (text, lambda rx: rx)
            for way, rx in a["forms"]:
                if has(way):
                    out.update(_starts(lower(rx), on))
            if a["near"] and has("near"):
                out.update(_near_places([lower(rx) for rx in a["near"]], on))
            sm = a.get("some")
            if sm and "no_some_places" not in MUT and (low is None or _some_ready(sm, low)):
                out.update(p for p, _ in _some_at(sm, _some_pos(sm, text, 0, low)))
        elif has("forms"):
            for _, rx in a["forms"]:
                out.update(_starts(rx, text))
    for _, rx, _ in con.get("extra", ()):
        out.update(_starts(rx, text))
    return sorted(out)


def _starts(rx, text):
    if "finditer_places" in MUT:   # selftest: the starts finditer gives, which skip one inside a match
        return [m.start() for m in rx.finditer(text)]
    out, m = [], rx.search(text)
    while m:
        out.append(m.start())
        m = rx.search(text, m.start() + 1)
    return out


def _near_places(rxs, text):
    pos = [[m.start() for m in rx.finditer(text)] for rx in rxs]
    if not all(pos):
        return []
    return [p for p in pos[0]
            if all((i := bisect.bisect_left(qs, p - NEAR)) < len(qs) and qs[i] <= p + NEAR for qs in pos[1:])]


def _lines_of(places, text):
    """The 0-based line of text each place is on, sorted; text's lines are split on \n only."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    return sorted({bisect.bisect_right(starts, p) - 1 for p in places})


def _covers(lines, lo, hi):
    i = bisect.bisect_left(lines, lo)
    return i < len(lines) and lines[i] <= hi


_LOWERED = {}


def _lowered(rx):
    """rx, an ASCII alternative's case-blind form, as a case-sensitive regex for lowercased text."""
    if rx.pattern not in _LOWERED:
        _LOWERED[rx.pattern] = re.compile(rx.pattern.lower())
    return _LOWERED[rx.pattern]


def _near_anywhere(rxs, text):
    """_near over every place of each word, not the first 400: true wherever _near is true on a part of text."""
    pos = [[m.start() for m in rx.finditer(text)] for rx in rxs]
    if not all(pos):
        return False
    return any(all((i := bisect.bisect_left(qs, p - NEAR)) < len(qs) and qs[i] <= p + NEAR for qs in pos[1:])
               for p in pos[0])


def _read_note(p):
    """-> (text, modified) or (None, "big") or (None, the OSError)."""
    try:
        if os.path.getsize(p) > 20 << 20:
            return None, "big"
        with open(p, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return text, datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc)
    except OSError as e:
        return None, e


def _search_files(queries, files, label, ids_of, name):
    cov_big, recs, unread, nbytes = [], [], [], 0
    # Read on threads: each open costs a fraction of a millisecond, and thousands in a row add up to seconds.
    with ThreadPoolExecutor(16) as ex:
        got = list(ex.map(_read_note, files))
    for p, (text, mt) in zip(files, got):
        if mt == "big":
            cov_big.append(p)
            continue
        if text is None:     # named, never skipped silently: a zero there would clear nothing
            if not (isinstance(mt, FileNotFoundError) and os.path.islink(p)):   # a link to nothing holds no text
                unread.append(f"file DID NOT READ: {p.replace(HOME, '~')}: {cc_logs.why_unread(mt)}")
            continue
        nbytes += len(text)
        # could: {query number: None (match every paragraph) or, per concept, the lines it can match on}
        if p.endswith(".jsonl"):   # the ledger's paragraphs are made from its decoded fields, not its text
            could = dict.fromkeys(range(len(queries)))
        else:
            flat = LINE_BREAK.sub("\n", text) if any(c in text for c in BREAKS) else text
            low = flat.lower() if "no_fold_check" in MUT or not any(c in flat for c in FOLD_ODD) else None
            could = {}
            for qi, q in enumerate(queries):
                if "whole_file_match" in MUT:   # selftest: the shortcut that misses near words past 400 uses
                    if match_record(q, [("", flat)])[0]:
                        could[qi] = None
                    continue
                lines = []
                for con in q["concepts"]:
                    if not _could_match(con, flat, low):
                        break
                    lines.append(_lines_of(_places(con, flat, low), flat))
                else:
                    could[qi] = lines
        paras = (_ledger_paras(text) if p.endswith(".jsonl") else _paragraphs(text, by_line=p.endswith(".json"))
                 ) if could else []
        recs.append((p, utc(mt), mt.astimezone().strftime("%Y-%m-%d"), paras, could))
    base = [f"{name}: {len(recs)} files, {nbytes / 1e6:.0f} M characters, all read; searched as they are "
            f"today (a file has no history here, so --since filters by last modified)"
            + (f"; {len(unread)} could not be read" if unread else "")]
    base += [f"{name}: NOT READ (over 20 MB): {p.replace(HOME, '~')}" for p in cov_big]
    out = []
    for qi, q in enumerate(queries):
        held, tried = [r for r in recs if qi in r[4]], 0
        hits = []
        win = {k: q.get(k) for k in ("since",)}
        for p, mt, day, paras, could in recs:
            if qi not in could or not _in_window(win, mt):
                continue
            lines, got = could[qi], []
            for ln, para in paras:
                if lines is not None and not all(_covers(ls, ln - 1, ln - 1 + para.count("\n")) for ls in lines):
                    continue
                tried += 1
                best, _, _ = match_record(q, [("", para)])
                if best:
                    got.append((ln, para, best))
            if got:
                # The paragraph holding the most of the query's alternatives, then the strongest form: a file is
                # counted by its best paragraph, not by everything spread across it.
                al = [_which(q, [g[1]]) for g in got]
                i = min(range(len(got)), key=lambda i: (-len(al[i]), max(b[0] for b in got[i][2])))
                ln, para, best = got[i]
                fname = os.path.basename(p).lower()
                hits.append({"ts": mt, "rank": max(b[0] for b in best), "form": "/".join(sorted({b[1] for b in best})),
                             "alts": al[i], "title": (para.lstrip().startswith("#") and bool(al[i]))
                             or bool(_which(q, [os.path.splitext(os.path.basename(p))[0]])),
                             "decision": fname in DECISION_FILES or (fname == "requests.jsonl" and ", ruled:" in para),
                             "head": f"{label(p)}:{ln}  modified {day}"
                                     + (f"  (+{len(got) - 1} more paragraph(s))" if len(got) > 1 else ""),
                             "excerpt": excerpt(para, best[0][2], 200), "ids": ids_of(p)})
        hits.sort(key=lambda h: (h["rank"], h["ts"]))
        hits.sort(key=lambda h: h["ts"], reverse=True)
        cov = base + [f"{name}: {len(held)} files hold every concept; {tried:,} of their "
                      f"{sum(len(r[3]) for r in held):,} paragraphs hold a place each concept can match, and "
                      f"were matched one by one"]
        cov += ([f"{name}: NOT LIMITED by --before: each file is searched as it is today, so text written "
                 f"after the cutoff can match"] if q.get("before") else [])
        out.append({"ran": True, "why": "", "cov": cov, "hits": hits, "partial": list(unread)})
    return out


def src_notes(queries, opts):
    sealed = getattr(opts, "sealed", None)            # search() walked the notes folders once, finding seals
    files = sealed["notes"] if sealed else _text_files(notes_dirs(), _note_files())
    held = {s["dir"]: {"notes": len(s["notes"])} for s in _seals(opts) if s["state"] != "expired"}
    if not files:
        return [dict(r, sealed=held) for r in _dnr("no note files found", len(queries))]
    return [dict(r, sealed=held) for r in _search_files(queries, files, lambda p: p.replace(HOME, "~"),
                                                        lambda p: [f"file:{p.replace(HOME, '~')}"], "notes")]


def src_memory(queries, opts):
    globs = memory_globs()
    if getattr(opts, "memory", None):        # one project's memory folder in place of every project's
        globs = [os.path.join(opts.memory, "*.md")] + [g for g in globs if os.sep + "memory" + os.sep not in g]
    files = sorted({p for g in globs for p in glob.glob(g, recursive=True)})
    files, held = sealing.hold_files(files, _seals(opts), "memory")
    if not files:
        return _dnr("no memory cards, skills or CLAUDE.md found", len(queries))

    def ids(p):
        out = [f"file:{p.replace(HOME, '~')}"]
        if os.sep + "memory" + os.sep in p:
            out.append("memory:" + os.path.splitext(os.path.basename(p))[0])
        return out
    return [dict(r, sealed=held) for r in _search_files(queries, files, lambda p: p.replace(HOME, "~"), ids, "memory")]


SRC = {"logs": src_logs, "figma": src_figma, "ado": src_ado, "transcripts": src_transcripts, "git": src_git,
       "notes": src_notes, "memory": src_memory}


# The sources that are Python string work from start to end. In threads they hold the interpreter lock for
# seconds and every other source waits on it, the logs index phase most of all. In processes of their own
# they run beside the rest instead.
PROC_SOURCES = ("notes", "memory", "transcripts")


def _picklable(v):
    import pickle
    try:
        pickle.dumps(v)
        return True
    except Exception:
        return False


def _child(name, cq, opts, config, mut):
    """A source in a process of its own, with this run's CONFIG and MUT."""
    CONFIG.update(config)
    MUT.clear()
    MUT.update(mut)
    return SRC[name](cq, opts)


def _configured(name):
    """Whether a source is configured (not _off), for search() to start it in a process; one whose check
    fails is left to safe(), which reports it."""
    try:
        return not _off(name)
    except Exception:
        return False


def search(queries, opts):
    """queries: [{"labels", "since", "before"}] -> [{"q": compiled query, "src": {name: result}}]."""
    cq = [compile_query(q) for q in queries]
    names = [s for s in SOURCES if s in opts.sources]
    # The logs inventory lists and checksums log files and reads no note, so it walks while the seals are
    # found; src_logs holds back what the seals name, as before.
    early = ThreadPoolExecutor(1) if "logs" in names else None
    opts.inventory = early and early.submit(cc_logs.Inventory, CONFIG["root"], refresh=getattr(opts, "refresh", False),
                                            cache=CONFIG["cache"])
    par = CONFIG["workers"] > 1 and not getattr(opts, "serial", False)
    procs = [n for n in names if n in PROC_SOURCES and _configured(n)] if par else []
    size = len(procs) + (CONFIG["workers"] if par and "logs" in names else 0)
    # One pool for these sources and the logs scan, started now: up by the time the seals are found. When none can
    # start here (_start_pool), every source and the logs scan run in this process instead.
    kids = _start_pool(size) if size else None
    if kids is None:
        procs = []
    opts.pool = kids if par and "logs" in names else None
    try:                                    # before any source runs, so none reads what a seal holds back
        opts.sealed = find_seals(opts)
    except Exception as e:                  # unknown seals: searching would read them, so nothing runs
        why = (f"nothing was searched: {e}" if isinstance(e, sealing.Unknown)
               else f"the seal check crashed, so nothing was searched: {_why(e)}")
        if early:
            early.shutdown(wait=True)
        if kids:
            kids.shutdown(wait=True)
        opts.inventory = opts.pool = None
        return [{"q": q, "src": {n: _dnr(why, 1)[0] for n in names}, "seals": []} for q in cq]
    if early:
        early.shutdown(wait=False)
    t0, kid = time.time(), {}
    if procs:
        sent = argparse.Namespace(**{k: v for k, v in vars(opts).items() if k not in ("inventory", "pool")})
        config = {k: v for k, v in CONFIG.items() if _picklable(v)}
        kid = {n: kids.submit(_child, n, cq, sent, config, sorted(MUT)) for n in procs}

    def safe(name):
        t1 = time.time()
        try:
            off = _off(name)
            if off:                         # nothing configured: said so, never read as a search that found nothing
                return [{"ran": False, "off": True, "why": off, "cov": [], "hits": [], "partial": []} for _ in cq]
            res = kid[name].result() if name in kid else SRC[name](cq, opts)
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            res = _dnr(f"crashed: {_why(e)}", len(cq))
        for r in res:
            r["secs"] = time.time() - (t0 if name in kid else t1)
        return res

    try:
        with ThreadPoolExecutor(len(names) or 1) as ex:
            futs = {n: ex.submit(safe, n) for n in names if n != "logs"}
            got = {"logs": safe("logs")} if "logs" in names else {}
            got.update({n: f.result() for n, f in futs.items()})
    finally:
        if kids:
            kids.shutdown(wait=False)
        opts.pool = None
    for res in got.values():
        for r in res:
            if r.get("ran"):
                order_hits(r["hits"])
    return [{"q": q, "src": {n: got[n][i] for n in names}, "seals": opts.sealed["seals"]} for i, q in enumerate(cq)]


def exit_code(qr):
    """A source with nothing configured (off) is left out: it was never asked to search. A lead (form some) is not
    a match: with nothing else, the exit is 1, and the report says leads are there to open (meaning())."""
    if any((not r["ran"] and (not r.get("off") or "off_is_gap" in MUT)) or r["partial"] for r in qr["src"].values()):
        return 2
    return 0 if any(not _partial(h) for r in qr["src"].values() for h in r["hits"]) else 1


MEANING = {0: "hits: read them before calling this new or open",
           1: "every configured source ran and nothing matched (mail and chat are not searched)",
           2: "a source DID NOT RUN: a zero there is not a clear"}


def meaning(qr, code):
    """MEANING[code], and for an exit 1 holding leads, that nothing matched in full and the leads are to open."""
    n = sum(1 for r in qr["src"].values() for h in r["hits"])
    if code == 1 and n:
        return (f"nothing matched in full; {n} lead(s) hold only some of a long concept's terms (form some): open "
                f"each before calling this new or open")
    return MEANING[code]


# -------------------------------------------------------------------------------------------- output

FIGMA_URL_KEY = re.compile(r"figma\.com/(?:design|board|file|proto)/([A-Za-z0-9]{10,})/")


def link_lines(lines, keys=None, ado=None, default=None):
    """lines as recall prints them, each ending in the link of every tracker item and Figma node it names that it
    doesn't link already (bare_ids.unlinked decides), so whichever line a session copies carries its links. A
    node links into keys[i], the file of the Figma hit line i belongs to, else the file a Figma URL on the line
    names, else figma.default_file; with none it stays bare. An item links only when ado.org and ado.project are
    set. Only what prints is linked: the hits, the lookup cache and --calibrate keep their text, and an item's
    line still starts with its #id."""
    import figma_comments as fc
    if "no_link" in MUT:
        return list(lines)
    org, project = ado or ado_target()
    if default is None:
        fd = CONFIG.get("figma_default")
        default = kit_config.get("figma", "default_file") if fd is None else fd
    out = []
    for i, ln in enumerate(lines):
        ln = kit_config.ado_linked(ln, org, project)
        m = FIGMA_URL_KEY.search(ln)
        key = (keys or {}).get(i) or (m and m.group(1)) or default
        out.append(fc.linked(key, ln) if key else ln)
    return out


def render(qr, opts, full=False, link=False):
    """The report as lines; with link, each line carries the links of the ids it names (link_lines)."""
    q, src = qr["q"], qr["src"]
    cap_logs = None if full or opts.everything else (opts.max or 8)
    cap = None if full or opts.everything else (opts.max or 5)
    code = exit_code(qr)
    L = ["recall  " + "  AND  ".join(f'"{c["label"]}"' for c in q["concepts"])
         + (f"   since {q['since']}" if q.get("since") else "") + (f"   before {q['before']}" if q.get("before") else ""),
         "  alternatives: " + "; ".join(", ".join(f'{a["text"]} ({a["kind"]})' if a["kind"] != "text" else a["text"]
                                                 for a in c["alts"]) for c in q["concepts"]),
         *[f'  some: "{a["text"]}" also matches {a["some"]["k"]} of {", ".join(a["some"]["terms"])} together'
           for c in q["concepts"] for a in c["alts"] if a.get("some")],
         f"SUMMARY  exit {code}: {meaning(qr, code)}"]
    for n, r in src.items():
        if not r["ran"]:
            L.append(f"  {n:12} " + ("NOT CONFIGURED, not searched: " if r.get("off") else "DID NOT RUN: ") + r["why"])
            continue
        hs = r["hits"]
        if n == "logs":
            sess = {skey(h["key"]) for h in hs}
            you = {skey(h["key"]) for h in hs if h["role"].startswith("you")
                   and (not _partial(h) or "you_counts_leads" in MUT)}   # selftest: the count before leads
            lead = {skey(h["key"]) for h in hs if h["role"].startswith("you") and _partial(h)} - you
            s = f"{len(hs)} record(s) in {len(sess)} session(s), typed by you in {len(you)}" \
                + (f" (and some of its words in {len(lead)} more)" if lead else "")
            if hs:
                s += f", newest {max(h['ts'] for h in hs)[:10] or 'undated'}"
            if r["me"] in sess:
                s += ", this session included"
            if r["aside"]:
                s += f"; {len(r['aside'])} more only in reminders, tool-result copies or harness records" \
                     + ("" if opts.everything else " (--everything)")
        elif n == "figma":
            th = [h for h in hs if not h.get("canvas")]
            s = f"{len(th)} thread(s), {sum(1 for h in th if h['open'])} open, {len(hs) - len(th)} canvas text layer(s)"
        else:
            new = max((h["ts"] or "" for h in hs), default="")
            s = f"{len(hs)} hit(s)" + (f", newest {new[:10]}" if new else "")
        part = sum(1 for h in hs if _partial(h))
        s += f"; {part} of them on some of the words only (form some, leads)" if part else ""
        L.append(f"  {n:12} {s}" + (f"   ⚠ PARTIAL: {len(r['partial'])} part(s) did not run" if r["partial"] else ""))
    lg = src.get("logs")
    if lg and lg["ran"] and lg["split"]:
        L.append(f"  {'SPLIT':12} {len(lg['split'])} session(s) hold every concept, never in one record: "
                 + ", ".join(s[:8] for s in lg["split"][:8]))
    live = [s for s in qr.get("seals") or () if s["state"] != "expired"]
    held = sum(1 for s in live if s["state"] != "lifted")
    if live:
        said = [f"{held} seal(s) in force: their folders and logs were not searched"] * bool(held) \
            + [f"{len(live) - held} seal(s) lifted by --include-sealed and searched"] * (held < len(live))
        L.append(f"  {'SEALED':12} " + "; ".join(said) + "; COVERAGE names each and what it held")
    L += narrowed(opts, q)
    keys = {}                     # line -> the Figma file its hit is in, so a comment's node ids link there
    L.append("COVERAGE")
    L += [f"  {x}" for x in _seal_lines(qr)]
    for n, r in src.items():
        L += [f"  {c}" for c in r["cov"]]
        L += [f"  ⚠ {n}: {p}" for p in r["partial"]]
        if r.get("secs") is not None and r["ran"]:
            L.append(f"  {n}: {r['secs']:.0f}s")
    for n, r in src.items():
        if not r["ran"] or not r["hits"] and not (n == "logs" and (r["split"] or (opts.everything and r["aside"]))):
            continue
        L.append("")
        if n == "logs":
            L += _render_logs(r, cap_logs, opts.everything or full)
            continue
        L.append(f"-- {n}: {len(r['hits'])} --")
        for h in r["hits"][:cap]:
            m = FIGMA_URL_KEY.search(h["head"]) if n == "figma" else None
            if m:
                keys[len(L)] = keys[len(L) + 1] = m.group(1)
            L.append(f"  {h['head']}   [{h['form']}]")
            L.append(f"      {h['excerpt']}")
        if cap is not None and len(r["hits"]) > cap:
            L.append(f"  (+{len(r['hits']) - cap} more: --max N, --everything or --out FILE)")
    L.append("")
    you, some = [], []
    if lg and lg["ran"]:
        seen, part = {}, {}
        for h in lg["hits"]:
            if h["role"].startswith("you"):
                d, k = part if _partial(h) else seen, skey(h["key"])
                d[k] = max(d.get(k, ""), h["ts"] or "")
        you = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
        some = sorted(((k, t) for k, t in part.items() if k not in seen), key=lambda kv: kv[1], reverse=True)
    newest = max((h["ts"] or "" for r in src.values() for h in r["hits"]), default="")
    L.append(f"RECAP  exit {code}: {meaning(qr, code)}."
             + (f" You typed it in {len(you)} session(s): " + ", ".join(f"{k[:8]} {t[:10]}" for k, t in you[:5])
                + "." if you else "")
             + (f" You typed some of its words in {len(some)} more (leads): "
                + ", ".join(f"{k[:8]} {t[:10]}" for k, t in some[:5]) + "." if some else "")
             + (f" Newest hit {newest[:10]}." if newest else "")
             + (f" {held} seal(s) held material back, so this is not a search of it: see COVERAGE." if held else ""))
    return link_lines(L, keys) if link else L


def narrowed(opts, q):
    """The NARROWED line: which sources a flag left out, so a narrow search says so."""
    out = []
    left = [n for n in SOURCES if n not in (getattr(opts, "sources", None) or SOURCES)]
    if left:
        out.append(f"  {'NARROWED':12} not searched: {', '.join(left)} (--source); a zero here says nothing about them")
    if q.get("since"):
        out.append(f"  {'NARROWED':12} --since {q['since'][:16]}: everything older was left out")
    return out


def _render_logs(r, cap, everything):
    hits = r["hits"] + (r["aside"] if everything else [])
    if everything:          # search() ordered the hits; the set-aside ones join them here
        order_hits(hits)
    pairs = log_groups(hits)
    groups = dict(pairs)
    order = [s for s, _ in pairs]
    L = [f"-- logs: {len(r['hits'])} record(s) in {len({skey(h['key']) for h in r['hits']})} session(s); "
         f"sessions where you typed it first, then newest --"]
    shown = order if cap is None else order[:cap]
    for s in shown:
        hs = sorted(groups[s], key=lambda h: (not h["role"].startswith("you"), h["role"].endswith("search run"),
                                              h["rank"], h["ts"] or ""))
        tss = sorted(h["ts"][:10] for h in hs if h["ts"])
        when = (tss[0] + (f" → {tss[-1]}" if tss[-1] != tss[0] else "")) if tss else "undated"
        title = "" if s == "history" or s.startswith("vscode/") else \
            " ".join(cc_logs.redact(_title(r["inv"], s)).split())[:90]
        places = sorted({h["where"] + ("" if h["via"] == "disk" else "-zip") for h in hs})
        also = sorted({a for h in hs for a in h.get("also") or ()} - {s})
        L.append(f"== {s[:8] if len(s) == 36 else s}  {when}  {title!r}  [{', '.join(places)}]  {len(hs)} record(s)"
                 + ("  (this session)" if s == r["me"] else "")
                 + ("  also in: " + ", ".join(a[:8] if len(a) == 36 else a for a in also)
                    if also and "no_also_print" not in MUT else ""))
        L.append(f"   {sorted(hs, key=_prefer)[0]['label']}")
        for h in (hs if everything or cap is None else hs[:3]):
            L.append(f"   {(h['ts'] or 'undated')[:16].replace('T', ' ')}  {h['role']:17} "
                     f"[{'/'.join(sorted(set(h['forms'])))}]{' (set aside)' if h['aside'] else ''}  {h['excerpt']}")
        if not everything and cap is not None and len(hs) > 3:
            L.append(f"   (+{len(hs) - 3} more in this session)")
    if len(shown) < len(order):
        L.append(f"(+{len(order) - len(shown)} more session(s): --max N, --everything or --out FILE)")
    for s in r["split"]:
        L.append(f"SPLIT {s[:8]}: every concept is in this session, never in one record; search each alone")
    return L


def write_atomic(path, data):
    """Write text (as UTF-8) or bytes through a temp file and a rename, so no reader sees half a file."""
    path = os.path.abspath(path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------- --last

def cmd_last(name, opts):
    name = os.path.basename(name.replace("\\", "/").rstrip("/"))
    try:                                   # a sealed session's title would print below, so seals come first
        seals = find_seals(opts)["seals"]
    except Exception as e:
        print(f"--last /{name}: no log was read: {e}" if isinstance(e, sealing.Unknown)
              else f"--last /{name}: the seal check crashed, so no log was read: {_why(e)}")
        return 2
    inv, copies, (held, nomatch) = _inventory(opts, seals)
    rs = _pool(json.dumps({"mode": "last", "name": name}), copies, getattr(opts, "serial", False))
    calls, auto, sub = {}, {}, {}
    for r in rs:
        for into, found in ((calls, r["calls"]), (auto, r["auto"]), (sub, r["sub"])):
            for ts, how in found:
                if ts not in into or _prefer({"key": r["key"], "sid": "", "via": r["via"], "live": r["live"]}) < \
                        _prefer({"key": into[ts][0], "sid": "", "via": into[ts][2], "live": into[ts][3]}):
                    into[ts] = (r["key"], how, r["via"], r["live"])
    failed = [r for r in rs if r["error"]]
    gaps = _gaps(inv, failed)                      # any one makes the exit 2, as in a search
    print(f"--last /{name}: {len(copies) - len(failed)} of {len(copies)} log copies read")
    for ln in _seal_lines({"seals": seals, "src": {"logs": {"ran": True, "sealed": held, "nomatch": nomatch}}}):
        print(f"  {ln}")
    cap = max(len(calls), len(auto), len(sub)) if getattr(opts, "everything", False) else \
        (getattr(opts, "max", None) or 8)

    def show(found):
        if len(found) > cap:
            print(f"  (+{len(found) - cap} earlier: --max N or --everything)")
        for ts in sorted(found)[-cap:]:
            key, how = found[ts][:2]
            print(link_lines([f"  {ts[:16]}  {skey(key)[:8]:8}  {cc_logs.redact(' '.join(how.split()))[:140]!r}"])[0])

    def apart():
        for found, what in ((auto, "load(s) by Claude Code itself"), (sub, "call(s) by subagents")):
            if found:
                print(f"\n  +{len(found)} {what}, not counted:")
                show(found)

    # The session asking is the pass now running, so its own call is not the last one: a /rebase run that
    # counted itself would read "0 days ago" and almost no logs since.
    me = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    mine = [k for k in calls if me and skey(calls[k][0]) == me]
    if len(mine) == len(calls):
        print(f"No invocation of /{name}" + (" before this session's own." if mine else "."))
        apart()
        for g in gaps:
            print(f"⚠ {g}")
        return 2 if gaps else 1
    days = sorted({ts[:10] for ts in calls})
    print(f"/{name}: {len(calls)} invocation(s) on {len(days)} day(s), {days[0]} to {days[-1]} (UTC)\n")
    show(calls)
    apart()
    ts = max(k for k in calls if k not in mine)
    t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    gap = (datetime.datetime.now(datetime.timezone.utc) - t).days
    print(f"\nLAST: {ts[:16]}Z ({t.astimezone().strftime('%m-%d %H:%M')} local) in {skey(calls[ts][0])[:8]}, "
          f"{gap} day(s) ago")
    if mine:
        print(f"  this session's own /{name} at {max(mine)[:16]}Z is not counted: it is the pass now running")
    since = []
    for c in copies:
        if c.via == "disk" and c.kind == "main":
            try:
                mt = os.path.getmtime(c.path)
            except FileNotFoundError:              # gone since the scan read it
                gaps.append(f"log gone before its write time was read; the list above may miss it: {c.label()}")
                continue
            if mt > t.timestamp():
                since.append((mt, c))
    since.sort(key=lambda x: x[0], reverse=True)
    print(f"{len(since)} session log(s) written since then, newest first, by last write (local time):")
    for mt, c in since[:30]:
        print(f"  {datetime.datetime.fromtimestamp(mt).strftime('%m-%d %H:%M')}  {c.key[:8]}  "
              f"{' '.join(cc_logs.redact(_title(inv, c.key[:36])).split())[:110]!r}")
    for g in gaps:
        print(f"⚠ {g}")
    return 2 if gaps else 0


# ------------------------------------------------------------------------------------ --calibrate

def _expect(exp, ids):
    """True/False whether one expected answer is among the ids found; None if it is not a lookup."""
    exp = exp.strip()
    if re.fullmatch(r"[0-9a-f]{8}", exp):
        return f"log:{exp}" in ids
    m = re.match(r"(figma|ado|git|memory|file|transcript)(?::\s*(.*))?$", exp)
    if not m:
        return None
    kind, rest = m.group(1), (m.group(2) or "").strip()
    if kind == "figma":
        n = re.search(r"\d{6,}", rest)
        return f"figma:{n.group(0)}" in ids if n else any(i.startswith("figma:") for i in ids)
    if kind == "ado":
        n = re.match(r"\d+", rest)
        return bool(n) and f"ado:{n.group(0)}" in ids
    if kind == "git":
        return any(i.startswith(f"git:{rest[:7]}") for i in ids)
    if kind == "memory":
        return f"memory:{rest}" in ids
    if kind == "file":
        base = os.path.basename(rest)
        return any(i.startswith("file:") and i.endswith(base) for i in ids)
    toks = rest.split()
    return any(i.startswith("transcript:") and all(t in i for t in toks) for i in ids)


# The sources an expected answer can come from, so a miss can be put down to a source that did not run.
_EXPECT_SRC = {"figma": ("figma",), "ado": ("ado",), "git": ("git",), "memory": ("memory",),
               "file": ("notes", "memory"), "transcript": ("transcripts",)}


def _expect_sources(exp):
    m = re.match(r"(figma|ado|git|memory|file|transcript)\b", exp.strip())
    return _EXPECT_SRC[m.group(1)] if m else ("logs",)


def _unread_ids(qr, sources):
    """The ids _ids would give the records in each file a source named as DID NOT READ, so _expect
    can tell a miss recall made from one it never had the bytes for."""
    ids = set()
    for s in sources:
        for line in qr["src"].get(s, {}).get("partial", []):
            m = re.search(r"DID NOT READ: (.+?): ", line)
            if not m:
                continue
            path = m.group(1)
            if s == "transcripts":
                ids.add("transcript:" + os.path.splitext(os.path.basename(path))[0])
            elif s == "logs":
                u = re.search(r"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-", path)
                if u:
                    ids.add("log:" + u.group(1))
            else:
                ids.add("file:" + path)
    return ids


def _ids(qr, leads=False):
    """The ids of the hits, full matches only; with leads, the leads' (form some) too."""
    ids = set()
    for n, r in qr["src"].items():
        for h in r["hits"]:
            if _partial(h) and not leads:
                continue
            if n == "logs":
                ids.add("log:" + skey(h["key"])[:8])
            else:
                ids.update(h["ids"])
    return ids


def _copy_ids(qr):
    """Log sessions a header names on "also in" with no hit printed under their own id: each holds a copy of a
    record printed under another session. A lead's copies are not credited."""
    if "no_copy_credit" in MUT:
        return set()
    lg = qr["src"].get("logs") or {}
    return {"log:" + skey(a)[:8] for h in lg.get("hits", ()) if not _partial(h) for a in h.get("also") or ()} - _ids(qr)


def cmd_calibrate(path, opts):
    """Each past miss searched as the command line searches it, form some included; an answer found only as a lead
    is not counted found, and is marked ~ with the count printed apart."""
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    queries = [{"labels": ["|".join(e["terms"])], "since": None, "before": e.get("before"), "some": True}
               for e in entries]
    t0 = time.time()
    res = search(queries, opts)
    print(f"calibrate: {len(entries)} past cases from {path.replace(HOME, '~')}, each searched as one concept "
          f"(its terms joined by |) with only what existed before its timestamp; {time.time() - t0:.0f}s\n")
    full, got_n, want_n, by_chan, copy_n, lead_n = [], 0, 0, collections.Counter(), 0, 0
    seen_miss, unseen_miss, down = 0, 0, set()
    for e, qr in zip(entries, res):
        ids, copies, leads = _ids(qr), _copy_ids(qr), _ids(qr, leads=True)
        code = exit_code(qr)
        marks = []
        for exp in e["expect"]:
            ok = _expect(exp, ids)
            if ok is None:
                marks.append(f"[behaviour: ran, exit {code}]")
                continue
            copy = not ok and bool(_expect(exp, copies))
            ok = ok or copy
            want_n += 1
            got_n += ok
            copy_n += copy
            chan = exp.split(":")[0] if ":" in exp else "logs"
            by_chan[(chan, ok)] += 1
            if not ok:
                # A source that ran only in part still ran: a miss there counts as a recall miss, unless the
                # source named the very file holding the answer as DID NOT READ.
                srcs = _expect_sources(exp)
                off = [s for s in srcs if s not in qr["src"] or not qr["src"][s]["ran"]]
                if off or _expect(exp, _unread_ids(qr, srcs)):
                    unseen_miss += 1
                    down.update(off or [f"{s} (the file holding it was not read)" for s in srcs])
                else:
                    seen_miss += 1
            lead = not ok and bool(_expect(exp, leads))
            lead_n += lead
            marks.append(("✓ " if ok else "~ " if lead else "✗ ") + exp + (" (copy)" if copy else "")
                         + (" (lead only: form some)" if lead else ""))
        print(f"  {e['id']:4} exit {code}  {'  '.join(marks)}")
        if opts.out:
            full += [f"===== {e['id']}: {e.get('failure_class', '')}"] + render(qr, opts, full=True) + [""]
    print(f"\n{got_n} of {want_n} expected answers found"
          + (f", {copy_n} of them as a copy: a header names the session on \"also in\"" if copy_n else "") + "."
          + (f" {lead_n} more only as a lead (form some, marked ~), not counted found." if lead_n else ""))
    for chan in sorted({c for c, _ in by_chan}):
        print(f"  {chan:11} {by_chan[(chan, True)]} of {by_chan[(chan, True)] + by_chan[(chan, False)]}")
    print("notes and memory are searched as they are today, so their hits are not limited by the cutoff.")
    if opts.out:
        write_atomic(opts.out, "\n".join(full) + "\n")
        print(f"full reports: {opts.out}")
    if unseen_miss:
        print(f"{unseen_miss} miss(es) in a source that DID NOT RUN, or in a file it could not read: "
              f"{', '.join(sorted(down))}")
    if got_n == want_n:
        return 0
    # A miss in a source that ran is a recall miss, and it outranks one that could not be seen.
    return 1 if seen_miss else 2


# ----------------------------------------------------------------------------------------- --brief
# What to read before answering, in one call: your own words on the topic, the sessions live on it with
# their plans, and earlier work on disk. Most corrections to a session's own work trace to a frame too
# small or a source not looked at, and the material for the better answer is often on disk already.

BRIEF_HOURS = 48                             # a session is live when it wrote a record this recently
BRIEF_WORDS = ("typed", "mid-turn", "card")  # your words; the ledger's "spawned" and "chip" texts are agents'
BRIEF_SOURCES = ("notes", "git", "ado", "transcripts")
BRIEF_OPTIONAL = ("ado", "transcripts")       # not configured here is not a gap, as in the full search
BRIEF_TOP = 12
PLAN_TOOL, WRAP_TOOL = "mcp__ccd_turn__update_plan", "mcp__ccd_turn__wrap_up"   # the desktop app's task list
TS_RX = re.compile(r'"timestamp":\s*"([^"]+)"')


def _clip(s, n):
    s = " ".join((s or "").split())
    s = s if len(s) <= n else s[:n - 1] + "…"
    return s if "no_redact" in MUT else cc_logs.redact(s)


def _brief_words(q, cut):
    """(lines, matched count, how many of them matched only as form some, problem): your typed messages and card
    answers in the request ledger that match every concept, rulings first, then newest; after them those that
    hold only some of a long concept's terms, each marked with the terms it holds, the most terms first. Before
    a cutoff, only what you had said by then, and no state, since the state is today's."""
    path = ledger_path()
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as e:
        return [], 0, 0, f"DID NOT RUN: the request ledger {path.replace(HOME, '~')}: {_why(e)}"
    got = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("source") not in BRIEF_WORDS:
            continue
        ts = utc(r.get("ts"))
        if cut and "brief_no_cut" not in MUT and (not ts or ts >= cut):
            continue
        for k in ("text", "question", "answer"):     # a multi-select answer is a list
            r[k] = r[k] if isinstance(r.get(k), str) else _join(r.get(k))
        segs = [("you", r["text"])]
        if r.get("source") == "card":
            segs = [("card", r["question"]), ("you", r["answer"] or r["text"])]
        best = match_record(q, segs)[0]
        if best:
            some = _held(q, best, segs)
            full = not any(b[1] == "some" for b in best)
            got.append((full, r.get("kind") == "decision" or r.get("state") == "ruled", len(some), ts, r, some))
    got.sort(key=lambda g: g[:4], reverse=True)     # full matches first, as before; then those holding most terms
    out = []
    for full, ruled, _, ts, r, some in got[:12]:
        tag = "ruling" if ruled else (r.get("kind") if cut else r.get("state")) or "?"
        said = (f'card "{_clip(r.get("question"), 140)}" -> "{_clip(r.get("answer") or r.get("text"), 140)}"'
                if r.get("source") == "card" else f'"{_clip(r.get("text"), 300)}"')
        lead = "" if full else f"  [some: {', '.join(some)}]"
        out.append(f"  {ts[:16].replace('T', ' ')}  {tag}{lead}  {said}  ({_clip(r.get('title') or 'untitled', 60)})")
    if len(got) > 12:
        out.append(f"  +{len(got) - 12} more: recall.py <the same concepts> --source notes")
    return out, len(got), sum(1 for g in got if not g[0]), None


def _plan(calls):
    """The task list as the app shows it after these update_plan inputs: [[step, status]]."""
    items = []
    for c in calls:
        if isinstance(c.get("items"), list):
            items = [[str(i.get("content") or ""), i.get("status") or "pending"] for i in c["items"] if isinstance(i, dict)]
            continue
        if c.get("advance"):
            for want, to in (("in_progress", "completed"), ("pending", "in_progress")):
                step = next((i for i in items if i[1] == want), None)
                if step:
                    step[1] = to
        for n in c.get("done") or ():
            if isinstance(n, int) and 0 < n <= len(items):
                items[n - 1][1] = "completed"
        n = c.get("start")
        if isinstance(n, int) and 0 < n <= len(items):
            items[n - 1][1] = "in_progress"
    return items


def _brief_view(path, cut):
    """One main log read up to the cutoff: its last record's time, entrypoint, title, your prompts, its task
    list, its last wrap-up recap and last long message, and the files it edited, each with its time."""
    v = {"last": "", "entry": "", "prompts": [], "recap": ("", ""), "report": ("", ""), "planned": "", "files": {}}
    calls, titles = [], {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            rec = None
            if any(k in line for k in ('"user"', '"assistant"', '"queued_command"', 'Title"')):
                try:
                    rec = json.loads(line)
                except ValueError:
                    pass
            if isinstance(rec, dict):   # its own time: the line can quote another record's
                ts = utc(rec.get("timestamp"))
            else:
                m = TS_RX.search(line)
                ts = utc(m.group(1)) if m else ""
            if cut and ts and ts >= cut and "brief_no_cut" not in MUT:
                continue
            v["last"] = max(v["last"], ts)
            if not isinstance(rec, dict) or rec.get("isSidechain"):
                continue
            v["entry"] = v["entry"] or rec.get("entrypoint") or ""
            for k in ("customTitle", "aiTitle"):      # a title you set outranks the one the app made up
                if rec.get(k):
                    titles[k] = rec[k]
            att = rec.get("attachment") if rec.get("type") == "attachment" else None
            p = _unremind(_join(att.get("prompt")))[0].strip() if isinstance(att, dict) and \
                att.get("type") == "queued_command" else typed(rec)
            if p and _user_role(p) == "you" and not scripted(rec) and not p.lstrip().startswith(("<bash-", "<scheduled-task")):
                v["prompts"].append((ts, p))      # typed, or sent mid-turn; not a ! command or a scheduled run
            for b in ((rec.get("message") or {}).get("content") or []) if rec.get("type") == "assistant" else ():
                if not isinstance(b, dict):
                    continue
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                if b.get("name") == PLAN_TOOL:
                    calls.append(inp)
                    v["planned"] = ts
                elif b.get("name") == WRAP_TOOL:
                    v["recap"] = (ts, inp.get("recap") or "")
                elif b.get("name") in ("Edit", "Write", "NotebookEdit") and inp.get("file_path"):
                    v["files"][inp["file_path"].replace(HOME, "~")] = ts
                elif b.get("type") == "text" and len(b.get("text") or "") >= 200:
                    v["report"] = (ts, b["text"])      # its last long message: what it last told you
    v["plan"], v["title"] = _plan(calls), titles.get("customTitle") or titles.get("aiTitle") or ""
    return v


def _app_sessions():
    """{cli session id: {"id", "title", "archived"}} from the desktop app's session files; {} without the app."""
    out = {}
    for p in glob.glob(os.path.join(CONFIG["app_sessions"], "*", "*", "local_*.json")):
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("cliSessionId"):
            out[d["cliSessionId"]] = {"id": d.get("sessionId") or "", "title": d.get("title") or "",
                                      "archived": bool(d.get("isArchived"))}
    return out


def _brief_sealed(path, seals):
    """A seal in force holds this log: one of its logs patterns names a component of the path, or the log
    sits in its folder. _brief_live reads logs from disk, not through cc_logs, so it checks here."""
    for s in seals:
        if s["state"] in ("expired", "lifted"):
            continue
        if any(sealing.glob_rx(p).search(path) for p in s["logs"]) or sealing.sealed_at(path, [s]):
            return True
    return False


def _brief_live(q, ref, cut, seals=()):
    """(matched, also live, coverage, problem). A session is live when its main log wrote a record in the
    BRIEF_HOURS before ref. This session (the desktop app's CLAUDE_CODE_HOST_SESSION_ID, or the CLI's
    CLAUDE_CODE_SESSION_ID), headless runs, sealed logs and, today, archived sessions are left out; before a
    cutoff an archived session counts, since it may have been live then."""
    proj = os.path.join(CONFIG["root"], ".claude", "projects")
    if not os.path.isdir(proj):
        return [], [], "", f"DID NOT RUN: no session logs at {proj.replace(HOME, '~')}"
    app = _app_sessions()
    me = os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or ""
    me_cli = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    lo_t = datetime.datetime.fromisoformat(ref.replace("Z", "+00:00")).timestamp() - BRIEF_HOURS * 3600
    lo = utc(lo_t * 1000)
    hit, other, read, left = [], [], 0, collections.Counter()
    for path in glob.glob(os.path.join(proj, "*", "*.jsonl")):
        sid = os.path.splitext(os.path.basename(path))[0]
        a = app.get(sid) or {"id": "", "title": "", "archived": False}
        try:
            if os.path.getmtime(path) < lo_t:
                continue
            why = ("this session" if ((me and a["id"] == me) or (me_cli and sid == me_cli)) and "brief_no_self" not in MUT
                   else "sealed" if "brief_no_seal" not in MUT and _brief_sealed(path, seals)
                   else "archived" if a["archived"] and not cut else None)
            v = None if why else _brief_view(path, cut)
        except OSError:
            why = "unreadable"
        if why:
            left[why] += 1
            continue
        read += 1
        if not v["last"] or v["last"] < lo:
            continue
        if v["entry"].startswith("sdk"):
            left["headless"] += 1
            continue
        title = a["title"] or v["title"] or "untitled"
        segs = ([("title", title)] + [("you", p) for _, p in v["prompts"]] + [("plan", s) for s, _ in v["plan"]]
                + [("recap", v["recap"][1]), ("report", v["report"][1])] + [("file", f) for f in v["files"]])
        best = match_record(q, segs)[0]
        (hit if best else other).append(dict(v, title=title, id=a["id"] or sid, archived=a["archived"],
                                             some=_held(q, best, segs) if best else []))
    for xs in (hit, other):
        xs.sort(key=lambda v: v["last"], reverse=True)
    hit.sort(key=lambda v: bool(v["some"]))      # a session holding only some of a long concept's terms goes after
    cov = (f"{read} log(s) written in the {BRIEF_HOURS} h before {ref[:16]}Z read"
           + (f"; left out: {', '.join(f'{k} {n}' for k, n in sorted(left.items()))}" if left else ""))
    return hit, other, cov, (f"{left['unreadable']} log(s) could not be read" if left["unreadable"] else None)


def _stands(v):
    """(when, text): the newer of its last wrap-up recap and its last long message."""
    return max(v["recap"], v["report"])


def _brief_session(q, v):
    when = lambda ts: ts[5:16].replace("T", " ")
    mark = {"completed": "[x]", "in_progress": "[>]"}
    plan = "; ".join(f"{mark.get(st, '[ ]')} {s}" for s, st in v["plan"])
    done = v["recap"][0] and v["recap"][0] >= v["planned"]
    said = [p for p in v["prompts"] if any(match_concept(c, p[1]) for c in q["concepts"])] or v["prompts"]
    out = [f"  {v['title']}  ({v['id'][:14]}{', archived since' if v['archived'] else ''}; last active "
           f"{when(v['last'])}Z)" + (f"  [some: {', '.join(v['some'])}]" if v.get("some") else "")]
    if v["plan"]:
        out.append(f"    plan{' (wrapped up after it)' if done else ''}: {_clip(plan, 300)}")
    ts, text = _stands(v)
    if text:
        out.append(f"    where it stands ({when(ts)}Z): {_clip(text, 260)}")
    if v["files"]:
        out.append("    files it edited: " + _clip(", ".join(sorted(v["files"], key=v["files"].get, reverse=True)[:6]), 260))
    if said:
        out.append(f"    you said ({when(said[-1][0])}Z): \"{_clip(said[-1][1], 220)}\"")
    return out


def _brief_search(labels, cut, opts):
    """(qr, notes left out as born after the cutoff): the earlier-work search, ADO read as cached (a pull is
    one comments call per item, minutes), notes trimmed of the ledger (your words are above), .cache data and,
    before a cutoff, notes born after it; a note changed after it is marked."""
    o = argparse.Namespace(**dict(vars(opts), sources=BRIEF_SOURCES, no_pull=True))
    qr = search([{"labels": labels, "since": None, "before": cut, "some": True}], o)[0]
    born = 0
    r = qr["src"].get("notes")
    if r and r["ran"]:
        keep = []
        for h in r["hits"]:
            p = next((os.path.expanduser(i[5:]) for i in h.get("ids") or () if i.startswith("file:")), "")
            if p and (os.path.abspath(p) == os.path.abspath(ledger_path()) or f"{os.sep}.cache{os.sep}" in p):
                continue
            if p and cut:
                st = os.stat(p) if os.path.exists(p) else None       # utc() reads a number as milliseconds
                if st and "brief_no_cut" not in MUT and utc(getattr(st, "st_birthtime", st.st_mtime) * 1000) >= cut:
                    born += 1
                    continue
                h["changed"] = bool(st and utc(st.st_mtime * 1000) >= cut)
            keep.append(h)
        r["hits"] = keep
    return qr, born


def _brief_earlier(labels, cut, opts):
    """(lines, hit count, how many of them are leads (form some), problem) from notes, git, ADO and transcripts,
    in one round-robin TOP: each source's strongest hit, then each one's next, every full match before any lead
    (ranked). ADO or transcripts not configured is said, not a problem."""
    qr, born = _brief_search(labels, cut, opts)
    out, n, nl, bad, off = [], 0, 0, [], []
    for name in BRIEF_SOURCES:
        r = qr["src"][name]
        if r.get("off") and name in BRIEF_OPTIONAL:
            off.append(name)
            continue
        if not r["ran"] or r["partial"]:
            bad.append(f"{name}: {r['why'] or '; '.join(r['partial'])[:200]}")
        n += len(r["hits"]) if r["ran"] else 0
        nl += sum(1 for h in r["hits"] if _partial(h)) if r["ran"] else 0
    shown = collections.Counter()
    for e in ranked(qr, top=BRIEF_TOP, caps={x: 0 for x in BRIEF_SOURCES}):
        if not e["place"]:
            continue
        h = e["hit"]
        shown[e["src"]] += 1
        out += [f"  {e['src']}  {h['head']}{'  (changed after the cutoff)' if h.get('changed') else ''}"
                + ("  [some of the words only]" if _partial(h) else ""), f"      {h['excerpt']}"]
    for name in BRIEF_SOURCES:
        r = qr["src"][name]
        more = (len(r["hits"]) if r["ran"] else 0) - shown[name]
        if more > 0:
            out.append(f"  {name}: +{more} more: recall.py <the same concepts> --source {name}")
    if born:
        out.append(f"  ({born} note(s) created after the cutoff left out)")
    if off:
        out.append(f"  ({', '.join(off)} not configured, so not searched)")
    return out, n, nl, "; ".join(bad) or None


def _ado_age():
    try:
        p = CONFIG["ado_cache"]
        if not p:
            import ado_rest
            p = ado_rest.CACHE
        return f" ({(time.time() - os.path.getmtime(p)) / 3600:.0f} h old)"
    except Exception:  # noqa: BLE001 -- an age it can't read is left unsaid
        return ""


def cmd_brief(labels, opts):
    """Print the brief; exit 0 something matched, 1 nothing matched (leads, form some, may still be listed:
    a LEADS ONLY line says so), 2 a part DID NOT RUN."""
    def say(text):                          # each line carries its ids' links (link_lines)
        print("\n".join(link_lines(str(text).split("\n"))))

    q = compile_query({"labels": labels, "before": opts.before, "some": True})
    cut = q["before"]
    ref = cut or CONFIG.get("brief_now") or utc(datetime.datetime.now(datetime.timezone.utc))  # brief_now: selftest
    words, nw, nsome, w_bad = _brief_words(q, cut)
    try:                                    # before any log is read, as search() does
        seals = find_seals(opts)["seals"]
    except Exception as e:                  # unknown seals: listing live sessions could show a sealed one
        seals = None
        hit, other, cov, l_bad = [], [], "", (f"DID NOT RUN: {e}" if isinstance(e, sealing.Unknown)
                                              else f"DID NOT RUN: the seal check crashed: {_why(e)}")
    if seals is not None:
        hit, other, cov, l_bad = _brief_live(q, ref, cut, seals)
    earlier, ne, nel, e_bad = _brief_earlier(labels, cut, opts)
    say(f"recall --brief  {' '.join(json.dumps(x, ensure_ascii=False) for x in labels)}  "
        + (f"(as it stood before {cut[:16]}Z)" if cut else "(now)"))
    say(f"NARROWED  --brief leaves out Figma threads and logs older than {BRIEF_HOURS} h, and reads ADO as cached"
        f"{_ado_age()}: run recall.py with the same concepts for those")
    some = "; ".join(f'"{a["text"]}" matches {a["some"]["k"]} of its terms together too ({", ".join(a["some"]["terms"])})'
                     for c in q["concepts"] for a in c["alts"] if a.get("some"))
    if some:
        say(f"SOME  {some}: a [some: ...] line holds only those terms, a lead to open, not a match")
    say(f"YOUR WORDS  {nw} message(s) and card answer(s) in the request ledger match"
        + (f", {nsome} of them on some of the words only" if nsome else "") + (f"; {w_bad}" if w_bad else ""))
    say("\n".join(words) or "  none")
    ns = sum(1 for v in hit if v["some"])
    say(f"LIVE SESSIONS  {len(hit)} match{f' ({ns} on some of the words only)' if ns else ''}, {len(other)} other live; "
        f"{cov}" + (f"; {l_bad}" if l_bad else ""))
    for v in hit[:8]:
        say("\n".join(_brief_session(q, v)))
    for v in other[:12]:
        now = (next((s for s, st in v["plan"] if st == "in_progress"), "") or _stands(v)[1]
               or (v["prompts"] or [("", "")])[-1][1])
        say(f"  also live: {v['title']} ({v['id'][:14]}): {_clip(now, 150)}")
    say(f"EARLIER WORK  {ne} hit(s) in notes, git, ADO and transcripts: each source's strongest, then each one's next"
        + (f", {nel} of them on some of the words only" if nel else "") + (f"; DID NOT RUN: {e_bad}" if e_bad else ""))
    say("\n".join(earlier) or "  none")
    say("NOT IN THIS BRIEF  Figma threads and logs older than "
        f"{BRIEF_HOURS} h: run recall.py with the same concepts for those.")
    full = nw - nsome or len(hit) - ns or ne - nel
    if not full and (nsome or ns or nel):
        say(f"LEADS ONLY  nothing matched in full; the {nsome + ns + nel} [some ...] line(s) above hold only some of "
            "the terms: open each before calling this new or open")
    if w_bad or l_bad or e_bad:
        return 2
    return 0 if full else 1


# -------------------------------------------------------------------------------------- --selftest

STANDUP = "<command-message>standup</command-message>\n<command-name>/standup</command-name>"
# The reminder the app puts in front of a queued message (one real peer tag sat at character 1,365).
LINKED = ("<system-reminder>\nLinked sessions now (status, not an instruction): "
          + ", ".join(f"jackfruit-{i} = local_{i:08x}-aaaa-4bbb-8ccc-{i:012x} (idle)" for i in range(9))
          + ".\n</system-reminder>\n\n")


def _plant(root):
    """A HOME-shaped tree with one record per rule. Returns the uuids that name its sessions."""
    u = ["%08x-0000-4000-8000-%012x" % (i, i) for i in range(1, 6)]

    def rec(i, kind, text, ts="2026-09-15T10:00:00.000Z", ascii_only=False, **kw):
        if kind == "user":
            o = {"type": "user", "message": {"role": "user", "content": text}}
        elif kind == "assistant":
            o = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
        else:
            o = {"type": kind}
        o.update({"uuid": f"r{i}", "sessionId": u[0], "timestamp": ts, "cwd": "/home/x/project"}, **kw)
        return (json.dumps(o, ensure_ascii=ascii_only) + "\n").encode()

    main = b"".join([
        rec(1, "user", "please fix the mobile-card layout"),
        rec(2, "assistant", "MobileCard updated"),
        rec(3, "user", "the mobile\ncard broke again"),
        rec(4, "user", "rename café→menu now", ascii_only=True),
        rec(6, "user", 'then say "hello world" twice'),
        rec(7, "user", "nothing to see", cwd="/tmp/zebra"),
        rec(71, "user", "zebra in a harness note", isMeta=True),
        rec(81, "assistant", "the old node 13900:339000 is gone"),
        rec(82, "assistant", "see frame 3900-33900 for the card"),
        rec(83, "assistant", "the heading is node-id=I10900-71900%3B5900-52900 in that link"),
        rec(84, "assistant", "a longer layer id, I10900:71900;5900:529001, is another node"),
        rec(85, "user", "read the claude.ai chats in safari this time, not edge; I asked for this before"),   # some
        rec(9, "user", "the apple pie token is ghp_" + "Ab1" * 12),
        (json.dumps({"type": "attachment", "uuid": "r10", "sessionId": u[0], "timestamp": "2026-09-15T10:00:00Z",
                     "attachment": {"type": "edited_text_file", "filename": "/x/notes.md",
                                    "snippet": "kiwi is ripe"}}) + "\n").encode(),
        rec(11, "user", "the quokka is here"),
        rec(12, "assistant", "a wombat appeared"),
        rec(13, "user", "old lemon", ts="2026-01-01T00:00:00.000Z"),
        rec(14, "user", "new lemon", ts="2026-09-16T00:00:00.000Z"),
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:01Z", "content": "olive branch please"}) + "\n").encode(),
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:02Z",
                     "content": "<cross-session-message from=\"x\">peach report</cross-session-message>"})
         + "\n").encode(),
        (json.dumps({"type": "attachment", "uuid": "r17", "sessionId": u[0], "timestamp": "2026-09-15T10:00:03Z",
                     "attachment": {"type": "queued_command", "commandMode": "prompt", "origin": {"kind": "peer"},
                                    "prompt": "<cross-session-message from=\"x\">peach report</cross-session-message>"}})
         + "\n").encode(),
        # a subagent's hand-back, its final report: an agent result like a task notice, not a peer
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:04Z",
                     "content": "<agent-message from=\"a1234567890abcdef\">\n[Subagent hand-back] guava finding\n"
                                "</agent-message>"}) + "\n").encode(),
        (json.dumps({"type": "attachment", "uuid": "r18", "sessionId": u[0], "timestamp": "2026-09-15T10:00:05Z",
                     "attachment": {"type": "queued_command", "commandMode": "prompt",
                                    "prompt": "<agent-message from=\"a1234567890abcdef\">\n[Subagent hand-back] guava "
                                              "finding\n</agent-message>"}}) + "\n").encode(),
        # a prompt a script sent into a desktop session: queued with no origin, delivered with turnOrigin sdk
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:06Z", "content": "tamarind brief from a script"}) + "\n").encode(),
        rec(19, "user", "tamarind brief from a script", ts="2026-09-15T10:00:07.000Z", turnOrigin="sdk"),
        # a peer message and a script's prompt behind LINKED, the way the app queues them, each with its delivered
        # copy; and your own words behind it, queued
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:08Z",
                     "content": LINKED + "<cross-session-message from=\"x\">rambutan report</cross-session-message>"})
         + "\n").encode(),
        (json.dumps({"type": "attachment", "uuid": "r20", "sessionId": u[0], "timestamp": "2026-09-15T10:00:09Z",
                     "attachment": {"type": "queued_command", "commandMode": "prompt", "origin": {"kind": "peer"},
                                    "prompt": LINKED + "<cross-session-message from=\"x\">rambutan report"
                                                       "</cross-session-message>"}}) + "\n").encode(),
        rec(21, "user", LINKED + "<cross-session-message from=\"x\">rambutan report</cross-session-message>",
            ts="2026-09-15T10:00:10.000Z"),
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:11Z", "content": LINKED + "salak brief from a script"}) + "\n").encode(),
        rec(22, "user", LINKED + "salak brief from a script", ts="2026-09-15T10:00:12.000Z", turnOrigin="sdk"),
        (json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": u[0],
                     "timestamp": "2026-09-15T10:00:13Z", "content": LINKED + "medlar and the footer too"}) + "\n").encode(),
        rec(15, "user", "<command-name>/rebase</command-name>\n<command-args>now</command-args>"),
        rec(16, "user", "<command-name>/rebase</command-name>\n<command-args>a script</command-args>",
            ts="2026-09-15T11:00:00.000Z", turnOrigin="sdk"),
        # --last /standup: typed twice a minute apart, and one Skill call, are 3; the rest only quote the tags.
        rec(20, "user", STANDUP, ts="2026-09-20T10:00:00.000Z"),
        rec(21, "user", STANDUP, ts="2026-09-20T10:01:00.000Z"),
        rec(22, "user", "", ts="2026-09-20T10:02:00.000Z", message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "L9 " + STANDUP}]}),
        rec(23, "user", "Summary: the user ran " + STANDUP, ts="2026-09-20T10:03:00.000Z", isCompactSummary=True),
        rec(24, "user", "Base directory for this skill: /x/standup\n" + STANDUP, ts="2026-09-20T10:04:00.000Z",
            isMeta=True),
        rec(28, "user", STANDUP, ts="2026-09-20T10:04:30.000Z", isMeta=True),  # isMeta in the typed form
        rec(25, "user", "it printed this: " + STANDUP, ts="2026-09-20T10:05:00.000Z"),
        rec(27, "user", "<command-message>go</command-message>\n<command-name>/go</command-name>\n<command-args>see "
            + STANDUP + "</command-args>", ts="2026-09-20T10:05:30.000Z"),
        rec(26, "assistant", "", ts="2026-09-20T10:06:00.000Z", message={"role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "Skill", "input": {"skill": "standup", "args": "the list"}}]}),
        # Claude Code's own loads: those after a trigger are listed, not counted, one with isMeta unset; the
        # one the Skill call above made is that call. workflow-authoring has only its load, as 49bb1d38 on 9/05.
        rec(29, "attachment", "", ts="2026-09-20T10:04:31.000Z",
            attachment={"type": "ultra_effort_enter", "reminderType": "full"}),
        rec(30, "user", SKILL_LOAD % ("standup", "standup"), ts="2026-09-20T10:04:32.000Z", isMeta=True,
            parentUuid="r29"),
        rec(31, "attachment", "", ts="2026-09-20T10:04:33.000Z", attachment={"type": "workflow_keyword_request"}),
        rec(32, "user", SKILL_LOAD % ("standup", "standup"), ts="2026-09-20T10:04:34.000Z", parentUuid="r31"),
        rec(35, "user", SKILL_LOAD % ("workflow-authoring", "workflow-authoring"), ts="2026-09-20T10:04:35.000Z",
            isMeta=True, parentUuid="r29"),
        rec(33, "user", "", ts="2026-09-20T10:06:01.000Z", parentUuid="r26", message={"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "Launching skill"}]}),
        rec(34, "user", SKILL_LOAD % ("standup", "standup"), ts="2026-09-20T10:06:02.000Z", isMeta=True,
            parentUuid="r33"),
        # A typed prompt ends the walk: this load is listed, though a Skill call sits further up its chain.
        rec(36, "user", "run that as a workflow", ts="2026-09-20T10:07:00.000Z", parentUuid="r34"),
        rec(37, "attachment", "", ts="2026-09-20T10:07:01.000Z", parentUuid="r36",
            attachment={"type": "workflow_keyword_request"}),
        rec(38, "user", SKILL_LOAD % ("standup", "standup"), ts="2026-09-20T10:07:02.000Z", isMeta=True,
            parentUuid="r37"),
        # A subagent's Skill call, here a sidechain record in the main log, is listed apart, not counted.
        rec(39, "assistant", "", ts="2026-09-20T10:09:00.000Z", isSidechain=True, message={
            "role": "assistant", "content": [
                {"type": "tool_use", "id": "t3", "name": "Skill", "input": {"skill": "standup", "args": "x"}}]}),
        # A denied tool call writes its "message" as a string; one that quotes the name must not end --last.
        rec(40, "system", "", ts="2026-09-20T10:09:30.000Z", subtype="permission_denied", tool_name="Bash",
            message="Permission to use Bash has been denied. The command was /standup the list."),
    ])

    def w(rel, data):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    w(f".claude/projects/S/{u[0]}.jsonl", main)
    w(f"archive/x/session-logs/{u[0]}.jsonl", main)
    sub = (json.dumps({"type": "user", "uuid": "s1", "sessionId": u[0], "timestamp": "2026-09-15T10:00:00Z",
                       "message": {"role": "user", "content": "durian task for you"}}) + "\n"
           + json.dumps({"type": "assistant", "uuid": "s2", "sessionId": u[0], "timestamp": "2026-09-15T10:00:01Z",
                         "message": {"role": "assistant", "content": [{"type": "text", "text": "durian done"}]}})
           + "\n"
           + json.dumps({"type": "user", "uuid": "s3", "sessionId": u[0], "timestamp": "2026-09-20T10:07:00Z",
                         "isSidechain": True, "message": {"role": "user", "content": STANDUP}})
           + "\n"
           + "".join(json.dumps({"type": "assistant", "uuid": f"s{i}", "sessionId": u[0], "timestamp": ts,
                                 "message": {"role": "assistant", "content": [
                                     {"type": "tool_use", "id": f"t{i}", "name": "Skill",
                                      "input": {"skill": skill, "args": "from the agent"}}]}}) + "\n"
                     for i, skill, ts in ((4, "standup", "2026-09-20T10:08:00Z"),
                                          (5, "qa-audit", "2026-09-20T10:08:30Z")))).encode()
    w(f".claude/projects/S/{u[0]}/subagents/agent-a1.jsonl", sub)
    cap = "cafecafe-0000-4000-8000-00000000cafe"         # a claude -p run whose script typed /standup: not counted
    w("evals/run9.jsonl", (json.dumps({"type": "system", "subtype": "init", "session_id": cap}) + "\n"
                                   + json.dumps({"type": "user", "uuid": "h1", "session_id": cap,
                                                 "timestamp": "2026-09-20T10:09:00Z",
                                                 "message": {"role": "user", "content": STANDUP}}) + "\n").encode())
    w(".claude/history.jsonl", (json.dumps({"display": "grape juice idea", "timestamp": 1757930400000}) + "\n"
                                + json.dumps({"display": "/rebase", "timestamp": 1757930500000}) + "\n").encode())
    os.makedirs(os.path.join(root, "backups"))
    with zipfile.ZipFile(os.path.join(root, "backups", ".claude.zip"), "w") as zf:
        zf.writestr(f".claude/projects/S/{u[0]}.jsonl", main + rec(16, "user", "resumed later"))
        zf.writestr(f".claude/projects/S/{u[1]}.jsonl",
                    json.dumps({"type": "user", "uuid": "z1", "sessionId": u[1], "timestamp": "2026-09-15T10:00:00Z",
                                "message": {"role": "user", "content": "papaya only in a zip"}}) + "\n")
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr(f"logs/{u[2]}.jsonl",
                    json.dumps({"type": "user", "uuid": "n1", "sessionId": u[2], "timestamp": "2026-09-15T10:00:00Z",
                                "message": {"role": "user", "content": "lychee nested twice"}}) + "\n")
    os.makedirs(os.path.join(root, "cloud", "backup"))
    with zipfile.ZipFile(os.path.join(root, "cloud", "backup", "outer.zip"), "w") as zf:
        zf.writestr("inner.zip", inner.getvalue())
        zf.writestr("__MACOSX/._inner.zip", b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X" + b"\0" * 60)  # not a zip
    cc_logs.plant_cut_zip(os.path.join(root, ".Trash", "cut.zip"),        # truncated, its log held on disk
                          [(f".claude/projects/S/{u[0]}.jsonl", main), ("media/v.mp4", b"m" * 500)])
    t = os.path.join(root, "transcripts")
    os.makedirs(t)
    for name, body in (("transcript_2026-09-10_1000_Standup.md",
                        "[00:01:02] A: the demo is ready\n\n[00:02:00] B: Kowalsky said it is fine\n"),
                       ("transcript_2026-09-11_1000_Other.md", "[00:00:01] A: nothing here\n"),
                       ("transcript_2026-09-11_1000_Other.txt", "[00:00:01] A: mango in the raw only\n"),
                       ("transcript_2026-09-12_1000_Raw.txt", "[00:00:05] A: open the fig jam board\n"),
                       ("transcript_2026-10-05_1030_Early.md", "[00:00:01] A: tzprobe early\n"),
                       ("transcript_2026-10-05_1100_Late.md", "[00:00:01] A: tzprobe late\n")):
        with open(os.path.join(t, name), "w", encoding="utf-8") as fh:
            fh.write(body)
    os.makedirs(os.path.join(root, "notes"))
    with open(os.path.join(root, "notes", "plan.md"), "w", encoding="utf-8") as fh:
        fh.write("# Plan\n\nRepo Enhancements spec from the platform lead.\n")
    with open(os.path.join(root, "notes", "crowded.md"), "w", encoding="utf-8") as fh:   # near past 400 earlier uses
        fh.write("gamut " * 500 + "\r\n\r\nthe spindle of the old gamut\r\n")
    with open(os.path.join(root, "notes", "hidden.md"), "w", encoding="utf-8") as fh:   # line 1's match runs on
        fh.write("x gatling\n\ngatling gatling y\n")                                    # into line 3's start
    with open(os.path.join(root, "notes", "longs.md"), "w", encoding="utf-8") as fh:   # re.I reads \u017f as s
        fh.write("the \u017fpoolprobe word\n")
    os.makedirs(os.path.join(root, "ledger"))
    with open(os.path.join(root, "ledger", "requests.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "r1", "ts": "2026-10-20T10:00:00.000Z", "title": "Planted session", "state": "open",
                             "why": "asked for later and nothing durable holds it", "text": "fix the planted ledger crossfade",
                             "ev": {"reply": "ledgerevidenceonly"}}) + "\nnot json\n")
    # 2026-10-05 at 10:30 and 11:00:55 CDT: 15:30Z and 16:00:55Z, either side of a 15:39 UTC cutoff.
    tz_at = {"early": ("2026-10-05T10:30:00-05:00", 1791214200), "late": ("2026-10-05T11:00:55-05:00", 1791216055)}
    for word, (_, epoch) in tz_at.items():
        p = os.path.join(root, "notes", f"tz-{word}.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"tzprobe {word}\n")
        os.utime(p, (epoch, epoch))
    os.makedirs(os.path.join(root, "mem", "projects", "P", "memory"))
    with open(os.path.join(root, "mem", "projects", "P", "memory", "project_x.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: project_x\n---\n\nZephyr release cut.\n")
    with open(os.path.join(root, "ado.json"), "w", encoding="utf-8") as fh:
        json.dump({"pulled": time.time(),
                   "items": {"9162": {"id": 9162, "fields": {"System.Title": "Stacked rather than tabbed",
                                                             "System.State": "Closed", "System.WorkItemType": "Bug",
                                                             "System.CreatedDate": "2026-08-01T00:00:00Z",
                                                             "System.ChangedDate": "2026-08-02T00:00:00Z"}}},
                   "comments": {"9162": [{"text": "<p>use the <b>stacked</b> one</p>", "by": "reviewer",
                                          "on": "2026-08-02T00:00:00Z"}]}}, fh)
    g = os.path.join(root, "repo")
    os.makedirs(g)
    git = ["git", "-C", g, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null",
           "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", g], check=True)
    for fname, body, msg in (("a.txt", "x\n", "Add pstack helper"), ("b.txt", "the hero crop moved\n", "tweak"),
                             # its message holds 2 of the terms (a lead), its diff the whole text (a match)
                             ("c.txt", "claude.ai Safari not Edge signed_in_browser\n", "Read claude.ai in Safari")):
        with open(os.path.join(g, fname), "w") as fh:
            fh.write(body)
        subprocess.run(git + ["add", fname], check=True)
        subprocess.run(git + ["commit", "-q", "-m", msg], check=True)
    # A cache committed, then untracked under an ignore rule: its add and its untrack match only there. Beside it:
    # a tracked file, a force-added one, a folder's own .gitignore, and a file only a global ignore rule names.
    def put(name, body):
        os.makedirs(os.path.dirname(os.path.join(g, name)), exist_ok=True)
        with open(os.path.join(g, name), "w") as fh:
            fh.write(body)
    for n, steps in enumerate((
            [("put", ".cache.json", '{"t": "ZQCACHE"}\n'), ("add", ".cache.json")],
            [("rmc", ".cache.json"), ("put", ".gitignore", ".cache.json\n*.log\n"), ("add", ".gitignore")],
            [("put", "docs/real.md", "ZQCACHE in a tracked doc\n"), ("add", "docs/real.md")],
            [("put", "keep.log", "ZQFORCE kept\n"), ("add -f", "keep.log")],
            [("put", "sub/secret.txt", "ZQSUB once\n"), ("add", "sub/secret.txt")],
            [("rmc", "sub/secret.txt"), ("put", "sub/.gitignore", "secret.txt\n"), ("add", "sub/.gitignore")],
            [("put", "glob.txt", "ZQGLOBAL once\n"), ("add", "glob.txt")],
            [("rmc", "glob.txt"), ("put", "other.txt", "x\n"), ("add", "other.txt")],
            [("put", "mixed.log", "ZQMIX\n"), ("add -f", "mixed.log")],
            [("rmc", "mixed.log"), ("put", "docs/mix.md", "A tracked note naming ZQMIX, long enough that git doesn't "
                                                          "pair it with mixed.log as a rename\n"), ("add", "docs/mix.md")]), 1):
        for op, name, *body in steps:
            if op == "put":
                put(name, body[0])
            else:
                subprocess.run(git + {"add": ["add"], "add -f": ["add", "-f"], "rmc": ["rm", "-q", "--cached"]}[op]
                               + [name], check=True)
        subprocess.run(git + ["commit", "-q", "-m", f"zq step {n}"], check=True)
    for word, (iso, _) in tz_at.items():  # %aI prints these in the author's offset, -05:00
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", f"tzprobe {word}"], check=True,
                       env=dict(os.environ, GIT_AUTHOR_DATE=iso, GIT_COMMITTER_DATE=iso))
    return u


def selftest_brief():
    """--brief on a planted tree, now and before a cutoff, then each of its rules broken on purpose."""
    import contextlib
    saved = dict(CONFIG)
    env = {k: os.environ.get(k) for k in ("CLAUDE_CODE_HOST_SESSION_ID", "CLAUDE_CODE_SESSION_ID")}
    ok = True
    with tempfile.TemporaryDirectory(suffix=".d") as root:  # ".d": as in selftest
        led, apps = os.path.join(root, "ledger", "requests.jsonl"), os.path.join(root, "app", "x", "y")
        proj, notes, repo = os.path.join(root, ".claude", "projects", "p"), os.path.join(root, "notes"), os.path.join(root, "repo")
        for d in (os.path.dirname(led), apps, proj, os.path.join(notes, ".cache"), repo):
            os.makedirs(d)
        rows = [("2026-10-20T10:00:00Z", "typed", "request", "done", {"text": "build the widget roster from the census"}),
                ("2026-10-21T11:00:00Z", "card", "answer", "answered",
                 {"question": "Which widget roster layout?", "answer": ["Two columns", "with photos"], "text": ""}),
                ("2026-10-21T08:00:00Z", "typed", "request", "open", {"text": "fix the footer spacing"}),
                ("2026-10-21T08:30:00Z", "spawned", "request", "done", {"text": "SPAWNED brief on the widget roster"}),
                ("2026-10-19T09:00:00Z", "typed", "decision", "ruled", {"text": "RULING the widget roster stays one page"}),
                # Shaped as the user's messages of 2026-11-10/11 on reading claude.ai, reworded: --brief "claude.ai
                # Safari not Edge signed_in_browser" missed them while --brief "claude.ai safari" found them.
                ("2026-10-22T04:29:00Z", "typed", "request", "done",
                 {"text": "read the claude.ai chats in safari this time, not edge; I asked for this before"}),
                ("2026-10-21T21:30:00Z", "typed", "request", "answered",
                 {"text": "> Cloudflare: a script can't get past it, so the scripted route won't reach claude.ai. "
                          "my own safari window has it open already"})]
        with open(led, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(dict(r, ts=t, source=s, kind=k, state=st, title="Roster work")) + "\n" for t, s, k, st, r in rows)
        for local, cli, title, arch in (("local_A", "A", "Roster redesign", False), ("local_B", "B", "Old roster", True),
                                        ("local_C", "C", "Footer fix", False), ("local_S", "S", "This one", False),
                                        ("local_D", "D", "Read every claude.ai chat", False)):
            with open(os.path.join(apps, local + ".json"), "w", encoding="utf-8") as fh:
                json.dump({"sessionId": local, "cliSessionId": cli, "title": title, "isArchived": arch}, fh)

        def user(ts, text, entry="claude-desktop"):
            return {"type": "user", "timestamp": ts, "entrypoint": entry, "message": {"role": "user", "content": text}}

        def tool(ts, name, inp):
            return {"type": "assistant", "timestamp": ts,
                    "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": inp}]}}
        steps = [{"content": "Read the census", "status": "in_progress"}, {"content": "Draft the roster", "status": "pending"}]
        logs = {"A": [user("2026-10-21T09:00:00Z", "rebuild the widget roster from the census"),
                      tool("2026-10-21T09:05:00Z", PLAN_TOOL, {"items": steps}),
                      tool("2026-10-21T09:06:00Z", PLAN_TOOL, {"advance": True}),
                      tool("2026-10-21T09:30:00Z", "Write", {"file_path": os.path.join(notes, "roster-draft.md")}),
                      tool("2026-10-21T12:00:00Z", WRAP_TOOL, {"recap": "ROSTER-RECAP the draft is written"}),
                      {"type": "attachment", "timestamp": "2026-10-21T12:30:00Z",
                       "attachment": {"type": "queued_command", "prompt": "MIDTURN also the widget roster legend"}},
                      {"type": "attachment", "timestamp": "2026-10-21T12:40:00Z",
                       "attachment": {"type": "queued_command", "prompt": LINKED + "<cross-session-message from=\"x\">"
                                      "PEERBEHIND the widget roster</cross-session-message>"}}],
                "B": [user("2026-10-21T09:10:00Z", "ARCHIVED widget roster, old version")],
                "C": [user("2026-10-21T10:00:00Z", "fix the footer"),
                      tool("2026-10-21T10:01:00Z", PLAN_TOOL, {"items": [{"content": "FOOTER-STEP", "status": "in_progress"}]})],
                # the session where the user said to read claude.ai in a browser, its recap naming the tools
                "D": [user("2026-10-22T10:00:00Z", "open a browser and read every chat end to end"),
                      tool("2026-10-22T11:00:00Z", WRAP_TOOL, {"recap": "Opened an Edge window for the Cloudflare check "
                                                               "on claude.ai, then read it through Safari; "
                                                               "signed_in_browser failed the check"})],
                "S": [user("2026-10-21T09:10:00Z", "SELF widget roster")],
                # this session as the CLI names it, with no desktop app file
                "S2": [user("2026-10-21T09:12:00Z", "SELFCLI widget roster", entry="cli")],
                "SEALD": [user("2026-10-21T09:11:00Z", "SEALEDLOG widget roster")],
                "H": [user("2026-10-21T09:20:00Z", "HEADLESS widget roster grader", entry="sdk-cli")],
                "OLD": [user("2026-10-10T09:00:00Z", "ANCIENT widget roster")]}
        for cli, recs in logs.items():
            with open(os.path.join(proj, cli + ".jsonl"), "w", encoding="utf-8") as fh:
                fh.writelines(json.dumps(r) + "\n" for r in recs)
        os.makedirs(os.path.join(notes, "sealed"))
        for path, text in ((os.path.join(notes, "sealed", SEAL),
                            json.dumps({"reason": "t", "owner": "t", "until": "2099-01-01", "logs": ["SEALD"]})),
                           (os.path.join(notes, "roster.md"), "# Roster\n\nNOTE the widget roster lives here.\n"),
                           (os.path.join(notes, ".cache", "c.md"), "CACHED widget roster\n"),
                           (os.path.join(notes, "browser-route.md"), "# Browser route\n\nclaude.ai is read through the "
                            "open Safari tab, since Cloudflare stops a scripted Edge.\n"),
                           (os.path.join(repo, "r.txt"), "x\n")):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        git = ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null",
               "-c", "commit.gpgsign=false"]
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "Add the widget roster"]):
            subprocess.run(git + args, check=True, capture_output=True)
        # ADO and a transcript, which --brief reads too: one item made before the cutoff below, one after.
        item = lambda t, made: {"fields": {"System.Title": t, "System.State": "Active", "System.WorkItemType": "Task",
                                           "System.CreatedDate": made, "System.ChangedDate": made}}
        with open(os.path.join(root, "ado.json"), "w", encoding="utf-8") as fh:
            json.dump({"pulled": time.time(), "items": {"7": item("WIDGETADO roster layout", "2026-10-20T00:00:00Z"),
                                                        "8": item("LATEADO widget roster", "2026-10-22T00:00:00Z")},
                       "comments": {"7": [{"text": "ok", "by": "reviewer", "on": "2026-10-20T01:00:00Z"}]}}, fh)
        tdir = os.path.join(root, "meetings")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "transcript_2026-10-20_1000_Roster.md"), "w", encoding="utf-8") as fh:
            fh.write("[00:00:01] A: WIDGETTALK the widget roster is one page\n")
        CONFIG.update(root=root, ledger=led, app_sessions=os.path.join(root, "app"), notes_dirs=[notes], notes_files=[],
                      repos=[repo], brief_now="2026-10-23T00:00:00.000Z", ado=("https://dev.azure.com/example", "Planted"),
                      figma_default="",
                      ado_cache=os.path.join(root, "ado.json"), ado_pull=["false"], transcripts=[tdir],
                      aliases=os.path.join(root, "none.md"),
                      ado_asof=lambda cut: {"7": item("WIDGETADO roster layout", "2026-10-20T00:00:00Z")},
                      ado_asof_cache=os.path.join(root, "asof"))
        os.environ["CLAUDE_CODE_HOST_SESSION_ID"] = "local_S"
        os.environ["CLAUDE_CODE_SESSION_ID"] = "S2"
        opts = argparse.Namespace(sources=SOURCES, everything=False, max=None, out=None, no_pull=True, refresh=False,
                                  serial=True, include_sealed=False, before=None, memory=None, scan=False)

        def brief(*labels, before=None):
            opts.before, buf = before, io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cmd_brief(list(labels), opts)
            return code, buf.getvalue()

        def checks():
            c, now = brief("widget roster")
            t, then = brief("widget roster", before="2026-10-21T09:15:00Z")
            res = [("now: your typed words with their state, a card's list answer and a ruling, the ruling first; "
                    "not a spawned brief or another topic",
                    c == 0 and "  done  \"build the widget" in now and "with photos" in now and "SPAWNED" not in now
                    and "footer spacing" not in now and now.find("RULING") < now.find("build the widget")),
                   ("now: the live session on it with its task list as advanced, its recap, the file it wrote and your "
                    "mid-turn message", "Roster redesign" in now and "[x] Read the census; [>] Draft the roster" in now
                    and "ROSTER-RECAP" in now and "roster-draft.md" in now and "MIDTURN" in now),
                   ("now: this session (by the desktop app's id or the CLI's), an archived one, a headless run, a sealed "
                    "one and one quiet for 48 h left out; another live one in a line",
                    not any(w in now for w in ("SELF", "ARCHIVED", "HEADLESS", "ANCIENT", "SEALEDLOG"))
                    and "also live: Footer fix (local_C): FOOTER-STEP" in now),
                   ("now: earlier work in notes, git, ADO and transcripts, not the ledger again or a .cache folder",
                    "NOTE the widget roster" in now and "Add the widget roster" in now and "CACHED" not in now
                    and "requests.jsonl" not in now and "WIDGETADO" in now and "WIDGETTALK" in now),
                   ("now: a peer message queued behind a reminder of 400+ characters is not what you said",
                    'you said (10-21 12:30Z): "MIDTURN also the widget roster legend"' in now),
                   ("now: a NARROWED line says what --brief leaves out", "NARROWED  --brief leaves out Figma" in now),
                   ("before a cutoff: only what was said and done by then, no state, an archived session counts, a note "
                    "and a commit made since left out", t == 0 and "  request  \"build the widget" in then
                    and "with photos" not in then and "ROSTER-RECAP" not in then and "roster-draft.md" not in then
                    and "[x] Read the census; [>] Draft the roster" in then and "ARCHIVED" in then
                    and "Footer fix" not in then and "NOTE the widget" not in then and "1 note(s) created after" in then
                    and "SEALEDLOG" not in then
                    and "Add the widget roster" not in then and "LATEADO" not in then and "WIDGETADO" in then)]
            # Known bad of 2026-11-11: the long query found none of these, the short one all of them.
            c, lg = brief("claude.ai Safari not Edge signed_in_browser")
            cs, sh = brief("claude.ai safari")
            _, un = brief("footer spacing Safari tablet breakpoint")
            mine = ("read the claude.ai chats in safari", "my own safari window has it open")
            said = 'you said (10-22 10:00Z): "open a browser and read every chat'
            res += [("a long query naming tools beside the topic lists your words that name only the topic, each "
                     "marked with the terms it holds, as leads: exit 1 and a LEADS ONLY line, not a match",
                     c == 1 and all(m in lg for m in mine) and "YOUR WORDS  2 message(s)" in lg
                     and "2 of them on some of the words only" in lg and lg.count("[some: claude.ai, Safari]") == 2
                     and "LEADS ONLY  nothing matched in full" in lg),
                    ("...and the live session on it, with what you said there, and the note, each marked as a lead",
                     "Read every claude.ai chat" in lg and "(1 on some of the words only)" in lg and said in lg
                     and "[some: claude.ai, Safari, signed_in_browser]" in lg
                     and "browser-route.md" in lg and "[some of the words only]" in lg),
                    ("the short query still finds the same words, session and note, as full matches",
                     cs == 0 and all(m in sh for m in mine) and "Read every claude.ai chat" in sh and said in sh
                     and "browser-route.md" in sh and "[some" not in sh and "LEADS ONLY" not in sh),
                    ("a long query on another topic that shares one of their terms finds none of them",
                     not any(m in un for m in mine) and "LIVE SESSIONS  0 match" in un and "browser-route.md" not in un)]
            CONFIG["ledger"] = os.path.join(root, "gone.jsonl")
            c, out = brief("widget roster")
            res.append(("a ledger that cannot be read is exit 2 and says DID NOT RUN", c == 2 and "DID NOT RUN" in out))
            CONFIG["ledger"] = led
            c, out = brief("zebra quokka")
            res.append(("nothing on the topic is exit 1, with the live sessions still listed", c == 1 and "also live" in out))
            CONFIG.update(ado=(None, None), transcripts=[])
            c, out = brief("widget roster")
            res.append(("ADO and transcripts not configured: said so, and not exit 2",
                        c == 0 and "(ado, transcripts not configured, so not searched)" in out and "WIDGETADO" not in out))
            CONFIG.update(ado=("https://dev.azure.com/example", "Planted"), transcripts=[tdir])
            return res
        for name, good in checks():
            ok &= good
            print(("pass " if good else "FAIL ") + "--brief " + name)
        for m in ("brief_no_cut", "brief_no_self", "brief_no_seal", "no_some", "no_some_places"):
            MUT.clear()
            MUT.add(m)
            failed = [n for n, g in checks() if not g]
            ok &= bool(failed)
            print(("pass " if failed else "FAIL ") + f"--brief mutation {m} is caught" + (f" by: {failed[0]}" if failed else ""))
        MUT.clear()
    CONFIG.clear()
    CONFIG.update(saved)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return ok


def selftest_rank():
    """Stems, listed aliases, strength order in --brief's ranked list, the full search's sections and the
    NARROWED line, each on a planted case, then each rule broken on purpose."""
    ok, saved = True, dict(CONFIG)

    def check(name, good):
        nonlocal ok
        ok &= bool(good)
        print(("pass " if good else "FAIL ") + "rank: " + name)

    def checks():
        res = []
        res.append(("the S-stemmer takes a plural to its singular, never under 5 letters",
                    (s_stem("widgets"), s_stem("entries"), s_stem("notes"), s_stem("users"), s_stem("class"))
                    == ("widget", "entry", "", "", "")))
        q = compile_query({"labels": ["widgets"]})
        m = match_concept(q["concepts"][0], "the widget repo")
        res.append(("a plural query finds the singular, as a stem, at a word start only",
                    m is not None and m[1] == "stem" and match_concept(q["concepts"][0], "rewidget") is None))
        q = compile_query({"labels": ["notes"]})
        res.append(("a 4-letter stem is not used: notes does not find not", match_concept(q["concepts"][0], "do not") is None))
        with tempfile.TemporaryDirectory() as d:
            idx = os.path.join(d, "aliases.md")
            with open(idx, "w", encoding="utf-8") as fh:
                fh.write("- alias: Gizmo = Agent Gizmo | #4242  (since 2025-10-06, item 4242)\n")
            CONFIG["aliases"] = idx
            late = compile_query({"labels": ["Gizmo"], "before": "2025-10-07"})
            early = compile_query({"labels": ["Gizmo"], "before": "2025-10-05"})
            res.append(("a listed alias applies after the date its record cites, as form named",
                        any(a.get("named") and a["kind"] == "ado" and a["id"] == "4242" for a in late["concepts"][0]["alts"])
                        and match_concept(late["concepts"][0], "see #4242")[1] == "named"))
            res.append(("...and not before it, so a search as of then can't credit a name the record didn't hold yet",
                        not any(a.get("named") for a in early["concepts"][0]["alts"])))
            CONFIG["aliases"] = os.path.join(d, "none.md")
            res.append(("no alias list: no alias, and the query still compiles",
                        not any(a.get("named") for a in compile_query({"labels": ["Gizmo"]})["concepts"][0]["alts"])))
            CONFIG["aliases"] = saved["aliases"]
        long = "claude.ai Safari not Edge signed_in_browser"
        q = compile_query({"labels": [long], "some": True})
        con, sm = q["concepts"][0], q["concepts"][0]["alts"][0].get("some")
        m = match_concept(con, "read the claude.ai chats in safari, not edge")
        res.append(("an alternative of 3 or more terms also matches half of them together, 2 at least, as form some; "
                    "a common word, and the word not rules out, is not a term",
                    sm is not None and sm["k"] == 2 and m is not None and m[1] == "some"
                    and sm["terms"] == ["claude.ai", "Safari", "signed_in_browser"]))
        res.append(("...not one term alone, the words of one term apart, or two terms over 120 characters apart",
                    match_concept(con, "safari and the signed browser") is None
                    and match_concept(con, "claude.ai " + "x " * 70 + "safari") is None))
        res.append(("...not an alternative of 2 terms, as before, nor one of 9 or more (a pasted sentence)",
                    compile_query({"labels": ["claude.ai safari"], "some": True})["concepts"][0]["alts"][0].get("some")
                    is None and compile_query({"labels": [" ".join(f"term{i}x" for i in range(9))], "some": True}
                                              )["concepts"][0]["alts"][0].get("some") is None))
        res.append(("...and a tool that imports recall gets form some only when its query asks for it",
                    compile_query({"labels": [long]})["concepts"][0]["alts"][0].get("some") is None))
        hs = order_hits([{"ts": "2026-10-30", "alts": ["x"], "rank": RANK["some"], "form": "some", "head": "lead",
                          "title": True, "decision": True},
                         {"ts": "2026-10-01", "alts": ["x"], "rank": 0, "form": "near", "head": "match"}])
        res.append(("a hit on some of the words prints after its source's full matches, however new, and weighs less",
                    [h["head"] for h in hs] == ["match", "lead"]
                    and hs[1].get("strength", 0) / 2.25 < hs[0].get("strength", 0)))
        bl = [e["hit"]["head"] for e in ranked({"src": {"notes": {"ran": True, "hits": hs[1:]},
                                                        "git": {"ran": True, "hits": hs[:1]}}}, top=2,
                                               caps={"notes": 0, "git": 0})]
        res.append(("...and in --brief's ranked list a full match places above a lead that weighs more (a decision "
                    "file's heading)", hs[1].get("strength", 0) > hs[0].get("strength", 0) and bl == ["match", "lead"]))
        lq = {"src": {"notes": {"ran": True, "partial": [], "hits": hs[1:]}}}
        res.append(("a search holding only leads exits 1, saying how many leads to open",
                    exit_code(lq) == 1 and "1 lead(s)" in meaning(lq, 1)))
        lg = log_groups([{"key": "aaaaaaaa-0000-4000-8000-000000000001", "ts": "2026-10-30", "role": "you",
                          "rank": RANK["some"]},
                         {"key": "bbbbbbbb-0000-4000-8000-000000000002", "ts": "2026-10-01", "role": "assistant",
                          "rank": 0}])
        res.append(("...and in the logs a session where you typed only some of the words comes after one holding them all",
                    [s[:1] for s, _ in lg] == ["b", "a"]))
        hs = [{"ts": "2026-10-30", "alts": ["atlas"], "form": "exact", "head": "new"},
              {"ts": "2026-10-01", "alts": ["rename", "atlas"], "form": "exact", "title": True, "head": "old"},
              {"ts": "2026-10-29", "alts": ["atlas"], "form": "exact", "head": "mid"}]
        hs = order_hits(hs)
        res.append(("each source's hits print newest first, each with its strength",
                    [h["head"] for h in hs] == ["new", "mid", "old"] and all("strength" in h for h in hs)))
        bl = [e["hit"]["head"] for e in ranked({"src": {"notes": {"ran": True, "hits": hs}}}, top=3, caps={"notes": 0})]
        res.append(("in --brief's ranked list, the record holding the rarer word and a title match outranks newer ones",
                    bl == ["old", "new", "mid"]))
        qr = {"src": {"logs": {"ran": True, "hits": [
                  {"key": "aaaaaaaa-0000-4000-8000-000000000001", "ts": "2026-10-02", "role": "you", "strength": 1.0},
                  {"key": "bbbbbbbb-0000-4000-8000-000000000002", "ts": "2026-10-03", "role": "assistant", "strength": 3.0}]},
                      "ado": {"ran": True, "hits": [{"ts": "x", "strength": 5.0, "head": "A1"}, {"ts": "y", "strength": 2.0, "head": "A2"}]},
                      "git": {"ran": True, "hits": [{"ts": "z", "strength": 1.0, "head": "c1"}]}}}

        def places(rk):
            return [(e["place"], e["src"], e.get("sid", "")[:1] or e.get("hit", {}).get("head")) for e in rk]
        got = places(ranked(qr, top=4))
        res.append(("a ranked list takes each source's strongest first, the strongest source first, then each one's next",
                    got[:4] == [(1, "ado", "A1"), (2, "logs", "a"), (3, "git", "c1"), (4, "ado", "A2")]))
        res.append(("an entry in the ranked list is not placed again in its section", got[4:] == [(5, "logs", "b")]))
        res.append(("the full search prints sections only, a session where you typed it above a stronger one",
                    places(ranked(qr)) == [(1, "logs", "a"), (2, "logs", "b"), (3, "ado", "A1"), (4, "ado", "A2"),
                                           (5, "git", "c1")]))
        opts = argparse.Namespace(sources=("logs", "ado"))
        nl = narrowed(opts, {"since": "2026-10-01T00:00:00.000Z"})
        res.append(("NARROWED names the sources --source left out and the --since window",
                    len(nl) == 2 and "figma, transcripts, git, notes, memory" in nl[0] and "--since 2026-10-01" in nl[1]))
        res += fold_checks()
        res += rewrite_checks()
        res += also_checks()
        res += link_checks()
        return res

    def link_checks():
        """Planted printed lines: each id ends up linked once, a comment's node into its hit's file, and a line
        that links its ids already, or an item line's start, stays as it was."""
        import bare_ids
        import figma_comments as fc
        org, k_hit, k_def = "https://dev.azure.com/example", "HITFILEKEY0001", "DEFAULTKEY0001"
        for k in (k_hit, k_def):
            fc._META.setdefault(k, ("design", "File"))
        lines = ["  #9947 Closed Bug: footer gap",
                 "   2026-10-29 05:04  you  [exact]  see 2101:3303 and #9102",
                 f"  2026-10-26  OPEN  0 repl.  someone  https://www.figma.com/design/{k_hit}/File?node-id=1-2#99",
                 "      move 4410:2208 left",
                 f"  done in {org}/Site/_workitems/edit/9102 and https://www.figma.com/design/{k_def}/File"
                 "?node-id=2101-3303 for 2101:3303 and #9102"]
        got = link_lines(lines, keys={2: k_hit, 3: k_hit}, ado=(org, "Site"), default=k_def)
        return [("every Figma node and tracker id on a printed line carries its link once, and an item line still "
                 "starts with its #id", not any(bare_ids.unlinked(x) for x in got)
                 and re.match(r"^\s+#(\d+) ", got[0]) is not None and got[1].count("_workitems/edit/9102/") == 1),
                ("a node in a Figma comment links into that hit's file, a node anywhere else into the default file",
                 f"/{k_hit}/File?node-id=4410-2208" in got[3] and f"/{k_def}/File?node-id=2101-3303" in got[1]),
                ("a line that links its ids already, an item link with no trailing slash included, is left as it was",
                 got[4] == lines[4])]

    class Copy:
        """A planted log copy, read the way _records reads one."""
        def __init__(self, key, body):
            self.key, self.via, self.body = key, "disk", body

        def label(self):
            return self.key

        def open(self):
            return io.BytesIO(self.body)

    def recs(sid, rows):
        return b"".join(json.dumps({"uuid": u, "timestamp": ts, "sessionId": sid}).encode() + b"\n" for u, ts in rows)

    def fold_checks():
        """A fork copies a session's first records under a new sessionId; the app's continuation copies all of
        one and goes on. Planted as copies in memory."""
        a, f, b = ("aaaaaaaa-0000-4000-8000-00000000000a", "ffffffff-0000-4000-8000-00000000000f",
                   "bbbbbbbb-0000-4000-8000-00000000000b")
        first = [("r1", "2026-08-06T01:00:00.000Z"), ("r2", "2026-08-06T02:00:00.000Z")]
        later = [("r3", "2026-08-07T01:00:00.000Z")]
        inv = argparse.Namespace(logs={a + ".jsonl": [Copy(a + ".jsonl", recs(a, first + later))],
                                       f + ".jsonl": [Copy(f + ".jsonl", recs(f, first))],
                                       b + ".jsonl": [Copy(b + ".jsonl", recs(b, first + later + [("r4", "2026-08-09T01:00:00.000Z")]))]})

        def hit(sid, where):
            return {"id": "r1", "key": sid + ".jsonl", "sid": sid, "via": "disk", "where": where, "label": sid + ".jsonl",
                    "ts": "2026-08-06T01:00:00.000Z"}
        _RECORDS.clear()
        fork = _fold([hit(f, "mac"), hit(a, "archive")], inv)
        cont = _fold([hit(a, "archive"), hit(b, "mac")], inv)
        _RECORDS.clear()
        return [("a record a fork copied prints once, under the session it was first written in, not the fork on "
                 "disk, and names the fork as also holding it",
                 len(fork) == 1 and fork[0]["key"].startswith(a) and fork[0]["also"] == [f]),
                ("a continuation that holds all of a session and goes on takes its records, naming the session too",
                 len(cont) == 1 and cont[0]["key"].startswith(b) and cont[0]["also"] == [a])]

    def rewrite_checks():
        """An older resume copied a session's past into a new log under new ids, keeping time, role and text.
        Planted as copies in memory."""
        def sid(c):
            return c * 8 + "-0000-4000-8000-" + c * 12
        t = [f"2026-09-0{d}T01:00:00.000Z" for d in range(1, 8)]
        r, c, x, y, m, p, q = (sid(ch) for ch in "1234567")
        logs = {r: [("r1", t[0]), ("r2", t[1]), ("r3", t[2])],          # the original, its last record not copied
                c: [("c1", t[0]), ("c2", t[1]), ("c4", t[3])],          # the resume: r1, r2 under new ids, then on
                x: [("x1", t[0]), ("x5", t[4])], y: [("y1", t[0]), ("y6", t[5])],   # one message reached both
                m: [("m2", t[1]), ("m3", t[2]), ("m7", t[6])],          # started mid-conversation, then on
                p: [("p1", t[4]), ("p2", t[5])], q: [("q1", t[4]), ("q2", t[5])]}   # two pure copies, no original
        inv = argparse.Namespace(logs={k + ".jsonl": [Copy(k + ".jsonl", recs(k, v))] for k, v in logs.items()})

        def hit(s, rid, ts, text, role="you"):
            return {"id": rid, "key": s + ".jsonl", "sid": s, "via": "disk", "where": "mac", "label": s + ".jsonl",
                    "ts": ts, "role": role, "excerpt": text}
        _RECORDS.clear()
        bad = _fold([hit(r, "r1", t[0], "hello"), hit(c, "c1", t[0], "hello")], inv)
        cast = _fold([hit(x, "x1", t[0], "ping"), hit(y, "y1", t[0], "ping")], inv)
        other = _fold([hit(r, "r2", t[1], "alpha", "assistant"), hit(c, "c2", t[1], "beta", "assistant")], inv)
        mid = _fold([hit(r, "r3", t[2], "late"), hit(m, "m3", t[2], "late"), hit(m, "m7", t[6], "own")], inv)
        pure = _fold([hit(p, "p1", t[4], "copy"), hit(q, "q1", t[4], "copy")], inv)
        _RECORDS.clear()
        return [("a record a resume copied under a new id prints once, under the session it was first written in, "
                 "naming the copy", len(bad) == 1 and bad[0]["sid"] == r and bad[0]["also"] == [c]),
                ("one message that reached two sessions at the same instant, sharing no other time, prints in both",
                 len(cast) == 2),
                ("records of a copy pair at the same time with other text stay apart", len(other) == 2),
                ("a session that started mid-conversation gives the copied record to the original and keeps its own",
                 sorted((h["sid"], h.get("also")) for h in mid) == sorted([(r, [m]), (m, None)])),
                ("two pure copies with no original left still print the record, once",
                 len(pure) == 1 and pure[0].get("also") in ([p], [q]))]

    def also_checks():
        """A session's header names each other session holding one of its records; a repeat dropped as one typed
        text hands its holders to the hit kept. Planted hits, rendered as the logs section renders them."""
        a, b, c = (ch * 8 + "-0000-4000-8000-" + ch * 12 for ch in "abc")

        def hit(s, ts, also=None, typed=None):
            h = {"key": s + ".jsonl", "sid": s, "via": "disk", "where": "mac", "label": s + ".jsonl", "ts": ts,
                 "role": "you", "rank": 1, "forms": ["exact"], "aside": False, "excerpt": "x"}
            h.update({k: v for k, v in (("also", also), ("typed", typed)) if v})
            return h
        r = {"hits": [hit(a, "2026-09-01", [b]), hit(a, "2026-09-02", [c, b]), hit(c, "2026-09-03")], "aside": [],
             "split": [], "me": "", "inv": argparse.Namespace(logs={}, cloud=set())}
        heads = [x for x in _render_logs(r, None, False) if x.startswith("== ")]
        ha = [x for x in heads if x.startswith("== aaaaaaaa")]
        hc = [x for x in heads if x.startswith("== cccccccc")]
        kept = _drop_repeats([hit(a, "2026-09-01", typed="t"), hit(a, "2026-09-02", [b], typed="t"),
                              hit(c, "2026-09-03", typed="t")])
        return [("a session's header names every other session holding one of its records, once; a session "
                 "holding none names none", len(heads) == 2 and len(ha) == 1 and len(hc) == 1
                 and ha[0].endswith("  also in: bbbbbbbb, cccccccc") and "also in" not in hc[0]),
                ("a repeat of one typed text in a session, dropped, hands the sessions holding it to the hit kept",
                 [(h["sid"], h.get("also")) for h in kept] == [(a, [b]), (c, None)]),
                ("--calibrate credits a session a header names on also in, as a copy, and not a session holding none",
                 _expect("bbbbbbbb", _copy_ids({"src": {"logs": r}})) and not _expect("bbbbbbbb", _ids({"src": {"logs": r}}))
                 and not _expect("dddddddd", _copy_ids({"src": {"logs": r}})))]

    for name, good in checks():
        check(name, good)
    for m in ("no_stem", "no_named", "no_strength", "no_origin", "no_link", "no_also_print", "no_also_keep",
              "no_copy_credit", "no_rewrite", "copy_any_text", "copy_one_time", "no_some", "no_some_tier"):
        MUT.clear()
        MUT.add(m)
        failed = [n for n, g in checks() if not g]
        check(f"mutation {m} is caught" + (f" by: {failed[0]}" if failed else ""), failed)
    MUT.clear()
    CONFIG.clear()
    CONFIG.update(saved)
    return ok


def selftest():
    import types
    ok = True
    saved = dict(CONFIG)
    K = "PLANTEDFILEKEY0"
    planted = [{"id": "1900007741", "message": "Mobile browse card meta row", "created_at": "2026-08-08T00:00:00Z",
                "client_meta": {"node_id": "3900:33900"}, "user": {"handle": "reviewer"}},
               {"id": "1877144800", "parent_id": "1900007741", "message": "agreed", "created_at": "2026-08-09T00:00:00Z",
                "user": {"handle": "Design"}}]
    # Offline stand-ins for figma_comments.py and ado_rest.py: the selftest never reaches a network.
    fc = types.ModuleType("figma_comments")
    fc.ancestry = lambda key, ids: {}
    ar = types.ModuleType("ado_rest")
    ar.CACHE, ar.MAX_CACHE_AGE, ar.API = "", 30 * 60, "api-version=7.0"

    def no_net(*a, **k):
        raise RuntimeError("selftest: no network")
    ar._req = no_net
    real_mods = {n: sys.modules.get(n) for n in ("figma_comments", "ado_rest")}
    sys.modules["figma_comments"], sys.modules["ado_rest"] = fc, ar
    tz_saved = os.environ.get("TZ")
    os.environ["TZ"] = "America/Chicago"  # the planted local times are CDT, -05:00, wherever this runs
    time.tzset()

    # ".d" ends the random folder name: under the system temp dir a name with mixed case and digits can run on
    # into a long path that cc_logs.redact() reads as a key, which hides the planted paths a check looks for.
    with tempfile.TemporaryDirectory(suffix=".d") as root:
        u = _plant(root)
        CONFIG.update(root=root, cache=os.path.join(root, "cache.json"),
                      transcripts=[os.path.join(root, "transcripts")], repos=[os.path.join(root, "repo")],
                      notes_dirs=[os.path.join(root, "notes")], notes_files=[],
                      ledger=os.path.join(root, "ledger", "requests.jsonl"),
                      memory_globs=[os.path.join(root, "mem", "projects", "*", "memory", "*.md")],
                      ado=("https://dev.azure.com/example", "Planted"),
                      ado_cache=os.path.join(root, "ado.json"), ado_pull=["false"],
                      figma_files={K: ("design", "Planted file")}, figma_token="planted", workers=1, figma_default="",
                      figma_canvas="cache", index=os.path.join(root, "index", "index.db"), index_spawn=False,
                      aliases=os.path.join(root, "no-aliases.md"))
        # figma_family's planted file under K, for the words on its canvas; its cache in the planted tree, and
        # no way to Figma.
        import figma_family
        fam_saved = (figma_family.CACHE, figma_family._get)
        figma_family.CACHE = os.path.join(root, "family")

        def offline(*a, **k):
            raise RuntimeError("selftest: no network")
        figma_family._get = offline
        figma_family.plant(K, figma_family._planted()[0])
        opts = argparse.Namespace(sources=SOURCES, everything=False, max=None, out=None, no_pull=True,
                                  refresh=False, serial=True, include_sealed=False, memory=None, scan=False)
        # #9162 as ADO held it at a past time: titled "Tabbed for now" and Active from its creation on 8/01.
        asof_dir, asof_calls = os.path.join(root, "asof"), []

        def asof(cut):
            asof_calls.append(cut)
            if cut < "2026-08-01T00:00:00.000Z":
                return {}
            return {"9162": {"fields": {"System.Title": "Tabbed for now", "System.State": "Active",
                                        "System.WorkItemType": "Bug", "System.CreatedDate": "2026-08-01T00:00:00Z",
                                        "System.ChangedDate": "2026-08-01T00:00:00Z", "System.AreaPath": "Planted",
                                        "Microsoft.VSTS.Common.StateChangeDate": "2026-08-01T00:00:00Z",
                                        "System.Description": "<p>Tabs &amp; panels<img src=\"data:image/png;base64,"
                                                              + "A" * 4000 + "\"></p>"}}}
        CONFIG.update(ado_asof=asof, ado_asof_cache=asof_dir)

        def run(*labels, since=None, before=None, fetch=None, refresh=False):
            """refresh: walk every folder, as a first run does; with the last run's folder index, a find that
            fails in a folder that has not changed is never started (cc_logs._find)."""
            fc.fetch = fetch or (lambda key: [dict(c) for c in planted])
            opts.refresh = refresh
            try:
                qr = search([{"labels": list(labels), "since": since, "before": before, "some": True}], opts)[0]
            finally:
                opts.refresh = False
            return qr, "\n".join(render(qr, opts, full=True))

        def logs(qr):
            return qr["src"]["logs"]["hits"]

        def checks():
            res = []

            def check(name, cond):
                res.append((name, bool(cond)))

            qr, _ = run("mobile card")
            forms = {h["id"]: h["forms"] for h in logs(qr)}
            check("variant: mobile-card, MobileCard and an escaped newline all match 'mobile card' as variant",
                  all(forms.get(r) == ["variant"] for r in ("r1", "r2", "r3")))
            qr, _ = run("café→menu")
            check("non-ASCII term finds a record written with \\u escapes", {h["id"] for h in logs(qr)} == {"r4"})
            qr, _ = run("→")
            check("a lone arrow finds the \\u-escaped record", "r4" in {h["id"] for h in logs(qr)})
            qr, _ = run('say "hello')
            check("a term with a quote finds its record", "r6" in {h["id"] for h in logs(qr)})
            qr, _ = run("zebra")
            check("cwd is not a hit; an isMeta record is set aside; exit 1",
                  not logs(qr) and len(qr["src"]["logs"]["aside"]) == 1 and exit_code(qr) == 1)
            qr, _ = run("3900:33900")
            ids = {h["id"] for h in logs(qr)}
            check("node id matches its dash form and not inside 13900:339000", "r82" in ids and "r81" not in ids)
            qr, text = run("apple pie")
            check("a token in a hit is redacted", "r9" in {h["id"] for h in logs(qr)} and "ghp_" not in text
                  and "[redacted]" in text)
            qr, _ = run("kiwi")
            check("edited_text_file attachment reads as 'you (edited file)'",
                  [h["role"] for h in logs(qr)] == ["you (edited file)"])
            qr, text = run("quokka", "wombat")
            check("two concepts in one session but no one record: no hit, SPLIT named",
                  not logs(qr) and qr["src"]["logs"]["split"] == [u[0]] and "SPLIT" in text)
            qr, _ = run("lemon", since="2026-09-01")
            check("--since keeps the newer record only", [h["id"] for h in logs(qr)] == ["r14"])

            # Planted at 10:30 and 11:00:55 CDT: 15:30Z and 16:00:55Z, either side of a 15:39 UTC cutoff,
            # though as text 11:00 sorts before 15:39.
            def tz(qr, src):
                return sorted(w for h in qr["src"][src]["hits"] for w in re.findall(r"tzprobe (early|late)",
                                                                                    h["excerpt"]))
            qr, _ = run("tzprobe", before="2026-10-05T15:39")
            check("--before is UTC: a git commit at 11:00:55-05:00 is left out, one at 10:30-05:00 kept",
                  tz(qr, "git") == ["early"])
            check("--before is UTC: a transcript named 1100, local time, is left out, one named 1030 kept",
                  tz(qr, "transcripts") == ["early"])
            qr, _ = run("tzprobe", since="2026-10-05T15:39")
            check("--since is UTC: a git commit at 11:00:55-05:00 is kept, one at 10:30-05:00 left out",
                  tz(qr, "git") == ["late"])
            check("--since is UTC: a transcript named 1100 and a note modified 11:00:55 local are kept, "
                  "those at 10:30 left out", tz(qr, "transcripts") == tz(qr, "notes") == ["late"])
            qr, _ = run("tzprobe", before="2026-10-05T17:39+02:00")
            check("a cutoff with an offset is read in that zone: 17:39+02:00 is 15:39Z", tz(qr, "git") == ["early"])
            qr, _ = run("papaya")
            check("zip-only log is read", [h["via"] for h in logs(qr)] == ["zip"])
            qr, _ = run("durian")
            check("subagent records read as agent roles",
                  sorted(h["role"] for h in logs(qr)) == ["agent: assistant", "agent: task"])
            qr, _ = run("grape")
            check("history.jsonl reads as 'you (history)'", [h["role"] for h in logs(qr)] == ["you (history)"])
            qr, _ = run("lychee")
            check("a log inside a zip inside a zip is read", [h["via"] for h in logs(qr)] == ["nested"])
            qr, _ = run("olive")
            check("a queued message reads as 'you (queued)'", [h["role"] for h in logs(qr)] == ["you (queued)"])
            qr, _ = run("peach report")
            check("a queued peer message, and its delivered copy, is one 'peer message', not you",
                  [h["role"] for h in logs(qr)] == ["peer message"])
            qr, _ = run("guava finding")
            check("a subagent's hand-back, queued and delivered, is one 'agent result', not a peer",
                  [h["role"] for h in logs(qr)] == ["agent result"])
            qr, _ = run("tamarind brief")
            check("a prompt a script sent into a desktop session, queued and delivered, is one 'script: prompt', "
                  "not you", [h["role"] for h in logs(qr)] == ["script: prompt"])
            # 2026-11-04: the app queues a message behind a "Linked sessions now" reminder, so the peer tag sat past
            # the 400 characters _user_role read, and the queued copy kept text its delivered copy sets aside
            qr, _ = run("rambutan report")
            check("a queued peer message behind a reminder of 400+ characters, and its delivered copy, is one "
                  "'peer message', not you", len(LINKED) > 400 and [h["role"] for h in logs(qr)] == ["peer message"])
            qr, _ = run("salak brief")
            check("a script's prompt queued behind a reminder of 400+ characters, and its delivered copy, is one "
                  "'script: prompt', not you", [h["role"] for h in logs(qr)] == ["script: prompt"])
            qr, _ = run("medlar")
            check("your own words queued behind a reminder of 400+ characters still read as 'you (queued)'",
                  [h["role"] for h in logs(qr)] == ["you (queued)"])
            qr, _ = run("jackfruit")
            check("a word only in a queued message's reminder is set aside, not typed by you",
                  not logs(qr) and qr["src"]["logs"]["aside"])
            qr, _ = run("MobileCard")
            check("one record in three copies (live, archive, resumed zip) is one hit",
                  [h["id"] for h in logs(qr)].count("r2") == 1)
            # Known bad of 2026-11-11: a query naming tools beside its topic found none of the user's words on it.
            qr, said = run("claude.ai Safari not Edge signed_in_browser")
            check("a query naming tools beside its topic finds a record you typed holding 2 of its 3 terms together, "
                  "through the index, as form some",
                  [(h["role"], h["forms"]) for h in logs(qr) if h["id"] == "r85"] == [("you", ["some"])])
            whole = {skey(h["key"]) for h in logs(qr) if h["role"].startswith("you") and not _partial(h)}
            lead = {skey(h["key"]) for h in logs(qr) if h["role"].startswith("you") and _partial(h)} - whole
            r85 = {skey(h["key"]) for h in logs(qr) if h["id"] == "r85"}
            check("...and the summary counts a session where you typed only some of the words apart from typed by you",
                  bool(r85) and r85 <= lead
                  and f"typed by you in {len(whole)} (and some of its words in {len(lead)} more)" in said)
            check("...and a commit whose message holds 2 of them but whose diff holds the whole text is a diff match, "
                  "not a lead", [h["form"] for h in qr["src"]["git"]["hits"] if "Read claude.ai in Safari" in h["head"]]
                  == ["diff"])
            qr, _ = run("footer spacing Safari tablet breakpoint")
            check("...and a long query on another topic, sharing one term with it, does not",
                  "r85" not in {h["id"] for h in logs(qr)})
            # The logs source reads through recall_index.py. Read whole (--scan), the same queries give the
            # same hits; the index follows a log that grows, is rewritten, or ends mid-line.
            def both(*qs):
                """qs: (labels, since) pairs, searched in the logs at once through the index and read whole.
                -> [(the two agree on hits, roles, forms and SPLIT, the result through the index, its text)]."""
                Q = [{"labels": list(lb), "since": since, "before": None, "some": True} for lb, since in qs]
                was, opts.sources = opts.sources, ("logs",)
                try:
                    a = search(Q, opts)
                    opts.scan = True
                    b = search(Q, opts)
                finally:
                    opts.scan, opts.sources = False, was
                hs = lambda qr: sorted((h["id"], h["role"], tuple(h["forms"]), h["key"], h["via"], h["aside"])
                                       for h in logs(qr) + qr["src"]["logs"]["aside"])
                out = []
                for x, y in zip(a, b):
                    tx, ty = "\n".join(render(x, opts, full=True)), "\n".join(render(y, opts, full=True))
                    out.append((hs(x) == hs(y) and x["src"]["logs"]["split"] == y["src"]["logs"]["split"]
                                and "copies read through it" in tx and "--scan: every copy read whole" in ty, x, tx))
                return out
            agree = both(*[((t,), None) for t in ("mobile card", "café→menu", "kiwi", "olive", "peach report",
                                                  "guava finding", "tamarind brief", "MobileCard", "durian", "papaya",
                                                  "lychee", "grape", "zebra", "3900:33900", "apple pie",
                                                  "claude.ai Safari not Edge signed_in_browser")],
                         (("quokka", "wombat"), None), (("lemon",), "2026-09-01"))
            check(f"{len(agree)} planted queries through the index and read whole (--scan) give the same hits, roles, "
                  f"forms and SPLIT", all(g for g, _, _ in agree) and len(agree) == 18)
            text = both((("→",), None))[0][2]
            check("a term with no 3-character run is read whole, and COVERAGE says why",
                  "every copy read whole, not through the index: '→' has no run of 3" in text)
            live = os.path.join(CONFIG["root"], ".claude", "projects", "S", f"{u[0]}.jsonl")
            with open(live, "rb") as fh:
                orig = fh.read()                  # put back below, so each pass of these checks starts the same
            with open(live, "ab") as fh:
                fh.write(json.dumps({"type": "user", "uuid": "g1", "sessionId": u[0], "timestamp": "2026-09-17T00:00:00Z",
                                     "message": {"role": "user", "content": "feijoa added later"}}).encode() + b"\n"
                         + b'{"type":"user","uuid":"g2","sessionId":"' + u[0].encode()
                         + b'","message":{"role":"user","content":"feijoa still bei')
            conn = recall_index.connect(CONFIG["index"], create=False)
            row0 = recall_index.rows(conn)[(live, "", "")]
            conn.close()
            qr, _ = run("feijoa")
            conn = recall_index.connect(CONFIG["index"], create=False)
            row1 = recall_index.rows(conn)[(live, "", "")]
            conn.close()
            check("a log that grew is read on from where the index stopped: its new record found, the line still "
                  "being written held back", {h["id"] for h in logs(qr)} == {"g1"} and row1["id"] == row0["id"]
                  and row1["done"] == row0["done"] + 1 and row1["offset"] > row0["offset"])
            with open(live, "ab") as fh:
                fh.write(b'ng written"}}\n')
            qr, _ = run("feijoa")
            check("the held line is found once it ends", {h["id"] for h in logs(qr)} == {"g1", "g2"})
            with open(live, "rb") as fh:
                whole = fh.read()
            with open(live, "wb") as fh:          # rewritten: the first record changed, the file shorter
                fh.write(whole.replace(b"please fix the mobile-card layout", b"please fix the guanabana", 1)
                         .rsplit(b"\n", 3)[0] + b"\n")
            qr, _ = run("guanabana")
            qm, _ = run("feijoa")
            check("a log rewritten shorter is read again whole: its changed record found, its cut ones gone",
                  {h["id"] for h in logs(qr)} == {"r1"} and not {"g1", "g2"} & {h["id"] for h in logs(qm)})
            with open(live, "wb") as fh:
                fh.write(orig)
            run("mobile card")
            idx = CONFIG["index"]
            with open(idx, "r+b") as fh:          # a corrupt index: recall sets it aside and reads every copy whole
                fh.write(b"not a database" * 64)
            for ext in ("-wal", "-shm"):
                if os.path.exists(idx + ext):
                    os.remove(idx + ext)
            qr, text = run("mobile card")
            check("a corrupt index is set aside and every copy read whole, and COVERAGE says so: the hits are the same",
                  sorted(h["id"] for h in logs(qr)) == sorted(h["id"] for h in logs(agree[0][1]))
                  and "could not be read, so every copy was read whole" in text and os.path.exists(idx + ".corrupt"))
            qr, text = run("mobile card")
            check("the next call builds a new index and reads through it", "copies read through it" in text
                  and sorted(h["id"] for h in logs(qr)) == sorted(h["id"] for h in logs(agree[0][1])))

            def in_index(*needles):
                """The needles any stored record, FTS lookup or index file byte holds, and the stored copies' keys."""
                got, conn = set(), recall_index.connect(CONFIG["index"], create=False)
                try:
                    for (z,) in conn.execute("select z from rec"):
                        s = zlib.decompress(z)
                        got |= {n for n in needles if n.encode() in s}
                    for n in needles:
                        e = recall_index.all_of([n])
                        if e and conn.execute("select 1 from fts where fts match ? limit 1", (e,)).fetchone():
                            got.add(n)
                    keys = {k for (k,) in conn.execute("select key from copy")}
                finally:
                    conn.close()
                for ext in ("", "-wal"):
                    if os.path.exists(CONFIG["index"] + ext):
                        with open(CONFIG["index"] + ext, "rb") as fh:
                            data = fh.read()
                        got |= {n for n in needles if n.encode() in data}
                return got, keys
            token = "ghp_" + "Ab1" * 12
            got, _ = in_index(token, "apple pie token")
            check("a planted token is in no stored record, FTS row or index file byte; its record is, redacted",
                  got == {"apple pie token"})
            qr, _ = run("Kowalski")
            t = qr["src"]["transcripts"]["hits"]
            check("transcript fuzzy: Kowalsky found for Kowalski, labelled fuzzy", t and "fuzzy" in t[0]["form"])
            qr, _ = run("mango")
            check("a .txt with a cleaned .md is not read; nothing anywhere is exit 1",
                  not qr["src"]["transcripts"]["hits"] and exit_code(qr) == 1)
            qr, _ = run("fig jam")
            t = qr["src"]["transcripts"]["hits"]
            check("a .txt with no .md is read and labelled raw", t and "raw .txt" in t[0]["head"])
            qr, _ = run("1900007741")
            check("figma comment id finds its thread", qr["src"]["figma"]["hits"])
            qr, _ = run(f"https://www.figma.com/design/{K}/Website?node-id=3900-33900#1900007741")
            check("a Figma URL finds its thread and the log record citing the node",
                  qr["src"]["figma"]["hits"] and "r82" in {h["id"] for h in logs(qr)})
            qr, _ = run("I10900:71900;5900:52900")
            ids = {h["id"] for h in logs(qr)}
            check("an instance-layer id finds its URL form (- and %3B) and not inside a longer layer id",
                  "r83" in ids and "r84" not in ids)
            # A thread pinned to a parent frame, its offset inside the node asked for, is on that node.
            frame = {"x": 0, "y": 0, "width": 100, "height": 100}
            fc.ancestry = lambda key, ids: {"5:6": [("1:2", frame), ("5:6", {"x": 10, "y": 10, "width": 20,
                                                                             "height": 20})]}
            pinned = [{"id": "2000000001", "message": "inside", "created_at": "2026-08-08T00:00:00Z",
                       "client_meta": {"node_id": "1:2", "node_offset": {"x": 15, "y": 15}}},
                      {"id": "2000000002", "message": "outside", "created_at": "2026-08-08T00:00:00Z",
                       "client_meta": {"node_id": "1:2", "node_offset": {"x": 80, "y": 80}}}]
            qr, _ = run("5:6", fetch=lambda key: [dict(c) for c in pinned])
            fc.ancestry = lambda key, ids: {}
            check("a thread pinned to a parent frame with its offset inside the node is found as 'offset on', one "
                  "outside it is not", [(h["ids"], h["form"]) for h in qr["src"]["figma"]["hits"]]
                  == [(["figma:2000000001"], "offset on 1:2")])
            qr, text = run("planted build cost")
            cv = [h for h in qr["src"]["figma"]["hits"] if h.get("canvas")]
            check("canvas: words on two text layers (a label and its copy) are found, linked, and counted apart "
                  "from threads", len(cv) == 2 and all("node-id=" in h["head"] and "$5.49" in h["excerpt"] for h in cv)
                  and "2 canvas text layer(s)" in text)
            qr, _ = run("zebra")
            check("canvas: a word on no layer finds no canvas hit",
                  not any(h.get("canvas") for h in qr["src"]["figma"]["hits"]))

            def boom(key):
                raise RuntimeError("planted failure")
            qr, text = run("mobile card", fetch=boom)
            check("figma that cannot be read is DID NOT RUN, exit 2, other hits still printed",
                  exit_code(qr) == 2 and "DID NOT RUN" in text and logs(qr))
            keep = {k: CONFIG[k] for k in ("figma_files", "ado", "notes_dirs", "transcripts", "figma_token", "ledger")}
            CONFIG.update(figma_files={}, ado=(None, None), notes_dirs=[], transcripts=[],
                          ledger=os.path.join(root, "no-ledger", "requests.jsonl"))
            try:
                qr, text = run("xyzzy-not-planted")
            finally:
                CONFIG.update(keep)
            check("a source with nothing configured says NOT CONFIGURED with the key to set, and leaves the exit 1",
                  exit_code(qr) == 1 and all(not qr["src"][n]["ran"] for n in ("figma", "ado", "notes", "transcripts"))
                  and text.count("NOT CONFIGURED, not searched") == 4 and "set figma.files" in text
                  and "set ado.org and ado.project" in text and "set recall.notes" in text)
            CONFIG["figma_token"] = ""
            try:
                qr, text = run("mobile card")
            finally:
                CONFIG.update(keep)
            check("figma configured with no token is DID NOT RUN, not 'not configured': exit 2",
                  exit_code(qr) == 2 and "figma        DID NOT RUN: no FIGMA_TOKEN" in text)
            qr, _ = run("#9162")
            check("ADO #N finds the item by id", [h["ids"] for h in qr["src"]["ado"]["hits"]] == [["ado:9162"]])
            qr, _ = run("stacked one")
            check("ADO comments are searched, HTML stripped", qr["src"]["ado"]["hits"])
            # #9162: created 8/01 as "Tabbed for now" (the planted asOf), today "Stacked rather than tabbed";
            # its comment "use the stacked one" was written 8/02.
            import shutil
            shutil.rmtree(asof_dir, ignore_errors=True)
            asof_calls.clear()
            qr, text = run("Tabbed for now", before="2026-08-15")
            gone, _ = run("Stacked rather than tabbed", before="2026-08-15")
            now, plain = run("Tabbed for now")
            hs = qr["src"]["ado"]["hits"]
            check("--before reads an ADO item as ADO held it then (asOf): its old title matches and its old state "
                  "shows, today's title does not, and COVERAGE says so; without --before only today's title counts",
                  [h["ids"] for h in hs] == [["ado:9162"]] and " Active " in hs[0]["head"]
                  and not gone["src"]["ado"]["hits"] and not now["src"]["ado"]["hits"]
                  and "ado: item fields as they were at 2026-08-15T00:00:00.000Z" in text
                  and "as they were at" not in plain and exit_code(qr) == 0)
            check("an asOf lookup is saved per cutoff: a second search at the same cutoff makes no call",
                  asof_calls.count("2026-08-15T00:00:00.000Z") == 1)
            import gzip
            used = os.path.join(asof_dir, "2026-08-15T00-00-00.000Z.json.gz")
            try:
                with gzip.open(used, "rt", encoding="utf-8") as fh:
                    kept = json.load(fh)["items"]["9162"]
            except (OSError, ValueError, KeyError):
                kept = {}
            again, _ = run("Tabbed for now", before="2026-08-15")
            seen = [[(h["head"], h["form"], h["excerpt"]) for h in r["src"]["ado"]["hits"]] for r in (qr, again)]
            check("a saved cutoff is gzip and keeps only what src_ado reads: the head fields, and each searchable "
                  "field as plain text, with no skipped field, other date or HTML; it finds what the fresh read found",
                  sorted(kept) == ["head", "segs"] and ["Description", "Tabs & panels"] in kept["segs"]
                  and "Title" in {s[0] for s in kept["segs"]} and "AreaPath" not in json.dumps(kept)
                  and "StateChangeDate" not in json.dumps(kept) and "data:image" not in json.dumps(kept)
                  and seen[0] and seen[0] == seen[1])
            v1 = os.path.join(asof_dir, "2026-08-16T00-00-00.000Z.json")
            os.makedirs(asof_dir, exist_ok=True)  # under a mutation nothing may have saved there yet
            with open(v1, "w", encoding="utf-8") as fh:
                json.dump({"cutoff": "2026-08-16T00:00:00.000Z", "items": asof("2026-08-16T00:00:00.000Z")}, fh)
            asof_calls.clear()
            qr, _ = run("Tabbed for now", before="2026-08-16")
            check("a cutoff saved in the old uncompressed form still reads, with no call, and is rewritten once "
                  "as gzip", [h["ids"] for h in qr["src"]["ado"]["hits"]] == [["ado:9162"]] and not asof_calls
                  and not os.path.exists(v1) and os.path.exists(v1 + ".gz"))
            # Over the cap the least recently used file goes first, and a read counts as a use.
            junk = os.path.join(asof_dir, "2026-07-01T00-00-00.000Z.json.gz")
            with open(junk, "wb") as fh:
                fh.write(os.urandom(50000))
            if os.path.exists(used):
                os.utime(used, (time.time() - 2 * 86400,) * 2)
            os.utime(junk, (time.time() - 86400,) * 2)
            run("Tabbed for now", before="2026-08-15")
            cap0 = CONFIG.get("ado_asof_max_mb")
            room = sum(os.path.getsize(os.path.join(asof_dir, n)) for n in os.listdir(asof_dir)) - 50000 + 5000
            CONFIG["ado_asof_max_mb"] = room / 1e6
            run("Tabbed for now", before="2026-08-17")
            CONFIG["ado_asof_max_mb"] = cap0
            check("the saved cutoffs are capped: over the cap the least recently used file goes first, a read "
                  "counts as a use, and the cutoff just saved stays", not os.path.exists(junk)
                  and os.path.exists(used) and os.path.exists(os.path.join(asof_dir, "2026-08-17T00-00-00.000Z.json.gz")))
            cut, _ = run("stacked one", before="2026-08-02")
            check("--before in ADO still cuts a comment written at or after the cutoff", not cut["src"]["ado"]["hits"])

            def down(c):
                raise RuntimeError("planted: no network")
            CONFIG["ado_asof"] = down
            qr, text = run("Stacked rather than tabbed", before="2026-08-20")
            CONFIG["ado_asof"] = asof
            check("an asOf lookup that cannot run matches today's fields, says NOT LIMITED by --before and DID NOT "
                  "RUN in COVERAGE, and exits 2", qr["src"]["ado"]["hits"] and "ado: NOT LIMITED by --before" in text
                  and re.search(r"asOf lookup DID NOT RUN \(RuntimeError: planted: no network\)", text)
                  and exit_code(qr) == 2)
            qr, _ = run("pstack")
            check("git commit message", qr["src"]["git"]["hits"])
            qr, _ = run("hero crop")
            check("git -S finds text only in a diff", [h["form"] for h in qr["src"]["git"]["hits"]] == ["diff"])
            check("git: with no matched file ignored (check-ignore exits 1), nothing reads DID NOT RUN",
                  not any("DID NOT RUN" in x for x in qr["src"]["git"]["partial"]))
            subj = lambda qr: sorted(h["head"].split("  ")[-1] for h in qr["src"]["git"]["hits"])  # noqa: E731
            qr, text = run("ZQCACHE")
            check("git -S: a cache file's add and its untrack, matched only in a file the clone now ignores, are not "
                  "hits; a tracked file holding the text is, and COVERAGE counts the 2 dropped: " + str(subj(qr)),
                  subj(qr) == ["zq step 3"] and "2 commit(s) dropped whose only matches are in files their clone now "
                                                "ignores (repo 1 of 2 paths)" in text)
            qr, _ = run("ZQFORCE")
            check("git -S: a force-added file an ignore rule names is tracked, so its commit is still a hit",
                  subj(qr) == ["zq step 4"])
            qr, _ = run("ZQSUB")
            check("git -S: a folder's own .gitignore counts, so its file's add and untrack are not hits",
                  subj(qr) == [])
            xdg = os.path.join(root, "xdg")
            os.makedirs(os.path.join(xdg, "git"), exist_ok=True)
            with open(os.path.join(xdg, "git", "ignore"), "w") as fh:
                fh.write("glob.txt\n")
            keep_xdg, os.environ["XDG_CONFIG_HOME"] = os.environ.get("XDG_CONFIG_HOME"), xdg
            qr, _ = run("ZQGLOBAL")
            if keep_xdg is None:
                os.environ.pop("XDG_CONFIG_HOME")
            else:
                os.environ["XDG_CONFIG_HOME"] = keep_xdg
            check("git -S: a rule only the user's global ignore file holds doesn't count; the clone's own rules do",
                  subj(qr) == ["zq step 7", "zq step 8"])
            qr, _ = run("ZQMIX")
            check("git -S: a commit that matched in an ignored file and a tracked one stays a hit; one that matched "
                  "only in the ignored file doesn't", subj(qr) == ["zq step 10"])
            bare = os.path.join(root, "repo-bare.git")
            if not os.path.exists(bare):
                subprocess.run(["git", "clone", "-q", "--bare", os.path.join(root, "repo"), bare], check=True,
                               capture_output=True)
            keep_repos, CONFIG["repos"] = CONFIG["repos"], [bare]
            qr, _ = run("ZQCACHE")
            CONFIG["repos"] = keep_repos
            check("git: a clone whose check-ignore can't run (a bare one) keeps its hits and says DID NOT RUN",
                  subj(qr) == ["zq step 1", "zq step 2", "zq step 3"]
                  and any(x.startswith("git check-ignore DID NOT RUN on repo-bare.git") for x in qr["src"]["git"]["partial"]))
            g_ = os.path.join(root, "repo")
            kept_, n_gone, ign_n = _unignored({(g_, "A"): {"s1": [b".cache.json"]},
                                               (g_, "B"): {"s1": [b"docs/real.md"], "s2": [b".cache.json"]}}, [])
            check("git: a commit one literal matched only in an ignored file and another in a tracked one stays, and "
                  "isn't counted as dropped", n_gone == 1 and kept_ == {(g_, "A"): set(), (g_, "B"): {"s1"}}
                  and ign_n == {g_: (1, 2)})
            picked = _picked(b"\x01" + b"a" * 40 + b"\0\n" + b"b" * 40 + b"\0x.md\0\x01" + b"c" * 40 + b"\0\nd/e f.md\0")
            check("git: the pickaxe's records parse by their \\x01 mark, so a path of 40 hex digits is a path",
                  picked == {"a" * 40: [b"b" * 40, b"x.md"], "c" * 40: [b"d/e f.md"]})
            qr, plain = run("Repo Enhancements")
            check("notes paragraph", qr["src"]["notes"]["hits"])
            qr, text = run("Repo Enhancements", before="2026-01-01")
            check("--before does not cut notes or memory, a file has no history: the hit stays and COVERAGE says "
                  "each is NOT LIMITED by --before; without --before it says nothing",
                  qr["src"]["notes"]["hits"] and all(f"{n}: NOT LIMITED by --before" in text for n in ("notes", "memory"))
                  and "NOT LIMITED by --before" not in plain)
            qr, _ = run("gamut spindle")
            check("a note paragraph found near, in a file whose first 400 uses of a word are far from it",
                  [h["form"] for h in qr["src"]["notes"]["hits"]] == ["near"])
            qr, _ = run("gatling-gatling")
            check("a note paragraph whose match starts inside a match that runs on from the paragraph before",
                  [h["head"].split("  ")[0].rsplit(":", 1)[1] for h in qr["src"]["notes"]["hits"]] == ["3"])
            qr, _ = run("spoolprobe")
            check("a note spelled with a long s is found by the case-blind match, as before the substring "
                  "pre-pass", len(qr["src"]["notes"]["hits"]) == 1)
            qr, _ = run("planted ledger crossfade")
            check("the request ledger is searched, one paragraph per request with its state",
                  [h["excerpt"].count("request, open") for h in qr["src"]["notes"]["hits"]] == [1])
            qr, _ = run("ledgerevidenceonly")
            check("a ledger request's settling reply is not searched there (the logs source has it)",
                  not qr["src"]["notes"]["hits"])
            qr, _ = run("Zephyr")
            check("memory card, named memory:<stem>", ["memory:project_x" in h["ids"]
                                                       for h in qr["src"]["memory"]["hits"]] == [True])
            qr, text = run("xyzzy-not-planted")
            check("nothing anywhere: exit 1", exit_code(qr) == 1)
            check("a cut zip whose log is held on disk prints UNREADABLE, SKIPPED and leaves that exit 1",
                  re.search(r"UNREADABLE, SKIPPED \S*/\.Trash/cut\.zip", text) and exit_code(qr) == 1)
            check("a nested ._ file that only ends in .zip prints NOT A ZIP, SKIPPED and leaves that exit 1",
                  "NOT A ZIP, SKIPPED 1 members" in text and exit_code(qr) == 1)
            fork = os.path.join(CONFIG["root"], "Downloads", "__MACOSX", "._loose.zip")
            os.makedirs(os.path.dirname(fork), exist_ok=True)
            with open(fork, "wb") as fh:
                fh.write(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X" + b"\0" * 196)
            qr, text = run("xyzzy-not-planted")
            os.remove(fork)
            check("a ._ file on disk that only ends in .zip prints NOT A ZIP, SKIPPED and leaves that exit 1",
                  re.search(r"NOT A ZIP, SKIPPED 1 files named \.zip .*__MACOSX/\._loose\.zip", text)
                  and exit_code(qr) == 1)
            whole = io.BytesIO()
            with zipfile.ZipFile(whole, "w") as zf:
                zf.writestr("x/%08x-0000-4000-8000-%012x.jsonl" % (98, 98), b'{"uuid":"n9"}\n')
            nest = os.path.join(CONFIG["root"], "Downloads", "nest.zip")
            os.makedirs(os.path.dirname(nest), exist_ok=True)
            with zipfile.ZipFile(nest, "w") as zf:
                zf.writestr("broken.zip", whole.getvalue()[:-22])              # its end record gone
            qr, text = run("xyzzy-not-planted")
            os.remove(nest)
            check("a nested zip that will not open is zip DID NOT READ: exit 2",
                  re.search(r"zip DID NOT READ: \S*/Downloads/nest\.zip: nested zip 'broken\.zip' could not be listed",
                            text) and exit_code(qr) == 2)
            held = os.path.join(CONFIG["root"], "Library", "Containers")
            os.makedirs(held, exist_ok=True)
            with cc_logs.find_times_out(held):
                qr, text = run("xyzzy-not-planted", refresh=True)
            check("a Library folder whose find times out is NOT SEARCHED: exit 2",
                  re.search(r"folder \S*/Library/Containers: NOT SEARCHED", text) and exit_code(qr) == 2)
            with cc_logs.find_quits(os.path.join(CONFIG["root"], "Downloads")):
                qr, text = run("xyzzy-not-planted", refresh=True)
            check("a folder whose find quits on fts_read, and again when rerun, is NOT SEARCHED in full: exit 2",
                  re.search(r"folder \S*/Downloads: NOT SEARCHED in full, find quit on fts_read.*"
                            r", and again when rerun alone", text) and exit_code(qr) == 2)
            with cc_logs.find_quits(os.path.join(CONFIG["root"], "Downloads"), times=1):
                qr, text = run("xyzzy-not-planted", refresh=True)
            check("a find that quits once and finishes when rerun alone leaves that exit 1",
                  "/Downloads and finished when rerun alone" in text and exit_code(qr) == 1)
            locked = os.path.join(CONFIG["root"], "Downloads", "locked")
            os.makedirs(locked, exist_ok=True)
            os.chmod(locked, 0)
            try:
                qr, text = run("xyzzy-not-planted")
            finally:
                os.chmod(locked, 0o755)
            os.rmdir(locked)
            check("a folder find may not read is named as could not be opened: exit 2",
                  re.search(r"folder could not be opened: \S*/Downloads/locked: Permission denied", text)
                  and exit_code(qr) == 2)
            only = cc_logs.plant_cut_zip(os.path.join(CONFIG["root"], "Downloads", "cut.zip"),
                                         [("x/%08x-0000-4000-8000-%012x.jsonl" % (99, 99), b'{"uuid":"c1"}\n'),
                                          ("media/v.mp4", b"m" * 500)])
            qr, text = run("xyzzy-not-planted")
            os.remove(only)
            check("a cut zip holding a log found nowhere else is zip DID NOT READ: exit 2",
                  re.search(r"zip DID NOT READ: \S*/Downloads/cut\.zip", text) and exit_code(qr) == 2)
            # A backup folder moved away mid-run must not take the whole logs source down.
            def scanned(text):
                m = re.search(r"scanned (\d+) of (\d+) copies", text)
                return m and tuple(map(int, m.groups()))
            qr, text = run("mobile card")
            gone = os.path.join(CONFIG["root"], "backups", ".claude.zip")
            n, held = scanned(text)[1], sum(c.path == gone for c in qr["src"]["logs"]["inv"].to_read())
            for ns, fn, when, want in ((vars(cc_logs), "_find", "after the walk lists it", (n - held, n - held)),
                                       (globals(), "_inventory", "before the scan opens it", (n - held, n))):
                with cc_logs.goes_away(gone, ns, fn):
                    qr, text = run("mobile card")
                check(f"a zip that goes away {when} is named once in COVERAGE as gone; every other copy is read, "
                      "its hits found: exit 2", qr["src"]["logs"]["ran"] and exit_code(qr) == 2
                      and held and scanned(text) == want and {"r1", "r2", "r3"} <= {h["id"] for h in logs(qr)}
                      and len(re.findall(r"zip DID NOT READ: \S*/backups/\.claude\.zip: gone before it was read",
                                         text)) == 1)
            # A folder that goes away while find walks it: a gap only if a log it held at the last run is found
            # nowhere this run. backups's zip holds 2 logs, neither of them byte for byte anywhere else.
            pcb, claude = os.path.join(CONFIG["root"], "backups"), os.path.join(CONFIG["root"], ".claude")
            for to, want, how in ((None, 2, "is a gap naming 2 of the 2 logs it held at the last run: exit 2"),
                                  (os.path.join(CONFIG["root"], ".Trash", "backups"), 1,
                                   "with each of its logs found elsewhere leaves that exit 1")):
                run("xyzzy-not-planted")                                       # the last run saw backups
                away = tempfile.mkdtemp()
                dest = to or os.path.join(away, "backups")
                os.replace(pcb, dest)
                try:
                    with cc_logs.find_quits(claude, error=f"{pcb}{cc_logs.GONE}"):
                        qr, text = run("xyzzy-not-planted", refresh=True)
                finally:
                    os.replace(dest, pcb)
                    os.rmdir(away)
                check(f"a folder that went away during the walk {how}", exit_code(qr) == want and (
                    len(re.findall(r"folder \S*/backups went away during the walk: 2 of the 2 logs it held at the"
                                   r" last run not found this run", text)) == 1 if want == 2
                    else "each found elsewhere" in text and "went away during the walk" in text))
            # A cloud-synced read that times out must not crash a source or be skipped silently: each source
            # names the file once and still reads the rest: exit 2.
            import builtins
            why = "could not be read: TimeoutError: [Errno 60] Operation timed out"
            once = lambda text, path: sum(path in ln and why in ln for ln in text.splitlines()) == 1
            qr, text = run("mobile card")
            want = {h["id"] for h in logs(qr)}
            quiet = next(c for c in qr["src"]["logs"]["inv"].to_read()
                         if c.via == "disk" and c.key[:36] not in {h["sid"] for h in logs(qr)})
            os.utime(quiet.path)                                         # changed since the last run: checksummed
            with cc_logs.times_out(quiet.path, vars(cc_logs), "_crc_file"):
                qr, text = run("mobile card")
            check("a log whose checksum read times out is log DID NOT READ with the error, once; the other logs'"
                  " hits are found: exit 2", qr["src"]["logs"]["ran"] and exit_code(qr) == 2
                  and {h["id"] for h in logs(qr)} == want and once(text, f"log DID NOT READ: {quiet.path}"))
            qr, _ = run("tzprobe")
            tdir, ndir = CONFIG["transcripts"][0], CONFIG["notes_dirs"][0]
            for name, path, gone, kept in (
                    ("transcripts", os.path.join(tdir, "transcript_2026-10-05_1030_Early.md"), "Early", "Late"),
                    ("notes", os.path.join(ndir, "tz-early.md"), "tz-early", "tz-late")):
                before = [h["ids"][0] for h in qr["src"][name]["hits"]]
                with cc_logs.times_out(path, vars(builtins), "open"):
                    qt, text = run("tzprobe")
                after = [h["ids"][0] for h in qt["src"][name]["hits"]]
                check(f"a {name} file whose read times out is DID NOT READ with the error, once; the rest are searched:"
                      " exit 2", qt["src"][name]["ran"] and exit_code(qt) == 2 and any(gone in i for i in before)
                      and not any(gone in i for i in after) and any(kept in i for i in after)
                      and once(text, path.replace(HOME, "~")) and len(qt["src"][name]["partial"]) == 1)
            # A folder holding a .recall-sealed marker, and the logs its patterns name, are held back from
            # every source.
            nd = CONFIG["notes_dirs"][0]
            subs = os.path.join(CONFIG["root"], ".claude", "projects", "S", u[0], "subagents")
            sealed_dir, zp, mem0 = os.path.join(nd, "exp-sealed"), os.path.join(root, "backups", "sealed.zip"), \
                list(CONFIG["memory_globs"])

            def put(path, data):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(data.encode() if isinstance(data, str) else data)

            def marker(name, until, pats, body=None):
                put(os.path.join(nd, name, SEAL), body if body is not None else json.dumps(
                    {"reason": f"planted {name}", "owner": "selftest", "until": until, "logs": pats}))

            def sub(aid, *texts):
                return "".join(json.dumps({"type": "user", "uuid": f"q-{aid}-{i}", "sessionId": u[0],
                                           "timestamp": "2026-09-15T10:00:00Z",
                                           "message": {"role": "user", "content": t}}) + "\n"
                               for i, t in enumerate(texts))

            def found(qr):
                return ({os.path.basename(h["ids"][0]) for n in ("notes", "memory") for h in qr["src"][n]["hits"]},
                        {h["id"] for h in logs(qr)})

            def hidden(qr, text):
                """The sealed folder's notes and every copy of the sealed subagent's log are not found, and
                COVERAGE names the seal with what it held back from each source."""
                files, ids = found(qr)
                return not files & {"held.md", "more.md"} and not any(i.startswith("q-sealed1-") for i in ids) \
                    and bool(re.search(rf"seal: {re.escape(sealed_dir.replace(HOME, '~'))} until 2999-12-31 "
                                       r"\(\"planted exp-sealed\", owner \"selftest\"\): not searched: 2 note files, "
                                       r"1 memory file, 0 transcripts, 2 log copies of 1 log;", text))
            try:
                marker("exp-sealed", "2999-12-31", ["agent-sealed1"])
                put(os.path.join(sealed_dir, "held.md"), "quince held-out check\n")
                put(os.path.join(sealed_dir, "deep", "more.md"), "quince sealed prediction\n")
                put(os.path.join(nd, "exp-open", "open.md"), "quince open note\n")
                marker("exp-old", "2020-01-01", ["agent-old1"])
                put(os.path.join(nd, "exp-old", "old.md"), "quince expired note\n")
                put(os.path.join(subs, "agent-sealed1.jsonl"), sub("sealed1", "quince sealed log"))
                put(os.path.join(subs, "agent-open1.jsonl"), sub("open1", "quince open log"))
                put(os.path.join(subs, "agent-old1.jsonl"), sub("old1", "quince expired log"))
                with zipfile.ZipFile(zp, "w") as zf:     # a backup copy with a record more, so it is read too
                    zf.writestr(f".claude/projects/S/{u[0]}/subagents/agent-sealed1.jsonl",
                                sub("sealed1", "quince sealed log", "quince only in the backup"))
                CONFIG["memory_globs"] = mem0 + [os.path.join(sealed_dir, "*.md")]   # memory reaching in
                qr, text = run("quince")
                files, ids = found(qr)
                check("a sealed folder's notes (memory reaching in too) and the subagent log its pattern names, on "
                      "disk and in a backup zip, are not found; COVERAGE names the seal with its counts, SUMMARY says "
                      "a seal is in force", hidden(qr, text) and "1 seal(s) in force" in text)
                check("an unsealed sibling folder and subagent log are still found",
                      "open.md" in files and "q-open1-0" in ids)
                sealed_key = f"{u[0]}/subagents/agent-sealed1.jsonl"
                got, keys = in_index("quince sealed log", "quince open log")
                check("a sealed log is never written to the index; an unsealed sibling is",
                      got == {"quince open log"} and sealed_key not in keys)
                check("an expired seal is ignored: its folder and log are found, and COVERAGE says it expired",
                      "old.md" in files and "q-old1-0" in ids
                      and "seal EXPIRED on 2020-01-01, ignored, so its folder and logs were searched as usual: "
                          + os.path.join(nd, "exp-old").replace(HOME, "~") in text)
                qs, stext = run("quince held-out")
                check("a term only sealed material holds is exit 1, as before, and SUMMARY and RECAP say a seal held "
                      "material back", exit_code(qs) == 1 and "1 seal(s) in force" in stext
                      and "seal(s) held material back" in stext)
                opts.include_sealed = True
                try:
                    qr, text = run("quince")
                finally:
                    opts.include_sealed = False
                files, ids = found(qr)
                got, keys = in_index("quince sealed log", "quince only in the backup")
                check("--include-sealed reads the sealed log whole and still writes none of it to the index",
                      not got and sealed_key not in keys)
                check("--include-sealed finds the sealed folder's notes and both copies of the sealed log, and "
                      "COVERAGE says it was used", {"held.md", "more.md"} <= files
                      and {"q-sealed1-0", "q-sealed1-1"} <= ids and "searched anyway: 2 note files" in text
                      and f"seal LIFTED by --include-sealed: {sealed_dir.replace(HOME, '~')} until 2999-12-31" in text)
                marker("exp-sealed", "2999-12-31", ["agent-sealed9"])           # known bad: names no log
                qr, text = run("quince")
                check("known bad: a marker whose logs pattern names no log copy fails the sealed-log check above "
                      "(its log is found), and COVERAGE names the pattern that matched nothing",
                      not hidden(qr, text) and any(i.startswith("q-sealed1-") for i in found(qr)[1])
                      and "1 of 1 logs patterns matched no log copy: 'agent-sealed9'" in text)
                was, _ = in_index("quince sealed log")
                marker("exp-sealed", "2999-12-31", ["agent-sealed1"])           # sealed again: deleted from the index
                qr, text = run("quince")
                got, keys = in_index("quince sealed log", "quince only in the backup")
                check("a log a new seal holds is deleted from the index at the next call, and not found",
                      was == {"quince sealed log"} and not got and sealed_key not in keys and hidden(qr, text))
                marker("exp-sealed", "", [], body="{not json")
                qr, text = run("quince")
                files, _ = found(qr)
                check("a marker that will not parse still seals its folder, and COVERAGE says it is unreadable",
                      not files & {"held.md", "more.md"} and "open.md" in files and "marker unreadable (" in text)
            finally:
                CONFIG["memory_globs"] = mem0
                for d in ("exp-sealed", "exp-open", "exp-old"):
                    shutil.rmtree(os.path.join(nd, d), ignore_errors=True)
                for p in [os.path.join(subs, f"agent-{a}.jsonl") for a in ("sealed1", "open1", "old1")] + [zp]:
                    if os.path.exists(p):
                        os.remove(p)
            # A claude -p capture (stream-json, no session log) is a log too, kind headless. A
            # script wrote its prompt, so no hit in it is "you"; a seal on its folder or its session holds it.
            caps = os.path.join(CONFIG["root"], "evalruns")
            cid = ["%08x-0000-4000-8000-%012x" % (n, n) for n in (71, 72, 73)]

            def capture(path, sid, *texts):
                put(path, json.dumps({"type": "system", "subtype": "init", "session_id": sid}) + "\n" + "".join(
                    json.dumps({"type": t, "uuid": f"c-{sid[:8]}-{i}", "session_id": sid,
                                "timestamp": "2026-09-16T10:00:00Z",
                                "message": {"role": t, "content": [{"type": "text", "text": x}]}}) + "\n"
                    for i, (t, x) in enumerate(texts)))
            try:
                capture(os.path.join(caps, "run1.jsonl"), cid[0], ("user", "persimmon batch prompt"),
                        ("assistant", "persimmon batch answer"))
                capture(os.path.join(nd, "exp-capseal", "run2.jsonl"), cid[1], ("user", "persimmon sealed folder"))
                capture(os.path.join(caps, "run3.jsonl"), cid[2], ("user", "persimmon sealed session"))
                marker("exp-capseal", "2999-12-31", [cid[2]])
                qr, text = run("persimmon")
                roles = {h["id"]: h["role"] for h in logs(qr)}
                check("a claude -p capture is searched as a log and its prompt is a claude -p record, never you; a seal"
                      " holds back one in its folder and one whose session it names",
                      roles.get(f"c-{cid[0][:8]}-0") == "claude -p: prompt"
                      and roles.get(f"c-{cid[0][:8]}-1") == "claude -p: assistant"
                      and not any(i.startswith((f"c-{cid[1][:8]}", f"c-{cid[2][:8]}")) for i in roles)
                      and not any(r.startswith("you") for r in roles.values()))
            finally:
                shutil.rmtree(caps, ignore_errors=True)
                shutil.rmtree(os.path.join(nd, "exp-capseal"), ignore_errors=True)
            return res

        def report(res):
            nonlocal ok
            for name, good in res:
                ok &= good
                print(("pass " if good else "FAIL ") + name)

        report(checks())
        # Pool and serial must agree.
        CONFIG["workers"] = 2
        opts.serial = False
        sp = json.dumps({"mode": "search", "mut": [], "queries": [{"labels": ["mobile card"], "since": None,
                                                                   "before": None}]})
        _, copies, _ = _inventory(opts)
        a = sorted((r["key"], h["id"]) for r in _pool(sp, copies) for h in r["hits"])
        b = sorted((r["key"], h["id"]) for r in _pool(sp, copies, serial=True) for h in r["hits"])
        good = a == b and len(a) >= 3 and len(_tasks(copies)) > 1
        ok &= good
        print(("pass " if good else "FAIL ") + f"process pool and serial scan agree ({len(a)} hits, "
              f"{len(_tasks(copies))} tasks)")
        # Notes, memory and transcripts in processes of their own (PROC_SOURCES), and the logs scan in the pool
        # search() starts early, find what they find in threads.

        def found(labels):
            qr = search([{"labels": labels, "since": None, "before": None}], opts)[0]
            return {n: sorted((h.get("head") or h.get("label", ""), h["excerpt"]) for h in r["hits"])
                    for n, r in qr["src"].items() if n in PROC_SOURCES + ("logs",)}
        probes = (["Repo Enhancements"], ["tzprobe"], ["mobile card"], ["Zephyr"])
        procs = [found(lb) for lb in probes]
        opts.serial = True
        threads = [found(lb) for lb in probes]
        opts.serial = False
        good = procs == threads and all(any(p[n] for p in procs) for n in PROC_SOURCES + ("logs",))
        ok &= good
        print(("pass " if good else "FAIL ") + "notes, memory and transcripts in processes and the logs scan in the "
              f"early pool find what threads find ({[{n: len(v) for n, v in p.items()} for p in procs]})")
        # A sandbox that denies multiprocessing's semaphores: every pool start raises PermissionError, as
        # CPython's _check_system_limits does there. The search runs in this process, says so once on stderr,
        # and finds what the pooled run found.
        import concurrent.futures
        import contextlib
        global NO_POOL

        def denied(*a, **k):
            raise PermissionError(1, "Operation not permitted")
        kept_pool, kept_cf = globals()["ProcessPoolExecutor"], concurrent.futures.ProcessPoolExecutor
        globals()["ProcessPoolExecutor"] = concurrent.futures.ProcessPoolExecutor = denied
        err, crashed = io.StringIO(), None
        try:
            NO_POOL = None
            with contextlib.redirect_stderr(err):
                nopool = [found(lb) for lb in probes]
                scan = sorted((r["key"], h["id"]) for r in _pool(sp, copies) for h in r["hits"])
            NO_POOL = None
            MUT.add("no_pool_fallback")
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    found(probes[0])
            except PermissionError as e:
                crashed = e
            finally:
                MUT.discard("no_pool_fallback")
        finally:
            globals()["ProcessPoolExecutor"], concurrent.futures.ProcessPoolExecutor = kept_pool, kept_cf
            NO_POOL = None
        said = err.getvalue().splitlines()
        good = (nopool == procs and scan == a and len(said) == 1 and "without the process pool" in said[0]
                and "PermissionError" in said[0])
        ok &= good
        print(("pass " if good else "FAIL ") + "a pool that can't start (PermissionError) runs the search and the logs "
              f"scan in this process, finds what the pooled run found, and says so once on stderr ({said[:2]})")
        good = crashed is not None
        ok &= good
        print(("pass " if good else "FAIL ") + "planted break: with the fallback off, the same denied pool crashes "
              "the search")
        CONFIG["workers"] = 1
        opts.serial = True
        # --last
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_last("/rebase", opts)
        good = code == 0 and "2 invocation(s)" in buf.getvalue()
        ok &= good
        print(("pass " if good else "FAIL ") + "--last finds the typed command and the history entry; a scripted "
              "one is not counted")
        good = f"in {u[0][:8]}," in buf.getvalue().split("\nLAST: ")[-1].splitlines()[0]
        was = os.environ.get("CLAUDE_CODE_SESSION_ID")
        os.environ["CLAUDE_CODE_SESSION_ID"] = u[0]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cmd_last("/rebase", opts)
        finally:
            if was is None:
                os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            else:
                os.environ["CLAUDE_CODE_SESSION_ID"] = was
        last = buf.getvalue().split("\nLAST: ")[-1]
        good = good and code == 0 and last.startswith("2025-09-15T10:01Z") and "is not counted" in last
        ok &= good
        print(("pass " if good else "FAIL ") + "--last from another session names that session's run; from the "
              "session that ran it, the run before it, and says it left its own out")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_last("/standup", opts)
        good = code == 0 and "/standup: 3 invocation(s)" in buf.getvalue()
        ok &= good
        print(("pass " if good else "FAIL ") + "--last counts two typed runs a minute apart and a Skill call; a tool "
              "result, summary, skill expansion, pasted quote, subagent record or denied tool call quoting the tags "
              "is not one")
        scan0 = _last_scan

        def stops(data, kind, name, r):
            if b'"r40"' in data:
                raise ValueError("planted")
            scan0(data, kind, name, r)
        globals()["_last_scan"] = stops
        try:
            sbuf = io.StringIO()
            with contextlib.redirect_stdout(sbuf):
                scode = cmd_last("/rebase", opts)
        finally:
            globals()["_last_scan"] = scan0
        good = scode == 2 and "copy not fully read: " in sbuf.getvalue() and "ValueError: planted" in sbuf.getvalue() \
            and "/rebase: 1 invocation(s)" in sbuf.getvalue()
        ok &= good
        print(("pass " if good else "FAIL ") + "--last: a log whose scan stops partway is named once and exits 2, "
              "and the other logs are still read")
        out = buf.getvalue()
        good = "+3 load(s) by Claude Code itself, not counted" in out and "'autoload (ultra effort)'" in out \
            and "'autoload (workflow keyword)'" in out
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_last("/workflow-authoring", opts)
        good &= code == 1 and "No invocation of /workflow-authoring." in buf.getvalue() \
            and "+1 load(s) by Claude Code itself" in buf.getvalue()
        ok &= good
        print(("pass " if good else "FAIL ") + "--last lists, uncounted, a skill Claude Code loaded by itself, with "
              "its trigger, even with no invocation; a load the model's Skill call made is that call")
        good = "+2 call(s) by subagents, not counted" in out and "'subagent Skill tool, args: x'" in out \
            and "'subagent Skill tool, args: from the agent'" in out
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_last("/qa-audit", opts)
        good &= code == 1 and "No invocation of /qa-audit." in buf.getvalue() \
            and "+1 call(s) by subagents, not counted" in buf.getvalue()
        ok &= good
        print(("pass " if good else "FAIL ") + "--last lists, uncounted, a Skill call a subagent made, in a subagent "
              "log or as a sidechain record, even with no invocation")
        opts.max = 1
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_last("/standup", opts)
        opts.max = None
        parts = re.split(r"load\(s\) by Claude Code itself|call\(s\) by subagents", buf.getvalue())
        good = len(parts) == 3 and "(+2 earlier: --max N" in parts[0] and all(
            "earlier: --max N" in part and part.count("\n  2026-09-20T") == 1 for part in parts)
        ok &= good
        print(("pass " if good else "FAIL ") + "--last names the invocations, loads and subagent calls its lists "
              "leave out")

        # A file that goes away mid-run is named, exit 2: not a crash, and not "No invocation" as exit 1.
        def last_while_gone(cmd, path, ns, fn):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), cc_logs.goes_away(path, ns, fn):
                try:
                    code = cmd_last(cmd, opts)
                except Exception as e:
                    code = f"crashed: {type(e).__name__}"
            return code, buf.getvalue()
        log = os.path.join(root, ".claude", "projects", "S", f"{u[0]}.jsonl")
        zipped = os.path.join(root, "backups", ".claude.zip")
        named = lambda out, path, why: sum(path in ln and why in ln for ln in out.splitlines()) == 1 \
            and sum(path in ln for ln in out.splitlines()) == 1
        code, out = last_while_gone("/standup", log, globals(), "_pool")
        good = code == 2 and "/standup: 3 invocation(s)" in out and named(out, log, "gone before its write time")
        ok &= good
        print(("pass " if good else "FAIL ") + "--last: a log that goes away after the scan read it still counts its "
              "invocations, is named once, and makes the exit 2")
        code, out = last_while_gone("/standup", zipped, globals(), "_inventory")
        good = code == 2 and "/standup: 3 invocation(s)" in out and named(out, zipped, "gone before it was read")
        ok &= good
        print(("pass " if good else "FAIL ") + "--last: a zip that goes away before the scan opens it is named once, "
              "however many copies it held: exit 2")
        code, out = last_while_gone("/xyzzy", zipped, vars(cc_logs), "_find")
        good = code == 2 and "No invocation of /xyzzy." in out and named(out, zipped, "gone before it was read")
        ok &= good
        print(("pass " if good else "FAIL ") + "--last: a zip that goes away after the walk lists it is named, and "
              "'No invocation' is exit 2, not 1")
        # --last on a log whose checksum read times out.
        os.utime(log)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), cc_logs.times_out(log, vars(cc_logs), "_crc_file"):
            try:
                code = cmd_last("/standup", opts)
            except Exception as e:
                code = f"crashed: {type(e).__name__}"
        out = buf.getvalue()
        good = code == 2 and "invocation(s)" in out and named(out, log, "could not be read: TimeoutError")
        ok &= good
        print(("pass " if good else "FAIL ") + "--last: a log whose checksum read times out is named once with the "
              f"error, the rest are read: exit 2 (got {code})")
        # --calibrate: a miss whose own file was not read is not a recall miss.
        import builtins
        cal = os.path.join(root, "calibration.json")
        with open(cal, "w", encoding="utf-8") as fh:
            json.dump([{"id": "T1", "terms": ["tzprobe"], "expect": ["transcript:2026-10-05 Early"]}], fh)
        early = os.path.join(CONFIG["transcripts"][0], "transcript_2026-10-05_1030_Early.md")

        def calibrate(timeout, rule=None):
            buf, real = io.StringIO(), globals()["_unread_ids"]
            if rule:
                globals()["_unread_ids"] = rule
            try:
                with contextlib.redirect_stdout(buf), (cc_logs.times_out(early, vars(builtins), "open")
                                                       if timeout else contextlib.nullcontext()):
                    return cmd_calibrate(cal, opts), buf.getvalue()
            finally:
                globals()["_unread_ids"] = real
        got = [calibrate(False), calibrate(True), calibrate(True, rule=lambda qr, s: set())]
        good = ([c for c, _ in got] == [0, 2, 1] and "1 of 1 expected" in got[0][1]
                and "in a file it could not read: transcripts (the file holding it was not read)" in got[1][1])
        ok &= good
        print(("pass " if good else "FAIL ") + "--calibrate: a miss whose transcript could not be read is exit 2, "
              "named as not read; read, it is found (0); the old rule called it a recall miss (1): got "
              f"{[c for c, _ in got]}")
        # Mutations: break one rule at a time; at least one check must fail.
        for m in ("no_variants", "no_decode_path", "no_dedup", "no_zip", "meta_counts", "no_redact", "no_instance_id",
                  "no_utc", "no_asof", "no_seal", "no_seal_notes", "no_seal_logs", "off_is_gap", "index_writes_sealed",
                  "whole_file_match", "no_fold_check", "finditer_places", "queued_reminders", "no_some_index",
                  "no_some_raw", "some_beats_diff", "you_counts_leads"):
            MUT.clear()
            MUT.add(m)
            _CACHE.clear()
            CONFIG["index"] = os.path.join(root, "index", f"{m}.db")   # each broken rule builds its own index
            failed = [n for n, g in checks() if not g]
            good = bool(failed)
            ok &= good
            print(("pass " if good else "FAIL ") + f"mutation {m} is caught" + (f" by: {failed[0]}" if failed else ""))
        MUT.clear()
        _CACHE.clear()
    CONFIG.clear()
    CONFIG.update(saved)
    figma_family.CACHE, figma_family._get = fam_saved
    for n, m in real_mods.items():
        if m is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = m
    if tz_saved is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = tz_saved
    time.tzset()

    def parsed(*argv):
        """parse(argv) as on the command line, or the error text it exits with."""
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                return parse(list(argv))
        except SystemExit:
            return err.getvalue()
    for name, good in (("a flag glued to its value in one argument (\"--since 2026-10-03\") is refused, saying to split it",
                        "its value as two words" in str(parsed("term", "--since 2026-10-03"))),
                       ("a term that starts with -- but is not a recall flag (-- --no-verify) is searched",
                        getattr(parsed("term", "--", "--no-verify"), "concepts", None) == ["term", "--no-verify"]),
                       ("a flag and its value as two words set the filter (--since 2026-10-03)",
                        getattr(parsed("term", "--since", "2026-10-03"), "since", None) == "2026-10-03")):
        ok &= good
        print(("pass " if good else "FAIL ") + "parse: " + name)
    ok &= selftest_brief()
    ok &= selftest_rank()
    ok &= selftest_settings()
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def selftest_settings():
    """recall.notes_files and recall.memory_globs, from a planted config."""
    ok, saved, env = True, dict(CONFIG), os.environ.get(kit_config.ENV)
    with tempfile.TemporaryDirectory() as t:
        def put(rel, text):
            p = os.path.join(t, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(text)
            return p
        one = put("runs/a/README.md", "same write-up")
        put("runs/b/README.md", "same write-up")
        other, top = put("runs/c/README.md", "another write-up"), put("WORKSPACE.md", "the map")
        cfg = os.path.join(t, "cfg.json")
        CONFIG.update(notes_files=[], ledger=os.path.join(t, "no-ledger.jsonl"))
        try:
            os.environ[kit_config.ENV] = cfg
            json.dump({"recall": {"notes_files": [top, os.path.join(t, "runs", "*", "README.md"),
                                                  os.path.join(t, "missing.md")],
                                  "memory_globs": [os.path.join(t, "skills", "*.md")]}}, open(cfg, "w"))
            kit_config.reset()
            got, mem = _note_files(), memory_globs()
            json.dump({}, open(cfg, "w"))
            kit_config.reset()
            unset_files, unset_mem = _note_files(), memory_globs()
            open(cfg, "w").write('{"recall": {"notes": "x"')       # settings that will not load
            kit_config.reset()
            seal_runs = {}
            for how, lift, mut in (("unread", False, set()), ("lifted", True, set()),
                                   ("broken", False, {"no_settings_check"})):
                sealing.MUT.clear()
                sealing.MUT.update(mut)
                try:
                    find_seals(argparse.Namespace(include_sealed=lift))
                    seal_runs[how] = "ran"
                except sealing.Unknown as e:
                    seal_runs[how] = str(e)
                finally:
                    sealing.MUT.clear()
            idx = os.path.join(t, "idx", "index.db")
            upd = recall_index.update(idx, 1, quiet=True), os.path.exists(os.path.dirname(idx))
        finally:
            CONFIG.update(saved)
            if env is None:
                os.environ.pop(kit_config.ENV, None)
            else:
                os.environ[kit_config.ENV] = env
            kit_config.reset()
        for name, good in (
                ("recall.notes_files: a path and a glob are read, a byte-identical copy once and a missing file not",
                 got == [top, one, other]),
                ("... and unset, no single files", unset_files == []),
                ("recall.memory_globs replaces the memory list, so a memory folder it leaves out isn't read",
                 mem == [os.path.join(t, "skills", "*.md")]),
                ("... and unset, every project's memory folder is read",
                 any(os.sep + "memory" + os.sep in g for g in unset_mem) and unset_mem == saved["memory_globs"]),
                ("settings that will not load: the seal markers are unknown, so the seal walk refuses, naming the file",
                 cfg.replace(sealing.HOME, "~") in seal_runs["unread"] and "could not be read" in seal_runs["unread"]),
                ("... and with the rule broken, the walk runs on with no marker folder",
                 seal_runs["broken"] == "ran"),
                ("... --include-sealed lifts every seal anyway, so the walk runs", seal_runs["lifted"] == "ran"),
                ("... and recall_index update writes nothing, exit 2, not even the index's folder",
                 upd == (2, False))):
            ok &= good
            print(("pass " if good else "FAIL ") + "settings: " + name)
    return ok


# ------------------------------------------------------------------------------------------------- main

def parse(argv=None):
    """The command line, refused with exit 2 as argparse refuses. A flag glued to its value in one argument
    ("--since 2026-10-03") reads to argparse as a concept, and the filter would silently not apply."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("concepts", nargs="*", help="each one must match; | separates alternatives inside one")
    ap.add_argument("--source", help="comma list of " + ",".join(SOURCES) + " (default: all)")
    ap.add_argument("--since", help="only records on or after YYYY-MM-DD[THH:MM], UTC unless it ends in Z or an "
                                    "offset such as -05:00")
    ap.add_argument("--before", help="only records before YYYY-MM-DD[THH:MM] (what was knowable then), UTC unless "
                                     "it ends in Z or an offset such as -05:00")
    ap.add_argument("--everything", action="store_true",
                    help="every session and record, and hits only in reminders or harness records")
    ap.add_argument("--max", type=int, help="sessions (logs) and records (other sources) to print; default 8 and 5;"
                                            " with --last, invocations to list, default 8")
    ap.add_argument("--out", help="also write the full, uncapped report to this file")
    ap.add_argument("--include-sealed", action="store_true",
                    help="also search the folders and logs a .recall-sealed marker holds back (for the experiment's "
                         "owner); COVERAGE says it was used")
    ap.add_argument("--no-pull", action="store_true", help="search the ADO cache as it is, even if stale")
    ap.add_argument("--refresh", action="store_true", help="re-read every zip listing and checksum")
    ap.add_argument("--serial", action="store_true", help="scan logs in this process (debugging)")
    ap.add_argument("--scan", action="store_true", help="read every log copy whole instead of through the index "
                                                       "(recall_index.py)")
    ap.add_argument("--last", metavar="COMMAND", help="every invocation of a command or skill, e.g. /rebase")
    ap.add_argument("--brief", action="store_true", help="your words, the live sessions and earlier work on the "
                                                         "concepts: what to read before answering")
    ap.add_argument("--calibrate", metavar="FILE",
                    help="run a past-miss set (JSON, see above) and print N of M expected answers found")
    ap.add_argument("--memory", metavar="DIR",
                    help="search this memory folder in place of every project's (e.g. ~/.claude/projects/<project>/memory)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_intermixed_args(argv)
    flags = {s for act in ap._actions for s in act.option_strings}
    for c in a.concepts:
        word = re.split(r"[\s=]", c.strip(), maxsplit=1)[0]
        if word in flags and word != c.strip():  # a term after --, even "--no-verify" or "--since", is searched
            ap.error(f"{c!r} is one argument, so {word} would not apply: pass the flag and its value as two words")
    a.sources = tuple(s.strip() for s in a.source.split(",")) if a.source else SOURCES
    bad = [s for s in a.sources if s not in SOURCES]
    if bad:
        ap.error(f"unknown source {', '.join(bad)}; choose from {', '.join(SOURCES)}")
    if a.memory:
        a.memory = cc_logs.memory_dir(a.memory) if hasattr(cc_logs, "memory_dir") else \
            os.path.abspath(os.path.expanduser(a.memory))
    for flag in ("since", "before"):
        try:
            _cut(getattr(a, flag))
        except ValueError as e:
            ap.error(f"--{flag}: {e}")
    if not (a.concepts or a.selftest or a.last or a.calibrate):
        ap.error("give at least one concept, or --last, --calibrate or --selftest")
    return a


def main():
    a = parse()
    if a.selftest:
        return kit_config.run_isolated(selftest)
    if a.last:
        return cmd_last(a.last, a)
    if a.calibrate:
        return cmd_calibrate(a.calibrate, a)
    if a.brief:
        return cmd_brief(a.concepts, a)
    qr = search([{"labels": a.concepts, "since": a.since, "before": a.before, "some": True}], a)[0]
    for line in render(qr, a, link=True):
        print(line)
    if a.out:
        write_atomic(a.out, "\n".join(render(qr, a, full=True, link=True)) + "\n")
        print(f"full report: {a.out}")
    return exit_code(qr)


if __name__ == "__main__":
    sys.exit(main())
