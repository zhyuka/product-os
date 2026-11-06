"""releases.py - the Claude Code release notes published since a date, newest first.

    python releases.py --since 2026-10-21            each version published after that day, with its notes
    python releases.py --since 2026-10-21 --json     the same as JSON: [{"version", "published", "notes": [...]}]
    python releases.py --selftest                    planted registry times and changelog: the window, the order, a gap

Reads two public sources: the npm registry's publish time for each version of the package, and the
CHANGELOG.md the package's repo keeps, which has the notes but no dates. A version the changelog has
no section for is listed with no notes, and named on stderr, so a gap is never silent.

On a network that answers a blocked site with HTTP 200 and an "Access Denied" page, a fetch that
comes back as an HTML page where JSON or markdown was expected is retried through the reader proxy
(--proxy, default https://r.jina.ai/). The shape decides, not the words: a release note that quotes
"Access Denied" is still a changelog.

Exit 0 listed (possibly none), 2 a source could not be read.
"""
import argparse
import json
import re
import sys
import urllib.request

NPM = "https://registry.npmjs.org/@anthropic-ai/claude-code"
CHANGELOG = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
BLOCKED = "Access Denied"


def is_page(text):
    """An HTML page, which neither source ever serves: a block page, a login wall, an error."""
    head = text.lstrip()[:500].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<head" in head


def as_json(text):
    """The JSON in a response, or in a reader proxy's wrapper around it (from the first '{')."""
    try:
        return json.loads(text)
    except ValueError:
        i = text.find("{")
        return json.loads(text[i:]) if i >= 0 else None


def fetch(url, proxy, kind, timeout=60):
    """The body of url as `kind` ("json" or "markdown"); through the proxy when it comes back as a page."""
    def get(u):
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    def ok(text):
        if is_page(text):
            return False
        if kind == "json":
            try:
                return isinstance(as_json(text), dict)
            except ValueError:
                return False
        return "## " in text

    text = get(url)
    if not ok(text) and proxy:
        text = get(proxy + url)
    if not ok(text):
        what = "a blocked page" if BLOCKED in text[:5000] else f"not {kind}"
        raise RuntimeError(f"{url}: {what}, directly and through the proxy")
    return as_json(text) if kind == "json" else text


def sections(changelog):
    """{version: [note, ...]} from '## <version>' headings and '- ' bullets."""
    out, cur = {}, None
    for line in changelog.splitlines():
        m = re.match(r"^##\s+v?(\d+\.\d+\.\d+)\s*$", line.strip())
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.startswith("- "):
            out[cur].append(line[2:].strip())
        elif cur and line.startswith("  ") and out[cur]:
            out[cur][-1] += " " + line.strip()
    return out


def window(times, notes, since):
    """Versions published after `since` (YYYY-MM-DD, UTC), newest first."""
    rows = []
    for v, t in times.items():
        if not re.match(r"^\d+\.\d+\.\d+$", v) or t[:10] <= since:
            continue
        rows.append({"version": v, "published": t[:10], "notes": notes.get(v)})
    rows.sort(key=lambda r: tuple(int(x) for x in r["version"].split(".")), reverse=True)
    return rows


def selftest():
    times = {"created": "2020-01-01T00:00:00Z", "1.0.9": "2026-10-20T10:00:00Z",
             "1.0.10": "2026-10-22T10:00:00Z", "1.0.11": "2026-10-23T10:00:00Z",
             "1.0.12-beta": "2026-10-24T10:00:00Z"}
    log = "# Changelog\n\n## 1.0.11\n\n- Added a\n  continued\n- Fixed b\n\n## 1.0.9\n\n- Old\n"
    rows = window(times, sections(log), "2026-10-21")
    cases = [
        ("window drops a version published on or before the day", [r["version"] for r in rows] == ["1.0.11", "1.0.10"]),
        ("newest first by version, not by string", rows[0]["version"] == "1.0.11"),
        ("a wrapped bullet joins its line", rows[0]["notes"] == ["Added a continued", "Fixed b"]),
        ("a version with no section has notes None", rows[1]["notes"] is None),
        ("pre-release tags left out", all("beta" not in r["version"] for r in rows)),
        ("a block page is a page", is_page("<!DOCTYPE html><html><title>Access Denied</title>")),
        ("a note quoting Access Denied is not a page", not is_page("# Changelog\n\n## 1.0.1\n\n- Fixed Access Denied on login\n")),
        ("JSON inside a proxy's wrapper is read", as_json('Title: x\nURL Source: y\n\n{"time": {"1.0.0": "t"}}') == {"time": {"1.0.0": "t"}}),
    ]
    bad = [n for n, ok in cases if not ok]
    print(f"selftest {len(cases) - len(bad)} of {len(cases)}" + ("" if not bad else "; failed: " + "; ".join(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="YYYY-MM-DD: list versions published after this day")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--proxy", default="https://r.jina.ai/")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.since or not re.match(r"^\d{4}-\d{2}-\d{2}$", a.since):
        ap.error("--since YYYY-MM-DD is required")
    try:
        times = fetch(NPM, a.proxy, "json").get("time", {})
        notes = sections(fetch(CHANGELOG, a.proxy, "markdown"))
    except Exception as e:  # a source we could not read is "did not run", never "no releases"
        print(f"did not run: {e}", file=sys.stderr)
        return 2
    rows = window(times, notes, a.since)
    for r in rows:
        if r["notes"] is None:
            print(f"no changelog section for {r['version']}", file=sys.stderr)
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        print(f"{len(rows)} version(s) published after {a.since}")
        for r in rows:
            print(f"\n## {r['version']} ({r['published']})")
            for n in r["notes"] or ["(no changelog section)"]:
                print(f"- {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
