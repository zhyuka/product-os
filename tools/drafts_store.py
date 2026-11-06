#!/usr/bin/env python3
"""drafts_store.py - keep a drafts file of Figma comments true without anyone tending it.

    list [<drafts.md>]      the open drafts: kind, target, length, heading
    stale [--figma] [--json F] [<file> ...]   test every hold in the drafts file and the outbound file, and
                                              their shape
    stale --structure [<file> ...]            the shape rules only, offline but for a NEW draft that links a
                                              comment id, whose file's comments the own-open rule reads
    selftest                planted cases on a temporary file, no network

THE FILE. A markdown file of comments drafted for Figma and not yet posted: each draft is a `### `
heading naming its target ("NEW on ... <node id in backticks>" or `EDIT your own comment [<comment id>](...)`)
with the text to post as `> ` quoted lines; a `## Cut: do not re-raise` table lists items decided
against. Its path is $FIGMA_DRAFTS, else `figma.drafts` in the product-os config. With neither,
every function here does nothing and refuses nothing.

WHY. A drafts file whose rule is "whoever posts a draft deletes it" is never tended: posted drafts
and notes about them pile up, and a "do not re-raise" table is enforced only by whoever reads it.

WHAT IT DOES. figma_post.py new and reply, and figma_attach.py edit, call remove_posted() once the
API has the comment: the one draft block whose quoted text is the posted text (or, for an EDIT
draft, whose heading names the edited comment, bare or in backticks, and whose text matches or whose
quoted paragraphs the new text holds, EDIT_HELD characters or more in all: an EDIT draft often
quotes only the lines it adds) leaves the file. A batch posts its new and reply items through the
same post() and its edit items through figma_attach.py's same check, so a batch removes its drafts
too. It removes nothing when no block matches, or when two do. figma_post.py new calls cut_refusal() before
posting, with the post's file key: a node a Cut row names is refused in the file the row's figma.com URL
names until that row is deleted, which is the deliberate way to raise a cut item again. Node ids are per
file, so the same id in another file passes. A node-id row with no URL refuses that id in every file, and
its refusal says to add the URL rather than delete the row. Writes are atomic (temp file, fsync, replace) and read the
file just before writing, because other sessions edit it too.

A draft reworded at post time beyond the match (0.95 for a NEW draft on the same node, 0.8 for an
EDIT draft of the same comment) stays, and the post names the drafts it kept on that target so the
session deletes the right one by hand.

A quote's lines are wrapped for the file, and Figma keeps every line break, so a quote copied as
a comment's text posts with a break every line. figma_post.py new and reply, and figma_attach.py
edit, refuse such text (wrapped_refusal()); text_of() joins a quote back into one line per paragraph, keeping list items,
blank lines and lines that end in a link or a colon.

STALE. A held item reported as held and never checked again stays "held" long after its reason is
gone. So each hold names what releases it, right after "held until": a request-ledger question
(q-xxxxxx, ledger.py), an ADO item (#N, or "#N has an owner"), the draft "<words of its heading>",
commit <sha> [on <branch>] in drafts.repo (default: the folder you run in; the branch defaults to
drafts.branch), or a date (YYYY-MM-DD). A section note, one paragraph opening "Held" before a
section's first draft, holds each draft in it that says "held with the section"; a status with "by
YYYY-MM-DD" is a deadline, held or not. `stale` sorts every hold into released (the question
answered, the item Closed, Resolved or Done or, with "has an owner", assigned; the draft gone; the
commit on the branch), target gone (no such question, item or commit), deadline passed (the date has
come), untestable (no release a tool can test: it goes to the user as a question, and the question's
id becomes the release) or still held, and prints N of M. A release it could not read (no ADO_PAT,
a git error, no branch named or configured) is not checked, never held. Then the shape rules that let
junk pile up: text before a section's first draft other than its hold note, a heading that says moot,
cut, withdrawn or dropped, a "draft below this heading was cut" placeholder, a block in the drafts
file that says it is not a comment, under a section naming a file in figma.new_thread_files a
drafted post command that carries an override flag (--new-thread, --new-cause and the rest: written
ahead, it hides the refusal that names the open thread the note folds into), a Cut row that names a
node id and no figma.com URL, and a NEW draft that links an open root comment of the token owner's,
which figma_post's own-open rule would refuse (edit that comment instead; Figma's comments are read
only for a NEW draft that links a comment id, and a read that fails is listed as did not run). With
--figma it lists the Cut rows whose every node id is gone from the row's own file (for a row with no
URL, from every file read), and removes none. Exit 1 when anything is to clear or ask about, else 2
when something was not checked, else 0.

PRINTED LINES. `list` and `stale` end each line they print with the link of every work item (#1234)
on it, and of every node id on it when the file is known: from the draft's `## ` section heading, or
from a figma.com URL in a Cut cell. Anywhere else a node id stays bare, since a link into the wrong
file is worse than none. A heading is cut at 80 characters and a Cut cell at 100, with a markdown
link turned into its label first and a word the cut splits dropped, so no half URL or half id is
left. The files and the JSON `stale --json` writes are unchanged.

The outbound file holds messages to people waiting to be sent, in the same `### ` shape, with "NOT
SENT" before each status. Its path is $OUTBOUND_DRAFTS, else drafts.outbound in the config.

BLIND TO a draft posted on a node other than the one its heading names, and to Cut rows that name
no node id (a topic only). A Cut row's hyphen id (1234-5678) is not matched, reply and edit never read
the Cut table, and an unreadable drafts file lets every post through. A live item overtaken by events
with no hold or date in its heading reads as live.
"""
import difflib, os, re, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
try:
    import kit_config
except ImportError:
    kit_config = None


def drafts_path():
    """$FIGMA_DRAFTS, else figma.drafts from the config, else None (not configured)."""
    p = os.environ.get("FIGMA_DRAFTS") or (kit_config.get("figma", "drafts") if kit_config else None)
    return os.path.expanduser(p) if p else None


LABEL = "before and after:"
MATCH = 0.95        # a NEW draft against the posted text, same node
EDIT_MATCH = 0.8    # an EDIT draft against the posted text, same comment id
EDIT_HELD = 40      # characters an EDIT draft's quote needs before "the new text holds it" counts
CUT = "## Cut: do not re-raise"


def norm(s):
    """Text as the API and the file both write it: straight quotes, x for the times sign, one space,
    lower case, and no closing picture label (the post adds it)."""
    s = (s or "").replace("×", "x").replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s[: -len(LABEL)].rstrip() if s.endswith(LABEL) else s


def blocks(text):
    """Each draft: a '### ' heading up to the next heading of level 2 or 3. Its quoted lines ('> '),
    the comment id an EDIT heading links to, and the node id a NEW heading names."""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
    out = []
    for i in starts:
        j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith(("### ", "## "))), len(lines))
        body = lines[i:j]
        head = body[0]
        # A bare ">" is a blank line inside the quote, the break between two paragraphs. Skipped, it
        # would run every paragraph of a quote into one line in text_of().
        quote = "\n".join(ln[2:] if ln.startswith("> ") else "" for ln in body
                          if ln.startswith("> ") or ln.rstrip() == ">")
        cid = re.search(r"EDIT your own comment \[`?(\d{9,})`?\]", head)   # the id bare or in backticks, as NEW's node
        node = re.search(r"NEW on [^`]*`([\d:;I]+)`", head)
        out.append({"first": i, "end": j, "head": head[4:], "quote": quote,
                    "comment": cid.group(1) if cid else None, "node": node.group(1) if node else None})
    return out


def _matches(b, posted, comment_id, node_id):
    if not b["quote"]:
        return False
    a, p = norm(b["quote"]), norm(posted)
    if a == p:
        return True
    ratio = difflib.SequenceMatcher(None, a, p).ratio()
    # An EDIT draft names the one comment it edits, so a reworded post still consumes it. Several NEW
    # drafts can sit on one node, so those need a near-exact match.
    if comment_id and b["comment"] == str(comment_id):
        # An EDIT draft often quotes only the lines it adds, so it is posted too when the new text holds each of
        # its paragraphs, EDIT_HELD characters or more in all.
        paras = [x for x in (norm(y) for y in b["quote"].split("\n\n")) if x]
        return ratio >= EDIT_MATCH or (sum(map(len, paras)) >= EDIT_HELD and all(x in p for x in paras))
    return bool(node_id and b["node"] == node_id) and ratio >= MATCH


def _write(path, text):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def post_blocks(posted, node_id, path=None):
    """The whole lines of each NEW draft block a post of `posted` on node_id would remove (_matches), for
    figma_post's own-open rule: a draft's link to a comment can sit in its notes, not its quoted text. [] when
    no drafts file is configured; raises OSError when the configured one can't be read."""
    path = path or drafts_path()
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    return ["\n".join(lines[b["first"]:b["end"]]) for b in blocks(text)
            if b["node"] and _matches(b, posted, None, node_id)]


