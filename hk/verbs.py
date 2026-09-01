"""hk verbs — stage S2 core (spec claims R2, R3, R4, R6.1, R7, R9 subset, R10 subset).

Every verb is a socket/CLI join, never a scheduler (spec F.3). No polling or
sleeping in any interactive path (spec F.6). Socket actions never move focus
(spec F.7) — `hk focus` is the one verb whose job IS focusing, and it moves
focus via kitty, not via a background socket action.
"""

from __future__ import annotations

import base64
import os
import shlex
import sys

from hk import config as hk_config
from hk import herdrc, kittyc

EXIT_OK = 0
EXIT_HERDR_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_HERDR_WINDOW = 3
EXIT_NOT_IMPLEMENTED = 4

READ_CAP = 1000  # server-enforced (census P21; probe: 999 returned on a 5000-line ask)

# Durable labels claimed by plugins own their panes (spec 7.5, census P36):
# the title bridge must never fight them.
PLUGIN_LABELS = frozenset({"reviewr"})


def _err(message: str) -> None:
    print(f"hk: {message}", file=sys.stderr)


def _herdr_fail(exc: herdrc.HerdrError) -> int:
    # propagate the server error verbatim (spec 4.2: refusal is a real signal)
    print(str(exc), file=sys.stderr)
    return EXIT_HERDR_ERROR


def plugin_owned(label: str | None) -> bool:
    if not label:
        return False
    return label in PLUGIN_LABELS or label.startswith("plugin:")


def encode_trampoline(argv: list[str]) -> str:
    """b64 payload for the HK_EXEC trampoline (spec D5, probe P-G3)."""
    quoted = " ".join(shlex.quote(a) for a in argv)
    return base64.b64encode(quoted.encode()).decode()


def default_label(cwd: str) -> str:
    """spec 9.2 / census-map P51: git repo-root basename, else cwd basename.

    git may be absent entirely (headless CI is one such environment), which is
    the same answer as "not a checkout" — fall down the chain, never crash.
    """
    import subprocess
    try:
        proc = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return os.path.basename(proc.stdout.strip())
    except OSError:
        pass
    return os.path.basename(os.path.abspath(cwd)) or "~"


# ---------------------------------------------------------------- workspaces

def _focused_workspace(host: str | None = None) -> dict | None:
    workspaces = herdrc.workspace_list(host)
    for ws in workspaces:
        if ws.get("focused"):
            return ws
    return workspaces[0] if workspaces else None


def _resolve_ws(host: str | None = None) -> str | None:
    """The workspace an in-window verb should join: hk_ws user-var first
    (spec 9.3 — joining creates no workspace), else the focused workspace."""
    if kittyc.available():
        try:
            window = kittyc.current_window()
        except kittyc.KittyError as exc:
            # KITTY_LISTEN_ON set but nobody listening: the window's own answer
            # is unavailable, not wrong. Fall through to the server's view.
            _err(f"kitty unreachable, resolving workspace from the server: {exc}")
            window = None
        if window:
            ws = (window.get("user_vars") or {}).get("hk_ws")
            if ws:
                return ws
    ws = _focused_workspace(host)
    return ws["workspace_id"] if ws else None


def _stamp(pane: dict, role: str, host: str | None = None) -> None:
    """Both directions of the join, one call each (spec R2, D16).

    kitty side: user-vars on the current window; herdr side: metadata tokens
    under source user:hk, ttl_ms and seq omitted, re-stamped on every attach.
    """
    pane_id = pane["pane_id"]
    tokens = {"hk_role": role}
    win_id = kittyc.window_id()
    sock = kittyc.listen_on()
    if win_id:
        tokens["kitty_win"] = win_id
    if sock:
        tokens["kitty_sock"] = sock[:80]  # token value cap (census P01)
    herdrc.report_metadata(pane_id, tokens=tokens, host=host)
    if not win_id:
        return
    # The herdr side is the durable half of the join and it is already written.
    # A kitty instance we cannot reach degrades the surface tier only, so it is
    # a warning, never a failed verb (headless CI runs entirely in this state).
    try:
        kittyc.set_user_vars(win_id, hk_pane=pane_id,
                             hk_ws=pane["workspace_id"], hk_role=role)
    except kittyc.KittyError as exc:
        _err(f"herdr-side join stamped; kitty user-vars not set: {exc}")


