#!/bin/sh
# G4 — bracketed populate (spec 4.1, gate row G4; census-map P15).
# `pane send-text` is RAW (probe P-EXTRA): hk supplies \x1b[200~ / \x1b[201~
# itself, and nothing is submitted. `cat -v` makes the framing visible as
# ^[[200~ / ^[[201~ in the pane's own output, so the assertion reads the
# SERVER's view of the pane, never hk's echo of what it sent.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G4 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")

herdr pane send-text "$pane" "$(printf 'cat -v\r')"
hk_wait_pane_shows "$pane" 'cat -v' 50 || gate_fail G4 "cat -v never started"

printf 'two\nlines' | hk send "$pane" || gate_fail G4 "hk send failed"
hk_wait_pane_shows "$pane" '200~two' 50 || gate_fail G4 "payload never reached the pane"

out=$(hk_pane_visible "$pane")
echo "$out" | grep -q '\^\[\[200~two' || gate_fail G4 "no open bracket before payload: $out"
echo "$out" | grep -q 'lines\^\[\[201~' || gate_fail G4 "no close bracket after payload: $out"
# populate-only (spec F.14): cat -v renders a submitted Enter as ^M; the framed
# payload must carry none, and `lines` must still be the last thing sent.
if echo "$out" | grep -q '201~\^M'; then gate_fail G4 "an Enter was submitted after the payload"; fi

gate_pass G4 "payload framed ^[[200~ .. ^[[201~, populate-only, nothing submitted"
