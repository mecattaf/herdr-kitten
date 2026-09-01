#!/bin/sh
# G5 — rename durability + restamp (spec 7.1/7.2/2.3, gate G5).
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G5 "server did not start"
herdr workspace create --cwd "$SBX" >/dev/null
pane=$(herdr pane list | hk_json "d=json.load(sys.stdin);print(d['result']['panes'][0]['pane_id'])")
hk rename "$pane" alpha || { hk_server_stop; gate_fail G5 "hk rename failed"; }
herdr server stop >/dev/null 2>&1; sleep 1
hk_server_start || gate_fail G5 "server did not restart"
trap hk_server_stop EXIT
hk_wait 'herdr pane list >/dev/null 2>&1' || gate_fail G5 "server not answering after restart"
# find the renamed pane by durable label via pane get over all panes
found=""
for pid in $(herdr pane list | hk_json "d=json.load(sys.stdin);print(' '.join(p['pane_id'] for p in d['result']['panes']))"); do
  lbl=$(herdr pane get "$pid" | hk_json "d=json.load(sys.stdin);print(d['result']['pane'].get('label') or '')")
  [ "$lbl" = "alpha" ] && found="$pid"
done
[ -n "$found" ] || gate_fail G5 "label alpha did not survive restart"
# restamp on attach path: tokens were wiped by restart; hk open --print restamps
hk open --print >/dev/null || gate_fail G5 "hk open failed post-restart"
role=$(herdr pane get "$found" | hk_json "d=json.load(sys.stdin);print(d['result']['pane'].get('tokens',{}).get('hk_role',''))")
[ -n "$role" ] || gate_fail G5 "no hk token restamped post-restart"
gate_pass G5 "label alpha survived restart; tokens restamped on attach"
