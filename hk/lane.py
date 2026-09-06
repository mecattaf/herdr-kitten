"""hk lane — supervised lanes launched from declared preset data.

One module carries three ports (herdr-kitten #36/#37/#38 = tally.nix
#670/#673/#678):

  * **#36 / #670 — spawn a supervised lane from preset data.** Pane selection
    and worker startup are terminal-rail operations. The invoking kit ships a
    *preset file*; hk reads it and launches the declared worker argv in a pane
    it selects. Nothing about the worker is compiled into hk, and nothing about
    panes is compiled into the caller — which is exactly why the tally kernel
    renders nothing and grows no harness behaviour.
  * **#37 / #673 — prove supervised delivery.** `tests/smoke/supervised-lane.sh`
    drives these verbs: it sends the canonical payload on stdin, reads it back
    through the terminal rail byte-identical, asserts the typed exits, and
    tears its test session down.
  * **#38 / #678 — plain-kitty delivery stays behind hk.** The payload is
    always on stdin, never argv, and the exits are typed. tally therefore never
    grows a `kitty @` implementation of its own.

EXIT CODES are RULING-kitten §5's, unchanged — `hk/verbs.py` owns the constants
and every other verb already answers with them:

    0  delivered
    1  refused by herdr or by the tool; the machine-readable code is printed
       verbatim on stderr (`agent_blocked`, `timeout`, …)
    2  CLI or preset syntax — the preset is malformed
    3  no lane reachable; **zero bytes were sent** (the safe-fallback signal)
    4  not implemented

The card for this unit glosses those five numbers differently (0 delivered,
1 refused, 2 no session, 3 timeout, 4 malformed). RULING-kitten §5 is the
captured ruling and it is already load-bearing across this repo, so the numbers
keep their §5 meanings and every one of the card's five *outcomes* is still
produced and asserted: delivered (0), refused (1, `agent_blocked`), timeout
(1, `timeout`), malformed preset (2), no session (1, `server_not_running`, when
no herdr server is up at all; 3 when one is up and no lane of that name is
running — §5's "no target reachable, zero bytes sent"), not implemented (4).
The divergence is recorded in docs/dev/DEFERRED.md.

WAITING. `hk lane start` may wait, bounded, for the worker to announce itself
(`ready_match`/`ready_timeout_ms`). Spec F.6 bars polling in *interactive*
paths; a lane launch is a lifecycle path whose whole job is "the worker is up",
and reporting 0 before the worker exists would be a lie a supervisor cannot
recover from. The wait is opt-in — a preset with no `ready_match` never sleeps.

RESIDUE. `hk lane start` either produces a lane that can be addressed, or leaves
nothing behind. The pane is split before it can be stamped, named or waited on,
so every step after the split sits inside one cleanup boundary: any fault closes
the pane again and says so in the same typed line, with herdr's own code still
leading it. A half-started lane is worse than no lane — the worker runs, no verb
can reach it, and the next `start` (which resolves the lane by its token and
finds none) splits a SECOND worker. For the same reason the join is READ BACK
before start reports 0: a metadata write herdr accepted but never published is
that same unaddressable state with no exception to catch.
`tests/proofs/hk1-retry-cleanup.py` measures both halves against a live server.
"""

from __future__ import annotations

import os
import time
import tomllib

from hk import herdrc, kittyc, verbs
from hk.verbs import (EXIT_HERDR_ERROR, EXIT_NOT_HERDR_WINDOW,
                      EXIT_NOT_IMPLEMENTED, EXIT_OK, EXIT_USAGE)

# The metadata token that makes a lane findable again. Written under source
# `user:hk` like every other token hk owns (spec D16), so a lane survives the
# process that started it and `deliver`/`stop` are separate invocations.
LANE_TOKEN = "hk_lane"

# The only lane kind hk implements. `unsupervised` is named, reserved and
# refused with exit 4: RULING-kitten §5 keeps unsupervised lanes on
# `systemd-run` with `stdin=/dev/null`, and hk never appears in one.
IMPLEMENTED_KINDS = ("supervised",)
RESERVED_KINDS = ("unsupervised",)

DEFAULT_KIND = "supervised"
DEFAULT_DIRECTION = "down"
DEFAULT_READY_TIMEOUT_MS = 15000
DIRECTIONS = ("down", "up", "left", "right")

# Bounded readiness wait: the interval is a lifecycle-path constant, not a
# tunable, so a preset cannot turn a lane launch into a busy loop.
_POLL_INTERVAL_S = 0.1
_READY_READ_LINES = 200

LANE_KEYS = {"name", "kind", "argv", "cwd", "direction",
             "ready_match", "ready_timeout_ms"}
