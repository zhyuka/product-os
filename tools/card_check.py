#!/usr/bin/env python3
"""card_check.py - check a question card before the user sees it: bare ids, paths they can't open, the
card's shape, questions the record may already answer, and questions about work that is ours to do.

    python tools/card_check.py <card.json>              the AskUserQuestion input ({"questions": [...]}), or - for stdin
    python tools/card_check.py <card.json> --session ID the Claude Code session asking (default $CLAUDE_CODE_SESSION_ID)
    python tools/card_check.py <card.json> --before T   the record as it stood before T (UTC, as recall reads it): a
                                                        replay of a card already asked, whose own answer is in the
                                                        ledger by now
    python tools/card_check.py <card.json> --leads      also recall's leads under each question (LEADS below): about
                                                        100 s a card, against about 1 s without, and they flag nothing
    python tools/card_check.py --selftest               planted cards: each flag fires on its bad case, none on a clean one
    python tools/card_check.py --share [--days 7]       per day, the cards asked that a run checked first, by question text
    --no-record is still accepted, as a no-op, and says so: the topic lookup always runs, the leads only with --leads.

WHY. Much of what goes wrong between a session and the user is in what the session asks or tells them:
a question the record already answers, a step that is ours to just do, a bare node or work-item id they
have to look up, a path they can't open. Claude Code can't refuse a question card, so a session runs this
on each card before it asks, and --share reports how often that happened.

FLAGS, each with the question it sits in:
  may answer     RECORD MAY ANSWER: <citation>. A ruling row, the user's own typed words or the doc of a
                 system the question names speaks to the question (TOPIC below): open the citation and act on
                 it before asking. Not raised when a passage that speaks to it leaves the call to the user
                 ("is the user's choice"); that passage prints as a `yours` line instead
  ours to do     OURS TO DO: the question asks whether to ask someone whether we may do work that is ours
                 ("ask X whether we may build Y"), or it asks to send a drafted message (an option's preview, or
                 a quoted message) that asks that ("could we show you ...", "would you like us to ..."): build it
                 and have it ready; ask only if the record names someone whose go it needs
  bare id        a Figma node id or #ADO id outside a URL (bare_ids.count, the daily count's own rule). The
                 card prints back with each one linked in place: an ADO id to its work item (ado.org and
                 ado.project), a Figma node into the file in figma.files whose cached index (figma_family)
                 holds it, else into the one file a Figma URL on the card names; one with neither stays bare
                 and is named
  path           a ~/ path or a ../ path; give the path from the session's start folder, or an absolute one
  shape          not 2-4 options, or a header over 12 characters
  estimate       a cost the card calls believed, a guess, a ballpark or not measured: measure it first
  your work?     the question asks the user to do a task ("will you label / review / recall / open ...") or
                 its recommended option has them do it ("I'll review them"), and neither says why only they
                 can (only you, no session can, a managed prompt, before you send): do it or research it instead
  answered?      a past card in the request ledger whose question shares at least 60% of this question's
                 content words (a lead: open it before asking)
  your words?    an answer the user typed on a card in the last 24 hours (6 or more content words, so not a
                 pick) shares 3 or more of this question's content words: what they just said may settle it,
                 so read it before asking. A row answered? already shows isn't shown again
  settled draft  drafts_store's ask, override or own-open rule fails a draft in the drafts file (figma.drafts
                 or $FIGMA_DRAFTS), and the question names drafts.md or posting Figma comments (every failing
                 draft is flagged), or shares 3 or more content words with that draft's subject, its heading
                 before the ' — ' (only that draft): it asks design what the record already settles, it is
                 written to open a new thread instead of folding into an open one, or it links the user's own
                 open comment, which the fix goes into instead. An ask or own-open check that could not run is
                 flagged too, never passed. The drafts check runs on every card; with no drafts file
                 configured it has nothing to read, and the summary says so
Not here: a flag for a recommended option that is setup work (settings, hooks, gates, a delete) with no
challenger run first; it needs a session coordinator that maps sessions to logs and lists setup paths.

TOPIC. Each question is looked up by its topic, in this process, on every run. Its header and text are
weighed word by word (light stemming: captions = caption, minimized = minimizes): a word weighs its rarity
across the request ledger's rows, half again in the header. Three kinds of record are read, each split
into passages (a table row, a bullet, a paragraph, a JSON entry) and each passage into windows of up to
TOPIC_WINDOW sentences, and a window scores the share of the question's weight its words hold (times
sqrt(TOPIC_LEN / its length) when longer):
  your words   what the user typed (the ledger's typed, mid-turn and card rows; a card's pick of an option
               is not typed words), with pasted blocks and quoted lines taken out
  ruling       a table row keyed by an id such as J4, or a bullet led by a bold title, in a file whose name
               says rulings or decisions at the top of a notes folder (recall.notes) or among workspace.docs;
               the entries of ledger.rulings and ledger.rulings_also (JSON); and each knowledge entry (kb). A
               row another row of its file supersedes ("Supersedes J1") is left out
  doc          the README of each folder the workspace map (workspace.root, workspace.map) names, and each
               knowledge body's page and canonical files (kb index.md), for the TOPIC_SYSTEMS systems whose
               names the question shares most; a file named for drafts is never a doc
A passage speaks to the question at TOPIC_BAR or more with TOPIC_SHARED or more shared words (typed words:
WORDS_BAR, WORDS_SHARED). A question whose step leaves the machine (send, post, add to someone's board,
everyone sees a banner: OUTWARD, in the question or its first option) needs a ruling row at OUTWARD_BAR or
typed words: what a system's doc says doesn't decide an outward step. The best passage of each kind prints
under the question with its score, link and excerpt, flagged or not: the leads to read before asking.

LEADS (--leads only). Each question also runs through recall's --brief search, in a child with a deadline
(RECORD_SECONDS): one concept, OR'd: its ids, quoted and capitalised names, its header as one phrase, then
the words its best TOPIC passages share with it, heaviest first (with none, its rarest words). Earlier work
comes from BRIEF_SOURCES: notes (not the ledger, which TOPIC reads, and not .cache folders), git, ADO as
cached and transcripts; the live sessions (recall --brief's: a main log written in the last 48 h, this
session, headless runs, sealed and archived ones left out) that hold 2 or more of its terms in their title,
prompts, plan, recap or files print too, at most RECORD_LIVE, the asking session's never. What prints is
recall's own first round of its ranked list (`shown`): the strongest hit of each source, ties newest first,
sources in order of their strongest, then the live sessions. Each source's status prints beside it: ran,
partial, not configured or did not run. recall's first 10 places go to `check(..., reader=)`, which has no
reader yet, so the leads flag nothing; that is why they are opt-in: a run without them takes about 1 s
instead of about 100 s, and a slow check is one sessions skip. Without --leads one line says they weren't
asked for. With it, a lookup over RECORD_SECONDS, or one that fails, prints "recall leads did not run" and
exits 2 when nothing else flagged; the topic lookup still runs and flags.
Other tools call run_record() and record_lookup() directly; their default is recall's full search on 4 rare
terms (RECORD_SOURCES: logs, ADO, transcripts, git, notes, memory and Figma), as before the topic lookup.
--leads passes sources=BRIEF_SOURCES and brief=True (the notes filter and the live sessions).

RUNS. Every run appends one line to `card_check.runs` in the product-os config (default
~/.local/share/product-os/card-checks.jsonl): time, the questions, the flag count, whether the leads ran,
didn't or weren't asked for, per question what was shown (source, id, link, the record printed for a log
place) beside recall's first 3 places, and the topic lookup's flag and best citation of each kind, so a
later replay can score them. --share reads it, leaving out replays (a run with --before carries its cut,
and checks nothing).

BEFORE. --before T reads the record as it stood then: the ledger's rows before T (for answered?, your
words? and the topic lookup's typed words and weights), and with --leads recall's search and live
sessions as of T. Files (docs, ruling rows, notes) have no history, so they are read as they are now, as
recall reads notes: a doc or ruling row written after the card was asked can make a replay flag what
the record at ask time could not have.

SESSION. The asking session is --session (a Claude Code session id, as the request ledger keeps it),
else $CLAUDE_CODE_SESSION_ID. When one session checks a card another drafted, name the other.

EXIT. 0 clean, 1 with flags, 2 when the card or the request ledger couldn't be read (ledger.py writes
the ledger, under ledger.dir), or, with nothing else flagged, a topic source did not run or the leads
asked for with --leads did not run. Leads not asked for are no reason for 2.

BLIND. Word overlap is a lead, not a match: a reworded question that was answered slips past, and a
new question on an old subject can flag. may answer reads words, not meaning: a passage on the same
subject that settles nothing can flag, and one that settles it in other words can't; an answer that
lives only in a session log, a Figma thread, ADO's state or the built site isn't among its three kinds,
and session logs aren't searched (the user's own words come from the ledger instead; --leads adds only
the live sessions, and flags nothing). A system the question doesn't name, by a word of the folder's or
body's name, isn't read. OUTWARD and ours to do read only their phrasings: an outward step put another
way is held to the lower bar, and a drafted ask the card neither previews nor quotes isn't read. With
--leads, what prints is one hit per source, the strongest by recall's match strength, which need not be
the one that settles the question. It doesn't judge whether a question is a craft call.
Its known-bad cases were mostly settled in the record after they were asked. Against the record as it
stood at ask time, the topic lookup catches the test-call question, just over its bar, with the paragraph
that had proposed the call as the next lead; it catches neither question about the builds for a set
date, whose ruling row was written after both (the row in force then said the plan was proposed, not
agreed). ours to do, written from that incident, catches the send. So of the 3 questions the record now
settles, the record as it stood catches 1 and ours to do 1 more.
An id in a form bare_ids doesn't count (an ADO id without #, a node id in its dashed form) passes as
linked. your work? reads only the phrasings TASKS lists, in the question and its first option; a task
put another way passes. Words inside a link don't count toward any overlap.
Not here either: pinning a named knowledge page above a question; it needs a knowledge index whose names
recall can match.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse
import collections
import datetime as dt
import glob
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path: sys.path.append(HERE)
import bare_ids  # noqa: E402
import kit_config  # noqa: E402
import pushback_score  # noqa: E402

PATH = re.compile(r"(?<![\w/])(~/|\.\./)[^\s)`'\"]+")
GUESS = re.compile(r"\b(believed|not measured|unmeasured|my guess|a guess|ballpark)\b", re.I)
# A task put to the user instead of a decision: "will you label...", "can you recall...", or a recommended option
# that has them do it ("I'll review them"). Known bad: a hand-labelling ask the user answered by saying no person
# was needed, and an ask to recall an old call, which the record can answer.
TASKS = (r"(?:hand-?)?label|review|check|test|measure|compare|rate|score|grade|tag|annotate|classify|sort"
         r"|read|recall|remember|find|look(?:\s+(?:up|at|through))?|open|inspect|verify|go\s+through|watch")
YOU_DO = re.compile(r"\b(?:will|can|could|would)\s+you\s+(?:please\s+)?(?:(?:also|first|just|then)\s+)?"
                    r"(?:" + TASKS + r")\b", re.I)
I_DO = re.compile(r"^\s*I'?ll\s+(?:(?:also|first|just|then)\s+)?(?:" + TASKS + r")\b", re.I)
# Why only the user can: said in the question or its recommended option, it lets the task through.
ONLY_YOU = re.compile(r"\bonly (?:you|the user|a person|a human|he|she|they)\b"
                      r"|\bno (?:session|tool|agent) (?:can|may)\b|\bmanaged (?:policy|prompts?)\b|\bbefore you send\b",
                      re.I)
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
    """Content words, links left out: a URL's host and path words (example, com, https) say nothing about what a
    question asks, and they were the whole overlap behind two false 'your words?' leads."""
    return {w for w in WORD.findall(URL.sub(" ", text or "").lower()) if w not in STOP}


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


def named_terms(text, strip=True):
    """A text's ids (a hash as its first 7), quoted names and capitalised names, in that order. strip: a name's
    leading stopword is no part of it ("In Teams" is Teams); terms() keeps it, as it always has."""
    text = re.sub(r"(?<=[A-Za-z])['’]s\b", "", text or "")
    ids = []
    for m in TERM_IDS.finditer(text):
        a, b = m.group(1), m.group(2)
        if a is not None and len(a) <= 2 and len(b) <= 2:
            continue
        t = m.group(0)
        ids.append(t[:7] if re.fullmatch(r"[0-9a-f]{8,40}", t) else t)
    names = []
    for nm in NAMES.findall(text):
        ws = nm.split()
        while strip and len(ws) > 1 and ws[0].lower() in TERM_STOP | TOPIC_STOP:
            ws = ws[1:]       # a capitalised sentence start is no part of the name: "In Teams" is Teams
        names.append(" ".join(ws))
    return ids + [a or b for a, b in TERM_QUOTED.findall(text)] + names


def terms(text, k=4, vocab=None):
    """The k terms of a text a lookup searches for: ids and quoted names first, then capitalised names, then
    the rarest words in vocab (vocabulary()). The words are read with the ids and quotes taken out, so a hash
    or a node id isn't read as a word too."""
    vocab = vocab or {}
    text = re.sub(r"(?<=[A-Za-z])['’]s\b", "", text or "")
    rest = TERM_QUOTED.sub(" ", TERM_IDS.sub(" ", text))
    found = {w.lower() for w in TERM_WORD.findall(rest)} - TERM_STOP
    rare = sorted(found, key=lambda w: (vocab.get(w, 0) == 0, vocab.get(w, 0), w))
    out = []
    for t in named_terms(text, strip=False) + rare:
        t = t.strip()
        if t and t.lower() not in {o.lower() for o in out} and t.lower() not in TERM_STOP:
            out.append(t)
        if len(out) >= k:
            break
    return out


