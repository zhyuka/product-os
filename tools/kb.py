"""kb.py - what is known about each body of work: cited entries, one page per body, that a daily check can fail.

    python tools/kb.py add --body <slug> --subject <key> --question "<words>" [--question-from <ledger id>]
                           --answer "<claim>" --cite "<citation>" [--cite ...] [--replaces <id>]
                           [--handback <agent id> | --correction <ledger id>]
    python tools/kb.py none --handback <agent id> ... | --correction <ledger id> ... --why "<reason>" [--cite ...]
    python tools/kb.py check [--body <slug>] [--record] [--new] [--json]
    python tools/kb.py show <slug | subject | id>
    python tools/kb.py --selftest

Each command takes --project DIR, the project whose settings count (default $CLAUDE_PROJECT_DIR, else the
working folder; never a folder inside the plugin's own, where it refuses in one line, exit 2).

WHY THIS EXISTS. A note nobody re-checks goes on reading as true after its source has moved. Each entry here
names sources a check can fail, so a fact whose source moved goes red instead of staying quietly wrong.

SETTINGS (kit_config, docs/config.md), each optional:
  kb.root      the folder a citation's relative path and a rule's glob start from (default: the project
               folder, as kit_config finds it)
  kb.dir       the store: index.md and one page per body (default knowledge/ under kb.root)
  kb.rules     the pointer rules (default .claude/rules under kb.root)
  kb.private   folders under kb.root that are never a source and that no rule may reach into, such as a
               folder of your own files nobody audits (default: none)
  kb.cache     where check --record and --new keep their state (default ~/.cache/product-os/kb). Outside
               the store, since a search over notes would read a .json there as a note
Read as well: ledger.dir (the request ledger ledger.py writes, requests.jsonl), logs.backups (cc_logs.py's
backup folders, whose copies are logs) and transcripts.dir, recall.transcripts or seen_before.transcripts
(meeting transcripts). The ADO cache is ado_rest.py's and each Figma index is figma_family.py's.

THE STORE. kb.dir holds index.md and one page per body of work, <slug>.md. A body's index line is `- [Name](slug.md):
what it is. Canonical: ... Name traps: ...`, and the alias lines under it (`  - alias: Billing = Billing Engine |
#4242  (since 2025-01-06, ADO #4242)`) are in the form recall.py reads (its NAMED_RX): set recall.aliases to this
index.md and recall finds a body by its other names. A page says what the body is and links its existing homes,
then holds its live entries under `## Entries`. A page whose frontmatter says `entries: none` (a body nobody
audits, such as your own files) takes no entry and wants no rule.

AN ENTRY settles one question about one subject:

    ### billing.naming
    - id: k-0001; status: live; written: 2025-01-07; by: local_1234abcd
    - question: "is it billing or billing engine" (their words, ledger r-77)
    - answer: The site says Billing Engine; ADO #4242 renamed every bare Billing.
    - source: ado 4242 rev 9
    - source: file `docs/plan.md` "The real link is the ledger"

The subject key is `<body slug>.<topic>`, and only one live entry may hold it. The question is in the user's
words when --question-from names the ledger row they are in, and `phrased by the writer` otherwise. Only the
user's own words count (user_words): a typed or mid-turn row's text, or a card's answer they typed. A card's
question and the labels it offered are the session's, and a spawned or chip row isn't the user typing.
Each source is a citation `check` can fail:

    file `<path>` "<anchor>"               the anchor, whitespace collapsed, is in the file now
    commit `<repo>` <sha>                  the clone has the commit
    commit `<repo>` <sha> `<path>` "<a>"   and the anchor is in that file at the clone's HEAD
    ado <id> rev <n>                       the ADO cache holds the item at revision n
    ado <id> <field> "<anchor>"            the anchor is in that field of the cached item now (below)
    figma <file key> <node> ["<anchor>"]   figma_family's index of the file has the node (and the
                                           anchor in its name or the text on it or under it)
    sha256 `<path>` <hex>                  the file hashes to it now
    ledger <id> ["<quote>"]                the request ledger has the row, and the quote is in it

Paths are from kb.root, absolute, or from ~. Never a source, because a check of it can never fail or the folder
is kept out: a session log or memory card (cc_logs.py's path shapes, the .claude projects folders and the
logs.backups folders), the ledger file cited as a file (cite `ledger <id>`), and anything under a kb.private
folder. A meeting transcript never changes either, so it can't be an entry's only source.

AN ADO FIELD. A rev cite fails on any edit, and most edits touch no content: most revisions to an item after it
closes change only links, comments, board columns or sprints. A field cite fails only when its text moves. The
field is title, description (a Bug's Repro Steps too), acceptance, comments (any comment), state, type,
iteration, tags, created or closed, or any field reference name the item holds (System.AreaPath). HTML is
stripped as `ado_rest.py show` prints it, whitespace collapsed and case aside. A text field holds the anchor
anywhere; state and type equal it; iteration's whole path or its last part equals it; tags hold it as one whole
tag; a date starts with it; a person is their display name. Blind: a later comment or an UPDATE appended to a
description can reverse the fact and leave the anchor in place, so ADO comments, alone or with transcripts,
can't be an entry's only source. A rev cite that goes red is re-cited in this form with --replaces.

ADD writes one entry. It refuses an entry with no source, a source that fails now, a source above, an unknown
body or one that takes no entries, a question that isn't in the user's words in the row --question-from names, a
second live entry on a subject unless --replaces names the live one, and a new subject settling a question (case
aside) or citing an anchor (or a ledger row and quote) a live entry already does. A replaced entry leaves its
page: log.jsonl keeps it, and `show` finds it there. Pages hold only what is true now, since a search that reads
them as notes takes them as current.

CHECK reports N of M live entries passing and names each miss: a moved anchor, a missing file, an unknown commit,
a moved ADO revision or an anchor gone from its ADO field, a dead Figma node, a changed hash, a missing ledger
row or quote, a question no longer in the user's words, and an entry with no passing check in STALE_DAYS (a
source that could not run keeps it unverified: an ADO cache older than ADO_DAYS or behind the citation, a Figma
index older than FIGMA_DAYS or missing). Faults: a duplicate live subject, a question or anchor two live entries
share, an entry it can't parse or on a page that takes none, an orphan page, an index body with no page, and
each pointer rule in kb.rules (searched to any depth, as Claude Code does) that isn't one it can trust to load
only where it should: frontmatter other than `paths:` and double-quoted globs (Claude Code loads a rule whose
YAML doesn't parse in every session), a glob matching no file or reaching into a kb.private folder, an @ import
(one loads at start whatever paths says), and for a body's rule: 3 to 6 lines, its page and recall named, and
the index's name traps word for word. --record (the daily run) writes each passing entry's time and each body's
counts to checked.json in kb.cache, for a tool that shows a body to print beside it; the pages don't change
daily. --new is red only for a miss or fault the last --new run didn't list. Exit 0 all pass, 1 a miss or
fault, 2 did not run.

FILING BACK. The session that spawned a challenger or research agent files from the hand-back it holds, since
the agent's own definition stays unchanged: `add --handback <agent id>` for each finding worth an entry, or
`none --handback <id> --why` when nothing in it is. A correction the user typed goes the same way with
--correction <ledger id>, which must be a row in their words; one fixed in its proper home (a gate, a rule line)
is a `none` whose --cite, in add's syntax, says where, checked when written. Both write a log.jsonl row naming
the id; `filed()` returns them, so a session-close check can list a hand-back or a correction with no row at or
after it. A `none` with no --cite is marked apart there (bare).

History: the store need not be in a git repo, so every add appends the whole entry to log.jsonl.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse
import contextlib
import datetime as dt
import fcntl
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

TOOLS = os.path.dirname(os.path.realpath(__file__))
if TOOLS not in sys.path:
    if TOOLS not in sys.path: sys.path.append(TOOLS)
import kit_config  # noqa: E402

PROJECT = None   # --project: the project kit_config reads, in place of $CLAUDE_PROJECT_DIR or the working folder
# Where each part reads. None: from kit_config at run time (the accessors below). The selftest plants each one.
CONFIG = {
    "root": None,          # kb.root, else the project folder
    "dir": None,           # kb.dir, else <root>/knowledge
    "rules": None,         # kb.rules, else <root>/.claude/rules
    "private": None,       # [folder]: kb.private, else none
    "cache": None,         # kb.cache, else ~/.cache/product-os/kb
    "ledger": None,        # <ledger.dir>/requests.jsonl, where ledger.py writes it
    "log_dirs": None,      # [folder]: logs.backups, as cc_logs.py reads it
    "transcripts": None,   # [folder]: transcripts.dir, recall.transcripts or seen_before.transcripts
    "ado_cache": None,     # ado_rest.CACHE
    "figma_cache": None,   # figma_family.CACHE
}
ADO_DAYS, FIGMA_DAYS, STALE_DAYS = 3, 7, 30
RULE_LINES = (3, 6)
# cc_logs.shape finds a log by its file name anywhere; this is the folder around one (memory cards too).
LOG_RX = re.compile(r"/\.claude[^/]*/projects/")
SUBJECT_RX = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9.-]*$")
BODY_RX = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<page>[a-z0-9-]+)\.md\):\s*(?P<rest>.*)$")
CITE_RX = {
    "file": re.compile(r'^file `(?P<path>[^`]+)` "(?P<anchor>[^"]+)"$'),
    "commit": re.compile(r'^commit `(?P<repo>[^`]+)` (?P<sha>[0-9a-f]{7,40})(?: `(?P<path>[^`]+)` "(?P<anchor>[^"]+)")?$'),
    "ado": re.compile(r'^ado (?P<id>\d+) (?:rev (?P<rev>\d+)|(?P<field>[A-Za-z][\w.]*) "(?P<anchor>[^"]+)")$'),
    "figma": re.compile(r'^figma (?P<key>[A-Za-z0-9]{10,}) (?P<node>[0-9I][0-9:;I-]*)(?: "(?P<anchor>[^"]+)")?$'),
    "sha256": re.compile(r"^sha256 `(?P<path>[^`]+)` (?P<hex>[0-9a-f]{64})$"),
    "ledger": re.compile(r'^ledger (?P<id>\S+)(?: "(?P<quote>[^"]+)")?$'),
}

# An ADO field cite's short names, its fields and how the anchor matches. description reads a Bug's Repro Steps
# too: a Bug usually keeps its text there and leaves Description empty.
ADO_FIELDS = {
    "title": (("System.Title",), "text"),
    "description": (("System.Description", "Microsoft.VSTS.TCM.ReproSteps"), "text"),
    "acceptance": (("Microsoft.VSTS.Common.AcceptanceCriteria",), "text"),
    "comments": ((), "text"),
    "state": (("System.State",), "exact"),
    "type": (("System.WorkItemType",), "exact"),
    "iteration": (("System.IterationPath",), "path"),
    "tags": (("System.Tags",), "tag"),
    "created": (("System.CreatedDate",), "date"),
    "closed": (("Microsoft.VSTS.Common.ClosedDate",), "date"),
}
ADO_REF = {r: name for name, (refs, _) in ADO_FIELDS.items() for r in refs}   # a reference name to its short name


# ---- settings

def _get(*keys):
    return kit_config.get(*keys, start=PROJECT)


def _cfg(*keys):
    v = _get(*keys)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _folders(v):
    v = [v] if isinstance(v, str) else (v if isinstance(v, (list, tuple)) else [])
    return [x for x in v if isinstance(x, str) and x.strip()]


def _abs(p, base):
    p = os.path.expanduser(p.strip())
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))


def root():
    """kb.root (absolute, from ~, or from the project folder), else the project folder."""
    if CONFIG["root"] is not None:
        return CONFIG["root"]
    v = _cfg("kb", "root")
    if v and os.path.isabs(os.path.expanduser(v)):
        return os.path.normpath(os.path.expanduser(v))
    return _abs(v or ".", kit_config.project_dir(PROJECT))


def kb_dir():
    return CONFIG["dir"] if CONFIG["dir"] is not None else _abs(_cfg("kb", "dir") or "knowledge", root())


def rules_dir():
    return CONFIG["rules"] if CONFIG["rules"] is not None else _abs(_cfg("kb", "rules") or os.path.join(".claude", "rules"), root())


def private_dirs():
    if CONFIG["private"] is not None:
        return CONFIG["private"]
    return [_abs(p, root()) for p in _folders(_get("kb", "private"))]


def cache_dir():
    if CONFIG["cache"] is not None:
        return CONFIG["cache"]
    v = _cfg("kb", "cache")
    return _abs(v, root()) if v else kit_config.home_dir(".cache", "kb")


def ledger_path():
    """The request ledger, as ledger.py finds it: ledger.dir, else its default folder."""
    if CONFIG["ledger"] is not None:
        return CONFIG["ledger"]
    d = _cfg("ledger", "dir") or kit_config.home_dir(os.path.join(".local", "share"), "ledger")
    return os.path.join(os.path.abspath(os.path.expanduser(d)), "requests.jsonl")


def log_dirs():
    """logs.backups, expanded as cc_logs.backup_dirs() does, read from --project's settings."""
    if CONFIG["log_dirs"] is not None:
        return CONFIG["log_dirs"]
    return [os.path.abspath(os.path.expanduser(x)).rstrip(os.sep) for x in _folders(_get("logs", "backups"))]


