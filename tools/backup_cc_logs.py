#!/usr/bin/env python3
"""backup_cc_logs.py - copy ~/.claude/projects to a backup folder so session logs outlive Claude Code's
log cleanup, ~/.claude/skills so your personal skills outlive this machine, and ~/.claude/file-history,
the only store of the versions an agent's edits overwrote.

    python tools/backup_cc_logs.py [--dest DIR]   copy what is new or changed, print one summary line
    python tools/backup_cc_logs.py --selftest     planted tree: new, unchanged, appended, rewritten, deleted,
                                                  skills, file-history, a planted fake token held

WHY THIS EXISTS. Claude Code deletes a session log `cleanupPeriodDays` after it was last written
(30 by default; an organisation can set it). The logs are the record of what was asked, decided and
done, and nothing else keeps them. Run this daily (and at login) from a scheduler.

WHERE IT COPIES. <backup>/cc-logs/, where <backup> is `backup.folder` in the product-os config: any
folder a cloud drive syncs (iCloud Drive, Dropbox, Google Drive, OneDrive) or an external disk.
--dest names the cc-logs folder directly. It refuses to run when the backup folder is missing,
because a copy into a folder that does not sync protects nothing.

WHAT IT DOES. Mirrors every file under ~/.claude/projects (session logs, subagent logs, tool results,
memory) into `cc-logs/projects/`, keeping the same relative paths, so a tool that reads session logs
finds each copy by its usual shape. It never deletes: a log the cleanup removes stays in the backup.
  - A file whose size and mtime match its copy is skipped without being read.
  - A grown .jsonl whose old copy is a byte prefix of it is overwritten (an append loses nothing).
  - Any other change keeps the old copy at `cc-logs/superseded/<YYYYMMDD-HHMMSS>/projects/<same path>`
    first, because a resumed or compacted session can rewrite records.
  - A .jsonl is copied up to its last newline, so a session being written never leaves a half record.
Writes are atomic: temp file in the target folder, fsync, os.replace.

ALSO ~/.claude/skills. Claude Code loads personal skills from there, and that folder is often not a
git repo. Each file goes to `cc-logs/skills/<same path>` by the rules above, so an edited file keeps
its old copy under `superseded/<stamp>/skills/` and a deleted skill stays in the backup. Skips
`synced/` (the desktop app's own copies of its skills) and `.trash/`. A missing folder is skipped.

ALSO ~/.claude/file-history. Before an agent edits a file, Claude Code keeps the file as it was at
`file-history/<session>/<first 16 hex of sha256(absolute path)>@v<n>`; nothing else keeps those versions.
Each goes to `cc-logs/file-history/<same path>` by the rules above. A missing folder is skipped.

HELD, never copied: a file-history or skills file likely to hold a credential, since a copy would put
it in a second store. The test runs on the file's own source path and on its bytes, before any write:
  - by path: SECRET_NAMES, SECRET_DIRS and SECRET_TAILS (settings.json, .claude.json, *.lock, .env, ssh
    keys and folders, credentials, .git/config, .netrc and the like, key files);
  - by content: workspace_audit.SECRET, the one credential detector the workspace audit uses too;
  - a file-history file whose source path no log of its session names is held too, as its path rule
    can't be applied. The path comes from the session's logs (live or backed up): each file-history
    snapshot's paths and each Edit or Write's file_path, kept when its sha256 gives the file's name;
    failing that, the path a snapshot links the file to by name (a renamed file's backups keep the old
    name). So a path is proven or linked by Claude Code, never guessed.
A held file prints as HELD with its label, source path and rule, never its bytes. Its label, size,
mtime, source path and rule go to `cc-logs/file-history-held.json`, so a later run counts it without
reading it again; a file
whose path was unknown is tried again each run. If the detector won't import, every file-history and
skills file still to copy is held and the run exits 1.

NOT COPIED. ~/.claude/history.jsonl (a dot-folder in a cloud drive is not reliably synced), `.DS_Store`.

Exit 0 when every file is copied or current; 1 when any file failed (each is named); 2 when it could
not run: no backup folder configured or it is missing, or ~/.claude/projects is missing.
"""
import argparse
import contextlib
import datetime
import glob
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

