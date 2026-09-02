"""herdr client wrapper — every herdr interaction in hk goes through here.

Two transports, one module (spec F.5):

* **the unix socket** — NDJSON request/response against the herdr server. This
  is the delivery path for anything carrying a payload, because the payload
  stops being an argv element (see ARGV_LIMIT below) and because it is the only
  way to reach socket-only methods: `pane.send_input` has NO CLI verb at all,
  which is precisely why hk used to hand-frame bracketed paste itself.
* **the `herdr` binary** — for everything else, and for `--host`, where the
  invocation rides `ssh <host>` (spec 4.3). kitty calls never do.

Both parse the same envelopes: {"id","result"} | {"id","error"}.

MEASURED LIMITS (binary-searched live against herdr 0.8.2 / protocol 21;
re-run them with tests/unit/test_send_path.py if either number is doubted):

  ARGV_LIMIT           131072  — passing a payload as argv raises
                                 OSError(E2BIG) at exactly this length.
                                 131071 bytes go through; 131072 does not.
                                 This is Linux MAX_ARG_STRLEN (32 pages), not
                                 a herdr limit, and it is BUG-5.
  SOCKET_REQUEST_LIMIT 1048576  — the server accepts a request line up to
                                 1 MiB and RESETS THE CONNECTION above it.
                                 Measured: 1048492 payload bytes accepted,
                                 1048493 -> ConnectionResetError, the ~84-byte
                                 difference being the JSON envelope.

The second number matters: a literal 1 MiB payload does NOT fit in one call
once the envelope is added, so payloads are chunked across successive calls
rather than hand-framed into one oversized request.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys

# See the module docstring: both were measured, neither is a guess.
ARGV_LIMIT = 131072
SOCKET_REQUEST_LIMIT = 1048576

# Bracketed-paste terminator. hk never WRITES this (herdr owns framing); it is
# here so framed payloads can be scrubbed of a hostile copy (BUG-9).
PASTE_END = "\x1b[201~"
PASTE_START = "\x1b[200~"


class HerdrError(RuntimeError):
    """A herdr-side error envelope or nonzero exit."""

    def __init__(self, message: str, code: str = "herdr_error", stderr: str = ""):
        super().__init__(message)
        self.code = code
        self.stderr = stderr


# ---- the socket transport --------------------------------------------------

def socket_path() -> str:
    """Where the herdr server listens.

    HERDR_SOCKET_PATH wins (the smoke sandbox sets it); otherwise the documented
    default under the config home.
    """
    override = os.environ.get("HERDR_SOCKET_PATH")
    if override:
        return override
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "herdr", "herdr.sock")


def socket_available() -> bool:
    """True when a socket call has any chance of landing."""
    try:
        import stat
        return stat.S_ISSOCK(os.stat(socket_path()).st_mode)
    except OSError:
        return False


def socket_call(method: str, params: dict, timeout: float = 30.0) -> dict:
    """One NDJSON request/response against the herdr server.

    Returns the parsed `result` object. Raises HerdrError — never a bare
    OSError and never a traceback — for every failure mode, so callers have
    exactly one exception type to handle.
    """
    request = json.dumps({"id": f"hk:{method}", "method": method, "params": params})
    encoded = (request + "\n").encode()
    if len(encoded) > SOCKET_REQUEST_LIMIT:
        raise HerdrError(
            f"request too large for the herdr socket: {len(encoded)} bytes "
            f"exceeds the {SOCKET_REQUEST_LIMIT}-byte request limit "
            f"(the server resets the connection above it)",
            code="request_too_large")
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.settimeout(timeout)
        conn.connect(socket_path())
        conn.sendall(encoded)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                raise HerdrError(
                    f"herdr closed the connection without answering {method}",
                    code="connection_closed")
            buf += chunk
    except socket.timeout as exc:
        raise HerdrError(f"herdr socket timed out after {timeout}s on {method}",
                         code="timeout") from exc
    except ConnectionResetError as exc:
        raise HerdrError(
            f"herdr reset the connection on {method} "
            f"(request was {len(encoded)} bytes; the server's limit is "
            f"{SOCKET_REQUEST_LIMIT})", code="connection_reset") from exc
    except OSError as exc:
        raise HerdrError(f"cannot reach the herdr socket at {socket_path()}: {exc}",
                         code="socket_unavailable") from exc
    finally:
        conn.close()

    try:
        envelope = json.loads(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
    except ValueError as exc:
        raise HerdrError(f"herdr sent an unparseable answer to {method}: {exc}",
                         code="bad_envelope") from exc
    if "error" in envelope:
        error = envelope["error"] or {}
        # verbatim propagation: agent_blocked and friends are real signals
        raise HerdrError(error.get("message", "herdr error"),
                         code=error.get("code", "herdr_error"))
    return envelope.get("result", {}) or {}


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
    """Literal bytes, no framing. Byte-transparent by contract (T1/T19)."""
    _deliver(pane_id, text, host=host, framed=False)


def pane_send_input(pane_id: str, text: str, host: str | None = None) -> None:
    """Text as INPUT — herdr applies bracketed-paste framing iff the pane's
    runtime enabled it (T4). This is the fix for BUG-8.

    Receipt, live against herdr 0.8.2 into a pane running `cat -v` (a program
    that does NOT enable bracketed paste):

        pane.send_input "HELLO-INPUT"                  -> pane shows HELLO-INPUT
        pane.send_text  "\x1b[200~HAND-FRAMED\x1b[201~" -> pane shows
                                                          ^[[200~HAND-FRAMED^[[201~

    The second line is what hk did to every send before round2-04: literal
    escape junk typed into anything that is not a bracketed-paste-aware reader.
    """
    _deliver(pane_id, text, host=host, framed=True)


def sanitise_framed(text: str) -> tuple[str, int]:
    """Strip bracketed-paste terminators from a payload bound for a framed path.

    BUG-9: a payload containing \x1b[201~ closes the paste bracket early, and
    everything after it is delivered as ordinary TYPED input — newlines
    included. That breaks the advertised "populate, never submit" guarantee
    with nothing more than a crafted string in the clipboard. Framed paths
    scrub it; `hk send --raw` is byte-transparent by contract and exempt.

    Returns (clean_text, number_of_terminators_removed).
    """
    if PASTE_END not in text:
        return text, 0
    return text.replace(PASTE_END, ""), text.count(PASTE_END)


def _chunks(pane_id: str, method: str, text: str) -> list[str]:
    """Split text so every resulting request fits under SOCKET_REQUEST_LIMIT.

    Chunking is done on the SERIALISED length, not the character count: JSON
    escaping expands control characters up to sixfold, so a character-count
    budget would still overflow on control-heavy payloads. Splitting halves
    recursively costs at most a few extra serialisations and is exact.

    Successive `pane.send_input` calls are safe to concatenate: each is framed
    independently by herdr, and adjacent bracketed-paste regions insert as one
    run of text in every reader. No hand-framing is reintroduced.
    """
    def fits(part: str) -> bool:
        request = json.dumps({"id": f"hk:{method}", "method": method,
                              "params": {"pane_id": pane_id, "text": part}})
        return len(request.encode()) + 1 <= SOCKET_REQUEST_LIMIT

    out: list[str] = []
    pending = [text]
    while pending:
        part = pending.pop(0)
        if not part or fits(part):
            if part:
                out.append(part)
            continue
        if len(part) == 1:
            raise HerdrError(
                "a single character does not fit in a herdr socket request; "
                "the server limit is unusually low", code="request_too_large")
        mid = len(part) // 2
        pending[0:0] = [part[:mid], part[mid:]]
    return out


def _deliver(pane_id: str, text: str, host: str | None, framed: bool) -> None:
    """The ONE delivery implementation. `hk send` and `hk voice text` share it.

    Local: the socket, chunked, with herdr owning framing (framed=True) or with
    literal bytes (framed=False).
    Remote (`--host`): there is no socket to reach, so the payload rides argv
    through ssh and inherits the ARGV_LIMIT ceiling, which the error names.
    """
    if host is None and socket_available():
        method = "pane.send_input" if framed else "pane.send_text"
        for part in _chunks(pane_id, method, text):
            socket_call(method, {"pane_id": pane_id, "text": part})
        return

    # --- the argv tier -----------------------------------------------------
    payload = f"{PASTE_START}{text}{PASTE_END}" if framed else text
    if len(payload.encode()) >= ARGV_LIMIT:
        where = f"over ssh to {host}" if host else "through the herdr binary"
        raise HerdrError(
            f"payload is {len(payload.encode())} bytes: too large to send "
            f"{where}, where it must travel as a command-line argument "
            f"(the kernel's limit is {ARGV_LIMIT} bytes per argument). "
            + ("Run hk on that host instead, where the local socket carries it."
               if host else
               "Start the herdr server so hk can use the local socket, which "
               "carries far larger payloads."),
            code="payload_too_large")
    call(["pane", "send-text", pane_id, payload], host)


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
    """Submit a prompt to an agent.

    Rides the socket locally for the same reason send does: the prompt text is
    a payload, and as argv it dies at ARGV_LIMIT. Error codes propagate
    verbatim either way — `agent_blocked` is a real signal, not a failure to
    smooth over (spec 4.2).
    """
    if host is None and socket_available():
        socket_call("agent.prompt", {"target": target, "text": text})
        return
    if len(text.encode()) >= ARGV_LIMIT:
        raise HerdrError(
            f"prompt is {len(text.encode())} bytes: too large to send as a "
            f"command-line argument (kernel limit {ARGV_LIMIT}); the local "
            f"herdr socket carries it, so run hk on that host",
            code="payload_too_large")
    call(["agent", "prompt", target, text], host)


def agent_rename(target: str, label: str, host: str | None = None) -> None:
    call(["agent", "rename", target, label], host)


def exec_attach(terminal_id: str) -> None:
    """Replace this process with `herdr terminal attach` (spec 3.1)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp("herdr", ["herdr", "terminal", "attach", terminal_id])
