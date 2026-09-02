# herdr-kitten

**herdr IS the kitty kitten.** [herdr](https://github.com/herdrdev/herdr)'s server owns
every pane, workspace, and agent; [kitty](https://sw.kovidgoyal.net/kitty/) windows are
projection surfaces onto it. Two artifacts, both stdlib Python, zero dependencies, zero
build step:

- **`hk`** — the CLI. Every verb is a socket/CLI join, never a scheduler.
- **`hk.py`** — the kitten. Four gestures on kitty's GUI thread with a <1ms budget.

The load-bearing physics: **closing a kitty window detaches** — the pane and everything
running in it survives on the server (gate G2 in the acceptance battery proves it live).

## Install

### nix

```sh
nix run github:mecattaf/herdr-kitten -- doctor     # try it
nix profile install github:mecattaf/herdr-kitten   # keep it
```

### install.sh (any host with kitty >= 0.47.1 and Python >= 3.11)

```sh
git clone https://github.com/mecattaf/herdr-kitten
cd herdr-kitten && ./install.sh
```

Copies `hk` to `~/.local/bin`, the kitten + assets to `~/.config/kitty/`, and the config
template to `~/.config/hk/config.toml` (only if absent — nothing of yours is overwritten).
Merge `conf/herdr-profile.toml` into your `~/.config/herdr/config.toml` BY HAND — hk never
writes herdr's config.

For `hk run` self-reaping panes, source the trampoline from your shell rc:
`. ~/.config/kitty/hk-assets/hk-trampoline.sh`

## Quickstart

```sh
hk doctor          # versions, socket reachability, predicate for this window
hk new             # new workspace (named after your git repo) + kitty window attached
hk open            # get-or-create a pane in this window's workspace and attach
hk resume          # picker over detached panes (terminal_id / label / agent status)
hk run -- make -j  # self-reaping pane: the pane closes when make exits
echo hi | hk send <pane>          # bracketed populate — never auto-submits
echo hi | hk send --submit <pane> # routes agent prompt; a blocked agent REFUSES (exit 1)
hk read <pane>     # scrollback read (server caps at 1000 lines; hk tells you on stderr)
hk rename <pane> alpha  # one verb, three tiers: durable label + live title + kitty title
hk materialise <ws>     # one kitty OS window per pane of the workspace
hk dematerialise <ws>   # close those windows; every pane survives
```

## Gestures

Suggested maps ship in [`conf/kitty-maps.conf`](conf/kitty-maps.conf)
(include it from kitty.conf; chords are suggestions, not law):

| chord | gesture | behavior |
|---|---|---|
| `ctrl+b` | toggle | thin client -> forward the prefix; herdr window -> prefix; plain window -> open a herdr vsplit; from that split -> close it (close IS detach) |
| `ctrl+shift+g` | fork | blank nvim OS window targeting this window's pane (see below) |
| `ctrl+shift+h` | scrollback | herdr window -> herdr's uncapped scrollback-in-$EDITOR; plain window -> your `plain_scrollback_action` (default kitty scrollback) |

### Slash-fork

`fork` opens a **blank** nvim in a kitty OS window of class `hk-fork`. Every `:w` delivers:
the first save sends the whole buffer (bracketed, populate-only), an append-only save sends
just the suffix, an edit inside already-delivered text sends nothing and notifies, and
`:q!` or a crash sends nothing at all. The buffer starts blank by doctrine — the fork path
never reads your agent's draft. `--submit` is the only path that presses Enter. Requires
nvim.

## Voice (the caller contract)

Dictation tools call three verbs; the hold-to-talk binding is YOUR territory, not hk's:

```sh
hk voice begin --window <kitty-window-id>   # recording spinner, bottom-right, non-destructive
... | hk voice text [--submit]              # deliver into the focused window's herdr pane
hk voice end --window <kitty-window-id>     # spinner off
```

Exit codes: `0` delivered · `1` herdr error · `2` usage · **`3` the focused window is not a
herdr client — zero bytes were sent; fall back to compositor-level injection.**

## Agent surfacing

`hk notifyd` is the repo's one event loop: it subscribes to herdr's socket events and
(a) runs your `notify_command` (default `notify-send`) once per agent blocked/done
transition, (b) mirrors agent status into the window's `hk_status` user-var for your
compositor/bar to consume. An example systemd user unit ships in
[`contrib/hk-notifyd.service`](contrib/hk-notifyd.service) — installed by nobody
automatically.

For Claude Code lifecycle reporting, use `herdr integration install claude` — **note it
writes the agent's own settings file**; hk hand-rolls no agent hooks.

## Remote

- `hk ssh <host>` — one kitty window running herdr's thin client
  (`herdr --remote <host> --remote-keybindings server`); tabs are herdr's, virtual, inside
  that window.
- `hk ssh --plain <host>` — pure `kitten ssh`: terminfo upload, ControlMaster, shell
  integration. Herdr-free by design.
- `hk --host <h> <verb>` — run the herdr side of any verb over ssh; kitty calls stay local.

## Configuration

ONE file: `~/.config/hk/config.toml` (template: [`conf/config.toml`](conf/config.toml)).
Missing file = built-in defaults, nothing written. Keys: `plain_scrollback_action`,
`notify_command`.

## Limitations

Everything deferred by the initial build is filed and indexed:
[the deferred-ledger index](https://github.com/mecattaf/herdr-kitten/issues/14)
maps every open issue back to its ledger line.


- **1000-line read cap**: `hk read` is server-capped at 1000 lines regardless of the ask
  (hk prints a notice; herdr does not). The uncapped path is the scrollback gesture.
  Upstream ask drafted.
- **One server**: a herdr crash takes every pane; snapshot restore recovers layout and
  cwd, not processes (`session.resume_agents_on_restore = true` re-invokes agents with
  native integrations). Upgrades: `herdr server live-handoff`.
- **Thin-client file-pick gap**: pre-existing and open — a remote pane cannot hand a
  local picker a file path. Restated here so it is not silently absorbed.
- **`TERM=xterm-256color` inside panes** (herdr hardcodes it), even under kitty.
- **recent* read sources lag young panes**: `pane read --source recent/recent-unwrapped`
  returns nothing until output has scrolled past the viewport; `--source visible` is
  live immediately.
- **Graphics stay gated**: `experimental.kitty_graphics = false` in the shipped snippet;
  see `docs/mapping.md` J-section for the flip condition.

## Version floors

kitty >= 0.47.1 · herdr >= 0.8.2 (wire protocol 21) · Python >= 3.11 · nvim (fork only)

## The evidence

- [`docs/mapping.md`](docs/mapping.md) — all 79 census points of the kitty<->herdr
  integration, each with its repo disposition.
- [`docs/dev/acceptance-run.md`](docs/dev/acceptance-run.md) — the G1-G18 gate battery results.
- [`docs/probe-report.md`](docs/probe-report.md) — the ground-truth probes this design
  was corrected against.
- [`docs/fork-ledger.md`](docs/fork-ledger.md) / [`docs/upstream.md`](docs/upstream.md) —
  what needs herdr itself to change, reserved, with ready-to-file asks.

## License

MIT — see [`LICENSE`](LICENSE). Copyright (c) 2026 Thomas Mecattaf.
