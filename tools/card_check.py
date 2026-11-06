#!/usr/bin/env python3
"""card_check.py - check a question card before the user sees it: bare ids, paths they can't open, the
card's shape, and questions the record may already answer.

    python tools/card_check.py <card.json>              the AskUserQuestion input ({"questions": [...]}), or - for stdin
    python tools/card_check.py <card.json> --no-record  the same without the record lookup (it says so)
    python tools/card_check.py <card.json> --session ID the Claude Code session asking (default $CLAUDE_CODE_SESSION_ID)
    python tools/card_check.py --selftest               planted cards: each flag fires on its bad case, none on a clean one
    python tools/card_check.py --share [--days 7]       per day, the cards asked that a run checked first, by question text

WHY. Much of what goes wrong between a session and the user is in what the session asks or tells them:
a question the record already answers, a bare node or work-item id they have to look up, a path they
can't open. Claude Code can't refuse a question card, so a session runs this on each card before it
asks, and --share reports how often that happened.

FLAGS, each with the question it sits in:
  bare id        a Figma node id or #ADO id outside a URL (bare_ids.count, the daily count's own rule). The
                 card prints back with each one linked in place: an ADO id to its work item (ado.org and
                 ado.project), a Figma node into the file in figma.files whose cached index (figma_family)
                 holds it, else into the one file a Figma URL on the card names; one with neither stays bare
                 and is named
  path           a ~/ path or a ../ path; give the path from the session's start folder, or an absolute one
  shape          not 2-4 options, or a header over 12 characters
  estimate       a cost the card calls believed, a guess, a ballpark or not measured: measure it first
  answered?      a past card in the request ledger whose question shares at least 60% of this question's
                 content words (a lead: open it before asking)
  settled draft  drafts_store's override or own-open rule fails a draft in the drafts file (figma.drafts or
                 $FIGMA_DRAFTS), and the question names drafts.md or posting Figma comments (every failing
                 draft is flagged), or shares 3 or more content words with that draft's subject, its heading
                 before the ' — ' (only that draft): it is written to open a new thread instead of folding
                 into an open one, or it links the user's own open comment, which the fix goes into instead.
                 An own-open check that could not run is flagged too, never passed. The drafts check runs on
                 every card; with no drafts file configured it has nothing to read, and the summary says so
Not here: a flag for a recommended option that is setup work (settings, hooks, gates, a delete) with no
challenger run first; it needs a session coordinator that maps sessions to logs and lists setup paths.

RECORD. Each question, with its options, also runs through recall.py's full search for 4 terms, OR'd:
ids and quoted names first, then capitalised names, then the words rarest in the request ledger's
messages and card questions. It searches logs, ADO as cached, transcripts, git, notes (the request
ledger among them), memory and Figma, each as configured for recall.py, as of now. The asking
session's own log counts only up to the user's last message there (from the ledger): what the session
wrote since is the card's own draft. What prints under the flags, as leads to open before asking, is
recall's own first round of its ranked list (`shown`): its first log place and the strongest hit of
each other source (ADO, notes, transcripts, git, Figma), ties newest first, sources in order of their
strongest. Memory is searched, not shown. Each source's status prints beside it: ran, partial, not
configured or did not run. The lookup's child runs figma_client in its gate lane with a deadline at
half RECORD_SECONDS, so a rate limit costs Figma alone. recall's first 10 places go to
`check(..., reader=)`, which has no reader yet, so nothing is flagged from them. A lookup over
RECORD_SECONDS, or one that fails, prints "record lookup did not run" and exits 2 when nothing else
flagged; --no-record skips it and says so.

RUNS. Every run appends one line to `card_check.runs` in the product-os config (default
~/.local/share/product-os/card-checks.jsonl): time, the questions, the flag count, whether the record
lookup ran, and per question what was shown (source, id, link, the record printed for a log place)
beside recall's first 3 places, so a later replay can score both. --share reads it.

SESSION. The asking session is --session (a Claude Code session id, as the request ledger keeps it),
else $CLAUDE_CODE_SESSION_ID. When one session checks a card another drafted, name the other.

EXIT. 0 clean, 1 with flags, 2 when the card or the request ledger couldn't be read (ledger.py writes
the ledger, under ledger.dir), or the record lookup did not run and nothing else flagged.

BLIND. Word overlap is a lead, not a match: a reworded question that was answered slips past, and a
new question on an old subject can flag. What prints is one hit per source, the strongest by recall's
match strength, which need not be the one that settles the question. A log place prints one record,
where the user typed it else its newest; an answer elsewhere in that session, or in its subagents'
logs, doesn't print. It doesn't judge whether a question is a craft call. An id in a form bare_ids
doesn't count (an ADO id without #, a node id in its dashed form) passes as linked.
Not here either: pinning a named knowledge page above a question; it needs a knowledge index whose names
recall can match.
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import bare_ids  # noqa: E402
import kit_config  # noqa: E402
import pushback_score  # noqa: E402

PATH = re.compile(r"(?<![\w/])(~/|\.\./)[^\s)`'\"]+")
GUESS = re.compile(r"\b(believed|not measured|unmeasured|my guess|a guess|ballpark)\b", re.I)
WORD = re.compile(r"[a-z][a-z0-9-]{2,}")
STOP = set("""the and for that this with what should from have has are was were will would can could
into about which when where there their them they you your his her its our not but all any each
one two now then than also only just more most some such does did done how why who whom whose
it's don't isn't keep make made take want wants need needs get got use used""".split())
OVERLAP = 0.6


def runs_path():
    """Where each run is logged: card_check.runs in the product-os config, else
    ~/.local/share/product-os/card-checks.jsonl."""
    v = kit_config.get("card_check", "runs")
    if isinstance(v, str) and v.strip():
        return os.path.abspath(os.path.expanduser(v))
    return kit_config.home_dir(os.path.join(".local", "share"), "card-checks.jsonl")


def ledger_path():
    """The request ledger, where ledger.py writes it (ledger.dir), as recall.py finds it."""
    import recall
    return recall.ledger_path()


def words(text):
    return {w for w in WORD.findall((text or "").lower()) if w not in STOP}


# ------------------------------------------------------------------------------------- lookup terms
# The 4 terms a question's record lookup searches for. An id is searched as it is: an ADO id, a Figma node
# id (not a time like 21:34 or two 1-2 digit numbers; a full stop after one ends the sentence), a file name,
# a commit hash (its first 7, as git and recall print it). A quoted name is one term. Then capitalised names,
# then the words the request ledger holds least often: a rare word says more about which record it is.
TERM_IDS = re.compile(r"#\d{3,5}\b|(?<![\w:/.-])(\d{1,6})[:-](\d{1,6})(?![\w:-]|\.\w)"
                      r"|\b[\w.-]+\.(?:md|py|json|astro|mjs)\b"
                      r"|(?<![\w-])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])")
