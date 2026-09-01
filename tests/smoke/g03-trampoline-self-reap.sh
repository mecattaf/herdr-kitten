#!/bin/sh
# G3 — trampoline self-reap (spec 3.3, gate row G3; census-map P10/P14; probe P-G3).
#
# Two assertions, both artifacts only the trampoline could produce:
#   1. the payload REALLY EXECUTED inside the pane (marker file written by it),
#      so a pane that merely died cannot pass;
#   2. the pane is gone after the payload exits (RuntimeExitAction::ClosePane),
#      so a payload that ran under a surviving shell cannot pass either.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G3 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
before=$(hk_pane_count)

marker=$SBX/g3.ran
pane=$(hk run -- sh -c "echo trampolined > $marker") || gate_fail G3 "hk run failed"
[ -n "$pane" ] || gate_fail G3 "hk run printed no pane id"

hk_wait "[ -f $marker ]" 50 || gate_fail G3 "payload never ran: HK_EXEC not decoded/exec'd"
grep -q trampolined "$marker" || gate_fail G3 "marker present but wrong content"

# spec G3: absent within 2s of payload exit; 5s of slack for a loaded machine.
hk_wait '[ "$(hk_pane_count)" -le "'"$before"'" ]' 25 \
  || gate_fail G3 "pane $pane not reaped (count $(hk_pane_count) > $before)"
if herdr pane list | grep -q "\"$pane\""; then gate_fail G3 "pane $pane still listed"; fi

gate_pass G3 "payload exec'd via HK_EXEC and pane $pane reaped on its exit"
