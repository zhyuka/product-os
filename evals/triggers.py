"""Trigger tests: does each skill fire when it should, and stay quiet when it shouldn't?

    python3 evals/triggers.py [--skill review] [--split train] [--runs 3] [--model claude-haiku-4-5] [--max-cost 6]

evals/triggers/<skill>.json lists about 20 queries, half that should fire the skill and half
near misses that shouldn't, each marked "train", "test" or "heldout". A description is tuned only on
the train queries, so the test queries are a held-out score. Once a decision has used the test
split, "heldout" holds new queries written for the next comparison. Each query runs --runs times
in a fresh scratch repository, as `claude -p` with this plugin loaded and at most
--max-turns turns, and counts as fired when the Skill tool was called with the skill's name.
The runs leave out your own user settings, skills and CLAUDE.md, so the score doesn't depend
on what else is installed on this machine; --user-settings puts them back. Claude Code's
built-in skills, such as code-review, still compete. A run that fails before the model
answers, such as a sign-in that didn't load, is tried up to twice more.

A skill is tested on its description only if the model saw it. Claude Code fits the skill
listing into 1% of the context window (8,000 characters on a 200K model) and, past that, shows
the least used skills by name only. So each run reads its own transcript's listing, and the
report says how many runs showed every one of this plugin's skills with its description.

It prints, per skill and split, how many runs fired as they should, and the cost. Every run
is a paid model call on whatever account `claude` is signed in to. It writes the full
results as JSON to --out, outside the repository by default; they stay local.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERIES = Path(__file__).resolve().parent / "triggers"
PLUGIN = "product-os"
SPLITS = ("train", "test", "heldout")
TIMEOUT = 300  # seconds per run

CART = '''def total(prices):
    return sum(prices)
'''
CHANGED = '''def total(prices):
    return sum(prices)


def mean(prices):
    return total(prices) / len(prices)
'''


def scaffold(folder):
    """A small git repository with one commit and one uncommitted change."""
    git = ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]
    (folder / "src").mkdir()
    (folder / "src" / "cart.py").write_text(CART, encoding="utf-8")
    subprocess.run(git + ["init", "-q"], cwd=folder, check=True)
    subprocess.run(git + ["add", "."], cwd=folder, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "Add total()"], cwd=folder, check=True)
    (folder / "src" / "cart.py").write_text(CHANGED, encoding="utf-8")


def fired(stream, skill):
    """(fired, the skills the run called, cost in USD, error or "", session id) from stream-json
    output. A run that used up --max-turns without calling a skill is an answer, not an error: in
    some runs Claude Code ends those with subtype error_during_execution, so the terminal reason
    decides."""
    called, cost, error, session = [], 0.0, "", ""
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        session = session or str(event.get("session_id") or "")
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use" and block.get("name") == "Skill":
                    called.append(str((block.get("input") or {}).get("skill", "")))
        elif event.get("type") == "result":
            cost = event.get("total_cost_usd") or 0.0
            turns_out = event.get("subtype") == "error_max_turns" or event.get("terminal_reason") == "max_turns"
            if event.get("is_error") and not turns_out:
                error = str(event.get("result") or event.get("subtype"))
    names = {skill, f"{PLUGIN}:{skill}"}
    return any(c.lstrip("/") in names for c in called), called, cost, error, session


def listing(session):
    """The plugin's skills the run's skill listing showed by name only, or None when the run's
    transcript or its listing can't be found. Claude Code drops descriptions, starting with the
    least used skills, once the listing passes its budget (1% of the context window), so a skill
    shown by name only was never tested on its description."""
    if not session:
        return None
    for path in (Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"skill_listing"' not in line:
                continue
            content = ((json.loads(line).get("attachment") or {}).get("content")) or ""
            return sorted(row[len(f"- {PLUGIN}:"):] for row in content.splitlines()
                          if row.startswith(f"- {PLUGIN}:") and ":" not in row[len(f"- {PLUGIN}:"):])
    return None


def run_one(query, skill, model, max_turns, user_settings=False):
    sources = "user,project,local" if user_settings else "project,local"
    for attempt in range(3):
        if attempt:
            time.sleep(5 * attempt)  # parallel runs that lost the sign-in race get it on a retry
        with tempfile.TemporaryDirectory(prefix="trigger-") as tmp:
            folder = Path(tmp)
            scaffold(folder)
            try:
                done = subprocess.run(
                    ["claude", "-p", query, "--plugin-dir", str(ROOT), "--model", model,
                     "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns),
                     "--strict-mcp-config", "--setting-sources", sources],
                    cwd=folder, capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
                stdout, stderr, code = done.stdout, done.stderr, done.returncode
            except subprocess.TimeoutExpired as e:
                # One slow run must not lose the batch. What it printed before the limit still
                # counts: a Skill call there is the run firing.
                text = [x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
                        for x in (e.stdout, e.stderr)]
                stdout, stderr, code = text[0], text[1], None
        hit, called, cost, error, session = fired(stdout, skill)
        if code is None and not called:
            error = f"timed out after {TIMEOUT}s"
        elif not stdout.strip():
            error = (stderr.strip().splitlines() or [f"exit {code}"])[-1]
        # Nothing was billed, so the model never answered: try again.
        if not (error and not cost and not called):
            break
    return {"fired": hit, "called": called, "cost": cost, "error": error, "attempts": attempt + 1,
            "bare": listing(session)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill", action="append", help="a skill to test; all with a query file by default")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--max-cost", type=float, default=6.0, help="stop starting runs past this many USD")
    parser.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "product-os-triggers.json"))
    parser.add_argument("--split", choices=SPLITS, help="run only this split's queries")
    parser.add_argument("--user-settings", action="store_true",
                        help="load your own user settings, skills and CLAUDE.md too")
    args = parser.parse_args(argv)
    skills = args.skill or sorted(p.stem for p in QUERIES.glob("*.json"))
    queries = {skill: [q for q in json.loads((QUERIES / f"{skill}.json").read_text(encoding="utf-8"))
                       if not args.split or q["split"] == args.split] for skill in skills}
    # Run number outermost, so a stop at --max-cost leaves fewer runs of every query, not no runs of the last skill.
    jobs = [(skill, item, number) for number in range(args.runs) for skill in skills for item in queries[skill]]
    spent, lock, results = [0.0], threading.Lock(), []

    def work(job):
        skill, item, number = job
        with lock:
            if spent[0] >= args.max_cost:
                return None
        try:
            outcome = run_one(item["query"], skill, args.model, args.max_turns, args.user_settings)
        except Exception as e:  # noqa: BLE001 - one broken run is an error row, not a lost batch
            outcome = {"fired": False, "called": [], "cost": 0.0, "error": f"{type(e).__name__}: {e}",
                       "attempts": 1, "bare": None}
        with lock:
            spent[0] += outcome["cost"]
        return {"skill": skill, "run": number, **item, **outcome}

    with ThreadPoolExecutor(args.jobs) as pool:
        for result in pool.map(work, jobs):
            if result is not None:
                results.append(result)
    Path(args.out).write_text(json.dumps({"model": args.model, "runs": args.runs, "results": results}, indent=2),
                              encoding="utf-8")
    print(f"Trigger tests: {args.model}, {args.runs} runs per query, at most {args.max_turns} turns, "
          f"${spent[0]:.2f}, {len(results)} of {len(jobs)} runs done, "
          f"{'with' if args.user_settings else 'without'} your user settings, "
          f"{sum(r['attempts'] > 1 for r in results)} tried again")
    seen = [r["bare"] for r in results if r["bare"] is not None]
    bare = sorted({name for names in seen for name in names})
    print(f"  Listing: {sum(not names for names in seen)} of {len(results)} runs showed every {PLUGIN} skill "
          f"with its description ({len(results) - len(seen)} listings not found)"
          + (f"; shown by name only in some: {', '.join(bare)}" if bare else ""))
    print("  A run that ended on an error counts only under errors.")
    print("  skill          split  should fire  fired      should not  stayed quiet  errors")
    for skill in skills:
        for split in SPLITS:
            mine = [r for r in results if r["skill"] == skill and r["split"] == split]
            if not mine and split not in ("train", "test"):
                continue
            ran = [r for r in mine if not r["error"]]
            yes = [r for r in ran if r["should_trigger"]]
            no = [r for r in ran if not r["should_trigger"]]
            print(f"  {skill:<14} {split:<6} {len(yes):<12} {sum(r['fired'] for r in yes):<10} "
                  f"{len(no):<11} {sum(not r['fired'] for r in no):<13} {len(mine) - len(ran)}")
    print(f"  Full results: {args.out}")
    for r in results:
        if r["error"]:
            print(f"  error: {r['skill']} {r['split']} run {r['run']}: {r['error']}: {r['query']}")
        elif r["fired"] != r["should_trigger"]:
            what = "didn't fire" if r["should_trigger"] else f"fired ({', '.join(r['called'])})"
            print(f"  miss: {r['skill']} {r['split']} run {r['run']}: {what}: {r['query']}")
    return 0 if len(results) == len(jobs) and not any(r["error"] for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