# ------------------------------------------------------------------------------------- record lookup
# Each question, with its options, runs through recall's full search by default (RECORD_SOURCES, 4 rare terms): what
# figma_post's batch --check and question_coverage get. recall's first round of its ranked list prints beside it
# (`shown`), its first 3 places are logged beside that, and its first 10 go to `reader`. Figma comes from recall's
# own fetch, in figma_client's gate lane with a deadline (child_env), so a 429 costs Figma alone. card_check's own
# --leads runs it brief instead: BRIEF_SOURCES (earlier work: notes, git, ADO as cached, transcripts), the notes as
# --brief keeps them, the topic's terms, and the live sessions on it. On a card, the full search on 4 rare words
# printed unrelated hits (a port-default commit, a scroll bug, an old standup) and took 70-190 s.
RECORD_SOURCES = ("logs", "ado", "transcripts", "git", "notes", "memory", "figma")
BRIEF_SOURCES = ("notes", "git", "ado", "transcripts")
SHOWN_SOURCES = ("logs", "ado", "notes", "transcripts", "git", "figma")
# 300 s: a 4-question card's lookup took 158 s, past the old 150, and printed 'did not run'.
RECORD_TOP, RECORD_SHOW, RECORD_SECONDS = 10, 3, 300
RECORD_TERMS, RECORD_LIVE, LIVE_SHARED, DETAIL_ROWS = 6, 2, 2, 3
URL = re.compile(r"https?://[^\s)>\]\"'`]+")


def question_text(q):
    """A question with its options, the words its record lookup reads: the options hold the choice. A label and
    its description go on lines of their own, so a name ending one and a capital starting the next aren't read
    as one name ("Matches Delta" and "The newer copy" are not "Delta The")."""
    opts = [x.strip() for o in q.get("options") or [] if isinstance(o, dict)
            for x in (str(o.get("label") or ""), str(o.get("description") or "")) if x.strip()]
    return "\n".join([str(q.get("question") or "")] + opts)


def lookup_terms(q, vocab=None):
    """The 4 terms the full search looks for, OR'd: terms() on the question and its options."""
    return terms(question_text(q), 4, vocab)


def brief_terms(q, vocab=None):
    """The RECORD_TERMS terms --leads searches for when its topic lookup found too little, OR'd: the ids, quoted names
    and capitalised names in the question and its options (3 at most), then the question's topic, its header and text
    words by weight (the rarest in vocab, a header word half again), each as its stem when that is 5 letters or more,
    so a search for caption finds captions too (recall matches a longer alternative inside a word)."""
    vocab = vocab or {}
    t = []
    for x in named_terms(question_text(q)):
        x = x.strip()
        if len(t) < 3 and x and x.lower() not in TERM_STOP and x.lower() not in {o.lower() for o in t}:
            t.append(x)
    words = {}
    head = set(topic_words(q.get("header") or ""))
    for w in TOPIC_WORD.findall(URL.sub(" ", " ".join([q.get("header") or "", q.get("question") or ""])).lower()):
        w = w.strip("-'’")
        if len(w) < 3 or w in TOPIC_STOP or w in TERM_STOP:
            continue
        s, c = stem(w), vocab.get(w, 0)
        if c < DETAIL_ROWS and s not in head and "/" not in w:
            continue        # a word in fewer than DETAIL_ROWS ledger rows is a detail of this card, not its topic
        key = s if len(s) >= 5 and w.startswith(s) else w
        rank = (c + 1) / (1.5 if s in head else 1.0)        # rarer first; a header word counts half again as rare
        words[key] = min(words.get(key, rank), rank)
    for w in sorted(words, key=lambda x: (words[x], x)):
        if len(t) >= RECORD_TERMS:
            break
        if w.lower() not in {x.lower() for x in t}:
            t.append(w)
    return t


def topic_terms(q, t, vocab=None):
    """The terms recall searches for a question whose topic lookup (t) found passages on it: its ids, quoted and
    capitalised names (3 at most), its header as one phrase, then the words its best passages share with it,
    heaviest first: what the record and the question have in common is its subject. A stem of 5 letters or more is
    searched as the stem (recall finds it inside a longer word); a shorter one as the question's own word. With
    fewer than 2 such words, brief_terms() fills in."""
    out = []

    def add(x):
        if x and len(out) < RECORD_TERMS and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    for x in named_terms(question_text(q)):
        if len(out) < 3 and x.strip().lower() not in TERM_STOP:
            add(x.strip())
    head = [w for w in TOPIC_WORD.findall((q.get("header") or "").lower()) if w not in TOPIC_STOP and len(w) >= 3]
    add(" ".join(head) if len(head) >= 2 else "")
    phrased = {stem(w) for w in head} if len(head) >= 2 else set()
    said = {}
    for w in TOPIC_WORD.findall(URL.sub(" ", q.get("question") or "").lower()):
        w = re.sub(r"['’]s$", "", w.strip("-'’"))
        said.setdefault(stem(w), w)
    shared = []
    for kind in ("ruling", "your words", "doc"):
        for h in (t or {}).get(kind) or []:
            if h["score"] >= TOPIC_PRINT:
                shared += [s for s in h["shared"] if s not in shared and s not in phrased]
    order = (t or {}).get("order") or []
    shared.sort(key=lambda s: order.index(s) if s in order else len(order))
    n = 0
    for s in shared:
        before = len(out)
        add(s if len(s) >= 5 else said.get(s, s))
        n += len(out) > before
    if n < 2:
        for x in brief_terms(q, vocab):
            add(x)
    return out


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


def brief_notes(qr):
    """Leave out of a search's notes what --brief leaves out: the request ledger (the topic lookup reads the user's
    words there) and anything under a .cache folder (a tool's copy of other sources)."""
    import recall
    r = qr["src"].get("notes")
    if not r or not r.get("ran"):
        return qr
    led = os.path.abspath(recall.ledger_path())

    def keep(h):
        p = next((os.path.expanduser(i[5:]) for i in h.get("ids") or () if i.startswith("file:")), "")
        return not p or (os.path.abspath(p) != led and f"{os.sep}.cache{os.sep}" not in p)
    r["hits"] = [h for h in r["hits"] if keep(h)]
    return qr


def live_sessions(ts, before=None, own=None, seals=None):
    """Per question, up to RECORD_LIVE live sessions (recall --brief's _brief_live: a main log written in the last 48 h
    before `before`; this session, headless runs, sealed and archived ones left out) whose title, prompts, plan, recap
    or files hold LIVE_SHARED or more of its terms, most terms first, then the latest; never the asking session
    (own). -> ([[{"title", "id", "last", "now", "holds"}]], status)."""
    import recall
    alts = list(dict.fromkeys(a for t in ts for a in t))
    if not alts:
        return [[] for _ in ts], "ran"
    q = recall.compile_query({"labels": ["|".join(alts)], "before": before})
    ref = q["before"] or recall.utc(dt.datetime.now(dt.timezone.utc))
    if seals is None:
        seals = recall.find_seals(recall.parse(["x"]))["seals"]
    hit, _, _, bad = recall._brief_live(q, ref, q["before"], seals)
    mine = ""
    if own:
        mine = next((v["id"] for k, v in recall._app_sessions().items() if k.startswith(own[:8])), "") or own
    out = []
    for t in ts:
        cq = recall.compile_query({"labels": ["|".join(t)]}) if t else None
        got = []
        for v in hit if cq else []:
            if mine and (v["id"] == mine or v["id"].startswith(own[:8])):
                continue
            texts = ([v["title"]] + [p for _, p in v["prompts"]] + [s for s, _ in v["plan"]]
                     + [v["recap"][1], v["report"][1]] + list(v["files"]))
            holds = recall._which(cq, texts)
            if len(holds) >= LIVE_SHARED:
                now = (next((s for s, st in v["plan"] if st == "in_progress"), "") or recall._stands(v)[1]
                       or (v["prompts"] or [("", "")])[-1][1])
                got.append({"title": v["title"], "id": v["id"], "last": v["last"], "now": _clip(now, 200),
                            "holds": holds})
        got.sort(key=lambda s: (len(s["holds"]), s["last"]), reverse=True)
        out.append(got[:RECORD_LIVE])
    return out, (f"partial: {bad}" if bad else "ran")


def record_lookup(card, own=None, since=None, before=None, searcher=None, ts=None, vocab=None, lives=None,
                  sources=RECORD_SOURCES, brief=False):
    """[{"terms", "top": [entry, ...], "shown": [entry, ...], "status"}] per question: the first RECORD_TOP places
    of recall's search over `sources` (by default its full search), as it prints them (recall.ranked), and what
    card_check prints (`shown`). own: the asking session's id; its log counts only before `since`, the user's last
    message there (what they said earlier in the session is record too). ts: each question's terms, else
    lookup_terms(q, vocab) (brief_terms when brief). brief: as --leads runs it, the notes as --brief keeps them
    (brief_notes) and "live", the live sessions on it (live_sessions; lives stands in for it), never the asking
    session."""
    import recall
    recall.CONFIG["figma_canvas"] = "cache"
    opts = recall.parse(["x", "--no-pull"])
    opts.sources = tuple(sources)
    pick = brief_terms if brief else lookup_terms
    ts = ts if ts is not None else [pick(q, vocab) for q in card.get("questions", [])]
    asks = [{"labels": ["|".join(t)], "since": None, "before": before} for t in ts if t]
    res = iter((searcher or recall.search)(asks, opts) if asks else [])
    live, lstat = [None] * len(ts), None
    if brief and lives:
        live, lstat = lives(ts, before)
    elif brief:
        try:
            live, lstat = live_sessions(ts, before, own, (getattr(opts, "sealed", None) or {}).get("seals"))
        except Exception as e:  # noqa: BLE001 -- live sessions that can't be read are named, never passed
            live, lstat = [[] for _ in ts], f"did not run: {type(e).__name__}: {e}"[:160]
    out = []
    for t, lv in zip(ts, live):
        if not t:
            out.append({"terms": [], "top": [], **({"live": []} if brief else {})})
            continue
        qr = next(res)
        if brief:
            qr = brief_notes(qr)
        r = qr["src"].get("logs")
        if own and since and r and r["ran"]:
            r["hits"] = [h for h in r["hits"] if not (recall.skey(h["key"]).startswith(own[:8]) and (h["ts"] or "") >= since)]
        top = [e for e in recall.ranked(qr) if e["place"] and e["place"] <= RECORD_TOP]
        status = {n: source_status(x) for n, x in qr["src"].items()}
        out.append({"terms": t, "top": top, "shown": shown(qr), "status": status}
                   if not brief else {"terms": t, "top": top, "shown": shown(qr), "live": lv,
                                      "status": {**status, "live sessions": lstat}})
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
        what = ("each source's strongest hit, then the live sessions on it" if "live" in f
                else "the first log place and each source's strongest hit")
        out.append((n, f"record   {' | '.join(f['terms'])}: {what}; " + (", ".join(gone) if gone else "every source ran")))
        out += [(n, "  " + top_line(e).replace("\n", "\n    ")) for e in f["shown"]]
        out += [(n, f"  live  {v['title']}  ({v['id'][:14]}; last active {v['last'][5:16].replace('T', ' ')}Z; holds "
                    f"{', '.join(v['holds'])}): {v['now']}") for v in f.get("live") or []]
    return out


