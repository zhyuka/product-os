"""The plugin files have the fields Claude Code's plugin and marketplace references require.

claude plugin validate is the full check. This one runs without Claude Code, in CI.
"""
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

import product_os
from product_os import hooks as hooks_module
from product_os import plugin

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
RESERVED = re.compile(r"(claude|anthropics?|cc-plugin)-|(claude|anthropics?|claude-code|claude-mods)$")


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class PluginFilesTest(unittest.TestCase):
    def test_plugin_manifest(self):
        plugin = load(".claude-plugin/plugin.json")
        self.assertRegex(plugin["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertIsNone(RESERVED.match(plugin["name"]))
        self.assertTrue(plugin["author"]["name"])
        self.assertEqual(plugin["version"], re.search(r'version = "(.+)"',
                                                      (ROOT / "pyproject.toml").read_text()).group(1))
        self.assertEqual(plugin["version"], product_os.__version__)

    def test_agent_plugins_manifest(self):
        # The Agent Plugins 1.0 manifest that VS Code, Copilot, Cursor and Codex read. Its field
        # list is closed, and a client rejects a plugin whose manifest breaks the schema.
        portable, claude = load("plugin.json"), load(".claude-plugin/plugin.json")
        self.assertEqual(portable["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertLessEqual(set(portable), {"$schema", "name", "version", "description", "homepage",
                                             "repository", "license", "author", "keywords", "extensions"})
        self.assertLessEqual(set(portable["author"]), {"name", "email", "url"})
        self.assertRegex(portable["name"], r"^[a-z0-9]([a-z0-9.-]{0,62}[a-z0-9])?$")
        self.assertNotRegex(portable["name"], r"--|\.\.")
        for key in ("name", "version", "homepage", "repository", "license", "author"):
            self.assertEqual(portable[key], claude[key], key)
        self.assertFalse((ROOT / "mcp.json").exists(), "the plugin starts no MCP server")

    def test_marketplace_lists_this_plugin_from_the_repo_root(self):
        market, plugin = load(".claude-plugin/marketplace.json"), load(".claude-plugin/plugin.json")
        self.assertTrue(NAME.fullmatch(market["name"]))
        self.assertTrue(market["owner"]["name"])
        [entry] = market["plugins"]
        self.assertEqual(entry["name"], plugin["name"])
        self.assertEqual(entry["version"], plugin["version"])
        self.assertTrue(entry["source"].startswith("./") and ".." not in entry["source"])

    def test_the_module_runs_and_the_command_is_registered(self):
        done = subprocess.run([sys.executable, "-m", "product_os", "--version"], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, f"product-os {product_os.__version__}"))
        scripts = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('product-os = "product_os.cli:main"', scripts)

    def test_hook_commands_run_the_launcher_and_differ_only_in_the_hook_name(self):
        hooks = load("hooks/hooks.json")["hooks"]
        names = {"SessionStart": "session_status", "PreToolUse": "reviewer_readonly",
                 "Stop": "qa_before_done", "SubagentStop": "qa_before_done"}
        self.assertEqual(set(hooks), set(names))
        shapes = set()
        for event, groups in hooks.items():
            [group] = groups
            [handler] = group["hooks"]
            self.assertEqual(handler["type"], "command")
            self.assertNotIn("args", handler)  # exec form can't pick the interpreter per platform
            self.assertNotIn("${user_config.", handler["command"])  # rejected in shell form
            sh_line, ps_line = handler["command"].split("\n")
            words = shlex.split(sh_line.replace("${CLAUDE_PLUGIN_ROOT}", ROOT.as_posix()))
            self.assertEqual(words, ["exec", "sh", (ROOT / "hooks" / "run.sh").as_posix(), names[event]])
            self.assertEqual(ps_line, "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "
                                      f'"$env:CLAUDE_PLUGIN_ROOT/hooks/run.ps1" {names[event]}')
            shapes.add(handler["command"].replace(names[event], "HOOK"))
        self.assertEqual(len(shapes), 1, "the four hook commands should differ only in the hook name")
        self.assertEqual(set(names.values()) - {"session_status"}, set(plugin.SCRIPTS))
        self.assertTrue(all(path.is_file() for path in plugin.SCRIPTS.values()))

    def test_each_hook_command_line_runs_one_program_it_names(self):
        # The plugin directory's validator reads a hook command as shell. It blocks one whose
        # program comes from a variable or an expression, since that could be any package launcher.
        for event, groups in load("hooks/hooks.json")["hooks"].items():
            for line in groups[0]["hooks"][0]["command"].split("\n"):
                with self.subTest(event=event, line=line[:30]):
                    words = list(shlex.shlex(line, posix=True, punctuation_chars=";|&"))
                    self.assertRegex(words[0], r"^[A-Za-z][A-Za-z0-9._-]*$")
                    self.assertEqual([w for w in words if set(w) <= set(";|&")], [], "one program per line")
        # A PowerShell script that names $input reads all of stdin before it starts, so no Python
        # it runs would get the hook input.
        self.assertNotRegex((ROOT / "hooks" / "run.ps1").read_text(encoding="utf-8"), r"(?i)\$input\b")

    def test_unset_plugin_options_mean_the_defaults(self):
        options = load(".claude-plugin/plugin.json")["userConfig"]
        self.assertEqual(set(options), {*hooks_module.LIST_OPTIONS, "reviewer_shell", "session_status"})
        for key in hooks_module.LIST_OPTIONS:
            self.assertEqual(options[key]["default"], ", ".join(hooks_module.DEFAULTS[key]), key)
        self.assertEqual(options["reviewer_shell"]["default"], hooks_module.DEFAULTS["reviewer_shell"])
        self.assertEqual(options["session_status"]["default"], plugin.STATUS_MODES[0])
        for option in options.values():
            self.assertEqual(option["type"], "string")
            self.assertNotIn("options", option)  # a fixed list needs Claude Code 2.1.271 to load at all

    def test_pre_tool_use_matches_every_tool_the_hook_handles(self):
        [group] = load("hooks/hooks.json")["hooks"]["PreToolUse"]
        self.assertEqual(set(group["matcher"].split("|")),
                         {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "PowerShell", "Agent"})

    def test_each_skill_has_a_description(self):
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual([path.parent.name for path in skills],
                         ["ado", "ambition", "build-change", "build-from-design", "check", "check-page",
                          "deliver-change", "figma-writes", "go", "humanize", "intent", "miss-to-check",
                          "open-question", "recall", "reconcile", "retro", "review", "review-change",
                          "setup-kit", "spec", "triage"])
        for path in skills:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), path)
            self.assertRegex(text.split("---")[1], r"\nname: " + re.escape(path.parent.name) + r"\n", path)
            self.assertRegex(text.split("---")[1], r"\ndescription: \S", path)

    def test_a_skill_only_a_person_may_start_says_it_is_already_running(self):
        # Claude Code expands /product-os:<name> before the model's first turn. A Skill call for it
        # after that is refused for a skill with disable-model-invocation, and the refusal tells the
        # model to ask the person to type the command, which ends the run. The opening says so first.
        checked = []
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            front, body = path.read_text(encoding="utf-8").split("---", 2)[1:]
            if not re.search(r"^disable-model-invocation:\s*true\s*$", front, re.M):
                continue
            name = path.parent.name
            opening = body.split("\n## ", 1)[0]
            self.assertIn(f"`/product-os:{name}`", opening, path)
            self.assertIn(f"Don't call the Skill tool for {name}.", opening, path)
            checked.append(name)
        if not checked:
            self.skipTest("no skill sets disable-model-invocation")

    def test_each_retro_setting_that_runs_something_needs_accepting_from_a_project(self):
        # kit_config.py withholds a project's command settings until they're accepted; a retro key
        # whose row says it runs a command must be one of them.
        spec = importlib.util.spec_from_file_location("kit_config", ROOT / "tools" / "kit_config.py")
        kit_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kit_config)
        text = (ROOT / "skills" / "retro" / "references" / "config.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (`[^|]+`) \| [^|]+ \| (.+) \|$", text, re.M)
        running = [(key, what) for keys, what in rows for key in re.findall(r"`([^`]+)`", keys)
                   if key.endswith("_cmd") or re.search(r"\bcmd\b|\bcommands?\b|\bscripts\b", what)]
        self.assertGreaterEqual(len(running), 10)
        for key, what in running:
            with self.subTest(key=key):
                self.assertTrue(kit_config.runs(("retro", key)), what)
        self.assertFalse(kit_config.runs(("retro", "report")))

    def test_the_reviewer_agent_is_read_only_by_the_default_settings(self):
        # The review skill starts product-os:reviewer. The reviewer hook keeps it from writing,
        # and where hooks don't run, its tool list has no file-writing tool.
        text = (ROOT / "agents" / "reviewer.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        self.assertRegex(front, r"\nname: reviewer\n")
        agent = f"{load('.claude-plugin/plugin.json')['name']}:reviewer"
        self.assertTrue(hooks_module.matches(agent, hooks_module.DEFAULTS["reviewer_agents"]))
        tools = re.search(r"\ntools: (.+)\n", front).group(1).split(", ")
        self.assertEqual([t for t in tools if t in ("Edit", "Write", "MultiEdit", "NotebookEdit")], [])
        self.assertIn(f"`{agent}`", (ROOT / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8"))
        # Hooks don't run everywhere, so the tool list is the rule: the reviewer only reads, and
        # no reviewing agent has a file-writing tool.
        self.assertEqual(tools, ["Read", "Grep", "Glob"])
        for name in ("page-qa", "section-reviewer"):
            with self.subTest(agent=name):
                front = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8").split("---")[1]
                listed = re.search(r"\ntools: (.+)\n", front).group(1).split(", ")
                self.assertEqual([t for t in listed if t in ("Edit", "Write", "MultiEdit", "NotebookEdit")], [])
        self.assertTrue(hooks_module.matches("product-os:section-reviewer", hooks_module.DEFAULTS["reviewer_agents"]))
        # page-qa keeps Bash to serve and measure, which the hook would block, so check-page holds its
        # rule: it records what the agent could change before starting it and compares after.
        page_qa = (ROOT / "agents" / "page-qa.md").read_text(encoding="utf-8")
        self.assertIn("\n  - check-page\n", page_qa)
        check_page = (ROOT / "skills" / "check-page" / "SKILL.md").read_text(encoding="utf-8")
        record, start, compare = (check_page.index(s) for s in (
            '/bin/product-os" qa_snapshot record', "Start the `product-os:page-qa` agent",
            '/bin/product-os" qa_snapshot compare'))
        self.assertLess(record, start)
        self.assertLess(start, compare)

    def test_ci_templates_install_this_release_and_prove_the_checks(self):
        # The checker comes from a fixed release outside the project, so a change can't edit it.
        for name in ("github-actions.yml", "azure-pipelines.yml"):
            text = (ROOT / "ci" / name).read_text(encoding="utf-8")
            self.assertIn(f'"product-os @ git+https://github.com/zhyuka/product-os'
                          f'@v{product_os.__version__}"', text, name)
            self.assertIn("product-os check --prove --run-listed --base", text, name)
        self.assertIn("ci/pre-push text eol=lf", (ROOT / ".gitattributes").read_text().splitlines())
        self.assertNotIn(b"\r", (ROOT / "ci" / "pre-push").read_bytes())

    def test_shell_scripts_keep_lf_line_endings(self):
        self.assertIn("*.sh text eol=lf", (ROOT / ".gitattributes").read_text().splitlines())
        self.assertNotIn(b"\r", (ROOT / "hooks" / "run.sh").read_bytes())


if __name__ == "__main__":
    unittest.main()
