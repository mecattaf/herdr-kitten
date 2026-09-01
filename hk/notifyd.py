"""hk notifyd — the repo's ONE event loop (spec R8, D4, D26; census P39/P52/P53).

One long-lived process; exactly ONE events.subscribe call site in the whole
repo (spec 8.5, unit-enforced). Design follows docs/probe-report.md surprises:

* `pane.agent_status_changed` subscriptions are PER-PANE (pane_id required) and
  the server reads a single request line per connection — so notifyd
  (re)connects with a fresh subscription list whenever the pane set changes,
  driven by the global pane.created/pane.closed/pane.exited events.
* Reactions: (a) blocked/done -> run notify_command once per transition;
  (b) mirror agent status into the projecting kitty window's `hk_status`
  user-var, resolved through the kitty_win/kitty_sock metadata tokens;
  (c) mirror editor self-reports (hk_role=editor token) to the window user-var.
* Reconnect with bounded backoff on socket loss (a background path — the
  no-polling law binds interactive paths, spec F.6).
* NEVER changes window focus (spec 8.4, F.7): the only kitty verb used is
  set-user-vars.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

from hk import config as hk_config
from hk import herdrc

NOTIFY_STATES = {"blocked", "done"}
BACKOFF_START = 0.5
BACKOFF_MAX = 15.0


def socket_path() -> str:
    override = os.environ.get("HERDR_SOCKET_PATH")
    if override:
        return override
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "herdr", "herdr.sock")


def subscriptions(pane_ids: list[str]) -> list[dict]:
    subs: list[dict] = [{"type": "pane.created"}, {"type": "pane.closed"},
                        {"type": "pane.exited"}, {"type": "pane.updated"}]
    subs.extend({"type": "pane.agent_status_changed", "pane_id": pid}
                for pid in pane_ids)
    return subs


def should_notify(prev: str | None, new: str | None) -> bool:
    """Once per TRANSITION into blocked/done (spec 8.2)."""
    return new in NOTIFY_STATES and prev != new


class Notifyd:
    def __init__(self, notify_command: str | None = None):
        cfg = hk_config.load()
        self.notify_command = notify_command or str(cfg.get("notify_command", "notify-send"))
        self.status: dict[str, str] = {}
        self.roles: dict[str, str] = {}

    # ---- side effects (overridable in tests) -------------------------------
    def run_notify(self, pane_id: str, state: str, agent: str | None) -> None:
        cmd = self.notify_command.split() + [f"herdr: {agent or pane_id} {state}"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_user_var(self, pane_id: str, key: str, value: str) -> None:
        try:
            pane = herdrc.pane_get(pane_id)
        except herdrc.HerdrError:
            return
        tokens = pane.get("tokens", {})
        win, sock = tokens.get("kitty_win"), tokens.get("kitty_sock")
        if not win or not sock:
            return
        subprocess.run(["kitty", "@", "--to", sock, "set-user-vars",
                        "--match", f"id:{win}", f"{key}={value}"],
                       capture_output=True)

    # ---- event handling ----------------------------------------------------
    def handle(self, envelope: dict) -> bool:
        """Returns True when the pane set changed (resubscribe needed)."""
        event = envelope.get("event", "")
        data = envelope.get("data", {}) or {}
        pane_id = data.get("pane_id", "")
        if event in ("pane.created", "pane.closed", "pane.exited"):
            self.status.pop(pane_id, None)
            return True
        if event == "pane.agent_status_changed":
            new = data.get("agent_status")
            prev = self.status.get(pane_id)
            if should_notify(prev, new):
                self.run_notify(pane_id, str(new), data.get("agent"))
            if new is not None and new != prev:
                self.status[pane_id] = str(new)
                self.set_user_var(pane_id, "hk_status", str(new))
            return False
        if event == "pane.updated":
            # editor self-report mirror (spec 2.6): hk_role token -> user-var
            role = (data.get("tokens") or {}).get("hk_role")
            if role and self.roles.get(pane_id) != role:
                self.roles[pane_id] = role
                self.set_user_var(pane_id, "hk_role", role)
            return False
        return False

    # ---- the loop ----------------------------------------------------------
    def run(self) -> int:
        backoff = BACKOFF_START
        while True:
            try:
                pane_ids = [p["pane_id"] for p in herdrc.pane_list()]
                conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.connect(socket_path())
                request = {"id": "hk:notifyd", "method": "events.subscribe",
                           "params": {"subscriptions": subscriptions(pane_ids)}}
                # THE one events.subscribe call site (spec 8.5)
                conn.sendall((json.dumps(request) + "\n").encode())
                backoff = BACKOFF_START
                buf = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        raise ConnectionError("event socket closed")
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        envelope = json.loads(line)
                        if "result" in envelope or "error" in envelope:
                            if "error" in envelope:
                                raise ConnectionError(str(envelope["error"]))
                            continue
                        if self.handle(envelope):
                            raise _Resubscribe()
            except _Resubscribe:
                continue
            except (OSError, ConnectionError, herdrc.HerdrError, json.JSONDecodeError) as exc:
                print(f"hk notifyd: {exc}; reconnecting in {backoff:.1f}s", file=sys.stderr)
                time.sleep(backoff)  # background path; bounded backoff
                backoff = min(backoff * 2, BACKOFF_MAX)


class _Resubscribe(Exception):
    pass


def main() -> int:
    return Notifyd().run()
