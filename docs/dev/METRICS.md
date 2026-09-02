# METRICS — herdr-kitten (pre-registered at Phase 0; closed out 2026-09-01T23:15Z)

## Completion oracle (registered up front)
| oracle | target | actual |
|---|---|---|
| G1-G18 gates | each PASS or SKIP-with-reason | **18/18 PASS** (G-ssh extra gate: typed SKIP by design) — docs/dev/acceptance-run.md |
| `nix flake check` | green | **green x4** (W0 first-try, W1, W2, final W3) |
| repo pushed | private, github.com/mecattaf/herdr-kitten | **done** (PRIVATE, main) |
| issues filed (W4) | ~10-25, labeled, receipted | **14** (6 labels; index #14; receipts banked) |
| HUMAN-ATTENDED checklist | verbatim in final STATUS | **done** (also issue #1) |

## Per-wave (wall-clock is active lane time; token meter is MACHINE-WIDE — three lanes
## plus one orphaned flow node shared it tonight, so per-wave attribution is honest only
## as deltas-with-that-caveat; snapshots banked before/w1-boundary/after)
| wave | what ran | active wall-clock (approx) | nodes plan vs actual | repair loops |
|---|---|---|---|---|
| W0 (warm) | probes + scaffold + flake | ~55 min | n/a (warm, sequential) | 0 (flake check green first try) |
| W1 | 1 flow node (daemon orphan) + 1 warm lane + merge | ~75 min | 4 planned flow nodes; 1 executed as orphan, 1 warm, 2 control warm | 5 warm gate/harness fixes |
| W2 (warm) | events-voice + remote-polish | ~45 min | flow authored+checked, run warm | 4 warm fixes (buffering, set -e, call-site laws) |
| W3 (warm) | docs + adversarial verify + attended battery + push | ~35 min | flow authored+checked, run warm | 1 (G11 buffering) |
| W4 (warm) | labels + 14 issues + index | ~15 min | flow authored+checked, run warm | 0 |

## Boundary crossings
| wave | adoption (author-done -> check exit 0) | flow-check failures caught warm | warm fixes at synthesis |
|---|---|---|---|
| W1 | ~10 min authoring, **check exit 0 first contact** | 0 | lib.sh merge conflict resolved; install.sh reconciled |
| W2 | ~5 min (scissors), first contact | 0 | niri-adapter duplication resolved in the stronger direction |
| W3 | ~5 min (scissors), first contact | 0 | — |
| W4 | ~10 min (fresh authoring), first contact | 0 | — |

Flow-run reality: `tally flow run` requires `--flow-run-id <UUID>` (not in any doc we had);
then EVERY claude() node dies at the runner on payload-hash-contract-drift (deterministic,
2/2, identical hashes; sh nodes fine). Full repro: ~/SEPT1/receipts-herdr-kitten/tally-defects.md.

## Defects caught by side
| side | count | notes |
|---|---|---|
| contract (gates/evidence) | 6 | flake smoke caught missing PATH shim; G4/G6/G11 caught the cat -v line-buffering physics; G15 caught the env-leak that stamped the developer's real kitty window; G16 (orphan node's) hardened the reattach-pid proof; G7 pinned <=1000 not ==1000; drift error itself was a contract catch |
| warm adjudication | 9 | herdrc empty-stdout envelopes; recent*-source lag discovery; XDG_RUNTIME_DIR hid the wayland socket; set -e pipeline swallowing (x2); merge-conflict resolution; kitty one-call-site law restored for notifyd; install.sh kitten modules; README verb sweep |
| bounced (mis-specialization) | 3 | W1 core-cli lane double-executed (warm + orphaned flow node racing in one worktree — resolved by handing the lane to the node and messaging it); my scratch niri helper superseded by the node's stronger adapter; W2-W4 flows authored for a substrate that could not run them (files remain as adoption artifacts) |

## Close-out
- ccusage-before: receipts/ccusage-before-lane1.json (19:44Z) · w1-boundary (21:30Z, machine-wide delta ~29.3M) · after: receipts/ccusage-after.json (23:14Z)
- The one accidental A/B of the night: the SAME lane prompt executed warm (me) and cold
  (the orphaned claude node) against the same worktree produced compatible designs — the
  node's gate assertions were STRONGER (marker files, pid proofs), the warm side was
  faster at physics discovery (buffering, source lag, env leaks). Division of labor
  confirmed, by accident, in one worktree.
