"""product-os check [--base REF] [--prove] [--run-listed] | product-os accept [NAME ...]
product-os prove [NAME ...] [--base REF] | product-os prove --check FILE
product-os check <folder> | product-os demo
product-os design import NODES.json | product-os design drift [NODES.json] [--meta META.json]
product-os design states | product-os design exercise URL [--serve FOLDER]

Also runs as python -m product_os.
"""
import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import (__version__, calibrate, check, design, exercise, gates, project, readonly, runlog,
               step_ran, vacuous)

BUILDS = Path(__file__).resolve().parent.parent / "examples" / "builds"


def table(headers, rows):
    rows = [list(map(str, row)) for row in [headers, *rows]]
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    for row in rows:
        print("  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())


def demo_vacuous():
    print("1. Vacuous pass: naive score vs guarded score")
    rows = vacuous.compare(BUILDS)
    table(["build", "naive", "rules that inspected nothing", "guarded"],
          [(name, f"{naive.value:.2f}",
            f"{sum(r.inspected == 0 for r in naive.results)} of {len(naive.results)}", guarded)
           for name, naive, guarded in rows])
    real = [(name, naive) for name, naive, guarded in rows if guarded.value is not None]
    for name, naive, guarded in rows:
        if guarded.value is None:
            beaten = [n for n, s in real if s.value < naive.value]
            print(f"  Naive scorer ranks '{name}' above {len(beaten)} of {len(real)} real builds"
                  f" ({', '.join(beaten) or 'none'}). The guard refuses to score it.")


def demo_readonly(runs=91, seed=0):
    print(f"2. Read-only audit: {runs} runs of a stub reviewer told to stay read-only")
    rows = []
    for label, tools in (("read and write", readonly.FileTools),
                         ("read-only layer", readonly.ReadOnlyTools)):
        results = readonly.audit(readonly.stub_reviewer, BUILDS / "good", runs, seed, tools)
        edited = [r for r in results if r.changes]
        blocked = [r for r in results if r.blocked]
        rows.append((label, f"{len(edited)} of {runs}", f"{len(blocked)} of {runs}"))
        if tools is readonly.FileTools:
            print(f"  {len(edited)} of {runs} runs edited files despite a read-only instruction:")
            for r in edited:
                print(f"    run {r.number}: {', '.join(r.changes)}")
    table(["tools given", "runs that edited files", "writes blocked"], rows)
    print("  Same prompt both times. The instruction did not stop the writes; the tool layer did.")


def demo_step_ran(runs=33):
    print(f"3. Step-ran verification: {runs} runs per stub agent")
    rows = []
    for agent in (step_ran.qa_agent, step_ran.cheap_agent):
        results = step_ran.trial(agent, BUILDS / "good", runs)
        claimed = sum(claim == "QA passed" for claim, _ in results)
        accepted = sum(v.accepted for _, v in results)
        reasons = "; ".join(sorted({v.reason for _, v in results}))
        rows.append((agent.__name__, f"{claimed} of {runs}", f"{accepted} of {runs}",
                     f"{runs - accepted} of {runs}", reasons))
    table(["agent", "claimed QA passed", "accepted", "rejected", "verifier reason"], rows)


def demo_calibration():
    print("4. Calibration: one planted bad case and one known-good case per check")
    results = calibrate.calibrate_all(BUILDS / "good")
    table(["check", "planted bad caught", "known good passed"],
          [(c.check, f"{c.caught} of {c.bad}", f"{c.passed} of {c.good}") for c in results])
    ok = sum(c.ok for c in results)
    print(f"  {ok} of {len(results)} checks passed calibration.")
    return ok == len(results)


def demo():
    if not BUILDS.is_dir():
        print(f"product-os: the demo reads {BUILDS}, which only exists in a clone of the repo",
              file=sys.stderr)
        return 2
    for part in (demo_vacuous, demo_readonly, demo_step_ran):
        part()
        print()
    return 0 if demo_calibration() else 1


def run_check(folder):
    """Exit 0 when no check failed, 1 when one did, 2 when the input is unusable."""
    try:
        results = check.check_folder(folder)
    except runlog.RunLogError as err:
        print(f"product-os: {err}", file=sys.stderr)
        return 2
    print(f"Release checks for {folder}")
    table(["check", "result", "detail"], [(r.check, r.status, r.detail) for r in results])
    ran = [r for r in results if r.status != "skip"]
    failed = [r for r in ran if r.status == "fail"]
    print(f"  {len(ran)} of {len(results)} checks ran: "
          f"{len(ran) - len(failed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


def run_project(root, base, reprove, run_listed=False):
    """Exit 0 when every check passed, 1 when one didn't or none ran, 2 on unusable input."""
    try:
        root = project.find_root(project.start_folder(root))
        results, notes = project.check_project(root, base=base, reprove=reprove,
                                               run_listed=run_listed)
    except project.ConfigError as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    print(f"Checks for {root}" + (f", against {base}" if base else ""))
    for note in notes:
        print(f"  {note}.")
    if not results:
        print(f"  There are no checks in {project.hooks.CONFIG.as_posix()}, so nothing passed.")
        return 1
    table(["check", "result", "detail"], [(r.check, r.status, r.detail) for r in results])
    failed = [r for r in results if r.status != "pass"]
    print(f"  {len(results) - len(failed)} of {len(results)} checks passed.")
    for r in failed:
        if r.output:
            print(f"\n--- {r.check}: the last lines of its output\n{r.output}")
    if any(r.detail.startswith("not accepted on this machine") for r in failed):
        print(f"\nA check that isn't accepted didn't run. Accepting it is {project.hooks.PERSON}: "
              f"read its command in {project.hooks.CONFIG.as_posix()}, then run product-os accept "
              "in a terminal of your own.")
    if failed:
        print(f"\n{project.BLOCKED}")
    return 1 if failed else 0


def run_prove(root, names, base, check_file=None, accept=False):
    """Exit 0 when every check named, or every check, was proven, 1 when one wasn't, 2 on
    unusable input. With accept, the checks that were proven are also accepted here."""
    try:
        root = project.find_root(project.start_folder(root))
        listed = project.commands(root, names, base=base) if accept else []
        if check_file:
            rows, notes, ok = project.prove_file(root, check_file)
        else:
            rows, notes, ok = project.prove_project(root, names, base=base, accept=accept)
    except project.ConfigError as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    if check_file:
        print(f"Proving the checks in {check_file}, for {root}")
    elif accept:
        print(f"Accepting the checks in {root}. These are the commands that now run on this "
              "machine:")
        for name, line in listed:
            print(f"  {name}: {line}")
    else:
        print(f"Proving the checks in {root}" + (f", against {base}" if base else ""))
    for note in notes:
        print(f"  {note}.")
    if not rows:
        print(f"  There are no checks in {check_file or project.hooks.CONFIG.as_posix()} to prove.")
        return 1
    table(["check", "bad cases caught", "good cases passed", "result"], rows)
    proven = sum(row[-1] in ("proven", "proven and accepted") for row in rows)
    records = Path(project.proofs_path(root)).relative_to(root).as_posix()
    print(f"  {proven} of {len(rows)} checks proven. Records: {records}.")
    if accept:
        print(f"  Accepted on this machine: {project.accepted_path(root, os.environ)[0]}.")
    elif proven:
        print(f"  On this machine a check runs only once it is accepted. That's {project.hooks.PERSON}: "
              "read its command, then run product-os accept in a terminal of your own.")
    if check_file and proven:
        print(f"  A proven entry counts once it is listed in {project.hooks.CONFIG.as_posix()} "
              "unchanged.")
    if not ok:
        print("  A check that isn't proven doesn't count. Fix the check, not its cases: a bad case "
              "it passes is a defect it would miss.")
    return 0 if ok else 1


def _read_response(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise design.BaselineError(f"{path} could not be read") from None


def run_import(folder, nodes, sets, file_key, meta=None):
    """Exit 0 when every frame was saved, 2 on unusable input."""
    try:
        state = _read_response(meta) if meta else None
        if state is not None:
            design.file_state(state)  # refuse a bad file before anything is written
        payloads = design.from_rest(_read_response(nodes), _read_response(sets) if sets else None,
                                    file_key)
        entries = [(p["frame"]["id"], design.save_frame(folder, p)) for p in payloads]
        if state is not None:
            design.record_file_state(folder, state)
    except design.BaselineError as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    print(f"Saved from {nodes} to {folder}")
    table(["frame", "name", "size", "sha256", "component sets"],
          [(frame_id, e["name"],
            f"{e['width']:g} x {e['height']:g}" if e["width"] and e["height"] else "",
            e["sha256"][:12], len(e["sets"])) for frame_id, e in entries])
    index = design.read_index(folder)
    missing = sorted({s for _, e in entries for s in e["sets"] if s not in index["sets"]})
    if missing:
        print(f"  {len(missing)} component sets the frames use aren't saved, so only the states "
              "their instances show are known. Read them with GET /v1/files/:key/nodes?ids= and "
              "pass the answer with --sets: " + ",".join(missing))
    return 0


def run_drift(folder, nodes, meta=None):
    """Exit 0 when no frame moved, 1 when one did, isn't in the baseline or may have, 2 on
    unusable input."""
    try:
        rows = design.drift(folder, _read_response(nodes) if nodes else None,
                            _read_response(meta) if meta else None)
    except design.BaselineError as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    print(f"{nodes or meta}, against the baseline in {folder}")
    table(["frame", "name", "design"], rows)
    moved = [r for r in rows if r[2] != "unchanged"]
    if rows and rows[0][0] == "file":
        print("  The file is unchanged since the baseline was last known to match it." if not moved
              else "  The file was edited. Read the frames and run design drift NODES.json to "
                   "see which moved.")
    else:
        print(f"  {len(rows) - len(moved)} of {len(rows)} frames unchanged.")
    return 1 if moved or not rows else 0


def run_states(folder, frames, as_json):
    """Exit 0 with the list, 2 when the baseline is unusable."""
    try:
        states = design.plan_states(folder, frames)
    except design.BaselineError as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps([asdict(s) for s in states], indent=2, ensure_ascii=False))
        return 0
    print(f"States the design in {folder} draws")
    if states:
        table(["frame", "node", "state", "input", "from"],
              [(s.frame_name or s.frame, f"{s.name} ({s.node})", s.state,
                s.keys or s.do if s.do != "none" else f"none: {s.why_not}", " and ".join(s.source))
               for s in states])
    reached = sum(s.do != "none" for s in states)
    print(f"  {len(states)} states: {reached} reached by an input, {len(states) - reached} not.")
    return 0


def run_exercise(folder, url, frames, selectors, evidence, wait_s, serve=None, accept=None):
    """Exit 0 when every exercised state responded or was accepted, 1 when one didn't or none
    was exercised, 2 on unusable input or when the browser can't run."""
    try:
        accepted = exercise.read_accepted(accept) if accept else {}
        results = exercise.exercise(folder, url, frames,
                                    exercise.read_selectors(selectors) if selectors else None,
                                    evidence, wait_s=wait_s, serve=serve, accepted=accepted)
    except (design.BaselineError, exercise.ExerciseError) as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    where = f"{url} on {serve}" if serve else url
    print(f"Exercising {where} in the states the design in {folder} draws")
    if results:
        table(["frame", "node", "state", "input", "result", "detail"],
              [(r["frame_name"] or r["frame"], f"{r['name']} ({r['node']})", r["state"],
                r["keys"] or r["do"], r["status"], r["detail"]) for r in results])
    done = [r for r in results if r["status"] != "not exercised"]
    failed = [r for r in done if r["status"] in exercise.FAILED]
    passed = sum(r["status"] == "responds" for r in done)
    taken = {(r["node"], r["state"]) for r in done if r["status"] == "accepted"}
    print(f"  {passed} of {len(done)} exercised states responded"
          + (f", {len(taken)} accepted" if taken else "")
          + f"; {len(results) - len(done)} states not exercised.")
    for node, state in sorted(set(accepted) - taken):
        print(f"  Accepted in {accept}, but not needed: {node} {state}. It responded, or the "
              "design no longer draws it.")
    if evidence:
        print(f"  Screenshots and results.json: {evidence}.")
    if not done:
        print("  No state was exercised, so nothing passed.")
    return 1 if failed or not done else 0


def run_gates(url, serve, baseline, widths, only, scale, out):
    """Exit 0 when every gate passed at every width, 1 when one didn't, 2 on unusable input or
    when the browser can't run."""
    try:
        sizes = gates.widths_from(baseline, widths)
        results = gates.gates(url, sizes, only or gates.GATES, serve=serve, scale=scale)
    except (design.BaselineError, gates.GateError, exercise.ExerciseError) as err:
        print(f"product-os: {err}.", file=sys.stderr)
        return 2
    where = f"{url} on {serve}" if serve else url
    print(f"Gates for {where}, at " + ", ".join(f"{w} px" for w in sizes))
    table(["width", "gate", "result", "detail"],
          [(r["width"], r["gate"], r["status"], r["detail"]) for r in results])
    failed = [r for r in results if r["status"] != "pass"]
    print(f"  {len(results) - len(failed)} of {len(results)} gates passed.")
    for line in gates.report(results):
        print(line)
    if out:
        gates.write(out, url, results)
        print(f"  Results: {out}.")
    return 1 if failed or not results else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="product-os",
                                     description="Checks an agent can't pass for itself.")
    parser.add_argument("--version", action="version", version=f"product-os {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="run the stub-agent demo and calibration")
    checking = commands.add_parser(
        "check", help="run the project's checks, or the built-in checks on a build or run folder",
        description="With no folder, run the checks the project lists in "
                    ".claude/product-os-checks.json. On this machine a check runs only once you "
                    "accepted it with product-os accept, and only as it was then. With a "
                    "folder, run the built-in checks on a build folder or a run folder with a "
                    "run.json.")
    checking.add_argument("folder", nargs="?", help="a build folder, or a run folder with a run.json")
    proving = commands.add_parser(
        "prove", help="run each check on its planted bad cases and good cases, and record the result",
        description="A check is proven when it fails every bad case and passes every good one.")
    proving.add_argument("names", nargs="*", metavar="NAME", help="the checks to prove; all by default")
    accepting = commands.add_parser(
        "accept", help="show each check's command, prove it, and let it run on this machine",
        description="Prints the command of each check the project lists, proves it as prove "
                    "does, and keeps the proof in product-os-checks-accepted.json beside your own "
                    "config. From then on, check runs it here until it or its cases change.")
    accepting.add_argument("names", nargs="*", metavar="NAME", help="the checks to accept; all by default")
    for sub in (checking, proving, accepting):
        sub.add_argument("--project", help="the project folder; by default the nearest folder up "
                         "from $CLAUDE_PROJECT_DIR, else from here, with a .claude/product-os-checks.json, "
                         "never from inside the plugin's own folder")
        sub.add_argument("--base", metavar="REF", help="a git ref, such as origin/main, whose checks "
                         "the project has to keep, with their cases unchanged")
    checking.add_argument("--prove", action="store_true", help="run each check's cases again "
                          "instead of trusting its record; use this in CI")
    checking.add_argument("--run-listed", action="store_true", help="run every check the "
                          "project lists, accepted or not, and count the project's own proof "
                          "records; for CI, which has no accepted checks")
    proving.add_argument("--check", metavar="FILE", help="prove the checks in FILE, such as "
                         "checks/<name>.json, before they are listed; the same entry counts once "
                         "it is listed")
    gating = commands.add_parser(
        "gates", help="measure keyboard use, visible focus, overflow, image sharpness and reduced "
        "motion on the build at URL, at each width the design draws",
        description="Open URL at each width and fail what can be measured: something a mouse can "
                    "click that Tab can't reach, a Tab stop that doesn't show focus, an element "
                    "that runs past the right edge, a blurry or broken image, and motion that "
                    "keeps running with reduced motion asked for. Needs Playwright.")
    gating.add_argument("url", help="the build, such as http://localhost:3000/; with --serve, a "
                        "path on it, such as /")
    gating.add_argument("--serve", metavar="FOLDER", help="serve a built site's folder, such as "
                        "dist, on 127.0.0.1 and check it; a check can name {target} here")
    gating.add_argument("--baseline", default=design.FOLDER, metavar="FOLDER", help="the baseline "
                        f"whose frames give the widths; {design.FOLDER} by default")
    gating.add_argument("--width", type=int, action="append", metavar="PX", help="a width to "
                        "check, instead of the frames'; repeat it for more. With neither, 1280 "
                        "and 390")
    gating.add_argument("--only", action="append", choices=gates.GATES, metavar="GATE",
                        help=f"run only this gate; repeat it for more. The gates: {', '.join(gates.GATES)}")
    gating.add_argument("--scale", type=float, default=gates.SCALE, metavar="N", help="the screen "
                        f"density images have to be sharp at; {gates.SCALE} by default")
    gating.add_argument("--json", metavar="FILE", help="write every result and finding to FILE")
    designing = commands.add_parser(
        "design", help="record a Figma design as a baseline, and exercise a build in the states "
        "it draws")
    parts = designing.add_subparsers(dest="design_command", required=True)
    importing = parts.add_parser(
        "import", help="record the frames in a saved REST API answer as the baseline",
        description="Save the frames in a GET /v1/files/:key/nodes?ids=<frames> answer to the "
                    "baseline, leaving out hidden layers.")
    importing.add_argument("nodes", metavar="NODES.json", help="the answer for the frames")
    importing.add_argument("--sets", metavar="SETS.json", help="the answer for the component "
                           "sets the frames use, so the variants they don't show are known")
    importing.add_argument("--file-key", metavar="KEY", help="the file's key, to record")
    listing = parts.add_parser(
        "states", help="list every state the design draws for the build to reach")
    listing.add_argument("--json", action="store_true", help="print the states as JSON")
    exercising = parts.add_parser(
        "exercise", help="drive the build at URL into each state and report whether it responded",
        description="Open URL as wide as each frame, drive it into each state the design draws, "
                    "and report whether its look changed. A change shows the state exists, not "
                    "that it matches the design. Needs Playwright.")
    exercising.add_argument("url", help="the build, such as http://localhost:3000/ or a file:// "
                            "URL; with --serve, a path on it, such as /")
    exercising.add_argument("--serve", metavar="FOLDER", help="serve a built site's folder, such "
                            "as dist, on 127.0.0.1 and exercise it; a check can name {target} here")
    exercising.add_argument("--selectors", metavar="FILE", help="a JSON object from a Figma node "
                            "id, or a component set's id or name, to a CSS selector, for nodes "
                            "without a data-figma-node attribute. A set's selector matches its "
                            "instances in the frame's layer order")
    exercising.add_argument("--evidence", metavar="FOLDER", help="save each state's before and "
                            "after screenshots, and results.json, in FOLDER")
    exercising.add_argument("--accept", metavar="FILE", help="a JSON list of the drawn states "
                            "the project built differently on purpose, each {\"node\", \"state\", "
                            "\"why\"}; one that fails is reported as accepted, with its why")
    exercising.add_argument("--wait", type=float, default=5.0, metavar="SECONDS", help="how long "
                            "to watch a timed state for a change; 5 by default")
    drifting = parts.add_parser(
        "drift", help="say whether the design moved in Figma since the baseline",
        description="With --meta, compare the file's last edit with the one the baseline is "
                    "known to match: one cheap call. With NODES.json, a fresh GET "
                    "/v1/files/:key/nodes answer, say which frames moved. Exit 1 when one did.")
    drifting.add_argument("nodes", nargs="?", metavar="NODES.json",
                          help="a fresh answer for the frames")
    for sub in (importing, drifting):
        sub.add_argument("--meta", metavar="META.json", help="an answer to GET "
                         "/v1/files/:key/meta, read before the nodes, to record or compare the "
                         "file's last edit")
    for sub in (listing, exercising, importing, drifting):
        sub.add_argument("--baseline", default=design.FOLDER, metavar="FOLDER",
                         help=f"the baseline folder; {design.FOLDER} by default")
    for sub in (listing, exercising):
        sub.add_argument("--frame", action="append", metavar="ID", help="only this frame; "
                         "repeat for more. Every frame by default")
    args = parser.parse_args(argv)
    if args.command == "design":
        if args.design_command == "states":
            return run_states(args.baseline, args.frame, args.json)
        if args.design_command == "import":
            return run_import(args.baseline, args.nodes, args.sets, args.file_key, args.meta)
        if args.design_command == "drift":
            if not (args.nodes or args.meta):
                parser.error("design drift needs NODES.json, --meta META.json or both")
            return run_drift(args.baseline, args.nodes, args.meta)
        return run_exercise(args.baseline, args.url, args.frame, args.selectors, args.evidence,
                            args.wait, args.serve, args.accept)
    if args.command == "check" and args.folder:
        if args.base or args.prove or args.run_listed or args.project is not None:
            parser.error("--base, --prove, --run-listed and --project are for a project's "
                         "checks, not a folder")
        return run_check(args.folder)
    if args.command == "check":
        return run_project(args.project, args.base, args.prove, args.run_listed)
    if args.command == "accept":
        if project.hooks.agent_shell(os.environ):
            line = " ".join(["product-os accept", *args.names])
            print(f"product-os: accepting is {project.hooks.PERSON}. This ran in an agent's shell, "
                  "so nothing was accepted. Give the person the line to run in a terminal they "
                  f"opened themselves, once they have read each check's command in "
                  f"{project.hooks.CONFIG.as_posix()}: {line}", file=sys.stderr)
            return 2
        return run_prove(args.project, args.names, args.base, accept=True)
    if args.command == "gates":
        return run_gates(args.url, args.serve, args.baseline, args.width, args.only, args.scale,
                         args.json)
    if args.command == "prove":
        if args.check and (args.names or args.base):
            parser.error("--check proves the checks in its file; leave out NAME and --base")
        return run_prove(args.project, args.names, args.base, args.check)
    return demo()
