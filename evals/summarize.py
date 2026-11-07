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

A grader the harness skipped, such as a judge left out once the cost ceiling was
reached, is recorded as failed, and the run's score counts it so. It measured
nothing, so here it is not graded: it is left out of the grader counts, listed as
not graded, and a run's score counts only the graders that ran.

A judge records its votes but not its reasons, and a grader's explanation can't
say what the agent did. So for each scored run that failed a grader, when its
trace is still on disk (evals/live.py keeps them), it also prints what the run
did: each tool call with the start of its result or its denial, the calls of an
agent the run started indented under it, and the end of the last reply. Anything
shaped like a token or key is masked.
"""
import json
import re
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


def skipped(mark):
    """True for a grader the harness never ran, such as a judge skipped at the cost ceiling. The
    harness records it as failed, with an explanation that starts "skipped"."""
    return str(mark.get("explanation") or "").lower().startswith("skipped")


def run_score(run):
    """The run's score over the graders that ran, weighted as the harness weights them, or None
    when none ran. With nothing skipped it is the harness's own score."""
    marks = [mark for mark in run.get("graders") or [] if mark.get("scored", True)]
    if not any(skipped(mark) for mark in marks):
        return run.get("score") or 0
    ran = [mark for mark in marks if not skipped(mark)]
    total = sum(mark.get("weight", 1) for mark in ran)
    return sum(mark.get("weight", 1) for mark in ran if mark.get("passed")) / total if total else None


def mean_score(runs):
    scores = [run_score(run) for run in runs if scored(run)]
    scores = [score for score in scores if score is not None]
    return sum(scores) / len(scores) if scores else None


def passes(runs, name):
    """'N of M' graded runs that passed the grader, with runs left out or never graded named."""
    kept = [run for run in runs if scored(run)]
    passed = graded = 0
    for run in kept:
        for grader in run.get("graders") or []:
            if grader.get("name") == name and not skipped(grader):
                graded += 1
                passed += bool(grader.get("passed"))
    text = f"{passed} of {graded}"
    notes = [f"{len(runs) - len(kept)} not scored"] if len(kept) < len(runs) else []
    if graded < len(kept):
        notes.append(f"{len(kept) - graded} not graded")
    return text + (f" ({', '.join(notes)})" if notes else "")


def failures(case, with_runs, without_runs, width=240):
    """One line per grader, arm and reason a scored run failed it, or skipped it, with how many runs
    gave that reason: the grader's own explanation, such as a missing file or the judge's votes. The
    step summary is all a reader without a GitHub sign-in gets, so the reason has to be here."""
    lines = []
    for grader in case.get("graders") or []:
        name = grader.get("name")
        for arm, runs in (("with plugin", with_runs), ("without", without_runs)):
            reasons = {}
            for run in filter(scored, runs):
                for mark in run.get("graders") or []:
                    if mark.get("name") == name and not mark.get("passed"):
                        why = " ".join(str(mark.get("explanation") or "no explanation").split())
                        why = why if len(why) <= width else why[:width - 3] + "..."
                        key = ("not graded" if skipped(mark) else "failed", why)
                        reasons[key] = reasons.get(key, 0) + 1
            for (what, why), count in reasons.items():
                lines.append(f"- {name} {what}, {arm}, {count} {'run' if count == 1 else 'runs'}: {why}")
    return lines


def errors(runs):
    return [(n, run["error"], scored(run)) for n, run in enumerate(runs, 1) if run.get("error")]


# The most the blocks saying what failed runs did may add. GitHub drops a step summary over 1 MiB.
DIGESTS = 600_000
# A JWT such as GitHub's OIDC token, an Anthropic key, or a bearer token.
SECRET = re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]*|sk-ant-[\w-]+|(?i:bearer)\s+[\w.~+/=-]{16,}")


def clip(text, width):
    text = SECRET.sub("[masked]", " ".join(str(text).split())).replace("```", "'''")
    return text if len(text) <= width else text[:width - 3] + "..."


def call_text(name, given):
    """The part of a tool call's input that says what it did."""
    for key in ("command", "file_path", "pattern", "skill", "url"):
        if isinstance(given.get(key), str):
            return given[key]
    if name in ("Agent", "Task"):
        return f"{given.get('subagent_type', 'general-purpose')}: {given.get('description', '')}"
    return json.dumps(given)


