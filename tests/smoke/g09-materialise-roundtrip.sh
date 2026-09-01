#!/bin/sh
# G9 — materialise round-trip, SOCKET HALF (spec 3.4/3.5/3.6/7.3/9.4, gate row G9).
#
# The gate row's window assertions ("3 OS windows appear", "each titled with
# beta") need a live kitty and run in the attended battery. What is provable
# headless — and is asserted here — is everything on the herdr side of the
# projection: the workspace rename, the token lifecycle that dematerialise
# owns, and the three-way focus boundary of D6.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G9 "server did not start"
trap hk_server_stop EXIT

ws=$(herdr workspace create --cwd "$SBX" | hk_json "d=json.load(sys.stdin);print(d['result']['workspace']['workspace_id'])")
p1=$(herdr pane list --workspace "$ws" | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
herdr pane split "$p1" --direction down >/dev/null
herdr pane split "$p1" --direction right >/dev/null
count=$(herdr pane list --workspace "$ws" | hk_json "d=json.load(sys.stdin);print(len(d['result']['panes']))")
[ "$count" -eq 3 ] || gate_fail G9 "expected 3 panes, got $count"

# --- materialise without a kitty: refuse loudly, project nothing -------------
set +e
mat_err=$SBX/g9.mat.err
hk materialise "$ws" >/dev/null 2>"$mat_err"; mat_code=$?
set -e
[ "$mat_code" -ne 0 ] || gate_fail G9 "materialise with no kitty should exit nonzero"
[ "$(wc -l < "$mat_err")" -eq 1 ] || gate_fail G9 "expected one line of reason, got: $(cat "$mat_err")"

# --- hk ws rename: durable on the herdr side, fan-out on the kitty side ------
hk ws rename "$ws" beta || gate_fail G9 "hk ws rename failed"
label=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print([w for w in d['result']['workspaces'] if w['workspace_id']=='$ws'][0].get('label',''))")
[ "$label" = "beta" ] || gate_fail G9 "ws label is '$label', want beta"

# --- hk focus (spec 3.6 / D6): no kitty_win token -> nonzero, one line -------
set +e
focus_err=$SBX/g9.focus.err
hk focus "$p1" >/dev/null 2>"$focus_err"; focus_code=$?
set -e
[ "$focus_code" -ne 0 ] || gate_fail G9 "hk focus with no kitty_win token must exit nonzero"
[ "$(wc -l < "$focus_err")" -eq 1 ] || gate_fail G9 "hk focus should print one line, got: $(cat "$focus_err")"

# --- dematerialise: stale tokens tolerated, cleared, panes all survive -------
# A kitty_win whose window is gone is the NORMAL post-restart state (D16:
# tokens die with the server), so dematerialise must clear it rather than trip.
herdr pane report-metadata "$p1" --source user:hk --token kitty_win=4242 \
  --token kitty_sock=unix:/nonexistent >/dev/null
hk dematerialise "$ws" >/dev/null || gate_fail G9 "dematerialise failed on a stale token"
after=$(herdr pane list --workspace "$ws" | hk_json "d=json.load(sys.stdin);print(len(d['result']['panes']))")
[ "$after" -eq 3 ] || gate_fail G9 "pane died during dematerialise ($after/3)"
left=$(herdr pane get "$p1" | hk_json "d=json.load(sys.stdin);print(d['result']['pane'].get('tokens',{}).get('kitty_win',''))")
[ -z "$left" ] || gate_fail G9 "stale kitty_win survived dematerialise (got '$left')"

gate_pass G9 "socket half: 3 panes, ws rename durable, focus refuses without a token, dematerialise clears stale tokens and every pane survives"
