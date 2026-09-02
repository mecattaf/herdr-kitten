# Probe report — ground truth against live herdr 0.8.2 + kitty 0.48.0 (2026-09-01)

Every claim below was executed against a real herdr server in a sandbox HOME
(`HOME`, all `XDG_*_HOME`, `XDG_RUNTIME_DIR`, `HERDR_SOCKET_PATH` redirected to `mktemp -d`)
and, for the kitty-attended probes, a real kitty 0.48.0 window on the live Wayland session.
Raw captures: `~/SEPT1/receipts-herdr-kitten/probe-battery/` (durable copy, receipts 00-12).
Binary: herdr 0.8.2 store path (wire protocol 21), build receipts 02/04/05 in the same tree.

| probe | verdict | evidence |
|---|---|---|
| P-G1 headless server | PASS | `herdr server` in sandbox; `herdr status` -> server running, protocol 21, compatible; `herdr workspace list` exit 0 JSON. Receipts 00, 01; also pre-flight liveness receipt 02. |
| P-G2 detach-survive (LOAD-BEARING) | PASS | kitty window ran `herdr terminal attach term_65a713b1db8495`; `sleep 9999` (pid 1478583) started in the pane; kitty OS window closed via remote control; `pane list` still shows w1:p5 and the sleep pid is alive. Receipts 10, 12. Close IS detach. |
| P-G3 self-reap | PASS | `pane split --env HK_PROBE=...` -> env var visible in the pane shell (receipt 07); `exec sleep 1` as pane root process -> pane disappears from `pane list` after payload exit (RuntimeExitAction::ClosePane confirmed). Receipt 06. |
| P-G7 read cap | PASS | 2000 lines generated; `pane read --source recent-unwrapped --lines 5000` returned 999 lines, exit 0, NO cap notice from herdr itself -> `hk read` must emit the stderr cap notice. Receipt 03. |
| P-G10 OSC termination | PASS | `printf '\033]1337;SetUserVar=hkprobe=aGk=\007'` inside the attached pane; `kitty @ ls` shows empty `user_vars` on the outer window. Receipt 11. |
| P-EXTRA bracketed framing | PASS | `pane send-text` is RAW: unframed payload arrived with no brackets; explicit `\x1b[200~...\x1b[201~` passed through byte-exact into a `cat -v` pane; nothing auto-submitted. Receipt 05. |
| P-EXTRA blocked refusal | PASS | `pane report-agent --source test:probe --agent fake --state blocked` then `agent prompt` -> exit 1, stderr `{"error":{"code":"agent_blocked",...}}`. Receipt 09. |
| P-EXTRA events envelope | PASS | Raw NDJSON `events.subscribe` on the socket; captured a REAL envelope: `{"data":{"agent":"fake","agent_status":"working","pane_id":"w1:p2","workspace_id":"w1"},"event":"pane.agent_status_changed"}` preceded by `{"id":"probe:events","result":{"type":"subscription_started"}}`. Receipt 08. notifyd builds against THIS capture. |

## Surprises (fold into designs; also appended to docs/dev/DEFERRED.md)

1. `pane.agent_status_changed` subscriptions are PER-PANE: the Subscription variant REQUIRES
   `pane_id` (schema `request.$defs.Subscription`; live server rejects the bare form with
   `invalid_request: missing field pane_id`). `pane.exited` / `pane.created` / `pane.closed` /
   `pane.updated` are global. The server reads ONE request line per connection, so a changing
   pane set means reconnect-with-new-subscription-list (still exactly one `events.subscribe`
   call site, spec 8.5) or a `pane.updated`-based loop. notifyd design decision for the S4 lane:
   subscribe `pane.created` + `pane.closed` + `pane.exited` + per-pane `pane.agent_status_changed`,
   reconnect on pane-set change (background path, backoff allowed).
2. `pane report-agent --state` accepts idle|working|blocked|unknown — NO `done` (census CLI row
   confirmed live). Smoke fixtures drive `blocked`; `done` transitions come only from real
   agents. G8's "blocked/done" reaction is tested via blocked.
3. `pane read` returned 999 lines (cap 1000 per census P21, minus interaction with the prompt
   line). Gates assert `<= 1000`, not `== 1000`.
4. herdr emits no cap notice on a truncated read; the notice is hk's obligation (spec 6.1).
5. `pane send-text` TEXT is a positional arg (not stdin); `hk send` reads stdin and passes argv.
   Control chars (`\r`, ESC) pass through intact.
6. `workspace create` returns the full root-pane object incl `terminal_id` in one call — `hk new`
   needs no second round-trip.
