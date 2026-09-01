#!/bin/sh
# G1 — headless server liveness (spec gate row G1). REAL since scaffold.
. "$(dirname "$0")/lib.sh"
hk_sandbox
hk_server_start || gate_fail G1 "server did not come up"
out=$(herdr workspace list) || { hk_server_stop; gate_fail G1 "workspace list nonzero"; }
hk_server_stop
echo "$out" | grep -q '"type":"workspace_list"' || gate_fail G1 "no workspace_list JSON: $out"
gate_pass G1 "server up, workspace list JSON ok"
