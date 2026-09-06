# DECISIONS

2026-09-06 orchestrator B: merged U-C2 PR35-PROOF, U-C3, U-C4, U-C5 to main under the handoff's merge authority; gate `PYTHONPATH=. python3 -m unittest discover -s tests/unit | tail -1 | grep -qx OK && sh tests/smoke/run-headless.sh && test -z "$(git status --porcelain)"` rc 0; receipts under /home/tom/research-methods/receipts/FACTORY-2026-09-06/.
