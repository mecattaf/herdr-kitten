"""Unit tests for the herdr-client predicate (spec 2.4, D3)."""

import unittest

from hk import predicate


def win(user_vars=None, fg=None):
    return {
        "user_vars": user_vars or {},
        "foreground_processes": fg or [],
    }


class PredicateTest(unittest.TestCase):
    def test_role_primary_wins(self):
        self.assertTrue(predicate.is_herdr_client(win({"hk_role": "herdr"})))
        self.assertTrue(predicate.is_herdr_client(win({"hk_role": "herdr_ui"})))

    def test_unknown_role_is_not_client(self):
        # a role we did not stamp means some other tool owns the window
        self.assertFalse(predicate.is_herdr_client(win({"hk_role": "somethingelse"})))

    def test_argv_confirms_without_role(self):
        fg = [{"cmdline": ["/nix/store/xxx/bin/herdr", "terminal", "attach", "t1"]}]
        self.assertTrue(predicate.is_herdr_client(win(fg=fg)))

    def test_plain_window_is_not_client(self):
        fg = [{"cmdline": ["/run/current-system/sw/bin/bash"]}]
        self.assertFalse(predicate.is_herdr_client(win(fg=fg)))

    def test_empty_window(self):
        self.assertFalse(predicate.is_herdr_client({}))

    def test_thin_client_tier(self):
        self.assertTrue(predicate.is_thin_client(win({"hk_role": "herdr_ui"})))
        self.assertFalse(predicate.is_thin_client(win({"hk_role": "herdr"})))
