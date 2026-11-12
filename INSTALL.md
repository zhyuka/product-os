# Install Product OS

This file is for an agent installing Product OS for the person it works with. A person can follow it
too.

<!-- install:start -->
<!-- github-only -->
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
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
This folder is the plugin, with its hooks and its `product-os:` skills and agents. Have your agent
follow `INSTALL.md` in it, or start Claude Code with `--plugin-dir` set to this folder for one
session.
-->

The tools and checks need Python 3.9 or later. The commands that drive a browser also need
Playwright: `pip install playwright`, then `playwright install chromium`.
<!-- install:end -->

<!-- github-only -->
## Steps for ways 2 and 3
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
## Steps
-->

Run each block below in a shell, in order, and on Windows in Git Bash. Each one starts by naming the
folder, because a variable set in one command is gone by the next.
<!-- github-only -->
The folder is `~/product-os` unless the person wants it elsewhere, or is installing from an unzipped
release: then set `PRODUCT_OS_DIR` to that folder at the top of every block.
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
Set `PRODUCT_OS_DIR` to this folder, the one this file is in, at the top of every block.
-->
If a command fails, stop and show the person its output. Don't work around it, and never move,
overwrite or delete their files yourself.

### 1. Check git and Python

```sh
git --version
py=
for name in python3 python; do "$name" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null && { py=$name; break; }; done
[ -n "$py" ] || { echo "No Python 3.9 or later runs here: tried python3 and python on PATH"; exit 1; }
"$py" -c 'import sys; print("Python", sys.version.split()[0])'
```

From an unzipped release, git isn't needed: skip the first line. It tries `python` after `python3`,
because on Windows `python3` is often a placeholder that only offers to install Python from the
Microsoft Store.

<!-- github-only -->
### 2. Get the latest release

Skip this step when installing from an unzipped release.

```sh
PRODUCT_OS_DIR="${PRODUCT_OS_DIR:-$HOME/product-os}"
if [ -e "$PRODUCT_OS_DIR" ]; then
  [ -f "$PRODUCT_OS_DIR/bin/product-os" ] || { echo "$PRODUCT_OS_DIR exists and isn't Product OS"; exit 1; }
  git -C "$PRODUCT_OS_DIR" fetch --quiet --tags
else
  git clone --quiet https://github.com/zhyuka/product-os "$PRODUCT_OS_DIR"
fi
tag=$(git -C "$PRODUCT_OS_DIR" tag --list 'v*' --sort=-v:refname | sed '/-/d' | head -n 1)
[ -z "$tag" ] || git -C "$PRODUCT_OS_DIR" checkout --quiet "$tag"
git -C "$PRODUCT_OS_DIR" log -1 --format='%h%d'
```

It checks out the newest release tag, or stays on the default branch when there's none yet. It skips
any tag with a hyphen, such as `v0.1.4-probe.1`, which CI uses for test runs. If the folder already
exists and isn't Product OS, it stops: ask the person which folder to use.
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
### 2. Nothing to fetch

This folder already holds every file, so go on to step 3.
-->

### 3. Load it as the plugin

This sets one key, `CLAUDE_CODE_PLUGIN_DIRS`, in the `env` block of the person's Claude Code
settings, so every session loads Product OS from this folder. First show them what would change:

```sh
PRODUCT_OS_DIR="${PRODUCT_OS_DIR:-$HOME/product-os}"
"$PRODUCT_OS_DIR/bin/product-os" enable
```

It writes nothing, and prints that key's value before and after; it never prints any other key from
the file. Give the person those lines and ask whether to make the change. Only on their yes:

```sh
PRODUCT_OS_DIR="${PRODUCT_OS_DIR:-$HOME/product-os}"
"$PRODUCT_OS_DIR/bin/product-os" enable --yes
```

If the key already names other folders, it changes nothing and says so: show the person, who adds
this folder to the list themselves. If it notes that the environment also sets the key to another
folder, tell the person: that value wins, so this folder loads only once they unset it or make it
name this folder.

### 4. Put the `product-os` command on the PATH

Inside Claude Code the plugin puts the command on the PATH itself. The project's git hooks run
outside it, and need the link.

```sh
PRODUCT_OS_DIR="${PRODUCT_OS_DIR:-$HOME/product-os}"
mkdir -p "$HOME/.local/bin"
export MSYS=winsymlinks:nativestrict
[ -e "$HOME/.local/bin/product-os" ] || ln -s "$PRODUCT_OS_DIR/bin/product-os" "$HOME/.local/bin/product-os"
"$HOME/.local/bin/product-os" --root
```

It prints the folder Product OS runs from. The `MSYS` line matters only in Git Bash on Windows.
Without it, `ln -s` there copies the file, and the copy runs from the wrong folder. With it, `ln`
makes a real link or fails. Windows allows a real link only with Developer Mode on, under Settings,
System, For developers, or from a shell run as administrator. If `ln` fails, show the person. They
can turn on Developer Mode and run this block again, or add `$PRODUCT_OS_DIR/bin` to their PATH in
place of the link. If `~/.local/bin` isn't on the person's PATH, give them the line
`export PATH="$HOME/.local/bin:$PATH"` to add to their shell profile. Don't edit the profile
yourself. If `~/.local/bin/product-os` already points at another folder, step 6 says so;
show the person and let them choose.

### 5. Restart Claude Code

The plugin loads when a session starts. Tell the person to restart Claude Code, or in the desktop
app to start a new session, after step 6.

### 6. Check the install

```sh
PRODUCT_OS_DIR="${PRODUCT_OS_DIR:-$HOME/product-os}"
"$PRODUCT_OS_DIR/bin/product-os" doctor
```

It prints how many of its checks pass and exits 0 only when all do. Give the person its first line
and every `MISS` line word for word.

## Upgrading

<!-- github-only -->
Run step 2 again to move the clone to the newest tag, restart Claude Code, then run step 6. The
setting from step 3 keeps naming the same folder, so it needs nothing.
<!-- /github-only -->
<!-- zip-only: the zip shows this instead; skip it here
The person unzips the new zip and puts its folder where this one is, under this folder's name, so
the setting from step 3 and the link from step 4 still name it. Then they restart Claude Code, and
you run step 6.
-->
