#!/bin/sh
# herdr-kitten installer for non-nix hosts (spec 1.1). Copies files; never edits configs.
#
# Usage:  sh install.sh              install (or re-install over an old copy)
#         sh install.sh --uninstall  remove exactly what the manifest lists
#
# INSTALLED LAYOUT (round2-02 — BUG-3, BUG-15)
#
#   ~/.config/kitty/hk/            the kitten tree, a DIRECTORY and a package
#     __init__.py                  (generated) the package marker — see below
#     hk.py                        the kitten kitty loads: `kitten hk/hk.py`
#     ladder.py  fork_state.py     the kitten's own flat modules
#     predicate.py  config.py      vendored copies: nothing under kitten/ ever
#                                  says `from hk import ...` (BUG-3)
#     assets/                      fork.lua, the trampoline, the spinner
#   ~/.config/kitty/hk-maps.conf   the suggested maps, to `include` from kitty.conf
#   ~/.local/share/hk/hk/*.py      the CLI package
#   ~/.local/share/hk/bin/hk       the CLI (bin/hk resolves ../hk of its realpath)
#   ~/.local/share/hk/install-manifest   what --uninstall reads
#   ~/.local/bin/hk                a symlink onto it
#   ~/.config/hk/config.toml       the template, only when absent
#
# WHY A SUBDIRECTORY, AND WHY IT IS NAMED `hk`
#
# kitty's custom-kitten loader inserts the kitten's own directory at sys.path[0]
# (kittens/runner.py:57-58). The old layout dropped `hk.py`, `ladder.py` and
# `fork_state.py` loose into ~/.config/kitty/, so that entry was the whole kitty
# config dir and the module file `hk.py` shadowed the `hk` PACKAGE — every
# `from hk import ...` on the kitten side resolved to the kitten itself and
# raised ImportError. No gesture ever dispatched from an installed tree.
#
# So the tree moves into one directory (BUG-15: nothing loose in the kitty
# config dir), and that directory is named `hk` and carries an __init__.py.
# The name is the point: `hk` is the one name anything looking from the kitty
# config dir will reach for, and it now resolves to a package DIRECTORY that
# cannot be shadowed by a stray module file. `sys.path` gets a directory whose
# own name is `hk`, and the kitten's flat neighbours (ladder, fork_state) import
# by their own names, as they always did.
#
# THE MANIFEST FORMAT is a default, not a ruling (RULING-kitten §6 row 2 leaves
# it unruled): one entry per line, "<kind> <absolute path>", kinds f/d/c/p as
# documented in manifest_header() below. Paths never contain a newline; nothing
# else is escaped. --uninstall removes exactly these entries and nothing else.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN_DIR="${HK_BIN_DIR:-$HOME/.local/bin}"
KITTY_DIR="${HK_KITTY_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/kitty}"
HK_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hk"
SHARE_DIR="${HK_SHARE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/hk}"
KITTEN_DIR="$KITTY_DIR/hk"
MAPS_FILE="$KITTY_DIR/hk-maps.conf"
MANIFEST="$SHARE_DIR/install-manifest"

usage() {
  echo "usage: sh install.sh [--uninstall]"
  echo "  (no argument)  install into \$HOME (honours XDG_*, HK_BIN_DIR, HK_KITTY_DIR, HK_SHARE_DIR)"
  echo "  --uninstall    remove exactly what $MANIFEST lists"
}

manifest_header() {
  cat <<'HDR'
# herdr-kitten install manifest v1 — written by install.sh, read by
# `install.sh --uninstall`. One entry per line: "<kind> <absolute path>".
#   f  a file or symlink this install created; --uninstall removes it
#   d  a directory this install created; --uninstall rmdir's it, and leaves it
#      alone (with a note) if anything of yours is still inside
#   c  a config file created from the shipped template; --uninstall removes it
#      only while it is still byte-identical to that template
#   p  a directory whose python bytecode cache this install is responsible for;
#      --uninstall removes <dir>/__pycache__ when it holds nothing but bytecode
# Paths never contain a newline; nothing else is escaped. Entries are in
# creation order, so removal walks them backwards.
HDR
}

