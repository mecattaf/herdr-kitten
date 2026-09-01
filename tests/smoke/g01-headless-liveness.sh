#!/bin/sh
# G1 — headless server liveness (spec gate row G1). REAL since scaffold.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G1 "server did not come up"
trap hk_server_stop EXIT
out=$(herdr workspace list) || gate_fail G1 "workspace list nonzero"
echo "$out" | grep -q '"type":"workspace_list"' || gate_fail G1 "no workspace_list JSON: $out"

# spec 1.5 rides this gate: against a reachable server, doctor reports both
# version floors (D19), the wire protocol, and the socket, and exits 0.
doc=$SBX/g1.doctor
hk doctor >"$doc" 2>&1 || gate_fail G1 "hk doctor exited nonzero: $(cat "$doc")"
grep -q "^socket: .*\[reachable\]" "$doc" || gate_fail G1 "doctor did not see the live socket: $(cat "$doc")"
grep -q "^protocol: client 21 / server 21 \[ok\]" "$doc" || gate_fail G1 "doctor did not report wire protocol 21: $(cat "$doc")"
grep -q "^herdr: .*\[ok\]" "$doc" || gate_fail G1 "doctor did not clear the herdr version floor: $(cat "$doc")"
# the kitty tier is reported either way; "absent" is a real answer, not a failure
grep -qE "^kitty: .*\[(ok|absent)\]" "$doc" || gate_fail G1 "doctor did not report the kitty tier: $(cat "$doc")"
grep -q "^predicate:" "$doc" || gate_fail G1 "doctor omitted the predicate line: $(cat "$doc")"

gate_pass G1 "server up, workspace list JSON ok, doctor reports protocol 21 + floors + socket"
