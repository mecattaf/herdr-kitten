#!/bin/sh
# G16 — resume picker (spec 10.1/10.2 + 7.6, gate row G16; census-map P57).
# The attach leg needs a TTY, so it runs under a pty here (python3 stdlib) —
# `herdr terminal attach` is a full-screen client and will not start otherwise.
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G16 "server did not start"
trap hk_server_stop EXIT
herdr workspace create --cwd "$SBX" >/dev/null
p1=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
herdr pane rename "$p1" alpha >/dev/null
p2=$(herdr pane split "$p1" --direction down | hk_json "d=json.load(sys.stdin);print(d['result']['pane']['pane_id'])")
herdr pane report-metadata "$p2" --source user:hk --token hk_role=fork >/dev/null

rows=$(hk resume --print) || gate_fail G16 "hk resume --print failed"
echo "$rows" | grep -q "alpha" || gate_fail G16 "labelled row missing: $rows"
echo "$rows" | awk -F'\t' '{print $1}' | grep -q '^term_' || gate_fail G16 "rows do not lead with terminal_id"
n=$(echo "$rows" | wc -l)
[ "$n" -eq 1 ] || gate_fail G16 "fork-role pane not filtered (got $n rows: $rows)"
echo "$rows" | awk -F'\t' '{print $3}' | grep -qE 'idle|working|blocked|done|unknown' \
  || gate_fail G16 "no agent_status column: $rows"

# --- the attach leg: processes intact across a reattach (spec 10.2) ----------
tid=$(echo "$rows" | awk -F'\t' '{print $1}')
herdr pane send-text "$p1" "$(printf 'sleep 9999 &\r')"
hk_wait_pane_shows "$p1" 'sleep 9999' 50 || gate_fail G16 "sleep never started"
before=$(herdr pane process-info --pane "$p1" | hk_json "d=json.load(sys.stdin);print(d['result']['process_info']['shell_pid'])")

python3 - "$tid" <<'PY' >"$SBX/g16.attach.log" 2>&1 || true
import os, pty, signal, sys, time
pid, fd = pty.fork()
if pid == 0:
    os.execvp("hk", ["hk", "resume", "--attach", sys.argv[1]])
time.sleep(3)
os.kill(pid, signal.SIGHUP)
os.waitpid(pid, 0)
PY

after=$(herdr pane process-info --pane "$p1" | hk_json "d=json.load(sys.stdin);print(d['result']['process_info']['shell_pid'])")
[ "$before" = "$after" ] || gate_fail G16 "shell pid changed across reattach ($before -> $after)"
# and the shell's own child outlived the attach client — "processes intact" is
# the claim (spec 10.2), not "the screen looks the same": the attach client is
# an alt-screen TUI and repaints the pane on both entry and exit.
python3 - "$before" <<'CHILD' || gate_fail G16 "the pane's child did not survive the reattach"
import os, sys
parent = sys.argv[1]
for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    try:
        argv = open("/proc/%s/cmdline" % entry, "rb").read().split(b"\0")
        ppid = open("/proc/%s/stat" % entry).read().rsplit(") ", 1)[1].split()[1]
    except OSError:
        continue
    if argv[:2] == [b"sleep", b"9999"] and ppid == parent:
        sys.exit(0)
sys.exit(1)
CHILD

# --- spec 7.6 / D23: agent rename rejects free text LOCALLY ------------------
set +e
slug_err=$SBX/g16.slug.err
hk agent rename "$p1" "Not A Slug" >/dev/null 2>"$slug_err"; slug_code=$?
set -e
[ "$slug_code" -eq 2 ] || gate_fail G16 "free-text agent name should be a usage error (got $slug_code)"
grep -q "refusing locally" "$slug_err" || gate_fail G16 "slug rejection not local: $(cat "$slug_err")"

gate_pass G16 "rows carry terminal_id/label/agent_status, fork pane filtered, reattach keeps shell pid $before, agent-rename slug enforced locally"
