"""`hk voice` — the dictation endpoint's failure contract and its destination.

Two halves of BUG-6, both about the same promise: the caller contract says
"exit 3 means no herdr client is focused, zero bytes were sent, fall back and
inject". Before this unit the endpoint broke that promise in two directions —
it delivered to the WRONG window when several tabs were open, and it raised a
raw KittyError (26 lines of traceback, exit 1) when the caller had no
`$KITTY_LISTEN_ON`, which is every dictation daemon, since none of them is a
kitty child process.

Nothing here does voxtype work: no socket discovery, no compositor call, no
`--spin` frame-cycler. Those are open questions and not this unit's.
"""

import contextlib
import io
import os
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

from hk import herdrc, kittyc, voice  # noqa: E402


def build_ls(shape, focused_os=0, focused_tabs=None, kitty_has_focus=True):
    """A small `kitty @ ls` tree, active window 0 of every tab.

    Deliberately a local copy rather than an import from test_focus: the
    import audit (spec 1.3 / D1) allows only stdlib, `hk` and `kitten`, and
    a cross-test import is not worth loosening a repo law for. The full
    arrangement sweep over this shape lives in test_focus.py; what is needed
    here is only enough tree to name a destination pane.
    """
    focused_tabs = focused_tabs or [0] * len(shape)
    tree = []
    for oi, tabs in enumerate(shape):
        os_focused = kitty_has_focus and oi == focused_os
        tab_dicts = []
        for ti, n_windows in enumerate(tabs):
            tab_active = ti == focused_tabs[oi]
            tab_dicts.append({
                "id": 100 + ti,
                "is_active": tab_active,
                "is_focused": tab_active and os_focused,
                "windows": [{
                    "id": wi,
                    "is_active": wi == 0,
                    # kitty 0.48.0 tabs.py:1064 — stamped per TAB, the bug
                    "is_focused": os_focused and wi == 0,
                    "title": f"os{oi}/tab{ti}/win{wi}",
                    "user_vars": {"hk_role": "herdr", "hk_pane": f"w{oi}:p{ti}{wi}"},
                } for wi in range(n_windows)],
            })
        tree.append({"id": oi + 1, "is_active": oi == focused_os,
                     "is_focused": os_focused, "tabs": tab_dicts})
    return tree


@contextlib.contextmanager
def patched(**attrs):
    """Swap module attributes and put them back (no third-party mock: D1).

    Key `modulename__attrname`, e.g. `kittyc__focused_window`,
    `kittyc___run` (the module's `_run`), `herdrc__pane_send_input`.
    """
    saved = []
    for key, value in attrs.items():
        mod_name, attr = key.split("__", 1)
        mod = globals()[mod_name]
        saved.append((mod, attr, getattr(mod, attr)))
        setattr(mod, attr, value)
    try:
        yield
    finally:
        for mod, attr, value in saved:
            setattr(mod, attr, value)


class Delivered(list):
    def record(self, pane, text, host=None):
        self.append((pane, text))


