"""Pure routing logic for the kitten gestures (spec R6.4, R10.5-R10.6, D10-D12).

No kitty imports here — everything operates on plain window dicts so the
routing table unit-tests without kitty (spec 6.4 demands exactly that).

WHY predicate IS LOADED BY PATH AND NOT BY `from hk import predicate`
(round2-01, the kitten half of BUG-3):

kitty's custom-kitten loader inserts the kitten's own directory at sys.path[0]
(`kittens/runner.py:57-58`). The kitten file is named `hk.py`. A module file
named `hk.py` and a package directory named `hk/` can never coexist on one
sys.path entry — the file wins, so `from hk import predicate` resolves `hk` to
the KITTEN and raises

    ImportError: cannot import name 'predicate' from 'hk' (.../kitten/hk.py)

That is not a packaging preference; it fires in the dev tree too, and it is the
reason no gesture has ever dispatched. The kitten tree is therefore made
self-contained: it locates `predicate.py` as a FILE and loads it under a
private module name, so no `hk` name lookup happens on the kitten side at all.
There is still exactly one copy of the logic in the repo (`hk/predicate.py`);
the installer places a copy beside the kitten for installed layouts.
"""

from __future__ import annotations

import importlib.util
import os
import sys


def _load_predicate():
    """Load hk/predicate.py by path, under a name that cannot collide.

    Candidates, in order of preference:
      1. a copy sitting beside this file (the installed kitten tree),
      2. <repo>/hk/predicate.py (the dev tree / a nix share tree),
      3. a genuine `hk` PACKAGE already importable (belt and braces; rejected
         when `hk` resolved to the kitten module instead of the package).
    """
    here = os.path.dirname(os.path.realpath(__file__))
    candidates = (
        os.path.join(here, "predicate.py"),
        os.path.join(os.path.dirname(here), "hk", "predicate.py"),
    )
    for path in candidates:
        if not os.path.isfile(path):
            continue
        spec = importlib.util.spec_from_file_location("_hk_predicate", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("_hk_predicate", module)
        spec.loader.exec_module(module)
        return module
    # 3. Only reachable when neither file is on disk. A real package answers;
    #    the kitten-file impostor raises ImportError and we re-raise with the
    #    diagnosis rather than the confusing stock message.
    try:
        from hk import predicate as module  # type: ignore[no-redef]
        return module
    except ImportError as exc:
        raise ImportError(
            "herdr-kitten: cannot locate predicate.py. Looked for "
            + " and ".join(candidates)
            + f". Falling back to the `hk` package failed too ({exc}). "
              "Reinstall with install.sh — the kitten tree is incomplete."
        ) from exc


predicate = _load_predicate()

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
