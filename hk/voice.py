"""hk voice — the dictation endpoint contract (spec R5, D8, D9; census P18/P20/P43).

Verbs: begin / text / end. The hold-to-talk binding lives in the CONSUMER's
config, never here. Exit codes are the caller contract (D9): 0 delivered,
1 herdr error, 2 usage, 3 not-a-herdr-window (caller falls back to
compositor-level injection, sending zero bytes through hk).
"""

from __future__ import annotations

import os
import subprocess
import sys

from hk import herdrc, kittyc, predicate, verbs

EXIT_OK = 0
EXIT_HERDR_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_HERDR_WINDOW = 3


def spinner_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    for cand in (os.path.join(here, "assets", "spinner.png"),
                 os.path.expanduser("~/.config/kitty/hk-assets/spinner.png")):
        if os.path.exists(cand):
            return cand
    return os.path.join(here, "assets", "spinner.png")


def cmd_begin(window_id: str, spin: bool = False) -> int:
    """Spinner logo bottom-right (D8): indicate, never mutate — the window's
    content and input flow are untouched. Static PNG; --spin reserved
    (DECISION-2 adopted-as-proposed: frame-cycling behind the flag)."""
    try:
        kittyc._run(["set-window-logo", "--match", f"id:{window_id}",
                     "--position", "bottom-right", spinner_path()])
        return EXIT_OK
    except kittyc.KittyError as exc:
        print(f"hk voice begin: {exc}", file=sys.stderr)
        return EXIT_HERDR_ERROR


def cmd_end(window_id: str) -> int:
    try:
        kittyc._run(["set-window-logo", "--match", f"id:{window_id}", "none"])
        return EXIT_OK
    except kittyc.KittyError as exc:
        print(f"hk voice end: {exc}", file=sys.stderr)
        return EXIT_HERDR_ERROR


def _focused_herdr_pane() -> str | None:
    window = kittyc.focused_window()
    if window is None or not predicate.is_herdr_client(window):
        return None
    return (window.get("user_vars") or {}).get("hk_pane") or None


def cmd_text(submit: bool = False) -> int:
    """spec 5.1/5.2 (G11/G12): stdin -> the focused window's herdr pane;
    plain window -> exit 3, zero bytes sent anywhere."""
    pane = _focused_herdr_pane()
    if pane is None:
        print("hk voice text: focused window is not a herdr client (fall back to injection)",
              file=sys.stderr)
        return EXIT_NOT_HERDR_WINDOW
    try:
        text = verbs.read_payload()
    except verbs.PayloadError as exc:
        print(f"hk voice text: {exc}", file=sys.stderr)
        return EXIT_HERDR_ERROR
    try:
        if submit:
            herdrc.agent_prompt(pane, text)
        else:
            # ONE framing implementation for the whole repo. voice used to
            # carry its own copy of the paste-frame constants and inherited
            # every bug the send path had; now both ride herdrc._deliver.
            clean, removed = herdrc.sanitise_framed(text)
            if removed:
                print(f"hk voice text: removed {removed} bracketed-paste "
                      f"terminator{'s' if removed > 1 else ''} from the "
                      f"dictated text", file=sys.stderr)
            herdrc.pane_send_input(pane, clean)
        return EXIT_OK
    except herdrc.HerdrError as exc:
        code = getattr(exc, "code", "") or ""
        prefix = f"{code}: " if code and code != "herdr_error" else ""
        print(f"{prefix}{exc}", file=sys.stderr)
        return EXIT_HERDR_ERROR
