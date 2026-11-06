#!/usr/bin/env python
"""ado_write.py - the write half of ado_rest.py.

WHY THIS EXISTS. ado.py is the canonical create/lint gate. Where `az` sits behind a permission
prompt, every az call blocks on a click nobody can make from a background run. ado_rest.py reads
over the PAT and python urllib, but it is read-only: pull / audit / show / decisions.

This file is narrow on purpose. It does the writes that a board reconcile needs and
nothing else, over the same PAT + urllib path:

    state    <id> <State>              System.State
    field    <id> <ref> <value> [--replaces WHY]
                                       any single field, e.g. Microsoft.VSTS.Common.AcceptanceCriteria;
                                       "" clears it. Refuses to drop a line someone else first
                                       wrote (see "Whose text" below) unless --replaces says why
    comment  <id> <text> [--stack WHY] add a comment. Refuses if the newest comment on the
                                       item is already yours - nobody has replied, so patch
                                       that one with `editcmt` instead of stacking a second.
                                       Allowed once a teammate has replied. A time gap, a closed
                                       item or a fix found later is no reason to --stack: merge
                                       it in, with no dated "Update" block. Warns over 700 chars.
    parent   <id> <parentId>           attach an orphan to its parent (a relation, not a field -
                                       `field System.Parent` does not work). Refuses if already set.
    reparent <id> <newParentId> [--keep-related]
                                       Move an item to a different parent (remove + add in one
                                       rev-guarded patch). Refuses if there is no parent, or >1.
                                       --keep-related links the old parent as Related in the same
                                       patch. Both refuse a parent in the child's own backlog
                                       category (a Bug under a Task), before any write.
    editcmt  <id> <commentId> <text>   Replace a comment (this is how a prose pile gets fixed;
                                       ADO has no delete-and-repost that keeps the thread)
    delcmt   <id> <commentId>          soft-delete a comment, only to collapse a same-author pile
                                       whose content has already been merged upward
    comments <id>                      list the item's comments with their ids (read-only), for
                                       editcmt/delcmt
    attach   <id> <file>... [--inline] upload each file and link it to the item (Attachments tab).
                                       --inline also appends each picture to the body field
                                       (ReproSteps on a Bug), in the same rev-guarded patch.
                                       Skips a file already attached with the same name and size,
                                       so a re-run adds nothing. Reads the item back after the
                                       patch and exits 1 unless every upload shows on it (and in
                                       the body, with --inline).
    delete   <id>:<rev>... [--undo <dir>]
                                       send Removed items to the recycle bin, never destroy, each
                                       id on the one command line, which names them all. Refuses
                                       an item not Removed or no longer at <rev>, the rev it was
                                       reviewed at; a test artifact (Test Plan, Suite, Case,
                                       Shared Steps or Parameter), which the API deletes for good;
                                       and an item with a child not in Removed. Writes
                                       <dir>/<id>-rev<rev>.undo.json first (default ado.undo_dir,
                                       else ~/.local/share/product-os/ado-undo), replacing one a
                                       failed run left. Reads back: the item must answer 404 and the
                                       recycle bin must hold it. A pair refused or not confirmed
                                       doesn't stop the rest; the last line says how many went
    restore  <id>                      bring an item back from the recycle bin (a delete's undo);
                                       reads back the item and the bin
    batch    <file.json> [--replaces <ids> WHY]
                                       apply a reviewed list of state, field, parent and comment
                                       edits in one run, so one command covers the list. Skips
                                       an item that changed since the list was made, writes an
                                       undo file in the same format first, stops at the first
                                       failed write. Refuses the file, before anything is sent,
                                       when an entry has a key it doesn't know or nothing to send
                                       (a delete, restore or attach is never batched), when a new
                                       entry's comment edit has no comment.expect, and when an
                                       entry drops a line someone else first wrote, unless
                                       --replaces names that item. See batch() for the format
    --selftest                         run the read-back against a stand-in ADO on 127.0.0.1;
                                       nothing goes to ADO. Exit 0 all cases pass, 1 any fails

`state`, `field`, `comment` and `editcmt` read the item back after the write, with a fresh GET,
and compare what ADO stored with what was sent. A comment or an HTML field (Description, History,
AcceptanceCriteria, ReproSteps, SystemInfo) compares the visible text with entities decoded, block
tags read as spaces and whitespace collapsed, plus every href, src and @mention; any other text
field compares as plain text with whitespace collapsed, so an escaped "&lt;" in a title differs, and
so does a custom HTML field ADO re-encodes: a false alarm, never a false pass. AssignedTo
matches the stored identity's uniqueName, displayName or id; Tags match as a set; a date or time
matches the same moment, a date sent alone matching midnight UTC; State, Reason and tree paths
match in any case; a field cleared with "" must come back empty. How ADO stores a date, and
whether it shifts one by time zone, is UNVERIFIED: a shift would read as not confirmed.

A difference prints WRITE NOT CONFIRMED and exits 1. A read-back that fails prints DID NOT RUN
and exits 2: the write was sent, and whether it landed is unknown. `attach`
reads back too and exits 1 with READ BACK FAILED. `parent`, `reparent` and `delcmt` don't read
back yet.

Exit 1 also covers a write ADO refused, a stacking refusal and a missing token; exit 2 also
covers an unset org or project, where nothing was sent. A write that times out exits 1 even if it
landed. Not compared: markup that changes no text, link or mention, such as a lost <b>, <s> or
alt text, and text moved across list items. Only the first page of comments, up to 200, is read.

It does not create work items. Creation stays behind ado.py's search-first gate, which is the
whole reason that gate exists - a create is where duplicates happen, and this file has no
dup-search in it. For a new item run `ado.py --rest new`, which keeps the search-first gate and
skips `az`.

Before each write, the session's own earlier sentences that name an item the write touches and put
work off ("I'll copy that text onto #1234, then delete #5678") are printed, from its log
(session_close.promises_about; CLAUDE_CODE_SESSION_ID names the session). They never stop the write.
None prints nothing; a log that can't be read prints "did not run".

Whose text a write drops. Before `field` or `batch` sends a Title, Description, AcceptanceCriteria,
ReproSteps or SystemInfo, each line the new value drops (a block of an HTML field, as a reader sees
it; a plain field whole) is credited to the first revision that shows it, from the item's history
(workItems/{id}/updates). A line someone other than the PAT's identity first wrote refuses the write,
and nothing is sent; the refusal names the item, field, author and lines and prints the value with
their lines on top. Putting back exactly what our own latest revision of the field replaced (an undo)
passes. A history that can't be read refuses. `--replaces` lifts it, its WHY in plain words on the
command line. A batch PATCH then carries a `test /rev` at the revision the check read.

Each write goes out from its own command line, `ado_write.py <subcommand> ...`, which names the
write, so a settings ask rule can prompt on it (ask_rules.py checks that each one does). --stack's
and --replaces' WHY sit on that command, in plain words (ask_rules.plain), so the prompt shows why.

CONFIG. ado.org and ado.project from kit_config.py; unset, a write exits 2 naming the key.
ado.undo_dir: where `delete` writes its undo files (default ~/.local/share/product-os/ado-undo).

The PAT is read from ADO_PAT / AZURE_DEVOPS_EXT_PAT, or the OS keychain (kit_config.token), and is
never printed, logged or echoed.
Text is sent as written, but for links: ADO renders HTML, so pass HTML (<br>, <ul>) rather than
markdown. A comment, and an HTML field's value (`field`, `batch`), goes out with each markdown link
made an anchor and each bare work-item id the project holds (asked live; the ado_rest cache when that
fails) linked to its item, since ADO links neither by itself (ado_links.py). The result line says
what was linked and which ids were left bare as no item of the project; the read-back compares what
went out. Every line that names a work item ends with the URL of each id on it
(kit_config.ado_linked), so whichever line a session copies, the link comes with it.
"""
import base64, datetime, json, os, re, sys, urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import ado_links  # a bare #1234 in a field or comment goes out as a link (ado_links.py)
import ask_rules  # an override's reason is plain words, the one rule every override flag takes
import kit_config
from ado import categories_from, same_category, same_category_reason  # one copy of the rule: ado.py's

ORG, PROJECT = kit_config.ado()  # the project's .claude/product-os.json (kit_config.py); None when unset


def _link(wid):
    """The item's URL after two spaces, for the end of a result line; "" when org or project is unset."""
    u = kit_config.ado_url(wid, ORG, PROJECT)
    return f"  {u}" if u else ""


API = "api-version=7.0"


def _ready():
    """Stop with what to set, before the token is even read, when the org or project is unset."""
    try:
        if not ORG:
            kit_config.need("ado", "org")
        if not PROJECT:
            kit_config.need("ado", "project")
    except kit_config.NotConfigured as e:
        print(f"ado_write.py: {e}", file=sys.stderr)
        sys.exit(2)


def _hdr(ct="application/json"):
    tok = kit_config.token("ADO_PAT", "AZURE_DEVOPS_EXT_PAT")
    if not tok:
        sys.exit("No ADO_PAT / AZURE_DEVOPS_EXT_PAT in the environment or the OS keychain.")
    return {"Authorization": "Basic " + base64.b64encode((":" + tok).encode()).decode(),
            "Content-Type": ct}


def _req(url, body=None, method="GET", ct="application/json"):
    # bytes go up as they are (an attachment upload); anything else is JSON.
    data = body if isinstance(body, bytes) else (
        json.dumps(body).encode("utf-8") if body is not None else None)
    _ready()
    r = urllib.request.Request(url, headers=_hdr(ct), data=data, method=method)
    try:
        raw = urllib.request.urlopen(r, timeout=120).read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"ADO {e.code} {e.reason}: {e.read().decode('utf-8', 'replace')[:600]}")


def _p(path):
    return f"{ORG}/{urllib.parse.quote(PROJECT)}{path}"


# ── read-back ────────────────────────────────────────────────────────────────────────────────
# A write's exit 0 is not evidence it landed. Items created over the az path have kept only their
# first line while the command exited 0, and a hand-written read-back after every write is a step
# people skip. So the tool reads back itself, with a fresh GET: the write's own response echoes
# what was sent, not what was stored.
#
# What counts as the same, from what ADO did to text sent this way: a comment can come back byte
# for byte, or with &#39; decoded to '; ReproSteps and SystemInfo can come back with " written as
# &quot; and a space added before each </p>. So a comment or an HTML field compares the visible
# text with entities decoded and whitespace collapsed, plus every href, src and @mention, never
# the raw string; titles came back exactly as sent, so a plain-text field compares as text. A raw
# comparison reports files missing that are attached.

# Block tags end a run of text, so "<p>a</p><p>b</p>" reads as "a b", the same as with a newline.
_BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
          "table", "blockquote", "pre", "hr"}
# A "<" is text unless it opens a complete tag (a name, attributes with no "<" or ">" in them, then
# ">"), a complete comment, or a complete "<!...>". Python's parser drops what follows an unclosed
# "<min", "a<b then c" or "<!--" on 3.13 and keeps it on 3.9, so escaping such a "<" first gives one
# answer on both. Any tag name counts, so an added <tbody> is markup, not text. A "<" inside an
# attribute value breaks its tag into text, which can only read as not confirmed.
_TAG = re.compile(r"<(?!/?[A-Za-z][\w:-]*(?:\s[^<>]*)?/?>|!--.*?-->|![^<>-][^<>]*>)", re.S)
# A date, or a date and time with an optional zone. A date alone is midnight UTC.
_WHEN = re.compile(r"(\d{4})-(\d\d)-(\d\d)(?:T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,7}))?)?(Z|[+-]\d\d:\d\d)?)?")
# Fields whose case ADO sets for itself: a tree path comes back in the node's casing.
_ANY_CASE = {"system.iterationpath", "system.areapath", "system.state", "system.reason"}
# Fields ADO keeps as HTML, and comments. Any other text field is plain text, compared as text, so
# an "&lt;" stored in a title is what a reader sees, not a "<". A custom HTML field not listed here
# is compared as plain text too: ADO's re-encoding would read as not confirmed, never as a match.
_HTML = {"", "system.description", "system.history", "microsoft.vsts.common.acceptancecriteria",
         "microsoft.vsts.tcm.reprosteps", "microsoft.vsts.tcm.systeminfo"}


def _plain(value):
    return " ".join(str(value).split())


class _TextParts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links = [], []

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK:
            self.text.append(" ")
        self.links += [v for k, v in attrs if k in ("href", "src", "data-vss-mention") and v]

    def handle_endtag(self, tag):
        if tag in _BLOCK:
            self.text.append(" ")

    handle_startendtag = handle_starttag


def _visible(value):
    """(text, links) of an ADO value: tags dropped, entities decoded, whitespace collapsed."""
    p = _TextParts()
    p.feed(_TAG.sub("&lt;", "" if value is None else str(value)))
    p.close()
    return " ".join("".join(p.text).split()), p.links


def _tags(value):
    return {t.strip().lower() for t in str(value or "").split(";") if t.strip()}


def _when(value):
    """A date or date-time as a UTC datetime, or None if it isn't a whole, valid one."""
    m = _WHEN.fullmatch(str(value or "").strip())
    if not m:
        return None
    y, mo, d, h, mi, s, frac, zone = m.groups()
    try:
        t = datetime.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0),
                              int((frac or "0").ljust(6, "0")[:6]), tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    if zone and zone != "Z":
        shift = datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
        t = t - shift if zone[0] == "+" else t + shift
    return t


def _field(fields, ref):
    """A field by its reference name, which ADO matches without regard to case."""
    if ref in fields:
        return fields[ref]
    return next((v for k, v in fields.items() if k.lower() == ref.lower()), None)


def _same(ref, sent, stored):
    """True when ADO stored what was sent, by the rules in the module docstring."""
    ref = ref or ""
    if isinstance(stored, bool):
        return sent.strip().lower() == str(stored).lower()
    sent_when, stored_when = _when(sent), _when(stored)
    if sent_when and stored_when:  # the same moment: a date sent alone comes back as midnight UTC
        return sent_when == stored_when
    if ref.lower() in _ANY_CASE and isinstance(stored, str):
        return _plain(sent).lower() == _plain(stored).lower()
    if ref.lower() == "system.assignedto" or isinstance(stored, dict):
        if sent.strip() == "":
            return not stored
        if not stored:
            return False
        ids = ({str(stored.get(k) or "").strip().lower() for k in ("uniqueName", "displayName", "id")}
               if isinstance(stored, dict) else {str(stored).strip().lower()})
        s = sent.strip().lower()
        m = re.search(r"<([^<>]+)>\s*$", s)  # "Name <email>" names the identity by its email
        return bool(({s, m.group(1).strip()} if m else {s}) & (ids - {""}))
    if ref.lower() == "system.tags":
        return _tags(sent) == _tags(stored)
    if sent == "":
        return stored in (None, "")
    if stored is None:
        return False
    if isinstance(stored, (int, float)) and not isinstance(stored, bool):
        try:
            return float(sent) == float(stored)
        except ValueError:
            return False
    if ref.lower() in _HTML:
        return _visible(sent) == _visible(stored)
    return _plain(sent) == _plain(stored)


def _difference(sent, stored, ref=""):
    """The first place the two differ, short enough to print."""
    if stored is None:
        return "nothing is stored"
    if isinstance(stored, dict):
        return f"stored identity is {stored.get('uniqueName') or stored.get('displayName') or stored}"
    html = (ref or "").lower() in _HTML
    (st, sl), (gt, gl) = (_visible(sent), _visible(stored)) if html else ((_plain(sent), []), (_plain(stored), []))
    if st != gt:
        i = next((k for k in range(min(len(st), len(gt))) if st[k] != gt[k]), min(len(st), len(gt)))
        return (f"text differs at character {i} of {len(st)}: sent ...{st[max(0, i - 30):i + 40]!r}, "
                f"stored ...{gt[max(0, i - 30):i + 40]!r} ({len(gt)} characters)")
    lost = [u for u in sl if u not in gl]
    return f"link address missing: {lost[0]}" if lost else "links differ"


