"""Targeting parity — T13 (`--current`), T14 (agent-name targets), T15
(HERDR_ENV as a precondition). RULING-kitten.md §1, round2-05 / issue #19.

Two claims carry the unit: that a target is resolved BEFORE any byte moves, and
that `--current` refuses outside a herdr-managed pane. Both are asserted the
strong way — by counting the delivery calls that did not happen — because the
weak form (assert the exit code) passes even when a payload has already landed
in someone else's pane.
"""

import importlib.machinery
import importlib.util
import io
import pathlib
import unittest
import unittest.mock

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

from hk import herdrc, verbs


def _load_bin_hk():
    spec = importlib.util.spec_from_loader(
        "bin_hk_targeting",
        importlib.machinery.SourceFileLoader("bin_hk_targeting", str(REPO / "bin" / "hk")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bin_hk = _load_bin_hk()

MANAGED = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}


def args(**fields):
    """A parsed-args stand-in with the transport-verb field set."""
    base = {"target": None, "current": False, "host": None,
            "submit": False, "raw": False, "lines": None, "text": False}
    base.update(fields)
    return unittest.mock.Mock(**base)


class TargetKindTest(unittest.TestCase):
    """The grammar lives in one function, so `what is this string` has one answer."""

    def test_pane_ids(self):
        for pane in ("w1:p1", "w12:p345", "w1:t1"):
            self.assertEqual(verbs.target_kind(pane), "pane", pane)

    def test_terminal_ids(self):
        # shape measured live: herdr 0.8.2 answers terminal_id "term_65accb4eef0d01"
        self.assertEqual(verbs.target_kind("term_65accb4eef0d01"), "terminal")

    def test_agent_names(self):
        for name in ("alpha", "claude-2", "reviewr", "a", "worker_7"):
            self.assertEqual(verbs.target_kind(name), "agent", name)

    def test_nonsense_is_not_silently_a_name(self):
        """A target hk cannot classify must not be handed to the server to
        puzzle over — that is how a typo becomes an `agent_not_found` the user
        reads as "the agent died"."""
        for junk in ("", "two words", "w1:p1:extra", "with/slash", None, 7):
            self.assertEqual(verbs.target_kind(junk), "unknown", repr(junk))

    def test_agent_grammar_is_wider_than_what_hk_will_mint(self):
        """hk refuses to CREATE an agent slug with capitals (AGENT_SLUG_RE), but
        it must still be able to ADDRESS a name herdr already holds."""
        self.assertEqual(verbs.target_kind("Alpha"), "agent")


class CurrentPaneTest(unittest.TestCase):
    """T13 + T15: --current is HERDR_PANE_ID, gated on HERDR_ENV."""

    def test_managed_pane_resolves(self):
        self.assertEqual(verbs.current_pane(MANAGED), "w1:p1")

    def test_herdr_env_unset_refuses_even_with_a_pane_id_present(self):
        """THE unit. HERDR_PANE_ID is inherited by every child of a pane and
        survives into environments herdr did not build; without HERDR_ENV it is
        not evidence that this process is in that pane."""
        with self.assertRaises(verbs.TargetError) as caught:
            verbs.current_pane({"HERDR_PANE_ID": "w1:p1"})
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_HERDR_WINDOW)
        self.assertIn("HERDR_ENV", str(caught.exception))

    def test_blank_herdr_env_is_unset(self):
        for value in ("", "   "):
            with self.assertRaises(verbs.TargetError):
                verbs.current_pane({"HERDR_ENV": value, "HERDR_PANE_ID": "w1:p1"})

    def test_env_without_pane_id_is_typed_not_a_keyerror(self):
        with self.assertRaises(verbs.TargetError) as caught:
            verbs.current_pane({"HERDR_ENV": "1"})
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_HERDR_WINDOW)

    def test_message_is_one_line_and_says_nothing_was_sent(self):
        for env in ({"HERDR_PANE_ID": "w1:p1"}, {"HERDR_ENV": "1"}):
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.current_pane(env, verb="send")
            message = str(caught.exception)
            self.assertNotIn("\n", message)
            self.assertIn("Nothing was sent", message)
            self.assertTrue(message.startswith("send: "), message)


class ResolveTargetTest(unittest.TestCase):
    def test_pane_id_passes_through_untouched(self):
        self.assertEqual(verbs.resolve_target(args(target="w1:p2")), "w1:p2")

    def test_current_wins_from_the_environment(self):
        self.assertEqual(verbs.resolve_target(args(current=True), env=MANAGED), "w1:p1")

    def test_current_and_a_target_together_are_a_usage_error(self):
        with self.assertRaises(verbs.TargetError) as caught:
            verbs.resolve_target(args(target="w1:p2", current=True), env=MANAGED)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)

    def test_no_target_at_all_is_a_usage_error_naming_the_grammar(self):
        with self.assertRaises(verbs.TargetError) as caught:
            verbs.resolve_target(args(), env=MANAGED)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)
        self.assertIn("--current", str(caught.exception))

    def test_unclassifiable_target_never_reaches_the_server(self):
        with unittest.mock.patch.object(herdrc, "call") as call:
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.resolve_target(args(target="two words"), env=MANAGED)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)
        call.assert_not_called()


