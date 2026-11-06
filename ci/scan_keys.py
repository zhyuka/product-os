"""scan_keys.py - refuse a commit whose staged lines hold a token, key or password.

    python3 scan_keys.py              the pre-commit check: the lines this commit adds
    python3 scan_keys.py --tree       every tracked file, to see what the patterns catch here
    python3 scan_keys.py selftest     planted keys caught, ordinary lines passed, N of M

It names the file, the line and the kind of key, never the value. Exit 0 clean, 1 refused, 2 did not
run (git failed). A scan that did not run is not a pass, so the pre-commit hook refuses on 2 as well.

A sample value that only looks like a key, such as a fixture or a docs example, passes when its line
also says `scan-keys: allow`. Never use that for a real key: take it out of the file, keep it in your
shell or keychain, and stage again.

BLIND TO: a key split across lines or built at run time, a kind not listed below, and anything
already committed (`--tree` shows those and never refuses).
"""
import re
import subprocess
import sys

KINDS = [
    ("Figma token", r"\bfig[a-z]_[A-Za-z0-9_-]{30,}"),
    ("GitHub token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})"),
    ("GitLab token", r"\bglpat-[A-Za-z0-9_-]{20,}"),
    ("Anthropic key", r"\bsk-ant-[A-Za-z0-9_-]{30,}"),
    ("OpenAI key", r"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}"),
    ("Azure DevOps token", r"\b[A-Za-z0-9]{76}AZDO[A-Za-z0-9]{4}\b"),
    ("AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Azure storage key", r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}"),
    ("signed URL", r"[?&]sig=[A-Za-z0-9%+/]{30,}"),
    ("JSON web token", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]
KINDS = [(k, re.compile(p)) for k, p in KINDS]
# A name that says secret, set to a quoted literal that looks random. Placeholders and lookups pass.
ASSIGN = re.compile(r"""\b(?:token|secret|password|passwd|pwd|api[_-]?key|access[_-]?key|"""
                    r"""client[_-]?secret|auth|pat|hmac[_-]?key)\b["']?\s*[:=]\s*(["'`])([^"'`\s]{16,})\1""", re.I)
PLACEHOLDER = re.compile(r"[<>{}$*]|\.\.\.|x{4,}|your|example|sample|dummy|placeholder|changeme|redacted|"
                         r"process\.env|os\.environ", re.I)
ALLOW = "scan-keys: " + "allow"


def looks_random(v):
    classes = sum(1 for r in (r"[a-z]", r"[A-Z]", r"[0-9]") if re.search(r, v))
    return classes >= 2 and not PLACEHOLDER.search(v)


def scan_line(text):
    """The kind of key on this line, or None."""
    if ALLOW in text:
        return None
    for kind, rx in KINDS:
        if rx.search(text):
            return kind
    m = ASSIGN.search(text)
    if m and looks_random(m.group(2)):
        return "password or secret"
    return None


def added_lines(diff):
    """(file, line number in the new file, text) for each line a unified diff adds."""
    out, file, line = [], None, 0
    for raw in diff.split("\n"):
        if raw.startswith("+++ "):
            file = None if raw == "+++ /dev/null" else re.sub(r"^b/", "", raw[4:])
            continue
        h = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if h:
            line = int(h.group(1))
            continue
        if file is None:
            continue
        if raw.startswith("+"):
            out.append((file, line, raw[1:]))
            line += 1
        elif not raw.startswith("-") and not raw.startswith("\\"):
            line += 1
    return out


def report(hits, where):
    if not hits:
        return 0
    print(f"pre-commit: REFUSED. {len(hits)} line(s) {where} look like a key or token:")
    for file, line, kind in hits:
        print(f"  {file}:{line}  {kind}")
    print("Take the value out of the file, keep it in your shell or keychain, and stage again.")
    print(f"If it is a sample value and not a real key, add `{ALLOW}` on that line.")
    return 1


def git(args):
    r = subprocess.run(["git"] + args, capture_output=True)
    if r.returncode:
        raise RuntimeError((r.stderr.decode("utf-8", "replace").strip().splitlines() or ["git failed"])[0])
    return r.stdout.decode("utf-8", "replace")


def staged():
    try:
        diff = git(["diff", "--cached", "--no-color", "--no-ext-diff", "-U0", "--diff-filter=ACMR"])
    except (OSError, RuntimeError) as e:
        print(f"pre-commit: REFUSED. The key scan did not run: git diff failed ({e}).")
        return 2
    hits = [(f, n, k) for f, n, t in added_lines(diff) for k in [scan_line(t)] if k]
    return report(hits, "in what you staged")


def tree():
    try:
        files = [f for f in git(["ls-files", "-z"]).split("\0") if f]
    except (OSError, RuntimeError) as e:
        print(f"scan_keys: did not run: git ls-files failed ({e}).")
        return 2
    hits = []
    for f in files:
        try:
            with open(f, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue
        for n, text in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
            k = scan_line(text)
            if k:
                hits.append((f, n, k))
    print(f"scan_keys --tree: {len(files)} tracked files read, {len(hits)} line(s) look like a key.")
    for f, n, k in hits:
        print(f"  {f}:{n}  {k}")
    return 0


def selftest():
    # Planted values are built here at run time, so this file never holds a key-shaped literal.
    a36, a40 = "A1b2" * 9, "Q7w8" * 10
    bad = [
        ("GitHub token", "token = " + "gh" + "p_" + a36),
        ("GitLab token", "url: https://x/?t=" + "gl" + "pat-" + a36),
        ("Figma token", "FIGMA_TOKEN=" + "fig" + "d_" + a36),
        ("Anthropic key", "key: " + "sk-" + "ant-" + a36),
        ("AWS access key", "id = " + "AK" + "IA" + "ABCDEFGHIJKLMNOP"),
        ("private key", "-----BEGIN RSA " + "PRIVATE KEY-----"),
        ("Azure DevOps token", "a" * 76 + "AZ" + "DO" + "b1c2"),
        ("password or secret", 'password = "' + a40[:20] + '"'),
    ]
    good = [
        "const total = items.reduce((a, b) => a + b, 0);",
        'password = "<your password here>"',
        'token = os.environ["GITHUB_TOKEN"]',
        "api_key: ${API_KEY}",
        'secret = "' + "x" * 20 + '"',
        'token = "' + "gh" + "p_" + a36 + '"  # ' + ALLOW,
    ]
    cases, passed = [], 0

    def expect(name, ok):
        nonlocal passed
        cases.append(name)
        passed += bool(ok)
        if not ok:
            print(f"  FAILED  {name}")

    for kind, text in bad:
        expect(f"planted {kind} is caught", scan_line(text) == kind)
    for text in good:
        expect(f"ordinary line passes: {text[:30]}", scan_line(text) is None)
    diff = ("diff --git a/a.py b/a.py\n+++ b/a.py\n@@ -3,0 +4,2 @@\n+x = 1\n+" + bad[0][1] + "\n"
            "+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
    lines = added_lines(diff)
    expect("added lines carry the new file's line numbers", [(f, n) for f, n, _ in lines] == [("a.py", 4), ("a.py", 5)])
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = report([("a.py", 5, scan_line(bad[0][1]))], "in what you staged")
    expect("a refusal exits 1", code == 1)
    expect("a refusal never prints the value", a36 not in out.getvalue())
    print(f"scan_keys selftest: {passed} of {len(cases)} {'PASS' if passed == len(cases) else 'FAIL'}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    arg = sys.argv[1:2]
    if arg in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    if arg in (["selftest"], ["--selftest"]):
        sys.exit(selftest())
    sys.exit(tree() if arg == ["--tree"] else staged())
