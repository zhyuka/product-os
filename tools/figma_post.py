#!/usr/bin/env python
"""figma_post.py - the write half of figma_comments.py.

figma_comments.py is deliberately read-only: inbox / nodes / check / frame / search. It is the gate
you run before writing. This is the write, kept in a separate file so the gate cannot be bypassed by
accident - you have to reach for a different command.

    reply   <file_key> <comment_id> <text> [--own-last-ok "<why>"] [--multi-ok "<why>"] [--repost-ok "<why>"]
            [--edited <id>,<id>... --picture <file.jpg> --separate <id>,<id>... "<why>" --cause <slug>]
            [--asks <id>]
                                              reply into an existing thread
    new     <file_key> <node_id> <text> [--separate <id>,<id>... "<why>"] [--pin-ok "<why>"] [--multi-ok "<why>"]
            [--repost-ok "<why>"] [--edited <id>,<id>... --picture <file.jpg> --cause <slug> [--new-cause "<why>"]]
            [--new-thread "<why>"] [--asks <id>]
                                              start a thread pinned to a node
    cause   <file_key> [<thread_id> <slug>]   tag an open FIX thread with its kind of fix; alone, list them
    fixnote <file_key> <comment_id> <text> --edited <id>,<id>... [--cause <slug>] [--separate <id>,<id>... "<why>"]
                                              check a FIX comment edited with figma_attach.py edit, then stamp it
    delete  <file_key> <comment_id>           remove a comment you posted that has no replies
    batch   <items.json> [--check]            post a pass's approved items as one batch; see THE BATCH
    selftest                                  planted cases for the local half of the rules below

    --drafts <drafts.md>   on new, reply and batch: the drafts file (drafts_store.py) to keep true.
                           A node in its "Cut: do not re-raise" table is refused, and a posted draft
                           leaves the file. Default: $FIGMA_DRAFTS, else figma.drafts in the
                           product-os config, else no drafts file.

THE ONE RULE THIS FILE ENFORCES. `new` and `reply` refuse unless `figma_comments.py frame` printed
the anchor node in the last 30 minutes. For a reply the anchor is the thread's root node. A read that
sees only the base text style and the first SOLID fill produces comments asking design for things
the mock already has (FOURTH FAILURE in figma_comments.py, in cmd_frame). `frame` prints both, and
this refusal makes running it the only way to post. A thread pinned to the canvas rather than a node
has nothing to read, so it is refused too: post that one from the Figma UI.

THE SECOND RULE, `new` only. It also refuses unless `figma_comments.py search` read every comment on
the file in the last 30 minutes. A comment about one frame often belongs as a reply in an open
thread on a different node (OTHER NODES, SAME SUBJECT in figma_comments.py). Whether the hits are on
the same subject is judgement; that a search ran is not.

THE THIRD RULE, `new` and `reply`. `frame` stamps each node with a hash of the frame it read, and the
post re-fetches that frame and refuses if the hash moved. A reply queued from a read made earlier in
the day can ask for something design has since done: a 30-minute stamp proves a read happened, not
that Figma still looks like it. Figma is re-read at post time, every time.

THE FOURTH RULE, `new` only. It refuses while an open thread sits on the same layer of any copy of
the node's component, on any page (figma_family.py), unless --separate lists every one of them. A
search on other words passes THE SECOND RULE and still misses the same question asked on another
copy of the component (OTHER COPIES in figma_comments.py). --separate says each listed thread was
read and is about something else. When the family check cannot run (no index, and building one
failed), `new` refuses too.

THE FIFTH RULE, `reply` only. It refuses when the newest comment in the thread, root or reply, is
the token owner's, unless --own-last-ok. A second comment under your own unanswered one reads as a
drip of corrections; edit the first one instead, with figma_attach.py edit (the browser; REST cannot
edit), once the new text is approved.

THE SIXTH RULE, `delete` only. It reads the file's comments first and refuses an id that is not in
the file, a comment that is not the token owner's, and a thread root with replies, because deleting
the root takes the replies with it. When it cannot tell whose token this is, it refuses too.

THE SEVENTH RULE, `new` only. It refuses while an open thread is pinned to the node, to a layer
inside it, or to an ancestor at an offset inside the node's box, or while any comment in an open
thread links to the node or a layer inside it, unless --separate lists every one of them. A FIX note
posted as a new thread, while your own open comment already covers the node (pinned to its parent
frame at an offset inside it, or linking to it from another thread), makes design delete or resolve
one of them; the right move is to edit your own comment. One more legitimate use of --separate: a
FIX note that THE EIGHTH RULE puts on a component, where the open thread sits on a page-frame copy
of it. List that thread and ask for it to be resolved once the component note is up.

THE EIGHTH RULE, `new`, `reply` and `fixnote`. A message starting with DONE_PREFIX needs --edited,
the nodes the fix changed. When one of them sits inside a component or component set, the anchor
has to sit inside one of those components too, or the post is refused with the component and its
page: a FIX note for an edit made inside a component, posted on a page frame, is never seen by the
designers working on the component. An edit inside other components as well prints a note naming
them, so the text can say so. A line added to the open thread of its kind of fix (THE FOURTEENTH
RULE: `fixnote` or `reply` with --cause, the cause that thread carries) gets that note in place of
the refusal, wherever the thread is pinned: the kind's thread is where its lines go. A refusal asks
for one thread inside any one of the components, the others named in its text. Each FIX post that
passes is stamped in FIXNOTES; `fixnote` runs the
same check for a comment edited with figma_attach.py edit (REST cannot edit) and stamps it.

THE NINTH RULE, `new`, `reply` and `fixnote`. Every FIX note carries its before/after picture in
the comment, after the closing "Before and after:" line, and the text says in words what each thing
was before. A REST comment cannot carry an image (POST takes message, comment_id and client_meta
only), so `new` and `reply` need --picture, the file figma_evidence.py sheet made (Figma before the
edit, Figma after, the build; up to 5, comma-separated), end the text with "Before and after:", and
right after the post hand it to figma_attach.py, which attaches the pictures in the browser (one
browser for the whole batch) and checks they are in the thread. They print the manual attach step
only when that did not attach. All three refuse text that links the picture instead, text with
anything after the label on its line (such as its file name), and --evidence (a frame placed in the
file and linked: the file fills with such frames, so the picture goes in the comment).

THE TENTH RULE, `new` only. The pin goes where no smaller layer sits. A pin at node_offset (0, 0),
the anchor's top-left corner, usually lands on a child. A reader takes a pin for a comment on the
layer under it, and figma_comments.py credits a pin at an offset to every layer whose box holds the
point, so a comment about a band also counts as one on its heading. `new` hit-tests the frame
`frame` read and pins at the first point inside the anchor, reading from the top left, that no layer
inside it and no painted layer drawn over it covers. A layer with the anchor's own box does not
count. When every point is covered it refuses and names the layer at the centre; --pin-ok pins at
the centre anyway. Blind to layers outside the frame `frame` read, and to lines, which have no area.

THE ELEVENTH RULE, `new` and `reply`. A comment that is not a FIX note asks one question. Text with
more than one "?" that ends a sentence is refused unless --multi-ok. A "?" in a link (?node-id=) or
in quoted copy ("Why do I need this?") is not counted. Comments with two or more questions are
nearly always two asks in one ("Can that flip to match? Also, is the pill meant to stay...").
--multi-ok is for an either/or that is one ask, or suggested copy that holds questions.

THE TWELFTH RULE, `new` and `reply`. `delete` stamps what the comment was on: its node for a thread
root, its thread for a reply. For 30 minutes after, `new` on that node, or `reply` in that thread,
is refused unless --repost-ok. Figma has no undelete, and every post notifies the file again. Your
own comment is reworded or re-pinned in the Figma UI, where its text and its pin both move.
--repost-ok is for a post on another subject, or a pin the UI cannot drag.

THE THIRTEENTH RULE, `new` and `reply`. Every "@" that starts a word must start the handle of someone
who has commented in the file, written as Figma writes it ("@Last, First"); otherwise it is refused,
because no mention can be made from it. Right after the post, the "@<handle>" becomes a mention chip in
the browser (figma_attach.py, in the same browser as the batch's pictures), and the markdown form of
the comment is read back to check it is a chip. Over REST a mention posts as plain text and notifies
nobody.

THE FOURTEENTH RULE, `new` with a FIX note. One kind of fix, one open thread. The note names its
kind with --cause, a short slug ("hero-scrim", "description-period"), and is refused while one of
your open FIX threads in the file carries the same cause: add it to that thread as a numbered line
(a batch `edit` item). A thread whose pictures would pass Figma's 5 still takes the line: combine
pictures (figma_attach.py combine) and edit with --replace. A fix of a kind you already have open is
an edit of your thread, never a new one, so each kind stays one thread its readers follow. --separate
lifts this only for a thread that is not the token owner's. A cause no thread has carried needs
--new-cause, after reading the open causes the refusal lists, so one kind does not get two names. In
one batch, a second new thread with a cause is refused: its line goes in the first. Causes are kept in
CAUSES; `cause <key> <thread> <slug>` tags an older thread. Without this, one design change repeated
across many frames draws one FIX note per frame, and merging them afterwards is done by hand.

THE FIFTEENTH RULE, `new` and `reply` with a FIX note. Each node in --edited that one of your other
open, placement-checked FIX threads also edited is a note that may now state an old value: a later
fix to the same header height or the same number leaves the earlier note wrong. Refused until each
such thread is in --separate (read, and about something else), or a batch `edit` or `reply` item
in the same batch gives it a dated "replaced by" line.

THE SIXTEENTH RULE, `new` with a FIX note. A FIX note on a component one of your open FIX threads
already touched goes into that thread as a numbered line (a batch `edit` item), not a new thread: the
cause slug of THE FOURTEENTH RULE is picked by the poster, so a fresh slug alone would open a thread
beside yours. The match reads facts the poster does not pick: the main components of each --edited
node (each copy on its path in figma_family's index: an instance's main, a main itself, a detached
copy's main) against those of every node the thread touched, read from its FIXNOTES stamp and from
the node ids in its text (a link, or an id written bare with 3+ digits a side, so a time is not one),
where a component set stands for all its variants. The refusal lists the threads that share one,
best match first (most shared, then the thread most about them, then the newest), and prints the
batch `edit` item for the top one. The ranking reads components, not subjects, so read the thread
before using it. It refuses too, failing closed, when it cannot rank: no index, an --edited node it
cannot place, a token owner it cannot read. In one batch, a second new FIX item on a component an
earlier one edited is refused. On a file listed in figma.new_thread_files (product-os config),
every new FIX thread is refused unless its own command line carries --new-thread "<why none of your
open FIX threads fits, in plain words>", so the reason shows in the permission prompt; the refusal
carries the same ranking. A batch cannot carry it, since its prompt shows only the file's name, so a
batch `new` FIX item on such a file is refused whatever it holds.

THE SEVENTEENTH RULE, `new` and a batch's new items, on every file. A new thread is refused while its text,
or the drafts-file block it posts (drafts_store.post_blocks: the NEW block a post of this text would remove),
links an open root comment of the token owner's: a comment id written bare or as a figma.com link's #id, a
reply standing for its thread's root. That comment is where this kind of thing already sits, so the fix is
made where it is the poster's to make and goes into that comment as a FIX (done in Figma) line, with
figma_attach.py edit or a batch `edit` item. A bare id is looked up in the post's file, a link naming another
file in that file's comments; a file that can't be read, or a token owner that can't be told, refuses.
--separate <root> "<why>" lifts it for that root, on the command line only. The block matters because a
draft's link to the comment it follows can sit in its notes, not in the text it posts. Print-only, in new's
notes: the owner's open non-FIX root comments that share LEAD_FLOOR or more of the text's words, at most
two, as a lead for a draft that names none. own_open_check is the same check, for a draft still in the
drafts file.

THE EIGHTEENTH RULE, on a file in figma.settled_files only: `new`, `reply`, a batch `edit` and
`figma_attach.py edit`. A finding the record answers is settled, not asked, so a comment that asks
design something the record already settles is refused. Every new comment but a FIX note asks, since a
comment names an action for design, so an ask worded as a statement counts too; an edit or reply asks
when it adds a question or an ask tag (Q, FLAG, ADD, FIX; new_asks). What the record says is the
command in figma.settled_cmd, which this file runs once per comment: it reads one JSON object on stdin,
{"asks": true or false, "cites": the --asks id (batch: "asks") or null, "node": the layer, "path": the
layer's lineage, page first}, prints each reason a line, and exits 0 for none, 1 for some and 2 when it
could not run. ask_refusal is the same rule on a text alone, with no layer ("node" null), for a draft
still in the drafts file (drafts_store). A file in figma.settled_files with no command, or a command
that can't run, refuses: the rule never passes unread. figma.settled_cmd runs a command, so a project's
own config sets it only once accepted: `python kit_config.py accept figma.settled_cmd`, run in the
project's folder.

LINKS. Each line this file prints that names a node ends with that node's link (figma_comments.linked), so
whichever line is copied opens the node; the posted and replied lines end with the thread's link. The text
a post sends, and the text the drafts file is matched against, stay as written.

THE BATCH. Posting is one batch per review pass, and the browser opens once for it.
`batch <items.json>` takes a JSON list, each item one of
    {"kind": "new",   "key", "node", "text", "edited": [..], "picture", "cause", "asks"}
    {"kind": "reply", "key", "parent", "text", "edited": [..], "picture", "cause", "asks"}
    {"kind": "edit",  "key", "cid", "text" or "text_file", "pictures": [..], "replace", "edited": [..], "cause",
                      "asks"}
An item can't carry an override ("separate", "pin_ok", "own_last_ok", "multi_ok", "repost_ok",
"new_cause"): the batch's permission prompt shows only its file's name, so nobody would read the
reason. One such item refuses the batch; post it on its own command line with the flag and its
reason (OVERRIDES below). (1) Every gate runs on every item; one refusal refuses the batch,
with nothing posted and no browser opened. --check stops here. (2) The items post in order, each
checked again just before it posts, with the threads this batch already started counted as read and
separate, since they were approved together. (3) One browser runs every picture, mention and edit
the batch holds, then each is checked over REST. A post that fails at (2) stops the batch there and
says what went out. An edit whose text is a FIX note runs THE EIGHTH, NINTH and FIFTEENTH RULES at
(1), as a reply does, with its "edited" and "cause"; each item's notes print there, before anyone
approves the batch; and the edit is stamped once (3) confirms it, so it needs no fixnote. `fixnote`,
for a line edited by hand, runs the same rules with --separate.

OVERRIDES. Each flag that lifts a refusal (--separate, --own-last-ok, --pin-ok, --multi-ok,
--repost-ok, --new-cause, --new-thread) takes a reason in plain words, three words or more
(ask_rules.plain), so the permission prompt for the command shows why. --separate takes its ids,
then the reason. A flag with no reason, one word or a list of ids refuses the command.

Text copied from a wrapped quote in the drafts file, with a line break mid-paragraph, is refused by
`new` and `reply` (drafts_store.wrapped_refusal), because Figma keeps every break. Any --picture is
attached, not only a FIX note's, and the text gets the "Before and after:" label it goes after.

RULES THIS FILE DOES NOT ENFORCE, because they need judgement:
  - If `search` or `nodes` shows an open thread on the subject, reply in it.
  - Two or three sentences per comment; THE ELEVENTH RULE counts only the questions. No node tables,
    no hex dumps.
  - Name the thing (page, section, component), not a bare node id.

Auth: via figma_auth.py (FIGMA_TOKEN or the OS keychain). Never printed.
NOTE: the REST API cannot @-mention, cannot edit a comment, and cannot resolve a thread. This file makes
the mention and figma_attach.py the edit, both in the browser; resolving stays in the UI, so do not
promise it in a reply.
"""
import atexit, hashlib, json, os, re, shutil, sys, tempfile, time, urllib.request, urllib.error

import figma_auth
import ask_rules  # the one plain-words rule every override flag's reason takes

API = "/v1"   # a Figma REST path; _req sends it through figma_client.py
# Written by `figma_comments.py frame`, one stamp per node it printed:
# {file_key: {node_id: [epoch, frame_id, frame_hash]}}. A bare epoch is a stamp from before the hash.
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "product-os")
READS = os.path.join(CACHE, "figma_reads.json")
# Written by `figma_comments.py search`, one stamp per file it read in full: {file_key: [epoch, terms]}.
SEARCHES = os.path.join(CACHE, "figma_searches.json")
# Written when a FIX note passes THE EIGHTH RULE, by `new`, `reply` or `fixnote`:
# {file_key: {thread root id: [epoch, [edited ids], anchor]}}. A report of fixed threads can read it.
# Never expires.
FIXNOTES = os.path.join(CACHE, "figma_fixnotes.json")
# Written by `delete`, one stamp per comment it removed: {file_key: {node id or "thread <root id>":
# [epoch, comment id]}}. See THE TWELFTH RULE.
DELETES = os.path.join(CACHE, "figma_deletes.json")
# The kind of fix each FIX thread is about, THE FOURTEENTH RULE: {file_key: {thread root id: cause}}.
# Kept apart from FIXNOTES, whose entry means "placement-checked".
CAUSES = os.path.join(CACHE, "figma_causes.json")
CAUSE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*$")
# Flags that each say a refusal was read and does not apply. parse_flags drops them from the args;
# pop_overrides takes the reason each carries first.
OK_FLAGS = ("--own-last-ok", "--pin-ok", "--multi-ok", "--repost-ok", "--new-cause")
# The batch keys that would lift a refusal. A batch item carrying one is refused (THE BATCH).
BATCH_OVERRIDES = ("separate", "own_last_ok", "pin_ok", "multi_ok", "repost_ok", "new_cause")
# What a FIX note starts with. Anything that reads FIX notes back should share this string.
DONE_PREFIX = "FIX (done in Figma)"
FRESH_MIN = 30


def _drafts():
    """drafts_store beside this file, or None when it is not there. Its file is --drafts, which main
    puts in $FIGMA_DRAFTS, else figma.drafts in the config; with neither it does nothing."""
    try:
        import drafts_store
        return drafts_store
    except ImportError:
        return None


def _drafts_cut(node_id, key=None):
    """The Cut table's refusal for node_id in file `key`: a row refuses only in the file its URL names."""
    ds = _drafts()
    return ds.cut_refusal(node_id, key) if ds else None


def _drafts_remove(text, **kw):
    ds = _drafts()
    return ds.remove_posted(text, **kw) if ds else None


def _drafts_wrapped(text):
    """drafts_store's refusal of text that keeps a wrapped quote's line breaks, or None."""
    ds = _drafts()
    return ds.wrapped_refusal(text) if ds and hasattr(ds, "wrapped_refusal") else None


def _drafts_blocks(text, node_id):
    """The whole lines of each NEW drafts-file block a post of text on node_id would remove
    (drafts_store.post_blocks), for THE SEVENTEENTH RULE. [] with no drafts file. Raises OSError when the
    file can't be read, and AttributeError when this drafts_store has no post_blocks."""
    ds = _drafts()
    if not ds or not ds.drafts_path():
        return []
    return ds.post_blocks(text, node_id)


def take_drafts_flag(argv):
    """argv without `--drafts <path>`; the path goes in $FIGMA_DRAFTS, where drafts_store (here and in
    figma_attach.py) reads it."""
    argv = list(argv)
    if "--drafts" in argv:
        i = argv.index("--drafts")
        if i + 1 >= len(argv):
            sys.exit("--drafts needs a path")
        os.environ["FIGMA_DRAFTS"] = os.path.abspath(os.path.expanduser(argv[i + 1]))
        del argv[i:i + 2]
    return argv


def _tok():
    return figma_auth.token()


def _norm(node_id):
    return str(node_id).replace("-", ":")


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _load_reads():
    return _load(READS)


def _save(path, data):
    """Atomic write: a temp file of its own, fsync, replace. With one fixed temp name, two runs at once
    replace each other's temp file away and raise FileNotFoundError. Two writers can still each replace
    the file whole, and the last one wins."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _stamp(v):
    """(epoch, frame_id, frame_hash) from a READS value. A bare epoch has no frame and no hash."""
    if isinstance(v, (int, float)):
        return v, None, None
    return tuple((list(v) + [None, None, None])[:3])


def node_hash(doc):
    """What `frame` read, as one value: the frame's whole REST subtree with its keys sorted."""
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def fetch_node(key, node_id):
    """The node's subtree from the call `frame` makes, so the two hashes compare like for like."""
    import figma_comments
    nid = _norm(node_id)
    data = figma_comments.get(figma_comments.NODES_API.format(key, nid))
    return ((data.get("nodes") or {}).get(nid) or {}).get("document")


def record_reads(key, node_ids, now=None, root=None, root_hash=None):
    """Stamp node ids as read, each with the frame `frame` printed them under and that frame's hash.
    Atomic write; stamps older than a day are dropped."""
    now = time.time() if now is None else now
    reads = _load_reads()
    for k in list(reads):
        reads[k] = {n: v for n, v in reads[k].items() if now - _stamp(v)[0] < 86400}
    frame = _norm(root) if root else None
    reads.setdefault(key, {}).update({_norm(n): [now, frame, root_hash] for n in node_ids if n})
    _save(READS, reads)


def record_search(key, terms, now=None):
    """Stamp a file as searched in full, with the terms. Stamps older than a day are dropped."""
    now = time.time() if now is None else now
    done = {k: v for k, v in _load(SEARCHES).items() if now - v[0] < 86400}
    done[key] = [now, list(terms)]
    _save(SEARCHES, done)


def search_gate(key, now=None):
    """None if `search` read this file in the last FRESH_MIN minutes, else the refusal text."""
    now = time.time() if now is None else now
    v = _load(SEARCHES).get(key)
    if v and now - v[0] <= FRESH_MIN * 60:
        return None
    when = ("has not read this file" if not v else
            f"last read this file {(now - v[0]) / 60:.0f} minutes ago, for {' + '.join(v[1])}")
    return (f"REFUSED: `search` {when}. It has to be within the last {FRESH_MIN} minutes.\n"
            f"  python figma_comments.py search --file {key} <words of the subject>\n"
            "If it shows an open thread on the same subject, on any node, reply in that thread instead.")