DELIVERY_KEYS = {"submit", "raw"}
TABLES = {"lane", "delivery"}


class LaneError(ValueError):
    """A preset or lane fault, carrying the §5 exit code it deserves.

    Every instance raised before delivery is raised BEFORE any byte is written,
    which is what keeps the zero-bytes-sent guarantee of exit 3 intact.
    """

    def __init__(self, message: str, exit_code: int = EXIT_USAGE):
        super().__init__(message)
        self.exit_code = exit_code


# ------------------------------------------------------------------- presets

def _require(condition: bool, message: str, exit_code: int = EXIT_USAGE) -> None:
    if not condition:
        raise LaneError(message, exit_code)


def load_preset(path: str) -> dict:
    """Read a supervised-lane preset file into a validated dict.

    Strict on purpose: an unknown key is a typo, and a typo that is silently
    ignored is a supervisor delivering into a pane nobody asked for. Every
    structural fault is exit 2 with one line; the file is never half-applied,
    because nothing is launched until the whole preset validates.
    """
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError:
        raise LaneError(f"lane: no preset file at {path}")
    except IsADirectoryError:
        raise LaneError(f"lane: {path} is a directory, not a preset file")
    except OSError as exc:
        raise LaneError(f"lane: cannot read the preset {path}: {exc}")
    except tomllib.TOMLDecodeError as exc:
        raise LaneError(f"lane: {path} is not valid TOML: {exc}")

    unknown = sorted(set(raw) - TABLES)
    _require(not unknown,
             f"lane: {path} has unknown top-level table(s) {unknown}; "
             f"a preset carries {sorted(TABLES)} and nothing else")
    section = raw.get("lane")
    _require(isinstance(section, dict), f"lane: {path} has no [lane] table")
    unknown = sorted(set(section) - LANE_KEYS)
    _require(not unknown,
             f"lane: {path} [lane] has unknown key(s) {unknown}; "
             f"known keys are {sorted(LANE_KEYS)}")
    delivery = raw.get("delivery") or {}
    _require(isinstance(delivery, dict), f"lane: {path} [delivery] is not a table")
    unknown = sorted(set(delivery) - DELIVERY_KEYS)
    _require(not unknown,
             f"lane: {path} [delivery] has unknown key(s) {unknown}; "
             f"known keys are {sorted(DELIVERY_KEYS)}")

    name = section.get("name")
    _require(isinstance(name, str) and bool(name),
             f"lane: {path} [lane] needs a name (a string)")
    _require(bool(verbs.AGENT_NAME_RE.match(name)),
             f"lane: {path} lane name {name!r} is not addressable; "
             f"use letters, digits, '.', '_' or '-' (1-64 chars)")

    argv = section.get("argv")
    _require(isinstance(argv, list) and bool(argv),
             f"lane: {path} [lane] needs a non-empty argv array — the worker "
             f"argv is DATA the preset declares, never something hk knows")
    _require(all(isinstance(a, str) for a in argv),
             f"lane: {path} [lane] argv must be an array of strings")

    kind = section.get("kind", DEFAULT_KIND)
    _require(isinstance(kind, str), f"lane: {path} [lane] kind must be a string")

    cwd = section.get("cwd", os.getcwd())
    _require(isinstance(cwd, str) and bool(cwd),
             f"lane: {path} [lane] cwd must be a non-empty string")

    direction = section.get("direction", DEFAULT_DIRECTION)
    _require(direction in DIRECTIONS,
             f"lane: {path} [lane] direction {direction!r} is not one of "
             f"{list(DIRECTIONS)}")

    ready_match = section.get("ready_match")
    _require(ready_match is None or (isinstance(ready_match, str) and ready_match),
             f"lane: {path} [lane] ready_match must be a non-empty string")
    timeout_ms = section.get("ready_timeout_ms", DEFAULT_READY_TIMEOUT_MS)
    _require(isinstance(timeout_ms, int) and not isinstance(timeout_ms, bool)
             and timeout_ms > 0,
             f"lane: {path} [lane] ready_timeout_ms must be a positive integer "
             f"number of milliseconds")

    submit = delivery.get("submit", False)
    raw_bytes = delivery.get("raw", False)
    _require(isinstance(submit, bool) and isinstance(raw_bytes, bool),
             f"lane: {path} [delivery] submit and raw are booleans")
    _require(not (submit and raw_bytes),
             f"lane: {path} [delivery] submit and raw are mutually exclusive "
             f"(--submit hands the text to an agent, which owns its own "
             f"delivery; raw is about byte-level pane writes)")

    # The kind gate is LAST so that a preset which is both malformed and of an
    # unimplemented kind reports the syntax fault first: a caller cannot act on
    # "not implemented" until the file it wrote is actually readable.
    if kind not in IMPLEMENTED_KINDS:
        detail = ("RULING-kitten §5 keeps unsupervised lanes on systemd-run "
                  "with stdin=/dev/null; hk never appears in one"
                  if kind in RESERVED_KINDS else
                  f"implemented kinds are {list(IMPLEMENTED_KINDS)}")
        raise LaneError(
            f"lane: {path} declares kind {kind!r}, which hk does not "
            f"implement ({detail}). Nothing was launched.",
            EXIT_NOT_IMPLEMENTED)

    return {
        "path": path, "name": name, "kind": kind, "argv": list(argv),
        "cwd": cwd, "direction": direction, "ready_match": ready_match,
        "ready_timeout_ms": timeout_ms, "submit": submit, "raw": raw_bytes,
    }


