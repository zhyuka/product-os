"""Run INSTALL.md's commands the way an agent following it would: each fenced `sh` block under a
"### N. ..." step, in order, in its own `sh -e`, so a variable set in one block is gone in the next.
Stop at the first block that fails and exit with its code.

    python .github/run_install_doc.py [--skip N] [--only N] [INSTALL.md]

HOME, PATH and PRODUCT_OS_DIR come from the environment, so CI points them at an empty home and
the checkout under test. --skip 2 leaves out step 2, which clones the newest release from GitHub
instead of the commit under test; --only 2 runs that step alone.
"""
import argparse, os, re, subprocess, sys

STEP = re.compile(r"^### (\d+)\. ")


def blocks(text):
    """(step number, block text) for each ```sh block under a numbered step."""
    out, step, buf = [], None, None
    for line in text.splitlines():
        if buf is not None:
            if line.startswith("```"):
                out.append((step, "\n".join(buf) + "\n"))
                buf = None
            else:
                buf.append(line)
            continue
        m = STEP.match(line)
        if m:
            step = int(m.group(1))
        elif line.strip() == "```sh" and step is not None:
            buf = []
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("doc", nargs="?", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "INSTALL.md"))
    ap.add_argument("--skip", type=int, action="append", default=[])
    ap.add_argument("--only", type=int, action="append", default=[])
    a = ap.parse_args(argv)
    with open(a.doc, encoding="utf-8") as f:
        found = blocks(f.read())
    chosen = [(s, b) for s, b in found if s not in a.skip and (not a.only or s in a.only)]
    if not chosen:
        print(f"could not run: no sh blocks chosen from {a.doc}")
        return 2
    for step, block in chosen:
        print(f"--- step {step}\n{block}", flush=True)
        code = subprocess.run(["sh", "-e", "-c", block]).returncode
        if code:
            print(f"--- step {step} failed with exit {code}")
            return code
    print(f"--- {len(chosen)} block(s) ran, steps {sorted({s for s, _ in chosen})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
