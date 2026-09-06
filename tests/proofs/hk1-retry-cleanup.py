#!/usr/bin/env python3
"""tests/proofs/hk1-retry-cleanup.py — DEFECT 2's teeth, rerunnable, LIVE.

Card HK-1 (herdr-kitten #36 / tally.nix #670): `hk lane start` must either
produce a lane that can be addressed, or leave nothing behind.

THE DEFECT THIS PROBE EXISTS FOR (evaluator receipt, verbatim):
  "hk/lane.py:243-249 splits the worker pane before stamping its hk_lane token
   and renaming it, but cleanup exists only in the later readiness-timeout
   branch. MEASURED evaluator probe argv `PYTHONPATH=. python3
   tests/proofs/hk1-retry-cleanup.py` returned rc 1 after an injected
   report_metadata HerdrError; output: w1:p3; PROBE FAIL: retry after metadata
   failure left the first worker unaddressable; split=['w1:p2','w1:p3'],
   close_calls=0, remaining=['w1:p2','w1:p3']."

A half-started lane is worse than no lane: the worker is running, no verb can
reach it, and the next `hk lane start` — which resolves the lane by its token and
finds none — splits a SECOND worker.

THE REPAIR
  Every step after the split sits inside one cleanup boundary
  (`hk/lane.py:_claim` -> `_abandon`), and the join is READ BACK before start
  reports 0: a metadata write herdr accepted but never published is the same
  unaddressable-worker state with no exception to catch, so `start` resolves the
  lane by name itself and refuses to claim success for a pane it cannot address.
  The fault is still reported as ONE typed line, with herdr's code verbatim and
  the cleanup disclosed.

WHAT THIS PROBE MEASURES — against a REAL herdr server in a sandbox HOME
  1. `hk lane start` with report_metadata failing once -> rc 1, one typed line,
     the code verbatim, the cleanup disclosed, and NO pane id printed.
  2. `herdr pane list` (the real server) shows the half-started pane is GONE.
  3. `hk lane status` -> rc 3, never rc 0 on a ghost.
  4. retry with the fault spent -> rc 0, and the server holds exactly ONE lane
     pane: the retry did not duplicate the worker.
  5. the retried lane is addressable AND usable: status resolves to the same
     pane, and the canonical payload delivered to it comes back byte-identical —
     all 62 bytes, the worker's own cumulative digest equal to the file's.
  6. `hk lane stop` -> rc 0 and the pane count is back to its baseline.

The ONLY thing simulated is the fault itself: a real server cannot be asked to
fail one call on demand. The split, the metadata write, the close, the delivery
and the read-back are all the real server's, and steps 2-6 drive the real
`bin/hk` as a subprocess, so the rc measured is the rc a caller gets.

  rc 0 = all six held. rc 1 = any one failed, with the measurement printed.
  Reverting the repair makes step 2 fail with the pane still open and step 4
  fail with two lane panes — the evaluator's measurement, reproduced.

USAGE
  python3 tests/proofs/hk1-retry-cleanup.py [--keep]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "supervised-lane"
LANE_TOKEN = "hk_lane"
WAIT_S = 60.0


class Probe(Exception):
    """A step that did not hold; its message is the measurement."""


def say(step: str, detail: str) -> None:
    print(f"  {step}: {detail}")


# ------------------------------------------------------------------ sandbox

def sandbox_env(root: pathlib.Path) -> dict:
    env = dict(os.environ)
    bash = shutil.which("bash")
    if not bash:
        raise Probe("no bash on PATH: the pane shell that sources the trampoline "
                    "cannot be prepared")
    # The pane shell must source hk's trampoline hook, or HK_EXEC is ignored and
    # the lane gets a plain shell instead of the worker (README, Limitations).
    # This is the one line tests/smoke/lib.sh:hk_sandbox_shell writes, and the
    # one line the README asks a user to add to their shell rc.
    (root / ".bashrc").write_text(f'. "{REPO / "assets" / "hk-trampoline.sh"}"\n')
    env.update({
        "HOME": str(root),
        "SHELL": bash,
        "XDG_CONFIG_HOME": str(root / ".config"),
        "XDG_STATE_HOME": str(root / ".state"),
        "XDG_DATA_HOME": str(root / ".data"),
        "XDG_CACHE_HOME": str(root / ".cache"),
        "XDG_RUNTIME_DIR": str(root / "run"),
        "HERDR_SOCKET_PATH": str(root / "herdr.sock"),
        "PATH": f"{REPO / 'bin'}:{env.get('PATH', '')}",
    })
    # the headless half is socket-only by definition: never let a developer's
    # live kitty leak into a probe (the same law tests/smoke/lib.sh enforces)
    for leak in ("KITTY_WINDOW_ID", "KITTY_LISTEN_ON", "KITTY_PID"):
        env.pop(leak, None)
    for path in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME",
                 "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        os.makedirs(env[path], exist_ok=True)
    return env


def herdr(env: dict, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["herdr", *argv], env=env, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise Probe(f"`herdr {' '.join(argv)}` exited {proc.returncode}: "
                    f"{(proc.stderr or proc.stdout).strip()}")
    return proc


def pane_list(env: dict) -> list[dict]:
    out = herdr(env, "pane", "list").stdout.strip()
    return json.loads(out)["result"]["panes"] if out else []


def lane_panes(env: dict) -> list[dict]:
    return [p for p in pane_list(env)
            if (p.get("tokens") or {}).get("hk_role") == "lane"]


def hk(env: dict, *argv: str, stdin: str = "") -> tuple[int, str, str]:
    """The real CLI as a subprocess: the rc measured is the rc a caller gets."""
    proc = subprocess.run([str(REPO / "bin" / "hk"), *argv], env=env, input=stdin,
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


def hk_in_process(argv: list[str]) -> tuple[int, str, str]:
    """bin/hk's own main(), so a fault can be injected into hk's herdr calls.

    The integer returned is the one `sys.exit(main())` exits with, i.e. the same
    rc the subprocess form gives.
    """
    spec = importlib.util.spec_from_loader(
        "bin_hk", importlib.machinery.SourceFileLoader("bin_hk", str(REPO / "bin" / "hk")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = module.main(argv)
    return rc, out.getvalue(), err.getvalue()


# -------------------------------------------------------------------- steps

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true",
                        help="do not delete the sandbox (path printed)")
    args = parser.parse_args()

    if not (FIXTURES / "worker.toml").is_file():
        print(f"PROBE FAIL: no fixtures at {FIXTURES}")
        return 1
    payload = (FIXTURES / "payload.txt").read_bytes()
    want_sha = hashlib.sha256(payload).hexdigest()

    sys.path.insert(0, str(REPO))
    root = pathlib.Path(tempfile.mkdtemp(prefix="hk1-cleanup-"))
    env = sandbox_env(root)
    os.environ.update(env)          # hk's in-process half reads os.environ
    os.chdir(root)                  # the lane's cwd is the sandbox, never the repo

    fixtures = root / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    worker = str(fixtures / "worker.toml")

    server = subprocess.Popen(["herdr", "server"], env=env,
                              stdout=(root / "server.log").open("w"),
                              stderr=subprocess.STDOUT)
    failures = []
    restore = None
    try:
        for _ in range(100):
            try:
                if os.path.exists(env["HERDR_SOCKET_PATH"]):
                    herdr(env, "workspace", "list")
                    break
            except Probe:
                pass
            time.sleep(0.1)
        else:
            raise Probe(f"the herdr server never became ready: "
                        f"{(root / 'server.log').read_text()[-400:]}")

        herdr(env, "workspace", "create", "--cwd", str(root))
        baseline = len(pane_list(env))
        print(f"hk1-retry-cleanup: live herdr {herdr(env, '--version').stdout.strip()} "
              f"in {root}; baseline panes {baseline}")

        # ---- the injected fault: herdr cannot be asked to fail one call ------
        from hk import herdrc
        real_report_metadata = herdrc.report_metadata
        armed = {"left": 1, "pane": None}

        def restore():
            herdrc.report_metadata = real_report_metadata

        def failing_report_metadata(pane_id, *pos, **kw):
            if armed["left"] > 0:
                armed["left"] -= 1
                armed["pane"] = pane_id
                raise herdrc.HerdrError(
                    "metadata write refused (injected by hk1-retry-cleanup)",
                    code="metadata_rejected")
            return real_report_metadata(pane_id, *pos, **kw)

        # ---- 1. a partial start reports one typed line and no pane id -------
        herdrc.report_metadata = failing_report_metadata
        rc, out, err = hk_in_process(["lane", "start", worker])
        say("1 start with report_metadata failing",
            f"rc={rc} stdout={out.strip()!r} stderr={err.strip()[:160]!r}")
        if rc != 1:
            failures.append(f"step 1: rc {rc}, want 1 (exit 1 = refused, §5)")
        if out.strip():
            failures.append(f"step 1: a failed start printed a pane id: {out.strip()!r}")
        if len(err.strip().splitlines()) != 1:
            failures.append(f"step 1: {len(err.strip().splitlines())} stderr lines, want 1")
        if "Traceback" in err:
            failures.append(f"step 1: traceback on stderr: {err}")
        if "metadata_rejected" not in err:
            failures.append("step 1: herdr's code did not reach the caller verbatim")
        if f"hk closed the half-started lane pane {armed['pane']}" not in err:
            failures.append(f"step 1: the cleanup was not disclosed: {err.strip()!r}")

        # ---- 2. the real server shows no residue ---------------------------
        left = [p["pane_id"] for p in pane_list(env)]
        say("2 herdr pane list after the failure",
            f"panes={left} half-started={armed['pane']!r} "
            f"lane panes={[p['pane_id'] for p in lane_panes(env)]}")
        if armed["pane"] is None:
            failures.append("step 2: the fault never fired, so nothing was measured")
        elif armed["pane"] in left:
            failures.append(f"step 2: the half-started pane {armed['pane']} is STILL "
                            f"OPEN — an unaddressable worker is running (panes {left})")
        if lane_panes(env):
            failures.append(f"step 2: a lane pane survived: {lane_panes(env)}")

        # ---- 3. status refuses rather than reporting a ghost ---------------
        rc, out, err = hk(env, "lane", "status", worker)
        say("3 hk lane status", f"rc={rc} stdout={out.strip()!r}")
        if rc != 3:
            failures.append(f"step 3: status exited {rc}, want 3 (no lane reachable)")

        # ---- 4. the retry launches exactly one worker ---------------------
        rc, out, err = hk(env, "lane", "start", worker)
        retried = out.strip()
        lanes = lane_panes(env)
        total = len(pane_list(env))
        say("4 retry", f"rc={rc} pane={retried!r} lane panes={[p['pane_id'] for p in lanes]} "
                      f"all panes={[p['pane_id'] for p in pane_list(env)]}")
        if rc != 0:
            failures.append(f"step 4: the retry exited {rc}: {err.strip()[:200]}")
        elif len(lanes) != 1:
            failures.append(f"step 4: the retry left {len(lanes)} lane panes "
                            f"({[p['pane_id'] for p in lanes]}), want exactly 1 — "
                            f"a duplicated worker")
        elif total != baseline + 1:
            failures.append(f"step 4: the server holds {total} panes, want baseline+1 "
                            f"= {baseline + 1} — the retry launched a second worker "
                            f"while the first one was still running")
        elif (lanes[0].get("tokens") or {}).get(LANE_TOKEN) != "hk1-worker":
            failures.append(f"step 4: the surviving lane does not carry its token: {lanes[0]}")
        elif lanes[0]["pane_id"] != retried:
            failures.append(f"step 4: start printed {retried!r} but the lane table holds "
                            f"{lanes[0]['pane_id']!r}")

        # ---- 5. the retried lane is usable: byte-identical read-back -------
        rc, out, err = hk(env, "lane", "status", worker)
        if rc != 0 or out.strip() != retried:
            failures.append(f"step 5: status resolved {out.strip()!r} (rc {rc}), "
                            f"start reported {retried!r}")
        rc, out, err = hk(env, "lane", "deliver", worker,
                          stdin=payload.decode())
        say("5 deliver the canonical payload", f"rc={rc} {err.strip()[:120]!r}")
        if rc != 0:
            failures.append(f"step 5: deliver exited {rc}: {err.strip()[:200]}")
        else:
            screen, got = "", b""
            deadline = time.monotonic() + WAIT_S
            while time.monotonic() < deadline:
                rc, screen, _err = hk(env, "read", retried, "--text", "--lines", "400")
                if f"READBACK-SHA {len(payload)} {want_sha}" in screen:
                    chunks = re.findall(r"READBACK-HEX ([0-9a-f]+)", screen)
                    got = bytes.fromhex("".join(chunks))
                    break
                time.sleep(0.2)
            say("5 read-back", f"{len(got)} bytes sha {hashlib.sha256(got).hexdigest()[:16]}…, "
                               f"want {len(payload)} bytes sha {want_sha[:16]}…")
            if got != payload:
                failures.append(f"step 5: the retried lane's read-back is not "
                                f"byte-identical: got {len(got)} bytes {got!r}, want "
                                f"{len(payload)} bytes {payload!r}")

        # ---- 6. teardown is a verb, and the count returns to baseline ------
        rc, out, err = hk(env, "lane", "stop", worker)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and len(pane_list(env)) > baseline:
            time.sleep(0.2)
        after = len(pane_list(env))
        say("6 hk lane stop", f"rc={rc} panes {after} (baseline {baseline})")
        if rc != 0:
            failures.append(f"step 6: stop exited {rc}: {err.strip()[:200]}")
        if after > baseline:
            failures.append(f"step 6: {after} panes remain, baseline was {baseline}")
    except Probe as exc:
        failures.append(str(exc))
    finally:
        if restore is not None:
            restore()
        herdr(env, "server", "stop", check=False)
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if args.keep:
            print(f"  kept sandbox: {root}")
        else:
            os.chdir(pathlib.Path(tempfile.gettempdir()))
            shutil.rmtree(root, ignore_errors=True)

    if failures:
        for line in failures:
            print(f"PROBE FAIL: {line}")
        return 1
    print("PROBE PASS: a start that fails part-way closes its own pane (measured on "
          "the real server's pane table), reports one typed line with herdr's code "
          "verbatim, leaves nothing addressable behind, and the retry launches "
          "exactly one worker that delivers and reads back all "
          f"{len(payload)} bytes byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
