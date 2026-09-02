# The kitty <-> herdr mapping

One row per integration point of the underlying census (P01-P79). This is the evidence
artifact behind herdr-kitten: which direction each point flows, what transport carries it,
and what in this repo (if anything) discharges it. Points marked *herdr-native* work with
zero repo code; *plain-tier* points live on kitty windows herdr never touches;
*out-of-scope* rows name their reason and stay visible instead of vanishing.

Verb = `hk <verb>` (the CLI). Gesture = `kitten hk.py <gesture>` (the kitten).
Gates G1-G18 are the acceptance battery in `tests/smoke/` + `docs/dev/acceptance-run.md`.

## A — Identity and join keys

| point | direction | transport | repo disposition |
|---|---|---|---|
| P01 kitty-identity -> herdr | kitty->herdr | socket RPC | every pane-touching verb stamps `pane report-metadata --source user:hk --token kitty_win/kitty_sock/hk_role`; ttl/seq omitted; re-stamped on every attach (tokens die with the server). Gate G15/G5. |
| P02 herdr-identity -> kitty | herdr->kitty | user-var + env | `hk materialise` / `hk new` / fork launch pass `--var hk_pane/hk_ws/hk_role`; herdr injects `HERDR_PANE_ID`/`HERDR_WORKSPACE_ID` itself. Gate G15. |
| P03 window<->pane cardinality | bidi | env | model law honored everywhere: one kitty window = one view; attach key is `terminal_id`, never `pane_id`. |
| P04 role stamping | bidi | user-var + socket RPC | `hk_role` stamped both sides at launch/attach; roles: herdr, herdr_ui, split, fork, editor. |
| P05 herdr-client predicate | herdr->kitty | user-var + env | ONE module `hk/predicate.py`: `hk_role` primary, foreground-argv confirming (false-positives under `--remote` otherwise). Three consumers import it. Unit-tested. |
| P06 editor self-report | herdr->kitty | socket RPC -> user-var | async mirror: editor calls `pane report-metadata --token hk_role=editor`; notifyd mirrors to the window user-var. Eventual consistency by design; zero sockets on kitty's GUI thread. Gate G8. |

## B — Pane lifecycle

| point | direction | transport | repo disposition |
|---|---|---|---|
| P07 split | bidi | launch + socket RPC | toggle gesture launches a vsplit running `hk open` (server-side pane first, kitty draws the split). |
| P08 close = detach | kitty->herdr | kitten launch | THE load-bearing equivalence: closing the kitty window leaves the pane and its processes alive. Proven live, gate G2. |
| P09 focus | bidi | socket RPC | three-way boundary (compositor owns OS windows; herdr owns pane focus; `hk focus <pane>` resolves the `kitty_win` token to `kitty @ focus-window`, nonzero when absent). |
| P10 argv pane + self-reap | kitty->herdr | env trampoline | `hk run -- ARGV`: b64 `HK_EXEC` env + `assets/hk-trampoline.sh` (decode/unset/exec) so the payload's exit is the pane's exit. Gate G3. Upstream ask: `pane split --command`. |
| P11 materialise | herdr->kitty | kitten launch | `hk materialise <ws>`: one kitty OS window per pane, `herdr terminal attach <terminal_id>`. Gate G9. |
| P12 dematerialise | bidi | socket RPC + launch | `hk dematerialise <ws>`: enumerate herdr-side `kitty_win` tokens, close windows, panes survive. Gate G9. |
| P13 rematerialise | herdr->kitty | socket RPC + launch | same verb re-run; geometry deliberately NOT replayed — the compositor places windows. |
| P14 pane exit -> window teardown | herdr->kitty | env | trampoline exec semantics + `RuntimeExitAction::ClosePane`; proven live (gate G3). |

## C — Text transport IN

