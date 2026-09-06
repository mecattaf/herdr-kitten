#!/usr/bin/env python3
"""tests/proofs/hk1-readback-bytes.py — DEFECT 1's teeth, rerunnable.

Card HK-1 (herdr-kitten #37 / tally.nix #673): the paste-read-back smoke must be
unable to pass a delivery that is not byte-identical to the canonical payload.

THE DEFECT THIS PROBE EXISTS FOR (evaluator receipt, verbatim):
  "tests/fixtures/supervised-lane/worker.toml:13 ignores an EOF-unterminated
   trailing fragment, while tests/smoke/supervised-lane.sh:136-146 extracts only
   the last READBACK sentinel body and strips the fixture newline. MEASURED after
   the evaluator mutation hk/lane.py:294 from `text = verbs.read_payload(stream)`
   to `text = verbs.read_payload(stream) + "X"`: bash
   tests/smoke/supervised-lane.sh returned rc 0 and printed GATE SUPERVISED-LANE
   PASS even though hk sent one extra trailing byte."

Two independent blind spots made that possible, and both are closed:
  * the worker was a line reader. `read` holds a trailing fragment that has no
    newline after it until a delimiter or an EOF that a LIVE lane never sends,
    so the appended byte was never reported at all. The shipped worker now puts
    the tty in raw mode (ICANON off — the tty's line discipline buffers the same
    fragment — and ECHO off) and reports every chunk the moment it arrives, as
    literal hex plus its own cumulative count and sha256.
  * the smoke compared 61 stripped bytes and read only the last sentinel. It now
    compares ALL 62 bytes of the payload FILE twice: `cmp` on the bytes
    reconstructed from the rail, and the worker's own `READBACK-SHA <count>
    <digest>` against `wc -c` / `sha256sum` of the same file.

WHAT THIS PROBE DOES
  It never writes into this repository. It copies the tree to a scratch dir and
  runs the COPY's smoke five times, mutating hk's delivery path in the copy:

    unmutated                        must PASS (rc 0)  [the gate is not merely red]
    append one byte                  must FAIL         [the evaluator's mutation]
    drop one byte inside the payload must FAIL
    drop the trailing newline        must FAIL         [invisible to a stripped cmp]
    alter one byte in place          must FAIL

  rc 0 = all five held. rc 1 = at least one did not, with the gate's own output
  pasted. Reverting the repair — the byte-oriented worker, or the
  cmp-against-the-file comparison — turns the appended-byte case green and this
  probe RED, which is the point: the probe fails on the unrepaired tree exactly
  where the evaluator measured it passing.

USAGE
  python3 tests/proofs/hk1-readback-bytes.py [--keep] [--only NAME] [--repo DIR]

Each case is a full smoke run: a real herdr server in a sandbox HOME, a real
pane, a real worker, ~10s. Five cases is about a minute — that is the price of a
claim about a live terminal rail, and the reason this is a proof harness rather
than a unit test. The unit half (the worker protocol over a pipe, including the
line-reader control that reproduces the defect) is
tests/unit/test_lane.py:WorkerProtocolTest.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
TARGET = "hk/lane.py"
SMOKE = "tests/smoke/supervised-lane.sh"

# The one line in hk's delivery path every mutation is applied to. If this
# anchor ever moves, the probe must FAIL loudly: a mutation that silently landed
# nowhere would report "the gate caught it" for a tree it never touched.
ANCHOR = "        text = verbs.read_payload(stream)\n"

MUTATIONS = {
    # name                       -> the mutated line
    "append-a-byte": '        text = verbs.read_payload(stream) + "X"\n',
    "drop-a-byte": ("        text = (lambda t: t[:-2] + t[-1:])"
                    "(verbs.read_payload(stream))\n"),
    "drop-the-trailing-newline": (
        '        text = (lambda t: t[:-1] if t.endswith("\\n") else t)'
        "(verbs.read_payload(stream))\n"),
    "alter-a-byte": ("        text = (lambda t: t.replace('payload', 'payloaD'))"
                     "(verbs.read_payload(stream))\n"),
}


def fail(message: str) -> int:
    print(f"PROBE FAIL: {message}")
    return 1


def copy_tree(repo: pathlib.Path, dst: pathlib.Path) -> None:
    shutil.copytree(repo, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def apply_mutation(dst: pathlib.Path, line: str | None) -> str:
    """Rewrite the copy's delivery line; return the sha of what was written."""
    path = dst / TARGET
    source = path.read_text()
    if source.count(ANCHOR) != 1:
        raise SystemExit(f"PROBE FAIL: the anchor {ANCHOR!r} occurs "
                         f"{source.count(ANCHOR)} times in {TARGET}; this probe "
                         f"would mutate nothing and report a lie")
    path.write_text(source.replace(ANCHOR, line or ANCHOR, 1))
    return line or "(unmutated)"


def run_smoke(dst: pathlib.Path, timeout: int = 900) -> tuple[int, str]:
    proc = subprocess.run(["bash", SMOKE], cwd=dst, capture_output=True,
                          text=True, timeout=timeout)
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-4:])
    return proc.returncode, tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(REPO),
                        help="the tree to copy and mutate (default: this repo)")
    parser.add_argument("--only", action="append", default=None,
                        help="run just this case (repeatable); default: all")
    parser.add_argument("--keep", action="store_true",
                        help="do not delete the scratch copies (paths printed)")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    for required in (TARGET, SMOKE, "tests/fixtures/supervised-lane/payload.txt"):
        if not (repo / required).is_file():
            return fail(f"{repo} is not a herdr-kitten tree: no {required}")

    cases = [("unmutated", None, 0)]
    cases += [(name, line, 1) for name, line in MUTATIONS.items()]
    if args.only:
        wanted = set(args.only)
        cases = [c for c in cases if c[0] in wanted]
        if not cases:
            return fail(f"--only matched nothing; cases are "
                        f"{[c[0] for c in cases]}")

    print(f"hk1-readback-bytes: {len(cases)} smoke run(s) against copies of {repo}")
    print(f"{'case':30} {'want rc':>7} {'got rc':>6}  verdict")
    failures = []
    for name, line, want_rc in cases:
        scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"hk1-proof-{name}-"))
        dst = scratch / "repo"
        try:
            copy_tree(repo, dst)
            applied = apply_mutation(dst, line)
            rc, tail = run_smoke(dst)
        except subprocess.TimeoutExpired:
            rc, tail = "TIMEOUT", "the smoke never finished"
        verdict = "held" if rc == want_rc else "DID NOT HOLD"
        print(f"{name:30} {want_rc:>7} {str(rc):>6}  {verdict}")
        print(f"    hk/lane.py delivery line: {applied.strip()}")
        for out_line in tail.splitlines():
            print(f"    | {out_line}")
        if rc != want_rc:
            failures.append((name, want_rc, rc, tail))
        if args.keep:
            print(f"    kept: {dst}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)

    if failures:
        for name, want_rc, rc, tail in failures:
            print(f"\nPROBE FAIL: case {name!r} wanted rc {want_rc}, got {rc}")
            print(tail)
        return 1
    print("\nPROBE PASS: the paste-read-back oracle refused every non-byte-identical "
          "delivery (appended, dropped, stripped-newline, altered) and passed the "
          "unmutated one — all five measured against a live herdr server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
