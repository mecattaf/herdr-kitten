#!/bin/sh
# G4 — populate-only delivery (spec 4.1, gate row G4; census-map P15).
#
# REWRITTEN in round2-04. This gate used to assert that `cat -v` shows literal
# ^[[200~ / ^[[201~ around the payload — i.e. it asserted BUG-8. hk hand-framed
# every send, so a program that never enabled bracketed paste was typed full of
# escape junk. Delivery now rides `pane.send_input` and herdr frames iff the
# pane runtime asked for it; `cat -v` does not, so the CORRECT observation is
# clean text and no escapes at all.
#
# Receipt from the live probe that drove the change:
#   pane.send_input "HELLO-INPUT"                    -> pane shows HELLO-INPUT
#   pane.send_text  "<ESC>[200~HAND-FRAMED<ESC>[201~" -> pane shows
#                                                       ^[[200~HAND-FRAMED^[[201~
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G4 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")

herdr pane send-text "$pane" "$(printf 'stty -echo; cat -v\r')"
hk_wait_pane_shows "$pane" 'cat -v' 50 || gate_fail G4 "cat -v never started"

printf 'two\nlines' | hk send "$pane" || gate_fail G4 "hk send failed"
hk_wait_pane_shows "$pane" '^two$' 50 || gate_fail G4 "payload never reached the pane"

out=$(hk_pane_visible "$pane")
# 1. BUG-8: no paste-bracket escape may be TYPED into a program that never
#    enabled bracketed paste. This is the assertion that would have caught it.
if echo "$out" | grep -q '\^\[\[20[01]~'; then
  gate_fail G4 "hand-framed escapes leaked into a plain program (BUG-8): $out"
fi
# 2. populate-only (spec F.14), asserted the strong way: the payload has no
#    trailing newline, so `lines` is still sitting in the pty's line buffer.
#    If ANY code path had appended a submission, cat -v would have flushed it.
if echo "$out" | grep -q '^lines$'; then
  gate_fail G4 "something was submitted after the payload (line flushed): $out"
fi
# 3. and the buffered bytes are intact: one raw newline flushes them verbatim.
printf '\n' | hk send --raw "$pane" || gate_fail G4 "hk send --raw failed"
hk_wait_pane_shows "$pane" '^lines$' 50 \
  || gate_fail G4 "buffered payload was not delivered byte-intact: $(hk_pane_visible "$pane")"

# 4. --raw is byte-transparent by contract, so IT may carry escapes through
printf 'RAWMARK\033[201~\n' | hk send --raw "$pane" || gate_fail G4 "hk send --raw failed"
hk_wait_pane_shows "$pane" 'RAWMARK' 50 || gate_fail G4 "raw payload never arrived"
hk_pane_visible "$pane" | grep -q 'RAWMARK\^\[\[201~' \
  || gate_fail G4 "--raw altered the bytes: $(hk_pane_visible "$pane")"

gate_pass G4 "framing delegated to herdr (no escapes typed into a plain program), populate-only, --raw byte-transparent"
