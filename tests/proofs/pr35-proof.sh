#!/bin/sh
# tests/proofs/pr35-proof.sh — the PR #35 evidence, banked rather than asserted.
#
# PR #35 (round2-03-followup, issue #17) does two things: it kills the junk file
# `herdr: fake blocked` at its source (hk/notifyd.py appends the notification
# message as a final argv element, so gate G8's `touch $SBX/hit` created it in
# notifyd's cwd — the repo root — on every battery run), and it closes the hole
# that let the file back (every hygiene assertion looked at TRACKED files, and
# the sequence that reintroduced the junk staged nothing until after the tests
# had already passed).
#
# This script re-runs the standing battery from a copy and reports whether the
# fix holds. It never writes into the source repo, never touches the network,
# and never merges anything — the merge is Tom's (see docs/dev/pr35-proof.md).
#
# Usage:
#   sh tests/proofs/pr35-proof.sh [--branch REF] [--receipt PATH] [--red] [--keep]
#
#   (default)   GREEN run: the battery from a cp -a copy must be rc 0, with an
#               empty `git status --porcelain` at the end. rc 0 = the fix holds.
#   --red       RED run: plant an untracked file at the copy's repo root first.
#               The hygiene gate MUST go red. rc 0 = the gate has teeth;
#               rc 1 = the gate is asleep, which is the bug PR #35 fixed.
#   --branch    which ref to check out inside the copy. Default: the branch PR
#               #35 is open from, round2-03-followup — this harness proves that
#               PR, so it pins that ref rather than inheriting whatever the
#               source checkout happens to be on. Override with HK_PROOF_BRANCH
#               or this flag (`--branch main` is the after-merge check).
#   --receipt   write a plain-text receipt of the run to PATH.
#   --keep      do not delete the scratch copy (its path is printed).
#
# WHAT GETS COPIED, AND WHY IT IS NOT "WHEREVER THIS SCRIPT LIVES".
# The copy has to carry a real .git (see below), so the source is the main
# checkout — resolved through `git rev-parse --git-common-dir` so that running
# this from a linked worktree, whose .git is a FILE pointing elsewhere, still
# copies something that has a repository in it. Override with HK_PROOF_SRC.
# The copy is then forced to a pristine checkout of the ref (`checkout -f` plus
# `git clean -fdq`) before anything runs: the source tree is shared with other
# branches and other hands, and a clean-root proof that started from someone
# else's uncommitted work would be proving nothing. Both of those touch the
# COPY only; the source repo is never written to.
#
# WHY cp -a AND NOT `git archive | tar -x` — MEASURED, not folklore.
# The archive form ships a tree with no .git, so the five git-based assertions
# in tests/unit/test_repo_hygiene.py die with
#     subprocess.CalledProcessError: Command '['git','ls-files','-z']'
#     returned non-zero exit status 128
# and the suite reports `Ran 118 tests ... FAILED (errors=5)`, rc 1, on a tree
# that is perfectly fine. Copying with `cp -a <repo>/. <dir>/` carries .git and
# the same tree reports `Ran 118 tests ... OK`, rc 0. A proof harness that
# cannot tell a healthy tree from a broken one is not evidence.
#
# WHY A COPY AT ALL, on any branch.
# On `main` the junk file is still TRACKED, and running the battery inside a
# checkout of `main` recreates it at the repo root. Working from a copy is what
# makes this script safe to run at any time from any checkout.

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# The main checkout, even when this script is run from a linked worktree.
REPO=${HK_PROOF_SRC:-$(CDPATH= cd -- "$HERE" && cd -- "$(git rev-parse --git-common-dir)/.." && pwd)}

# The herdr binary the smoke gates drive. Already on PATH? use it. Otherwise
# fall back to the pinned store path, overridable so this is not nix-only.
HERDR_BIN=${HK_PROOF_HERDR_BIN:-/nix/store/17wp72zqjv6yjrl069ssnapaqqnmmx5f-herdr-0.8.2/bin}

branch=${HK_PROOF_BRANCH:-round2-03-followup}
receipt=""
mode=green
keep=no

while [ $# -gt 0 ]; do
  case $1 in
    --branch)  branch=${2:?--branch needs a ref}; shift 2 ;;
    --receipt) receipt=${2:?--receipt needs a path}; shift 2 ;;
    --red)     mode=red; shift ;;
    --keep)    keep=yes; shift ;;
    -h|--help) sed -n '2,60p' "$0"; exit 0 ;;
    *) echo "pr35-proof: unknown argument: $1" >&2; exit 2 ;;
  esac
done

command -v herdr >/dev/null 2>&1 || PATH=$HERDR_BIN:$PATH
export PATH
if ! command -v herdr >/dev/null 2>&1; then
  echo "pr35-proof: no herdr on PATH and none at $HERDR_BIN" >&2
  echo "pr35-proof: set HK_PROOF_HERDR_BIN to the directory holding it" >&2
  exit 2
