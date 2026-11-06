#!/usr/bin/env python3
"""digest.py - DIGEST.md: your open requests and the questions you put off, by age, and your standing answers.

    python tools/digest.py               write <ledger dir>/DIGEST.md from the ledger
    python tools/digest.py --print       print it instead of writing it
    python tools/digest.py --selftest    a planted ledger: header, open requests, answers, line budget

Reads requests.jsonl in the ledger folder (ledger.dir in the product-os config), which ledger.py
writes; run ledger.py first. Nothing here decides a state: an open request is one ledger.py left
open, an open question is a card question you put off that no later card has answered (listed under
its id, which a later card or a triage pass names to close it), and a standing answer is one of your
decisions (or anything a ruling holds) that nothing later reversed or replaced.

This machine's open requests and questions come first, up to 40 of each, oldest first; past that the
oldest win and the rest are counted with the command that lists them. The standing answers get 28
lines, newest first. Other machines' open requests and questions (ledger.from_other: a session whose
working folder is another machine's, from logs copied here) are listed in full at the end, under
"Other machines' sessions, <first day> to <last day>", so an older item from another machine never
takes a line from this one.

RULINGS. A ruled entry is shown with its ruling from ledger.rulings. ledger.rulings_also lists globs
of other copies of the rulings file (e.g. in git worktrees): a ruling only a copy holds is "not in
the main file yet", and one no file holds reads as removed after it was written. With
rulings_also unset that second test is skipped.

Every entry is personal, so this file is for you. Nothing loads it into a session.

Exit 0 written; 2 the ledger could not be read.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

OPEN_MAX = 40            # this machine's; other machines' are listed in full at the end
QUESTION_MAX = 40
ANSWER_LINES = 28
PER_TOPIC = 3
TOOLS = os.path.dirname(os.path.abspath(__file__))


def one_line(s, n):
    """Your words on one line, verbatim except: pasted blocks, an HTML comment marker and agent text quoted
    with "> " are left out, so what shows is what you wrote."""
    s = ledger.own_words(s).replace("<", "&lt;").replace("|", "\\|")
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def when(e):
    return (e.get("ts") or "")[:10]


def age_days(e, now):
    t = ledger.parse_ts(e.get("ts") or "")
    return int((now - t).total_seconds() // 86400) if t else None


def where(e):
    """A link that opens the session in the desktop app, or its title and date when it has no app id."""
    title = one_line(e.get("title") or e["session"][:8], 60)
    if e.get("ccd"):
        return f"[{title}](claude://claude.ai/epitaxy/{e['ccd']})"
    return f"{title} ({when(e)}, session {e['session'][:8]})"


def words(e, n=170):
    """Your words. For a card: the question, then what you picked or typed."""
    if e.get("source") == "card":
        q = one_line(e.get("question") or "", 70)
        return f"card \"{q}\" → \"{one_line(e.get('text') or '', max(40, n - len(q) - 12))}\""
    return "\"" + one_line(e.get("text") or "", n) + "\""


def card_sections(memory=None):
    """{card file: (section, title)} from each memory card's `index: "<section> | <title> | ..."` line."""
    out = {}
    folders = ledger.default_memory() if memory is None else memory
    for p in [p for f in folders for p in glob.glob(os.path.join(f, "*.md"))]:
        try:
            head = open(p, encoding="utf-8").read(3000)
        except OSError:
            continue
        m = re.search(r"^index:\s*\"?([^|\"\n]+)\|([^|\"\n]+)", head, re.M)
        if m:
            out[os.path.basename(p)] = (m.group(1).strip(), m.group(2).strip())
    return out


def load_rulings(path=None):
    path = path or ledger.RULINGS
    if not path:
        return {}
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rs = d.get("rulings") if isinstance(d, dict) else d
    return {r.get("id"): r for r in rs or [] if isinstance(r, dict)}