def gate(key, node_id, now=None):
    """None if `frame` printed this node in the last FRESH_MIN minutes, else the refusal text."""
    now = time.time() if now is None else now
    if not node_id:
        return ("REFUSED: this thread is pinned to the canvas, not a node, so there is nothing to read "
                "first. Post it from the Figma UI.")
    v = _load_reads().get(key, {}).get(_norm(node_id))
    t = None if v is None else _stamp(v)[0]
    if t is not None and now - t <= FRESH_MIN * 60:
        return None
    when = (f"has not printed node {_norm(node_id)}" if t is None
            else f"last printed node {_norm(node_id)} {(now - t) / 60:.0f} minutes ago")
    return (f"REFUSED: `frame` {when}. It has to be within the last {FRESH_MIN} minutes.\n"
            f"  python figma_comments.py frame {key} {_norm(node_id)}\n"
            "Read every fill and text run it prints, check the comment against them, then post.")


def drift_gate(key, node_id, fetch=fetch_node, now=None):
    """None if the frame this node was printed under is unchanged in Figma since `frame` read it,
    else the refusal text. One API call. See THE THIRD RULE."""
    now = time.time() if now is None else now
    v = _load_reads().get(key, {}).get(_norm(node_id))
    t, frame, was = _stamp(v) if v is not None else (None, None, None)
    if not frame or not was:
        return (f"REFUSED: the stamp on node {_norm(node_id)} holds no hash of what `frame` read, so "
                "there is nothing to compare Figma against. Re-run it:\n"
                f"  python figma_comments.py frame {key} {_norm(node_id)}")
    doc = fetch(key, frame)
    is_now = node_hash(doc) if doc else None
    if is_now == was:
        return None
    return (f"REFUSED: {frame} has changed in Figma since `frame` printed it "
            f"{(now - t) / 60:.0f} minutes ago ({was} then, {is_now or 'deleted'} now). Someone edited "
            "it after the read, so the ask may already be done. Re-run frame, check the comment "
            "against what it prints now, then post.\n"
            f"  python figma_comments.py frame {key} {frame}")


def family_gate(key, node_id, separate=(), comments=None, mode="auto", link=None):
    """None if no open thread sits on the same layer of a copy of node_id's component, or if each
    one is in separate; else the refusal text. See THE FOURTH RULE."""
    import figma_family
    rep = figma_family.check(key, [node_id], comments, mode=mode)
    if not rep.ran:
        cov = figma_family.coverage(rep)
        return f"REFUSED: {cov}" + ("" if "figma_family.py build" in cov else
                                    f"\n  python figma_family.py build {key}")
    left = sorted(set(rep.same_layer(node_id)) - {str(s) for s in separate})
    if not left:
        return None
    return (f"REFUSED: {len(left)} open thread(s) sit on the same layer as {_norm(node_id)} in a copy "
            "of its component, on this page or another one:\n"
            + "\n".join(figma_family.lines(rep, node_id, link, show_resolved=False))
            + "\nRead each one. If one is about the same thing, reply in it. If none is, re-run with\n"
              f"  --separate {','.join(left)} \"<why each is about something else>\"\n{figma_family.coverage(rep)}")


def own_last_gate(key, comment_id, comments, me, link=None):
    """None unless the newest comment in the thread is me's; else the refusal text. See THE FIFTH
    RULE. No me means no way to tell, which refuses too."""
    by_id = {str(c["id"]): c for c in comments}
    r = by_id.get(str(comment_id))
    if r is None:
        return f"REFUSED: comment {comment_id} is not in file {key}."
    while r.get("parent_id") and str(r["parent_id"]) in by_id:
        r = by_id[str(r["parent_id"])]
    thread = [r] + [c for c in comments if str(c.get("parent_id") or "") == str(r["id"])]
    last = max(thread, key=lambda c: c.get("created_at", ""))
    who = (last.get("user") or {}).get("handle", "")
    if not me:
        return ("REFUSED: could not tell whose token this is (FIGMA_ME is unset and /v1/me failed), so "
                f"there is no telling whether the newest comment in thread {r['id']} is yours. Read the "
                "thread, then pass --own-last-ok \"<why a reply is right>\" if it is.")
    if who.strip().lower() != me.strip().lower():
        return None
    words = " ".join((last.get("message") or "").split())[:100]
    return (f"REFUSED: the newest comment in thread {r['id']} is yours ({last.get('created_at', '')[:16]}, "
            f"\"{words}\"), and nobody has answered it. Edit that comment instead of adding a reply "
            "under it: figma_attach.py edit, once the new text is approved. REST cannot edit."
            + (f"\n  {link(r)}" if link else "")
            + "\nIf a separate reply is still right, re-run with --own-last-ok \"<why>\".")


def delete_gate(key, comment_id, comments, me):
    """None if comment_id is me's and nobody has replied under it; else the refusal text. See THE
    SIXTH RULE. No me means no way to tell, which refuses too."""
    by_id = {str(c["id"]): c for c in comments}
    c = by_id.get(str(comment_id))
    if c is None:
        return f"REFUSED: comment {comment_id} is not in file {key}."
    if not me:
        return ("REFUSED: could not tell whose token this is (FIGMA_ME is unset and /v1/me failed), so "
                f"there is no telling whether comment {comment_id} is yours. Delete it in the Figma UI.")
    who = (c.get("user") or {}).get("handle", "")
    if who.strip().lower() != me.strip().lower():
        return f"REFUSED: comment {comment_id} is not yours. This deletes only the token owner's comments."
    replies = [r for r in comments if str(r.get("parent_id") or "") == str(c["id"])]
    if replies:
        return (f"REFUSED: comment {comment_id} is the root of a thread with {len(replies)} "
                f"repl{'y' if len(replies) == 1 else 'ies'}, and deleting it deletes them too. Edit it "
                "in the Figma UI instead.")
    return None


def ids_in(text):
    """Every node id a Figma link in text points at, in colon form: node-id=1-2, 1%3A2, and an
    instance layer I1-2%3B3-4 as I1:2;3:4."""
    out = set()
    for m in re.finditer(r"node-id=([0-9A-Za-z%:;-]+)", text or ""):
        v = re.sub("%3[Aa]", ":", re.sub("%3[Bb]", ";", m.group(1)))
        out.add(v.replace("-", ":"))
    return out


def _root_of(comments, comment_id):
    """The root comment of comment_id's thread, or None if the id is not in comments."""
    by_id = {str(c["id"]): c for c in comments}
    c = by_id.get(str(comment_id))
    while c is not None and c.get("parent_id") and str(c["parent_id"]) in by_id:
        c = by_id[str(c["parent_id"])]
    return c


def dup_gate(key, node_id, separate=(), comments=(), loc=None, link=None):
    """None unless an open thread is on node_id or links to it, each not in separate; else the
    refusal text. See THE SEVENTH RULE. loc is figma_comments.locate, or a stub in the selftest."""
    import figma_comments as FC
    nid = _norm(node_id)
    try:
        paths, subs = (loc or FC.locate)(key, [nid])
    except (SystemExit, Exception) as e:  # get() exits on an HTTP error
        return (f"REFUSED: could not read where {nid} sits in file {key} ({e}), so there is no "
                "telling which threads are already on it.")
    if nid not in paths:
        return f"REFUSED: node {nid} is not in file {key}."
    inside = {nid} | set(subs.get(nid) or ())
    hits = {}
    for c, how in FC.on_nodes(list(comments), paths, [nid], subs).get(nid, []):
        r = _root_of(comments, c["id"])
        hits.setdefault(str(r["id"]), (r, how))
    for c in comments:
        cited = ids_in(c.get("message")) & inside
        r = _root_of(comments, c["id"]) if cited else None
        if r is not None:
            hits.setdefault(str(r["id"]), (r, f"links to {sorted(cited)[0]}"))
    skip = {str(s) for s in separate}
    left = {t: v for t, v in hits.items() if not v[0].get("resolved_at") and t not in skip}
    if not left:
        return None
    rows = [f"  {t} ({how}, {(r.get('user') or {}).get('handle', '?')}): "
            f"\"{' '.join((r.get('message') or '').split())[:90]}\""
            + (f"\n    {link(r)}" if link else "") for t, (r, how) in sorted(left.items())]
    return (f"REFUSED: {len(left)} open thread(s) are already on {nid} or link to it:\n"
            + "\n".join(rows)
            + "\nIf one is yours, edit that comment with figma_attach.py edit (REST cannot edit). If it is "
              "someone else's, reply in it. If none is about this, or one sits on a page-frame copy "
              "and this FIX note on the component replaces it (ask for that one to be resolved), "
              f"re-run with\n  --separate {','.join(sorted(left))} \"<why>\"")


def _layer(node_id):
    """An instance layer I<instance>;<main> as the instance it sits in, where the files API can find
    it; any other id as itself."""
    n = _norm(node_id)
    return n[1:].split(";")[0] if n.startswith("I") else n


def pin_gate(node_id):
    """A pin on a layer inside a component instance (an id starting I) comes back from Figma as a 400
    that waiting does not fix. Refused before any call, with the instance to pin on instead."""
    if _norm(node_id).startswith("I"):
        return (f"REFUSED: {node_id} is a layer inside a component instance, and Figma refuses a pin "
                f"there with a 400. Pin on the instance, {_layer(node_id)}, or a plain node beside it.")
    return None


def asks(text):
    """The questions in text: each "?" that ends a sentence, once links, quoted copy and code are
    taken out. See THE ELEVENTH RULE."""
    t = re.sub(r"https?://\S+", " ", text or "")
    t = re.sub(r"\"[^\"\n]*\"|“[^”\n]*”|`[^`\n]*`", " ", t)
    return [q.strip() for q in re.findall(r"[^.?!\n]*\?(?=\s|$|[)\]*_'’])", t)]


def question_gate(text, multi_ok=False):
    """None unless text is not a FIX note and asks more than one question; else the refusal text."""
    qs = asks(text)
    if multi_ok or len(qs) < 2 or text.startswith(DONE_PREFIX):
        return None
    return (f"REFUSED: the text asks {len(qs)} questions:\n"
            + "\n".join(f"  - {q[-100:]}" for q in qs)
            + "\nOne comment carries one ask, so the answer can be one reply. Post the others as their own "
              "comments, or rewrite them as one question. If they are one ask (an either/or), or quoted "
              "copy that holds questions, re-run with --multi-ok \"<why it is one ask>\".")


def record_delete(key, comment_id, comments, now=None):
    """Stamp what a deleted comment was on: its node for a thread root, "thread <root id>" for a
    reply. A canvas pin has no node and is not stamped. Stamps older than a day are dropped."""
    now = time.time() if now is None else now
    c = {str(x["id"]): x for x in comments}.get(str(comment_id))
    root = _root_of(comments, comment_id)
    if c is None or root is None:
        return None
    on = (f"thread {root['id']}" if c.get("parent_id")
          else _norm((c.get("client_meta") or {}).get("node_id") or ""))
    if not on:
        return None
    done = {k: {t: v for t, v in d.items() if now - v[0] < 86400} for k, d in _load(DELETES).items()}
    done.setdefault(key, {})[on] = [now, str(comment_id)]
    _save(DELETES, done)
    return on


def repost_gate(key, on, now=None):
    """None unless `delete` removed a comment on `on` (a node id, or "thread <root id>") in the last
    FRESH_MIN minutes; else the refusal text. See THE TWELFTH RULE."""
    now = time.time() if now is None else now
    v = _load(DELETES).get(key, {}).get(_norm(on)) if on else None
    if not v or now - v[0] > FRESH_MIN * 60:
        return None
    where = f"in thread {on.split()[1]}" if on.startswith("thread ") else f"on {_norm(on)}"
    return (f"REFUSED: comment {v[1]} {where} was deleted {(now - v[0]) / 60:.0f} minutes ago, so this "
            "reads as a delete and repost. Figma has no undelete, and every post notifies the file again. "
            "Reword or re-pin your own comment in the Figma UI, where its text and its pin both move. If "
            "this post is on another subject, or replaces a pin the UI cannot drag, re-run with --repost-ok "
            "\"<why>\".")


def _cut(b, c):
    """Box b cut to box c, or None when no area of b is inside c."""
    x0, y0 = max(b["x"], c["x"]), max(b["y"], c["y"])
    x1 = min(b["x"] + b["width"], c["x"] + c["width"])
    y1 = min(b["y"] + b["height"], c["y"] + c["height"])
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0} if x1 > x0 and y1 > y0 else None


def _has(b, x, y):
    """Whether box b holds the point, edges included, as figma_comments.how_on reads a pin."""
    return b["x"] <= x <= b["x"] + b["width"] and b["y"] <= y <= b["y"] + b["height"]


def _paints(n):
    """Whether the layer draws anything itself: text, or a visible fill or stroke. A frame or group
    with neither only holds its children."""
    if n.get("type") == "TEXT":
        return True
    return any(p.get("visible", True) is not False and p.get("opacity", 1) != 0
               for p in (n.get("fills") or []) + (n.get("strokes") or []))


EVERYWHERE = {"x": -1e9, "y": -1e9, "width": 2e9, "height": 2e9}


def drawn(doc):
    """[(node, box)] for every layer in doc with an area on screen, in paint order (a later one draws
    over an earlier one), each box cut to the frames that clip it. A layer hidden on itself or an
    ancestor, at opacity 0, or clipped away entirely is left out, and so is a line."""
    out = []

    def walk(n, clip):
        if n.get("visible", True) is False or n.get("opacity", 1) == 0:
            return
        b = n.get("absoluteBoundingBox")
        b = _cut(b, clip) if b else None
        if b:
            out.append((n, b))
        if n.get("clipsContent"):
            if not b:
                return
            clip = b
        for k in n.get("children") or []:
            walk(k, clip)
    walk(doc or {}, EVERYWHERE)
    return out


def _free_spot(box, covers, least=1.0):
    """The first point in box, by rows from the top and then from the left, that no box in covers
    holds, or None. Coverage changes only at an edge, so one point between each pair of neighbouring
    edges is enough: a 32px gap between cards is found, which a fixed grid steps over.
    A strip thinner than `least` pixels is taken for float noise between boxes that abut."""
    top, bottom = box["y"], box["y"] + box["height"]
    ys = sorted({top, bottom} | {v for _, b in covers for v in (b["y"], b["y"] + b["height"]) if top < v < bottom})
    for y0, y1 in zip(ys, ys[1:]):
        if y1 - y0 < least:
            continue
        y = (y0 + y1) / 2
        runs = sorted((b["x"], b["x"] + b["width"]) for _, b in covers if b["y"] <= y <= b["y"] + b["height"])
        x = box["x"]
        for r0, r1 in runs + [(box["x"] + box["width"], box["x"] + box["width"])]:
            if r0 - x >= least:
                return (x + r0) / 2, y
            x = max(x, r1)
    return None


def pin_spot(doc, anchor_id, pin_ok=False):
    """(node_offset or None, refusal or None, note). See THE TENTH RULE. doc is the frame `frame`
    read. The point is the first free one in the part of the anchor on screen (_free_spot). The
    offset is from the anchor's own top-left."""
    nid = _norm(anchor_id)
    layers = drawn(doc)
    at = next((i for i, (n, _) in enumerate(layers) if n.get("id") == nid), None)
    if at is None:
        return None, (f"REFUSED: {nid} has no area on screen in the frame `frame` read (hidden, clipped "
                      "away or not in it), so a pin on it would sit on nothing a reader sees."), None
    node, box = layers[at]
    corner, area = node["absoluteBoundingBox"], box["width"] * box["height"]
    inner, stack = set(), list(node.get("children") or [])
    while stack:
        k = stack.pop()
        inner.add(k.get("id"))
        stack.extend(k.get("children") or [])
    # What a reader would take the pin for instead: any smaller layer inside the anchor, painted or
    # not (figma_comments credits the pin to it either way), or a painted layer drawn over it.
    over = [(n, b) for i, (n, b) in enumerate(layers) if i != at and _cut(b, box)
            and ((n.get("id") in inner and b["width"] * b["height"] < area * 0.999)
                 or (i > at and n.get("id") not in inner and _paints(n)))]
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    rel = lambda x, y: {"x": round(x - corner["x"], 1), "y": round(y - corner["y"], 1)}
    spot = _free_spot(box, over)
    if spot:
        off = rel(*spot)
        return off, None, f"  pin: {off['x']:g},{off['y']:g} inside {nid}, where no smaller layer sits"
    under = min((nb for nb in over if _has(nb[1], cx, cy)), key=lambda nb: nb[1]["width"] * nb[1]["height"],
                default=None)
    what = f"{under[0].get('name')!r} {under[0].get('id')}" if under else "a layer"
    if pin_ok:
        return rel(cx, cy), None, f"  pin: the centre of {nid}, on {what} (--pin-ok)"
    return None, (f"REFUSED: every point inside {nid} {node.get('name')!r} sits on a smaller layer or one "
                  f"drawn over it, so the pin will read as about that layer. At the centre that is {what}. "
                  f"If the comment is about that layer, post on it. If it is about {nid} as a whole, re-run "
                  "with --pin-ok \"<why the whole of it>\" to pin at its centre."), None


def kinds_path(doc, ids):
    """{id: [(id, type, name), ...]}, the path from the document root down to each id in doc."""
    want, out, stack = set(ids), {}, [(doc, [])]
    while stack:
        n, path = stack.pop()
        path = path + [(n["id"], n.get("type"), n.get("name", ""))]
        if n["id"] in want:
            out[n["id"]] = path
        stack.extend((k, path) for k in n.get("children") or [])
    return out


def placement_gate(key, anchor_id, edited, doc=None, cause=None):
    """(refusal text or None, notes). See THE EIGHTH RULE. doc is a planted tree holding the edited
    ids and the anchor (the selftest); when None, where each sits comes from figma_comments.lineage.
    cause: the line goes in the open thread of that kind of fix, so a component it is outside is a note."""
    if not edited:
        return (f"REFUSED: a message starting with \"{DONE_PREFIX}\" needs --edited <id>,<id>...: the "
                "nodes the fix changed, so the comment can be checked against where they live.", [])
    if not anchor_id:
        return ("REFUSED: this thread is pinned to the canvas, not a node, so there is no telling "
                "whether it sits where the edit is.", [])
    a, ed = _layer(anchor_id), sorted({_layer(e) for e in edited})
    if doc is None:
        import figma_comments as FC
        try:
            lin = FC.lineage(key, set(ed) | {a})
        except (SystemExit, Exception) as e:  # lineage() exits on an HTTP error
            return (f"REFUSED: could not read where the edited nodes sit in file {key} ({e}).", [])
        paths = {i: [(n["id"], n.get("type"), n.get("name", "")) for n in p] for i, p in lin.items() if p}
    else:
        paths = kinds_path(doc, ed + [a])
    gone = [n for n in ed + [a] if n not in paths]
    if gone:
        return f"REFUSED: not in file {key}: {', '.join(gone)}.", []
    around_anchor = {i for i, _, _ in paths[a]}
    held, covered = {}, False
    for e in ed:
        comps = [(i, nm) for i, t, nm in paths[e] if t in ("COMPONENT", "COMPONENT_SET")]
        if not comps:
            continue
        if any(i in around_anchor for i, _ in comps):
            covered = True
            continue
        page = next((nm for _, t, nm in paths[e] if t == "CANVAS"), "?")
        held.setdefault(comps[0], (page, []))[1].append(e)
    if not held:
        return None, []
    import figma_comments
    rows = [f"  {nm} {i} on page \"{page}\" (edited {', '.join(es)})  {figma_comments.node_link(key, i)}"
            for (i, nm), (page, es) in sorted(held.items())]
    if covered or cause:
        return None, [f"NOTE: the fix changed nodes inside {'other ' if covered else ''}components. " + (
            "Say so in the text, or put a note there too:" if covered else
            f"This is the open thread for {cause!r} (THE FOURTEENTH RULE), so the line goes here; "
            "name them in it:")] + rows
    return (f"REFUSED: the fix changed nodes inside a component, and {_norm(anchor_id)} is inside "
            "none of them. A designer works on the component, so the comment goes in one thread pinned "
            "inside any one of these, with the others named in its text:\n" + "\n".join(rows), [])


def fix_placement(key, comments, root, node, edited, claimed=None, doc=None, causes=None):
    """THE EIGHTH RULE for a FIX line in thread `root`: placement_gate, with the thread's cause when the
    line claims the cause that thread carries (THE FOURTEENTH RULE). (refusal or None, notes)."""
    rid, live = str((root or {}).get("id", "")), open_causes(key, comments, causes)
    have = next((c for c, ts in live.items() if rid in ts), None)
    refused, notes = placement_gate(key, node, edited, doc=doc, cause=have if claimed and claimed == have else None)
    if refused and have and claimed != have:
        refused += f"\nThread {rid} is the open thread for {have!r}: a line of that kind passes --cause {have}."
    return refused, notes


def fix_line_gate(key, comments, root, node, edited, cause=None, skip=(), own=None, link=None, doc=None,
                  causes=None, fixnotes=None):
    """THE EIGHTH and FIFTEENTH RULES for a FIX line going into thread `root`, by reply or by edit.
    (refusal or None, notes)."""
    refused, notes = fix_placement(key, comments, root, node, edited, cause, doc=doc, causes=causes)
    return refused or replaced_gate(key, edited, comments, skip, own=own or (root or {}).get("id"), link=link,
                                    notes=fixnotes), notes


PICTURE_HOW = ("Make the picture with figma_evidence.py sheet (Figma before the edit, Figma after, the build) "
               "and pass the file as --picture (up to 5, comma-separated); right after the post, figma_attach.py "
               "attaches it to the comment in the Figma UI, after \"Before and after:\".")
