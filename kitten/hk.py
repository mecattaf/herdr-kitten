"""hk.py — the kitty kitten half of herdr-kitten (spec D2).

Gesture dispatch only: toggle / fork / scrollback / voice. Handlers run on
kitty's GUI thread with a <1ms budget — user_vars reads and remote-control
calls only; ZERO sockets, ZERO subprocess waits, ZERO polling (spec F.6).
The heavy lifting happens in `bin/hk`, launched fire-and-forget.

Stage S3 (kitten-gestures lane) fills the ladder bodies; this scaffold
registers the dispatch surface so `kitty @ kitten hk.py <gesture>` is wired.
"""

from __future__ import annotations

import sys

GESTURES = ("toggle", "fork", "scrollback", "voice")


def main(args: list[str]) -> str:
    # Runs in the kitten's own process; the result string reaches handle_result.
    gesture = args[1] if len(args) > 1 else ""
    return gesture


def _not_yet(boss, window, gesture: str) -> None:  # noqa: ANN001 (kitty types)
    # S3 replaces these with the real ladder. A stub gesture is a visible no-op:
    # never a crash, never a bell loop.
    print(f"hk.py: gesture {gesture!r} lands in stage S3", file=sys.stderr)


def handle_result(args: list[str], answer: str, target_window_id: int, boss) -> None:  # noqa: ANN001
    gesture = answer.strip()
    if gesture not in GESTURES:
        print(f"hk.py: unknown gesture {gesture!r} (want one of {GESTURES})", file=sys.stderr)
        return
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return
    _not_yet(boss, window, gesture)


handle_result.no_ui = True
