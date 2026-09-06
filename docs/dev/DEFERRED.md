# DEFERRED — herdr-kitten (seeded at Phase 0, 2026-09-01; updated at every wave boundary)

Everything the tonight build will NOT attempt, declared not silent. Each entry: what, why
deferred, and where the evidence lives.

## 1. Fork-ledger items (ADDENDUM seed table -> docs/fork-ledger.md)
Reserved for a later herdr fork or patchset. A ledger, not work; nothing here blocks S1-S6.
- kitty graphics passthrough
- OSC 52 read (architecturally dead in current herdr; see also census P27 / spec F.1)
- OSC 133 prompt marks through panes
- pane-emitted OSC 1337
- xterm extras

## 2. Spec A held decisions — HELD, NOT ASKED (Tom is asleep; never asked tonight)
- UNKNOWN-1: public names. Build proceeds under working names `herdr-kitten` / `hk`.
  Tom confirms names before the S6 public flip. adopted-as-working (GUESS), relitigable.
- DECISION-1: private at creation, public at S6 by Tom. adopted-as-proposed (GUESS), relitigable.
- DECISION-2: static mic-glyph PNG; frame-cycling behind --spin. adopted-as-proposed (GUESS), relitigable.
- DECISION-3: README chord suggestions ctrl+b / ctrl+shift+g / ctrl+shift+h.
  adopted-as-proposed (GUESS), relitigable.

## 3. Census AMBIGUOUS rows the build routes around
- P19: hold-to-talk not expressible in niri; gesture is consumer territory (spec R5/D9).
- P25: last_cmd_output plain-tier-only (D21).
- P27: OSC 52 read architecturally dead (F.1).
- P43: niri-tier spinner host resolved via D8 window-logo; the OSD gap recorded.
- P49/P50: workspace-number and chord collisions — consumer territory (D15).
- config census: `update.channel` build-dependent default.
- CLI census AMBIGUOUS spec-vs-runtime rows: trust live behavior as probed in W0, cite the row.

## 4. Hijack adoption semantics dropped (one entry, adoption-ledger law; applies to all waves)
phase() -> log(); budget -> maxNodes/iterationCap; effort field dropped; model dropped by law
(daemon pin claude-code/claude-opus-5 covers it, modelProvenance=daemon-config); warm
inter-phase adjudication moved from inside flows to wave boundaries (the point of the re-cut).

## 5. HUMAN-ATTENDED — prepared tonight, never performed
- Public repo flip (spec D28/DECISION-1).
- #284 announcement comment (spec 12.7).
- Upstream-ask filing on herdr's tracker (spec 12.2) — drafts land in docs/upstream.md only.
- Visual gates: spec 5.5, 6.2, 6.3, 9.6, 9.7, 10.3, 10.4, U.1-U.3.

