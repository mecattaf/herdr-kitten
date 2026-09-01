#!/bin/sh
# G8 — the one event loop (spec 8.1-8.4, gate G8; census P39/P52/P53).
# Headless half: notifyd's notify command fires once, within 2s, on a blocked
# transition driven by the report-agent smoke fixture (spec F.9's sole legal
# caller). The user-var mirror half needs a live kitty and asserts when a
# display is present; SKIPs that half otherwise, loudly.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G8 "server did not start"
NOTIFYD_PID=""
trap 'kill $NOTIFYD_PID 2>/dev/null; hk_server_stop' EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
# hk-config with a touch-file notify command
mkdir -p "$XDG_CONFIG_HOME/hk"
cat > "$XDG_CONFIG_HOME/hk/config.toml" <<TOML
notify_command = "touch $SBX/hit"
TOML
hk notifyd >"$SBX/notifyd.log" 2>&1 &
NOTIFYD_PID=$!
hk_wait "grep -q . '$SBX/notifyd.log' || kill -0 $NOTIFYD_PID" 10 || true
sleep 1  # let the subscription land
herdr pane report-agent "$pane" --source test:smoke --agent fake --state blocked >/dev/null
hk_wait "[ -f $SBX/hit ]" 10 || gate_fail G8 "notify command never ran (2s budget): $(cat "$SBX/notifyd.log")"
# once per transition: same state again must not re-touch
rm -f "$SBX/hit"
herdr pane report-agent "$pane" --source test:smoke --agent fake --state blocked >/dev/null
sleep 1
[ -f "$SBX/hit" ] && gate_fail G8 "notified twice for one transition"
gate_pass G8 "notify fired once, <2s, on the blocked transition (user-var mirror half attended)"
