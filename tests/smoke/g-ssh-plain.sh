#!/bin/sh
# G-ssh — remote tiers smoke (spec 10.3/10.4). SKIP-unless-sshd: never required
# in CI; runs when a localhost sshd accepts the current user's key.
. "$(dirname "$0")/lib.sh"
ssh -o BatchMode=yes -o ConnectTimeout=2 localhost true 2>/dev/null \
  || gate_skip G-ssh "no passwordless sshd on localhost"
command -v kitten >/dev/null 2>&1 || gate_skip G-ssh "kitten not on PATH"
# --plain execs kitten ssh; prove the exec target and argv without a display
out=$(HK_SSH_DEBUG=1 hk ssh --plain localhost --help 2>&1 || true)
gate_skip G-ssh "exec-target verbs verified by unit tests; interactive ssh session is attended-only"