def _read_back(url):
    """GET for a read-back. A failure here exits 2: the write was sent, the result is unknown."""
    try:
        return _req(url)
    except SystemExit as e:
        why = e.code
    except Exception as e:  # a dropped connection, a timeout, a page that isn't JSON
        why = f"{type(e).__name__}: {e}"
    print(f"DID NOT RUN: the write was sent, but reading it back failed ({str(why)[:300]}).\n"
          f"  Whether it landed is unknown. Check the item before writing it again.")
    sys.exit(2)


def _ln(text):
    """text with each line ending in the URL of every item id on it that it doesn't already link."""
    return kit_config.ado_linked(text, ORG, PROJECT)


def _not_confirmed(what):
    print(_ln(f"WRITE NOT CONFIRMED: {what}"))
    sys.exit(1)


def _in_project(ids):
    """The ids among `ids` that are items of this project, asked live; the cache's ids when the
    question can't be answered (a stand-in or an old server), None when neither can be read."""
    if not ids:
        return set()
    try:
        d = _req(f"{ORG}/_apis/wit/workitems?ids={','.join(str(i) for i in sorted(ids)[:200])}"
                 f"&fields=System.TeamProject&errorPolicy=omit&{API}")
        if isinstance(d.get("value"), list):
            return {int(w["id"]) for w in d["value"] if w and str((w.get("fields") or {}).get(
                "System.TeamProject", "")).lower() == str(PROJECT).lower()}
    except (SystemExit, Exception):
        pass
    return ado_links.known_ids()


def _linked(text):
    """An HTML field or comment as it goes out: each markdown link made an anchor, and each bare
    work-item id this project holds linked to its item (ado_links.py). ADO links neither itself, so
    a #1234 sent bare stays plain text. Prints what it linked and what it left."""
    if not text or not ado_links.candidate_ids(text) and "](" not in text:
        return text
    ids = ado_links.candidate_ids(text)
    known = _in_project(ids)
    if known is None:
        # Neither ADO nor the ado_rest cache says which numbers are items, and a link to a number
        # that isn't one is worse than a bare id: send the ids as written, and say so.
        print(_ln("  ids left bare: neither ADO nor the ado_rest cache could say which of "
                  + ", ".join(f"#{w}" for w in sorted(ids)) + " are items; run `ado_rest.py pull` to link them"))
        return ado_links.md_links_to_anchors(text)
    new, hits = ado_links.html_link(text, known, lambda w: kit_config.ado_url(w, ORG, PROJECT))
    line = ado_links.summary(hits, _ln)
    if line:
        print(line)
    return new


def patch_fields(wid, pairs, link=True, rev=None):
    # A bare #1234 in an HTML field goes out as a link; every check below compares what was sent.
    # link=False sends the values as they are: an undo puts back exactly what was there. rev pins the
    # PATCH to the revision a check read (a `test /rev` op), so ADO refuses it if the item moved since.
    # Returns the revision read back.
    if link:
        pairs = [(ref, _linked(val) if ref.lower() in _HTML and val else val) for ref, val in pairs]
    # An "add" with an empty value is a silent no-op in ADO (seen on System.Tags): exit 0, rev
    # unchanged. Clearing a field takes "remove".
    ops = [{"op": "remove", "path": f"/fields/{ref}"} if val == "" else
           {"op": "add", "path": f"/fields/{ref}", "value": val} for ref, val in pairs]
    if rev is not None:
        ops.insert(0, {"op": "test", "path": "/rev", "value": rev})
    _req(_p(f"/_apis/wit/workitems/{wid}?{API}"), ops, "PATCH", "application/json-patch+json")
    back = _read_back(_p(f"/_apis/wit/workitems/{wid}?{API}"))
    f = back.get("fields") or {}
    for ref, val in pairs:
        if not _same(ref, val, _field(f, ref)):
            _not_confirmed(f"#{wid} {ref} at rev {back.get('rev')}: {_difference(val, _field(f, ref), ref)}")
    print(f"  #{wid} OK  state={f.get('System.State')}  rev={back.get('rev')}  "
          f"read back: {len(pairs)} of {len(pairs)} field(s) as sent" + _link(wid))
    if any(ref.lower() == "system.state" and str(val).lower() == "removed" for ref, val in pairs):
        print(_ln(f"  Next: Removed is the step before delete (python ado_write.py delete {wid}:{back.get('rev')}). "
                  f"An item that isn't dead goes to the dateless backlog iteration (ado.backlog_iteration) instead."))
    return back.get("rev")


def _me():
    """The identity behind the PAT, as (id, display_name).

    Match on the GUID, never on a name. `authenticatedUser.providerDisplayName` can be an
    EMAIL ("pat.doe@example.com") while a comment's `createdBy.displayName` is a formatted
    name ("Doe, Pat"), so comparing names compares two strings that can never be equal and
    the refusal below becomes unreachable: a gate that always passes, the silent-zero
    failure. Both endpoints carry the same stable GUID, so that is the comparison.

    The name is returned for the message text only. The PAT itself is never echoed.
    """
    d = _req(f"{ORG}/_apis/connectionData?api-version=7.0-preview")
    u = d.get("authenticatedUser") or {}
    return ((u.get("id") or "").strip().lower(),
            (u.get("customDisplayName") or u.get("providerDisplayName") or "").strip())


def _live_comments(wid):
    cs = [c for c in _req(_p(f"/_apis/wit/workItems/{wid}/comments"
                             f"?api-version=7.0-preview.3")).get("comments", [])
          if not c.get("isDeleted")]
    cs.sort(key=lambda c: c.get("createdDate", ""))
    return cs


def add_comment(wid, text, stack_reason=None):
    """Add a comment - but REFUSE to stack a second unanswered one on your own.

    WHY THIS GATE EXISTS. "One comment per thread - edit it, do not stack a second one"
    and "the detail belongs in the BODY, not the comment" can be written down and still
    lose: under load, sessions stack a correction comment anyway. A ticket should be clean
    and current; its history tab already records every change, so a pile of comments
    tracking the changes is noise for the reviewer.

    Prose did not hold, so this is the mechanism. Same shape as ado.py making the
    dup-search a hard precondition of `new`: the miss was COMPLIANCE, not guidance,
    and more prose does nothing about compliance.

    THE TEST is the newest live comment on the item, which implements the carve-out
    for threads someone has already replied to:
      - newest comment is MINE   -> nobody has replied since; patching it rewrites
                                    nothing anyone has read.          REFUSE.
      - newest comment is THEIRS -> they replied; my earlier comments are the context
                                    they answered, and collapsing them would leave
                                    their reply answering something off-screen. ALLOW.
      - no comments at all       -> ALLOW.

    `--stack "<reason>"` overrides, because a gate with no escape hatch gets routed
    around instead of used. The reason is required and is printed, so the override is
    visible rather than silent.
    """
    if len(text) > 700:
        print(f"  ! {len(text)} chars. Target is ~700; a wall of text gets rewritten by hand. "
              f"Mechanism and measurements belong in Description/AC; the comment points at them.")

    if stack_reason is None:
        cs = _live_comments(wid)
        if cs:
            newest = cs[-1]
            by = newest.get("createdBy") or {}
            who = (by.get("id") or "").strip().lower()
            me, my_name = _me()
            if me and who == me:
                head = " ".join(newest.get("text", "").split())[:160]
                sys.exit(_ln(
                    f"REFUSED: #{wid}'s newest comment ({newest['id']}) is already yours "
                    f"({my_name or 'this PAT'}), so nobody has replied since.\n"
                    f"  Stacking a second one makes the reviewer read a running log instead of "
                    f"one current message.\n\n"
                    f"  yours now: {head}...\n\n"
                    f"  Patch it instead:\n"
                    f'    python ado_write.py editcmt {wid} {newest["id"]} "<merged text>"\n\n'
                    f"  If the new material is mechanism, alternatives or measurements, it is the "
                    f"living spec -\n"
                    f"  rewrite the BODY and let the comment point at it:\n"
                    f'    python ado_write.py field {wid} System.Description "<clean current truth>"\n\n'
                    f"  A time gap, a closed item or a fix found later is no reason to stack. Merge it so\n"
                    f"  the comment reads as the resolution as it stands, with no dated \"Update\" block.\n\n"
                    f"  Genuinely need a second comment? "
                    f'python ado_write.py comment {wid} "<text>" --stack "<why>"'))
    else:
        print(f"  --stack override: {stack_reason}")

    text = _linked(text)
    d = _req(_p(f"/_apis/wit/workItems/{wid}/comments?api-version=7.0-preview.3"),
             {"text": text}, "POST")
    _confirm_comment(wid, d.get("id"), text, "added")


def edit_comment(wid, cid, text, link=True):
    text = _linked(text) if link else text
    _req(_p(f"/_apis/wit/workItems/{wid}/comments/{cid}?api-version=7.0-preview.3"),
         {"text": text}, "PATCH")
    _confirm_comment(wid, cid, text, "replaced")


def _confirm_comment(wid, cid, text, did):
    """Read the comment list again and find this comment by id. The list is the one the stacking
    gate already reads; ADO returns up to 200 comments, so a comment past that would read as
    missing."""
    back = _read_back(_p(f"/_apis/wit/workItems/{wid}/comments?api-version=7.0-preview.3"))
    found = [c for c in back.get("comments", []) if str(c.get("id")) == str(cid) and not c.get("isDeleted")]
    if cid is None or not found:
        _not_confirmed(f"#{wid} comment {cid}: ADO answered the write, but no such comment is on the item")
    if not _same(None, text, found[0].get("text")):
        _not_confirmed(f"#{wid} comment {cid}: {_difference(text, found[0].get('text'))}")
    print(f"  #{wid} comment {cid} {did} ({len(text)} chars), read back as sent" + _link(wid))


def del_comment(wid, cid):
    """Soft-delete a comment. Used ONLY to collapse a same-author pile after its content has
    been merged into the surviving comment - never to erase a record."""
    _req(_p(f"/_apis/wit/workItems/{wid}/comments/{cid}?api-version=7.0-preview.3"),
         None, "DELETE")
    print(_ln(f"  #{wid} comment {cid} deleted"))


def list_comments(wid):
    d = _req(_p(f"/_apis/wit/workItems/{wid}/comments?api-version=7.0-preview.3"))
    for c in d.get("comments", []):
        print(f"  id={c['id']}  {c.get('createdDate','')[:16]}  "
              f"{(c.get('createdBy') or {}).get('displayName','')}  {len(c.get('text',''))} chars")


def _refuse_same_category(wid, child_type, parent):
    """Exit before any write when `parent` is in the child's own backlog category (ado.py
    CATEGORY says why). The categories come from the board's own backlog configuration."""
    p = _req(_p(f"/_apis/wit/workitems/{parent}?fields=System.WorkItemType&{API}"))
    ptype = p.get("fields", {}).get("System.WorkItemType", "")
    cats = categories_from(_req(_p(f"/_apis/work/backlogconfiguration?{API}")))
    cat = same_category(child_type, ptype, cats)
    if cat:
        sys.exit(_ln("REFUSED: " + same_category_reason(f"#{wid}", child_type, parent, ptype, cat)
                     + f" `reparent {wid} <id> --keep-related` does both."))


def set_parent(wid, parent):
    """Attach an ORPHAN to its parent.

    A parent is a RELATION, not a field, so `field System.Parent <id>` silently does the wrong
    thing. This is the only correct path, and the fix for the `orphan` check in ado_rest.py audit
    without `az`. REFUSES if a parent link already exists, because ADO accepts a second
    Hierarchy-Reverse relation and then the item has two parents and neither tree is true.
    """
    cur = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
    for rel in (cur.get("relations") or []):
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            have = rel.get("url", "").rsplit("/", 1)[-1]
            sys.exit(_ln(f"REFUSED: #{wid} already has parent #{have}. "
                         f"Remove it deliberately before re-parenting to #{parent}."))
    _refuse_same_category(wid, cur.get("fields", {}).get("System.WorkItemType", ""), parent)
    ops = [{"op": "add", "path": "/relations/-", "value": {
        "rel": "System.LinkTypes.Hierarchy-Reverse",
        "url": f"{ORG}/_apis/wit/workItems/{parent}"}}]
    d = _req(_p(f"/_apis/wit/workitems/{wid}?{API}"), ops, "PATCH",
             "application/json-patch+json")
    print(_ln(f"  #{wid} OK  parent -> #{parent}  rev={d.get('rev')}" + _link(wid)))