def remove_posted(posted, comment_id=None, node_id=None, path=None):
    """Remove the one draft that was just posted. Returns a line to print, or None when the file is
    missing or holds no draft for this node or comment."""
    path = path or drafts_path()
    if not path:
        return None
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    hits = [b for b in blocks(text) if _matches(b, posted, comment_id, node_id)]
    if not hits:
        near = [b for b in blocks(text)
                if (comment_id and b["comment"] == str(comment_id)) or (node_id and b["node"] == node_id)]
        if near:   # a draft on this target whose text differs: reworded before posting, or another ask
            return (f"  drafts.md: the posted text matches none of the {len(near)} drafts on this target, "
                    "so none was removed; if one was reworded and posted, delete its block: "
                    + "; ".join(h["head"][:60] for h in near))
        return None
    if len(hits) > 1:
        return (f"  drafts.md: {len(hits)} drafts match the posted text, so none was removed: "
                + "; ".join(h["head"][:60] for h in hits))
    lines = text.split("\n")
    b = hits[0]
    _write(path, "\n".join(lines[: b["first"]] + lines[b["end"]:]))
    return f"  drafts.md: removed the posted draft \"{b['head'][:80]}\""


# A line that starts a list item: an intended break. Any other break inside a paragraph is the file's
# wrapping, unless the line before ends with a URL or a colon.
LIST_ITEM = re.compile(r"[ \t]*(?:\d+[.)]|[*•\-])[ \t]")


def wrapped_lines(text):
    """The line breaks inside a paragraph that look like a quote's wrapping, as (end of line, start of
    next) pairs. Text copied from a wrapped quote in the drafts file posts with a break every line."""
    out = []
    for para in re.split(r"\n[ \t]*\n", text or ""):
        lines = para.split("\n")
        for a, b in zip(lines, lines[1:]):
            if LIST_ITEM.match(b) or re.search(r"https?://\S+$", a.rstrip()) or a.rstrip().endswith(":"):
                continue
            out.append((a.rstrip()[-30:], b.strip()[:30]))
    return out


def wrapped_refusal(text):
    """Refusal text or None, for a post or an edit."""
    w = wrapped_lines(text)
    if not w:
        return None
    return (f"REFUSED: the text breaks {len(w)} line(s) mid-paragraph, as a wrapped quote in the drafts file does, "
            f"for one: \"...{w[0][0]}\" / \"{w[0][1]}...\". Figma keeps each break. Build the text with "
            "drafts_store.text_of(), or join the lines; an intended break is a list item or a blank line.")


def text_of(quote):
    """A draft's quote as the comment's text: the file's wrapping joined back into one line per paragraph,
    list items and blank lines kept."""
    paras = []
    for para in re.split(r"\n[ \t]*\n", (quote or "").strip()):
        lines, out = para.split("\n"), []
        for ln in lines:
            if out and not LIST_ITEM.match(ln) and not re.search(r"https?://\S+$", out[-1].rstrip()) \
                    and not out[-1].rstrip().endswith(":"):
                out[-1] = out[-1].rstrip() + " " + ln.strip()
            else:
                out.append(ln.rstrip())
        paras.append("\n".join(out))
    return "\n\n".join(paras)


def cut_table(text):
    """The Cut table's rows: {"cell": the item cell, "ids": node ids like 1234:5678 and thread ids in it,
    "nodes": the node ids alone, "file": the key of the first figma.com URL in the cell or None, "line": its
    1-based line}. Node ids are per file, so a row's file is the one its URL names."""
    if CUT not in text:
        return []
    at = text.index(CUT)
    sec = text[at:]
    nxt = sec.find("\n## ", len(CUT))
    sec = sec if nxt < 0 else sec[:nxt]
    first = text[:at].count("\n") + 1
    rows = []
    for k, ln in enumerate(sec.split("\n")):
        if not ln.startswith("|") or ln.startswith(("| Item", "|---")):
            continue
        cell = ln.split("|")[1]
        # A node id's first part can be one digit (a file's early layers, such as 8:4345). A time (12:45) has two
        # digits after its colon, so it is still not read as one.
        ids = set(re.findall(r"(?<![\d-])(\d{1,6}:\d{3,7})(?![\d])", cell)) | set(re.findall(r"\b(\d{10})\b", cell))
        key = URL_KEY.search(cell)
        rows.append({"cell": cell.strip(), "ids": ids, "nodes": {i for i in ids if ":" in i},
                     "file": key.group(1) if key else None, "line": first + k})
    return rows


def cut_rows(text):
    """The Cut table's rows as (item cell, ids in it): node ids like 1234:5678 and thread ids."""
    return [(r["cell"], r["ids"]) for r in cut_table(text)]


def cut_refusal(node_id, file_key=None, path=None):
    """Refusal text when a Cut row names node_id in file_key's file, else None. A row with a figma.com URL
    refuses only in the file it names, since the same id in another file is another node; a node-id row with
    no URL refuses node_id in every file, and says to add the URL rather than delete the row. file_key None:
    any file."""
    path = path or drafts_path()
    if not path:
        return None
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    for r in cut_table(text):
        if node_id not in r["ids"] or (r["file"] and file_key and r["file"] != file_key):
            continue
        said = f"REFUSED: {node_id} is in drafts.md's \"Cut: do not re-raise\" table ({clip(r['cell'], 90)}). "
        if r["file"]:
            return said + "To raise it again on purpose, delete that row first."
        return (said + "That row names no Figma file, so it refuses this id in every file. If the row is about "
                "a node in another file, add that node's figma.com URL to the row; don't delete it. To raise "
                "this one again on purpose, delete the row.")
    return None


# ---------------------------------------------------------------- stale: holds and the files' structure
TOOLS = os.path.dirname(os.path.realpath(__file__))
HOLD = re.compile(r"\b(?:held|holds?|holding|waiting|waits)\b|\bmatters only\b", re.I)
UNTIL = re.compile(r"\bheld until\s+(.*)", re.I | re.S)
WITH_SECTION = re.compile(r"\bheld with the section\b", re.I)
BY_DATE = re.compile(r"\bby (\d{4}-\d{2}-\d{2})\b")
MOOT = re.compile(r"\b(?:moot|cut|withdrawn|dropped)\b", re.I)
PLACEHOLDER = re.compile(r"\bdraft below this heading was cut\b", re.I)
NOT_COMMENT = re.compile(r"\bnot a (?:figma )?comment\b", re.I)
FILE_KEY = re.compile(r"`[A-Za-z0-9]{22}`")
URL_KEY = re.compile(r"figma\.com/(?:design|board|file)/([A-Za-z0-9]{22})")
MDLINK = re.compile(r"\[([^\]]*)\]\(https?://[^)\s]+\)")


def clip(s, n):
    """s cut to n characters for a printed line. A markdown link becomes its label first, so no half URL is
    left, and a word the cut splits is dropped, so no half id is left to link."""
    s = MDLINK.sub(r"\1", s)
    if len(s) <= n:
        return s
    return s[:n] if s[n].isspace() else s[:n].rsplit(" ", 1)[0]


def key_at(text, line):
    """The Figma file key the '## ' section holding 1-based `line` names in its heading, else None."""
    for s in sections(text or ""):
        if s["line"] < line <= s["end"]:
            m = FILE_KEY.search(s["head"])
            return m.group(0).strip("`") if m else None
    return None


def shown(text, key=None):
    """text as printed: each line ending in the link of every #1234 on it (kit_config.ado_linked, which leaves it
    as it is when ado.org or ado.project is unset) and, when `key` names the file, of every node id on it
    (figma_comments.linked). With no key a node id stays bare, since a link into the wrong file is worse than
    none. Only printed lines: the drafts files and the JSON stale writes stay as they are."""
    if key:
        import figma_comments
        text = figma_comments.linked(key, text)
    return kit_config.ado_linked(text) if kit_config else text


RELEASES = (    # what may follow "held until", in this order; anything else is untestable
    ("question", re.compile(r"(q-[0-9a-f]{6})\b")),
    # an id written bare or as a link to its item, [#1234](<url>), the way docs write them
    ("ado", re.compile(r"(?:ADO\s+)?\[?#(\d{3,6})\b(?:\]\([^)\s]*\))?( has an owner)?", re.I)),
    ("draft", re.compile(r'the draft "([^"]{8,})"')),
    ("commit", re.compile(r"commit `?([0-9a-f]{7,40})`?(?: (?:is )?on `?([\w./-]+?)`?)?(?=[\s.,;:)]|$)")),
    ("date", re.compile(r"(?:by )?(\d{4}-\d{2}-\d{2})\b")),
)
VERDICTS = ("released", "target gone", "deadline passed", "untestable", "not checked", "held")


class NotChecked(Exception):
    """A release that could not be read (no ADO_PAT, a git or ledger error): never read as still held."""


def _cfg(*keys):
    return kit_config.get(*keys) if kit_config else None


def is_drafts_file(path):
    """The configured drafts file, or a file named like one (drafts.md, not outbound-drafts.md)."""
    mine = drafts_path()
    name = os.path.basename(path)
    return bool(mine and os.path.abspath(path) == os.path.abspath(mine)) or \
        (name.endswith("drafts.md") and not name.endswith("outbound-drafts.md"))


def outbound_path():
    """$OUTBOUND_DRAFTS, else drafts.outbound from the config, else None (not configured)."""
    p = os.environ.get("OUTBOUND_DRAFTS") or _cfg("drafts", "outbound")
    return os.path.expanduser(p) if p else None


def status_of(head):
    """The part of a heading after its subject: after NOT SENT (the outbound file), after Last reviewed:
    or the last ' · ' (the drafts file), else the whole heading."""
    for mark in ("NOT SENT", "Last reviewed:"):
        if mark in head:
            return head[head.index(mark) + len(mark):]
    return head.rsplit(" · ", 1)[-1] if " · " in head else head


