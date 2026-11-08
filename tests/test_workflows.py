"""Hold the GitHub workflows to the CI rules in docs/checks.md, "CI and what it costs".

- A job that asks for an id token never runs on a pull request, a fork's included. Its
  workflow runs only on a push of a release tag starting with v.
- No workflow names an API key: the paid jobs sign in through workload identity federation.
- Every job runs on a standard GitHub-hosted runner, never a larger one.

PyYAML isn't a dependency, so the workflows are read by indentation, which is enough for
the keys these rules need. Each rule is first shown to fail a planted bad workflow and
pass a good one.
"""
import base64
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# The labels of GitHub's standard hosted runners this repository may use. A larger runner
# has a label of its own, such as ubuntu-latest-4-cores or macos-latest-xlarge, so it isn't here.
STANDARD = {
    "ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04",
    "macos-latest", "macos-15", "macos-14",
    "windows-latest", "windows-2025", "windows-2022",
}
PULL_REQUEST_EVENTS = {"pull_request", "pull_request_target", "workflow_run"}
KEY = re.compile(r"^([A-Za-z0-9_-]+|\"[^\"]*\"|'[^']*'):(?:\s+(.*))?$")


def _strip_comment(line):
    """The line without a trailing # comment, keeping a # inside quotes."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def tree(text):
    """Each non-blank line as (text, children), nested by indentation."""
    root = []
    stack = [(-1, root)]
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        node = (line.strip(), [])
        while stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((indent, node[1]))
    return root


def kv(text):
    """(key, value) for a `key: value` line, or (None, None)."""
    m = KEY.match(text[2:] if text.startswith("- ") else text)
    if not m:
        return None, None
    return m.group(1).strip("\"'"), (m.group(2) or "").strip()


def child(nodes, key):
    """(value, children) of the first node with this key, or (None, [])."""
    for text, children in nodes:
        k, v = kv(text)
        if k == key:
            return v, children
    return None, []


def flow_list(value):
    """The items of `[a, "b"]`, or the one bare value."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [v.strip().strip("\"'") for v in value.split(",") if v.strip()]


def triggers(nodes):
    """{event: children} for the workflow's `on:`."""
    value, children = child(nodes, "on")
    if value is None:
        value, children = child(nodes, "true")  # YAML 1.1 reads a bare on as true
    if value:
        return {event: [] for event in flow_list(value)}
    return {kv(text)[0]: sub for text, sub in children}


def grants_id_token(nodes):
    value, children = child(nodes, "permissions")
    if value == "write-all":
        return True
    return child(children, "id-token")[0] == "write"


def jobs(nodes):
    """{job id: children}."""
    return {kv(text)[0]: sub for text, sub in child(nodes, "jobs")[1]}


def runners(job):
    """Every runner label the job can ask for."""
    value, children = child(job, "runs-on")
    if value is None:
        return []
    if children or value.startswith("["):
        return [value or "a runner group"]
    value = value.strip("\"'")
    if value.replace(" ", "") != "${{matrix.os}}":
        return [value]
    matrix = child(child(job, "strategy")[1], "matrix")[1]
    labels = []
    os_value, os_items = child(matrix, "os")
    if os_value:
        labels += flow_list(os_value)
    labels += [text[2:].strip().strip("\"'") for text, _ in os_items if text.startswith("- ")]
    for text, sub in child(matrix, "include")[1]:
        m = re.search(r"\bos:\s*([^,}\s]+)", text)
        if m:
            labels.append(m.group(1).strip("\"'"))
        labels += [v.strip("\"'") for k, v in map(lambda n: kv(n[0]), sub) if k == "os"]
    return labels


def problems(name, text):
    """What breaks the CI rules in one workflow, one line each."""
    found = []
    if "ANTHROPIC_API_KEY" in text:
        found.append(f"{name}: names ANTHROPIC_API_KEY; the paid jobs sign in through federation")
    nodes = tree(text)
    events = triggers(nodes)
    top_grants = grants_id_token(nodes)
    for job_id, job in jobs(nodes).items():
        if top_grants or grants_id_token(job):
            for event in sorted(set(events) & PULL_REQUEST_EVENTS):
                found.append(f"{name}: job {job_id} asks for an id token and runs on {event}")
            for event in sorted(set(events) - {"push"} - PULL_REQUEST_EVENTS):
                found.append(f"{name}: job {job_id} asks for an id token and runs on {event}, not only on a tag push")
            push = events.get("push")
            if push is not None:
                tags = child(push, "tags")[0]
                if child(push, "branches")[0] is not None or child(push, "branches")[1] or not tags \
                        or not all(t.startswith("v") for t in flow_list(tags)):
                    found.append(f"{name}: job {job_id} asks for an id token on a push that isn't only a v tag")
        for label in runners(job):
            if label not in STANDARD:
                found.append(f"{name}: job {job_id} runs on {label}, not a standard GitHub-hosted runner")
    return found