def reparent(wid, parent, keep_related=False, rev=None):
    """MOVE an item to a different parent. Removes the existing Hierarchy-Reverse relation by INDEX
    and adds the new one in one patch, so the item is never briefly parentless and never briefly
    double-parented. The index is the position in the item's own relations array - ADO has no
    remove-by-url - so it is read immediately before the patch and the patch carries the rev it was
    read at, which makes a concurrent edit fail loudly instead of silently removing the wrong link.

    --keep-related links the old parent as Related in the same patch: the fix ADO's "same category
    hierarchy" banner asks for, which moves the item up a level without losing the link to the
    Task or Story it was filed under (a Bug filed under a QA Task, say).

    rev, from a batch, is the revision its check read: an item that moved since is refused unsent.
    """
    cur = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
    if rev is not None and cur.get("rev") != rev:
        sys.exit(_ln(f"REFUSED: #{wid} changed after the batch read it (rev {rev}, now {cur.get('rev')}). "
                     f"Nothing sent for it."))
    rels = cur.get("relations") or []
    idx = [i for i, r in enumerate(rels)
           if r.get("rel") == "System.LinkTypes.Hierarchy-Reverse"]
    if not idx:
        sys.exit(_ln(f"REFUSED: #{wid} has no parent to move. Use `parent` to attach one."))
    if len(idx) > 1:
        sys.exit(_ln(f"REFUSED: #{wid} has {len(idx)} parent links. Fix that by hand first."))
    old = rels[idx[0]].get("url", "").rsplit("/", 1)[-1]
    if str(old) == str(parent):
        print(_ln(f"  #{wid} already parented to #{parent}, nothing to do"))
        return
    _refuse_same_category(wid, cur.get("fields", {}).get("System.WorkItemType", ""), parent)
    ops = [
        {"op": "test", "path": "/rev", "value": cur.get("rev")},
        {"op": "remove", "path": f"/relations/{idx[0]}"},
        {"op": "add", "path": "/relations/-", "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"{ORG}/_apis/wit/workItems/{parent}"}},
    ]
    related = {r.get("url", "").rsplit("/", 1)[-1] for r in rels
               if r.get("rel") == "System.LinkTypes.Related"}
    if keep_related and str(old) not in related:
        ops.append({"op": "add", "path": "/relations/-", "value": {
            "rel": "System.LinkTypes.Related", "url": f"{ORG}/_apis/wit/workItems/{old}"}})
    d = _req(_p(f"/_apis/wit/workitems/{wid}?{API}"), ops, "PATCH",
             "application/json-patch+json")
    print(_ln(f"  #{wid} OK  parent #{old} -> #{parent}"
              + (f", #{old} kept as related" if keep_related else "") + f"  rev={d.get('rev')}" + _link(wid)))


# ── whose text a write drops ─────────────────────────────────────────────────────────────────────
# A batch's expects can be read after a teammate's text is already in, so the drift check passes and
# the batch replaces what they wrote. So before `field` or `batch` sends a text field, each line the
# new value drops is credited to the first revision that shows it, and a line someone else first
# wrote refuses the write. First, not latest: once our own revision puts their lines back, "latest"
# would let a later write of ours drop them. One exemption: putting back exactly what our own latest
# revision of the field replaced, which is what an undo file does. Some refusals are rewrites agreed
# with their author, so `--replaces` exists, and its reason sits on the command line, never in the
# file (ask_rules.override).
_CHECKED = {"system.title", "system.description", "microsoft.vsts.common.acceptancecriteria",
            "microsoft.vsts.tcm.reprosteps", "microsoft.vsts.tcm.systeminfo"}
_OURS = "(this batch)"  # the author of a value an earlier entry of the same batch sets


class _BlockLines(HTMLParser):
    """The visible text of an HTML value, one entry per block: "<div>a</div><div>b</div>" is ["a", "b"].
    Inline markup (a <b>, a link, the green highlight pasting from ADO's history view leaves) doesn't
    split a line."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur = [], []

    def end(self):
        line = " ".join("".join(self.cur).split())  # str.split() takes a no-break space as whitespace too
        if line:
            self.lines.append(line)
        self.cur = []

    def handle_data(self, data):
        self.cur.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK:
            self.end()

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag in _BLOCK:
            self.end()


def _lines(ref, value):
    """A text field's lines as a reader sees them: each block of an HTML field; a plain field whole."""
    if value is None or str(value) == "":
        return []
    if (ref or "").lower() not in _HTML:
        v = _plain(value)
        return [v] if v else []
    p = _BlockLines()
    p.feed(_TAG.sub("&lt;", str(value)))
    p.close()
    p.end()
    return p.lines


def _dropped(ref, live, new):
    """The lines of `live` that `new` doesn't have, in order, each once."""
    keep = set(_lines(ref, new))
    return list(dict.fromkeys(line for line in _lines(ref, live) if line not in keep))


def _updates(wid):
    """Every update of the item, oldest first, from workItems/{id}/updates, 200 to a page; None when it
    can't be read (a 404 for a deleted item, an error, a page that isn't a list)."""
    out, skip = [], 0
    try:
        while True:
            d = _req(_p(f"/_apis/wit/workItems/{wid}/updates?$top=200&$skip={skip}&{API}"))
            page = d.get("value") if isinstance(d, dict) else None
            if not isinstance(page, list):
                return None
            out += page
            if len(page) < 200:
                return sorted(out, key=lambda u: (u.get("id") or 0))
            skip += 200
    except (SystemExit, Exception):
        return None


def _touches(updates, ref):
    """(author id, author name, old value, new value) for each update that changed `ref`, oldest first.
    A child link added to an item makes an update with no field change, so most updates touch nothing."""
    out = []
    for u in updates:
        ch = next((v for k, v in (u.get("fields") or {}).items() if k.lower() == ref.lower()), None)
        if isinstance(ch, dict) and ("newValue" in ch or "oldValue" in ch):
            by = u.get("revisedBy") or {}
            out.append(((by.get("id") or "").strip().lower(),
                        by.get("displayName") or by.get("uniqueName") or "someone",
                        ch.get("oldValue"), ch.get("newValue")))
    return out


def _line_problem(ref, live, new, touches, me):
    """[(line, author)] for each line of `live` that `new` drops and someone other than `me` first wrote,
    or None. A line the history never shows counts as someone else's: a check that can't tell refuses.
    Putting back exactly the value our own latest change of the field replaced passes (an undo)."""
    dropped = _dropped(ref, live, new)
    if not dropped:
        return None
    ours = (me, _OURS)
    if touches and touches[-1][0] in ours and _lines(ref, new) == _lines(ref, touches[-1][2]):
        return None
    first = {}
    for who, name, _, val in touches:
        for line in _lines(ref, val):
            first.setdefault(line, (who, name))
    theirs = [(line, first[line][1] if line in first else "an author the history doesn't show")
              for line in dropped if (first.get(line) or (None,))[0] not in ours]
    return theirs or None


def _merged(ref, theirs, new):
    """What a refusal offers instead: their lines on top, then ours. Their
    lines come back as text, without their markup. A plain field (a Title) can't hold two: theirs stays."""
    if ref.lower() not in _HTML:
        return theirs[0][0]
    import html
    return ("".join(f"<div>{html.escape(line, quote=False)}</div>" for line, _ in theirs)
            + "<div><br> </div>" + (new or ""))


def _text_check(entries, replaces=(), reason=None):
    """Before anything is sent: the lines each entry's text fields would drop that someone else first
    wrote. Returns (refusal lines, {id: rev the check read}, notes). Entries for one item are taken in
    order, each against the value the entries before it leave, so a line an earlier entry adds is ours.
    An id in `replaces` is let through, and the note says so; one with nothing to lift is named too."""
    problems, revs, notes, live, hist, after = [], {}, [], {}, {}, {}
    me, lifted = None, set()
    for it in entries:
        wid = str(it["id"])
        for ref, val in (it.get("set") or {}).items():
            if ref.lower() not in _CHECKED:
                continue
            key = (wid, ref.lower())
            if key in after:
                cur = after[key][-1][3]
            else:
                if wid not in live:
                    try:
                        d = _req(_p(f"/_apis/wit/workitems/{wid}?{API}"))
                        live[wid], revs[wid] = d.get("fields") or {}, d.get("rev")
                    except SystemExit as e:
                        live[wid] = None
                        problems.append(_ln(f"  REFUSED #{wid}: the item can't be read, so whose text it drops is "
                                            f"unknown ({str(e.code)[:200]})"))
                if live[wid] is None:
                    continue
                v = _field(live[wid], ref)
                cur = "" if v is None else str(v)
            new = "" if val is None else str(val)
            if _dropped(ref, cur, new):
                if me is None:
                    try:
                        me = _me()[0]
                    except SystemExit:
                        me = ""
                if not me:
                    problems.append(_ln(f"  REFUSED #{wid} {ref}: the PAT's own identity can't be read, so whose "
                                        f"lines it drops is unknown"))
                    continue
                if wid not in hist:
                    hist[wid] = _updates(wid)
                if hist[wid] is None:
                    problems.append(_ln(f"  REFUSED #{wid} {ref}: its revision history can't be read, so who wrote "
                                        f"the {len(_dropped(ref, cur, new))} line(s) it drops is unknown"))
                else:
                    theirs = _line_problem(ref, cur, new, _touches(hist[wid], ref) + after.get(key, []), me)
                    if theirs and wid in replaces:
                        lifted.add(wid)
                        notes.append(_ln(f"  --replaces lifts it on #{wid} {ref}, which drops {len(theirs)} line(s) "
                                         f"{theirs[0][1]} first wrote: {reason}"))
                    elif theirs:
                        authors = ", ".join(dict.fromkeys(a for _, a in theirs))
                        problems.append(_ln(f"  REFUSED #{wid} {ref}: drops {len(theirs)} line(s) {authors} first "
                                            f"wrote, by its revision history:"))
                        problems += [_ln(f"      {a}: {line[:160]!r}") for line, a in theirs]
                        problems.append(_ln(f"    merged, their lines on top: {_merged(ref, theirs, new)}"))
            after.setdefault(key, []).append((_OURS, "this batch", cur, new))
    for wid in sorted(set(replaces) - lifted, key=lambda w: int(w) if str(w).isdigit() else 0):
        notes.append(_ln(f"  --replaces names #{wid}, but nothing sent to it drops another author's line: "
                         f"nothing to lift there"))
    return problems, revs, notes


_BATCH_KEYS = {"id", "expect", "set", "comment", "raw", "status"}  # "status" is what an undo file adds
_BATCH_COMMENT_KEYS = {"id", "text", "expect"}


def batch(path, replaces=None):
    """Apply a reviewed list of writes in one run, so one command covers the list.

    The file is a JSON list. Each entry: {"id": N, "expect": {ref: value}, "set": {ref: value},
    "comment": {"id": commentId, "text": "...", "expect": "..."}}, all but "id" optional. "set" may
    name System.Parent, which goes through reparent() and its refusals; "comment" replaces that
    comment's text, as editcmt does. An item whose "expect" no longer matches what ADO holds, a
    field's or the comment's, is skipped: someone changed it after the list was made. HTML values
    and comment text go out linked, as `field` and `editcmt` send them, unless the entry says
    "raw": true. Before each write the item's current values go to <file>.undo.json, in this same
    format with "raw": true and the linked values as its "expect", so `batch <file>.undo.json` puts
    back exactly what was there. The run stops at the first write that fails, since what follows
    may depend on it. Any other key, or an entry with no set and no comment, refuses the whole file before
    a write, and so does a comment edit with no comment.expect in an entry that isn't from an undo file
    (one with "status"). An undo entry with nothing to put back is counted and says so.

    Before any write, every entry is checked for text it drops that someone else first wrote
    (_text_check); one refusal refuses the whole file. replaces is (ids, why) from the command line's
    `--replaces <id>,<id> "<why>"`, and lets those items through. Each item's first write carries a
    `test /rev` at the revision that check read, and later writes in the run at the revision this run's
    own write left. System.History is a discussion comment, not a value: an expect never compares it, a
    History set to "" is left out, and an undo entry never holds it.
    Returns 0 when every item applied, 1 otherwise.
    """
    with open(path, encoding="utf-8") as fh:
        items = json.load(fh)
    # A key batch doesn't know is sent nowhere: {"id": N, "delete": true} would read as "1 of 1 applied", and
    # so would an entry with nothing to send. A delete, restore or attach runs as its own command, since a batch's
    # command line names only the file.
    odd = []
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict) or "id" not in it:
            odd.append((n, "no id"))
            continue
        keys = sorted(set(it) - _BATCH_KEYS)
        if isinstance(it.get("comment"), dict):
            keys += [f"comment.{k}" for k in sorted(set(it["comment"]) - _BATCH_COMMENT_KEYS)]
        if keys:
            odd.append((n, f"{', '.join(keys)}, which batch doesn't send"))
        elif not it.get("set") and not it.get("comment") and "status" not in it:
            odd.append((n, "nothing to send: no set and no comment"))
        elif isinstance(it.get("comment"), dict) and it["comment"].get("expect") is None and "status" not in it:
            odd.append((n, f"a comment edit with no comment.expect, the text it replaces (python ado_write.py "
                           f"comments {it['id']} lists them), so a change since the list was made would go unseen"))
    if odd:
        n, why = odd[0]
        print(_ln(f"REFUSED: item {n} of {path} has {why}" + (f" ({len(odd)} items refused)" if len(odd) > 1 else "")
                  + ". Batch sends state, field, parent and comment edits only; run a delete, restore or attach as "
                    "its own command. Nothing sent."))
        return 1
    undo_path = re.sub(r"\.json$", "", path) + ".undo.json"
    if os.path.exists(undo_path):
        print(f"REFUSED: {undo_path} is there from an earlier run, and this run would overwrite it. "
              f"Put the items still to do in a new batch file.")
        return 1
    ids, why = (set(str(i) for i in replaces[0]), replaces[1]) if replaces else (set(), None)
    problems, checked_at, notes = _text_check(items, ids, why)
    for line in notes:
        print(line)
    if problems:
        print("\n".join(problems))
        hit = sorted({m.group(1) for m in (re.match(r"\s*REFUSED #(\d+)", p) for p in problems) if m}, key=int)
        theirs = sorted({m.group(1) for m in (re.match(r"\s*REFUSED #(\d+) \S+: drops ", p) for p in problems) if m},
                        key=int)
        print(_ln(f"REFUSED: {path} can't be sent as it is, for {len(hit)} item(s) ({', '.join('#' + h for h in hit)}). "
                  f"Nothing sent."
                  + (f" Keep their lines: the merged value above puts them on top. If replacing them is agreed with "
                     f"their author, name the items on the command line: python ado_write.py batch {path} "
                     f"--replaces {','.join(theirs)} \"<why, in plain words>\"" if theirs else "")
                  + (" An item whose history or identity can't be read has no override: check it by hand, then send "
                     "it on its own." if set(hit) - set(theirs) else "")))
        return 1
    undo, applied, skipped, written = [], [], [], set()

    def save_undo():
        tmp = undo_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(undo, fh, indent=1, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, undo_path)

    for n, it in enumerate(items, 1):
        wid = str(it["id"])
        # System.Parent comes back only with relations expanded
        got = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
        f, pin = got.get("fields") or {}, got.get("rev")
        if wid in checked_at and wid not in written and pin != checked_at[wid]:
            print(_ln(f"  SKIPPED #{wid}: it changed after the text check read it (rev {checked_at[wid]}, now {pin}), "
                      f"so that check is stale. Someone changed it after the list was made."))
            skipped.append(wid)
            continue
        drift = [(ref, val) for ref, val in (it.get("expect") or {}).items()
                 if ref.lower() != "system.history" and not _same(ref, str(val), _field(f, ref))]
        if drift:
            ref, val = drift[0]
            print(_ln(f"  SKIPPED #{wid}: {ref} is now {_field(f, ref)!r}, the list expected {val!r}. "
                      f"Someone changed it after the list was made."))
            skipped.append(wid)
            continue
        raw = bool(it.get("raw"))
        cmt = it.get("comment")
        old_text = None
        if cmt:
            old_text = _req(_p(f"/_apis/wit/workItems/{wid}/comments/{cmt['id']}?api-version=7.0-preview.3")).get("text", "")
            if cmt.get("expect") is not None and not _same(None, str(cmt["expect"]), old_text):
                print(_ln(f"  SKIPPED #{wid}: comment {cmt['id']} is not the text the list expected. "
                          f"Someone changed it after the list was made."))
                skipped.append(wid)
                continue
        # Link here, not in patch_fields, so the undo file's "expect" holds what ADO will store.
        sets = {ref: (str(val) if raw or ref.lower() not in _HTML or not val else _linked(str(val)))
                for ref, val in (it.get("set") or {}).items()}
        # A History set to "" was an undo putting back "no comment"; sent, it is a remove on History.
        if any(ref.lower() == "system.history" and val == "" for ref, val in sets.items()):
            sets = {ref: val for ref, val in sets.items() if not (ref.lower() == "system.history" and val == "")}
            print(_ln(f"  #{wid}: left out System.History \"\": it is a discussion comment, which an undo can't take back"))
        cmt_text = None if not cmt else (cmt["text"] if raw else _linked(cmt["text"]))
        if not sets and not cmt:
            print(_ln(f"  #{wid} nothing to send: an undo can't take back a discussion comment (System.History)"))
            applied.append(wid)
            continue
        before = {}
        for ref in sets:
            if ref.lower() == "system.history":  # GET returns only the latest revision's comment: no value to put back
                continue
            v = _field(f, ref)
            before[ref] = "" if v is None else str(v.get("uniqueName") or "" if isinstance(v, dict) else v)
        entry = {"id": int(wid), "raw": True, "expect": {k: v for k, v in sets.items() if k.lower() != "system.history"},
                 "set": before, "status": "sending"}
        if cmt:
            entry["comment"] = {"id": cmt["id"], "text": old_text, "expect": cmt_text}
        _promised(wid, sets.get("System.Parent"))
        undo.append(entry)
        save_undo()
        try:
            parent = sets.pop("System.Parent", None)
            if parent:
                reparent(wid, parent, rev=pin)
                back = _read_back(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
                now, pin = _field(back.get("fields") or {}, "System.Parent"), back.get("rev")
                if not _same("System.Parent", parent, now):
                    _not_confirmed(f"#{wid} System.Parent: sent {parent}, stored {now}")
            written.add(wid)
            if sets:
                pin = patch_fields(wid, list(sets.items()), link=False, rev=pin)
            if cmt:
                edit_comment(wid, cmt["id"], cmt_text, link=False)
        except SystemExit as e:
            entry["status"] = "failed"
            save_undo()
            if isinstance(e.code, str):
                print(e.code)
            print(_ln(f"  STOPPED at #{wid}, item {n} of {len(items)}: the write above failed, so nothing "
                      f"after it ran. What landed is in {undo_path}."))
            break
        entry["status"] = "applied"
        save_undo()
        applied.append(wid)
    print(_ln(f"batch: {len(applied)} of {len(items)} applied, {len(skipped)} skipped"
              + (f" ({', '.join('#' + s for s in skipped)})" if skipped else "")
              + f". Undo: python ado_write.py batch {undo_path}"))
    return 0 if len(applied) == len(items) else 1


ATTACH_MAX = 60 * 1024 * 1024  # one-request upload; ADO wants a chunked upload past ~130 MB


def attach(wid, paths, inline=False):
    """Upload files and link each to the item as an AttachedFile relation.

    So a bug carries its pictures (the design frame and the build at the same width). Two steps per file: POST the bytes to /wit/attachments,
    which returns a URL, then one PATCH that adds every relation. The PATCH carries the rev it
    was read at, so a concurrent edit fails loudly instead of being overwritten by --inline.

    A file already linked under the same name and size is skipped, so running the same command
    twice adds nothing. A same-name file of a different size is a new picture and is attached.
    """
    for p in paths:
        if not os.path.isfile(p):
            sys.exit(f"REFUSED: no file at {p}. Nothing uploaded.")
        if os.path.getsize(p) > ATTACH_MAX:
            sys.exit(f"REFUSED: {p} is over {ATTACH_MAX // 2**20} MB. Nothing uploaded.")
    cur = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
    have = {((r.get("attributes") or {}).get("name"), (r.get("attributes") or {}).get("resourceSize"))
            for r in (cur.get("relations") or []) if r.get("rel") == "AttachedFile"}
    ops, imgs = [{"op": "test", "path": "/rev", "value": cur.get("rev")}], []
    for p in paths:
        name, size = os.path.basename(p), os.path.getsize(p)
        if (name, size) in have:
            print(_ln(f"  #{wid} already has {name} ({size} bytes), skipped"))
            continue
        with open(p, "rb") as f:
            up = _req(_p(f"/_apis/wit/attachments?fileName={urllib.parse.quote(name)}&{API}"),
                      f.read(), "POST", "application/octet-stream")
        ops.append({"op": "add", "path": "/relations/-",
                    "value": {"rel": "AttachedFile", "url": up["url"]}})
        imgs.append((name, up["url"]))
        print(f"  uploaded {name}  {up['url']}")
    if not imgs:
        print(_ln(f"  #{wid} nothing new to attach"))
        return
    if inline:
        f = cur.get("fields") or {}
        ref = BODY_FIELD.get(f.get("System.WorkItemType"), "System.Description")
        tags = "".join(f'<p><img src="{u}" alt="{n}"></p>' for n, u in imgs)
        ops.append({"op": "add", "path": f"/fields/{ref}", "value": (f.get(ref) or "") + tags})
    d = _req(_p(f"/_apis/wit/workitems/{wid}?{API}"), ops, "PATCH",
             "application/json-patch+json")
    # Read it back, as every write here should be: rc=0 from a PATCH is not evidence the relation
    # landed (the ado skill, section 7). Each upload's URL must be an AttachedFile on the item, and
    # with --inline in the body field too. The upload returns its URL with ?fileName=<name>; the
    # relation stores it without the query (comparing whole URLs reports attached files as
    # missing), so the comparison is on the URL before its query. The body keeps the URL as sent.
    back = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
    rels = {r.get("url", "").split("?")[0]: r.get("attributes") or {} for r in (back.get("relations") or [])
            if r.get("rel") == "AttachedFile"}
    body = (back.get("fields") or {}).get(ref, "") if inline else ""
    missing = [n for n, u in imgs if u.split("?")[0] not in rels or (inline and u not in body)]
    for n, u in imgs:
        if u.split("?")[0] in rels:
            print(f"  read back {n}: attached, {rels[u.split('?')[0]].get('resourceSize', '?')} bytes")
    if missing:
        sys.exit(_ln(f"READ BACK FAILED: #{wid} rev={back.get('rev')} does not show {', '.join(missing)}"
                     + (" in its attachments and body" if inline else " in its attachments")))
    print(f"  #{wid} OK  {len(imgs)} of {len(imgs)} attached{' and shown in the body' if inline else ''}"
          f", read back  rev={back.get('rev')}" + _link(wid))


# The body field per work-item type, for attach --inline; any type not listed uses System.Description.
BODY_FIELD = {"Bug": "Microsoft.VSTS.TCM.ReproSteps"}


# ── delete and restore ───────────────────────────────────────────────────────────────────────
# A delete sends the item to the project's recycle bin and never passes destroy=true, so `restore`
# brings it back. The checks are the ones a careful close-out delete runs by hand: the item must be
# Removed at the rev the list was reviewed at, the undo file goes to disk before the DELETE, and the
# read-back wants the item to answer 404 and the recycle bin to hold it. The undo folder is
# ado.undo_dir, else ~/.local/share/product-os/ado-undo.
UNDO_DIR = os.path.expanduser(kit_config.get("ado", "undo_dir")
                              or kit_config.home_dir(os.path.join(".local", "share"), "ado-undo"))
_BIN = ("7.1", "7.1-preview.3")  # the recycle bin's api-versions; one that answers 400 passes to the next
# Test artifacts take their own delete path, and "test cases deleted through APIs or non-portal methods are
# permanently deleted" (Microsoft Learn, "Delete test artifacts"), so delete refuses them.
_TEST_TYPES = {"Test Plan", "Test Suite", "Test Case", "Shared Steps", "Shared Parameter"}


def _status(url):
    """(HTTP status, body) for a GET that may rightly answer 404, without exiting; (None, why) when no
    answer came at all."""
    _ready()
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=_hdr()), timeout=120).read().decode("utf-8")
        return 200, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:  # a dropped connection, a timeout, a page that isn't JSON
        return None, {"message": f"{type(e).__name__}: {e}"}


