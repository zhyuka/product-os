# This machine

Facts about this machine that a session can't derive and needs only now and then. Copy this file
next to your `CLAUDE.md`, keep what holds for you, and add your own. Read on demand, not loaded
every session.

## Files

- Check non-ASCII output with a U+FFFD count, in the file and in `git show HEAD:<path>`.
- On a case-insensitive filesystem, never rename to a name that differs only by case; verify a move
  by listing the source.
- A reboot can wipe the system temp folder (`/private/tmp` on macOS), the session scratchpad
  included: anything a later session needs goes in the project.

## This environment

- A variable inside Claude's process says nothing about the user's terminal; test where the tool
  will run, and unset a variable for one run with `env -u`.
- Behind a corporate proxy, a blocked site can answer HTTP 200 with an access-denied page. Check
  that fetched text is the real page.
