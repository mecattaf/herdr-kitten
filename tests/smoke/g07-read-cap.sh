#!/bin/sh
# G7 — read cap surfaced (spec 6.1, gate row G7; census-map P21).
# Probe P-G7: 2000 lines generated, `--lines 5000` returned 999 and herdr
# emitted NO notice of its own — the notice is hk's obligation.
# The read under test is the spec'd one: --source recent-unwrapped --format ansi.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G7 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")

herdr pane send-text "$pane" "$(printf 'seq 2000\r')"
hk_wait "hk_pane_recent $pane | grep -qx 2000" 75 || gate_fail G7 "seq output never arrived"

out=$SBX/g7.out; err=$SBX/g7.err
hk read "$pane" --lines 5000 >"$out" 2>"$err" || gate_fail G7 "hk read failed: $(cat "$err")"

count=$(wc -l < "$out")
[ "$count" -le 1000 ] || gate_fail G7 "got $count lines (> the 1000 cap)"
[ "$count" -gt 100 ] || gate_fail G7 "got only $count lines — the read did not reach the cap"
grep -q "caps pane reads at 1000" "$err" || gate_fail G7 "no cap notice on stderr: $(cat "$err")"
# the notice is on stderr, never mixed into the payload on stdout
if grep -q "caps pane reads" "$out"; then gate_fail G7 "cap notice leaked into stdout"; fi

# and a read that stays under the cap says nothing (the notice is a signal, not noise)
quiet=$SBX/g7.quiet
hk read "$pane" --lines 10 >/dev/null 2>"$quiet" || gate_fail G7 "small hk read failed"
if grep -q "caps pane reads" "$quiet"; then gate_fail G7 "cap notice fired on an uncapped read"; fi

gate_pass G7 "returned $count lines (<=1000) with the cap notice on stderr only"
