#!/bin/sh
# G15 — join keys both directions (spec 2.1/2.2/3.1/9.3, gate row G15; P01-P04).
#
# SOCKET HALF, headless. KITTY_WINDOW_ID / KITTY_LISTEN_ON are exported exactly
# as kitty exports them to a child, so `hk open` takes the same code path it
# takes inside a real window. The kitty half of the join (`set-user-vars` on the
# outer window) cannot land without a kitty to talk to and is asserted in the
# attended battery; what IS asserted here is the half that lives on the server:
# all three tokens under source user:hk, with ttl_ms and seq omitted (D16).
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G15 "server did not start"
trap hk_server_stop EXIT

export KITTY_WINDOW_ID=77
export KITTY_LISTEN_ON=unix:$SBX/kitty.sock

pane=$(hk open --print 2>"$SBX/g15.warn") || gate_fail G15 "hk open failed: $(cat "$SBX/g15.warn")"
[ -n "$pane" ] || gate_fail G15 "hk open printed no pane id"
# kitty unreachable must degrade the surface tier only, never fail the verb
grep -q "kitty user-vars not set" "$SBX/g15.warn" \
  || gate_fail G15 "expected a warning about the unreachable kitty, got: $(cat "$SBX/g15.warn")"

toks=$SBX/g15.tokens
herdr pane get "$pane" | hk_json "
d=json.load(sys.stdin)['result']['pane']
t=d.get('tokens',{})
print('hk_role=%s' % t.get('hk_role',''))
print('kitty_win=%s' % t.get('kitty_win',''))
print('kitty_sock=%s' % t.get('kitty_sock',''))
" > "$toks"
grep -qx 'hk_role=herdr' "$toks" || gate_fail G15 "hk_role token missing: $(cat "$toks")"
grep -qx 'kitty_win=77' "$toks" || gate_fail G15 "kitty_win token missing: $(cat "$toks")"
grep -qx "kitty_sock=unix:$SBX/kitty.sock" "$toks" || gate_fail G15 "kitty_sock token missing: $(cat "$toks")"

# spec 9.3: joining an existing workspace creates no new one
n=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print(len(d['result']['workspaces']))")
hk open --print >/dev/null 2>&1 || gate_fail G15 "second hk open failed"
n2=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print(len(d['result']['workspaces']))")
[ "$n2" -eq "$n" ] || gate_fail G15 "hk open created a workspace ($n -> $n2); it must join (spec 9.3)"

# the other direction of the join: herdr injects HERDR_PANE_ID into the pane env
herdr pane send-text "$pane" "$(printf 'echo PANEENV=$HERDR_PANE_ID\r')"
hk_wait_pane_shows "$pane" "PANEENV=$pane" 50 || gate_fail G15 "HERDR_PANE_ID absent from the pane env"

gate_pass G15 "socket half: kitty_win/kitty_sock/hk_role under user:hk, HERDR_PANE_ID live in the pane, no workspace created (kitty user-var half attended)"