GOOD = """\
name: paid
on:
  push:
    tags: ["v*"]
permissions:
  contents: read
jobs:
  evals:
    runs-on: ${{ matrix.os }}
    permissions:
      contents: read
      id-token: write   # for the OIDC token
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            tools: Bash
          - { os: windows-latest, tools: Edit }
    steps:
      - run: echo "# not a comment" && echo ok
"""

FREE = """\
name: free
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        exclude:
          - { os: macos-latest-xlarge }
        include:
          - { os: ubuntu-24.04, python-version: "3.9" }
  lint:
    runs-on: ubuntu-latest
"""

BAD = {
    "id token on a pull request": GOOD.replace('    tags: ["v*"]\n', '    tags: ["v*"]\n  pull_request:\n'),
    "id token on pull_request_target": GOOD.replace("  push:\n", "  pull_request_target:\n  push:\n"),
    "id token for the whole workflow, on a pull request": FREE.replace("jobs:\n", "permissions:\n  id-token: write\njobs:\n"),
    "write-all on a pull request": FREE.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    permissions: write-all\n"),
    "id token, triggers inline": GOOD.replace('on:\n  push:\n    tags: ["v*"]\n', "on: [push, pull_request]\n"),
    "id token by hand": GOOD.replace("  push:\n", "  workflow_dispatch:\n  push:\n"),
    "id token on a branch push": GOOD.replace('    tags: ["v*"]\n', '    tags: ["v*"]\n    branches: [main]\n'),
    "id token on every push": GOOD.replace('  push:\n    tags: ["v*"]\n', "  push:\n"),
    "API key in a step": GOOD.replace("      - run: echo", "      - env:\n          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}\n        run: echo"),
    "a larger runner": FREE.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest-4-cores\n"),
    "a larger runner in the matrix": FREE.replace("os: [ubuntu-latest, macos-latest]", "os: [ubuntu-latest, macos-latest-xlarge]"),
    "a larger runner in an include": GOOD.replace("{ os: windows-latest,", "{ os: windows-latest-8-cores,"),
    "a larger runner in a block include": GOOD.replace("- os: ubuntu-latest", "- os: ubuntu-latest-16-cores"),
    "a runner group": FREE.replace("    runs-on: ubuntu-latest\n", "    runs-on:\n      group: large\n"),
}


class TheRules(unittest.TestCase):
    def test_a_good_paid_workflow_and_a_free_one_pass(self):
        self.assertEqual(problems("good", GOOD), [])
        self.assertEqual(problems("free", FREE), [])

    def test_each_planted_mistake_is_caught(self):
        for name, text in BAD.items():
            with self.subTest(name):
                self.assertNotEqual(text, GOOD)
                self.assertNotEqual(text, FREE)
                self.assertTrue(problems(name, text), f"{name} passed")


CEILING = re.compile(r"So a release tag costs at most \$(\d+(?:\.\d+)?)\.")


