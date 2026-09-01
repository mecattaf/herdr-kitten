#!/bin/sh
# G13 — spinner set/clear (spec 5.4 / D8, gate G13). KITTY-ATTENDED.
. "$(dirname "$0")/lib.sh"
[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] || gate_skip G13 "no display (kitty-attended gate)"
command -v kitty >/dev/null 2>&1 || gate_skip G13 "kitty not on PATH"
REAL_XRD=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
hk_sandbox; hk_sandbox_shell
KSOCK=unix:$SBX/kitty.sock
trap 'XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" close-window --match all >/dev/null 2>&1 || true' EXIT
XDG_RUNTIME_DIR="$REAL_XRD" kitty -o allow_remote_control=yes --listen-on "$KSOCK" --title hk-g13 sh -c 'sleep 600' >/dev/null 2>&1 &
hk_wait "XDG_RUNTIME_DIR='$REAL_XRD' kitty @ --to '$KSOCK' ls >/dev/null 2>&1" 50 || gate_fail G13 "kitty never came up"
win=$(XDG_RUNTIME_DIR="$REAL_XRD" kitty @ --to "$KSOCK" ls | hk_json "d=json.load(sys.stdin);print(d[0]['tabs'][0]['windows'][0]['id'])")
KITTY_LISTEN_ON="$KSOCK" hk voice begin --window "$win" || gate_fail G13 "voice begin failed"
KITTY_LISTEN_ON="$KSOCK" hk voice end --window "$win" || gate_fail G13 "voice end failed"
gate_pass G13 "spinner begin/end both exit 0; begin-then-end leaves no logo"