| point | direction | transport | repo disposition |
|---|---|---|---|
| P15 populate, do not submit | kitty->herdr | send-text | `hk send <pane>`: stdin framed `\x1b[200~..\x1b[201~` manually (herdr sends raw bytes — verified). Gate G4. |
| P16 submit now | kitty->herdr | send-text | `hk send --submit`: routes `agent prompt`; a Blocked agent refuses server-side, exit 1, error verbatim on stderr. Gate G6. |
| P17 kitty clipboard paste | kitty->herdr | send-text | plain-tier / client-focused-pane behavior; untouched, documented. |
| P18 dictation | kitty->herdr | compositor injection / hk | `hk voice text` targets the focused window's herdr pane; non-herdr window -> exit 3 + zero bytes so the dictation layer falls back to compositor injection. Gates G11/G12. |
| P19 hold-to-talk gesture | kitty->herdr | compositor | out-of-scope: the binding is consumer territory (not expressible in every compositor); the repo owns only the `hk voice` endpoint contract. |
| P20 recording indicator | herdr->kitty | socket RPC | `hk voice begin/end --window <id>`: `kitten @ set-window-logo` bottom-right; non-destructive, no input interception. Gate G13. |

## D — Text transport OUT

| point | direction | transport | repo disposition |
|---|---|---|---|
| P21 scriptable pane read | herdr->kitty | socket RPC | `hk read <pane>`: `pane read --source recent-unwrapped --format ansi`; the server caps at 1000 lines silently — hk prints the cap notice on stderr. Gate G7. Upstream ask: configurable cap. |
| P22 uncapped scrollback -> editor | herdr->kitty | send-text | dispatcher herdr lane forwards `\x02e` (herdr `keys.edit_scrollback`: uncapped plain-text in `$EDITOR`). |
| P23 two-lane dispatcher | bidi | send-text + user-var | scrollback gesture: herdr window -> `\x02e`; plain window -> `plain_scrollback_action` from hk-config (default kitty `show_scrollback`). A herdr window can NEVER reach the plain lane — unit-tested routing table. |
| P24 kitty-scrollback.nvim | kitty-only | kitten launch | plain tier preserved byte-identical; consumers point `plain_scrollback_action` at it if wanted. |
| P25 last_cmd_output extents | kitty-only | kitten launch | plain-tier-only: herdr exposes no OSC-133 prompt extent. Upstream ask filed as draft; no local imitation. |
| P26 select -> clipboard | herdr->kitty | OSC in-band | herdr-native (OSC 52 write path); zero repo code. |
| P27 clipboard read in pane | herdr->kitty | OSC in-band | architecturally dead (OSC 52 reads terminated in herdr's VT layer); no clipboard verb exists in this repo by law. Fork-ledger row. |
| P28 remote image paste | herdr->kitty | socket RPC | herdr-native (`keys.remote_image_paste`, `--remote` only); documented. |

## E — Titles and renames

| point | direction | transport | repo disposition |
|---|---|---|---|
| P29 durable rename | bidi | socket RPC | `hk rename` tier 1: `pane rename` — the only name field that survives server restart. Gate G5. |
| P30 live display title | herdr->kitty | socket RPC | `hk rename` tier 2: `pane report-metadata --title` (display-only, dies with the server). |
| P31 title ownership | herdr->kitty | socket + OSC | ruled: kitty owns the window title. The shipped herdr profile snippet sets `ui.window_title = ""`; `hk rename` tier 3 writes `kitten @ set-window-title`. |
| P32 cold-tier title sidecar | herdr->kitty | socket RPC | out-of-scope: consumer (dotfiles) territory; the repo's durable tier (P29) is the base it builds on. |
| P33 workspace rename fan-out | herdr->kitty | socket + launch | `hk ws rename <ws> <label>`: herdr rename + re-title every kitty window whose `hk_ws` matches. Gate G9. |
| P34 tab rename | bidi | socket RPC | non-target: the repo never creates or touches kitty tabs; herdr's virtual tabs (thin client) untouched; profile snippet hides the single-tab bar. |
| P35 agent rename | kitty->herdr | socket RPC | `hk agent rename`: validating pass-through (slug `^[a-z][a-z0-9_-]{0,31}$` rejected locally); CLI-only, no gesture. |
| P36 titler vs plugin labels | bidi | socket RPC | title bridge skips panes whose durable label carries plugin provenance (e.g. `reviewr`); unit-tested. |

## F — Agent state surfacing

| point | direction | transport | repo disposition |
|---|---|---|---|
| P37 agent lifecycle IN | kitty->herdr | socket RPC | `herdr integration install claude` remains the installer; the repo hand-rolls no agent hooks (README warns it writes the agent's settings). `report-agent` is never called outside smoke fixtures. |
| P38 toast -> kitty notification | herdr->kitty | OSC in-band | profile snippet sets `[ui.toast] delivery = "terminal"` — herdr toasts ride OSC 99 into kitty. |
| P39 agent status -> desktop notification | herdr->kitty | socket -> OSC | THE verified gap (direct attach gets no SemanticNotification): `hk notifyd` subscribes over the socket and runs the notify command once per blocked/done transition. Gate G8. |
| P40 notification daemon | herdr->kitty | OSC | `notify_command` configurable in hk-config (default `notify-send`); provisioning a daemon is the consumer's problem. |
| P41 agent status -> kitty tab bar | herdr->kitty | socket RPC | non-target (no kitty tabs, ever). |
| P42 agent status -> window decoration | herdr->kitty | socket + launch | out-of-scope: compositor window-rules are consumer territory; the title bridge (E) and `hk_status` user-var (P53) are the hooks it consumes. |
| P43 spinner host | herdr->kitty | socket RPC | resolved: the host surface is kitty itself via `set-window-logo` (P20/D8); the compositor-OSD gap stays recorded. |
| P44 notification click -> focus | herdr->kitty | socket RPC | out-of-scope: needs a notification daemon action protocol; upstream plugin exists; not wrapped. |

## G — Workspace model

| point | direction | transport | repo disposition |
|---|---|---|---|
| P45 new herdr-backed terminal | kitty->herdr | launch + socket | `hk new`: workspace create + root pane + kitty OS window attached. Gate G17. |
| P46 plain terminal | kitty-only | launch | preserved tier, deliberately herdr-free; nothing in this repo touches it. |
| P47 N windows <-> 1 workspace | bidi | user-var + socket | the `hk_ws` user-var is the join; `hk open` joins the focused window's workspace, creating none. Gates G15/G9. |
| P48 herdr <-> compositor workspace pinning | herdr->kitty | socket + launch | niri adapter: `NIRI_SOCKET` present -> materialised windows move to the focused niri workspace; absent -> zero compositor calls (unit-tested). |
| P49 workspace focus by number | kitty->herdr | socket RPC | `hk ws focus <n>` joins on `WorkspaceInfo.number`. Chord wiring is consumer territory. Gate G17. |
| P50 workspace rename chord | kitty->herdr | socket RPC | chord collisions are consumer territory; `hk ws rename` is the bind target. |
| P51 workspace label default | herdr->kitty | socket RPC | `hk new` labels from the git repo-root basename (herdr's own default is honored elsewhere). Gate G17. |

## H — Events

| point | direction | transport | repo disposition |
|---|---|---|---|
| P52 event subscription | herdr->kitty | socket RPC | `hk notifyd`: the repo's ONE event loop; raw NDJSON `events.subscribe` (no CLI verb exists upstream); exactly one call site, unit-enforced. |
| P53 role/status mirror | herdr->kitty | socket -> user-var | notifyd mirrors agent status + editor self-reports into window user-vars (`hk_status`, `hk_role`). Gate G8. |
| P54 incumbent event stream | kitty-only | launch | replaced: the net count of long-lived event loops stays one (notifyd). |
| P55 plugin [[events]] hooks | herdr->kitty | socket + env | documented alternative, not used (hookable list excludes the high-volume events the mirror needs). |

## I — Attach / detach / remote

| point | direction | transport | repo disposition |
|---|---|---|---|
| P56 detach | kitty->herdr | kitten launch | spelled "close the window" (P08); herdr's own `prefix+q` unreachable and unneeded on this tier. |
| P57 reattach picker | herdr->kitty | socket + launch | `hk resume`: rows of terminal_id / label / agent_status; fork-role panes filtered; fzf if present, numbered menu otherwise; attach by terminal_id. Gate G16. |
| P58 thin client | bidi | launch + user-var | `hk ssh <host>`: kitty window exec `herdr --remote <host> --remote-keybindings server`, stamped `hk_role=herdr_ui`. |
| P59 remote, plain | kitty-only | launch | `hk ssh --plain <host>` execs `kitten ssh` — terminfo, ControlMaster, shell integration live only there. No fork of kitten ssh. |
| P60 prefix routing | bidi | user-var + send-text | toggle ladder step 0: `hk_role=herdr_ui` -> forward `\x02` to the child, deferring to herdr's prefix layer. Unit-tested. |
| P61 socket asymmetry | kitty->herdr | socket RPC | `hk --host <h>` prefixes herdr calls with `ssh <h>`; every kitty call stays local, always. |
| P62 server-side callback | herdr->kitty | env | thin-client fork variant: the same `hk fork --pane` backend behind a herdr `[[keys.command]]` binding (server-side, where kitty verbs would be wrong). |
| P63 thin-client file-pick gap | kitty->herdr | env | pre-existing, unchanged by herdr, restated as OPEN in README limitations — never folded into a "fixed" claim. |

## J — Images

| point | direction | transport | repo disposition |
|---|---|---|---|
| P64 graphics passthrough | herdr->kitty | socket RPC | gated: `experimental.kitty_graphics` stays false in the shipped snippet; README documents the flag and the flip condition (detach-reattach staleness probe). Fork-ledger row. |
| P65 image placement methods | herdr->kitty | socket RPC | `pane.graphics.*` are socket-only (no CLI); documented here, not wrapped. |
| P66 direct-kitty fast path | herdr->kitty | socket RPC | documented; not available over `--remote` (degrades to inline). |
| P67 icat inside a pane | kitty->herdr | launch | gated entirely on P64's flag; documented. |

## K — Slash-fork

| point | direction | transport | repo disposition |
|---|---|---|---|
| P68 the chord | kitty->herdr | launch + user-var | `kitten hk.py fork` (suggested `ctrl+shift+g`); window without `hk_pane` -> silent no-op, no bell. |
| P69 the blank window | kitty->herdr | launch + user-var | `--type=os-window --os-window-class=hk-fork`, target pane threaded via `HK_FORK_PANE` env (launched windows inherit no HERDR_* env). |
| P70 the delivery gate | kitty->herdr | env | nvim `BufWritePost`/`VimLeavePre` are the only decision points; `:q!`/crash delivers nothing. Gate G14. |
| P71 the delivery | kitty->herdr | send-text | `hk send` (populate) / `hk send --submit` (agent prompt) — one transport, two consumers. |
| P72 blank is correctness | — | — | the buffer starts blank by doctrine; the fork path contains no `pane read` (enforced by the forbidden sweep). |
| P73 multi-save semantics | kitty->herdr | send-text | ruled: idempotent append-only — unchanged saves no-op, append-only saves deliver the suffix, inner edits deliver nothing + notification. Pure logic unit-tested; gate G14. |
| P74 submit-or-populate | kitty->herdr | send-text | populate by default; `agent prompt` only behind an explicit `--submit`. |

## L — Cross-cutting

| point | direction | transport | repo disposition |
|---|---|---|---|
| P75 session name in prompt | kitty->herdr | env | out-of-scope: consumer territory (thread your own env at pane creation); herdr injects ids only. |
| P76 availability posture | — | socket RPC | one server; a crash takes every pane; snapshot restore recovers layout+cwd, not processes. Stated in README limitations; `resume_agents_on_restore = true` in the snippet; not mitigated further. |
| P77 artifact shape | — | — | Python-only by necessity (Go kittens are builtin-only with zero Boss access); stdlib-only CLI; zero build step. |
| P78 vocabulary hygiene | — | — | the words drain/handoff/pickup name nothing here — they belong to herdr's live-handoff machinery. |
| P79 "clipboard transport" | kitty->herdr | send-text | does not exist upstream and is not imitated: the transport IS `pane send-text` / `agent prompt`, with real failure signals. No clipboard verb, by law. |