def child_env(seconds, now=None):
    """The lookup child's environment: figma_client's gate lane and a deadline at half the lookup's time, so a
    Figma rate limit ends Figma's fetch (recall prints it as did not run) before the lookup's own deadline."""
    return dict(os.environ, FIGMA_CLIENT_LANE="gate",
                FIGMA_CLIENT_DEADLINE_AT=f"{(now or time.time()) + seconds / 2:.0f}")


def run_record(card, own=None, since=None, seconds=RECORD_SECONDS, vocab=None, before=None, ts=None,
               sources=RECORD_SOURCES, brief=False):
    """record_lookup in a child process with a deadline: (found, None) or (None, why it did not run). The terms
    are chosen here (ts, else lookup_terms() from the ledger's vocabulary, brief_terms() when brief), so the child
    reads no ledger. before: the record as of then. sources and brief pass through to record_lookup: by default
    recall's full search, as figma_post and question_coverage call it."""
    pick = brief_terms if brief else lookup_terms
    ts = ts if ts is not None else [pick(q, vocab) for q in card.get("questions", [])]
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "card.json"), os.path.join(tmp, "found.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"card": card, "own": own, "since": since, "terms": ts, "before": before,
                       "sources": list(sources), "brief": bool(brief)}, f)
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
    found = record_lookup(a["card"], a.get("own"), a.get("since"), before=a.get("before"), ts=a.get("terms"),
                          sources=a.get("sources") or RECORD_SOURCES, brief=bool(a.get("brief")))
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(found_json(found), f)
    return 0


def found_json(found):
    """record_lookup's result as the child hands it back: per question its terms, status, recall's first
    RECORD_TOP places, what is shown, each hit with its link, date and full excerpt, and, brief, the live
    sessions; and the lines."""
    keep = [{"terms": f["terms"], "status": f.get("status", {}),
             "top": [hit_row(e) for e in f["top"]], "shown": [hit_row(e) for e in f.get("shown", [])],
             **({"live": f.get("live") or []} if "live" in f else {})}
            for f in found]
    return {"found": keep, "lines": record_lines(found)}


def shown_log(found):
    """Per question, for the runs log: what was shown and recall's first RECORD_SHOW places, by source, id,
    link and, for a log place, the record printed; and, brief, the live sessions shown, by id and title."""
    def brief(x):
        return {"src": x["src"], "id": x["id"], "link": x["link"],
                **({"record": f"{x['date']} {x['role']}"} if x["src"] == "logs" else {})}
    return [{"shown": [brief(x) for x in f.get("shown", [])], "first3": [brief(x) for x in f["top"][:RECORD_SHOW]],
             **({"live": [{"id": v["id"], "title": v["title"]} for v in f.get("live") or []]} if "live" in f else {})}
            for f in found or []]


def topic_log(topics):
    """Per question, for the runs log: the topic lookup's flag, the passage that left it to the user, and the best
    citation of each kind with its score."""
    def brief(h):
        return h and {"kind": h["kind"], "cite": h["cite"], "score": h["score"], "shared": len(h["shared"])}
    return [{"flag": brief(t["flag"]), "yours": brief(t["yours"]), "outward": t["outward"],
             "best": [brief(t[k][0]) for k in ("your words", "ruling", "doc") if t[k]]} for t in topics or []]


# ------------------------------------------------------------------------------------- answered before
def past_cards(rows):
    """The request ledger's answered cards: each row one card question (`question`) with its answer (`text`)."""
    return [r for r in rows or [] if r.get("source") == "card" and r.get("question") and r.get("text")]


def answered(question, cards, limit=3):
    """[(share, row)] for each past card whose question holds at least OVERLAP of this question's content words.
    The past card's question is what is compared, never its answer: a pick alone ('Hold it') shares almost no
    word with a re-ask of its question."""
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


# The user's own typed words in the last day: a new question that shares RECENT_SHARED content words with an answer
# they typed (TYPED_WORDS or more content words, so not a pick) within RECENT_HOURS is shown beside it, since what
# they just said may settle it. Known bad: a question asking where a demo's reset control lives, 50 minutes after
# the user's typed answer had put present and reset in the site's demo UI; it shared 4 words with that answer and
# 17% of its words, far under OVERLAP.
RECENT_HOURS, RECENT_SHARED, TYPED_WORDS = 24, 3, 6


