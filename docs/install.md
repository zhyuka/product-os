# The install block

This is the one copy of how to install Product OS. `README.md` and `INSTALL.md` carry the block
between the two markers word for word, and `tests/test_install_docs.py` fails when either says it
differently. Change it here first, then paste it into both.

<!-- install:start -->
There are three ways in. The first updates itself; the other two need no plugin marketplace. All
three load the same plugin, with its hooks and its `product-os:` skills and agents.

1. **From the marketplace.** In a Claude Code session, run `/plugin marketplace add
   zhyuka/product-os`, then `/plugin install product-os@product-os`. Where your organization allows
   plugins only from marketplaces it lists, use 2 or 3.
2. **Point your agent at the repo.** Tell Claude Code: "Fetch and follow
   https://raw.githubusercontent.com/zhyuka/product-os/main/INSTALL.md". It clones the latest
   release and, on your yes, sets `CLAUDE_CODE_PLUGIN_DIRS` in your Claude Code settings so the
   plugin loads from the clone. It puts the `product-os` command on your PATH for the git hooks,
   and ends with `product-os doctor`, which has to pass.
3. **From the release zip.** Download `product-os-<version>.zip` from the
   [latest release](https://github.com/zhyuka/product-os/releases/latest) and unzip it. Have your
   agent follow `INSTALL.md` inside it from step 3, or start Claude Code with `--plugin-dir` set to
   the unzipped folder for one session.

The tools and checks need Python 3.9 or later. The commands that drive a browser also need
Playwright: `pip install playwright`, then `playwright install chromium`.
<!-- install:end -->
