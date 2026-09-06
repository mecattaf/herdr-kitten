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

`payload.txt` is the canonical payload: exactly one line plus its newline, 62
bytes, sha256 `562fd7fc051db1c68dc8fb44818db60ea591109854161ca4cd24605762e963f9`.
The smoke pins that digest *and* compares the read-back to the file, so a byte
dropped from either side of the round trip goes RED.