# -------------------------------------------------------------------- verbs

def cmd_open(args) -> int:
    """spec 3.1 / G15: get-or-create pane in this window's hk_ws, exec attach."""
    host = getattr(args, "host", None)
    try:
        ws_id = _resolve_ws(host)
        if ws_id is None:
            created = herdrc.workspace_create(cwd=os.getcwd(), host=host)
            pane = created["root_pane"]
        else:
            panes = herdrc.pane_list(workspace=ws_id, host=host)
            # `pane list` already carries tokens and label (verified live against
            # 0.8.2), so the get-or-create decision costs no extra round trip.
            unclaimed = [p for p in panes
                         if not (p.get("tokens") or {}).get("kitty_win")]
            if unclaimed:
                pane = unclaimed[0]
            else:
                anchor = panes[0]["pane_id"] if panes else None
                pane = herdrc.pane_split(pane_id=anchor, direction="down", host=host)
        _stamp(pane, role="herdr", host=host)
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    except kittyc.KittyError as exc:
        _err(str(exc))
        return EXIT_HERDR_ERROR
    if getattr(args, "print_only", False):
        print(pane["pane_id"])
        return EXIT_OK
    herdrc.exec_attach(pane["terminal_id"])  # never returns
    return EXIT_OK


def cmd_run(args) -> int:
    """spec 3.3 / G3: trampoline pane; payload exit closes the pane."""
    host = getattr(args, "host", None)
    argv = list(args.argv or [])
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        _err("usage: hk run -- <argv...>")
        return EXIT_USAGE
    try:
        ws_id = _resolve_ws(host)
        panes = herdrc.pane_list(workspace=ws_id, host=host) if ws_id else []
        anchor = panes[0]["pane_id"] if panes else None
        pane = herdrc.pane_split(pane_id=anchor, direction="down",
                                 env={"HK_EXEC": encode_trampoline(argv)}, host=host)
        print(pane["pane_id"])
        return EXIT_OK
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)


def _frame(text: str) -> str:
    return f"\x1b[200~{text}\x1b[201~"


def cmd_send(args) -> int:
    """spec 4.1/4.2 (G4, G6): stdin -> bracketed send-text; --submit -> agent prompt."""
    host = getattr(args, "host", None)
    text = sys.stdin.read()
    try:
        if args.submit:
            herdrc.agent_prompt(args.pane, text, host=host)
        else:
            herdrc.pane_send_text(args.pane, _frame(text), host=host)
        return EXIT_OK
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)


def cmd_read(args) -> int:
    """spec 6.1 (G7): recent-unwrapped ansi read; cap notice on stderr."""
    host = getattr(args, "host", None)
    requested = args.lines
    try:
        out = herdrc.pane_read(args.pane, lines=requested,
                               fmt="ansi" if not args.text else "text", host=host)
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    sys.stdout.write(out)
    returned = out.count("\n")
    # herdr emits no cap notice of its own (probe surprise 4) — it is hk's
    # obligation (spec 6.1). Fires both when the ask exceeded the cap and when
    # the answer came back at it with no --lines given.
    if (requested is not None and requested > READ_CAP) or returned >= READ_CAP:
        print(f"hk read: herdr caps pane reads at {READ_CAP} lines "
              f"(requested {requested if requested is not None else 'default'}, "
              f"got {returned}); use the pane's own prefix+e for uncapped "
              f"scrollback (spec 6.1, census-map P21)", file=sys.stderr)
    return EXIT_OK


def cmd_rename(args) -> int:
    """spec 7.1 (G5): three tiers in one verb; plugin-labelled panes skipped."""
    host = getattr(args, "host", None)
    label = " ".join(args.label)
    try:
        pane = herdrc.pane_get(args.pane, host=host)
        if plugin_owned(pane.get("label")):
            _err(f"pane {args.pane} is plugin-labelled ({pane.get('label')!r}); not touching it (spec 7.5)")
            return EXIT_OK
        herdrc.pane_rename(args.pane, label, host=host)            # durable tier
        herdrc.report_metadata(args.pane, title=label, host=host)  # live tier
        win = pane.get("tokens", {}).get("kitty_win")
        if win and kittyc.available():                              # surface tier
            kittyc.set_window_title(label, win_id=win)
        return EXIT_OK
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    except kittyc.KittyError as exc:
        _err(f"durable+live tiers renamed; kitty surface tier failed: {exc}")
        return EXIT_OK


