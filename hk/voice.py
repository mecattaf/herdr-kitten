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
    content and input flow are untouched.

    `--spin` is RESERVED, not implemented. RULING-kitten §4 row #13: a silently
    inert flag fails the bug-free bar, so the flag announces itself on stderr
    and the static glyph is shown. The frame-cycler itself is DECISION-2, an
    open question that is not this unit's to answer.
    """
    if spin:
        print("hk voice begin: --spin is reserved and not implemented "
              "(DECISION-2 is open); showing the static mic glyph",
              file=sys.stderr)
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


def _focused_herdr_pane() -> tuple[str | None, str]:
    """(pane id, "") or (None, the one-line reason there is no destination).

    Every branch here ends at exit 3 — "no herdr client focused, zero bytes
    sent" — including the one that used to end in a traceback: a caller with
    no `$KITTY_LISTEN_ON` (every dictation daemon, which runs outside kitty)
    reached `kitty @` with no socket to aim at and got a raw KittyError
    through the top of the program. A traceback is never an acceptable answer
    to a caller contract that says "on 3, fall back and inject".
    """
    try:
        window = kittyc.focused_window()
    except kittyc.KittyError as exc:
        return None, f"{exc} (fall back to injection)"
    if window is None:
        return None, "no single focused kitty window (fall back to injection)"
    if not predicate.is_herdr_client(window):
        return None, "focused window is not a herdr client (fall back to injection)"
    pane = (window.get("user_vars") or {}).get("hk_pane") or None
    if pane is None:
        return None, "focused herdr window projects no pane (fall back to injection)"
    return pane, ""


def cmd_text(submit: bool = False, argv_text: list[str] | None = None) -> int:
    """spec 5.1/5.2 (G11/G12): stdin -> the focused window's herdr pane;
    plain window -> exit 3, zero bytes sent anywhere.

    Argument order is deliberate. The destination precondition is resolved
    FIRST, so a caller that is not looking at a herdr client gets exit 3 —
    the code its fallback branch is written against — whatever else its argv
    said. Only once a real destination exists does a payload on argv become
    reportable, and it is refused rather than delivered: the payload is always
    on stdin, never argv (the standing rule `verbs.read_payload` carries).
    """
    pane, why = _focused_herdr_pane()
    if pane is None:
        print(f"hk voice text: {why}", file=sys.stderr)
        return EXIT_NOT_HERDR_WINDOW
    if argv_text:
        count = len(argv_text)
        print(f"hk voice text: the dictated text is read from stdin, never argv "
              f"({count} trailing word{'s' if count > 1 else ''} refused, "
              f"nothing delivered); pipe it instead", file=sys.stderr)
        return EXIT_USAGE
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