PICTURE_LABEL = "Before and after:"
# A "Before and after:" line followed by a link: the picture linked, not attached.
PICTURE_LINKED = re.compile(r"Before and after:[ \t]*\S*https?://", re.I)
# Anything else after it on its line, such as the picture's file name: posted as text beside the picture.
PICTURE_NAMED = re.compile(r"Before and after:[ \t]*\S", re.I)


def picture_gate(text, evidence=None, picture=None, posting=True):
    """Refusal text or None. See THE NINTH RULE. `posting` is False for fixnote, where the picture
    was attached by hand and the API cannot see it."""
    if evidence:
        return ("REFUSED: --evidence is not supported: the before/after picture goes in "
                "the comment itself, attached in the Figma UI, not as a frame in the file that the note links. "
                + PICTURE_HOW)
    if PICTURE_LINKED.search(text):
        return (f"REFUSED: the text links its before/after picture. The picture goes in the comment itself, "
                f"attached in the Figma UI after \"{PICTURE_LABEL}\": drop the link.")
    if PICTURE_NAMED.search(text):
        return (f"REFUSED: the text has more after \"{PICTURE_LABEL}\" on its line, such as the picture's file name. "
                f"The label ends the text; the file goes in --picture: drop what follows it.")
    if posting:
        if not picture:
            return (f"REFUSED: a message starting with \"{DONE_PREFIX}\" needs --picture <file.jpg>, the before/after "
                    "picture to attach to it. " + PICTURE_HOW)
        for p in pictures_of(picture):
            if not (os.path.isfile(p) and p.lower().endswith((".jpg", ".jpeg", ".png"))):
                return f"REFUSED: --picture {p} is not a .jpg or .png file. " + PICTURE_HOW
        if len(pictures_of(picture)) > 5:
            return ("REFUSED: a comment takes up to 5 pictures; combine them into fewer first "
                    "(figma_attach.py combine <out.jpg> <picture>...). " + PICTURE_HOW)
    return None


def pictures_of(picture):
    """The files --picture names: one, or several separated by commas."""
    return [p.strip() for p in (picture or "").split(",") if p.strip()]


def picture_step(text, evidence=None, picture=None):
    """(refusal or None, text to post). A FIX note always carries a picture; any other text that has
    one gets the same checks and the label figma_attach puts it after, so the picture is not left out."""
    if not (text.startswith(DONE_PREFIX) or picture):
        return None, text
    refused = picture_gate(text, evidence, picture)
    return refused, (text if refused else with_label(text))


def with_label(text):
    """text ending in "Before and after:", where figma_attach.py puts the picture."""
    return text if text.rstrip().endswith(PICTURE_LABEL) else f"{text.rstrip()}\n\n{PICTURE_LABEL}"


def attach_note(key, cid, node, picture):
    return (f"  ATTACH {picture} to comment {cid} in the Figma UI, after \"{PICTURE_LABEL}\" (REST cannot "
            f"attach an image): {thread_link(key, cid, node)}")


def record_fixnote(key, thread_id, edited, anchor_id, now=None):
    """Stamp a thread's FIX note as placement-checked. Atomic write."""
    now = time.time() if now is None else now
    notes = _load(FIXNOTES)
    had = (notes.get(key) or {}).get(str(thread_id)) or [None, []]
    notes.setdefault(key, {})[str(thread_id)] = [now, sorted({_norm(e) for e in edited} | set(had[1])),
                                                 _norm(anchor_id) if anchor_id else None]
    _save(FIXNOTES, notes)


def record_cause(key, thread_id, cause):
    """Keep a FIX thread's cause (THE FOURTEENTH RULE). Atomic write."""
    causes = _load(CAUSES)
    causes.setdefault(key, {})[str(thread_id)] = cause
    _save(CAUSES, causes)


def _open_roots(comments):
    return {str(c["id"]) for c in comments if not c.get("parent_id") and not c.get("resolved_at")}


def _thread_url(comments, link):
    """id -> what to print for it: link(comment) when given (figma_comments.permalink takes the comment,
    not its id), else the id."""
    by = {str(c["id"]): c for c in comments}
    return lambda t: link(by[t]) if link and t in by else t


def open_causes(key, comments, causes=None):
    """{cause: [open thread ids]} for the file, from CAUSES and a read of its comments."""
    causes, live, out = _load(CAUSES) if causes is None else causes, _open_roots(comments), {}
    for t, c in (causes.get(key) or {}).items():
        if t in live:
            out.setdefault(c, []).append(t)
    return out


def cause_gate(key, cause, comments, separate=(), new_cause=False, link=None, causes=None, me=None):
    """None, or the refusal. See THE FOURTEENTH RULE. `me`: the token owner's handle (read when needed); a thread
    in `separate` is lifted only when its root is someone else's."""
    causes = _load(CAUSES) if causes is None else causes
    live = open_causes(key, comments, causes)
    url = _thread_url(comments, link)
    listed = "\n".join(f"  {c}: " + ", ".join(url(t) for t in ts) for c, ts in sorted(live.items())) or "  (none)"
    if not cause:
        return ("REFUSED: a FIX note names its kind of fix with --cause <slug> (batch: \"cause\"). If one of "
                f"these open threads is the same kind, add a numbered line to it instead (a batch edit item):\n{listed}")
    if not CAUSE_RE.match(cause):
        return f"REFUSED: --cause {cause!r} is not a slug: lower case, digits and hyphens, like \"hero-scrim\"."
    same, sep = live.get(cause, []), {str(x) for x in separate}
    if sep & set(same):
        me = ((_me() if me is None else me) or "").strip().lower()
        by_id = {str(c["id"]): c for c in comments}
        who = lambda t: ((by_id.get(t) or {}).get("user") or {}).get("handle", "").strip().lower()
        same = [t for t in same if not (t in sep and me and who(t) and who(t) != me)]
    if same:
        return (f"REFUSED: your open FIX thread {', '.join(url(t) for t in same)} is already about {cause!r}. Add this "
                "as a numbered line to it (a batch edit item), with its picture. When the pictures would pass 5, "
                "combine them into fewer (figma_attach.py combine <out.jpg> <picture>...) and edit with --replace. "
                "--separate lifts this only for a thread that is not yours.")
    if not new_cause and cause not in {c for c in (causes.get(key) or {}).values()}:
        return (f"REFUSED: no thread has carried the cause {cause!r}. Read the open ones; if this is one of them, "
                f"use its name. If it is a new kind, re-run with --new-cause \"<why none fits>\" on its own "
                f"command line; a batch can't carry it.\n{listed}")
    return None


BARE_ID = re.compile(r"(?<![\w:;/=-])(I?\d{3,}:\d{3,}(?:;\d+:\d+)*)(?![\w:])")   # 3+ digits a side: not a time


def new_thread_files():
    """figma.new_thread_files in the product-os config: the files where every new FIX thread needs
    --new-thread "<why>" on its own command line (THE SIXTEENTH RULE). Empty when unset."""
    try:
        import kit_config
    except ImportError:
        return set()
    v = kit_config.get("figma", "new_thread_files") or []
    return {v} if isinstance(v, str) else {str(k) for k in v}


def read_only():
    """figma.read_only in the product-os config. A project whose own guarded tools own its Figma writes sets it,
    so this copy posts, replies and deletes nothing: _req refuses each write before any call. False when unset."""
    try:
        import kit_config
    except ImportError:
        return False
    return bool(kit_config.get("figma", "read_only"))


# THE EIGHTEENTH RULE. An ask's tag starts a line, after any @mention; FIX (done in Figma) has no colon after FIX,
# so it is none.
ASK_TAG = re.compile(r"^\s*(?:@[^\n]*?\s)?(?:Q|FLAG|ADD|FIX)\s*:", re.M)
SETTLED = None      # the selftest's and the tests' stand-in for figma.settled_cmd: SETTLED(request) -> (reasons, why)


def new_asks(text, old):
    """The asks in `text` that `old` (the text before an edit; "" for a reply) does not hold: a question, or a line
    with an ask tag, unlike each of old's at 0.9 and neither holding the other (a reworded question is a new ask; a
    note appended to an old ask line is not, and any question it adds is caught on its own)."""
    import difflib
    fold = lambda t: re.sub(r"\W+", " ", t).strip().lower()
    tagged = lambda t: [ln for ln in (t or "").splitlines() if ASK_TAG.match(ln)]
    had = [fold(q) for q in asks(old) + tagged(old)]
    return [q for q in asks(text) + tagged(text)
            if not any(difflib.SequenceMatcher(None, fold(q), h).ratio() >= 0.9 or fold(q) in h or h in fold(q)
                       for h in had)]


def is_ask(text, old=None):
    """THE EIGHTEENTH RULE: whether text asks. A new comment names an action for design, so each one but a FIX note
    asks, worded as a question or not. An edit or reply (`old` its text before, or "" for a reply) asks when it adds
    one."""
    return not text.startswith(DONE_PREFIX) if old is None else bool(new_asks(text, old))


def settled_files():
    """figma.settled_files in the product-os config: the files THE EIGHTEENTH RULE judges. Empty when unset."""
    try:
        import kit_config
    except ImportError:
        return set()
    v = kit_config.get("figma", "settled_files") or []
    return {v} if isinstance(v, str) else {str(k) for k in v}


def settled(request):
    """(reasons, why it did not run or None) from figma.settled_cmd for one request (THE EIGHTEENTH RULE)."""
    if SETTLED is not None:
        return SETTLED(request)
    try:
        import kit_config
        cmd = kit_config.get("figma", "settled_cmd")
    except ImportError:
        cmd = None
    if not cmd:
        return [], ("figma.settled_cmd is not set, or this project's value is not accepted (`python kit_config.py "
                    "accept figma.settled_cmd`, in the project's folder)")
    import shlex, subprocess
    try:
        p = subprocess.run(shlex.split(cmd) if isinstance(cmd, str) else [str(c) for c in cmd],
                           input=json.dumps(request), capture_output=True, text=True, timeout=120)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return [], f"figma.settled_cmd could not run ({type(e).__name__})"
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    if p.returncode == 0:
        return [], None
    if p.returncode == 1 and lines:
        return lines, None
    return [], f"figma.settled_cmd exited {p.returncode}" + (f": {lines[-1][:200]}" if lines else "")


class SettledNotRun(RuntimeError):
    """THE EIGHTEENTH RULE could not judge a text: figma.settled_cmd is unset, unaccepted or failed."""


def ask_refusal(text, cid=None, old=None):
    """THE EIGHTEENTH RULE on a text alone, with no Figma read: None when the text does not ask, or when
    figma.settled_cmd finds no reason; else why not. Raises SettledNotRun when the command did not run, so a
    caller lists it as a check that didn't run, never as a refusal or a pass. settled_gate adds what needs the
    layer."""
    if not is_ask(text, old):
        return None
    reasons, why = settled({"asks": True, "cites": cid, "node": None, "path": None})
    if why:
        raise SettledNotRun(f"THE EIGHTEENTH RULE did not run: {why}")
    return "; ".join(reasons) or None


def settled_gate(key, node_id, text, cid=None, old=None, path=None):
    """THE EIGHTEENTH RULE: None, or the refusal. `old`: the comment's text before an edit, or "" for a reply; None
    for a new comment. `path`: the layer's lineage, page first (read here when None)."""
    if key not in settled_files():
        return None
    ask = is_ask(text, old)
    if old is not None and not ask:
        return None
    if path is None:
        import figma_client
        try:
            path = figma_client.lineage(key, [_norm(node_id)], kids=False, tool="figma_post").get(_norm(node_id)) or []
        except Exception as e:  # noqa: BLE001 -- a rate limit or no network: refuse, never pass unread
            return f"REFUSED: could not read where {_norm(node_id)} sits ({type(e).__name__}), so THE EIGHTEENTH RULE did not run."
    reasons, why = settled({"asks": ask, "cites": cid, "node": _norm(node_id), "path": path})
    if why:
        return f"REFUSED: THE EIGHTEENTH RULE did not run: {why}."
    return ("REFUSED (THE EIGHTEENTH RULE): " + "; ".join(reasons) + ".") if reasons else None


def node_components(ix, node):
    """The main components a node is part of, from figma_family's index: each copy on its path (an
    instance's main, a main itself, a detached copy's main), or every variant of a component set.
    None when the index does not hold the node."""
    import figma_family
    n = figma_family.norm(node)
    v = ix.idx.get(n)
    if v is None:
        return None
    if v[figma_family.T] == "COMPONENT_SET":
        return {k for k in ix.kids.get(n, ()) if ix.idx[k][figma_family.T] == "COMPONENT"}
    return {k for a in ix.chain(n) for k in ix.comps_of(a)}


def edited_components(key, edited, ix):
    """({component: an edited node in it}, why not or None) for --edited. A node the index lacks is read live
    once (figma_family's add_live); one still unplaced is a why, since its component is unknown."""
    import figma_family
    lacking = sorted({figma_family.norm(e) for e in edited if node_components(ix, e) is None})
    if lacking:
        try:
            lacking = ix.add_live(key, lacking)
        except Exception as e:
            return {}, (f"the family index (built {ix.age_h():.1f} h ago) lacks {', '.join(lacking[:4])}, and the live "
                        f"read failed ({type(e).__name__}), so its component is unknown "
                        f"(python figma_family.py build {key})")
        if lacking:
            return {}, (f"{', '.join(lacking[:4])} is in neither the family index nor the file, so its component is "
                        "unknown: check the --edited ids")
    return {k: _norm(e) for e in edited for k in sorted(node_components(ix, e) or ())}, None


def fold_rank(key, edited, comments, me=None, notes=None, mode="auto", ix=None):
    """THE SIXTEENTH RULE's ranking: (ranked, ix, why). ranked is [(thread id, {shared components})], the owner's
    open FIX threads that touched a main component an --edited node is part of, best match first: most shared,
    then the thread most about them, then the newest. why says what stopped it, with ranked empty."""
    me = ((_me() if me is None else me) or "").strip().lower()
    if not me:
        return [], ix, "could not read the token owner's handle, so your open FIX threads are unknown"
    mine = [c for c in comments if not c.get("parent_id") and not c.get("resolved_at")
            and ((c.get("user") or {}).get("handle") or "").strip().lower() == me
            and (c.get("message") or "").startswith("FIX")]
    if not mine or not edited:      # no --edited is THE EIGHTH RULE's refusal
        return [], ix, None
    if ix is None:
        import figma_family
        ix, note = figma_family.load(key, mode=mode)
        if ix is None:
            return [], None, f"the family index did not load: {note} (python figma_family.py build {key})"
    want, why = edited_components(key, edited, ix)
    if why or not want:
        return [], ix, why
    notes = (_load(FIXNOTES) if notes is None else notes).get(key) or {}
    hits = []
    for c in mine:
        t, text = str(c["id"]), c.get("message") or ""
        touched = set((notes.get(t) or [0, []])[1]) | ids_in(text) | set(BARE_ID.findall(text))
        ks = set().union(*[node_components(ix, n) or set() for n in touched]) if touched else set()
        shared = ks & set(want)
        if shared:
            hits.append((len(shared), len(shared) / len(ks), c.get("created_at") or "", t, shared))
    return [(t, shared) for *_, t, shared in sorted(hits, key=lambda h: h[:4], reverse=True)], ix, None


def fold_rows(key, ranked, comments, edited, picture, causes=None, link=None, ix=None):
    """The ranked threads, five at most, and the batch `edit` item for the top one."""
    causes = (_load(CAUSES) if causes is None else causes).get(key) or {}
    url, rows = _thread_url(comments, link), []
    for t, shared in ranked[:5]:
        names = sorted({ix.name(k).strip()[:48] for k in shared})
        rows.append(f"  {url(t)} touched {'; '.join(names[:3])}{' ...' if len(names) > 3 else ''}")
    top = ranked[0][0]
    item = {"kind": "edit", "key": key, "cid": top, "text_file": "<its text, with this fix as its next numbered line>",
            "edited": [_norm(e) for e in edited], **({"cause": causes[top]} if causes.get(top) else {}),
            "pictures": pictures_of(picture)}
    return ("Your open FIX threads that touched a component this fix edits, best match first:\n" + "\n".join(rows)
            + (f"\n  and {len(ranked) - 5} more" if len(ranked) > 5 else "")
            + f"\nThe batch edit item for the top one, {top} (the ranking reads components, not subjects: read the "
              "thread first; combine pictures past 5 with figma_attach.py combine, then --replace):\n"
            + f"  {json.dumps(item)}")


def fold_gate(key, edited, comments, picture=None, me=None, notes=None, causes=None, mode="auto", link=None, ix=None):
    """THE SIXTEENTH RULE on a file not in figma.new_thread_files: None, or the refusal. `me`: the token owner's
    handle (read when None); `ix`: a loaded figma_family index (loaded with `mode` when None)."""
    ranked, ix, why = fold_rank(key, edited, comments, me, notes, mode, ix)
    if why:
        return f"REFUSED: THE SIXTEENTH RULE did not run: {why}."
    if not ranked:
        return None
    return (f"REFUSED: {len(ranked)} of your open FIX threads already touched a component this fix edits, so this "
            "goes into one of them as a numbered line, not a new thread.\n"
            + fold_rows(key, ranked, comments, edited, picture, causes, link, ix))


NEW_THREAD_WORDS = ask_rules.PLAIN_WORDS   # a --new-thread reason in plain words, not a token


def new_thread_head(in_batch):
    """The first line of THE SIXTEENTH RULE's refusal on a file in figma.new_thread_files, before any ranking."""
    return ("REFUSED: a batch cannot open a new FIX thread on this file (figma.new_thread_files). --new-thread goes "
            "on a command line of its own, where the permission prompt shows its reason, and a batch's prompt shows "
            "only its file name. Make this a batch edit item, or post it alone with `new ... --new-thread \"<reason>\"`."
            if in_batch else
            "REFUSED: a new FIX thread on this file (figma.new_thread_files) needs --new-thread \"<why none of your "
            "open FIX threads fits, in plain words>\" on this command line, so the reason shows in the permission "
            "prompt. Otherwise it goes into an open thread as a numbered line (a batch edit item).")


def new_thread_gate(key, edited, comments, reason=None, in_batch=False, picture=None, me=None, notes=None,
                    causes=None, mode="auto", link=None, ix=None, files=None):
    """THE SIXTEENTH RULE for a new FIX thread: None, or the refusal. On a file in figma.new_thread_files (`files`
    in the selftest) it takes --new-thread with a reason, on the command line only (`in_batch` refuses it whatever
    the reason); elsewhere, fold_gate."""
    if key not in (new_thread_files() if files is None else files):
        return fold_gate(key, edited, comments, picture, me, notes, causes, mode, link, ix)
    if reason is not None and not in_batch:
        if ask_rules.plain(reason) is None:   # the one plain-words rule every override flag takes
            return None
        return (f"REFUSED: --new-thread {reason!r} gives no reason. Say in plain words, {NEW_THREAD_WORDS} words or "
                "more, why none of your open FIX threads fits this fix.")
    head = new_thread_head(in_batch)
    ranked, ix, why = fold_rank(key, edited, comments, me, notes, mode, ix)
    if why:
        return f"{head}\nThe open threads could not be ranked by component: {why}."
    if not ranked:
        return (f"{head}\nNone of your open FIX threads touched a component this fix edits. Read them first "
                f"(figma_post.py cause {key} lists them with their causes).")
    return f"{head}\n" + fold_rows(key, ranked, comments, edited, picture, causes, link, ix)


def batch_new_threads(items, read=None, mode="auto", me=None, notes=None, files=None):
    """{item number: refusal} for each batch `new` FIX item on a file in figma.new_thread_files (THE SIXTEENTH
    RULE), each with its ranking. read(key) -> the file's comments; the token owner is read once, when an item
    needs it."""
    files = new_thread_files() if files is None else files
    read = read or (lambda key: _req(f"{API}/files/{key}/comments").get("comments", []))
    out, comments = {}, {}
    # SystemExit too: _req and figma_comments.get exit on an HTTP error, and this runs before batch()'s per-item
    # loop, so a stale token's 401 here would end the whole --check instead of refusing this item.
    failed = (Exception, SystemExit)
    for i, it in enumerate(items, 1):
        if not (it.get("kind") == "new" and it.get("key") in files and str(it.get("text", "")).startswith(DONE_PREFIX)):
            continue
        key = it["key"]
        if key not in comments:
            try:
                comments[key] = read(key)
            except failed as e:  # noqa: BLE001 -- the item is refused either way; only the ranking is lost
                comments[key] = e
        cs = comments[key]
        if isinstance(cs, failed):
            # No comments, so nothing to rank and no owner to read: new_thread_gate would ask /v1/me for nothing.
            why = str(cs) if isinstance(cs, SystemExit) else type(cs).__name__
            out[i] = new_thread_head(True) + f"\nThe comments could not be read ({why}), so the open threads are not ranked."
            continue
        if me is None:
            try:
                me = _me() or ""
            except failed:  # noqa: BLE001 -- no owner: fold_rank says it cannot rank
                me = ""
        out[i] = new_thread_gate(key, tuple(it.get("edited", ())), cs, None, True, it.get("picture"), me=me,
                                 notes=notes, mode=mode, files=files)
    return out


def batch_fold(items, mode="auto", files=None):
    """THE SIXTEENTH RULE within one batch, on files not in figma.new_thread_files (where batch_new_threads refuses
    every new FIX item): a refusal line for each new FIX item on a component an earlier new FIX item in the batch
    edited."""
    files = new_thread_files() if files is None else files
    news = [(i, it) for i, it in enumerate(items, 1) if it.get("kind") == "new" and it.get("edited")
            and it.get("key") not in files and str(it.get("text", "")).startswith(DONE_PREFIX)]
    if len(news) < 2:
        return []
    import figma_family
    out, first, loaded = [], {}, {}
    for i, it in news:
        key = it.get("key")
        if key not in loaded:
            loaded[key] = figma_family.load(key, mode=mode)
        ix, note = loaded[key]
        if ix is None:
            out.append(shown(key, f"  item {i} (new {it.get('node')}): REFUSED: THE SIXTEENTH RULE needs the family "
                                  f"index, and {note}."))
            continue
        want, why = edited_components(key, it["edited"], ix)
        if why:
            out.append(shown(key, f"  item {i} (new {it.get('node')}): REFUSED: THE SIXTEENTH RULE did not run: {why}."))
            continue
        earlier = sorted({first[(key, k)] for k in want if (key, k) in first})
        if earlier:
            names = sorted({ix.name(k).strip()[:48] for k in want if (key, k) in first})
            out.append(shown(key, f"  item {i} (new {it.get('node')}): REFUSED: item {earlier[0]} already starts a "
                                  f"thread on {'; '.join(names[:3])}; put this in it as a numbered line, its pictures "
                                  "combined (figma_attach.py combine) when they would pass 5."))
        for k in want:
            first.setdefault((key, k), i)
    return out