def recent_words(question, cards, now=None, limit=2):
    """[(shared words, row)]: the user's typed card answers from the last RECENT_HOURS sharing RECENT_SHARED or more
    of this question's content words, most shared first, then newest."""
    q, now = words(question), now or dt.datetime.now(dt.timezone.utc)
    out = []
    for r in cards:
        try:
            ts = dt.datetime.fromisoformat((r.get("ts") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        ts = ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
        a = words(r["text"])
        if len(a) < TYPED_WORDS or not dt.timedelta(0) <= now - ts <= dt.timedelta(hours=RECENT_HOURS):
            continue
        shared = q & a
        if len(shared) >= RECENT_SHARED:
            out.append((sorted(shared), r))
    out.sort(key=lambda x: (len(x[0]), x[1].get("ts", "")), reverse=True)
    return out[:limit]


# ------------------------------------------------------------------------------------- topic lookup
# The record by topic (TOPIC in the help). Known bad: a card asked the user to run a solo test call to see whether
# captions keep coming while the screen is shared, when the capture tool's own README says the call's audio is the
# main source because sharing stops the captions; and two cards asked about builds for a set date (whether to ask
# two leads, then whether to send them a message asking if they'd like them) that a ruling row says are ours to
# build, nobody asked first. The rare-word lookup that ran then printed a port-default commit, a scroll bug and an
# old standup. Known good, which must not flag: an outward write to a teammate's board, starting a meeting
# transcript everyone sees, a note to the person who runs planning, and when to edit the user's own board.
# What the record held at ask time is less than it holds now. The README passages that settle the test call were
# edited in after that card; minutes before it, a session had added a paragraph proposing the call. Rebuilt as of
# the card, the test-call question still flags (0.37), but its next lead (0.35) is that proposing paragraph. The
# ruling row that settles the builds was written after both cards; the row in force then said the plan was
# proposed, not agreed, and without the later row neither question flags. So against the record as it stood, the
# topic lookup caught 1 of the 3 questions the record now settles; ours to do, written from this incident, caught
# the send. Calibrated on the cards asked over two weeks, with the ledger cut at each card's time and files as they
# are now: TOPIC_BAR 0.30 flagged one known-good card, 0.40 missed the test-call card (0.37); a 60-word length
# allowance flagged long tool catalogue rows, so a passage scores by its best TOPIC_WINDOW-sentence window instead.
TOPIC_BAR, TOPIC_SHARED = 0.35, 5
OUTWARD_BAR = 0.5
WORDS_BAR, WORDS_SHARED = 0.45, 6
TOPIC_WINDOW, TOPIC_LEN = 3, 40
TOPIC_SYSTEMS, TOPIC_SHOW, TOPIC_PRINT = 3, 2, 0.15
TOPIC_STOP = set("""the and for that this with what should from have has are was were will would can could into about
which when where there their them they you your his her its our not but all any each one two now then than also
only just more most some such does did done how why who whom whose it's don't isn't keep make made take want wants
need needs get got use used here these those being been very still yet same other another every both either
neither again before after while because since until within without please pls yes okay ok recommended option
options card question asked ask answer answered today yesterday tomorrow week day time way thing things like look
looks show shows say says said know see lines line whether instead rather let lets i'll i'm we'll we're you're
it’s that's there's what's he she him me my mine us we i a an of to in on at by or is be as if so do no it up out
off via per vs""".split())
TOPIC_WORD = re.compile(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?|[a-z][a-z0-9'’-]*[a-z0-9]")
# Blocks a user's message carries that aren't their words: a paste, an opened file, a reminder, a command's output.
PASTED = re.compile(r"<(pasted_content|ide_opened_file|ide_selection|system-reminder|command-[a-z]+|local-command-[a-z]+"
                    r"|bash-[a-z]+)[^>]*>.*?</\1>", re.S)
SENTENCE = re.compile(r"(?<=[.?!;])\s+|\s+\|\s+")
# A step that leaves the machine or that others see. What a system's doc says doesn't decide it.
OUTWARD = re.compile(r"\b(?:send|post|publish|reply|email|e-mail|ping|notify|message)\b(?!\s+(?:me|you)\b)"
                     r"|\badd (?:\w+ ){0,3}?(?:to|on|onto) (?:her|his|their|the team's|[A-Z]\w+'s)\b"
                     r"|\b(?:go|goes|put|land) (?:on|onto) (?:the|her|his|their|your|a) (?:\w+ )?board\b"
                     r"|\beveryone (?:sees|will see|in the (?:call|meeting))\b|\bbanner\b|\bvisible to\b"
                     r"|\bteammates? (?:see|sees|read|reads)\b", re.I)
# A passage that leaves the call to the user: the question is theirs, so it isn't flagged.
YOURS = re.compile(r"\b(?:his|her|their|your|the user's|[A-Z][a-z]+'s) (?:own )?(?:choice|decision)\b"
                   r"|\b(?:is|stays|remains) (?:his|her|their|your|the user's|[A-Z][a-z]+'s) call\b"
                   r"|\bask (?:him|her|them|the user|you) (?:first|each time|every time)\b")
RULING_NAME = re.compile(r"ruling|decision", re.I)
RULING_ID = re.compile(r"^\|\s*([A-Z]{1,3}\d{1,4}[a-z]?)\s*\|")
SUPERSEDES = re.compile(r"\bsupersedes ([A-Z]{1,3}\d{1,4}[a-z]?)\b", re.I)
TICK = re.compile(r"`([^`\n]+)`")
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")


def stem(w):
    """A word's stem: plural, -ing and -ed off, then a final e, so captions, captioning and caption share one."""
    w = re.sub(r"['’]s?$", "", w)
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", "e"), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not (suf == "s" and w.endswith(("ss", "us", "is"))):
            w = w[:-len(suf)] + rep
            break
    return w[:-1] if w.endswith("e") and len(w) > 4 else w


def topic_words(text):
    """The stems of a text's content words, links left out: a date such as 11/24 counts, a word under 3 letters doesn't."""
    out = []
    for w in TOPIC_WORD.findall(URL.sub(" ", text or "").lower()):
        if "/" not in w:
            w = w.strip("-'’")
            if len(w) < 3 or w in TOPIC_STOP:
                continue
        out.append(stem(w))
    return out


def typed_text(text):
    """What the user typed in a message: pasted blocks, opened-file notes and quoted lines ('> ...') taken out."""
    t = PASTED.sub(" ", text if isinstance(text, str) else "")
    return "\n".join(ln for ln in t.splitlines() if not ln.lstrip().startswith((">", "<!--")))


def topic_idf(rows, before=None):
    """A stem's weight: ln((N + 1) / (rows holding it + 1)) over the ledger rows before `before`, their text and
    card question."""
    df, n = collections.Counter(), 0
    for r in rows or []:
        if before and (r.get("ts") or "") >= before:
            continue
        n += 1
        df.update(set(topic_words(" ".join(x for x in (r.get("text"), r.get("question")) if isinstance(x, str)))))
    return lambda s: math.log((n + 1) / (df.get(s, 0) + 1))


def question_weights(q, idf):
    """{stem: weight} for a question's header and text, a header word half again: its topic."""
    head = set(topic_words(q.get("header") or ""))
    return {s: idf(s) * (1.5 if s in head else 1.0) for s in head | set(topic_words(q.get("question") or ""))}


def passage(kind, cite, text, **extra):
    """One passage to score: its kind, where to open it, its text and its windows of up to TOPIC_WINDOW sentences."""
    s = [x for x in SENTENCE.split(text) if x.strip()]
    wins = [" ".join(s[i:i + TOPIC_WINDOW]) for i in range(max(1, len(s) - TOPIC_WINDOW + 1))] if s else [text]
    return dict(extra, kind=kind, cite=cite, text=text, wins=[(w, set(topic_words(w))) for w in wins])


def score(qw, p):
    """(score, shared stems, window text) of a passage's best window: the share of the question's weight the window's
    words hold, times sqrt(TOPIC_LEN / its length) when it is longer."""
    tot, best = sum(qw.values()), (0.0, [], "")
    for text, ws in p["wins"]:
        shared = sorted(s for s in qw if s in ws)
        got = (sum(qw[s] for s in shared) / tot if tot else 0.0) * min(1.0, math.sqrt(TOPIC_LEN / max(len(ws), 1)))
        if got > best[0]:
            best = (got, shared, text)
    return best


def top_passages(qw, ps, k=TOPIC_SHOW):
    """The k best passages for a question, each as {"kind", "cite", "score", "shared", "excerpt", ...}."""
    got = []
    for p in ps:
        s, shared, text = score(qw, p)
        if s > 0:
            got.append(dict({x: v for x, v in p.items() if x != "wins"}, score=round(s, 3), shared=shared, excerpt=text))
    got.sort(key=lambda h: (-h["score"], h["cite"]))
    return got[:k]


def words_passages(rows, before=None, ledger=None):
    """The user's own typed words: each ledger row they typed (typed, mid-turn, or a card answer they typed) before
    `before`, with 6 or more content words once pastes and quotes are out. A pick of an option isn't typed words."""
    out = []
    for r in rows or []:
        if r.get("source") not in ("typed", "mid-turn", "card") or (before and (r.get("ts") or "") >= before):
            continue
        t = typed_text(r.get("text"))
        if len(set(topic_words(t))) < 6:
            continue
        on = f' on the card "{_clip(r.get("question"), 80)}"' if r.get("source") == "card" else ""
        out.append(passage("your words", f"{ledger or 'ledger'} {r.get('id') or '?'} ({(r.get('ts') or '')[:16]}Z, "
                                         f"{r.get('source')}{on})", t,
                           ts=r.get("ts") or "", ruled=r.get("kind") == "decision" or r.get("state") == "ruled"))
    return out


def md_blocks(text):
    """[(line, heading, block)] of a markdown text: each table row, each bullet with its continuation lines, and each
    paragraph, under the heading above it; separator rows and code fences left out."""
    out, head, buf, start, fence = [], "", [], 0, False

    def flush():
        if buf:
            out.append((start, head, " ".join(buf)))
        buf.clear()
    for n, line in enumerate((text or "").splitlines(), 1):
        s = line.strip()
        if s.startswith("```"):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if s.startswith("#"):
            flush()
            head = s.lstrip("# ")
        elif not s or s == "---" or re.fullmatch(r"\|?[\s:|-]+\|?", s):
            flush()
        elif s.startswith("|") or re.match(r"[-*] |\d+\. ", s):
            flush()
            buf.append(s)
            start = n
        else:
            if not buf:
                start = n
            buf.append(s)
    flush()
    return out


def doc_passages(path, text=None):
    """A doc's passages, each cited as path:line with its heading."""
    if text is None:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    return [passage("doc", f"{path}:{n}" + (f" ({_clip(h, 50)})" if h else ""), b) for n, h, b in md_blocks(text)]


def ruling_passages(path, text=None):
    """A rulings file's rows: in markdown, each table row keyed by an id such as J4 and each top-level bullet led by
    a bold title, without the rows another row supersedes; in JSON, each entry of its list (or of its "rulings"
    list) by its text fields. Each cited as path:line, or path and the entry's id."""
    if text is None:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    out = []
    if path.lower().endswith(".json"):
        d = json.loads(text)
        items = d.get("rulings") if isinstance(d, dict) and isinstance(d.get("rulings"), list) else d
        for e in items if isinstance(items, list) else []:
            if not isinstance(e, dict) or str(e.get("status") or "").lower() in ("retired", "superseded", "dropped"):
                continue
            t = " ".join(e[k] for k in ("topic", "ruling", "decision", "question", "answer", "text", "exceptions")
                         if isinstance(e.get(k), str))
            if t.strip():
                out.append(passage("ruling", f"{path} id {e.get('id') or '?'}", t, id=str(e.get("id") or "")))
        return out
    rows, gone = [], set()
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        m = RULING_ID.match(line)
        if m:
            rows.append((n, m.group(1), line.strip()))
        elif line.startswith("- **"):
            more = []
            for nxt in lines[n:]:
                if not nxt.startswith((" ", "\t")) or not nxt.strip():
                    break
                more.append(nxt.strip())
            rows.append((n, "", " ".join([line.strip()] + more)))
        else:
            continue
        gone.update(x.upper() for x in SUPERSEDES.findall(rows[-1][2]))
    return [passage("ruling", f"{path}:{n}" + (f" (row {i})" if i else ""), t, id=i)
            for n, i, t in rows if not (i and i.upper() in gone and not SUPERSEDES.search(t))]


def workspace_root():
    """workspace.root, else the project folder."""
    v = kit_config.get("workspace", "root")
    return os.path.abspath(os.path.expanduser(v)) if isinstance(v, str) and v.strip() else os.getcwd()


def ruling_files():
    """The files ruling rows come from: each file at the top of a notes folder (recall.notes) whose name says
    rulings or decisions, the workspace docs (workspace.docs) named so, and ledger.rulings and ledger.rulings_also."""
    import recall
    found = []
    for d in recall.notes_dirs():
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        found += [os.path.join(d, n) for n in names if RULING_NAME.search(n) and n.lower().endswith((".md", ".json"))]
    root = workspace_root()
    docs = kit_config.get("workspace", "docs") or []
    found += [os.path.join(root, os.path.expanduser(p)) for p in (docs if isinstance(docs, list) else [docs])
              if isinstance(p, str) and RULING_NAME.search(os.path.basename(p))]
    for key in ("rulings", "rulings_also"):
        v = kit_config.get("ledger", key)
        found += [os.path.expanduser(p) for p in (v if isinstance(v, list) else [v]) if isinstance(p, str) and p.strip()]
    seen, out = set(), []
    for p in found:
        r = os.path.realpath(p)
        if r not in seen and os.path.isfile(p):
            seen.add(r)
            out.append(os.path.abspath(p))
    return out


def name_words(tok):
    """A folder's or file's name as words: TeamsTranscripts/ -> Teams Transcripts, DS-Workstream -> DS Workstream."""
    last = re.sub(r"\.(md|py|json|jsonc|html|txt)$", "", tok.rstrip("/").split("/")[-1])
    return " ".join(p for w in re.split(r"[\s_.\-]+", last) for p in CAMEL.split(w) if p)


def map_systems(text, root):
    """[{"name", "desc", "docs"}] for each bullet of a workspace map that opens with a folder (resolved against its
    parent bullet's folder, then the root) holding a README.md: the system, its line, and that README."""
    bullets = []
    for n, line in enumerate((text or "").splitlines(), 1):
        m = re.match(r"^(\s*)- (.*)$", line)
        if m:
            bullets.append([len(m.group(1)), m.group(2)])
        elif line.strip() and bullets and bullets[-1][0] >= 0 and line.startswith(" "):
            bullets[-1][1] += " " + line.strip()
        elif line.strip():
            bullets.append([-1, line.strip()])
    out, stack = [], []
    for depth, body in bullets:
        if depth < 0:
            stack = []
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = next((d for _, d in reversed(stack) if d), root)
        toks = TICK.findall(body.split(" - ", 1)[0]) if body.startswith("`") else []
        opens = next((p for t in toks[:1] for p in (os.path.join(parent, t), os.path.join(root, t))
                      if os.path.isdir(p)), None)
        stack.append((depth, opens))
        if opens and os.path.isfile(os.path.join(opens, "README.md")):
            out.append({"name": name_words(toks[0]), "desc": body, "docs": [os.path.join(opens, "README.md")]})
    return out


def kb_systems():
    """([{"name", "desc", "docs"}] for each knowledge body: its name and aliases, its line, its page and the canonical
    files its line names (a folder by its README.md); [the knowledge entries as ruling passages]) from kb.py's index,
    or ([], []) when there is none."""
    import kb
    bodies, why = kb.read_index()
    if why:
        return [], [], why
    d, root = kb.kb_dir(), kb.root()
    systems, entries = [], []
    for b in bodies:
        page = os.path.join(d, b["slug"] + ".md")
        listed = b["rest"].split("Canonical:", 1)[1].split("Name traps:", 1)[0] if "Canonical:" in b["rest"] else ""
        docs = [page] if os.path.isfile(page) else []
        for t in TICK.findall(listed):
            p = os.path.join(root, os.path.expanduser(t))
            p = os.path.join(p, "README.md") if os.path.isdir(p) else p
            if p.endswith(".md") and os.path.isfile(p) and p not in docs:
                docs.append(p)
        names = " ".join([b["name"]] + [a.split("alias:", 1)[1].split("(since")[0] for a in b.get("aliases", [])])
        systems.append({"name": names.replace("|", " ").replace("=", " "), "label": b["name"],
                        "desc": b["rest"].split("Canonical:", 1)[0], "docs": docs})
        if os.path.isfile(page):
            with open(page, encoding="utf-8", errors="replace") as f:
                es, _, _ = kb.parse_page(f.read(), b["slug"])
            entries += [passage("ruling", f"{page}:{e['line']} (knowledge entry {e.get('id') or e['subject']})",
                                f"{e.get('question') or ''} {e.get('answer') or ''}", id=e.get("id") or "")
                        for e in es if e.get("answer")]
    return systems, entries, None


def topic_sources(rows, before=None):
    """What the topic lookup reads: {"words", "rulings", "systems", "read" (a doc's passages by path), "status",
    "files"}. A part with nothing configured says so; one that fails says it did not run."""
    import recall
    status, files = {}, {}
    src = {"words": words_passages(rows, before, recall.ledger_path()), "rulings": [], "systems": [], "status": status,
           "files": files}
    status["your words"] = "ran"
    paths = ruling_files()
    for p in paths:
        try:
            ps = ruling_passages(p)
        except (OSError, ValueError) as e:
            status[f"ruling {p}"] = f"did not run: {type(e).__name__}: {e}"[:160]
            continue
        src["rulings"] += ps
        files[p] = len(ps)
    status["rulings"] = f"ran on {len(paths)} file(s)" if paths else "not configured (no rulings or decisions file)"
    mp = kit_config.get("workspace", "map")
    if isinstance(mp, str) and mp.strip():
        path = os.path.join(workspace_root(), os.path.expanduser(mp))
        try:
            with open(path, encoding="utf-8") as f:
                src["systems"] += map_systems(f.read(), workspace_root())
            status["map"] = f"ran ({path})"
        except OSError as e:
            status["map"] = f"did not run: {type(e).__name__}: {e}"[:160]
    else:
        status["map"] = "not configured (workspace.map)"
    try:
        ks, entries, why = kb_systems()
        src["systems"] += ks
        src["rulings"] += entries
        status["knowledge"] = f"not configured ({why})" if why else f"ran ({len(ks)} bodies, {len(entries)} entries)"
    except Exception as e:  # noqa: BLE001 -- a knowledge index that can't be read is named, never passed
        status["knowledge"] = f"did not run: {type(e).__name__}: {e}"[:160]
    cache = {}

    def read(p):
        if p not in cache:
            try:
                cache[p] = doc_passages(p)
            except OSError:
                cache[p] = []
        return cache[p]
    src["read"] = read
    return src


def systems_for(qw, systems, k=TOPIC_SYSTEMS):
    """The k systems the question names: each sharing one or more stems with its name, by twice the weight of those
    plus the weight of the stems its line shares."""
    got = []
    for s in systems:
        nb, db = set(topic_words(s["name"])), set(topic_words(s["desc"]))
        named = [w for w in qw if w in nb]
        if named:
            got.append((2 * sum(qw[w] for w in named) + sum(qw[w] for w in qw if w in db and w not in nb), s))
    got.sort(key=lambda x: (-x[0], x[1]["name"]))
    return [s for _, s in got[:k]]


def outward(q):
    """The OUTWARD phrase in the question or its first option's label, or None."""
    first = ((q.get("options") or [{}])[0] or {}).get("label") or ""
    m = OUTWARD.search(q.get("question") or "") or OUTWARD.search(first)
    return m.group(0) if m else None


def topic_lookup(card, rows, before=None, src=None, idf=None):
    """Per question: {"terms": its heaviest stems, "your words", "ruling", "doc": the best passages of each kind,
    "systems": the names read, "outward": the phrase or None, "flag": the passage that speaks to it or None, "yours":
    a passage that speaks to it and leaves the call to the user, or None}. src: topic_sources(rows, before) or a
    stand-in; idf: topic_idf(rows, before) or a stand-in."""
    src = src if src is not None else topic_sources(rows, before)
    idf = idf or topic_idf(rows, before)
    out = []
    for q in card.get("questions", []):
        qw = question_weights(q, idf)
        if not qw:
            out.append({"terms": [], "order": [], "your words": [], "ruling": [], "doc": [], "systems": [],
                        "outward": None, "flag": None, "yours": None})
            continue
        systems = systems_for(qw, src["systems"])
        docs = list(dict.fromkeys(p for s in systems for p in s["docs"] if "draft" not in os.path.basename(p).lower()))
        got = {"your words": top_passages(qw, src["words"]), "ruling": top_passages(qw, src["rulings"]),
               "doc": top_passages(qw, [p for d in docs for p in src["read"](d)])}
        out_ = outward(q)
        bars = {"ruling": (OUTWARD_BAR if out_ else TOPIC_BAR, TOPIC_SHARED), "your words": (WORDS_BAR, WORDS_SHARED),
                "doc": (None if out_ else TOPIC_BAR, TOPIC_SHARED)}
        speaks, yours = [], None
        for kind in ("ruling", "your words", "doc"):
            for h in got[kind]:
                if h["score"] >= TOPIC_BAR and len(h["shared"]) >= TOPIC_SHARED and YOURS.search(h["excerpt"]):
                    yours = yours or h
                bar, n = bars[kind]
                if bar is not None and h["score"] >= bar and len(h["shared"]) >= n:
                    speaks.append(h)
        order = sorted(qw, key=lambda s: (-qw[s], s))
        out.append({"terms": order[:8], "order": order, **got, "systems": [s.get("label") or s["name"] for s in systems],
                    "outward": out_, "flag": None if yours else (speaks[0] if speaks else None), "yours": yours})
    return out


def topic_lines(topics):
    """[(question number, line)]: each question's topic, the best passage of each kind at TOPIC_PRINT or more with
    its score, link and excerpt, and a passage that leaves the call to the user."""
    out = []
    for n, t in enumerate(topics or [], 1):
        if not t["terms"]:
            out.append((n, "topic    no words to weigh"))
            continue
        out.append((n, f"topic    {', '.join(t['terms'])}" + (f"; systems read: {'; '.join(t['systems'])}" if t["systems"]
                                                              else "; no system named")
                    + (f"; outward ({t['outward']!r}), so a doc alone doesn't decide it" if t["outward"] else "")))
        for kind in ("your words", "ruling", "doc"):
            hs = [h for h in t[kind] if h["score"] >= TOPIC_PRINT]
            out += [(n, f"  {kind:10} {h['score']:.2f} ({len(h['shared'])} shared)  {h['cite']}: \"{_clip(h['excerpt'], 220)}\"")
                    for h in hs[:1]] or [(n, f"  {kind:10} nothing at {TOPIC_PRINT} or more")]
        if t["yours"]:
            out.append((n, f"  yours      {t['yours']['cite']} leaves this call to the user: "
                           f"\"{_clip(t['yours']['excerpt'], 200)}\""))
    return out


# Asking leave for work that is ours. Known bad: a card asked to send two leads a drafted message, "could we show
# you builds from 5 to 8 briefs?", about builds a ruling says are ours to build and have ready, nobody asked first.
# Known good: a drafted board card asking a platform team "Can the builder run builds on a server ...?" (a
# question for them, not leave for us), and a note handing someone facts.
LEAVE = re.compile(r"\b(?:could|can|may|shall|should|might) we (?:\w+ ){0,2}?(?:show|build|make|run|prepare|bring|"
                   r"demo|put together|create|set up|try|do|give|walk)\b"
                   r"|\bwould (?:you|they) (?:like|want|be (?:ok|okay|fine|open to|interested in)) "
                   r"(?:us|me|to see|if|having|seeing)\b"
                   r"|\bdo (?:you|they) want (?:us|me) to\b|\b(?:is it|would it be) (?:ok|okay|alright|fine) (?:if|for) (?:we|us)\b",
                   re.I)
ASK_LEAVE = re.compile(r"\b(?i:ask(?:ing)?) (?:[A-Z]\w+|him|her|them|the \w+)(?: (?:and|or) [A-Z]\w+)? (?:whether|if) "
                       r"(?:we (?:may|can|could|should)|they(?:'d| would)? (?:like|want)|it'?s (?:ok|okay|fine))")
QUOTE = re.compile(r"\"([^\"\n]{12,})\"|“([^”\n]{12,})”")


def ours_to_do(q):
    """(the phrase, where it is) when the question asks whether to ask leave for work that is ours, or asks to send a
    drafted message (an option's preview, or a quoted message) that asks it; else None."""
    m = ASK_LEAVE.search(q.get("question") or "")
    if m:
        return m.group(0), "the question"
    if not outward(q):
        return None
    for o in q.get("options") or []:
        m = isinstance(o, dict) and LEAVE.search(str(o.get("preview") or ""))
        if m:
            return m.group(0), f"the drafted message in option {o.get('label')!r}'s preview"
    for t in [q.get("question") or ""] + [str(o.get(k) or "") for o in q.get("options") or [] if isinstance(o, dict)
                                          for k in ("label", "description")]:
        for a, b in QUOTE.findall(t):
            m = LEAVE.search(a or b)
            if m:
                return m.group(0), "the quoted message"
    return None


# ------------------------------------------------------------------------------------- settled drafts
# A question about Figma comment drafts: it names the drafts file, or posting or sending comments or drafts.
DRAFTISH = re.compile(r"drafts\.md|\bFigma (?:comment|note|draft)s?\b"
                      r"|\b(?:post|send)\w*\b[^.?!]{0,60}\b(?:comment|draft)s?\b", re.I)


def settled_rules():
    """drafts_store's structure rules whose problem means the card asks about a draft that shouldn't be posted as
    it is, and the own-open and ask checks that could not run, which are named, never passed."""
    import drafts_store
    return ("ask", "override", "own-open", drafts_store.OWN_NOT_RUN, drafts_store.ASK_NOT_RUN)


def drafts_file():
    """The drafts file drafts_store reads ($FIGMA_DRAFTS, else figma.drafts), or None."""
    import drafts_store
    return drafts_store.drafts_path()


def settled_drafts():
    """drafts_store's ask, override and own-open problems in the drafts file, and the drafts its ask or own-open
    check couldn't judge: a draft asking what the record settles, one written to open a new thread, or one that
    links the user's own open comment. Each row (file, line, rule, words, title): title is the draft's subject,
    its heading before the ' — ' that opens the status. No drafts file configured: no rows."""
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
def check(card, cards, drafts=None, found=None, reader=None, now=None, topics=None):
    """[(question number, flag, detail)]. drafts: settled_drafts or a stand-in; without one the settled-draft
    flag isn't checked. found: run_record()'s lookups, one per question. reader(question, top) -> [(flag,
    detail)] reads a question's top RECORD_TOP for what the record settles; without one (today) nothing is
    flagged from them. now: the time your words? counts the last RECENT_HOURS back from (default the clock).
    topics: topic_lookup()'s results, one per question, whose flag is may answer; ours to do needs no lookup."""
    flags, seen, failing = [], set(), {}
    for n, (q, f) in enumerate(zip(card.get("questions", []), found or []), 1):
        if reader and f.get("terms"):
            flags += [(n, flag, detail) for flag, detail in reader(q, f["top"])]
    for n, t in enumerate(topics or [], 1):
        h = t.get("flag")
        if h:
            what = {"ruling": "a ruling row", "your words": "what the user typed", "doc": "the system's own doc"}[h["kind"]]
            flags.append((n, "may answer", f"RECORD MAY ANSWER: {h['cite']} ({what}; {h['score']:.2f} of the question's "
                                           f"weight, {len(h['shared'])} words shared): \"{_clip(h['excerpt'], 240)}\"; "
                                           f"open it and act on it before asking"))
    for n, q in enumerate(card.get("questions", []), 1):
        m = ours_to_do(q)
        if m:
            flags.append((n, "ours to do", f"OURS TO DO: {m[1]} asks leave for work that is ours ('{m[0]}'): build it "
                                           f"and have it ready; ask only if the record names someone whose go it needs"))

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
        first = (q.get("options") or [{}])[0]
        asks = YOU_DO.search(q.get("question", "")) or I_DO.search(first.get("label", ""))
        if asks and not any(ONLY_YOU.search(t) for t in texts[:2]):
            flags.append((n, "your work?", f"'{asks.group(0).strip()}' puts a task to the user, not a decision: do it "
                                           f"or research it in a session; ask only if no session can, and say why in "
                                           f"the question"))
        k = len(q.get("options", []))
        if not 2 <= k <= 4:
            flags.append((n, "shape", f"{k} options"))
        if len(q.get("header", "")) > 12:
            flags.append((n, "shape", f"header {q.get('header')!r} is over 12 characters"))
        hits = answered(q.get("question", ""), cards)
        for shared, r in hits:
            flags.append((n, "answered?", f"{shared:.0%} shared with {r.get('ts', '')[:10]} session "
                                          f"{(r.get('session') or '?')[:8]}: {r['question'][:100]} -> {r['text'][:60]}"))
        for shared, r in recent_words(q.get("question", ""), cards, now):
            if not any(r is h for _, h in hits):
                flags.append((n, "your words?", f"shares {', '.join(shared)} with what the user typed "
                                                f"{r.get('ts', '')[:16]}Z to {(r.get('question') or '')[:80]!r}: "
                                                f"{r['text'][:200]!r}; read it before asking"))
    return flags


def log_run(card, flags, path, record=None, found=None, topics=None, before=None):
    row = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "questions": [q.get("question", "")[:80] for q in card.get("questions", [])],
           "flags": len(flags)}
    if record is not None:
        row["record"] = record
    if before:
        row["before"] = before
    if found:
        row["shown"] = shown_log(found)
    if topics:
        row["topics"] = topic_log(topics)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def utc_text(t):
    """A time as the ledger writes it, UTC with milliseconds and Z, so the two compare as text; None stays None."""
    if not t:
        return None
    t = t if isinstance(t, dt.datetime) else dt.datetime.fromisoformat(str(t).strip().replace("Z", "+00:00"))
    t = t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def checked(card, cards, rows, sid, no_record=False, runs=None, runner=None, drafts=settled_drafts, before=None,
            topic_src=None, leads=False):
    """(the lines main prints for one card, its exit code), the run logged to runs: the flags; each question's
    topic lines and, with leads, its record lines; the line saying the leads didn't run or weren't asked for; the
    card with its ids linked when one is bare; and the summary. leads: recall's --brief search under each question
    (run_record with BRIEF_SOURCES), its own log cut at the user's last message there (sid, from the ledger rows).
    runner stands in for run_record and topic_src for topic_sources. before: the record as it stood then, the
    ledger rows and past cards cut there. no_record is a no-op, and says so."""
    before = utc_text(before)
    if before:
        rows = [r for r in rows if (r.get("ts") or "") < before]
        cards = [c for c in cards if (c.get("ts") or "") < before]
    now = dt.datetime.fromisoformat(before.replace("Z", "+00:00")) if before else dt.datetime.now(dt.timezone.utc)
    src = topic_src if topic_src is not None else topic_sources(rows, before)
    topics = topic_lookup(card, rows, before, src=src)
    last = pushback_score.last_before(pushback_score.user_times(rows).get(sid, []), now) if sid else None
    since = last and last.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    found, why = None, None
    if leads:
        vocab = vocabulary(rows)
        ts = [topic_terms(q, t, vocab) for q, t in zip(card.get("questions", []), topics)]
        found, why = (runner or run_record)(card, sid, since, vocab=vocab, before=before, ts=ts,
                                            sources=BRIEF_SOURCES, brief=True)
    flags = check(card, cards, drafts, (found or {}).get("found"), now=now, topics=topics)
    log_run(card, flags, runs or runs_path(),
            record=("ran" if found else f"did not run: {why}") if leads else "not asked",
            found=(found or {}).get("found"), topics=topics, before=before)
    out = [f"Q{n}  {kind:10} {what}" for n, kind, what in flags]
    if no_record:
        out.append("--no-record is a no-op: the topic lookup always runs, and recall's leads only with --leads")
    lines, tlines = (found or {}).get("lines", []), topic_lines(topics)
    for n in range(1, len(card.get("questions", [])) + 1):
        out += [f"Q{m}  {line}" for m, line in tlines if m == n]
        out += [f"Q{m}  {line}" for m, line in lines if m == n]
    if leads and not found:
        out.append(f"record   recall leads did not run: {why}; the topic lookup above ran, the leads under it did not")
    elif not leads:
        out.append("record   recall's leads weren't asked for: --leads adds them under each question (about 100 s a "
                   "card; they flag nothing)")
    if any(kind == "bare id" for _, kind, _ in flags):
        fixed, bare = linked_card(card)
        out += ["card, with its ids linked in place (ask this one):", json.dumps(fixed, ensure_ascii=False, indent=1)]
        if bare:
            out.append(f"still bare, no file or work item found for: {', '.join(bare)}"
                       + ("" if all(kit_config.ado()) or not any(b.startswith("#") for b in bare)
                          else " (ado.org and ado.project are not set, so no work item links)"))
    no_drafts = drafts is settled_drafts and not drafts_file()
    nq = len(card.get("questions", []))
    may = [f"Q{n}" for n, k, _ in flags if k == "may answer"]
    ours = [f"Q{n}" for n, k, _ in flags if k == "ours to do"]
    st = src.get("status") or {}
    out.append(f"card_check: {len(flags)} flag(s) in {nq} question(s); record may answer {len(may)} of {nq}"
               + (f" ({', '.join(may)})" if may else "") + f", ours to do {len(ours)} of {nq}"
               + (f" ({', '.join(ours)})" if ours else "")
               + f"; topic lookup: {'; '.join(f'{k} {v}' for k, v in st.items())}"
               + f"; {len(cards)} past card answers read; recall leads "
               + ("ran" if found else "did not run" if leads else "not asked for (--leads)")
               + (f"; the record as it stood before {before}" if before else "")
               + ("; no drafts file configured (figma.drafts or $FIGMA_DRAFTS), so no draft was checked"
                  if no_drafts else ""))
    gone = [k for k, v in st.items() if str(v).startswith("did not run")]
    return out, 1 if flags else (2 if (leads and not found) or gone else 0)


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
                if r.get("before"):
                    continue        # a replay (--before) of a card already asked: no check of it
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
              "session": "bbbbbbbb-0000"},
             # A pick that shares no word with a re-ask of its question.
             {"source": "card", "question": "Your chat draft to the vendor about the access request and the 14 tool "
                                            "fixes is ready, and nothing holds it. What should happen to it?",
              "text": "Hold it", "ts": "2026-11-05T07:27:00Z", "session": "cccccccc-0000"}]
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
        ("re-asked behind a pick", {"questions": [{**q0, "question":
                                    "The chat draft to the vendor about the access request and the 14 tool fixes is "
                                    "ready. Send it, or hold it?"}]}, {"answered?"}),
    ]
    bad = 0
    for name, card, want in cases:
        got = {f[1] for f in check(card, cards)}
        good = got == want
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  {name}: want {sorted(want)}, got {sorted(got)}")
    # Your words in the last day: a question asking where a demo's reset control lives, 50 minutes after the user's
    # typed answer put reset in the site's demo UI, sharing 4 words and 17% of its words (known bad); the same answer
    # 3 days old, and a pick sharing 3 of its words (known good: no flag).
    said = ("one shell with free screens i guess? but our lab and network demos had no present or reset mode, right? "
            "they reset on refresh or something - so wouldnt those be part of the site demo ui instead of each demo's "
            "actual ui?")
    reset_q = {"questions": [{**q0, "question": (
        "Reset in rebuilt walkthroughs: question 9 of the spec says the site's panel needs no reset because the demo "
        "build has its own Reset button. The Present frame in the design and last week's working session put reset "
        "outside the demo. Where does the Reset control live?")}]}
    now = dt.datetime(2026, 11, 10, 4, 0, tzinfo=dt.timezone.utc)
    row = lambda text, ts: [{"source": "card", "text": text, "ts": ts, "session": "dddddddd-0000",  # noqa: E731
                             "question": "Which wins: one shell, fixed layouts, or fully free?"}]
    extra_recent = 0    # the your-words and your-work cases, which the total below counts one by one
    for name, rows, want in (("known-bad: the user's typed answer 50 minutes earlier", row(said, "2026-11-10T03:10:40Z"), 1),
                             ("known-good: the same answer 3 days earlier", row(said, "2026-11-07T03:10:40Z"), 0),
                             ("known-good: a pick, not typed words", row("Fixed layouts, reset in the site demo",
                                                                         "2026-11-10T03:10:40Z"), 0)):
        got = [f for f in check(reset_q, rows, now=now) if f[1] == "your words?"]
        good = len(got) == want
        bad, extra_recent = bad + (not good), extra_recent + 1
        print(f"{'PASS' if good else 'FAIL'}  your words: {name}: want {want} flag, got {len(got)}")
    # A cleanup card whose only overlap with a typed answer is link words (example, com, https): no lead.
    linked_q = {"questions": [{**q0, "question": (
        "Close these issues now? https://git.example.com/team/x/-/work_items/11 and https://www.example.com/us-en/x")}]}
    got = [f for f in check(linked_q, row("The model endpoint is OpenAI-compatible: base_url https://models.example.com"
                                          "/v1, model small-flash-0731, key in the env file", "2026-11-10T03:10:40Z"),
                            now=now) if f[1] == "your words?"]
    bad, extra_recent = bad + bool(got), extra_recent + 1
    print(f"{'FAIL' if got else 'PASS'}  your words: known-good: words shared only through links: want 0, got {len(got)}")
    # Your work: a hand-labelling ask the user answered by saying no person was needed, a check in the design file's
    # version history, a recall of an old call, and a recommended option that has the user do it (known bad); an
    # accept no session may give, a spend, a tracker write and a send the user reads first (known good).
    ask_q = lambda text, first="Yes (Recommended)": {"questions": [{**q0, "question": text, "options": [  # noqa: E731
        {"label": first, "description": "x"}, q0["options"][1]]}]}
    for name, card, want in (
            ("known-bad: hand labels", ask_q("The render check has to agree with a person on 90% of first screens. "
                                             "Will you label about 30 first-screen screenshots on a local page?",
                                             "I'll label them (Recommended)"), 1),
            ("known-bad: version history", ask_q("Will you open last week's version in the design file's version "
                                                 "history and read both stamps' avatars?"), 1),
            ("known-bad: an old call", ask_q("Can you recall which call named the owner of the gallery integration?"), 1),
            ("known-bad: only the option", ask_q("Which reviewer should go through the 40 board questions?",
                                                 "I'll review them myself (Recommended)"), 1),
            ("known-good: the user's accept", ask_q("The command that checks it needs your one-time accept on this "
                                                    "machine, and no session may accept for you. Will you accept it?",
                                                    "I'll run the accept (Recommended)"), 0),
            ("known-good: a spend", ask_q("On this machine a build finishes only if a person approves its prompts. "
                                          "Run all four arms?", "All four arms (Recommended)"), 0),
            ("known-good: a tracker write", ask_q("Work item 4242 still names someone who has left. Retitle it?",
                                                  "Retitle it (Recommended)"), 0),
            ("known-good: a send the user reads", ask_q("Will you read the call message again before you send it?"), 0)):
        got = [f for f in check(card, cards) if f[1] == "your work?"]
        good = len(got) == want
        bad, extra_recent = bad + (not good), extra_recent + 1
        print(f"{'PASS' if good else 'FAIL'}  your work: {name}: want {want} flag, got {len(got)}")
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
            ("drafts.md", 64, drafts_store.ASK_NOT_RUN, "the ask check did not run (SettledNotRun: not accepted)"),
            ("drafts.md", 68, drafts_store.OWN_NOT_RUN, "the own-open check did not run (HTTPError: 429)")]
        got = [f for f in check(post4, cards, drafts=settled_drafts) if f[1] == "settled draft"]
        good = len(got) == 2 and all("did not run" in g[2] for g in got)
        bad, extra = bad + (not good), extra + 1
        print(f"{'PASS' if good else 'FAIL'}  known-bad: an ask or own-open check that could not run is flagged, "
              f"never passed: want 2, got {len(got)}")
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
            # a replay (--before) of the footer card, logged before its ask: no check of it, so footer stays unchecked
            f.write(json.dumps({"ts": at(4)[:19] + "Z", "questions": [q["question"][:80] for q in footer["questions"]],
                                "flags": 0, "before": at(6)}) + "\n")
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
              f"checked, a replay (--before) checks nothing, and a run for a card never asked is counted apart: want "
              f"[1, 2, 1], got {tot}")
    rec = selftest_record()
    bad += rec[0]
    top = selftest_topic()
    bad += top[0]
    total = len(cases) + extra + extra_recent + 1 + rec[1] + top[1]
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
    q3 = {"question": "In Teams, do the captions stop when the screen is shared?", "header": "Captions"}
    res.append(("other callers' terms are as before: terms() on the question and options, 4 of them, a name with its "
                "leading word; --leads drops that word",
                lookup_terms(q) == terms(question_text(q), 4) and len(t) == 4 and "In Teams" in lookup_terms(q3)
                and "Teams" in brief_terms(q3) and "In Teams" not in brief_terms(q3)))
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

    # Other callers (figma_post's batch --check, question_coverage) get recall's full search, as before; --leads
    # passes the brief sources, the notes as --brief keeps them, and the live sessions.
    import recall
    asked_with = []

    def noting(asks, opts):
        asked_with.append(tuple(opts.sources))
        return searcher(asks, opts)
    recall.CONFIG.pop("figma_canvas", None)
    full = record_lookup(card, own, since, searcher=noting)
    res.append(("by default the lookup is recall's full search, Figma from its cache, with no live sessions",
                asked_with == [RECORD_SOURCES] and set(RECORD_SOURCES) >= {"logs", "memory", "figma"}
                and recall.CONFIG.get("figma_canvas") == "cache" and "live" not in full[0]
                and "live sessions" not in full[0]["status"] and "the first log place" in record_lines(full)[0][1]
                and "live" not in found_json(full)["found"][0] and "live" not in shown_log(found_json(full)["found"])[0]))
    led = os.path.abspath(recall.ledger_path())
    noted = json.loads(json.dumps(planted))
    noted["notes"] = {"ran": True, "partial": [], "hits": [
        {"head": f"{led}:4", "excerpt": "Project Atlas", "strength": 6, "ts": "2026-10-30T00:00:00Z", "ids": [f"file:{led}"]},
        {"head": "~/w/.cache/ado/4242.md:1", "excerpt": "Project Atlas", "strength": 5, "ts": "2026-10-30T00:00:00Z",
         "ids": ["file:~/w/.cache/ado/4242.md"]},
        {"head": "~/w/notes/atlas.md:9", "excerpt": "Project Atlas", "strength": 2, "ts": "2026-10-29T00:00:00Z",
         "ids": ["file:~/w/notes/atlas.md"]}]}
    asked_with.clear()
    lv = [{"title": "Atlas rename", "id": "local_123456789abcdef", "last": "2026-10-31T05:00:00.000Z",
           "now": "renaming the gallery", "holds": ["Project Atlas", "c0ffee1"]}]
    br = record_lookup(card, own, since, sources=BRIEF_SOURCES, brief=True,
                       searcher=lambda asks, opts: (asked_with.append(tuple(opts.sources)),
                                                    [{"q": a, "src": json.loads(json.dumps(noted))} for a in asks])[1],
                       lives=lambda ts, before: ([lv for _ in ts], "ran"))
    bl = record_lines(br)
    kept = [h["head"] for h in noted["notes"]["hits"]]
    res.append(("--leads searches the brief sources, leaves the ledger and .cache notes out, and prints the live "
                "sessions after the strongest hits",
                asked_with == [BRIEF_SOURCES] and br[0]["live"] == lv and br[0]["status"]["live sessions"] == "ran"
                and [e["hit"]["head"] for e in br[0]["top"] if e["src"] == "notes"] == [kept[2]]
                and "then the live sessions" in bl[0][1] and bl[-1][1].startswith("  live  Atlas rename")
                and shown_log(found_json(br)["found"])[0]["live"] == [{"id": lv[0]["id"], "title": "Atlas rename"}]))
    took = {}
    real = globals()["record_lookup"]
    with tempfile.TemporaryDirectory() as tmp:
        for name, extra in (("old", {}), ("brief", {"sources": list(BRIEF_SOURCES), "brief": True})):
            src_f, dst_f = os.path.join(tmp, f"{name}.json"), os.path.join(tmp, f"{name}.out.json")
            with open(src_f, "w", encoding="utf-8") as fh:
                json.dump({"card": card, "own": None, "since": None, "terms": [["Atlas"]], **extra}, fh)
            globals()["record_lookup"] = lambda *a_, **kw: (took.__setitem__(name, kw), [])[1]
            try:
                record_child(src_f, dst_f)
            finally:
                globals()["record_lookup"] = real
    res.append(("the lookup child passes sources and brief through, and a request without them is the full search",
                took.get("old", {}).get("sources") == RECORD_SOURCES and took["old"].get("brief") is False
                and tuple(took.get("brief", {}).get("sources") or ()) == BRIEF_SOURCES and took["brief"].get("brief") is True))

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
        nothing = {"words": [], "rulings": [], "systems": [], "read": lambda p: [], "status": {"rulings": "ran"}}
        ran = {"found": [{"terms": ["#4242"], "status": {}, "top": [], "shown": []}],
               "lines": [[1, "record   #4242: the first log place"], [1, "   1. logs  abcdefgh  a lead"]]}
        asked = []
        out, code = checked(clean, [], [], None, runs=runs, drafts=None, topic_src=nothing,
                            runner=lambda c, o, s, **_: (asked.append(1), (ran, None))[1])
        res.append(("without --leads the leads don't run: one line says they weren't asked for and names --leads, "
                    "nothing says did not run, and a clean card exits 0",
                    not asked and code == 0 and sum("weren't asked for: --leads" in x for x in out) == 1
                    and not any("did not run" in x for x in out) and "recall leads not asked for" in out[-1]
                    and last_row().get("record") == "not asked"))
        out, code = checked(clean, [], [], None, no_record=True, runs=runs, drafts=None, topic_src=nothing,
                            runner=lambda c, o, s, **_: (asked.append(1), (ran, None))[1])
        res.append(("--no-record is a no-op, and says so",
                    not asked and code == 0 and any("--no-record is a no-op" in x for x in out)))
        out, code = checked(clean, [], [], None, runs=runs, drafts=None, topic_src=nothing, leads=True,
                            runner=lambda c, o, s, **_: (None, "over 150 s"))
        row = last_row()
        res.append(("leads asked for that timed out print the did-not-run line, are logged, and exit 2",
                    code == 2 and any("leads did not run: over 150 s" in x for x in out)
                    and row.get("record") == "did not run: over 150 s"))
        out, code = checked(clean, [], [], None, runs=runs, drafts=None, topic_src=nothing, leads=True,
                            runner=lambda c, o, s, **_: (ran, None))
        order = [x.split()[1] for x in out if x.startswith("Q1  ")]
        res.append(("a lookup that ran prints that question's topic lines, then its leads, and exits 0",
                    order[0] == "topic" and order[-2:] == ["record", "1."] and code == 0
                    and last_row().get("record") == "ran"))
        out, code = checked(clean, [], [], None, runs=runs, drafts=None,
                            topic_src=dict(nothing, status={"map": "did not run: OSError: gone"}))
        res.append(("a topic source that did not run is named and exits 2 when nothing flagged, never a pass",
                    code == 2 and "map did not run" in out[-1]))
        seen = {}
        said = [{"source": "typed", "session": "s1", "ts": "2026-10-31T06:00:00.000Z"},
                {"source": "typed", "session": "s2", "ts": "2026-10-31T07:00:00.000Z"}]
        checked(clean, [], said, "s1", runs=runs, drafts=None, topic_src=nothing, leads=True,
                runner=lambda c, o, s, **_: (seen.update(own=o, since=s), (ran, None))[1])
        res.append(("the asking session's own log is cut at the user's last message there, from the ledger",
                    seen == {"own": "s1", "since": "2026-10-31T06:00:00.000Z"}))
        # --before: the record as it stood then. A past card answered after it, and the user's message after it,
        # aren't read, so a replay of a card already asked isn't flagged by its own answer.
        replay = {"questions": [dict(clean["questions"][0],
                                     question="Which footer should the demo screens and the help pages use?")]}
        later = [{"source": "card", "question": replay["questions"][0]["question"], "text": "Use the design's",
                  "ts": "2026-11-01T00:05:00.000Z", "session": "s1"}]
        seen = {}
        out, code = checked(replay, later, said + later, "s1", runs=runs, drafts=None, topic_src=nothing,
                            before="2026-11-01T00:00:00Z", leads=True,
                            runner=lambda c, o, s, **kw: (seen.update(kw), (ran, None))[1])
        brow = last_row()
        out2, _ = checked(replay, later, said + later, "s1", runs=runs, drafts=None, topic_src=nothing,
                          runner=lambda c, o, s, **_: (ran, None))
        res.append(("--before cuts the ledger there: the card's own later answer flags without it and not with it, "
                    "and the lookup and the run log carry the cut",
                    not any("answered?" in x for x in out) and any("answered?" in x for x in out2)
                    and seen.get("before") == "2026-11-01T00:00:00.000Z" and seen.get("brief") is True
                    and tuple(seen.get("sources") or ()) == BRIEF_SOURCES
                    and brow.get("before") == "2026-11-01T00:00:00.000Z" and code == 0))
    bad = 0
    for name, good in res:
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  record: {name}")
    return bad, len(res)


