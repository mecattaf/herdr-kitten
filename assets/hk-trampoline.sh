# hk trampoline hook (spec D5, census P10; POSIX sh — source from your shell rc,
# e.g. `. /path/to/hk-trampoline.sh` in .bashrc/.zshrc, or the fish translation).
# A pane launched by `hk run` carries HK_EXEC=<base64 of a shell-quoted argv>.
# Decode, unset, exec — the payload's exit IS the pane's exit, and herdr's
# RuntimeExitAction::ClosePane reaps the pane (probe P-G3 proved this live).
if [ -n "${HK_EXEC:-}" ]; then
  # GNU coreutils spells it -d, older BSD/macOS base64 spells it -D.
  _hk_payload=$(printf '%s' "$HK_EXEC" | base64 -d 2>/dev/null) \
    || _hk_payload=$(printf '%s' "$HK_EXEC" | base64 -D 2>/dev/null) \
    || _hk_payload=""
  unset HK_EXEC
  if [ -n "$_hk_payload" ]; then
    eval "set -- $_hk_payload"
    unset _hk_payload
    exec "$@"
  fi
  unset _hk_payload
fi
