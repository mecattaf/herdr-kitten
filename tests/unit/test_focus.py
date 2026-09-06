"""BUG-6 — the focused-window resolver, over the real shape of `kitty @ ls`.

RULING-kitten §3.4 item 4 asks for exactly this: "multi-tab `kitty @ ls`
fixture in which N windows report `is_focused`; asserts exactly the truly-
focused window is chosen".

The fixture is not invented. Its three flags are transcribed from the kitty
0.48.0 in this closure, so the test fails if kitty's own semantics move:

    os_window  'is_focused': focused_wid == os_window_id            boss.py:528
               'is_active':  tm is active_tab_manager
    tab        'is_focused': tab is active_tab
                             and tab.os_window_id == current_focused_os_window_id()
                                                                    tabs.py:1456
               'is_active':  tab is active_tab
    window     is_focused=w.os_window_id == current_focused_os_window_id()
                          and w is active_window                    tabs.py:1064

The third line is the bug: `active_window` is per TAB, so a focused OS window
with N tabs stamps `is_focused: true` on N windows. The old resolver flattened
every OS window x tab and took the first — the active window of tab 1 — and
dictated text went there instead of to the window the user was looking at.
"""

import itertools
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

from hk import kittyc  # noqa: E402


def build_ls(shape, focused_os=0, focused_tabs=None, active_windows=None,
             kitty_has_focus=True):
    """A `kitty @ ls` tree.

    shape: [[windows_in_tab, ...] per OS window, ...]
    focused_os: index of the OS window the compositor focuses
    focused_tabs: active tab index per OS window (default 0)
    active_windows: active window index per (os, tab) (default 0)
    kitty_has_focus: False models kitty itself unfocused — kitty then stamps
                     `is_focused: false` everywhere and only `is_active` holds.
    """
    focused_tabs = focused_tabs or [0] * len(shape)
    active_windows = active_windows or {}
    wid = itertools.count(1)
    tid = itertools.count(101)
    tree = []
    for oi, tabs in enumerate(shape):
        os_focused = kitty_has_focus and oi == focused_os
        tab_dicts = []
        for ti, n_windows in enumerate(tabs):
            tab_active = ti == focused_tabs[oi]
            active_w = active_windows.get((oi, ti), 0)
            windows = [{
                "id": next(wid),
                "is_active": wi == active_w,
                # tabs.py:1064 — the per-tab stamp that is BUG-6
                "is_focused": os_focused and wi == active_w,
                "title": f"os{oi}/tab{ti}/win{wi}",
                "user_vars": {"hk_role": "herdr", "hk_pane": f"w{oi}:p{ti}{wi}"},
            } for wi in range(n_windows)]
            tab_dicts.append({
                "id": next(tid),
                "is_active": tab_active,
                "is_focused": tab_active and os_focused,
                "title": f"os{oi}/tab{ti}",
                "windows": windows,
            })
        tree.append({
            "id": oi + 1,
            "is_active": oi == focused_os,
            "is_focused": os_focused,
            "tabs": tab_dicts,
        })
    return tree


def truly_focused_title(shape, focused_os, focused_tabs, active_windows):
    ti = focused_tabs[focused_os]
    wi = active_windows.get((focused_os, ti), 0)
    return f"os{focused_os}/tab{ti}/win{wi}"


def first_match_resolver(os_windows):
    """The resolver as it shipped before this fix, kept as the RED reference:
    flatten every OS window x tab, return the first `is_focused`."""
    for os_window in os_windows:
        for tab in os_window.get("tabs", []):
            for window in tab.get("windows", []):
                if window.get("is_focused"):
                    return window
    return None


