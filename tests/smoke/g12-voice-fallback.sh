#!/bin/sh
# G12 — voice fallback (spec 5.2 / D9, gate G12). KITTY-ATTENDED.
. "$(dirname "$0")/lib.sh"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || gate_skip G12 "no display (kitty-attended gate)"
command -v kitty >/dev/null 2>&1 || gate_skip G12 "kitty not on PATH"
REAL_XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G12 "server did not start"
KSOCK=unix:$SBX/kitty.sock
trap 'hk_server_stop; XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all >/dev/null 2>&1 || true' EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
herdr pane send-text "$pane" "$(printf 'cat -v\r')"
# a PLAIN kitty window (no user-vars, plain shell), focused
XDG_RUNTIME_DIR="$REAL_XRD" kitty -o allow_remote_control=yes --listen-on "$KSOCK" --title hk-g12 sh -c 'sleep 600' >/dev/null 2>&1 &
hk_wait "XDG_RUNTIME_DIR='$REAL_XRD' kitty @ --to '$KSOCK' ls >/dev/null 2>&1" 50 || gate_fail G12 "kitty never came up"
sleep 1
code=0
printf 'x' | KITTY_LISTEN_ON="$KSOCK" hk voice text >"$SBX/g12.out" 2>&1 || code=$?
[ "$code" -eq 3 ] || gate_fail G12 "expected exit 3, got $code: $(cat "$SBX/g12.out")"
sleep 1
if hk_pane_visible "$pane" | grep -q '^x$'; then gate_fail G12 "bytes leaked into a pane"; fi
gate_pass G12 "plain focused window -> exit 3, zero bytes delivered"
