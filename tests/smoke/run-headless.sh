#!/bin/sh
# The headless smoke battery (spec D27): the subset that needs no kitty window.
# Runs standalone AND as the flake check herdr-kitten-smoke.
#
# g18-install-layout needs no window either, but it does need the kitty BINARY
# (it drives the installed kitten through kitty's own loader with `kitty
# +launch`). It skips with a printed reason when kitty is absent, and the flake
# check sets HK_REQUIRE_KITTY=1 so that skip is a failure there.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HEADLESS="g01-headless-liveness g03-trampoline-self-reap g04-bracketed-populate g05-rename-durability g06-submit-refusal g07-read-cap g09-materialise-roundtrip g15-join-keys g16-resume-picker g17-workspace-verbs g08-event-loop g14-fork-roundtrip g18-install-layout"
fails=0
for g in $HEADLESS; do
  sh "$HERE/$g.sh" || fails=$((fails + 1))
done
[ "$fails" -eq 0 ] || { echo "run-headless: $fails gate(s) FAILED"; exit 1; }
echo "run-headless: all executed, none failed"
