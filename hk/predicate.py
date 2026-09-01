"""The herdr-client predicate — the ONE module answering
"does this kitty window host a herdr client?" (spec D3, claim 2.4).

Three consumers import this and nothing else re-implements it:
the toggle ladder (kitten/hk.py), fork hygiene (kitten/hk.py), the dispatcher.

Rule (spec D3, census-map P05): the `hk_role` user-var is PRIMARY;
foreground-process argv containing `herdr` is CONFIRMING-ONLY, because it
false-positives under `herdr --remote` where the local process IS herdr.

Pure functions over kitty window dicts (the shape `kitty @ ls` returns and the
shape the kitten sees on `boss.window_id_map` entries via reflection), so the
routing logic unit-tests without kitty.
"""

from __future__ import annotations

# Roles that mark a window as herdr-involved. `herdr_ui` is the thin client
# (spec D13); any hk-stamped role means an hk verb created or attached it.
HERDR_ROLES = frozenset({"herdr", "herdr_ui", "fork", "editor"})


def role_of(window: dict) -> str | None:
    """The hk_role user-var of a kitty window dict, or None."""
    user_vars = window.get("user_vars") or {}
    role = user_vars.get("hk_role")
    return role if isinstance(role, str) and role else None


def argv_confirms(window: dict) -> bool:
    """Confirming-only signal: a foreground process whose argv[0] is herdr."""
    for proc in window.get("foreground_processes") or []:
        cmdline = proc.get("cmdline") or []
        if cmdline and str(cmdline[0]).rsplit("/", 1)[-1] == "herdr":
            return True
    return False


def is_herdr_client(window: dict) -> bool:
    """PRIMARY: hk_role user-var. CONFIRMING-ONLY: herdr in the foreground argv.

    A window with an hk_role in HERDR_ROLES is a herdr client, full stop.
    A window with NO role but herdr in the foreground argv is treated as a
    herdr client (e.g. a hand-launched `herdr` the kitten should defer to).
    """
    role = role_of(window)
    if role is not None:
        return role in HERDR_ROLES
    return argv_confirms(window)


def is_thin_client(window: dict) -> bool:
    """True only for the remote thin client tier (spec 10.5): hk_role=herdr_ui."""
    return role_of(window) == "herdr_ui"
