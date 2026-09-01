# herdr-kitten: herdr is the kitty kitten

*(Announcement draft — posted by the maintainer at launch, alongside the repo going
public. Written to be pasteable as-is.)*

## What it is

herdr-kitten wires [herdr](https://github.com/herdrdev/herdr) and
[kitty](https://sw.kovidgoyal.net/kitty/) into one system: herdr's server owns every pane,
workspace, and agent; kitty windows are projection surfaces onto it. Two artifacts, both
Python, zero dependencies:

- **`hk`** — a stdlib-Python CLI where every verb is a socket/CLI join (open, run, send,
  read, rename, focus, materialise/dematerialise, ws, new, resume, ssh, voice, notifyd,
  doctor). No scheduler, no daemon beyond one event loop.
- **`hk.py`** — a kitty kitten dispatching four gestures (toggle / fork / scrollback /
  voice) with a <1ms budget on kitty's GUI thread.

## Why herdr under kitty

Closing a kitty window **detaches** — the pane and everything running in it survives on
the server (proven by the acceptance battery, not asserted). That one equivalence deletes
the whole class of watcher scripts terminal multiplexer setups accumulate. On top of it:

- **Bracketed populate-only text transport**: `hk send` frames stdin with real bracketed
  paste and never auto-submits; `hk send --submit` routes through `agent prompt`, which
  *refuses* a blocked agent with a real error instead of silently typing into it.
- **Agent state on your desktop**: direct-attach herdr clients get no notifications;
  `hk notifyd` closes that gap with one events.subscribe loop -> notify-send (or whatever
  you configure) + window user-var mirrors.
- **Slash-fork**: a blank nvim OS window; `:w` delivers the buffer into the target pane
  (append-only saves deliver just the suffix; `:q!` delivers nothing). The buffer starts
  blank by doctrine — it never scrapes your agent's draft.
- **Workspace projection**: `hk materialise` turns a herdr workspace into one kitty OS
  window per pane; closing them all changes nothing server-side.
- **Two honest remote tiers**: `hk ssh` (herdr thin client, virtual tabs inside one
  window) or `hk ssh --plain` (pure `kitten ssh`, herdr-free).

## What works day 1

Every mechanical row of the 79-point kitty<->herdr integration census ships as a verb,
gesture, or documented native path — the full table is in
[`docs/mapping.md`](docs/mapping.md), including what is deliberately out of scope and why.
The acceptance battery (18 gates, headless subset in CI against a live herdr server) is
committed as `docs/acceptance-run.md`.

## Install

```sh
git clone https://github.com/mecattaf/herdr-kitten && cd herdr-kitten && ./install.sh
```

or with nix: `nix run github:mecattaf/herdr-kitten` — CI is exactly one gate:
`nix flake check` (build + smoke battery against a live headless herdr).

Floors: kitty >= 0.47.1, herdr >= 0.8.2 (wire protocol 21), Python >= 3.11, nvim for fork.
