"""The live eval suite's own plumbing: the fixtures its scaffolds share.

`claude plugin eval` runs a case's scaffold in <run>/home/cwd with HOME set to <run>/home and no
CLAUDE_CONFIG_DIR, then starts the session there with CLAUDE_CONFIG_DIR set to <run>/config. These
tests plant that layout and read the result the way the session's hooks do.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from product_os import hooks

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "evals" / "_fixtures" / "workspace.sh"
BUILDER = '{"builder_agents": ["main"], "qa_commands": ["python3 qa.py"]}'


def scaffold(cwd, home, config_dir=None):
    """Run builder_workspace in cwd with the environment plugin eval gives a scaffold."""
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "USERPROFILE": str(home), "TERM": "dumb"}
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    done = subprocess.run(["bash", "-c", f'. "{WORKSPACE}" && builder_workspace \'{BUILDER}\''],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    if done.returncode:
        raise AssertionError(f"the scaffold failed: {done.stderr}")


@unittest.skipIf(os.name == "nt", "the builder scaffolds run only where plugin eval grants a shell")
class AcceptQaCommands(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.root)]))

    def qa_commands(self, cwd, config_dir):
        config, problem = hooks.load_config(str(cwd), {"CLAUDE_CONFIG_DIR": str(config_dir)})
        self.assertEqual(problem, "")
        return config["qa_commands"]

    def test_plugin_eval_session_reads_the_accept(self):
        config, home = self.root / "config", self.root / "home"
        cwd = home / "cwd"
        config.mkdir()
        cwd.mkdir(parents=True)
        scaffold(cwd, home)
        self.assertEqual(self.qa_commands(cwd, config), ["python3 qa.py"])
        self.assertFalse((home / ".claude" / "product-os-checks.json").exists())

    def test_claude_config_dir_wins(self):
        config, other = self.root / "config", self.root / "mine"
        cwd = self.root / "home" / "cwd"
        config.mkdir()
        cwd.mkdir(parents=True)
        scaffold(cwd, self.root / "home", config_dir=other)
        self.assertEqual(self.qa_commands(cwd, other), ["python3 qa.py"])
        self.assertFalse((config / "product-os-checks.json").exists())

    def test_outside_plugin_eval_the_accept_goes_in_home(self):
        home, cwd = self.root / "home", self.root / "work" / "e-1a2b"
        cwd.mkdir(parents=True)
        home.mkdir()
        scaffold(cwd, home)
        data = json.loads((home / ".claude" / "product-os-checks.json").read_text(encoding="utf-8"))
        self.assertEqual(data, {"projects": {str(self.root / "work" / "e-*"): {"qa_commands": ["python3 qa.py"]}}})


def load_summarize():
    spec = importlib.util.spec_from_file_location("summarize", ROOT / "evals" / "summarize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SIGN_IN = "exit 1: API Error: Token exchange failed with status 401 (request-id req_0): Authentication failed"
GRADERS = [{"name": "built-nothing", "type": "regex", "weight": 1}, {"name": "names-route", "type": "llm", "weight": 2}]


def run(score, built, named, cost=0.03, judge=0.002, error=None, graders=True):
    marks = [{"name": "built-nothing", "passed": built}, {"name": "names-route", "passed": named}]
    return {"score": score, "turns": 1, "costUsd": cost, "judgeCostUsd": judge, "error": error,
            "graders": marks if graders else []}


def result(with_runs, without_runs):
    return {"claudeVersion": "2.1.319", "costUsd": 1.0, "durationSeconds": 600, "suite": {"threshold": 0.8},
            "aggregates": {"casesPassed": 0, "casesTotal": 1, "meanDelta": 0.6},
            "cases": [{"name": "skill-go-extra-route", "graders": GRADERS,
                       "aggregates": {"score": 0.6, "scoreWithout": 0.0, "delta": 0.6},
                       "arms": {"with": with_runs, "without": without_runs}}]}


class Summarize(unittest.TestCase):
    """macOS, v0.1.0: three with-plugin runs failed to sign in. The harness still graded them,
    the absence grader passed, and the case scored 0.60."""

    def setUp(self):
        self.summarize = load_summarize().summarize

    def row(self, text):
        return next(line for line in text.splitlines() if line.startswith("| skill-go-extra-route"))

    def test_a_run_that_never_reached_the_model_is_not_scored(self):
        signed_out = [run(0.33, True, False, cost=0.002, error=SIGN_IN) for _ in range(3)]
        text = self.summarize(result(signed_out, [run(0.0, False, False)]))
        self.assertEqual(self.row(text), "| skill-go-extra-route | n/a | 0.00 | n/a | 3 of 3, 3 not scored | 0 of 1 |")
        self.assertIn("| built-nothing | regex | 1 | 0 of 0 (3 not scored) | 0 of 1 |", text)
        self.assertIn("**3 runs not scored**", text)
        self.assertIn("- with plugin, run 1, not scored: " + SIGN_IN, text)
        self.assertIn("0 of 1 cases at or above the threshold of 0.8. Mean delta: n/a.", text)

    def test_an_api_error_with_no_grader_run_is_not_scored(self):
        api_error = run(0, False, False, cost=0, judge=0, error="exit 1: API Error: 401", graders=False)
        text = self.summarize(result([api_error, run(1.0, True, True)], []))
        self.assertTrue(self.row(text).startswith("| skill-go-extra-route | 1.00 | n/a | n/a | 1 of 2, 1 not scored |"))

    def test_each_failed_grader_names_its_reason(self):
        missing = run(0.5, True, False)
        missing["graders"][1]["explanation"] = "judge votes: FAIL FAIL PASS"
        broken = run(0.5, False, True, error="timed out after 420s")
        broken["graders"][0]["explanation"] = "pattern found (expected absent)"
        signed_out = run(0.33, True, False, cost=0.002, error=SIGN_IN)
        signed_out["graders"][1]["explanation"] = "judge votes: FAIL FAIL FAIL"
        text = self.summarize(result([missing, broken, signed_out], [run(0.0, False, False)]))
        self.assertIn("- names-route failed, with plugin, 1 run: judge votes: FAIL FAIL PASS", text)
        self.assertIn("- built-nothing failed, with plugin, 1 run: pattern found (expected absent)", text)
        self.assertIn("- names-route failed, without, 1 run: no explanation", text)
        self.assertNotIn("FAIL FAIL FAIL", text)

    def test_a_judge_skipped_at_the_cost_ceiling_is_not_graded(self):
        """In the 11-07 run, judges skipped at the cost ceiling were recorded as failed and counted in
        each run's score. Here the one grader that ran passed, so the run scores 1.00, not 0.33."""
        skipped = run(0.33, True, False)
        skipped["graders"][0]["weight"], skipped["graders"][1]["weight"] = 1, 2
        skipped["graders"][1]["explanation"] = "skipped: cost ceiling"
        skipped["skippedPaidGraders"] = True
        judged = run(1.0, True, True)
        text = self.summarize(result([skipped, judged], [run(0.0, False, False)]))
        self.assertEqual(self.row(text), "| skill-go-extra-route | 1.00 | 0.00 | +1.00 | 0 of 2 | 0 of 1 |")
        self.assertIn("| names-route | llm | 2 | 1 of 1 (1 not graded) | 0 of 1 |", text)
        self.assertIn("- names-route not graded, with plugin, 1 run: skipped: cost ceiling", text)
        self.assertNotIn("names-route failed, with plugin", text)
        self.assertIn("**1 run with graders skipped**", text)

    def test_a_failed_run_says_what_it_did(self):
        """The judge records votes, not reasons. In v0.1.1, check-page with the plugin failed
        not-pass on Linux with nothing in the summary to say why."""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJyZXBvOngifQ.c2lnbmF0dXJl"
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Checking the baseline."},
                {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": "git diff main -- qa-baseline.json"}},
                {"type": "tool_use", "id": "t2", "name": "Agent",
                 "input": {"subagent_type": "product-os:page-qa", "description": "QA the page"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                                      "content": "+ OVERFLOW .plans at 390"}]}},
            {"type": "assistant", "parent_tool_use_id": "t2", "message": {"content": [
                {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "curl -s localhost:8765"}}]}},
            {"type": "system", "subtype": "permission_denied", "tool_use_id": "t3", "decision_reason_type": "mode",
             "message": "denied"},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "is_error": True,
                                                      "content": [{"type": "text", "text": f"token {jwt}"}]}]}},
            {"type": "result", "subtype": "success", "result": "VERDICT: PASS (0 BLOCKER)"}]
        trace = folder / "trace.jsonl"
        trace.write_text("".join(json.dumps(event) + "\n" for event in events) + "not json\n", encoding="utf-8")
        failed = run(0.5, True, False)
        failed["tracePath"] = str(trace)
        passed = run(1.0, True, True)
        passed["tracePath"] = str(trace)
        gone = run(0.5, True, False)
        gone["tracePath"] = str(folder / "removed.jsonl")
        text = self.summarize(result([failed, passed, gone], []))
        self.assertEqual(text.count("<details>"), 1)
        self.assertIn("<details><summary>with plugin, run 1, failed names-route: what it did</summary>", text)
        self.assertIn("Bash: git diff main -- qa-baseline.json -> + OVERFLOW .plans at 390\n", text)
        self.assertIn("Agent: product-os:page-qa: QA the page -> error: token [masked]\n", text)
        self.assertIn("\n    Bash: curl -s localhost:8765 -> DENIED (mode)\n", text)
        self.assertIn("last reply: VERDICT: PASS (0 BLOCKER)\n", text)
        self.assertNotIn(jwt.split(".")[1], text)

    def test_a_run_that_worked_then_timed_out_is_scored(self):
        timed_out = run(0.33, True, False, error="timed out after 420s")
        text = self.summarize(result([timed_out, run(1.0, True, True)], [run(0.0, False, False)]))
        self.assertEqual(self.row(text), "| skill-go-extra-route | 0.67 | 0.00 | +0.67 | 1 of 2 | 0 of 1 |")
        self.assertIn("| names-route | llm | 2 | 1 of 2 | 0 of 1 |", text)
        self.assertIn("- with plugin, run 1: timed out after 420s", text)