if os.path.dirname(os.path.realpath(__file__)) not in sys.path: sys.path.append(os.path.dirname(os.path.realpath(__file__)))
import kit_config

HOME = os.path.expanduser("~")
SRC = os.path.join(HOME, ".claude", "projects")
SKILLS = os.path.join(HOME, ".claude", "skills")
SKILLS_SKIP = {"synced", ".trash"}  # top-level folders under SKILLS that are not backed up
FILE_HISTORY = os.path.join(HOME, ".claude", "file-history")
HELD_FILE = "file-history-held.json"   # under dest: what HELD above kept back, so a later run need not reread it
CHUNK = 1 << 20

# HELD by path (above), matched lowercased on the source path, since paths can be case-insensitive.
SECRET_NAMES = re.compile(r"settings(\.local)?\.json|\.claude\.json.*|.*\.lock|\.env.*|.*\.env|\.?(git-)?credentials(\..*)?"
                          r"|\.netrc|\.npmrc|\.pypirc|\.pgpass|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?"
                          r"|.*\.(pem|key|p12|pfx|jks|ppk|keystore)")
SECRET_DIRS = {".ssh", "ssh", ".aws", ".gnupg", ".docker", ".kube", "credentials", "secrets", ".secrets"}
SECRET_TAILS = ("/.git/config",)
_FILE_PATH = re.compile(rb'"(?:file_path|notebook_path)":"((?:[^"\\]|\\.)*)"')
_CWD = re.compile(rb'"cwd":"((?:[^"\\]|\\.)*)"')


def backup_root():
    """The configured backup folder (backup.folder), expanded. Raises kit_config.NotConfigured."""
    return os.path.expanduser(kit_config.need("backup", "folder"))


def dest_root():
    return os.path.join(backup_root(), "cc-logs")


def _payload(path):
    """The bytes to back up: the whole file, or a .jsonl up to its last newline."""
    with open(path, "rb") as f:
        data = f.read()
    if path.endswith(".jsonl"):
        data = data[:data.rfind(b"\n") + 1]
    return data


def _is_prefix(old_path, data):
    """True when the copy on file is a byte prefix of the new payload."""
    if os.path.getsize(old_path) > len(data):
        return False
    with open(old_path, "rb") as f:
        pos = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                return True
            if data[pos:pos + len(chunk)] != chunk:
                return False
            pos += len(chunk)


def _write(target, data, mtime):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.utime(tmp, (mtime, mtime))
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _files(base, skip=()):
    """(path, name, path relative to base) for every file under base, in a fixed order, leaving out
    the top-level folders named in skip."""
    for root, dirs, files in os.walk(base):
        if root == base:
            dirs[:] = [d for d in dirs if d not in skip]
        dirs.sort()
        for name in sorted(files):
            if name != ".DS_Store":
                path = os.path.join(root, name)
                yield path, name, os.path.relpath(path, base)


def _jobs(src, skills=None, history=None):
    """(path, name, label, output path under dest): src's files, then skills' and history's (ALSO above)."""
    for path, name, rel in _files(src):
        yield path, name, rel, os.path.join("projects", rel)
    if skills and os.path.isdir(skills):
        for path, name, rel in _files(skills, SKILLS_SKIP):
            yield path, name, "skills/" + rel, os.path.join("skills", rel)
    if history and os.path.isdir(history):
        for path, name, rel in _files(history):
            yield path, name, "file-history/" + rel, os.path.join("file-history", rel)


def _detector():
    """workspace_audit.SECRET, or None when it won't import (then HELD above holds every guarded file)."""
    if os.path.dirname(os.path.realpath(__file__)) not in sys.path: sys.path.append(os.path.dirname(os.path.realpath(__file__)))
    try:
        import workspace_audit
        return workspace_audit.SECRET
    except Exception:  # noqa: BLE001 - any failure to load the detector must fail closed
        return None