TERM_QUOTED = re.compile(r"(?<![A-Za-z])'([^'\n]{3,40})'(?![A-Za-z])|\"([^\"\n]{3,40})\"")
TERM_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
TERM_STOP = set("""the and for that this with what should from have has are was were will would can could into
about which when where there their them they you your his her its our not but all any each one two now
then than also only just more most some such does did done how why who whom whose don isn keep make made
take want wants need needs get got use used here these those being been very still yet same other another
every both either neither again before after while because since until within without please pls yes okay
recommended option options card question asked ask answer answered new old today yesterday tomorrow week
day time way thing things like look looks show shows say says said know see lines line file files page
pages build built site session sessions which whether instead rather""".split())
NAMES = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+|[A-Z][a-z]+[A-Z]\w+)\b")


def vocabulary(rows):
    """How many request-ledger rows hold each word, over their text and card questions."""
    c = collections.Counter()
    for r in rows or []:
        c.update({w.lower() for w in TERM_WORD.findall(" ".join(x for x in (r.get("text"), r.get("question"))
                                                                 if isinstance(x, str)))})
    return c


def terms(text, k=4, vocab=None):
    """The k terms of a text a lookup searches for: ids and quoted names first, then capitalised names, then
    the rarest words in vocab (vocabulary()). The words are read with the ids and quotes taken out, so a hash
    or a node id isn't read as a word too."""
    vocab = vocab or {}
    text = re.sub(r"(?<=[A-Za-z])['’]s\b", "", text or "")
    ids = []
    for m in TERM_IDS.finditer(text):
        a, b = m.group(1), m.group(2)
        if a is not None and len(a) <= 2 and len(b) <= 2:
            continue
        t = m.group(0)
        ids.append(t[:7] if re.fullmatch(r"[0-9a-f]{8,40}", t) else t)
    quoted = [a or b for a, b in TERM_QUOTED.findall(text)]
    names = NAMES.findall(text)
    rest = TERM_QUOTED.sub(" ", TERM_IDS.sub(" ", text))
    found = {w.lower() for w in TERM_WORD.findall(rest)} - TERM_STOP
    rare = sorted(found, key=lambda w: (vocab.get(w, 0) == 0, vocab.get(w, 0), w))
    out = []
    for t in ids + quoted + names + rare:
        t = t.strip()
        if t and t.lower() not in {o.lower() for o in out} and t.lower() not in TERM_STOP:
            out.append(t)
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------------------------- record lookup
# Each question, with its options, runs through recall's full search; recall's first round of its ranked list
# prints beside it (`shown`), its first 3 places are logged beside that, and its first 10 go to `reader`. Figma
# comes from recall's own fetch, in figma_client's gate lane with a deadline (child_env), so a 429 costs Figma alone.
RECORD_SOURCES = ("logs", "ado", "transcripts", "git", "notes", "memory", "figma")
SHOWN_SOURCES = ("logs", "ado", "notes", "transcripts", "git", "figma")
RECORD_TOP, RECORD_SHOW, RECORD_SECONDS = 10, 3, 150
URL = re.compile(r"https?://[^\s)>\]\"'`]+")


def question_text(q):
    """A question with its options, the words its record lookup reads: the options hold the choice. A label and
    its description go on lines of their own, so a name ending one and a capital starting the next aren't read
    as one name ("Matches Delta" and "The newer copy" are not "Delta The")."""
    opts = [x.strip() for o in q.get("options") or [] if isinstance(o, dict)
            for x in (str(o.get("label") or ""), str(o.get("description") or "")) if x.strip()]
    return "\n".join([str(q.get("question") or "")] + opts)


def lookup_terms(q, vocab=None):
    """The 4 terms the lookup searches for, OR'd: terms() on the question and its options."""
    return terms(question_text(q), 4, vocab)


def source_status(x):
    """One source's result as a word: a source with nothing configured is not a search that did not run."""
    if x.get("off"):
        return "not configured"
    if x["ran"]:
        return "partial" if x["partial"] else "ran"
    return "did not run"


def shown(qr):
    """What prints for one question: recall's own first round of its ranked list (recall.ranked with top= the
    number of SHOWN_SOURCES that have a hit). That is its first log place and each other source's strongest
    hit, ties newest first, the sources in order of their strongest. Memory is searched, not shown."""
    import recall
    sub = {"src": {n: r for n, r in qr["src"].items() if n in SHOWN_SOURCES}}
    k = sum(1 for r in sub["src"].values() if r["ran"] and r["hits"])
    return [e for e in recall.ranked(sub, top=k) if e["place"] and e["place"] <= k]


def record_lookup(card, own=None, since=None, before=None, searcher=None, ts=None, vocab=None):
    """[{"terms", "top": [entry, ...], "shown": [entry, ...], "status"}] per question: the first RECORD_TOP
    places of recall's full search, as it prints them (recall.ranked), and what card_check prints (`shown`).
    own: the asking session's id; its log counts only before `since`, the user's last message there (what
    they said earlier in the session is record too). ts: each question's terms, else lookup_terms(q, vocab)."""
    import recall
    recall.CONFIG["figma_canvas"] = "cache"
    opts = recall.parse(["x", "--no-pull"])
    opts.sources = RECORD_SOURCES
    ts = ts if ts is not None else [lookup_terms(q, vocab) for q in card.get("questions", [])]
    asks = [{"labels": ["|".join(t)], "since": None, "before": before} for t in ts if t]
    res = iter((searcher or recall.search)(asks, opts) if asks else [])
    out = []
    for t in ts:
        if not t:
            out.append({"terms": [], "top": []})
            continue
        qr = next(res)
        r = qr["src"].get("logs")
        if own and since and r and r["ran"]:
            r["hits"] = [h for h in r["hits"] if not (recall.skey(h["key"]).startswith(own[:8]) and (h["ts"] or "") >= since)]
        top = [e for e in recall.ranked(qr) if e["place"] and e["place"] <= RECORD_TOP]
        out.append({"terms": t, "top": top, "shown": shown(qr),
                    "status": {n: source_status(x) for n, x in qr["src"].items()}})
    return out


def chosen(e):
    """The record an entry prints: a log session's where the user typed it, else its newest; any other entry's hit."""
    if e["src"] == "logs":
        return max(e["hits"], key=lambda h: (h["role"].startswith("you"), h["ts"] or ""))
    return e["hit"]