def replaced_gate(key, edited, comments, skip=(), own=None, link=None, notes=None):
    """None, or the refusal. See THE FIFTEENTH RULE. skip: threads read and separate, or that this batch
    edits or replies in; own: the thread this note goes into."""
    notes = (_load(FIXNOTES) if notes is None else notes).get(key) or {}
    live, mine = _open_roots(comments), {_norm(e) for e in edited}
    skip = {str(x) for x in skip} | ({str(own)} if own else set())
    url = _thread_url(comments, link)
    hits = sorted((t, sorted(mine & {_norm(e) for e in v[1]})) for t, v in notes.items()
                  if t in live and t not in skip and mine & {_norm(e) for e in v[1]})
    if not hits:
        return None
    rows = "\n".join(f"  {url(t)} also edited {', '.join(n[:3])}" for t, n in hits)
    return ("REFUSED: other open FIX notes of yours edited the same nodes, so one of them may now state an old "
            f"value:\n{rows}\nIn the same batch, give each a dated \"replaced by\" line (an edit item, or a reply "
            "when it has replies), or list it in separate if it is about something else.")


def _me():
    import figma_comments
    return os.environ.get("FIGMA_ME", "") or figma_comments.whoami()


def _link(key):
    import figma_comments
    return lambda c: figma_comments.permalink(key, c)


def shown(key, text):
    """text as printed: each line ending in the link of every node id on it in file `key`
    (figma_comments.linked), and of every work item #1234 when kit_config has ado_linked. Terminal lines
    only: the body a post sends, a reply's text and what the drafts file is matched against stay as
    written."""
    import figma_comments, kit_config
    text = figma_comments.linked(key, text) if key else str(text)
    ado_linked = getattr(kit_config, "ado_linked", None)
    return ado_linked(text) if ado_linked else text


def thread_link(key, thread, node):
    """The link that opens thread `thread`, pinned to `node` (None for a canvas pin), in file `key`."""
    import figma_comments
    return figma_comments.permalink(key, {"id": thread, "client_meta": {"node_id": _norm(node) if node else ""}})


def anchor(key, comment_id, comments=None):
    """The node a thread is pinned to, read from its root comment. None for a canvas pin."""
    if comments is None:
        comments = _req(f"{API}/files/{key}/comments").get("comments", [])
    by_id = {c["id"]: c for c in comments}
    c = by_id.get(str(comment_id))
    if c is None:
        sys.exit(f"comment {comment_id} is not in file {key}.")
    while c.get("parent_id") and c["parent_id"] in by_id:
        c = by_id[c["parent_id"]]
    return (c.get("client_meta") or {}).get("node_id")


def _req(url, body=None, method="GET"):
    """Through figma_client.py beside this file: paced with every other tool. A GET
    waits a 429 out; a POST or DELETE is retried after a 429 only, which Figma refuses before acting,
    so a comment is never posted twice. With figma.read_only set, a write exits before any call."""
    if method != "GET" and read_only():
        sys.exit(f"REFUSED: figma.read_only is set in the product-os config, so this copy of figma_post sends no "
                 f"{method}: the project's own tool owns its Figma writes. Nothing was sent.")
    import figma_client
    try:
        raw = figma_client.request(method, url, body, token=_tok(), tool="figma_post", timeout=90,
                                   **_comment_write(figma_client, method)).data.decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        import figma_comments
        stale, body = figma_comments.token_stale(e)
        sys.exit(stale or f"Figma {e.code}: {body[:400]}")


def _comment_write(client, method):
    """figma_client refuses a comment write (a post or a delete under files/KEY/comments) unless the caller
    passes comment_write=True, so only a tool that runs its checks first writes one. This file runs its gates
    before every write, so it passes the flag on each one. A client from before that change has no such keyword,
    so it gets none: this file works with either."""
    import inspect
    return {"comment_write": True} if method != "GET" and \
        "comment_write" in inspect.signature(client.request).parameters else {}


def known_handles(comments):
    """Everyone who has commented in the file, as Figma writes them ("Last, First")."""
    return {(c.get("user") or {}).get("handle") for c in comments} - {None}


def mention_gate(text, comments):
    """Refusal text or None. See THE THIRTEENTH RULE."""
    import figma_attach
    stray = figma_attach.stray_ats(text, known_handles(comments))
    if stray:
        return (f"REFUSED: {', '.join(stray)} is not the handle of anyone who has commented in this file, so no "
                "mention can be made from it. Write the person as @<Last, First>, exactly as Figma shows them "
                "on their comments, or drop the @.")
    return None


# THE SEVENTEENTH RULE: a comment id, bare (not part of a node id, a size or a date) or a figma.com link's #id,
# and a link that names its file.
COMMENT_ID = re.compile(r"(?<![\w.:/-])(\d{9,11})(?![\w:-])")
COMMENT_URL = re.compile(r"figma\.com/(?:design|board|file)/([A-Za-z0-9]{22})/[^\s)#]*#(\d{9,11})(?!\d)")
# The share of a text's words an open comment of the owner's must hold to be printed as a lead.
LEAD_FLOOR = 0.3
LEAD_SKIP = set("about after again also because been before being between both could does done each from have "
                "here into just like make more most much only other over same should some such than that their "
                "them then there these they this those through under very want what when where which while will "
                "with would your yours page pages frame frames".split())


def own_open_hits(key, text, comments, me, read=None):
    """THE SEVENTEENTH RULE's finding: [(file key, root comment)] for each open root comment of `me` (a handle)
    that `text` links, a reply counting as its thread's root, once each. A bare id is looked up in `comments`,
    file `key`'s; a figma.com link naming another file in read(that key). Raises when such a file can't be read."""
    me = (me or "").strip().lower()
    pairs = {(k, i) for k, i in COMMENT_URL.findall(text or "")}
    ids = {m.group(1) for m in COMMENT_ID.finditer(text or "")} | {i for k, i in pairs if k == key}
    files, hits = {key: comments}, []
    for k in sorted({k for k, _ in pairs if k != key}):
        files[k] = (read or (lambda f: _req(f"{API}/files/{f}/comments").get("comments", [])))(k)
    want = [(key, i) for i in sorted(ids)] + sorted((k, i) for k, i in pairs if k != key)
    for k, i in want:
        root = _root_of(files.get(k) or [], i)
        if (root and not root.get("parent_id") and not root.get("resolved_at")
                and ((root.get("user") or {}).get("handle") or "").strip().lower() == me
                and all(str(r["id"]) != str(root["id"]) for _, r in hits)):
            hits.append((k, root))
    return hits


def own_open_refusal(key, text, comments, me, separate=(), read=None, link=None):
    """None, or THE SEVENTEENTH RULE's refusal for a new thread whose text (with its drafts-file block) links an
    open root comment of the token owner's. separate: the roots --separate says this is not about."""
    if not COMMENT_ID.search(text or ""):
        return None
    if not (me or "").strip():
        return ("REFUSED: could not tell whose token this is (FIGMA_ME is unset and /v1/me failed), so whether this "
                "new thread links an open comment of the token owner's is unknown (THE SEVENTEENTH RULE).")
    try:
        hits = [(k, r) for k, r in own_open_hits(key, text, comments, me, read) if str(r["id"]) not in set(separate)]
    except Exception as e:  # noqa: BLE001 -- a file that could not be read refuses, never passes
        return f"REFUSED: a comment this new thread links could not be checked ({type(e).__name__}: {e})."
    if not hits:
        return None
    rows = [f"  {r['id']} ({(r.get('user') or {}).get('handle', '?')}): "
            f"\"{' '.join((r.get('message') or '').split())[:90]}\""
            + (f"\n    {link(r)}" if link and k == key else "") for k, r in hits]
    first_key, first = hits[0]
    return (f"REFUSED: this new thread links {len(hits)} open comment(s) of your own (THE SEVENTEENTH RULE):\n"
            + "\n".join(rows)
            + "\nThat comment is where this kind of thing already sits. Make the fix where it is yours to make, then "
              "add it to that comment as a FIX (done in Figma) line:\n"
              f"  python figma_attach.py edit {first_key} {first['id']} --text-file <the comment with the new line>\n"
              "or a batch edit item. If this thread is about something else, re-run with\n"
              f"  --separate {','.join(str(r['id']) for _, r in hits)} \"<why>\"")


def own_open_check(key, text, read=None, me=None):
    """[root id] of THE SEVENTEENTH RULE's hits in `text`, file `key`, read now: the same check for a draft
    still in the drafts file. Raises when the comments or the token owner can't be read."""
    read = read or (lambda f: _req(f"{API}/files/{f}/comments").get("comments", []))
    me = _me() if me is None else me
    if not (me or "").strip():
        raise RuntimeError("could not tell whose token this is (FIGMA_ME is unset and /v1/me failed)")
    return [str(r["id"]) for _, r in own_open_hits(key, text, read(key), me, read)]


def own_open_leads(text, comments, me, n=2):
    """THE SEVENTEENTH RULE's print-only lead: [(share, root)] for the owner's open non-FIX root comments that
    hold LEAD_FLOOR or more of the text's words, best first, at most n."""
    words = lambda t: {w for w in re.findall(r"[a-z][a-z'-]{3,}", (t or "").lower()) if w not in LEAD_SKIP}  # noqa: E731
    me, mine = (me or "").strip().lower(), words(text)
    if not me or not mine:
        return []
    scored = [(len(mine & words(c.get("message"))) / len(mine), c) for c in comments
              if not c.get("parent_id") and not c.get("resolved_at") and not (c.get("message") or "").startswith("FIX")
              and ((c.get("user") or {}).get("handle") or "").strip().lower() == me]
    return sorted([x for x in scored if x[0] >= LEAD_FLOOR], key=lambda x: -x[0])[:n]


def own_open_gate(key, node_id, text, separate, comments, notes, me=None, read=None):
    """THE SEVENTEENTH RULE in check_new: the refusal for the text and its drafts-file block(s), or None. notes
    gets the print-only lead, and a line when the drafts file could not be read."""
    try:
        block = "\n\n".join(_drafts_blocks(text, node_id))
    except (OSError, AttributeError) as e:
        block = ""
        notes.append(f"  own-open: the drafts file was not read ({type(e).__name__}: {e}); the text's own links "
                     "are checked")
    me = _me() if me is None else me
    refused = own_open_refusal(key, f"{text}\n\n{block}", comments, me, separate, read, _link(key))
    if not refused:
        notes += [f"  lead: your open comment {r['id']} holds {s:.2f} of this text's words: "
                  f"\"{' '.join((r.get('message') or '').split())[:80]}\"; if this is its kind, edit it instead "
                  f"({_link(key)(r)})" for s, r in own_open_leads(text, comments, me)]
    return refused


def check_reply(key, parent_id, text, own_last_ok=False, edited=(), evidence=None, multi_ok=False,
                repost_ok=False, picture=None, separate=(), also=(), cause=None, asks_cid=None):
    """(refusal or None, plan): every gate for a reply, and what post() sends. Posts nothing. also: the
    threads this batch edits or replies in (THE FIFTEENTH RULE)."""
    cs = _req(f"{API}/files/{key}/comments").get("comments", [])
    node = anchor(key, parent_id, cs)
    root = _root_of(cs, parent_id)
    refused = (settled_gate(key, node, text, asks_cid, old="") or question_gate(text, multi_ok) or _drafts_wrapped(text)
               or (None if repost_ok or root is None else repost_gate(key, f"thread {root['id']}"))
               or (None if own_last_ok else own_last_gate(key, parent_id, cs, _me(), _link(key)))
               or gate(key, node) or drift_gate(key, node) or mention_gate(text, cs))
    notes = []
    if not refused and text.startswith(DONE_PREFIX):
        refused, notes = fix_line_gate(key, cs, root, node, edited, cause, tuple(separate) + tuple(also),
                                       own=(root or {}).get("id", str(parent_id)), link=_link(key))
    if not refused:
        refused, text = picture_step(text, evidence, picture)
    import figma_attach
    return refused, {"kind": "reply", "key": key, "parent": str(parent_id), "node": node, "text": text,
                     "root": (root or {}).get("id", str(parent_id)), "edited": edited, "picture": picture,
                     "notes": notes, "mentions": figma_attach.handles_in(text, known_handles(cs)),
                     "body": {"message": text, "comment_id": str(parent_id)}}


def check_new(key, node_id, text, separate=(), edited=(), evidence=None, pin_ok=False, multi_ok=False,
              repost_ok=False, picture=None, cause=None, new_cause=False, also=(), new_thread=None, in_batch=False,
              asks_cid=None):
    """(refusal or None, plan): every gate for a new thread, and what post() sends. Posts nothing. also:
    the threads this batch edits or replies in (THE FIFTEENTH RULE)."""
    docs = {}

    def fetch(k, n):  # drift_gate and pin_spot read the same frame: one call
        if n not in docs:
            docs[n] = fetch_node(k, n)
        return docs[n]
    refused = (settled_gate(key, node_id, text, asks_cid) or pin_gate(node_id) or question_gate(text, multi_ok)
               or _drafts_wrapped(text) or _drafts_cut(node_id, key)
               or (None if repost_ok else repost_gate(key, node_id))
               or search_gate(key) or gate(key, node_id) or drift_gate(key, node_id, fetch))
    notes, offset, cs = [], None, []
    if not refused:
        frame = _stamp(_load_reads()[key][_norm(node_id)])[1]
        offset, refused, pin_note = pin_spot(fetch(key, frame), node_id, pin_ok)
        notes += [pin_note] if pin_note else []
    if not refused and text.startswith(DONE_PREFIX):
        refused, placed = placement_gate(key, node_id, edited)
        notes += placed
    if not refused:
        refused, text = picture_step(text, evidence, picture)
    if not refused:
        cs = _req(f"{API}/files/{key}/comments").get("comments", [])
        refused = (family_gate(key, node_id, separate, cs, link=_link(key))
                   or dup_gate(key, node_id, separate, cs, link=_link(key))
                   or mention_gate(text, cs)
                   or own_open_gate(key, node_id, text, separate, cs, notes))
        if not refused and text.startswith(DONE_PREFIX):
            refused = (cause_gate(key, cause, cs, separate, new_cause, link=_link(key))
                       or new_thread_gate(key, edited, cs, new_thread, in_batch, picture, link=_link(key))
                       or replaced_gate(key, edited, cs, tuple(separate) + tuple(also), link=_link(key)))
    import figma_attach
    return refused, {"kind": "new", "key": key, "node": node_id, "text": text, "edited": edited, "cause": cause,
                     "picture": picture, "notes": notes,
                     "mentions": figma_attach.handles_in(text, known_handles(cs)),
                     "body": {"message": text, "client_meta": {"node_id": node_id, "node_offset": offset}}}


def post(plan):
    """Send a checked plan. Returns (new comment id or None, the browser jobs it leaves: its
    pictures first, then its mentions, for figma_attach.run_jobs)."""
    key, text = plan["key"], plan["text"]
    if plan["notes"]:
        print(shown(key, "\n".join(plan["notes"])))
    d = _req(f"{API}/files/{key}/comments", plan["body"], "POST")
    cid = d.get("id")
    if plan["kind"] == "reply":
        at = f"  {thread_link(key, plan['root'], plan['node'])}" if cid else ""
        print(shown(key, f"  replied in {plan['parent']} -> new comment {cid} ({len(text)} chars){at}"))
    else:
        at = f"  {thread_link(key, cid, plan['node'])}" if cid else ""
        print(shown(key, f"  posted on {plan['node']} -> comment {cid} ({len(text)} chars){at}"))
    if not cid:
        return None, []
    gone = (_drafts_remove(text, comment_id=plan["parent"], node_id=plan["node"])
            if plan["kind"] == "reply" else _drafts_remove(text, node_id=plan["node"]))
    if gone:
        print(shown(key, gone))
    jobs = []
    thread = plan["root"] if plan["kind"] == "reply" else cid
    if text.startswith(DONE_PREFIX):
        record_fixnote(key, thread, plan["edited"], plan["node"])
        if plan["kind"] == "new" and plan.get("cause"):
            record_cause(key, thread, plan["cause"])
    # Any --picture goes in, not only a FIX note's.
    if plan.get("picture"):
        jobs.append({"key": key, "cid": cid, "pictures": pictures_of(plan["picture"]),
                     "thread": thread, "node": plan["node"], "picture": plan["picture"]})
    if plan["mentions"]:
        jobs.append({"key": key, "cid": cid, "mentions": plan["mentions"], "thread": thread, "node": plan["node"]})
    return cid, jobs


def run_after(jobs, runner=None):
    """Every picture and mention the posts left, in ONE browser (figma_attach.run_jobs). Prints the
    manual step for each that did not go in. Returns the exit code."""
    if not jobs:
        return 0
    if runner is None:
        try:
            import figma_attach
            runner = figma_attach.run_jobs
        except ImportError as e:
            print(f"  DID NOT ATTACH OR MENTION: figma_attach.py is not beside figma_post.py ({e}).")
            runner = None
    keep = ("key", "cid", "pictures", "mentions", "text", "replace")
    code, codes = runner([{k: v for k, v in j.items() if k in keep} for j in jobs]) if runner else (2, [2] * len(jobs))
    for j, own in zip(jobs, codes):     # each job by its own code: a comment can carry a picture and a mention
        if own == 0:
            if j.get("fix"):
                record_fixnote(j["key"], *j["fix"])
                print(f"  thread {j['fix'][0]}: the edit is in, placement was checked before it, stamped.")
            continue
        if "text" in j:
            print(f"  EDIT NOT MADE on {j['cid']}: run figma_attach.py edit {j['key']} {j['cid']} --text-file <txt>"
                  + (" <pictures>" if j.get("pictures") else "") + "; the draft stays in the drafts file.")
        elif j.get("pictures"):
            print(attach_note(j["key"], j["thread"], j["node"], j["picture"]))
        if j.get("mentions"):
            print(f"  MENTION NOT MADE on {j['cid']}: run figma_attach.py mention {j['key']} {j['cid']} "
                  f"(it holds {', '.join('@' + h for h in j['mentions'])} as plain text, which notifies nobody).")
    return code


def reply(key, parent_id, text, own_last_ok=False, edited=(), evidence=None, multi_ok=False,
          repost_ok=False, picture=None, separate=(), cause=None, asks_cid=None):
    refused, plan = check_reply(key, parent_id, text, own_last_ok, edited, evidence, multi_ok, repost_ok, picture,
                                separate, cause=cause, asks_cid=asks_cid)
    if refused:
        sys.exit(shown(key, refused))
    _, jobs = post(plan)
    run_after(jobs)


def new(key, node_id, text, separate=(), edited=(), evidence=None, pin_ok=False, multi_ok=False,
        repost_ok=False, picture=None, cause=None, new_cause=False, new_thread=None, asks_cid=None):
    refused, plan = check_new(key, node_id, text, separate, edited, evidence, pin_ok, multi_ok, repost_ok, picture,
                              cause, new_cause, new_thread=new_thread, asks_cid=asks_cid)
    if refused:
        sys.exit(shown(key, refused))
    _, jobs = post(plan)
    run_after(jobs)


def _check_item(it, extra_separate=()):
    """(refusal or None, plan) for one batch item. An edit item is checked by figma_attach, from REST
    alone: no browser."""
    kind = it.get("kind")
    flags = dict(evidence=None, multi_ok=it.get("multi_ok", False), repost_ok=it.get("repost_ok", False),
                 picture=it.get("picture"), edited=tuple(it.get("edited", ())))
    also = tuple(it.get("_also", ()))      # batch() sets it: the threads the batch edits or replies in
    if kind == "new":
        return check_new(it["key"], it["node"], it["text"],
                         separate=tuple(it.get("separate", ())) + tuple(extra_separate),
                         pin_ok=it.get("pin_ok", False), cause=it.get("cause"),
                         new_cause=it.get("new_cause", False), also=also, in_batch=True, asks_cid=it.get("asks"),
                         **flags)
    if kind == "reply":
        return check_reply(it["key"], it["parent"], it["text"], own_last_ok=it.get("own_last_ok", False),
                           separate=tuple(it.get("separate", ())), also=also, cause=it.get("cause"),
                           asks_cid=it.get("asks"), **flags)
    if kind == "edit":
        import figma_attach
        comments, me = figma_attach._read(it["key"])
        if comments is None:    # me holds why: a stale token's says "token stale"
            return f"DID NOT RUN: the Figma API failed{': ' + me if me else ''}.", None
        mine, root = next((c for c in comments if str(c["id"]) == str(it["cid"])), {}), _root_of(comments, it["cid"])
        node = ((root or {}).get("client_meta") or {}).get("node_id") or ""
        notes, fix = [], bool(root) and it["text"].startswith(DONE_PREFIX) and [root["id"], flags["edited"], node or None]
        refused = settled_gate(it["key"], node, it["text"], it.get("asks"), old=mine.get("message") or "")
        if fix and not refused:
            refused, notes = fix_line_gate(it["key"], comments, root, node, flags["edited"], it.get("cause"),
                                           tuple(it.get("separate", ())) + also, link=_link(it["key"]))
            refused = refused or picture_gate(it["text"], posting=False)
        if refused:
            return refused, None
        job = {"key": it["key"], "cid": str(it["cid"]), "text": it["text"], "pictures": it.get("pictures", []),
               "replace": it.get("replace", False), **({"fix": fix} if fix else {})}
        return (figma_attach.job_refusal(job, comments, me.get("id"), figma_attach._stamps()),
                {"kind": "edit", "job": job, "notes": notes})
    return f"REFUSED: unknown kind {kind!r}; use new, reply or edit.", None


