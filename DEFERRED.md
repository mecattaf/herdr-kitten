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