class AgentNameTest(unittest.TestCase):
    """T14. hk owns the name -> pane mapping because herdr does not.

    MEASURED live against herdr 0.8.2, this lane: with `agent list` reporting
    {"agent": "alpha", "pane_id": "w1:p1"},
        herdr agent get alpha -> {"error":{"code":"agent_not_found", ...}}
        herdr agent get w1:p1 -> that same agent
    The server's agent verbs take pane/terminal ids; the label exists only in
    `agent list`.
    """

    def agents(self, *rows):
        return unittest.mock.patch.object(
            herdrc, "call", lambda a, host=None: {"agents": list(rows)})

    def test_live_name_resolves_to_its_pane(self):
        with self.agents({"agent": "alpha", "pane_id": "w1:p1"},
                         {"agent": "beta", "pane_id": "w2:p3"}):
            self.assertEqual(verbs.resolve_agent("beta"), "w2:p3")

    def test_dead_name_fails_typed_and_lists_what_is_live(self):
        with self.agents({"agent": "alpha", "pane_id": "w1:p1"}):
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.resolve_agent("ghost")
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_HERDR_WINDOW)
        message = str(caught.exception)
        self.assertNotIn("\n", message)
        self.assertIn("ghost", message)
        self.assertIn("alpha", message)

    def test_no_agents_at_all_still_answers_in_one_line(self):
        with self.agents():
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.resolve_agent("ghost")
        self.assertIn("none", str(caught.exception))

    def test_an_agent_with_no_pane_is_not_a_target(self):
        with self.agents({"agent": "alpha"}):
            with self.assertRaises(verbs.TargetError):
                verbs.resolve_agent("alpha")

    def test_ambiguous_name_refuses_rather_than_picking(self):
        """Two live agents under one label is a coin flip over whose pane gets
        the payload. hk does not flip it."""
        with self.agents({"agent": "alpha", "pane_id": "w1:p1"},
                         {"agent": "alpha", "pane_id": "w2:p9"}):
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.resolve_agent("alpha")
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)
        self.assertIn("w1:p1", str(caught.exception))
        self.assertIn("w2:p9", str(caught.exception))

    def test_a_server_error_during_lookup_is_typed_not_a_traceback(self):
        def boom(_args, host=None):
            raise herdrc.HerdrError("socket unavailable", code="socket_unavailable")
        with unittest.mock.patch.object(herdrc, "call", boom):
            with self.assertRaises(verbs.TargetError) as caught:
                verbs.resolve_agent("alpha")
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_HERDR_ERROR)


class ZeroBytesSentTest(unittest.TestCase):
    """The guarantee the §5 exit-code contract sells: exit 3 means nothing moved.

    Asserted by counting deliveries, not by reading the exit code — a payload
    that already landed in the wrong pane also returns 3.
    """

    def setUp(self):
        self.calls = []
        for name in ("pane_send_input", "pane_send_text", "agent_prompt"):
            patch = unittest.mock.patch.object(
                herdrc, name,
                lambda *a, _n=name, **kw: self.calls.append((_n, a)))
            patch.start()
            self.addCleanup(patch.stop)

    def send(self, payload="MARKER", **fields):
        with unittest.mock.patch("sys.stdin", io.StringIO(payload)):
            return verbs.cmd_send(args(**fields))

    def test_current_without_herdr_env_sends_nothing(self):
        """The RED case, in unit form: delete the HERDR_ENV precondition and
        this test goes red because MARKER reaches w1:p1."""
        with unittest.mock.patch.dict("os.environ",
                                      {"HERDR_PANE_ID": "w1:p1"}, clear=True):
            code = self.send(current=True)
            self.assertEqual(code, verbs.EXIT_NOT_HERDR_WINDOW)
        self.assertEqual(self.calls, [])

    def test_current_inside_a_managed_pane_delivers_there(self):
        with unittest.mock.patch.dict("os.environ", dict(MANAGED), clear=True):
            self.assertEqual(self.send(current=True), verbs.EXIT_OK)
        self.assertEqual([(name, a[0]) for name, a in self.calls],
                         [("pane_send_input", "w1:p1")])

    def test_a_dead_agent_name_sends_nothing(self):
        with unittest.mock.patch.object(herdrc, "call",
                                        lambda a, host=None: {"agents": []}):
            self.assertEqual(self.send(target="ghost"),
                             verbs.EXIT_NOT_HERDR_WINDOW)
        self.assertEqual(self.calls, [])

    def test_a_live_agent_name_delivers_to_its_pane(self):
        with unittest.mock.patch.object(
                herdrc, "call",
                lambda a, host=None: {"agents": [{"agent": "alpha",
                                                  "pane_id": "w3:p7"}]}):
            self.assertEqual(self.send(target="alpha"), verbs.EXIT_OK)
        self.assertEqual([(name, a[0]) for name, a in self.calls],
                         [("pane_send_input", "w3:p7")])

    def test_submit_to_an_agent_name_prompts_its_pane(self):
        with unittest.mock.patch.object(
                herdrc, "call",
                lambda a, host=None: {"agents": [{"agent": "alpha",
                                                  "pane_id": "w3:p7"}]}):
            self.assertEqual(self.send(target="alpha", submit=True), verbs.EXIT_OK)
        self.assertEqual([(name, a[0]) for name, a in self.calls],
                         [("agent_prompt", "w3:p7")])

    def test_stdin_is_not_even_read_when_the_target_is_unreachable(self):
        """A caller piping a megabyte deserves the refusal before the pipe,
        not after it."""
        class Exploding(io.StringIO):
            def read(self, *a):
                raise AssertionError("stdin was read before the target resolved")

        with unittest.mock.patch.dict("os.environ",
                                      {"HERDR_PANE_ID": "w1:p1"}, clear=True):
            with unittest.mock.patch("sys.stdin", Exploding()):
                self.assertEqual(verbs.cmd_send(args(current=True)),
                                 verbs.EXIT_NOT_HERDR_WINDOW)