def link_of(e):
    """Where to open an entry, as an absolute path or a URL: a log session's copy holding the printed record; the
    URL its head carries (ADO, Figma); a note's or memory card's file and line; a transcript's file and line;
    else its id (a commit)."""
    h = chosen(e)
    if e["src"] == "logs":
        return os.path.expanduser(h.get("label") or e["sid"])
    head, ids = h.get("head") or "", h.get("ids") or [""]
    m = URL.search(head)
    if m:
        return m.group(0)
    if ids[0].startswith("file:"):
        at = re.match(r"\S+?:(\d+)\b", head)
        return os.path.expanduser(ids[0][len("file:"):]) + (f":{at.group(1)}" if at else "")
    if ids[0].startswith("transcript:"):
        import recall
        d = next((p for p in recall.transcript_dirs() if os.path.isdir(p)), None)
        at = re.search(r"\bline (\d+)", head)
        name = ids[0][len("transcript:"):] + (".txt" if "(raw .txt" in head else ".md")
        return (os.path.join(d, name) if d else name) + (f":{at.group(1)}" if at else "")
    return ids[0] or head[:80]


def hit_row(e):
    """One entry as found keeps it: its link, date and full excerpt beside the clipped line card_check prints."""
    h = chosen(e)
    return {"place": e["place"], "src": e["src"], "id": e.get("sid") or (h.get("ids") or [""])[0],
            "link": link_of(e), "date": (h.get("ts") or "")[:19], "role": h.get("role", ""),
            "excerpt": h.get("excerpt") or "", "line": top_line(e)}


def top_line(e):
    """One printed place: a log session by the record where the user typed it, else its newest; any other hit
    by its head and excerpt."""
    h = chosen(e)
    if e["src"] == "logs":
        return f"{e['place']:>2}. logs  {e['sid'][:8]}  {(h['ts'] or '')[:16]}  {h['role']}: {_clip(h.get('excerpt'), 160)}"
    return f"{e['place']:>2}. {e['src']}  {(h.get('head') or '')[:150]}\n        {_clip(h.get('excerpt'), 160)}"


def _clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def record_lines(found):
    """[(question number, line)] for what each question's lookup shows (`shown`), after a line naming its terms
    and any source that didn't run."""
    out = []
    for n, f in enumerate(found, 1):
        if not f["terms"]:
            out.append((n, "record   no terms to search for"))
            continue
        gone = [f"{s} {v}" for s, v in (f.get("status") or {}).items() if v != "ran"]
        out.append((n, f"record   {' | '.join(f['terms'])}: the first log place and each source's strongest hit; "
                       + (", ".join(gone) if gone else "every source ran")))
        out += [(n, "  " + top_line(e).replace("\n", "\n    ")) for e in f["shown"]]
    return out


def child_env(seconds, now=None):
    """The lookup child's environment: figma_client's gate lane and a deadline at half the lookup's time, so a
    Figma rate limit ends Figma's fetch (recall prints it as did not run) before the lookup's own deadline."""
    return dict(os.environ, FIGMA_CLIENT_LANE="gate",
                FIGMA_CLIENT_DEADLINE_AT=f"{(now or time.time()) + seconds / 2:.0f}")


def run_record(card, own=None, since=None, seconds=RECORD_SECONDS, vocab=None):
    """record_lookup in a child process with a deadline: (found, None) or (None, why it did not run). The terms
    are chosen here, from the ledger's vocabulary, so the child reads no ledger."""
    ts = [lookup_terms(q, vocab) for q in card.get("questions", [])]
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "card.json"), os.path.join(tmp, "found.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"card": card, "own": own, "since": since, "terms": ts}, f)
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--record-child", src, dst],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True,
                             env=child_env(seconds))
        try:
            _, err = p.communicate(timeout=seconds)
        except subprocess.TimeoutExpired:
            if hasattr(os, "killpg"):
                os.killpg(p.pid, signal.SIGKILL)
            else:
                p.kill()
            p.wait()
            return None, f"over {seconds} s"
        if p.returncode or not os.path.exists(dst):
            return None, (err.decode("utf-8", "replace").strip().splitlines() or [f"exit {p.returncode}"])[-1][:200]
        with open(dst, encoding="utf-8") as f:
            return json.load(f), None


def record_child(src, dst):
    with open(src, encoding="utf-8") as f:
        a = json.load(f)
    found = record_lookup(a["card"], a.get("own"), a.get("since"), ts=a.get("terms"))
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(found_json(found), f)
    return 0


def found_json(found):
    """record_lookup's result as the child hands it back: per question its terms, status, recall's first
    RECORD_TOP places, and what is shown, each hit with its link, date and full excerpt; and the lines."""
    keep = [{"terms": f["terms"], "status": f.get("status", {}),
             "top": [hit_row(e) for e in f["top"]], "shown": [hit_row(e) for e in f.get("shown", [])]}
            for f in found]
    return {"found": keep, "lines": record_lines(found)}


def shown_log(found):
    """Per question, for the runs log: what was shown and recall's first RECORD_SHOW places, by source, id,
    link and, for a log place, the record printed."""
    def brief(x):
        return {"src": x["src"], "id": x["id"], "link": x["link"],
                **({"record": f"{x['date']} {x['role']}"} if x["src"] == "logs" else {})}
    return [{"shown": [brief(x) for x in f.get("shown", [])], "first3": [brief(x) for x in f["top"][:RECORD_SHOW]]}
            for f in found or []]


# ------------------------------------------------------------------------------------- answered before
def past_cards(rows):
    """The request ledger's answered cards: each row one card question (`question`) with its answer (`text`)."""
    return [r for r in rows or [] if r.get("source") == "card" and r.get("question") and r.get("text")]


def answered(question, cards, limit=3):
    """[(share, row)] for each past card whose question holds at least OVERLAP of this question's content words.
    The past card's question is what is compared, never its answer."""
    q = words(question)
    if len(q) < 4:
        return []
    hits = []
    for r in cards:
        shared = len(q & words(r["question"])) / len(q)
        if shared >= OVERLAP:
            hits.append((shared, r))
    hits.sort(key=lambda h: (-h[0], h[1].get("ts", "")))
    return hits[:limit]


# ------------------------------------------------------------------------------------- settled drafts
# A question about Figma comment drafts: it names the drafts file, or posting or sending comments or drafts.
DRAFTISH = re.compile(r"drafts\.md|\bFigma (?:comment|note|draft)s?\b"
                      r"|\b(?:post|send)\w*\b[^.?!]{0,60}\b(?:comment|draft)s?\b", re.I)


def settled_rules():
    """drafts_store's structure rules whose problem means the card asks about a draft that shouldn't be posted as
    it is, and the own-open check that could not run, which is named, never passed."""
    import drafts_store
    return ("override", "own-open", drafts_store.OWN_NOT_RUN)


def drafts_file():
    """The drafts file drafts_store reads ($FIGMA_DRAFTS, else figma.drafts), or None."""
    import drafts_store
    return drafts_store.drafts_path()


