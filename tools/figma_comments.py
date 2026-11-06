"""Read-before-you-write gate for Figma comments.

  python figma_comments.py inbox  <file_key> [--since YYYY-MM-DD] [--me "<your Figma handle>"]
  python figma_comments.py nodes  <file_key> <node_id> [<node_id> ...]
  python figma_comments.py check  <file_key> <draft.md>
  python figma_comments.py frame  <file_key> <node_id> [--show-hidden] [--vars]
  python figma_comments.py search <term> [<term> ...] [--file <key> ...]
  python figma_comments.py pins   [--file <key> ...] [--all] [--new] [--lane batch]
  python figma_comments.py stale  [--days 45] [--file <key> ...] [--all] [--new] [--lane batch]

WHY THIS EXISTS. Comments drafted from build notes, without reading the live comments on the file,
repeat threads that are already posted and describe nodes a reply has since changed or deleted. A
skill that SAYS "de-dup against live comments and ground every claim on the live frame" does not
stop that; prose never does. So this is the mechanical version: you cannot honestly draft a comment
until `inbox` and `check` are clean.

  inbox  - every thread touched since --since, newest last, with replies nested under their root and
           an UNANSWERED marker on any reply to one of your own comments that you have not answered,
           in an open thread. A resolved thread with such a reply prints "resolved, not counted"
           and has its own count line (RESOLVED THREADS). Run it first, every time.
  nodes  - every existing comment on specific node ids. Run before drafting a comment on a node:
           if a thread exists, reply in it rather than starting a second one. A comment counts if
           it is pinned to the node, to an ancestor with an offset inside the node's box, or to a
           layer inside the node; each thread prints which. Below that, figma_family.py lists the
           threads on the same layer of every other copy of the node's component, on any page.
           See OFFSET PINS, CHILD LAYERS and OTHER COPIES.
  check  - extracts node ids from a draft markdown and reports which already carry comments, so a
           duplicate is caught before it is posted rather than after. Same matching as `nodes`,
           family block included.
  frame  - pulls a frame and walks it with hidden layers removed, so a finding cannot be measured off
           a node the designer switched off (HIDDEN LAYERS). Prints every paint, each TEXT node's
           characters (not its layer name; EIGHTH FAILURE) and every per-character text run, and
           stamps each node it prints as read: figma_post.py will not post on a node `frame` has
           not printed, or whose frame has changed in Figma since. See FOURTH FAILURE in cmd_frame
           and THE THIRD RULE in figma_post.py.
  search - every thread whose root or any reply holds all the terms, on every known file, resolved
           ones included and marked. Run before drafting a NEW comment: an open thread on the same
           subject can sit on a different node, which `nodes` and `check` cannot see. figma_post.py
           refuses `new` on a file `search` has not covered in the last 30 minutes. See OTHER
           NODES, SAME SUBJECT.
  pins   - your open threads pinned to a node Figma has deleted or that sits under a hidden layer, on
           every known file.
  stale  - your open threads, not FIX notes, with no comment in 45 days, by page: one resolve batch.
           With --new, either one suits a daily audit: it exits 1 only for a thread the last --new
           run did not list, kept in ~/.cache/product-os/figma_comment_flags.json.

Every thread line ends with its permalink, ...?node-id=<node>#<comment id>. A link to the node alone
opens the frame, not the discussion.

The files `search`, `pins` and `stale` cover by default are kit_config's `figma.files` (see
kit_config.py).

HIDDEN LAYERS. A component slot the designer switched off (visible:false) still has a box and
paints, so a finding measured on it is an artifact: a container that hugs its one visible child reads
as overflowing, and text that never renders reads as a contrast bug. On a real frame a quarter of the
nodes can be hidden, so eyeballing the JSON is not good enough. `frame` therefore drops any node with
visible:false on itself or any ancestor before printing, and prints the dropped count so the filter
is visible rather than silent.

The inverse is the point of pulling at all: invisible properties are the high-value read. Variable
bindings, component states, hover and dark-mode values cannot be checked by looking at the canvas.
`--vars` reports the binding behind each fill for exactly that reason. Skip hidden layers, read hidden
properties.

SAME NODE, OTHER SUBJECT. A node match says nothing about whether a thread is on the same subject: a
page frame can carry many unrelated threads, and a comment about one subject posted as a reply into
a thread about another is the result. So `check` never tells you to reply. It prints each existing
thread's opening words and makes you choose, and it warns when a node looks like a page-level
container (3+ root threads), where a new comment is almost always right. A node match is a prompt to
read, not an instruction.

OFFSET PINS. Figma pins a comment made in the UI to a frame plus an offset, and re-pins some REST
comments the same way after they post, so most root comments in a busy file carry a non-zero offset
on an ancestor, and matching only client_meta.node_id prints a silent zero. `nodes` and `check` read
each node's ancestor chain (figma_client.lineage) and also count a comment pinned to an ancestor
whose offset lands inside the node's box. An id the file does not hold prints as not in this file,
never as clear.

OTHER NODES, SAME SUBJECT. An open thread on the same subject can sit on a different node (a card's
container, while the draft cites the card), which `nodes` and `check` cannot see, and `inbox` cuts
at --since. `search` matches the words of every comment, and every thread line carries the link with
its #comment id.

CHILD LAYERS. A thread about a component is often pinned to one of its layers. locate() returns each
node's subtree from the same request, and a comment pinned to any layer in it prints as
"on child <id>".

OTHER COPIES. Copies of one component on different pages each carry their own threads, so a match by
where a comment sits misses the same question asked on another copy. `nodes` and `check` print
figma_family.py's block under every node: the threads on the same layer of any copy of each component
on the node's path. A zero does not print a verdict; it prints what was searched. `check` reads an id
like I10:20;30:40 whole: its last part alone is the layer in the main component, not the one cited.

RESOLVED THREADS. A resolved thread waits on nobody, whoever spoke last. `inbox` marks UNANSWERED
only in an open thread; a resolved thread with such a reply prints "resolved, not counted" in place
of the marker, and the count of those prints on its own line under the UNANSWERED count. A
teammate's reply posted after a resolve is not counted either.

Auth: resolved by figma_auth.py (FIGMA_TOKEN or the OS keychain). Never printed. Run
`python figma_auth.py` to see which source is in play.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import argparse, json, os, re, sys, tempfile, urllib.request, urllib.error

# Windows consoles are cp1252 by default, so ONE non-ASCII glyph raises UnicodeEncodeError and
# aborts the run halfway through the report, and a truncated report reads like a short one.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from collections import defaultdict

import figma_auth
import kit_config

# Figma REST paths; get() sends them through figma_client.py. META_API is /meta (Tier 3): it names
# the file and its editor type as files?depth=1 would, without a Tier 1 call.
API = "/v1/files/{}/comments"
NODES_API = "/v1/files/{}/nodes?ids={}&depth=60"
VARS_API = "/v1/files/{}/variables/local"
META_API = "/v1/files/{}/meta"
# The files `search` covers when no --file is given, {key: (editor, name)}: figma.files in the
# project's .claude/product-os.json (kit_config.py). Any other key is looked up once per run.
KNOWN_FILES = kit_config.figma_files()
_META = dict(KNOWN_FILES)


def token():
    # The environment first, then the OS keychain. See figma_auth.
    return figma_auth.token()


STALE_FIX = "store a new one in FIGMA_TOKEN or the OS keychain; `python figma_auth.py` checks it"


def token_stale(e):
    """(the "token stale" line or None, Figma's body) for an HTTPError, reading its body once. An invalid token
    gets 401 {"status":401,"err":"Invalid token"} on the comments read and on /v1/me, but 403
    {"status":403,"err":"Invalid token"} on /nodes, and an expired one 403s. So a 401, or a 403 whose body
    names the token, is a stale token. Any other 403 is a token that can't see the file; that, and any other
    code, is None. figma_post and figma_attach call this too, so every tool says it alike."""
    try:
        body = (e.read() or b"").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 -- a body that can't be read leaves the code to decide
        body = ""
    code = getattr(e, "code", None)
    if code == 401 or (code == 403 and "token" in body.lower()):
        return f"Figma {code}: token stale ({body.strip()[:200] or e.reason}); {STALE_FIX}", body
    return None, body


def get(url, timeout=180):
    """Through figma_client.py beside this file: paced with every other tool, and a 429 waited out
    instead of ending the run."""
    import figma_client
    try:
        return figma_client.get(url, token=token(), tool="figma_comments", timeout=timeout)
    except urllib.error.HTTPError as e:
        sys.exit(token_stale(e)[0]
                 or f"Figma API {e.code}: {e.reason}. A 403 usually means the token cannot see this file.")


def whoami():
    """Who is this token? Used as the --me default.

    If --me depended only on $FIGMA_ME and it was never set, `inbox` would print every thread and
    flag NONE as waiting on you, silently. An unset env var that degrades to "no signal" is worse
    than one that errors, because the output still looks like a complete answer.
    /v1/me returns the token owner's handle in exactly the format comment authors carry, so the tool
    can identify itself and the env var becomes an override rather than a requirement. The env var
    still wins, for the case where you are reading someone else's inbox.
    """
    try:
        return get("/v1/me", timeout=30).get("handle", "") or ""
    except Exception:
        return ""


def fetch(file_key):
    return get(API.format(file_key), timeout=90)["comments"]


def flat(c):
    return re.sub(r"\s+", " ", c.get("message", "")).strip()


def handle(c):
    return (c.get("user") or {}).get("handle", "?")


def node_of(c):
    return ((c.get("client_meta") or {}).get("node_id")) or ""


def file_meta(file_key, fetch=True):
    """("design" or "board", URL slug of the file name). Known files cost nothing; any other key
    costs one GET, and falls back to ("design", "File") if that fails, which Figma still opens.
    With fetch=False an unknown key costs nothing either: ("design", "File"), not cached."""
    if file_key not in _META and not fetch:
        return ("design", "File")
    if file_key not in _META:
        try:
            d = get(META_API.format(file_key), timeout=60).get("file") or {}
            _META[file_key] = ("board" if d.get("editorType") == "figjam" else "design",
                               re.sub(r"[^A-Za-z0-9]+", "-", d.get("name") or "File").strip("-") or "File")
        except (SystemExit, Exception):
            _META[file_key] = ("design", "File")
    return _META[file_key]


def node_link(file_key, node, fetch=True):
    """The link that opens a node in its file: ...?node-id=<node, dashed>, with an instance id's ; escaped."""
    kind, name = file_meta(file_key, fetch)
    return f"https://www.figma.com/{kind}/{file_key}/{name}?node-id={node.replace(':', '-').replace(';', '%3B')}"


def linked(file_key, text):
    """text with each line ending in the link of every node id on it that the line doesn't already
    link, so whichever line a session copies carries its links (figma_client.unlinked is the check).
    It only decorates printed lines, so it never reads Figma: a file not in figma.files gets the
    "design/<key>/File" link, which Figma still opens."""
    import figma_client
    out = []
    for ln in str(text).split("\n"):
        miss = dict.fromkeys(i for _, i in figma_client.unlinked(ln))
        out.append(ln + "".join(f"  {node_link(file_key, n, fetch=False)}" for n in miss))
    return "\n".join(out)


def permalink(file_key, c):
    """The link that opens the THREAD, not just its frame: ...?node-id=<node, dashed>#<root id>."""
    kind, name = file_meta(file_key)
    node = node_of(c).replace(":", "-")
    return (f"https://www.figma.com/{kind}/{file_key}/{name}"
            + (f"?node-id={node}" if node else "") + f"#{c['id']}")


def state(c):
    return f"RESOLVED {c['resolved_at'][:10]}" if c.get("resolved_at") else "OPEN"


def lineage(file_key, ids):
    """figma_client.lineage without kids: {id: [entry, ...] from the page down to the node, or None}.
    The path comes from there (the mirror, for a mirrored file) instead of a GET /files?ids= read
    of the file tree."""
    import figma_client
    try:
        return figma_client.lineage(file_key, sorted(set(ids)), kids=False, token=token(), tool="figma_comments",
                                    timeout=180)
    except urllib.error.HTTPError as e:
        sys.exit(token_stale(e)[0]
                 or f"Figma API {e.code}: {e.reason}. A 403 usually means the token cannot see this file.")


def subtrees(file_key, ids):
    """{id: {every layer id under it}} for each id the file holds, from one nodes?ids= read."""
    out = {}
    if not ids:
        return out
    got = get(NODES_API.format(file_key, ",".join(sorted(set(ids))))).get("nodes") or {}
    for i in ids:
        doc = (got.get(i) or {}).get("document")
        if not doc:
            continue
        under, stack = set(), list(doc.get("children") or [])
        while stack:
            n = stack.pop()
            under.add(n["id"])
            stack.extend(n.get("children") or [])
        out[i] = under
    return out


def locate(file_key, ids):
    """({node id: [(id, absoluteBoundingBox), ...]}, {node id: {descendant ids}}).

    The first is the path from the node's page down to the node itself (lineage()); the second is
    every layer under the node (subtrees()). An id the file does not hold is absent from both.
    """
    lin = lineage(file_key, ids)
    out = {i: [(e["id"], e.get("absoluteBoundingBox")) for e in path] for i, path in lin.items() if path}
    return out, subtrees(file_key, sorted(out))


def ancestry(file_key, ids):
    """{node id: path from the root}, as locate() returns it, for a caller that needs only the paths."""
    return locate(file_key, ids)[0]


def how_on(c, path):
    """"direct" if c is pinned to the node at the end of path, "offset on <id>" if it is pinned to an
    ancestor with node_offset inside the node's box, else None. The offset is from the pinned node's
    top-left, as re-pinned comments show. A region comment matches by its pin
    point only."""
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


def on_nodes(cs, paths, ids, subs=None):
    """{node id: [(comment, how), ...]}. A reply goes with its root, so a thread matched by offset
    brings its replies. An id missing from paths is matched direct only. With `subs` from locate(),
    a comment pinned straight to a layer inside the node counts too, as "on child <id>": a finding
    on a component is usually commented on one of its text layers, not on the component."""
    roots = {c["id"]: c for c in cs if not c.get("parent_id")}
    hit = defaultdict(list)
    for n in ids:
        path = paths.get(n) or [(n, None)]
        kids = (subs or {}).get(n) or ()
        for c in cs:
            r = roots.get(c.get("parent_id"), c)
            pin = node_of(r).replace("-", ":")
            how = how_on(r, path) or (f"on child {pin}" if pin in kids else None)
            if how:
                hit[n].append((c, how))
    return hit


def cmd_inbox(a):
    if not a.me:
        a.me = os.environ.get("FIGMA_ME", "") or whoami()
        if not a.me:
            print("  (could not identify you - no $FIGMA_ME and /v1/me failed; "
                  "the waiting-on-you split is OFF)")
    cs = fetch(a.file_key)
    by_id = {c["id"]: c for c in cs}
    kids = defaultdict(list)
    roots = []
    for c in cs:
        p = c.get("parent_id")
        if p:
            kids[p].append(c)
        else:
            roots.append(c)
    touched = []
    for r in roots:
        times = [r.get("created_at", "")] + [k.get("created_at", "") for k in kids[r["id"]]]
        last = max(times)
        if last >= a.since:
            touched.append((last, r))
    touched.sort()
    print(f"{len(cs)} comments in the file. {len(touched)} thread(s) touched since {a.since}.\n")
    unanswered = resolved_after = 0
    for last, r in touched:
        ch = sorted(kids[r["id"]], key=lambda c: c.get("created_at", ""))
        print(linked(a.file_key, f"--- thread {r['id']}  node {node_of(r) or '(none)'}  "
                                 f"last activity {last[:16]}  {state(r)}"))
        print(f"    {permalink(a.file_key, r)}")
        print(linked(a.file_key, f"    {handle(r):20} {r.get('created_at','')[:16]}  {flat(r)[:220]}"))
        for k in ch:
            print(linked(a.file_key, f"      ↳ {handle(k):18} {k.get('created_at','')[:16]}  {flat(k)[:220]}"))
        # a reply by someone else, after my last word in the thread, that I have not answered
        if a.me:
            mine = [c for c in [r] + ch if a.me.lower() in handle(c).lower()]
            if mine:
                my_last = max(c.get("created_at", "") for c in mine)
                theirs = [c for c in ch if a.me.lower() not in handle(c).lower()
                          and c.get("created_at", "") > my_last]
                if theirs:
                    who = ", ".join(sorted({handle(t) for t in theirs}))
                    # A resolved thread waits on nobody. Listed, never counted. See RESOLVED THREADS.
                    if r.get("resolved_at"):
                        resolved_after += 1
                        print(f"    resolved, not counted: {who} replied after your last message here.")
                    else:
                        unanswered += 1
                        print(f"    >>> UNANSWERED: {who} replied after your last message here.")
        print()
    if a.me:
        print(f"UNANSWERED threads needing a reply from you: {unanswered}")
        print(f"Resolved threads with a reply after your last message, not counted: {resolved_after}")
    print("\nRead this before drafting. A comment that repeats a posted one, or that describes a node a\n"
          "reply has already changed, costs more trust than it buys.")


def cmd_nodes(a):
    import figma_family
    cs = fetch(a.file_key)
    ids = [figma_family.norm(n) for n in a.node_ids]
    paths, subs = locate(a.file_key, ids)
    hit = on_nodes(cs, paths, ids, subs)
    fam = figma_family.check(a.file_key, ids, cs)
    link = lambda c: permalink(a.file_key, c)
    for n, k in zip(a.node_ids, ids):
        got = sorted(hit.get(k, []), key=lambda t: t[0].get("created_at", ""))
        if k not in paths:
            print(linked(a.file_key, f"{n}: NOT IN THIS FILE, or deleted. Only comments pinned straight to "
                                     "the id are counted, so a zero here is not a clear."))
        if not got:
            if k in paths:
                print(linked(a.file_key, f"{n}: 0 comments pinned to it, to an ancestor with an offset "
                                         "inside it, or to a layer inside it."))
            print(linked(a.file_key, "\n".join(figma_family.lines(fam, k, link))))
            print()
            continue
        roots = [t for t in got if not t[0].get("parent_id")]
        many = len(roots) >= 3
        print(linked(a.file_key, f"{n}: {len(got)} comment(s) in {len(roots)} thread(s)."
              + ("  <== PAGE-LEVEL NODE: threads here are on unrelated subjects, so a NEW comment is"
                 " probably right. Reply ONLY into a thread about the same thing." if many
                 else "  Reply only if a thread below is about the same subject; otherwise post new.")))
        for c, how in roots:
            print(linked(a.file_key, f"    thread {c['id']}  {how:22} {state(c):19} {handle(c):20} "
                                     f"{c.get('created_at','')[:16]}  {flat(c)[:150]}"))
            print(f"        {permalink(a.file_key, c)}")
        print(linked(a.file_key, "\n".join(figma_family.lines(fam, k, link))))
        print()
    print(figma_family.coverage(fam))


def cmd_check(a):
    txt = open(a.draft, encoding="utf-8").read()
    # The SECOND part carries the >=3 rule, which is what keeps a date like "2024-09" or a time like
    # "04:00" out. The first part must not: a small file's ids are often 2-digit-prefixed (66:2287),
    # and requiring 3 there drops them from the denominator, which is the worst shape for a duplicate
    # sweep: a clean verdict on nodes it never looked at. A node whose second part is 2 digits is
    # still invisible.
    # A draft cites a node twice, as `123:4567` in its header and as 123-4567 in its Link URL.
    # Convert before de-duplicating, or the same node is listed and counted twice. A layer inside an
    # instance, I10:2000;30:4000 (%3B in a URL), is one id. See OTHER COPIES.
    import figma_family
    ids = sorted({figma_family.norm(m) for m in re.findall(
        r"\b(I\d+[:-]\d+(?:(?:;|%3B)\d+[:-]\d+)+|\d{2,6}[:-]\d{3,6})\b", txt)})
    if not ids:
        print(f"No node ids found in {a.draft}. Nothing to check — is the draft citing nodes at all?")
        return
    cs = fetch(a.file_key)
    paths, subs = locate(a.file_key, ids)
    have = on_nodes(cs, paths, ids, subs)
    fam = figma_family.check(a.file_key, ids, cs)
    link = lambda c: permalink(a.file_key, c)
    print(f"{len(ids)} node id(s) cited in {os.path.basename(a.draft)}:\n")
    dupes = absent = kin = 0
    for n in ids:
        got = have.get(n, [])
        if fam.ran and fam.same_layer(n):
            kin += 1
        if n not in paths:
            absent += 1
        if got:
            dupes += 1
            roots = [t for t in got if not t[0].get("parent_id")] or got
            tag = "PAGE-LEVEL, prefer a NEW comment" if len(roots) >= 3 else "read these before replying"
            print(f"  {n:16} {len(roots)} thread(s)  <== {tag}"
                  + ("  (id NOT IN THIS FILE, or deleted)" if n not in paths else f"  {node_link(a.file_key, n)}"))
            for c, how in sorted(roots, key=lambda t: t[0].get("created_at", ""))[-4:]:
                print(linked(a.file_key, f"                   {c['id']}  {how:22} {state(c):19} {flat(c)[:104]}"))
                print(f"                       {permalink(a.file_key, c)}")
        elif n not in paths:
            print(linked(a.file_key, f"  {n:16} NOT IN THIS FILE, or deleted: not checked"))
        else:
            print(f"  {n:16} 0 threads on it, on an ancestor with an offset inside it, or on a layer"
                  f" inside it  {node_link(a.file_key, n)}")
        if n in paths:
            print(linked(a.file_key, "\n".join("  " + s for s in figma_family.lines(fam, n, link))))
    print(f"\n{dupes} of {len(ids)} cited nodes already carry a comment, "
          f"checked against file {a.file_key} ONLY.")
    print(f"{kin} of {len(ids)} cited nodes have an open thread on the same layer of a copy of their "
          f"component, this copy included.\n{figma_family.coverage(fam)}")
    # A draft file holds ids from several files. An id the file does not hold used to print 'clear',
    # a verdict on a node never looked at. It now prints NOT IN THIS FILE and is counted here.
    print(f"⚠ {absent} of {len(ids)} cited ids are not in this file, or deleted, so were not checked."
          "\n  Re-run with each other file's key to cover them.")
    if dupes:
        print("Rewrite those as replies, or cut them if the existing thread already settles the point.")


def _term_pats(term):
    """One term -> its alternatives as regexes. 'a|b' matches either; a node id matches in both forms,
    123:456 and 123-456, because drafts and links write it one way and comments the other."""
    pats = []
    for alt in (x.strip() for x in term.split("|")):
        if not alt:
            continue
        if re.fullmatch(r"\d+[:-]\d+", alt):
            pats.append(re.compile(re.escape(alt.replace("-", ":")) + "|" + re.escape(alt.replace(":", "-"))))
        else:
            pats.append(re.compile(re.escape(alt), re.I))
    return pats


def _excerpt(text, pats, width=160):
    m = next((m for p in pats for m in [p.search(text)] if m), None)
    if not m or len(text) <= width:
        return text[:width]
    lo = max(0, min(m.start() - width // 3, len(text) - width))
    return ("…" if lo else "") + text[lo:lo + width] + ("…" if lo + width < len(text) else "")


def search(keys, groups):
    """groups: [(label, [regex, ...])], one per term. Every thread on each file where every group
    matches the root, a reply, or the pinned node. -> (hits, lines, failed): hits are
    (created_at, key, root, thread); lines are one coverage line per file. Stamps the post gate."""
    hits, lines, failed = [], [], []
    for key in keys:
        name = file_meta(key)[1]
        try:
            cs = fetch(key)
        except (SystemExit, Exception) as e:
            failed.append(key)
            lines.append(f"{name} ({key}): DID NOT RUN - {str(e)[:160]}")
            continue
        roots = {c["id"]: c for c in cs if not c.get("parent_id")}
        kids = defaultdict(list)
        for c in cs:
            if c.get("parent_id"):
                kids[c["parent_id"]].append(c)
        n = 0
        for rid, r in roots.items():
            thread = [r] + sorted(kids.get(rid, []), key=lambda c: c.get("created_at", ""))
            pin = node_of(r).replace("-", ":")
            # A term that IS a comment id (a #1234567890 from a link) matches its thread.
            if all(any(p.search(flat(c)) or p.fullmatch(str(c.get("id", ""))) for c in thread for p in ps)
                   or any(pin and p.fullmatch(pin) for p in ps) for _, ps in groups):
                n += 1
                hits.append((r.get("created_at", ""), key, r, thread))
        opened = sum(1 for h in hits if h[1] == key and not h[2].get("resolved_at"))
        lines.append(f"{name} ({key}): {len(cs)} comments in {len(roots)} threads, "
                     f"{sum(1 for r in roots.values() if r.get('resolved_at'))} resolved. "
                     f"{n} thread(s) match: {opened} open, {n - opened} resolved.")
        import figma_post
        figma_post.record_search(key, [t for t, _ in groups])
    return hits, lines, failed


def cmd_search(a):
    """Every thread, on every file asked for, where each term matches the root, a reply, or the pinned
    node. Oldest first, resolved included and marked, each with its permalink. Exit 0 on a match, 1 when
    every file was read and nothing matched, 2 when a file could not be read (DID NOT RUN)."""
    keys = a.file or list(KNOWN_FILES)
    if not keys:
        print("search: DID NOT RUN: no Figma file to search. Pass --file KEY, or set figma.files in the "
              "project's .claude/product-os.json (kit_config.py).", file=sys.stderr)
        sys.exit(2)
    groups = [(t, _term_pats(t)) for t in a.terms]
    groups = [(t, ps) for t, ps in groups if ps]
    if not groups:
        sys.exit("search: no terms.")
    print(f"search: every comment on {len(keys)} file(s), resolved included, for all of: "
          + " + ".join(t for t, _ in groups) + "\n")
    hits, lines, failed = search(keys, groups)
    for ln in lines:
        print("  " + ln)
    every = [p for _, ps in groups for p in ps]
    for ts, key, r, thread in sorted(hits, key=lambda h: h[0]):
        print(f"\n{ts[:10]}  {state(r):19} {len(thread) - 1:>2} repl{'y' if len(thread) == 2 else 'ies'}"
              f"  {handle(r):20} {permalink(key, r)}")
        print(linked(key, f"    {_excerpt(flat(r), every)}"))
        more = [c for c in thread[1:] if any(p.search(flat(c)) for p in every)]
        for c in more[:3]:
            print(linked(key, f"      ↳ {handle(c):18} {c.get('created_at', '')[:10]}  {_excerpt(flat(c), every, 140)}"))
        if len(more) > 3:
            print(f"      ↳ … {len(more) - 3} more matching repl(ies)")
    print(f"\n{len(hits)} thread(s) on {len(keys) - len(failed)} of {len(keys)} file(s).")
    if failed:
        print(f"⚠ DID NOT RUN on {', '.join(failed)}: a zero there is not a clear.")
        sys.exit(2)
    if hits:
        print("An OPEN thread on the same subject means reply in it (figma_post.py reply <key> <root id>),"
              " and cite it by the link above.")
    sys.exit(0 if hits else 1)


def dead_pins(roots, chains):
    """[(root, "DELETED" or "HIDDEN" or "UNREAD", detail)] for each root pinned to a node that is gone.
    chains is lineage()'s answer: None = Figma no longer has the node; a chain with visible:false on the
    node or a layer above it = hidden; an id missing from it was not read, which is never a clear."""
    out = []
    for r in roots:
        n = node_of(r)
        if not n:
            continue
        if n not in chains:
            out.append((r, "UNREAD", n))
        elif chains[n] is None:
            out.append((r, "DELETED", n))
        else:
            off = [e for e in chains[n] if e.get("visible", True) is False]
            if off:
                out.append((r, "HIDDEN", f"{n} under {off[0].get('id')} {off[0].get('name')!r}"))
    return out


FLAGS = os.path.join(os.path.expanduser("~"), ".cache", "product-os", "figma_comment_flags.json")


def _read_open(a):
    """([(key, roots, replies by root id, lineage of each pinned node)], [files not read]) for the
    open thread roots by the token owner (--all: by anyone) on each --file, default figma.files.
    Exits 2, DID NOT RUN, when there is no file to read or the token owner is unknown."""
    keys = a.file or list(KNOWN_FILES)
    if not keys:
        print(f"{a.cmd}: DID NOT RUN: no Figma file to read. Pass --file KEY, or set figma.files in the "
              "project's .claude/product-os.json (kit_config.py).", file=sys.stderr)
        sys.exit(2)
    os.environ["FIGMA_CLIENT_LANE"] = a.lane
    import figma_client
    try:
        me = "" if a.all else (os.environ.get("FIGMA_ME", "") or whoami())
    except SystemExit as e:
        me, why = "", e.code
    else:
        why = "no $FIGMA_ME and /v1/me failed"
    if not a.all and not me:
        print(f"{a.cmd}: DID NOT RUN: whose threads is unknown ({why}).")
        sys.exit(2)
    a.who = "" if a.all else f" by {me}"
    out, failed = [], []
    for key in keys:
        try:
            cs = fetch(key)
            roots = [c for c in cs if not c.get("parent_id") and not c.get("resolved_at")
                     and (a.all or me.lower() in handle(c).lower())]
            replies = defaultdict(list)
            for c in cs:
                if c.get("parent_id"):
                    replies[c["parent_id"]].append(c)
            chains = figma_client.lineage_or_exit(key, [node_of(r) for r in roots if node_of(r)], kids=False,
                                                  token=token(), tool="figma_comments")
        except SystemExit as e:
            failed.append(f"{key} ({e.code})")
            continue
        out.append((key, roots, replies, chains))
    return out, failed


def _flag_new(kind, ids):
    """The ids this kind of report did not list at its last --new run. Saves the ids now listed, each
    with the date it was first listed; one that drops off and comes back later is new again. Red once,
    so a thread only someone else can move does not turn a daily audit red every day."""
    import datetime
    try:
        with open(FLAGS, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    old = state.get(kind) or {}
    state[kind] = {i: old.get(i, datetime.date.today().isoformat()) for i in ids}
    os.makedirs(os.path.dirname(FLAGS), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(FLAGS), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FLAGS)
    return {i: old.get(i) for i in ids}


def _report(a, kind, found, failed, total_files, tail):
    """Print found [(key, root, label, detail)] and exit: 2 when a file was not read, else 1 when any
    is listed (with --new: any not listed at the last --new run), else 0."""
    since = _flag_new(kind, [r["id"] for _, r, _, _ in found]) if a.new and not failed else {}
    for key, r, label, detail in found:
        mark = (f"since {since[r['id']]}" if since.get(r["id"]) else "NEW") if a.new and not failed else ""
        print(linked(key, f"  {label:8} {r.get('created_at', '')[:10]}  {mark:16} {detail}  {flat(r)[:80]}"))
        print(f"           {permalink(key, r)}")
    print(f"\n{len(found)} thread(s) on {total_files - len(failed)} of {total_files} file(s)"
          + (f", {sum(1 for v in since.values() if not v)} not listed before." if a.new and not failed else "."))
    if found:
        print(tail)
    if failed:
        print(f"⚠ DID NOT RUN on {', '.join(failed)}: a zero there is not a clear.")
        sys.exit(2)
    if a.new:
        sys.exit(1 if any(not v for v in since.values()) else 0)
    sys.exit(1 if found else 0)


def cmd_pins(a):
    """Open threads by you (--all: by anyone) pinned to a node Figma has deleted, or that sits under a
    hidden layer. Design deletes and hides old frames as pages move on, and the thread stays open on
    nothing; found by hand, they are found late."""
    read, failed = _read_open(a)
    found = []
    for key, roots, _, chains in read:
        dead = dead_pins(roots, chains)
        print(f"{_META.get(key, ('', key))[1]} {key}: {len(roots)} open thread(s){a.who}, "
              f"{sum(1 for r in roots if node_of(r))} pinned to a node, {len(dead)} on a dead pin.")
        found += [(key, *d) for d in sorted(dead, key=lambda d: (d[1], d[0].get("created_at", "")))]
    _report(a, "pins", found, failed, len(read) + len(failed),
            "Resolve one whose subject is gone; one still true gets its root edited and its pin dragged "
            "onto the live node in the Figma UI.")


def cmd_stale(a):
    """Open threads by you (--all: by anyone) with no comment in --days days, by page, oldest first.
    FIX notes are left out, since design resolves those, and so are threads `pins` lists. The list is
    for one approved resolve batch (figma_attach.py resolve); nothing is resolved here."""
    import datetime
    cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%S")
    read, failed = _read_open(a)
    found = []
    for key, roots, replies, chains in read:
        dead = {d[0]["id"] for d in dead_pins(roots, chains)}
        old = []
        for r in roots:
            last = max(c.get("created_at", "") for c in [r] + replies[r["id"]])
            if r["id"] in dead or flat(r).startswith("FIX") or last >= cut:
                continue
            chain = chains.get(node_of(r)) or []
            page = chain[0].get("name") if chain else "(not pinned to a node)"
            old.append((page, last, r))
        print(f"{_META.get(key, ('', key))[1]} {key}: {len(roots)} open thread(s){a.who}, "
              f"{len(old)} with nothing since {cut[:10]}.")
        found += [(key, r, "STALE", f"last {last[:10]}  page {page!r}") for page, last, r in sorted(old, key=lambda o: (o[0], o[1]))]
    _report(a, "stale", found, failed, len(read) + len(failed),
            "Resolve the ones whose subject is settled in one approved batch (figma_attach.py resolve); "
            "a question still owed an answer gets a nudge instead.")


def _hex(f):
    c = f.get("color") or {}
    a = f.get("opacity", 1.0) * c.get("a", 1.0)
    return "#%02X%02X%02X@%.2f" % (round(c.get("r", 0) * 255), round(c.get("g", 0) * 255),
                                   round(c.get("b", 0) * 255), a)


def _paint(f):
    # Every paint type, not only SOLID. See FOURTH FAILURE in cmd_frame.
    t = f.get("type") or "?"
    if t == "SOLID":
        return _hex(f)
    if t == "IMAGE":
        return f"IMAGE(ref={(f.get('imageRef') or '?')[:10]}, {f.get('scaleMode', '?')})"
    if t.startswith("GRADIENT"):
        return f"{t}({len(f.get('gradientStops') or [])} stops)"
    return t


def _paints(ps):
    """All visible paints joined with '+', and a count of the paints switched off."""
    ps = ps or []
    on = [p for p in ps if p.get("visible", True)]
    s = " + ".join(_paint(p) for p in on) or "none"
    off = len(ps) - len(on)
    return s + (f" (+{off} hidden paint)" if off else "")


_RUN_NOISE = {"boundVariables", "isOverrideOverTextStyle", "textAutoResize", "fontPostScriptName",
              "inheritTextStyleId"}

# styleOverrideTable states a variable-bound value in the collection's DEFAULT mode, while the node's
# own `style` and `fills` are in the mode it sits in. On a phone frame, a title whose characters all
# carry one entry would print the desktop mode's size and line height beside its real ones. A value
# bound to the same variable as the node's own binding is the node's value (one variable, one node,
# one mode), so it is taken from the node; one bound to another variable is printed as stated and
# marked.
_ENTRY_VARS = {"fontSize": "fontSize", "lineHeight": "lineHeightPx", "letterSpacing": "letterSpacing",
               "fontFamily": "fontFamily"}


def _var_id(ref):
    """The variable id of a boundVariables value (an alias, or a list holding one); None otherwise."""
    if isinstance(ref, list) and len(ref) == 1:
        ref = ref[0]
    return ref.get("id") if isinstance(ref, dict) and ref.get("type") == "VARIABLE_ALIAS" else None


def _entry_in_mode(n, ov):
    """(entry, others): override entry `ov` of TEXT node `n` with each value bound to the node's own
    variable taken from the node, and the properties bound to a variable the node does not use."""
    st, own_bv, bv = n.get("style") or {}, n.get("boundVariables") or {}, ov.get("boundVariables") or {}
    out, others = dict(ov), set()
    for key, prop in _ENTRY_VARS.items():
        vid = _var_id(bv.get(key))
        if not vid:
            continue
        if vid == _var_id(own_bv.get(key)) and prop in st:
            out[prop] = st[prop]
        elif prop in ov:
            others.add(prop)
    if ov.get("fills"):
        own = {}
        for p in n.get("fills") or []:
            vid = isinstance(p, dict) and _var_id((p.get("boundVariables") or {}).get("color"))
            if vid:
                own.setdefault(vid, p)
        fills = []
        for p in ov["fills"]:
            vid = isinstance(p, dict) and _var_id((p.get("boundVariables") or {}).get("color"))
            if vid and vid in own:
                fills.append(own[vid])
            else:
                if vid:
                    others.add("fills")
                fills.append(p)
        out["fills"] = fills
    return out, others


def _runs(n):
    """Per-character style runs that differ from the base: [(start, end, {property: value})].

    A run's table entry restates most of the base style, so only the properties that differ are
    kept, and a run that differs in nothing is dropped. A value the entry binds to a variable the
    node does not use is stated in the default mode, so it is printed with "(default mode)".
    """
    ids = n.get("characterStyleOverrides") or []
    table = n.get("styleOverrideTable") or {}
    base = dict(n.get("style") or {}, fills=n.get("fills"))
    spans = []
    for i, oid in enumerate(ids):
        if not oid:
            continue
        if spans and spans[-1][2] == oid and spans[-1][1] == i:
            spans[-1][1] = i + 1
        else:
            spans.append([i, i + 1, oid])
    runs = []
    for s, e, oid in spans:
        entry, others = _entry_in_mode(n, table.get(str(oid)) or {})
        diff = {k: v for k, v in entry.items()
                if k not in _RUN_NOISE and base.get(k, "NONE" if k == "textDecoration" else None) != v}
        if diff:
            runs.append((s, e, {k: (_Default(v) if k in others else v) for k, v in diff.items()}))
    return runs


class _Default:
    """A run value stated in the default mode: prints as the value plus "(default mode)"."""
    def __init__(self, v):
        self.v = v

    def __str__(self):
        return f"{self.v} (default mode)"


def cmd_frame(a):
    """FOURTH FAILURE: a partial read that prints like a full one. Comments asked design to
    underline links and to put an image in an avatar, and both were already in the mock. The
    underline sat in the text's per-character overrides (characterStyleOverrides +
    styleOverrideTable), and `style`, the only thing read, said NONE. The avatar was an IMAGE fill
    under a translucent SOLID, and only the first SOLID fill printed. That is a silent zero.

    So every visible paint prints by type, text prints weight, decoration and case, and each
    per-character run prints under its node with the characters it covers. The header names what is
    still not printed. Each node printed is stamped as read, and figma_post.py refuses `new` and
    `reply` on a node that was not printed in the last 30 minutes.

    EIGHTH FAILURE: the layer name read as the copy. A TEXT layer is named after the copy it was
    created with, and an instance override changes the characters but not the name. Printing the
    layer `name` showed the component's wording, in the slot where content goes, for an instance
    that says something else.

    So a TEXT node prints `text=` and its full characters in that slot. When the layer name
    differs, the line ends `name!=text` and the name: either the layer was renamed ("Label") or
    the instance overrides the component's copy. --text is accepted and does nothing.
    """
    key = a.node_id.replace("-", ":")
    data = get(NODES_API.format(a.file_key, key))
    doc = ((data.get("nodes") or {}).get(key) or {}).get("document")
    if not doc:
        sys.exit(f"{a.node_id} is not in this file, or was deleted. Nothing to read.")
    vnames = {}
    if a.vars:
        meta = get(VARS_API.format(a.file_key)).get("meta") or {}
        vnames = {k: d.get("name") for k, d in (meta.get("variables") or {}).items()}

    shown, hidden = [], []
    # visible:false on ANY ancestor poisons the whole subtree, so the flag is carried down.
    def walk(n, anc_hidden, depth):
        self_hidden = n.get("visible", True) is False
        eff = anc_hidden or self_hidden
        (hidden if eff else shown).append((depth, n, self_hidden))
        for c in n.get("children") or []:
            walk(c, eff, depth + 1)
    # visible:false ABOVE the node hides it too, and the walk down from it cannot see that: a layer
    # inside a hidden old frame reads as visible, and a thread can sit pinned there. Nothing under a
    # hidden ancestor is stamped, so figma_post.py refuses to post on it.
    chain = (lineage(a.file_key, [key]) or {}).get(key) or []
    above = [e for e in chain[:-1] if e.get("visible", True) is False]
    walk(doc, bool(above), 0)

    def line(depth, n):
        bb = n.get("absoluteBoundingBox") or {}
        st = n.get("style") or {}
        dims = f"{bb.get('width')}x{bb.get('height')}" if bb.get("width") is not None else "-"
        # A TEXT layer's name is stale under an instance override, so the content slot holds
        # `characters`, whole. See EIGHTH FAILURE.
        is_text = n.get("type") == "TEXT"
        label = f"text={n.get('characters')!r}" if is_text else repr(n.get("name"))
        out = f"{'  ' * min(depth, 8)}{n.get('id'):26} [{(n.get('type') or '')[:9]:9}] {dims:14} {label}"
        if st.get("fontSize"):
            out += f"  {st['fontSize']:g}/{st.get('lineHeightPx', 0):g} w{st.get('fontWeight')} ls={st.get('letterSpacing')}"
            if st.get("textDecoration", "NONE") != "NONE":
                out += f" {st['textDecoration']}"
            if st.get("textCase", "ORIGINAL") != "ORIGINAL":
                out += f" {st['textCase']}"
        if n.get("fills"):
            out += f"  fill={_paints(n['fills'])}"
            if a.vars:
                bv = (n.get("boundVariables") or {}).get("fills") or []
                names = [vnames.get(b.get("id"), "?") for b in bv]
                out += f" var={','.join(names) if names else 'RAW (unbound)'}"
        if n.get("strokes"):
            out += f"  stroke={_paints(n['strokes'])} w{n.get('strokeWeight', '?')}"
        fx = [e.get("type") for e in (n.get("effects") or []) if e.get("visible", True)]
        if fx:
            out += f"  effects={','.join(fx)}"
        if n.get("opacity", 1) != 1:
            out += f"  opacity={n['opacity']:.2f}"
        if is_text and n.get("name") != n.get("characters"):
            out += f"  name!=text name={n.get('name')!r}"
        runs = _runs(n)
        if runs:
            out += f"  MIXED: {len(runs)} run(s) override the base style"
            pad = "  " * min(depth, 8) + " " * 28
            for s, e, props in runs:
                desc = ", ".join(f"{k}={_paints(v) if k == 'fills' else v}" if not isinstance(v, _Default)
                                 else f"{k}={_paints(v.v) if k == 'fills' else v.v} (default mode)"
                                 for k, v in props.items())
                text = re.sub(chr(10), " ", (n.get("characters") or "")[s:e])[:40]
                out += f"\n{pad}chars {s}-{e} {text!r}: {desc}"
        return out

    print(linked(a.file_key, f"{key}  {doc.get('name')!r}"))
    if above:
        print(linked(a.file_key, "ANCESTOR HIDDEN: " + ", ".join(f"{e.get('id')} {e.get('name')!r}" for e in above)
                     + ". The node and everything in it are hidden; don't comment on it."))
    elif not chain:
        print("ANCESTORS UNREAD: no path from the page came back, so a hidden layer above this node "
              "would not show here.")
    print(f"{len(shown)} visible node(s).  {len(hidden)} DROPPED as hidden "
          f"(visible:false on the node or an ancestor).")
    print("Findings must come from the visible list only. A hidden layer is off on purpose.")
    print("Printed: every visible fill and stroke by type, effects, layer opacity, text size, weight,\n"
          "decoration and case, and each per-character run. A TEXT node shows text=<characters>,\n"
          "and name!=text <layer name> when the name differs. NOT printed: padding, gap, alignment,\n"
          "corner radius, constraints, component properties. Read get_design_context for those.\n"
          "Tree lines carry no link, to keep a big frame's read short. To cite a node, use the frame's\n"
          "link above with that node's id in node-id, : as -.\n")
    for depth, n, _ in shown:
        print(line(depth, n))
    # figma_post.py refuses to post on a node this command has not printed. See FOURTH FAILURE.
    import figma_post
    # Each stamp carries this frame's hash; figma_post.py re-fetches the frame and refuses if it moved.
    figma_post.record_reads(a.file_key, [n.get("id") for _, n, _ in shown],
                            root=key, root_hash=figma_post.node_hash(doc))
    print(linked(a.file_key, f"\n{len(shown)} node(s) stamped as read for figma_post.py (good for "
                             f"{figma_post.FRESH_MIN} minutes, and only while {key} is unchanged in Figma)."))
    if a.show_hidden:
        roots = [(d, n) for d, n, sh in hidden if sh]
        print(f"\n--- {len(roots)} hidden subtree root(s), for reference. DO NOT file these as findings ---")
        for depth, n in roots:
            print(line(depth, n))


def cmd_selftest(a=None):
    """Planted cases, offline: frame and inbox on a planted file and comment list print each node id
    with its link on the same line (figma_client.unlinked), and a line printed without linked() is caught.
    token_stale tells a rejected token from a file the token can't see, and get() exits with its line."""
    import contextlib, io, types
    import figma_client
    key, fails, ran = "PLANTEDselftestKey0000", [], []

    def chk(name, ok, got=""):
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        got {got!r}"))
        ran.append(name)
        if not ok:
            fails.append(name)

    def run(fn, ns):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(ns)
        return buf.getvalue()

    doc = {"id": "1600:3000", "name": "buttons", "type": "FRAME",
           "absoluteBoundingBox": {"width": 1016, "height": 1040}, "children": [
               {"id": "1600:3010", "type": "TEXT", "name": "buttons", "characters": "buttons",
                "absoluteBoundingBox": {"width": 856, "height": 56},
                "style": {"fontSize": 48, "lineHeightPx": 56, "fontWeight": 500}},
               {"id": "I1600:3020;2200:30005", "type": "RECTANGLE", "name": "old", "visible": False}]}
    comments = [{"id": "1900000101", "message": "Is 1600:3010 the right size?", "created_at": "2026-10-30T00:00:00Z",
                 "user": {"handle": "Design, A."}, "client_meta": {"node_id": "1600:3000"}}]
    g, had_meta, had_post = globals(), _META.get(key), sys.modules.get("figma_post")
    keep = {k: g[k] for k in ("get", "lineage", "fetch")}
    try:
        _META[key] = ("design", "File")
        got = linked(key, "1100:20001 'Landing' in 1100:20000, 1100:20001 again\nat 10:30, port 127.0.0.1:4321, 1440x900")
        chk("linked ends a line with each id's link once, and leaves times, ports and sizes alone",
            got == ("1100:20001 'Landing' in 1100:20000, 1100:20001 again  " + node_link(key, "1100:20001") + "  "
                    + node_link(key, "1100:20000") + "\nat 10:30, port 127.0.0.1:4321, 1440x900")
            and not figma_client.unlinked(got), got)
        reads = []
        g["get"] = lambda url, timeout=180: reads.append(url) or {}
        unknown = key + "Z"
        got = linked(unknown, "see 1100:20001")
        chk("linked never reads Figma: a file not in figma.files gets the design/<key>/File link and no GET",
            reads == [] and got == f"see 1100:20001  https://www.figma.com/design/{unknown}/File?node-id=1100-20001"
            and unknown not in _META, reads or got)
        g["get"] = lambda url, timeout=180: {"nodes": {"1600:3000": {"document": doc}}}
        g["lineage"] = lambda k, ids: {"1600:3000": [{"id": "0:1", "name": "Page"}, {"id": "1600:3000"}]}
        g["fetch"] = lambda k: comments
        sys.modules["figma_post"] = types.SimpleNamespace(record_reads=lambda *x, **kw: None,
                                                         node_hash=lambda d: "h", FRESH_MIN=30)
        out = run(cmd_frame, argparse.Namespace(file_key=key, node_id="1600-3000", vars=False, show_hidden=True))
        tree = [ln for ln in out.splitlines() if re.match(r"\s*I?[\d:;]+\s+\[", ln)]
        chk("frame: the header carries the frame's link, and the tree lines, visible and hidden, carry none",
            out.splitlines()[0].endswith(f"  {node_link(key, '1600:3000')}") and len(tree) == 3
            and not any("https://" in ln for ln in tree), tree or out)
        out = run(cmd_inbox, argparse.Namespace(file_key=key, since="1970-01-01", me="Owner"))
        thread = [ln for ln in out.splitlines() if ln.startswith("--- thread")]
        chk("inbox: a thread line carries its node's link, and every id its text cites carries its own",
            len(thread) == 1 and thread[0].endswith(f"  {node_link(key, '1600:3000')}")
            and not figma_client.unlinked(out), figma_client.unlinked(out) or out)
        chk("known bad: a thread line printed without linked() is caught",
            figma_client.unlinked("--- thread 1900000101  node 1600:3000  last activity 2026-10-30")
            == [(1, "1600:3000")])
    finally:
        g.update(keep)
        if had_meta is None:
            _META.pop(key, None)
        if had_post is None:
            sys.modules.pop("figma_post", None)
        else:
            sys.modules["figma_post"] = had_post
    # token_stale: what each tool says when Figma rejects the token.
    err = lambda code, body: urllib.error.HTTPError("https://api.figma.com/v1/x", code, "planted", {}, io.BytesIO(body))
    stale, body = token_stale(err(401, b'{"status":401,"err":"Invalid token"}'))
    chk("token_stale: a 401 (Figma's answer to an invalid token) reads 'token stale', with Figma's body and the fix",
        bool(stale) and stale.startswith("Figma 401: token stale") and "Invalid token" in stale
        and "FIGMA_TOKEN" in stale and "Invalid token" in body, stale)
    chk("token_stale: a 403 whose body names the token (an expired one 403s) reads 'token stale' too",
        (token_stale(err(403, b'{"status":403,"err":"Token expired"}'))[0] or "").startswith("Figma 403: token stale"))
    got = [token_stale(err(c, b))[0] for c, b in ((403, b'{"status":403,"err":"Forbidden"}'), (404, b'{"status":404}'),
                                                  (500, b""))]
    chk("token_stale: a 403 that doesn't name the token, a 404 and a 500 are not a stale token", got == [None] * 3, got)
    kept = figma_client.get, figma_auth.token

    def rejected(*a, **k):
        raise err(401, b'{"status":401,"err":"Invalid token"}')
    try:
        figma_client.get, figma_auth.token = rejected, (lambda *a, **k: "figd_planted")
        try:
            get("/v1/files/K/comments")
            said = "returned"
        except SystemExit as e:
            said = str(e)
        chk("get: a 401 exits with the 'token stale' line, not 'the token cannot see this file'",
            said.startswith("Figma 401: token stale") and "cannot see" not in said, said)
    finally:
        figma_client.get, figma_auth.token = kept
    print(f"\nfigma_comments selftest: {len(fails) or 'no'} failure(s) in {len(ran)} planted cases")
    return 1 if fails else 0


if __name__ == "__main__":  # other tools may import search()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inbox"); p.add_argument("file_key"); p.add_argument("--since", default="1970-01-01")
    # --me splits "my threads" from "threads waiting on me". Resolved in cmd_inbox, not here:
    # $FIGMA_ME if set, else whoami(). See whoami() for why the env-var-only version was a trap.
    p.add_argument("--me", default=None,
                   help="whose inbox. Defaults to $FIGMA_ME, else the token owner via /v1/me.")
    p.set_defaults(fn=cmd_inbox)
    p = sub.add_parser("nodes"); p.add_argument("file_key"); p.add_argument("node_ids", nargs="+")
    p.set_defaults(fn=cmd_nodes)
    p = sub.add_parser("check"); p.add_argument("file_key"); p.add_argument("draft")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("frame"); p.add_argument("file_key"); p.add_argument("node_id")
    p.add_argument("--show-hidden", action="store_true",
                   help="also list the hidden subtree roots, labelled, so you can see what was dropped")
    # Kept so older commands still parse (figma_post.py's refusal prints one). Text always prints.
    p.add_argument("--text", action="store_true",
                   help="no effect: a TEXT node's characters always print")
    p.add_argument("--vars", action="store_true",
                   help="resolve the variable behind each fill, and flag RAW (unbound) fills")
    p.set_defaults(fn=cmd_frame)
    p = sub.add_parser("search"); p.add_argument("terms", nargs="+",
                   help="all must match somewhere in a thread; 'a|b' accepts either; a node id matches both forms")
    p.add_argument("--file", action="append", metavar="KEY",
                   help="a file key to search, repeatable. Default: every file in figma.files "
                        "(the project's .claude/product-os.json)")
    p.set_defaults(fn=cmd_search)
    for name, fn, hlp in (("pins", cmd_pins, "open threads pinned to a deleted or hidden node"),
                          ("stale", cmd_stale, "open threads, not FIX notes, with no comment in --days days")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--file", action="append", metavar="KEY", help="a file key, repeatable; default figma.files")
        p.add_argument("--all", action="store_true", help="everyone's open threads, not only the token owner's")
        p.add_argument("--lane", default="interactive", help="figma_client lane; a scheduled audit passes batch")
        p.add_argument("--new", action="store_true",
                       help=f"exit 1 only for a thread the last --new run did not list ({FLAGS})")
        if name == "stale":
            p.add_argument("--days", type=int, default=45)
        p.set_defaults(fn=fn)
    sub.add_parser("selftest", help="planted cases, offline: each node id it prints carries its link"
                   ).set_defaults(fn=lambda a: kit_config.run_isolated(cmd_selftest, a))
    a = ap.parse_args()
    rc = a.fn(a)
    if a.cmd == "selftest":
        sys.exit(rc)