def _in_bin(wid):
    """(status, api-version) of the recycle bin's entry for the item: 200 holds it, 404 doesn't."""
    for v in _BIN:
        code, _ = _status(_p(f"/_apis/wit/recyclebin/{wid}?api-version={v}"))
        if code != 400:
            return code, v
    return code, v


def _unread(what, code):
    """Exit 2 when a read-back got no usable answer: the write was sent, the result is unknown."""
    if code not in (200, 404):
        print(_ln(f"DID NOT RUN: the write was sent, but reading back {what} failed (answered {code}).\n"
                  f"  Whether it landed is unknown. Check the item before writing it again."))
        sys.exit(2)


def delete(wid, rev, undo_dir=UNDO_DIR):
    """Send a Removed item to the recycle bin. Refuses a test artifact, an item not in Removed or not at `rev` (the
    rev the delete was reviewed at), and one with a child not in Removed; writes the undo file before the DELETE."""
    url = _p(f"/_apis/wit/workitems/{wid}?{API}")
    cur = _req(_p(f"/_apis/wit/workitems/{wid}?$expand=relations&{API}"))
    f = cur.get("fields") or {}
    if f.get("System.WorkItemType") in _TEST_TYPES:
        sys.exit(_ln(f"REFUSED: #{wid} is a {f['System.WorkItemType']}. Test artifacts skip the recycle bin: one deleted "
                     f"through the API is gone for good. Delete it from Test Plans by hand. Nothing deleted."))
    if f.get("System.State") != "Removed" or str(cur.get("rev")) != str(rev):
        sys.exit(_ln(f"REFUSED: #{wid} is {f.get('System.State')} at rev {cur.get('rev')}; a delete needs it Removed "
                     f"at rev {rev}, the rev it was reviewed at. Nothing deleted."))
    # ADO doesn't cascade a delete: a deleted parent leaves its open children behind with no parent.
    kids = [r.get("url", "").rsplit("/", 1)[-1] for r in cur.get("relations") or []
            if r.get("rel") == "System.LinkTypes.Hierarchy-Forward"]
    if kids:
        got = _req(f"{ORG}/_apis/wit/workitems?ids={','.join(kids[:200])}&fields=System.State"
                   f"&errorPolicy=omit&{API}").get("value") or []
        live = [f"#{w['id']} ({(w.get('fields') or {}).get('System.State')})" for w in got
                if w and (w.get("fields") or {}).get("System.State") != "Removed"]
        if live:
            sys.exit(_ln(f"REFUSED: #{wid} has {len(live)} child item(s) not in Removed: {', '.join(live[:10])}. "
                         f"Deleting it leaves them with no parent. Remove or move them first. Nothing deleted."))
    # The item answered at `rev` above, so an undo file already there is from a run whose DELETE never landed
    # (a refusal, a 403, a timeout). Replacing it loses nothing; refusing would block every retry.
    undo = os.path.join(undo_dir, f"{wid}-rev{rev}.undo.json")
    if os.path.exists(undo):
        print(f"  replacing {undo}: the item is still there at rev {rev}, so the delete that wrote it never landed")
    os.makedirs(undo_dir, exist_ok=True)
    tmp = undo + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        # A restore puts the item at the root path when its area or iteration node was deleted since.
        json.dump({"id": int(wid), "rev": cur.get("rev"), "state": "Removed", "title": f.get("System.Title") or "",
                   "area": f.get("System.AreaPath") or "", "iteration": f.get("System.IterationPath") or "",
                   "undo": f"python ado_write.py restore {wid}"}, fh, indent=1, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, undo)
    _req(url, None, "DELETE")
    gone, _ = _status(url)
    _unread(f"#{wid}", gone)
    binned, _ = _in_bin(wid)
    _unread("the recycle bin", binned)
    if gone != 404:
        _not_confirmed(f"#{wid} still answers {gone} after the delete")
    if binned != 200:
        _not_confirmed(f"#{wid} is gone, but the recycle bin doesn't hold it, so restore can't bring it back")
    print(_ln(f"  #{wid} OK  deleted at rev {rev}, read back: the item answers 404 and the recycle bin holds it. "
              f"Undo: python ado_write.py restore {wid} (also in {undo})"))


def delete_many(pairs, undo_dir=UNDO_DIR):
    """delete() each (id, rev) pair in order, so one command line names every id. A pair refused or not confirmed
    doesn't stop the rest. Returns the worst exit: 0 all deleted, 1 any refused or not confirmed, 2 any whose
    read-back didn't run."""
    done, missed, worst = [], [], 0
    for wid, rev in pairs:
        try:
            delete(wid, rev, undo_dir)
            done.append(wid)
        except SystemExit as e:
            if isinstance(e.code, str):
                print(e.code)
            missed.append(wid)
            worst = max(worst, e.code if isinstance(e.code, int) else 1)
    if len(pairs) > 1:
        print(_ln(f"delete: {len(done)} of {len(pairs)} deleted and in the recycle bin"
                  + (f"; not deleted: {', '.join('#' + w for w in missed)}" if missed else "")))
    return worst


def restore(wid):
    """Bring an item back from the recycle bin: the undo a delete writes. Refuses an item the bin doesn't hold."""
    code, v = _in_bin(wid)
    if code != 200:
        sys.exit(_ln(f"REFUSED: the recycle bin doesn't hold #{wid} (it answers {code}). Nothing restored."))
    _req(_p(f"/_apis/wit/recyclebin/{wid}?api-version={v}"), {"IsDeleted": False}, "PATCH")
    back, item = _status(_p(f"/_apis/wit/workitems/{wid}?{API}"))
    _unread(f"#{wid}", back)
    binned, _ = _in_bin(wid)
    _unread("the recycle bin", binned)
    if back != 200 or binned != 404:
        _not_confirmed(f"#{wid} answers {back} and the recycle bin {binned} after the restore; both should have moved")
    f = item.get("fields") or {}
    print(_ln(f"  #{wid} OK  restored, read back: the item answers 200 at rev {item.get('rev')} "
              f"({f.get('System.State')}) and the recycle bin no longer holds it") + _link(wid))


# ── earlier promises ─────────────────────────────────────────────────────────────────────────
# A session can write "I'll copy that text onto #1234, then delete #5678" and then delete #5678 without the
# copy. So before a write, the session's own earlier sentences that name an item the write touches and put
# work off are printed (session_close.promises_about). Nothing is printed when there are none; a log that
# can't be read says so. It never stops the write. _LOGS is the projects folder, so the self-test reads a
# planted log instead of yours.
_LOGS = None


def _promised(*ids):
    for wid in dict.fromkeys(str(i) for i in ids if str(i).isdigit()):
        try:
            import session_close
            got, why = session_close.promises_about(int(wid), projects=_LOGS or session_close.PROJECTS)
        except Exception as e:  # advice only: a broken reader never blocks the write
            got, why = [], f"{type(e).__name__}: {e}"
        if why:
            print(_ln(f"  earlier promises about #{wid}: did not run ({why})"))
        for at, s in got:
            print(_ln(f"  #{wid}, said earlier at {at[11:16]}Z: {s}"))


# ── self-test ────────────────────────────────────────────────────────────────────────────────
# A stand-in ADO on 127.0.0.1, one per case. A case says what the server keeps of a write
# (`store`: the value kept, or None to keep nothing), what it answers, and the exit a correct tool
# gives. The server always answers a write by echoing what was SENT, so a tool that trusts the
# write's response is fooled. Reads before the write always succeed; `read_status` applies after.
# `existing` puts comments on the item first; `stored_ref` stores a field under another name.
# A case passes on the exit code AND on its words: `says` must be printed (by default "read back",
# "WRITE NOT CONFIRMED" or "DID NOT RUN" for exit 0, 1 or 2), and `names`, when given, too. So a
# crash that happens to exit 1 is not a pass.
# `--against <file>` runs the same cases on another copy of this tool: run on a copy without the
# read-back, the planted bad cases must miss.

_ORIGINAL = "ORIGINAL COMMENT"
_SAYS = {0: "read back", 1: "WRITE NOT CONFIRMED", 2: "DID NOT RUN"}

# The maker's cases: known-good writes, from what ADO did to text this tool sent, and the calls on
# field types made from that reading. A read-back that fails these
# cries wolf.
_MAKER_CASES = [
    dict(name="stores the text as sent", op="comment",
         sent="<div>Answered by design: keep the shared footer line on every page.</div>",
         store=lambda s: s, expect=0),
    dict(name="decodes &#39; and changes whitespace", op="comment",
         sent="<div>the pricing page&#39;s question,\n  so the  row stays</div>",
         store=lambda s: s.replace("&#39;", "'").replace(",\n  so the  ", ", so the "), expect=0),
    dict(name="an edit stored as sent", op="editcmt", sent="<p>Fixed on <code>2fed223</code>.</p>",
         store=lambda s: s, expect=0),
    dict(name="state stored as sent", op="state", sent="Resolved", prior="Active",
         store=lambda s: s, expect=0),
    dict(name="AssignedTo comes back as an identity", op="field", ref="System.AssignedTo",
         sent="Pat Doe <pat.doe@example.com>", prior=None, expect=0,
         store=lambda s: {"displayName": "Doe, Pat", "uniqueName": "pat.doe@example.com", "id": "5e1f"}),
    dict(name="Tags come back reordered, in the project's casing", op="field", ref="System.Tags",
         sent="decision; Checkout", prior=None, store=lambda s: "checkout; Decision", expect=0),
    dict(name="a cleared field comes back absent", op="field",
         ref="Microsoft.VSTS.Common.AcceptanceCriteria", sent="", prior="<p>old</p>",
         store=lambda s: s, expect=0),
    dict(name="writes \" as &quot; and adds a space before </p>", op="field",
         ref="Microsoft.VSTS.TCM.ReproSteps",
         sent='<p>The home page\'s "Find your starting point" row.</p>\n\n<p><b>1. A focus ring</b> is cut.</p>',
         store=lambda s: s.replace('"Find', "&quot;Find").replace('point"', "point&quot;").replace(".</p>", ". </p>"),
         expect=0),
]

