"""Slash-fork delivery-state logic (spec R11, D11) — pure and unit-testable.

The nvim side (assets/fork.lua) pipes the whole buffer here on every save/exit
decision point; this module decides what (if anything) to deliver:

  first save                  -> deliver the WHOLE buffer
  unchanged buffer            -> no-op
  append-only save            -> deliver only the appended suffix
  edit inside delivered text  -> deliver NOTHING + notification on stderr

Delivery is bracketed populate-only via `hk send` (spec 4.1); --submit routes
`hk send --submit` (spec 11.6). The delivered prefix is tracked in a state
file under the fork's own tmpdir. NEVER reads the target pane (spec F.8).
"""

from __future__ import annotations

import os
import subprocess
import sys

DELIVER_ALL = "all"
DELIVER_SUFFIX = "suffix"
DELIVER_NOTHING = "nothing"
CONFLICT = "conflict"


def decide(delivered: str, current: str) -> tuple[str, str]:
    """(action, payload) for a buffer now reading `current` when `delivered`
    was already sent."""
    if not delivered:
        return (DELIVER_ALL, current) if current else (DELIVER_NOTHING, "")
    if current == delivered:
        return (DELIVER_NOTHING, "")
    if current.startswith(delivered):
        return (DELIVER_SUFFIX, current[len(delivered):])
    return (CONFLICT, "")


def run(argv: list[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="fork_state")
    parser.add_argument("--state", required=True, help="delivered-prefix state file")
    parser.add_argument("--pane", required=True)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args(argv)

    current = sys.stdin.read()
    delivered = ""
    if os.path.exists(args.state):
        with open(args.state, "r") as fh:
            delivered = fh.read()

    action, payload = decide(delivered, current)
    if action == CONFLICT:
        print("hk fork: buffer edited inside already-delivered text; nothing delivered",
              file=sys.stderr)
        return 65
    if action == DELIVER_NOTHING:
        return 0

    hk = os.environ.get("HK_BIN", "hk")
    cmd = [hk, "send"]
    if args.submit:
        cmd.append("--submit")
    cmd.append(args.pane)
    proc = subprocess.run(cmd, input=payload, text=True)
    if proc.returncode != 0:
        return proc.returncode
    with open(args.state, "w") as fh:
        fh.write(current)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