def what_it_did(path, calls=24, width=140, tail=600):
    """Lines saying what one run did, from its trace: each tool call with the start of its result,
    or "DENIED" and why, the calls of an agent it started indented, and the end of its last reply.
    [] when the trace isn't there to read. Past `calls` calls, the first and last halves."""
    if not path:
        return []
    order, outcome, last = [], {}, ""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                inner = bool(event.get("parent_tool_use_id"))
                message = event.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                content = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else None
                if event.get("type") == "assistant" and content is not None:
                    for block in content:
                        if block.get("type") == "tool_use":
                            order.append((block.get("id"), block.get("name", "?"), inner,
                                          call_text(block.get("name"), block.get("input") or {})))
                        elif block.get("type") == "text" and not inner and block.get("text", "").strip():
                            last = block["text"]
                elif event.get("type") == "user" and content is not None:
                    for block in content:
                        if block.get("type") == "tool_result" and block.get("tool_use_id") not in outcome:
                            body = block.get("content")
                            if isinstance(body, list):
                                body = " ".join(part.get("text", "") for part in body if isinstance(part, dict))
                            outcome[block.get("tool_use_id")] = ("error: " if block.get("is_error") else "") + str(body)
                elif event.get("subtype") == "permission_denied":
                    outcome[event.get("tool_use_id")] = f"DENIED ({event.get('decision_reason_type', '?')})"
                elif event.get("type") == "result" and isinstance(event.get("result"), str) and event["result"].strip():
                    last = event["result"]
    except OSError:
        return []
    lines = [f"{'    ' if inner else ''}{name}: {clip(text, width)} -> {clip(outcome.get(ident, 'no result'), width)}"
             for ident, name, inner, text in order]
    if len(lines) > calls:
        lines = lines[:calls // 2] + [f"... {len(lines) - calls} more calls ..."] + lines[-(calls - calls // 2):]
    reply = clip(last, 10 ** 6)
    lines.append("last reply: " + (("..." + reply[-tail:]) if len(reply) > tail else reply or "(none)"))
    return lines


def failed_runs(case, with_runs, without_runs, budget):
    """A collapsed block per scored run that failed a grader that ran, saying what it did, while
    budget[0] characters are left. GitHub drops a step summary over 1 MiB whole."""
    lines = []
    for arm, runs in (("with plugin", with_runs), ("without", without_runs)):
        for number, run in enumerate(runs, 1):
            missed = [mark.get("name") for mark in run.get("graders") or []
                      if mark.get("scored", True) and not mark.get("passed") and not skipped(mark)]
            if not scored(run) or not missed:
                continue
            did = what_it_did(run.get("tracePath"))
            block = ["", f"<details><summary>{arm}, run {number}, failed {', '.join(missed)}: what it did"
                         "</summary>", "", "```text", *did, "```", "", "</details>"]
            size = sum(len(line) + 1 for line in block)
            if did and size > budget[0]:
                budget[1] += 1
            elif did:
                budget[0] -= size
                lines += block
    return lines


def summarize(doc):
    lines = []
    cases = doc.get("cases") or []
    threshold = (doc.get("suite") or {}).get("threshold")
    rows, deltas, passed, unscored, partly = [], [], 0, 0, 0
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
        partly += sum(scored(run) and any(skipped(mark) for mark in run.get("graders") or [])
                      for run in with_runs + without_runs)
        rows.append((case, with_runs, without_runs, score, without, delta))
    lines.append(f"## Live evals: Claude Code {doc.get('claudeVersion', '?')}, {len(cases)} cases, "
                 f"${doc.get('costUsd', 0):.2f}, {doc.get('durationSeconds', 0)}s")
    lines.append("")
    lines.append(f"{passed} of {len(cases)} cases at or above the threshold of "
                 f"{'?' if threshold is None else threshold}. "
                 f"Mean delta: {fmt(sum(deltas) / len(deltas) if deltas else None, True)}.")
    if doc.get("notice"):
        lines += ["", f"**Notice:** {doc['notice']}"]
    if unscored:
        lines.append("")
        lines.append(f"**{unscored} {'run' if unscored == 1 else 'runs'} not scored**: each errored "
                     "before the model answered, or no grader ran. The scores and counts below leave "
                     "them out, and each is listed with its error under its case.")
    if partly:
        lines.append("")
        lines.append(f"**{partly} {'run' if partly == 1 else 'runs'} with graders skipped**, such as a "
                     "judge left out at the cost ceiling. Those graders count as not graded, and those "
                     "runs score on the graders that ran.")
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
    budget = [DIGESTS, 0]
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
        lines += failures(case, with_runs, without_runs)
        for advisory in case.get("advisories") or []:
            lines.append(f"- advisory: {advisory}")
        lines += failed_runs(case, with_runs, without_runs, budget)
    if budget[1]:
        lines += ["", f"What {budget[1]} more failed {'run' if budget[1] == 1 else 'runs'} did is left out, "
                      "to keep this summary under GitHub's size limit."]
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
