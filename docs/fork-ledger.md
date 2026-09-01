# Fork ledger — herdr niceties reserved for a later fork or patchset

Sorting heuristic (ADDENDUM, 2026-09-01, #284 comment 5498332341): quasi-mechanical inside
dotfiles/herdr-kitten -> build now; requires tweaks outside those -> this ledger.
A ledger, not work; nothing here blocks S1-S6.

| nicety | today's state | why it needs the fork |
| --- | --- | --- |
| kitty graphics passthrough | `experimental.kitty_graphics` default false; partial | full fidelity needs VT-layer work in herdr |
| OSC 52 read (clipboard->pane) | terminated at herdr's vendored VT | policy + VT change upstream |
| OSC 133 prompt marks through panes | not forwarded; kitty-scrollback stays inert inside herdr panes | VT forwarding change |
| pane-emitted OSC 1337 SetUserVar | stops at the VT binding (probe P-G10 re-proved it live) | forwarding change |
| xterm extras (per census AMBIGUOUS rows) | absent | enumerate at fork time from the census |
| global agent-status event subscription | `pane.agent_status_changed` requires `pane_id` per subscription; one request line per connection (probe discovery 1) | server-side wildcard subscription variant |