FAKE_CLAUDE = r'''
import json, os, stat, sys
args = sys.argv[1:]
cache = os.environ["CLAUDE_CODE_FEDERATION_CACHE_DIR"]
record = {"case": args[args.index("--case") + 1], "cap": args[args.index("--max-cost-usd") + 1],
          "token": open(os.environ["ANTHROPIC_IDENTITY_TOKEN_FILE"]).read(), "cache": cache,
          "cache_empty": os.listdir(cache) == [], "cache_mode": stat.S_IMODE(os.stat(cache).st_mode)}
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(record) + "\n")
cost = float(os.environ["FAKE_COST"])
doc = {"claudeVersion": "9.9.9", "costUsd": cost, "cases": [{"name": record["case"], "arms": {}}]}
open(args[args.index("--json") + 1], "w").write(json.dumps(doc))
'''

FAKE_FETCH = r'''
import os, sys
path, count = sys.argv[1], sys.argv[2]
n = int(open(count).read()) + 1 if os.path.exists(count) else 1
open(count, "w").write(str(n))
open(path, "w").write(f"token-{n}")
'''


class LiveRunner(unittest.TestCase):
    """evals/live.py runs each case as its own `claude plugin eval`, after a new GitHub token and
    with an empty federation cache, and holds them all to one cap."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "claude.py").write_text(FAKE_CLAUDE, encoding="utf-8")
        (self.folder / "fetch.py").write_text(FAKE_FETCH, encoding="utf-8")
        self.log = self.folder / "calls.jsonl"

    def live(self, cap, cost, *tags):
        token = self.folder / "gha-jwt"
        env = dict(os.environ, FAKE_LOG=str(self.log), FAKE_COST=str(cost), ANTHROPIC_IDENTITY_TOKEN_FILE=str(token))
        out = self.folder / "live.json"
        done = subprocess.run(
            [sys.executable, str(ROOT / "evals" / "live.py"), "--json", str(out), "--cap", str(cap),
             "--tools", "Edit", "Write", *(["--tag", *tags] if tags else []),
             "--fetch", sys.executable, str(self.folder / "fetch.py"), str(token), str(self.folder / "count"),
             "--claude", sys.executable, str(self.folder / "claude.py")],
            capture_output=True, text=True, env=env, timeout=120)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return done.returncode, json.loads(out.read_text(encoding="utf-8")), calls

    def test_each_case_signs_in_afresh(self):
        code, doc, calls = self.live(1.0, 0.05, "no-shell")
        self.assertEqual([c["case"] for c in calls], ["reviewer-edit", "reviewer-subagent-edit"])
        self.assertEqual([c["token"] for c in calls], ["token-1", "token-2"])
        self.assertEqual(len({c["cache"] for c in calls}), 2)
        self.assertTrue(all(c["cache_empty"] for c in calls))
        if os.name != "nt":
            self.assertEqual({c["cache_mode"] for c in calls}, {0o700})
        self.assertFalse(any(Path(c["cache"]).exists() for c in calls))
        self.assertEqual(code, 0)
        self.assertEqual([c["name"] for c in doc["cases"]], ["reviewer-edit", "reviewer-subagent-edit"])
        self.assertAlmostEqual(doc["costUsd"], 0.10)
        self.assertFalse(doc["partial"])

    def test_the_cap_holds_across_cases(self):
        code, doc, calls = self.live(0.10, 0.06, "builder")
        self.assertEqual([(c["case"], c["cap"]) for c in calls], [("builder-piped-qa", "0.10"), ("builder-qa-fails", "0.04")])
        self.assertEqual(code, 1)
        self.assertTrue(doc["partial"])
        self.assertEqual(doc["partialReason"], "cost_ceiling: builder-skips-qa, builder-subagent-skips-qa")

    def test_no_tag_runs_every_case(self):
        names = sorted(p.name for p in (ROOT / "evals").iterdir() if (p / "case.yaml").is_file())
        code, doc, calls = self.live(100, 0.01)
        self.assertEqual([c["case"] for c in calls], names)
        self.assertEqual(len(names), 27)


if __name__ == "__main__":
    unittest.main()
