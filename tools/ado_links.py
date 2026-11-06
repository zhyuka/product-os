#!/usr/bin/env python3
"""ado_links.py - one rule for ADO work-item ids: find the ones a text leaves bare, and link them.

    python ado_links.py scan <file.md>...         each bare id, with its line; exit 1 if any
    python ado_links.py link <file.md>... [--dry-run]
                                                  each bare id becomes a markdown link to its item;
                                                  nothing else in the file changes
    python ado_links.py census [--json F]         ids, linked, bare and skipped, place by place
    python ado_links.py --selftest

In Python: md_scan/md_link for markdown, html_scan/html_link for ADO's HTML fields and comments,
candidate_ids(text) for the ids a writer should check exist, known_ids() for the project's ids.

WHY THIS EXISTS. ADO links nothing by itself. In the rendered page, a bare #1234 in a Description,
a bare #1234 in a comment posted over REST, and ADO's own "Copied from #1234" comment all show as
plain text; only an anchor is a link. So the writers (ado_write.py, ado.py new) link through here,
`scan` flags a doc that leaves one bare, and the census counts what is left. The anchor is the
plain one, <a href=".../_workitems/edit/N/">#N</a>, which keeps the text as written; the web
editor's data-vss-mention form renders a chip with the item's title.

CONFIG (kit_config.py). ado.org and ado.project build each link; unset, `scan` and `link` exit 2
naming the key. For the census and for which files a rewrite leaves alone:
  ado_links.root          the folder the places below are relative to (default workspace.root,
                          else the folder you run in)
  ado_links.places        folders the census walks (default: the root itself)
  ado_links.records       path fragments of records: gate fixtures, benchmark and experiment
                          records, copies of old skill versions, whose text is evidence
  ado_links.stores        {"<path prefix>": "<why>"} for stores a tool writes and parses
  ado_links.plain_quotes  path endings of markdown files whose blockquotes are posted as plain
                          text (default: the figma.drafts file, whose quotes go out as comments)

WHAT COUNTS AS AN ID
  #1234 or #12345, not right after a letter, digit, _, /, &, # or ! (so not AB#1234, a path, an
  entity or a colour run), and not right after "PR" or "MR".
  A 4-5 digit number right after a work-item word, with the list that follows it: item, story, task,
  bug, feature, epic, ticket, work item, ADO, PBI, parent, child, WI ("Tasks 9894, 9895 and 9897");
  and the list after a #1234 ("#9894, 9895 and 9897").
  Only an id the project holds is linked (known_ids(), or the live check a writer passes); any other
  is reported as "not an item", since it is deleted, in another project, or not an id at all.
WHAT COUNTS AS LINKED
  The id inside a link to its own _workitems/edit/<id> URL: a markdown link, an <a>, or the URL bare.
WHAT IS LEFT ALONE, in markdown: front matter, fenced code, HTML comments, a link's label or URL
  (another link's label is reported "other-link"), HTML tags, reference definitions, and a code span
  unless it holds only "#1234" (then the span is linked whole). In HTML: anything inside <a>, <code>,
  <pre>, <style> or <script>, and attribute values. A markdown file's blockquote lines are left too
  where the file names them plain text (ado_links.plain_quotes: Figma comment drafts, posted as
  plain text, where a markdown link shows its syntax).
WHAT THE CENSUS AND `link` LEAVE OUT: _archive, _retired, node_modules, dist and .git folders, files
  that say they are generated, records (ado_links.records), since editing them changes the evidence
  they hold, and stores (ado_links.stores), whose lines a tool parses and whose entries change
  through that tool.

BLIND TO an id written as a 3-digit number, one spelled out, an id followed by
  a letter (#1234a), and a 4-5 digit number in a work-item word's company that is not an id (counted
  only when the project holds that number). A "#1234" PR number of a repo whose PRs share the range is
  read as an item unless "PR" precedes it.

Exit: scan 0 none bare, 1 some bare, 2 a file could not be read; link 0 written or nothing to do,
1 a write was refused (the check below failed), 2 unreadable; scan and link 2 also when ado.org or
ado.project is unset; census 0; selftest 0 all pass.
"""
import argparse
import html as _html
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import kit_config

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def url(wid, org=None, project=None):
    return kit_config.ado_url(wid, org, project)


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "unset"


def cache_path(org=None, project=None):
    """ado_rest.py's cache for the project (its CACHE), without importing ado_rest."""
    if org is None and project is None:
        org, project = kit_config.ado()
    return os.path.join(os.path.expanduser("~"), ".cache", kit_config.NAME, "ado",
                        f"{_slug((org or '').rsplit('/', 1)[-1])}--{_slug(project)}.json")


