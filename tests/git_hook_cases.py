"""Planted cases for ci/pre-push and ci/pre-commit, the hooks setup-kit installs, run against this
repo's own launcher (bin/product-os). HOME is a temp folder, so nothing touches the real ~/.claude.
tests/test_git_hooks.py runs it."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
CI = PLUGIN / "ci"
results = []


def sh(cmd, cwd, env, input=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, input=input,
                       stdin=None if input is not None else subprocess.DEVNULL, timeout=600)
    return r.returncode, r.stdout + r.stderr


def expect(name, ok, out=""):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print("    " + out.strip().replace("\n", "\n    ")[-1500:])


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    home, binp, remote, proj = t / "home", t / "bin", t / "remote.git", t / "proj"
    for d in (home, binp, proj):
        d.mkdir()
    base_path = "/usr/bin:/bin:/usr/sbin:/sbin:" + str(Path(sys.executable).parent)
    env = {"HOME": str(home), "PATH": base_path, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com", "PRODUCT_OS_NO_KEYCHAIN": "1"}
    with_runner = dict(env, PATH=str(binp) + ":" + base_path)
    os.symlink(PLUGIN / "bin" / "product-os", binp / "product-os")
    sh(["git", "init", "-q", "--bare", str(remote)], t, env)
    sh(["git", "init", "-q", "-b", "main"], proj, env)
    sh(["git", "remote", "add", "origin", str(remote)], proj, env)
    hooks = proj / ".githooks"
    hooks.mkdir()
    for f in ("pre-push", "pre-commit", "scan_keys.py"):
        shutil.copy2(CI / f, hooks / f)
    (proj / ".claude").mkdir()
    (proj / "chk.py").write_text("import sys, pathlib\nsys.exit(1 if any('BAD' in p.read_text() for p in pathlib.Path(sys.argv[1]).rglob('*') if p.is_file()) else 0)\n")
    for case, text in (("bad", "BAD"), ("good", "fine")):
        (proj / "cases" / case).mkdir(parents=True)
        (proj / "cases" / case / "f.txt").write_text(text)
    (proj / "src").mkdir()
    (proj / "src" / "a.txt").write_text("fine")
    (proj / ".claude" / "product-os-checks.json").write_text(json.dumps({"checks": [
        {"name": "no-bad", "run": "{python} chk.py {target}", "target": "src", "bad": "cases/bad", "good": "cases/good"}]}))
    settings = {"app": {"build_cmd": "true", "check_cmd": "true"}}
    (proj / ".claude" / "product-os.json").write_text(json.dumps(settings))
    code, out = sh(["product-os", "accept"], proj, with_runner)
    expect("product-os accept proves the planted check (setup for the cases)", code == 0, out)
    sh(["git", "add", "-A"], proj, env)
    sh(["git", "commit", "-qm", "first", "--no-verify"], proj, env)
    sh(["git", "push", "-q", "--no-verify", "origin", "main"], proj, env)
    sh(["git", "remote", "set-head", "origin", "main"], proj, env)

    def commit(name, text):
        (proj / "src" / name).write_text(text)
        sh(["git", "add", "-A"], proj, env)
        sh(["git", "commit", "-qm", name, "--no-verify"], proj, env)

    def push(e):
        return sh(["git", "-c", "core.hooksPath=.githooks", "push", "origin", "main"], proj, e)

    commit("b.txt", "fine")
    code, out = push(env)
    expect("bad: no product-os on PATH refuses the push", code != 0 and "isn't on PATH" in out, out)
    code, out = push(with_runner)
    expect("bad: app.build_cmd not accepted refuses, naming the accept line",
           code != 0 and "kit_config accept" in out and "DID NOT RUN" in out, out)
    code, out = sh(["product-os", "kit_config", "accept", "app.build_cmd", "app.check_cmd"], proj, with_runner)
    expect("kit_config accept (the person's step, setup for the cases)", code == 0, out)
    code, out = push(with_runner)
    expect("good: accepted commands pass and a proven, accepted check passes: push goes", code == 0, out)
    settings["app"]["check_cmd"] = "echo gate-x DID NOT RUN"
    (proj / ".claude" / "product-os.json").write_text(json.dumps(settings))
    commit("c.txt", "fine")
    sh(["product-os", "kit_config", "accept", "app.check_cmd"], proj, with_runner)
    code, out = push(with_runner)
    expect("bad: a DID NOT RUN line refuses even at exit 0", code != 0 and "did not run" in out, out)
    settings["app"]["check_cmd"] = "false"
    (proj / ".claude" / "product-os.json").write_text(json.dumps(settings))
    commit("d.txt", "fine")
    code, out = push(with_runner)
    expect("bad: a changed check_cmd stops counting until accepted again", code != 0 and "kit_config accept app.check_cmd" in out, out)
    sh(["product-os", "kit_config", "accept", "app.check_cmd"], proj, with_runner)
    code, out = push(with_runner)
    expect("bad: a failing check_cmd refuses", code != 0 and "failed" in out, out)
    settings["app"]["check_cmd"] = "true"
    (proj / ".claude" / "product-os.json").write_text(json.dumps(settings))
    commit("e.txt", "BAD")
    sh(["product-os", "kit_config", "accept", "app.check_cmd"], proj, with_runner)
    code, out = push(with_runner)
    expect("bad: product-os check failing refuses", code != 0 and "no-bad" in out, out)
    commit("e.txt", "fine")
    (proj / "src" / "a.txt").write_text("edited, not committed")
    code, out = push(with_runner)
    expect("bad: uncommitted edits refuse", code != 0 and "aren't committed" in out, out)
    sh(["git", "checkout", "--", "src/a.txt"], proj, env)
    code, out = push(with_runner)
    expect("good: clean again, the push goes", code == 0, out)
    # pre-commit
    tok = "gh" + "p_" + "A1b2" * 9
    (proj / "src" / "k.txt").write_text("token = " + tok + "\n")
    sh(["git", "add", "-A"], proj, env)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "key"], proj, with_runner)
    expect("bad: a staged token refuses the commit and never prints it", code != 0 and "GitHub token" in out and tok not in out, out)
    (proj / "src" / "k.txt").write_text("token = os.environ['X']\n")
    sh(["git", "add", "-A"], proj, env)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "clean"], proj, with_runner)
    expect("good: a clean commit goes", code == 0, out)
    os.rename(hooks / "scan_keys.py", hooks / "gone.py")
    (proj / "src" / "k.txt").write_text("more\n")
    sh(["git", "add", "src/k.txt"], proj, env)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "noscan"], proj, with_runner)
    expect("bad: a missing scanner refuses the commit", code != 0 and "did not run" in out, out)
    # The shims: the project keeps two short files that run the installed plugin's hooks.
    for f in ("pre-push", "pre-commit", "gone.py"):
        (hooks / f).unlink()
    for f in ("pre-push", "pre-commit"):
        shutil.copy2(CI / "shim" / f, hooks / f)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "noplugin"], proj, env)
    expect("bad: through the shim, no product-os on PATH refuses the commit", code != 0 and "did not run" in out, out)
    (proj / "src" / "k.txt").write_text("token = " + tok + "\n")
    sh(["git", "add", "-A"], proj, env)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "key"], proj, with_runner)
    expect("bad: through the shim, a staged token refuses and is never printed",
           code != 0 and "GitHub token" in out and tok not in out, out)
    (proj / "src" / "k.txt").write_text("clean through the shim\n")
    sh(["git", "add", "-A"], proj, env)
    code, out = sh(["git", "-c", "core.hooksPath=.githooks", "commit", "-qm", "shim"], proj, with_runner)
    expect("good: through the shim, a clean commit goes", code == 0, out)
    code, out = push(env)
    expect("bad: through the shim, no product-os on PATH refuses the push", code != 0 and "isn't on PATH" in out, out)
    code, out = push(with_runner)
    expect("good: through the shim, the plugin's push check runs and the push goes",
           code == 0 and "pre-push: running in" in out, out)
    commit("f.txt", "BAD")
    code, out = push(with_runner)
    expect("bad: through the shim, product-os check failing refuses", code != 0 and "no-bad" in out, out)

print(f"hook cases: {sum(results)} of {len(results)} passed")
sys.exit(0 if all(results) else 1)
