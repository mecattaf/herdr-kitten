"""Pure routing logic for the kitten gestures (spec R6.4, R10.5-R10.6, D10-D12).

No kitty imports here — everything operates on plain window dicts so the
routing table unit-tests without kitty (spec 6.4 demands exactly that).
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hk import predicate  # noqa: E402

# The role toggle stamps on the vsplit it launches; a second toggle from that
# window closes it (close IS detach — probe P-G2).
SPLIT_ROLE = "split"

# toggle outcomes
PREFIX = "prefix"          # write \x02 to the child (defer to herdr's prefix layer)
CLOSE = "close"            # close the kitty window; the pane survives
LAUNCH_SPLIT = "launch_split"  # open a herdr vsplit running `hk open`

# scrollback outcomes
HERDR_LANE = "herdr"       # forward \x02e -> herdr keys.edit_scrollback
PLAIN_LANE = "plain"       # run plain_scrollback_action from hk-config


def toggle_action(window: dict) -> str:
    """The toggle ladder (spec 10.5, 10.6, flow ruling D10).

    herdr_ui (thin client)  -> PREFIX  (herdr owns its own prefix layer)
    the toggle-launched split -> CLOSE (second invocation; close IS detach)
    any other herdr client  -> PREFIX
    plain window            -> LAUNCH_SPLIT
    """
    role = predicate.role_of(window)
    if role == "herdr_ui":
        return PREFIX
    if role == SPLIT_ROLE:
        return CLOSE
    if predicate.is_herdr_client(window):
        return PREFIX
    return LAUNCH_SPLIT


def scrollback_lane(window: dict) -> str:
    """The two-lane dispatcher (spec 6.2-6.4, D12).

    A herdr window must NEVER reach the plain lane. The split window hosts a
    herdr attach, so it routes to the herdr lane like any other client.
    """
    if predicate.role_of(window) == SPLIT_ROLE:
        return HERDR_LANE
    if predicate.is_herdr_client(window):
        return HERDR_LANE
    return PLAIN_LANE


def fork_target(window: dict) -> str | None:
    """spec 11.1/11.8: the target pane comes from the window's hk_pane user-var;
    a window without one means fork is a silent no-op."""
    pane = (window.get("user_vars") or {}).get("hk_pane")
    return pane if pane else None