def known_ids(path=None):
    """The ids of every item in the project, from ado_rest.py's cache (`ado_rest.py pull`); None when
    it can't be read, and then every id-shaped match counts."""
    try:
        with open(path or cache_path(), encoding="utf-8") as fh:
            return {int(k) for k in json.load(fh)["items"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


# The one #1234 pattern: bare_ids.py counts session text with it too (its ADO).
HASH_TOKEN = re.compile(r"(?<![\w/&#!])#\d{4,5}(?!\w)")
HASH = re.compile(r"(?<![\w/&#!])#(\d{4,5})(?!\w)")
_WORDS = (r"ado|items?|stor(?:y|ies)|tasks?|bugs?|features?|epics?|tickets?|work[ -]items?|pbis?"
          r"|parents?|child(?:ren)?|wi")
_SP = r"(?:\s|&nbsp;|&#160;)"
_ID = r"#?\d{4,5}(?!\w|[-./:]\d)"   # never a date's year, a decimal or a time
WORD = re.compile(rf"(?i)\b(?:{_WORDS}){_SP}*:?{_SP}*({_ID}(?:{_SP}*(?:,{_SP}*and\b|,{_SP}*or\b|,|/|&amp;|&|\band\b|\bor\b)"
                  rf"{_SP}*{_ID})*)")
NUM = re.compile(r"#?(\d{4,5})(?!\w|[-./:]\d)")
# The list after a #1234 names items too: "#9894, 9895 and 9897".
TAIL = re.compile(rf"(?<![\w/&#!])#\d{{4,5}}(?!\w)((?:{_SP}*(?:,{_SP}*and\b|,{_SP}*or\b|,|/|&amp;|&|\band\b|\bor\b){_SP}*{_ID})+)")
PR_BEFORE = re.compile(r"(?i)(?:\bPRs?|\bMRs?|pull request|merge request)\s*$")
LINKED = re.compile(r"_workitems/edit/(\d+)")


def candidates(text, known=None):
    """[(start, end, id, form)] for each work-item id in plain text. form is 'hash' (#1234) or
    'word' (item 1234); 'pr' for a #1234 right after "PR"; 'unknown-…' for an id the project
    doesn't hold, when known is given."""
    out = {}
    for m in HASH.finditer(text):
        wid, form = int(m.group(1)), "hash"
        if PR_BEFORE.search(text[max(0, m.start() - 16):m.start()]):
            form = "pr"
        elif known is not None and wid not in known:
            form = "unknown-hash"
        out[m.start()] = (m.start(), m.end(), wid, form)
    for m in list(WORD.finditer(text)) + list(TAIL.finditer(text)):
        for n in NUM.finditer(m.group(1)):
            s, e = m.start(1) + n.start(), m.start(1) + n.end()
            if any(a <= s < b for a, b, _, _ in out.values()):
                continue
            wid = int(n.group(1))
            form = "hash" if n.group(0).startswith("#") else "word"
            if known is not None and wid not in known:
                form = "unknown-" + form
            out[s] = (s, e, wid, form)
    return [out[k] for k in sorted(out)]


def candidate_ids(text):
    """Every id-shaped number a text cites as an item, for a writer's live existence check."""
    return {w for _, _, w, f in candidates(text) if f != "pr"}


# ------------------------------------------------------------------------------------- markdown

FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
SPAN = re.compile(
    r"(?P<code>(?P<tick>`+)(?P<codebody>.+?)(?P=tick))"
    r"|(?P<mdlink>!?\[(?P<label>(?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]\((?P<href>[^)\s]*)(?:\s+\"[^\"]*\")?\))"
    r"|(?P<anchor><a\b[^>]*?href=[\"']?(?P<ahref>[^\"'>\s]*)[^>]*>(?P<alabel>.*?)</a>)"
    r"|(?P<auto><https?://[^>\s]+>)"
    r"|(?P<url>https?://[^\s)>\]\"'`]+)"
    r"|(?P<tag></?[A-Za-z][^>\n]*>)",
    re.I)
REFDEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S+")
QUOTE = re.compile(r"^\s{0,3}>")


def _regions(text):
    """(kind, start, end) of what holds no prose: front matter, fenced code, HTML comments."""
    out, lines, starts, pos = [], text.splitlines(keepends=True), [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln)
    starts.append(pos)
    i = 0
    if lines and lines[0].rstrip("\r\n") == "---":
        for j in range(1, len(lines)):
            if lines[j].rstrip("\r\n") in ("---", "..."):
                out.append(("frontmatter", 0, starts[j + 1]))
                i = j + 1
                break
    fence = None
    while i < len(lines):
        m = FENCE.match(lines[i])
        if fence is None and m:
            fence = (m.group(1)[0], len(m.group(1)), starts[i])
        elif fence is not None and m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                and not lines[i].strip()[len(m.group(1)):].strip():
            out.append(("fence", fence[2], starts[i + 1]))
            fence = None
        i += 1
    if fence is not None:
        out.append(("fence", fence[2], starts[-1]))
    for m in re.finditer(r"<!--.*?-->", text, re.S):
        if not any(a <= m.start() < b for _, a, b in out):
            out.append(("comment", m.start(), m.end()))
    return sorted(out, key=lambda r: r[1])


def md_scan(text, known=None, plain_quotes=False, to=None):
    """Every work-item id in a markdown text, as dicts: line, start, end, id, form, status. status
    is 'bare' (to link; it carries 'repl', the text for [start:end]), 'linked', or why it is left:
    frontmatter, fence, comment, code, other-link, html, refdef, plain-text, pr, unknown."""
    hits, to = [], to or url
    line_of = lambda p: text.count("\n", 0, p) + 1
    regions = _regions(text)
    for kind, a, b in regions:
        for s, e, wid, form in candidates(text[a:b], known):
            hits.append(dict(line=line_of(a + s), start=a + s, end=a + e, id=wid, form=form, status=kind))
    gaps, pos = [], 0
    for _, a, b in regions:
        if a > pos:
            gaps.append((pos, a))
        pos = max(pos, b)
    if pos < len(text):
        gaps.append((pos, len(text)))
    for ga, gb in gaps:
        for lm in re.finditer(r"[^\n]+", text[ga:gb]):
            ls, line = ga + lm.start(), lm.group(0)
            left = "refdef" if REFDEF.match(line) else "plain-text" if plain_quotes and QUOTE.match(line) else None
            if left:
                for s, e, wid, form in candidates(line, known):
                    hits.append(dict(line=line_of(ls), start=ls + s, end=ls + e, id=wid, form=form, status=left))
                continue
            cur = 0
            for sm in SPAN.finditer(line):
                _prose(line[cur:sm.start()], ls + cur, known, hits, line_of, to)
                _span(sm, ls, known, hits, line_of, to)
                cur = sm.end()
            _prose(line[cur:], ls + cur, known, hits, line_of, to)
    return sorted(hits, key=lambda h: h["start"])


def _left(form):
    return "pr" if form == "pr" else "unknown"


def _prose(seg, base, known, hits, line_of, to):
    for s, e, wid, form in candidates(seg, known):
        h = dict(line=line_of(base + s), start=base + s, end=base + e, id=wid, form=form)
        if form in ("hash", "word"):
            h.update(status="bare", repl=f"[{seg[s:e]}]({to(wid)})")
        else:
            h["status"] = _left(form)
        hits.append(h)


def _span(sm, base, known, hits, line_of, to):
    s0, e0 = base + sm.start(), base + sm.end()
    if sm.group("code"):
        found = candidates(sm.group("codebody"), known)
        whole = len(found) == 1 and re.fullmatch(r"\s*#\d{4,5}\s*", sm.group("codebody"))
        for s, e, wid, form in found:
            h = dict(line=line_of(s0), start=s0, end=e0, id=wid, form=form, status="code")
            if whole and form == "hash":
                h.update(status="bare", repl=f"[{sm.group(0)}]({to(wid)})")
            elif form not in ("hash", "word"):
                h["status"] = _left(form)
            hits.append(h)
        return
    if sm.group("mdlink") or sm.group("anchor"):
        label = sm.group("label") if sm.group("mdlink") else sm.group("alabel")
        to = {int(x) for x in LINKED.findall(sm.group("href") if sm.group("mdlink") else sm.group("ahref") or "")}
        found = candidates(label or "", known)
        for s, e, wid, form in found:
            hits.append(dict(line=line_of(s0), start=s0, end=e0, id=wid, form=form,
                             status="linked" if wid in to else "other-link"))
        for wid in to - {w for _, _, w, _ in found}:
            hits.append(dict(line=line_of(s0), start=s0, end=e0, id=wid, form="url", status="linked"))
        return
    if sm.group("auto") or sm.group("url"):
        for wid in LINKED.findall(sm.group(0)):
            hits.append(dict(line=line_of(s0), start=s0, end=e0, id=int(wid), form="url", status="linked"))
        return
    for s, e, wid, form in candidates(sm.group(0), known):
        hits.append(dict(line=line_of(s0), start=s0, end=e0, id=wid, form=form, status="html"))


def _apply(text, hits):
    out, cur = [], 0
    for h in hits:
        if h["status"] == "bare" and h.get("repl"):
            out += [text[cur:h["start"]], h["repl"]]
            cur = h["end"]
    return "".join(out + [text[cur:]])


def md_link(text, known=None, plain_quotes=False, to=None):
    """(new text, hits): each bare id replaced by a markdown link to its item, every other byte kept."""
    hits = md_scan(text, known, plain_quotes, to)
    return _apply(text, hits), hits


def unlink_md(text):
    """text with every markdown link to a work item put back to its label: md_link's inverse, which
    `link` uses to prove a rewrite changed nothing but the ids."""
    return re.sub(r"\[([^\[\]\n]*)\]\((?:https?://[^)\s]*_workitems/edit/\d+/?)\)", r"\1", text)


# ------------------------------------------------------------------------------------- ADO HTML

TOKEN = re.compile(r"<!--.*?-->|<[^>]*>", re.S)
SKIP_TAGS = ("code", "pre", "style", "script")
MDLINK = re.compile(r"\[((?:[^\[\]\n<>]|\[[^\[\]\n<>]*\])+)\]\((https?://[^)\s\"<>]+)\)")


def _walk(value, on_text):
    """Call on_text(start, end, anchor, in_code) for each text run of an HTML value. anchor is the
    set of item ids the enclosing <a> links to, or None outside one."""
    stack, cur = [], 0
    for tm in TOKEN.finditer(value):
        if tm.start() > cur:
            a = next((x for x in reversed(stack) if x[0] == "a"), None)
            on_text(cur, tm.start(), a[1] if a else None, any(x[0] in SKIP_TAGS for x in stack))
        tag = tm.group(0)
        cur = tm.end()
        if tag.startswith("<!--"):
            continue
        m = re.match(r"<\s*(/?)\s*([A-Za-z0-9]+)", tag)
        if not m:
            continue
        closing, name = m.group(1) == "/", m.group(2).lower()
        if name == "a" or name in SKIP_TAGS:
            if closing:
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == name:
                        del stack[i]
                        break
            elif not tag.endswith("/>"):
                href = re.search(r"href\s*=\s*[\"']?([^\"'>\s]*)", tag, re.I)
                stack.append((name, {int(x) for x in LINKED.findall(href.group(1) if href else "")}))
    if cur < len(value):
        a = next((x for x in reversed(stack) if x[0] == "a"), None)
        on_text(cur, len(value), a[1] if a else None, any(x[0] in SKIP_TAGS for x in stack))


def html_scan(value, known=None, to=None):
    """Every work-item id in an ADO HTML value, as dicts: start, end, id, form, status, where status
    is 'bare' (with 'repl'), 'linked', 'other-link', 'code', 'attr', 'pr' or 'unknown'. An <a> that
    links an item without naming it counts that item as linked once."""
    hits, to = [], to or url
    if not value:
        return hits
    named = []

    def on_text(a, b, anchor, code):
        seg = value[a:b]
        for s, e, wid, form in candidates(seg, known):
            h = dict(start=a + s, end=a + e, id=wid, form=form)
            if anchor is not None:
                h["status"] = "linked" if wid in anchor else "other-link"
                named.append(wid)
            elif code:
                h["status"] = "code"
            elif form in ("hash", "word"):
                h.update(status="bare", repl=f'<a href="{to(wid)}">{seg[s:e]}</a>')
            else:
                h["status"] = _left(form)
            hits.append(h)

    _walk(value, on_text)
    for tm in TOKEN.finditer(value):
        tag = tm.group(0)
        if re.match(r"<\s*a\b", tag, re.I):
            for wid in {int(x) for x in LINKED.findall(tag)}:
                if wid not in named:
                    hits.append(dict(start=tm.start(), end=tm.end(), id=wid, form="url", status="linked"))
        elif not tag.startswith("<!--"):
            for s, e, wid, form in candidates(tag, known):
                hits.append(dict(start=tm.start() + s, end=tm.start() + e, id=wid, form=form, status="attr"))
    return sorted(hits, key=lambda h: h["start"])


def md_links_to_anchors(value):
    """An HTML value with each markdown link in its text, [label](https://…), made an <a>: ADO shows
    the markdown itself, so a line copied from a doc into a comment would read as [#9811](https://…)."""
    out, cur = [], 0
    spans = []
    _walk(value, lambda a, b, anchor, code: spans.append((a, b)) if anchor is None and not code else None)
    for a, b in spans:
        out.append(value[cur:a])
        out.append(MDLINK.sub(lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}">{m.group(1)}</a>',
                              value[a:b]))
        cur = b
    return "".join(out + [value[cur:]])


def html_link(value, known=None, to=None):
    """(new value, hits): markdown links made anchors, then each bare id the project holds linked."""
    if not value:
        return value, []
    value = md_links_to_anchors(value)
    hits = html_scan(value, known, to)
    return _apply(value, hits), hits


def summary(hits, link_line):
    """One line for a writer to print: what it linked and what it left. link_line adds URLs."""
    done = [h["id"] for h in hits if h["status"] == "bare"]
    unknown = sorted({h["id"] for h in hits if h["status"] == "unknown"})
    if not done and not unknown:
        return ""
    parts = []
    if done:
        parts.append(f"linked {len(done)} bare id(s): " + ", ".join(f"#{w}" for w in dict.fromkeys(done)))
    if unknown:
        parts.append("left bare, not an item of this project: " + ", ".join(str(w) for w in unknown))
    return link_line("  " + "; ".join(parts))


# ------------------------------------------------------------------------------------- files

def _cfg(key, default=None):
    v = kit_config.get("ado_links", key)
    return default if v is None else v


def _x(p):
    return os.path.abspath(os.path.expanduser(str(p)))


def _list(v):
    """A setting that holds one string or a list of them, as a tuple of strings."""
    return (v,) if isinstance(v, str) else tuple(str(x) for x in v) if isinstance(v, (list, tuple)) else ()


def _here():
    """kit_config.project_dir(), or None inside the plugin's own folder, where main refuses."""
    try:
        return kit_config.project_dir()
    except kit_config.InPluginFolder:
        return None


# The folder the census places and the record and store fragments are relative to. None inside the
# plugin's own folder with no root set: the census and the commands refuse there.
_ROOT = _cfg("root") or kit_config.get("workspace", "root") or _here()
ROOT = _x(_ROOT) if _ROOT else None
SKIP_DIRS = {"_archive", "_retired", "node_modules", "dist", ".git", ".astro", ".venv", "__pycache__"}
GENERATED = re.compile(r"(?i)generated (?:file|by)\b|do not (?:hand-)?edit")
# Records: what a run, a gate or an experiment produced or was fed. Editing one changes the evidence.
RECORDS = _list(_cfg("records"))
# Files whose blockquotes are posted as plain text, where a markdown link shows its syntax: by default
# the Figma comment drafts file (figma.drafts or $FIGMA_DRAFTS), whose quotes go out as comments.
_DRAFTS = os.environ.get("FIGMA_DRAFTS") or kit_config.get("figma", "drafts")
PLAIN_QUOTES = _list(_cfg("plain_quotes") or _DRAFTS)


def _rel(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not ROOT:
        return p
    d = ROOT.replace("\\", "/").rstrip("/") + "/"
    return p[len(d):] if p.startswith(d) else p


# Stores a tool writes and parses: a hand edit there goes around the tool. {"<path prefix>": "<why>"}
_STORES = _cfg("stores")
STORES = {str(k): str(v) for k, v in _STORES.items()} if isinstance(_STORES, dict) else {}


def left_out(path, text=None):
    """Why a file is out of the rule ('archive', 'record', a store's why, 'generated'), or None."""
    rel = _rel(path)
    if set(rel.split("/")[:-1]) & SKIP_DIRS:
        return "archive"
    if any(r in "/" + rel for r in RECORDS):
        return "record"
    for frag, why in STORES.items():
        if rel.startswith(frag):
            return why
    if text is not None and GENERATED.search(text[:600]):
        return "generated"
    return None


def plain_quotes(path):
    ap, rel = os.path.abspath(path), _rel(path)
    return any(ap == _x(p) or rel.endswith(str(p).replace("\\", "/")) for p in PLAIN_QUOTES)


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ado_links.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def link_file(path, known, dry_run=False):
    """(linked count, hits, refusal or None). The rewrite goes out only when putting every new link
    back to its label gives the original bytes and it adds no U+FFFD."""
    with open(path, encoding="utf-8", newline="") as fh:
        old = fh.read()
    new, hits = md_link(old, known, plain_quotes(path))
    n = sum(1 for h in hits if h["status"] == "bare")
    if not n:
        return 0, hits, None
    if unlink_md(new) != unlink_md(old):
        return 0, hits, "putting the links back to their labels does not give the original text"
    if new.count("\ufffd") != old.count("\ufffd"):
        return 0, hits, "the rewrite changes the number of U+FFFD characters"
    if not dry_run:
        _write_atomic(path, new)
        with open(path, encoding="utf-8", newline="") as fh:
            if fh.read() != new:
                return 0, hits, "the file reads back different from what was written"
    return n, hits, None


def _walk_md(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for f in sorted(fns):
            if f.endswith(".md"):
                yield os.path.join(dp, f)


# Folders the census walks, each relative to ROOT unless absolute (ado_links.places; default the root).
PLACES = _list(_cfg("places")) or (".",)


def census(known=None, places=None, root=None, cache=None):
    """{place: {total, linked, bare, skipped: {why: n}, files_with_bare}} over each place's .md, then
    the ADO cache's fields and comments by author. A place that isn't a folder reads "did not run"."""
    known = known_ids(cache) if known is None else known
    root = root or ROOT or kit_config.project_dir()     # refuses inside the plugin's own folder
    out = {}
    for place in places or PLACES:
        place = os.path.expanduser(place)
        where = place if os.path.isabs(place) else os.path.normpath(os.path.join(root, place))
        name = os.path.basename(where) if os.path.isabs(place) or place in (".", "") else place
        if not os.path.isdir(where):
            out[name] = f"did not run: {where} is not a folder (ado_links.places)"
            continue
        c = {"total": 0, "linked": 0, "bare": 0, "skipped": {}, "files_with_bare": 0}
        for p in _walk_md(where):
            try:
                text = open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                c["skipped"]["unreadable file"] = c["skipped"].get("unreadable file", 0) + 1
                continue
            why = left_out(p, text)
            hits = md_scan(text, known, plain_quotes(p))
            bare = 0
            for h in hits:
                c["total"] += 1
                st = h["status"] if h["status"] == "linked" else (why or h["status"])
                if st in ("linked", "bare"):
                    c[st] += 1
                    bare += st == "bare"
                else:
                    c["skipped"][st] = c["skipped"].get(st, 0) + 1
            c["files_with_bare"] += bool(bare)
        out[name] = c
    try:
        d = json.load(open(cache or cache_path(), encoding="utf-8"))
    except (OSError, ValueError):
        out["ADO"] = "did not run: the cache could not be read (ado_rest.py pull)"
        return out
    for ref in ("System.Description", "Microsoft.VSTS.Common.AcceptanceCriteria", "Microsoft.VSTS.TCM.ReproSteps",
                "Microsoft.VSTS.TCM.SystemInfo"):
        c = {"total": 0, "linked": 0, "bare": 0, "skipped": {}, "items_with_bare": 0}
        for it in d.get("items", {}).values():
            hits = html_scan((it.get("fields") or {}).get(ref) or "", known)
            for h in hits:
                c["total"] += 1
                if h["status"] in ("linked", "bare"):
                    c[h["status"]] += 1
                else:
                    c["skipped"][h["status"]] = c["skipped"].get(h["status"], 0) + 1
            c["items_with_bare"] += any(h["status"] == "bare" for h in hits)
        out["ADO " + ref.rsplit(".", 1)[-1]] = c
    by = {}
    for cs in d.get("comments", {}).values():
        for cm in cs:
            c = by.setdefault(cm.get("by") or "?", {"total": 0, "linked": 0, "bare": 0, "skipped": {},
                                                    "comments_with_bare": 0})
            hits = html_scan(cm.get("text") or "", known)
            for h in hits:
                c["total"] += 1
                if h["status"] in ("linked", "bare"):
                    c[h["status"]] += 1
                else:
                    c["skipped"][h["status"]] = c["skipped"].get(h["status"], 0) + 1
            c["comments_with_bare"] += any(h["status"] == "bare" for h in hits)
    for who, c in sorted(by.items(), key=lambda x: -x[1]["total"]):
        out[f"ADO comments by {who}"] = c
    return out


def section(known=None, places=None, root=None, cache=None):
    """Lines for the daily digest: bare ids left in docs and in ADO, place by place. A census that
    could not run says so; it never reads as zero."""
    try:
        r = census(known, places, root, cache)
    except Exception as e:
        return [f"- did not run ({type(e).__name__}: {e})"]
    out = []
    for place, c in r.items():
        if isinstance(c, str):
            out.append(f"- {place}: {c}")
        elif c["bare"] or place.startswith("ADO"):
            out.append(f"- {place}: {c['bare']} bare of {c['total']} ids, {c['linked']} linked")
    return (out or ["- none bare"]) + ["  (`ado_links.py link <file>` links a doc; ado_write.py links what it writes)"]


# ------------------------------------------------------------------------------------- selftest

def selftest():
    """Planted cases, offline, against a planted org and project, so it runs with no settings."""
    g = globals()
    kept = {k: g[k] for k in ("url", "ROOT", "RECORDS", "STORES", "PLAIN_QUOTES")}
    g["url"] = lambda wid, org=None, project=None: kit_config.ado_url(wid, "https://dev.azure.com/o", "p")
    try:
        return _selftest()
    finally:
        g.update(kept)


def _selftest():
    fails = []
    U = lambda w: url(w)

    def chk(name, ok, got=""):
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        got {got!r}"))
        if not ok:
            fails.append(name)

    # Planted ids only: work-item numbers no real tracker is meant to hold.
    K = {3247, 3894, 3895, 3897, 4511, 4513, 4526}
    md_cases = [  # (text, linked text)
        ("see #4511 and Story 4513", f"see [#4511]({U(4511)}) and Story [4513]({U(4513)})"),
        ("Tasks 3894, 3895 and 3897 hold", f"Tasks [3894]({U(3894)}), [3895]({U(3895)}) and [3897]({U(3897)}) hold"),
        ("item #4526's AC", f"item [#4526]({U(4526)})'s AC"),
        ("`#4511` alone", f"[`#4511`]({U(4511)}) alone"),
        (f"[#4511]({U(4511)}) linked, {U(3247)} bare url", None),
        ("colour #333333, port 6543, PR #4511, AB#4511, file.py:4511, comment #3877144741, x/#4511", None),
        ("#9999 is no item, and item 6543 neither", None),
        ("---\nado: 4511\n---\n```\n#4511\n```\n<!-- #4511 -->\n`ado_write.py field 4511 x`", None),
        ("[thread #4511](https://www.figma.com/design/K/W?node-id=1-2) <a href=\"x\">#4511</a>", None),
        ("> FIX: from #4511", f"> FIX: from [#4511]({U(4511)})"),
        ("#3894, 3895 and 3897 hold", f"[#3894]({U(3894)}), [3895]({U(3895)}) and [3897]({U(3897)}) hold"),
        ("#4511, 2026 plans", f"[#4511]({U(4511)}), 2026 plans"),
        ("#4511, 4513-11-04 and Task 4526.5", f"[#4511]({U(4511)}), 4513-11-04 and Task 4526.5"),
    ]
    for text, want in md_cases:
        got, _ = md_link(text, K)
        chk(f"md_link {text[:58]!r}", got == (want if want is not None else text), got)
        chk(f"  and unlink_md gives the original back", unlink_md(got) == unlink_md(text), unlink_md(got))
    got, hits = md_link("> FIX: from #4511\nbody #4511", K, plain_quotes=True)
    chk("plain_quotes leaves a quote line, links the rest",
        got == f"> FIX: from #4511\nbody [#4511]({U(4511)})" and hits[0]["status"] == "plain-text", got)
    chk("a link's own id is linked, another link's label is other-link, a tag's is html",
        [h["status"] for h in md_scan(f"[#4511]({U(4511)}) [see #4513](https://x.example/) <b data-x=\"#4526\">", K)]
        == ["linked", "other-link", "html"], [h["status"] for h in md_scan(f"[#4511]({U(4511)}) [see #4513](https://x.example/) <b data-x=\"#4526\">", K)])
    chk("a list stops at the first number that isn't an item", [h["id"] for h in md_scan("Tasks 3894, 3895 and 3897", K)]
        == [3894, 3895, 3897])
    chk("unknown ids are reported, not linked",
        [h["status"] for h in md_scan("#9999 and Task 6543", K)] == ["unknown", "unknown"])
    chk("with no cache every id-shaped match counts", md_link("#9999", None)[0] == f"[#9999]({U(9999)})")

    h_in = (f'<div>See #4511 and <a href="{U(3247)}">#3247</a>, Story&nbsp;4513, <code>#4511</code>, '
            f'<span style="color:#1234">PR #4526</span> [#4526]({U(4526)})</div>')
    h_want = (f'<div>See <a href="{U(4511)}">#4511</a> and <a href="{U(3247)}">#3247</a>, '
              f'Story&nbsp;<a href="{U(4513)}">4513</a>, <code>#4511</code>, <span style="color:#1234">PR #4526</span> '
              f'<a href="{U(4526)}">#4526</a></div>')
    got, hits = html_link(h_in, K)
    chk("html_link links text, leaves anchors, code, attributes and PR numbers, makes a markdown link an <a>",
        got == h_want, got)
    chk("html_link is idempotent", html_link(got, K)[0] == got, html_link(got, K)[0])
    chk("html_scan counts the old anchor as linked", sum(h["status"] == "linked" for h in html_scan(h_in, K)) == 1)
    chk("candidate_ids reads every id-shaped number but a PR's",
        candidate_ids("#4511, Task 9999, PR #3229, #333333") == {4511, 9999})
    s = summary(html_link("#4511 and #9999", K)[1], lambda t: t)
    chk("summary names what it linked and what it left", "#4511" in s and "not an item" in s and "9999" in s, s)

    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "doc.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# Notes\n\nclosed #4511 — café\r\nnext line #4513\n")
        n, _, why = link_file(p, K)
        body = open(p, encoding="utf-8", newline="").read()
        chk("link_file writes only the ids, CRLF and non-ASCII kept",
            n == 2 and why is None and body == f"# Notes\n\nclosed [#4511]({U(4511)}) — café\r\nnext line [#4513]({U(4513)})\n",
            (n, why, body))
        n2, _, _ = link_file(p, K)
        chk("a second run changes nothing", n2 == 0)
        real = globals()["md_link"]
        globals()["md_link"] = lambda t, k=None, q=False, to=None: (t.replace("Notes", "Notez") + "#4511", [{"status": "bare"}])
        try:
            before = open(p, encoding="utf-8", newline="").read()
            n3, _, why3 = link_file(p, K)
        finally:
            globals()["md_link"] = real
        chk("known bad: a rewrite that changes more than the ids is refused and nothing is written",
            n3 == 0 and why3 and open(p, encoding="utf-8", newline="").read() == before, (n3, why3))
        os.makedirs(os.path.join(tmp, "docs", "_archive"))
        os.makedirs(os.path.join(tmp, "docs", "reviews", "gate-records"))
        for rel, text in (("docs/a.md", "#4511 and #4513\n"), ("docs/_archive/b.md", "#4511\n"),
                          ("docs/reviews/gate-records/c.md", "#4511\n"), ("docs/d.md", "<!-- GENERATED by x -->\n#4511\n")):
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        globals().update(ROOT=tmp, RECORDS=("docs/reviews/gate-records/",), STORES={"knowledge/": "kb store"},
                         PLAIN_QUOTES=("reviews/drafts.md",))
        r = census(K, ("docs", "no-such-folder"), tmp, os.path.join(tmp, "none.json"))
        c = r["docs"]
        chk("census: archive not walked; a record and a generated file are skipped, never bare",
            c["bare"] == 2 and c["skipped"] == {"record": 1, "generated": 1} and c["total"] == 4, c)
        chk("census: a place that isn't a folder reads did not run, never zero",
            str(r.get("no-such-folder", "")).startswith("did not run"), r.get("no-such-folder"))
        chk("census: an unreadable cache reads did not run for ADO", str(r.get("ADO", "")).startswith("did not run"),
            r.get("ADO"))
        chk("a store is left out with its why", left_out(os.path.join(tmp, "knowledge", "x.md")) == "kb store"
            and left_out(os.path.join(tmp, "docs", "a.md")) is None)
        chk("plain_quotes matches a configured path ending, and only that file",
            plain_quotes(os.path.join(tmp, "reviews", "drafts.md")) and not plain_quotes(os.path.join(tmp, "docs", "a.md")))
    print(f"\nado_links selftest: {'all pass' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", nargs="?", choices=("scan", "link", "census"))
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return kit_config.run_isolated(selftest)
    if ROOT is None:               # inside the plugin's own folder, with no root set
        try:
            kit_config.project_dir()
        except kit_config.InPluginFolder as e:
            print(f"ado_links.py: {e}", file=sys.stderr)
            return 2
    if a.cmd in ("scan", "link"):  # each link is built from the org and project: never a guess
        try:
            org, project = kit_config.ado()
            if not org:
                kit_config.need("ado", "org")
            if not project:
                kit_config.need("ado", "project")
        except kit_config.NotConfigured as e:
            print(f"ado_links.py: {e}", file=sys.stderr)
            return 2
    known = known_ids()
    if known is None:
        print(f"note: the ADO cache could not be read ({cache_path()}), so every id-shaped match counts")
    if a.cmd == "census":
        r = census(known)
        for place, c in r.items():
            if isinstance(c, str):
                print(f"{place}: {c}")
                continue
            more = {k: v for k, v in c.items() if k.endswith("_with_bare")}
            print(f"{place}: {c['total']} ids, {c['linked']} linked, {c['bare']} bare, "
                  f"{sum(c['skipped'].values())} skipped {c['skipped']} {more}")
        if a.json:
            with open(a.json, "w", encoding="utf-8") as fh:
                json.dump(r, fh, indent=1)
        return 0
    if not a.paths:
        ap.error("name at least one file")
    rc = 0
    for p in a.paths:
        try:
            text = open(p, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"{p}: cannot read ({e})")
            rc = 2
            continue
        why = left_out(p, text)
        if a.cmd == "scan":
            bare = [h for h in md_scan(text, known, plain_quotes(p)) if h["status"] == "bare"]
            for h in bare:
                print(f"{p}:{h['line']}: bare #{h['id']}  {url(h['id'])}")
            rc = max(rc, 1 if bare and not why else 0)
            if bare and why:
                print(f"{p}: {len(bare)} bare, left: a {why} file")
            continue
        if why:
            print(f"{p}: left alone, a {why} file")
            continue
        n, hits, refused = link_file(p, known, a.dry_run)
        if refused:
            print(f"{p}: REFUSED, {refused}; nothing written")
            rc = max(rc, 1)
        else:
            left = [h for h in hits if h["status"] not in ("bare", "linked")]
            print(f"{p}: {'would link' if a.dry_run else 'linked'} {n}, {sum(h['status'] == 'linked' for h in hits)} "
                  f"already linked, {len(left)} left ({', '.join(sorted({h['status'] for h in left})) or 'none'})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
