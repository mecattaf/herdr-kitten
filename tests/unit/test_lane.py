"""Supervised lanes from preset data — the pure paths (no server, no kitty).

Card HK-1; herdr-kitten #36/#37/#38 = tally.nix #670/#673/#678.

Three claims carry this module, and all three are asserted the strong way:

  * **a preset is data, and hk validates all of it before launching anything.**
    Every structural fault is one typed line and exit 2, and the assertions
    count the herdr calls that did NOT happen — the weak form (assert the exit
    code) passes even when a pane has already been split.
  * **the exits are RULING-kitten §5's**, so a supervisor can branch on them:
    0 delivered · 1 refused, the herdr code verbatim · 2 preset/CLI syntax ·
    3 no lane reachable and zero bytes sent · 4 not implemented.
  * **a start either produces an addressable lane or leaves nothing behind**
    (evaluator DEFECT 2), and **the read-back worker is byte-oriented, so no
    trailing byte can go unreported** (evaluator DEFECT 1). Both are driven
    through a small model of herdr's pane table (`FakeHerdr`) that reflects what
    a metadata write published and what a close removed, and the worker protocol
    is run for real over a pipe — the live-pane form of both is
    `tests/proofs/hk1-retry-cleanup.py` and `tests/proofs/hk1-readback-bytes.py`.
"""

import base64
import contextlib
import hashlib
import io
import os
import pathlib
import re
import select
import shlex
import subprocess
import tempfile
import time
import unittest
import unittest.mock

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "supervised-lane"
SMOKE = REPO / "tests" / "smoke" / "supervised-lane.sh"

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


class FakeHerdr:
    """A small model of herdr's pane table, so a PARTIAL start failure can be
    driven and its residue counted.

    `pane_list` reflects what `report_metadata` published and what `pane_close`
    removed — the property the DEFECT-2 repair stands on: a lane is addressable
    because its token is really there, not because a call returned Ok. Any call
    can be made to raise by name, once (a list) or always (an exception), and
    `publish_tokens=False` models a write herdr accepted and never published.
    Every call is logged, so "nothing was launched" stays a counted claim.
    """

    def __init__(self, workspace="w1", fail=None, publish_tokens=True):
        self.workspace = workspace
        self.panes = [{"pane_id": f"{workspace}:p1", "workspace_id": workspace,
                       "label": "shell", "tokens": {}}]
        self.calls = []
        self.fail = dict(fail or {})
        self.publish_tokens = publish_tokens
        self.screen = ""
        self._next = 2

    # ---- plumbing
    def _note(self, name, *pos, **kw):
        self.calls.append((name, pos, kw))
        fault = self.fail.get(name)
        if isinstance(fault, list):
            if fault:
                raise fault.pop(0)
        elif fault is not None:
            raise fault

    def names(self, name):
        return [call for call in self.calls if call[0] == name]

    def lane_panes(self):
        return [p for p in self.panes if (p.get("tokens") or {}).get("hk_role") == "lane"]

    def _pane(self, pane_id):
        for pane in self.panes:
            if pane["pane_id"] == pane_id:
                return pane
        return None

    # ---- the herdr surface hk.lane uses
    def pane_list(self, workspace=None, host=None):
        self._note("pane_list", workspace=workspace, host=host)
        return [dict(p, tokens=dict(p.get("tokens") or {})) for p in self.panes]

    def workspace_create(self, cwd=None, label=None, host=None):
        self._note("workspace_create", cwd=cwd, label=label, host=host)
        root = {"pane_id": "w7:p1", "workspace_id": "w7", "label": "shell", "tokens": {}}
        self.panes.append(root)
        return {"workspace_id": "w7", "root_pane": dict(root)}

    def pane_split(self, pane_id=None, direction=None, cwd=None, env=None,
                   focus=False, host=None):
        self._note("pane_split", pane_id=pane_id, direction=direction, cwd=cwd,
                   env=env, host=host)
        anchor = self._pane(pane_id) if pane_id else None
        ws = anchor["workspace_id"] if anchor else self.workspace
        new = {"pane_id": f"{ws}:p{self._next}",
               "workspace_id": ws, "label": None, "tokens": {}}
        self._next += 1
        self.panes.append(new)
        return dict(new)

    def report_metadata(self, pane_id, source="user:hk", tokens=None, title=None,
                        host=None):
        self._note("report_metadata", pane_id, source=source, tokens=tokens, host=host)
        if not self.publish_tokens:
            return
        pane = self._pane(pane_id)
        if pane is not None:
            pane.setdefault("tokens", {}).update(tokens or {})

    def pane_rename(self, pane_id, label, host=None):
        self._note("pane_rename", pane_id, label, host=host)
        pane = self._pane(pane_id)
        if pane is not None:
            pane["label"] = label

    def pane_close(self, pane_id, host=None):
        self._note("pane_close", pane_id, host=host)
        self.panes = [p for p in self.panes if p["pane_id"] != pane_id]

    def pane_read(self, pane_id, source="recent-unwrapped", lines=None,
                  fmt="ansi", host=None):
        self._note("pane_read", pane_id, source=source, host=host)
        return self.screen


