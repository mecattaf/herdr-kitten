"""Unit tests for S2 verb logic — the pure paths: no server, no kitty.

Everything here is a routing or shaping decision hk makes BEFORE it talks to
anything, which is exactly the part a live smoke gate cannot pin down.
"""

import base64
import os
import re
import subprocess
import unittest
import unittest.mock

from hk import herdrc, verbs


class TrampolineTest(unittest.TestCase):
    """spec D5: HK_EXEC is base64 of a shell-quoted argv the hook `eval set --`s."""

    def test_roundtrip_simple(self):
        payload = base64.b64decode(verbs.encode_trampoline(["true"])).decode()
        self.assertEqual(payload, "true")

    def test_quoting(self):
        payload = base64.b64decode(
            verbs.encode_trampoline(["echo", "two words", "$HOME"])).decode()
        self.assertEqual(payload, "echo 'two words' '$HOME'")

    def test_hostile_argv_survives_quoting(self):
        # a payload that broke out of the quoting would run the wrong command
        argv = ["sh", "-c", "echo 'a'; rm -rf /", "arg\nwith\nnewlines"]
        payload = base64.b64decode(verbs.encode_trampoline(argv)).decode()
        import shlex
        self.assertEqual(shlex.split(payload), argv)


class FramingTest(unittest.TestCase):
    """spec 4.1 / F.14: bracketing is manual and nothing is auto-submitted."""

    def test_bracketed(self):
        framed = verbs._frame("two\nlines")
        self.assertTrue(framed.startswith("\x1b[200~"))
        self.assertTrue(framed.endswith("\x1b[201~"))

    def test_no_trailing_submission(self):
        # nothing whatsoever follows the close bracket — no \r, no \n
        self.assertEqual(verbs._frame("hi").rsplit("\x1b[201~", 1)[1], "")

    def test_payload_is_byte_exact(self):
        payload = "line1\nline2\twith tab"
        framed = verbs._frame(payload)
        self.assertEqual(framed[len("\x1b[200~"):-len("\x1b[201~")], payload)


class PluginOwnedTest(unittest.TestCase):
    """spec 7.5 / census-map P36: the title bridge never fights a plugin label."""

    def test_reviewr_owned(self):
        self.assertTrue(verbs.plugin_owned("reviewr"))
        self.assertTrue(verbs.plugin_owned("plugin:foo"))

    def test_user_labels_free(self):
        self.assertFalse(verbs.plugin_owned("alpha"))
        self.assertFalse(verbs.plugin_owned(None))
        self.assertFalse(verbs.plugin_owned(""))


class ResumeRowsTest(unittest.TestCase):
    """spec 10.1 (G16). Shape mirrors a real `pane list` result element."""

    PANES = [
        {"pane_id": "w1:p1", "terminal_id": "term_a", "agent_status": "idle",
         "label": "alpha", "tokens": {"hk_role": "herdr"}},
        {"pane_id": "w1:p2", "terminal_id": "term_b", "agent_status": "working",
         "terminal_title_stripped": "nvim", "tokens": {"hk_role": "fork"}},
        {"pane_id": "w1:p3", "terminal_id": "term_c", "agent_status": "blocked",
         "terminal_title_stripped": "bash", "tokens": {}},
    ]

    def test_fork_filtered(self):
        self.assertNotIn("term_b", [r[0] for r in verbs.resume_rows(self.PANES)])

    def test_row_shape(self):
        rows = verbs.resume_rows(self.PANES)
        self.assertEqual(rows[0], ("term_a", "alpha", "idle"))
        # label falls back to the terminal title, never to empty when one exists
        self.assertEqual(rows[1], ("term_c", "bash", "blocked"))

    def test_untokened_pane_is_resumable(self):
        # a pane hk never touched is still a session to come back to
        self.assertEqual(len(verbs.resume_rows([{"pane_id": "w1:p9",
                                                 "terminal_id": "t9"}])), 1)


class SlugTest(unittest.TestCase):
    """spec D23 / 7.6: free text is rejected LOCALLY, before the socket call."""

    def test_slug_shape(self):
        self.assertTrue(re.match(verbs.AGENT_SLUG_RE, "my-agent_2"))
        self.assertTrue(re.match(verbs.AGENT_SLUG_RE, "a"))
        self.assertFalse(re.match(verbs.AGENT_SLUG_RE, "My Agent"))
        self.assertFalse(re.match(verbs.AGENT_SLUG_RE, "2agent"))
        self.assertFalse(re.match(verbs.AGENT_SLUG_RE, "-agent"))
        self.assertFalse(re.match(verbs.AGENT_SLUG_RE, "a" * 33))
        self.assertTrue(re.match(verbs.AGENT_SLUG_RE, "a" * 32))


class HostRoutingTest(unittest.TestCase):
    """spec 4.3 / D13: `--host` moves the HERDR call onto ssh. Kitty stays local."""

    def test_local_argv_is_bare_herdr(self):
        self.assertEqual(herdrc._argv(["pane", "list"], None), ["herdr", "pane", "list"])

    def test_host_argv_rides_ssh(self):
        argv = herdrc._argv(["pane", "list"], "buildbox")
        self.assertEqual(argv[:2], ["ssh", "buildbox"])
        self.assertEqual(argv[2], "herdr pane list")

    def test_host_argv_quotes_the_payload(self):
        # a bracketed send-text payload must survive the remote shell intact
        argv = herdrc._argv(["pane", "send-text", "w1:p1", verbs._frame("a b; rm -rf /")],
                            "buildbox")
        import shlex
        self.assertEqual(shlex.split(argv[2]),
                         ["herdr", "pane", "send-text", "w1:p1", verbs._frame("a b; rm -rf /")])


class ReadCapTest(unittest.TestCase):
    """spec 6.1 / census-map P21: the cap is 1000 and the notice is hk's job."""

    def test_cap_constant_matches_the_census(self):
        self.assertEqual(verbs.READ_CAP, 1000)


class NiriAdapterTest(unittest.TestCase):
    """spec 9.7 / D15 / F.11: the compositor adapter activates only on its own
    environment signal. No NIRI_SOCKET means zero compositor calls — the repo
    must be installable on a host that has never heard of niri."""

    def setUp(self):
        self.calls = []
        self.real_run = subprocess.run
        subprocess.run = lambda *a, **k: self.calls.append(a) or self.real_run(
            ["true"], capture_output=True, text=True)

    def tearDown(self):
        subprocess.run = self.real_run

    def test_absent_socket_makes_no_compositor_call(self):
        env = dict(os.environ)
        env.pop("NIRI_SOCKET", None)
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            verbs._niri_adopt("hk-ws-w1")
        self.assertEqual(self.calls, [])

    def test_present_socket_reaches_for_niri(self):
        import contextlib, io
        with unittest.mock.patch.dict(os.environ, {"NIRI_SOCKET": "/tmp/fake.sock"}), \
                contextlib.redirect_stderr(io.StringIO()):
            verbs._niri_adopt("hk-ws-w1")
        self.assertTrue(self.calls, "NIRI_SOCKET set but niri was never consulted")
        self.assertEqual(self.calls[0][0][:2], ["niri", "msg"])

    def test_window_class_is_per_workspace(self):
        self.assertEqual(verbs.window_class("w1"), "hk-ws-w1")
        self.assertNotEqual(verbs.window_class("w1"), verbs.window_class("w2"))


if __name__ == "__main__":
    unittest.main()
