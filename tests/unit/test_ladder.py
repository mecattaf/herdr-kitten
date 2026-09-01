"""Routing-table unit tests (spec 6.4: a herdr window NEVER reaches the plain
lane; spec 10.5/10.6 toggle ladder; spec 11.8 fork no-op)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kitten import ladder


def win(role=None, fg=None):
    return {"user_vars": ({"hk_role": role} if role else {}),
            "foreground_processes": fg or []}


class ToggleLadderTest(unittest.TestCase):
    def test_thin_client_defers_to_prefix(self):
        self.assertEqual(ladder.toggle_action(win("herdr_ui")), ladder.PREFIX)

    def test_split_window_closes(self):
        self.assertEqual(ladder.toggle_action(win("split")), ladder.CLOSE)

    def test_herdr_client_gets_prefix(self):
        self.assertEqual(ladder.toggle_action(win("herdr")), ladder.PREFIX)
        argv = [{"cmdline": ["/bin/herdr", "terminal", "attach", "t"]}]
        self.assertEqual(ladder.toggle_action(win(fg=argv)), ladder.PREFIX)

    def test_plain_window_launches_split(self):
        self.assertEqual(ladder.toggle_action(win(fg=[{"cmdline": ["bash"]}])),
                         ladder.LAUNCH_SPLIT)


class DispatcherTest(unittest.TestCase):
    def test_herdr_windows_never_plain(self):
        for w in (win("herdr"), win("herdr_ui"), win("split"), win("fork"),
                  win("editor"),
                  win(fg=[{"cmdline": ["herdr", "--remote", "h"]}])):
            self.assertEqual(ladder.scrollback_lane(w), ladder.HERDR_LANE, w)

    def test_plain_windows_plain(self):
        self.assertEqual(ladder.scrollback_lane(win(fg=[{"cmdline": ["bash"]}])),
                         ladder.PLAIN_LANE)
        self.assertEqual(ladder.scrollback_lane(win()), ladder.PLAIN_LANE)


class ForkTargetTest(unittest.TestCase):
    def test_target_from_user_var(self):
        w = {"user_vars": {"hk_pane": "w1:p9"}}
        self.assertEqual(ladder.fork_target(w), "w1:p9")

    def test_no_var_silent_none(self):
        self.assertIsNone(ladder.fork_target(win()))
        self.assertIsNone(ladder.fork_target({"user_vars": {"hk_pane": ""}}))
