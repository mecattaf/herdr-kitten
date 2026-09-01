# shared smoke harness (sourced by every gate script and the driver)
# Convention: each gate prints "GATE <id> PASS|FAIL|STUB|SKIP <detail>" and
# exits 0 for PASS/STUB/SKIP, 1 for FAIL. A STUB is a gate whose stage has not
# landed yet — it must still EXECUTE (spec: no-op runner allowed at scaffold,
# silent drops never).
set -eu

gate_pass() { echo "GATE $1 PASS ${2:-}"; exit 0; }
gate_fail() { echo "GATE $1 FAIL ${2:-}"; exit 1; }
gate_stub() { echo "GATE $1 STUB ${2:-lands in a later stage}"; exit 0; }
gate_skip() { echo "GATE $1 SKIP ${2:-}"; exit 0; }

# Make a sandbox HOME for a private herdr server (never the user's, spec law).
hk_sandbox() {
  SBX=$(mktemp -d "${TMPDIR:-/tmp}/hk-smoke.XXXXXX")
  export SBX HOME="$SBX" \
    XDG_CONFIG_HOME="$SBX/.config" XDG_STATE_HOME="$SBX/.state" \
    XDG_DATA_HOME="$SBX/.data" XDG_CACHE_HOME="$SBX/.cache" \
    XDG_RUNTIME_DIR="$SBX/run" HERDR_SOCKET_PATH="$SBX/herdr.sock"
  mkdir -p "$SBX/.config" "$SBX/.state" "$SBX/.data" "$SBX/.cache" "$SBX/run"
}

hk_server_start() {
  herdr server >"$SBX/server.log" 2>&1 &
  HK_SERVER_PID=$!
  # bounded readiness wait (test harness, not an interactive path)
  for _ in $(seq 1 50); do
    [ -S "$HERDR_SOCKET_PATH" ] && herdr workspace list >/dev/null 2>&1 && return 0
    sleep 0.2
  done
  echo "server never became ready; log:" >&2; cat "$SBX/server.log" >&2 || true
  return 1
}

hk_server_stop() {
  herdr server stop >/dev/null 2>&1 || kill "${HK_SERVER_PID:-0}" 2>/dev/null || true
  wait "${HK_SERVER_PID:-0}" 2>/dev/null || true
}
