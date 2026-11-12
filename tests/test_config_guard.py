"""Any agent that writes .claude/product-os-checks.json could turn the checks off.

The PreToolUse hook answers "ask" for such a call, whoever makes it, so the
user decides. Reads of the file, and writes elsewhere, are left alone. An
agent's accept, by command or by writing an accepted file, is denied, since
accepting is the person's step, even on their yes.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from product_os.hooks import DEFAULTS, reviewer_readonly

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "reviewer_readonly.py"

SHELL_WRITES = [
    "echo '{}' > .claude/product-os-checks.json",
    "echo '{}' >| ./.claude/product-os-checks.json",
    "printf '{}' >> .claude/product-os-checks.json",
    "sed -i '' 's/block-writes/block-all/' .claude/product-os-checks.json",
    "perl -pi -e 's/x/y/' .claude/product-os-checks.json",
    "rm .claude/product-os-checks.json",
    "rm -rf .claude",
    "mv .claude/product-os-checks.json .claude/off.json",
    "cp /tmp/other.json .claude/product-os-checks.json",
    "cp /tmp/other.json .claude/",
    "cp -r /tmp/elsewhere/.claude .",
    "truncate -s 0 .claude/product-os-checks.json",
    "tee .claude/product-os-checks.json < /tmp/other.json",
    "dd if=/tmp/other.json of=.claude/product-os-checks.json",
    "cd .claude && rm product-os-checks.json",
    "cd src && echo '{}' > ../.claude/product-os-checks.json",
    "rm .claude/*.json",
    "rm .claude/product-os-check?.json",
    "rm -rf .cl*",
    "F=.claude/product-os-checks.json; echo '{}' > $F",
    "echo .claude/product-os-checks.json | xargs rm",
    "find .claude -name '*.json' -delete",
    "find .claude -type f -exec rm {} +",
    "sudo rm .claude/product-os-checks.json",
    "bash -c 'echo {} > .claude/product-os-checks.json'",
    "python3 -c \"open('.claude/product-os-checks.json', 'w').write('{}')\"",
    "python3 -c \"import os; os.remove(os.path.join('.claude', 'product-os-checks' + '.json'))\"",
    "node -e \"require('fs').writeFileSync('.claude/product-os-checks.json', '{}')\"",
    "git checkout -- .claude/product-os-checks.json",
    "git restore .claude",
    "ln -sf /tmp/other.json .claude/product-os-checks.json",
    "ln -s .claude/product-os-checks.json c && echo '{}' > c",
    "rm .Claude/Product-OS-Checks.json",
    "echo 'unclosed > .claude/product-os-checks.json",
    "rm \"$CLAUDE_DIR/product-os-checks.json\"",
]


SHELL_READS = [
    "cat .claude/product-os-checks.json",
    "jq .qa_commands .claude/product-os-checks.json",
    "python3 -c \"import json; print(json.load(open('.claude/product-os-checks.json')))\"",
    "cp .claude/product-os-checks.json /tmp/backup.json",
    "grep reviewer .claude/product-os-checks.json > /tmp/found.txt",
    "git add .claude/product-os-checks.json",
    "git diff .claude/product-os-checks.json",
    "git log -p -- .claude/product-os-checks.json",
    "mkdir -p .claude",
    "ls -la .claude",
    "echo hi > notes.md",
    "rm -rf build",
    "find src -type f -exec rm {} +",
    "rm *.json",
    "pip install product-os",
    "echo 'unclosed",
    # The file's name without .json is also the package's and the repo folder's name.
    "cd product-os && echo 'unclosed",
    "rm -rf \"$WORK/product-os\"",
    "python -m product_os demo > \"$OUT\"",
]


def event(tool, tool_input, agent=None, cwd=None):
    out = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    if agent:
        out["agent_type"] = agent
    if cwd:
        out["cwd"] = str(cwd)
    return out


def decision(output):
    return (output or {}).get("hookSpecificOutput", {}).get("permissionDecision", "allow")


def home(folder):
    """The variables ~ is read from, all set to folder: HOME on POSIX, USERPROFILE on Windows."""
    return {"HOME": str(folder), "USERPROFILE": str(folder)}


class ConfigGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "project"
        (self.project / ".claude").mkdir(parents=True)
        (self.project / "src").mkdir()
        self.config = self.project / ".claude" / "product-os-checks.json"
        self.config.write_text("{}\n")
        self.user = Path(self.tmp.name) / "home" / ".claude"
        self.user.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["CLAUDE_CONFIG_DIR"] = str(self.user)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def answer(self, tool, tool_input, agent="main", cwd=None):
        return reviewer_readonly(event(tool, tool_input, agent, cwd or self.project), dict(DEFAULTS))

    def test_shell_writes_to_the_config_ask_for_every_agent(self):
        for agent in ("main", "builder", "general-purpose"):
            for command in SHELL_WRITES:
                with self.subTest(agent=agent, command=command):
                    self.assertEqual(decision(self.answer("Bash", {"command": command}, agent)), "ask")

    def test_shell_reads_of_the_config_are_left_alone(self):
        for command in SHELL_READS:
            with self.subTest(command=command):
                self.assertIsNone(self.answer("Bash", {"command": command}))

    def test_file_tool_writes_ask_however_the_path_is_written(self):
        paths = [str(self.config), ".claude/product-os-checks.json", "./.claude/product-os-checks.json",
                 "src/../.claude/product-os-checks.json",
                 str(self.project / ".claude" / "." / "product-os-checks.json"),
                 str(self.project / ".CLAUDE" / "Product-OS-Checks.JSON")]
        for tool in ("Write", "Edit", "MultiEdit"):
            for path in paths:
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(decision(self.answer(tool, {"file_path": path})), "ask")

    def test_a_symlink_to_the_config_counts(self):
        link = self.project / "settings-link.json"
        try:
            link.symlink_to(self.config)
        except (OSError, NotImplementedError):
            self.skipTest("this file system cannot make symlinks")
        self.assertEqual(decision(self.answer("Write", {"file_path": str(link)})), "ask")
        self.assertEqual(decision(self.answer("Bash", {"command": "echo '{}' > settings-link.json"})), "ask")

    def test_other_files_and_reads_are_left_alone(self):
        for tool, tool_input in (("Write", {"file_path": str(self.project / "notes.md")}),
                                 ("Write", {"file_path": str(self.project / "docs" / "product-os-checks.json")}),
                                 ("Edit", {"file_path": str(self.project / ".claude" / "settings.json")}),
                                 ("Read", {"file_path": str(self.config)}),
                                 ("Grep", {"pattern": "reviewer", "path": str(self.config)})):
            with self.subTest(tool=tool, tool_input=tool_input):
                self.assertIsNone(self.answer(tool, tool_input))

    def test_project_dir_comes_from_the_environment_first(self):
        elsewhere = Path(self.tmp.name) / "elsewhere"
        elsewhere.mkdir()
        # Quoted, since bash reads a backslash outside quotes as an escape. Git Bash also takes C:/ and /c/.
        paths = [f"'{self.config}'", self.config.as_posix()]
        if os.name == "nt":
            paths.append("/" + self.config.drive[0].lower() + self.config.as_posix()[2:])
        for path in paths:
            with self.subTest(path=path):
                with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.project)}):
                    output = self.answer("Bash", {"command": f"rm {path}"}, cwd=elsewhere)
                self.assertEqual(decision(output), "ask")

    def test_the_reason_says_what_is_at_stake(self):
        output = self.answer("Bash", {"command": "rm .claude/product-os-checks.json"})
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(".claude/product-os-checks.json", reason)
        self.assertIn("changes the release checks", reason)
        self.assertIn("needs your OK", reason)
        self.assertIn("runs rm", reason)

    def test_writes_to_the_users_own_config_ask_too(self):
        # It decides which QA commands count, so changing it can turn the QA check off.
        for name in ("product-os-checks.json",):
            mine = self.user / name
            for tool, tool_input in (("Write", {"file_path": str(mine)}),
                                     ("Edit", {"file_path": str(mine)}),
                                     ("Bash", {"command": f"echo '{{}}' > '{mine}'"}),
                                     ("Bash", {"command": f"rm '{mine}'"}),
                                     ("Bash", {"command": f"cd '{self.user}' && sed -i '' 's/a/b/' {name}"})):
                with self.subTest(tool=tool, tool_input=tool_input):
                    output = self.answer(tool, tool_input)
                    self.assertEqual(decision(output), "ask")
                    self.assertIn("your own product-os config",
                                  output["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIsNone(self.answer("Read", {"file_path": str(mine)}))
        self.assertIsNone(self.answer("Write", {"file_path": str(self.user / "settings.json")}))

    def test_writes_to_the_proof_records_ask_and_running_prove_does_not(self):
        # A record written by hand could make a check that never caught its bad case count.
        proofs = self.project / ".claude" / "product-os-checks-proofs.json"
        proofs.write_text('{"proofs": {}}\n')
        for name in ("product-os-checks-proofs.json",):
            for tool, tool_input in (("Write", {"file_path": str(proofs.with_name(name))}),
                                     ("Edit", {"file_path": f".claude/{name}"}),
                                     ("Bash", {"command": f"echo '{{}}' > .claude/{name}"}),
                                     ("Bash", {"command": f"rm .claude/{name}"})):
                with self.subTest(tool=tool, tool_input=tool_input):
                    output = self.answer(tool, tool_input)
                    self.assertEqual(decision(output), "ask")
                    self.assertIn(name, output["hookSpecificOutput"]["permissionDecisionReason"])
        for command in ("python3 -m product_os prove", "product-os check --prove",
                        "cat .claude/product-os-checks-proofs.json", "git diff .claude/product-os-checks-proofs.json"):
            with self.subTest(command=command):
                self.assertIsNone(self.answer("Bash", {"command": command}))

    def test_an_agents_write_to_the_accepted_checks_is_refused(self):
        # Only an accepted check runs on this machine, so a hand-written entry could run anything,
        # and writing it is accepting, which is the person's step.
        accepted = self.user / "product-os-checks-accepted.json"
        for tool, tool_input in (("Write", {"file_path": str(accepted)}),
                                 ("Bash", {"command": f"echo '{{}}' > '{accepted}'"}),
                                 ("Monitor", {"command": f"echo '{{}}' > '{accepted}'"}),
                                 ("Bash", {"command": f"rm '{accepted}'"})):
            with self.subTest(tool=tool, tool_input=tool_input):
                output = self.answer(tool, tool_input)
                self.assertEqual(decision(output), "deny")
                reason = output["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn("the checks you accepted", reason)
                self.assertIn("never an agent's, even on their yes", reason)

    def test_an_agents_accept_is_refused_and_running_every_listed_check_asks(self):
        # Neither writes a file a guard sees: product-os writes the accepted file itself. Accepting
        # is the person's step, even on their yes, so an agent's is refused, in every form.
        accepts = ("product-os accept", "product-os accept no-print --project shop",
                   "python3 -m product_os accept", "cd shop && product-os accept",
                   "FOO=1 ~/.local/bin/product-os accept", "product-os check | product-os accept",
                   "product-os 'accept", "python -m product_os.__main__ accept",
                   "bash -c 'product-os accept'", "zsh -lc \"cd shop && product-os accept no-print\"",
                   "eval \"product-os accept\"", "sh -c \"bash -c 'product-os accept'\"",
                   "pwsh -NoProfile -Command product-os accept", "cmd /c product-os accept",
                   "env -u CLAUDE_CODE_CHILD_SESSION product-os accept",
                   "product-os check --run-listed && product-os accept")
        for tool in ("Bash", "PowerShell", "Monitor"):
            for command in accepts:
                with self.subTest(tool=tool, command=command):
                    output = self.answer(tool, {"command": command})
                    self.assertEqual(decision(output), "deny")
                    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
                    self.assertIn(f"refused this {tool} call", reason)
                    self.assertIn("never an agent's, even on their yes", reason)
                    self.assertIn(".claude/product-os-checks.json", reason)
        for command in ("product-os check --run-listed", "bash -c 'product-os check --run-listed'",
                        "python -m product_os check --prove --run-listed --base origin/main"):
            with self.subTest(command=command):
                output = self.answer("Bash", {"command": command})
                self.assertEqual(decision(output), "ask")
                self.assertIn("needs your OK", output["hookSpecificOutput"]["permissionDecisionReason"])
        for command in ("product-os check", "product-os check --prove --base origin/main",
                        "product-os prove", "grep accept README.md", "product-os design states",
                        "echo 'product-os accept'", "git commit -m 'product-os accept refuses agents'",
                        "bash -c 'product-os check'", "bash scripts/accept.sh"):
            with self.subTest(command=command):
                self.assertIsNone(self.answer("Bash", {"command": command}))

    def test_the_tools_settings_and_accepted_commands_ask_and_accepting_one_asks(self):
        # A command in your own settings runs without being accepted, and the accepted file decides
        # which of a project's commands run. kit_config.py keeps both in ~/.claude.
        with mock.patch.dict(os.environ, home(self.user.parent)):
            # Your own settings ask; writing the accepted commands is accepting, so it is refused.
            for name, said, decided in (("product-os.json", "your own product-os settings", "ask"),
                                        ("product-os-commands-accepted.json",
                                         "the project commands you accepted", "deny")):
                path = self.user / name
                for tool, tool_input in (("Write", {"file_path": str(path)}),
                                         ("Bash", {"command": f"echo '{{}}' > ~/.claude/{name}"}),
                                         ("Bash", {"command": f"rm '{path}'"})):
                    with self.subTest(tool=tool, tool_input=tool_input):
                        output = self.answer(tool, tool_input)
                        self.assertEqual(decision(output), decided)
                        self.assertIn(said, output["hookSpecificOutput"]["permissionDecisionReason"])
            self.assertIsNone(self.answer("Read", {"file_path": str(self.user / "product-os.json")}))
        for command in ("product-os kit_config accept retro.propose_cmd", "python3 tools/kit_config.py accept --all",
                        "python \"${CLAUDE_PLUGIN_ROOT}/tools/kit_config.py\" accept triage.sources",
                        "product-os kit_config --project . accept --all",
                        "python3 tools/kit_config.py accept --project shop app.build_cmd",
                        "bash -c 'product-os kit_config accept --all'"):
            with self.subTest(command=command):
                output = self.answer("Bash", {"command": command})
                self.assertEqual(decision(output), "deny")
                reason = output["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn("product-os.json", reason)
                self.assertIn("never an agent's, even on their yes", reason)
        for command in ("product-os kit_config", "python3 tools/kit_config.py --selftest",
                        "product-os kit_config --project ."):
            with self.subTest(command=command):
                self.assertIsNone(self.answer("Bash", {"command": command}))

    def test_without_claude_config_dir_the_users_config_is_in_home(self):
        with mock.patch.dict(os.environ, home(self.user.parent)):
            del os.environ["CLAUDE_CONFIG_DIR"]
            output = self.answer("Bash", {"command": "echo '{}' > ~/.claude/product-os-checks.json"})
        self.assertEqual(decision(output), "ask")

    def test_a_reviewer_is_still_denied(self):
        output = self.answer("Bash", {"command": "rm .claude/product-os-checks.json"}, agent="code-reviewer")
        self.assertEqual(decision(output), "deny")
        output = self.answer("Write", {"file_path": str(self.config)}, agent="code-reviewer")
        self.assertEqual(decision(output), "deny")

    def test_the_hook_script_answers_ask(self):
        payload = json.dumps(event("Bash", {"command": "echo '{}' > .claude/product-os-checks.json"},
                                   cwd=self.project))
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        done = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                              text=True, cwd=ROOT, env=env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(decision(json.loads(done.stdout)), "ask")


if __name__ == "__main__":
    unittest.main()