# ---------------------------------------------------------------- uninstall --
do_uninstall() {
  [ -f "$MANIFEST" ] || {
    echo "install.sh --uninstall: no manifest at $MANIFEST" >&2
    echo "  (nothing was removed; was this installed by install.sh?)" >&2
    exit 1
  }
  work=$(mktemp "${TMPDIR:-/tmp}/hk-uninstall.XXXXXX")
  trap 'rm -f "$work"' EXIT INT HUP TERM
  grep -v '^#' "$MANIFEST" > "$work" || true

  removed=0
  kept=0
  # files, config templates and bytecode caches first: the manifest lists
  # itself, so it goes with them.
  while IFS=' ' read -r kind path; do
    [ -n "${path:-}" ] || continue
    case "$kind" in
      f)
        if [ -e "$path" ] || [ -L "$path" ]; then
          rm -f -- "$path"
          removed=$((removed + 1))
        fi
        ;;
      c)
        template="$HERE/conf/$(basename -- "$path")"
        if [ ! -e "$path" ]; then
          :
        elif [ -f "$template" ] && cmp -s -- "$path" "$template"; then
          rm -f -- "$path"
          removed=$((removed + 1))
        else
          echo "left in place (edited by you, or the template is gone): $path" >&2
          kept=$((kept + 1))
        fi
        ;;
      p)
        cache="$path/__pycache__"
        if [ -d "$cache" ]; then
          if [ -z "$(find "$cache" ! -name '*.pyc' ! -name '*.pyo' ! -path "$cache" -print -quit)" ]; then
            rm -f -- "$cache"/*.pyc "$cache"/*.pyo 2>/dev/null || true
            rmdir -- "$cache" 2>/dev/null || true
            removed=$((removed + 1))
          else
            echo "left in place (not only bytecode): $cache" >&2
            kept=$((kept + 1))
          fi
        fi
        ;;
    esac
  done < "$work"

  # directories last, deepest first, and only while empty.
  awk '$1 == "d" { n = gsub(/\//, "/"); print n "\t" $0 }' "$work" \
    | sort -rn | cut -f2- \
    | while IFS=' ' read -r kind path; do
        [ -d "$path" ] || continue
        if rmdir -- "$path" 2>/dev/null; then
          :
        else
          echo "left in place (not empty): $path" >&2
        fi
      done

  echo "uninstalled: $removed file/config/cache entries removed, $kept left in place;"
  echo "  directories from the manifest pruned wherever they were left empty."
  exit 0
}

case "${1:-}" in
  --uninstall) do_uninstall ;;
  -h|--help)   usage; exit 0 ;;
  "")          ;;
  *)           echo "install.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
esac

# ------------------------------------------------------------------ install --
command -v python3 >/dev/null 2>&1 || { echo "install.sh: python3 >= 3.11 required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "install.sh: python3 >= 3.11 required (tomllib)" >&2; exit 1; }

# The manifest is built in a temp file because SHARE_DIR, where it finally
# lands, is itself one of the directories the run may have to create and record.
MANIFEST_TMP=$(mktemp "${TMPDIR:-/tmp}/hk-manifest.XXXXXX")
PRIOR=$(mktemp "${TMPDIR:-/tmp}/hk-manifest-prior.XXXXXX")
trap 'rm -f "$MANIFEST_TMP" "$PRIOR"' EXIT INT HUP TERM
# A re-install must not forget what the previous one created: a directory that
# already exists is not recorded again below, so the old manifest's entries are
# carried forward verbatim before the new manifest is written.
if [ -f "$MANIFEST" ]; then grep -v '^#' "$MANIFEST" > "$PRIOR" || true; fi

record() {  # record <kind> <path>
  printf '%s %s\n' "$1" "$2" >> "$MANIFEST_TMP"
}

ensure_dir() {  # mkdir -p, recording every level THIS run creates
  _ed_missing=
  _ed_p=$1
  while [ ! -d "$_ed_p" ]; do
    _ed_missing="$_ed_p
$_ed_missing"
    _ed_next=$(dirname -- "$_ed_p")
    if [ "$_ed_next" = "$_ed_p" ]; then break; fi
    _ed_p=$_ed_next
  done
  if [ -z "$_ed_missing" ]; then return 0; fi
  mkdir -p -- "$1"
  # shallowest first: that is creation order, and removal walks it backwards
  printf '%s\n' "$_ed_missing" | while IFS= read -r _ed_d; do
    if [ -n "$_ed_d" ]; then record d "$_ed_d"; fi
  done
}

install_file() {  # install_file <src> <dst> [chmod-mode]
  ensure_dir "$(dirname -- "$2")"
  cp -- "$1" "$2"
  if [ -n "${3:-}" ]; then chmod "$3" "$2"; fi
  record f "$2"
}

# ---- the CLI ---------------------------------------------------------------
# *.py only: never copy __pycache__ into a user's install.
for src in "$HERE"/hk/*.py; do
  install_file "$src" "$SHARE_DIR/hk/$(basename -- "$src")"
done
install_file "$HERE/bin/hk" "$SHARE_DIR/bin/hk" 755
ensure_dir "$BIN_DIR"
ln -sf "$SHARE_DIR/bin/hk" "$BIN_DIR/hk"
record f "$BIN_DIR/hk"

# ---- the kitten tree -------------------------------------------------------
for name in hk.py ladder.py fork_state.py; do
  install_file "$HERE/kitten/$name" "$KITTEN_DIR/$name"
done
# Vendored beside the kitten: ladder.py loads predicate.py BY PATH and hk.py
# loads config.py BY PATH, so the kitten tree is self-contained and the `hk`
# name is never looked up from inside it (BUG-3).
install_file "$HERE/hk/predicate.py" "$KITTEN_DIR/predicate.py"
install_file "$HERE/hk/config.py" "$KITTEN_DIR/config.py"
for src in "$HERE"/assets/*; do
  install_file "$src" "$KITTEN_DIR/assets/$(basename -- "$src")"
done
ensure_dir "$KITTEN_DIR"
cat > "$KITTEN_DIR/__init__.py" <<'PY'
"""Package marker for the installed herdr-kitten tree (generated by install.sh).

This directory is `hk` under the kitty config directory. The marker is what
makes `hk` a package there rather than a name a loose `hk.py` could claim:
that shadowing is BUG-3, the reason no gesture dispatched from an installed
tree before round2-02. Nothing imports this module; deleting it re-opens the
hole. The kitten itself is hk.py beside this file, loaded by kitty as
`kitten hk/hk.py`.
"""
PY
record f "$KITTEN_DIR/__init__.py"

# the maps live beside the kitten so `include hk-maps.conf` in kitty.conf is
# the whole wiring step, and its relative kitten path resolves from there
install_file "$HERE/conf/kitty-maps.conf" "$MAPS_FILE"

# Both trees are imported by python, which writes bytecode beside them — this
# very script triggers it below with `hk --version`. Owning the caches in the
# manifest is what lets --uninstall leave nothing behind.
record p "$SHARE_DIR/hk"
record p "$KITTEN_DIR"

# ---- config template, only if absent (never clobber user config) -----------
if [ -e "$HK_CONF_DIR/config.toml" ]; then
  echo "kept: $HK_CONF_DIR/config.toml (already yours; template not copied)"
else
  ensure_dir "$HK_CONF_DIR"
  cp -- "$HERE/conf/config.toml" "$HK_CONF_DIR/config.toml"
  record c "$HK_CONF_DIR/config.toml"
fi

# ---- the manifest, listing itself last -------------------------------------
ensure_dir "$SHARE_DIR"
record f "$MANIFEST"
while IFS= read -r prior_line; do
  if [ -n "$prior_line" ] && ! grep -qxF -- "$prior_line" "$MANIFEST_TMP"; then
    printf '%s\n' "$prior_line" >> "$MANIFEST_TMP"
  fi
done < "$PRIOR"
{ manifest_header; cat "$MANIFEST_TMP"; } > "$MANIFEST"

echo "installed:"
echo "  $BIN_DIR/hk -> $SHARE_DIR/bin/hk"
echo "  $KITTEN_DIR/  (kitten: 'kitten hk/hk.py')"
echo "  $MAPS_FILE"
echo "  $MANIFEST  ('sh install.sh --uninstall' removes exactly what it lists)"
echo "wire it up: add   include hk-maps.conf   to $KITTY_DIR/kitty.conf"
echo "herdr profile snippet to merge by hand: $HERE/conf/herdr-profile.toml"
"$BIN_DIR/hk" --version