# --------------------------------------------------------------- lane lookup

def find_pane(name: str, host: str | None = None) -> str | None:
    """The pane a running lane owns, or None. Tokens are the join, not labels:
    a label is a human surface anyone may rename, `hk_lane` is hk's own."""
    for pane in herdrc.pane_list(host=host):
        if (pane.get("tokens") or {}).get(LANE_TOKEN) == name:
            return pane["pane_id"]
    return None


def _anchor_pane(cwd: str, host: str | None) -> str | None:
    """Pane selection (#36): join this window's workspace, else the focused
    one, else create a workspace. The lane is split off whatever we land on."""
    ws_id = verbs._resolve_ws(host)
    if ws_id is None:
        created = herdrc.workspace_create(cwd=cwd, host=host)
        return created["root_pane"]["pane_id"]
    panes = herdrc.pane_list(workspace=ws_id, host=host)
    return panes[0]["pane_id"] if panes else None


# --------------------------------------------------------------------- verbs

def start(preset: dict, host: str | None = None) -> int:
    """Launch the preset's worker argv in a pane of its own.

    The argv rides the HK_EXEC trampoline (spec D5, gate G3), so the worker's
    exit IS the pane's exit and a finished lane reaps itself.

    A FAILED START LEAVES NO RESIDUE, whichever step fails. The pane is split
    first, and every step after the split sits inside one cleanup boundary
    (`_claim` -> `_abandon`), because a half-started lane is worse than no
    lane: the worker is running, nothing can address it, and the next
    `hk lane start` — which resolves the lane by its token and finds none —
    splits a SECOND worker. Cleanup is not a branch of the readiness path; it
    is the shape of the whole launch.
    """
    name = preset["name"]
    existing = find_pane(name, host=host)
    if existing is not None:
        raise LaneError(
            f"lane: {name!r} already runs in pane {existing}; stop it first. "
            f"Nothing was launched.")
    anchor = _anchor_pane(preset["cwd"], host)
    pane = herdrc.pane_split(
        pane_id=anchor, direction=preset["direction"], cwd=preset["cwd"],
        env={"HK_EXEC": verbs.encode_trampoline(preset["argv"])}, host=host)
    pane_id = pane["pane_id"]
    try:
        _claim(preset, pane_id, host)
    except Exception as exc:
        raise _abandon_and_report(preset, pane_id, exc, host) from exc
    print(pane_id)
    return EXIT_OK


def _claim(preset: dict, pane_id: str, host: str | None) -> None:
    """Turn a freshly split pane INTO a lane: stamp the join, prove it landed,
    name it, then — only if the preset asks — wait for the worker.

    The token is verified by reading it back rather than assumed. A metadata
    write herdr accepted but did not publish would leave exactly the state
    `start` exists to prevent: a running worker no `deliver`, `status` or
    `stop` can reach, and a retry that duplicates it. So `start` reports 0 only
    for a lane it has just resolved by name itself.
    """
    name = preset["name"]
    herdrc.report_metadata(
        pane_id, tokens={"hk_role": "lane", LANE_TOKEN: name}, host=host)
    resolved = find_pane(name, host=host)
    if resolved != pane_id:
        raise LaneError(
            f"lane: pane {pane_id} was split for {name!r} but does not answer "
            f"to its {LANE_TOKEN} token — that name resolves to {resolved!r}",
            EXIT_HERDR_ERROR)
    herdrc.pane_rename(pane_id, name, host=host)
    _await_ready(preset, pane_id, host)


def _abandon(pane_id: str, host: str | None) -> bool:
    """Close a half-started lane's pane. Best effort and never raising: the
    caller is already handling a failure, and a second failure must not mask
    the first — but whether it worked is reported, because "hk cleaned up" is
    a claim a supervisor should be able to check."""
    try:
        herdrc.pane_close(pane_id, host=host)
        return True
    except Exception:
        return False


