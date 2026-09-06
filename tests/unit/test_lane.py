"""Supervised lanes from preset data — the pure paths (no server, no kitty).

Card HK-1; herdr-kitten #36/#37/#38 = tally.nix #670/#673/#678.

Two claims carry this module, and both are asserted the strong way:

  * **a preset is data, and hk validates all of it before launching anything.**
    Every structural fault is one typed line and exit 2, and the assertions
    count the herdr calls that did NOT happen — the weak form (assert the exit
    code) passes even when a pane has already been split.
  * **the exits are RULING-kitten §5's**, so a supervisor can branch on them:
    0 delivered · 1 refused, the herdr code verbatim · 2 preset/CLI syntax ·
    3 no lane reachable and zero bytes sent · 4 not implemented.
"""

import base64
import io
import pathlib
import tempfile
import unittest
import unittest.mock

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "supervised-lane"

from hk import herdrc, lane, verbs


def write_preset(body: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    handle.write(body)
    handle.close()
    return handle.name


GOOD = """
[lane]
name = "w"
argv = ["cat"]
"""


def args(verb: str, preset: str):
    return unittest.mock.Mock(lane_verb=verb, preset=preset, host=None)


class PresetShapeTest(unittest.TestCase):
    def test_minimal_preset_defaults(self):
        preset = lane.load_preset(write_preset(GOOD))
        self.assertEqual(preset["name"], "w")
        self.assertEqual(preset["argv"], ["cat"])
        self.assertEqual(preset["kind"], "supervised")
        self.assertEqual(preset["direction"], "down")
        self.assertIsNone(preset["ready_match"])
        self.assertEqual(preset["ready_timeout_ms"], lane.DEFAULT_READY_TIMEOUT_MS)
        self.assertFalse(preset["submit"])
        self.assertFalse(preset["raw"])

    def test_cwd_defaults_to_the_callers_cwd(self):
        import os
        self.assertEqual(lane.load_preset(write_preset(GOOD))["cwd"], os.getcwd())

    def test_argv_is_data_the_preset_declares(self):
        """The whole point of #36: hk knows no worker, only the argv it is given."""
        body = '[lane]\nname = "w"\nargv = ["bash", "-lc", "make -j && echo ok"]\n'
        self.assertEqual(lane.load_preset(write_preset(body))["argv"],
                         ["bash", "-lc", "make -j && echo ok"])


class MalformedPresetTest(unittest.TestCase):
    """Exit 2, one line, and nothing launched."""

    def assert_usage(self, body: str, needle: str):
        with self.assertRaises(lane.LaneError) as caught:
            lane.load_preset(write_preset(body))
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)
        self.assertIn(needle, str(caught.exception))
        self.assertEqual(len(str(caught.exception).splitlines()), 1,
                         "a preset fault must be ONE line")

    def test_absent_file(self):
        with self.assertRaises(lane.LaneError) as caught:
            lane.load_preset("/nonexistent/preset.toml")
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)

    def test_invalid_toml(self):
        self.assert_usage('[lane]\nname = unquoted\n', "not valid TOML")

    def test_no_lane_table(self):
        self.assert_usage('[delivery]\nsubmit = true\n', "no [lane] table")

    def test_missing_argv(self):
        self.assert_usage('[lane]\nname = "w"\n', "non-empty argv")

    def test_empty_argv(self):
        self.assert_usage('[lane]\nname = "w"\nargv = []\n', "non-empty argv")

    def test_argv_of_non_strings(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat", 7]\n',
                          "array of strings")

    def test_missing_name(self):
        self.assert_usage('[lane]\nargv = ["cat"]\n', "needs a name")

    def test_unaddressable_name(self):
        self.assert_usage('[lane]\nname = "not a name"\nargv = ["cat"]\n',
                          "not addressable")

    def test_unknown_lane_key_is_a_typo_not_a_shrug(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\nreadymatch = "x"\n',
                          "unknown key(s)")

    def test_unknown_delivery_key(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\n'
                          '[delivery]\nsubmitt = true\n', "unknown key(s)")

    def test_unknown_table(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\n[extra]\nx = 1\n',
                          "unknown top-level table")

    def test_bad_direction(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\ndirection = "sideways"\n',
                          "direction")

    def test_bad_ready_timeout(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\nready_timeout_ms = 0\n',
                          "positive integer")

    def test_submit_and_raw_are_exclusive(self):
        self.assert_usage('[lane]\nname = "w"\nargv = ["cat"]\n'
                          '[delivery]\nsubmit = true\nraw = true\n',
                          "mutually exclusive")