def batch(path, check_only=False, checker=None, poster=None, runner=None):
    """THE BATCH. See its section in the header. Returns the exit code."""
    items = json.load(open(path, encoding="utf-8"))
    checker, poster = checker or _check_item, poster or post
    for it in items:
        if "text_file" in it:
            it["text"] = open(it["text_file"], encoding="utf-8").read()
    # The threads this batch edits or replies in, for THE FIFTEENTH RULE.
    touched = {}
    for it in items:
        t = it.get("cid") if it.get("kind") == "edit" else it.get("parent") if it.get("kind") == "reply" else None
        if t:
            touched.setdefault(it.get("key"), set()).add(str(t))
    for it in items:
        it["_also"] = sorted(touched.get(it.get("key"), ()))
    # 1. Every gate on every item, with nothing posted. THE FOURTEENTH RULE within the batch first:
    #    a second new thread with a cause goes into the first, its pictures combined past 5.
    refusals, last = [], {}
    for i, it in enumerate(items, 1):   # an override in a batch file: the prompt never shows its reason
        for k in BATCH_OVERRIDES:
            if it.get(k):
                refusals.append(shown(it.get("key"), f"  item {i} ({it.get('kind')} "
                                      f"{it.get('node') or it.get('parent') or it.get('cid')}): "
                                      + ask_rules.override("--" + k.replace("_", "-"), None, in_batch=True)))
    for i, it in enumerate(items, 1):
        if it.get("kind") == "new" and it.get("cause") and str(it.get("text", "")).startswith(DONE_PREFIX):
            k = (it.get("key"), it["cause"])
            if k in last:
                refusals.append(shown(it.get("key"), f"  item {i} (new {it.get('node')}): REFUSED: item {last[k]} "
                                      f"already starts a thread about {it['cause']!r}; put this in it as a numbered "
                                      "line, its pictures combined (figma_attach.py combine) when they would pass 5."))
            last.setdefault(k, i)
    files = new_thread_files()
    refusals += batch_fold(items, files=files)   # THE SIXTEENTH RULE within the batch: one thread per component
    no_new = batch_new_threads(items, files=files) if any(it.get("key") in files and it.get("kind") == "new"
                                                          for it in items) else {}
    refusals += [shown(items[i - 1].get("key"), f"  item {i} (new {items[i - 1].get('node')}): {r}")
                 for i, r in no_new.items()]
    for i, it in enumerate(items, 1):
        if i in no_new:     # refused above, with its ranking; its other gates would read Figma for nothing
            continue
        try:
            refused, plan = checker(it)
        except SystemExit as e:
            refused, plan = str(e), None
        for n in (plan or {}).get("notes") or []:
            print(shown(it.get("key"), f"  item {i}: {n}"))
        if refused:
            refusals.append(shown(it.get("key"), f"  item {i} ({it.get('kind')} "
                                  f"{it.get('node') or it.get('parent') or it.get('cid')}): {refused}"))
    if refusals:
        print("\n".join(refusals))
        print(f"REFUSED: {len(refusals)} of {len(items)} item(s) refused; nothing posted, no browser opened.")
        return 1
    if check_only:
        print(f"CHECKED: all {len(items)} item(s) pass every gate; nothing posted (--check).")
        return 0
    # 2. Post in order. Each item is checked again just before it posts, with the threads this batch
    #    has already started counted as read and separate (they were approved together).
    jobs, started, posted = [], {}, 0
    for i, it in enumerate(items, 1):
        try:
            refused, plan = checker(it, started.get(it["key"], ()))
            if refused:
                print(shown(it.get("key"), f"STOPPED before item {i}: {refused}"))
                break
            if plan["kind"] == "edit":
                jobs.append(plan["job"])
                continue
            cid, its_jobs = poster(plan)
        except SystemExit as e:
            print(shown(it.get("key"), f"STOPPED at item {i}: {e}"))
            break
        if not cid:
            print(f"STOPPED at item {i}: the post returned no comment id.")
            break
        posted += 1
        jobs += its_jobs
        if plan["kind"] == "new":
            started[it["key"]] = started.get(it["key"], ()) + (cid,)
    # 3. One browser for every picture, mention and edit the batch holds.
    code = run_after(jobs, runner) if jobs else 0
    n_edits = sum(1 for j in jobs if "text" in j)
    print(f"BATCH: {posted} of {len(items) - n_edits} post(s) sent, {len(jobs)} browser job(s) in one browser, exit {code}.")
    return code if posted + n_edits == len(items) else 2


def fixnote(key, comment_id, text, edited=(), evidence=None, cause=None, separate=()):
    """THE EIGHTH, NINTH and FIFTEENTH RULES for a FIX comment edited with figma_attach.py edit, then the
    FIXNOTES stamp. cause: the kind of fix the edited line is (THE FOURTEENTH RULE); separate: the older
    notes on the same nodes that hold their "replaced by" line, or are about something else. Posts
    nothing."""
    if not text.startswith(DONE_PREFIX):
        sys.exit(f"REFUSED: the text does not start with \"{DONE_PREFIX}\", so it is not a FIX note.")
    cs = _req(f"{API}/files/{key}/comments").get("comments", [])
    root = _root_of(cs, comment_id)
    if root is None:
        sys.exit(f"REFUSED: comment {comment_id} is not in file {key}.")
    node = (root.get("client_meta") or {}).get("node_id")
    refused, notes = fix_line_gate(key, cs, root, node, edited, cause, separate, link=_link(key))
    refused = refused or picture_gate(text, evidence, posting=False)
    if refused:
        sys.exit(shown(key, refused))
    if notes:
        print(shown(key, "\n".join(notes)))
    record_fixnote(key, root["id"], edited, node)
    print(f"  thread {root['id']} on {node}: placement checked and stamped. If the comment does not "
          f"hold this text yet, put it there with figma_attach.py edit.  {thread_link(key, root['id'], node)}")


def cause(key, thread_id=None, slug=None):
    """THE FOURTEENTH RULE's record by hand: tag an open FIX thread of yours with its cause, or list the
    open ones. Writes CAUSES only; nothing in Figma."""
    cs = _req(f"{API}/files/{key}/comments").get("comments", [])
    if thread_id is None:
        live = open_causes(key, cs)
        for c, ts in sorted(live.items()):
            print(f"{c}: " + ", ".join(_thread_url(cs, _link(key))(t) for t in ts))
        print(f"{sum(len(v) for v in live.values())} open thread(s) under {len(live)} cause(s) in {key}.")
        return
    root = next((c for c in cs if str(c["id"]) == str(thread_id)), None)
    if root is None or root.get("parent_id"):
        sys.exit(f"REFUSED: {thread_id} is not a thread root in {key}.")
    if not (root.get("message") or "").startswith(DONE_PREFIX):
        sys.exit(f"REFUSED: thread {thread_id} is not a FIX note.")
    if not CAUSE_RE.match(slug or ""):
        sys.exit(f"REFUSED: {slug!r} is not a slug: lower case, digits and hyphens.")
    record_cause(key, thread_id, slug)
    print(f"  thread {thread_id} is about {slug!r}{'' if root.get('resolved_at') else ' (open)'}.")


def delete(key, cid):
    cs = _req(f"{API}/files/{key}/comments").get("comments", [])
    refused = delete_gate(key, cid, cs, _me())
    if refused:
        sys.exit(shown(key, refused))
    _req(f"{API}/files/{key}/comments/{cid}", None, "DELETE")
    on = record_delete(key, cid, cs)
    print(shown(key, f"  deleted comment {cid}"
                + (f". A post {('in ' if on.startswith('thread') else 'on ') + on} in the next {FRESH_MIN} minutes "
                   "needs --repost-ok \"<why>\": to reword, edit with figma_attach.py edit; to re-pin, use the Figma "
                   "UI." if on else "")))


def pop_flag(argv, flag):
    """(the value after flag or None, argv without flag and its value). A flag given last has no value."""
    if flag not in argv:
        return None, list(argv)
    i = argv.index(flag)
    return (argv[i + 1] if i + 1 < len(argv) else None), list(argv[:i]) + list(argv[i + 2:])


def pop_overrides(argv):
    """({flag: its reason, or None when none follows}, argv without the reasons). Each flag in OK_FLAGS
    goes off with its reason; --separate keeps its ids for parse_flags and gives up the reason after them;
    --new-thread goes off with its reason."""
    argv, got = list(argv), {}
    take = lambda k: argv[k] if k < len(argv) and not argv[k].startswith("--") else None
    for flag in OK_FLAGS + ("--new-thread",):
        if flag in argv:
            i = argv.index(flag)
            got[flag] = take(i + 1)
            del argv[i:i + (2 if got[flag] is not None else 1)]
    if "--separate" in argv:
        i = argv.index("--separate")
        got["--separate"] = take(i + 2)
        if got["--separate"] is not None:
            del argv[i + 2]
    return got, argv


def parse_flags(argv):
    """(positional args, --own-last-ok given, --separate ids, --edited ids, --evidence id or None,
    --picture file or None, --cause slug or None). The ids split on commas or spaces. Every flag in OK_FLAGS is dropped from
    the args; the caller reads the others from argv. --evidence is parsed so picture_gate can refuse it."""
    args = [x for x in argv if x not in OK_FLAGS]
    lists = {}
    for flag in ("--separate", "--edited", "--evidence"):
        lists[flag] = ()
        if flag in args:
            i = args.index(flag)
            lists[flag] = tuple(x for x in " ".join(args[i + 1:i + 2]).replace(",", " ").split())
            del args[i:i + 2]
    picture = cause = None
    if "--picture" in args:
        i = args.index("--picture")
        picture = (args[i + 1:i + 2] or [None])[0]
        del args[i:i + 2]
    if "--cause" in args:
        i = args.index("--cause")
        cause = (args[i + 1:i + 2] or [None])[0]
        del args[i:i + 2]
    evidence = lists["--evidence"][0] if lists["--evidence"] else None
    return args, "--own-last-ok" in argv, lists["--separate"], lists["--edited"], evidence, picture, cause


# THE SEVENTEENTH RULE's known-bad cases: a drafts-file block whose notes, not its quote, link the owner's open
# comment on the same kind of thing, and a text that links the owner's open comment itself. {key} is the file.
OWN_DRAFT = (
    "### Hero photo: a larger original or a wider crop — NEW on \"Background image\" [`4100:20001`]"
    "(https://www.figma.com/design/{key}/File?node-id=4100-20001) · Not sent. The crop takes 1800x1200 of the fill "
    "for the 1440x900 frame, so a 2x hero has no real pixels behind it. The same kind for the CTA photos sits in "
    "your own open comment [1900000201](https://www.figma.com/design/{key}/File?node-id=4100-30001#1900000201), with "
    "no reply.\n\n"
    "`python figma_post.py new {key} 4100:20001 \"<text below>\"`, after `figma_comments.py frame` on the node.\n\n"
    "> Q: Can the hero get a larger original of its photo, or a wider crop? Its crop\n"
    "> holds 1,800 px of the photo across the screen, and a sharp hero on a 2x laptop needs 2,880.\n"
    ">\n"
    "> A larger original keeps today's framing if it is at least 4,800 px wide and sits in the same\n"
    "> crop. A wider crop works with the photo we have, but it zooms the hero out about 1.6 times.\n")
OWN_ASK = (
    "One more scrim ask, and it is the same decision as the hero one rather than a separate one.\n\nThe footer band "
    "darkens its photo 25%, which puts the band heading under the contrast floor on two pages. Could the footer band "
    "move to 40% as well? One answer covers both: https://www.figma.com/design/{key}/File?node-id=4100-40001"
    "#1900000202")


def settled_selftest(case, tmp):
    """THE EIGHTEENTH RULE's planted cases: whether a text asks, the gate on a listed file with a stand-in record,
    the command it runs, and the CLI's and the batch's --asks reaching the gate."""
    global SETTLED
    import figma_client
    seen = []
    last = lambda: seen[-1] if seen else {}
    kept = (globals()["settled_files"], SETTLED, figma_client.lineage)
    globals()["settled_files"] = lambda: {"SF"}
    figma_client.lineage = lambda key, ids, **kw: {ids[0]: [{"id": "0:1", "type": "CANVAS"}, {"id": ids[0]}]}
    try:
        case("is_ask: a new comment that is not a FIX note asks, worded as a statement or not",
             None if is_ask("The hero gap reads 24.") and is_ask("Q: which gap?") else "no", False)
        case("is_ask: a new FIX note asks nothing", True if is_ask("FIX (done in Figma): the gap is 24.") else None, False)
        case("is_ask: a reply that adds no question asks nothing", True if is_ask("Done, thanks.", "") else None, False)
        case("is_ask: an edit that adds a Q line asks", None if is_ask("Old note.\nQ: which frame?", "Old note.") else "no",
             False)
        case("is_ask: an edit that leaves its question as it was asks nothing",
             True if is_ask("Which frame is current? Noted.", "Which frame is current?") else None, False)
        SETTLED = lambda req: seen.append(req) or (["planted: the record settles it"], None)
        case("a file not in figma.settled_files is not judged", settled_gate("K", "1:2", "Q: which?", "c-1"), False)
        got = settled_gate("SF", "1-2", "Q: which?", "c-1")
        case("an ask on a listed file the record settles is refused, with the command's reason",
             got if got and got.startswith("REFUSED (THE EIGHTEENTH RULE): planted") else None, True)
        case("... and the command got the cite, the asks flag, the layer and its lineage",
             None if last() == {"asks": True, "cites": "c-1", "node": "1:2",
                                  "path": [{"id": "0:1", "type": "CANVAS"}, {"id": "1:2"}]} else last(), False)
        n = len(seen)
        case("a reply that asks nothing is not judged, and the command does not run",
             settled_gate("SF", "1:2", "Done, thanks.", None, old="") or (len(seen) != n or None), False)
        got = settled_gate("SF", "1:2", "FIX (done in Figma): the gap is 24.")
        case("a new FIX note still goes to the command (a superseded frame refuses any comment), with asks false",
             None if got and last()["asks"] is False else (got or "passed"), False)
        SETTLED = lambda req: ([], None)
        case("an ask the record leaves a question posts", settled_gate("SF", "1:2", "Q: which?", "c-1"), False)
        SETTLED = lambda req: ([], "figma.settled_cmd is not set")
        got = settled_gate("SF", "1:2", "Q: which?", "c-1")
        case("a command that did not run refuses: the rule never passes unread",
             got if got and "did not run" in got else None, True)
        case("ask_refusal: a text that does not ask is None", ask_refusal("Done, thanks.", None, ""), False)
        try:
            got = ask_refusal("Q: which?", "c-1")
        except SettledNotRun as e:
            got = str(e)
        else:
            got = None
        case("ask_refusal: a command that did not run raises SettledNotRun, so it is never read as a pass or a refusal",
             got if got and "did not run" in got else None, True)
        SETTLED = lambda req: seen.append(req) or (["planted reason"], None)
        got = ask_refusal("Q: which?", "c-1")
        case("ask_refusal: an ask the record settles gives the reason, with no layer",
             got if got == "planted reason" and last()["node"] is None else None, True)
        got = check_new("SF", "1:2", "Q: which gap?", asks_cid="c-9", repost_ok=True)[0] or ""
        case("check_new runs the rule first, with its --asks cite",
             got if got.startswith("REFUSED (THE EIGHTEENTH RULE)") and last()["cites"] == "c-9" else None, True)
        case("--asks comes off the command line with its id",
             None if pop_flag(["new", "K", "1:2", "t", "--asks", "c-9"], "--asks") == ("c-9", ["new", "K", "1:2", "t"])
             else "no", False)
        import figma_attach as _attach
        kept_read = _attach._read
        _attach._read = lambda key, md=False: ([{"id": "e1", "message": "Old note.",
                                                  "client_meta": {"node_id": "1:2"}}], {"id": "me"})
        try:
            got = _check_item({"kind": "edit", "key": "SF", "cid": "e1", "text": "Old note.\nQ: which frame?",
                               "asks": "c-3"})
        finally:
            _attach._read = kept_read
        case("a batch edit that adds an ask is judged against the comment's text, with the item's \"asks\"",
             got[0] if (got[0] or "").startswith("REFUSED (THE EIGHTEENTH RULE)") and last()["cites"] == "c-3"
             else None, True)
        # The command itself: a planted script, as figma.settled_cmd runs it.
        SETTLED = None
        script = os.path.join(tmp, "settled_cmd.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write("import json, sys\nreq = json.load(sys.stdin)\n"
                    "if req.get('cites') == 'boom':\n    print('no record here'); sys.exit(2)\n"
                    "if req.get('cites') == 'c-open':\n    sys.exit(0)\n"
                    "print('the record settles ' + str(req.get('cites'))); sys.exit(1)\n")
        import kit_config
        kept_get = kit_config.get
        cmd = f"{sys.executable} {script}"
        kit_config.get = lambda *keys, **kw: cmd if keys == ("figma", "settled_cmd") else kept_get(*keys, **kw)
        try:
            r = [settled({"asks": True, "cites": c, "node": None, "path": None}) for c in ("c-done", "c-open", "boom")]
            kit_config.get = lambda *keys, **kw: None if keys == ("figma", "settled_cmd") else kept_get(*keys, **kw)
            unset = settled({"asks": True, "cites": "c-done", "node": None, "path": None})
        finally:
            kit_config.get = kept_get
        case("settled_cmd: exit 1 gives its reasons", None if r[0] == (["the record settles c-done"], None) else r[0], False)
        case("settled_cmd: exit 0 gives none", None if r[1] == ([], None) else r[1], False)
        case("settled_cmd: exit 2 is did-not-run, with its last line",
             None if r[2][0] == [] and "exited 2: no record here" in (r[2][1] or "") else r[2], False)
        case("settled_cmd unset is did-not-run", None if unset[0] == [] and "not set" in (unset[1] or "") else unset, False)
    finally:
        globals()["settled_files"], SETTLED, figma_client.lineage = kept


def own_open_selftest(case, tmp):
    """THE SEVENTEENTH RULE: the two known-bad cases, the known-good ones, its lift, and its wiring into check_new."""
    import types
    import drafts_store as _ds
    me, key = "Owner, Token", "PK" + "0" * 18 + "PK"
    root = lambda cid, **kw: {"id": cid, "parent_id": "", "resolved_at": None, "user": {"handle": me},  # noqa: E731
                              "message": "About the CTA band (Footer) photos, which look soft on a few pages.", **kw}
    cta, draft = [root("1900000201")], OWN_DRAFT.format(key=key)
    quote = _ds.text_of(_ds.blocks(draft)[0]["quote"])
    got = own_open_refusal(key, draft, cta, me)
    case("17th known-bad: a draft whose notes link the owner's open comment is refused, naming the edit of it",
         None if got and f"figma_attach.py edit {key} 1900000201" in got and "FIX (done in Figma)" in got
         else got or "passed", False)
    got = own_open_refusal(key, OWN_ASK.format(key=key), [root("1900000202", message="One ask about the hero "
                                                                                    "backgrounds.")], me)
    case("17th known-bad: a text linking the owner's open comment is refused, naming it",
         None if got and f"edit {key} 1900000202" in got else got or "passed", False)
    reply = {"id": "1900000301", "parent_id": "1900000201", "resolved_at": None, "user": {"handle": "Design, A."},
             "message": "Looking."}
    got = own_open_refusal(key, f"Same as https://www.figma.com/design/{key}/W?node-id=1-2#1900000301", cta + [reply], me)
    case("17th: a link to a reply in the owner's open thread is refused, naming the thread's root",
         None if got and f"edit {key} 1900000201" in got and "1900000301 (" not in got else got or "passed", False)
    case("17th known-good: the draft citing a resolved thread of the owner's passes",
         own_open_refusal(key, draft, [root("1900000201", resolved_at="2026-10-26T04:34:12Z")], me), False)
    case("17th known-good: the draft citing a teammate's open comment passes",
         own_open_refusal(key, draft, [root("1900000201", user={"handle": "Design, A."})], me), False)
    case("17th: --separate 1900000201 \"<why>\" lifts it for that root",
         own_open_refusal(key, draft, cta, me, separate=["1900000201"]), False)
    got = own_open_refusal(key, draft, cta, "")
    case("17th: a token owner that can't be told refuses",
         None if got and "whose token" in got else got or "passed", False)
    other = "KB" + "0" * 18 + "KB"
    far = f"See https://www.figma.com/board/{other}/B?node-id=1-2#1900000401"
    got = own_open_refusal(key, far, [], me, read=lambda k: [root("1900000401")] if k == other else [])
    case("17th: a link naming another file is checked in that file's comments",
         None if got and f"edit {other} 1900000401" in got else got or "passed", False)
    got = own_open_refusal(key, far, [], me, read=lambda k: (_ for _ in ()).throw(OSError("down")))
    case("17th: ... and refuses when that file can't be read", None if got and "could not be checked" in got
         else got or "passed", False)
    ids = [m.group(1) for m in COMMENT_ID.finditer("node 4100:20001, 4096x2731, 2026-11-03, version 2400000000000000001, "
                                                    "node-id=4100-30001, #1234, I1100:2001;3300:4001")]
    case("17th: node ids, sizes, dates, a file version and a work item id are not comment ids", None if not ids else ids,
         False)
    case("17th: a text that links no comment id passes without asking who the owner is",
         own_open_refusal(key, quote, cta, ""), False)
    fix = root("1900000501", message="FIX (done in Figma): crop photos larger original wider")
    near = root("1900000201", message="Q: could these photos get a larger original or a wider crop? The crop holds "
                                      "too few pixels for a sharp hero on a 2x laptop screen.")
    leads = own_open_leads(quote, [near, fix, root("1900000601", message="Footer link colour on the phone."),
                                   root("1900000701", message=near["message"], resolved_at="2026-10-01T00:00:00Z")], me)
    case("17th lead, print-only: the owner's open non-FIX comment sharing the text's words is listed; a FIX note, an "
         "unrelated one and a resolved one are not",
         None if [r["id"] for _, r in leads] == ["1900000201"] and leads[0][0] >= LEAD_FLOOR else leads, False)
    # Wired into check_new: every other gate stubbed to pass, the draft's quote posted, its block in the drafts file.
    g, node = globals(), "4100:20001"
    names = ("pin_gate", "question_gate", "_drafts_wrapped", "_drafts_cut", "search_gate", "gate", "drift_gate",
             "_load_reads", "_stamp", "fetch_node", "pin_spot", "picture_step", "family_gate", "dup_gate",
             "mention_gate", "_req", "_me", "_link", "_drafts_blocks", "_drafts")
    saved = {n: g[n] for n in names + ("own_open_gate",)}
    try:
        g.update(pin_gate=lambda *a, **k: None, question_gate=lambda *a, **k: None, _drafts_wrapped=lambda *a: None,
                 _drafts_cut=lambda *a: None, search_gate=lambda *a, **k: None, gate=lambda *a, **k: None,
                 drift_gate=lambda *a, **k: None, _load_reads=lambda: {key: {_norm(node): 0}},
                 _stamp=lambda v: (0, node), fetch_node=lambda k, n: {},
                 pin_spot=lambda doc, n, ok: ({"x": 0, "y": 0}, None, None), picture_step=lambda t, e, p: (None, t),
                 family_gate=lambda *a, **k: None, dup_gate=lambda *a, **k: None, mention_gate=lambda *a, **k: None,
                 _req=lambda url, body=None, method="GET": {"comments": cta}, _me=lambda: me,
                 _link=lambda k: (lambda c: f"https://x#{c['id']}"),
                 _drafts_blocks=lambda text, n: [draft] if (text, n) == (quote, node) else [])
        wired = check_new(key, node, quote, repost_ok=True)[0]
        alone = check_new(key, node, "Q: Is this hero photo the final one, or a placeholder?", repost_ok=True)[0]
        # A drafts_store with no post_blocks: the text's own links are still checked, and the notes say so.
        g["_drafts_blocks"] = saved["_drafts_blocks"]
        g["_drafts"] = lambda: types.SimpleNamespace(drafts_path=lambda: os.path.join(tmp, "drafts.md"))
        refused, plan = check_new(key, node, quote, repost_ok=True)
        old_store = (refused, [n for n in plan["notes"] if "own-open" in n])
        g["_drafts_blocks"] = lambda text, n: [draft] if (text, n) == (quote, node) else []
        g["own_open_gate"] = lambda *a, **k: None
        out = check_new(key, node, quote, repost_ok=True)[0]
    finally:
        g.update(saved)
    case("17th wiring: check_new refuses the quote by its drafts-file block's link, which the quote lacks",
         None if wired and "SEVENTEENTH" in wired else wired or "passed", False)
    case("17th wiring: ... a text no block matches is checked alone, and passes", alone, False)
    case("17th wiring: ... a drafts_store with no post_blocks checks the text alone and says the file was not read",
         None if old_store[0] is None and old_store[1] and "AttributeError" in old_store[1][0] else old_store, False)
    case("17th wiring: ... and with the rule taken out of check_new, the same post passes", out, False)