def tag_cost(live, release):
    """(the most a release tag can spend, problems): the sum of live.yml's matrix caps and
    release.yml's budgets. Each eval run in live.yml must take its runner's cap, and each runner
    must have one, so the sum is the whole of live.yml's spend."""
    found = []
    live, release = ("\n".join(_strip_comment(line) for line in text.splitlines()) for text in (live, release))
    caps = [float(c) for c in re.findall(r'^\s*cap:\s*"?(\d+(?:\.\d+)?)"?\s*$', live, re.M)]
    runners = re.findall(r"^\s*- os:", live, re.M)
    if len(caps) != len(runners):
        found.append(f"live.yml: {len(runners)} runners and {len(caps)} caps")
    evals = re.findall(r"claude plugin eval\b", live)
    capped = re.findall(r"--max-cost-usd\s+\$\{\{\s*matrix\.cap\s*\}\}", live)
    if len(capped) != len(evals) or len(re.findall(r"--max-cost-usd", live)) != len(evals):
        found.append("live.yml: each `claude plugin eval` must take --max-cost-usd ${{ matrix.cap }}")
    # evals/live.py runs the cases one by one and holds them all to its --cap.
    runners = re.findall(r"evals/live\.py\b", live)
    if len(re.findall(r"--cap\s+\$\{\{\s*matrix\.cap\s*\}\}", live)) != len(runners) \
            or len(re.findall(r"--cap\b", live)) != len(runners):
        found.append("live.yml: each `evals/live.py` must take --cap ${{ matrix.cap }}")
    if not evals and not runners:
        found.append("live.yml: no eval run found")
    budgets = [float(b) for b in re.findall(r"--max-budget-usd\s+(\d+(?:\.\d+)?)", release)]
    if len(budgets) != len(re.findall(r"\bclaude -p\b", release)):
        found.append("release.yml: each `claude -p` must take --max-budget-usd")
    return sum(caps) + sum(budgets), found


class TheCeiling(unittest.TestCase):
    """docs/checks.md says what a release tag can cost at most. The caps in the paid workflows
    have to add up to no more than that."""

    def setUp(self):
        flows = ROOT / ".github" / "workflows"
        self.live = (flows / "live.yml").read_text(encoding="utf-8")
        self.release = (flows / "release.yml").read_text(encoding="utf-8")
        self.ceiling = float(CEILING.search((ROOT / "docs" / "checks.md").read_text(encoding="utf-8")).group(1))

    def test_the_caps_fit_under_the_ceiling(self):
        total, found = tag_cost(self.live, self.release)
        self.assertEqual(found, [])
        self.assertLessEqual(total, self.ceiling)

    def test_planted_overruns_are_caught(self):
        raised = re.sub(r'cap: "8\.25"', 'cap: "9.25"', self.live)
        self.assertNotEqual(raised, self.live)
        self.assertGreater(tag_cost(raised, self.release)[0], self.ceiling)
        literal = self.live.replace("--cap ${{ matrix.cap }}", "--cap 3")
        self.assertNotEqual(literal, self.live)
        self.assertTrue(tag_cost(literal, self.release)[1])
        bare = self.live.replace("python3 evals/live.py", "claude plugin eval .")
        self.assertNotEqual(bare, self.live)
        self.assertTrue(tag_cost(bare, self.release)[1])
        uncapped = re.sub(r'\n\s*cap: "0\.50"', "", self.live)
        self.assertNotEqual(uncapped, self.live)
        self.assertTrue(tag_cost(uncapped, self.release)[1])
        unbudgeted = self.release.replace("--max-budget-usd 1.00", "")
        self.assertNotEqual(unbudgeted, self.release)
        self.assertTrue(tag_cost(self.live, unbudgeted)[1])


def tag_pattern(pattern):
    """GitHub's filter pattern for a tag, as a regex: * is any run of characters but /, ** any
    run at all, + and ? repeat what's before them, [...] is a set, anything else is itself."""
    out, i = "", 0
    while i < len(pattern):
        if pattern[i] == "[":
            end = pattern.index("]", i)
            out, i = out + pattern[i:end + 1], end + 1
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out, i = out + {"*": "[^/]*", "+": "+", "?": "?"}.get(pattern[i], re.escape(pattern[i])), i + 1
    return re.compile(out)


def runs_on_tag(text, name):
    """Whether pushing the tag name starts the workflow."""
    push = triggers(tree(text)).get("push")
    tags = child(push, "tags")[0] if push is not None else None
    return bool(tags) and any(tag_pattern(p).fullmatch(name) for p in flow_list(tags))


PROBE_TAG, RELEASE_TAG = "v0.1.4-probe.1", "v0.1.4"
PROBE_FILTER = "evals/live.py ${{ contains(github.ref_name, '-probe') && '--tag probe' || matrix.filter }}"