def release_of(text):
    """(kind, value) for the release a hold names right after "held until", or ("untestable", words)."""
    m = UNTIL.search(text)
    if not m:
        return "untestable", "names no release (no \"held until ...\")"
    after = m.group(1).strip()
    for kind, rx in RELEASES:
        r = rx.match(after)
        if r:
            return kind, r.groups() if kind in ("ado", "commit") else r.group(1)
    return "untestable", after[:80]


def sections(text):
    """Each '## ' section: its heading line, where its first '### ' block starts (or its end), and its end."""
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    out = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        first = next((k for k in range(i + 1, end) if lines[k].startswith("### ")), end)
        out.append({"line": i, "head": lines[i][3:], "first": first, "end": end})
    return out


def paragraphs(lines, start, end):
    """(first line, text) of each paragraph in lines[start:end]; a fenced code block is one paragraph."""
    out, cur, at, fence = [], [], None, False
    for k in range(start, end):
        ln = lines[k]
        if ln.strip().startswith("```"):
            fence = not fence
        if not ln.strip() and not fence:
            if cur:
                out.append((at, "\n".join(cur)))
            cur, at = [], None
            continue
        at = k if at is None else at
        cur.append(ln)
    if cur:
        out.append((at, "\n".join(cur)))
    return out


def holds(text, name):
    """Every hold in one file: [{file, line, head, kind, value}]. A block holds when its status says held or
    waiting; a section note (one paragraph opening "Held") holds every block that says "held with the
    section"; a status with "by YYYY-MM-DD" is a deadline, held or not."""
    lines = text.split("\n")
    out, notes = [], {}
    for s in sections(text):
        paras = paragraphs(lines, s["line"] + 1, s["first"])
        if len(paras) == 1 and paras[0][1].lstrip().startswith("Held"):
            kind, value = release_of(paras[0][1])
            notes[s["line"]] = len(out)
            out.append({"file": name, "line": paras[0][0] + 1, "head": f"section note under \"{s['head'][:60]}\"",
                        "kind": kind, "value": value})
    owner = lambda i: max((s["line"] for s in sections(text) if s["line"] < i), default=None)
    for b in blocks(text):
        st = status_of(b["head"])
        hold = {"file": name, "line": b["first"] + 1, "head": b["head"]}
        if WITH_SECTION.search(st):
            sec = owner(b["first"])
            if sec in notes:
                note = out[notes[sec]]
                out.append(dict(hold, kind=note["kind"], value=note["value"], via=note["line"]))
            else:
                out.append(dict(hold, kind="untestable", value="held with a section that has no \"Held\" note"))
        elif HOLD.search(st) or UNTIL.search(st):
            kind, value = release_of(st)
            out.append(dict(hold, kind=kind, value=value))
        elif BY_DATE.search(st):
            out.append(dict(hold, kind="date", value=BY_DATE.search(st).group(1)))
    return out


def structure(text, name, drafts_file=None, files=None, own_check=None):
    """[(file, line, rule, words)] for the shapes that let junk pile up:
    prose     a '## ' section holding drafts or naming a Figma file has text before its first block other
              than one paragraph opening "Held" (the section's hold note)
    moot      a block's heading status says moot, cut, withdrawn or dropped
    cut       a block keeps a "the draft below this heading was cut" placeholder
    comment   a block in the drafts file says it is not a comment
    override  a draft under a section naming a file in figma.new_thread_files has a post command that carries
              an override flag (--new-thread, --new-cause and the rest): written ahead, it hides the refusal
              that names the open thread the note folds into
    cutfile   a Cut row in the drafts file names a node id and no figma.com URL, so it refuses that id in
              every file: add the node's URL
    own-open  a NEW draft in the drafts file links an open root comment of the token owner's, which
              figma_post's own-open rule would refuse: make the fix and edit that comment instead. Figma is
              read only for a NEW draft that links a comment id; a read that fails is listed as did not run
    drafts_file: whether this is the drafts file (None: is_drafts_file(name)). files: the
    figma.new_thread_files stand-in for the selftest; own_check: figma_post.own_open_check's."""
    lines = text.split("\n")
    if drafts_file is None:
        drafts_file = is_drafts_file(name)
    out = []
    for s in sections(text):
        if not (FILE_KEY.search(s["head"]) or s["first"] < s["end"]):
            continue
        paras = paragraphs(lines, s["line"] + 1, s["first"])
        ok = len(paras) == 1 and paras[0][1].lstrip().startswith("Held")
        for at, para in ([] if ok else paras):
            out.append((name, at + 1, "prose", f"text outside any draft under \"{s['head'][:50]}\": "
                        f"{' '.join(para.split())[:90]}"))
    for b in blocks(text):
        m = MOOT.search(status_of(b["head"]))
        if m:
            out.append((name, b["first"] + 1, "moot", f"the heading says {m.group(0)}: {b['head'][:90]}"))
        body = lines[b["first"] + 1:b["end"]]
        for k, ln in enumerate(body):
            if PLACEHOLDER.search(ln):
                out.append((name, b["first"] + 2 + k, "cut", f"a cut draft's placeholder: {ln.strip()[:90]}"))
            elif drafts_file and not ln.startswith(">") and NOT_COMMENT.search(ln):
                out.append((name, b["first"] + 2 + k, "comment",
                            f"a block that says it is not a comment ({b['end'] - b['first']} lines): {b['head'][:70]}"))
                break
    if drafts_file:
        out += [(name, r["line"], "cutfile", f"a Cut row names {', '.join(sorted(r['nodes']))} and no figma.com URL, "
                 f"so it refuses that id in every file; add the node's URL: {clip(r['cell'], 70)}")
                for r in cut_table(text) if r["nodes"] and not r["file"]]
        out += override_drafts(text, name, files)
        out += own_open_drafts(text, name, own_check)
    return out


OWN_NOT_RUN = "own-open not run"   # listed with the structure problems, but it is a check that didn't run: exit 2


def own_open_drafts(text, name, own_check=None):
    """The own-open rule of structure(): each NEW draft whose lines link an open root comment of the token owner's,
    by figma_post.own_open_check, in the file its heading's link or its section names. Reads nothing when no NEW
    draft links a comment id."""
    sys.path.insert(0, TOOLS)
    import figma_post
    lines, out = text.split("\n"), []
    secs = sections(text)
    for b in blocks(text):
        body = "\n".join(lines[b["first"]:b["end"]])
        if not b["node"] or not figma_post.COMMENT_ID.search(body):
            continue
        sec = next((s for s in secs if s["line"] < b["first"] < s["end"]), None)
        m = URL_KEY.search(lines[b["first"]])
        f = None if m or not sec else FILE_KEY.search(sec["head"])
        key = m.group(1) if m else (f.group(0).strip("`") if f else None)
        try:
            if not key:
                raise ValueError("no file key in its heading's link or its section")
            ids = (own_check or figma_post.own_open_check)(key, body)
        except Exception as e:  # noqa: BLE001 -- a check that could not run is named, never passed
            out.append((name, b["first"] + 1, OWN_NOT_RUN, f"the own-open check did not run ({type(e).__name__}: "
                        f"{e}): {b['head'][:70]}"))
            continue
        if ids:
            out.append((name, b["first"] + 1, "own-open",
                        f"it links your own open comment {', '.join(ids)}, so figma_post refuses the new thread: make "
                        f"the fix, then add a FIX (done in Figma) line to it with figma_attach.py edit {key} {ids[0]}: "
                        f"{b['head'][:70]}"))
    return out


POST_CMD = re.compile(r"`[^`]*\bfigma_(?:post|attach)\.py\b[^`]*`")


def override_drafts(text, name, files=None):
    """The override rule of structure(), for the drafts under a section naming a file in figma.new_thread_files,
    where figma_post refuses every new FIX thread without --new-thread. It runs at draft time what the post runs,
    so a draft written to step past a refusal is caught before anyone approves it."""
    if files is None:   # the key figma_post.new_thread_files reads; figma_post loads only when a file is listed
        v = _cfg("figma", "new_thread_files") or []
        files = {v} if isinstance(v, str) else {str(k) for k in v}
    if not files:
        return []
    sys.path.insert(0, TOOLS)
    import figma_post
    lines, out = text.split("\n"), []
    listed = [s for s in sections(text) if any(f"`{k}`" in s["head"] for k in files)]
    for b in blocks(text):
        if not any(s["first"] <= b["first"] < s["end"] for s in listed):
            continue
        cmd = next((m.group(0) for ln in lines[b["first"] + 1:b["end"]] if not ln.startswith(">")
                    for m in [POST_CMD.search(ln)] if m), "")
        flags = [f for f in figma_post.OK_FLAGS + ("--new-thread", "--separate") if f in cmd]
        if flags:
            out.append((name, b["first"] + 1, "override",
                        f"the post command carries {', '.join(flags)}: drop it, and the post's refusal names the open "
                        f"thread this folds into: {b['head'][:70]}"))
    return out


def ledger_questions():
    sys.path.insert(0, TOOLS)
    import ledger
    return ledger.load_jsonl(os.path.join(ledger.LEDGER_DIR, "requests.jsonl"))


