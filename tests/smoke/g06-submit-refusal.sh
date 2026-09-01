#!/bin/sh
# G6 — submit refusal (spec 4.2 / D25, gate row G6; census-map P16).
# `pane report-agent` here is a smoke FIXTURE — tests are the sole legal caller
# outside real agents and their installers (spec F.9).
# Probe P-EXTRA established the live shape: agent prompt against a blocked agent
# exits 1 with {"error":{"code":"agent_blocked",...}} on stderr.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G6 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")

herdr pane send-text "$pane" "$(printf 'cat -v\r')"
hk_wait_pane_shows "$pane" 'cat -v' 50 || gate_fail G6 "cat -v never started"

herdr pane report-agent "$pane" --source test:smoke --agent fake --state blocked >/dev/null

err=$SBX/g6.err
set +e
echo hi | hk send --submit "$pane" >"$SBX/g6.out" 2>"$err"
code=$?
set -e
[ "$code" -eq 1 ] || gate_fail G6 "expected exit 1, got $code (stderr: $(cat "$err"))"
grep -q "agent_blocked" "$err" || gate_fail G6 "server refusal not propagated verbatim: $(cat "$err")"

# zero bytes reached the pane: cat -v would have echoed `hi` had any arrived.
if hk_pane_visible "$pane" | grep -q '^hi$'; then gate_fail G6 "payload leaked into the pane despite refusal"; fi

gate_pass G6 "blocked refusal: exit 1, agent_blocked verbatim on stderr, zero bytes delivered"