class ReservedKindTest(unittest.TestCase):
    def test_unsupervised_is_exit_4_not_a_syntax_error(self):
        body = '[lane]\nname = "w"\nkind = "unsupervised"\nargv = ["cat"]\n'
        with self.assertRaises(lane.LaneError) as caught:
            lane.load_preset(write_preset(body))
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_IMPLEMENTED)
        self.assertIn("systemd-run", str(caught.exception),
                      "the refusal must say WHY it is permanent (RULING-kitten §5)")

    def test_unknown_kind_is_exit_4(self):
        body = '[lane]\nname = "w"\nkind = "telepathic"\nargv = ["cat"]\n'
        with self.assertRaises(lane.LaneError) as caught:
            lane.load_preset(write_preset(body))
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_IMPLEMENTED)

    def test_a_malformed_preset_of_a_reserved_kind_reports_the_syntax_first(self):
        """A caller cannot act on `not implemented` until the file parses."""
        body = '[lane]\nkind = "unsupervised"\nargv = ["cat"]\n'
        with self.assertRaises(lane.LaneError) as caught:
            lane.load_preset(write_preset(body))
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)


class LaneLookupTest(unittest.TestCase):
    """`hk_lane` is the join, not the label: a label is a human surface."""

    PANES = [
        {"pane_id": "w1:p1", "label": "shell", "tokens": {}},
        {"pane_id": "w1:p2", "label": "renamed-by-a-human",
         "tokens": {"hk_role": "lane", "hk_lane": "w"}},
        {"pane_id": "w1:p3", "label": "w", "tokens": {"hk_role": "herdr"}},
    ]

    def test_found_by_token_not_by_label(self):
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=self.PANES):
            self.assertEqual(lane.find_pane("w"), "w1:p2")

    def test_absent_lane_is_none(self):
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=self.PANES):
            self.assertIsNone(lane.find_pane("other"))

    def test_panes_without_tokens_do_not_crash_the_scan(self):
        panes = [{"pane_id": "w1:p1"}, {"pane_id": "w1:p2", "tokens": None}]
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=panes):
            self.assertIsNone(lane.find_pane("w"))


class ZeroBytesTest(unittest.TestCase):
    """Exit 3 means NO TARGET REACHED AND NOTHING SENT — the safe-fallback
    signal a supervisor branches on. Asserted by counting the delivery calls
    that did not happen, and by leaving stdin unread."""

    def test_deliver_to_an_absent_lane_sends_nothing_and_reads_no_stdin(self):
        preset = lane.load_preset(write_preset(GOOD))
        stdin = io.StringIO("payload that must not be consumed\n")
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=[]), \
             unittest.mock.patch.object(herdrc, "pane_send_input") as send_input, \
             unittest.mock.patch.object(herdrc, "pane_send_text") as send_text, \
             unittest.mock.patch.object(herdrc, "agent_prompt") as prompt:
            with self.assertRaises(lane.LaneError) as caught:
                lane.deliver(preset, stream=stdin)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_NOT_HERDR_WINDOW)
        send_input.assert_not_called()
        send_text.assert_not_called()
        prompt.assert_not_called()
        self.assertEqual(stdin.tell(), 0, "the refusal consumed stdin")

    def test_start_refuses_a_second_lane_of_the_same_name_before_splitting(self):
        preset = lane.load_preset(write_preset(GOOD))
        panes = [{"pane_id": "w1:p2", "tokens": {"hk_lane": "w"}}]
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=panes), \
             unittest.mock.patch.object(herdrc, "pane_split") as split:
            with self.assertRaises(lane.LaneError) as caught:
                lane.start(preset)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_USAGE)
        split.assert_not_called()

    def test_stop_and_status_on_an_absent_lane_are_exit_3(self):
        preset = lane.load_preset(write_preset(GOOD))
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=[]), \
             unittest.mock.patch.object(herdrc, "pane_close") as close:
            for verb in (lane.stop, lane.status):
                with self.assertRaises(lane.LaneError) as caught:
                    verb(preset)
                self.assertEqual(caught.exception.exit_code,
                                 verbs.EXIT_NOT_HERDR_WINDOW)
        close.assert_not_called()