def other_ruling_ids(patterns=None):
    """Ruling ids in the other copies of the rulings file (ledger.rulings_also), or None when unset."""
    pats = patterns if patterns is not None else ledger._cfg("rulings_also", [])
    if not pats:
        return None
    ids = set()
    for pat in pats:
        for p in glob.glob(os.path.expanduser(pat)):
            ids.update(load_rulings(p))
    return ids


def standing(rows, rulings, sections, elsewhere=None):
    """Your decisions and ruled entries, newest first, minus anything reversed or replaced later.

    elsewhere: ruling ids found in other copies of the rulings file. A ruled entry whose ruling is in
    none of them was removed after it was written, so it is not reported as waiting to land. None skips
    that test."""
    replaced = {e.get("supersedes") for e in rows if e.get("supersedes")}
    out = []
    for e in rows:
        if e.get("source") in ("chip", "spawned") or e.get("state") == "dropped":
            continue
        if not (e.get("kind") == "decision" or e.get("state") == "ruled"):
            continue
        if e["id"] in replaced or (e.get("scope") or {}).get("reversed"):
            continue
        r = rulings.get(e.get("ref")) if e.get("state") == "ruled" else None
        if r and r.get("reversed"):
            continue
        if r:
            topic, src = r.get("topic") or "Rulings", f"ruling `{r['id']}` ({ledger.RULINGS_NAME})"
        elif e.get("state") == "ruled" and elsewhere is not None and e.get("ref") not in elsewhere:
            topic, src = ("Held only in the session log",
                          f"ruling `{e.get('ref')}` was removed after it was written; the session log has the decision")
        elif e.get("state") == "ruled":
            topic, src = "Rulings", f"ruling `{e.get('ref')}` (written in another copy; not in the main file yet)"
        elif e.get("state") == "card" and e.get("ref") in sections:
            topic, src = sections[e["ref"]][0], f"card {e['ref']}"
        elif e.get("state") == "card":
            topic, src = "Memory cards", f"card {e.get('ref')}"
        elif e.get("state") == "done" and (e.get("ref") or "").startswith("edited "):
            topic, src = "Held in a commit or an edit", e["ref"]
        elif e.get("state") == "done" and e.get("ref") not in (None, "reported"):
            topic, src = "Held in a commit or an edit", f"commit {e['ref']}"
        else:
            topic, src = "Held only in the session log", "the session log"
        out.append((topic, src, e))
    out.sort(key=lambda x: x[2].get("ts") or "", reverse=True)
    return out