def _abandon_and_report(preset: dict, pane_id: str, exc: Exception,
                        host: str | None) -> Exception:
    """Close the pane, then re-raise the SAME fault with the cleanup disclosed.

    The exit code and, for a herdr fault, the machine-readable code that leads
    the line are preserved exactly (RULING-kitten §5: the code is the half a
    supervisor branches on), and the message stays ONE line.
    """
    closed = _abandon(pane_id, host)
    note = (f"hk closed the half-started lane pane {pane_id}" if closed else
            f"hk could NOT close the half-started lane pane {pane_id}, which "
            f"may still be running")
    suffix = f" ({note}; nothing was delivered)"
    if isinstance(exc, herdrc.HerdrError):
        return herdrc.HerdrError(f"{exc}{suffix}", code=exc.code,
                                 stderr=exc.stderr)
    if isinstance(exc, LaneError):
        return LaneError(f"{exc}{suffix}", exc.exit_code)
    return LaneError(
        f"lane: start failed for {preset['name']!r}: "
        f"{exc.__class__.__name__}: {exc}{suffix}", EXIT_HERDR_ERROR)


def _await_ready(preset: dict, pane_id: str, host: str | None) -> None:
    marker = preset["ready_match"]
    if not marker:
        return
    deadline = time.monotonic() + preset["ready_timeout_ms"] / 1000.0
    while True:
        try:
            screen = herdrc.pane_read(pane_id, source="visible",
                                      lines=_READY_READ_LINES, fmt="text",
                                      host=host)
        except herdrc.HerdrError:
            screen = ""
        if marker in screen:
            return
        if time.monotonic() >= deadline:
            # The pane is closed by `start`'s cleanup boundary, not here: one
            # place owns residue, so no failure path can forget it.
            raise LaneError(
                f"timeout: lane {preset['name']!r} never printed {marker!r} "
                f"within {preset['ready_timeout_ms']} ms",
                EXIT_HERDR_ERROR)
        time.sleep(_POLL_INTERVAL_S)


def deliver(preset: dict, host: str | None = None, stream=None) -> int:
    """Payload on stdin -> the lane's pane. Never argv (#38 / §5)."""
    name = preset["name"]
    # The lane is resolved BEFORE stdin is read, so an unreachable lane costs
    # zero bytes and the caller learns it before piping a megabyte at us.
    pane_id = find_pane(name, host=host)
    if pane_id is None:
        raise LaneError(
            f"lane: no supervised lane named {name!r} is running; nothing was "
            f"sent (start it with: hk lane start {preset['path']})",
            EXIT_NOT_HERDR_WINDOW)
    try:
        text = verbs.read_payload(stream)
    except verbs.PayloadError as exc:
        raise LaneError(f"lane deliver: {exc}", EXIT_HERDR_ERROR)
    if preset["submit"]:
        herdrc.agent_prompt(pane_id, text, host=host)
    elif preset["raw"]:
        herdrc.pane_send_text(pane_id, text, host=host)
    else:
        clean, removed = herdrc.sanitise_framed(text)
        if removed:
            verbs._err(
                f"lane deliver: removed {removed} bracketed-paste terminator"
                f"{'s' if removed > 1 else ''} from the payload; left in place "
                f"they would end the paste early and the rest would be TYPED "
                f"as input (declare raw = true in [delivery] if you meant it)")
        herdrc.pane_send_input(pane_id, clean, host=host)
    return EXIT_OK


def status(preset: dict, host: str | None = None) -> int:
    pane_id = find_pane(preset["name"], host=host)
    if pane_id is None:
        raise LaneError(
            f"lane: no supervised lane named {preset['name']!r} is running",
            EXIT_NOT_HERDR_WINDOW)
    print(pane_id)
    return EXIT_OK


def stop(preset: dict, host: str | None = None) -> int:
    """Tear the lane down. The test session's teardown is a verb, not a trap."""
    pane_id = find_pane(preset["name"], host=host)
    if pane_id is None:
        raise LaneError(
            f"lane: no supervised lane named {preset['name']!r} is running; "
            f"nothing to stop",
            EXIT_NOT_HERDR_WINDOW)
    herdrc.pane_close(pane_id, host=host)
    print(pane_id)
    return EXIT_OK


VERBS = {"start": start, "deliver": deliver, "status": status, "stop": stop}


def cmd_lane(args) -> int:
    host = getattr(args, "host", None)
    try:
        preset = load_preset(args.preset)
        return VERBS[args.lane_verb](preset, host=host)
    except LaneError as exc:
        verbs._err(str(exc))
        return exc.exit_code
    except herdrc.HerdrError as exc:
        return verbs._herdr_fail(exc)
    except kittyc.KittyError as exc:
        verbs._err(f"lane: {exc}")
        return EXIT_HERDR_ERROR