class PaneSelectionTest(unittest.TestCase):
    """#36's other half: hk chooses the pane, and the caller never learns how.

    The live proof is the smoke; these assert the SHAPE of the launch — the
    worker argv rides the HK_EXEC trampoline as data (never a shell string hk
    assembles), the pane is stamped with the token that makes the lane findable
    again, and a host with no workspace gets one instead of an error.
    """

    SPLIT = {"pane_id": "w1:p9", "workspace_id": "w1", "terminal_id": "term_x"}

    def launch(self, body, ws="w1", created=None):
        preset = lane.load_preset(write_preset(body))
        stdout = io.StringIO()
        with unittest.mock.patch.object(verbs, "_resolve_ws", return_value=ws), \
             unittest.mock.patch.object(herdrc, "pane_list",
                                        return_value=[{"pane_id": "w1:p1"}]), \
             unittest.mock.patch.object(herdrc, "workspace_create",
                                        return_value=created) as create, \
             unittest.mock.patch.object(herdrc, "pane_split",
                                        return_value=dict(self.SPLIT)) as split, \
             unittest.mock.patch.object(herdrc, "report_metadata") as metadata, \
             unittest.mock.patch.object(herdrc, "pane_rename") as rename, \
             unittest.mock.patch("sys.stdout", stdout):
            rc = lane.start(preset)
        return rc, stdout.getvalue().strip(), split, create, metadata, rename

    def test_the_worker_argv_rides_the_trampoline_as_data(self):
        body = '[lane]\nname = "w"\nargv = ["sh", "-c", "make -j 8 && echo up"]\n'
        rc, pane, split, *_ = self.launch(body)
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(pane, "w1:p9", "start must print the pane it launched")
        env = split.call_args.kwargs["env"]
        self.assertEqual(list(env), ["HK_EXEC"],
                         "the worker travels as one env var, not as an argv hk types")
        self.assertEqual(env["HK_EXEC"],
                         verbs.encode_trampoline(["sh", "-c", "make -j 8 && echo up"]))
        # Decoded, every element is shell-quoted: a worker argument with spaces
        # in it stays ONE argument instead of becoming three.
        self.assertEqual(base64.b64decode(env["HK_EXEC"]).decode(),
                         "sh -c 'make -j 8 && echo up'")

    def test_the_lane_splits_off_the_anchor_and_keeps_its_declared_cwd(self):
        body = ('[lane]\nname = "w"\nargv = ["cat"]\n'
                'cwd = "/srv/work"\ndirection = "left"\n')
        *_, split, _c, _m, _r = self.launch(body)
        self.assertEqual(split.call_args.kwargs["pane_id"], "w1:p1")
        self.assertEqual(split.call_args.kwargs["direction"], "left")
        self.assertEqual(split.call_args.kwargs["cwd"], "/srv/work")

    def test_the_pane_is_stamped_with_the_token_that_finds_it_again(self):
        _, _, _, _, metadata, rename = self.launch('[lane]\nname = "w"\nargv = ["cat"]\n')
        self.assertEqual(metadata.call_args.kwargs["tokens"],
                         {"hk_role": "lane", "hk_lane": "w"})
        # spec D16: hk's own tokens go under source user:hk, ttl_ms and seq omitted
        self.assertEqual(metadata.call_args.kwargs.get("source", "user:hk"), "user:hk")
        self.assertEqual(rename.call_args.args, ("w1:p9", "w"))

    def test_a_host_with_no_workspace_gets_one_instead_of_an_error(self):
        created = {"workspace_id": "w7", "root_pane": {"pane_id": "w7:p1"}}
        rc, pane, split, create, *_ = self.launch(
            '[lane]\nname = "w"\nargv = ["cat"]\n', ws=None, created=created)
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(pane, "w1:p9")
        create.assert_called_once()
        self.assertEqual(split.call_args.kwargs["pane_id"], "w7:p1",
                         "the new workspace's root pane is the anchor")


