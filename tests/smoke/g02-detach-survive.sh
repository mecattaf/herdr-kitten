#!/bin/sh
# G2 — detach-survive through the toggle path (spec 3.2/10.6, gate G2;
# probe P-G2 proved the raw close). KITTY-ATTENDED: needs a live display.
. "$(dirname "$0")/lib.sh"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || gate_skip G2 "no display (kitty-attended gate)"
command -v kitty >/dev/null 2>&1 || gate_skip G2 "kitty not on PATH"
REAL_XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G2 "server did not start"
trap 'hk_server_stop; XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all >/dev/null 2>&1 || true' EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
tid=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['terminal_id'])")
KSOCK=unix:$SBX/kitty.sock
XDG_RUNTIME_DIR="$REAL_XRD" kitty --title hk-g2 -o allow_remote_control=yes --listen-on "$KSOCK" \
  env HERDR_SOCKET_PATH="$HERDR_SOCKET_PATH" herdr terminal attach "$tid" >/dev/null 2>&1 &
KPID=$!
hk_wait "XDG_RUNTIME_DIR='$REAL_XRD' kitty @ --to '$KSOCK' ls >/dev/null 2>&1" 50 || gate_fail G2 "kitty never came up"
# start the survivor inside the pane
herdr pane send-text "$pane" "$(printf 'sleep 9999 &\recho PID=$! > %s/g2.pid\r' "$SBX")"
hk_wait "[ -f $SBX/g2.pid ]" 50 || gate_fail G2 "survivor never started"
spid=$(cut -d= -f2 "$SBX/g2.pid")
# close the kitty OS window (the toggle CLOSE action is boss.mark_window_for_close;
# remote close-window is the same code path from outside)
XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all || gate_fail G2 "close failed"
sleep 2
herdr pane list | grep -q "\"$pane\"" || gate_fail G2 "pane died with the window"
kill -0 "$spid" 2>/dev/null || gate_fail G2 "survivor process $spid died"
gate_pass G2 "kitty window closed; pane $pane and pid $spid survived (close IS detach)"
