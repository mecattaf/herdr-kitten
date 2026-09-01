#!/bin/sh
# herdr-kitten installer for non-nix hosts (spec 1.1). Copies files; never edits configs.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN_DIR="${HK_BIN_DIR:-$HOME/.local/bin}"
KITTY_DIR="${HK_KITTY_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/kitty}"
HK_CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hk"
SHARE_DIR="${HK_SHARE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/hk}"

command -v python3 >/dev/null 2>&1 || { echo "install.sh: python3 >= 3.11 required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "install.sh: python3 >= 3.11 required (tomllib)" >&2; exit 1; }

mkdir -p "$BIN_DIR" "$KITTY_DIR" "$SHARE_DIR"
# the hk package must sit beside bin/hk's parent (bin/hk resolves ../hk)
cp -R "$HERE/hk" "$SHARE_DIR/"
mkdir -p "$SHARE_DIR/bin"
cp "$HERE/bin/hk" "$SHARE_DIR/bin/hk"
chmod +x "$SHARE_DIR/bin/hk"
ln -sf "$SHARE_DIR/bin/hk" "$BIN_DIR/hk"

# kitten + assets into the kitty config dir (kitty loads kittens from there);
# ladder.py + fork_state.py install flat beside hk.py (its import fallback)
cp "$HERE/kitten/hk.py" "$KITTY_DIR/hk.py"
cp "$HERE/kitten/ladder.py" "$KITTY_DIR/ladder.py"
cp "$HERE/kitten/fork_state.py" "$KITTY_DIR/fork_state.py"
mkdir -p "$KITTY_DIR/hk-assets"
cp -R "$HERE/assets/." "$KITTY_DIR/hk-assets/"

# config template only if absent (never clobber user config)
if [ ! -e "$HK_CONF_DIR/config.toml" ]; then
  mkdir -p "$HK_CONF_DIR"
  cp "$HERE/conf/config.toml" "$HK_CONF_DIR/config.toml"
fi

echo "installed: $BIN_DIR/hk, $KITTY_DIR/hk.py, $KITTY_DIR/hk-assets/"
echo "suggested kitty maps: $HERE/conf/kitty-maps.conf (include it from kitty.conf)"
echo "herdr profile snippet to merge by hand: $HERE/conf/herdr-profile.toml"
"$BIN_DIR/hk" --version