def cmd_focus(args) -> int:
    """spec 3.6 / D6: kitty_win token -> kitty focus-window; absent -> nonzero."""
    host = getattr(args, "host", None)
    try:
        pane = herdrc.pane_get(args.pane, host=host)
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    win = pane.get("tokens", {}).get("kitty_win")
    if not win:
        _err(f"pane {args.pane} has no live kitty_win token")
        return EXIT_HERDR_ERROR
    try:
        kittyc.focus_window(win)
        return EXIT_OK
    except kittyc.KittyError as exc:
        _err(str(exc))
        return EXIT_HERDR_ERROR


def window_class(workspace_id: str) -> str:
    """The Wayland app-id kitty stamps on a materialised window. It is the
    handle the compositor adapter matches on, and the only thing this repo asks
    a window manager to know about it."""
    return f"hk-ws-{workspace_id}"


def cmd_materialise(args) -> int:
    """spec 3.4 (G9): one kitty OS window per pane, attach by terminal_id,
    zero geometry replay. niri adapter ONLY behind NIRI_SOCKET (spec 9.7, F.11)."""
    host = getattr(args, "host", None)
    if not kittyc.available():
        _err("materialise needs a kitty instance (KITTY_LISTEN_ON unset)")
        return EXIT_HERDR_ERROR
    try:
        ws = args.workspace
        panes = herdrc.pane_list(workspace=ws, host=host)
        if not panes:
            _err(f"workspace {ws} has no panes")
            return EXIT_HERDR_ERROR
        sock = kittyc.listen_on()
        for pane in panes:
            win_id = kittyc.launch_os_window(
                ["herdr", "terminal", "attach", pane["terminal_id"]],
                user_vars={"hk_pane": pane["pane_id"], "hk_ws": pane["workspace_id"],
                           "hk_role": "herdr"},
                window_class=window_class(ws),
                env={"HERDR_SOCKET_PATH": os.environ.get("HERDR_SOCKET_PATH", "")}
                    if os.environ.get("HERDR_SOCKET_PATH") else None,
            )
            herdrc.report_metadata(pane["pane_id"],
                                   tokens={"kitty_win": win_id,
                                           "kitty_sock": (sock or "")[:80],
                                           "hk_role": "herdr"}, host=host)
        print(f"materialised {len(panes)} pane(s) of {ws}; geometry not replayed")
        _niri_adopt(window_class(ws))
        return EXIT_OK
    except (herdrc.HerdrError, kittyc.KittyError) as exc:
        _err(str(exc))
        return EXIT_HERDR_ERROR


def _niri_adopt(app_id: str) -> None:
    """spec 9.7 / D15 / F.11: move the windows just materialised to the focused
    niri workspace — and ONLY when NIRI_SOCKET says niri is the compositor.
    Absent, this makes zero compositor calls and the repo depends on no
    compositor at all.

    Matching is by the app-id we stamped, never by focus, so nothing is stolen
    from a window the user is actually using. Enumeration happens once: a
    surface kitty has not mapped yet is reported as not-yet-adopted rather than
    slept on (spec F.6 forbids polling in an interactive path).
    """
    if not os.environ.get("NIRI_SOCKET"):
        return
    import json
    import subprocess

    def niri(*argv):
        return subprocess.run(["niri", "msg", *argv], capture_output=True, text=True)

    try:
        workspaces = json.loads(niri("-j", "workspaces").stdout or "[]")
        windows = json.loads(niri("-j", "windows").stdout or "[]")
    except (OSError, ValueError) as exc:
        _err(f"NIRI_SOCKET is set but niri did not answer; windows left where they are: {exc}")
        return

    focused = next((ws for ws in workspaces if ws.get("is_focused")), None)
    if focused is None:
        _err("niri reports no focused workspace; windows left where they are")
        return

    mine = [w for w in windows if w.get("app_id") == app_id]
    for window in mine:
        # --focus false: adopting a window must never yank the user's focus
        niri("action", "move-window-to-workspace", "--window-id", str(window["id"]),
             "--focus", "false", str(focused["idx"]))
    print(f"niri: adopted {len(mine)} window(s) onto workspace {focused['idx']}")


