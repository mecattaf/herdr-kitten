#!/bin/sh
# G11 — voice delivery (spec 5.1, gate G11). KITTY-ATTENDED.
. "$(dirname "$0")/lib.sh"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || gate_skip G11 "no display (kitty-attended gate)"
command -v kitty >/dev/null 2>&1 || gate_skip G11 "kitty not on PATH"
REAL_XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G11 "server did not start"
KSOCK=unix:$SBX/kitty.sock
trap 'hk_server_stop; XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all >/dev/null 2>&1 || true' EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
tid=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['terminal_id'])")
# echo stays ON: cat -v line-buffers, and the bracketed payload has no newline,
# so the tty echo is what makes the delivered bytes visible (this gate greps,
# it never counts, so the echo double-render is harmless).
herdr pane send-text "$pane" "$(printf 'cat -v\r')"
hk_wait_pane_shows "$pane" '\$ cat -v' 50 || gate_fail G11 "cat -v never started"
XDG_RUNTIME_DIR="$REAL_XRD" kitty -o allow_remote_control=yes --listen-on "$KSOCK" \
  --title hk-g11 -o "env=HERDR_SOCKET_PATH=$HERDR_SOCKET_PATH" \
  env HERDR_SOCKET_PATH="$HERDR_SOCKET_PATH" herdr terminal attach "$tid" >/dev/null 2>&1 &
hk_wait "XDG_RUNTIME_DIR='$REAL_XRD' kitty @ --to '$KSOCK' ls >/dev/null 2>&1" 50 || gate_fail G11 "kitty never came up"
win=$(XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" ls | hk_json "d=json.load(sys.stdin);print(d[0]['tabs'][0]['windows'][0]['id'])")
XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" set-user-vars --match "id:$win" hk_pane="$pane" hk_ws=w1 hk_role=herdr
XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" focus-window --match "id:$win" 2>/dev/null || true
sleep 1
out=$SBX/g11.out
code=0
printf 'dictated words' | KITTY_LISTEN_ON="$KSOCK" hk voice text >"$out" 2>&1 || code=$?
[ "$code" -eq 0 ] || gate_fail G11 "hk voice text exit $code: $(cat "$out")"
hk_wait_pane_shows "$pane" '200~dictated words' 50 || gate_fail G11 "payload never landed bracketed"
gate_pass G11 "dictation landed bracketed in the focused window's herdr pane, exit 0"
