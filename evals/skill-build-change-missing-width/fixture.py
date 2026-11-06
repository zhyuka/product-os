"""Builds the workspace for skill-build-change-missing-width in the current folder: a project that
ships 1440 and 390, a mockup picture for 1440 only, and an empty page to build the hero into."""
import json, os, struct, zlib


def png(path, width, height, rows):
    """A plain RGB PNG, stdlib only. rows(y) gives the colour of row y."""
    raw = b"".join(b"\x00" + bytes(rows(y)) * width for y in range(height))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


os.makedirs(".claude", exist_ok=True)
os.makedirs("mockups", exist_ok=True)
with open(os.path.join(".claude", "product-os.json"), "w", encoding="utf-8") as f:
    json.dump({"app": {"widths": [1440, 390]}}, f, indent=2)
# a dark band with a lighter heading bar and a light body: the hero at 1440 wide
png(os.path.join("mockups", "hero-1440.png"), 1440, 480,
    lambda y: (17, 17, 19) if y < 320 and not 120 <= y < 176 else ((240, 240, 240) if y < 320 else (255, 255, 255)))
with open("index.html", "w", encoding="utf-8") as f:
    f.write("<!doctype html>\n<html lang=\"en\">\n<head><meta charset=\"utf-8\"><title>Home</title></head>\n"
            "<body>\n<!-- hero goes here -->\n</body>\n</html>\n")
with open("README.md", "w", encoding="utf-8") as f:
    f.write("# Home page\n\nThe hero says \"Plan the release\" over a dark band, with the line "
            "\"Everything the team needs before launch.\" under it.\n")
