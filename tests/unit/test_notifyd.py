"""notifyd decision-logic units (spec 8.1-8.5, D26; probe surprises 1-2)."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from hk import notifyd


class SubscriptionsTest(unittest.TestCase):
    def test_globals_plus_per_pane(self):
        subs = notifyd.subscriptions(["w1:p1", "w1:p2"])
        types = [s["type"] for s in subs]
        for t in ("pane.created", "pane.closed", "pane.exited", "pane.updated"):
            self.assertIn(t, types)
        per_pane = [s for s in subs if s["type"] == "pane.agent_status_changed"]
        self.assertEqual([s["pane_id"] for s in per_pane], ["w1:p1", "w1:p2"])
        for s in per_pane:  # probe surprise 1: pane_id REQUIRED
            self.assertIn("pane_id", s)


class ShouldNotifyTest(unittest.TestCase):
    def test_once_per_transition(self):
        self.assertTrue(notifyd.should_notify(None, "blocked"))
        self.assertTrue(notifyd.should_notify("working", "done"))
        self.assertFalse(notifyd.should_notify("blocked", "blocked"))
        self.assertFalse(notifyd.should_notify(None, "working"))
        self.assertFalse(notifyd.should_notify("blocked", "idle"))


class FakeNotifyd(notifyd.Notifyd):
    def __init__(self):
        super().__init__(notify_command="true")
        self.notified = []
        self.uservars = []

    def run_notify(self, pane_id, state, agent):
        self.notified.append((pane_id, state, agent))

    def set_user_var(self, pane_id, key, value):
        self.uservars.append((pane_id, key, value))


class HandleTest(unittest.TestCase):
    def envelope(self, event, **data):
        return {"event": event, "data": data}

    def test_blocked_transition_notifies_and_mirrors(self):
        d = FakeNotifyd()
        resub = d.handle(self.envelope("pane.agent_status_changed",
                                       pane_id="w1:p1", agent_status="blocked",
                                       agent="fake", workspace_id="w1"))
        self.assertFalse(resub)
        self.assertEqual(d.notified, [("w1:p1", "blocked", "fake")])
        self.assertEqual(d.uservars, [("w1:p1", "hk_status", "blocked")])

    def test_repeat_state_no_double_notify(self):
        d = FakeNotifyd()
        env = self.envelope("pane.agent_status_changed", pane_id="w1:p1",
                            agent_status="blocked", agent="fake", workspace_id="w1")
        d.handle(env)
        d.handle(env)
        self.assertEqual(len(d.notified), 1)

    def test_pane_set_change_resubscribes(self):
        d = FakeNotifyd()
        self.assertTrue(d.handle(self.envelope("pane.created", pane_id="w1:p9")))
        self.assertTrue(d.handle(self.envelope("pane.exited", pane_id="w1:p9")))

    def test_editor_role_mirror(self):
        d = FakeNotifyd()
        d.handle(self.envelope("pane.updated", pane_id="w1:p1",
                               tokens={"hk_role": "editor"}))
        self.assertEqual(d.uservars, [("w1:p1", "hk_role", "editor")])


class OneCallSiteTest(unittest.TestCase):
    def test_exactly_one_events_subscribe_call_site(self):
        """spec 8.5: the whole repo contains exactly one events.subscribe caller
        (tests and docs excluded)."""
        repo = pathlib.Path(__file__).resolve().parent.parent.parent
        hits = []
        for path in list(repo.glob("hk/*.py")) + list(repo.glob("kitten/*.py")) + [repo / "bin" / "hk"]:
            text = path.read_text()
            count = text.count('"events.subscribe"')
            if count:
                hits.append((str(path), count))
        self.assertEqual(hits, [(str(repo / "hk" / "notifyd.py"), 1)], hits)
