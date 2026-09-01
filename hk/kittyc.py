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


def focused_window() -> dict | None:
    for window in windows():
        if window.get("is_focused"):
            return window
    return None


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