def selftest_topic():
    """The topic lookup and ours to do on a planted record: a capture tool's README, a rulings register, a workspace
    map and a knowledge index in a temp folder, and a planted ledger. -> (failures, checks)."""
    res = []
    readme = """# Meeting capture

## Settled: read this before asking

- **The call's audio is the main source.** A stretch with no captions (a share minimizes the meeting window) loses
  speaker names, not speech. Never run a test call about caption drawing.
- **The vendor's own transcription** is the user's choice for each call. The cross-check uses a transcript only
  when one exists.

## 1. What is captured

| Source | What it is |
|---|---|
| The vendor's own transcript | when someone in the meeting turned on transcription (everyone sees the vendor's banner) |

Why the audio: the meeting app stops drawing its captions panel whenever its meeting window is minimized, and when
you share your screen it minimizes that window itself. The pop-out captions window is read when it is open. The
audio fills those stretches.

```
| X9 | a code block is not a passage |
```
"""
    register = """# Rulings register

| ID | Ruling | Who | When |
|---|---|---|---|
| J1 | The 11/24 one-demo test is proposed, not agreed, if the two leads agree | leads | 11/09 |
| J4 | The 11/24 builds (5 to 8 briefs, built by the builder with the kit and by the plain agent) are ours to build and have ready; nobody is asked first. Supersedes J1's "if the two leads agree" | user | 11/10 |
| 3 | an assumption row with a number for its id is not a ruling | x | y |

- **Release notes** (2026-10-05): keep them to five lines.
  They go out each Friday.
- **Platform agenda** (2026-11-09): the six platform questions (runtime, the model, the environment, where demos
  live, who pays) go to the platform team before the call.
- a plain bullet is a note, not a ruling
"""
    rows = [{"id": f"r{i}", "ts": f"2026-10-{i + 1:02d}T00:00:00.000Z", "source": "typed",
             "text": t, "session": "aaaaaaaa"} for i, t in enumerate([
                 "please fix the footer spacing on the help pages and the demo screens today",
                 "the board looks good, keep going on the other sections of the board",
                 "the footer links should move into the help menu bar on every page",
                 "check the release notes and the screens before friday",
                 "keep the demo screens light and the board sections short for now",
                 "the gallery cards need their thumbnails before the team reads them tomorrow"])]
    rows.append({"id": "r-said", "ts": "2026-10-20T00:00:00.000Z", "source": "typed", "session": "aaaaaaaa",
                 "text": "the gallery thumbnails come from the source repo screenshots, never from the design file crops"})
    rows.append({"id": "r-later", "ts": "2026-11-20T00:00:00.000Z", "source": "typed", "session": "aaaaaaaa",
                 "text": "the onboarding tour stays three steps long, with the skip button on every single step"})
    rows.append({"id": "r-pick", "ts": "2026-10-21T00:00:00.000Z", "source": "card", "session": "aaaaaaaa",
                 "question": "Which source do the gallery thumbnails come from?", "text": "Repo screenshots (Recommended)"})
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "MeetingCapture"))
        os.makedirs(os.path.join(tmp, "Work", "nested"))
        os.makedirs(os.path.join(tmp, "Empty"))
        with open(os.path.join(tmp, "MeetingCapture", "README.md"), "w", encoding="utf-8") as f:
            f.write(readme)
        with open(os.path.join(tmp, "Work", "nested", "README.md"), "w", encoding="utf-8") as f:
            f.write("# Nested\n\nA nested folder's own README.\n")
        reg = os.path.join(tmp, "rulings-register.md")
        with open(reg, "w", encoding="utf-8") as f:
            f.write(register)
        wmap = ("# Map\n\n- `MeetingCapture/` - the meeting caption capture tool and its `README.md`.\n"
                "- `Work/` - the work folder.\n  - `nested/` - a nested folder\n    that runs on.\n"
                "- `Empty/` - no README here.\n")
        systems = map_systems(wmap, tmp)
        res.append(("the map names each folder with a README, a nested one under its parent bullet, and skips one without",
                    [s["name"] for s in systems] == ["Meeting Capture", "nested"]
                    and systems[0]["docs"] == [os.path.join(tmp, "MeetingCapture", "README.md")]
                    and "runs on" in systems[1]["desc"]))
        rp = ruling_passages(reg)
        ids = [p["id"] for p in rp]
        res.append(("ruling rows: an id-keyed row and a bold-led bullet with its continuation; a superseded row, a "
                    "number-keyed row and a plain bullet are not rulings",
                    ids == ["J4", "", ""] and "each Friday" in rp[1]["text"] and rp[0]["cite"].endswith(":6 (row J4)")))
        blocks = md_blocks(readme)
        res.append(("a doc splits into bullets, table rows and paragraphs under their headings; separators and code "
                    "fences are left out",
                    not any("X9" in b or "|---|" in b for _, _, b in blocks)
                    and any(h.startswith("1. What") and b.startswith("Why the audio") for _, h, b in blocks)))
        js = os.path.join(tmp, "rulings.json")
        with open(js, "w", encoding="utf-8") as f:
            json.dump({"rulings": [{"id": "accordion", "topic": "Accordions", "ruling": "ship all collapsed"},
                                   {"id": "old", "ruling": "gone", "status": "retired"}]}, f)
        jp = ruling_passages(js)
        res.append(("a JSON rulings file gives each live entry by its text, a retired one left out",
                    [p["id"] for p in jp] == ["accordion"] and "collapsed" in jp[0]["text"]))
        src = {"words": words_passages(rows), "rulings": rp, "systems": systems,
               "read": lambda p: doc_passages(p), "status": {"rulings": "ran"}}
        idf = topic_idf(rows)
        res.append(("stems: captions, caption and captioning share one, and so do minimized and minimizes",
                    len({stem(w) for w in ("captions", "caption", "captioning")}) == 1
                    and stem("minimized") == stem("minimizes")))
        res.append(("typed words: a pick of an option and a paste are not the user's words",
                    "r-pick" not in " ".join(p["cite"] for p in src["words"])
                    and typed_text("<pasted_content id='1'>the vendor note</pasted_content> mine\n> quoted") .strip() == "mine"))

        def look(q, before=None, s=src):
            return topic_lookup({"questions": [q]}, rows, before, src=s, idf=idf)[0]
        test_call = {"header": "Test call", "question": (
            "One gap is left: when you share your screen, the meeting app minimizes its window and stops drawing "
            "captions. Its pop-out captions window may keep drawing, and only a short test call can prove it. Run a "
            "3-minute solo test call before 3:15?"),
            "options": [{"label": "I'll run it by 3:15 (Recommended)"}, {"label": "Skip it today"}]}
        t = look(test_call)
        res.append(("known-bad: a test call the capture tool's README settles is RECORD MAY ANSWER, citing the README",
                    bool(t["flag"]) and t["flag"]["kind"] == "doc" and "MeetingCapture/README.md" in t["flag"]["cite"]
                    and not t["outward"]))
        transcript = {"header": "Transcript", "question": (
            "The vendor saves its own transcript of the call only if someone turns on transcription, and then everyone "
            "sees a banner. Your meeting capture would use it to cross-check speakers. Start it for this call?"),
            "options": [{"label": "Leave it off (Recommended)"}, {"label": "I'll start transcription"}]}
        t = look(transcript)
        res.append(("known-good: starting a transcript everyone sees is outward, the README alone doesn't decide it, "
                    "and its user's-choice bullet prints as yours",
                    not t["flag"] and t["outward"] and t["yours"] and "user's choice" in t["yours"]["excerpt"]))
        ask = {"header": "11/24 ask", "question": (
            "The 11/24 ask to the two leads is drafted: builds from 5 to 8 briefs, each built by the builder with the "
            "kit and by the plain agent. Send it?"),
            "options": [{"label": "You send it today (Recommended)", "preview": (
                "Hi both! For 11/24, could we show you builds from 5 to 8 briefs? Does 11/24 still work for you?")},
                {"label": "Hold", "description": "Nothing goes out."}]}
        t = look(ask)
        res.append(("known-bad: a send the ruling row J4 settles is RECORD MAY ANSWER citing J4 at the outward bar, "
                    "and the row J4 supersedes (J1) is never cited",
                    bool(t["flag"]) and t["flag"]["kind"] == "ruling" and "(row J4)" in t["flag"]["cite"]
                    and t["flag"]["score"] >= OUTWARD_BAR and not any("J1" in h["cite"] for h in t["ruling"])))
        flags = check({"questions": [ask]}, [], topics=[t])
        res.append(("the flags read RECORD MAY ANSWER and OURS TO DO on that question, the drafted preview named",
                    [k for _, k, _ in flags] == ["may answer", "ours to do"]
                    and flags[0][2].startswith("RECORD MAY ANSWER: ") and "could we show" in flags[1][2]
                    and "preview" in flags[1][2]))
        tell = {"header": "Vendor post", "question": (
            "When you share your screen the meeting app minimizes its window and stops drawing captions, while its "
            "pop-out captions window keeps drawing. Post this to the vendor's forum?"),
            "options": [{"label": "Post it (Recommended)"}, {"label": "Hold"}]}
        t = look(tell)
        res.append(("known-good: an outward post on a subject the README covers isn't decided by the README",
                    not t["flag"] and t["outward"] and t["doc"] and t["doc"][0]["score"] >= TOPIC_BAR))
        board = {"header": "Board cards", "question": (
            "Her six cards miss three platform questions the timeline needs: unattended builds, the approved model and "
            "who pays, and the staging environment. Add those to her open questions board?"),
            "options": [{"label": "Add 3 cards (Recommended)", "preview": (
                "Can the builder run builds on a server with nobody at the keyboard? Who owns that policy?")},
                {"label": "Don't add any"}]}
        t = look(board)
        res.append(("known-good: an outward write to a teammate's board flags neither, though a ruling row on the "
                    "platform questions speaks to it under the outward bar and its preview asks a platform team "
                    "whether it can build",
                    not t["flag"] and t["outward"] and not check({"questions": [board]}, [], topics=[t])
                    and t["ruling"] and TOPIC_SHARED <= len(t["ruling"][0]["shared"]) and t["ruling"][0]["score"] < OUTWARD_BAR))
        icon = {"header": "Icon", "question": "Which colour should the meeting capture tool's menu bar icon use?",
                "options": [{"label": "Grey"}, {"label": "Red"}]}
        t = look(icon)
        res.append(("known-good: a question on a named system that its README only touches flags nothing",
                    not t["flag"] and t["systems"] == ["Meeting Capture"] and t["doc"]))
        thumbs = {"header": "Thumbnails", "question": "Where should the gallery thumbnails come from: the source repo "
                                                      "screenshots or the design file crops?",
                  "options": [{"label": "Repo screenshots"}, {"label": "Design crops"}]}
        t = look(thumbs)
        res.append(("known-bad: what the user typed settles it: RECORD MAY ANSWER citing their ledger row",
                    bool(t["flag"]) and t["flag"]["kind"] == "your words" and "r-said" in t["flag"]["cite"]))
        tour = {"header": "Tour", "question": "How many steps should the onboarding tour keep, and should every "
                                              "single step show the skip button?",
                "options": [{"label": "Three, skip on each"}, {"label": "Five"}]}
        res.append(("--before: a message typed after the cut is not read; the same message before it flags",
                    not look(tour, "2026-11-01T00:00:00.000Z",
                             dict(src, words=words_passages(rows, "2026-11-01T00:00:00.000Z")))["flag"]
                    and bool(look(tour)["flag"])))
        footer = {"header": "Footer", "question": "Which footer should the pricing page use?",
                  "options": [{"label": "A"}, {"label": "B"}]}
        res.append(("known-good: a question no record speaks to flags nothing", not look(footer)["flag"]))
        tt = topic_terms(test_call, look(test_call))
        res.append(("the recall terms: the header as one phrase, then the words the best passage shares, a long stem "
                    "as its stem", tt[0] == "test call" and "call" not in tt and "minimiz" in tt and len(tt) <= RECORD_TERMS))
        lines = topic_lines([look(test_call), look(transcript)])
        res.append(("each question prints its topic, the best of each kind with score and link, and a yours line",
                    lines[0][1].startswith("topic ") and any(n == 1 and ln.lstrip().startswith("doc ") and "README.md:" in ln
                                                            for n, ln in lines)
                    and any(n == 2 and ln.lstrip().startswith("yours") for n, ln in lines)))
        kbd = os.path.join(tmp, "knowledge")
        os.makedirs(kbd)
        with open(os.path.join(kbd, "index.md"), "w", encoding="utf-8") as f:
            f.write("# Knowledge\n\n- [Meeting capture](meeting.md): the caption capture tool. Canonical: "
                    "`MeetingCapture/`. Name traps: none.\n  - alias: recorder = capture tool  (since 2026-01-01, x)\n")
        with open(os.path.join(kbd, "meeting.md"), "w", encoding="utf-8") as f:
            f.write("# Meeting\n\n## Entries\n\n### meeting.audio\n- id: k-0001; status: live; written: 2026-11-03\n"
                    "- question: \"Is the audio the main source?\" (phrased by the writer)\n"
                    "- answer: Yes, since 11/03: captions add names only.\n- source: file `MeetingCapture/README.md`\n")
        import kb
        saved = dict(kb.CONFIG)
        try:
            kb.CONFIG["dir"], kb.CONFIG["root"] = kbd, tmp
            ks, entries, why = kb_systems()
        finally:
            kb.CONFIG.clear()
            kb.CONFIG.update(saved)
        res.append(("the knowledge index: a body's page and canonical folder's README are its docs, its alias widens its "
                    "name, and its entries are ruling passages",
                    not why and ks and ks[0]["docs"] == [os.path.join(kbd, "meeting.md"),
                                                         os.path.join(tmp, "MeetingCapture", "README.md")]
                    and "recorder" in ks[0]["name"] and entries and "k-0001" in entries[0]["cite"]))
    # Ours to do without a lookup: the question asks whether to ask leave, or a quoted message asks it; a note handing
    # someone facts, and a send with no drafted ask, don't.
    leave_q = {"question": "Should I ask Ana whether we may build the two demos before the review?",
               "options": [{"label": "Ask her"}, {"label": "Don't"}]}
    quoted = {"question": "Send Bo this: \"Would you like us to set up the demo for your team next week?\"",
              "options": [{"label": "Send it"}, {"label": "Hold"}]}
    note = {"question": "A note to Bo is drafted: 12 items have no owner, and the legal check is due 11/24. Send it "
                        "before planning?", "options": [{"label": "You send it today"}, {"label": "Hold"}]}
    res.append(("ours to do: asking whether to ask leave, and a quoted message asking it, flag; a note of facts doesn't",
                bool(ours_to_do(leave_q)) and ours_to_do(leave_q)[1] == "the question" and bool(ours_to_do(quoted))
                and not ours_to_do(note)))
    bad = 0
    for name, good in res:
        bad += not good
        print(f"{'PASS' if good else 'FAIL'}  topic: {name}")
    return bad, len(res)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--share", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--session", help="the Claude Code session asking, as the request ledger names it "
                                      "(default $CLAUDE_CODE_SESSION_ID)")
    ap.add_argument("--leads", action="store_true", help="also recall's --brief leads under each question: about "
                                                         "100 s a card; they flag nothing")
    ap.add_argument("--no-record", action="store_true", help="a no-op, and said so: the topic lookup always runs, "
                                                             "the leads only with --leads")
    ap.add_argument("--before", help="the record as it stood before this time (UTC unless it carries an offset), "
                                     "for a replay of a card already asked")
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
        before = utc_text(a.before)
    except (OSError, ValueError) as e:
        print(f"did not run: {type(e).__name__}: {e}")
        return 2
    sid = a.session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    out, code = checked(card, past_cards(rows), rows, sid, a.no_record, before=before, leads=a.leads)
    print("\n".join(out))
    return code


if __name__ == "__main__":
    sys.exit(kit_config.run(main))