def transcript_dirs():
    if CONFIG["transcripts"] is not None:
        return CONFIG["transcripts"]
    for keys in (("transcripts", "dir"), ("recall", "transcripts"), ("seen_before", "transcripts")):
        v = _folders(_get(*keys))
        if v:
            return [os.path.abspath(os.path.expanduser(x)) for x in v]
    return []


def inside(p, d):
    d = os.path.normpath(d)
    return p == d or p.startswith(d.rstrip(os.sep) + os.sep)


def path_of(p):
    p = os.path.expanduser(p.strip())
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(root(), p))


def flat(s):
    return re.sub(r"\s+", " ", s or "").strip()


def is_log(p):
    try:
        import cc_logs
        if cc_logs.shape(p):
            return True
    except ImportError:
        pass
    return bool(LOG_RX.search(p.replace("\\", "/"))) or any(inside(p, d) for d in log_dirs())


def is_transcript(p):
    return any(inside(p, d) for d in transcript_dirs())


def private_of(p):
    """The kb.private folder p is in, or None."""
    return next((d for d in private_dirs() if inside(p, d)), None)


def _rel(p):
    r = root()
    return os.path.relpath(p, r) if inside(p, r) else p


def never_source(p):
    """Why a path can't be a source, or None."""
    d = private_of(p)
    if d:
        return f"under {_rel(d)}/, a folder kb.private keeps out of the store"
    if is_log(p):
        return "a session log or memory card, whose line can never fail a check"
    if os.path.realpath(p) == os.path.realpath(ledger_path()):
        return "the ledger file; cite one row as ledger <id> \"<quote>\""
    return None


# ---- the ledger, the ADO cache and the Figma indexes, each read once per run