def cmd_dematerialise(args) -> int:
    """spec 3.5 (G9): close the projecting kitty windows; every pane survives.

    Enumeration is herdr-side (census-map P12): the workspace is the object
    being named, and `pane list` already carries the tokens. Tokens die with
    the server (D16), so a token whose window is gone is expected, not an
    error — it is cleared, because a stale kitty_win would misroute `hk focus`.
    """
    host = getattr(args, "host", None)
    try:
        panes = herdrc.pane_list(workspace=args.workspace, host=host)
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    if not panes:
        _err(f"workspace {args.workspace} has no panes")
        return EXIT_HERDR_ERROR
    closed = stale = 0
    for pane in panes:
        win = (pane.get("tokens") or {}).get("kitty_win")
        if not win:
            continue
        if kittyc.available():
            try:
                kittyc.close_window(win)
                closed += 1
            except kittyc.KittyError:
                stale += 1
        else:
            stale += 1
        try:
            herdrc.clear_tokens(pane["pane_id"], ["kitty_win", "kitty_sock"], host=host)
        except herdrc.HerdrError as exc:
            return _herdr_fail(exc)
    print(f"dematerialised {closed} window(s)"
          + (f", {stale} stale token(s) cleared" if stale else "")
          + f"; {len(panes)} pane(s) untouched")
    return EXIT_OK


def cmd_new(args) -> int:
    """spec 9.1/9.2 (G17): workspace create + root pane + kitty OS window."""
    host = getattr(args, "host", None)
    cwd = os.getcwd()
    label = args.label
    if not label:
        label = default_label(cwd)
    try:
        created = herdrc.workspace_create(cwd=cwd, label=label, host=host)
        pane = created["root_pane"]
        print(pane["workspace_id"], pane["pane_id"])
        if kittyc.available() and not getattr(args, "no_window", False):
            win_id = kittyc.launch_os_window(
                ["herdr", "terminal", "attach", pane["terminal_id"]],
                user_vars={"hk_pane": pane["pane_id"], "hk_ws": pane["workspace_id"],
                           "hk_role": "herdr"},
                env={"HERDR_SOCKET_PATH": os.environ.get("HERDR_SOCKET_PATH", "")}
                    if os.environ.get("HERDR_SOCKET_PATH") else None,
            )
            herdrc.report_metadata(pane["pane_id"],
                                   tokens={"kitty_win": win_id,
                                           "kitty_sock": (kittyc.listen_on() or "")[:80],
                                           "hk_role": "herdr"}, host=host)
        return EXIT_OK
    except (herdrc.HerdrError, kittyc.KittyError) as exc:
        _err(str(exc))
        return EXIT_HERDR_ERROR


def cmd_ws(args) -> int:
    """spec R9: hk ws list|new|focus|rename."""
    host = getattr(args, "host", None)
    try:
        if args.ws_verb == "list":
            for ws in herdrc.workspace_list(host):
                print(f"{ws['number']}\t{ws['workspace_id']}\t{ws.get('label') or ''}"
                      f"\t{'focused' if ws.get('focused') else ''}")
            return EXIT_OK
        if args.ws_verb == "new":
            created = herdrc.workspace_create(cwd=os.getcwd(),
                                              label=args.arg or None, host=host)
            print(created["workspace"]["workspace_id"])
            return EXIT_OK
        if args.ws_verb == "focus":
            # spec 9.5 / D15: the number IS the join
            number = int(args.arg)
            for ws in herdrc.workspace_list(host):
                if ws.get("number") == number:
                    herdrc.call(["workspace", "focus", ws["workspace_id"]], host)
                    return EXIT_OK
            _err(f"no workspace with number {number}")
            return EXIT_HERDR_ERROR
        if args.ws_verb == "rename":
            ws_id, label = args.arg, " ".join(args.rest or [])
            if not label:
                _err("usage: hk ws rename <ws> <label>")
                return EXIT_USAGE
            herdrc.call(["workspace", "rename", ws_id, label], host)
            # fan-out (spec 7.3): re-title every kitty window whose hk_ws matches
            if kittyc.available():
                for window in kittyc.windows():
                    if (window.get("user_vars") or {}).get("hk_ws") == ws_id:
                        kittyc.set_window_title(label, win_id=str(window["id"]))
            return EXIT_OK
        _err(f"unknown ws verb {args.ws_verb!r}")
        return EXIT_USAGE
    except (herdrc.HerdrError, ValueError) as exc:
        if isinstance(exc, herdrc.HerdrError):
            return _herdr_fail(exc)
        _err(str(exc))
        return EXIT_USAGE
    except kittyc.KittyError as exc:
        _err(f"herdr side done; kitty fan-out failed: {exc}")
        return EXIT_OK


