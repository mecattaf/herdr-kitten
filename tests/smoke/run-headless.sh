#!/bin/sh
# The headless smoke battery (spec D27): the subset that needs no kitty window.
# Runs standalone AND as the flake check herdr-kitten-smoke.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HEADLESS="g01-headless-liveness g03-trampoline-self-reap g05-rename-durability g06-submit-refusal g07-read-cap g15-join-keys g16-resume-picker g17-workspace-verbs"
fails=0
for g in $HEADLESS; do
  sh "$HERE/$g.sh" || fails=$((fails + 1))
done
[ "$fails" -eq 0 ] || { echo "run-headless: $fails gate(s) FAILED"; exit 1; }
echo "run-headless: all executed, none failed"
