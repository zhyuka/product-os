"""Run the live eval suite one case at a time, each with a fresh sign-in, under one cost cap.

    python3 evals/live.py --json OUT.json --cap 6.75 --tools Bash Edit Write \
        [--tag builder reviewer] [--judge-model M] [--fetch CMD ...] [--claude CMD ...]

Why one case at a time: under workload identity federation, every Claude Code process that a
`claude plugin eval` starts shares one exchanged access token, through a cache keyed on the
GitHub token each read when it started. That access token lasts at most twice the GitHub
token's remaining life, about 10 minutes. A process still running then exchanges again with
whatever token the shared file holds, and another process may present that same token. A
GitHub token can be exchanged once, so the second gets a 401 (jti_reused). That is how v0.1.0's
macOS evals lost every run from about 10 minutes in.

So each case runs as its own `claude plugin eval`, after --fetch writes a new GitHub token to
the token file, with its own empty federation cache folder. Every process in it presents the
same never-used token once, shares the result, and is done long before it expires.

--cap is the most the whole run may spend. Each case gets what is left, as its
--max-cost-usd, and a case is not started once less than a cent is left. --tag keeps the cases
with any of those tags, as `claude plugin eval --tag` does. The cases' results go in a folder
named after --json, and --json gets one document in the same format with every case in it, for
evals/summarize.py. A case that didn't run is named in its partialReason.

Exit 0 when every case ran and passed, else 1.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
LEFT_OVER = 0.01


def cases(tags):
    """The case folders under evals/, in name order, that carry any of tags (all with none)."""
    found = []
    for folder in sorted(p for p in EVALS.iterdir() if (p / "case.yaml").is_file()):
        text = (folder / "case.yaml").read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(\S+)", text, re.M)
        listed = re.search(r"^tags:\s*\[([^\]]*)\]", text, re.M)
        own = {t.strip().strip("'\"") for t in listed.group(1).split(",")} if listed else set()
        if not tags or own & set(tags):
            found.append(name.group(1) if name else folder.name)
    return found


def run_case(name, budget, args, results):
    """Run one case with a fresh token and an empty federation cache. (its result or None, exit
    code, why it didn't run)."""
    if args.fetch:
        fetched = subprocess.run(args.fetch, cwd=ROOT)
        if fetched.returncode:
            return None, 1, "no fresh OIDC token"
    out = results / f"{name}.json"
    cache = tempfile.mkdtemp(prefix="wif-cache-")
    env = dict(os.environ, CLAUDE_CODE_FEDERATION_CACHE_DIR=cache)
    command = [*args.claude, "plugin", "eval", ".", "--case", name, "--trust-plugin", "--scaffold",
               "--no-publish", "--max-cost-usd", f"{budget:.2f}", "--threshold", str(args.threshold),
               "--judge-model", args.judge_model, "--concurrency", "3", "--json", str(out),
               "--allow-tools", *args.tools]
    print(f"live.py: {name}, up to ${budget:.2f}", flush=True)
    try:
        code = subprocess.run(command, cwd=ROOT, env=env).returncode
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    try:
        return json.loads(out.read_text(encoding="utf-8")), code, ""
    except (OSError, ValueError):
        return None, code or 1, f"no result (exit {code})"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--cap", required=True, type=float)
    parser.add_argument("--tools", nargs="+", required=True)
    parser.add_argument("--tag", nargs="+", default=[])
    parser.add_argument("--judge-model", default="claude-haiku-4-5")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--fetch", nargs="+", default=[], help="the command that writes a new token")
    parser.add_argument("--claude", nargs="+", default=["claude"])
    args = parser.parse_args(argv)
    results = args.json.with_suffix("")
    results.mkdir(parents=True, exist_ok=True)
    started, spent, docs, missed, failed = time.time(), 0.0, [], [], False
    for name in cases(args.tag):
        budget = args.cap - spent
        if budget < LEFT_OVER:
            missed.append((name, "cost_ceiling"))
            continue
        doc, code, why = run_case(name, budget, args, results)
        failed = failed or code != 0
        if doc is None:
            missed.append((name, why))
            continue
        spent += doc.get("costUsd") or 0
        docs.append(doc)
        if doc.get("partial"):
            missed.append((name, doc.get("partialReason") or "partial"))
    reasons = sorted({why for _, why in missed})
    merged = {
        "schemaVersion": 1,
        "claudeVersion": next((d.get("claudeVersion") for d in docs if d.get("claudeVersion")), "?"),
        "costUsd": spent,
        "durationSeconds": round(time.time() - started),
        "partial": bool(missed),
        "suite": {"threshold": args.threshold, "cap": args.cap, "tags": args.tag},
        "cases": [case for doc in docs for case in doc.get("cases") or []],
    }
    if missed:
        merged["partialReason"] = "; ".join(
            f"{why}: {', '.join(n for n, w in missed if w == why)}" for why in reasons)
    args.json.write_text(json.dumps(merged, indent=1) + "\n", encoding="utf-8")
    print(f"live.py: {len(docs)} cases ran, ${spent:.2f}" + (f"; not run or partial: {merged['partialReason']}"
                                                               if missed else ""))
    return 1 if failed or missed else 0


if __name__ == "__main__":
    sys.exit(main())
