# Acceptance run — 2026-09-01 (overnight build, live battery)

Environment: herdr 0.8.2 (wire protocol 21, nix store build), kitty 0.48.0 on a live
Wayland session (niri), Python 3.14, nvim 0.12. Every gate ran against a REAL herdr
server in a sandbox HOME; kitty-attended gates ran real kitty windows on the live
display. Headless battery driver: `tests/smoke/run-headless.sh` (also the flake check
`herdr-kitten-smoke`). Durable raw captures: `~/SEPT1/receipts-herdr-kitten/`
(probe-battery/, w1-core-cli-smoke.txt, w2-battery.txt, w3-*.txt).

| gate | mode | verdict | evidence |
|---|---|---|---|
| G1 headless liveness | headless | **PASS** | server up, `workspace list` JSON, doctor reports protocol 21 + floors + socket |
| G2 detach-survive | attended | **PASS** | `tests/smoke/g02-detach-survive.sh`: kitty window closed; pane and `sleep` pid survived (close IS detach). Also probe P-G2. |
| G3 trampoline self-reap | headless | **PASS** | marker file proves the payload exec'd via HK_EXEC; pane reaped on payload exit |
| G4 bracketed populate | headless | **PASS** | `cat -v` shows `^[[200~..^[[201~` server-side; nothing submitted |
| G5 rename durability + restamp | headless | **PASS** | label `alpha` survived `server stop`+restart; tokens re-stamped on the next attach |
| G6 submit refusal | headless | **PASS** | blocked agent: exit 1, `agent_blocked` verbatim on stderr, zero bytes delivered |
| G7 read cap surfaced | headless | **PASS** | 999 lines returned on a 5000-line ask; cap notice on stderr only |
| G8 the one event loop | headless + attended | **PASS** | notify fired once <2s per blocked transition (gate); user-var mirror half attended: `hk_status=blocked` landed on the window, focus unchanged (w3-g8-attended.txt) |
| G9 materialise round-trip | headless + attended | **PASS** | socket half in battery; attended: 3 OS windows materialised, rename fan-out re-titled all to `beta`, dematerialise closed all 3, all 3 panes alive; niri adapter adopted 3 windows live (w3-g9-attended.txt) |
| G10 OSC termination | attended | **PASS** | pane-emitted OSC 1337 SetUserVar absent from the outer kitty window's user_vars |
| G11 voice delivery | attended | **PASS** | dictation landed bracketed in the focused window's herdr pane, exit 0 |
| G12 voice fallback | attended | **PASS** | plain focused window: exit 3, zero bytes delivered anywhere |
| G13 spinner set/clear | attended | **PASS** | begin/end both exit 0; begin-then-end leaves no logo configured |
| G14 fork round-trip | headless (nvim) | **PASS** | first `:w` whole-buffer bracketed; append-only save delivered ONLY the suffix; `:q!` delivered zero bytes |
| G15 join keys both directions | headless + attended | **PASS** | socket half in battery; attended: `hk open` inside a real kitty window stamped `hk_pane/hk_ws/hk_role` user-vars AND `kitty_win/kitty_sock/hk_role` tokens under `user:hk` (w3-g15-attended.txt) |
| G16 resume picker | headless | **PASS** | rows terminal_id/label/agent_status; fork-role pane filtered; `--attach` reattached with the shell pid unchanged |
| G17 workspace verbs | headless | **PASS** | config-absent defaults with nothing written; `hk new` labels from git basename; `ws focus` joins by number |
| G18 smoke-socket battery | CI | **PASS** | `nix flake check` green: herdr-kitten-build (py_compile + import audit + 66 units) and herdr-kitten-smoke (headless battery vs a live in-sandbox herdr built from the pinned input) |
| G-ssh remote tiers | conditional | **SKIP** | by design: SKIP-unless-sshd; exec targets covered by units; interactive ssh session is attended-only |

## Adversarial sweeps (this run)

- **Forbidden sweep F.1–F.15**: clean — no clipboard verb, no pty interposition, no
  scheduler shapes, no sleep/poll in interactive paths, focus moved only by `hk focus`,
  no pane-read in the fork path, `report-agent` only under `tests/`, no kitty tab verbs,
  niri behind `NIRI_SOCKET` with a zero-calls unit, no drain/handoff/pickup names, no Go,
  no third-party imports (unit-enforced), `agent prompt` only behind `--submit`
  (receipt: w3-forbidden-sweep.txt).
- **Liveness sweep**: every verb has a named caller (README quickstart/gesture table,
  a gate, or a documented contract); `--help` of every README-mentioned verb exits 0.
- **CI shape**: `.github/workflows/ci.yml` is exactly one job running `nix flake check`
  (spec 12.4).
- **Coverage**: `docs/mapping.md` carries all 79 census points; every day1-mechanical
  point maps to a shipped verb, gesture, or herdr-native path.

## Known SKIPs / HUMAN-ATTENDED remainder

Visual/UX confirmations that need human eyes (spec 5.5, 5.6, 6.2, 6.3, 8.7, 9.6, 9.7
visual placement, 10.3, 10.4, 10.7, U.1–U.3): the mechanisms are gate-proven above;
the *look and feel* sign-off is Tom's morning checklist (see the final STATUS entry).