def selftest():
    """Planted cases against a temp stamp file and a stub Figma. No network, no post. figma.read_only is pinned
    off, so the planted posts run whatever the machine's config says; its own cases set it."""
    real = globals()["read_only"]
    globals()["read_only"] = lambda: False
    try:
        return _selftest(real)
    finally:
        globals()["read_only"] = real


def _selftest(real_read_only):
    global READS, SEARCHES, FIXNOTES, DELETES, CAUSES
    saved, tmp = (READS, SEARCHES), tempfile.mkdtemp()
    CAUSES = os.path.join(tmp, "causes.json")    # no case may write the real one
    atexit.register(shutil.rmtree, tmp, True)
    READS, SEARCHES = os.path.join(tmp, "reads.json"), os.path.join(tmp, "searches.json")
    band = {"id": "1:1", "type": "FRAME", "itemSpacing": 12,
            "children": [{"id": "1:2", "type": "TEXT", "characters": "Governance out of box"}]}
    moved = json.loads(json.dumps(band))
    moved["itemSpacing"] = 20
    figma = {"1:1": band}
    fetch = lambda key, nid: figma.get(_norm(nid))
    results = []
    # The one Figma call a case made: _me() -> figma_comments.whoami(), GET /v1/me, for a case that passes no
    # owner. With no token or a stale one that call exits the process (figma_auth's "No Figma token found", or
    # figma_comments.get's sys.exit on a 401), which whoami's `except Exception` does not catch, so the selftest
    # stopped partway. A planted owner keeps every case offline; FIGMA_ME still wins, as in _me().
    import figma_comments as _fc
    saved_whoami, _fc.whoami = _fc.whoami, lambda: "Owner"
    # Printed lines carry links (shown), and a link names its file's kind: the planted keys are design files,
    # so no case asks Figma for a file's name.
    planted_meta = [k for k in ("K", "KS", "K2", "W", "PK", "PK" + "0" * 18 + "PK") if k not in _fc._META]
    for k in planted_meta:
        _fc._META[k] = ("design", "File")

    def case(name, got, want_refused):
        ok = (got is not None) == want_refused
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        got: {got!r}"))
    try:
        record_reads("K", ["1:1", "1:2"], root="1:1", root_hash=node_hash(band))
        case("frame unchanged, anchor is the frame: posts",
             gate("K", "1:1") or drift_gate("K", "1:1", fetch), False)
        case("frame unchanged, anchor is a node printed inside it: posts",
             gate("K", "1:2") or drift_gate("K", "1:2", fetch), False)
        figma["1:1"] = moved
        case("design moved the gap 12 -> 20 after the read: refused", drift_gate("K", "1:2", fetch), True)
        del figma["1:1"]
        case("frame deleted after the read: refused", drift_gate("K", "1:1", fetch), True)
        figma["1:1"] = band
        _save(READS, {"K": {"1:1": time.time()}})
        case("fresh stamp from before the hash (bare epoch): refused",
             gate("K", "1:1") or drift_gate("K", "1:1", fetch), True)
        record_reads("K", ["1:1"], now=time.time() - 31 * 60, root="1:1", root_hash=node_hash(band))
        case("read 31 minutes ago, frame unchanged: refused", gate("K", "1:1"), True)
        case("node never printed: refused", gate("K", "9:9"), True)

        # THE FOURTH RULE, on figma_family's planted file: B/h is the heading in instance B; open
        # t1 sits on the heading in instance A on another page, open t3 on a detached copy's.
        import figma_family
        fam_saved, figma_family.CACHE = figma_family.CACHE, os.path.join(tmp, "family")
        fam_net = figma_family._get, figma_family._lineage
        try:
            doc, cms = figma_family._planted()
            figma_family.plant("K", doc)
            fg = lambda node, sep=(), key="K": family_gate(key, node, sep, cms, mode="cache")
            case("same layer as open threads on two other copies: refused", fg("B/h"), True)
            case("both listed in --separate: posts", fg("B/h", ["t1", "t3"]), False)
            case("one of the two listed: refused", fg("B/h", ["t1"]), True)
            case("a layer no thread is on: posts", fg("B/3"), False)
            case("no family index for the file: refused", fg("B/h", key="K2"), True)

            # THE SIXTEENTH RULE on the same file: A and B are instances of main M, D a detached copy
            # of it, SB another component. f1 is the owner's open FIX thread, stamped as editing A's heading.
            figma_family._get = figma_family._lineage = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
            fix = lambda i, msg="FIX (done in Figma): the heading sits at 10.", **kw: dict(
                {"id": i, "message": msg, "created_at": "2000-01-05T00:00:00Z", "user": {"handle": "Owner"}}, **kw)
            st = {"K": {"f1": [0, ["A/h"], "A"]}}
            fo = lambda edited, cm, notes=st, me="Owner", key="K": fold_gate(key, edited, cm, "p.jpg,q.jpg", me=me,
                                                                            notes=notes, causes={}, mode="cache")
            got = fo(["B/3"], [fix("f1")]) or ""
            case("16th: a new FIX note on a component the owner's open FIX thread touched: refused, naming it and its "
                 "edit item", None if "f1 touched footer" in got and '"kind": "edit", "key": "K", "cid": "f1"' in got
                 and '"pictures": ["p.jpg", "q.jpg"]' in got else got or "passed", False)
            case("16th: ... the detached copy's edit too", fo(["D/2"], [fix("f1")]), True)
            case("16th: a FIX note on a component no open thread of the owner's touched: posts (known good)",
                 fo(["SB"], [fix("f1")]), False)
            case("16th: a thread with no stamp that links a copy in its text counts",
                 fo(["B/h"], [fix("f2", "FIX (done in Figma): the heading. https://www.figma.com/design/K/W?node-id=D")],
                    notes={}), True)
            case("16th: the owner's resolved thread, someone else's thread, and a Q thread take nothing",
                 fo(["B/3"], [fix("f1", resolved_at="2000-01-06T00:00:00Z"), fix("f1b", user={"handle": "Design, A."}),
                              fix("f1c", "Q: should the heading sit at 10?")],
                    notes={"K": {k: [0, ["A/h"], "A"] for k in ("f1", "f1b", "f1c")}}), False)
            case("16th: an --edited node the index lacks, with no live read: refused", fo(["9:9"], [fix("f1")]), True)
            offline = figma_family._get, figma_family._lineage
            figma_family._lineage, figma_family._get = (lambda *a, **k: {}), (lambda *a, **k: {"nodes": {}})
            case("16th: ... and one the live read does not find either: refused", fo(["9:9"], [fix("f1")]), True)
            figma_family._get, figma_family._lineage = offline
            case("16th: no family index for the file: refused", fo(["B/3"], [fix("f1")], key="K2"), True)
            case("16th: a token owner it cannot read: refused", fo(["SB"], [fix("f1")], me=""), True)
            # A component set stands for its variants: a thread citing set S touched V1 and V2 alike.
            figma_family.plant("KS", {"document": {"id": "0:0", "type": "DOCUMENT", "children": [
                {"id": "P", "type": "CANVAS", "name": "Page", "children": [
                    {"id": "S", "type": "COMPONENT_SET", "name": "card", "children": [
                        {"id": "V1", "type": "COMPONENT", "name": "size=s"}, {"id": "V2", "type": "COMPONENT", "name": "size=l"}]},
                    {"id": "F", "type": "FRAME", "name": "page", "children": [
                        {"id": "I1", "type": "INSTANCE", "name": "card", "componentId": "V2"},
                        {"id": "1001:2002", "type": "INSTANCE", "name": "card", "componentId": "V2"},
                        {"id": "10:30", "type": "INSTANCE", "name": "card", "componentId": "V1"}]}]}]},
                "components": {"V1": {"name": "size=s", "componentSetId": "S"}, "V2": {"name": "size=l", "componentSetId": "S"}},
                "componentSets": {"S": {"name": "card"}}})
            case("16th: a thread that cites a component set touched each of its variants",
                 fo(["I1"], [fix("f3", "FIX (done in Figma): cards. https://www.figma.com/design/KS/W?node-id=S")],
                    notes={}, key="KS"), True)
            case("16th: a node id written bare in a thread's text counts too",
                 fo(["V2"], [fix("f4", "FIX (done in Figma): the large card, `1001:2002`.")], notes={}, key="KS"), True)
            case("16th: ... but not a time, with under 3 digits a side",
                 fo(["V1"], [fix("f4", "FIX (done in Figma): checked at 10:30.")], notes={}, key="KS"), False)
            # A file in figma.new_thread_files: --new-thread with a reason, on the command line only. The same
            # planted file, under the key "W".
            figma_family.plant("W", doc)
            nt = lambda edited, cm, reason=None, in_batch=False, me="Owner": new_thread_gate(
                "W", edited, cm, reason, in_batch, "p.jpg", me=me, notes={"W": st["K"]}, causes={}, mode="cache",
                files={"W"})
            got = nt(["B/3"], [fix("f1"), fix("f0", user={"handle": "Design, A."})]) or ""
            case("16th listed file: a new FIX thread without --new-thread: refused, ranking f1 first with its edit item",
                 None if "needs --new-thread" in got and "f1 touched footer" in got and '"cid": "f1"' in got
                 else got or "passed", False)
            case("16th listed file: ... refused too on a component no open thread touched, pointing at the threads",
                 None if "None of your open FIX threads" in (nt(["SB"], [fix("f1")]) or "") else "passed", False)
            case("16th listed file: ... and when it cannot rank, saying why", None if "could not be ranked" in
                 (nt(["B/3"], [fix("f1")], me="") or "") else "passed", False)
            case("16th listed file: with --new-thread and a reason in plain words: posts (known good)",
                 nt(["B/3"], [fix("f1")], "the footer thread is about its height, this is its links"), False)
            case("16th listed file: --new-thread with one word is no reason: refused", nt(["B/3"], [fix("f1")], "new"),
                 True)
            case("16th listed file: --new-thread with three ids is no reason either (ask_rules.plain)",
                 nt(["B/3"], [fix("f1")], "1111111111 2222222222 33333"), True)
            case("16th listed file: a batch item is refused even with a reason, since its prompt shows only the file",
                 nt(["SB"], [fix("f1")], "the footer thread is about its height", in_batch=True), True)
            case("16th: a file not listed takes no --new-thread: the component match decides, passing a new component",
                 new_thread_gate("K", ["SB"], [fix("f1")], None, False, me="Owner", notes=st, causes={}, mode="cache",
                                 files={"W"}), False)
            case("16th: ... and refusing a touched one, --new-thread and its reason or not",
                 new_thread_gate("K", ["B/3"], [fix("f1")], "the footer thread is about its height", False, me="Owner",
                                 notes=st, causes={}, mode="cache", files={"W"}), True)
            items = [{"kind": "new", "key": "W", "node": "n1", "text": "FIX (done in Figma): x.", "edited": ["B/3"]},
                     {"kind": "edit", "key": "W", "cid": "f1", "text": "FIX (done in Figma): x.\n\n2. y."},
                     {"kind": "new", "key": "W", "node": "n2", "text": "Q: which?"},
                     {"kind": "new", "key": "K", "node": "n3", "text": "FIX (done in Figma): z.", "edited": ["SB"]}]
            got = batch_new_threads(items, read=lambda key: [fix("f1")], mode="cache", me="Owner",
                                    notes={"W": st["K"]}, files={"W"})
            case("16th listed file: in a batch, the new FIX item is refused with its ranking; the edit, the Q and "
                 "another file's item are not", None if list(got) == [1] and "f1 touched footer" in got[1] else got,
                 False)
            got = batch_new_threads(items[:1], read=lambda key: (_ for _ in ()).throw(OSError("down")), mode="cache",
                                    me="Owner", files={"W"})
            case("16th listed file: ... refused when the comments cannot be read, saying the ranking is lost",
                 None if "not ranked" in got.get(1, "") else got, False)
            import contextlib, io
            g, env_me, env_cfg = globals(), os.environ.get("FIGMA_ME"), os.environ.get("PRODUCT_OS_CONFIG")
            cfg = os.path.join(tmp, "workbench.json")
            json.dump({"figma": {"new_thread_files": ["W"]}}, open(cfg, "w", encoding="utf-8"))
            saved_req, os.environ["FIGMA_ME"], os.environ["PRODUCT_OS_CONFIG"] = g["_req"], "Owner", cfg
            g["_req"] = lambda url, body=None, method="GET": {"comments": [fix("f1")]}
            try:
                bp, seen, buf = os.path.join(tmp, "new-thread.json"), [], io.StringIO()
                json.dump(items, open(bp, "w", encoding="utf-8"))
                with contextlib.redirect_stdout(buf):
                    out = batch(bp, check_only=True,
                                checker=lambda it, extra=(): seen.append(it.get("node") or it.get("cid")) or (None, {}))
                case("16th: batch() reads figma.new_thread_files, refuses the batch on its new FIX item there and still "
                     "checks the other items",
                     None if out == 1 and "item 1 (new n1): REFUSED: a batch cannot" in buf.getvalue()
                     and seen == ["f1", "n2", "n3"] else (out, seen), False)
                for k in BATCH_OVERRIDES:
                    over = [{"kind": "new", "key": "K", "node": "n9", "text": "Q: which?", k: ["t1"] if k == "separate"
                             else True}]
                    json.dump(over, open(bp, "w", encoding="utf-8"))
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        out = batch(bp, check_only=True, checker=lambda it, extra=(): (None, {}))
                    case(f"a batch item carrying {k!r} refuses the batch, naming its flag",
                         None if out == 1 and f"--{k.replace('_', '-')} can't come from a batch file" in buf.getvalue()
                         else (out, buf.getvalue()[-200:]), False)
            finally:
                g["_req"] = saved_req
                for name, was in (("FIGMA_ME", env_me), ("PRODUCT_OS_CONFIG", env_cfg)):
                    if was is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = was
            # The same rule inside one batch, on a file not listed.
            nf = lambda node, edited: {"kind": "new", "key": "K", "node": node, "text": "FIX (done in Figma): x.",
                                       "edited": edited, "cause": node}
            got = batch_fold([nf("n1", ["A/h"]), nf("n2", ["SB"]), nf("n3", ["B/3"])], mode="cache", files=set())
            case("16th: in one batch, a second new FIX item on a component an earlier one edited: refused, naming it",
                 None if len(got) == 1 and "item 3" in got[0] and "item 1 already" in got[0] else got, False)
            case("16th: ... and new FIX items on different components pass",
                 batch_fold([nf("n1", ["A/h"]), nf("n2", ["SB"])], mode="cache", files=set()) or None, False)
        finally:
            figma_family.CACHE = fam_saved
            figma_family._get, figma_family._lineage = fam_net

        # THE FIFTH RULE: whose comment is newest in the thread.
        me = "Owner, Token"
        th = [{"id": "r1", "created_at": "2026-10-05T10:00", "user": {"handle": me}, "message": "root"},
              {"id": "c2", "parent_id": "r1", "created_at": "2026-10-05T11:00", "user": {"handle": "Design, A."},
               "message": "answer"}]
        case("someone else answered last: replies", own_last_gate("K", "r1", th, me), False)
        th.append({"id": "c3", "parent_id": "r1", "created_at": "2026-10-05T12:00", "user": {"handle": me},
                   "message": "my follow-up"})
        case("own comment newest, asked by its root id: refused", own_last_gate("K", "r1", th, me), True)
        case("own comment newest, asked by a reply id: refused", own_last_gate("K", "c2", th, me), True)
        case("token owner unknown: refused", own_last_gate("K", "r1", th, ""), True)

        # THE SIXTH RULE, on the same thread: r1 is the owner's root, c2 someone else's reply, c3 the
        # owner's reply.
        case("delete own reply, nothing under it: deletes", delete_gate("K", "c3", th, me), False)
        case("delete own thread root with replies: refused", delete_gate("K", "r1", th, me), True)
        case("delete someone else's comment: refused", delete_gate("K", "c2", th, me), True)
        case("delete an id not in the file: refused", delete_gate("K", "zz", th, me), True)
        case("delete with the token owner unknown: refused", delete_gate("K", "c3", th, ""), True)

        # THE SEVENTH RULE. Frame 5:1 holds band 5:2 (box 100-300) with text 5:3; 5:9 is elsewhere.
        paths = {"5:2": [("0:1", None), ("5:1", {"x": 0, "y": 0, "width": 1000, "height": 1000}),
                         ("5:2", {"x": 100, "y": 100, "width": 200, "height": 200})]}
        loc = lambda key, ids: (paths, {"5:2": {"5:3", "I5:4;7:7"}})
        pin = lambda cid, node, msg="x", off=None, **kw: dict(
            {"id": cid, "created_at": "2026-10-05T10:00", "user": {"handle": "Design, A."},
             "message": msg, "client_meta": {"node_id": node, **({"node_offset": off} if off else {})}},
            **kw)
        dg = lambda cs, sep=(): dup_gate("K", "5:2", sep, cs, loc=loc)
        case("open thread pinned to the node: refused", dg([pin("d1", "5:2")]), True)
        case("open thread pinned to a layer inside it: refused", dg([pin("d1", "5:3")]), True)
        case("pinned to the parent frame at an offset inside the node: refused",
             dg([pin("d1", "5:1", off={"x": 150, "y": 150})]), True)
        case("pinned to the parent frame at an offset outside the node: posts",
             dg([pin("d1", "5:1", off={"x": 900, "y": 900})]), False)
        for form in ("5-2", "5%3A2", "I5-4%3B7-7"):
            case(f"a reply elsewhere links to it as node-id={form}: refused",
                 dg([pin("d1", "5:9"), dict(pin("d2", None, f"see ?node-id={form}#1"), parent_id="d1")]),
                 True)
        case("a link to another node: posts", dg([pin("d1", "5:9", "see ?node-id=5-9")]), False)
        case("resolved thread on the node: posts",
             dg([pin("d1", "5:2", resolved_at="2026-10-06T10:00")]), False)
        case("open thread listed in --separate: posts", dg([pin("d1", "5:2")], ["d1"]), False)
        case("node not in the file: refused", dup_gate("K", "8:8", (), [], loc=loc), True)

        def broken(key, ids):
            raise SystemExit("Figma 500")
        case("location read fails: refused", dup_gate("K", "5:2", (), [], loc=broken), True)

        # THE EIGHTH RULE. Components page: set S > variant V > label L, and component C2. Page
        # V1: frame PF > instance I, and frame PF2 > text PT.
        nd = lambda i, t, *kids: {"id": i, "type": t, "name": i, "children": list(kids)}
        doc = nd("0:0", "DOCUMENT",
                 nd("c:0", "CANVAS", nd("S", "COMPONENT_SET", nd("V", "COMPONENT", nd("L", "TEXT"))),
                    nd("C2", "COMPONENT", nd("C2t", "TEXT"))),
                 nd("p:0", "CANVAS", nd("PF", "FRAME", nd("I", "INSTANCE")), nd("PF2", "FRAME", nd("PT", "TEXT"))))
        pg = lambda anc, ed: placement_gate("K", anc, ed, doc=doc)
        case("edited a component's layer, comment on a page frame: refused", pg("PF", ["L"])[0], True)
        for anc in ("S", "V", "L"):
            case(f"edited a component's layer, comment on {anc} inside it: posts", pg(anc, ["L"])[0], False)
        case("edited a page frame's layer, comment on that frame: posts", pg("PF2", ["PT"])[0], False)
        case("edited an instance layer on a page (I<inst>;<main>): posts", pg("PF", ["II;9:9"])[0], False)
        case("no --edited: refused", pg("S", [])[0], True)
        case("comment pinned to the canvas: refused", pg(None, ["L"])[0], True)
        case("edited id not in the file: refused", pg("S", ["Z"])[0], True)
        got = pg("S", ["L", "C2t"])
        case("edited two components, comment on one: posts with a note naming the other",
             None if got[0] is None and any("C2" in n for n in got[1]) else got, False)
        case("edited a component and a page layer, comment on the page: refused", pg("PF2", ["L", "PT"])[0], True)
        # THE FOURTEENTH RULE's thread takes its kind's line: r9 carries menu-order, pinned on page frame PF.
        open9 = [{"id": "r9", "client_meta": {"node_id": "PF"}}]
        fp = lambda claimed: fix_placement("K", open9, open9[0], "PF", ["L"], claimed, doc=doc,
                                           causes={"K": {"r9": "menu-order"}})
        got = fp("menu-order")
        case("a line of the thread's own cause, editing a component's layer, on a page-frame thread: passes, "
             "the note naming the component and the cause",
             None if got[0] is None and any("menu-order" in n for n in got[1]) and any(" S " in n for n in got[1])
             else got, False)
        got = [fp(c)[0] for c in (None, "hero-scrim")]
        case("...with no --cause, or another kind's: refused, asking for one thread and naming the thread's cause",
             got if all(g and "one thread" in g and "--cause menu-order" in g for g in got) else None, True)
        fl = lambda notes: fix_line_gate("K", open9 + [{"id": "r8"}], open9[0], "PF", ["L"], "menu-order", doc=doc,
                                         causes={"K": {"r9": "menu-order"}}, fixnotes=notes)
        got = fl({"K": {"r8": [0, ["L"], "S"]}})
        case("an edit's FIX line on its cause thread: another open note that edited the same layer still needs its "
             "replaced-by line (THE FIFTEENTH RULE at batch --check, before the edit)",
             got[0] if got[0] and "r8" in got[0] else None, True)
        case("...and with no other note on that layer it passes with the placement note",
             None if fl({"K": {}})[0] is None and fl({"K": {}})[1] else fl({"K": {}}), False)

        fix_saved, FIXNOTES = FIXNOTES, os.path.join(tmp, "fixnotes.json")
        try:
            record_fixnote("K", "r1", ["L"], "S")
            got = _load(FIXNOTES).get("K", {}).get("r1")
            case("a passing fix note is stamped with its edits and anchor",
                 None if got and got[1:] == [["L"], "S"] else got, False)
            record_fixnote("K", "r1", ["C2t"], "S")
            got = _load(FIXNOTES).get("K", {}).get("r1")
            case("a second line's stamp keeps the first line's edits (THE FIFTEENTH RULE still sees them)",
                 None if got and got[1:] == [["C2t", "L"], "S"] else got, False)
        finally:
            FIXNOTES = fix_saved

        # THE NINTH RULE: the picture goes in the comment, attached in the Figma UI. A real picture
        # file, a file that is not one, and the texts FIX notes are written in.
        pic = os.path.join(tmp, "sheet.jpg")
        open(pic, "wb").write(b"\xff\xd8\xff")
        fix = "FIX (done in Figma): the crop. It was cut at the chin. Please confirm and resolve."
        linked = fix + "\n\nBefore and after: https://www.figma.com/design/K/File?node-id=1234-5678"
        got = picture_gate(fix)
        case("FIX post with no --picture: refused, saying how to make it and where it goes",
             got if got and "--picture" in got and "figma_evidence.py" in got and "Figma UI" in got else None, True)
        case("FIX post with a picture file: posts", picture_gate(fix, picture=pic), False)
        case("a --picture that is not a .jpg or .png file: refused", picture_gate(fix, picture=pic + ".txt"), True)
        got = picture_gate(fix, evidence="1234:5678", picture=pic)
        case("--evidence: refused, saying the picture goes in the comment",
             got if got and "not supported" in got and "in the comment" in got else None, True)
        case("text that links its picture: refused", picture_gate(linked, picture=pic), True)
        named = fix + "\n\nBefore and after: `evidence/hero/phone-title-before-after.jpg`"
        case("text that names its picture's file after the label: refused", picture_gate(named, picture=pic), True)
        case("fixnote text that names its picture's file: refused", picture_gate(named, posting=False), True)
        case("text ending in the bare label: posts", picture_gate(fix + "\n\nBefore and after:", picture=pic), False)
        case("the label, then the next paragraph on its own line: posts",
             picture_gate(fix + "\n\nBefore and after:\n\nFigma before, Figma after, the build.", picture=pic), False)
        case("two pictures, comma-separated: posts", picture_gate(fix, picture=f"{pic},{pic}"), False)
        case("two pictures, one not a picture file: refused", picture_gate(fix, picture=f"{pic},{pic}.txt"), True)
        case("six pictures: refused", picture_gate(fix, picture=",".join([pic] * 6)), True)
        import io, contextlib
        case("fixnote text that links its picture: refused", picture_gate(linked, posting=False), True)
        case("fixnote text ending in the bare label, the picture attached by hand: stamps",
             picture_gate(fix + "\n\nBefore and after:", posting=False), False)
        case("fixnote of a note that links nothing: no picture asked for", picture_gate(fix, posting=False), False)
        got = with_label(fix)
        case("a posted FIX note ends in 'Before and after:', where the picture is attached",
             None if got == fix + "\n\nBefore and after:" else got, False)
        case("a note that ends in the label already is left as it is",
             None if with_label(got) == got else with_label(got), False)

        got = parse_flags(["new", "K", "1:2", "the text", "--separate", "t1, t3"])
        case("--separate after the text is parsed off it",
             None if got == (["new", "K", "1:2", "the text"], False, ("t1", "t3"), (), None, None, None) else got, False)
        got = parse_flags(["reply", "--own-last-ok", "K", "r1", "the text"])
        case("--own-last-ok anywhere is parsed off",
             None if got == (["reply", "K", "r1", "the text"], True, (), (), None, None, None) else got, False)
        got = parse_flags(["fixnote", "K", "r1", "--edited", "1:2,3:4", "the text"])
        case("--edited before the text is parsed off it",
             None if got == (["fixnote", "K", "r1", "the text"], False, (), ("1:2", "3:4"), None, None, None) else got, False)
        got = parse_flags(["new", "K", "1:2", "--evidence", "1234-5679", "the text", "--edited", "9:9"])
        case("--evidence is still parsed off, so the gate can refuse it",
             None if got == (["new", "K", "1:2", "the text"], False, (), ("9:9",), "1234-5679", None, None) else got, False)
        got = parse_flags(["new", "K", "1:2", "the text", "--picture", "/x/sheet.jpg", "--edited", "9:9"])
        case("--picture is parsed off, one file",
             None if got == (["new", "K", "1:2", "the text"], False, (), ("9:9",), None, "/x/sheet.jpg", None) else got, False)
        case("a pin on a layer inside an instance is refused", pin_gate("I4321:8765;1:2"), True)
        case("the refusal names the instance to pin on",
             None if "4321:8765" in (pin_gate("I4321:8765;1:2") or "") else "no instance named", False)
        case("a pin on a plain node passes", pin_gate("4321:8765"), False)
        case("a pin given with hyphens passes", pin_gate("4321-8765"), False)

        # THE TENTH RULE. Frame R: band B at 100,100 with a full-width heading H on its top edge and a
        # body BD; band T tiled by halves T1 and T2; band S with a background SB of its own box; band
        # HB under a hidden cover HC; A under S2, a painted layer clipped away by its frame C; A2 under
        # a painted layer O drawn after it, and under a transparent frame TF; L, drawn under a painted
        # layer U that comes before it.
        bx = lambda i, x, y, w, h, t="FRAME", **kw: dict(
            {"id": i, "type": t, "name": i, "absoluteBoundingBox": {"x": x, "y": y, "width": w, "height": h},
             "fills": [{"type": "SOLID"}]}, **kw)
        R = bx("R", 0, 0, 3000, 3000, children=[
            bx("B", 100, 100, 1000, 500, children=[bx("H", 100, 100, 1000, 100, "TEXT"), bx("BD", 200, 250, 800, 300)]),
            bx("T", 0, 700, 1000, 500, children=[bx("T1", 0, 700, 500, 500), bx("T2", 500, 700, 500, 500)]),
            bx("S", 0, 1300, 400, 400, children=[bx("SB", 0, 1300, 400, 400, "RECTANGLE")]),
            bx("HB", 500, 1300, 400, 400, children=[bx("HC", 520, 1320, 300, 300, visible=False)]),
            bx("A", 0, 1800, 400, 400),
            bx("C", 500, 1800, 400, 400, clipsContent=True, children=[bx("S2", 0, 1800, 900, 400, "RECTANGLE")]),
            bx("A2", 0, 2300, 400, 400), bx("TF", 0, 2300, 400, 400, fills=[]), bx("O", 0, 2300, 400, 400),
            bx("U", 1000, 2300, 400, 400), bx("L", 1000, 2300, 400, 400, "TEXT")])
        ps = lambda anc, ok=False, doc=R: pin_spot(doc, anc, ok)
        off, ref, _ = ps("B")
        hit = lambda o, *boxes: o and any(_has(b, 100 + o["x"], 100 + o["y"]) for b in boxes)
        case("the band's corner sits on its heading: the pin moves to a point no smaller layer covers",
             ref or (None if off and off != {"x": 0, "y": 0} and 0 < off["x"] < 1000 and 0 < off["y"] < 500
                     and not hit(off, {"x": 100, "y": 100, "width": 1000, "height": 100},
                                 {"x": 200, "y": 250, "width": 800, "height": 300}) else off), False)
        case("a band its two halves tile entirely: refused, naming the layer at the centre",
             (lambda r: r if r and "T1" in r or r and "T2" in r else None)(ps("T")[1]), True)
        got = ps("T", True)
        case("the same band with --pin-ok: pins at its centre",
             None if got[1] is None and got[0] == {"x": 500, "y": 250} else got, False)
        row = bx("K", 0, 0, 1216, 520, children=[bx(f"K{i}", i * 416, 0, 384, 520) for i in range(3)])
        got = ps("K", doc=row)
        case("three full-height cards 32px apart: the pin lands in the first gap",
             None if got[0] and 384 < got[0]["x"] < 416 else got, False)
        case("a child with the band's own box is not a smaller layer: posts", ps("S")[1], False)
        case("a hidden cover is not drawn: posts", ps("HB")[1], False)
        case("a painted layer over the anchor, clipped away by its frame: posts", ps("A")[1], False)
        R2 = json.loads(json.dumps(R))
        R2["children"][5]["clipsContent"] = False
        case("the same layer with its frame not clipping: refused", ps("A", doc=R2)[1], True)
        case("a painted layer drawn over the anchor: refused", ps("A2")[1], True)
        R3 = json.loads(json.dumps(R))
        R3["children"] = [k for k in R3["children"] if k["id"] != "O"]
        case("a transparent frame drawn over it paints nothing: posts", ps("A2", doc=R3)[1], False)
        case("a painted layer drawn under the anchor: posts", ps("L")[1], False)
        case("an anchor that is hidden: refused", ps("HC")[1], True)

        # THE ELEVENTH RULE. The first text is two asks in one.
        two = ("This card's CTA still reads \"Learn more about Hosting\". Can that flip to match? "
               "Also, is the type pill meant to stay \"On-premises\" or become \"hosted\"?")
        case("two asks in one comment: refused", question_gate(two), True)
        case("the same with --multi-ok: posts", question_gate(two, multi_ok=True), False)
        case("one question beside a link and a quoted heading: posts",
             question_gate("The heading reads \"Why do I need this?\" on "
                           "https://www.figma.com/design/K/W?node-id=1-2. Should it say Platform?"), False)
        case("one question beside a relative link (?tagText=): posts",
             question_gate("The cards link to /collections?tagText=Model with no filter. Which tag should they pass?"), False)
        case("a FIX note with two questions: posts", question_gate("FIX (done in Figma): done? and done?"), False)
        case("no question at all: posts", question_gate("The gap is 20 in the build."), False)

        # THE TWELFTH RULE. th from THE FIFTH RULE: r1 the owner's root on no node, c3 the owner's reply.
        del_saved, DELETES = DELETES, os.path.join(tmp, "deletes.json")
        try:
            gone = [pin("g1", "5:2"), pin("g2", None)]
            record_delete("K", "g1", gone)
            case("a new post on the node of a comment deleted just now: refused", repost_gate("K", "5-2"), True)
            case("a new post on another node: posts", repost_gate("K", "5:9"), False)
            case("31 minutes after the delete: posts", repost_gate("K", "5:2", now=time.time() + 31 * 60), False)
            record_delete("K", "c3", th)
            case("a reply in the thread a reply was deleted from: refused", repost_gate("K", "thread r1"), True)
            case("a deleted canvas pin stamps nothing", record_delete("K", "g2", gone), False)
        finally:
            DELETES = del_saved
        got = parse_flags(["new", "K", "1:2", "the text", "--pin-ok", "--multi-ok", "--repost-ok"])
        case("--pin-ok, --multi-ok and --repost-ok are parsed off",
             None if got == (["new", "K", "1:2", "the text"], False, (), (), None, None, None) else got, False)
        got = parse_flags(["new", "K", "1:2", "the text", "--cause", "hero-scrim", "--new-cause"])
        case("--cause is parsed off, one slug, and --new-cause with it",
             None if got == (["new", "K", "1:2", "the text"], False, (), (), None, None, "hero-scrim") else got, False)
        got = pop_flag(["new", "K", "1:2", "t", "--new-thread", "its links, not its height", "--edited", "1:3"], "--new-thread")
        case("--new-thread's reason is taken off the line with it",
             None if got == ("its links, not its height", ["new", "K", "1:2", "t", "--edited", "1:3"]) else got, False)
        case("... and a --new-thread given last has no reason", pop_flag(["new", "--new-thread"], "--new-thread")[0], False)
        why = "the hero thread is about its crop"
        got = pop_overrides(["new", "K", "1:2", "t", "--pin-ok", why, "--separate", "t1,t3", why, "--multi-ok"])
        case("pop_overrides: each flag's reason comes off, --separate keeps its ids, a flag with none reads None",
             None if got == ({"--pin-ok": why, "--multi-ok": None, "--separate": why},
                             ["new", "K", "1:2", "t", "--separate", "t1,t3"]) else got, False)
        got = pop_overrides(["reply", "K", "r1", "t", "--own-last-ok", "--multi-ok", why])
        case("pop_overrides: a bare --own-last-ok, followed by a flag, has no reason, and the override refuses it",
             None if got == ({"--own-last-ok": None, "--multi-ok": why}, ["reply", "K", "r1", "t"])
             and ask_rules.override("--own-last-ok", got[0]["--own-last-ok"]) else got, False)
        case("an override with its reason in plain words is taken", ask_rules.override("--pin-ok", why), False)
        case("an override from a batch file is refused, whatever its reason", ask_rules.override("--pin-ok", why, True),
             True)

        # THE FOURTEENTH RULE: r1 is an open thread about hero-scrim, r2 a resolved one about faq.
        cms = [{"id": "r1", "parent_id": "", "resolved_at": None, "user": {"handle": "Owner"}},
               {"id": "r2", "parent_id": "", "resolved_at": "x"},
               {"id": "r3", "parent_id": "", "resolved_at": None},
               {"id": "r4", "parent_id": "", "resolved_at": None, "user": {"handle": "Designer"}}]
        cz = {"K": {"r1": "hero-scrim", "r2": "faq", "r4": "badge-gap"}}
        cg = lambda cause, sep=(), new=False: cause_gate("K", cause, cms, sep, new, causes=cz, me="Owner")
        case("a FIX note with no cause: refused, listing the open causes",
             None if "hero-scrim: r1" in (cg(None) or "") else (cg(None) or "not refused"), False)
        case("a cause that is not a slug: refused", cg("Hero Scrim"), True)
        case("a cause an open thread of yours carries: refused, naming it and the combine step",
             None if "combine" in (cg("hero-scrim") or "") else "passed or no combine step", False)
        case("... and --separate on that thread of yours lifts nothing, however many pictures it holds",
             cg("hero-scrim", ["r1"]), True)
        case("... --separate still lifts a thread that is someone else's", cg("badge-gap", ["r4"]), False)
        case("... and an owner it cannot read lifts nothing",
             cause_gate("K", "badge-gap", cms, ["r4"], causes=cz, me=""), True)
        case("a cause only a resolved thread carried: posts, no --new-cause needed", cg("faq"), False)
        case("a cause no thread has carried: refused without --new-cause", cg("footer-gap"), True)
        case("... posts with --new-cause", cg("footer-gap", new=True), False)
        # THE FIFTEENTH RULE: r1 (open) and r2 (resolved) both edited 5:5; r3 (open) edited 6:6.
        fx = {"K": {"r1": [0, ["5:5"], "5:1"], "r2": [0, ["5:5"], "5:1"], "r3": [0, ["6:6"], "6:1"]}}
        rg = lambda edited, skip=(), own=None: replaced_gate("K", edited, cms, skip, own, notes=fx)
        case("a FIX note editing a node an open FIX note of yours edited: refused, naming it",
             None if "r1 also edited 5:5" in (rg(["5:5", "7:7"]) or "") else (rg(["5:5", "7:7"]) or "not refused"), False)
        case("... posts when that thread is in separate, or the batch edits it", rg(["5:5"], ["r1"]), False)
        case("... posts as a reply into that same thread", rg(["5:5"], own="r1"), False)
        case("a node only a resolved note edited, or none did: posts", rg(["7:7"]) or rg(["8:8"]), False)
        lk = lambda c: f"https://x#{c['id']}"
        case("a refusal links each thread it names (link takes the comment, as figma_comments.permalink does)",
             None if "https://x#r1" in (cause_gate("K", "hero-scrim", cms, causes=cz, link=lk) or "")
             and "https://x#r1" in (replaced_gate("K", ["5:5"], cms, notes=fx, link=lk) or "") else "no link", False)
        case("instance-layer ids compare in either form",
             replaced_gate("K", ["I1:2;3:4"], cms, notes={"K": {"r3": [0, ["I1-2;3-4"], None]}}), True)

        # THE THIRTEENTH RULE.
        people = [{"user": {"handle": "Rivera, Ana"}}, {"user": {"handle": "Okafor, Lee"}}]
        case("a mention of someone who has commented here: posts", mention_gate("FIX: @Rivera, Ana please match.", people), False)
        case("an @ before a name nobody here goes by: refused", mention_gate("Q: @Ana can you check?", people), True)
        case("an email address is not a mention", mention_gate("mail design@example.com", people), False)

        # THE BATCH, with stub gates, posts and browser: the shape, not Figma.
        bdir = tempfile.mkdtemp()
        try:
            items = [{"kind": "new", "key": "K", "node": "1:2", "text": "Q: @Rivera, Ana which?"},
                     {"kind": "new", "key": "K", "node": "1:2", "text": "Q: which other one?"},
                     {"kind": "reply", "key": "K", "parent": "r1", "text": "FIX (done in Figma): x.", "picture": pic}]
            bpath = os.path.join(bdir, "batch.json")
            json.dump(items, open(bpath, "w", encoding="utf-8"))
            seen, posts, runs = [], [], []

            def checker(it, extra=(), refuse=None):
                seen.append((it.get("node") or it.get("parent"), tuple(extra)))
                return (refuse if refuse and it is not None and it["text"] == refuse else None,
                        {"kind": it["kind"], "text": it["text"]})

            def poster(plan):
                posts.append(plan["text"])
                cid = f"n{len(posts)}"
                return cid, [{"key": "K", "cid": cid, "mentions": ["Rivera, Ana"], "thread": cid, "node": "1:2"}] \
                    if "@" in plan["text"] else [{"key": "K", "cid": cid, "pictures": [pic], "thread": "r1",
                                                  "node": "1:2", "picture": pic}] if "FIX" in plan["text"] else []

            def runner(jobs):
                runs.append(len(jobs))
                return 0, [0] * len(jobs)
            fix_saved, FIXNOTES = FIXNOTES, os.path.join(bdir, "fixnotes.json")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    run_after([{"key": "K", "cid": "e1", "text": "FIX (done in Figma): x.", "fix": ["e1", ["L"], "PF"]},
                               {"key": "K", "cid": "e2", "text": "FIX (done in Figma): y.", "fix": ["e2", ["M"], "PF"]}],
                              lambda jobs: (1, [0, 1]))
                got = sorted(_load(FIXNOTES).get("K", {}))
            finally:
                FIXNOTES = fix_saved
            case("batch: a FIX edit the browser confirmed is stamped, one it did not make is not", None if got == ["e1"]
                 else got, False)
            # A picture and a mention on one comment: each NOT MADE line follows its own job's code.
            pm = [{"key": "K", "cid": "p1", "pictures": [pic], "thread": "p1", "node": "1:2", "picture": pic},
                  {"key": "K", "cid": "p1", "mentions": ["Rivera, Ana"], "thread": "p1", "node": "1:2"}]

            def said(own):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    run_after(pm, lambda jobs: (2, own))
                return ("ATTACH" in out.getvalue(), "MENTION NOT MADE" in out.getvalue())
            case("batch: a picture that failed beside a chip that was made asks for the picture only",
                 None if said([2, 0]) == (True, False) else said([2, 0]), False)
            case("batch: a chip not made beside a picture that went in asks for the mention only",
                 None if said([0, 2]) == (False, True) else said([0, 2]), False)
            out = batch(bpath, checker=checker, poster=poster, runner=runner)
            case("batch: 3 approved items post in order, and every picture and mention goes to ONE browser run",
                 None if (out, len(posts), runs) == (0, 3, [2]) else (out, len(posts), runs), False)
            case("batch: the second new thread on the node counts the first as read and separate",
                 None if ("1:2", ("n1",)) in seen else seen, False)
            seen[:], posts[:], runs[:] = [], [], []
            out = batch(bpath, checker=lambda it, extra=(): checker(it, extra, refuse="Q: which other one?"),
                        poster=poster, runner=runner)
            case("batch: one item a gate refuses stops the whole batch before anything posts or a browser opens",
                 None if (out, posts, runs) == (1, [], []) else (out, posts, runs), False)
            out = batch(bpath, check_only=True, checker=checker, poster=poster, runner=runner)
            case("batch --check: every gate runs, nothing posts", None if (out, posts, runs) == (0, [], []) else posts, False)
            posts[:], runs[:] = [], []
            for it in items:     # the old way: a post, then its own browser, item by item
                _, jobs = poster({"kind": it["kind"], "text": it["text"]})
                if jobs:
                    run_after(jobs, runner)
            case("batch: posting item by item opens a browser per post (the count catches the old way)",
                 None if runs == [1, 1] else runs, False)
            # THE FOURTEENTH RULE inside one batch: two new threads with one cause.
            two = [{"kind": "new", "key": "K", "node": "1:2", "text": "FIX (done in Figma): a.", "cause": "faq",
                    "picture": pic}, {"kind": "new", "key": "K", "node": "1:3", "text": "FIX (done in Figma): b.",
                                      "cause": "faq", "picture": pic}]
            tpath = os.path.join(bdir, "two.json")
            json.dump(two, open(tpath, "w", encoding="utf-8"))
            with contextlib.redirect_stdout(io.StringIO()):
                out = batch(tpath, check_only=True, checker=checker, poster=poster, runner=runner)
            case("batch: a second new thread with the same cause: refused", None if out == 1 else out, False)
            two[0]["picture"] = ",".join([pic] * 5)
            json.dump(two, open(tpath, "w", encoding="utf-8"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = batch(tpath, check_only=True, checker=checker, poster=poster, runner=runner)
            case("... refused too when the first already holds 5 pictures, naming the combine step",
                 None if out == 1 and "combine" in buf.getvalue() else out, False)
            json.dump(two[:1] + [{"kind": "edit", "key": "K", "cid": "r9", "text": "x"}], open(tpath, "w", encoding="utf-8"))
            seen_items = []
            with contextlib.redirect_stdout(io.StringIO()):
                batch(tpath, check_only=True, checker=lambda it, extra=(): seen_items.append(it.get("_also")) or (None, {}),
                      poster=poster, runner=runner)
            case("batch: every item learns the threads the batch edits (for THE FIFTEENTH RULE)",
                 None if seen_items == [["r9"], ["r9"]] else seen_items, False)
            # post() itself, with the API stubbed: a picture goes to the browser whatever the text's kind.
            g = globals()
            saved_post = g["_req"], g["_drafts_remove"], g["record_fixnote"]
            try:
                g["_req"] = lambda url, body=None, method="GET": {"id": "c9"}
                g["_drafts_remove"] = lambda *a, **k: None
                g["record_fixnote"] = lambda *a, **k: None
                qplan = {"kind": "new", "key": "K", "node": "1:2", "text": "Q: should this use a variable?",
                         "edited": (), "picture": pic, "notes": [], "mentions": [], "body": {}}
                with contextlib.redirect_stdout(io.StringIO()):
                    _, qjobs = post(qplan)
                    _, njobs = post(dict(qplan, picture=None))
                case("post: a Q with --picture queues its picture for the browser",
                     None if [j.get("pictures") for j in qjobs] == [[pic]] else qjobs, False)
                case("post: a Q with no picture queues no browser job", None if njobs == [] else njobs, False)
                got = picture_step("Q: should this use a variable?", picture=pic)
                case("a Q with --picture is posted ending in the label figma_attach needs",
                     None if got[0] is None and got[1].endswith(PICTURE_LABEL) else got, False)
                got = picture_step("Q: should this use a variable?")
                case("a Q with no picture is posted as written", None if got == (None, "Q: should this use a variable?")
                     else got, False)
                got = picture_step("Q: should this use a variable?", picture=pic + ".txt")
                case("a Q whose --picture is not a picture file: refused", got[0], True)
            finally:
                g["_req"], g["_drafts_remove"], g["record_fixnote"] = saved_post
            # Links go on terminal lines only. A planted post and reply whose text names a node, so shown() would
            # change it, are sent byte for byte, and the drafts file is matched against the text as written.
            sent, removed = [], []
            saved_ln = g["_req"], g["_drafts_remove"], g["record_fixnote"], g["shown"]
            try:
                g["_req"] = lambda url, body=None, method="GET": sent.append(json.dumps(body)) or {"id": "c77"}
                g["_drafts_remove"] = lambda text, **k: (removed.append(text)
                                                         or f"  drafts: removed the draft on {k['node_id']}")
                g["record_fixnote"] = lambda *a, **k: None
                said = "Q: should 2200:30002 keep the 24px gap the build has?"
                lplan = {"kind": "new", "key": "K", "node": "2200:30002", "text": said, "edited": (),
                         "picture": None, "notes": ["  pin: the centre of 2200:30002, on a frame (--pin-ok)"],
                         "mentions": [], "body": {"message": said, "client_meta": {"node_id": "2200:30002",
                                                                                    "node_offset": {"x": 1, "y": 2}}}}
                rplan = dict(lplan, kind="reply", parent="c70", root="c70", body={"message": said, "comment_id": "c70"})
                before = [json.dumps(lplan["body"]), json.dumps(rplan["body"])]
                changed = shown("K", said) != said
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    post(lplan)
                    post(rplan)
                g["shown"] = lambda key, text: str(text)
                with contextlib.redirect_stdout(io.StringIO()) as bare:
                    post(lplan)
            finally:
                g["_req"], g["_drafts_remove"], g["record_fixnote"], g["shown"] = saved_ln
            case("a planted post and reply, whose text links would change, are sent byte for byte, and the drafts "
                 "file is matched against the text as written",
                 None if changed and sent[:2] == before and removed[:2] == [said, said] else (sent, removed), False)
            out = buf.getvalue()
            import figma_client as _links
            case("the post's printed lines end with each node's link, and the posted and replied lines with the "
                 "thread's",
                 None if not _links.unlinked(out) and "node-id=2200-30002#c77" in out
                 and "node-id=2200-30002#c70" in out else out, False)
            case("planted break: printed without links, the pin and drafts lines name 2200:30002 bare",
                 None if [i for _, i in _links.unlinked(bare.getvalue())] == ["2200:30002", "2200:30002"]
                 else bare.getvalue(), False)
            # A FIX edit item: the real _check_item runs the placement and replaced-by rules from REST alone.
            import figma_attach as _fa
            saved_read = _fa._read
            try:
                fixed = {"id": "72", "parent_id": "", "user": {"id": "me", "handle": "Owner"},
                         "message": "FIX (done in Figma): the order matches the menu.", "created_at": "2026-01-01T00:00:00Z",
                         "resolved_at": None, "client_meta": {"node_id": "7:7"}}
                _fa._read = lambda key, md=False: ([fixed], {"id": "me", "email": "a@b.c"})
                rpath = os.path.join(bdir, "edit.json")
                gates, saved_gate = [], g["fix_line_gate"]
                edit = {"kind": "edit", "key": "K", "cid": "72", "edited": ["8:8"], "cause": "menu-order",
                        "text": "FIX (done in Figma): the order matches the menu, and the footer's too."}
                try:
                    g["fix_line_gate"] = lambda *a, **k: gates.append((a, k)) or ("REFUSED: planted.", [])
                    got = _check_item(edit)
                    case("batch: a FIX edit runs THE EIGHTH and FIFTEENTH RULES before the edit, with its edited "
                         "layers and cause, and their refusal refuses the item",
                         None if got == ("REFUSED: planted.", None) and gates and gates[0][0][4:6] == (("8:8",), "menu-order")
                         else (got, gates), False)
                    g["fix_line_gate"] = lambda *a, **k: (None, ["NOTE: planted placement note."])
                    got = _check_item(edit)
                    case("...passing, its job carries the stamp for step 3 (thread, edits, anchor)",
                         None if got[1] and got[1]["job"].get("fix") == ["72", ("8:8",), "7:7"] else got, False)
                    json.dump([edit], open(rpath, "w", encoding="utf-8"))
                    said = io.StringIO()
                    with contextlib.redirect_stdout(said):
                        out = batch(rpath, check_only=True, poster=poster, runner=runner)
                    case("batch --check prints a FIX edit's placement note before anyone approves the batch",
                         None if out == 0 and "item 1: NOTE: planted placement note." in said.getvalue()
                         else (out, said.getvalue()), False)
                    got = _check_item(dict(edit, text="Q: should this use a variable?"))
                    case("...an edit that is not a FIX note carries no stamp", (got[1] or {}).get("job", {}).get("fix"), False)
                    saved_fn = g["_req"], g["record_fixnote"], g["_link"]
                    stamps, gates[:] = [], []
                    try:
                        g["_req"] = lambda url, body=None, method="GET": {"comments": [fixed]}
                        g["record_fixnote"] = lambda *a, **k: stamps.append(a)
                        g["_link"] = lambda key: str
                        g["fix_line_gate"] = lambda *a, **k: gates.append((a, k)) or ("REFUSED: planted.", [])
                        try:
                            fixnote("K", "72", edit["text"], ("8:8",), cause="menu-order", separate=("r5",))
                            got = None
                        except SystemExit as e:
                            got = str(e)
                        case("fixnote runs THE FIFTEENTH RULE too, with --separate, and its refusal stamps nothing",
                             None if got == "REFUSED: planted." and gates and gates[0][0][6] == ("r5",) and not stamps
                             else (got, gates, stamps), False)
                    finally:
                        g["_req"], g["record_fixnote"], g["_link"] = saved_fn
                finally:
                    g["fix_line_gate"] = saved_gate
            finally:
                _fa._read = saved_read
        finally:
            shutil.rmtree(bdir, ignore_errors=True)

        # The comment_write opt-in figma_client needs for a comment write: a client with the keyword gets it on a
        # POST and a DELETE, never on a GET; one from before the change gets none.
        class New:
            def request(method, path, body=None, *, token=None, tool=None, timeout=120, comment_write=False): pass

        class Old:
            def request(method, path, body=None, *, token=None, tool=None, timeout=120): pass
        for cl, m, want in ((New, "POST", {"comment_write": True}), (New, "DELETE", {"comment_write": True}),
                            (New, "GET", {}), (Old, "POST", {})):
            got = _comment_write(cl, m)
            case(f"a {m} through the {cl.__name__.lower()} client passes {want or 'no opt-in'}",
                 None if got == want else got, False)
        # One real post path: _req through the figma_client beside this file, to its local mock. The client refuses
        # a comment write without the opt-in before anything is sent, so this shows the two files agree.
        import figma_client
        g = globals()
        mock = figma_client._Mock()
        env_saved = {k: os.environ.get(k) for k in ("FIGMA_API_BASE", "FIGMA_CLIENT_DIR", "FIGMA_CLIENT_MIRROR")}
        saved_tok, saved_cw = g["_tok"], g["_comment_write"]
        try:
            os.environ.update(FIGMA_API_BASE=mock.serve(), FIGMA_CLIENT_DIR=os.path.join(tmp, "figma_client"),
                              FIGMA_CLIENT_MIRROR="0")
            g["_tok"] = lambda: figma_client.DUMMY
            try:
                got = _req(f"{API}/files/PK/comments", {"message": "planted"}, "POST")
                gone = _req(f"{API}/files/PK/comments/9", None, "DELETE")
            except figma_client.CommentWriteRefused as e:
                got, gone = {"refused": str(e)[:80]}, {}
            case("a post and a delete through the real client reach Figma's stand-in, the opt-in passed",
                 None if got.get("method") == "POST" and gone.get("method") == "DELETE"
                 and len(mock.hits("/PK/comments")) == 2 else (got, gone, mock.hits("/PK/")), False)
            g["_comment_write"] = lambda client, method: {}
            try:
                _req(f"{API}/files/PK/comments", {"message": "planted"}, "POST")
                refused = None
            except figma_client.CommentWriteRefused as e:
                refused = str(e)
            case("... and with the opt-in dropped, the client refuses the post and nothing is sent",
                 None if refused and len(mock.hits("/PK/comments")) == 2 else (refused, mock.hits("/PK/")), False)
            # figma.read_only: the same post, through the same client, exits before any call.
            g["_comment_write"], g["read_only"] = saved_cw, (lambda: True)
            try:
                _req(f"{API}/files/PK/comments", {"message": "planted"}, "POST")
                ro = None
            except SystemExit as e:
                ro = str(e.code)
            finally:
                g["read_only"] = lambda: False
            case("figma.read_only set: the post is refused before any call, and nothing is sent",
                 None if ro and "figma.read_only" in ro and len(mock.hits("/PK/comments")) == 2
                 else (ro, mock.hits("/PK/")), False)
            kc_saved, fake = sys.modules.get("kit_config"), type(sys)("kit_config")
            try:
                sys.modules["kit_config"] = fake
                fake.get = lambda *k, default=None: True if k == ("figma", "read_only") else default
                on = real_read_only()
                fake.get = lambda *k, default=None: default
                off = real_read_only()
            finally:
                if kc_saved is None:
                    sys.modules.pop("kit_config", None)
                else:
                    sys.modules["kit_config"] = kc_saved
            case("read_only() is figma.read_only from the product-os config: set, True; unset, False",
                 None if on is True and off is False else (on, off), False)
        finally:
            g["_tok"], g["_comment_write"] = saved_tok, saved_cw
            mock.httpd.shutdown()
            for k, v in env_saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        # The drafts file's Cut table, read per file: new hands cut_refusal the post's file key, so a board row
        # on 3300:30001 refuses on the board and not on another file's 3300:30001. With no search stamp for
        # either key, the first refusal after the Cut table's is the search's.
        import drafts_store as _dcut
        cut_md = os.path.join(tmp, "cut-drafts.md")
        board = "KB" + "0" * 18 + "KB"
        with open(cut_md, "w", encoding="utf-8") as f:
            f.write(_dcut.CUT + "\n\n| Item | Why |\n|---|---|\n| Download method, [`3300:30001`](https://www.figma.com/"
                    f"board/{board}/Board?node-id=3300-30001) | Dropped |\n")
        kept_env = os.environ.get("FIGMA_DRAFTS")
        os.environ["FIGMA_DRAFTS"] = cut_md
        try:
            on_other = check_new("KW" + "0" * 18 + "KW", "3300:30001", "FIX (done in Figma): x.", repost_ok=True)[0] or ""
            on_board = check_new(board, "3300:30001", "FIX (done in Figma): x.", repost_ok=True)[0] or ""
        finally:
            if kept_env is None:
                os.environ.pop("FIGMA_DRAFTS", None)
            else:
                os.environ["FIGMA_DRAFTS"] = kept_env
        case("known-bad: a board Cut row doesn't refuse a post on the same id in another file; known-good: it "
             "refuses on the board",
             None if "re-raise" not in on_other and "search" in on_other and "re-raise" in on_board
             else (on_other[:120], on_board[:120]), False)

        # A stale token. Figma answers an invalid token with 401 on the comments read and on /v1/me, and with 403
        # "Invalid token" on /nodes. Every read below is planted, so nothing leaves and no token is needed.
        import io as _io
        import figma_attach as _attach
        import figma_client as _client
        err = lambda code, body: urllib.error.HTTPError("https://api.figma.com/v1/x", code, "planted", {},  # noqa: E731
                                                        _io.BytesIO(body))
        stale, body = _fc.token_stale(err(401, b'{"status":401,"err":"Invalid token"}'))
        case("token_stale: a 401 reads 'token stale', with Figma's body and the fix",
             None if stale and stale.startswith("Figma 401: token stale") and "Invalid token" in stale
             and "FIGMA_TOKEN" in stale and "Invalid token" in body else stale, False)
        case("token_stale: a 403 whose body names the token reads 'token stale' too",
             None if (_fc.token_stale(err(403, b'{"status":403,"err":"Token expired"}'))[0] or "").startswith(
                 "Figma 403: token stale") else "not stale", False)
        got = [_fc.token_stale(err(c, b))[0] for c, b in ((403, b'{"status":403,"err":"Forbidden"}'),
                                                          (404, b'{"status":404}'), (500, b""))]
        case("token_stale: a 403 that doesn't name the token, a 404 and a 500 aren't a stale token",
             None if got == [None] * 3 else got, False)

        def rejected(*a, **k):
            raise err(401, b'{"status":401,"err":"Invalid token"}')

        def owner_asked():
            raise SystemExit("planted: the token owner was asked")

        kept = (_client.request, _client.get, _fc.token, _attach._get, _attach._read, globals()["_tok"],
                globals()["_me"])
        try:
            _client.request, _client.get, _attach._get = rejected, rejected, rejected
            _fc.token = globals()["_tok"] = lambda *a, **k: "figd_planted"
            globals()["_me"] = owner_asked
            for name, call in (("_req", lambda: _req(f"{API}/files/K/comments")),
                               ("figma_comments.get", lambda: _fc.get("/v1/files/K/comments"))):
                try:
                    call()
                    said = "returned"
                except SystemExit as e:
                    said = str(e)
                case(f"{name}: a 401 exits with the 'token stale' line", None if said.startswith(
                    "Figma 401: token stale") and "cannot see" not in said else said, False)
            with contextlib.redirect_stdout(_io.StringIO()):
                comments, why = _attach._read("K")
            case("figma_attach._read: a 401 gives (None, the 'token stale' line)",
                 None if comments is None and (why or "").startswith("Figma 401: token stale") else (comments, why), False)
            item = {"kind": "new", "key": "KS", "node": "1:2", "text": DONE_PREFIX + ": the gap is 24.", "edited": ["1:2"]}
            try:
                out = batch_new_threads([item], read=lambda key: _req(f"{API}/files/{key}/comments"), files=("KS",))
            except SystemExit as e:
                out = {"ended the run": str(e)}
            case("batch_new_threads: a stale token on the comments read refuses the item, with the read's reason, "
                 "instead of ending the whole --check, and doesn't ask who owns the token",
                 None if list(out) == [1] and out[1].startswith(new_thread_head(True))
                 and "could not be read (Figma 401: token stale" in out[1] else out, False)
            _attach._read = lambda key, md=False: (None, "Figma 401: token stale (planted)")
            got = _check_item({"kind": "edit", "key": "K", "cid": "e1", "text": "FIX: the gap is 24."})
            case("an edit item whose comments can't be read is refused with the read's reason",
                 None if got[0] == "DID NOT RUN: the Figma API failed: Figma 401: token stale (planted)." else got, False)
        finally:
            (_client.request, _client.get, _fc.token, _attach._get, _attach._read, globals()["_tok"],
             globals()["_me"]) = kept
        own_open_selftest(case, tmp)
        settled_selftest(case, tmp)
    finally:
        _fc.whoami = saved_whoami
        for k in planted_meta:
            _fc._META.pop(k, None)
        READS, SEARCHES = saved
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{sum(results)} of {len(results)} planted cases behave as expected.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.argv[1:] = take_drafts_flag(sys.argv[1:])
    if sys.argv[1:2] == ["selftest"]:
        sys.exit(selftest())
    if sys.argv[1:2] == ["batch"] and len(sys.argv) >= 3:
        sys.exit(batch(sys.argv[2], check_only="--check" in sys.argv[3:]))
    asks_cid, argv = pop_flag(sys.argv[1:], "--asks")     # THE EIGHTEENTH RULE: the record entry the text asks about
    overrides, argv = pop_overrides(argv)
    for flag, why in overrides.items():   # each with its reason, in plain words (ask_rules.plain)
        refused = ask_rules.override(flag, why)
        if refused:
            sys.exit(refused)
    new_thread = overrides.get("--new-thread")
    args, _, separate, edited, evidence, picture, cause_slug = parse_flags(argv)
    own_last_ok = "--own-last-ok" in overrides
    # Each command's own count. `reply K r1` with no text passed a shared `< 3` and died on args[3].
    need = {"reply": 4, "new": 4, "fixnote": 4, "delete": 3, "cause": 2}
    cmd = args[0] if args else ""
    if {"-h", "--help"} & set(args):
        print(__doc__)
        sys.exit(0)
    if len(args) < need.get(cmd, 3):
        sys.exit(__doc__)
    ok = lambda flag: flag in overrides
    {"reply": lambda: reply(args[1], args[2], args[3], own_last_ok, edited, evidence,
                            ok("--multi-ok"), ok("--repost-ok"), picture, separate, cause_slug, asks_cid),
     "new": lambda: new(args[1], args[2], args[3], separate, edited, evidence,
                        ok("--pin-ok"), ok("--multi-ok"), ok("--repost-ok"), picture, cause_slug, ok("--new-cause"),
                        new_thread, asks_cid),
     "cause": lambda: cause(args[1], *(args[2:4] if len(args) >= 4 else ())),
     "fixnote": lambda: fixnote(args[1], args[2], args[3], edited, evidence, cause_slug, separate),
     "delete": lambda: delete(args[1], args[2])}.get(cmd, lambda: sys.exit(f"unknown: {cmd}"))()
