"""Which repository a path belongs to, so an accept made in one worktree counts in the others.

An accept is recorded per repository and command, not per folder path: every worktree of one
repository shares its git folder (`git rev-parse --git-common-dir`), so they share accepts. A
separate clone or a fork has a git folder of its own, so cloning still can't choose what runs.
tools/kit_config.py keeps its own copy of this rule, because the tools run without the package.
"""
import os
import subprocess


def _git(folder, *args):
    try:
        p = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = p.stdout.strip()
    return out if p.returncode == 0 and out else None


def repo_key(path):
    """"git:<the repository's git folder>:<path inside the work tree>" for a path in a git work
    tree, else None. Both parts are real paths with forward slashes."""
    path = os.path.realpath(path)
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    top = _git(folder, "rev-parse", "--show-toplevel")
    common = _git(folder, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not top or not common:
        return None
    inside = os.path.relpath(path, os.path.realpath(top)).replace(os.sep, "/")
    return f"git:{os.path.realpath(common).replace(os.sep, '/')}:{inside}"


def main_worktree(path):
    """The main work tree of the repository path is in, when that isn't path's own work tree;
    else None. A worktree's own folder name differs from the main checkout's, so a setting
    written for the main checkout's path covers its worktrees through this. The hooks call it on
    every tool call, so git runs only when the nearest .git is a file, as in a linked worktree."""
    folder = os.path.realpath(path if os.path.isdir(path) else os.path.dirname(path))
    probe = folder
    while not os.path.lexists(os.path.join(probe, ".git")):
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent
    if not os.path.isfile(os.path.join(probe, ".git")):
        return None  # a main checkout keeps a .git folder; a submodule's file is ruled out below
    common = _git(folder, "rev-parse", "--path-format=absolute", "--git-common-dir")
    top = _git(folder, "rev-parse", "--show-toplevel")
    if not common or not top or os.path.basename(common) != ".git":
        return None
    main = os.path.dirname(os.path.realpath(common))
    return main if main != os.path.realpath(top) else None
