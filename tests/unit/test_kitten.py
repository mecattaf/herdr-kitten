"""The regression floor for the kitty kitten (RULING §3.4 item 1, BUG-0).

Before round2-01 this repo had ZERO tests that ever invoked the kitten entry
point — `grep -rn handle_result tests/` was empty — which is exactly why two
fatal loader bugs shipped to a "ship-ready" verdict. Every test here drives
`kitten/hk.py` through the REAL kitty loader
(`kittens.runner.create_kitten_handler`) in a real kitty python, then calls
the bound `handle_result` the way `boss.py:2325-2326` calls it for a no_ui
kitten.

Skips are not free here: set HK_REQUIRE_KITTY=1 (the flake check does) and a
missing kitty binary becomes a FAILURE instead of a silent pass. That is the
CI-honesty rule from round2-14 applied at the source.
"""

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
KITTEN = REPO / "kitten" / "hk.py"
PROBE = Path(__file__).resolve().parent / "kitten_loader_probe.py"


def _kitty() -> str | None:
    return os.environ.get("HK_KITTY_BIN") or shutil.which("kitty")


def _require_kitty() -> bool:
    return os.environ.get("HK_REQUIRE_KITTY") == "1"


class KittyLoaderTestCase(unittest.TestCase):
    """Base class owning the `kitty +launch` bridge into the real loader."""

    @classmethod
    def setUpClass(cls):
        cls.kitty = _kitty()
        if cls.kitty is None:
            if _require_kitty():
                raise AssertionError(
                    "HK_REQUIRE_KITTY=1 but no kitty binary is on PATH: the "
                    "loader-level gate cannot run, and a skip here is how "
                    "BUG-1/BUG-2 shipped. Provide kitty or unset the flag.")
            raise unittest.SkipTest(
                "kitty not on PATH; loader-level kitten gate not executed "
                "(set HK_REQUIRE_KITTY=1 to make this a failure)")

    def drive(self, gesture, user_vars=None, foreground=None):
        """Load hk.py through kitty's own loader and fire one gesture."""
        proc = subprocess.run(
            [self.kitty, "+launch", str(PROBE), str(KITTEN), gesture,
             json.dumps(user_vars or {}), json.dumps(foreground or [])],
            capture_output=True, text=True)
        self.assertEqual(
            proc.returncode, 0,
            f"kitten loader probe failed for gesture {gesture!r}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        last = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
        self.assertTrue(last, f"probe printed no JSON:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(last[-1])


class LoaderContractTest(KittyLoaderTestCase):
    """BUG-1 and BUG-2: the kitten must LOAD and must DISPATCH."""

    def test_loads_under_the_real_kitten_loader(self):
        # BUG-1 repro, pre-fix: NameError: name '__file__' is not defined,
        # raised inside exec(code, {'__name__': 'kitten'}) at runner.py:63.
        result = self.drive("toggle", {"hk_role": "herdr_ui"})
        self.assertTrue(result["loaded"])
        self.assertTrue(result["no_ui"], "handle_result.no_ui must stay True")

    def test_gesture_comes_from_args_not_answer(self):
        # BUG-2 repro, pre-fix: AttributeError on None.strip(), because a no_ui
        # kitten is called as handle_result(args, None, wid, boss) and main()
        # is never invoked. A herdr_ui window must take the PREFIX branch.
        result = self.drive("toggle", {"hk_role": "herdr_ui"})
        self.assertEqual(result["written"], ["02"])
        self.assertEqual(result["errors"], [],
                         "a valid gesture must not surface an error")


class GestureDispatchTest(KittyLoaderTestCase):
    """Every advertised gesture, driven through the loader, asserting effects."""

    def test_toggle_prefix_on_herdr_client(self):
        result = self.drive("toggle", {"hk_role": "herdr"})
        self.assertEqual(result["written"], ["02"])
        self.assertEqual(result["remote_control"], [])

    def test_toggle_closes_the_launched_split(self):
        result = self.drive("toggle", {"hk_role": "split"})
        self.assertEqual(result["closed"], 1, "second toggle must close (close IS detach)")
        self.assertEqual(result["written"], [])

    def test_toggle_launches_split_on_plain_window(self):
        result = self.drive("toggle", {}, [{"cmdline": ["bash"]}])
        self.assertEqual(len(result["remote_control"]), 1)
        argv = result["remote_control"][0]
        self.assertEqual(argv[0], "launch")
        self.assertIn("--location=vsplit", argv)
        self.assertIn("hk_role=split", argv)
        self.assertEqual(argv[-2:], ["hk", "open"])

    def test_scrollback_herdr_lane_writes_edit_scrollback(self):
        result = self.drive("scrollback", {"hk_role": "herdr"})
        self.assertEqual(result["written"], ["0265"])
        self.assertEqual(result["remote_control"], [])

    def test_scrollback_plain_lane_uses_kitty_action(self):
        result = self.drive("scrollback", {}, [{"cmdline": ["bash"]}])
        self.assertEqual(result["written"], [])
        self.assertEqual(result["remote_control"], [["action", "show_scrollback"]])

    def test_fork_opens_nvim_for_a_stamped_window(self):
        result = self.drive("fork", {"hk_pane": "w1:p9"})
        self.assertEqual(len(result["remote_control"]), 1)
        argv = result["remote_control"][0]
        self.assertEqual(argv[0], "launch")
        self.assertIn("--os-window-class=hk-fork", argv)
        self.assertIn("HK_FORK_PANE=w1:p9", argv)
        self.assertIn("nvim", argv)

    def test_fork_is_a_silent_noop_without_a_pane(self):
        result = self.drive("fork", {})
        self.assertEqual(result["remote_control"], [])
        self.assertEqual(result["written"], [])
        self.assertEqual(result["errors"], [], "spec 11.8: no bell, no window, no dialog")

    def test_voice_points_at_the_cli_visibly(self):
        result = self.drive("voice", {})
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("hk voice", result["errors"][0]["msg"])


class UnknownGestureTest(KittyLoaderTestCase):
    def test_unknown_gesture_is_visible_to_a_gui_user(self):
        # A bare stderr print from a key-map kitten is invisible: the user just
        # sees a dead keybinding. It has to reach boss.show_error.
        result = self.drive("tooggle", {})
        self.assertEqual(len(result["errors"]), 1, "must surface, not vanish into the log")
        self.assertIn("tooggle", result["errors"][0]["msg"])
        self.assertIn("toggle", result["errors"][0]["msg"], "must list the valid gestures")
        self.assertEqual(result["written"], [])
        self.assertEqual(result["remote_control"], [])


class DeclarativeCLITest(KittyLoaderTestCase):
    """ssh-kitten convention (RULING §2): the kitten introspects."""

    def test_declarative_globals_are_exported_to_the_docs_hook(self):
        proc = subprocess.run(
            [self.kitty, "+runpy",
             "import sys, types;"
             "src = open(sys.argv[1]).read();"
             "cd = {};"
             "sys.cli_docs = cd;"
             "g = {'__name__': '__doc__'};"
             "exec(compile(src, sys.argv[1], 'exec'), g);"
             "print(sorted(cd));"
             "print(cd.get('short_desc'))",
             str(KITTEN)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("help_text", proc.stdout)
        self.assertIn("short_desc", proc.stdout)
        self.assertIn("usage", proc.stdout)
        self.assertIn("options", proc.stdout)
        self.assertIn("gesture", proc.stdout.lower())


class SourceRegressionTest(unittest.TestCase):
    """Cheap, kitty-free guards so the exact regressions cannot creep back.

    These run everywhere, including a machine with no kitty at all.
    """

    def setUp(self):
        self.src = KITTEN.read_text()

    def test_no_toplevel_file_dunder(self):
        # `__file__` inside _kitten_dir() is guarded by globals().get; a bare
        # top-level read is the BUG-1 regression.
        for line in self.src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "globals()" in stripped:
                continue
            self.assertNotRegex(
                stripped, r"^_?\w+\s*=\s*os\.path\.\w+\(os\.path\.realpath\(__file__\)",
                "BUG-1 regression: kitty's loader provides no __file__ "
                f"(offending line: {stripped!r})")

    def test_handle_result_does_not_strip_the_answer(self):
        # BUG-2 regression: answer is None for a no_ui kitten.
        # The bug was the *assignment*: gesture = answer.strip() at the top of
        # handle_result. answer.strip() inside the resolver is fine and wanted.
        self.assertNotIn("gesture = answer.strip()", self.src)
        self.assertIn("_gesture_from(args, answer)", self.src)

    def test_no_ui_flag_survives(self):
        self.assertIn("handle_result.no_ui = True", self.src)

    def test_gesture_tuple_matches_the_dispatch_table(self):
        gestures = re.search(r"^GESTURES = \((.*?)\)$", self.src, re.M).group(1)
        names = set(re.findall(r'"(\w+)"', gestures))
        table = re.search(r'\{"toggle".*?\}\[gesture\]', self.src, re.S).group(0)
        self.assertEqual(names, set(re.findall(r'"(\w+)":', table)))


if __name__ == "__main__":
    unittest.main()