def settled_drafts():
    """drafts_store's override and own-open problems in the drafts file: a draft written to open a new thread, or
    one that links the user's own open comment. Each row (file, line, rule, words, title): title is the draft's
    subject, its heading before the ' — ' that opens the status. No drafts file configured: no rows."""
    import drafts_store
    path = drafts_store.drafts_path()
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads = {b["first"] + 1: b["head"] for b in drafts_store.blocks(text)}
    rules = settled_rules()
    return [x + (draft_title(heads.get(x[1], "")),) for x in drafts_store.structure(text, path) if x[2] in rules]


# A question that names a failing draft's subject asks about that draft though it says nothing of comments or
# drafts ("Post the pricing banner photo ask to Figma?"): it shares this many of the subject's content words.
TITLE_SHARED = 3


def draft_title(head):
    """A draft heading's subject: the text before the ' — ' that opens its status (NEW on ..., EDIT ...)."""
    return re.split(r"\s+—\s+", head or "", maxsplit=1)[0].strip()


# ------------------------------------------------------------------------------------- the check
def check(card, cards, drafts=None, found=None, reader=None):
    """[(question number, flag, detail)]. drafts: settled_drafts or a stand-in; without one the settled-draft
    flag isn't checked. found: run_record()'s lookups, one per question. reader(question, top) -> [(flag,
    detail)] reads a question's top RECORD_TOP for what the record settles; without one (today) nothing is
    flagged from them."""
    flags, seen, failing = [], set(), {}
    for n, (q, f) in enumerate(zip(card.get("questions", []), found or []), 1):
        if reader and f.get("terms"):
            flags += [(n, flag, detail) for flag, detail in reader(q, f["top"])]

    def failing_drafts():
        if "rows" not in failing:   # read once per card, an empty result included
            try:
                failing["rows"] = list(drafts())
            except Exception as e:  # noqa: BLE001 -- a drafts check that could not run is named, never passed
                failing["rows"] = [("drafts file", 0, "did not run", f"{type(e).__name__}: {e}")]
        return failing["rows"]
    for n, q in enumerate(card.get("questions", []), 1):
        texts = [q.get("question", "")] + [o.get("label", "") + " " + o.get("description", "")
                                           for o in q.get("options", [])]
        if drafts:
            wide = any(DRAFTISH.search(t) for t in texts)
            said = words(" ".join(texts))
            for name, line, rule, problem, *title in failing_drafts():
                subject = words(title[0] if title else "")
                if (line, rule) not in seen and (wide or len(subject & said) >= TITLE_SHARED):
                    seen.add((line, rule))
                    flags.append((n, "settled draft", f"{name}:{line} {rule}: {problem[:150]}"))
        for t in texts:
            bf, ba, _, _ = bare_ids.count(t)
            if bf or ba:
                flags.append((n, "bare id", f"{bf} Figma, {ba} ADO in: {t[:90]}"))
            for m in PATH.finditer(t):
                flags.append((n, "path", m.group(0)))
            for m in GUESS.finditer(t):
                flags.append((n, "estimate", f"'{m.group(0)}': measure it first from past work of the same kind, "
                                             f"or leave the cost off the card"))
        k = len(q.get("options", []))
        if not 2 <= k <= 4:
            flags.append((n, "shape", f"{k} options"))
        if len(q.get("header", "")) > 12:
            flags.append((n, "shape", f"header {q.get('header')!r} is over 12 characters"))
        for shared, r in answered(q.get("question", ""), cards):
            flags.append((n, "answered?", f"{shared:.0%} shared with {r.get('ts', '')[:10]} session "
                                          f"{(r.get('session') or '?')[:8]}: {r['question'][:100]} -> {r['text'][:60]}"))
    return flags


def log_run(card, flags, path, record=None, found=None):
    row = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "questions": [q.get("question", "")[:80] for q in card.get("questions", [])],
           "flags": len(flags)}
    if record is not None:
        row["record"] = record
    if found:
        row["shown"] = shown_log(found)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def checked(card, cards, rows, sid, no_record=False, runs=None, runner=None, drafts=settled_drafts):
    """(the lines main prints for one card, its exit code), the run logged to runs: the flags; each question's
    record lines; the did-not-run line; the card with its ids linked when one is bare; and the summary. sid: the
    asking session, whose own log counts only up to the user's last message there (from the ledger rows).
    runner stands in for run_record."""
    found, why = None, "--no-record"
    if not no_record:
        last = pushback_score.last_before(pushback_score.user_times(rows).get(sid, []),
                                          dt.datetime.now(dt.timezone.utc)) if sid else None
        since = last and last.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        found, why = (runner or run_record)(card, sid, since, vocab=vocabulary(rows))
    flags = check(card, cards, drafts, (found or {}).get("found"))
    log_run(card, flags, runs or runs_path(), record="ran" if found else f"did not run: {why}",
            found=(found or {}).get("found"))
    out = [f"Q{n}  {kind:10} {what}" for n, kind, what in flags]
    lines = (found or {}).get("lines", [])
    for n in range(1, len(card.get("questions", [])) + 1):
        out += [f"Q{m}  {line}" for m, line in lines if m == n]
    if not found:
        out.append(f"record   lookup did not run: {why}; no question was checked against the record")
    if any(kind == "bare id" for _, kind, _ in flags):
        fixed, bare = linked_card(card)
        out += ["card, with its ids linked in place (ask this one):", json.dumps(fixed, ensure_ascii=False, indent=1)]
        if bare:
            out.append(f"still bare, no file or work item found for: {', '.join(bare)}"
                       + ("" if all(kit_config.ado()) or not any(b.startswith("#") for b in bare)
                          else " (ado.org and ado.project are not set, so no work item links)"))
    no_drafts = drafts is settled_drafts and not drafts_file()
    out.append(f"card_check: {len(flags)} flag(s) in {len(card.get('questions', []))} question(s); "
               f"{len(cards)} past card answers read; record lookup {'ran' if found else 'did not run'}"
               + ("; no drafts file configured (figma.drafts or $FIGMA_DRAFTS), so no draft was checked"
                  if no_drafts else ""))
    return out, 1 if flags else (2 if not found and not no_record else 0)


# ---------------------------------------------------------------------------------------- linked card
MDLINK_OR_URL = re.compile(r"\[[^\]\n]*\]\((?:https?://[^)\s]+)\)|https?://[^\s)>\]\"'`]+")
FIGMA_KEY = re.compile(r"figma\.com/(?:design|board|file|proto)/([A-Za-z0-9]{10,})/")


def figma_index():
    """{file key: node ids} from each figma.files file's cached figma_family index, read only (never built)."""
    import figma_comments as fc
    import figma_family
    out = {}
    for key in fc.KNOWN_FILES:
        with open(os.devnull, "w") as quiet:
            ix, _ = figma_family.load(key, mode="cache", log=quiet)
        if ix is not None:
            out[key] = set(ix.idx)
    return out


