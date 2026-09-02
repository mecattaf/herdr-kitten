#!/bin/sh
# G14 — fork round-trip (spec 11.1-11.5, gate G14; census-map P68-P73).
# Drives assets/fork.lua in a scripted headless nvim against a cat -v pane:
#   run 1: write two paragraphs, :w (whole buffer, bracketed), append a third,
#          :w (suffix only), :q
#   run 2: :q! with text -> zero bytes delivered
# Needs `hk` (send path) and nvim >= 0.10 on PATH.
. "$(dirname "$0")/lib.sh"
command -v nvim >/dev/null 2>&1 || gate_skip G14 "nvim not on PATH"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G14 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
# stty -echo: the pty would otherwise echo every delivered byte a second time
herdr pane send-text "$pane" "$(printf 'stty -echo; cat -v\r')"
hk_wait_pane_shows "$pane" 'cat -v' 50 || gate_fail G14 "cat -v never started"

export HK_FORK_PANE="$pane" HK_FORK_ASSETS="$REPO_ROOT/assets"
# run 1: first save = whole buffer; append-only second save = suffix; :q
nvim --headless --cmd "luafile $REPO_ROOT/assets/fork.lua" \
  -c 'call setline(1,["para one","","para two"])' -c 'w' \
  -c 'call append(line("$"),["para three"])' -c 'w' -c 'q' 2>"$SBX/g14-run1.err" \
  || gate_fail G14 "nvim run1 failed: $(cat "$SBX/g14-run1.err")"
hk_wait_pane_shows "$pane" 'para three' 50 || gate_fail G14 "deliveries never arrived"
out=$(hk_pane_visible "$pane")
# round2-04: framing is herdr's, and it is runtime-aware, so a `cat -v` pane
# receives clean text. The assertions are about WHAT was delivered and HOW MANY
# TIMES, which is what the gate was really protecting.
echo "$out" | grep -q '^para one$' || gate_fail G14 "first save did not deliver the whole buffer: $out"
echo "$out" | grep -q '^para two$' || gate_fail G14 "first save truncated: $out"
echo "$out" | grep -q '^para three$' || gate_fail G14 "suffix save not delivered: $out"
if echo "$out" | grep -q '\^\[\[20[01]~'; then
  gate_fail G14 "hand-framed escapes leaked into a plain program (BUG-8): $out"
fi
count=$(echo "$out" | grep -c '^para one$')
[ "$count" -eq 1 ] || gate_fail G14 "para one delivered $count times (suffix save leaked the whole buffer)"

# run 2: :q! with text delivers NOTHING
nvim --headless --cmd "luafile $REPO_ROOT/assets/fork.lua" \
  -c 'call setline(1,["ghost text"])' -c 'q!' 2>/dev/null
sleep 1
if hk_pane_visible "$pane" | grep -q 'ghost text'; then
  gate_fail G14 ":q! delivered bytes"
fi
gate_pass G14 "whole-buffer then suffix-only, no escape junk typed, :q! delivered nothing"
