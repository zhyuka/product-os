"""Workspace for skill-review-change-builder-account. scaffold.sh runs it in the empty run folder.

A small site whose home hero shows three cards. The design sets them 24 px apart. The committed
build matched; the uncommitted change sets the gap to 32 px. The person's pictures and numbers file
for 1440 sit in .look/home-hero-1440/, and the numbers flag the gap. The prompt says the gap was
fixed and the section matches now. The graders read these values, so change them together.

    python3 fixture.py            build the workspace in the current folder
    python3 fixture.py selftest   build it in a temp folder and check the planted miss is there
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

GIT = ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]

WIDTH, HEIGHT = 1440, 400
BACKGROUND = (24, 26, 38)
CARD_W, CARD_TOP, CARD_H, LEFT = 384, 180, 160, 120
DESIGN_GAP, BUILD_GAP = 24, 32
TITLES = ("Plan", "Build", "Ship")

HERO = """<section class="hero">
  <h1>Ship with confidence</h1>
  <p>Every change reviewed before it goes out.</p>
  <div class="cards">
    <article class="card">Plan</article>
    <article class="card">Build</article>
    <article class="card">Ship</article>
  </div>
</section>
<style>
  .hero {{ padding: 60px 120px; }}
  .cards {{ display: flex; gap: {gap}px; margin-top: 48px; }}
  .card {{ width: 384px; height: 160px; }}
</style>
"""

DECISIONS = [{
    "id": "D-2",
    "where": "home hero, at 390",
    "decision": "The three cards stack in one column, 16 px apart, as built. The phone frame's "
                "two-column row is not followed.",
    "by": "design lead",
}]


def card_lefts(gap):
    return [LEFT + i * (CARD_W + gap) for i in range(len(TITLES))]


def boxes(gap):
    """The rectangles a picture of the section draws: (x, y, w, h, colour)."""
    out = [(120, 60, 600, 40, (230, 230, 240)), (120, 116, 400, 16, (150, 150, 170))]
    for x in card_lefts(gap):
        out += [(x, CARD_TOP, CARD_W, CARD_H, (52, 56, 80)),
                (x + 24, CARD_TOP + 24, 32, 32, (120, 140, 255)),
                (x + 24, CARD_TOP + 80, 200, 16, (200, 200, 215))]
    return out


def png(path, rects):
    """A flat-colour RGB PNG, stdlib only."""
    rows = []
    for y in range(HEIGHT):
        row = bytearray(bytes(BACKGROUND) * WIDTH)
        for x, top, w, h, colour in rects:
            if top <= y < top + h:
                row[x * 3:(x + w) * 3] = bytes(colour) * w
        rows.append(b"\x00" + bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    write(path, b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
          + chunk(b"IEND", b""))


def numbers(build_gap=BUILD_GAP):
    lines = [
        "# Numbers: home hero at 1440",
        "",
        "One row per element: its box in the design and in the build, as x,y,w,h in CSS px from the",
        "section's top left, then the difference, build minus design. FLAG marks a row that differs",
        "by more than 2 px.",
        "",
        "| element | design | build | dx | dy | dw | dh | flag |",
        "|---|---|---|---|---|---|---|---|",
        '| heading "Ship with confidence" | 120,60,600,40 | 120,60,600,40 | 0 | 0 | 0 | 0 | |',
        "| subline | 120,116,400,16 | 120,116,400,16 | 0 | 0 | 0 | 0 | |",
    ]
    def delta(n):
        return f"{n:+d}" if n else "0"

    def flag(n):
        return "FLAG" if abs(n) > 2 else ""

    for title, d, b in zip(TITLES, card_lefts(DESIGN_GAP), card_lefts(build_gap)):
        lines.append(f'| card "{title}" | {d},{CARD_TOP},{CARD_W},{CARD_H} | {b},{CARD_TOP},{CARD_W},{CARD_H} '
                     f"| {delta(b - d)} | 0 | 0 | 0 | {flag(b - d)} |")
    gap = build_gap - DESIGN_GAP
    lines.append(f"| gap between cards | {DESIGN_GAP} | {build_gap} | | | {delta(gap)} | | {flag(gap)} |")
    return "\n".join(lines) + "\n"


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def build():
    subprocess.run(GIT + ["init", "-q"], check=True)
    write(".gitignore", ".look/\n")
    write(".claude/product-os.json", json.dumps({"app": {"widths": [1440], "decisions": "docs/decisions.json"}},
                                                 indent=2) + "\n")
    write("docs/decisions.json", json.dumps(DECISIONS, indent=2) + "\n")
    write("src/hero.html", HERO.format(gap=DESIGN_GAP))
    subprocess.run(GIT + ["add", "-A"], check=True)
    subprocess.run(GIT + ["commit", "-q", "-m", "Add the home hero"], check=True)
    write("src/hero.html", HERO.format(gap=BUILD_GAP))
    png(".look/home-hero-1440/design.png", boxes(DESIGN_GAP))
    png(".look/home-hero-1440/build.png", boxes(BUILD_GAP))
    write(".look/home-hero-1440/numbers.md", numbers())


def selftest():
    """The planted miss is there (gap 32 against 24, flagged), and a matching build flags nothing."""
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            build()
            look = Path(".look/home-hero-1440")
            flagged = [line for line in (look / "numbers.md").read_text(encoding="utf-8").splitlines()
                       if line.endswith("| FLAG |")]
            design, built = ((look / f"{n}.png").read_bytes() for n in ("design", "build"))
            base = subprocess.run(GIT + ["show", "HEAD:src/hero.html"], capture_output=True, text=True,
                                  check=True).stdout
            checks = {
                "bad: the two moved cards and the gap are flagged": len(flagged) == 3,
                "bad: the gap row reads 24 against 32": any("gap between cards | 24 | 32" in l for l in flagged),
                "bad: the pictures are PNGs and differ": design != built and design.startswith(b"\x89PNG"),
                "bad: the change sets a 32 px gap": "gap: 32px" in Path("src/hero.html").read_text(encoding="utf-8"),
                "good: the base sets a 24 px gap": "gap: 24px" in base,
                "good: a matching build flags nothing":
                    not [l for l in numbers(DESIGN_GAP).splitlines() if l.endswith("| FLAG |")],
            }
        finally:
            os.chdir(here)
    for name, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + name)
    return 0 if all(checks.values()) else 1

if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["selftest"] else build())