@contextlib.contextmanager
def herdr_model(fake, workspace="w1"):
    """Route every herdr call hk.lane makes through the model."""
    with unittest.mock.patch.object(verbs, "_resolve_ws", return_value=workspace), \
         unittest.mock.patch.object(herdrc, "pane_list", fake.pane_list), \
         unittest.mock.patch.object(herdrc, "workspace_create", fake.workspace_create), \
         unittest.mock.patch.object(herdrc, "pane_split", fake.pane_split), \
         unittest.mock.patch.object(herdrc, "report_metadata", fake.report_metadata), \
         unittest.mock.patch.object(herdrc, "pane_rename", fake.pane_rename), \
         unittest.mock.patch.object(herdrc, "pane_close", fake.pane_close), \
         unittest.mock.patch.object(herdrc, "pane_read", fake.pane_read):
        yield fake


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

    Driven through `FakeHerdr`, whose pane table reflects what a metadata write
    published and what a close removed — so "the lane is addressable" is a
    property of the model's state, not of a mock having been called.
    """

    def launch(self, body, workspace="w1", fake=None):
        fake = fake if fake is not None else FakeHerdr()
        preset = lane.load_preset(write_preset(body))
        stdout = io.StringIO()
        with herdr_model(fake, workspace=workspace), \
             unittest.mock.patch("sys.stdout", stdout), \
             unittest.mock.patch("time.sleep"):
            rc = lane.start(preset)
            # resolved INSIDE the model: outside it there is no pane table left
            resolved = lane.find_pane(preset["name"])
        return rc, stdout.getvalue().strip(), fake, resolved

    def split_kwargs(self, fake):
        return fake.names("pane_split")[0][2]

    def test_the_worker_argv_rides_the_trampoline_as_data(self):
        body = '[lane]\nname = "w"\nargv = ["sh", "-c", "make -j 8 && echo up"]\n'
        rc, pane, fake, resolved = self.launch(body)
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(pane, "w1:p2", "start must print the pane it launched")
        self.assertEqual(resolved, "w1:p2")
        env = self.split_kwargs(fake)["env"]
        self.assertEqual(list(env), ["HK_EXEC"],
                         "the worker travels as one env var, not as an argv hk types")
        self.assertEqual(env["HK_EXEC"],
                         verbs.encode_trampoline(["sh", "-c", "make -j 8 && echo up"]))
        # Decoded, every element is shell-quoted: a worker argument with spaces
        # in it stays ONE argument instead of becoming three.
        self.assertEqual(base64.b64decode(env["HK_EXEC"]).decode(),
                         "sh -c 'make -j 8 && echo up'")
        self.assertEqual(shlex.split(base64.b64decode(env["HK_EXEC"]).decode()),
                         ["sh", "-c", "make -j 8 && echo up"])

    def test_the_shipped_worker_script_survives_the_trampoline_intact(self):
        """The fixture worker is a multi-line python script in one argv element;
        if the trampoline encoding mangled it, the read-back would prove nothing."""
        preset = lane.load_preset(str(FIXTURES / "worker.toml"))
        decoded = base64.b64decode(
            verbs.encode_trampoline(preset["argv"])).decode()
        self.assertEqual(shlex.split(decoded), preset["argv"])
        self.assertIn("READBACK-HEX", preset["argv"][-1])

    def test_the_lane_splits_off_the_anchor_and_keeps_its_declared_cwd(self):
        body = ('[lane]\nname = "w"\nargv = ["cat"]\n'
                'cwd = "/srv/work"\ndirection = "left"\n')
        _, _, fake, _ = self.launch(body)
        kwargs = self.split_kwargs(fake)
        self.assertEqual(kwargs["pane_id"], "w1:p1")
        self.assertEqual(kwargs["direction"], "left")
        self.assertEqual(kwargs["cwd"], "/srv/work")

    def test_the_pane_is_stamped_with_the_token_that_finds_it_again(self):
        _, _, fake, resolved = self.launch('[lane]\nname = "w"\nargv = ["cat"]\n')
        _name, pos, kwargs = fake.names("report_metadata")[0]
        self.assertEqual(pos[0], "w1:p2")
        self.assertEqual(kwargs["tokens"], {"hk_role": "lane", "hk_lane": "w"})
        # spec D16: hk's own tokens go under source user:hk, ttl_ms and seq omitted
        self.assertEqual(kwargs["source"], "user:hk")
        self.assertEqual(fake.names("pane_rename")[0][1], ("w1:p2", "w"))
        # and the join really landed: the lane is addressable by name afterwards
        self.assertEqual(resolved, "w1:p2")

    def test_a_host_with_no_workspace_gets_one_instead_of_an_error(self):
        rc, pane, fake, resolved = self.launch(
            '[lane]\nname = "w"\nargv = ["cat"]\n', workspace=None)
        self.assertEqual(rc, verbs.EXIT_OK)
        self.assertEqual(len(fake.names("workspace_create")), 1)
        self.assertEqual(self.split_kwargs(fake)["pane_id"], "w7:p1",
                         "the new workspace's root pane is the anchor")
        self.assertEqual(pane, "w7:p2")
        self.assertEqual(resolved, "w7:p2")


class PartialStartCleanupTest(unittest.TestCase):
    """DEFECT 2: a start that fails part-way leaves NOTHING behind.

    The pane is split before it can be stamped, named or waited on, so every
    step after the split sits inside one cleanup boundary. A half-started lane
    is worse than no lane: the worker is running, no verb can address it, and
    the next `hk lane start` — which finds no token — splits a SECOND worker.
    Each case asserts the residue (the model's pane table), the exit code, and
    that the fault is still reported as ONE typed line with herdr's code
    verbatim and the cleanup disclosed.
    """

    BODY = '[lane]\nname = "w"\nargv = ["cat"]\n'

    def run_start(self, fake, body=None):
        preset = lane.load_preset(write_preset(body or self.BODY))
        stderr, stdout = io.StringIO(), io.StringIO()
        with herdr_model(fake), unittest.mock.patch("sys.stderr", stderr), \
             unittest.mock.patch("sys.stdout", stdout), \
             unittest.mock.patch("time.sleep"):
            rc = lane.cmd_lane(args("start", preset["path"]))
            resolved = lane.find_pane(preset["name"])
        return rc, stderr.getvalue(), stdout.getvalue(), resolved

    def assert_cleaned_up(self, fake, rc, err, resolved, code=None):
        self.assertEqual(rc, verbs.EXIT_HERDR_ERROR)
        self.assertEqual(len(err.strip().splitlines()), 1,
                         f"a start fault must be ONE typed line: {err!r}")
        self.assertNotIn("Traceback", err)
        if code:
            self.assertIn(code, err, "herdr's code must reach the caller verbatim")
        self.assertIn("hk closed the half-started lane pane w1:p2", err,
                      "the cleanup must be disclosed, not silent")
        self.assertEqual([p["pane_id"] for p in fake.panes], ["w1:p1"],
                         f"residue left behind: {fake.panes}")
        self.assertEqual(fake.lane_panes(), [])
        self.assertEqual([c[1][0] for c in fake.names("pane_close")], ["w1:p2"])
        self.assertIsNone(resolved, "an unaddressable worker survived")

    def test_a_metadata_refusal_closes_the_pane_it_had_already_split(self):
        fake = FakeHerdr(fail={"report_metadata": herdrc.HerdrError(
            "metadata write refused", code="metadata_rejected")})
        rc, err, out, resolved = self.run_start(fake)
        self.assert_cleaned_up(fake, rc, err, resolved, code="metadata_rejected")
        self.assertEqual(out, "", "a failed start must not print a pane id")

    def test_a_retry_after_that_failure_launches_exactly_one_worker(self):
        """The other half of DEFECT 2: no duplicate on the second attempt."""
        fake = FakeHerdr(fail={"report_metadata": [
            herdrc.HerdrError("metadata write refused", code="metadata_rejected")]})
        _rc, _err, _out, first = self.run_start(fake)
        self.assertIsNone(first, "the failed start left an addressable lane behind")
        rc, err, out, resolved = self.run_start(fake)
        self.assertEqual(rc, verbs.EXIT_OK, err)
        self.assertEqual(out.strip(), "w1:p3")
        self.assertEqual(resolved, "w1:p3")
        self.assertEqual(len(fake.lane_panes()), 1,
                         f"the retry duplicated the worker: {fake.panes}")
        self.assertEqual([p["pane_id"] for p in fake.panes], ["w1:p1", "w1:p3"])
        self.assertEqual(len(fake.names("pane_split")), 2)
        self.assertEqual(len(fake.names("pane_close")), 1)

    def test_a_rename_failure_is_cleaned_up_the_same_way(self):
        fake = FakeHerdr(fail={"pane_rename": herdrc.HerdrError(
            "label refused", code="invalid_label")})
        rc, err, _out, resolved = self.run_start(fake)
        self.assert_cleaned_up(fake, rc, err, resolved, code="invalid_label")

    def test_a_token_herdr_accepted_but_never_published_is_cleaned_up(self):
        """No exception at all, and still the worst case: a running worker no
        verb can reach. `start` reads the join back and refuses to report 0."""
        fake = FakeHerdr(publish_tokens=False)
        rc, err, _out, resolved = self.run_start(fake)
        self.assert_cleaned_up(fake, rc, err, resolved)
        self.assertIn("does not answer to its hk_lane token", err)
        self.assertIn("resolves to None", err)

    def test_a_readiness_timeout_is_cleaned_up_by_the_same_boundary(self):
        fake = FakeHerdr()
        fake.screen = ""
        body = ('[lane]\nname = "w"\nargv = ["cat"]\n'
                'ready_match = "NEVER"\nready_timeout_ms = 1\n')
        rc, err, _out, resolved = self.run_start(fake, body)
        self.assert_cleaned_up(fake, rc, err, resolved)
        self.assertTrue(err.startswith("hk: timeout:"),
                        f"the §5 code must lead the line: {err!r}")

    def test_an_unexpected_fault_is_one_typed_line_and_still_cleans_up(self):
        fake = FakeHerdr(fail={"pane_rename": RuntimeError("boom")})
        rc, err, _out, resolved = self.run_start(fake)
        self.assert_cleaned_up(fake, rc, err, resolved)
        self.assertIn("RuntimeError: boom", err)

    def test_a_cleanup_that_cannot_close_says_so_instead_of_claiming_it_did(self):
        fake = FakeHerdr(fail={
            "report_metadata": herdrc.HerdrError("refused", code="metadata_rejected"),
            "pane_close": herdrc.HerdrError("pane already gone", code="no_pane")})
        rc, err, _out, _resolved = self.run_start(fake)
        self.assertEqual(rc, verbs.EXIT_HERDR_ERROR)
        self.assertIn("metadata_rejected", err)
        self.assertIn("could NOT close the half-started lane pane w1:p2", err)
        self.assertIn("may still be running", err)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertEqual([p["pane_id"] for p in fake.panes], ["w1:p1", "w1:p2"],
                         "the model must still show the pane the close failed on")


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
        """Driven through `start`, which owns the cleanup boundary: `_await_ready`
        reports the timeout and the pane is closed by the one place that owns
        residue, so no failure path can forget it."""
        body = ('[lane]\nname = "w"\nargv = ["cat"]\n'
                'ready_match = "NEVER"\nready_timeout_ms = 1\n')
        preset = lane.load_preset(write_preset(body))
        fake = FakeHerdr()
        with herdr_model(fake), unittest.mock.patch("time.sleep"), \
             unittest.mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(lane.LaneError) as caught:
                lane.start(preset)
        self.assertEqual(caught.exception.exit_code, verbs.EXIT_HERDR_ERROR)
        self.assertTrue(str(caught.exception).startswith("timeout:"),
                        "the §5 code must lead the line: "
                        f"{caught.exception}")
        self.assertEqual([c[1][0] for c in fake.names("pane_close")], ["w1:p2"])
        self.assertEqual([p["pane_id"] for p in fake.panes], ["w1:p1"])


PAYLOAD = (FIXTURES / "payload.txt").read_bytes()
WORKER_SCRIPT = lane.load_preset(str(FIXTURES / "worker.toml"))["argv"][-1]

# The shape the fixture worker had before DEFECT 1 was found: a line reader.
# Kept here only as the CONTROL that proves why the shipped worker is not one.
LINE_WORKER = (
    "stty -echo 2>/dev/null || true; printf 'LANE-READY\\n'; "
    "while IFS= read -r line; do printf 'READBACK<%s>\\n' \"$line\"; done")


class _LineReader:
    """Line reader over a RAW fd.

    `select` on a buffered reader lies: data readline() already pulled into
    Python's buffer leaves the fd empty, so a select-then-readline watchdog
    times out with the answer sitting in the buffer. One buffer, owned here.
    """

    def __init__(self, stream, timeout=20.0):
        self.fd = stream.fileno()
        self.timeout = timeout
        self.buf = b""

    def readline(self):
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.fd], [], [], left)[0]:
                raise AssertionError(
                    f"the worker printed nothing for {self.timeout}s "
                    f"(buffer so far: {self.buf!r})")
            chunk = os.read(self.fd, 65536)
            if not chunk:
                raise AssertionError(
                    f"the worker's stdout closed before it reported "
                    f"(buffer: {self.buf!r})")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode()


def run_worker(script: str, deliveries: list[bytes]):
    """Run the worker over a pipe, one delivery at a time, and return
    (bytes reconstructed from its reports, its per-chunk reports, the byte count
    it announced at EOF, its exit code, its stderr).

    Each chunk is written and then WAITED FOR. That wait is the assertion: the
    worker must report a chunk while stdin is still open, because a live lane
    never sends the EOF a line reader needs before it will give up an
    unterminated trailing fragment (DEFECT 1).
    """
    proc = subprocess.Popen(["python3", "-u", "-c", script],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    reader = _LineReader(proc.stdout)
    reports = []
    try:
        ready = reader.readline()
        if ready.strip() != "LANE-READY":
            raise AssertionError(f"the worker did not announce itself: {ready!r}")
        for chunk in deliveries:
            proc.stdin.write(chunk)
            proc.stdin.flush()
            hexed = reader.readline()
            measured = reader.readline()
            if not hexed.startswith("READBACK-HEX "):
                raise AssertionError(f"expected the bytes, got {hexed!r}")
            if not measured.startswith("READBACK-SHA "):
                raise AssertionError(f"expected the measure, got {measured!r}")
            reports.append((bytes.fromhex(hexed.split()[1]),
                            int(measured.split()[1]), measured.split()[2]))
        proc.stdin.close()
        eof = reader.readline()
        if not eof.startswith("LANE-EOF "):
            raise AssertionError(f"expected the EOF report, got {eof!r}")
        stderr = proc.stderr.read().decode()
        rc = proc.wait(timeout=20)
        return (b"".join(r[0] for r in reports), reports, int(eof.split()[1]),
                rc, stderr)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream and not stream.closed:
                stream.close()


class WorkerProtocolTest(unittest.TestCase):
    """DEFECT 1 at the protocol level: the read-back worker cannot lose a byte.

    The oracle's byte-identity claim is only as good as the thing that reports
    the bytes back. A `while read -r line` worker reports nothing at all for a
    trailing fragment with no newline after it — `read` holds that fragment
    until a delimiter or an EOF a live pane never sends — so a delivery with one
    byte appended was indistinguishable from the canonical one and the gate
    passed on a delivery that was not byte-identical. These tests run the shipped
    worker for real and hand it exactly those payloads.
    """

    def test_the_canonical_payload_comes_back_byte_for_byte(self):
        got, reports, eof_count, rc, err = run_worker(WORKER_SCRIPT, [PAYLOAD])
        self.assertEqual(rc, 0, err)
        self.assertEqual(got, PAYLOAD)
        self.assertEqual(len(got), 62, "the fixture is 62 bytes, newline included")
        self.assertEqual(eof_count, len(PAYLOAD))
        self.assertEqual(reports[-1][1], len(PAYLOAD))
        self.assertEqual(reports[-1][2], hashlib.sha256(PAYLOAD).hexdigest(),
                         "the worker's own digest must equal the FILE's")

    def test_a_byte_appended_after_the_newline_is_reported_not_held(self):
        """The evaluator's mutation, at the protocol level."""
        sent = PAYLOAD + b"X"
        got, reports, eof_count, rc, _err = run_worker(WORKER_SCRIPT, [sent])
        self.assertEqual(rc, 0)
        self.assertEqual(got, sent)
        self.assertNotEqual(got, PAYLOAD, "the extra byte went unreported")
        self.assertEqual(eof_count, len(sent))
        self.assertEqual(reports[-1][2], hashlib.sha256(sent).hexdigest())

    def test_a_missing_trailing_newline_is_reported(self):
        """The other half of DEFECT 1: the oracle compared 61 stripped bytes."""
        sent = PAYLOAD[:-1]
        got, _reports, eof_count, rc, _err = run_worker(WORKER_SCRIPT, [sent])
        self.assertEqual(rc, 0)
        self.assertEqual(got, sent)
        self.assertEqual(len(got), 61)
        self.assertNotEqual(got, PAYLOAD)
        self.assertEqual(eof_count, 61)

    def test_a_payload_split_across_two_writes_is_reassembled_in_order(self):
        got, reports, eof_count, rc, _err = run_worker(
            WORKER_SCRIPT, [PAYLOAD[:20], PAYLOAD[20:]])
        self.assertEqual(rc, 0)
        self.assertEqual(len(reports), 2, "each chunk must be reported as it lands")
        self.assertEqual(got, PAYLOAD)
        self.assertEqual(eof_count, len(PAYLOAD))

    def test_nothing_delivered_reports_zero_bytes(self):
        got, reports, eof_count, rc, _err = run_worker(WORKER_SCRIPT, [])
        self.assertEqual(rc, 0)
        self.assertEqual((got, reports, eof_count), (b"", [], 0))

    def test_control_a_line_oriented_worker_loses_the_trailing_byte(self):
        """Why the shipped worker is not a line reader, measured rather than
        asserted: the old shape reports the canonical payload and silently drops
        the appended byte, so any oracle built on it passes a delivery that is
        not byte-identical."""
        sent = PAYLOAD + b"X"
        proc = subprocess.run(["sh", "-c", LINE_WORKER], input=sent,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        bodies = re.findall(rb"READBACK<(.*?)>", proc.stdout, re.S)
        reconstructed = b"".join(body + b"\n" for body in bodies)
        self.assertEqual(reconstructed, PAYLOAD,
                         "the control changed shape: it no longer models DEFECT 1")
        self.assertNotEqual(reconstructed, sent,
                            "a line reader reported the trailing byte after all")


class ReadBackOracleTest(unittest.TestCase):
    """The smoke's comparison itself, pinned against the two shapes that made it
    blind: a stripped `want` (61 bytes for a 62-byte fixture) and a
    last-sentinel-only extraction."""

    def setUp(self):
        self.smoke = SMOKE.read_text()

    def test_the_read_back_is_compared_to_the_payload_file_with_cmp(self):
        self.assertIn('cmp "$SBX/readback.bin" "$PAYLOAD"', self.smoke)
        self.assertIn('want_bytes=$(wc -c < "$PAYLOAD"', self.smoke)
        self.assertIn('want_sha=$(sha256_of "$PAYLOAD")', self.smoke)

    def test_the_worker_own_measure_is_waited_for_by_count_and_digest(self):
        self.assertIn("READBACK-SHA $want_bytes $want_sha", self.smoke)

    def test_the_literal_bytes_are_reconstructed_from_the_rail(self):
        self.assertIn("READBACK-HEX ([0-9a-f]+)", self.smoke)
        self.assertIn("sys.stdout.buffer.write(bytes.fromhex(", self.smoke)

    def test_no_stripped_copy_of_the_payload_is_compared_any_more(self):
        for blind in ("want.txt", "readback.txt", "rstrip", "found[-1]"):
            self.assertNotIn(blind, self.smoke,
                             f"{blind} is the shape that hid DEFECT 1")


class ShippedExampleTest(unittest.TestCase):
    def test_conf_supervised_lane_toml_is_a_valid_preset(self):
        preset = lane.load_preset(str(REPO / "conf" / "supervised-lane.toml"))
        self.assertEqual(preset["kind"], "supervised")
        self.assertTrue(preset["argv"])

    def test_the_worker_fixture_declares_its_readiness_marker(self):
        preset = lane.load_preset(str(FIXTURES / "worker.toml"))
        self.assertEqual(preset["ready_match"], "LANE-READY")
        self.assertIn("LANE-READY", preset["argv"][-1])

    def test_the_worker_fixture_is_byte_oriented_not_line_oriented(self):
        """DEFECT 1's root cause, pinned in the fixture: no line reader, and the
        tty's own line discipline turned off so a trailing fragment arrives."""
        script = WORKER_SCRIPT
        self.assertNotIn("read -r", script)
        self.assertIn("termios.ICANON", script)
        self.assertIn("termios.ECHO", script)
        self.assertIn("os.read(0", script)
        for tag in ("READBACK-HEX", "READBACK-SHA", "LANE-EOF"):
            self.assertIn(tag, script)

    def test_blocked_targets_the_lane_the_worker_preset_started(self):
        """blocked.toml is delivered TO, never started: its `name` is the join
        and its argv is inert, so the two presets must not drift apart."""
        worker = lane.load_preset(str(FIXTURES / "worker.toml"))
        blocked = lane.load_preset(str(FIXTURES / "blocked.toml"))
        self.assertEqual(blocked["name"], worker["name"])
        self.assertTrue(blocked["submit"], "the refusal is the agent prompt's")
        self.assertFalse(worker["submit"], "spec F.14: populate, never submit")
        smoke = SMOKE.read_text()
        self.assertIn('lane_run deliver "$P/blocked.toml"', smoke)
        self.assertNotIn('start "$P/blocked.toml"', smoke)


if __name__ == "__main__":
    unittest.main()
