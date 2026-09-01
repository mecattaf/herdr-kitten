"""hk-config — the ONE repo config file (spec F.4), read with tomllib.

Missing file -> every verb runs on these defaults and writes nothing (spec 1.4).
"""

from __future__ import annotations

import os
import tomllib

DEFAULTS = {
    "plain_scrollback_action": "show_scrollback",  # spec D12
    "notify_command": "notify-send",               # spec D26
}


def config_path() -> str:
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config_home, "hk", "config.toml")


def load() -> dict:
    merged = dict(DEFAULTS)
    try:
        with open(config_path(), "rb") as fh:
            merged.update(tomllib.load(fh))
    except FileNotFoundError:
        pass
    return merged
