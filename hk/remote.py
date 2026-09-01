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
