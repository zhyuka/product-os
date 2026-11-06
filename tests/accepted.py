"""Run hooks as a user who accepted the project's QA commands, the way /product-os:setup-kit has the person do it."""
import json
from pathlib import Path


def project_of(payload, project, root):
    """The project a hook run on payload works in: project, or else the input's cwd under root."""
    if project:
        return project
    try:
        cwd = json.loads(payload).get("cwd")
    except (ValueError, AttributeError, RecursionError):
        cwd = None
    return Path(root) / (cwd if isinstance(cwd, str) else ".")


def accept(project, folder):
    """Write folder/product-os-checks.json, the user's own config, accepting the QA commands that
    project's .claude/product-os-checks.json proposes. Gives folder, for CLAUDE_CONFIG_DIR."""
    try:
        data = json.loads((Path(project) / ".claude" / "product-os-checks.json").read_text(encoding="utf-8"))
        qa = data.get("qa_commands", [])
    except (OSError, ValueError, AttributeError):
        qa = None
    ok = isinstance(qa, list) and all(isinstance(q, str) for q in qa)
    projects = {str(Path(project).resolve()): {"qa_commands": qa}} if ok else {}
    (Path(folder) / "product-os-checks.json").write_text(json.dumps({"projects": projects}), encoding="utf-8")
    return str(folder)
