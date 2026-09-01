"""herdr client wrapper — every herdr interaction in hk goes through here.

CLI-and-socket only (spec F.5): we shell out to the `herdr` binary and parse
its JSON envelopes ({"id","result"} | {"id","error"} — census-surface). With
host set, the herdr invocation runs over `ssh <host>` (spec 4.3); kitty calls
never do.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys


class HerdrError(RuntimeError):
    """A herdr-side error envelope or nonzero exit."""

    def __init__(self, message: str, code: str = "herdr_error", stderr: str = ""):
        super().__init__(message)
        self.code = code
        self.stderr = stderr


def _argv(args: list[str], host: str | None) -> list[str]:
    if host:
        # remote tier: the herdr call rides ssh; quoting is simple because every
        # arg we pass is id/label/flag shaped. Text payloads go via stdin-safe
        # single args and are quoted here.
        import shlex
        return ["ssh", host, " ".join(shlex.quote(a) for a in ["herdr", *args])]
    return ["herdr", *args]


def run(args: list[str], host: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(_argv(args, host), capture_output=True, text=True)
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        code = "herdr_error"
        try:
            envelope = json.loads(message.splitlines()[-1]) if message else {}
            code = envelope.get("error", {}).get("code", code)
        except (ValueError, IndexError):
            pass
        raise HerdrError(message or f"herdr {' '.join(args)} failed", code=code, stderr=proc.stderr)
    return proc


def call(args: list[str], host: str | None = None) -> dict:
    """Run a herdr CLI verb and return the parsed `result` object."""
    proc = run(args, host=host)
    if not proc.stdout.strip():
        # verbs like report-metadata/rename answer with an empty Ok
        return {}
    envelope = json.loads(proc.stdout)
    if "error" in envelope:
        raise HerdrError(envelope["error"].get("message", "herdr error"),
                         code=envelope["error"].get("code", "herdr_error"))
    return envelope.get("result", {})


# ---- typed helpers (thin; the census is the contract) ----------------------

def workspace_list(host: str | None = None) -> list[dict]:
    return call(["workspace", "list"], host)["workspaces"]


def workspace_create(cwd: str | None = None, label: str | None = None,
                     host: str | None = None) -> dict:
    args = ["workspace", "create"]
    if cwd:
        args += ["--cwd", cwd]
    if label:
        args += ["--label", label]
    return call(args, host)


def pane_list(workspace: str | None = None, host: str | None = None) -> list[dict]:
    args = ["pane", "list"]
    if workspace:
        args += ["--workspace", workspace]
    return call(args, host)["panes"]


def pane_get(pane_id: str, host: str | None = None) -> dict:
    return call(["pane", "get", pane_id], host)["pane"]


def pane_split(pane_id: str | None = None, direction: str | None = None,
               cwd: str | None = None, env: dict[str, str] | None = None,
               focus: bool = False, host: str | None = None) -> dict:
    args = ["pane", "split"]
    if pane_id:
        args += ["--pane", pane_id]
    if direction:
        args += ["--direction", direction]
    if cwd:
        args += ["--cwd", cwd]
    for key, value in (env or {}).items():
        args += ["--env", f"{key}={value}"]
    if focus:
        args += ["--focus"]
    return call(args, host)["pane"]


def pane_send_text(pane_id: str, text: str, host: str | None = None) -> None:
    call(["pane", "send-text", pane_id, text], host)


def pane_read(pane_id: str, source: str = "recent-unwrapped", lines: int | None = None,
              fmt: str = "ansi", host: str | None = None) -> str:
    args = ["pane", "read", pane_id, "--source", source, "--format", fmt]
    if lines is not None:
        args += ["--lines", str(lines)]
    # pane read prints raw content, not a JSON envelope
    return run(args, host=host).stdout


def pane_rename(pane_id: str, label: str, host: str | None = None) -> None:
    call(["pane", "rename", pane_id, label], host)


def pane_close(pane_id: str, host: str | None = None) -> None:
    call(["pane", "close", pane_id], host)


def report_metadata(pane_id: str, source: str = "user:hk",
                    tokens: dict[str, str] | None = None, title: str | None = None,
                    host: str | None = None) -> None:
    # spec D16: source user:hk, ttl_ms omitted, seq omitted — always.
    args = ["pane", "report-metadata", pane_id, "--source", source]
    for key, value in (tokens or {}).items():
        args += ["--token", f"{key}={value}"]
    if title is not None:
        args += ["--title", title]
    call(args, host)


def clear_tokens(pane_id: str, names: list[str], source: str = "user:hk",
                 host: str | None = None) -> None:
    """Drop metadata tokens this source owns (spec 3.5: a dematerialised pane
    must not keep a kitty_win that no longer resolves)."""
    args = ["pane", "report-metadata", pane_id, "--source", source]
    for name in names:
        args += ["--clear-token", name]
    call(args, host)


def agent_prompt(target: str, text: str, host: str | None = None) -> None:
    call(["agent", "prompt", target, text], host)


def agent_rename(target: str, label: str, host: str | None = None) -> None:
    call(["agent", "rename", target, label], host)


def exec_attach(terminal_id: str) -> None:
    """Replace this process with `herdr terminal attach` (spec 3.1)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp("herdr", ["herdr", "terminal", "attach", terminal_id])