class NoSocketTest(unittest.TestCase):
    """The traceback path, issue #21 fact 2."""

    def test_missing_kitty_socket_is_exit_3_one_line(self):
        sent = Delivered()

        def boom():
            raise kittyc.KittyError("not inside a kitty window (KITTY_LISTEN_ON unset)")

        err = io.StringIO()
        with patched(kittyc__focused_window=boom,
                     herdrc__pane_send_input=sent.record):
            with contextlib.redirect_stderr(err):
                rc = voice.cmd_text()
        self.assertEqual(rc, voice.EXIT_NOT_HERDR_WINDOW)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual(sent, [], "exit 3 means zero bytes sent")

    def test_the_cli_says_it_in_one_line_and_exits_3(self):
        """The whole program, not just the function: a daemon's argv reaches
        the fallback contract instead of an argparse usage dump."""
        env = {k: v for k, v in os.environ.items() if k != "KITTY_LISTEN_ON"}
        proc = subprocess.run([sys.executable, str(REPO / "bin" / "hk"),
                               "voice", "text", "hi"],
                              capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertNotIn("usage:", proc.stderr)


class DestinationTest(unittest.TestCase):
    """BUG-6 end to end: the pane the dictation lands in."""

    TREE = build_ls([[1, 1, 1]], focused_os=0, focused_tabs=[2])

    def deliver(self, tree, stdin="dictated words"):
        sent = Delivered()
        with patched(kittyc__focused_window=lambda: kittyc.resolve_focused_window(tree),
                     herdrc__pane_send_input=sent.record):
            saved, sys.stdin = sys.stdin, io.StringIO(stdin)
            try:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    rc = voice.cmd_text()
            finally:
                sys.stdin = saved
        return rc, sent, err.getvalue()

    def test_dictation_lands_in_the_focused_tab_not_the_first(self):
        rc, sent, _ = self.deliver(self.TREE)
        self.assertEqual(rc, voice.EXIT_OK)
        self.assertEqual(sent, [("w0:p20", "dictated words")],
                         "the third tab is focused; tab 1's pane is the BUG-6 answer")

    def test_no_focused_window_sends_nothing(self):
        tree = build_ls([[2, 2]], kitty_has_focus=False)
        rc, sent, err = self.deliver(tree)
        self.assertEqual(rc, voice.EXIT_NOT_HERDR_WINDOW)
        self.assertEqual(sent, [])
        self.assertEqual(len(err.strip().splitlines()), 1)

    def test_plain_window_still_falls_back(self):
        """G12's contract, unchanged by this unit."""
        tree = build_ls([[1]])
        tree[0]["tabs"][0]["windows"][0]["user_vars"] = {}
        rc, sent, err = self.deliver(tree)
        self.assertEqual(rc, voice.EXIT_NOT_HERDR_WINDOW)
        self.assertEqual(sent, [])
        self.assertIn("not a herdr client", err)


class ArgvIsNotAPayloadTest(unittest.TestCase):
    """`verbs.read_payload`'s standing rule holds inside voice too: the payload
    is always on stdin, never argv. Trailing words are refused, never sent."""

    def test_trailing_words_are_refused_once_a_destination_exists(self):
        tree = build_ls([[1]])
        sent = Delivered()
        err = io.StringIO()
        with patched(kittyc__focused_window=lambda: kittyc.resolve_focused_window(tree),
                     herdrc__pane_send_input=sent.record):
            with contextlib.redirect_stderr(err):
                rc = voice.cmd_text(argv_text=["hello", "there"])
        self.assertEqual(rc, voice.EXIT_USAGE)
        self.assertEqual(sent, [], "argv must never become a delivery channel")
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertIn("stdin", err.getvalue())

    def test_voice_reads_no_payload_from_argv_in_source(self):
        src = (REPO / "hk" / "voice.py").read_text()
        self.assertNotIn("join(argv_text", src)
        self.assertNotIn(" \".join(argv", src)


class SpinIsReservedTest(unittest.TestCase):
    """RULING-kitten §4 row #13: implement the frame-cycler or make the flag
    announce itself. DECISION-2 is open, so it announces itself."""

    def test_spin_announces_itself_and_still_shows_the_static_glyph(self):
        calls = []
        err = io.StringIO()
        with patched(kittyc___run=lambda args, check=True: calls.append(args)):
            with contextlib.redirect_stderr(err):
                rc = voice.cmd_begin("7", spin=True)
        self.assertEqual(rc, voice.EXIT_OK)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertIn("reserved", err.getvalue())
        self.assertEqual(len(calls), 1)
        self.assertIn("set-window-logo", calls[0])

    def test_without_spin_it_is_silent(self):
        err = io.StringIO()
        with patched(kittyc___run=lambda args, check=True: None):
            with contextlib.redirect_stderr(err):
                rc = voice.cmd_begin("7")
        self.assertEqual(rc, voice.EXIT_OK)
        self.assertEqual(err.getvalue(), "")

    def test_no_frame_cycler_was_implemented(self):
        src = (REPO / "hk" / "voice.py").read_text()
        for forbidden in ("time.sleep", "threading", "itertools.cycle", "spinner_frames"):
            self.assertNotIn(forbidden, src,
                             "the frame-cycler is DECISION-2, not this unit's")

    def test_the_flag_help_does_not_claim_a_feature(self):
        import importlib.machinery
        import importlib.util
        spec = importlib.util.spec_from_loader(
            "bin_hk_voice", importlib.machinery.SourceFileLoader(
                "bin_hk_voice", str(REPO / "bin" / "hk")))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parser = module.build_parser()
        voice_parser = parser._subparsers._group_actions[0].choices["voice"]
        begin = voice_parser._subparsers._group_actions[0].choices["begin"]
        spin = [a for a in begin._actions if a.dest == "spin"][0]
        self.assertIn("RESERVED", spin.help)


if __name__ == "__main__":
    unittest.main()