# The planter's cases: written by a separate agent from a table of observed failures, without
# this code. Don't change them alone; a case that fails is reported, not edited to pass.
# Cases 3-6 are the table's. x1-x6 are the planter's extras: each tries to make the read-back
# lie, either a false pass (stored value wrong, a sloppy compare calls it a match) or a false
# alarm (ADO legitimately changes the value, a strict compare cries wolf).

_COMMIT = "https://dev.azure.com/example-org/Example-Project/_git/example-repo/commit/4f2a91c"
_FIGMA = "https://www.figma.com/design/AbC123xyz/Example?node-id=1234-56789"

PLANTED = [
    # ---- table cases 3 to 6 -------------------------------------------------------------------
    dict(
        name="3 entity dropped from Description",
        op="field",
        ref="System.Description",
        sent=(
            "<p>Steps: open /checkout &rarr; choose <b>Express</b> &rarr; the score panel stays empty.</p>"
            "<p>Same on the Q&amp;A page.</p>"
        ),
        store=lambda s: s.replace("&rarr;", ""),
        prior="<p>Score panel empty.</p>",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Description",
        why="Table case 3, as observed on the az path: the non-ASCII entity &rarr; vanishes "
            "on storage, so the visible text loses both arrows; output should name System.Description.",
    ),
    dict(
        name="4 comment edit cut at first newline",
        op="editcmt",
        ref=None,
        sent=(
            "<p>Fixed on the work branch in 4f2a91c.</p>\n"
            "<ul><li>Hero band matches node 1234-56789 at 1440 and 375.</li>\n"
            "<li>Card hover restored; the Q&amp;A link points at /faq.</li></ul>\n"
            "<p>Ready for QA &rarr; please re-test on staging.</p>"
        ),
        store=lambda s: s.split("\n", 1)[0],
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="Table case 4 on the comment-edit path: only the first line is kept, so three lines of text "
            "are gone; whitespace collapsing must not hide a loss of text.",
    ),
    dict(
        name="5 comment answered 200, nothing stored",
        op="comment",
        ref=None,
        sent=(
            "<p>QA pass done &#39;as built&#39; on staging.</p>"
            "<ul><li>Hero band: matches</li>"
            "<li>Footer: see <a href=\"" + _COMMIT + "\">commit 4f2a91c</a></li></ul>"
        ),
        store=lambda s: None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="Table case 5: the write answers 200 with an id and echoes the text, but no comment exists; "
            "if the fresh GET for that id answers 404, that is a missing comment (1), not a failed read (2).",
    ),
    dict(
        name="6 state accepted, read-back fails",
        op="state",
        ref=None,
        sent="Resolved",
        store=lambda s: s,
        prior="Active",
        read_status=503,
        expect=2,
        says="DID NOT RUN",
        why="Table case 6: the write succeeds but every later read answers 503, so nothing can be "
            "confirmed; the tool must say DID NOT RUN, not pass on the write's echo and not exit 1.",
    ),
    # ---- planter's extras ---------------------------------------------------------------------
    dict(
        name="x1 link text kept, address dropped",
        op="comment",
        ref=None,
        sent=(
            "<p>Fixed in <a href=\"" + _COMMIT + "\">commit 4f2a91c</a>. "
            "The hero now matches the <a href=\"" + _FIGMA + "\">Figma node</a>.</p>"
        ),
        store=lambda s: s.replace(' href="' + _FIGMA + '"', "", 1),
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="False pass: visible text is identical, only the second link's href is gone; the maker's "
            "call counts that as a change. ADO's rich-text sanitizer does strip hrefs it rejects; "
            "UNVERIFIED that it ever strips an https one.",
    ),
    dict(
        name="x2 AssignedTo comes back as an identity",
        op="field",
        ref="System.AssignedTo",
        sent="pat.tester@example.com",
        store=lambda s: dict(
            displayName="Pat Tester",
            uniqueName="Pat.Tester@example.com",
            id="a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
        ),
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: ADO returns AssignedTo as an object; uniqueName carries the "
            "directory's casing, not what was typed; matching uniqueName case aside is a pass.",
    ),
    dict(
        name="x3 Tags recased and reordered",
        op="field",
        ref="System.Tags",
        sent="readback; QA-Pass; trial-2026",
        store=lambda s: "qa-pass; readback; trial-2026",
        prior="readback",
        expect=0,
        says="read back",
        why="False alarm: ADO tags are case-insensitive and reuse a tag's existing project casing "
            "(here qa-pass), stored as 'a; b'; same set, case aside. Whether ADO reorders is UNVERIFIED.",
    ),
    dict(
        name="x4 cleared Description comes back absent",
        op="field",
        ref="System.Description",
        sent="",
        store=lambda s: s,  # nothing kept: ADO omits an emptied field from the GET's fields
        prior="<p>Old description, to be cleared.</p>",
        expect=0,
        says="read back",
        why="False alarm: a field cleared with \"\" is left out of ADO's work-item GET entirely; a tool "
            "that indexes fields[ref] crashes or calls it unreadable. Absent or empty is a pass.",
    ),
    dict(
        name="x5 clear ignored, old criteria kept",
        op="field",
        ref="Microsoft.VSTS.Common.AcceptanceCriteria",
        sent="",
        store=lambda s: None,
        prior="<ul><li>Hero matches node 1234-56789 at 1440 and 375.</li></ul>",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="Microsoft.VSTS.Common.AcceptanceCriteria",
        why="False pass: \"\" is a substring of anything and normalizes to nothing, so a 'sent found in "
            "stored' check passes; the prior text is still there, so the clear did not happen.",
    ),
    dict(
        name="x6 state answered 200, prior kept",
        op="state",
        ref=None,
        sent="Closed",
        store=lambda s: None,
        prior="Resolved",
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="Case 5's server on State, the most-written field; real ADO rejects a bad "
            "transition with 400, so this guards against trusting the write's echo on the state path.",
    ),
]

# ---- second batch: paths a separate reviewer found untested by PLANTED ------------------------
# The stand-in's extra keys: existing (comments already on the item, same author) and
# stored_ref (the key the server stores and returns a field under).

_MENTION = ' data-vss-mention="version:2.0,6c1f3a2b-8d4e-4f5a-9b0c-1d2e3f4a5b6c"'
_RETEST = "<p>Re-tested on staging: hero band matches node 1234-56789.</p>"

PLANTED_2 = [
    # 1. identity path, known-bad
    dict(
        name="b1 AssignedTo comes back as a different person",
        op="field",
        ref="System.AssignedTo",
        sent="Pat Tester",
        store=lambda s: dict(
            displayName="Pat Testerson",
            uniqueName="Pat.Testerson@example.com",
            id="9e8d7c6b-5a49-4382-a1b0-c9d8e7f6a5b4",
        ),
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.AssignedTo",
        why="False pass: 'pat tester' is a substring of 'pat testerson'; the sent text must equal one "
            "of displayName, uniqueName or id, not sit inside one. Stand-in known-bad, not observed ADO.",
    ),
    dict(
        name="b2 AssignedTo comes back empty",
        op="field",
        ref="System.AssignedTo",
        sent="pat.tester@example.com",
        store=lambda s: None,
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.AssignedTo",
        why="False pass: the field is absent after the write; absent is right only for a \"\" clear "
            "(x4), so a tool that skips a missing identity as 'nothing to compare' is fooled.",
    ),
    # 2. Tags, known-bad
    dict(
        name="b3 Tags come back with one dropped",
        op="field",
        ref="System.Tags",
        sent="readback; QA-Pass; trial-2026",
        store=lambda s: "qa-pass; readback",
        prior="readback",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Tags",
        why="False pass: stored is a subset of sent, so 'every stored tag was sent' passes; trial-2026 "
            "is missing. Sets must be equal, case aside.",
    ),
    dict(
        name="b4 Tags keep a tag the write replaced",
        op="field",
        ref="System.Tags",
        sent="readback; qa-pass",
        store=lambda s: "needs-design; qa-pass; readback",
        prior="needs-design; readback",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Tags",
        why="False pass the other way: 'every sent tag is stored' passes, but needs-design should be gone. "
            "Assumes the tool's tag write replaces the set, as 'match as a set' implies; if it adds, this case is wrong.",
    ),
    # 3. number field
    dict(
        name="b5 StoryPoints stored as a different number",
        op="field",
        ref="Microsoft.VSTS.Scheduling.StoryPoints",
        sent="3",
        store=lambda s: 3.5,
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="Microsoft.VSTS.Scheduling.StoryPoints",
        why="False pass: '3' is a prefix and substring of '3.5', and int(3.5) == 3; compare as numbers. "
            "Stand-in known-bad, not observed ADO.",
    ),
    dict(
        name="b6 StoryPoints 3 comes back as 3.0",
        op="field",
        ref="Microsoft.VSTS.Scheduling.StoryPoints",
        sent="3",
        store=lambda s: 3.0,
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: StoryPoints is a Double in ADO and the GET returns the JSON number 3.0; a "
            "string compare of '3' with '3.0' cries wolf.",
    ),
    # 4. comment lookup
    dict(
        name="b7 no new comment, an older one holds the same text",
        op="comment",
        ref=None,
        sent=_RETEST,
        store=lambda s: None,
        existing=["<p>QA pass started on staging.</p>", _RETEST],
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="False pass: the write answers 200 with a new id, but only the older identical comment exists; "
            "a tool that searches the item's comments for its text finds that one. Look up by the returned id.",
    ),
    # 5. lost @mention
    dict(
        name="b8 @mention attribute stripped, text and href kept",
        op="comment",
        ref=None,
        sent="<div><a href=\"#\"" + _MENTION + ">@Pat Doe</a> please re-test the hero band on staging.</div>",
        store=lambda s: s.replace(_MENTION, "", 1),
        expect=1,
        says="WRITE NOT CONFIRMED",
        why="Without data-vss-mention nobody is notified, and the ado skill checks for that attribute; the text "
            "and href survive, so the maker's text-plus-href compare (its stated blind spot) will pass this.",
    ),
    # 6. casing ADO normalises
    dict(
        name="b9 IterationPath comes back in the node's casing",
        op="field",
        ref="System.IterationPath",
        sent="example project\\sprint 6",
        store=lambda s: "Example Project\\Sprint 6",
        prior="Example Project\\Sprint 5",
        expect=0,
        says="read back",
        why="False alarm: ADO resolves an iteration path to its node, case aside, and returns the node's "
            "own casing; I believe so, UNVERIFIED on this org.",
    ),
    dict(
        name="b10 ref sent lower case, stored under System.Title",
        op="field",
        ref="system.title",
        stored_ref="System.Title",
        sent="Gallery cards wrap at the wrong width",
        store=lambda s: s,
        prior="Gallery cards wrap",
        expect=0,
        says="read back",
        why="False alarm: ADO accepts a field reference name in any case and the GET returns it under the "
            "canonical name; a tool that looks up fields[ref] as sent finds nothing.",
    ),
    # 7. whitespace between blocks, and a bare less-than sign
    dict(
        name="b11 newline between paragraphs removed",
        op="field",
        ref="System.Description",
        sent="<p>Hero band matches node 1234-56789.</p>\n<p>Footer links fixed.</p>",
        store=lambda s: s.replace("</p>\n<p>", "</p><p>"),
        prior="<p>Hero band off.</p>",
        expect=0,
        says="read back",
        why="False alarm: same two paragraphs on screen; measured, Python's html.parser yields "
            "'matches.Footer' for the stored form, so a compare with no break at block ends cries wolf.",
    ),
    dict(
        name="b12 bare less-than sign stored as sent",
        op="field",
        ref="System.Title",
        sent="Gallery cards: wrap when width<min, then 24 px gap",
        store=lambda s: s,
        prior="Gallery cards: wrap",
        expect=0,
        says="read back",
        why="Known good: Title is plain text and ADO stores it as sent; a tool must not error or flag "
            "it because '<min,' looks like the start of a tag.",
    ),
    dict(
        name="b13 bare less-than sign, title cut after width",
        op="field",
        ref="System.Title",
        sent="Gallery cards: wrap when width<min, then 24 px gap",
        store=lambda s: s.split("<", 1)[0],
        prior="Gallery cards: wrap",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Title",
        why="False pass: measured, Python's html.parser drops everything from a bare '<' on, so sent and "
            "stored both extract to 'Gallery cards: wrap when width'.",
    ),
    # 8. dates and Booleans
    dict(
        name="b14 DueDate comes back as an ISO datetime",
        op="field",
        ref="Microsoft.VSTS.Scheduling.DueDate",
        sent="2026-10-30",
        store=lambda s: "2026-10-30T00:00:00Z",
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: ADO returns DateTime fields as ISO 8601 UTC; same day. Whether ADO shifts a "
            "date-only value by the caller's time zone is UNVERIFIED.",
    ),
    dict(
        name="b15 Boolean true comes back as True",
        op="field",
        ref="Custom.ReadyForQA",
        sent="true",
        store=lambda s: True,
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: ADO returns a Boolean field as JSON true, which Python reads as True and str() "
            "gives 'True'. The field name is made up; inherited processes do allow Boolean custom fields.",
    ),
    dict(
        name="b16 Boolean false comes back as True",
        op="field",
        ref="Custom.ReadyForQA",
        sent="false",
        store=lambda s: True,
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="Custom.ReadyForQA",
        why="False pass: bool('false') is True in Python, so a truthiness compare calls it a match; "
            "the stored value is the opposite of the one sent.",
    ),
]

# ---- third batch: date and less-than paths a second reviewer found untested ------------------
# Measured on Python 3.13: datetime.fromisoformat rejects '2026-10-30T10:0' and
# '2026-10-30T99:99'; html.parser reads 'if a<b then c' as 'if a' and 'if a&lt;b then c' as
# 'if a<b then c'.

_DUE = "Microsoft.VSTS.Scheduling.DueDate"

