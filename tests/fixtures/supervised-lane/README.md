# supervised-lane fixture

The presets `tests/smoke/supervised-lane.sh` drives, one per typed outcome of
the RULING-kitten §5 exit contract. They are fixtures, not templates: the
documented example a user copies is `conf/supervised-lane.toml`.

| file                | verb                | exit | outcome                                   |
|---------------------|---------------------|-----:|-------------------------------------------|
| `worker.toml`       | `start` + `deliver` |  `0` | delivered — the paste-read-back lane       |
| `blocked.toml`      | `deliver`           |  `1` | refused — `agent_blocked`, verbatim        |
| `stalled.toml`      | `start`             |  `1` | refused — `timeout`, the pane closed again |
| `absent.toml`       | any, **no server**  |  `1` | no session — `server_not_running` verbatim |
| `malformed.toml`    | any                 |  `2` | malformed preset (invalid TOML)            |
| `absent.toml`       | `deliver`           |  `3` | no lane reachable, **zero bytes sent**     |
| `unsupervised.toml` | any                 |  `4` | not implemented, and never will be         |

`absent.toml` does double duty on purpose: it is a perfectly valid preset, so what it
returns is decided entirely by the world it is run against — no herdr server at all is
exit 1 with `server_not_running` verbatim (the smoke's first step, before it starts a
server), and a live server with no lane of that name is exit 3. Neither consumes a byte
of stdin.

`blocked.toml` is delivered TO, never started: its `name` is the join onto the lane
`worker.toml` already launched, and its `argv` is inert (`cat`) because nothing in that
step reaches a pane — the refusal happens in herdr, before any byte moves. Its
`submit = true` is the whole point: the agent-prompt route is the one a blocked agent
refuses on.

`payload.txt` is the canonical payload: exactly one line plus its newline, **62 bytes**,
sha256 `562fd7fc051db1c68dc8fb44818db60ea591109854161ca4cd24605762e963f9`. The smoke
pins that digest *and* compares the read-back to the file, so a byte dropped from either
side of the round trip goes RED.

## The read-back worker is byte-oriented, and that is load-bearing

`worker.toml`'s argv is a python worker that puts its tty in raw mode (`ICANON` off,
`ECHO` off) and reports **every chunk the moment it arrives**:

| line | meaning |
|---|---|
| `LANE-READY` | the readiness marker `hk lane start` waits for |
| `READBACK-HEX <hex>` | the literal bytes just received, in order — the smoke concatenates these and `cmp`s the result against `payload.txt` |
| `READBACK-SHA <count> <digest>` | the worker's OWN cumulative count and sha256 of everything it has received — the smoke waits for `READBACK-SHA 62 562fd7fc…`, i.e. for `wc -c` and `sha256sum` of the same file |
| `LANE-EOF <count>` | stdin closed; the pane then reaps itself |

It must not be a line reader. `while IFS= read -r line` cannot report a trailing fragment
that has no newline after it: `read` holds that fragment until a delimiter or an EOF that
a LIVE lane never sends, and the tty's own canonical mode buffers it the same way. That is
exactly how this fixture once let a delivery with one extra byte pass as byte-identical
(evaluator DEFECT 1 on card HK-1). Two independent measures of the same delivery — the
bytes as they came back through the rail, and the digest the worker computed over what it
read — are both compared against all 62 bytes of the file, never against a stripped copy
of it.

## Rerunnable proofs (beside the other tools in `tests/proofs/`)

- `python3 tests/proofs/hk1-readback-bytes.py` — copies the tree, mutates hk's delivery
  path four ways in the copy (append a byte, drop one, drop the trailing newline, alter
  one in place) and requires the smoke to go RED each time and GREEN unmutated.
- `python3 tests/proofs/hk1-retry-cleanup.py` — live server: a `start` whose metadata
  write fails must close its own pane, leave nothing addressable behind, and the retry
  must launch exactly one worker (evaluator DEFECT 2).
