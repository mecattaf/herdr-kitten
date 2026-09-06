#!/bin/sh
# supervised-lane — the paste-read-back smoke, and the typed-exit fixture.
#
# Card HK-1; herdr-kitten #36/#37/#38 = tally.nix #670/#673/#678.
#
# What it proves, against a live herdr server in a sandbox HOME:
#
#   1. A worker argv declared in a PRESET FILE is launched through `hk` in a
#      pane hk selects (#36). The caller declares what to run; it never learns
#      how panes are chosen, and nothing about the worker is compiled into hk.
#   2. The canonical payload, sent ON STDIN, comes back through the terminal
#      rail BYTE-IDENTICAL (#37) — all 62 bytes of it, the trailing newline
#      included. The worker reports two independent measures of what it
#      received (the literal bytes in hex, and its own cumulative count and
#      sha256) and the smoke compares BOTH to the payload file: `cmp` on the
#      reconstruction, and the worker's `READBACK-SHA <count> <digest>` against
#      `wc -c` / `sha256sum` of the same file.
#   3. Every typed exit of the RULING-kitten §5 contract is produced by the
#      fixture and asserted here (#38): 0 delivered, 1 refused (`agent_blocked`,
#      `timeout` and `server_not_running`, each printed verbatim), 2 malformed
#      preset, 3 no lane reachable with ZERO BYTES sent, 4 not implemented.
#   4. The test session is torn down by a verb (`hk lane stop`), not a trap,
#      and the pane count returns to its baseline.
#
# THE READ-BACK IS ASSERTED FROM BOTH SIDES, on purpose. The worker's measures
# come from the bytes it actually read, so a byte appended, dropped or altered
# anywhere in hk's delivery or in the rail makes them disagree with the payload
# FILE; and the fixture's own sha256 is PINNED below, so a byte dropped from the
# fixture itself — which would otherwise move both sides together and stay green
# — fails the digest. Every one of those mutations was applied and observed RED
# (tests/proofs/hk1-readback-bytes.py reruns two of them).
#
# The worker must therefore be BYTE-oriented: a `while read -r line` worker
# never reports a trailing fragment with no newline after it, because `read`
# holds that fragment until a delimiter or an EOF a live lane never sends — so
# the extra byte the evaluator appended was invisible and the gate passed on a
# delivery that was not byte-identical (DEFECT 1). The fixture worker puts the
# tty in raw mode and reports every chunk the moment it arrives.
#
# `pane report-agent` is a smoke FIXTURE here, exactly as in G6: tests are the
# sole legal caller outside real agents and their installers (spec F.9).
#
# Not in tests/smoke/run-headless.sh: this gate is its own oracle entry (card
# HK-1) and runs alongside the repository battery, not inside it.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell

G=SUPERVISED-LANE

# The presets are copied into the sandbox and driven from there, so the lane's
# default cwd is the sandbox and no gate ever runs a worker in the repo tree.
cp -R "$REPO_ROOT/tests/fixtures/supervised-lane" "$SBX/fixtures"
P="$SBX/fixtures"
PAYLOAD="$P/payload.txt"
PINNED_SHA=562fd7fc051db1c68dc8fb44818db60ea591109854161ca4cd24605762e963f9