PLANTED_3 = [
    # 1. date mismatches
    dict(
        name="c1 DueDate write dropped, old time on the same day kept",
        op="field",
        ref=_DUE,
        sent="2026-10-30",
        store=lambda s: None,
        prior="2026-10-30T15:00:00Z",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names=_DUE,
        why="False pass: same calendar day, so a date-part compare matches; a date-only value is midnight "
            "(b14), and 15:00Z on the 30th is not midnight on the 30th in any time zone from UTC-12 to UTC+14.",
    ),
    dict(
        name="c2 DueDate sent with a digit missing, stored at 10:05",
        op="field",
        ref=_DUE,
        sent="2026-10-30T10:0",
        store=lambda s: "2026-10-30T10:05:00Z",
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names=_DUE,
        why="False pass: the stored text starts with the sent text, so a prefix compare matches once the "
            "date parse fails; 10:0 can only mean 10:00. The read worked, so this is 1, not 2.",
    ),
    dict(
        name="c3 date-shaped Title stored with a bad time added",
        op="field",
        ref="System.Title",
        sent="2026-10-30",
        store=lambda s: "2026-10-30T99:99",
        prior="Release date",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Title",
        why="False pass: Title is plain text, so a tool that spots a date shape and compares date parts "
            "or prefixes is fooled; the stored text is not the text sent.",
    ),
    # 2. a stray less-than sign before a real tag name
    dict(
        name="c4 'if a<b then c' cut to 'if a'",
        op="field",
        ref="System.Description",
        sent="if a<b then c",
        store=lambda s: s.split("<", 1)[0],
        prior="<p>Condition to check.</p>",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Description",
        why="False pass: measured, html.parser reads '<b then c' as an unfinished <b> tag and drops it, "
            "so sent and stored both extract to 'if a'; ' then c' is gone from the item.",
    ),
    dict(
        name="c5 'if a<b then c' stored with the sign escaped",
        op="field",
        ref="System.Description",
        sent="if a<b then c",
        store=lambda s: s.replace("<", "&lt;"),
        prior="<p>Condition to check.</p>",
        expect=0,
        says="read back",
        why="False alarm: an HTML field shows 'if a&lt;b then c' as 'if a<b then c'; measured, html.parser "
            "decodes the stored form in full but cuts the sent form to 'if a'. Whether ADO escapes it is UNVERIFIED.",
    ),
    # 3. a tag ADO adds that changes no text
    dict(
        name="c6 table gains a tbody",
        op="field",
        ref="System.Description",
        sent="<table><tr><td>x</td></tr></table>",
        store=lambda s: "<table><tbody><tr><td>x</td></tr></tbody></table>",
        prior="<p>No table yet.</p>",
        expect=0,
        says="read back",
        why="False alarm: an HTML5 parser inserts tbody into a table, and the text 'x' is unchanged; a markup "
            "compare cries wolf. Whether ADO's sanitizer inserts it is UNVERIFIED.",
    ),
    # 4. bad partner for b9
    dict(
        name="c7 IterationPath comes back as a different sprint",
        op="field",
        ref="System.IterationPath",
        sent="example project\\sprint 6",
        store=lambda s: "Example Project\\Sprint 7",
        prior="Example Project\\Sprint 5",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.IterationPath",
        why="False pass for a compare that is loose enough to pass b9: casing aside, Sprint 7 is not "
            "Sprint 6.",
    ),
    # 5. good partner for b14 with an explicit time
    dict(
        name="c8 DueDate comes back with milliseconds",
        op="field",
        ref=_DUE,
        sent="2026-10-30T10:05:00Z",
        store=lambda s: "2026-10-30T10:05:00.000Z",
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: ADO's REST API often writes DateTimes with fractional seconds; same instant, "
            "so a string compare cries wolf.",
    ),
    # planter's own: make the date or less-than rules lie
    dict(
        name="cx1 DueDate sent with an offset, stored as the same instant in UTC",
        op="field",
        ref=_DUE,
        sent="2026-10-30T12:05:00+02:00",
        store=lambda s: "2026-10-30T10:05:00Z",
        prior=None,
        expect=0,
        says="read back",
        why="False alarm: ADO keeps DateTimes in UTC and returns them with Z; 12:05+02:00 is 10:05Z. A "
            "wall-clock or string compare cries wolf.",
    ),
    dict(
        name="cx2 DueDate offset dropped on storage",
        op="field",
        ref=_DUE,
        sent="2026-10-30T23:30:00-05:00",
        store=lambda s: "2026-10-30T23:30:00Z",
        prior=None,
        expect=1,
        says="WRITE NOT CONFIRMED",
        names=_DUE,
        why="False pass: same wall-clock time and same date part, but 23:30-05:00 is 2026-10-31T04:30Z, "
            "five hours and a day away; a compare that drops the offset is fooled.",
    ),
    dict(
        name="cx3 plain-text Title stored with the sign escaped",
        op="field",
        ref="System.Title",
        sent="Gallery cards: wrap when width<min, then 24 px gap",
        store=lambda s: s.replace("<", "&lt;"),
        prior="Gallery cards: wrap",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Title",
        why="False pass, the mirror of c5: Title is plain text, so the item now shows a literal '&lt;'; a "
            "tool that decodes entities in every field is fooled. ADO stores Title as sent (b12); this is a stand-in fault.",
    ),
]

# ---- fourth batch: HTML comment openers ------------------------------------------------------
# Measured: html.parser on 3.13 reads 'Done <!-- note then more text' as 'Done'; on 3.9 it keeps the whole string. Both read 'a <!-- x --> b' as 'a b'.

PLANTED_4 = [
    dict(
        name="d1 unclosed comment opener, stored cut to 'Done'",
        op="field",
        ref="System.Description",
        sent="Done <!-- note then more text",
        store=lambda s: "Done",
        prior="<p>In progress.</p>",
        expect=1,
        says="WRITE NOT CONFIRMED",
        names="System.Description",
        why="False pass on 3.13: its parser drops everything after an unclosed '<!--', so sent and stored "
            "both read 'Done'; 3.9 keeps the text. The words after the opener are gone from the item.",
    ),
    dict(
        name="d2 closed comment stripped on storage",
        op="field",
        ref="System.Description",
        sent="a <!-- x --> b",
        store=lambda s: "a b",
        prior="<p>In progress.</p>",
        expect=0,
        says="read back",
        why="False alarm: a closed comment is never shown, so removing it changes nothing a reader sees; "
            "a raw compare cries wolf. Whether ADO's sanitizer strips comments is UNVERIFIED.",
    ),
    dict(
        name="dx1 comment holding '>' across a line, stripped on storage",
        op="field",
        ref="System.Description",
        sent="<p>Ready for QA.</p><!-- checked: width > 1440\nand 375 --><p>Footer fixed.</p>",
        store=lambda s: "<p>Ready for QA.</p><p>Footer fixed.</p>",
        prior="<p>In progress.</p>",
        expect=0,
        says="read back",
        why="False alarm: a comment ends only at '-->', so its '>' and newline are hidden too; measured, a "
            "'<[^>]*>' strip leaves ' 1440 and 375 -->' as text, while both parsers read the two values the same.",
    ),
]

# ---- fifth batch: `batch`, one approval for a reviewed list ----------------------------------
PLANTED_5 = [
    dict(
        name="b1 batch applies a state change and keeps the prior value for undo",
        op="batch", ref="System.State", prior="Active", store=lambda s: s, expect=0,
        batch=[{"id": 4242, "expect": {"System.State": "Active"}, "set": {"System.State": "Resolved"}}],
        says="1 of 1 applied", names='"System.State": "Active"',
        why="Known good: the item still holds what the list expected, so the write goes and the undo "
            "file can put Active back.",
    ),
    dict(
        name="b2 batch skips an item someone changed after the list was made",
        op="batch", ref="System.State", prior="Active", store=lambda s: s, expect=1, write_status=500,
        batch=[{"id": 4242, "expect": {"System.State": "New"}, "set": {"System.State": "Resolved"}}],
        says="SKIPPED", names="0 of 1 applied",
        why="False pass: writing over a teammate's later change. The stand-in refuses any write, so a "
            "batch that wrote anyway prints STOPPED, not SKIPPED.",
    ),
    dict(
        name="b3 batch stops at a write ADO did not keep",
        op="batch", ref="System.State", prior="Active", store=lambda s: None, expect=1,
        batch=[{"id": 4242, "expect": {"System.State": "Active"}, "set": {"System.State": "Closed"}},
               {"id": 4242, "expect": {"System.State": "Active"}, "set": {"System.State": "New"}}],
        says="STOPPED", names='"status": "failed"', not_says=["item 2 of 2"],
        why="False pass: going on after a write that didn't land, so later items act on a state that "
            "isn't there. The undo file has to show the failed item as failed.",
    ),
    dict(
        name="b4 batch reads the parent it expects (ADO omits it from a plain GET)",
        op="batch", ref="System.State", prior="Active", store=lambda s: s, expect=0,
        extra_fields={"System.Parent": 9198},
        batch=[{"id": 4242, "expect": {"System.Parent": "9198"}, "set": {"System.State": "Resolved"}}],
        says="1 of 1 applied",
        why="False alarm, measured: a plain GET has no System.Parent, so a batch "
            "that reads it that way skips every item whose parent it checks.",
    ),
    dict(
        name="b5 batch refuses to overwrite an earlier run's undo file",
        op="batch", ref="System.State", prior="Active", store=lambda s: s, expect=1, undo_exists=True,
        batch=[{"id": 4242, "expect": {"System.State": "Active"}, "set": {"System.State": "Resolved"}}],
        says="REFUSED", names='"System.State": "New"',
        why="Lost record: a second run of the same file replaced the first run's undo file, and with it "
            "the only list of what to put back.",
    ),
]


# ---- linking: a bare id goes out as a link (ado_links.py) -------------------------------------
# Each store refuses what an unlinked write would send, so a copy without the linking misses them.
_ITEM = "/_workitems/edit/"
_LINK_CASES = [
    dict(name="l1 a comment's bare #3482 and 'Story 4513' go out linked", op="comment",
         sent="<p>Closed. QA stays on #3482, and Story 4513 carries the copy.</p>", exists={3482, 4513},
         store=lambda s: s if f"{_ITEM}3482/" in s and f"{_ITEM}4513/" in s else "sent unlinked",
         expect=0, names="linked 2 bare id(s): #3482, #4513"),
    dict(name="l2 a Description links the item it holds and leaves one the project doesn't", op="field",
         ref="System.Description", sent="<div>Reverses #3482; #9999 was deleted.</div>", exists={3482},
         store=lambda s: s if f"{_ITEM}3482/" in s and f"{_ITEM}9999/" not in s else "sent wrong",
         expect=0, names="not an item of this project: 9999"),
    dict(name="l3 an edit turns a markdown link copied from a doc into an anchor", op="editcmt",
         sent="<p>Under [#3482](https://dev.azure.com/o/p/_workitems/edit/3482/) now.</p>", exists={3482},
         store=lambda s: s if '<a href="https://dev.azure.com/o/p/_workitems/edit/3482/">#3482</a>' in s
         and "](" not in s else "sent as markdown", expect=0),
    dict(name="l4 a plain-text Title is sent as written", op="field", ref="System.Title",
         sent="Fix #3482 card gap", exists={3482}, prior="Fix",
         store=lambda s: s if "<a" not in s else "an anchor in a plain field", expect=0),
    dict(name="l5 a batch's comment edit goes out linked", op="batch", ref="System.State", prior="Active",
         exists={3482}, store=lambda s: s if f"{_ITEM}3482/" in s else "sent unlinked", expect=0,
         batch=[{"id": 4242, "comment": {"id": 8001, "text": "<p>QA on #3482.</p>", "expect": _ORIGINAL}}],
         says="1 of 1 applied", names="linked 1 bare id(s): #3482"),
    dict(name="l6 a batch's undo puts back the bare value as it was, and finds the linked one it expects",
         op="batch", ref="System.Description", prior="<p>Prior, on #3482.</p>", exists={3482}, then_undo=True,
         store=lambda s: "relinked" if s.startswith("<p>Prior") and _ITEM in s else s, expect=0,
         batch=[{"id": 4242, "expect": {"System.Description": "<p>Prior, on #3482.</p>"},
                 "set": {"System.Description": "<p>Now, on #3482.</p>"}}],
         says="-- undo run --", names="1 of 1 applied, 0 skipped. Undo: python ado_write.py batch",
         not_says=["SKIPPED", "WRITE NOT CONFIRMED"]),
    dict(name="l7 a batch skips a comment someone changed after the list was made", op="batch",
         ref="System.State", prior="Active", exists={3482}, store=lambda s: s, expect=1, write_status=500,
         batch=[{"id": 4242, "comment": {"id": 8001, "text": "<p>QA on #3482.</p>", "expect": "<p>What I wrote</p>"}}],
         says="SKIPPED", names="0 of 1 applied"),
]


# ---- whose text a write drops -----------------------------------------------------------------
# Each case plants the field's history: who wrote each value of it, oldest first ("me" is the PAT).
_THEIRS = "<div>Their line</div><div>Their second line</div>"
_D = "System.Description"
_LINE_CASES = [
    dict(name="w1 a batch that drops a teammate's lines is refused whole, before anything is sent", op="batch",
         ref=_D, history=[("someone-else", _THEIRS)], store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {_D: "<div>Ours</div>"}}],
         says="REFUSED #4242 System.Description: drops 2 line(s) Teammate, A. first wrote",
         names="merged, their lines on top: <div>Their line</div><div>Their second line</div><div><br> </div><div>Ours</div>",
         not_says=["undo holds", "applied", "has no override"]),
    dict(name="w2 keeping their lines on top passes", op="batch", ref=_D, history=[("someone-else", _THEIRS)],
         store=lambda s: s, expect=0, batch=[{"id": 4242, "set": {_D: _THEIRS + "<div>Ours</div>"}}],
         says="1 of 1 applied", not_says=["REFUSED"]),
    dict(name="w3 replacing our own line passes", op="batch", ref=_D, history=[("me", "<div>Old ours</div>")],
         store=lambda s: s, expect=0, batch=[{"id": 4242, "set": {_D: "<div>New ours</div>"}}], says="1 of 1 applied"),
    dict(name="w4 their line counts as theirs after we put it back in our revision (first author, not latest)",
         op="batch", ref=_D, history=[("someone-else", "<div>Their line</div>"),
                                      ("me", "<div><b>Their&nbsp;line</b></div><div>Ours</div>")],
         store=lambda s: s, expect=1, batch=[{"id": 4242, "set": {_D: "<div>Ours, reworded</div>"}}],
         says="drops 1 line(s) Teammate, A. first wrote", not_says=["undo holds"]),
    dict(name="w5 an undo of our own latest write passes, though it drops their line", op="batch", ref=_D,
         history=[("someone-else", "<div>Their line</div>"), ("me", "<div>Ours</div>"),
                  ("me", "<div>Their line</div><div>Ours</div>")],
         store=lambda s: s, expect=0, batch=[{"id": 4242, "set": {_D: "<div>Ours</div>"}}], says="1 of 1 applied",
         not_says=["REFUSED"]),
    dict(name="w6 the same history, a value that isn't the undo, is refused", op="batch", ref=_D,
         history=[("someone-else", "<div>Their line</div>"), ("me", "<div>Ours</div>"),
                  ("me", "<div>Their line</div><div>Ours</div>")],
         store=lambda s: s, expect=1, batch=[{"id": 4242, "set": {_D: "<div>Ours, reworded</div>"}}], says="REFUSED"),
    dict(name="w7 --replaces on the command line lets the named item through, and says so", op="batch", ref=_D,
         history=[("someone-else", _THEIRS)], store=lambda s: s, expect=0,
         replaces=({"4242", "777"}, "the owner agreed to the rewrite"),
         batch=[{"id": 4242, "set": {_D: "<div>Ours</div>"}}],
         says="--replaces lifts it on #4242 System.Description, which drops 2 line(s) Teammate, A. first wrote: "
              "the owner agreed to the rewrite", names="--replaces names #777, but nothing sent to it drops"),
    dict(name="w8 a history that can't be read refuses (a check that can't tell doesn't pass)", op="batch", ref=_D,
         prior="<div>Their line</div>", updates_status=404, store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {_D: "<div>Ours</div>"}}], says="its revision history can't be read",
         names="has no override: check it by hand", not_says=["undo holds", "--replaces 4242"]),
    dict(name="w9 a teammate's Title is a line too", op="batch", ref="System.Title",
         history=[("someone-else", "Their title")], store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {"System.Title": "Our title"}}],
         says="REFUSED #4242 System.Title: drops 1 line(s)", names="merged, their lines on top: Their title"),
    dict(name="w10 the history is read past its first page of 200", op="batch", ref=_D, fillers=250,
         history=[("me", "<div>Ours</div>")], store=lambda s: s, expect=0,
         batch=[{"id": 4242, "set": {_D: "<div>Ours, reworded</div>"}}], says="1 of 1 applied",
         not_says=["REFUSED"]),
    dict(name="w11 `field` runs the same check and sends nothing", op="cli",
         argv=["field", "4242", _D, "<div>Ours</div>"], ref=_D, history=[("someone-else", _THEIRS)],
         store=lambda s: s, expect=1, says="REFUSED: this would drop text someone else wrote on #4242",
         names="stand-in writes: none"),
    dict(name="w12 `field` keeping their lines passes and pins its PATCH", op="cli",
         argv=["field", "4242", _D, _THEIRS + "<div>Ours</div>"], ref=_D, history=[("someone-else", _THEIRS)],
         store=lambda s: s, expect=0, says="read back", names="stand-in writes: PATCH fields"),
    dict(name="w13 --replaces with no reason is refused before anything is read", op="cli",
         argv=["field", "4242", _D, "<div>Ours</div>", "--replaces", " "], ref=_D, history=[("someone-else", _THEIRS)],
         store=lambda s: s, expect=1, says="--replaces requires a reason", names="stand-in writes: none"),
    dict(name="w14 a later entry for the same item is checked against what the earlier one leaves", op="batch",
         ref=_D, history=[("someone-else", "<div>Their line</div>")], store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {_D: "<div>Their line</div><div>Ours</div>"}},
                {"id": 4242, "set": {_D: "<div>Ours only</div>"}}],
         says="drops 1 line(s) Teammate, A. first wrote", not_says=["undo holds"]),
    dict(name="w15 two entries for one item: the second PATCH is pinned to the rev the first left", op="batch",
         ref=_D, history=[("me", "<div>Ours</div>")], store=lambda s: s, expect=0,
         batch=[{"id": 4242, "set": {_D: "<div>Ours</div><div>More</div>"}},
                {"id": 4242, "set": {_D: "<div>Ours</div><div>More</div><div>Again</div>"}}],
         says="2 of 2 applied", not_says=["STOPPED", "SKIPPED"]),
    dict(name="w16 an item saved by someone else between the check and the write is skipped", op="batch", ref=_D,
         history=[("me", "<div>Ours</div>")], rev_moves_after_gets=1, store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {_D: "<div>Ours, reworded</div>"}}],
         says="SKIPPED #4242: it changed after the text check read it", not_says=["undo holds"]),
    dict(name="w17 a PATCH carries test /rev: an item saved between the read and the write stops the run", op="batch",
         ref="System.State", prior="Active", rev_moves_after_gets=1, store=lambda s: s, expect=1,
         batch=[{"id": 4242, "set": {"System.State": "Resolved"}}], says="STOPPED", names="412"),
    dict(name="w18 a new entry's comment edit with no comment.expect is refused, nothing sent", op="batch",
         ref="System.State", prior="Active", store=lambda s: "written", expect=1,
         batch=[{"id": 4242, "comment": {"id": 8001, "text": "<p>Edited.</p>"}}],
         says="REFUSED: item 1", names="no comment.expect", not_says=["applied"]),
    dict(name="w19 an undo entry's comment edit needs no expect (undo files written before the rule have none)", op="batch",
         ref="System.State", prior="Active", store=lambda s: s, expect=0,
         batch=[{"id": 4242, "raw": True, "status": "applied", "comment": {"id": 8001, "text": "<p>Back.</p>"}}],
         says="1 of 1 applied"),
    dict(name="w20 an old undo entry's History '' is left out and its State revert still runs", op="batch",
         ref="System.State", prior="Active", store=lambda s: s, expect=0,
         batch=[{"id": 4242, "raw": True, "status": "applied",
                 "expect": {"System.History": "<p>A note.</p>", "System.State": "Active"},
                 "set": {"System.History": "", "System.State": "New"}}],
         says="1 of 1 applied", names='left out System.History ""', not_says=["SKIPPED"]),
    dict(name="w21 a History comment is sent, and its undo holds no History and puts nothing back", op="batch",
         ref="System.State", prior="Active", store=lambda s: s, expect=0, then_undo=True,
         batch=[{"id": 4242, "set": {"System.History": "<p>A note.</p>"}}],
         says="nothing to send: an undo can't take back a discussion comment", not_says=['"System.History"']),
]

