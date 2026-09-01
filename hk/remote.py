"""hk ssh — the two-tier remote posture (spec R10.3/R10.4, D13; census P58/P59).

Launcher, not layering: each tier execs the real thing and adds nothing.
"""

from __future__ import annotations

import os
import sys

from hk import kittyc

EXIT_OK = 0
EXIT_ERROR = 1


def cmd_ssh(host: str, plain: bool = False, in_place: bool = False) -> int:
    """hk ssh HOST: kitty window running `herdr --remote HOST
    --remote-keybindings server`, stamped hk_role=herdr_ui (spec 10.3).
    --plain: exec `kitten ssh HOST` — terminfo, ControlMaster, shell
    integration survive only there; zero herdr (spec 10.4)."""
    if plain:
        os.execvp("kitten", ["kitten", "ssh", host])  # never returns
    argv = ["herdr", "--remote", host, "--remote-keybindings", "server"]
    if in_place or not kittyc.available():
        # stamp this window if we can, then exec in place
        win = kittyc.window_id()
        if win:
            try:
                kittyc.set_user_vars(win, hk_role="herdr_ui")
            except kittyc.KittyError:
                pass
        os.execvp(argv[0], argv)  # never returns
    try:
        kittyc.launch_os_window(argv, user_vars={"hk_role": "herdr_ui"})
        return EXIT_OK
    except kittyc.KittyError as exc:
        print(f"hk ssh: {exc}", file=sys.stderr)
        return EXIT_ERROR


def niri_move_materialised(window_ids: list[str]) -> int:
    """spec 9.7 (D15): NIRI_SOCKET present -> move the given kitty windows to
    the focused niri workspace; absent -> ZERO compositor calls (unit-tested
    by asserting this function is the only niri call site and returns 0
    immediately when the env var is unset)."""
    if not os.environ.get("NIRI_SOCKET"):
        return 0
    import json
    import subprocess
    focused = None
    try:
        out = subprocess.run(["niri", "msg", "-j", "workspaces"],
                             capture_output=True, text=True, timeout=10)
        for ws in json.loads(out.stdout):
            if ws.get("is_focused"):
                focused = ws.get("idx")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0
    if focused is None:
        return 0
    moved = 0
    for _win in window_ids:
        # kitty window id -> wayland window: niri matches by focus history;
        # the adapter moves the MOST RECENT window per materialise launch.
        proc = subprocess.run(["niri", "msg", "action",
                               "move-window-to-workspace", str(focused)],
                              capture_output=True, timeout=10)
        if proc.returncode == 0:
            moved += 1
    return moved