def resume_rows(panes: list[dict]) -> list[tuple[str, str, str]]:
    """spec 10.1 (G16): rows of terminal_id, label, agent_status; hk_role=fork
    panes filtered out (census-map P57 — a fork pane is a delivery buffer, not
    a session to come back to). Pure over `pane list` output, which already
    carries tokens and label, so this unit-tests without a server.
    """
    rows = []
    for pane in panes:
        if (pane.get("tokens") or {}).get("hk_role") == "fork":
            continue
        rows.append((pane["terminal_id"],
                     pane.get("label") or pane.get("terminal_title_stripped") or "",
                     pane.get("agent_status", "unknown")))
    return rows


def cmd_resume(args) -> int:
    """spec 10.1/10.2 (G16): picker over panes; attach by terminal_id."""
    host = getattr(args, "host", None)
    try:
        rows = resume_rows(herdrc.pane_list(host=host))
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)
    if args.attach:
        for terminal_id, _, _ in rows:
            if terminal_id == args.attach:
                herdrc.exec_attach(terminal_id)  # never returns
        _err(f"terminal {args.attach} not found (or filtered)")
        return EXIT_HERDR_ERROR
    if args.print_only or not sys.stdin.isatty():
        for row in rows:
            print("\t".join(row))
        return EXIT_OK
    if not rows:
        _err("nothing to resume")
        return EXIT_OK
    # fzf if present, else a numbered menu (spec R10.1)
    import shutil
    import subprocess
    if shutil.which("fzf"):
        lines = "\n".join("\t".join(row) for row in rows)
        proc = subprocess.run(["fzf", "--with-nth=2,3", "--delimiter=\t"],
                              input=lines, capture_output=True, text=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            return EXIT_OK
        herdrc.exec_attach(proc.stdout.split("\t", 1)[0].strip())
    else:
        for index, row in enumerate(rows, 1):
            print(f"{index}) {row[1] or row[0]} [{row[2]}]")
        choice = input("resume> ").strip()
        if not choice.isdigit() or not 1 <= int(choice) <= len(rows):
            return EXIT_USAGE
        herdrc.exec_attach(rows[int(choice) - 1][0])
    return EXIT_OK


AGENT_SLUG_RE = r"^[a-z][a-z0-9_-]{0,31}$"


def cmd_agent(args) -> int:
    """spec 7.6 / D23: slug-validating pass-through; no gesture binds it."""
    import re
    host = getattr(args, "host", None)
    if args.agent_verb != "rename":
        _err("usage: hk agent rename <target> <slug>")
        return EXIT_USAGE
    if not re.match(AGENT_SLUG_RE, args.name):
        _err(f"invalid agent slug {args.name!r} (want {AGENT_SLUG_RE}); refusing locally")
        return EXIT_USAGE
    try:
        herdrc.agent_rename(args.target, args.name, host=host)
        return EXIT_OK
    except herdrc.HerdrError as exc:
        return _herdr_fail(exc)


def cmd_config(_args) -> int:
    cfg = hk_config.load()
    print(f"# {hk_config.config_path()}"
          f" ({'present' if os.path.exists(hk_config.config_path()) else 'absent — defaults'})")
    for key, value in sorted(cfg.items()):
        print(f"{key} = {value!r}")
    return EXIT_OK