sha256_of() { python3 -c "
import hashlib,sys
sys.stdout.write(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

lane_run() {  # $1 verb  $2 preset  [$3 stdin file] -> LANE_RC, lane.out, lane.err
  set +e
  hk lane "$1" "$2" <"${3:-/dev/null}" >"$SBX/lane.out" 2>"$SBX/lane.err"
  LANE_RC=$?
  set -e
}

assert_typed_one_liner() {  # $1 stderr file, $2 substring, $3 what failed
  _lines=$(wc -l < "$1" | tr -d ' ')
  [ "$_lines" -eq 1 ] || gate_fail $G "$3: expected one typed line, got $_lines: $(cat "$1")"
  if grep -q 'Traceback' "$1"; then gate_fail $G "$3: traceback: $(cat "$1")"; fi
  grep -q "$2" "$1" || gate_fail $G "$3: message does not name '$2': $(cat "$1")"
}

# --- 0. the canonical payload is the one this gate was written against -------
have_sha=$(sha256_of "$PAYLOAD")
[ "$have_sha" = "$PINNED_SHA" ] \
  || gate_fail $G "the canonical payload changed: sha256 $have_sha, pinned $PINNED_SHA \
($(wc -c < "$PAYLOAD" | tr -d ' ') bytes). A payload with a byte dropped cannot prove a byte-identical read-back."
lines=$(wc -l < "$PAYLOAD" | tr -d ' ')
[ "$lines" -eq 1 ] || gate_fail $G "the canonical payload must be exactly one line, got $lines"

# --- 1. NO SESSION: nothing is listening, so nothing can be sent -------------
# Deliberately the first step and deliberately BEFORE `hk_server_start`: the
# card's "no session" outcome only exists while no server is up, and §5 says a
# server/tool error is exit 1 with herdr's code verbatim — the same answer
# `hk send` gives in this state. Zero bytes of stdin are consumed, which is the
# property a supervisor actually branches on.
lane_run status "$P/absent.toml"
[ "$LANE_RC" -eq 1 ] || gate_fail $G "no herdr session exited $LANE_RC, want 1 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "server_not_running" "no herdr session"
set +e
rest=$( { hk lane deliver "$P/absent.toml" >"$SBX/lane.out" 2>"$SBX/lane.err"; echo "RC=$?" >"$SBX/lane.rc"; cat; } < "$PAYLOAD" )
set -e
LANE_RC=$(sed 's/^RC=//' "$SBX/lane.rc")
[ "$LANE_RC" -eq 1 ] || gate_fail $G "deliver with no herdr session exited $LANE_RC, want 1 (stderr: $(cat "$SBX/lane.err"))"
[ "$rest" = "$(cat "$PAYLOAD")" ] \
  || gate_fail $G "a dead session consumed stdin: $(printf '%s' "$rest" | wc -c) bytes left of $(wc -c < "$PAYLOAD")"

hk_server_start || gate_fail $G "server did not start"
trap hk_server_stop EXIT

herdr workspace create --cwd "$SBX" >/dev/null
baseline=$(hk_pane_count)

# --- 2. exit 2: a malformed preset launches nothing --------------------------
lane_run start "$P/malformed.toml"
[ "$LANE_RC" -eq 2 ] || gate_fail $G "malformed preset exited $LANE_RC, want 2 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "not valid TOML" "malformed preset"
[ "$(hk_pane_count)" -eq "$baseline" ] || gate_fail $G "a malformed preset launched a pane"

# --- 3. exit 4: a kind hk does not implement, and never will ------------------
lane_run start "$P/unsupervised.toml"
[ "$LANE_RC" -eq 4 ] || gate_fail $G "unsupervised kind exited $LANE_RC, want 4 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "does not implement" "unsupervised kind"
[ "$(hk_pane_count)" -eq "$baseline" ] || gate_fail $G "an unimplemented kind launched a pane"

# --- 4. exit 3: no lane reachable, and ZERO BYTES were read from stdin --------
# stdin is the whole payload; the refusal must land before it is consumed, so
# the pipe still holds every byte when hk exits.
set +e
rest=$( { hk lane deliver "$P/absent.toml" >"$SBX/lane.out" 2>"$SBX/lane.err"; echo "RC=$?" >"$SBX/lane.rc"; cat; } < "$PAYLOAD" )
set -e
LANE_RC=$(sed 's/^RC=//' "$SBX/lane.rc")
[ "$LANE_RC" -eq 3 ] || gate_fail $G "absent lane exited $LANE_RC, want 3 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "hk1-absent" "absent lane"
[ "$rest" = "$(cat "$PAYLOAD")" ] \
  || gate_fail $G "the refusal consumed stdin: $(printf '%s' "$rest" | wc -c) bytes left of $(wc -c < "$PAYLOAD")"

# --- 5. #36: the worker argv is launched through hk from the preset file ------
lane_run start "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "hk lane start exited $LANE_RC (stderr: $(cat "$SBX/lane.err"))"
pane=$(cat "$SBX/lane.out")
[ -n "$pane" ] || gate_fail $G "hk lane start printed no pane id"
# start returned 0, so the readiness marker the preset declares is already on
# screen: the worker really executed, a pane that merely exists cannot pass.
hk_pane_visible "$pane" | grep -q 'LANE-READY' \
  || gate_fail $G "hk lane start returned 0 without the worker's marker: $(hk_pane_visible "$pane")"
lane_run status "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "hk lane status exited $LANE_RC on a running lane"
[ "$(cat "$SBX/lane.out")" = "$pane" ] \
  || gate_fail $G "status resolved '$(cat "$SBX/lane.out")', start reported '$pane'"

# --- 6. #37: payload on stdin, read back through the rail BYTE-IDENTICAL ------
# Byte-identical means ALL of the bytes: both comparisons are against the
# payload FILE — 62 bytes, trailing newline included — and never against a
# stripped copy of it. DEFECT 1 was exactly that strip plus a last-sentinel-only
# read, which together made a delivery with one extra trailing byte
# indistinguishable from the canonical one.
want_bytes=$(wc -c < "$PAYLOAD" | tr -d ' ')
want_sha=$(sha256_of "$PAYLOAD")
lane_run deliver "$P/worker.toml" "$PAYLOAD"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "hk lane deliver exited $LANE_RC (stderr: $(cat "$SBX/lane.err"))"
# (a) the worker's OWN cumulative measure of everything it received
hk_wait "hk read $pane --text --lines 400 | grep -q 'READBACK-SHA $want_bytes $want_sha'" 75 \
  || gate_fail $G "the worker never reported the whole payload byte-for-byte: want 'READBACK-SHA $want_bytes $want_sha', screen: $(hk_pane_visible "$pane")"
# (b) the literal bytes, reconstructed from the rail and compared with cmp
hk read "$pane" --text --lines 400 2>/dev/null | python3 -c "
import re, sys
chunks = re.findall(r'READBACK-HEX ([0-9a-f]+)', sys.stdin.read())
sys.stdout.buffer.write(bytes.fromhex(''.join(chunks)))" > "$SBX/readback.bin"
cmp "$SBX/readback.bin" "$PAYLOAD" \
  || gate_fail $G "read-back is NOT byte-identical: got $(wc -c < "$SBX/readback.bin" | tr -d ' ') bytes \
[$(cat -v "$SBX/readback.bin")] sha $(sha256_of "$SBX/readback.bin"), want $want_bytes bytes \
[$(cat -v "$PAYLOAD")] sha $want_sha"

# --- 7. exit 1: a blocked agent REFUSES, and the code is propagated verbatim --
herdr pane report-agent "$pane" --source test:smoke --agent hk1-worker --state blocked >/dev/null
lane_run deliver "$P/blocked.toml" "$PAYLOAD"
[ "$LANE_RC" -eq 1 ] || gate_fail $G "blocked delivery exited $LANE_RC, want 1 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "agent_blocked" "blocked delivery"

# --- 8. exit 1: a worker that never announces itself times out ----------------
# The lane's pane is closed again: a start that failed leaves no residue.
before=$(hk_pane_count)
lane_run start "$P/stalled.toml"
[ "$LANE_RC" -eq 1 ] || gate_fail $G "stalled lane exited $LANE_RC, want 1 (stderr: $(cat "$SBX/lane.err"))"
assert_typed_one_liner "$SBX/lane.err" "timeout" "stalled lane"
hk_wait '[ "$(hk_pane_count)" -le "'"$before"'" ]' 50 \
  || gate_fail $G "the timed-out lane left its pane behind ($(hk_pane_count) > $before)"

# --- 9. teardown is a verb: the test session ends clean -----------------------
lane_run stop "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "hk lane stop exited $LANE_RC (stderr: $(cat "$SBX/lane.err"))"
hk_wait '[ "$(hk_pane_count)" -le "'"$baseline"'" ]' 50 \
  || gate_fail $G "hk lane stop left the pane behind ($(hk_pane_count) > $baseline)"
lane_run status "$P/worker.toml"
[ "$LANE_RC" -eq 3 ] || gate_fail $G "status on a stopped lane exited $LANE_RC, want 3"

gate_pass $G "worker argv launched from $P/worker.toml into pane $pane; \
all $want_bytes payload bytes on stdin read back byte-identical (cmp against the fixture file, and the worker's own READBACK-SHA $want_bytes $want_sha); \
exits 0/1/2/3/4 asserted (delivered; refused as agent_blocked, timeout and server_not_running; \
malformed preset; no lane reachable with zero bytes read; not implemented); \
lane stopped, pane count back to $baseline"