class DeliveryRoutingTest(unittest.TestCase):
    """Which herdr method a delivery rides is the preset's decision, not hk's."""

    PANES = [{"pane_id": "w1:p2", "tokens": {"hk_lane": "w"}}]

    def route(self, body, payload="hi\n"):
        preset = lane.load_preset(write_preset(body))
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=self.PANES), \
             unittest.mock.patch.object(herdrc, "pane_send_input") as send_input, \
             unittest.mock.patch.object(herdrc, "pane_send_text") as send_text, \
             unittest.mock.patch.object(herdrc, "agent_prompt") as prompt:
            rc = lane.deliver(preset, stream=io.StringIO(payload))
        return rc, send_input, send_text, prompt

    def test_default_populates_and_never_submits(self):
        rc, send_input, send_text, prompt = self.route(GOOD)
        self.assertEqual(rc, verbs.EXIT_OK)
        send_input.assert_called_once_with("w1:p2", "hi\n", host=None)
        prompt.assert_not_called()
        send_text.assert_not_called()

    def test_submit_routes_the_agent_prompt(self):
        body = GOOD + "[delivery]\nsubmit = true\n"
        rc, send_input, send_text, prompt = self.route(body)
        self.assertEqual(rc, verbs.EXIT_OK)
        prompt.assert_called_once_with("w1:p2", "hi\n", host=None)
        send_input.assert_not_called()

    def test_raw_is_byte_transparent(self):
        body = GOOD + "[delivery]\nraw = true\n"
        payload = "\x1b[201~ends the bracket\n"
        rc, send_input, send_text, prompt = self.route(body, payload)
        self.assertEqual(rc, verbs.EXIT_OK)
        send_text.assert_called_once_with("w1:p2", payload, host=None)

    def test_framed_delivery_scrubs_the_paste_terminator(self):
        rc, send_input, _, _ = self.route(GOOD, "a\x1b[201~b\n")
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(send_input.call_args.args[1], "ab\n")

    def test_the_payload_arrives_byte_for_byte(self):
        """#37's claim at the unit boundary: what stdin held is what is sent."""
        payload = (FIXTURES / "payload.txt").read_text()
        rc, send_input, _, _ = self.route(GOOD, payload)
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(send_input.call_args.args[1], payload)

    def test_a_nul_payload_is_one_typed_line_not_a_traceback(self):
        preset = lane.load_preset(write_preset(GOOD))
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=self.PANES), \
             unittest.mock.patch.object(herdrc, "pane_send_input") as send_input:
            with self.assertRaises(lane.LaneError) as caught:
                lane.deliver(preset, stream=io.StringIO("a\x00b"))
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_HERDR_ERROR)
        self.assertEqual(len(str(caught.exception).splitlines()), 1)
        send_input.assert_not_called()


class ExitCodeSurfaceTest(unittest.TestCase):
    """`cmd_lane` turns every LaneError into its §5 number and one line."""

    def run_verb(self, verb, preset_path, stderr):
        with unittest.mock.patch("sys.stderr", stderr):
            return lane.cmd_lane(args(verb, preset_path))

    def test_the_shipped_fixture_produces_each_typed_exit(self):
        expected = {
            "malformed.toml": verbs.EXIT_USAGE,
            "unsupervised.toml": verbs.EXIT_NOT_IMPLEMENTED,
        }
        for name, code in expected.items():
            stderr = io.StringIO()
            rc = self.run_verb("start", str(FIXTURES / name), stderr)
            self.assertEqual(rc, code, f"{name}: {stderr.getvalue()}")
            self.assertEqual(len(stderr.getvalue().strip().splitlines()), 1, name)
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_absent_lane_is_exit_3(self):
        stderr = io.StringIO()
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=[]):
            rc = self.run_verb("status", str(FIXTURES / "absent.toml"), stderr)
        self.assertEqual(rc, verbs.EXIT_NOT_HERDR_WINDOW)

    def test_no_herdr_session_is_exit_1_code_verbatim_and_zero_bytes_read(self):
        """The card's "no session" outcome, under §5's numbering: a server/tool
        error is 1 with herdr's code propagated unchanged — the same answer
        `hk send` gives in this state — and stdin is still unread."""
        stderr = io.StringIO()
        stdin = io.StringIO("payload that must not be consumed\n")
        dead = herdrc.HerdrError("no herdr server is running",
                                 code="server_not_running")
        with unittest.mock.patch.object(herdrc, "pane_list", side_effect=dead), \
             unittest.mock.patch.object(herdrc, "pane_send_input") as send_input, \
             unittest.mock.patch("sys.stdin", stdin):
            rc = self.run_verb("deliver", str(FIXTURES / "absent.toml"), stderr)
        self.assertEqual(rc, verbs.EXIT_HERDR_ERROR)
        self.assertIn("server_not_running", stderr.getvalue())
        self.assertEqual(len(stderr.getvalue().strip().splitlines()), 1)
        self.assertNotIn("Traceback", stderr.getvalue())
        send_input.assert_not_called()
        self.assertEqual(stdin.tell(), 0, "a dead session consumed stdin")

    def test_a_herdr_refusal_keeps_its_code_and_exits_1(self):
        stderr = io.StringIO()
        panes = [{"pane_id": "w1:p2", "tokens": {"hk_lane": "hk1-worker"}}]
        blocked = herdrc.HerdrError("agent is blocked", code="agent_blocked")
        with unittest.mock.patch.object(herdrc, "pane_list", return_value=panes), \
             unittest.mock.patch.object(herdrc, "agent_prompt", side_effect=blocked), \
             unittest.mock.patch("sys.stdin", io.StringIO("hi\n")):
            rc = self.run_verb("deliver", str(FIXTURES / "blocked.toml"), stderr)
        self.assertEqual(rc, verbs.EXIT_HERDR_ERROR)
        self.assertIn("agent_blocked", stderr.getvalue())

    def test_every_shipped_fixture_is_covered_by_the_smoke(self):
        """The fixture directory and the smoke must not drift apart."""
        smoke = (REPO / "tests" / "smoke" / "supervised-lane.sh").read_text()
        for preset in sorted(FIXTURES.glob("*.toml")):
            self.assertIn(preset.name, smoke,
                          f"{preset.name} is shipped but no smoke step drives it")

    def test_the_five_codes_are_distinct_and_are_the_ruling_s(self):
        self.assertEqual(
            [verbs.EXIT_OK, verbs.EXIT_HERDR_ERROR, verbs.EXIT_USAGE,
             verbs.EXIT_NOT_HERDR_WINDOW, verbs.EXIT_NOT_IMPLEMENTED],
            [0, 1, 2, 3, 4])