class ReadTargetTest(unittest.TestCase):
    """`hk read` is transport too (text OUT), so it carries the same grammar."""

    def test_read_current_resolves(self):
        seen = {}

        def fake_read(target, **kw):
            seen["target"] = target
            return ""

        with unittest.mock.patch.object(herdrc, "pane_read", fake_read):
            with unittest.mock.patch.dict("os.environ", dict(MANAGED), clear=True):
                self.assertEqual(verbs.cmd_read(args(current=True)), verbs.EXIT_OK)
        self.assertEqual(seen["target"], "w1:p1")

    def test_read_without_herdr_env_refuses(self):
        with unittest.mock.patch.object(herdrc, "pane_read") as read:
            with unittest.mock.patch.dict("os.environ",
                                          {"HERDR_PANE_ID": "w1:p1"}, clear=True):
                self.assertEqual(verbs.cmd_read(args(current=True)),
                                 verbs.EXIT_NOT_HERDR_WINDOW)
        read.assert_not_called()


class ParserSurfaceTest(unittest.TestCase):
    """The plumbing half: `bin/hk` names the argument `target` and offers
    `--current` on exactly the transport verbs."""

    def setUp(self):
        self.parser = bin_hk.build_parser()
        self.choices = self.parser._subparsers._group_actions[0].choices

    def transport(self):
        return ("send", "read")

    def test_transport_verbs_take_a_target_and_current(self):
        for verb in self.transport():
            parsed = self.parser.parse_args([verb, "--current"])
            self.assertTrue(parsed.current, verb)
            self.assertIsNone(parsed.target, verb)
            named = self.parser.parse_args([verb, "w1:p4"])
            self.assertFalse(named.current, verb)
            self.assertEqual(named.target, "w1:p4", verb)

    def test_an_agent_name_parses_as_a_target(self):
        self.assertEqual(self.parser.parse_args(["send", "alpha"]).target, "alpha")

    def test_no_transport_verb_still_calls_the_argument_pane(self):
        """T14 is a naming ruling as much as a routing one: help text that says
        `pane` teaches callers the wrong grammar."""
        for verb in self.transport():
            dests = [a.dest for a in self.choices[verb]._actions]
            self.assertIn("target", dests, verb)
            self.assertNotIn("pane", dests, verb)

    def test_current_is_not_bolted_onto_non_transport_verbs(self):
        """T13 says every TRANSPORT verb. `rename` and `focus` address a pane
        but move no text, and `rename`'s variadic label makes an optional
        positional genuinely ambiguous (`hk rename --current my label`). They
        keep their required `pane` until a ruling says otherwise."""
        for verb in ("rename", "focus", "materialise", "new", "ws"):
            dests = [a.dest for a in self.choices[verb]._actions]
            self.assertNotIn("current", dests, verb)

    def test_help_text_names_all_three_ways_to_target(self):
        source = (REPO / "bin" / "hk").read_text()
        for phrase in ("HERDR_PANE_ID", "HERDR_ENV", "agent name", "pane id"):
            self.assertIn(phrase, source, phrase)


if __name__ == "__main__":
    unittest.main()
