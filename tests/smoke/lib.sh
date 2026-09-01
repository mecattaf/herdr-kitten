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
  # the headless battery is socket-half by definition: never let the developer's
  # live kitty leak into a gate (G5 once stamped user-vars on a real window)
  unset KITTY_WINDOW_ID KITTY_LISTEN_ON KITTY_PID 2>/dev/null || true
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

# Prepare the sandbox pane shell: bash reading a .bashrc that sources the
# trampoline hook (spec D5). Call after hk_sandbox, before hk_server_start.
hk_sandbox_shell() {
  # $0 is the gate script (every gate sources this as `. $(dirname $0)/lib.sh`).
  # HK_REPO_ROOT overrides it for callers that source the harness some other way.
  REPO_ROOT=${HK_REPO_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
  [ -f "$REPO_ROOT/bin/hk" ] || { echo "lib.sh: cannot locate the repo root from '$0'; set HK_REPO_ROOT" >&2; return 1; }
  export SHELL=$(command -v bash)
  # One line, exactly the line the README asks a user to add to their shell rc.
  # PS1 is deliberately NOT touched: herdr's own shell integration owns the prompt.
  cat > "$SBX/.bashrc" <<RC
. "$REPO_ROOT/assets/hk-trampoline.sh"
RC
  export PATH="$REPO_ROOT/bin:$PATH"

  # bin/hk ships `#!/usr/bin/env python3` — correct for every host that runs it
  # (install.sh copies the file; NixOS provides /usr/bin/env). A nix BUILD
  # sandbox does not, so when the shebang cannot resolve we front the very same
  # file with a shim rather than skip the gate or weaken the artifact.
  if ! hk --version >/dev/null 2>&1; then
    mkdir -p "$SBX/bin"
    printf '#!/bin/sh\nexec python3 "%s/bin/hk" "$@"\n' "$REPO_ROOT" > "$SBX/bin/hk"
    chmod +x "$SBX/bin/hk"
    export PATH="$SBX/bin:$PATH"
    echo "note: /usr/bin/env unavailable; running bin/hk through python3 directly" >&2
  fi
}

# wait (bounded, test-harness-only) until a condition command exits 0
hk_wait() {
  _tries=${2:-25}
  while [ "$_tries" -gt 0 ]; do
    eval "$1" && return 0
    _tries=$((_tries - 1))
    sleep 0.2
  done
  return 1
}

hk_pane_count() {
  herdr pane list | python3 -c "import json,sys; print(len(json.load(sys.stdin)['result']['panes']))"
}

hk_json() { python3 -c "import json,sys;$1"; }

# Reading a pane in a gate.
#
# Ground truth, executed live 2026-09-01 against herdr 0.8.2: `pane read
# --source recent|recent-unwrapped --lines N` returns the last N RENDERED ROWS
# counted from the bottom of the pane's row buffer, blank rows included — NOT
# the last N non-empty lines. On a fresh 40-row pane whose output sits at the
# top, `--lines 20` returns the bottom 20 rows, i.e. nothing. Ask for at least a
# full viewport, or use the `visible` source, whenever a gate asserts on-screen
# content. (`hk read` itself is recent-unwrapped by spec 6.1 and passes --lines
# straight through; this is a harness concern, not a verb concern.)
HK_READ_ROWS=200
hk_pane_visible() { herdr pane read "$1" --source visible --lines "${2:-$HK_READ_ROWS}" --format text; }
hk_pane_recent() { herdr pane read "$1" --source recent-unwrapped --lines "${2:-$HK_READ_ROWS}" --format text; }
hk_wait_pane_shows() { hk_wait "hk_pane_visible $1 | grep -q -- '$2'" "${3:-25}"; }
