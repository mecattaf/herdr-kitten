#!/bin/sh
# hk1-eval-relay-redelivery.sh — EVALUATOR probe for card HK-1 (rule of the night).
#
# The card's oracle delivers the canonical payload ONCE to a lane it started and
# never touches again. Three things the card never asks are asserted here, each
# of which the supervised-lane mechanism could plausibly get wrong while the
# card's own smoke stays green:
#
#   A. RE-DELIVERY (a drain, not a one-shot). The same live lane is delivered to
#      a SECOND time. The worker's cumulative measure must move to 124 bytes with
#      the sha256 of payload||payload, and the bytes reconstructed from the rail
#      must cmp equal to payload||payload. A rail that replays a stale sentinel,
#      a delivery that is silently dropped after the first, or a worker whose
#      counter does not accumulate all fail here while the card's single-shot
#      delivery passes.
#   B. OUT-OF-BAND LANE DEATH. The pane is closed by `herdr pane close`, NOT by
#      `hk lane stop`, so hk never learns the lane died. `hk lane deliver` must
#      then exit 3 with one typed line, no traceback, and ZERO bytes of stdin
#      consumed — a stale pane id resolved from a cached or dead handle would
#      instead pipe the payload into nothing and report success.
#   C. STORE RECREATION. `hk lane start` on the same preset after that death must
#      produce a FRESH pane that is ready and byte-exact again, with the worker's
#      cumulative counter back at 62 — the lane must be recreatable, not poisoned.
#
# Written and run by the mechanical evaluator of HK-1; it is not the card's
# oracle and does not replace it.
: "${HK_REPO_ROOT:=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}"
export HK_REPO_ROOT
. "$HK_REPO_ROOT/tests/smoke/lib.sh"
hk_sandbox; hk_sandbox_shell

G=HK1-EVAL-RELAY

cp -R "$HK_REPO_ROOT/tests/fixtures/supervised-lane" "$SBX/fixtures"
P="$SBX/fixtures"
PAYLOAD="$P/payload.txt"
cat "$PAYLOAD" "$PAYLOAD" > "$SBX/payload2.bin"

sha_of() { python3 -c "
import hashlib,sys
sys.stdout.write(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

rail_bytes() {  # $1 pane -> $2 out file : every READBACK-HEX chunk, in order
  hk read "$1" --text --lines 800 2>/dev/null | python3 -c "
import re,sys
sys.stdout.buffer.write(bytes.fromhex(''.join(re.findall(r'READBACK-HEX ([0-9a-f]+)', sys.stdin.read()))))" > "$2"
}

lane_run() {
  set +e
  hk lane "$1" "$2" <"${3:-/dev/null}" >"$SBX/o" 2>"$SBX/e"
  LANE_RC=$?
  set -e
}

hk_server_start || gate_fail $G "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
baseline=$(hk_pane_count)

want1=$(wc -c < "$PAYLOAD" | tr -d ' '); sha1=$(sha_of "$PAYLOAD")
want2=$(wc -c < "$SBX/payload2.bin" | tr -d ' '); sha2=$(sha_of "$SBX/payload2.bin")

# --- lane up ----------------------------------------------------------------
lane_run start "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "start exited $LANE_RC ($(cat "$SBX/e"))"
pane=$(cat "$SBX/o")

# --- A. first delivery, then RE-DELIVERY to the same live lane ---------------
lane_run deliver "$P/worker.toml" "$PAYLOAD"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "first deliver exited $LANE_RC ($(cat "$SBX/e"))"
hk_wait "hk read $pane --text --lines 800 | grep -q 'READBACK-SHA $want1 $sha1'" 75 \
  || gate_fail $G "first delivery never reported $want1/$sha1: $(hk_pane_visible "$pane")"

lane_run deliver "$P/worker.toml" "$PAYLOAD"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "SECOND deliver exited $LANE_RC ($(cat "$SBX/e"))"
hk_wait "hk read $pane --text --lines 800 | grep -q 'READBACK-SHA $want2 $sha2'" 75 \
  || gate_fail $G "the lane did not accumulate a second delivery: want 'READBACK-SHA $want2 $sha2', screen: $(hk_pane_visible "$pane")"
rail_bytes "$pane" "$SBX/rail.bin"
cmp "$SBX/rail.bin" "$SBX/payload2.bin" \
  || gate_fail $G "re-delivery is not byte-identical: rail has $(wc -c < "$SBX/rail.bin" | tr -d ' ') bytes sha $(sha_of "$SBX/rail.bin"), want $want2 sha $sha2"

# --- B. out-of-band death: the pane is closed behind hk's back ---------------
herdr pane close "$pane" >/dev/null
hk_wait '[ "$(hk_pane_count)" -le "'"$baseline"'" ]' 50 \
  || gate_fail $G "pane close left the pane behind ($(hk_pane_count) > $baseline)"
set +e
rest=$( { hk lane deliver "$P/worker.toml" >"$SBX/o" 2>"$SBX/e"; echo "RC=$?" >"$SBX/rc"; cat; } < "$PAYLOAD" )
set -e
LANE_RC=$(sed 's/^RC=//' "$SBX/rc")
[ "$LANE_RC" -eq 3 ] || gate_fail $G "deliver to an out-of-band-killed lane exited $LANE_RC, want 3 ($(cat "$SBX/e"))"
grep -q 'Traceback' "$SBX/e" && gate_fail $G "deliver to a dead lane traced back: $(cat "$SBX/e")"
[ "$(wc -l < "$SBX/e" | tr -d ' ')" -eq 1 ] || gate_fail $G "dead lane: expected one typed line, got $(cat "$SBX/e")"
[ "$rest" = "$(cat "$PAYLOAD")" ] \
  || gate_fail $G "a dead lane consumed stdin: $(printf '%s' "$rest" | wc -c) bytes left of $want1"

# --- C. store recreation: the same preset starts a FRESH, byte-exact lane ----
lane_run start "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "restart after an out-of-band death exited $LANE_RC ($(cat "$SBX/e"))"
pane2=$(cat "$SBX/o")
[ -n "$pane2" ] || gate_fail $G "restart printed no pane id"
hk_pane_visible "$pane2" | grep -q 'LANE-READY' || gate_fail $G "the restarted lane never announced itself"
lane_run deliver "$P/worker.toml" "$PAYLOAD"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "deliver after restart exited $LANE_RC ($(cat "$SBX/e"))"
hk_wait "hk read $pane2 --text --lines 800 | grep -q 'READBACK-SHA $want1 $sha1'" 75 \
  || gate_fail $G "the restarted lane did not read back $want1/$sha1: $(hk_pane_visible "$pane2")"
rail_bytes "$pane2" "$SBX/rail2.bin"
cmp "$SBX/rail2.bin" "$PAYLOAD" \
  || gate_fail $G "restarted lane not byte-identical: $(wc -c < "$SBX/rail2.bin" | tr -d ' ') bytes sha $(sha_of "$SBX/rail2.bin"), want $want1 sha $sha1"

lane_run stop "$P/worker.toml"
[ "$LANE_RC" -eq 0 ] || gate_fail $G "stop exited $LANE_RC ($(cat "$SBX/e"))"
hk_wait '[ "$(hk_pane_count)" -le "'"$baseline"'" ]' 50 || gate_fail $G "stop left a pane behind"

gate_pass $G "re-delivery accumulated to $want2 bytes ($sha2) byte-identical on the rail; \
an out-of-band pane close left deliver at exit 3 with all $want1 bytes unread; \
the preset restarted into pane $pane2 and read back $want1 bytes ($sha1) byte-identical; pane count back to $baseline"