def probe_problems(live, release):
    """What would let a probe tag cut a release, or spend anywhere but Ubuntu's probe."""
    found = []
    if runs_on_tag(release, PROBE_TAG):
        found.append(f"release.yml runs on the probe tag {PROBE_TAG}")
    if not runs_on_tag(release, RELEASE_TAG):
        found.append(f"release.yml doesn't run on the release tag {RELEASE_TAG}")
    if not runs_on_tag(live, PROBE_TAG) or not runs_on_tag(live, RELEASE_TAG):
        found.append("live.yml doesn't run on both a probe tag and a release tag")
    job = jobs(tree(live)).get("evals", [])
    paid = child(child(job, "env")[1], "PAID")[0] or ""
    if "'-probe'" not in paid or "'ubuntu'" not in paid:
        found.append("live.yml: PAID doesn't leave out every runner but Ubuntu on a probe tag")
    for text, sub in child(job, "steps")[1]:
        key, value = kv(text)
        cond = child(sub, "if")[0] or ""
        if (key == "uses" and value.startswith("actions/checkout@")) or "env.PAID != 'true'" in cond:
            continue
        if "env.PAID == 'true'" not in cond:
            found.append(f"live.yml: the step {value} runs on a probe tag on every runner")
    if PROBE_FILTER not in live:
        found.append("live.yml: a probe tag doesn't run only the cases tagged probe")
    return found


class TheProbeTag(unittest.TestCase):
    """A tag such as v0.1.4-probe.1 runs Ubuntu's sandbox-write probe alone: no release, and no
    paid step on macOS or Windows."""

    def setUp(self):
        flows = ROOT / ".github" / "workflows"
        self.live = (flows / "live.yml").read_text(encoding="utf-8")
        self.release = (flows / "release.yml").read_text(encoding="utf-8")

    def test_a_probe_tag_runs_only_the_ubuntu_probe(self):
        self.assertEqual(probe_problems(self.live, self.release), [])

    def test_the_tag_patterns_read_as_github_reads_them(self):
        exact = tag_pattern("v[0-9]+.[0-9]+.[0-9]+")
        self.assertTrue(exact.fullmatch("v0.1.4") and exact.fullmatch("v1.10.0"))
        self.assertFalse(exact.fullmatch("v0.1.4-probe.1") or exact.fullmatch("v0x1.4"))
        self.assertTrue(tag_pattern("v*").fullmatch("v0.1.4-probe.1"))

    def test_each_planted_mistake_is_caught(self):
        guard = "if: env.PAID == 'true'\n        run: |\n          python3 evals/live.py"
        planted = {
            "release on every v tag": (self.live, re.sub(r'tags: \["v\[[^\n]*\]', 'tags: ["v*"]', self.release)),
            "the eval step unguarded": (self.live.replace(guard, "run: |\n          python3 evals/live.py"), self.release),
            "PAID on every runner": (re.sub(r"PAID: \$\{\{[^\n]*\}\}", "PAID: true", self.live), self.release),
            "the matrix filter on a probe tag": (self.live.replace(PROBE_FILTER, "evals/live.py ${{ matrix.filter }}"),
                                                 self.release),
        }
        for name, (live, release) in planted.items():
            with self.subTest(name):
                self.assertNotEqual((live, release), (self.live, self.release))
                self.assertTrue(probe_problems(live, release), f"{name} passed")