## 6. Out-of-scope by trio design
- dotfiles consumption (spec B — the dotfiles session's night).
- tally-side maximalism / overlap-deletion / prompt-transport scope (campaign C — the
  tally-herdr session's night).

## 7. Wave-boundary additions
(appended at the wave boundary where each item surfaces)

### W0 boundary (2026-09-01T20:20Z)
- PROBE SURPRISES (binding; full detail in docs/probe-report.md "Surprises"):
  (1) pane.agent_status_changed subscription REQUIRES pane_id (per-pane); one request line
  per connection -> notifyd reconnects on pane-set change (still one events.subscribe call
  site) or rides pane.updated; S4 lane decides against the captured envelope.
  (2) report-agent --state has no `done` -> G8/G6 fixtures drive `blocked` only.
  (3) read cap observed as 999 lines on a 5000 request -> gates assert <=1000, not ==1000.
  (4) herdr emits no truncation notice -> the cap notice is hk's obligation (spec 6.1).
- ORCHESTRATION ADAPTATION: this session has no Workflow/Agent-spawn tool; W0's two warm
  lanes ran sequentially in-session (probes first — front-loaded G2 risk). W1-W4 fan-out
  comes from the tally flow runtime. Not a blocker; a substrate fact.
- W1 RE-CUT DEVIATIONS from banked flow-a (file: herdr-kitten-flow/waves/flow-a-w1.js):
  wave-boundary split (only waveOne executes; flow ends at merge-wave-1 synthesis point);
  maxNodes 20->8, iterationCap 12->6 (4 planned nodes + repair headroom); kitten-lane
  "sibling is writing the predicate concurrently" corrected to "predicate EXISTS from W0";
  CONTEXT gained two sentences (probe-report-wins rule; herdr binary path for smoke runs);
  core-cli file-domain clarified (trampoline hook in assets/ is core-cli's; fork.lua and
  kitty-maps.conf are kitten lane's).
- FLOW-A PROBE NODE DELTA: the banked probe prompt FILES the four upstream asks on herdr's
  tracker; tonight that is HUMAN-ATTENDED (spec 12.2, mission law) -> docs/upstream.md holds
  ready-to-file drafts instead. The probe battery itself ran warm in W0, all PASS.

### W1 boundary amendment (2026-09-01T20:35Z) — TALLY DEFECT, waves run warm
- payload-hash-contract-drift kills every claude() flow node deterministically (2/2 runs,
  identical hashes; sh nodes pass). Full repro + logs:
  ~/SEPT1/receipts-herdr-kitten/tally-defects.md. NOT filed on mecattaf/tally.nix (repo
  ownership wall); the defect file is the handoff.
- Ruling applied (mission escalation ladder): W1-W4 execute WARM in this session as the
  ultracode workflows they were authored as; flow files + `tally flow check` exit-0 receipts
  remain the adoption artifacts; the claude-window pool is not consumed by warm execution.

### W2 boundary amendment (2026-09-01T21:36Z)
- W2 lanes execute sequentially WARM on main (single executor; the parallel-worktree
  shape had no remaining value once the flow substrate bounced — flow files
  flow-a-w2.js/w3.js/w4.js remain check-passing adoption artifacts). File-domain
  discipline preserved at commit granularity instead.

### W4 externalization (2026-09-01T23:05Z) — every remaining item now has a gh issue
Issues filed on mecattaf/herdr-kitten (receipts: ~/SEPT1/receipts-herdr-kitten/issues-filed.md):
- §1 fork-ledger -> #6 · §2 held decisions -> #1 (+#13 for the --spin remainder)
- §3 consumer-territory rows -> #8 · §5 human-attended -> #1, #7
- upstream asks -> #2 #3 #4 #5 · probe surprises -> #11 (recent* lag), #12 (done state)
- D10 thin-client fork variant -> #9 · trampoline ergonomics -> #10
- Index mapping issues<->ledger lines: #14 (linked from README limitations)
- NOT externalized here by design: tally payload-hash drift (handoff file
  tally-defects.md, tally.nix's domain); spec B dotfiles consumption; campaign C scope.

### HK-1 boundary (2026-09-06) — supervised lanes, and one gloss a ruling bars
- **The card's exit-code gloss is NOT adopted.** Card `HK-1` glosses the five typed
  exits as `0 delivered, 1 refused, 2 no session, 3 timeout, 4 malformed`. RULING-kitten
  §5 — the captured ruling this repo's whole CLI contract already answers to, and which
  `hk/verbs.py`'s `EXIT_*` constants encode — assigns `2` to CLI/preset syntax, `3` to
  "no target reachable, zero bytes sent", and `4` to "not implemented". Renumbering
  would silently change what every existing verb means to callers who already branch on
  it, so the numbers keep their §5 meanings and `hk lane` produces all five of the
  card's *outcomes* under them: delivered (0), refused (1, `agent_blocked`), timeout
  (1, `timeout`), no session (1, `server_not_running` verbatim when no herdr server is
  up at all — the answer `hk send` already gives in that state — and 3 when the server
  is up but no lane of that name is running, which is §5's "no target reachable, zero
  bytes sent"), malformed preset (2), not implemented (4). In every refusing case zero
  bytes of stdin are consumed, which is the property a supervisor branches on.
  `tests/smoke/supervised-lane.sh` asserts every one; `tests/fixtures/supervised-lane/`
  ships one preset per row. Relitigable only by a newer ruling on §5.
- **`kind = "unsupervised"` is answered, never implemented.** RULING-kitten §5 keeps
  tally's unsupervised lanes on `systemd-run` with `stdin=/dev/null` and says hk never
  appears in one. A preset declaring it gets exit 4 and a line saying why it is
  permanent, rather than a lane hk should not have.
- **`hk lane` grows no `wait`/`wait-output` verb — and hk still has neither.**
  RULING-kitten §5 lists `hk wait-output <target> --match/--regex [--timeout MS]` and
  `hk wait <agent> [--until S] [--timeout MS]` in the CLI contract tally may rely on;
  MEASURED 2026-09-06: `bin/hk` builds no such parser, so both are still unbuilt repo-wide
  and neither is this unit's to build. `hk lane` does not smuggle them in: the bounded
  readiness wait inside `hk lane start` (`ready_match`/`ready_timeout_ms`, opt-in, one
  0.1 s interval that a preset cannot tune) is a lifecycle precondition — the worker is
  up before delivery is possible — not a general waiting surface, and spec F.6's
  no-polling rule governs interactive paths. Filing the two §5 wait verbs is a separate
  unit's.
- **`tests/smoke/supervised-lane.sh` is not in `run-headless.sh`.** It is its own oracle
  entry for card HK-1 and runs alongside the repository battery. Folding it in is a
  later editorial call, not a silent one.
