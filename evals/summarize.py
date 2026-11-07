"""Summarize a `claude plugin eval --json` result as Markdown.

    python3 evals/summarize.py results.json

For each case it prints the score with the plugin and without it, the runs in
each arm that ended on an error (a turn cap, a timeout, an API error), and for
each grader how many runs passed it in each arm. Field names follow the
schemaVersion 1 result document. It never changes the exit code of a run; it
exits 2 only when the file can't be read.

A run that errored and never got an answer from the model, or that errored with
no grader run, measures nothing. A failed sign-in is one. The harness still grades
some of those, and a grader that checks for an absence passes on an empty run. So
the scores, the deltas and the grader counts here leave such runs out, and each
is listed with its error under its case.
"""
import json
import sys


def fmt(value, signed=False):
    if value is None:
        return "n/a"
    return f"{value:+.2f}" if signed else f"{value:.2f}"


def scored(run):
    """False for a run that errored and measured nothing: the agent spent nothing, so the model
    never answered, or no grader ran."""
    if not run.get("error"):
        return True
    agent_cost = (run.get("costUsd") or 0) - (run.get("judgeCostUsd") or 0)
    return agent_cost > 0 and bool(run.get("graders"))


def mean_score(runs):
    scores = [run.get("score") or 0 for run in runs if scored(run)]
    return sum(scores) / len(scores) if scores else None


def passes(runs, name):
    """'N of M' scored runs that passed the grader, with runs left out or never graded named."""
    kept = [run for run in runs if scored(run)]
    passed = graded = 0
    for run in kept:
        for grader in run.get("graders") or []:
            if grader.get("name") == name:
                graded += 1
                passed += bool(grader.get("passed"))
    text = f"{passed} of {len(kept)}"
    notes = [f"{len(runs) - len(kept)} not scored"] if len(kept) < len(runs) else []
    if graded < len(kept):
        notes.append(f"{len(kept) - graded} not graded")
    return text + (f" ({', '.join(notes)})" if notes else "")


def errors(runs):
    return [(n, run["error"], scored(run)) for n, run in enumerate(runs, 1) if run.get("error")]


def summarize(doc):
    lines = []
    cases = doc.get("cases") or []
    threshold = (doc.get("suite") or {}).get("threshold")
    rows, deltas, passed, unscored = [], [], 0, 0
    for case in cases:
        arms = case.get("arms") or {}
        with_runs, without_runs = arms.get("with") or [], arms.get("without") or []
        score, without = mean_score(with_runs), mean_score(without_runs)
        delta = None if score is None or without is None else score - without
        if delta is not None:
            deltas.append(delta)
        if score is not None and isinstance(threshold, (int, float)) and score >= threshold:
            passed += 1
        unscored += sum(not scored(run) for run in with_runs + without_runs)
        rows.append((case, with_runs, without_runs, score, without, delta))
    lines.append(f"## Live evals: Claude Code {doc.get('claudeVersion', '?')}, {len(cases)} cases, "
                 f"${doc.get('costUsd', 0):.2f}, {doc.get('durationSeconds', 0)}s")
    lines.append("")
    lines.append(f"{passed} of {len(cases)} cases at or above the threshold of "
                 f"{'?' if threshold is None else threshold}. "
                 f"Mean delta: {fmt(sum(deltas) / len(deltas) if deltas else None, True)}.")
    if unscored:
        lines.append("")
        lines.append(f"**{unscored} {'run' if unscored == 1 else 'runs'} not scored**: each errored "
                     "before the model answered, or no grader ran. The scores and counts below leave "
                     "them out, and each is listed with its error under its case.")
    if doc.get("partial"):
        lines.append("")
        lines.append(f"**Partial result** ({doc.get('partialReason', 'reason not given')}): "
                     "some runs never started, so the scores below are not comparable to a full run.")
    lines += ["", "| case | with plugin | without | delta | with-arm runs that errored | "
                  "baseline runs that errored |", "| --- | --- | --- | --- | --- | --- |"]

    def errored(runs):
        found = errors(runs)
        lost = sum(not ok for _, _, ok in found)
        return f"{len(found)} of {len(runs)}" + (f", {lost} not scored" if lost else "")

    for case, with_runs, without_runs, score, without, delta in rows:
        lines.append(f"| {case.get('name')} | {fmt(score)} | {fmt(without)} | {fmt(delta, True)} | "
                     f"{errored(with_runs)} | {errored(without_runs)} |")
    for case, with_runs, without_runs, *_ in rows:
        lines += ["", f"### {case.get('name')}", "",
                  "| grader | type | weight | with plugin | without |",
                  "| --- | --- | --- | --- | --- |"]
        for grader in case.get("graders") or []:
            name = grader.get("name")
            config = grader.get("config") or {}
            kind = grader.get("type", "?") + (" (with-only)" if config.get("arm") == "with-only" else "")
            lines.append(f"| {name} | {kind} | {grader.get('weight', 1)} | {passes(with_runs, name)} | "
                         f"{passes(without_runs, name) if without_runs else 'not run'} |")
        for arm, runs in (("with plugin", with_runs), ("without", without_runs)):
            for number, error, ok in errors(runs):
                lines.append(f"- {arm}, run {number}{'' if ok else ', not scored'}: {error}")
        for advisory in case.get("advisories") or []:
            lines.append(f"- advisory: {advisory}")
    return "\n".join(lines) + "\n"


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as err:
        print(f"summarize: could not read {argv[1]}: {err}", file=sys.stderr)
        return 2
    sys.stdout.write(summarize(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
