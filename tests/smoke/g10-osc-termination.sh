#!/bin/sh
# G10 — OSC termination (spec 2.5, gate G10; census P06/§0). KITTY-ATTENDED.
# An OSC 1337 SetUserVar emitted INSIDE a herdr pane must never surface as a
# user-var on the outer kitty window (herdr's VT layer terminates it).
. "$(dirname "$0")/lib.sh"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || gate_skip G10 "no display (kitty-attended gate)"
command -v kitty >/dev/null 2>&1 || gate_skip G10 "kitty not on PATH"
REAL_XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G10 "server did not start"
KSOCK=unix:$SBX/kitty.sock
trap 'hk_server_stop; XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all >/dev/null 2>&1 || true' EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
tid=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['terminal_id'])")
XDG_RUNTIME_DIR="$REAL_XRD" kitty -o allow_remote_control=yes --listen-on "$KSOCK" --title hk-g10 \
  env HERDR_SOCKET_PATH="$HERDR_SOCKET_PATH" herdr terminal attach "$tid" >/dev/null 2>&1 &
hk_wait "XDG_RUNTIME_DIR='$REAL_XRD' kitty @ --to '$KSOCK' ls >/dev/null 2>&1" 50 || gate_fail G10 "kitty never came up"
sleep 1
# emit OSC 1337 SetUserVar INSIDE the pane (value aGk= is base64 "hi")
herdr pane send-text "$pane" "$(printf 'printf "\\033]1337;SetUserVar=hkprobe=aGk=\\007"\r')"
sleep 2
vars=$(XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" ls | hk_json "d=json.load(sys.stdin);print(sum((list((w.get('user_vars') or {}).keys()) for osw in d for t in osw['tabs'] for w in t['windows']), []))")
case "$vars" in *hkprobe*) gate_fail G10 "OSC 1337 leaked through: $vars";; esac
gate_pass G10 "pane-emitted OSC 1337 terminated at herdr's VT; outer window vars: $vars"