class ReadyWaitTest(unittest.TestCase):
    """A lane that never comes up must not be reported as delivered."""

    def test_a_preset_without_ready_match_never_sleeps(self):
        preset = lane.load_preset(write_preset(GOOD))
        with unittest.mock.patch.object(herdrc, "pane_read") as read, \
             unittest.mock.patch("time.sleep") as sleep:
            lane._await_ready(preset, "w1:p2", None)
        read.assert_not_called()
        sleep.assert_not_called()

    def test_the_marker_is_looked_for_on_the_visible_screen(self):
        body = '[lane]\nname = "w"\nargv = ["cat"]\nready_match = "UP"\n'
        preset = lane.load_preset(write_preset(body))
        with unittest.mock.patch.object(herdrc, "pane_read",
                                        return_value="banner\nUP\n") as read, \
             unittest.mock.patch("time.sleep") as sleep:
            lane._await_ready(preset, "w1:p2", None)
        self.assertEqual(read.call_args.kwargs["source"], "visible")
        sleep.assert_not_called()

    def test_a_timeout_closes_the_pane_and_is_exit_1_named_timeout(self):
        body = ('[lane]\nname = "w"\nargv = ["cat"]\n'
                'ready_match = "NEVER"\nready_timeout_ms = 1\n')
        preset = lane.load_preset(write_preset(body))
        with unittest.mock.patch.object(herdrc, "pane_read", return_value=""), \
             unittest.mock.patch.object(herdrc, "pane_close") as close, \
             unittest.mock.patch("time.sleep"):
            with self.assertRaises(lane.LaneError) as caught:
                lane._await_ready(preset, "w1:p2", None)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_HERDR_ERROR)
        self.assertTrue(str(caught.exception).startswith("timeout:"),
                        "the §5 code must lead the line: "
                        f"{caught.exception}")
        close.assert_called_once_with("w1:p2", host=None)


class ShippedExampleTest(unittest.TestCase):
    def test_conf_supervised_lane_toml_is_a_valid_preset(self):
        preset = lane.load_preset(str(REPO / "conf" / "supervised-lane.toml"))
        self.assertEqual(preset["kind"], "supervised")
        self.assertTrue(preset["argv"])

    def test_the_worker_fixture_declares_its_readiness_marker(self):
        preset = lane.load_preset(str(FIXTURES / "worker.toml"))
        self.assertEqual(preset["ready_match"], "LANE-READY")
        self.assertIn("LANE-READY", preset["argv"][-1])


if __name__ == "__main__":
    unittest.main()
