"""The send path, edge-first (round2-04; BUG-5, BUG-8, BUG-9; T1/T4/T19/T20).

Every test here is a bug that used to produce either a raw Python traceback or
silently wrong bytes in somebody's terminal. The numbers in LimitsTest were
binary-searched live against herdr 0.8.2 (protocol 21) — they are measurements,
not guesses, and this file is where they are re-checkable.
"""

import io
import json
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

from hk import herdrc, verbs


class FakeServer:
    """Captures what hk would put on the wire, without a herdr running."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, method, params, timeout=30.0):
        self.calls.append((method, params))
        if self.error:
            raise self.error
        return {"type": "ok"}

    @property
    def text(self):
        """Everything delivered, reassembled in order."""
        return "".join(p["text"] for _, p in self.calls if "text" in p)

    @property
    def methods(self):
        return [m for m, _ in self.calls]


class SocketDelivery(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        patches = [
            unittest.mock.patch.object(herdrc, "socket_call", self.server),
            unittest.mock.patch.object(herdrc, "socket_available", lambda: True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def send(self, text, **kw):
        # round2-05: the resolved-target grammar — `target` + `--current`.
        fields = {"target": "w1:p1", "current": False,
                  "host": None, "submit": False, "raw": False}
        fields.update(kw)
        args = unittest.mock.Mock(**fields)
        with unittest.mock.patch("sys.stdin", io.StringIO(text)):
            return verbs.cmd_send(args)


class LimitsTest(unittest.TestCase):
    """The two ceilings, and which one applies where."""

    def test_measured_constants_are_the_measured_values(self):
        # Linux MAX_ARG_STRLEN: 131071 bytes go through as argv, 131072 raises
        # OSError(E2BIG). Measured by binary search against the real herdr CLI.
        self.assertEqual(herdrc.ARGV_LIMIT, 131072)
        # herdr resets the connection above a 1 MiB request line. Measured:
        # 1048492 payload bytes accepted, 1048493 -> ConnectionResetError.
        self.assertEqual(herdrc.SOCKET_REQUEST_LIMIT, 1048576)

    def test_a_one_mib_payload_does_not_fit_in_one_request(self):
        """The correction that forced chunking to exist.

        A literal 1 MiB payload plus the JSON envelope is larger than the
        server's 1 MiB request limit, so 'send 1 MiB in one call' is not a
        thing that can work — the connection is reset, not an error returned.
        """
        payload = "A" * (1024 * 1024)
        request = json.dumps({"id": "hk:pane.send_input", "method": "pane.send_input",
                              "params": {"pane_id": "w1:p1", "text": payload}})
        self.assertGreater(len(request.encode()) + 1, herdrc.SOCKET_REQUEST_LIMIT)

    def test_chunks_all_fit_under_the_limit(self):
        for payload in ("A" * (1024 * 1024),            # BUG-5's headline case
                        "\x01" * 300_000,               # control chars: 6x JSON expansion
                        "é" * 400_000):                 # multibyte
            parts = herdrc._chunks("w1:p1", "pane.send_input", payload)
            self.assertEqual("".join(parts), payload, "chunking must be lossless")
            for part in parts:
                request = json.dumps({"id": "hk:pane.send_input",
                                      "method": "pane.send_input",
                                      "params": {"pane_id": "w1:p1", "text": part}})
                self.assertLessEqual(len(request.encode()) + 1,
                                     herdrc.SOCKET_REQUEST_LIMIT)

    def test_short_payloads_are_not_split(self):
        self.assertEqual(herdrc._chunks("w1:p1", "pane.send_input", "hello"), ["hello"])


class LargePayloadTest(SocketDelivery):
    """BUG-5: an ordinary large paste used to be an uncaught OSError."""

    def test_one_mebibyte_is_delivered_whole(self):
        payload = "A" * (1024 * 1024)
        self.assertEqual(self.send(payload), verbs.EXIT_OK)
        self.assertEqual(self.server.text, payload)
        self.assertGreater(len(self.server.calls), 1, "1 MiB must be chunked")
        self.assertEqual(set(self.server.methods), {"pane.send_input"})

    def test_just_over_the_argv_ceiling_is_fine_on_the_socket(self):
        payload = "x" * (herdrc.ARGV_LIMIT + 1)
        self.assertEqual(self.send(payload), verbs.EXIT_OK)
        self.assertEqual(self.server.text, payload)

    def test_argv_tier_refuses_with_a_named_error_not_a_traceback(self):
        """--host has no socket, so the ceiling is real there and must be said."""
        with unittest.mock.patch.object(herdrc, "socket_available", lambda: False):
            with self.assertRaises(herdrc.HerdrError) as caught:
                herdrc.pane_send_input("w1:p1", "x" * herdrc.ARGV_LIMIT, host="buildbox")
        self.assertEqual(caught.exception.code, "payload_too_large")
        self.assertIn(str(herdrc.ARGV_LIMIT), str(caught.exception))
        self.assertIn("buildbox", str(caught.exception))


class BadInputTest(SocketDelivery):
    """The three recon repros, each now a typed one-liner instead of a trace."""

    def test_nul_byte_is_a_typed_error(self):
        code = self.send("before\x00after")
        self.assertEqual(code, verbs.EXIT_HERDR_ERROR)
        self.assertEqual(self.server.calls, [], "not one byte may be delivered")

    def test_non_utf8_stdin_is_a_typed_error(self):
        class Undecodable:
            def read(self):
                raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

        with unittest.mock.patch("sys.stdin", Undecodable()):
            args = unittest.mock.Mock(target="w1:p1", current=False,
                                      host=None, submit=False, raw=False)
            self.assertEqual(verbs.cmd_send(args), verbs.EXIT_HERDR_ERROR)
        self.assertEqual(self.server.calls, [])

    def test_read_payload_raises_payload_error_not_valueerror_soup(self):
        with self.assertRaises(verbs.PayloadError):
            verbs.read_payload(io.StringIO("a\x00b"))

    def test_empty_stdin_is_not_an_error(self):
        self.assertEqual(self.send(""), verbs.EXIT_OK)


class HostilePayloadTest(SocketDelivery):
    """BUG-9: 'never auto-submits' has to survive a crafted payload."""

    HOSTILE = "SAFE\x1b[201~rm -rf ~\r"

    def test_terminator_is_stripped_on_the_framed_path(self):
        self.assertEqual(self.send(self.HOSTILE), verbs.EXIT_OK)
        delivered = self.server.text
        self.assertNotIn("\x1b[201~", delivered,
                         "a payload that closes the paste bracket escapes the frame")
        self.assertIn("SAFE", delivered)
        # The rest of the payload survives as TEXT — we scrub the escape, we do
        # not silently truncate the user's data.
        self.assertIn("rm -rf ~", delivered)

    def test_nothing_after_the_terminator_can_be_typed_as_input(self):
        """The actual guarantee: no delivered chunk can end a paste bracket.

        With the terminator gone, every byte after it stays inside herdr's
        frame, so the trailing \\r is pasted text and not a submission.
        """
        self.send(self.HOSTILE)
        for _, params in self.server.calls:
            self.assertNotIn("\x1b[201~", params["text"])

    def test_sanitise_reports_how_many_it_removed(self):
        clean, removed = herdrc.sanitise_framed("a\x1b[201~b\x1b[201~c")
        self.assertEqual(clean, "abc")
        self.assertEqual(removed, 2)

    def test_clean_payloads_are_untouched(self):
        clean, removed = herdrc.sanitise_framed("ordinary text\nwith a newline")
        self.assertEqual(removed, 0)
        self.assertEqual(clean, "ordinary text\nwith a newline")

    def test_send_never_appends_a_submission(self):
        self.send("some text")
        self.assertEqual(self.server.text, "some text",
                         "no \\r, no \\n, nothing appended — populate only")


class RawTest(SocketDelivery):
    """T1/T19: --raw is byte-transparent, and says so."""

    def test_raw_round_trips_bytes_exactly(self):
        payload = "SAFE\x1b[201~and\ttabs\nand newlines\x1b[200~"
        self.assertEqual(self.send(payload, raw=True), verbs.EXIT_OK)
        self.assertEqual(self.server.text, payload, "--raw must not alter a byte")

    def test_raw_uses_send_text_not_send_input(self):
        self.send("literal", raw=True)
        self.assertEqual(self.server.methods, ["pane.send_text"])

    def test_framed_uses_send_input(self):
        self.send("framed")
        self.assertEqual(self.server.methods, ["pane.send_input"])

    def test_raw_and_submit_are_refused_as_usage(self):
        self.assertEqual(self.send("x", raw=True, submit=True), verbs.EXIT_USAGE)
        self.assertEqual(self.server.calls, [])

    def test_help_text_warns_that_raw_is_sharp(self):
        help_src = (REPO / "bin" / "hk").read_text()
        self.assertIn("--raw", help_src)
        self.assertIn("byte-transparent", help_src.lower())


class ExitCodeTest(SocketDelivery):
    """The contract tally relies on: 0 / 1 / 2, and verbatim error codes."""

    def test_herdr_error_code_propagates_verbatim(self):
        self.server.error = herdrc.HerdrError("agent is blocked", code="agent_blocked")
        args = unittest.mock.Mock(target="w1:p1", current=False,
                                  host=None, submit=True, raw=False)
        with unittest.mock.patch("sys.stdin", io.StringIO("hi")):
            self.assertEqual(verbs.cmd_send(args), verbs.EXIT_HERDR_ERROR)

    def test_submit_routes_to_agent_prompt(self):
        # round2-05: an agent NAME here would now cost an `agent list`
        # round trip (T14); the name-resolution path has its own cover in
        # test_targeting.py. What this test pins is the --submit routing.
        args = unittest.mock.Mock(target="w1:p1", current=False,
                                  host=None, submit=True, raw=False)
        with unittest.mock.patch("sys.stdin", io.StringIO("do the thing")):
            self.assertEqual(verbs.cmd_send(args), verbs.EXIT_OK)
        self.assertEqual(self.server.methods, ["agent.prompt"])
        self.assertEqual(self.server.calls[0][1]["text"], "do the thing")


class SocketErrorTest(unittest.TestCase):
    """No socket error may reach the user as a traceback."""

    def test_missing_socket_is_a_herdr_error(self):
        with unittest.mock.patch.object(herdrc, "socket_path",
                                        lambda: "/nonexistent/herdr.sock"):
            with self.assertRaises(herdrc.HerdrError) as caught:
                herdrc.socket_call("pane.send_input", {"pane_id": "w1:p1", "text": "x"})
        self.assertEqual(caught.exception.code, "socket_unavailable")

    def test_oversized_request_is_refused_before_the_connection(self):
        with self.assertRaises(herdrc.HerdrError) as caught:
            herdrc.socket_call("pane.send_input",
                               {"pane_id": "w1:p1",
                                "text": "A" * (herdrc.SOCKET_REQUEST_LIMIT + 10)})
        self.assertEqual(caught.exception.code, "request_too_large")


class SharedImplementationTest(unittest.TestCase):
    """One delivery path, not two (the voice/send dedupe)."""

    def test_voice_and_send_share_the_delivery_function(self):
        voice_src = (REPO / "hk" / "voice.py").read_text()
        self.assertIn("herdrc.pane_send_input", voice_src)
        self.assertNotIn("200~", voice_src, "voice must not carry its own frame")

    def test_only_herdrc_knows_the_frame_bytes(self):
        owners = sorted(p.name for p in (REPO / "hk").glob("*.py")
                        if "200~" in p.read_text())
        self.assertEqual(owners, ["herdrc.py"])

    def test_notifyd_reuses_the_shared_socket_path(self):
        from hk import notifyd
        self.assertIs(notifyd.socket_path, herdrc.socket_path)


if __name__ == "__main__":
    unittest.main()