class ArrangementTest(unittest.TestCase):
    """Every arrangement, not one lucky one."""

    SHAPES = [
        [[1]],
        [[1, 1]],
        [[2, 3]],
        [[1, 1, 1, 1]],
        [[2], [2]],
        [[3, 1], [1, 2], [2, 2]],
    ]

    def arrangements(self):
        for shape in self.SHAPES:
            for focused_os in range(len(shape)):
                tab_choices = [range(len(tabs)) for tabs in shape]
                for focused_tabs in itertools.product(*tab_choices):
                    win_keys = [(oi, ti) for oi, tabs in enumerate(shape)
                                for ti in range(len(tabs))]
                    win_choices = [range(shape[oi][ti]) for oi, ti in win_keys]
                    for combo in itertools.product(*win_choices):
                        active = dict(zip(win_keys, combo))
                        yield shape, focused_os, list(focused_tabs), active

    def test_the_truly_focused_window_is_chosen_exactly_once(self):
        seen = 0
        for shape, focused_os, focused_tabs, active in self.arrangements():
            tree = build_ls(shape, focused_os, focused_tabs, active)
            chosen = kittyc.resolve_focused_window(tree)
            want = truly_focused_title(shape, focused_os, focused_tabs, active)
            self.assertIsNotNone(chosen, f"no window chosen for {want}")
            self.assertEqual(chosen["title"], want,
                             f"wrong window for shape={shape} os={focused_os} "
                             f"tabs={focused_tabs} active={active}")
            # "exactly once": the resolver's own candidate set is a singleton,
            # not a list it happens to index [0] of.
            candidates = [w for os_w in tree if os_w["is_focused"]
                          for tab in os_w["tabs"] if tab["is_focused"]
                          for w in tab["windows"] if w["is_focused"]]
            self.assertEqual(len(candidates), 1, f"{len(candidates)} candidates")
            seen += 1
        self.assertGreater(seen, 100, "the arrangement sweep collapsed")

    def test_the_fixture_really_reproduces_bug_6(self):
        """Guard the guard: in at least one multi-tab arrangement the shipped
        first-match resolver picks a DIFFERENT window. Without this, the sweep
        above could pass against a resolver that never fixed anything."""
        divergences = 0
        for shape, focused_os, focused_tabs, active in self.arrangements():
            tree = build_ls(shape, focused_os, focused_tabs, active)
            old = first_match_resolver(tree)
            new = kittyc.resolve_focused_window(tree)
            if old is not new:
                divergences += 1
        self.assertGreater(divergences, 0,
                           "the fixture never makes the old resolver misfire")

    def test_n_windows_report_focused_in_a_multi_tab_arrangement(self):
        """The premise of the bug, stated as a fact about the fixture."""
        tree = build_ls([[1, 1, 1, 1]], focused_os=0, focused_tabs=[3])
        flagged = [w for os_w in tree for tab in os_w["tabs"]
                   for w in tab["windows"] if w["is_focused"]]
        self.assertEqual(len(flagged), 4, "kitty stamps is_focused per tab")
        self.assertEqual(kittyc.resolve_focused_window(tree)["title"],
                         "os0/tab3/win0")
        self.assertEqual(first_match_resolver(tree)["title"], "os0/tab0/win0",
                         "this is the misdelivery BUG-6 names")


class FailClosedTest(unittest.TestCase):
    """A dictation tool that guesses is worse than one that declines."""

    def test_kitty_unfocused_yields_no_window(self):
        tree = build_ls([[2, 2]], kitty_has_focus=False)
        self.assertIsNone(kittyc.resolve_focused_window(tree))

    def test_empty_tree(self):
        self.assertIsNone(kittyc.resolve_focused_window([]))

    def test_ambiguous_tree_is_declined_not_guessed(self):
        tree = build_ls([[2]])
        tree[0]["tabs"][0]["windows"][1]["is_focused"] = True
        self.assertIsNone(kittyc.resolve_focused_window(tree),
                          "two focused windows must not resolve to a guess")

    def test_a_tree_without_flags_is_not_disqualified(self):
        """Older/partial trees carry is_active only; absence is not evidence."""
        tree = [{"id": 1, "tabs": [{"id": 101, "is_active": True, "windows": [
            {"id": 1, "is_active": True, "title": "only"}]}]}]
        self.assertEqual(kittyc.resolve_focused_window(tree)["title"], "only")


class NoFirstMatchLeftTest(unittest.TestCase):
    """The RED case, pinned in source: the flatten-and-take-first shape must
    not come back into the resolver."""

    def test_focused_window_walks_the_chain(self):
        src = (REPO / "hk" / "kittyc.py").read_text()
        body = src.split("def resolve_focused_window")[1].split("\ndef ")[0]
        self.assertIn("tabs", body, "the resolver must see tabs, not a flat list")
        self.assertNotIn("for window in windows()", body)
        self.assertIn("len(found) == 1", body,
                      "the resolver must require a unique candidate")


if __name__ == "__main__":
    unittest.main()
