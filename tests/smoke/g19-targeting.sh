#!/bin/sh
# G19 — targeting parity (RULING-kitten.md §1 rows T13/T14/T15, round2-05 / #19).
#
# Four claims, against a live herdr server:
#   1. HERDR_ENV=1 + HERDR_PANE_ID -> `hk send --current` delivers to THAT pane.
#   2. HERDR_ENV unset, HERDR_PANE_ID still set and still valid -> one typed
#      line, exit 2 or 3, and ZERO BYTES reach the pane. This is the gate's
#      teeth: without the precondition hk resolves HERDR_PANE_ID happily and the
#      marker lands, so deleting the precondition turns this gate red.
#   3. a live agent name resolves to its pane and the payload arrives there.
#   4. a dead agent name fails typed — one line, no traceback, nothing sent.
#
# Absence is never asserted on a timer. After each refusal the gate pushes a
# barrier marker down the SAME ordered socket and waits for it; anything the
# refusal had leaked would already be on screen behind it.
#
# `pane report-agent` is a smoke FIXTURE here, exactly as in G6: tests are the
# sole legal caller outside real agents and their installers (spec F.9).
#
# MEASURED live in this lane against herdr 0.8.2 / protocol 21: a managed pane's
# environment carries HERDR_ENV=1, HERDR_PANE_ID=w1:p1, HERDR_WORKSPACE_ID=w1,
# HERDR_TAB_ID=w1:t1 — so the variables this gate sets by hand are the ones
# herdr itself injects, and the gate invents no contract.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G19 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")

# A reader that echoes what it is given and never enables bracketed paste.
herdr pane send-text "$pane" "$(printf 'stty -echo; cat -v\r')"
hk_wait_pane_shows "$pane" 'cat -v' 50 || gate_fail G19 "cat -v never started"

# Push a marker through herdr's own socket and wait for it: an ordered barrier
# that proves anything sent earlier has already been rendered.
barrier() {
  herdr pane send-text "$pane" "$(printf '%s\r' "$1")"
  hk_wait_pane_shows "$pane" "$1" 50 || gate_fail G19 "barrier $1 never rendered"
}

assert_typed_one_liner() {
  # $1 = stderr file, $2 = a substring the message must carry, $3 = what failed
  _lines=$(wc -l < "$1" | tr -d ' ')
  [ "$_lines" -eq 1 ] || gate_fail G19 "$3: expected one typed line, got $_lines: $(cat "$1")"
  if grep -q 'Traceback' "$1"; then gate_fail G19 "$3: traceback: $(cat "$1")"; fi
  grep -q "$2" "$1" || gate_fail G19 "$3: message does not name $2: $(cat "$1")"
}

# --- 1. T13: --current inside a managed pane ---------------------------------
set +e
printf 'CURRENTMARK\n' | env HERDR_ENV=1 HERDR_PANE_ID="$pane" hk send --current \
  >"$SBX/g19.out" 2>"$SBX/g19.err"
code=$?
set -e
[ "$code" -eq 0 ] \
  || gate_fail G19 "--current in a managed pane exited $code (stderr: $(cat "$SBX/g19.err"))"
hk_wait_pane_shows "$pane" 'CURRENTMARK' 50 \
  || gate_fail G19 "--current did not deliver to HERDR_PANE_ID: $(hk_pane_visible "$pane")"

# --- 2. T15: the precondition, with HERDR_PANE_ID still perfectly good --------
err=$SBX/g19-unset.err
set +e
printf 'DENIEDMARK\n' | env -u HERDR_ENV HERDR_PANE_ID="$pane" hk send --current \
  >"$SBX/g19-unset.out" 2>"$err"
denied_code=$?
set -e
case "$denied_code" in
  2|3) ;;
  *) gate_fail G19 "HERDR_ENV unset: expected exit 2 or 3, got $denied_code (stderr: $(cat "$err"))" ;;
esac
assert_typed_one_liner "$err" "HERDR_ENV" "HERDR_ENV unset"
barrier BARRIER1
if hk_pane_visible "$pane" | grep -q 'DENIEDMARK'; then
  gate_fail G19 "bytes were sent with HERDR_ENV unset — the T15 precondition is gone"
fi

# --- 3. T14: a live agent name resolves --------------------------------------
herdr pane report-agent "$pane" --source test:smoke --agent alpha --state idle >/dev/null
set +e
printf 'AGENTMARK\n' | hk send alpha >"$SBX/g19-agent.out" 2>"$SBX/g19-agent.err"
code=$?
set -e
[ "$code" -eq 0 ] \
  || gate_fail G19 "live agent name exited $code (stderr: $(cat "$SBX/g19-agent.err"))"
hk_wait_pane_shows "$pane" 'AGENTMARK' 50 \
  || gate_fail G19 "agent-name target did not deliver: $(hk_pane_visible "$pane")"

# --- 4. T14: a dead agent name fails typed -----------------------------------
derr=$SBX/g19-dead.err
set +e
printf 'GHOSTMARK\n' | hk send ghost >"$SBX/g19-dead.out" 2>"$derr"
dead_code=$?
set -e
[ "$dead_code" -ne 0 ] || gate_fail G19 "a dead agent name exited 0"
assert_typed_one_liner "$derr" "ghost" "dead agent name"
barrier BARRIER2
if hk_pane_visible "$pane" | grep -q 'GHOSTMARK'; then
  gate_fail G19 "bytes were sent to a dead agent name"
fi

gate_pass G19 "--current delivers to HERDR_PANE_ID; HERDR_ENV unset -> exit $denied_code, one typed line, zero bytes; agent name 'alpha' resolved, 'ghost' refused (exit $dead_code) with nothing sent"
