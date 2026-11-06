#!/usr/bin/env python3
"""bare_ids.py - how many Figma node ids and ADO item ids sessions hand the user bare, against linked.

    python tools/bare_ids.py [--days 7]     one line per local day, oldest first, today last
    python tools/bare_ids.py --sample N     N random bare ids in their words, to check by eye
    python tools/bare_ids.py --selftest     a planted log: each id form counted, each decoy left out

WHY THIS EXISTS. The user opens what a session names by clicking it, so a bare 1234:5678 or #4567 is a
lookup done by hand. Asking sessions for links again and again does not hold: tools print full URLs,
and this counts, every day, whether sessions pass them on. section() gives the lines for the daily
audit digest (scheduled_audits.py's today.md).

WHAT IT COUNTS, per local day, in each main session log under ~/.claude/projects with records in
the window: the text the user reads, which is assistant text blocks, AskUserQuestion questions and
options, and the wrap-up recap and question.
  bare Figma   a node id in colon form (1234:5678, I2345:67890;3456:78901) outside a URL
  bare ADO     #1234 or #12345 outside a URL
  linked       a node-id= in a figma.com URL, and an _workitems/edit/<id> URL
Report-only: exit 0 when it ran, 2 when no log could be read. Read by hand, nearly every random bare
hit is a Figma or ADO id; the usual miss is a GitHub pull request number.

BLIND. A node id written in its URL form outside a URL (1234-5678) is not counted, since dates look
the same. An ADO id written without # ("item 4567", "ADO 4567") is not counted, and a GitHub pull
request number of 4 or 5 digits is. A slice or ratio with 3+ digits on each side (x[100:200] is left
out, "1440:900" is not) reads as a node id, and a node id right after [ is left out with the slices, an
instance path's inner ids too. Subagent and headless logs are not read, since the user doesn't read
them. Text another session relays is counted where that session writes it.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse
import datetime as dt
import glob
import json
import os
import random
import re
import sys
import tempfile

if os.path.dirname(os.path.realpath(__file__)) not in sys.path: sys.path.append(os.path.dirname(os.path.realpath(__file__)))
import ado_links  # the one #1234 pattern, shared with the doc and ADO linker

PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
URL = re.compile(r"https?://[^\s)>\]\"'`]+")
FIG = re.compile(r"(?<![\w:./=%\[;-])I?\d{3,6}:\d{2,7}(?:;\d{3,6}:\d{2,7})*(?!\w|:\d)")
ADO = ado_links.HASH_TOKEN
# A markdown link's label is clickable, so [1234:5678](<url>) counts as its URL alone.
MDLINK = re.compile(r"\[[^\]\n]*\]\((https?://[^)\s]+)\)")
FIG_LINK = re.compile(r"figma\.com/(?:design|board|file|proto)/[^\s]*?node-id=I?\d+-\d+")
ADO_LINK = re.compile(r"_workitems/edit/\d+")
CARD_TOOLS = ("AskUserQuestion", "mcp__ccd_turn__wrap_up")


def texts(rec):
    """The strings in one log record that the user reads."""
    if rec.get("type") != "assistant":
        return []
    out = []
    for c in (rec.get("message") or {}).get("content") or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "text":
            out.append(c.get("text") or "")
        elif c.get("type") == "tool_use" and c.get("name") in CARD_TOOLS:
            i = c.get("input") or {}
            out += [i.get("recap") or "", i.get("ask") or ""]
            for q in i.get("questions") or []:
                out.append(q.get("question") or "")
                out += [f"{o.get('label') or ''} {o.get('description') or ''}" for o in q.get("options") or []]
    return [t for t in out if t]


def count(text):
    """(bare Figma, bare ADO, linked Figma, linked ADO) in one string."""
    text = MDLINK.sub(lambda m: f" {m.group(1)} ", text)
    links = " ".join(URL.findall(text))
    plain = URL.sub(" ", text)
    return (len(FIG.findall(plain)), len(ADO.findall(plain)),
            len(FIG_LINK.findall(links)), len(ADO_LINK.findall(links)))


def unlinked(text):
    """[(line number, id)] for each Figma node or ADO id on a line that doesn't carry that id's URL.
    A tool's planted case runs it on what the tool printed: every line names its links itself, so
    whichever line a session copies, the link comes with it."""
    out = []
    for i, ln in enumerate(str(text).splitlines(), 1):
        ln = MDLINK.sub(lambda m: f" {m.group(1)} ", ln)
        links = " ".join(URL.findall(ln))
        plain = URL.sub(" ", ln)
        for n in FIG.findall(plain):
            d = re.escape(n.replace(":", "-")).replace(";", "(?:;|%3B)")
            if not re.search(rf"node-id={d}(?![\d;%])", links):
                out.append((i, n))
        for a in ADO.findall(plain):
            if not re.search(rf"_workitems/edit/{a[1:]}(?!\d)", links):
                out.append((i, a))
    return out


def local_day(ts):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date()
    except (AttributeError, ValueError):
        return None


def tally(days=7, now=None, projects=PROJECTS, keep=None):
    """{day: [bare fig, bare ado, linked fig, linked ado, sessions]}, logs read, logs unreadable."""
    today = (now or dt.datetime.now().astimezone()).date()
    first = today - dt.timedelta(days=days - 1)
    cut = dt.datetime.combine(first, dt.time()).astimezone().timestamp()
    per = {first + dt.timedelta(days=i): [0, 0, 0, 0, 0] for i in range(days)}
    read = bad = 0
    for f in glob.glob(os.path.join(projects, "*", "*.jsonl")):
        try:
            if os.path.getmtime(f) < cut:
                continue
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            bad += 1
            continue
        read += 1
        seen = set()
        with fh:
            for ln in fh:
                if '"assistant"' not in ln:
                    continue
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                d = local_day(rec.get("timestamp"))
                if d not in per:
                    continue
                for t in texts(rec):
                    c = count(t)
                    for k in range(4):
                        per[d][k] += c[k]
                    if keep is not None and c[0] + c[1]:
                        keep.append((d, f, t))
                    if d not in seen and any(c):
                        seen.add(d)
                        per[d][4] += 1
    return per, read, bad


def lines(per, today=None):
    out = []
    for d in sorted(per):
        bf, ba, lf, la, s = per[d]
        bare, ids = bf + ba, bf + ba + lf + la
        share = f"{100 * bare / ids:.0f}% bare" if ids else "no ids"
        out.append(f"- {d:%m-%d}{' (so far)' if d == today else ''}: {bare} bare of {ids} ids, {share} "
                   f"(Figma {bf} of {bf + lf}, ADO {ba} of {ba + la}), in {s} sessions")
    return out


def section(days=7, now=None, projects=PROJECTS):
    """Lines for the daily digest. A folder with no readable log says so; it never reads as zero."""
    try:
        per, read, bad = tally(days, now, projects)
    except Exception as e:
        return [f"- did not run ({type(e).__name__})"]
    if not read:
        return [f"- did not run: no session log under {projects} was readable ({bad} could not be opened)"]
    today = (now or dt.datetime.now().astimezone()).date()
    return lines(per, today) + ["  (ids in the text, cards and wrap-ups sessions show you, outside a URL; "
                                "tools/bare_ids.py says what it can't see)"]


def selftest():
    fails = []

    def chk(name, ok, got=""):
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"   got {got}"))
        if not ok:
            fails.append(name)

    # Planted ids only: a node id, an instance path and work-item numbers no real file or tracker is meant to hold.
    cases = [
        ("the node 1234:5678 moved", (1, 0, 0, 0)),
        ("instance I2345:67890;3456:78901 here", (1, 0, 0, 0)),
        ("see #4567 and #5678", (0, 2, 0, 0)),
        ("https://www.figma.com/design/AbCdEfGhIjKlMnOpQrStUv/Planted?node-id=1234-5678", (0, 0, 1, 0)),
        ("https://dev.azure.com/o/p/_workitems/edit/4567/", (0, 0, 0, 1)),
        ("a markdown link's text: [1234:5678](https://www.figma.com/design/K/W?node-id=1234-5678)", (0, 0, 1, 0)),
        ("a markdown link to a bare-looking label: [#4567](https://dev.azure.com/o/p/_workitems/edit/4567/)", (0, 0, 0, 1)),
        ("at 10:30, on 2026-10-29T08:00:14, port 127.0.0.1:4321, x[100:200]", (0, 0, 0, 0)),
        ("colours #9E9E9E #999 #333333 #27272a, comment #3877144741, file.py:1234", (0, 0, 0, 0)),
        ("a link with no address is bare: [#5595]( )", (0, 1, 0, 0)),
        ("node-id=1234-5678 without a host, and 1234-5678 alone", (0, 0, 0, 0)),
    ]
    for text, want in cases:
        got = count(text)
        chk(f"count {text[:60]!r} = {want}", got == want, got)

    root = tempfile.mkdtemp(prefix="bareids-")
    proj = os.path.join(root, "p")
    os.makedirs(os.path.join(proj, "sid", "subagents"))
    now = dt.datetime(2026, 10, 29, 12, 0).astimezone()
    day = lambda h: (now - dt.timedelta(hours=h)).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    recs = [
        {"type": "assistant", "timestamp": day(1), "message": {"content": [
            {"type": "text", "text": "Fixed 1234:5678 and #4567."},
            {"type": "tool_use", "name": "AskUserQuestion", "input": {"questions": [
                {"question": "Close #5678?", "options": [{"label": "Yes", "description": "closes 34567:891011"}]}]}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "echo 9999:99999 #4444"}}]}},
        {"type": "user", "timestamp": day(1), "message": {"content": [
            {"type": "tool_result", "content": "6666:77777 #3333"}]}},
        {"type": "assistant", "timestamp": day(25), "message": {"content": [
            {"type": "tool_use", "name": "mcp__ccd_turn__wrap_up", "input": {
                "recap": "https://dev.azure.com/o/p/_workitems/edit/4567/ done", "ask": "Post on 1234:5678?"}}]}},
        {"type": "assistant", "timestamp": day(24 * 9), "message": {"content": [{"type": "text", "text": "old #6666"}]}},
    ]
    with open(os.path.join(proj, "s1.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in recs) + "\nnot json\n")
    with open(os.path.join(proj, "sid", "subagents", "a.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(recs[0]) + "\n")
    per, read, bad = tally(7, now, root)
    t, y = now.date(), now.date() - dt.timedelta(days=1)
    chk("today: text and card ids counted; Bash input, tool results and subagents not",
        per[t] == [2, 2, 0, 0, 1], per[t])
    chk("yesterday: the wrap-up's bare id and its linked one", per[y] == [1, 0, 0, 1, 1], per[y])
    chk("a record older than the window is left out", sum(sum(v[:4]) for v in per.values()) == 6, per)
    chk("one main log read, the subagent log not", read == 1, read)
    chk("lines say the share and mark today partial",
        lines(per, t)[-1] == f"- {t:%m-%d} (so far): 4 bare of 4 ids, 100% bare (Figma 2 of 2, ADO 2 of 2), in 1 sessions",
        lines(per, t)[-1])
    chk("an empty folder is did not run, never zero", section(7, now, os.path.join(root, "none"))[0].startswith("- did not run"))

    fig = "https://www.figma.com/design/K/W?node-id="
    ado = "https://dev.azure.com/o/p/_workitems/edit/"
    for text, want in [
        (f"1234:5678 'Landing'  {fig}1234-5678", []),
        (f"#4567 OK  {ado}4567/", []),
        (f"[#4567]({ado}4567/) and [1234:5678]({fig}1234-5678)", []),
        (f"I2345:67890;3456:78901  {fig}I2345-67890%3B3456-78901", []),
        (f"1234:5678 'Landing'\n{fig}1234-5678", [(1, "1234:5678")]),
        (f"1234:567 here  {fig}1234-5678", [(1, "1234:567")]),
        (f"#4567 OK parent -> #5678  {ado}4567/", [(1, "#5678")]),
        (f"#5678 cited  {ado}56780/", [(1, "#5678")]),
        ("at 10:30, port 127.0.0.1:8080, fill #333333", []),
        ("phone 23456:78901: note, and 123:45:67", [(1, "23456:78901")]),
        ("x[I3456:78901;4567:890123] is a slice, never its tail", []),
    ]:
        got = unlinked(text)
        chk(f"unlinked {text[:58]!r} = {want}", got == want, got)
    print(f"\nbare_ids selftest: {'all pass' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--sample", type=int)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    keep = [] if a.sample else None
    per, read, bad = tally(a.days, keep=keep)
    if not read:
        print(f"bare_ids: DID NOT RUN, no session log under {PROJECTS} was readable ({bad} could not be opened)")
        return 2
    if a.sample:
        for d, f, t in random.sample(keep, min(a.sample, len(keep))):
            s = URL.sub(" ", MDLINK.sub(lambda m: f" {m.group(1)} ", t))
            for m in list(FIG.finditer(s)) + list(ADO.finditer(s)):
                print(f"{d:%m-%d} {os.path.basename(f)[:8]}  ...{s[max(0, m.start() - 50):m.end() + 30]!r}")
                break
        return 0
    print(f"bare_ids: {read} session logs, last {a.days} days")
    print("\n".join(lines(per, dt.date.today())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
