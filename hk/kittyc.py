"""kitty remote-control wrapper — every kitty interaction in hk goes through here.

Uses `kitty @` against $KITTY_LISTEN_ON (the socket of the kitty instance the
verb runs inside). Socket actions NEVER move focus except the one verb whose
whole job is focusing (spec F.7 / D6).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess


class KittyError(RuntimeError):
    pass


def listen_on() -> str | None:
    return os.environ.get("KITTY_LISTEN_ON") or None


def window_id() -> str | None:
    return os.environ.get("KITTY_WINDOW_ID") or None


def available() -> bool:
    """True when a kitty remote-control call has any chance of landing: both a
    socket to aim at and a kitty binary to aim with. Headless CI has neither."""
    return listen_on() is not None and shutil.which("kitty") is not None


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    sock = listen_on()
    if sock is None:
        raise KittyError("not inside a kitty window (KITTY_LISTEN_ON unset)")
    try:
        proc = subprocess.run(["kitty", "@", "--to", sock, *args],
                              capture_output=True, text=True)
    except OSError as exc:
        # No kitty binary at all is the same condition as an unreachable socket
        # from every caller's point of view: the surface tier is unavailable.
        raise KittyError(f"kitty remote control unavailable: {exc}") from exc
    if check and proc.returncode != 0:
        raise KittyError((proc.stderr or proc.stdout).strip())
    return proc


def ls() -> list[dict]:
    return json.loads(_run(["ls"]).stdout)


def windows() -> list[dict]:
    result = []
    for os_window in ls():
        for tab in os_window.get("tabs", []):
            result.extend(tab.get("windows", []))
    return result


def current_window() -> dict | None:
    wid = window_id()
    if wid is None:
        return None
    for window in windows():
        if str(window.get("id")) == wid:
            return window
    return None


def _focus_flag(node: dict) -> bool:
    """Focused-ness of one node of the `kitty @ ls` tree.

    kitty stamps `is_focused` at all three levels (measured against the kitty
    0.48.0 in this closure): OS window `boss.py:528`, tab `tabs.py:1456`,
    window `tabs.py:1064`. `is_active` is the per-parent fallback for trees
    that carry only it; a node carrying neither flag cannot be disqualified on
    evidence it does not have.
    """
    for key in ("is_focused", "is_active"):
        if key in node:
            return bool(node[key])
    return True


def resolve_focused_window(os_windows: list[dict]) -> dict | None:
    """The one window kitty delivers keyboard events to, or None.

    BUG-6 (RULING-kitten §3.1/§3.2, ruled a plain bug): the window-level
    `is_focused` flag is stamped per TAB —

        is_focused=w.os_window_id == current_focused_os_window_id()
                   and w is active_window      # kitty 0.48.0 tabs.py:1064

    — so in a focused OS window with N tabs, N windows report
    `is_focused: true`. The old resolver flattened every OS window x tab and
    returned the FIRST match, i.e. the active window of whichever tab came
    first in iteration order, not the window the user is looking at. Dictated
    text landed in the wrong pane, silently, and the exit-3 fallback never
    fired because a herdr window *was* found.

    The focused window is the focused window OF the focused tab OF the focused
    OS window. This walks that chain instead of flattening it.

    Fails closed: no candidate and an ambiguous tree (which kitty cannot
    produce) both return None, so a caller exits 3 and falls back rather than
    guessing a destination for the user's words.
    """
    found = []
    for os_window in os_windows:
        if not _focus_flag(os_window):
            continue
        for tab in os_window.get("tabs") or []:
            if not _focus_flag(tab):
                continue
            for window in tab.get("windows") or []:
                if _focus_flag(window):
                    found.append(window)
    return found[0] if len(found) == 1 else None


def focused_window() -> dict | None:
    return resolve_focused_window(ls())


def focus_window(win_id: str) -> None:
    _run(["focus-window", "--match", f"id:{win_id}"])


def close_window(win_id: str) -> None:
    _run(["close-window", "--match", f"id:{win_id}"])


def set_window_title(title: str, win_id: str | None = None) -> None:
    args = ["set-window-title"]
    if win_id is not None:
        args += ["--match", f"id:{win_id}"]
    args.append(title)
    _run(args)


def set_user_vars(win_id: str, **vars_: str) -> None:
    args = ["set-user-vars", "--match", f"id:{win_id}"]
    args += [f"{key}={value}" for key, value in vars_.items()]
    _run(args)


def launch_os_window(cmd: list[str], user_vars: dict[str, str] | None = None,
                     window_class: str | None = None, env: dict[str, str] | None = None) -> str:
    """Launch a kitty OS window running cmd; returns the new kitty window id."""
    args = ["launch", "--type=os-window"]
    for key, value in (user_vars or {}).items():
        args += ["--var", f"{key}={value}"]
    for key, value in (env or {}).items():
        args += ["--env", f"{key}={value}"]
    if window_class:
        args += [f"--os-window-class={window_class}"]
    args += ["--", *cmd]
    return _run(args).stdout.strip()


def set_user_vars_at(sock: str, win_id: str, **vars_: str) -> None:
    """set-user-vars against an EXPLICIT kitty socket (notifyd resolves the
    socket from herdr-side kitty_sock tokens, not from its own env)."""
    import subprocess
    args = ["kitty", "@", "--to", sock, "set-user-vars", "--match", f"id:{win_id}"]
    args += [f"{key}={value}" for key, value in vars_.items()]
    subprocess.run(args, capture_output=True)