class Record:
    def __init__(self):
        self._ledger = self._ado = None
        self._figma = {}

    def ledger(self):
        if self._ledger is None:
            led = {}
            with open(ledger_path(), encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(e, dict) and e.get("id"):
                        led[e["id"]] = e
            self._ledger = led
        return self._ledger

    def ado(self):
        if self._ado is None:
            path = CONFIG["ado_cache"]
            if path is None:
                import ado_rest
                path = ado_rest.CACHE
            with open(path, encoding="utf-8") as f:
                self._ado = json.load(f)
        return self._ado

    def figma(self, key):
        """(index dict or None, age in days or None, note). The dict: idx, text, kids."""
        if key not in self._figma:
            import pickle
            import figma_family
            p = os.path.join(CONFIG["figma_cache"] or figma_family.CACHE, f"{key}.pkl")
            try:
                with open(p, "rb") as f:
                    data = pickle.load(f)
                self._figma[key] = ({"idx": data["idx"], "text": data.get("text") or {}, "kids": None},
                                    (time.time() - data["built"]) / 86400, "")
            except (OSError, KeyError, pickle.UnpicklingError, EOFError) as e:
                self._figma[key] = (None, None, f"no Figma index for {key} ({type(e).__name__}; python "
                                                f"tools/figma_family.py build {key})")
        return self._figma[key]


def words_of(e):
    """Every word a ledger row holds: typed text, a card's question and its answer."""
    return " ".join(str(e.get(k) or "") for k in ("text", "question", "answer"))


def user_words(e):
    """The words in a ledger row that are the user's. A card's question and the labels it offered are the
    session's: most card answers are an offered label, the recommended one above all."""
    if e.get("source") in ("typed", "mid-turn"):
        return e.get("text") or ""
    if e.get("source") == "card" and e.get("answer_kind") == "typed":
        return e.get("answer") or ""
    return ""


def question_check(qid, question, rec):
    try:
        e = rec.ledger().get(qid)
    except OSError as err:
        return "did not run", f"the ledger wasn't read ({err})"
    if not e:
        return "miss", f"no ledger row {qid}"
    words = user_words(e)
    if not words:
        return "miss", (f"ledger {qid} holds none of the user's words (a {e.get('source')} row"
                        + (f", answered with {e.get('answer_kind')}" if e.get("answer_kind") else "") + ")")
    if flat(question).lower() not in flat(words).lower():
        return "miss", f"the question isn't in the user's words in ledger {qid}"
    return "ok", ""


def _figma_words(ix, nid):
    """The node's name and the text on it and on every layer under it."""
    import figma_family
    if ix["kids"] is None:
        kids = {}
        for k, v in ix["idx"].items():
            kids.setdefault(v[figma_family.PAR], []).append(k)
        ix["kids"] = kids
    out, stack = [ix["idx"][nid][figma_family.NAME]], [nid]
    while stack:
        n = stack.pop()
        out.append(ix["text"].get(n) or "")
        stack += ix["kids"].get(n, [])
    return " ".join(out)


def cite_check(c, rec):
    """("ok" | "miss" | "did not run", why) for one citation."""
    kind = c.split(" ", 1)[0]
    m = CITE_RX.get(kind) and CITE_RX[kind].match(c)
    if not m:
        return "miss", f"not a citation kb.py can check: {c[:80]}"
    g = m.groupdict()
    if kind in ("file", "sha256"):
        p = path_of(g["path"])
        never = never_source(p)
        if never:
            return "miss", f"never a source: {g['path']} is {never}"
        try:
            data = open(p, "rb").read()
        except OSError:
            return "miss", f"missing file: {g['path']}"
        if kind == "sha256":
            h = hashlib.sha256(data).hexdigest()
            return ("ok", "") if h == g["hex"] else ("miss", f"changed hash: {g['path']} is {h[:12]}..., cited {g['hex'][:12]}...")
        if flat(g["anchor"]) not in flat(data.decode("utf-8", "replace")):
            return "miss", f"moved anchor: \"{g['anchor'][:60]}\" is no longer in {g['path']}"
        return "ok", ""
    if kind == "commit":
        repo = path_of(g["repo"])
        if private_of(repo):
            return "miss", f"never a source: {g['repo']} is under a kb.private folder"
        if not os.path.isdir(repo):
            return "miss", f"missing file: no clone at {g['repo']}"
        try:
            r = subprocess.run(["git", "-C", repo, "cat-file", "-e", g["sha"] + "^{commit}"], capture_output=True, timeout=30)
            if r.returncode != 0:
                return "miss", f"unknown commit: {g['sha']} isn't in {g['repo']}"
            if not g.get("path"):
                return "ok", ""
            r = subprocess.run(["git", "-C", repo, "show", "HEAD:" + g["path"]], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            return "did not run", f"git in {g['repo']}: {e}"
        if r.returncode != 0:
            return "miss", f"missing file: {g['path']} isn't in {g['repo']} at HEAD"
        if flat(g["anchor"]) not in flat(r.stdout.decode("utf-8", "replace")):
            return "miss", f"moved anchor: \"{g['anchor'][:60]}\" is no longer in {g['path']} at {g['repo']} HEAD"
        return "ok", ""
    if kind == "ado":
        try:
            d = rec.ado()
        except (OSError, ValueError, ImportError, SystemExit, kit_config.NotConfigured) as e:
            return "did not run", f"the ADO cache wasn't read ({type(e).__name__}; python tools/ado_rest.py pull)"
        age = (time.time() - float(d.get("pulled") or 0)) / 86400
        it = (d.get("items") or {}).get(g["id"])
        if age > ADO_DAYS:
            return "did not run", f"the ADO cache is {age:.0f} days old (python tools/ado_rest.py pull)"
        if not it:
            return "miss", f"ADO #{g['id']} isn't in the cache: deleted or another project"
        if g.get("field"):
            try:
                return ado_field_check(g, it, d)
            except ImportError as e:
                return "did not run", f"ado_rest wasn't imported to strip HTML ({e})"
        rev = int(it.get("rev") or 0)
        if rev < int(g["rev"]):
            return "did not run", f"the ADO cache has #{g['id']} at rev {rev}, behind the cited {g['rev']} (python tools/ado_rest.py pull)"
        if rev > int(g["rev"]):
            return "miss", f"moved ADO revision: #{g['id']} is at rev {rev}, cited at rev {g['rev']}"
        return "ok", ""
    if kind == "figma":
        import figma_family
        ix, age, note = rec.figma(g["key"])
        if ix is None:
            return "did not run", note
        if age > FIGMA_DAYS:
            return "did not run", f"the Figma index of {g['key']} is {age:.0f} days old (python tools/figma_family.py build {g['key']})"
        nid = figma_family.norm(g["node"])
        if nid not in ix["idx"]:
            return "miss", (f"dead Figma node: {nid} isn't in {g['key']}'s index, built {age:.0f} days ago (a node "
                            f"newer than that: python tools/figma_family.py build {g['key']})")
        if g.get("anchor") and flat(g["anchor"]).lower() not in flat(_figma_words(ix, nid)).lower():
            return "miss", f"moved anchor: \"{g['anchor'][:60]}\" is no longer on Figma node {nid} or under it"
        return "ok", ""
    if kind == "ledger":
        try:
            led = rec.ledger()
        except OSError as e:
            return "did not run", f"the ledger wasn't read ({e})"
        e = led.get(g["id"])
        if not e:
            return "miss", f"no ledger row {g['id']}"
        if g.get("quote") and flat(g["quote"]).lower() not in flat(words_of(e)).lower():
            return "miss", f"ledger {g['id']} doesn't hold \"{g['quote'][:60]}\""
        return "ok", ""
    return "miss", f"unknown citation kind {kind}"


def ado_field_name(f):
    """A cited ADO field's short name, a reference name's short name (System.Title is title), or the reference name."""
    return f if f in ADO_FIELDS else ADO_REF.get(f, f)


def ado_field_check(g, it, d):
    """("ok" | "miss", why) for `ado <id> <field> "<anchor>"` on the cached item: the anchor, HTML stripped as
    `ado_rest.py show` prints it, whitespace collapsed and case aside, is in that field now. A text field holds it
    anywhere; state and type equal it; iteration's whole path or its last part equals it; tags hold it as one whole
    tag; a date starts with it."""
    import ado_rest
    f = g["field"]
    name = ado_field_name(f)
    if name in ADO_FIELDS:
        refs, how = ADO_FIELDS[name]
    elif "." in f:
        refs, how = (f,), "text"
    else:
        return "miss", (f"unknown ADO field {f}: give one of {', '.join(ADO_FIELDS)}, or a field's reference name "
                        f"such as System.AreaPath")
    if name == "comments":
        vals = [c.get("text") for c in (d.get("comments") or {}).get(g["id"]) or []]
    else:
        vals = [(it.get("fields") or {}).get(r) for r in refs]
    vals = [(v.get("displayName") or "") if isinstance(v, dict) else v for v in vals]
    vals = [flat(ado_rest.strip_html(str(v))).lower() for v in vals if v not in (None, "")]
    if not any(vals):
        return "miss", f"ADO #{g['id']} has nothing in {f}"
    want = flat(g["anchor"]).lower()
    if how == "exact":
        hit = want in vals
    elif how == "path":
        hit = any(want in (v, v.rsplit("\\", 1)[-1].strip()) for v in vals)
    elif how == "tag":
        hit = any(want in [t.strip() for t in v.split(";")] for v in vals)
    elif how == "date":
        hit = any(v.startswith(want) for v in vals)
    else:
        hit = any(want in v for v in vals)
    if not hit:
        return "miss", f"moved anchor: \"{g['anchor'][:60]}\" is no longer in ADO #{g['id']}'s {f}"
    return "ok", ""


def cite_keys(cites):
    """The anchors an entry's sources hold, to find one fact filed twice under two subjects."""
    out = set()
    for c in cites:
        kind = c.split(" ", 1)[0]
        m = CITE_RX.get(kind) and CITE_RX[kind].match(c)
        if not m:
            continue
        g = m.groupdict()
        if kind == "file":
            out.add(("file", path_of(g["path"]), flat(g["anchor"]).lower()))
        elif kind == "commit" and g.get("path"):
            out.add(("commit", path_of(g["repo"]), g["path"], flat(g["anchor"]).lower()))
        elif kind == "figma" and g.get("anchor"):
            out.add(("figma", g["key"], g["node"].replace("-", ":"), flat(g["anchor"]).lower()))
        elif kind == "ledger":
            out.add(("ledger", g["id"], flat(g.get("quote")).lower()))
        elif kind == "ado" and g.get("field"):
            out.add(("ado", g["id"], ado_field_name(g["field"]), flat(g["anchor"]).lower()))
    return out


def entry_keys(cites, question):
    """cite_keys, and the question itself: one question settled under two subjects is one fact filed twice."""
    return cite_keys(cites) | ({("question", flat(question).lower())} if question else set())


def only_transcripts(cites):
    paths = [m["path"] for c in cites for m in [CITE_RX["file"].match(c) or CITE_RX["sha256"].match(c)] if m]
    return bool(cites) and len(paths) == len(cites) and all(is_transcript(path_of(p)) for p in paths)


def only_comments(cites):
    """Every source an ADO comment anchor or a transcript, one comment at least: a later comment can reverse the
    fact while the cited one stays in place, so its anchor never fails."""
    comment = [bool(m and m["field"] and ado_field_name(m["field"]) == "comments")
               for m in (CITE_RX["ado"].match(c) for c in cites)]
    return any(comment) and all(k or only_transcripts([c]) for k, c in zip(comment, cites))


# ---- the index and the pages

def read_index(kb=None):
    """([{"name", "slug", "rest", "traps", "aliases": [lines]}], why or None)."""
    path = os.path.join(kb or kb_dir(), "index.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        return None, f"{path} not read ({e})"
    bodies = []
    for line in text.splitlines():
        m = BODY_RX.match(line)
        if m:
            traps = m["rest"].split("Name traps: ", 1)[1].strip() if "Name traps: " in m["rest"] else None
            bodies.append({"name": m["name"], "slug": m["page"], "rest": m["rest"], "traps": traps, "aliases": []})
        elif bodies and re.match(r"^\s+- alias:", line):
            bodies[-1]["aliases"].append(line.strip())
    return bodies, None


FIELD_RX = re.compile(r"^- (id|question|answer|source):\s*(.*)$")
QUESTION_RX = re.compile(r'^"(?P<q>[^"]+)" \((?:their words, ledger (?P<from>\S+)|phrased by the writer)\)$')


def parse_page(text, slug):
    """([entry], [fault], takes entries). An entry: {subject, id, status, written, by, replaces, question,
    question_from, answer, sources, line, end}; line and end bound its lines, 1-based, end exclusive."""
    entries, faults, cur, in_entries = [], [], None, False
    head = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    closed = bool(head and re.search(r"^entries: none\b", head.group(1), re.M))
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        if line.startswith("## ") or line.startswith("### "):
            if cur is not None:
                cur["end"] = n
                cur = None
        if line.startswith("## "):
            in_entries = line.strip() == "## Entries"
            continue
        if not in_entries:
            continue
        if line.startswith("### "):
            cur = {"subject": line[4:].strip(), "line": n, "end": len(lines) + 1, "sources": [], "body": slug}
            entries.append(cur)
            continue
        m = FIELD_RX.match(line)
        if cur is None or not m:
            continue
        k, v = m.groups()
        if k == "id":
            for part in ("id: " + v).split(";"):
                a, _, b = part.strip().partition(":")
                cur[a.strip()] = b.strip()
        elif k == "question":
            q = QUESTION_RX.match(v.strip())
            cur["question"], cur["question_from"] = (q["q"], q["from"]) if q else (None, None)
        elif k == "answer":
            cur["answer"] = v.strip()
        else:
            cur["sources"].append(v.strip())
    for e in entries:
        why = [w for w, bad in (("no id line", not e.get("id")), ("no question line in kb.py's form", not e.get("question")),
                                ("no answer", not e.get("answer")), ("no source", not e["sources"]),
                                ("a subject key not of the form <body>.<topic>", not SUBJECT_RX.match(e["subject"])),
                                (f"a subject outside its page's body ({slug})", not e["subject"].startswith(slug + ".")),
                                ("a status other than live (a replaced entry lives in log.jsonl only)",
                                 e.get("status") != "live"),
                                ("a page whose frontmatter says entries: none", closed))
               if bad]
        if why:
            faults.append(f"{slug}.md:{e['line']} entry {e.get('id') or e['subject']} can't be read: {'; '.join(why)}")
    return entries, faults, not closed


def load_store(kb=None):
    """(bodies, {slug: entries}, [faults], why or None). Each body gains "open": whether it takes entries."""
    kb = kb or kb_dir()
    bodies, why = read_index(kb)
    if why:
        return None, None, None, why
    pages, faults = {}, []
    for b in bodies:
        p = os.path.join(kb, b["slug"] + ".md")
        try:
            pages[b["slug"]], f, b["open"] = parse_page(open(p, encoding="utf-8").read(), b["slug"])
            faults += f
        except OSError:
            b["open"] = True
            faults.append(f"the index names {b['slug']}.md, which isn't there")
    slugs = {b["slug"] for b in bodies}
    for p in sorted(glob.glob(os.path.join(kb, "*.md"))):
        s = os.path.basename(p)[:-3]
        if s != "index" and s not in slugs:
            faults.append(f"orphan page: {s}.md isn't in index.md")
    return bodies, pages, faults, None


# ---- the pointer rules

def frontmatter(text):
    """(globs, [lines that aren't paths: or a double-quoted glob], body) or (None, None, why)."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None, None, "no frontmatter"
    globs, bad, seen = [], [], False
    for ln in m.group(1).split("\n"):
        g = re.match(r'^  - "([^"]+)"$', ln)
        if ln == "paths:" and not seen:
            seen = True
        elif g and seen:
            globs.append(g.group(1))
        else:
            bad.append(ln)
    return globs, bad, m.group(2)


def page_ref(slug, kb=None, desk=None):
    """How a body's rule names its page: the page's path from kb.root, or its absolute path outside it."""
    p, desk = os.path.join(kb or kb_dir(), slug + ".md"), desk or root()
    return os.path.relpath(p, desk) if inside(p, desk) else p


def rule_faults(bodies, rules=None, desk=None, kb=None):
    """[fault] for each body's pointer rule, and for any rule in the folder, at any depth, that would load
    where it shouldn't."""
    rules, desk, out = rules or rules_dir(), desk or root(), []
    have = {os.path.relpath(p, rules): p for p in glob.glob(os.path.join(rules, "**", "*.md"), recursive=True)}
    want = {f"kb-{b['slug']}.md": b for b in bodies if b.get("open", True)}
    for name, p in sorted(have.items()):
        globs, bad, body = frontmatter(open(p, encoding="utf-8").read())
        if not globs:
            out.append(f"rule {name} has no paths frontmatter, so it loads in every session")
            continue
        if bad:
            out.append(f"rule {name}: frontmatter line {bad[0]!r} isn't `paths:` or a double-quoted glob, and a "
                       "rule whose YAML doesn't parse loads in every session")
        lines = [ln for ln in body.splitlines() if ln.strip()]
        mine = [g for g in globs if private_of(os.path.normpath(os.path.join(desk, g)))]
        if mine:
            out.append(f"rule {name}: paths {', '.join(mine)} reach into a kb.private folder")
        dead = [g for g in globs if g not in mine and not glob.glob(os.path.join(desk, g), recursive=True)]
        if dead:
            out.append(f"rule {name}: paths {', '.join(dead)} match no file, so it never loads there")
        if any(ln.lstrip().startswith("@") for ln in lines):
            out.append(f"rule {name} has an @ import, which loads at every start whatever paths says")
        b = want.get(name)
        if b is None:
            continue
        lo, hi = RULE_LINES
        if not lo <= len(lines) <= hi:
            out.append(f"rule {name} has {len(lines)} lines, not {lo} to {hi}")
        ref = page_ref(b["slug"], kb, desk)
        if ref not in body:
            out.append(f"rule {name} doesn't name its page, {ref}")
        if "recall" not in body:
            out.append(f"rule {name} doesn't say to run recall")
        if b.get("traps") and f"Name traps: {b['traps']}" not in lines:
            out.append(f"rule {name}'s name traps aren't index.md's word for word: copy the index's into its Name traps line")
    for name in sorted(set(want) - set(have)):
        out.append(f"no pointer rule {name} for {want[name]['name']}")
    return out


# ---- check

def checked():
    try:
        d = json.load(open(os.path.join(cache_dir(), "checked.json"), encoding="utf-8"))
        return d if isinstance(d.get("entries"), dict) else {"entries": {}, "bodies": {}}
    except (OSError, ValueError, AttributeError):
        return {"entries": {}, "bodies": {}}


def check(kb=None, body=None, record=False, now=None, rules=None):
    """{"live", "pass", "misses": [(where, why)], "faults": [...], "did_not_run": [...], "writer": n,
    "per_body": {slug: {live, pass, miss}}, "why"}."""
    now = now or time.time()
    bodies, pages, faults, why = load_store(kb)
    if why:
        return {"why": why}
    rec, last = Record(), checked()
    out = {"live": 0, "pass": 0, "misses": [], "faults": faults + rule_faults(bodies, rules, kb=kb), "did_not_run": [],
           "writer": 0, "bodies": len(bodies), "pages": len(pages), "per_body": {}, "why": None}
    live, keys = {}, {}
    for slug, es in pages.items():
        for e in es:
            if e.get("status") == "live" and e.get("id"):
                live.setdefault(e["subject"], []).append(e)
                for k in entry_keys(e["sources"], e.get("question")):
                    keys.setdefault(k, []).append(e["id"])
    for subj, es in live.items():
        if len(es) > 1:
            out["faults"].append(f"duplicate live subject {subj}: {', '.join(e['id'] for e in es)}")
    for k, ids in keys.items():
        if len(set(ids)) > 1:
            what = "question" if k[0] == "question" else f"{k[0]} anchor"
            out["faults"].append(f"live entries {', '.join(sorted(set(ids)))} share one {what}: one fact, filed twice?")
    passed = {}
    for slug, es in pages.items():
        if body and slug != body:
            continue
        pb = out["per_body"].setdefault(slug, {"live": 0, "pass": 0, "miss": 0})
        for e in es:
            if e.get("status") != "live" or not e.get("id") or not e.get("question"):
                continue
            out["live"] += 1
            pb["live"] += 1
            out["writer"] += not e.get("question_from")
            res = [cite_check(c, rec) for c in e["sources"]]
            if e.get("question_from"):
                res.append(question_check(e["question_from"], e["question"], rec))
            if only_transcripts(e["sources"]):
                res.append(("miss", "a meeting transcript is its only source, and one never changes"))
            elif only_comments(e["sources"]):
                res.append(("miss", "ADO comments are its only source, and a later comment can reverse one that stays"))
            bad = [w for s, w in res if s == "miss"]
            dnr = [w for s, w in res if s == "did not run"]
            where = f"{e['id']} {e['subject']}"
            if bad:
                out["misses"] += [(where, w) for w in bad]
                pb["miss"] += 1
                continue
            if dnr:
                out["did_not_run"] += [(where, w) for w in dnr]
                seen = last["entries"].get(e["id"]) or _epoch(e.get("written"))
                if seen and (now - seen) / 86400 > STALE_DAYS:
                    out["misses"].append((where, f"no passing check in {STALE_DAYS} days: {dnr[0]}"))
                    pb["miss"] += 1
                continue
            out["pass"] += 1
            pb["pass"] += 1
            passed[e["id"]] = now
    if record:
        day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        rec_bodies = dict(last.get("bodies") or {}, **{s: dict(v, at=day) for s, v in out["per_body"].items()})
        os.makedirs(cache_dir(), exist_ok=True)
        write_atomic(os.path.join(cache_dir(), "checked.json"),
                     json.dumps({"entries": dict(last["entries"], **passed), "bodies": rec_bodies}, indent=1) + "\n")
    return out


def _epoch(day):
    try:
        return dt.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def flag_new(r):
    """{finding: the date it was first listed, or None if the last --new run didn't list it}. Saves the ones
    listed now; one that drops off and comes back is new again. A miss is keyed by its entry and its kind
    (the text before its colon), so a number in it that moves daily doesn't make it new daily."""
    path = os.path.join(cache_dir(), "flags.json")
    try:
        old = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    now = [f"{w} | {why.split(':')[0]}" for w, why in r["misses"]] + [f"fault | {f}" for f in r["faults"]]
    today = dt.date.today().isoformat()
    os.makedirs(cache_dir(), exist_ok=True)
    write_atomic(path, json.dumps({k: old.get(k, today) for k in now}, indent=1) + "\n")
    return {k: old.get(k) for k in now}


def show_check(r, since=None):
    if r.get("why"):
        return f"did not run: {r['why']}"
    lines = [f"kb check: {r['pass']} of {r['live']} live entries pass; {r['bodies']} bodies, {r['pages']} pages; "
             f"{len(r['faults'])} store or rule fault(s); {r['writer']} question(s) phrased by the writer, not the "
             "user's words"]

    def mark(k):
        return "" if since is None else ("  NEW" if not since.get(k) else f"  (since {since[k]})")
    lines += [f"MISS  {w}: {why}{mark(f'{w} | ' + why.split(':')[0])}" for w, why in r["misses"]]
    lines += [f"FAULT  {f}{mark('fault | ' + f)}" for f in r["faults"]]
    lines += [f"DID NOT RUN  {w}: {why}" for w, why in r["did_not_run"]]
    if r["misses"]:
        lines.append("A miss: re-read the source. If the answer holds, re-cite it with kb.py add --replaces <id> and "
                     "the same subject; if not, write the new answer the same way.")
    return "\n".join(lines)


# ---- add

def write_atomic(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(kb=None):
    fd = os.open(os.path.join(kb or kb_dir(), ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def render(e):
    q = f'"{e["question"]}" ' + (f"(their words, ledger {e['question_from']})" if e.get("question_from")
                                 else "(phrased by the writer)")
    head = f"- id: {e['id']}; status: {e['status']}; written: {e['written']}; by: {e['by']}"
    head += "".join(f"; {k}: {e[k]}" for k in ("replaces", "superseded_by", "from") if e.get(k))
    return "\n".join([f"### {e['subject']}", head, f"- question: {q}", f"- answer: {e['answer']}"]
                     + [f"- source: {s}" for s in e["sources"]]) + "\n"


def log_rows(kb=None):
    try:
        with open(os.path.join(kb or kb_dir(), "log.jsonl"), encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]
    except (OSError, ValueError):
        return []


def _session():
    """Who writes: this session's id (the desktop app's, else the CLI's), else terminal."""
    return os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "terminal"


def add(body, subject, question, answer, cites, question_from=None, replaces=None, by=None, kb=None, today=None,
        handback=None, correction=None):
    """(code, message). Writes one entry to its body's page, or refuses. handback (an agent id) or correction (a
    ledger row in the user's words) names what the entry was filed from, for a session-close check."""
    kb = kb or kb_dir()
    with locked(kb):
        bodies, pages, faults, why = load_store(kb)
        if why:
            return 2, f"did not run: {why}"
        if body not in pages:
            return 1, f"refused: no page for body {body!r}; the index's bodies are {', '.join(sorted(pages))}"
        if not next(b for b in bodies if b["slug"] == body)["open"]:
            return 1, f"refused: {body}.md says entries: none"
        if not cites:
            return 1, "refused: an entry needs at least one --cite that kb.py check can fail"
        if not SUBJECT_RX.match(subject) or not subject.startswith(body + "."):
            return 1, f"refused: the subject is <body>.<topic> in lowercase, here {body}.<topic>"
        if '"' in question or any("\n" in x for x in [question, answer] + list(cites)):
            return 1, "refused: the question can't hold a double quote, and no field a line break"
        rec, fails = Record(), []
        for c in cites:
            s, w = cite_check(c, rec)
            if s != "ok":
                fails.append(f"{c[:80]}: {w or s}")
        if question_from:
            s, w = question_check(question_from, question, rec)
            if s != "ok":
                fails.append(f"--question-from: {w}")
        if only_transcripts(cites):
            fails.append("a meeting transcript never changes, so it can't be the only source")
        elif only_comments(cites):
            fails.append("a later ADO comment can reverse one that stays, so comments can't be the only source")
        why = trigger_check(handback and [handback], correction and [correction], rec)
        if why:
            fails.append(why)
        if fails:
            return 1, "refused: " + "; ".join(fails)
        everyone = [e for es in pages.values() for e in es if e.get("status") == "live"]
        live = [e for e in everyone if e.get("subject") == subject]
        if live and not (replaces and any(e["id"] == replaces for e in live)):
            return 1, (f"refused: {subject} has a live entry, {live[0]['id']}; give --replaces {live[0]['id']} if this "
                       "one supersedes it")
        if replaces and not live:
            return 1, f"refused: {replaces} is not a live entry on {subject}"
        mine = entry_keys(cites, question)
        twin = [(e, mine & entry_keys(e["sources"], e.get("question"))) for e in everyone if e.get("subject") != subject]
        twin = [(e, k) for e, k in twin if k]
        if twin:
            e, k = twin[0]
            what = "settles that question" if any(x[0] == "question" for x in k) else "cites that anchor"
            return 1, (f"refused: {e['id']} ({e['subject']}) already {what}; replace it, or settle and cite what "
                       "this entry says that it doesn't")
        ids = [e.get("id") or "" for es in pages.values() for e in es] + [r.get("id") or "" for r in log_rows(kb)]
        n = 1 + max([int(m) for i in ids for m in re.findall(r"^k-(\d+)$", i)] or [0])
        e = {"subject": subject, "id": f"k-{n:04d}", "status": "live", "written": today or dt.date.today().isoformat(),
             "by": (by or _session())[:14], "question": question,
             "question_from": question_from, "answer": answer, "sources": list(cites)}
        if replaces:
            e["replaces"] = replaces
        if handback or correction:
            e["from"] = f"handback {handback}" if handback else f"correction {correction}"
        path = os.path.join(kb, body + ".md")
        text = open(path, encoding="utf-8").read()
        at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        logged = []
        if replaces:
            old = live[0]
            lines = text.splitlines(keepends=True)
            text = "".join(lines[:old["line"] - 1] + lines[old["end"] - 1:])
            gone = {k: v for k, v in old.items() if k not in ("line", "end")}
            logged.append(dict(gone, status="superseded", superseded_by=e["id"], event="superseded", at=at))
        if "\n## Entries\n" not in "\n" + text:
            text = text.rstrip("\n") + "\n\n## Entries\n"
        text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n\n" + render(e)
        write_atomic(path, text)
        with open(os.path.join(kb, "log.jsonl"), "a", encoding="utf-8") as f:
            trig = {"handback": handback} if handback else {"correction": correction} if correction else {}
            for row in logged + [dict(e, body=body, event="added", at=at, **trig)]:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return 0, f"added {e['id']} on {subject}" + (f"; {replaces} left the page for log.jsonl" if replaces else "")


AGENT_RX = re.compile(r"^a[0-9a-f]{8,}$")


def trigger_check(handbacks, corrections, rec):
    """Why a --handback or --correction can't be named, or None: an agent id is a, then 8 or more hex digits;
    a correction is a ledger row holding the user's own words."""
    if handbacks and corrections:
        return "name a hand-back or a correction, not both"
    bad = [h for h in handbacks or [] if not AGENT_RX.match(h or "")]
    if bad:
        return f"--handback {bad[0]!r} isn't an agent id (a, then 8 or more hex digits, as its hand-back names it)"
    for c in corrections or []:
        try:
            e = rec.ledger().get(c)
        except OSError as err:
            return f"the ledger wasn't read ({err})"
        if not e:
            return f"--correction: no ledger row {c}"
        if not user_words(e):
            return f"--correction: ledger {c} holds none of the user's words"
    return None


def none(handbacks=(), corrections=(), why="", by=None, kb=None, cites=()):
    """(code, message). Records that a hand-back or a correction was read and holds nothing to file: a log.jsonl
    row only, no entry, which filed() counts. cites, in add's syntax, say where it was handled instead (a
    correction fixed in a gate's commit): each must pass now, and the row keeps them."""
    kb = kb or kb_dir()
    if not handbacks and not corrections:
        return 1, "refused: name what was read, with --handback <agent id> or --correction <ledger id>"
    if len(flat(why).split()) < 4:
        return 1, "refused: --why says in a few words why nothing in it is worth an entry"
    rec = Record()
    bad = trigger_check(list(handbacks), list(corrections), rec)
    if bad:
        return 1, f"refused: {bad}"
    if any("\n" in c for c in cites):
        return 1, "refused: a citation can't hold a line break"
    fails = [f"{c[:80]}: {w or s}" for c in cites for s, w in [cite_check(c, rec)] if s != "ok"]
    if fails:
        return 1, "refused: " + "; ".join(fails)
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    who = (by or _session())[:14]
    with locked(kb):
        with open(os.path.join(kb, "log.jsonl"), "a", encoding="utf-8") as f:
            for k, ids in (("handback", handbacks), ("correction", corrections)):
                for i in ids:
                    f.write(json.dumps(dict({"event": "nothing", k: i, "why": flat(why), "by": who, "at": at},
                                            **({"sources": list(cites)} if cites else {})),
                                       ensure_ascii=False) + "\n")
    n = len(handbacks) + len(corrections)
    return 0, f"recorded {n} read with nothing to file"


def filed(kb=None):
    """What the store has filed something from, for a session-close check: {"handback": {agent id: newest row's
    time}, "correction": {ledger id: newest row's time}, "ledger": {ledger id an entry cites or takes its question
    from}, "bare": {agent or ledger id whose newest row is a `none` with no source}}. A replaced entry still
    counts, and so does a `none` row. -> (dict, why or None); why when log.jsonl can't be read."""
    kb = kb or kb_dir()
    out = {"handback": {}, "correction": {}, "ledger": set(), "bare": set()}
    path = os.path.join(kb, "log.jsonl")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as e:
        return out, f"{path} not read ({e})"
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        for k in ("handback", "correction"):
            if r.get(k) and (r.get("at") or "") >= out[k].get(r[k], ""):
                out[k][r[k]] = r.get("at") or ""
                (out["bare"].add if r.get("event") == "nothing" and not r.get("sources") else out["bare"].discard)(r[k])
        if r.get("question_from"):
            out["ledger"].add(r["question_from"])
        for c in r.get("sources") or []:
            m = CITE_RX["ledger"].match(c)
            if m:
                out["ledger"].add(m["id"])
    return out, None


def show(what, kb=None):
    bodies, pages, faults, why = load_store(kb)
    if why:
        return 2, f"did not run: {why}"
    if what in pages:
        return 0, open(os.path.join(kb or kb_dir(), what + ".md"), encoding="utf-8").read()
    hits = [e for es in pages.values() for e in es if what in (e.get("id"), e.get("subject"))]
    hits += [r for r in log_rows(kb) if r.get("event") == "superseded" and what in (r.get("id"), r.get("subject"))]
    if not hits:
        return 1, f"no body, subject or id {what!r}"
    return 0, "\n".join(render(e) for e in hits)


def main(argv):
    if argv[:1] == ["--selftest"]:
        return selftest()
    global PROJECT
    ap = argparse.ArgumentParser(prog="kb.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", help="the project whose settings count (default $CLAUDE_PROJECT_DIR, else "
                                          "the working folder)")
    a = sub.add_parser("add", parents=[common])
    a.add_argument("--body", required=True)
    a.add_argument("--subject", required=True)
    a.add_argument("--question", required=True)
    a.add_argument("--question-from")
    a.add_argument("--answer", required=True)
    a.add_argument("--cite", action="append", default=[])
    a.add_argument("--replaces")
    a.add_argument("--handback", help="the agent id of the hand-back this entry files a finding from")
    a.add_argument("--correction", help="the ledger id of the user's correction this entry answers")
    nn = sub.add_parser("none", parents=[common])
    nn.add_argument("--handback", nargs="+", default=[])
    nn.add_argument("--correction", nargs="+", default=[])
    nn.add_argument("--why", required=True)
    nn.add_argument("--cite", action="append", default=[], help="where it was handled instead, in add's syntax")
    c = sub.add_parser("check", parents=[common])
    c.add_argument("--body")
    c.add_argument("--record", action="store_true")
    c.add_argument("--new", action="store_true")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("show", parents=[common])
    s.add_argument("what")
    o = ap.parse_args(argv)
    PROJECT = getattr(o, "project", None)
    if o.cmd == "add":
        code, msg = add(o.body, o.subject, o.question, o.answer, o.cite, o.question_from, o.replaces,
                        handback=o.handback, correction=o.correction)
        print(msg)
        return code
    if o.cmd == "none":
        code, msg = none(o.handback, o.correction, o.why, cites=o.cite)
        print(msg)
        return code
    if o.cmd == "check":
        r = check(body=o.body, record=o.record)
        since = flag_new(r) if o.new and not r.get("why") else None
        print(json.dumps(r, indent=1) if o.json else show_check(r, since))
        if r.get("why"):
            return 2
        if since is not None:
            return 1 if any(not v for v in since.values()) else 0
        return 1 if r["misses"] or r["faults"] else 0
    if o.cmd == "show":
        code, msg = show(o.what)
        print(msg)
        return code
    print(__doc__)
    return 1


def selftest():
    """A planted store: each citation kind passing and failing, each store and rule fault, each refusal of
    add, the 30-day rule, and the settings each folder comes from. No network: the ADO cache, the Figma index
    and the ledger are planted."""
    import pickle
    import shutil
    global PROJECT
    kept, kept_project = dict(CONFIG), PROJECT
    env_kept = {k: os.environ.get(k) for k in ("HOME", kit_config.ENV, "CLAUDE_PROJECT_DIR")}
    root_ = os.path.realpath(tempfile.mkdtemp())
    ok = []

    def case(what, good):
        ok.append(bool(good))
        print(("PASS " if good else "FAIL ") + what)
    try:
        KB, RULES, ADO_CACHE = os.path.join(root_, "knowledge"), os.path.join(root_, ".claude", "rules"), os.path.join(root_, "ado.json")
        FIGMA_CACHE = os.path.join(root_, "figma")
        CONFIG.update(root=root_, dir=KB, rules=RULES, private=[os.path.join(root_, "_mine")],
                      cache=os.path.join(root_, "cache"), ledger=os.path.join(root_, "requests.jsonl"),
                      log_dirs=[os.path.join(root_, "log-backups")], transcripts=[os.path.join(root_, "transcripts")],
                      ado_cache=ADO_CACHE, figma_cache=FIGMA_CACHE)
        LEDGER = CONFIG["ledger"]
        for d in (KB, RULES, FIGMA_CACHE, os.path.join(root_, "docs"), os.path.join(root_, ".claude", "projects", "-x"),
                  os.path.join(root_, "_mine"), os.path.join(root_, "transcripts"), os.path.join(root_, "log-backups")):
            os.makedirs(d, exist_ok=True)
        put = lambda rel, text: open(os.path.join(root_, rel), "w", encoding="utf-8").write(text)  # noqa: E731
        put("docs/plan.md", "The real link is the ledger:\nthe service sits beside the API.\nThe invoice page ships first.\n")
        put("docs/blob.bin", "fixed bytes")
        put(".claude/projects/-x/s.jsonl", '{"text": "a log line"}\n')
        put("docs/0b9e1f2a-1111-4222-8333-444455556666.jsonl", '{"text": "a copied log line"}\n')
        put("log-backups/notes.txt", "a backed-up log line\n")
        put("_mine/notes.md", "my own words\n")
        put("transcripts/call.md", "we said billing is the engine\n")
        with open(LEDGER, "w", encoding="utf-8") as f:
            for row in ({"id": "card:t1:0", "source": "card", "question": "Which name goes on the page?",
                         "answer": "should use billing engine", "answer_kind": "recommended"},
                        {"id": "card:t2:0", "source": "card", "question": "Which name?", "answer": "say billing engine everywhere",
                         "answer_kind": "typed"},
                        {"id": "r-77", "source": "typed", "text": "is it billing or billing engine on the site"},
                        {"id": "sp-1", "source": "spawned", "text": "is it billing or billing engine on the site"}):
                f.write(json.dumps(row) + "\n")
        f4242 = {"System.Title": "Rename Billing to Billing Engine", "System.WorkItemType": "Bug", "System.State": "Closed",
                 "System.Description": "", "Microsoft.VSTS.TCM.ReproSteps":
                 "<div>Every bare <b>Billing</b> becomes Billing&nbsp;Engine.</div>",
                 "Microsoft.VSTS.Common.AcceptanceCriteria": "<p>The site says Billing Engine.</p>",
                 "System.IterationPath": "Proj\\Release 2\\Someday", "System.Tags": "design-review; naming",
                 "System.CreatedDate": "2025-01-06T14:00:00Z", "System.AreaPath": "Proj\\Payments",
                 "System.AssignedTo": {"displayName": "Item Owner", "uniqueName": "owner@example.com"}}
        ado_plant = lambda **k: json.dump(dict({"pulled": time.time(), "items": {"4242": {"rev": 9, "fields": f4242},  # noqa: E731
                                                                                "4243": {"rev": 3}},
                                                "comments": {"4242": [{"text": "<p>Renamed on every page.</p>"}]}}, **k),
                                          open(ADO_CACHE, "w"))
        ado_plant()
        fig = {"built": time.time(), "idx": {"1:1": ("FRAME", "Hero", None, "1:1", None, None, False),
                                             "1100:2000": ("FRAME", "Card", "1:1", "1:1", None, None, False),
                                             "1100:2001": ("TEXT", "label", "1100:2000", "1:1", None, None, False),
                                             "1100:2002": ("FRAME", "Other", "1:1", "1:1", None, None, False)},
               "text": {"1100:2001": "Billing Engine sends invoices"}}
        figpkl = os.path.join(FIGMA_CACHE, "FILEKEY123.pkl")
        pickle.dump(fig, open(figpkl, "wb"))
        repo = os.path.join(root_, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        put("repo/a.txt", "the invoice page ships first\n")
        g = lambda *a: subprocess.run(["git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", *a],  # noqa: E731
                                      capture_output=True, text=True, check=True).stdout.strip()
        g("add", "a.txt")
        g("commit", "-q", "-m", "a")
        sha = g("rev-parse", "HEAD")
        blob_hash = hashlib.sha256(b"fixed bytes").hexdigest()
        put("knowledge/index.md", "# Knowledge index\n\n"
            "- [Billing work](billing.md): the billing engine. Canonical: docs/plan.md. Name traps: Billing is Billing Engine.\n"
            "  - alias: Billing = Billing Engine | #4242  (since 2025-01-06, ADO #4242)\n"
            "- [Kickoff](kickoff.md): the program's start. Name traps: none.\n"
            "- [Mine](mine.md): my own files.\n")
        page = "---\nbody: {s}\n---\n# {s}\n\nWhat it is, and its homes.\n\n## Entries\n"
        put("knowledge/billing.md", page.format(s="billing"))
        put("knowledge/kickoff.md", page.format(s="kickoff"))
        put("knowledge/mine.md", "---\nbody: mine\nentries: none (my own files)\n---\n# Mine\n\n## Entries\n")
        rule = ("---\npaths:\n  - \"{g}\"\n---\n{s} work: what it is.\nName traps: {t}\nWhat we know: knowledge/{s}.md.\n"
                "Run `recall` before asking.\n")
        wrule, krule = rule.format(g="docs/**", s="billing", t="Billing is Billing Engine."), rule.format(g="docs/plan.md", s="kickoff", t="none.")
        put(".claude/rules/kb-billing.md", wrule)
        put(".claude/rules/kb-kickoff.md", krule)

        good = {"file": 'file `docs/plan.md` "The real link is the ledger: the service"', "commit": f"commit `repo` {sha}",
                "commit anchor": f'commit `repo` {sha} `a.txt` "the invoice page ships first"',
                "ado": "ado 4242 rev 9", "figma": "figma FILEKEY123 1100-2000",
                "figma anchor": 'figma FILEKEY123 1100:2000 "billing engine sends"',
                "sha256": f"sha256 `docs/blob.bin` {blob_hash}", "ledger": 'ledger card:t1:0 "should use billing engine"',
                "ado title": 'ado 4242 title "rename billing to billing"',
                "ado repro": 'ado 4242 description "every bare billing becomes billing engine"',
                "ado state": 'ado 4242 state "closed"', "ado iteration": 'ado 4242 iteration "Someday"',
                "ado tag": 'ado 4242 tags "naming"', "ado created": 'ado 4242 created "2025-01-06"',
                "ado ref": 'ado 4242 System.AreaPath "Payments"', "ado person": 'ado 4242 System.AssignedTo "Item Owner"',
                "ado comment": 'ado 4242 comments "renamed on every page"'}
        bad = {"file": 'file `docs/plan.md` "a phrase that is not there"', "missing file": 'file `docs/gone.md` "x"',
               "commit": f"commit `repo` {'0' * 40}", "ado": "ado 4242 rev 8", "figma": "figma FILEKEY123 999:1",
               "sha256": f"sha256 `docs/blob.bin` {'0' * 64}", "ledger": 'ledger card:t1:0 "use invoicing"',
               "ledger id": "ledger card:none:0", "log": 'file `.claude/projects/-x/s.jsonl` "a log line"',
               "copied log": 'file `docs/0b9e1f2a-1111-4222-8333-444455556666.jsonl` "a copied log line"',
               "backup log": 'file `log-backups/notes.txt` "a backed-up log line"',
               "ledger file": 'file `requests.jsonl` "should use billing engine"',
               "private": 'file `_mine/notes.md` "my own words"',
               "commit anchor": f'commit `repo` {sha} `a.txt` "the refund page ships first"',
               "figma anchor": 'figma FILEKEY123 1100:2000 "invoicing"', "shape": "see the last call"}
        rec = Record()
        case("known good: one citation of each kind passes, an anchor across a line break, a commit's file at HEAD, "
             "a Figma node's text and each ADO field form (a Bug's Repro Steps under HTML, a whole state, iteration's "
             "last part, one whole tag, a date, a reference name, a person, a comment) included: "
             + ", ".join(k for k, c in good.items() if cite_check(c, rec) != ("ok", "")),
             all(cite_check(c, rec) == ("ok", "") for c in good.values()))
        res = {k: cite_check(c, rec) for k, c in bad.items()}
        case("known bad: a missing anchor, a missing file, an unknown commit, a moved ADO revision, a dead Figma node, "
             "a changed hash, a quote not in the ledger row, a missing ledger row, a session log in its folder, one "
             "copied out of it and one in a logs.backups folder, the ledger file, a file under a kb.private folder, an "
             "anchor gone from a commit's file at HEAD or from a Figma node, and a bare phrase each fail, each saying which",
             all(s == "miss" for s, _ in res.values())
             and [w.split(":")[0] for _, w in (res["file"], res["missing file"], res["commit"], res["ado"], res["figma"],
                                                res["sha256"], res["commit anchor"], res["figma anchor"])]
             == ["moved anchor", "missing file", "unknown commit", "moved ADO revision", "dead Figma node", "changed hash",
                 "moved anchor", "moved anchor"]
             and all("never a source" in res[k][1] for k in ("log", "copied log", "backup log", "ledger file", "private"))
             and "no ledger row" in res["ledger id"][1])
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 8}}}, open(ADO_CACHE, "w"))
        case("an ADO cache behind the citation doesn't run; it isn't a miss", cite_check(good["ado"], Record())[0] == "did not run")
        ado_plant()
        adobad = {"removed": ('ado 4242 title "invoicing"', "moved anchor"),
                  "only in another field": ('ado 4242 acceptance "every bare billing"', "moved anchor"),
                  "part of a tag": ('ado 4242 tags "design"', "moved anchor"),
                  "part of a state": ('ado 4242 state "clos"', "moved anchor"),
                  "part of a state by its reference name": ('ado 4242 System.State "clos"', "moved anchor"),
                  "the middle of an iteration": ('ado 4242 iteration "Release 2"', "moved anchor"),
                  "another date": ('ado 4242 created "2025-01-07"', "moved anchor"),
                  "a person's email": ('ado 4242 System.AssignedTo "owner@example.com"', "moved anchor"),
                  "an empty field": ('ado 4242 closed "2025"', "has nothing in closed"),
                  "an unknown short name": ('ado 4242 priority "2"', "unknown ADO field"),
                  "an uncached item": ('ado 9999 title "x"', "isn't in the cache")}
        res = {k: cite_check(c, Record()) for k, (c, _) in adobad.items()}
        case("known bad: an ADO anchor removed from its field, found only in another field, part of a tag, a state or an "
             "iteration path, another date, a person's email, an empty field, an unknown short name and an uncached "
             "item each miss, each saying which: "
             + ", ".join(k for k, (c, why) in adobad.items() if not (res[k][0] == "miss" and why in res[k][1])),
             all(res[k][0] == "miss" and why in res[k][1] for k, (c, why) in adobad.items()))
        ado_plant(pulled=time.time() - 5 * 86400)
        case("an ADO cache older than ADO_DAYS doesn't run a field cite either; it isn't a miss",
             cite_check(good["ado title"], Record())[0] == "did not run")
        ado_plant()

        day = dt.date.today().isoformat()   # written today, so the 30 days start now
        A = lambda subj, cites, **k: add(k.pop("body", "billing"), subj, k.pop("q", "is it billing or billing engine on the site"),  # noqa: E731
                                         k.pop("a", "Billing Engine."), cites, today=k.pop("today", day), by="local_test", **k)
        r1 = A("billing.naming", [good["ado"], good["file"], good["ado title"]], question_from="r-77")
        case("add writes a cited entry in the user's words, and check passes it", r1[0] == 0 and "k-0001" in r1[1]
             and check()["pass"] == 1 and check()["writer"] == 0)
        tq = 'file `transcripts/call.md` "billing is the engine"'
        refusals = {"no source": (A("billing.other", [], q="q1"), "at least one --cite"),
                    "a failing source": (A("billing.other", [bad["file"]], q="q2"), "moved anchor"),
                    "a session log": (A("billing.other", [bad["log"]], q="q3"), "session log"),
                    "a copied log": (A("billing.other", [bad["copied log"]], q="q4"), "session log"),
                    "the ledger file": (A("billing.other", [bad["ledger file"]], q="q5"), "the ledger file"),
                    "a private folder": (A("billing.other", [bad["private"]], q="q6"), "kb.private"),
                    "a transcript alone": (A("billing.other", [tq], q="q7"), "can't be the only source"),
                    "a second live entry": (A("billing.naming", [good["commit"]], q="q8"), "has a live entry"),
                    "a shared anchor": (A("billing.renamed", [good["file"]], q="q9"), "already cites that anchor"),
                    "a shared ADO anchor": (A("billing.retitled", ['ado 4242 System.Title "Rename  Billing to Billing"'],
                                              q="q13"), "already cites that anchor"),
                    "ADO comments alone": (A("billing.said", [good["ado comment"]], q="q14"),
                                           "comments can't be the only source"),
                    "a settled question": (A("billing.again", [good["commit"]], q="Is it Billing or Billing Engine on the site"),
                                           "already settles that question"),
                    "words not in the ledger row": (A("billing.other", [good["commit"]], q="what does invoicing do",
                                                      question_from="r-77"), "isn't in the user's words"),
                    "a card's offered label": (A("billing.other", [good["commit"]], q="should use billing engine",
                                                 question_from="card:t1:0"), "holds none of the user's words"),
                    "a spawned row": (A("billing.other", [good["commit"]], q="billing engine on the site", question_from="sp-1"),
                                      "holds none of the user's words"),
                    "an unknown body": (A("payroll.x", [good["commit"]], body="payroll", q="q10"), "no page for body"),
                    "a body that takes none": (A("mine.x", [good["commit"]], body="mine", q="q11"), "entries: none"),
                    "a subject outside its body": (A("kickoff.x", [good["commit"]], q="q12"), "the subject is")}
        case("add refuses no source, a failing source, a log in or out of its folder, the ledger file, a kb.private "
             "folder, a transcript alone, ADO comments alone, a second live entry, a new subject on a live entry's anchor "
             "(an ADO field's under its reference name too) or question (case aside), a "
             "question not in the user's words (not in the row, a card's offered label, a spawned row), an unknown body, "
             "one that takes none and a subject outside its body, each for its own reason, and writes none of them: "
             + ", ".join(k for k, ((c, m), why) in refusals.items() if not (c == 1 and m.startswith("refused") and why in m)),
             all(c == 1 and m.startswith("refused") and why in m for (c, m), why in refusals.values())
             and check()["live"] == 1)
        r2 = A("billing.naming", [good["commit"]], replaces="k-0001", a="Billing Engine, per the commit.")
        st, wtext = check(), open(os.path.join(KB, "billing.md")).read()
        logged = log_rows()
        case("--replaces takes the old entry off its page into log.jsonl; check counts one live entry",
             r2[0] == 0 and st["live"] == 1 and st["pass"] == 1 and not st["faults"] and "id: k-0001" not in wtext
             and "replaces: k-0001" in wtext and any(x.get("id") == "k-0001" and x.get("superseded_by") == "k-0002"
                                                     and x.get("answer") == "Billing Engine." for x in logged))
        A("billing.link", [good["ado"], good["file"]], q="billing or billing engine", question_from="r-77")
        A("billing.figma-node", [good["figma anchor"], good["sha256"]], q="say billing engine everywhere",
          question_from="card:t2:0")
        A("kickoff.ledger", [good["ledger"], good["commit anchor"]], body="kickoff", q="which name goes on the page")
        A("kickoff.transcript", ['file `transcripts/call.md` "billing is the engine"',
                                 'file `docs/plan.md` "The invoice page ships first."'], body="kickoff", q="who builds")
        case("known good: the seeded planted store passes whole; a card's typed answer counts as the user's words, a "
             "transcript with another source is taken, and a question with no ledger row counts as the writer's",
             (lambda r: r["pass"] == r["live"] == 5 and not r["misses"] and not r["faults"] and r["writer"] == 3)(check()))
        case("every add appends the whole entry to log.jsonl, and a replace logs the old one too",
             sum(1 for x in log_rows() if x.get("event") == "added") == 6 and len(log_rows()) == 7)
        code, msg = show("billing.naming")
        case("show finds an entry by subject, the replaced one included from the log, and a page by its body",
             code == 0 and "k-0001" in msg and "k-0002" in msg and show("kickoff")[0] == 0 and show("nothing")[0] == 1)

        # What an entry was filed from: a hand-back or a correction, and `none` for one with nothing.
        hb = "a1b2c3d4e5f60718"
        fb = A("billing.handback", [good["ado"]], q="what did the challenger find", handback=hb)
        fc = A("kickoff.correction", ['file `docs/plan.md` "the service sits beside the API"'], body="kickoff",
               q="where does the service sit", correction="r-77")
        trig_bad = {"not an agent id": A("billing.t1", [good["commit"]], q="t1", handback="xyz"),
                    "a spawned row": A("billing.t2", [good["commit"]], q="t2", correction="sp-1"),
                    "a card's offered label": A("billing.t3", [good["commit"]], q="t3", correction="card:t1:0"),
                    "both": A("billing.t4", [good["commit"]], q="t4", handback=hb, correction="r-77")}
        wt2 = open(os.path.join(KB, "billing.md")).read()
        case("add names what it filed from: a hand-back's agent id or a correction in the user's words, on the id line "
             "and in the log; not an agent id, a row without the user's words, or both are refused: "
             + ", ".join(k for k, (c, m) in trig_bad.items() if not (c == 1 and m.startswith("refused"))),
             fb[0] == 0 and fc[0] == 0 and f"from: handback {hb}" in wt2
             and all(c == 1 and m.startswith("refused") for c, m in trig_bad.values())
             and any(r.get("correction") == "r-77" and r.get("event") == "added" for r in log_rows()))
        nb = {"no id": none([], [], "nothing durable in this verdict"),
              "a short why": none(["a1234567890"], [], "agree"),
              "a bad id": none(["zz"], [], "nothing durable in this verdict"),
              "a card's offered label": none([], ["card:t1:0"], "an approval with nothing to keep")}
        n1 = none(["a1234567890", "a0987654321"], [], "agreed with the plan; nothing durable", by="local_test")
        n2 = none([], ["card:t2:0"], "a one-off wording pick for that card", by="local_test")
        cite_bad = {k: none([], ["r-77"], "fixed in the gate instead", cites=[bad[c]])
                    for k, c in (("a failing source", "commit"), ("a log as source", "log"))}
        n3 = none([], ["r-77"], "fixed in the gate instead", by="local_test", cites=[good["commit"]])
        n4 = none(["a1234567890"], [], "filed after all, from the gate commit", by="local_test", cites=[good["commit"]])
        f, fwhy = filed()
        case("none records a hand-back or correction read with nothing to file, with a reason of 4 words or more; "
             "one with no id, a short reason, a bad id or a row without the user's words is refused: "
             + ", ".join(k for k, (c, m) in nb.items() if not (c == 1 and m.startswith("refused"))),
             all(c == 1 and m.startswith("refused") for c, m in nb.values()) and n1[0] == 0 and n2[0] == 0
             and n4[0] == 0 and sum(1 for r in log_rows() if r.get("event") == "nothing") == 5)
        case("none --cite keeps where it was handled instead, checked now; a failing source or a log is refused: "
             + ", ".join(k for k, (c, m) in cite_bad.items() if not (c == 1 and m.startswith("refused"))),
             n3[0] == 0 and all(c == 1 and m.startswith("refused") for c, m in cite_bad.values())
             and "unknown commit" in cite_bad["a failing source"][1] and "log" in cite_bad["a log as source"][1]
             and log_rows()[-1].get("sources") == [good["commit"]])
        case("filed() names every hand-back and correction filed or read with nothing, at its newest row, and each "
             "ledger row an entry cites or asks from; a bare none is marked, and a later one with a source or an "
             "entry clears it; a store with no log can't say",
             fwhy is None and set(f["handback"]) == {hb, "a1234567890", "a0987654321"}
             and set(f["correction"]) == {"r-77", "card:t2:0"} and {"r-77", "card:t1:0", "card:t2:0"} <= f["ledger"]
             and f["bare"] == {"a0987654321", "card:t2:0"}
             and all(v for v in list(f["handback"].values()) + list(f["correction"].values()))
             and filed(os.path.join(root_, "nowhere"))[1] is not None)
        for subj in ("billing.handback", "kickoff.correction"):     # the store's counts below don't include these
            body = subj.split(".")[0]
            t = open(os.path.join(KB, body + ".md")).read()
            i = t.index(f"### {subj}")
            j = t.find("\n### ", i + 4)
            put(f"knowledge/{body}.md", (t[:i] + (t[j + 1:] if j >= 0 else "")).rstrip("\n") + "\n")

        # Each miss, planted after the add: the record moved under a passing entry.
        def moved(fn, undo, want):
            fn()
            r = check()
            undo()
            return any(want in w for _, w in r["misses"]) or any(want in f for f in r["faults"])
        text = open(os.path.join(root_, "docs", "plan.md")).read()
        case("known bad: an anchor edited out of its file after the add is a miss",
             moved(lambda: put("docs/plan.md", "rewritten"), lambda: put("docs/plan.md", text), "moved anchor"))
        put("repo/a.txt", "the refund page ships first\n")
        g("commit", "-q", "-am", "b")
        case("known bad: an anchor edited out of a commit's file at HEAD is a miss, though the commit stays",
             any("at repo HEAD" in w for _, w in check()["misses"]))
        put("repo/a.txt", "the invoice page ships first\n")
        g("commit", "-q", "-am", "c")
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 10}}}, open(ADO_CACHE, "w"))
        case("known bad: an ADO item edited after its citation is a moved revision",
             any("moved ADO revision" in w for _, w in check()["misses"]))
        json.dump({"pulled": time.time() - 5 * 86400, "items": {"4242": {"rev": 10}}}, open(ADO_CACHE, "w"))
        st = check()
        case("an ADO cache older than ADO_DAYS doesn't run, and isn't a miss until STALE_DAYS pass",
             any("days old" in w for _, w in st["did_not_run"]) and not st["misses"])
        later = time.time() + 31 * 86400
        json.dump({"pulled": time.time() - 5 * 86400, "items": {"4242": {"rev": 9}}}, open(ADO_CACHE, "w"))
        case("known bad: 31 days with no passing check is a miss", any("no passing check" in w for _, w in check(now=later)["misses"]))
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 9}}}, open(ADO_CACHE, "w"))
        check(record=True)
        ck = checked()
        case("--record keeps each passing entry's time and each body's counts outside the store, and the 30 days "
             "count from it", set(ck["entries"]) >= {"k-0002", "k-0003", "k-0004"} and ck["bodies"]["kickoff"]["pass"] == 2
             and not os.path.exists(os.path.join(KB, "checked.json")) and not check(now=time.time() + 10 * 86400)["misses"])
        pickle.dump(dict(fig, idx={k: v for k, v in fig["idx"].items() if k != "1100:2000"}), open(figpkl, "wb"))
        case("known bad: a node deleted from a fresh Figma index is dead",
             any("dead Figma node" in w for _, w in check()["misses"]))
        pickle.dump(dict(fig, text={}), open(figpkl, "wb"))
        case("known bad: a Figma node whose text changed is a moved anchor",
             any("on Figma node" in w for _, w in check()["misses"]))
        pickle.dump(dict(fig, built=time.time() - 9 * 86400), open(figpkl, "wb"))
        case("a Figma index older than FIGMA_DAYS doesn't run", any("days old" in w for _, w in check()["did_not_run"]))
        pickle.dump(fig, open(figpkl, "wb"))
        put("docs/blob.bin", "other bytes")
        case("known bad: a hashed file that changed is a miss", any("changed hash" in w for _, w in check()["misses"]))
        put("docs/blob.bin", "fixed bytes")

        # Store faults.
        wtext = open(os.path.join(KB, "billing.md")).read()
        entry = ("\n### billing.{t}\n- id: k-00{n}; status: {st}; written: " + day + "; by: x\n"
                 "- question: \"{q}\" ({w})\n- answer: a.\n- source: {c}\n")
        hand = {"dup": entry.format(t="naming", n=10, st="live", q="dup", w="phrased by the writer", c=good["commit"]),
                "twin": entry.format(t="renamed", n=11, st="live", q="twin", w="phrased by the writer", c=good["file"]),
                "old": entry.format(t="old", n=12, st="superseded", q="old", w="phrased by the writer", c=good["commit"]),
                "loose": "\n### billing.loose\n- id: k-0013; status: live; written: " + day + "; by: x\n- answer: none.\n",
                "card": entry.format(t="card", n=14, st="live", q="should use billing engine", w="their words, ledger card:t1:0",
                                     c=good["commit"]),
                "sameq": entry.format(t="sameq", n=16, st="live", q="Billing or Billing Engine", w="phrased by the writer",
                                      c=good["commit"]),
                "transcript": entry.format(t="heard", n=15, st="live", q="heard", w="phrased by the writer",
                                           c='file `transcripts/call.md` "we said"'),
                "ado twin": entry.format(t="adoa", n=17, st="live", q="adoa", w="phrased by the writer", c=good["ado title"])
                + entry.format(t="adob", n=18, st="live", q="adob", w="phrased by the writer",
                               c='ado 4242 System.Title "Rename Billing to Billing"'),
                "comments": entry.format(t="said", n=19, st="live", q="said", w="phrased by the writer", c=good["ado comment"])}
        want = {"dup": "duplicate live subject billing.naming", "twin": "share one file anchor", "old": "status other than live",
                "loose": "no source", "card": "holds none of the user's words", "transcript": "only source",
                "sameq": "share one question", "ado twin": "share one ado anchor", "comments": "ADO comments are its only source"}
        got = {k: moved(lambda k=k: put("knowledge/billing.md", wtext + hand[k]), lambda: put("knowledge/billing.md", wtext),
                        want[k]) for k in hand}
        case("known bad, written by hand: a second live entry on a subject, a new subject on a live entry's anchor, a "
             "superseded entry left on a page, an entry missing its source, a question from a card's offered label, "
             "a transcript or ADO comments as the only source, two subjects on one ADO field anchor, and a question "
             "another live entry settles each fault or miss: " + ", ".join(k for k, v in got.items() if not v), all(got.values()))
        case("known bad: a question edited away from the ledger row it says it came from is a miss",
             moved(lambda: put("knowledge/billing.md", wtext.replace('"billing or billing engine" (their words',
                                                                     '"what is billing" (their words')),
                   lambda: put("knowledge/billing.md", wtext), "isn't in the user's words"))
        ptext = open(os.path.join(KB, "mine.md")).read()
        case("known bad: an entry on a page that takes none is a fault",
             moved(lambda: put("knowledge/mine.md", ptext + hand["dup"].replace("billing.", "mine.")),
                   lambda: put("knowledge/mine.md", ptext), "entries: none"))
        put("knowledge/stray.md", "# stray\n")
        os.rename(os.path.join(KB, "kickoff.md"), os.path.join(KB, "kickoff.md.x"))
        fs = check()["faults"]
        case("known bad: a page the index doesn't name is an orphan, and an index body with no page is a fault",
             any("orphan page: stray.md" in f for f in fs) and any("names kickoff.md" in f for f in fs))
        os.remove(os.path.join(KB, "stray.md"))
        os.rename(os.path.join(KB, "kickoff.md.x"), os.path.join(KB, "kickoff.md"))

        # Rule faults.
        base = check()
        case("known good: the planted store, its pages and its rules pass with no fault, and the page that takes "
             "no entries wants no rule", not base["faults"] and not base["misses"] and base["pass"] == base["live"] == 5)
        variants = {"no paths": "---\nother: x\n---\nkickoff.\nknowledge/kickoff.md\nrecall\n",
                    "no frontmatter": "kickoff work.\nknowledge/kickoff.md\nrecall\n",
                    "unquoted glob": krule.replace('"docs/plan.md"', "docs/plan.md"),
                    "another key": krule.replace("paths:\n", "description: x\npaths:\n"),
                    "private glob": krule.replace('"docs/plan.md"', '"_mine/**"'),
                    "dead glob": krule.replace("docs/plan.md", "nowhere/**"),
                    "too long": krule + "a\nb\nc\n",
                    "no page": krule.replace("knowledge/kickoff.md", "the page"),
                    "no recall": krule.replace("`recall`", "search"),
                    "traps drift": krule.replace("Name traps: none.", "Name traps: none at all."),
                    "import": krule + "@docs/plan.md\n"}
        want = {"no paths": "no paths", "no frontmatter": "no paths", "unquoted glob": "no paths",
                "another key": "double-quoted glob", "private glob": "reach into a kb.private", "dead glob": "match no file",
                "too long": "7 lines", "no page": "doesn't name its page", "no recall": "recall",
                "traps drift": "word for word", "import": "@ import"}
        got = {}
        for k, t in variants.items():
            put(".claude/rules/kb-kickoff.md", t)
            got[k] = any(want[k] in f for f in check()["faults"])
        put(".claude/rules/kb-kickoff.md", krule)
        os.remove(os.path.join(RULES, "kb-billing.md"))
        got["missing"] = any("no pointer rule kb-billing.md" in f for f in check()["faults"])
        put(".claude/rules/kb-billing.md", wrule)
        os.makedirs(os.path.join(RULES, "sub"))
        put(".claude/rules/sub/other.md", "loads everywhere\n")
        got["unscoped rule a folder down"] = any("sub/other.md has no paths" in f for f in check()["faults"])
        shutil.rmtree(os.path.join(RULES, "sub"))
        case("known bad: a rule with no paths (none at all, or an unquoted glob), another frontmatter key, a glob "
             "into a kb.private folder or matching nothing, 7 lines, no page, no recall, name traps not the index's, "
             "an @ import, a body with no rule, and an unscoped rule a folder down each fault: "
             + ", ".join(k for k, v in got.items() if not v), all(got.values()))
        case("and the store is whole again", (lambda r: not r["faults"] and not r["misses"])(check()))

        # --new: red once per new finding.
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 10}}}, open(ADO_CACHE, "w"))
        first, second = flag_new(check()), flag_new(check())
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 11}}}, open(ADO_CACHE, "w"))
        third = flag_new(check())
        json.dump({"pulled": time.time(), "items": {"4242": {"rev": 9}}}, open(ADO_CACHE, "w"))
        fourth = flag_new(check())
        case("--new: a miss is new on its first run, not on the next (its revision moving again included), and "
             "a finding that clears drops off", first and not any(first.values()) and second and all(second.values())
             and third and all(third.values()) and fourth == {})

        # The settings: each folder from its kb key, relative ones from kb.root; unset, the defaults under the project.
        home = os.path.join(root_, "home")
        os.makedirs(home)
        cfg = os.path.join(root_, "cfg.json")
        json.dump({"kb": {"root": root_, "dir": "store", "rules": "rules2", "private": ["_mine", "~/own"],
                          "cache": "~/kbstate"}, "ledger": {"dir": os.path.join(root_, "led")},
                   "logs": {"backups": [os.path.join(root_, "log-backups")]},
                   "transcripts": {"dir": os.path.join(root_, "transcripts")}}, open(cfg, "w"))
        os.environ.update(HOME=home, CLAUDE_PROJECT_DIR=os.path.join(root_, "docs"))
        os.environ[kit_config.ENV] = cfg
        kit_config.reset()
        CONFIG.update({k: None for k in CONFIG})
        set_ = (kb_dir(), rules_dir(), private_dirs(), cache_dir(), ledger_path(), log_dirs(), transcript_dirs())
        json.dump({}, open(cfg, "w"))
        kit_config.reset()
        unset = (root(), kb_dir(), rules_dir(), private_dirs(), cache_dir(), transcript_dirs())
        PROJECT = repo
        kit_config.reset()
        named = (root(), kb_dir())
        PROJECT = None
        case("settings: kb.dir, kb.rules, kb.private and kb.cache resolve from kb.root or ~, the ledger, log backups "
             "and transcripts from their own keys; unset, the store and rules sit under the project folder (--project "
             "when given), nothing is private and the state goes under ~/.cache",
             set_ == (os.path.join(root_, "store"), os.path.join(root_, "rules2"),
                      [os.path.join(root_, "_mine"), os.path.join(home, "own")], os.path.join(home, "kbstate"),
                      os.path.join(root_, "led", "requests.jsonl"), [os.path.join(root_, "log-backups")],
                      [os.path.join(root_, "transcripts")])
             and unset == (os.path.join(root_, "docs"), os.path.join(root_, "docs", "knowledge"),
                           os.path.join(root_, "docs", ".claude", "rules"), [],
                           os.path.join(home, ".cache", kit_config.NAME, "kb"), [])
             and named == (repo, os.path.join(repo, "knowledge")))
    finally:
        CONFIG.clear()
        CONFIG.update(kept)
        PROJECT = kept_project
        for k, v in env_kept.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        kit_config.reset()
        shutil.rmtree(root_, ignore_errors=True)
    print(f"selftest: {sum(ok)} of {len(ok)} checks passed")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(kit_config.run(lambda: main(sys.argv[1:])))
