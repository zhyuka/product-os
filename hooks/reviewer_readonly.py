#!/usr/bin/env python3
"""PreToolUse hook: a reviewer agent may not write files. See product_os/hooks.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from product_os import hooks  # noqa: E402

sys.exit(hooks.main(hooks.reviewer_readonly))
