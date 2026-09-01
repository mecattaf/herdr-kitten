"""hk.py — the kitty kitten half of herdr-kitten (spec D2, stage S3).

Gesture dispatch: toggle / fork / scrollback / voice. handle_result runs on
kitty's GUI thread with a <1ms budget: user-var reads, window writes, and
in-process launches only — ZERO sockets, ZERO subprocess waits, ZERO polling
(spec F.6/F.7). All routing decisions live in kitten/ladder.py (pure,
unit-tested); this file only touches kitty.

Invoke from kitty maps (see conf/kitty-maps.conf):
    map ctrl+b            kitten hk.py toggle
    map ctrl+shift+g      kitten hk.py fork
    map ctrl+shift+h      kitten hk.py scrollback
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.realpath(__file__))
for _cand in (_HERE, os.path.dirname(_HERE)):
    if _cand not in sys.path:
        sys.path.insert(0, _cand)

GESTURES = ("toggle", "fork", "scrollback", "voice")

try:
    from kitten import ladder  # dev tree: <repo>/kitten/ladder.py
except ImportError:
    import ladder  # installed flat beside hk.py


def main(args: list[str]) -> str:
    return args[1] if len(args) > 1 else ""


def _window_dict(window) -> dict:
    """Project the live kitty Window onto the plain dict the ladder consumes."""
    user_vars = dict(getattr(window, "user_vars", None) or {})
    fg = []
    try:
        for proc in window.child.foreground_processes:
            fg.append({"cmdline": list(proc.get("cmdline") or [])})
    except Exception:
        pass
    return {"user_vars": user_vars, "foreground_processes": fg}


def _config():
    # tiny cached toml read; file I/O only on first gesture use
    if not hasattr(_config, "_cached"):
        try:
            from hk import config as hk_config
            _config._cached = hk_config.load()
        except Exception:
            _config._cached = {"plain_scrollback_action": "show_scrollback"}
    return _config._cached


def _assets_dir() -> str:
    # dev tree: <repo>/assets ; installed: ~/.config/kitty/hk-assets
    for cand in (os.path.join(os.path.dirname(_HERE), "assets"),
                 os.path.join(_HERE, "hk-assets")):
        if os.path.isdir(cand):
            return cand
    return os.path.join(_HERE, "hk-assets")


def _toggle(boss, window) -> None:
    action = ladder.toggle_action(_window_dict(window))
    if action == ladder.PREFIX:
        window.write_to_child(b"\x02")
    elif action == ladder.CLOSE:
        boss.mark_window_for_close(window)  # close IS detach (probe P-G2)
    else:
        # launch a herdr vsplit running `hk open`, stamped for the second toggle
        boss.call_remote_control(window, (
            "launch", "--type=window", "--location=vsplit", "--cwd=current",
            "--var", "hk_role=split", "hk", "open"))


def _scrollback(boss, window) -> None:
    lane = ladder.scrollback_lane(_window_dict(window))
    if lane == ladder.HERDR_LANE:
        window.write_to_child(b"\x02e")  # herdr keys.edit_scrollback
        return
    action = str(_config().get("plain_scrollback_action", "show_scrollback"))
    if action == "show_scrollback":
        boss.call_remote_control(window, ("action", "show_scrollback"))
    else:
        boss.call_remote_control(window, tuple(action.split()))


def _fork(boss, window) -> None:
    pane = ladder.fork_target(_window_dict(window))
    if pane is None:
        return  # silent no-op (spec 11.8): no bell, no window
    assets = _assets_dir()
    fork_lua = os.path.join(assets, "fork.lua")
    boss.call_remote_control(window, (
        "launch", "--type=os-window", "--os-window-class=hk-fork",
        "--var", "hk_role=fork",
        "--env", f"HK_FORK_PANE={pane}",
        "--env", f"HK_FORK_ASSETS={assets}",
        "nvim", "--cmd", f"luafile {fork_lua}"))


def _voice(boss, window) -> None:
    # stage S4 territory (spec R5); the gesture surface exists so maps don't
    # error, but dictation goes through `hk voice` (the CLI owns the endpoint).
    print("hk.py: voice endpoint is `hk voice begin|text|end` (stage S4)", file=sys.stderr)


def handle_result(args: list[str], answer: str, target_window_id: int, boss) -> None:
    gesture = answer.strip()
    if gesture not in GESTURES:
        print(f"hk.py: unknown gesture {gesture!r} (want one of {GESTURES})", file=sys.stderr)
        return
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return
    {"toggle": _toggle, "fork": _fork, "scrollback": _scrollback, "voice": _voice}[gesture](boss, window)


handle_result.no_ui = True
