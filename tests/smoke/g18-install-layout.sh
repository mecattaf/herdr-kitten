#!/bin/sh
# G18 — install layout (round2-02; BUG-3, BUG-4, BUG-15; RULING-kitten §3.4
# item 2: "runs install.sh into a temp HOME, then asserts (a) the kitten loads
# through the real kitty loader from the installed location, (b) ladder
# imports, (c) the fork helper path resolves, (d) a manifest exists and
# uninstall removes everything").
#
# This is the regression floor for a whole class: every one of those bugs was
# invisible to the dev tree and fatal to an installed one, which is exactly why
# a "ship-ready" verdict was reached with no gesture ever having dispatched
# from an install.
#
# ON THE ID: docs/dev/acceptance-run.md already has a "G18 smoke-socket
# battery" row for the CI meta-gate. The RULING names THIS file g18; the docs
# row is round2-15's to reconcile.
. "$(dirname "$0")/lib.sh"
REPO_ROOT=${HK_REPO_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
[ -f "$REPO_ROOT/install.sh" ] || gate_fail G18 "cannot locate the repo root from '$0'; set HK_REPO_ROOT"

hk_sandbox   # HOME + XDG_* into a fresh temp tree; install.sh honours both
WORK=$(mktemp -d "${TMPDIR:-/tmp}/hk-g18.XXXXXX")   # lists live OUTSIDE $SBX
KITTY_DIR="$XDG_CONFIG_HOME/kitty"
KITTEN_DIR="$KITTY_DIR/hk"
MANIFEST="$XDG_DATA_HOME/hk/install-manifest"

snapshot() { find "$SBX" | LC_ALL=C sort > "$1"; }

snapshot "$WORK/pre.list"
sh "$REPO_ROOT/install.sh" >"$WORK/install.log" 2>&1 \
  || gate_fail G18 "install.sh exited $?: $(tail -n 3 "$WORK/install.log" | tr '\n' ' ')"

# ---- (d1) the manifest exists ----------------------------------------------
[ -f "$MANIFEST" ] || gate_fail G18 "no manifest at $MANIFEST"
grep -q '^f ' "$MANIFEST" || gate_fail G18 "manifest lists no files: $MANIFEST"

# ---- BUG-15: nothing loose in the kitty config dir -------------------------
top=$(ls -A "$KITTY_DIR" | LC_ALL=C sort | tr '\n' ' ')
[ "$top" = "hk hk-maps.conf " ] \
  || gate_fail G18 "BUG-15: kitty config dir top level is '$top', expected 'hk hk-maps.conf'"
[ -d "$KITTEN_DIR" ] || gate_fail G18 "kitten tree is not a directory: $KITTEN_DIR"
grep -q 'kitten hk/hk.py' "$KITTY_DIR/hk-maps.conf" \
  || gate_fail G18 "installed maps do not point at the installed kitten path"

# ---- BUG-3: `hk` under the kitty config dir is a PACKAGE, not a loose file --
# kitty puts the kitten's directory on sys.path; a module file named hk.py
# there shadows the hk package and every `from hk import ...` dies. The name
# must resolve to the directory.
python3 - "$KITTY_DIR" <<'PY' >"$WORK/import.log" 2>&1 || gate_fail G18 "BUG-3: import hk from the kitty config dir failed: $(tail -n 2 "$WORK/import.log" | tr '\n' ' ')"
import os, sys
config_dir = sys.argv[1]
sys.path.insert(0, config_dir)
import hk
assert os.path.basename(hk.__file__) == "__init__.py", f"hk is not a package: {hk.__file__}"
assert os.path.dirname(hk.__file__) == os.path.join(config_dir, "hk"), hk.__file__
PY

# ---- (b) ladder imports from the installed tree, with a vendored predicate --
python3 - "$KITTEN_DIR" <<'PY' >"$WORK/ladder.log" 2>&1 || gate_fail G18 "ladder did not import from the installed tree: $(tail -n 2 "$WORK/ladder.log" | tr '\n' ' ')"
import os, sys
kitten_dir = sys.argv[1]
sys.path.insert(0, kitten_dir)
import ladder
assert ladder.predicate.__file__ == os.path.join(kitten_dir, "predicate.py"), ladder.predicate.__file__
assert ladder.toggle_action({"user_vars": {"hk_role": "herdr_ui"}}) == ladder.PREFIX
PY

# ---- (c) BUG-4: a fork.lua helper candidate resolves ------------------------
# The candidates are read out of the installed fork.lua itself, so this follows
# the source instead of restating it.
assets="$KITTEN_DIR/assets"
[ -f "$assets/fork.lua" ] || gate_fail G18 "fork.lua not installed at $assets"
resolved=0
tried=""
grep -o 'assets \.\. "[^"]*\.py"' "$assets/fork.lua" | sed 's/.*"\(.*\)"/\1/' > "$WORK/cands"
while IFS= read -r suffix; do
  tried="$tried $suffix"
  [ -f "$assets$suffix" ] && resolved=$((resolved + 1))
done < "$WORK/cands"
[ "$resolved" -ge 1 ] \
  || gate_fail G18 "BUG-4: no fork.lua helper candidate resolves under $assets (tried:$tried)"

# ---- (a) the real kitty loader, from the installed location ----------------
kitty_bin=${HK_KITTY_BIN:-$(command -v kitty || true)}
if [ -z "$kitty_bin" ]; then
  # CI honesty: a skipped loader gate is precisely how BUG-1/BUG-2 shipped.
  [ "${HK_REQUIRE_KITTY:-}" = "1" ] \
    && gate_fail G18 "HK_REQUIRE_KITTY=1 but no kitty on PATH: the loader half cannot run"
  echo "GATE G18 SKIP kitty not on PATH: layout+manifest halves passed, loader half not executed"
  exit 0
fi
probe="$REPO_ROOT/tests/unit/kitten_loader_probe.py"
"$kitty_bin" +launch "$probe" "$KITTEN_DIR/hk.py" toggle '{"hk_role":"herdr_ui"}' \
  >"$WORK/toggle.json" 2>"$WORK/toggle.err" \
  || gate_fail G18 "BUG-3/BUG-1: the installed kitten did not load: $(tail -n 2 "$WORK/toggle.err" | tr '\n' ' ')"
"$kitty_bin" +launch "$probe" "$KITTEN_DIR/hk.py" fork '{"hk_pane":"w1:p9"}' \
  >"$WORK/fork.json" 2>"$WORK/fork.err" \
  || gate_fail G18 "the installed kitten did not dispatch fork: $(tail -n 2 "$WORK/fork.err" | tr '\n' ' ')"
python3 - "$WORK/toggle.json" "$WORK/fork.json" "$KITTEN_DIR" <<'PY' >"$WORK/probe.log" 2>&1 || gate_fail G18 "loader assertions failed: $(tail -n 2 "$WORK/probe.log" | tr '\n' ' ')"
import json, os, sys

toggle = json.load(open(sys.argv[1]))
fork = json.load(open(sys.argv[2]))
kitten_dir = sys.argv[3]

assert toggle["loaded"] and toggle["no_ui"], toggle
assert toggle["written"] == ["02"], f"toggle wrote {toggle['written']!r}, expected the herdr prefix"
assert not toggle["errors"], toggle["errors"]

argv = fork["remote_control"][0]
assert "--os-window-class=hk-fork" in argv, argv
assert f"HK_FORK_ASSETS={kitten_dir}/assets" in argv, argv
# BUG-4 second half: an absolute, existing hk, not a bare name off PATH.
hk_bin = [a.split("=", 1)[1] for a in argv if a.startswith("HK_BIN=")]
assert hk_bin, f"no HK_BIN passed to the fork window: {argv}"
assert os.path.isabs(hk_bin[0]) and os.access(hk_bin[0], os.X_OK), hk_bin
lua = [a for a in argv if a.startswith("luafile ")][0].split(" ", 1)[1]
assert os.path.isfile(lua), lua
PY

# ---- (d2) uninstall removes exactly the manifest, and nothing else ---------
sh "$REPO_ROOT/install.sh" --uninstall >"$WORK/uninstall.log" 2>&1 \
  || gate_fail G18 "install.sh --uninstall exited $?: $(tail -n 3 "$WORK/uninstall.log" | tr '\n' ' ')"
snapshot "$WORK/post.list"
if ! diff -u "$WORK/pre.list" "$WORK/post.list" > "$WORK/diff"; then
  gate_fail G18 "uninstall did not restore the tree: $(grep -c '^+' "$WORK/diff") leftover(s), first: $(grep -m1 '^+[^+]' "$WORK/diff")"
fi

# ---- the gate's own teeth: a manifest that lies must be caught -------------
# The RED case the unit is judged on: drop one line from the manifest and the
# uninstall has to leave that file behind. If this half ever goes quiet, the
# half above is proving nothing.
sh "$REPO_ROOT/install.sh" >>"$WORK/install.log" 2>&1 \
  || gate_fail G18 "second install.sh exited $?"
grep -v "^f $KITTEN_DIR/hk.py$" "$MANIFEST" > "$WORK/tampered" || true
cp "$WORK/tampered" "$MANIFEST"
sh "$REPO_ROOT/install.sh" --uninstall >"$WORK/uninstall2.log" 2>&1 \
  || gate_fail G18 "uninstall after tampering exited $?"
[ -f "$KITTEN_DIR/hk.py" ] \
  || gate_fail G18 "self-check: a manifest missing hk.py still removed it — the manifest is not what uninstall reads"
snapshot "$WORK/post2.list"
diff -q "$WORK/pre.list" "$WORK/post2.list" >/dev/null \
  && gate_fail G18 "self-check: the tree compared equal after an incomplete uninstall — the diff assertion above has no teeth"

gate_pass G18 "installed layout loads through kitty $("$kitty_bin" --version 2>/dev/null | cut -d' ' -f2), ladder+predicate vendored, fork helper and HK_BIN resolve, uninstall restores the tree byte-for-byte, and a tampered manifest is caught"
