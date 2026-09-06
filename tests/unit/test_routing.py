"""Structural checks on the CLI surface: argument parsing, verb routing, and the
two "no verb may ever do X" rulings that only source inspection can enforce.

These are the claims the spec files under [check: herdr-kitten-build].
"""

import ast
import importlib.util
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent


def _load_bin_hk():
    """bin/hk has no .py suffix; load it as a module so the parser is testable."""
    spec = importlib.util.spec_from_loader(
        "bin_hk", importlib.machinery.SourceFileLoader("bin_hk", str(REPO / "bin" / "hk")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bin_hk = _load_bin_hk()


class ParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = bin_hk.build_parser()

    def test_vocabulary_hygiene(self):
        """spec D17 / F.12: drain, handoff, pickup name nothing here."""
        actions = self.parser._subparsers._group_actions[0].choices
        for forbidden in ("drain", "handoff", "pickup"):
            self.assertNotIn(forbidden, actions)

    def test_the_ruled_verb_set_is_what_ships(self):
        """spec D17 names the verb list exactly; nothing extra, nothing missing."""
        ruled = {"open", "new", "run", "send", "read", "rename", "resume", "focus",
                 "ws", "materialise", "dematerialise", "fork", "ssh", "voice",
                 "notifyd", "doctor", "config",
                 # HK-1 (#36/#37/#38): the supervised lane. The pin's job is to
                 # catch a verb appearing BY ACCIDENT; a verb the card mandates
                 # is added here by hand, which is the whole point of a pin.
                 "lane"}
        shipped = set(self.parser._subparsers._group_actions[0].choices)
        # `agent` is the D23 CLI-only pass-through, ruled in but absent from the
        # D17 sentence that enumerates gestures.
        self.assertEqual(shipped - {"agent"}, ruled)

    def test_send_routes_submit_and_target(self):
        # round2-05 (T14): the positional is `target`, not `pane` — a pane id is
        # only one of the three things it accepts.
        args = self.parser.parse_args(["send", "--submit", "w1:p2"])
        self.assertTrue(args.submit)
        self.assertEqual(args.target, "w1:p2")
        self.assertEqual(args.func.__name__, "cmd_send")

    def test_send_defaults_to_populate_only(self):
        """spec F.14: --submit is opt-in, never a default."""
        self.assertFalse(self.parser.parse_args(["send", "w1:p2"]).submit)

    def test_host_is_global_and_defaults_off(self):
        """spec 4.3: `hk --host h send ...`."""
        self.assertIsNone(self.parser.parse_args(["send", "w1:p2"]).host)
        self.assertEqual(self.parser.parse_args(["--host", "box", "send", "w1:p2"]).host,
                         "box")

    def test_run_captures_argv_after_the_separator(self):
        args = self.parser.parse_args(["run", "--", "sh", "-c", "echo hi"])
        self.assertEqual(args.argv, ["--", "sh", "-c", "echo hi"])
        self.assertEqual(args.func.__name__, "cmd_run")

    def test_read_lines_is_optional_and_typed(self):
        self.assertIsNone(self.parser.parse_args(["read", "w1:p1"]).lines)
        self.assertEqual(self.parser.parse_args(["read", "w1:p1", "--lines", "5000"]).lines,
                         5000)

    def test_rename_takes_a_multiword_label(self):
        args = self.parser.parse_args(["rename", "w1:p1", "my", "long", "label"])
        self.assertEqual(args.label, ["my", "long", "label"])

    def test_ws_verbs(self):
        for verb in ("list", "new", "focus", "rename"):
            self.assertEqual(self.parser.parse_args(["ws", verb]).ws_verb, verb)

    def test_lane_routes_its_four_verbs_and_a_preset_path(self):
        """HK-1: the preset is a FILE (data the caller declares), the verb is one
        of four, and both reach `hk.lane.cmd_lane` — which owns the §5 exits."""
        for verb in ("start", "deliver", "status", "stop"):
            args = self.parser.parse_args(["lane", verb, "./lane.toml"])
            self.assertEqual(args.lane_verb, verb)
            self.assertEqual(args.preset, "./lane.toml")
            self.assertEqual(args.func.__name__, "_cmd_lane")
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["lane", "wait", "./lane.toml"])

    def test_resume_print_and_attach(self):
        self.assertTrue(self.parser.parse_args(["resume", "--print"]).print_only)
        self.assertEqual(self.parser.parse_args(["resume", "--attach", "term_x"]).attach,
                         "term_x")


class DeliveryPathTest(unittest.TestCase):
    """spec 4.4: no verb wraps `kitty @ send-text` for pane delivery — delivery
    code paths contain only herdr transports (census-map P15/P79)."""

    def test_kitty_is_invoked_from_exactly_one_module(self):
        """Every `kitty @` argv in the repo is built in hk/kittyc.py, so
        "which kitty verbs does hk use" is answerable by reading one file."""
        callers = sorted(
            str(path.relative_to(REPO))
            for path in [REPO / "bin" / "hk", *(REPO / "hk").rglob("*.py")]
            if '"kitty", "@"' in path.read_text())
        self.assertEqual(callers, ["hk/kittyc.py"])

    def test_kitty_wrapper_exposes_no_send_verb(self):
        """spec 4.4: delivery never rides `kitty @ send-text` — the wrapper does
        not expose the verb, so no verb can reach for it."""
        from hk import kittyc
        source = pathlib.Path(kittyc.__file__).read_text()
        self.assertNotIn("send-text", source)
        self.assertNotIn("send_text", source)
        self.assertFalse([name for name in dir(kittyc) if "send" in name])

    def test_no_kitty_tab_verb(self):
        """spec F.10 / D18: the repo never calls a kitty tab verb."""
        from hk import kittyc
        source = pathlib.Path(kittyc.__file__).read_text()
        for tab_verb in ("set-tab-title", "set-tab-color", "new-tab", "close-tab",
                         "goto-tab", "detach-tab"):
            self.assertNotIn(tab_verb, source)


class PredicateSingleSourceTest(unittest.TestCase):
    """spec 2.4 / D3: the predicate is defined in ONE module and imported."""

    def test_only_predicate_module_defines_it(self):
        definers = []
        for path in [REPO / "bin" / "hk", *(REPO / "hk").rglob("*.py"),
                     *(REPO / "kitten").rglob("*.py")]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "is_herdr_client":
                    definers.append(str(path.relative_to(REPO)))
        self.assertEqual(definers, ["hk/predicate.py"])


class ConfigSurfaceTest(unittest.TestCase):
    """spec 1.6 / F.4: exactly one config template plus one profile snippet."""

    def test_conf_tree_shape(self):
        names = sorted(p.name for p in (REPO / "conf").iterdir() if p.is_file())
        self.assertEqual(names, ["config.toml", "herdr-profile.toml", "kitty-maps.conf"])

    def test_defaults_stand_alone(self):
        """spec 1.4: absent hk-config -> defaults, and nothing is written."""
        from hk import config as hk_config
        self.assertIn("plain_scrollback_action", hk_config.DEFAULTS)
        self.assertIn("notify_command", hk_config.DEFAULTS)
        source = pathlib.Path(hk_config.__file__).read_text()
        for writer in ("open(", "write", "mkdir"):
            if writer == "open(":
                self.assertNotIn('"wb"', source)
                self.assertNotIn('"w"', source)
            else:
                self.assertNotIn(f".{writer}", source)


if __name__ == "__main__":
    unittest.main()
