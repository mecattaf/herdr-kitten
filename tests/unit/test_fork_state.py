"""Fork delivery-state unit tests (spec 11.2-11.5, D11) — pure python."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kitten import fork_state as fs


class DecideTest(unittest.TestCase):
    def test_first_save_delivers_all(self):
        self.assertEqual(fs.decide("", "para one\n\npara two\n"),
                         (fs.DELIVER_ALL, "para one\n\npara two\n"))

    def test_empty_first_save_nothing(self):
        self.assertEqual(fs.decide("", ""), (fs.DELIVER_NOTHING, ""))

    def test_unchanged_noop(self):
        self.assertEqual(fs.decide("body\n", "body\n"), (fs.DELIVER_NOTHING, ""))

    def test_append_only_delivers_suffix(self):
        self.assertEqual(fs.decide("one\n", "one\ntwo\n"),
                         (fs.DELIVER_SUFFIX, "two\n"))

    def test_inner_edit_conflicts(self):
        self.assertEqual(fs.decide("one\ntwo\n", "one!\ntwo\nthree\n"),
                         (fs.CONFLICT, ""))

    def test_truncation_conflicts(self):
        self.assertEqual(fs.decide("one\ntwo\n", "one\n"), (fs.CONFLICT, ""))