def link_ids(text, card_keys, index, ado_url, node_link):
    """(text with each bare ADO id and Figma node id linked in place as a markdown link, [ids left bare]). A node
    links into the known file whose index holds it (a card's own file first when several do), else into the one
    file the card's Figma URLs name; else it stays bare. What counts as bare is bare_ids' rule."""
    bare = []

    def ado(m):
        u = ado_url(m.group(0)[1:])
        if not u:
            bare.append(m.group(0))
        return f"[{m.group(0)}]({u})" if u else m.group(0)

    def fig(m):
        n = m.group(0)
        holds = [k for k, ids in index.items() if n in ids]
        key = next((k for k in card_keys if k in holds), None) or (holds[0] if len(holds) == 1 else None) \
            or (card_keys[0] if not holds and len(card_keys) == 1 else None)
        if not key:
            bare.append(n)
        return f"[{n}]({node_link(key, n)})" if key else n

    out, at = [], 0
    for m in MDLINK_OR_URL.finditer(text):
        out.append(bare_ids.ADO.sub(ado, bare_ids.FIG.sub(fig, text[at:m.start()])) + m.group(0))
        at = m.end()
    out.append(bare_ids.ADO.sub(ado, bare_ids.FIG.sub(fig, text[at:])))
    return "".join(out), bare


def linked_card(card, index=None, ado_url=None, node_link=None):
    """(the card with every bare id in its questions and options linked in place, [ids left bare])."""
    import figma_comments as fc
    index = figma_index() if index is None else index
    ado_url = ado_url or kit_config.ado_url
    node_link = node_link or fc.node_link
    qs = card.get("questions", [])
    texts = [q.get("question") or "" for q in qs] + [o.get(x) or "" for q in qs for o in q.get("options", [])
                                                      for x in ("label", "description")]
    keys = list(dict.fromkeys(m.group(1) for t in texts for m in FIGMA_KEY.finditer(t)))
    out, bare = json.loads(json.dumps(card)), []
    for q in out.get("questions", []):
        for d, k in [(q, "question")] + [(o, x) for o in q.get("options", []) for x in ("label", "description")]:
            if d.get(k):
                d[k], b = link_ids(d[k], keys, index, ado_url, node_link)
                bare += b
    return out, list(dict.fromkeys(bare))


# ---------------------------------------------------------------------------------------- share
def share_key(text):
    """A question as log_run keeps it (its first 80 characters), with case and spacing folded, so a run and the
    card it checked match."""
    return " ".join(str(text or "")[:80].split()).casefold()


# A run checks a card asked up to this long after it: a run the day before a card is a check of another draft.
SHARE_HOURS = 12