fi

d=$(mktemp -d) || exit 2
cleanup() { [ "$keep" = yes ] || rm -rf "$d"; }
trap cleanup EXIT INT TERM

# cp -a, with the trailing /. so dotfiles and .git come along. NOT git archive.
cp -a "$REPO"/. "$d"/ || exit 2
cd "$d" || exit 2
# Force the copy to a pristine $branch. -f discards any uncommitted work the
# source happened to be carrying, -fdq removes untracked leftovers; both act on
# the throwaway copy only.
git checkout --quiet -f "$branch" || { echo "pr35-proof: cannot check out $branch in the copy" >&2; exit 2; }
git clean -fdq || exit 2

head=$(git rev-parse HEAD)
herdr_path=$(command -v herdr)

emit() { echo "$@"; [ -z "$receipt" ] || echo "$@" >> "$receipt"; }

[ -z "$receipt" ] || : > "$receipt"
emit "pr35-proof: mode=$mode branch=$branch head=$head"
emit "pr35-proof: copy=$d (cp -a, .git carried)"
emit "pr35-proof: herdr=$herdr_path"

# The clean-root proof only means something if the tree was clean to begin with.
pre=$(git -C "$d" status --porcelain)
if [ -n "$pre" ]; then
  emit "pr35-proof: FAILED — the copy was not pristine before the battery:"
  printf '%s\n' "$pre" | sed 's/^/pr35-proof:   /'
  exit 2
fi
emit "pr35-proof: copy is pristine before the battery"

if [ "$mode" = red ]; then
  # Exactly the shape of the litter PR #35 stopped: an untracked, non-ignored
  # entry at the repo root, left behind by a tool that wrote into the repo
  # instead of its sandbox.
  : > "$d/herdr: fake blocked"
  emit "pr35-proof: planted untracked litter at the copy root: 'herdr: fake blocked'"
fi

units_out=$(PYTHONPATH=. python3 -m unittest discover -s tests/unit 2>&1)
units_rc=$?
units_ran=$(printf '%s\n' "$units_out" | sed -n 's/^Ran \([0-9]*\) tests.*/\1/p' | tail -1)
units_tail=$(printf '%s\n' "$units_out" | tail -1)
emit "pr35-proof: unit suite ran=$units_ran rc=$units_rc tail=$units_tail"

if [ "$mode" = red ]; then
  # The gate must name the litter. Anything else and we have not proven teeth.
  if [ "$units_rc" -eq 0 ]; then
    emit "pr35-proof: RED FAILED — the suite stayed green with litter at the root"
    exit 1
  fi
  if ! printf '%s\n' "$units_out" | grep -q "untracked litter at the repo root"; then
    emit "pr35-proof: RED FAILED — suite went red, but not on the hygiene gate"
    exit 1
  fi
  emit "pr35-proof: RED OK — test_working_tree_root_is_clean_too caught the litter"
  exit 0
fi

[ "$units_rc" -eq 0 ] || { emit "pr35-proof: GREEN FAILED — unit suite rc=$units_rc"; exit 1; }
printf '%s\n' "$units_tail" | grep -qx OK || { emit "pr35-proof: GREEN FAILED — last line was not OK"; exit 1; }

smoke_out=$(sh tests/smoke/run-headless.sh 2>&1)
smoke_rc=$?
gates_pass=$(printf '%s\n' "$smoke_out" | grep -c '^GATE .* PASS')
emit "pr35-proof: headless battery rc=$smoke_rc gates_pass=$gates_pass"
printf '%s\n' "$smoke_out" | grep '^GATE ' | sed 's/^/pr35-proof: /' | while IFS= read -r l; do
  echo "$l"; [ -z "$receipt" ] || echo "$l" >> "$receipt"
done
[ "$smoke_rc" -eq 0 ] || { emit "pr35-proof: GREEN FAILED — headless battery rc=$smoke_rc"; exit 1; }

# The clean-root proof: after the whole battery, the copy's tree is untouched.
porcelain=$(git -C "$d" status --porcelain)
if [ -n "$porcelain" ]; then
  emit "pr35-proof: GREEN FAILED — the battery dirtied the tree:"
  printf '%s\n' "$porcelain" | sed 's/^/pr35-proof:   /' | while IFS= read -r l; do
    echo "$l"; [ -z "$receipt" ] || echo "$l" >> "$receipt"
  done
  exit 1
fi
emit "pr35-proof: clean-root proof OK — git status --porcelain is empty after the battery"
emit "pr35-proof: GREEN OK — $units_ran units, $gates_pass gates, zero root litter"
exit 0