# ---- delete, restore and earlier promises -------------------------------------------------------
# Each run plants a session log (case "log"; None plants none) and names it in CLAUDE_CODE_SESSION_ID, so
# _promised reads it and never your own logs. A delete or restore case prints the stand-in's writes
# and the undo folder's files after the run, so "sent nothing" and "undo on disk" are checked words.
_SID = "5e1f7e57-0000-4000-8000-000000000000"


def _said(hm, text, **kw):
    return {"type": "assistant", "timestamp": f"2026-11-04T{hm}:00.000Z", "sessionId": _SID, "isSidechain": False,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, **kw}


# Planted ids only: work-item numbers no real tracker is meant to hold.
_PROMISE_LOG = [
    _said("18:13", "- **Hold #5389.** Its description is the original goal statement.\n"
                   "I'll copy that text onto #5195, then delete #5389."),
    _said("18:14", "#5497, #5498, #5525, #5526: template updates that turned out not to be needed."),
    _said("18:20", "I'll delete #5389 once the copy is checked.", isSidechain=True),
    _said("18:21", "I'll restore #5389 tomorrow.", sessionId="0e1f7e57-0000-4000-8000-000000000000"),
    dict(_said("18:22", "I'll copy #5389's text again later."), type="api-request-blob", timestamp=None),
    _said("18:42", "No other deleted item held anything worth moving. #5497 and #5498 described template "
                   "updates that weren't needed."),
    _said("18:50", "Deleted #5389 after copying its text."),
]
_REMOVED = {"System.State": "Removed", "System.Title": "An item nobody needs"}
_DELETE_CASES = [
    dict(name="d1 a Removed item at its reviewed rev goes to the recycle bin, the undo file on disk first",
         op="delete", extra_fields=_REMOVED, rev=1, expect=0,
         says="the item answers 404 and the recycle bin holds it", names="DELETE; undo files: ['4242-rev1.undo.json']"),
    dict(name="d2 refuses an item not in Removed and sends nothing", op="delete", rev=1, expect=1,
         says="REFUSED", names="stand-in writes: none"),
    dict(name="d3 refuses an item whose rev moved since the review and sends nothing", op="delete",
         extra_fields=_REMOVED, start_rev=3, rev=2, expect=1, says="REFUSED", names="stand-in writes: none"),
    dict(name="d4 replaces the undo file a run whose delete never landed left, and deletes", op="delete",
         extra_fields=_REMOVED, rev=1, undo_there=True, expect=0, says="replacing",
         names="the item answers 404 and the recycle bin holds it"),
    dict(name="d13 refuses an item with a child still in New, and sends nothing", op="delete", extra_fields=_REMOVED,
         rev=1, children={5101: "Removed", 5102: "New"}, expect=1, says="REFUSED: #4242 has 1 child item(s) not in "
         "Removed: #5102 (New)", names="stand-in writes: none"),
    dict(name="d14 an item whose children are all Removed goes to the recycle bin, its paths in the undo file",
         op="delete", extra_fields=dict(_REMOVED, **{"System.AreaPath": "proj\\Site", "System.IterationPath": "proj\\S9"}),
         rev=1, children={5101: "Removed"}, expect=0, says="the recycle bin holds it",
         names='"area": "proj\\\\Site", "iteration": "proj\\\\S9"'),
    dict(name="d5 ADO answers the DELETE but keeps the item", op="delete", extra_fields=_REMOVED, rev=1,
         on_delete="keep", expect=1, names="still answers 200"),
    dict(name="d6 the item is gone and not in the recycle bin, as a destroy leaves it", op="delete",
         extra_fields=_REMOVED, rev=1, on_delete="destroy", expect=1, names="restore can't bring it back"),
    dict(name="d7 the read-back fails after the DELETE", op="delete", extra_fields=_REMOVED, rev=1,
         read_status=500, expect=2),
    dict(name="d8 a server that answers 400 to api-version 7.1 is read at the preview version", op="delete",
         extra_fields=_REMOVED, rev=1, bin_old=True, expect=0, says="the recycle bin holds it"),
    dict(name="d12 refuses a Removed Test Case, whose API delete skips the recycle bin, and sends nothing",
         op="delete", extra_fields=dict(_REMOVED, **{"System.WorkItemType": "Test Case"}), rev=1, expect=1,
         says="REFUSED: #4242 is a Test Case", names="stand-in writes: none"),
    dict(name="d10 a batch entry asking for a delete is refused, and nothing is sent", op="batch", ref="System.State",
         prior="Active", store=lambda s: "written", batch=[{"id": 4242, "delete": True}], expect=1,
         says="REFUSED: item 1", names="has delete, which batch doesn't send", not_says=["applied"]),
    dict(name="d15 a batch entry with nothing to send is refused, not counted as applied", op="batch",
         ref="System.State", prior="Active", store=lambda s: "written", batch=[{"id": 4242}], expect=1,
         says="REFUSED: item 1", names="nothing to send", not_says=["applied"]),
    dict(name="d11 state Removed prints the next step: delete, or the backlog iteration for an item that isn't dead",
         op="state", sent="Removed", prior="Active", store=lambda s: s, expect=0,
         names="Removed is the step before delete (python ado_write.py delete 4242:2)"),
    dict(name="r1 restore brings a deleted item back", op="restore", extra_fields=_REMOVED, start_deleted=True,
         expect=0, says="restored, read back", names="PATCH recyclebin"),
    dict(name="r2 restore refuses an item the recycle bin doesn't hold and sends nothing", op="restore",
         expect=1, says="REFUSED", names="stand-in writes: none"),
    dict(name="r3 ADO answers the restore but the item stays in the bin", op="restore", extra_fields=_REMOVED,
         start_deleted=True, on_restore="stay", expect=1),
    dict(name="p1 #5389's delete prints the 18:13Z promise to copy first; a subagent's, another session's, a "
         "repeated copy's and a past-tense line are left out", op="promised", ids=[5389], log=_PROMISE_LOG, expect=0,
         says="#5389, said earlier at 18:13Z: I'll copy that text onto #5195, then delete #5389.",
         names="#5389, said earlier at 18:13Z: Hold #5389.",
         not_says=["once the copy is checked", "tomorrow", "again later", "after copying"]),
    dict(name="p2 #5497 prints nothing: its lines name it but put nothing off ('held anything' is past)",
         op="promised", ids=[5497], log=_PROMISE_LOG, expect=0, says="promised: done", not_says=["5497"]),
    dict(name="p3 no log for the session says did not run", op="promised", ids=[5389], log=None, expect=0,
         says="earlier promises about #5389: did not run (no log for session 5e1f7e57)"),
    dict(name="p4 a delete typed as a command prints the earlier promise before it deletes", op="cli",
         argv=["delete", "4242:1", "--undo", "{undo}"], extra_fields=_REMOVED, expect=0,
         log=[_said("17:00", "I'll copy #4242's text onto #5195 first, then delete it.")],
         says="#4242, said earlier at 17:00Z: I'll copy #4242's text onto #5195 first, then delete it.",
         names="the recycle bin holds it"),
    dict(name="m1 several pairs on one command line: a refused pair doesn't stop the next, and the count says so",
         op="cli", argv=["delete", "4242:9", "4242:1", "--undo", "{undo}"], extra_fields=_REMOVED, expect=1,
         says="REFUSED: #4242 is Removed at rev 1", names="delete: 1 of 2 deleted and in the recycle bin; not deleted: #4242"),
    dict(name="m2 a delete without id:rev pairs is refused, and nothing is sent", op="cli",
         argv=["delete", "4242", "1"], extra_fields=_REMOVED, expect=1, says="delete takes <id>:<rev> pairs",
         names="stand-in writes: none"),
    dict(name="p5 a state write prints the promise about its item and not one about another", op="cli",
         argv=["state", "4242", "Resolved"], prior="Active", store=lambda s: s, expect=0,
         log=[_said("09:00", "I'll resolve #4242 after the push lands."), _said("09:01", "I'll close #4243 next pass.")],
         says="#4242, said earlier at 09:00Z: I'll resolve #4242 after the push lands.", names="read back",
         not_says=["#4243"]),
    dict(name="p6 a reparent prints the promise about the new parent too", op="cli", argv=["reparent", "4242", "5195"],
         log=_PROMISE_LOG, expect=1, says="#5195, said earlier at 18:13Z: I'll copy that text onto #5195", names="REFUSED"),
    dict(name="p7 a batch prints the promise about each item before its write", op="batch", ref="System.State",
         prior="Active", store=lambda s: s, batch=[{"id": 4242, "set": {"System.State": "Resolved"}}],
         log=[_said("09:00", "Holding #4242 until the push lands.")], expect=0,
         says="#4242, said earlier at 09:00Z: Holding #4242 until the push lands.", names="1 of 1 applied"),
]