def share(days=7, runs=None, projects=bare_ids.PROJECTS):
    """[(day, cards checked first, cards asked, runs that matched no card)] for each UTC day: a card (one
    AskUserQuestion call, counted once though a log is copied) is checked when a run whose questions hold its first
    question ran up to SHARE_HOURS before it. Counting runs against cards instead would count reruns of one card,
    and checks of cards never asked, as checks."""
    runs = runs or runs_path()
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    stamp = lambda ts: dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))  # noqa: E731
    done = []
    if os.path.exists(runs):
        with open(runs, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r["ts"] >= (since - dt.timedelta(hours=SHARE_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ"):
                    done.append((stamp(r["ts"]), {share_key(q) for q in r.get("questions") or []}))
    cards = {}
    for p in glob.glob(os.path.join(projects, "*", "*.jsonl")):
        if os.path.getmtime(p) < since.timestamp():
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"AskUserQuestion"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = rec.get("timestamp", "")
                if ts < since.isoformat()[:19]:
                    continue
                for b in (rec.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                        qs = (b.get("input") or {}).get("questions") or [{}]
                        cards.setdefault(b.get("id") or f"{p}:{ts}", (ts, share_key(qs[0].get("question"))))
    days_seen, used = {}, set()
    for ts, key in sorted(cards.values()):
        at = stamp(ts)
        hit = [i for i, (t, qs) in enumerate(done) if key in qs and at - dt.timedelta(hours=SHARE_HOURS) <= t <= at]
        row = days_seen.setdefault(ts[:10], [0, 0, 0])
        row[0] += bool(hit)
        row[1] += 1
        used.update(hit)
    for i, (t, _) in enumerate(done):
        if i not in used and t >= since:
            days_seen.setdefault(t.strftime("%Y-%m-%d"), [0, 0, 0])[2] += 1
    return [(d, *days_seen[d]) for d in sorted(days_seen)]


# ---------------------------------------------------------------------------------------- selftest
def selftest():
    """Planted cards, drafts, logs and lookups only: no real ledger, log, drafts file or network is read."""
    cards = [{"source": "card", "question": "Archive the nine finished sessions the archive check passed today?",
              "text": "Archive them", "ts": "2026-10-29T01:00:00Z", "session": "aaaaaaaa-0000"},
             {"source": "card", "question": "Which footer goes on the help pages?",
              "text": "Move the footer links into the help menu bar", "ts": "2026-10-28T01:00:00Z",
              "session": "bbbbbbbb-0000"}]
    ok = {"questions": [{"question": "Which header should the demo screens share?", "header": "Header",
                         "options": [{"label": "A", "description": "reviews/drafts.md:59"},
                                     {"label": "B", "description": "https://www.figma.com/design/k/W?node-id=1-2"}]}]}
    q0 = ok["questions"][0]
    cases = [
        ("clean card", ok, set()),
        ("bare Figma id", {"questions": [{**q0, "question": "Fix node 1100:2000 now?"}]}, {"bare id"}),
        ("bare ADO id", {"questions": [{**q0, "question": "Close #4242 today?"}]}, {"bare id"}),
        ("tilde path", {"questions": [{**q0, "question": "Read ~/notes/x.md first?"}]}, {"path"}),
        ("dotdot path", {"questions": [{**q0, "question": "Open ../reviews/a.md?"}]}, {"path"}),
        ("one option", {"questions": [{**q0, "options": q0["options"][:1]}]}, {"shape"}),
        ("long header", {"questions": [{**q0, "header": "A very long header"}]}, {"shape"}),
        ("already answered", {"questions": [{**q0,
                              "question": "Archive the nine finished sessions the archive check passed?"}]}, {"answered?"}),
        ("a past answer holding the words, under another question, is no match",
         {"questions": [{**q0, "question": "Move the footer links into the help menu bar?"}]}, set()),
        ("unmeasured cost", {"questions": [{**q0, "options": [
                             {"label": "Build it", "description": "About 3 days of work, believed, not measured."},
                             q0["options"][1]]}]}, {"estimate"}),
        ("linked id passes", {"questions": [{**q0, "question":
                              "Close [4242](https://dev.azure.com/o/p/_workitems/edit/4242/) today?"}]}, set()),
    ]
    bad = 0
    for name, card, want in cases:
        got = {f[1] for f in check(card, cards)}
        good = got == want
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  {name}: want {sorted(want)}, got {sorted(got)}")
    # The settled-draft flag: a card offering to post drafts the record settles, and a card about something else,
    # against a planted drafts check that fails two drafts.
    planted = lambda: [("drafts.md", 76, "override", "the post command carries --new-thread"),  # noqa: E731
                       ("drafts.md", 80, "own-open", "it links your own open comment 1000000002")]
    post4 = {"questions": [{**q0, "question": "Four Figma comments are drafted and not sent, listed "
                            "in reviews/drafts.md. Post them?"}]}
    other = {"questions": [{**q0, "options": [
        {"label": "A", "description": "https://www.figma.com/design/k/W?node-id=1-2"},
        {"label": "B", "description": "Keep the header as built."}]}]}
    extra = 0       # the settled-draft cases, which the total below counts one by one
    for name, card, want in (("known-bad: a card offering to post settled drafts", post4, 2),
                             ("known-good: a card not about drafts flags no draft", other, 0)):
        got = [f for f in check(card, cards, drafts=planted) if f[1] == "settled draft"]
        good = len(got) == want
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  {name}: want {want} settled-draft flags, got {len(got)}")
    # drafts_store's own rules reach the flag through settled_drafts: own-open and a check that did not run are kept,
    # a moot heading is not; and no drafts file configured reads nothing and raises nothing.
    import drafts_store
    saved = drafts_store.structure, drafts_store.drafts_path
    try:
        drafts_store.drafts_path = lambda: __file__      # any readable file: structure is planted
        drafts_store.structure = lambda text, name: [
            ("drafts.md", 56, "own-open", "it links your own open comment 1000000001"),
            ("drafts.md", 60, "moot", "the heading says moot")]
        got = [f for f in check(post4, cards, drafts=settled_drafts) if f[1] == "settled draft"]
        good = len(got) == 1 and "1000000001" in got[0][2]
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  known-bad: a draft linking the user's own open comment flags a card "
              f"offering to post drafts, and a moot heading does not: want 1, got {len(got)}")
        drafts_store.structure = lambda text, name: [
            ("drafts.md", 64, drafts_store.OWN_NOT_RUN, "the own-open check did not run (HTTPError: 429)")]
        got = [f for f in check(post4, cards, drafts=settled_drafts) if f[1] == "settled draft"]
        good = len(got) == 1 and "did not run" in got[0][2]
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  known-bad: an own-open check that could not run is flagged, never "
              f"passed: want 1, got {len(got)}")
        drafts_store.drafts_path = lambda: None
        got = settled_drafts()
        good = got == []
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  no drafts file configured: nothing to read, nothing raised: got {got}")
    finally:
        drafts_store.structure, drafts_store.drafts_path = saved
    # A question naming a failing draft's subject, with no word about comments or drafts.
    hero_row = lambda: [("drafts.md", 56, "own-open", "it links your own open comment 1000000001",  # noqa: E731
                         draft_title("Pricing banner photo: a larger original or a wider crop — NEW on "
                                     "\"Background image\" [`1100:2000`](https://www.figma.com/design/FILEKEY123/W) "
                                     "· Not sent."))]
    ask = lambda text: {"questions": [{**q0, "question": text, "options": [  # noqa: E731
        {"label": "Post it", "description": "Post it now."}, {"label": "Hold it", "description": "Leave it unsent."}]}]}
    for name, text, want in (
            ("known-bad: 'Post the Pricing banner photo ask to Figma?' names the failing draft by its subject, "
             "though DRAFTISH reads nothing in it", "Post the Pricing banner photo ask to Figma?", 1),
            ("known-good: 'Send the vendor the access ask?' shares no draft's subject",
             "Send the vendor the access ask?", 0)):
        got = [f for f in check(ask(text), cards, drafts=hero_row) if f[1] == "settled draft"]
        good = len(got) == want and not DRAFTISH.search(text)
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  {name}: want {want}, got {len(got)}")
    with tempfile.TemporaryDirectory() as tmp:
        runs = os.path.join(tmp, "runs.jsonl")
        t0 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        at = lambda m: (t0 + dt.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
        footer = {"questions": [{**q0, "question": "Which footer should the demo screens use?"}]}
        never = {"questions": [{**q0, "question": "Which logo goes on the gateway?"}]}
        with open(runs, "w", encoding="utf-8") as f:
            for m, c in ((0, ok), (1, ok), (2, never)):     # a card checked twice, and a check of a card never asked
                f.write(json.dumps({"ts": at(m)[:19] + "Z", "questions": [q["question"][:80] for q in c["questions"]],
                                    "flags": 0}) + "\n")
        for folder in ("-a", "-b"):                         # one log in two copies: each card counts once
            os.makedirs(os.path.join(tmp, folder), exist_ok=True)
            with open(os.path.join(tmp, folder, "s.jsonl"), "w", encoding="utf-8") as f:
                for m, cid, c in ((5, "toolu_ok", ok), (6, "toolu_footer", footer)):
                    f.write(json.dumps({"timestamp": at(m), "message": {"content": [
                        {"type": "tool_use", "id": cid, "name": "AskUserQuestion", "input": c}]}}) + "\n")
        rows = share(7, runs, tmp)
        tot = [sum(r[i] for r in rows) for i in (1, 2, 3)]
        good = tot == [1, 2, 1]
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  --share matches each run to the card it checked by question text: a card "
              f"checked twice is 1 checked, a card in two log copies is 1 asked, a card no run checked is asked and not "
              f"checked, and a run for a card never asked is counted apart: want [1, 2, 1], got {tot}")
    rec = selftest_record()
    bad += rec[0]
    total = len(cases) + extra + 1 + rec[1]
    print(f"{total - bad} of {total} cases pass")
    return 1 if bad else 0


def selftest_record():
    """The record lookup on planted results: its terms, the asking session's own log cut at the user's last
    message, what prints, the reader seam, the deadline, the run log, the linked card, and checked()'s output and
    exit for a lookup skipped, timed out or run. -> (failures, checks)."""
    res = []
    q = {"question": "Which name does the app build, at 21:34 per commit c0ffee12?", "header": "Name",
         "options": [{"label": "Atlas (Recommended)", "description": "the newer Figma copy"},
                     {"label": "Project Atlas", "description": "the older copy"}]}
    t = lookup_terms(q)
    res.append(("the terms come from the question and its options, a hash whole, a time not an id",
                "c0ffee1" in t and "Project Atlas" in t and not any("21:34" in x for x in t)))
    t2 = lookup_terms({"question": "Who owns the top agent?", "options": [
        {"label": "Matches Delta", "description": "The newer diagram"}, {"label": "Bo", "description": "The older one"}]})
    res.append(("an option's label and description are read apart, so no name runs across them",
                "Matches Delta" in t2 and not any(x.endswith(" The") for x in t2)))
    own, since = "aaaaaaaa-0000-0000-0000-000000000000", "2026-10-31T06:00:00.000Z"

    def hit(key, ts, s, role="assistant"):
        return {"key": key, "ts": ts, "role": role, "strength": s, "excerpt": f"{key[:8]} said Project Atlas"}
    planted = {"logs": {"ran": True, "partial": [], "hits": [
                   hit(own, "2026-10-31T06:10:00.000Z", 9),                       # the asking session, after the message
                   hit(own, "2026-10-30T01:00:00.000Z", 2),                       # the asking session, before it
                   hit("bbbbbbbb-0000-0000-0000-000000000000", "2026-10-06T01:00:00.000Z", 5)]},
               "ado": {"ran": True, "partial": [], "hits": [
                   {"head": "#4242 Closed Bug: Project Atlas copy update", "excerpt": "Rename as Project Atlas",
                    "strength": 8, "ts": "2026-10-17T00:00:00Z"}]},
               "git": {"ran": True, "partial": [], "hits": [
                   {"head": "c0ffee1 rename to Project Atlas", "excerpt": "Project Atlas", "strength": 3,
                    "ts": "2026-10-06T00:00:00Z"}]}}

    def searcher(asks, opts):
        return [{"q": a, "src": json.loads(json.dumps(planted))} for a in asks]
    found = record_lookup({"questions": [q]}, own, since, searcher=searcher)
    top = found[0]["top"]
    logs = [e for e in top if e["src"] == "logs"]
    res.append(("the asking session's log after the user's last message there is dropped; before it, it stays",
                all(h["ts"] < since for e in logs for h in e["hits"] if e["sid"].startswith(own[:8]))
                and any(e["sid"].startswith(own[:8]) for e in logs)))
    res.append(("the top is what the full search prints first: the log sessions, then ADO's #4242, then git",
                [e["src"] for e in top] == ["logs", "logs", "ado", "git"] and "#4242" in top[2]["hit"]["head"]))
    lines = record_lines(found)
    res.append(("what is shown prints under the question, one line each, after its terms line",
                len([ln for n, ln in lines if ln.startswith("  ")]) == len(found[0]["shown"]) == 3
                and "Project Atlas" in lines[0][1]))
    reader = lambda qq, tt: [("record", f"the record picks Project Atlas: {tt[0]['src']}")] if tt else []  # noqa: E731
    card = {"questions": [q]}
    flagged = [f for f in check(card, [], found=found, reader=reader) if f[1] == "record"]
    quiet = [f for f in check(card, [], found=found) if f[1] == "record"]
    res.append(("the reader seam: a reader's flag lands on its question; with no reader, none", len(flagged) == 1 and not quiet))
    got, why = run_record(card, seconds=0.01)
    res.append(("a lookup past its deadline did not run, never a pass", got is None and why.startswith("over")))

    # What prints: recall's first round. ADO's strongest (#4242) prints though a newer, weaker item comes first in
    # recall's order; the log place is recall's first (the asking session, before the message), at its own strength;
    # memory's stronger hit doesn't print; Figma, stopped by a 429, is named and the rest print.
    long = "Rename every Atlas to Project Atlas on the gallery cards, the bullet and the footer body. " * 3
    wide = json.loads(json.dumps(planted))
    wide["ado"]["hits"] = [{"head": "#4243 Closed User Story: Project Atlas  https://dev.azure.com/o/p/_workitems/edit/4243/",
                            "excerpt": "Project Atlas flow", "strength": 3, "ts": "2026-10-20T00:00:00Z", "ids": ["ado:4243"]},
                           {"head": "#4242 Closed Bug: Project Atlas copy  https://dev.azure.com/o/p/_workitems/edit/4242/",
                            "excerpt": long, "strength": 8, "ts": "2026-10-17T00:00:00Z", "ids": ["ado:4242"]}]
    wide["notes"] = {"ran": True, "partial": [], "hits": [{"head": "~/notes/arch/systems.md:343  modified 2026-10-31",
                                                           "excerpt": "Project Atlas", "strength": 4,
                                                           "ts": "2026-10-31T00:00:00Z",
                                                           "ids": ["file:~/notes/arch/systems.md"]}]}
    wide["memory"] = {"ran": True, "partial": [], "hits": [{"head": "feedback_atlas.md", "excerpt": "Atlas",
                                                            "strength": 9, "ts": "2026-10-01T00:00:00Z"}]}
    wide["figma"] = {"ran": False, "why": "HTTP 429 past the deadline", "partial": [], "hits": []}
    wide["transcripts"] = {"ran": False, "off": True, "why": "set recall.transcripts", "partial": [], "hits": []}
    for h in wide["logs"]["hits"]:
        h["label"] = f"mac:{h['key'][:8]}.jsonl"
    f2 = record_lookup({"questions": [q]}, own, since,
                       searcher=lambda asks, opts: [{"q": a, "src": json.loads(json.dumps(wide))} for a in asks])[0]
    sh = f2["shown"]
    res.append(("what prints is recall's first round: each source once, ADO's strongest though it isn't ADO's first place",
                [e["src"] for e in sh] == ["ado", "notes", "git", "logs"] and "#4242" in sh[0]["hit"]["head"]
                and sh[3]["sid"].startswith(own[:8])
                and [e["src"] for e in f2["top"][:3]] == ["logs", "logs", "ado"] and "#4243" in f2["top"][2]["hit"]["head"]))
    res.append(("memory is searched, not shown, though its hit is the strongest",
                f2["status"].get("memory") == "ran" and not any(e["src"] == "memory" for e in sh)))
    ln = record_lines([f2])
    res.append(("a source stopped by a 429 is named, and the others still print",
                "figma did not run" in ln[0][1] and len([x for n, x in ln if x.startswith("  ")]) == 4))
    res.append(("a source with nothing configured is named so, never as did not run",
                "transcripts not configured" in ln[0][1] and "transcripts did not run" not in ln[0][1]))
    fj = found_json([f2])["found"][0]
    a = fj["shown"][0]
    res.append(("found keeps each hit's link (a note's as its full path and line), date and full excerpt",
                a["link"] == "https://dev.azure.com/o/p/_workitems/edit/4242/" and a["date"] == "2026-10-17T00:00:00"
                and a["excerpt"] == long and "…" in a["line"] and fj["shown"][3]["link"] == "mac:aaaaaaaa.jsonl"
                and fj["shown"][1]["link"] == os.path.expanduser("~/notes/arch/systems.md:343")))
    env = child_env(150, now=1000)
    res.append(("the lookup child runs Figma in the gate lane with a deadline at half the lookup's time",
                env.get("FIGMA_CLIENT_LANE") == "gate" and env.get("FIGMA_CLIENT_DEADLINE_AT") == "1075"))
    with tempfile.TemporaryDirectory() as tmp:
        runs = os.path.join(tmp, "runs.jsonl")
        log_run(card, [], runs, record="ran", found=found_json([f2])["found"])
        with open(runs, encoding="utf-8") as fh:
            row = json.loads(fh.read())
    lg = (row.get("shown") or [{}])[0]
    res.append(("the run log keeps what was shown and recall's first 3 places, a log place with its printed record",
                [x["src"] for x in lg.get("shown", [])] == ["ado", "notes", "git", "logs"]
                and [x["src"] for x in lg.get("first3", [])] == ["logs", "logs", "ado"]
                and lg["shown"][3].get("record", "").startswith("2026-10-30")))

    # The card printed back: each bare id linked in place, so bare_ids reads none; an unknown node stays bare and
    # is named; a node in no index links into the one file a URL on the card names.
    ado_url = lambda n: f"https://dev.azure.com/o/p/_workitems/edit/{n}/"  # noqa: E731
    node_link = lambda k, n: f"https://www.figma.com/design/{k}/F?node-id={n.replace(':', '-')}"  # noqa: E731
    bad_card = {"questions": [{"question": "Close #4242 and fix node 1100:2000 and 9999:11111? See "
                               "[#4243](https://dev.azure.com/o/p/_workitems/edit/4243/).", "header": "Ids",
                               "options": [{"label": "Yes", "description": "node 1100:2000 again"}, {"label": "No"}]}]}
    fixed, left = linked_card(bad_card, {"FILEKEY123": {"1100:2000"}, "BOARDKEY12": {"1:2"}}, ado_url, node_link)
    qtext = fixed["questions"][0]["question"]
    counts = bare_ids.count(qtext.replace("9999:11111", ""))
    res.append(("the card prints back with its ids linked in place, so bare_ids reads none, and an unknown node is named",
                counts[0] == 0 and counts[1] == 0 and "[#4242](https://dev.azure.com/o/p/_workitems/edit/4242/)" in qtext
                and "design/FILEKEY123/" in qtext and left == ["9999:11111"]
                and "[1100:2000](" in fixed["questions"][0]["options"][0]["description"]
                and qtext.count("_workitems/edit/4243/") == 1))
    on_url = {"questions": [{"question": "Fix 7777:88 in https://www.figma.com/board/BOARDKEY12/B?node-id=1-2 ?",
                             "options": [{"label": "A"}, {"label": "B"}]}]}
    fixed2, left2 = linked_card(on_url, {"FILEKEY123": {"1100:2000"}}, ado_url, node_link)
    res.append(("a node no index holds links into the one file a Figma URL on the card names",
                "[7777:88](https://www.figma.com/design/BOARDKEY12/" in fixed2["questions"][0]["question"] and not left2))

    # checked(): what main prints and its exit, for a lookup skipped, timed out or run, on a clean card.
    clean = {"questions": [{"question": "Which footer should the demo screens use?", "header": "Footer",
                            "options": [{"label": "A", "description": "as built"},
                                        {"label": "B", "description": "the design's"}]}]}
    with tempfile.TemporaryDirectory() as tmp:
        runs = os.path.join(tmp, "runs.jsonl")

        def last_row():
            with open(runs, encoding="utf-8") as fh:
                return json.loads(fh.read().splitlines()[-1])
        out, code = checked(clean, [], [], None, no_record=True, runs=runs, drafts=None)
        row = last_row()
        res.append(("--no-record says so and exits 0 on a clean card, and its run is logged as did not run",
                    code == 0 and any("lookup did not run: --no-record" in x for x in out)
                    and row.get("record") == "did not run: --no-record"))
        out, code = checked(clean, [], [], None, runs=runs, drafts=None,
                            runner=lambda c, o, s, **_: (None, "over 150 s"))
        row = last_row()
        res.append(("a lookup that timed out prints the did-not-run line, is logged, and exits 2",
                    code == 2 and any("lookup did not run: over 150 s" in x for x in out)
                    and row.get("record") == "did not run: over 150 s"))
        ran = {"found": [{"terms": ["#4242"], "status": {}, "top": [], "shown": []}],
               "lines": [[1, "record   #4242: the first log place"], [1, "   1. logs  abcdefgh  a lead"]]}
        out, code = checked(clean, [], [], None, runs=runs, drafts=None, runner=lambda c, o, s, **_: (ran, None))
        order = [x.split()[1] for x in out if x.startswith("Q1  ")]
        res.append(("a lookup that ran prints that question's leads under it, and exits 0",
                    order[:2] == ["record", "1."] and code == 0 and last_row().get("record") == "ran"))
        seen = {}
        said = [{"source": "typed", "session": "s1", "ts": "2026-10-31T06:00:00.000Z"},
                {"source": "typed", "session": "s2", "ts": "2026-10-31T07:00:00.000Z"}]
        checked(clean, [], said, "s1", runs=runs, drafts=None,
                runner=lambda c, o, s, **_: (seen.update(own=o, since=s), (ran, None))[1])
        res.append(("the asking session's own log is cut at the user's last message there, from the ledger",
                    seen == {"own": "s1", "since": "2026-10-31T06:00:00.000Z"}))
    bad = 0
    for name, good in res:
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  record: {name}")
    return bad, len(res)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--share", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--session", help="the Claude Code session asking, as the request ledger names it "
                                      "(default $CLAUDE_CODE_SESSION_ID)")
    ap.add_argument("--no-record", action="store_true", help="skip the record lookup (it says so)")
    ap.add_argument("--record-child", nargs=2, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.record_child:
        return record_child(*a.record_child)
    if a.selftest:
        return kit_config.run_isolated(selftest)
    if a.share:
        for d, c, k, u in share(a.days):
            print(f"{d}  {c} of {k} cards asked were checked first" + (f"; {u} run(s) matched no card asked" if u else ""))
        return 0
    if not a.card:
        ap.error("give a card file, - for stdin, --share or --selftest")
    path = ledger_path()
    try:
        if a.card == "-":
            card = json.load(sys.stdin)
        else:
            with open(a.card, encoding="utf-8") as f:
                card = json.load(f)
        if not isinstance(card, dict) or not isinstance(card.get("questions"), list):
            raise ValueError('the card is not {"questions": [...]}, the AskUserQuestion input')
        if not os.path.isfile(path):
            raise FileNotFoundError(f"no request ledger at {path}: python tools/ledger.py writes it (ledger.dir "
                                    f"says where)")
        rows = pushback_score.load(path)
    except (OSError, ValueError) as e:
        print(f"did not run: {type(e).__name__}: {e}")
        return 2
    sid = a.session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    out, code = checked(card, past_cards(rows), rows, sid, a.no_record)
    print("\n".join(out))
    return code


if __name__ == "__main__":
    sys.exit(kit_config.run(main))