def secret_path(path):
    """The HELD path rule a source path meets, or None."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    if SECRET_NAMES.fullmatch(parts[-1]):
        return "name " + parts[-1]
    hit = next((d for d in parts[:-1] if d in SECRET_DIRS), None)
    if hit:
        return "folder " + hit
    return next(("path */" + t.lstrip("/") for t in SECRET_TAILS if p.endswith(t)), None)


class Guard:
    """HELD above: says why a skills or file-history file must not be copied, or None. Reads no file
    itself except a session's logs, to find a file-history file's source path."""

    def __init__(self, log_roots, secret):
        self.log_roots = [r for r in log_roots if r and os.path.isdir(r)]
        self.secret = secret
        self.maps = {}
        self.shown = []    # one line per file held this run: label, source path, rule; never its bytes

    def guards(self, label):
        return label.startswith(("skills/", "file-history/"))

    def _logs(self, session):
        for root in self.log_roots:
            yield from glob.glob(os.path.join(glob.escape(root), "*", glob.escape(session) + ".jsonl"))
            yield from glob.glob(os.path.join(glob.escape(root), "*", glob.escape(session), "subagents", "*.jsonl"))

    def paths(self, session):
        """{first 16 hex of sha256(path): path} for every path a log of this session names; then, for a name no
        path hashes to, the path a snapshot links it to by its backupFileName (a renamed file's backup keeps its
        old name)."""
        if session in self.maps:
            return self.maps[session]
        found, cwds, rel, links = {}, [], set(), {}

        def add(p):
            found.setdefault(hashlib.sha256(p.encode("utf-8", "surrogatepass")).hexdigest()[:16], p)

        def where(p):
            if os.path.isabs(p) or not cwds:
                return p
            try:
                return os.path.join(json.loads(b'"' + cwds[0] + b'"'), p)
            except ValueError:
                return p

        for log in self._logs(session):
            try:
                with open(log, "rb") as f:
                    for line in f:
                        if b'"file_path"' in line or b'"notebook_path"' in line:
                            for raw in _FILE_PATH.findall(line):
                                try:
                                    add(json.loads(b'"' + raw + b'"'))
                                except ValueError:
                                    pass
                        m = _CWD.search(line, 0, 4000)
                        if m and m.group(1) not in cwds:
                            cwds.append(m.group(1))
                        if b"trackedFileBackups" in line:
                            try:
                                r = json.loads(line)
                            except ValueError:
                                continue
                            for p, v in ((r.get("snapshot") or {}).get("trackedFileBackups") or {}).items():
                                (add if os.path.isabs(p) else rel.add)(p)
                                if isinstance(v, dict) and v.get("backupFileName"):
                                    links.setdefault(v["backupFileName"].split("@")[0], p)
            except OSError:
                continue
        for p in rel:                     # a snapshot keys a path by the session's cwd at the time
            for c in cwds:
                try:
                    add(os.path.join(json.loads(b'"' + c + b'"'), p))
                except ValueError:
                    pass
        for h, p in links.items():
            found.setdefault(h, where(p))
        self.maps[session] = found
        return found

    def source(self, label, path):
        if label.startswith("skills/"):
            return path
        session, name = label.split("/")[1], label.split("/")[-1]
        return self.paths(session).get(name.split("@")[0])

    def reason(self, label, path, data):
        if self.secret is None:
            return "no credential detector: workspace_audit.SECRET did not import"
        src = self.source(label, path)
        if src is None:
            return "source path unknown: no log of its session names it"
        why = secret_path(src)
        if why:
            return "path rule, " + why
        if self.secret.search(data.decode("utf-8", "replace")):
            return "credential-shaped content"
        return None


def _load_held(dest):
    try:
        with open(os.path.join(dest, HELD_FILE), encoding="utf-8") as f:
            held = json.load(f)
        return held if isinstance(held, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_held(dest, held):
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, HELD_FILE), json.dumps(held, indent=1, sort_keys=True).encode("utf-8"),
           datetime.datetime.now().timestamp())


def guard_for(src, dest, secret=False):
    """The Guard for a run: logs from src and their backup copies; secret False means load it."""
    return Guard([src, os.path.join(dest, "projects")], _detector() if secret is False else secret)


def backup(src, dest, stamp, skills=None, history=None, guard=None):
    """Copy src into dest/projects, and `skills` and `history` as ALSO above says, holding back what HELD above
    says (its lines in guard.shown). Returns (counts, failures)."""
    n = {"files": 0, "new": 0, "appended": 0, "superseded": 0, "current": 0, "skills": 0, "history": 0,
         "held": 0}
    failed = []
    guard = guard or guard_for(src, dest)
    held = _load_held(dest)
    held_before = dict(held)
    blind = 0                     # guarded files held because the detector did not import
    for path, name, label, out in _jobs(src, skills, history):
        target = os.path.join(dest, out)
        n["files"] += 1
        n["skills"] += label.startswith("skills/")
        n["history"] += label.startswith("file-history/")
        try:
            st = os.stat(path)
            if os.path.exists(target):
                tst = os.stat(target)
                if int(tst.st_mtime) == int(st.st_mtime) and (
                        tst.st_size == st.st_size or name.endswith(".jsonl") and tst.st_size <= st.st_size):
                    n["current"] += 1
                    continue
            was = held.get(label)
            if was and was.get("size") == st.st_size and was.get("mtime") == int(st.st_mtime):
                n["held"] += 1
                continue
            data = _payload(path)
            if guard.guards(label):
                why = guard.reason(label, path, data)
                if why:
                    n["held"] += 1
                    if guard.secret is None:
                        blind += 1
                        continue
                    src_path = guard.source(label, path)
                    guard.shown.append(f"{label} ({(src_path or '?').replace(HOME, '~')}): {why}")
                    if src_path:          # an unknown path is tried again next run
                        held[label] = {"size": st.st_size, "mtime": int(st.st_mtime),
                                       "source": src_path.replace(HOME, "~"), "why": why}
                    continue
            if not os.path.exists(target):
                n["new"] += 1
            elif os.path.getsize(target) == len(data) and _is_prefix(target, data):
                os.utime(target, (st.st_mtime, st.st_mtime))
                n["current"] += 1
                continue
            elif name.endswith(".jsonl") and _is_prefix(target, data):
                n["appended"] += 1
            else:
                keep = os.path.join(dest, "superseded", stamp, out)
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                shutil.copy2(target, keep)
                n["superseded"] += 1
            _write(target, data, st.st_mtime)
        except OSError as e:
            failed.append(f"{label}: {type(e).__name__}: {e.strerror or e}")
    if blind:
        failed.append(f"{blind} skills and file-history files held, none checked: workspace_audit.SECRET did not import")
    if held != held_before:
        try:
            _save_held(dest, held)
        except OSError as e:
            failed.append(f"{HELD_FILE}: {type(e).__name__}: {e.strerror or e}")
    return n, failed


def run(dest=None):
    if dest is None:
        try:
            root = backup_root()
        except kit_config.NotConfigured as e:
            print(f"DID NOT RUN: {e}")
            return 2
        if not os.path.isdir(root):
            print(f"DID NOT RUN: the backup folder {root.replace(HOME, '~')} is missing, so a copy would not sync")
            return 2
        dest = os.path.join(root, "cc-logs")
    elif not os.path.isdir(os.path.dirname(os.path.abspath(dest))):
        print(f"DID NOT RUN: the folder above {dest} is missing")
        return 2
    if not os.path.isdir(SRC):
        print(f"DID NOT RUN: {SRC.replace(HOME, '~')} is missing")
        return 2
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    guard = guard_for(SRC, dest)
    n, failed = backup(SRC, dest, stamp, SKILLS, FILE_HISTORY, guard)
    print(f"{stamp} {n['files']} files under ~/.claude/projects, skills and file-history "
          f"({n['skills']} skill files, {n['history']} file-history): {n['new']} new, "
          f"{n['appended']} appended, "
          f"{n['superseded']} changed (old copy kept), {n['current']} already current, "
          f"{n['held']} held as likely credentials, {len(failed)} failed. "
          f"Dest {dest.replace(HOME, '~')}")
    for line in guard.shown:
        print("HELD", line)
    for line in failed:
        print("FAILED", line)
    return 1 if failed else 0


def selftest():
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(("PASS " if cond else "FAIL ") + label)

    def put(path, data, mtime=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        if mtime:
            os.utime(path, (mtime, mtime))

    def read(path):
        with open(path, "rb") as f:
            return f.read()

    u = "0b0b0b0b-1111-2222-3333-444444444444"
    with tempfile.TemporaryDirectory() as t:
        src, dest = os.path.join(t, "projects"), os.path.join(t, "cc-logs")
        main = os.path.join(src, "S", u + ".jsonl")
        sub = os.path.join(src, "S", u, "subagents", "agent-a.jsonl")
        meta = os.path.join(src, "S", u, "subagents", "agent-a.meta.json")
        put(main, b'{"a":1}\n{"b":', 1_000_000)                   # half-written last record
        put(sub, b'{"s":1}\n', 1_000_000)
        put(meta, b'{"m":1}', 1_000_000)
        put(os.path.join(src, "S", ".DS_Store"), b"x")
        n, f = backup(src, dest, "R1")
        bm = os.path.join(dest, "projects", "S", u + ".jsonl")
        check("first run copies 3 files, skips .DS_Store", n["new"] == 3 and n["files"] == 3 and not f)
        check("a half-written record is not copied", read(bm) == b'{"a":1}\n')
        check("copy keeps the source mtime", int(os.stat(bm).st_mtime) == 1_000_000)

        n, f = backup(src, dest, "R2")
        check("second run with no change copies nothing", n["current"] == 3 and n["new"] + n["appended"] == 0)

        put(main, b'{"a":1}\n{"b":2}\n', 1_000_100)
        n, f = backup(src, dest, "R3")
        check("an append overwrites, keeps no old copy",
              n["appended"] == 1 and read(bm) == b'{"a":1}\n{"b":2}\n' and not os.path.exists(os.path.join(dest, "superseded")))

        put(main, b'{"c":3}\n', 1_000_200)
        n, f = backup(src, dest, "R4")
        kept = os.path.join(dest, "superseded", "R4", "projects", "S", u + ".jsonl")
        check("a rewrite keeps the old copy under superseded/",
              n["superseded"] == 1 and read(kept) == b'{"a":1}\n{"b":2}\n' and read(bm) == b'{"c":3}\n')

        os.remove(sub)
        n, f = backup(src, dest, "R5")
        check("a log deleted at the source stays in the backup",
              os.path.exists(os.path.join(dest, "projects", "S", u, "subagents", "agent-a.jsonl")))

        os.chmod(meta, 0)
        put(meta + "2", b"{}", 1_000_000)
        os.utime(meta, (1_000_300, 1_000_300))
        n, f = backup(src, dest, "R6")
        os.chmod(meta, 0o600)
        check("an unreadable file is named as failed, the rest still copy",
              len(f) == 1 and "agent-a.meta.json" in f[0] and os.path.exists(os.path.join(dest, "projects", "S", u, "subagents", "agent-a.meta.json2")))

        # skills (ALSO above): copied beside projects/, synced/ and .trash/ left out, edits versioned.
        src3, sk, dest3 = (os.path.join(t, d) for d in ("p3", "sk", "d3"))
        put(os.path.join(src3, "S", u + ".jsonl"), b'{"a":1}\n', 1_000_000)
        put(os.path.join(sk, "ask", "SKILL.md"), b"v1", 1_000_000)
        put(os.path.join(sk, "ask", "references", "r.md"), b"r", 1_000_000)
        put(os.path.join(sk, "synced", "app", "SKILL.md"), b"app", 1_000_000)
        put(os.path.join(sk, ".trash", "old", "SKILL.md"), b"old", 1_000_000)
        n, f = backup(src3, dest3, "K1", sk)
        check("skills copy to skills/ at the same paths, without synced/ or .trash/",
              n["skills"] == 2 and n["files"] == 3 and not f
              and read(os.path.join(dest3, "skills", "ask", "SKILL.md")) == b"v1"
              and os.path.exists(os.path.join(dest3, "skills", "ask", "references", "r.md"))
              and not os.path.exists(os.path.join(dest3, "skills", "synced"))
              and not os.path.exists(os.path.join(dest3, "skills", ".trash")))
        put(os.path.join(sk, "ask", "SKILL.md"), b"v2", 1_000_100)
        os.remove(os.path.join(sk, "ask", "references", "r.md"))
        n, f = backup(src3, dest3, "K2", sk)
        check("an edited SKILL.md keeps its old copy under superseded/; a deleted skill file stays",
              n["superseded"] == 1 and not f
              and read(os.path.join(dest3, "skills", "ask", "SKILL.md")) == b"v2"
              and read(os.path.join(dest3, "superseded", "K2", "skills", "ask", "SKILL.md")) == b"v1"
              and os.path.exists(os.path.join(dest3, "skills", "ask", "references", "r.md")))
        n, f = backup(src3, dest3, "K3", os.path.join(t, "absent"))
        check("a missing skills folder is skipped", n["skills"] == 0 and n["files"] == 1 and not f)

        # file-history and HELD (above): a planted fake token must reach neither the backup nor the output.
        # The token is built at run time, so this file carries no credential-shaped literal.
        fake = ("fig" + "d_" + "Zq7Xw2Pk9Lm4Rt8Vb3Nc6Hy1Jd5Fs0Ga").encode()
        src4, fh, dest4 = (os.path.join(t, d) for d in ("p4", "fh", "d4"))
        s = "0e0e0e0e-1111-2222-3333-444444444444"
        proj = "/w/proj"

        def hname(p, v):
            return hashlib.sha256(p.encode()).hexdigest()[:16] + "@v" + str(v)

        files = {"deck": (proj + "/deck.html", b'<img src="data:image/png;base64,iVBOR' + b"ak" + b'iaq7xb2mzr4kd9wpvtZm9v">'),
                 "notes": (proj + "/notes.md", b"a note\nAPI_TOKEN " + fake + b"\n"),
                 "settings": (proj + "/.claude/settings.json", b'{"env": {}}'),
                 "env": (proj + "/.env", b"X=1"),
                 "ssh": ("/w/.ssh/config", b"Host x"),
                 "skill": (proj + "/sk.md", b"clean")}
        snap = {"type": "file-history-snapshot", "snapshot": {"trackedFileBackups": {
            "deck.html": {"backupFileName": hname(files["deck"][0], 1)},
            ".claude/settings.json": {"backupFileName": hname(files["settings"][0], 1)},
            "renamed.md": {"backupFileName": hname(proj + "/old-name.md", 1)},                 # linked, not hashed
            "linked/settings.json": {"backupFileName": hname(proj + "/old.json", 1)}}}}
        edits = [{"type": "assistant", "cwd": proj, "message": {"content": [{"type": "tool_use", "name": "Edit",
                  "input": {"file_path": files[k][0]}}]}} for k in ("notes", "env", "ssh")]
        put(os.path.join(src4, "-w-proj", s + ".jsonl"),
            b"".join(json.dumps(r, separators=(",", ":")).encode() + b"\n"
                     for r in [{"type": "user", "cwd": proj}, snap] + edits), 1_000_000)
        for k in ("deck", "notes", "settings", "env", "ssh"):
            put(os.path.join(fh, s, hname(files[k][0], 1)), files[k][1], 1_000_000)
        put(os.path.join(fh, s, hname(files["deck"][0], 2)), files["deck"][1] + b"<p>v2</p>", 1_000_000)
        put(os.path.join(fh, s, hname(proj + "/old-name.md", 1)), b"renamed", 1_000_000)
        put(os.path.join(fh, s, hname(proj + "/old.json", 1)), b"{}", 1_000_000)
        put(os.path.join(fh, s, hname("/w/proj/nowhere.md", 1)), b"x", 1_000_000)        # no log names it
        put(os.path.join(fh, "0f0f0f0f-1111-2222-3333-444444444444", hname("/w/x.md", 1)), b"x", 1_000_000)  # no log
        sk4 = os.path.join(t, "sk4")
        put(os.path.join(sk4, "ok", "SKILL.md"), b"clean", 1_000_000)
        put(os.path.join(sk4, "leaky", "SKILL.md"), b"git clone https://deploy:" + fake + b"@gitlab.example.com/x", 1_000_000)
        out = io.StringIO()
        g = guard_for(src4, dest4)
        with contextlib.redirect_stdout(out):
            n, f = backup(src4, dest4, "H1", sk4, fh, g)
            for line in g.shown:
                print("HELD", line)
        fhd = os.path.join(dest4, "file-history", s)
        check("file-history copies to file-history/ at the same paths: both deck versions, base64 image data and all",
              read(os.path.join(fhd, hname(files["deck"][0], 1))) == files["deck"][1]
              and os.path.exists(os.path.join(fhd, hname(files["deck"][0], 2))) and n["history"] == 10 and not f)
        why = {ln.split(" (")[0].split("/")[-1]: ln.split("): ")[-1] for ln in g.shown}
        check("a renamed file's backup resolves by its snapshot link: copied when clean, held by its path rule",
              read(os.path.join(fhd, hname(proj + "/old-name.md", 1))) == b"renamed"
              and why.get(hname(proj + "/old.json", 1), "").startswith("path rule, name settings.json"))
        check("held by path: settings.json, .env and a file under .ssh",
              why.get(hname(files["settings"][0], 1), "").startswith("path rule, name settings.json")
              and why.get(hname(files["env"][0], 1), "").startswith("path rule, name .env")
              and why.get(hname(files["ssh"][0], 1), "").startswith("path rule, folder .ssh"))
        check("held by content: a file-history file and a skill holding the planted fake token",
              why.get(hname(files["notes"][0], 1)) == "credential-shaped content"
              and why.get("SKILL.md") == "credential-shaped content"
              and read(os.path.join(dest4, "skills", "ok", "SKILL.md")) == b"clean")
        check("held, path unknown: a file no log names, and a session with no log",
              sum(w.startswith("source path unknown") for w in why.values()) == 2 and n["held"] == 8)
        leaked = []
        for root, _, names in os.walk(dest4):
            leaked += [nm for nm in names if fake in read(os.path.join(root, nm))]
        check("the planted fake token is in no file under the backup and not in the output",
              not leaked and fake.decode() not in out.getvalue() and n["new"] == 5)
        noread = os.path.join(fh, s, hname(files["settings"][0], 1))
        os.chmod(noread, 0)
        n, f = backup(src4, dest4, "H2", sk4, fh, guard_for(src4, dest4))
        os.chmod(noread, 0o600)
        check("the next run counts a held file from file-history-held.json without reading it; "
              "a file whose path was unknown is tried again",
              n["held"] == 8 and n["current"] == 5 and not f)
        put(os.path.join(fh, s, hname(files["deck"][0], 3)), b"<p>v3</p>", 1_000_000)
        n, f = backup(src4, os.path.join(t, "d5"), "H3", sk4, fh, guard_for(src4, dest4, None))
        check("no detector: every skills and file-history file is held, none copied, and the run fails",
              n["held"] == 13 and n["new"] == 1 and len(f) == 1 and "did not import" in f[0]
              and not os.path.exists(os.path.join(t, "d5", "file-history")))
        check("path rules on real-shaped paths, and none on a deck or a note about credentials",
              all(secret_path(p) for p in (HOME + "/.claude/settings.json", HOME + "/.claude.json",
                                           "/x/.git/config", "/x/repo/.npmrc", HOME + "/.aws/config",
                                           "/x/.credentials.json", HOME + "/.claude/ide/123.lock",
                                           "/x/.env.local", HOME + "/.ssh/id_ed25519"))
              and not any(secret_path(p) for p in (HOME + "/notes/deck.html",
                                                   "/x/notes/credential-handling.md",
                                                   "/x/package-lock.json", "/x/tools/ledger.py")))

    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    # A help probe or a typo'd flag must never fall through to a real backup.
    ap = argparse.ArgumentParser(prog="backup_cc_logs.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", help="the cc-logs folder to copy into (default <backup.folder>/cc-logs)")
    ap.add_argument("--selftest", action="store_true",
                    help="planted tree: new, unchanged, appended, rewritten, deleted, skills, file-history, "
                         "a planted fake token held")
    a = ap.parse_args()
    sys.exit(kit_config.run_isolated(selftest) if a.selftest else run(a.dest))
