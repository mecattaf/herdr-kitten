"""Loader-level probe for kitten/hk.py — run under `kitty +launch`.

This file is NOT a unittest. It is the half of `tests/unit/test_kitten.py`
that has to execute inside a real kitty python, because the two fatal bugs it
guards against are properties of kitty's own loader, not of our source:

  * BUG-1: `kittens/runner.py:56-63` execs a custom kitten with globals
    `{'__name__': 'kitten'}` — no `__file__`. Any top-level `__file__` read is
    a NameError before dispatch.
  * BUG-2: `handle_result.no_ui = True` makes `boss.py:2325-2326` call
    `handle_result(None, window_id, boss)`. `main()` never runs and `answer`
    is always None, so the gesture must come out of `args`.

Nothing here mocks the loader: we call the real
`kittens.runner.create_kitten_handler` and the real bound partial, and only
the *kitty side* (Boss/Window) is faked, exactly as boss.py would supply it.

Usage:  kitty +launch tests/unit/kitten_loader_probe.py <path-to-hk.py> <gesture>
Prints a single JSON object describing every effect the gesture produced.
"""

import json
import sys


class FakeWindow:
    def __init__(self, user_vars=None, foreground=None):
        self.user_vars = dict(user_vars or {})
        self.written = []
        self.child = _FakeChild(foreground or [])

    def write_to_child(self, data):
        # hex, not text: these are control bytes (\x02 = herdr's prefix key) and
        # any text encoding of them makes the assertions ambiguous.
        self.written.append(data.hex() if isinstance(data, bytes) else str(data))


class _FakeChild:
    def __init__(self, foreground):
        self.foreground_processes = list(foreground)


class FakeBoss:
    """The subset of kitty's Boss a no_ui kitten is allowed to touch."""

    def __init__(self, window):
        self.window_id_map = {1: window}
        self.remote_control = []
        self.closed = []
        self.errors = []

    def call_remote_control(self, window, args):
        self.remote_control.append(list(args))

    def mark_window_for_close(self, window):
        self.closed.append(getattr(window, "user_vars", {}))

    def show_error(self, title, msg):
        self.errors.append({"title": title, "msg": msg})


def main():
    kitten_path, gesture = sys.argv[1], sys.argv[2]
    user_vars = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    foreground = json.loads(sys.argv[4]) if len(sys.argv) > 4 else []

    from kittens.runner import create_kitten_handler

    # This is the exact call kitty makes for a `map ... kitten hk.py <gesture>`
    # binding, and the exact point BUG-1 used to raise NameError.
    handler = create_kitten_handler(kitten_path, [gesture])

    window = FakeWindow(user_vars, foreground)
    boss = FakeBoss(window)

    # And this is boss.py:2325-2326 verbatim for a no_ui kitten: answer=None.
    handler.handle_result(None, 1, boss)

    print(json.dumps({
        "loaded": True,
        "no_ui": bool(handler.no_ui),
        "written": window.written,
        "remote_control": boss.remote_control,
        "closed": len(boss.closed),
        "errors": boss.errors,
    }))


if __name__ == "__main__":
    main()