def _standin(case):
    import http.server
    ref = "System.State" if case["op"] == "state" else case.get("ref")
    st = {"fields": {"System.State": "Active", **case.get("extra_fields", {})},
          "comments": [], "written": False, "next": 9000, "rev": case.get("start_rev", 1),
          "deleted": bool(case.get("start_deleted")), "binned": bool(case.get("start_deleted")), "writes": []}
    prior = case.get("prior", "PRIOR VALUE")
    if ref:
        ref = case.get("stored_ref") or ref
        st["fields"].pop(ref, None)
        if prior is not None:
            st["fields"][ref] = prior
    for k, text in enumerate(case.get("existing") or []):
        st["comments"].append({"id": 7001 + k, "text": text, "createdBy": {"id": "me"},
                               "isDeleted": False, "createdDate": "2026-10-0%dT00:00:00Z" % (k % 9 + 1)})
    if case["op"] == "editcmt" or any((b.get("comment") or {}).get("id") == 8001 for b in case.get("batch") or []):
        st["comments"].append({"id": 8001, "text": _ORIGINAL, "createdBy": {"id": "someone-else"},
                               "isDeleted": False, "createdDate": "2026-10-10T00:00:00Z"})
    # The item's revision history (workItems/{id}/updates). A case's "history" is the successive values
    # of its ref, each with its author ("me" is the PAT's identity), after "fillers" updates that change
    # only System.Tags; with none, one revision by "me" created every field as it stands.
    names = {"me": "selftest", "someone-else": "Teammate, A."}
    if case.get("history"):
        hist_ref = case.get("ref")
        ups = [{"id": k + 1, "rev": 1, "revisedBy": {"id": "someone-else", "displayName": names["someone-else"]},
                "fields": {"System.Tags": {"newValue": f"t{k}"}}} for k in range(case.get("fillers", 0))]
        old = None
        for k, (who, val) in enumerate(case["history"], 1):
            ups.append({"id": len(ups) + 1, "rev": k, "revisedBy": {"id": who, "displayName": names.get(who, who)},
                        "fields": {hist_ref: {"oldValue": old, "newValue": val}}})
            old = val
        st["fields"][hist_ref], st["rev"] = old, len(case["history"])
    else:
        ups = [{"id": 1, "rev": 1, "revisedBy": {"id": "me", "displayName": "selftest"},
                "fields": {k: {"newValue": v} for k, v in st["fields"].items()}}]
    st["updates"], st["item_gets"] = ups, 0

    class Standin(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if st["written"] and case.get("read_status", 200) != 200:
                return self._send(case["read_status"], {"message": "stand-in: read refused"})
            path = urllib.parse.urlparse(self.path).path
            if "/recyclebin/" in path:  # bin_old: a server that knows only the preview api-version
                if case.get("bin_old") and "-preview" not in self.path:
                    return self._send(400, {"message": "stand-in: no such api-version"})
                return self._send(200, {"id": 4242}) if st["binned"] else self._send(404, {"message": "not in the bin"})
            if st["deleted"] and "/_apis/wit/workitems/" in path:
                return self._send(404, {"message": "stand-in: no such item"})
            if path.endswith("/_apis/wit/workitems"):  # which ids exist (ado_links.py), and children's states
                asked = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("ids", [""])[0]
                kids = case.get("children", {})
                return self._send(200, {"value": [
                    {"id": int(i), "fields": {"System.TeamProject": "proj", "System.State": kids.get(int(i), "Active")}}
                    if int(i) in case.get("exists", ()) or int(i) in kids else None for i in asked.split(",") if i]})
            if path.endswith("/connectionData"):
                return self._send(200, {"authenticatedUser": {"id": "me", "providerDisplayName": "selftest"}})
            if path.endswith("/updates"):
                if case.get("updates_status"):
                    return self._send(case["updates_status"], {"message": "stand-in: no history"})
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                skip, top = int(q.get("$skip", ["0"])[0]), int(q.get("$top", ["200"])[0])
                page = st["updates"][skip:skip + min(top, 200)]
                return self._send(200, {"count": len(page), "value": page})
            if path.endswith("/comments"):
                return self._send(200, {"comments": st["comments"]})
            if "/comments/" in path:
                cid = path.rsplit("/", 1)[1]
                return self._send(200, next((c for c in st["comments"] if str(c["id"]) == cid), {}))
            fields = dict(st["fields"])
            if "expand=relations" not in self.path:  # ADO leaves System.Parent out of a plain GET
                fields.pop("System.Parent", None)
            item = {"id": 4242, "rev": st["rev"], "fields": fields}
            st["item_gets"] += 1
            if st["item_gets"] == case.get("rev_moves_after_gets"):  # someone else saves the item after this read
                st["rev"] += 1
            if "expand=relations" in self.path and case.get("children"):
                item["relations"] = [{"rel": "System.LinkTypes.Hierarchy-Forward",
                                      "url": f"http://stand-in/_apis/wit/workItems/{k}"} for k in case["children"]]
            return self._send(200, item)

        def _write(self):
            if case.get("write_status", 200) != 200:
                return self._send(case["write_status"], {"message": "stand-in: write refused"})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
            path = urllib.parse.urlparse(self.path).path
            st["written"] = True
            if "/recyclebin/" in path:  # a restore; on_restore="stay" answers it and keeps the item in the bin
                st["writes"].append(f"{self.command} recyclebin")
                if case.get("bin_old") and "-preview" not in self.path:
                    return self._send(400, {"message": "stand-in: no such api-version"})
                if body == {"IsDeleted": False} and case.get("on_restore") != "stay":
                    st["deleted"] = st["binned"] = False
                    st["rev"] += 1
                return self._send(200, {"id": 4242})
            if path.endswith("/comments"):
                st["next"] += 1
                kept = case["store"](body["text"])
                if kept is not None:
                    st["comments"].append({"id": st["next"], "text": kept, "createdBy": {"id": "me"},
                                           "isDeleted": False, "createdDate": "2026-10-22T00:00:00Z"})
                return self._send(200, {"id": st["next"], "text": body["text"]})
            if "/comments/" in path:
                cid, kept = path.rsplit("/", 1)[1], case["store"](body["text"])
                for c in st["comments"]:
                    if str(c["id"]) == cid and kept is not None:
                        c["text"] = kept
                return self._send(200, {"id": int(cid), "text": body["text"]})
            echo = dict(st["fields"])
            st["writes"].append("PATCH fields")
            for op in body:
                if op.get("op") == "test" and op.get("path") == "/rev" and op.get("value") != st["rev"]:
                    return self._send(412, {"message": f"stand-in: rev is {st['rev']}, the patch tested {op.get('value')}"})
            changed = {}
            for op in body:
                if op.get("op") not in ("add", "remove"):
                    continue
                name = case.get("stored_ref") or op["path"].split("/fields/", 1)[1]
                sent = op.get("value", "") if op["op"] == "add" else ""
                echo[name], kept = sent, case["store"](sent)
                if kept is None:
                    continue
                changed[name] = {"oldValue": st["fields"].get(name), "newValue": None if kept == "" else kept}
                if kept == "":
                    st["fields"].pop(name, None)
                else:
                    st["fields"][name] = kept
            st["rev"] += 1
            st["updates"].append({"id": len(st["updates"]) + 1, "rev": st["rev"],
                                  "revisedBy": {"id": "me", "displayName": "selftest"}, "fields": changed})
            return self._send(200, {"id": 4242, "rev": st["rev"], "fields": echo})

        do_POST = do_PATCH = _write

        def do_DELETE(self):
            # on_delete: "bin" (the default) as ADO does; "keep" answers and keeps the item; "destroy" drops it
            # from the bin too, as destroy=true would. A DELETE with no undo file on disk yet is refused.
            st["writes"].append("DELETE")
            if case.get("write_status", 200) != 200:
                return self._send(case["write_status"], {"message": "stand-in: write refused"})
            if not any(n.endswith(".undo.json") for n in os.listdir(case["undo_dir"])):
                return self._send(500, {"message": "stand-in: no undo file on disk before the DELETE"})
            st["written"] = True
            how = "destroy" if "destroy=true" in self.path.lower() else case.get("on_delete", "bin")
            st["deleted"], st["binned"] = how != "keep", how == "bin"
            return self._send(200, {"id": 4242, "code": 200})

    Standin.st = st
    return Standin


def _run_case(mod, case):
    """Run one write of `mod` against a fresh stand-in. Returns (exit code, printed output)."""
    import contextlib, http.server, io, tempfile, threading
    case = dict(case, undo_dir=tempfile.mkdtemp())
    logs = tempfile.mkdtemp()
    if case.get("log", []) is not None:
        os.makedirs(os.path.join(logs, "proj"))
        with open(os.path.join(logs, "proj", f"{_SID}.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in case.get("log", []))
    handler = _standin(case)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    keys = ("ADO_PAT", "NO_PROXY", "no_proxy", "CLAUDE_CODE_SESSION_ID")
    saved = (mod.ORG, mod.PROJECT, {k: os.environ.get(k) for k in keys}, getattr(mod, "_LOGS", None))
    mod.ORG, mod.PROJECT, mod._LOGS = f"http://127.0.0.1:{srv.server_address[1]}/org", "proj", logs
    os.environ["ADO_PAT"] = "selftest-not-a-token"  # the stand-in ignores it; the real one is restored
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"  # never through a proxy
    os.environ["CLAUDE_CODE_SESSION_ID"] = _SID
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                if case["op"] == "comment":
                    mod.add_comment("4242", case["sent"], "selftest")
                elif case["op"] == "editcmt":
                    mod.edit_comment("4242", "8001", case["sent"])
                elif case["op"] == "batch":
                    import tempfile
                    path = os.path.join(tempfile.mkdtemp(), "b.json")
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(case["batch"], fh)
                    if case.get("undo_exists"):
                        with open(path[:-5] + ".undo.json", "w", encoding="utf-8") as fh:
                            fh.write('[{"id": 4242, "set": {"System.State": "New"}, "status": "applied"}]')
                    rc = mod.batch(path, case["replaces"]) if case.get("replaces") else mod.batch(path)
                    undo_file = path[:-5] + ".undo.json"
                    if case.get("then_undo") and os.path.exists(undo_file):
                        print("-- undo run --")
                        rc = rc or mod.batch(undo_file)
                    if os.path.exists(undo_file):
                        print("undo holds: " + open(undo_file, encoding="utf-8").read().replace("\n", " "))
                    raise SystemExit(rc)
                elif case["op"] == "delete":
                    if case.get("undo_there"):
                        open(os.path.join(case["undo_dir"], "4242-rev1.undo.json"), "w").close()
                    mod.delete("4242", case.get("rev", 1), case["undo_dir"])
                elif case["op"] == "restore":
                    mod.restore("4242")
                elif case["op"] == "promised":
                    mod._promised(*case["ids"])
                    print("promised: done")
                elif case["op"] == "cli":
                    mod.run(["ado_write.py"] + [a.replace("{undo}", case["undo_dir"]) for a in case["argv"]])
                else:
                    ref = "System.State" if case["op"] == "state" else case["ref"]
                    mod.patch_fields("4242", [(ref, case["sent"])])
                code = 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                if isinstance(e.code, str):
                    print(e.code)
            except Exception as e:  # what python itself would exit 1 on
                print(f"{type(e).__name__}: {e}")
                code = 1
            if case["op"] in ("delete", "restore", "cli"):
                print(f"stand-in writes: {'; '.join(handler.st['writes']) or 'none'}; "
                      f"undo files: {sorted(os.listdir(case['undo_dir']))}")
                for name in sorted(os.listdir(case["undo_dir"])):
                    text = open(os.path.join(case["undo_dir"], name), encoding="utf-8").read()
                    print(f"  {name}: {json.dumps(json.loads(text)) if text.strip() else '(empty)'}")
    finally:
        srv.shutdown()
        srv.server_close()
        mod.ORG, mod.PROJECT, mod._LOGS = saved[0], saved[1], saved[3]
        import shutil
        for d in (case["undo_dir"], logs):
            shutil.rmtree(d, ignore_errors=True)
        for k, v in saved[2].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return code, out.getvalue()


def _selftest(against=None):
    import bare_ids  # every case's output must link each item id it prints, on the line that prints it
    mod = sys.modules[__name__]
    if against:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ado_write_against", against)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print(f"selftest against {against}")
    planted_all = [c for n in ("PLANTED", "PLANTED_2", "PLANTED_3", "PLANTED_4", "PLANTED_5")
                   for c in globals().get(n, [])]
    cases = [("maker", c) for c in _MAKER_CASES + _LINK_CASES + _DELETE_CASES + _LINE_CASES] + [("planted", c) for c in planted_all]
    wrong, codes = [], {}
    for i, (by, c) in enumerate(cases, 1):
        code, out = _run_case(mod, c)
        codes[i] = code
        words = [c.get("says") or _SAYS[c["expect"]]] + ([c["names"]] if c.get("names") else [])
        unsaid = [w for w in words if w not in out] + [f"(said) {w}" for w in c.get("not_says", []) if w in out]
        unsaid += [f"(no link on line {n}) {i}" for n, i in bare_ids.unlinked(out)]
        ok = code == c["expect"] and not unsaid
        last = (out.strip().splitlines() or ["(nothing printed)"])[-1][:160]
        print(f"  {'ok  ' if ok else 'MISS'} {i:2} {by:7} {c['op']:7} expect {c['expect']} got {code}  {c['name']}")
        if not ok:
            wrong.append(i)
            print(f"          last line: {last}" + (f"\n          not printed: {unsaid}" if unsaid else ""))
    import contextlib, io
    kept_in = mod._in_project
    try:
        mod._in_project = lambda ids: None
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = mod._linked('<p>On #3482, see [notes](https://x.example/a).</p>')
    finally:
        mod._in_project = kept_in
    ok = got == '<p>On #3482, see <a href="https://x.example/a">notes</a>.</p>' and "ids left bare" in buf.getvalue()
    print(f"  {'ok  ' if ok else 'MISS'} unread: with no read of which numbers are items, each id stays bare and a "
          f"markdown link still becomes an anchor")
    if not ok:
        wrong.append("unread")
        print(f"          got: {got!r}; printed: {buf.getvalue().strip()!r}")
    planted = sum(1 for by, _ in cases if by == "planted")
    print(f"selftest: {len(cases) - len(wrong)} of {len(cases)} cases gave the expected exit and words "
          f"({len(_MAKER_CASES) + len(_LINK_CASES) + len(_DELETE_CASES) + len(_LINE_CASES)} maker, {planted} planted)"
          + (f"; missed {wrong}" if wrong else ""))
    if against:  # a copy with no read-back also misses every good case on its words, so count the bad
        bad = [i for i, (_, c) in enumerate(cases, 1) if c["expect"] != 0]
        print(f"  against: {sum(1 for i in bad if codes[i] == 0)} of {len(bad)} bad cases got exit 0 "
              f"from that copy, the success a missing read-back gives")
    if not planted:
        print("  no planted cases: the bad cases are missing, so this run proves only the good ones")
    return 0 if not wrong and planted else 1


def run(argv):
    """One command line, argv as sys.argv holds it. The self-test runs it on a stand-in."""
    cmd, wid = argv[1], argv[2]
    replaces = None
    if "--replaces" in argv and cmd in ("batch", "field"):
        i = argv.index("--replaces")
        ids, reason = (argv[i + 1:i + 2] or [""])[0], (argv[i + 2:i + 3] or [""])[0]
        if cmd == "field":
            ids, reason = wid, (argv[i + 1:i + 2] or [""])[0]
        if cmd == "batch" and not re.fullmatch(r"\d+(,\d+)*", ids):
            sys.exit('--replaces takes the item ids joined by commas, then the reason: '
                     '--replaces 101,102 "<why, in plain words>"')
        if not reason.strip():
            sys.exit("--replaces requires a reason, in plain words on this command line. It is printed, so the "
                     "override is visible.")
        refused = ask_rules.override("--replaces", reason)
        if refused:
            sys.exit(refused)
        replaces = (set(ids.split(",")), reason)
        argv = argv[:i] + argv[i + (2 if cmd == "field" else 3):]
    if cmd == "batch":
        sys.exit(batch(wid, replaces))
    if cmd in ("state", "field", "comment", "editcmt", "delcmt", "attach", "restore"):
        _promised(wid)
    elif cmd in ("parent", "reparent"):
        _promised(wid, argv[3] if len(argv) > 3 else "")
    if cmd == "delete":
        end = argv.index("--undo") if "--undo" in argv else len(argv)
        pairs = [w.split(":", 1) for w in argv[2:end]]
        if not pairs or any(len(p) != 2 or not (p[0].isdigit() and p[1].isdigit()) for p in pairs):
            sys.exit("delete takes <id>:<rev> pairs, each rev the one the item was reviewed at: "
                     "ado_write.py delete 101:7 102:5 [--undo <dir>]")
        _promised(*[p[0] for p in pairs])
        sys.exit(delete_many(pairs, argv[end + 1] if end + 1 < len(argv) else UNDO_DIR))
    elif cmd == "restore":
        restore(wid)
    elif cmd == "state":
        patch_fields(wid, [("System.State", argv[3])])
    elif cmd == "field":
        ref, value, pin = argv[3], argv[4], None
        if ref.lower() in _CHECKED:
            problems, revs, notes = _text_check([{"id": wid, "set": {ref: value}}], *(replaces or ((), None)))
            for line in notes:
                print(line)
            if problems:
                print("\n".join(problems))
                sys.exit(_ln(f"REFUSED: this would drop text someone else wrote on #{wid}. Nothing sent. Keep their "
                             f"lines: the merged value above puts them on top. If replacing them is agreed with their "
                             f"author: python ado_write.py field {wid} {ref} \"<value>\" --replaces "
                             f"\"<why, in plain words>\""))
            pin = revs.get(wid)
        patch_fields(wid, [(ref, value)], rev=pin)
    elif cmd == "comment":
        reason = None
        if "--stack" in argv:
            i = argv.index("--stack")
            reason = argv[i + 1] if i + 1 < len(argv) else ""
            if not reason.strip():
                sys.exit("--stack requires a reason. It is printed, so the override is visible.")
            refused = ask_rules.override("--stack", reason)
            if refused:
                sys.exit(refused)
        add_comment(wid, argv[3], reason)
    elif cmd == "editcmt":
        edit_comment(wid, argv[3], argv[4])
    elif cmd == "delcmt":
        del_comment(wid, argv[3])
    elif cmd == "comments":
        list_comments(wid)
    elif cmd == "parent":
        set_parent(wid, argv[3])
    elif cmd == "reparent":
        reparent(wid, argv[3], keep_related="--keep-related" in argv[4:])
    elif cmd == "attach":
        files = [a for a in argv[3:] if a != "--inline"]
        if not files:
            sys.exit("attach needs at least one file.")
        attach(wid, files, inline="--inline" in argv[3:])
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        a = sys.argv.index("--against") + 1 if "--against" in sys.argv else 0
        sys.exit(kit_config.run_isolated(_selftest, os.path.abspath(sys.argv[a]) if a and a < len(sys.argv) else None))
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    run(sys.argv)