def token_script(text):
    """The oidc_token.py a paid workflow's fetch step writes, as Python reads it."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "oidc_token.py\" <<'EOF'" in line)
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "EOF")
    body = lines[start + 1:end]
    cut = min(len(line) - len(line.lstrip()) for line in body if line.strip())
    return "\n".join(line[cut:] for line in body) + "\n"


def jwt(claims, signature="UExBTlRFRC1TSUdOQVRVUkU"):
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    return part({"alg": "RS256", "typ": "JWT"}) + "." + part(claims) + "." + signature


class GitHub(http.server.BaseHTTPRequestHandler):
    """A planted GitHub token endpoint: the server's answer is (status, body)."""
    answer = (200, b"{}")

    def do_GET(self):
        status, body = self.server.answer
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TheTokenScript(unittest.TestCase):
    """The paid jobs' token script replaces the token file only with a JWT it checked, and says
    why when it can't. Before, a refresh wrote GitHub's missing value as the word null, or any
    other answer, over a good token, and warned about neither."""

    CLAIMS = {"sub": "repo:owner@1/product-os@2:ref:refs/tags/v0.1.1", "ref": "refs/tags/v0.1.1",
              "event_name": "push", "iat": 1_700_000_000, "exp": 1_700_000_300}

    def setUp(self):
        flows = ROOT / ".github" / "workflows"
        self.script = token_script((flows / "live.yml").read_text(encoding="utf-8"))
        self.other = token_script((flows / "release.yml").read_text(encoding="utf-8"))
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "oidc_token.py").write_text(self.script, encoding="utf-8")
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GitHub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.file = self.folder / "gha-jwt"

    def fetch(self, status, body, *flags):
        self.server.answer = (status, body if isinstance(body, bytes) else json.dumps(body).encode())
        env = dict(os.environ, ACTIONS_ID_TOKEN_REQUEST_TOKEN="planted",
                   ACTIONS_ID_TOKEN_REQUEST_URL=f"http://127.0.0.1:{self.server.server_port}/token?api-version=2.0")
        done = subprocess.run([sys.executable, str(self.folder / "oidc_token.py"), str(self.file), *flags],
                              capture_output=True, text=True, env=env, timeout=60)
        return done.returncode, done.stdout + done.stderr

    def test_both_workflows_hold_the_same_script(self):
        self.assertEqual(self.script, self.other)

    def test_a_token_is_written_and_described_never_printed(self):
        token = jwt(self.CLAIMS)
        code, out = self.fetch(200, {"count": 1, "value": token}, "--claims")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.file.read_text(encoding="utf-8"), token + "\n")
        self.assertIn("OIDC token issued 22:13:20, expires 22:18:20 UTC", out)
        self.assertIn("sub: repo:owner@1/product-os@2:ref:refs/tags/v0.1.1", out)
        for piece in token.split("."):
            self.assertNotIn(piece, out)
        if os.name != "nt":
            self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        code, out = self.fetch(200, {"value": token})
        self.assertIn("the same token as before", out)
        self.assertNotIn("sub:", out)
        code, out = self.fetch(200, {"value": jwt({**self.CLAIMS, "iat": 1_700_000_120})})
        self.assertIn("a new token", out)

    def test_a_bad_answer_keeps_the_last_token(self):
        good = jwt(self.CLAIMS)
        self.file.write_text(good + "\n", encoding="utf-8")
        cases = {"no value": (200, {"count": 0}, "GitHub's response held no value"),
                 "null": (200, {"value": None}, "GitHub's response held no value"),
                 "the word null": (200, {"value": "null"}, "GitHub's response held no value"),
                 "not a JWT": (200, {"value": "not-a-token"}, "GitHub's response is not a JWT"),
                 "refused": (403, {"message": "planted"}, "the request failed (HTTP 403)"),
                 "not JSON": (200, b"<html>", "the request failed (JSONDecodeError)")}
        for name, (status, body, why) in cases.items():
            with self.subTest(name):
                code, out = self.fetch(status, body)
                self.assertEqual(code, 1)
                self.assertIn(f"No OIDC token: {why}", out)
                self.assertEqual(self.file.read_text(encoding="utf-8"), good + "\n")


class TheWorkflows(unittest.TestCase):
    def test_the_workflows_are_there(self):
        names = {p.name for p in WORKFLOWS}
        self.assertTrue({"tests.yml", "install.yml", "live.yml", "release.yml"} <= names, names)

    def test_no_job_that_asks_for_an_id_token_runs_on_a_pull_request(self):
        for path in WORKFLOWS:
            nodes = tree(path.read_text(encoding="utf-8"))
            events = set(triggers(nodes))
            for job_id, job in jobs(nodes).items():
                if grants_id_token(nodes) or grants_id_token(job):
                    with self.subTest(f"{path.name} {job_id}"):
                        self.assertFalse(events & PULL_REQUEST_EVENTS, f"{path.name} {job_id} runs on {events}")

    def test_every_workflow_keeps_the_ci_rules(self):
        found = []
        for path in WORKFLOWS:
            found += problems(path.name, path.read_text(encoding="utf-8"))
        self.assertEqual(found, [])

    def test_the_paid_workflows_ask_for_an_id_token_and_the_free_ones_dont(self):
        asks = {}
        for path in WORKFLOWS:
            nodes = tree(path.read_text(encoding="utf-8"))
            asks[path.name] = grants_id_token(nodes) or any(grants_id_token(j) for j in jobs(nodes).values())
        self.assertEqual({n for n, a in asks.items() if a}, {"live.yml", "release.yml"})

    def test_the_free_workflows_run_on_push_and_pull_request(self):
        for name in ("tests.yml", "install.yml"):
            with self.subTest(name):
                events = triggers(tree((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")))
                self.assertTrue({"push", "pull_request"} <= set(events), events)


if __name__ == "__main__":
    unittest.main()