def render(rows, now=None, rulings=None, sections=None, ledger_path=None, elsewhere=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if rulings is None:
        rulings = load_rulings()
        elsewhere = other_ruling_ids() if elsewhere is None else elsewhere
    sections = card_sections() if sections is None else sections
    rows = list(rows)

    def open_of(kind):
        return sorted((e for e in rows if e.get("kind") == kind and e.get("state") == "open"
                       and not e.get("repeated_as")), key=lambda e: e.get("ts") or "")

    # This machine's come first, under their own caps; other machines' are listed in full at the end, so they
    # never take a line from this machine's.
    opens, asked = open_of("request"), open_of("question")
    far_opens, far_asked = [e for e in opens if ledger.from_other(e)], [e for e in asked if ledger.from_other(e)]
    opens, asked = [e for e in opens if not ledger.from_other(e)], [e for e in asked if not ledger.from_other(e)]
    far = f"other machines' sessions, {ledger.other_span(far_opens + far_asked)}"
    local = now.astimezone()
    out = [
        "<!-- Generated file: do not edit. The next run of digest.py replaces it. -->",
        "# Requests and answers",
        "",
        f"Generated {local:%Y-%m-%d %H:%M %Z} by `python {TOOLS}/digest.py`, from "
        f"{len(rows)} ledger entries (`python {TOOLS}/ledger.py` first). Personal: not for a team digest.",
        "",
        f"## Open requests from this machine ({len(opens)}, oldest first)",
        "",
    ]
    if not opens:
        out.append("None. Every request has a commit, a work item, a ruling, a card or a reply that settles it.")
    out += request_lines(opens[:OPEN_MAX], now)
    if len(opens) > OPEN_MAX:
        out.append(f"- and {len(opens) - OPEN_MAX} newer: `python {TOOLS}/ledger.py --open --source this`")
    if far_opens:
        out.append(f"- {len(far_opens)} more from the {far}: listed in full at the end")
    out += ["", f"## Open questions to you from this machine ({len(asked)}, oldest first)", "",
            "Put off on a card. Each closes when a later card or a triage pass names its id and you answer it."]
    if not asked:
        out.append("None.")
    out += question_lines(asked[:QUESTION_MAX], now)
    if len(asked) > QUESTION_MAX:
        out.append(f"- and {len(asked) - QUESTION_MAX} newer: `python {TOOLS}/ledger.py --questions --source this`")
    if far_asked:
        out.append(f"- {len(far_asked)} more from the {far}: listed in full at the end")
    out += ["", "## Standing answers (newest first, by topic)", ""]
    ans = standing(rows, rulings, sections, elsewhere)
    topics, order = {}, []
    for topic, src, e in ans:
        if topic not in topics:
            topics[topic] = []
            order.append(topic)
        topics[topic].append((src, e))
    used, shown = 0, 0
    for topic in order:            # topics in order of their newest answer; the newest 3 of each
        if used + 2 > ANSWER_LINES:
            break
        items = topics[topic]
        out.append(f"**{topic}** ({len(items)})")
        used += 1
        for src, e in items[:PER_TOPIC]:
            if used >= ANSWER_LINES:
                break
            out.append(f"- {when(e)} · {words(e, 140)} · {src}")
            used += 1
            shown += 1
    if shown < len(ans):
        out.append(f"- and {len(ans) - shown} older or in other topics: `python {TOOLS}/ledger.py` keeps them all "
                   f"in {ledger_path or os.path.join(ledger.LEDGER_DIR, 'requests.jsonl')}")
    if far_opens or far_asked:
        out += ["", f"## {far[0].upper()}{far[1:]}", "",
                "Typed in sessions on another machine, from logs copied here. Every open one is listed; a card that "
                "names its id closes it as it closes any other.",
                "", f"### Open requests ({len(far_opens)}, oldest first)", ""]
        out += request_lines(far_opens, now) or ["None."]
        out += ["", f"### Open questions to you ({len(far_asked)}, oldest first)", ""]
        out += question_lines(far_asked, now) or ["None."]
    out.append("")
    return linked("\n".join(out))


def linked(text):
    """text with each line ending in the URL of every #1234 on it (kit_config.ado_linked); unchanged when
    ado.org or ado.project is unset."""
    import kit_config
    return kit_config.ado_linked(text)


def request_lines(rows, now):
    return [f"- {'`%s` ' % ledger.rid_of(e) if ledger.rid_of(e) else ''}{when(e)} ({age_days(e, now)}d) · {where(e)} · "
            f"{words(e)}" for e in rows]


def question_lines(rows, now):
    return [f"- `{e.get('qid')}` {when(e)} ({age_days(e, now)}d) · {where(e)} · {words(e)}" for e in rows]


def write(text, path=None):
    path = path or os.path.join(ledger.LEDGER_DIR, "DIGEST.md")
    ledger.write_atomic(path, text)
    bad = open(path, encoding="utf-8").read().count(chr(0xFFFD))
    return bad


def selftest():
    results = []

    def check(label, ok):
        results.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + label)

    now = dt.datetime(2026, 10, 23, 18, 0, tzinfo=dt.timezone.utc)
    rows = [
        {"id": "5e1f00a2-planted", "ts": "2026-10-21T21:22:00Z", "session": "0830382a-x", "ccd": "local_abc", "title": "Rate limits",
         "source": "typed", "kind": "request", "state": "open", "text": "research the planted durable fix"},
        {"id": "b", "ts": "2026-10-03T03:31:00Z", "session": "4b32273c-x", "title": "Mac setup", "source": "card",
         "kind": "request", "state": "open", "text": "Later", "question": "Port the planted backup job?"},
        {"id": "c", "ts": "2026-10-22T10:00:00Z", "session": "s", "source": "typed", "kind": "request", "state": "done",
         "ref": "1234abc", "text": "fix the planted crash"},
        {"id": "d", "ts": "2026-10-23T09:00:00Z", "session": "s", "source": "card", "kind": "decision", "state": "ruled",
         "ref": "planted-rule", "text": "ship as drawn", "question": "Planted band: ship as drawn?"},
        {"id": "e", "ts": "2026-10-20T09:00:00Z", "session": "s", "source": "typed", "kind": "decision", "state": "ruled",
         "ref": "planted-reversed", "text": "badge keeps 12px"},
        {"id": "f", "ts": "2026-10-19T09:00:00Z", "session": "s", "source": "chip", "kind": "request", "state": "ruled",
         "ref": "planted-rule", "text": "Do this task here: agent words"},
        {"id": "g", "ts": "2026-10-18T09:00:00Z", "session": "s", "source": "typed", "kind": "decision", "state": "card",
         "ref": "people_planted.md", "text": "the planted owner is the design lead"},
        {"id": "h", "ts": "2026-10-14T09:00:00Z", "session": "s", "source": "typed", "kind": "request", "state": "open",
         "text": "ok let me know when both are done", "repeated_as": "i"},
        {"id": "j", "ts": "2026-10-23T06:37:00Z", "session": "s", "source": "typed", "kind": "request", "state": "open",
         "text": "<!-- reply 1 -->\n> The planted agent quote.\n\nwhere? that planted page is a mess"},
        {"id": "k", "ts": "2026-10-16T09:00:00Z", "session": "s", "source": "card", "kind": "question", "qid": "q-0a1b2c",
         "state": "open", "text": "Later", "question": "Move the planted capture store?"},
        {"id": "l", "ts": "2026-10-15T09:00:00Z", "session": "s", "source": "card", "kind": "question", "qid": "q-3d4e5f",
         "state": "answered", "ref": "card:x:0", "text": "Hold", "question": "Rotate the planted logs?"},
        {"id": "m", "ts": "2026-10-14T09:00:00Z", "session": "s", "source": "card", "kind": "question", "qid": "q-6a7b8c",
         "state": "open", "repeated_as": "k", "text": "Defer", "question": "Prune the planted cache?"},
    ]
    winw = {"worktree": "c:\\Users\\x\\Desktop"}        # a working folder on another machine
    far_rows = [{"id": "w1", "ts": "2026-06-02T09:00:00Z", "session": "far-s", "source": "typed", "kind": "request",
                 "state": "open", "text": "the planted far-machine ask", "state_refs": winw},
                {"id": "w2", "ts": "2026-06-03T09:00:00Z", "session": "far-s", "source": "card", "kind": "question",
                 "qid": "q-9c9c9c", "state": "open", "text": "Later", "question": "The planted far-machine question?",
                 "state_refs": winw}]
    rulings = {"planted-rule": {"id": "planted-rule", "topic": "Planted bands"},
               "planted-reversed": {"id": "planted-reversed", "topic": "Badges", "reversed": "2026-10-22, the user"}}
    text = render(rows, now, rulings, {"people_planted.md": ("People", "Planted")}, "/x/requests.jsonl")
    lines = text.splitlines()
    check("the generated-file header and the generator command come first",
          lines[0].startswith("<!-- Generated file") and "digest.py" in lines[3] and "ledger.py" in lines[3])
    pt = render(rows + far_rows, now, rulings, {}, "/x/requests.jsonl")
    # This machine's oldest first, then the other machines' after them, older or not.
    i_b, i_a, i_p = (pt.find(s) for s in ("Port the planted backup", "research the planted durable",
                                           "the planted far-machine ask"))
    check("this machine's open requests are listed oldest first, with their words and the id a card names, and an "
          "older request from another machine comes after them", 0 < i_b < i_a < i_p and "`5e1f00a2` " in pt)
    check("a session with an app id links into the desktop app; one without shows its title and date",
          "(claude://claude.ai/epitaxy/local_abc)" in text and "Mac setup (2026-10-03, session 4b32273c)" in text)
    check("a reply with a marker shows your words, not the marker or the agent text it quotes",
          "\"where? that planted page is a mess\"" in text and "planted agent quote" not in text)
    check("a done request is not listed, nor an earlier copy of a request typed again",
          "fix the planted crash" not in text and "let me know when both" not in text)
    check("a standing answer shows its topic, words, source and date; a reversed ruling and agent words do not",
          "**Planted bands**" in text and "ship as drawn" in text and "ruling `planted-rule`" in text
          and "2026-10-23" in text and "badge keeps" not in text and "agent words" not in text)
    check("a decision held in a memory card is listed under the card's index section",
          "**People**" in text and "card people_planted.md" in text)
    check("an open question put off is listed under its id with the question; an answered one and one a "
          "later card carries are not",
          "`q-0a1b2c` 2026-10-16" in text and "Move the planted capture store?" in text
          and "q-3d4e5f" not in text and "q-6a7b8c" not in text and "Open questions to you from this machine (1," in text)
    gone = rows + [
        {"id": "n", "ts": "2026-10-23T08:00:00Z", "session": "s", "source": "card", "kind": "decision", "state": "ruled",
         "ref": "planted-in-worktree", "text": "planted worktree answer"},
        {"id": "o", "ts": "2026-10-23T07:00:00Z", "session": "s", "source": "card", "kind": "decision", "state": "ruled",
         "ref": "planted-removed", "text": "planted removed answer"}]
    gt = render(gone, now, rulings, {}, "/x/requests.jsonl", elsewhere={"planted-in-worktree"})
    check("a ruling only another copy holds is 'not in the main file yet'; one no copy holds reads as removed",
          "ruling `planted-in-worktree` (written in another copy; not in the main file yet)" in gt
          and "ruling `planted-removed` was removed after it was written" in gt
          and "planted-removed` (written in another copy" not in gt)
    head, _, tail = pt.partition("\n## Other machines' sessions, 6/2 to 6/3\n")
    check("other machines' open request and question are listed in full at the end, under their span, each "
          "section pointing there; this machine's sections hold neither",
          tail and "### Open requests (1, oldest first)" in tail and "the planted far-machine ask" in tail
          and "### Open questions to you (1, oldest first)" in tail and "The planted far-machine question?" in tail
          and tail.find("far-machine ask") < tail.find("far-machine question") and "## Standing answers" in head
          and "far-machine" not in head
          and head.count("- 1 more from the other machines' sessions, 6/2 to 6/3: listed in full at the end") == 2
          and "## Other machines' sessions" not in text)
    many = rows + [dict(rows[0], id=f"x{i}", ts=f"2026-10-22T{i % 24:02d}:00:00Z", text=f"planted ask {i}")
                   for i in range(50)]
    many += [dict(far_rows[0], id=f"wx{i}", ts=f"2026-06-{1 + i % 28:02d}T09:00:00Z", text=f"planted far ask {i}")
             for i in range(60)]
    big = render(many, now, rulings, {}, "/x/requests.jsonl")
    here_part = big.partition("\n## Other machines' sessions,")[0].splitlines()
    check("with 53 open requests from this machine its section stops at 40 and points at the rest; the other "
          "machines' 60 are all listed after it",
          sum(l.startswith("- ") and "planted ask " in l for l in here_part) == OPEN_MAX - 2
          and any("and 13 newer: `python" in l and "ledger.py --open --source this`" in l for l in here_part)
          and len(here_part) <= OPEN_MAX + QUESTION_MAX + ANSWER_LINES
          and all(f'"planted far ask {i}"' in big for i in range(60)))
    # The known-bad: oldest first with no split, older items from another machine fill every line and push this
    # machine's out of view. More of them than either cap, all older.
    flood = rows + [dict(far_rows[0], id=f"wy{i}", ts=f"2026-05-{1 + i % 28:02d}T09:00:00Z", text=f"planted flood {i}")
                    for i in range(OPEN_MAX + 10)]
    flood += [dict(far_rows[1], id=f"wq{i}", qid=f"q-far{i:03d}", ts=f"2026-05-{1 + i % 28:02d}T10:00:00Z")
              for i in range(QUESTION_MAX + 10)]
    flood += [dict(rows[9], id=f"mq{i}", qid=f"q-here{i:02d}", ts=f"2026-10-2{i}T09:00:00Z",
                   question=f"Planted local question {i}?") for i in range(3)]
    fl = render(flood, now, rulings, {}, "/x/requests.jsonl")
    fl_here = fl.partition("\n## Other machines' sessions,")[0]
    here_items = ["`5e1f00a2`", "Port the planted backup job", "where? that planted page is a mess", "`q-0a1b2c`"] + [
        f"`q-here{i:02d}`" for i in range(3)]
    check("no item from this machine is hidden behind other machines' items: with more of theirs than either cap, "
          "all older, every local item is listed before their section and no local section counts any as newer",
          all(m in fl_here for m in here_items) and " newer: `python" not in fl_here and "planted flood" not in fl_here
          and all(f'"planted flood {i}"' in fl for i in range(OPEN_MAX + 10)))
    import bare_ids, kit_config
    cites = [dict(rows[0], id="ado1", text="close #2840 when the header ships")]
    kept_ado, kit_config.ado = kit_config.ado, lambda: ("https://dev.azure.com/Org", "My Project")
    try:
        cited = render(cites, now, rulings, {}, "/x/requests.jsonl")
        g, kept_linked = globals(), linked
        g["linked"] = lambda t: t
        try:
            bare = render(cites, now, rulings, {}, "/x/requests.jsonl")
        finally:
            g["linked"] = kept_linked
    finally:
        kit_config.ado = kept_ado
    line = next((ln for ln in cited.splitlines() if "#2840" in ln), "")
    check("a request that cites #2840 ends its line with the item's link",
          line.endswith("/_workitems/edit/2840/") and not bare_ids.unlinked(cited))
    check("planted break: rendered without links, the same request names #2840 bare",
          [i for _, i in bare_ids.unlinked(bare)] == ["#2840"])
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "DIGEST.md")
        bad = write(text + "\nem dash — kept\n", p)
        check("the file is written whole and its non-ASCII survives (0 U+FFFD)",
              bad == 0 and open(p, encoding="utf-8").read().endswith("em dash — kept\n"))
    print(f"selftest: {sum(results)} of {len(results)} checks passed")
    return 0 if all(results) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="digest.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", action="store_true", help="print instead of writing DIGEST.md")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir", default=ledger.LEDGER_DIR, help=f"ledger folder (default {ledger.LEDGER_DIR})")
    a = ap.parse_args(argv)
    if a.selftest:
        return __import__("kit_config").run_isolated(selftest)
    path = os.path.join(a.dir, "requests.jsonl")
    if not os.path.isfile(path):
        print(f"digest: no ledger at {path}; run ledger.py first", file=sys.stderr)
        return 2
    rows = ledger.load_jsonl(path).values()
    text = render(rows, ledger_path=path)
    if a.print:
        print(text)
        return 0
    out = os.path.join(a.dir, "DIGEST.md")
    bad = write(text, out)
    print(f"digest: {len(text.splitlines())} lines, {bad} U+FFFD. Written {out}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
