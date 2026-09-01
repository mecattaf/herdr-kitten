#!/bin/sh
# G17 — workspace verbs (spec 9.1/9.2/9.5 + 1.4, gate row G17; P45/P49/P51, D15).
. "$(dirname "$0")/lib.sh"
hk_sandbox; hk_sandbox_shell
hk_server_start || gate_fail G17 "server did not start"
trap hk_server_stop EXIT

# --- spec 1.4: no hk-config anywhere -> defaults, and nothing gets written ----
if [ -e "$XDG_CONFIG_HOME/hk/config.toml" ]; then gate_fail G17 "sandbox was not clean"; fi
hk config | grep -q "plain_scrollback_action" || gate_fail G17 "hk config did not print defaults"
hk config | grep -q "absent" || gate_fail G17 "hk config did not report the missing file"
if [ -e "$XDG_CONFIG_HOME/hk" ]; then gate_fail G17 "hk wrote a config directory (spec 1.4 forbids it)"; fi

# --- spec 9.1/9.2: hk new under a git checkout labels from the repo basename --
mkdir -p "$SBX/repos/myproj"
cd "$SBX/repos/myproj"
have_git=no
if command -v git >/dev/null 2>&1 && git init -q . 2>/dev/null; then have_git=yes; fi
out=$(hk new --no-window) || gate_fail G17 "hk new failed"
ws=$(echo "$out" | cut -d' ' -f1)
label=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print([w for w in d['result']['workspaces'] if w['workspace_id']=='$ws'][0].get('label',''))")
[ "$label" = "myproj" ] || gate_fail G17 "workspace $ws labelled '$label', want the git basename myproj"
panes=$(herdr pane list --workspace "$ws" | hk_json "d=json.load(sys.stdin);print(len(d['result']['panes']))")
[ "$panes" -ge 1 ] || gate_fail G17 "new workspace has no root pane"

# The distinguishing test for "repo ROOT basename" vs "cwd basename" is a
# nested subdirectory — and it only means anything where git actually exists.
mkdir -p "$SBX/repos/myproj/src/deep"
cd "$SBX/repos/myproj/src/deep"
out2=$(hk new --no-window) || gate_fail G17 "hk new failed in a subdirectory"
ws2=$(echo "$out2" | cut -d' ' -f1)
label2=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print([w for w in d['result']['workspaces'] if w['workspace_id']=='$ws2'][0].get('label',''))")
if [ "$have_git" = yes ]; then
  [ "$label2" = "myproj" ] || gate_fail G17 "label from a subdir is '$label2', want the repo root basename myproj"
else
  # census-map P51's fallback chain: no git -> cwd basename, never a crash
  [ "$label2" = "deep" ] || gate_fail G17 "no git: label from a subdir is '$label2', want the cwd basename deep"
fi
cd "$SBX"

# --- spec 9.5 / D15: the workspace NUMBER is the join ------------------------
herdr workspace create --cwd "$SBX" --label second >/dev/null
n=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print([w for w in d['result']['workspaces'] if w['label']=='second'][0]['number'])")
hk ws focus "$n" || gate_fail G17 "hk ws focus $n failed"
focused=$(herdr workspace list | hk_json "d=json.load(sys.stdin);print([w for w in d['result']['workspaces'] if w.get('focused')][0].get('label',''))")
[ "$focused" = "second" ] || gate_fail G17 "focus landed on '$focused', want second"

# a number nobody has is a real failure, not a silent no-op
set +e
hk ws focus 999 >/dev/null 2>"$SBX/g17.err"; code=$?
set -e
[ "$code" -ne 0 ] || gate_fail G17 "hk ws focus on an absent number should exit nonzero"

# --- hk ws list surfaces the number that hk ws focus consumes ----------------
hk ws list | awk -F'\t' '{print $1}' | grep -qx "$n" || gate_fail G17 "hk ws list omits number $n"

gate_pass G17 "defaults with no config file and nothing written; hk new labels correctly (git=$have_git); ws focus joins by number $n"