def ado_items(ids):
    """{id: {"state", "owner"}} for the ADO ids that exist; NotChecked without the PAT, the settings or on an
    error."""
    if not ids:
        return {}
    sys.path.insert(0, TOOLS)
    if not kit_config or not kit_config.token("ADO_PAT", "AZURE_DEVOPS_EXT_PAT"):
        raise NotChecked("no ADO_PAT in the environment or the OS keychain")
    try:
        import ado_rest
        d = ado_rest._req(ado_rest._p(f"/_apis/wit/workitemsbatch?{ado_rest.API}"),
                          {"ids": sorted(int(i) for i in ids), "errorPolicy": "Omit",
                           "fields": ["System.State", "System.AssignedTo", "System.Title"]})
    except SystemExit as e:
        raise NotChecked(f"ADO read failed ({e.code})")
    except kit_config.NotConfigured as e:
        raise NotChecked(str(e))
    out = {}
    for w in d.get("value") or []:
        if w and w.get("id"):
            f = w.get("fields") or {}
            who = f.get("System.AssignedTo")
            out[str(w["id"])] = {"state": f.get("System.State"),
                                 "owner": who.get("displayName") if isinstance(who, dict) else who}
    return out


def git_release(sha, branch, repo=None):
    """(verdict, detail) for "held until commit <sha> [on <branch>]": released once origin/<branch> holds it.
    repo: drafts.repo, else the folder you run in."""
    import subprocess
    repo = os.path.expanduser(repo or _cfg("drafts", "repo") or ".")
    run = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=30)
    try:
        if run("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            return "target gone", f"commit {sha} is not in {repo}"
        r = run("merge-base", "--is-ancestor", sha, f"origin/{branch}")
    except (OSError, subprocess.SubprocessError) as e:
        raise NotChecked(f"git: {type(e).__name__}")
    if r.returncode == 0:
        return "released", f"commit {sha} is on origin/{branch} (as of the last fetch)"
    if r.returncode == 1:
        return "held", f"commit {sha} is not on origin/{branch} yet (as of the last fetch)"
    raise NotChecked(f"git merge-base exit {r.returncode}: {r.stderr.strip()[:80]}")


def judge(hs, headings, today=None, questions=None, ado=None, git=git_release, branch=None):
    """Each hold with its verdict and a detail line. questions: the ledger rows, or a function that returns
    them; ado: a function of a set of ids; both are read only when a hold needs them. branch: the branch a
    commit release names none of (drafts.branch when None)."""
    import datetime as dt
    today = today or dt.date.today()
    branch = branch or _cfg("drafts", "branch")
    need = {h["value"][0] for h in hs if h["kind"] == "ado"}
    items, ado_err = {}, None
    if need:
        try:
            items = (ado or ado_items)(need)
        except NotChecked as e:
            ado_err = str(e)
    rows, q_err = None, None
    if any(h["kind"] == "question" for h in hs):
        try:
            rows = questions() if callable(questions) else questions if questions is not None else ledger_questions()
        except Exception as e:      # noqa: BLE001 - an unreadable ledger is not checked, never "still held"
            q_err = f"the ledger could not be read ({type(e).__name__})"
    byq = {e["qid"]: e for e in (rows or {}).values() if e.get("qid")} if rows is not None else {}
    out = []
    for h in hs:
        kind, v = h["kind"], h["value"]
        verdict, detail = "held", ""
        try:
            if kind == "untestable":
                verdict, detail = "untestable", f"{v}; ask the user what releases it, and if they put it off, write " \
                                                "`held until q-xxxxxx` with the question's id"
            elif kind == "question":
                if q_err:
                    raise NotChecked(q_err)
                e, seen = byq.get(v), set()
                while e and e.get("repeated_as") and e["repeated_as"] in rows and e["id"] not in seen:
                    seen.add(e["id"])
                    e = rows[e["repeated_as"]]        # carried by a later card: that card's state counts
                if not e:
                    verdict, detail = "target gone", f"{v} is not in the request ledger"
                elif e.get("state") == "open":
                    detail = f"{v} is still open"
                else:
                    verdict, detail = "released", f"{v} is {e.get('state')}: \"{(e.get('text') or '')[:60]}\""
            elif kind == "ado":
                wid, owner = v
                if ado_err:
                    raise NotChecked(ado_err)
                w = items.get(wid)
                if not w or w["state"] == "Removed":
                    verdict, detail = "target gone", f"#{wid} is {'Removed' if w else 'not in ADO'}"
                elif w["state"] in ("Closed", "Resolved", "Done"):
                    verdict, detail = "released", f"#{wid} is {w['state']}"
                elif owner and w["owner"]:
                    verdict, detail = "released", f"#{wid} has an owner, {w['owner']} ({w['state']})"
                else:
                    detail = f"#{wid} is {w['state']}" + ("" if w["owner"] else ", unassigned")
            elif kind == "draft":
                found = [x for x in headings if norm(v) in norm(x)]
                verdict, detail = ("held", f"the draft \"{v[:50]}\" is still unsent") if found else \
                    ("released", f"no draft heading holds \"{v[:50]}\": it went out or was dropped")
            elif kind == "commit":
                if not (v[1] or branch):
                    raise NotChecked(f"commit {v[0]} names no branch, and drafts.branch is not set")
                verdict, detail = git(v[0], v[1] or branch)
            elif kind == "date":
                d = dt.date.fromisoformat(v)
                verdict, detail = ("deadline passed", f"{v} has come") if today >= d else ("held", f"until {v}")
        except NotChecked as e:
            verdict, detail = "not checked", str(e)
        out.append(dict(h, verdict=verdict, detail=detail))
    return out


def cut_gone(text, lineage=None, files=None):
    """(rows whose every node id Figma no longer has, files not read). A row with a figma.com URL is judged in
    the file it names only, since ids are per file: its node alive in another file is another node. A row
    with no URL is judged in every file read, and its node counts as gone only when none holds it. With a
    file unread, no row is judged. Listed only: nothing here removes a row."""
    rows = [r for r in cut_table(text) if r["nodes"]]
    if not rows:
        return [], []
    if files is None:
        files = list(kit_config.figma_files() if kit_config else []) + URL_KEY.findall(text)
    files = list(dict.fromkeys(list(files) + [r["file"] for r in rows if r["file"]]))
    where = lambda r: [r["file"]] if r["file"] else files  # noqa: E731
    want = {key: set().union(*[r["nodes"] for r in rows if key in where(r)]) for key in files}
    if lineage is None:
        sys.path.insert(0, TOOLS)
        import figma_auth
        import figma_client
        tok = figma_auth.token()
        lineage = lambda key, ns: figma_client.lineage_or_exit(key, sorted(ns), kids=False, token=tok, tool="drafts_store")
    alive, unread = set(), []        # alive: (file, node id)
    for key in files:
        if not want[key]:
            continue
        try:
            chains = lineage(key, want[key])
        except SystemExit as e:
            unread.append(f"{key} ({e.code})")
            continue
        alive |= {(key, n) for n in want[key] if chains.get(n) is not None}
    if unread:
        return [], unread
    if not files:
        return [], ["no Figma file named in figma.files or in the drafts file"]
    return [r["cell"] for r in rows if not any((key, n) in alive for key in where(r) for n in r["nodes"])], []


def stale(paths=None, figma=False, today=None, questions=None, ado=None, git=git_release, lineage=None,
          figma_files=None, branch=None, files=None):
    """The whole check: {"holds": judged holds, "structure": problems, "cut_gone": rows, "cut_unread": files,
    "unread": files not read}. paths: the drafts file and the outbound file by default (the first, when
    configured, is read as the drafts file). figma: also list Cut rows on deleted nodes (the daily run)."""
    mine = drafts_path()
    paths = paths or [x for x in (mine, outbound_path()) if x]
    texts, unread = {}, []
    for p in paths:
        try:
            texts[p] = open(p, encoding="utf-8").read()
        except OSError as e:
            unread.append(f"{p} ({type(e).__name__})")
    headings = [b["head"] for t in texts.values() for b in blocks(t)]
    hs = [h for p, t in texts.items() for h in holds(t, os.path.basename(p))]
    out = {"holds": judge(hs, headings, today, questions, ado, git, branch),
           "structure": [x for p, t in texts.items()
                         for x in structure(t, os.path.basename(p), is_drafts_file(p), files)],
           "cut_gone": [], "cut_unread": None, "unread": unread}
    if figma:
        cut_text = "".join(t for p, t in texts.items() if CUT in t)
        out["cut_gone"], out["cut_unread"] = cut_gone(cut_text, lineage, figma_files) if cut_text else ([], [])
    return out


def count_line(r):
    """One line: what a reader of a daily digest or a triage pass acts on."""
    hs = r["holds"]
    n = {v: sum(1 for h in hs if h["verdict"] == v) for v in VERDICTS}
    act = n["released"] + n["target gone"] + n["deadline passed"] + n["untestable"]
    cut = ("Cut rows not checked (--figma reads Figma)" if r["cut_unread"] is None else
           f"Cut rows not checked ({', '.join(r['cut_unread'])})" if r["cut_unread"] else
           f"{len(r['cut_gone'])} Cut row{'s' * (len(r['cut_gone']) != 1)} on deleted nodes")
    return (f"{act} of {len(hs)} holds to clear or ask about ({n['released']} released, {n['target gone']} target gone, "
            f"{n['deadline passed']} deadline passed, {n['untestable']} untestable), {n['held']} still held, "
            f"{n['not checked']} not checked; {len(r['structure'])} structure problem{'s' * (len(r['structure']) != 1)}; "
            + cut + ("; not read: " + ", ".join(r["unread"]) if r["unread"] else ""))


def stale_exit(r):
    act = any(h["verdict"] not in ("held", "not checked") for h in r["holds"])
    found = [x for x in r["structure"] if x[2] != OWN_NOT_RUN]
    if act or found or r["cut_gone"]:
        return 1
    return 2 if (r["unread"] or r["cut_unread"] or len(found) < len(r["structure"])
                 or any(h["verdict"] == "not checked" for h in r["holds"])) else 0


def list_lines(text):
    """What `list` prints: a line per draft, its node ids linked in the file its section names."""
    out = []
    for b in blocks(text):
        kind = "EDIT" if b["comment"] else "NEW" if b["node"] else "other"
        out.append(shown(f"{kind:5} {b['comment'] or b['node'] or '-':14} {len(b['quote']):5} chars  "
                         f"{clip(b['head'], 80)}", key_at(text, b["first"] + 1)))
    return out


def show_stale(r, out=print, texts=None):
    """r as printed. texts, {file name: its text}, gives each hold its section's file, so its node ids link; a
    detail or structure line, cut before it gets here, links only its #1234s."""
    texts = texts or {}
    out("stale: " + count_line(r))
    for v in VERDICTS[:-1]:
        for h in (h for h in r["holds"] if h["verdict"] == v):
            out(shown(f"  {v.upper():16} {h['file']}:{h['line']}  {clip(h['head'], 80)}",
                      key_at(texts.get(h["file"]), h["line"])))
            out(shown(f"  {'':16} {h['detail']}"))
    for name, line, rule, words in r["structure"]:
        out(shown(f"  {'STRUCTURE ' + rule:16} {name}:{line}  {words}"))
    for cell in r["cut_gone"]:
        key = URL_KEY.search(cell)
        out(shown(f"  {'CUT ROW GONE':16} {clip(cell, 100)}  (list only: delete the row by hand if it guards "
                  "nothing)", key and key.group(1)))
    if any(h["verdict"] != "held" for h in r["holds"]) or r["structure"]:
        out("Clear the released, gone and passed ones in one batch, and put each untestable one to the user as a "
            "question.")


SAMPLE = """# Figma comments owed

## Open

### Hero button — NEW on the hero row [`7900:62900`](https://x) · **Not sent.**

> FIX (done in Figma): The hero button reads "Install" again. Please confirm and resolve. Before and after:

### Footer — EDIT your own comment [1900005074](https://x#1900005074) on the footer · **Not sent.**

> FIX (done in Figma): The footer heading sits 64 below the photo. Please check and resolve. Before and after:

### Held question — `5200:52001` · Last reviewed: 2026-10-20 — held.

> Who owns the load credential?

## Cut: do not re-raise

| Item | Why |
|---|---|
| Comparison table header cell, `5300:53001` | Intentional |
| Mobile frames | Known work |
"""


# The known-bad shapes, cut down: a file section with history paragraphs before its drafts, drafts held "until
# the designer finishes" (no release a tool can test), a block that says it is not a comment, an empty file
# section, and a moot, a placeholder and a held item in the outbound file.
BAD_DRAFTS = """# Figma comments owed

## How a draft is written

- A status update or a thank-you is not a comment.

## Design file `PlantedFileKey00000001`

Last week the waiting drafts were merged into one comment per kind of fix and posted: several new
threads and edits to several of your own comments.

The two drafts below are notes on the designer's final journey frames. The designer was still editing the
section, so both are held until that's done.

### Journey screen 1, agent avatar — NEW on builder [`3100:1001`](https://x) · **Last reviewed: 2030-01-08 — held on the user's call until the designer finishes editing the section.**

> FIX: Use the icon for the avatar in place of the initial.

### Journey screen 2, builder copy — NEW on builder [`3100:1002`](https://x) · **Last reviewed: 2030-01-08 — held on the user's call until the designer finishes editing the section.**

> FIX: Say "pick a project" in the subtitle.

### Build cost and models — NEW section on page `3100:1003` · Last reviewed: 2030-01-09

Not a comment: a page-level section of our own, written with `use_figma`.

> Where the build flow stands on cost.

## Slide decks `PlantedFileKey00000002`

No open drafts. Read a slide with `figma_comments.py frame PlantedFileKey00000002 <slide>` before posting.

## Cut: do not re-raise

`figma_post.py new` refuses a post on a node one of these rows names.

| Item | Why |
|---|---|
| Card 6 "(coming soon)", `8:4345` | Dropped in review |
| Gallery photos squeezed to fit, `3200:30001` | Dropped in review |
| Comparison header cell 69 in a 72 row, `3200:30002` | Dropped: intentional |
| Stranded threads `1000000001`, `1000000002` | Corrections to frames that no longer exist |
"""

BAD_OUTBOUND = """# Outbound drafts

Each message waits for the user to send it.

### Reviewer, chat: the PR for the release. NOT SENT. Moot: the reviewer completed the PR.

Hey! The PR is up.

### Events team, email: the submission. NOT SENT. Held: the entry is being rebuilt.

The draft below this heading was cut: it described the old entry.

### Design group chat: notes on the final journey frames. NOT SENT. Held: waits on the two journey-frame Figma comments, which the user held until the designer finishes editing the section.

> hey all, notes on the journey frames.

### QA chat: today's feedback fixes. NOT SENT.

> the fixes are on the test branch.
"""

# The override rule: drafts under a file in figma.new_thread_files whose post command was written to step past
# a refusal, beside ones that were not, and a board the setting does not list.
OVERRIDE_DRAFTS = """# Figma comments owed

## Design file `PlantedFileKey00000001`

### Footer bar taller than the footer component — NEW on "footer" [`3001:1001`](https://x) · **Not sent.**

`figma_post.py new PlantedFileKey00000001 3001:1001 <text> --new-thread "no thread on the file covers the bar's size"`

> FIX (done in Figma): The footer bar matches the footer component now.

### Sticky bar at 65% — NEW on "Sticky bar" [`3001:1002`](https://x) · **Not sent.**

`figma_post.py new PlantedFileKey00000001 3001:1002 <text> --cause sticky-bar --new-cause "no open cause covers it"`

> FIX (done in Figma): The sticky bar's dark fill is now 65% opacity, up from 50%.

### Hero crop cut off on phone — NEW on hero [`3001:1003`](https://x) · **Not sent.**

`figma_post.py new PlantedFileKey00000001 3001:1003 <text> --edited 3001:1003 --picture x.jpg --cause hero-crop`

> FIX (done in Figma): The hero crop is centred now.

## Journey board `PlantedFileKey00000003`

### Search and download events — `3002:1001` · **Not sent.**

`figma_post.py new PlantedFileKey00000003 3002:1001 <text> --pin-ok "the whole band is the subject"`

> Q: Should search and download each get their own event?
"""

# The same items written as the rule asks: a section held by one "Held" note, drafts held with it, and each kind
# of release.
GOOD_DRAFTS = """# Figma comments owed

## How a draft is written

- **Last reviewed: <date> — held until <release>** means it is held on purpose; a draft that says "not a
  comment" here is about the rule, not a block.

## Design file `PlantedFileKey00000001`

### Sticky bar at 65% — NEW on "Sticky bar" [`3001:1002`](https://x) · **Not sent.** Goes in the next batch.

> FIX (done in Figma): The sticky bar's fill is 65% now.

### Hero crop cut off on phone — NEW on hero [`3001:1003`](https://x) · **Not sent.**

> FIX (done in Figma): The hero crop is centred now.

## Journey board `PlantedFileKey00000003`

Held until #545 closes: drafts on the library section (`3002:1002`), waiting on the knowledge-layer
decision.

### Search and download events — `3002:1001` · Last reviewed: 2030-01-10 — held with the section.

> Q: Should search and download each get their own event?

### Who owns the load credential — `3002:1003` · Last reviewed: 2030-01-08 — held until #895 has an owner (it is New and unassigned).

> Q: Who owns the credential?

### What triggers the retire rebuild — `3002:1004` · Last reviewed: 2030-01-08 — held until #897 has an owner.

> Q: Who runs the release sync?

## Cut: do not re-raise

| Item | Why |
|---|---|
| Comparison header cell 69 in a 72 row, [`3200:30002`](https://www.figma.com/design/KW000000000000000000KW/File?node-id=3200-30002) | Dropped: intentional |
| Stranded thread `1000000003` | A thread-id row takes no file |
"""

GOOD_OUTBOUND = """# Outbound drafts

Each message waits for the user to send it. An item that waits on something says held until its
release; reasoning about a draft does not belong here.

### Partner A, chat 1:1: pilot ask. NOT SENT. Held until q-a0a0a0 (the entry waits for 9 of 9).

Hi!

### Events team, email: the submission. NOT SENT. Held until q-a0a0a0. No draft yet: write it then from the entry's page.

### Partner B, chat 1:1: builds through the gallery. NOT SENT. Held until the draft "Platform contact, chat 1:1: what the onboarding concept needs" goes out.

> Hi!

### Platform contact, chat 1:1: what the onboarding concept needs from their team's service. NOT SENT.

Hi!

### Pilot group chat: a ready signal. NOT SENT. Held until 2030-01-10, when wave 1 scores.

> hey both.

### Site team, group chat: the kit. NOT SENT. Held until commit bb2d77bc is on release.

> Hi all!

### Concept team, group chat: two facts before the review. NOT SENT. Send by 2030-01-10.

> two facts.

### Library lead, chat 1:1: one point for the library session. NOT SENT. Held until the user has room for that session.

> hey, one to add.

### Engineering lead: what is actually in the release. NOT SENT. READY: send before the follow-up.

**Do not add the pricing finding.** Held.

> counted what's actually in the release.
"""


def selftest_stale(case):
    import datetime as dt
    today = dt.date(2030, 1, 10)
    ledger_rows = {
        "a": {"id": "a", "qid": "q-a0a0a0", "state": "open", "text": "Hold until 9 of 9"},
        "b": {"id": "b", "qid": "q-111111", "state": "answered", "text": "Go"},
        "c": {"id": "c", "qid": "q-222222", "state": "open", "repeated_as": "d", "text": "Later"},
        "d": {"id": "d", "qid": "q-333333", "state": "answered", "text": "Send it"},
    }
    ado_rows = {"895": {"state": "New", "owner": None}, "897": {"state": "New", "owner": "Lee, Sam"},
                "545": {"state": "Active", "owner": "Lee, Sam"}, "637": {"state": "Closed", "owner": None},
                "700": {"state": "Removed", "owner": None}}
    git_rows = {"bb2d77bc": ("held", "not on origin/release"), "1f68938d": ("released", "on origin"),
                "deadbeef": ("target gone", "not in the repo")}
    fake_git = lambda sha, branch: git_rows[sha]
    st = lambda d, o, **k: stale(_planted(d, o), today=today, questions=ledger_rows, ado=lambda ids: ado_rows,
                                 git=fake_git, branch="release", files=set(), **k)
    by = lambda r, words: next((h for h in r["holds"] if words in h["head"]), {})

    bad = st(BAD_DRAFTS, BAD_OUTBOUND)
    prose = [x for x in bad["structure"] if x[2] == "prose"]
    case("known-bad: a file section's two history paragraphs and an empty file section are prose outside any draft",
         len(prose) == 3 and sum("Design file" in x[3] for x in prose) == 2 and any("Slide decks" in x[3] for x in prose))
    case("known-bad: the block that says it is not a comment is named, with its length",
         [x[1] for x in bad["structure"] if x[2] == "comment"] == [BAD_DRAFTS.split("\n").index(
             "Not a comment: a page-level section of our own, written with `use_figma`.") + 1])
    case("known-bad: a moot heading and a cut draft's placeholder are named",
         any(x[2] == "moot" and "Reviewer, chat" in x[3] for x in bad["structure"])
         and any(x[2] == "cut" and "draft below this heading was cut" in x[3] for x in bad["structure"]))
    j = [h for h in bad["holds"] if h["head"].startswith("Journey screen")]
    case("known-bad: the drafts held \"until the designer finishes\" are untestable, so they go to the user",
         len(j) == 2 and all(h["verdict"] == "untestable" for h in j)
         and by(bad, "notes on the final journey frames").get("verdict") == "untestable")
    case("known-bad: a live item with no hold, the QA-chat note, is not a hold (its miss is named in BLIND TO)",
         not by(bad, "QA chat") and stale_exit(bad) == 1)
    good = st(GOOD_DRAFTS, GOOD_OUTBOUND)
    case("known-good: no structure problem in the files as the rule writes them (a one-paragraph Held note is allowed)",
         good["structure"] == [])
    od = {(x[2], x[1]) for x in structure(OVERRIDE_DRAFTS, "drafts.md", True, {"PlantedFileKey00000001"})}
    at = lambda words: OVERRIDE_DRAFTS.split("\n").index(next(ln for ln in OVERRIDE_DRAFTS.split("\n") if words in ln)) + 1
    case("known-bad: under a file in figma.new_thread_files, a post command with --new-thread or --new-cause "
         "written ahead is an override",
         ("override", at("Footer bar taller")) in od and ("override", at("Sticky bar at 65%")) in od)
    case("known-good: a plain post command there, and an override on a file the setting does not list, pass",
         not {x for x in od if x[1] in (at("Hero crop"), at("Search and download"))})
    case("... and with no file listed, the rule reads nothing",
         not [x for x in structure(OVERRIDE_DRAFTS, "drafts.md", True, set()) if x[2] == "override"])
    case("a draft held with the section takes the section note's release",
         by(good, "Search and download").get("kind") == "ado" and by(good, "Search and download").get("value")
         == ("545", None) and by(good, "Search and download").get("verdict") == "held"
         and by(good, "section note").get("verdict") == "held")
    case("ADO: unassigned with \"has an owner\" is held; assigned is released",
         by(good, "load credential").get("verdict") == "held" and by(good, "retire rebuild").get("verdict") == "released")
    case("a ledger question still open holds; a draft heading still in the file holds",
         by(good, "Partner A").get("verdict") == "held" and by(good, "Partner B").get("verdict") == "held")
    case("a date that has come is a deadline passed, held or a send-by",
         by(good, "Pilot group").get("verdict") == "deadline passed"
         and by(good, "Concept team").get("verdict") == "deadline passed")
    case("a commit not on the branch yet holds", by(good, "Site team").get("verdict") == "held")
    case("a hold with no release a tool can test is untestable; \"Held\" inside a draft's body is not a hold",
         by(good, "Library lead").get("verdict") == "untestable" and not by(good, "Engineering lead"))
    case("the count line reads N of M, each verdict counted",
         count_line(good).startswith("4 of 11 holds to clear or ask about (1 released, 0 target gone, 2 deadline passed, "
                                     "1 untestable), 7 still held, 0 not checked; 0 structure problems"))
    rel = lambda line, branch="release": judge(
        holds("### X — `1:2345` · Last reviewed: 2030-01-10 — " + line + "\n\n> Q?\n", "drafts.md"),
        ["Platform contact, chat 1:1: what the onboarding"], today, ledger_rows, lambda ids: ado_rows, fake_git,
        branch)[0]
    case("each release resolves: a question answered, one carried to a later answered card, one not in the ledger",
         rel("held until q-111111.")["verdict"] == "released" and rel("held until q-222222.")["verdict"] == "released"
         and rel("held until q-999999.")["verdict"] == "target gone")
    case("... an ADO item Closed, Removed or missing; a commit on the branch or not in the repo",
         rel("held until #637.")["verdict"] == "released" and rel("held until #700.")["verdict"] == "target gone"
         and rel("held until ADO #999.")["verdict"] == "target gone"
         and rel("held until commit 1f68938d.")["verdict"] == "released"
         and rel("held until commit deadbeef on trunk.")["verdict"] == "target gone")
    U = "https://dev.azure.com/Org/Project/_workitems/edit/"
    case("... an ADO id written as a link to its item reads the same as bare",
         rel(f"held until [#637]({U}637/).")["verdict"] == "released"
         and rel(f"held until [#700]({U}700/).")["verdict"] == "target gone"
         and rel(f"held until ADO [#999]({U}999/).")["verdict"] == "target gone"
         and rel(f"held until [#895]({U}895/) has an owner.")["verdict"] == rel("held until #895 has an owner.")["verdict"])
    case("... a commit that names no branch, with none configured, is not checked",
         rel("held until commit 1f68938d.", branch="")["verdict"] == "not checked")
    case("... a draft gone from both files is released; a date still to come holds",
         rel('held until the draft "Partner A, chat 1:1".')["verdict"] == "released"
         and rel('held until the draft "Platform contact, chat 1:1".')["verdict"] == "held"
         and rel("held until 2030-01-20.")["verdict"] == "held")

    def no_pat(ids):
        raise NotChecked("no ADO_PAT")
    r = stale(_planted(GOOD_DRAFTS, ""), today=today, questions=ledger_rows, ado=no_pat, git=fake_git, branch="release",
              files=set())
    case("an ADO release it cannot read is not checked, never held, and alone exits 2",
         by(r, "load credential").get("verdict") == "not checked"
         and by(r, "Search and download").get("verdict") == "not checked" and stale_exit(r) == 2)
    case("... and a file it cannot read is named and exits 2", stale_exit(stale(
         [os.path.join(os.sep, "nonexistent", "drafts.md")], today=today, questions=ledger_rows, files=set())) == 2)
    lin = lambda key, ns: {n: (None if n in ("8:4345", "3200:30001") else [{"id": n}]) for n in ns}
    rb = st(BAD_DRAFTS, "", figma=True, lineage=lin, figma_files=["K1", "K2"])
    case("known-bad: the Cut rows on deleted nodes are listed (a one-digit first part too); the live one and "
         "thread-only rows are not",
         len(rb["cut_gone"]) == 2 and all(("8:4345" in c) ^ ("3200:30001" in c) for c in rb["cut_gone"])
         and "8:4345" in {i for _, ids in cut_rows(BAD_DRAFTS) for i in ids})

    def half(key, ns):
        if key == "K2":
            raise SystemExit("Figma 500")
        return lin(key, ns)
    rh = st(BAD_DRAFTS, "", figma=True, lineage=half, figma_files=["K1", "K2"])
    case("... and with a file unread, no row is called gone", rh["cut_gone"] == [] and rh["cut_unread"] == ["K2 (Figma 500)"])
    # Each row in its own file. KW holds every id here and KB none, so the board row's id lives only as another
    # file's node.
    kw, kb = "KW" + "0" * 18 + "KW", "KB" + "0" * 18 + "KB"
    per = (f"{CUT}\n\n| Item | Why |\n|---|---|\n"
           f"| Board row, [`3300:30001`](https://www.figma.com/board/{kb}/B?node-id=3300-30001) | x |\n"
           f"| Design row, [`3300:30002`](https://www.figma.com/design/{kw}/W?node-id=3300-30002) | x |\n"
           "| No file, `8:4345` | x |\n| Stranded thread `1000000003` | x |\n")
    asked = {}

    def per_file(key, ns):
        asked[key] = set(ns)
        return {n: [{"id": n}] if key == kw else None for n in ns}
    rp = st(per, "", figma=True, lineage=per_file, figma_files=[kw])
    case("known-bad: a row whose node is alive only in another file is gone; known-good: a row alive in its own "
         "file, and a row with no URL alive in any file read, are not",
         len(rp["cut_gone"]) == 1 and "Board row" in rp["cut_gone"][0])
    case("... and a row's own file is read though no setting lists it, for its ids and the no-URL rows' only",
         asked == {kw: {"3300:30002", "8:4345"}, kb: {"3300:30001", "8:4345"}})
    flagged = [x for x in structure(per, "drafts.md", drafts_file=True, files=set()) if x[2] == "cutfile"]
    case("stale --structure flags a node-id Cut row with no URL; a row with one and a thread-id row pass",
         len(flagged) == 1 and "8:4345" in flagged[0][3] and per.split("\n")[flagged[0][1] - 1].startswith("| No file")
         and not [x for x in structure(per, "outbound-drafts.md", drafts_file=False, files=set()) if x[2] == "cutfile"])
    import shutil
    while PLANTED:
        shutil.rmtree(PLANTED.pop(), ignore_errors=True)


PLANTED = []      # the selftest's temporary folders, removed when it ends


def _planted(drafts_text, outbound_text):
    """Two planted files in a fresh temporary folder, as stale() reads them."""
    td = tempfile.mkdtemp(prefix="drafts-stale-selftest-")
    PLANTED.append(td)
    paths = []
    for name, t in (("drafts.md", drafts_text), ("outbound-drafts.md", outbound_text)):
        if t:
            p = os.path.join(td, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(t)
            paths.append(p)
    return paths


def selftest():
    results = []

    def case(name, ok):
        results.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    td = tempfile.mkdtemp(prefix="drafts-store-selftest-")
    p = os.path.join(td, "drafts.md")
    reset = lambda: open(p, "w", encoding="utf-8").write(SAMPLE)
    reset()
    bs = blocks(SAMPLE)
    case("three drafts parsed, with an EDIT's comment id and a NEW's node id",
         len(bs) == 3 and bs[0]["node"] == "7900:62900" and bs[1]["comment"] == "1900005074")
    posted = 'FIX (done in Figma): The hero button reads "Install" again. Please confirm and resolve.\n\nBefore and after:'
    got = remove_posted(posted, node_id="7900:62900", path=p)
    after = open(p, encoding="utf-8").read()
    case("the posted NEW draft leaves the file, label and line breaks aside",
         got and "Hero button" not in after and "Footer" in after and "Held question" in after and CUT in after)
    reset()
    got = remove_posted("Q: Is the hero row meant to be 720 or 760 tall?", node_id="7900:62900", path=p)
    case("another post on the same node, about something else, removes nothing and names the draft it kept",
         got and "none was removed" in got and "Hero button" in got and open(p, encoding="utf-8").read() == SAMPLE)
    case("a post whose text matches no draft removes nothing",
         remove_posted("FIX (done in Figma): something else entirely.", node_id="1:2", path=p) is None
         and open(p, encoding="utf-8").read() == SAMPLE)
    edited = "FIX (done in Figma): The footer heading sits 64 below the photo, as on the site. Please check and resolve."
    case("an EDIT draft leaves by its comment id and a close match",
         remove_posted(edited, comment_id="1900005074", path=p) and "Footer" not in open(p, encoding="utf-8").read())
    reset()
    case("... but not by a close match on another comment's id",
         remove_posted(edited, comment_id="1111111111", path=p) is None)
    got = remove_posted("Q: Should the badge be 12 or 14 tall?", comment_id="1900005074", path=p)
    case("... nor by unrelated text on its own comment id, which it names",
         got and "none was removed" in got and open(p, encoding="utf-8").read() == SAMPLE)
    frag = ("### Footer, a seventh screen — EDIT your own comment [`2222222222`](https://x#2222222222) · **Not sent.**\n\n"
            "> 7. Gallery page phone footer. The links stack, as on the other six screens.\n>\n"
            "> Please check it and resolve this.\n")
    open(p, "w", encoding="utf-8").write(SAMPLE + frag)
    case("an EDIT heading whose comment id sits in backticks is parsed",
         [b["comment"] for b in blocks(SAMPLE + frag)][-1] == "2222222222")
    whole = ("FIX (done in Figma): The footer links stack on phone.\n\n1. Home. 2. Gallery.\n\n"
             "7. Gallery page phone footer. The links stack, as on the other six screens.\n\n"
             "Please check it and resolve this.")
    case("an EDIT draft that quotes only the lines it adds leaves when the new text holds each paragraph",
         remove_posted(whole, comment_id="2222222222", path=p) and "seventh screen" not in open(p, encoding="utf-8").read())
    open(p, "w", encoding="utf-8").write(SAMPLE + frag)
    case("... but not when that text goes on another comment",
         remove_posted(whole, comment_id="3333333333", path=p) is None
         and open(p, encoding="utf-8").read() == SAMPLE + frag)
    got = remove_posted(whole.replace("as on the other six", "like the other six"), comment_id="2222222222", path=p)
    case("... nor when one of its paragraphs was reworded, which it names",
         got and "none was removed" in got and open(p, encoding="utf-8").read() == SAMPLE + frag)
    short = "### Tiny — EDIT your own comment [`4444444444`](https://x#4444444444)\n\n> Please resolve.\n"
    open(p, "w", encoding="utf-8").write(SAMPLE + short)
    case("... nor a quote under 40 characters that the new text happens to hold",
         "none was removed" in (remove_posted("FIX (done in Figma): The badge is 12 tall now. Please resolve.",
                                              comment_id="4444444444", path=p) or ""))
    reset()
    twice = SAMPLE.replace("### Held question", "### Hero again — NEW on [`7900:62900`](https://x)\n\n> FIX (done in Figma): "
                           "The hero button reads \"Install\" again. Please confirm and resolve.\n\n### Held question")
    open(p, "w", encoding="utf-8").write(twice)
    got = remove_posted(posted, node_id="7900:62900", path=p)
    case("two drafts with the posted text: neither is removed, and it says so",
         got and "none was removed" in got and open(p, encoding="utf-8").read() == twice)
    reset()
    case("a held question with no post is never touched by an unrelated post",
         remove_posted("Who owns the deploy key?", path=p) is None)
    case("a node in the Cut table is refused", "Cut: do not re-raise" in (cut_refusal("5300:53001", path=p) or ""))
    case("a node not in it passes", cut_refusal("5300:5300", path=p) is None and cut_refusal("5200:52001", path=p) is None)
    case("a missing file refuses nothing and removes nothing",
         cut_refusal("5300:53001", path=p + "x") is None and remove_posted(posted, path=p + "x") is None)
    # Node ids are per file: a row refuses only in the file its URL names.
    web, board = "KW" + "0" * 18 + "KW", "KB" + "0" * 18 + "KB"
    cutp = os.path.join(td, "cut.md")
    with open(cutp, "w", encoding="utf-8") as f:
        f.write(f"{CUT}\n\n| Item | Why |\n|---|---|\n| Is the download method settled now, [`3300:30001`]"
                f"(https://www.figma.com/board/{board}/Board?node-id=3300-30001) | Dropped |\n"
                "| Comparison header cell, `3200:30002` | Intentional |\n")
    case("known-bad: a Cut row on a board node doesn't refuse a post on the same id in another file",
         cut_refusal("3300:30001", web, path=cutp) is None)
    case("known-good: the same row still refuses on the board, and when no file is named",
         "delete that row first" in (cut_refusal("3300:30001", board, path=cutp) or "")
         and cut_refusal("3300:30001", path=cutp) is not None)
    case("a node-id row with no URL refuses in every file, and says to add the URL rather than delete the row",
         all("add that node's figma.com URL" in (cut_refusal("3200:30002", k, path=cutp) or "") for k in (web, board)))
    os.remove(cutp)
    wrapped = ("FIX (done in Figma): These cards are 450 tall now, on desktop and phone, so the row fits its\n"
               "seven pills with the last one back in place.\n\nBefore and after:")
    listed = ("FIX (done in Figma): Two fixes.\n\n1. The title reads \"A\". It read \"B\".\n"
              "2. The badge reads \"C\".\n\nFirst: https://www.figma.com/design/K/File?node-id=1-2\n"
              "Second: https://www.figma.com/design/K/File?node-id=3-4\n\nBefore and after:")
    case("a quote's wrapping, copied as a comment's text, is refused", wrapped_refusal(wrapped) is not None)
    case("list items and lines that end in a link or a colon are kept", wrapped_refusal(listed) is None)
    case("text_of joins the wrapping back into one line", wrapped_refusal(text_of(wrapped)) is None
         and "fits its seven pills" in text_of(wrapped))
    case("text_of keeps list items and link lines as they are", text_of(listed) == listed)
    md = "### Two fixes — EDIT your own comment [1111111111](https://x#1111111111)\n\n" + "\n".join(
        ("> " + ln) if ln else ">" for ln in listed.split("\n")) + "\n"
    case("a quote's blank '>' lines come through blocks() and text_of() as paragraph breaks",
         text_of(blocks(md)[0]["quote"]) == listed)
    os.remove(p)
    os.rmdir(td)
    selftest_stale(case)
    selftest_links(case)
    selftest_own_open(case)
    print(f"{sum(results)} of {len(results)} planted cases behave as expected.")
    return 0 if all(results) else 1


def selftest_own_open(case):
    """The own-open structure rule: figma_post's own-open cases while the draft sits in the drafts file, through
    figma_post.own_open_check with planted comments, so no network."""
    import figma_post as fp
    me, key = "Owner, Planted", "KO" + "0" * 18 + "KO"
    root = lambda cid, **kw: {"id": cid, "parent_id": "", "resolved_at": None, "user": {"handle": me},
                              "message": "x", **kw}
    calls = []

    def check(cs):
        def run(k, body):
            calls.append(k)
            return fp.own_open_check(k, body, read=lambda f: cs, me=me)
        return run
    notes = (f"### Hero photo crop — NEW on `1100:20001`\n\nSame kind as [your comment on the card photos]"
             f"(https://www.figma.com/design/{key}/F?node-id=1100-20000#1000000001).\n\n> Q: Should the hero photo "
             "crop to the same frame as the card photos?\n")
    quoted = ("### Footer scrim — NEW on `1100:20002`\n\n> Q: Should the footer scrim be 35% as well, as in "
              "https://x#1000000002?\n")
    edit = "### Card photos — EDIT your own comment [`1000000001`](https://x#1000000001)\n\n> FIX (done in Figma): x.\n"
    plain = "### Hero copy — NEW on `1100:20003`\n\n> Q: Is the hero's copy final?\n"
    md = f"## Design file `{key}`\n\n{notes}\n{quoted}\n{edit}\n{plain}"
    own = lambda cs: [x for x in structure(md, "drafts.md", True, set(), own_check=check(cs)) if x[2] == "own-open"]
    got = own([root("1000000001"), root("1000000002")])
    case("own-open known-bad: a draft linking your open comment in its notes, and one linking it in its text, are "
         "listed, each naming the comment to edit; the EDIT block of that comment and a draft linking none are not",
         len(got) == 2 and f"figma_attach.py edit {key} 1000000001" in got[0][3] and "1000000002" in got[1][3]
         and md.split("\n")[got[0][1] - 1].startswith("### Hero photo crop"))
    case("own-open: Figma is read only for the two NEW drafts that link a comment id", calls == [key, key])
    case("own-open known-good: the same drafts citing resolved threads, or a teammate's open comments, are not listed",
         not own([root("1000000001", resolved_at="2030-01-01T04:34:12Z"),
                  root("1000000002", user={"handle": "Teammate, Planted"})]))
    down = [x for x in structure(md, "drafts.md", True, set(),
                                 own_check=lambda k, b: (_ for _ in ()).throw(OSError("no token")))
            if x[2] == OWN_NOT_RUN]
    case("own-open: a read that fails is listed as did not run, never passed",
         len(down) == 2 and all("did not run (OSError: no token)" in x[3] for x in down))
    blank = {"holds": [], "cut_gone": [], "cut_unread": None, "unread": []}
    case("own-open: a check that didn't run exits 2, not 1; a refusal it found exits 1",
         stale_exit(dict(blank, structure=down)) == 2
         and stale_exit(dict(blank, structure=down + own([root("1000000001")]))) == 1)
    case("own-open: the outbound file is not read",
         not [x for x in structure(md, "outbound-drafts.md", False, set(), own_check=check([root("1000000001")]))
              if x[2] == "own-open"])


def selftest_links(case):
    """Printed lines link a node only in the file its '## ' section or its Cut cell names, and link every #1234. A
    cut never leaves half an id or half a URL, and r is printed, never changed."""
    import copy
    import bare_ids
    import figma_comments
    web, board = "KD" + "0" * 18 + "KD", "KB" + "0" * 18 + "KB"
    lead = (f"NEW on `5100:51001` · held until #4820 has an owner, see "
            f"[the thread](https://www.figma.com/design/{web}/Design?node-id=5100-51001#1000000009)")
    plain = MDLINK.sub(r"\1", lead)
    head = lead + " " + "x" * max(1, 69 - len(plain)) + " 12900:17001 next"     # the 80-character cut: 12900:170
    text = "\n".join([f"## Design file `{web}`", "", "### " + head, "> Q: does the gap match?", "",
                      f"## Planning board `{board}`", "", "### NEW on `5200:52001` · held until #4895 has an owner",
                      "> Q: who owns it?", "", "## Notes", "", "### About `5300:53001` · held until 2030-12-01", "> x", ""])
    bs = blocks(text)
    r = {"holds": [{"file": "d.md", "line": b["first"] + 1, "head": b["head"], "verdict": "released",
                    "detail": d} for b, d in zip(bs, ("#4820 is Closed", "#4895 has an owner, A (Active)",
                                                      "until 2030-12-01"))],
         "structure": [], "cut_unread": [], "unread": [],
         "cut_gone": [f"Old pill `6900:81001`, [here](https://www.figma.com/design/{web}/Design?node-id=6900-81001)",
                      "Gateway card `11900:113001`, no file named"]}
    before = copy.deepcopy(r)
    kept_ado, kept_meta = kit_config.ado, dict(figma_comments._META)
    kit_config.ado = lambda: ("https://dev.azure.com/Org", "Planted Project")
    figma_comments._META.update({web: ("design", "Design"), board: ("board", "Board")})    # no file-name read
    try:
        listed = list_lines(text)
        got = []
        show_stale(r, out=got.append, texts={"d.md": text})
        g = globals()
        kept_shown, g["shown"] = g["shown"], lambda t, key=None: t
        try:
            bare = list_lines(text)
        finally:
            g["shown"] = kept_shown
    finally:
        kit_config.ado = kept_ado
        figma_comments._META.clear()
        figma_comments._META.update(kept_meta)
    printed = "\n".join(listed + got)
    held = [ln for ln in got if " d.md:" in ln]
    cut = [ln for ln in got if "CUT ROW GONE" in ln]
    case("list and stale link each node in the file its section or Cut cell names, and each #1234",
         len(held) == 3 and len(cut) == 2
         and all(f"/design/{web}/Design?node-id=5100-51001" in x and "/_workitems/edit/4820/" in x
                 for x in (listed[0], held[0]))
         and all(f"/board/{board}/" in x and "node-id=5200-52001" in x for x in (listed[1], held[1]))
         and any("/_workitems/edit/4895/" in ln and "has an owner, A" in ln for ln in got)
         and f"/design/{web}/Design?node-id=6900-81001" in cut[0])
    case("a node in a section or Cut cell that names no file stays bare, and nothing else does",
         [i for _, i in bare_ids.unlinked(printed)] == ["5300:53001", "5300:53001", "11900:113001"])
    s = MDLINK.sub(r"\1", head)
    case("the 80-character cut drops the id it would split, and a markdown link is its label, not half a URL",
         s.index("12900:17001") + len("12900:17") < 80 < s.index("12900:17001") + len("12900:17001")
         and "12900" not in printed and "](" not in printed and "the thread" in listed[0])
    case("show_stale prints r and leaves it as it was (the JSON stale writes)", r == before)
    case("planted break: printed without links, the design and board drafts name their nodes bare",
         [i for _, i in bare_ids.unlinked("\n".join(bare))] == ["5100:51001", "5100:51001", "#4820", "5200:52001",
                                                                 "5200:52001", "#4895", "5300:53001"])


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    if args[:1] in (["selftest"], ["--selftest"]):
        sys.exit(__import__("kit_config").run_isolated(selftest))
    if args[:1] == ["stale"]:
        import json
        rest, js = args[1:], None
        if "--json" in rest:
            k = rest.index("--json")
            js, rest = rest[k + 1], rest[:k] + rest[k + 2:]
        paths = [x for x in rest if not x.startswith("--")] or [x for x in (drafts_path(), outbound_path()) if x]
        if not paths:
            print("drafts_store.py: not configured: name the files, or set $FIGMA_DRAFTS or figma.drafts (the drafts "
                  "file) and $OUTBOUND_DRAFTS or drafts.outbound (the outbound file)")
            sys.exit(2)
        if "--structure" in rest:
            found = []
            for p in paths:
                found += structure(open(p, encoding="utf-8").read(), p)
            print(f"structure: {len(found)} problem{'s' * (len(found) != 1)} in {len(paths)} file(s)")
            for name, line, rule, words in found:
                print(shown(f"  {rule:8} {name}:{line}  {words}"))
            sys.exit(1 if found else 0)
        r = stale(paths, figma="--figma" in rest)
        texts = {}
        for p in paths:
            try:
                texts[os.path.basename(p)] = open(p, encoding="utf-8").read()
            except OSError:
                pass        # stale() has named it as not read
        show_stale(r, texts=texts)
        if js:
            _write(js, json.dumps(dict(r, line=count_line(r)), indent=1, default=list))
        sys.exit(stale_exit(r))
    if args[:1] == ["list"]:
        path = args[1] if len(args) > 1 else drafts_path()
        if not path:
            print("drafts_store.py: not configured: set $FIGMA_DRAFTS or figma.drafts, or name the file")
            sys.exit(2)
        for ln in list_lines(open(path, encoding="utf-8").read()):
            print(ln)
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
