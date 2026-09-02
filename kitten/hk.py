"""hk.py — the kitty kitten half of herdr-kitten (spec D2, stage S3).

Gesture dispatch: toggle / fork / scrollback / voice. handle_result runs on
kitty's GUI thread with a <1ms budget: user-var reads, window writes, and
in-process launches only — ZERO sockets, ZERO subprocess waits, ZERO polling
(spec F.6/F.7). All routing decisions live in kitten/ladder.py (pure,
unit-tested); this file only touches kitty.

Invoke from kitty maps (see conf/kitty-maps.conf):
    map ctrl+b            kitten hk-kitten/hk.py toggle
    map ctrl+shift+g      kitten hk-kitten/hk.py fork
    map ctrl+shift+h      kitten hk-kitten/hk.py scrollback

LOADER CONTRACT (round2-01, receipts against kitty 0.48.0):

  * kitty execs this file with ``exec(code, {'__name__': 'kitten'})``
    (``kittens/runner.py:56-63``). There is NO ``__file__`` in that globals
    dict — touching it raises ``NameError`` before a single gesture can run.
    The directory is recovered from ``sys.path[0]``, which the loader has just
    set to ``dirname(path)`` (``runner.py:57-58``).

  * ``handle_result.no_ui = True`` means kitty calls
    ``end_kitten.handle_result(None, w.id, boss)`` directly
    (``boss.py:2325-2326``) — ``main()`` is NEVER called and ``answer`` is
    always ``None``. The gesture therefore has to be read out of ``args``,
    which ``create_kitten_handler`` bound as ``[kitten, *orig_args]``
    (``runner.py:90``).

Both of those are covered by ``tests/unit/test_kitten.py``, which drives this
file through the real ``kittens.runner.create_kitten_handler``.
"""

from __future__ import annotations

import os
import sys


def _kitten_dir() -> str:
    """Directory this kitten was loaded from, without relying on ``__file__``.

    kitty's custom-kitten loader compiles the source and ``exec``s it with a
    globals dict containing only ``__name__`` (runner.py:62), so ``__file__``
    is undefined at load time. It does, however, insert ``dirname(path)`` at
    ``sys.path[0]`` immediately beforehand (runner.py:57-58), so that entry is
    the authoritative answer under kitty. Normal imports (dev tree, unit
    tests) still get the fast, exact ``__file__`` path.
    """
    here = globals().get("__file__")
    if here:
        return os.path.dirname(os.path.realpath(here))
    for cand in sys.path[:1]:
        if cand and os.path.isfile(os.path.join(cand, "hk.py")):
            return os.path.realpath(cand)
    config_dir = os.environ.get("KITTY_CONFIG_DIRECTORY")
    if config_dir:
        for cand in (os.path.join(config_dir, "hk-kitten"), config_dir):
            if os.path.isfile(os.path.join(cand, "hk.py")):
                return os.path.realpath(cand)
    # Last resort: sys.path[0] verbatim. Better a wrong directory than a
    # NameError that kills dispatch outright.
    return os.path.realpath(sys.path[0] or os.getcwd())


_HERE = _kitten_dir()
for _cand in (_HERE, os.path.dirname(_HERE)):
    if _cand not in sys.path:
        sys.path.insert(0, _cand)

GESTURES = ("toggle", "fork", "scrollback", "voice")

try:
    from kitten import ladder  # dev tree: <repo>/kitten/ladder.py
except ImportError:
    import ladder  # installed beside hk.py in the kitten subdirectory


# ---- declarative kitten CLI (ssh-kitten convention, RULING §2) -------------
#
# kitty reads these module globals to render `kitten hk.py --help` and to build
# the docs entry; see kittens/broadcast/main.py:118-165 for the reference shape.

OPTIONS = '''
--dry-run
type=bool-set
Resolve the gesture and print what would happen without touching any window.
Useful when wiring new key maps.


'''.format

usage = '{}'.format(' | '.join(GESTURES))

help_text = (
    'Dispatch a herdr-kitten gesture on the kitty window the key map fired in. '
    'toggle drives the herdr prefix (or opens a herdr split for a plain window), '
    'fork opens the scrollback of the current herdr pane in nvim, '
    'scrollback routes to herdr edit-scrollback or kitty show_scrollback, '
    'and voice points at the `hk voice` CLI endpoint. '
    'This kitten is meant to be bound from kitty.conf, not run by hand.'
)

short_desc = 'Dispatch a herdr-kitten gesture (toggle/fork/scrollback/voice)'


def main(args: list[str]) -> str:
    """CLI entry point.

    Only reached when the kitten is run WITHOUT ``no_ui`` (i.e. by hand, from
    the command line). Under a key map, ``handle_result`` is called directly
    and this never runs — which is precisely the trap BUG-2 fell into.
    """
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
    # dev tree: <repo>/assets ; installed: <kitten dir>/hk-assets
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
    _show_error(boss, "herdr-kitten: voice",
                "Dictation is driven by the CLI: `hk voice begin|text|end`. "
                "Bind that, not the `voice` gesture.")


def _show_error(boss, title: str, message: str) -> None:
    """Surface a message where a GUI user can actually see it.

    A kitten bound to a key map has no terminal attached to its stderr: a bare
    `print(..., file=sys.stderr)` lands in kitty's log and the user sees an
    apparently dead keybinding. kitty's Boss exposes show_error (boss.py:2497)
    for exactly this. stderr is still written so headless tests and
    `kitty --debug-*` keep their receipt.
    """
    print(f"hk.py: {title}: {message}", file=sys.stderr)
    show = getattr(boss, "show_error", None)
    if callable(show):
        try:
            show(title, message)
        except Exception:
            pass


def _gesture_from(args, answer) -> str:
    """The gesture this invocation is asking for.

    ``no_ui`` kittens never see an ``answer`` — kitty passes None
    (boss.py:2325-2326). ``args`` is what create_kitten_handler bound:
    ``[kitten, *orig_args]`` (runner.py:90), so the gesture is args[1].
    ``answer`` is honoured when a non-no_ui caller supplies one, which keeps
    the hand-run `kitten hk.py toggle` path working too.
    """
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    if args and len(args) > 1 and isinstance(args[1], str):
        return args[1].strip()
    return ""


def handle_result(args: list[str], answer: str, target_window_id: int, boss) -> None:
    gesture = _gesture_from(args, answer)
    if gesture not in GESTURES:
        _show_error(
            boss, "herdr-kitten: unknown gesture",
            f"{gesture!r} is not a herdr-kitten gesture. "
            f"Expected one of: {', '.join(GESTURES)}. "
            "Check the `kitten hk-kitten/hk.py <gesture>` line in your kitty.conf.")
        return
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return
    {"toggle": _toggle, "fork": _fork, "scrollback": _scrollback, "voice": _voice}[gesture](boss, window)


handle_result.no_ui = True


if __name__ == '__main__':
    main(sys.argv)
elif __name__ == '__doc__':
    cd = sys.cli_docs  # type: ignore[attr-defined]
    cd['usage'] = usage
    cd['options'] = OPTIONS
    cd['help_text'] = help_text
    cd['short_desc'] = short_desc
