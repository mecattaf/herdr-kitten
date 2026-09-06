# PR #35 — the evidence, banked

PR **#35** (`round2-03-followup` → `main`, issue #17) is one commit, `bc0f3a3`,
"hygiene: kill the junk file at its source, and close the hole that let it back".
It is open.

This page is the evidence a reviewer needs to merge it, in the form that can be
re-run instead of re-read. **The merge command is at the bottom, prepared and
not run** — see [Who merges](#who-merges).

---

## 1. What #35 fixes

Two defects, one symptom: a zero-byte file literally named `herdr: fake blocked`
kept appearing at the repo root, and once appeared *tracked*.

**The cause.** `hk/notifyd.py`'s `run_notify` appends the notification message
as a final argv element:

```python
cmd = self.notify_command.split() + [f"herdr: {agent or pane_id} {state}"]
```

That is correct in production — `notify-send "herdr: agent blocked"` wants
exactly that argument. But gate **G8** configured `notify_command = "touch
$SBX/hit"`, so notifyd executed

```
touch /tmp/hk-smoke.XXX/hit "herdr: fake blocked"
```

and `touch` dutifully created the second file in its cwd, which was the repo
root, on **every run of the battery**. round2-03 was right that nothing in the
sources recreated the file and wrong that nothing did: the fixture did, through
a product behaviour that is right everywhere else. #35 points G8's
`notify_command` at a wrapper script that discards `"$@"`.

**The hole.** Every assertion in `tests/unit/test_repo_hygiene.py` inspected
**tracked** files. The sequence that reintroduced the junk was "run the battery,
`git add -A`, commit" — the tests ran *before* the add, so nothing was tracked
yet and the gate passed on a repo that already had litter sitting in it. #35
adds `test_working_tree_root_is_clean_too`, which inspects the working tree and
fails on any untracked, non-gitignored entry at the repo root.

---

## 2. The proof, and how to re-run it

```
sh tests/proofs/pr35-proof.sh              # GREEN: the fix holds        -> rc 0
sh tests/proofs/pr35-proof.sh --red        # RED:   the gate has teeth   -> rc 0
```

The harness copies the main checkout with `cp -a`, forces a pristine `bc0f3a3`
inside the copy, runs the unit suite and the headless battery, and then asserts
the copy's `git status --porcelain` is empty. It never writes into the source
repo and never reaches the network.

Two things it pins deliberately, both learned the hard way in this lane:

- **It checks out a rev, not a branch name.** A branch name in a shared checkout
  is a moving target. While this page was being written, a parallel lane
  committed three unrelated commits straight onto `round2-03-followup`; a run
  against the name then measured a different tree and reported a different test
  count. `bc0f3a3` cannot drift.
- **It deletes the copy's `.git/worktrees` first.** `cp -a` carries the source's
  linked-worktree registrations, which still point at real directories, so the
  copy refuses to check out any branch that is live in one of them —
  *"already used by worktree at ..."*. Unhandled, that failure is quiet, and the
  copy keeps the source's uncommitted tree while the run looks like it worked.

### GREEN — measured

```
pr35-proof: mode=green ref=bc0f3a36fae08862040a2e38a75d2c97b483df8a head=bc0f3a36fae08862040a2e38a75d2c97b483df8a
pr35-proof: head is the rev PR #35 is open at
pr35-proof: copy is pristine before the battery
pr35-proof: unit suite ran=118 rc=0 tail=OK
pr35-proof: headless battery rc=0 gates_pass=12
pr35-proof: clean-root proof OK — git status --porcelain is empty after the battery
pr35-proof: GREEN OK — 118 units, 12 gates, zero root litter
```

The twelve gates, all PASS: G1, G3, G4, G5, G6, G7, G9, G15, G16, G17, G8, G14.
G14 (fork round-trip) really executed rather than skipping — nvim is present on
this box.

**118 is the measured unit count.** `docs/dev/METRICS.md` still says 66; that
figure is stale by 52 and is a separate, documentation-only correction. This
unit deliberately adds no unit tests, because it is the unit that proves the
number.

### RED — measured

Plant `herdr: fake blocked` at the copy's root, then run the suite:

```
pr35-proof: planted untracked litter at the copy root: 'herdr: fake blocked'
pr35-proof: unit suite ran=118 rc=1 tail=FAILED (failures=1)
pr35-proof: RED OK — test_working_tree_root_is_clean_too caught the litter
```

One failure, and it is the right one. A GREEN run with no RED run is not
evidence that a gate works; it is evidence that a gate is quiet.

---

## 3. Two counter-facts, both measured, both worth keeping

### 3.1 `cp -a`, never `git archive | tar -x`

The archive form ships a tree with **no `.git`**, so the five git-based
assertions in the hygiene module die inside `git ls-files`:

```
subprocess.CalledProcessError: Command '['git', 'ls-files', '-z']'
returned non-zero exit status 128
Ran 118 tests in 0.42s
FAILED (errors=5)                                              # rc 1
```

— on a tree that is perfectly healthy. The same tree copied with
`cp -a <repo>/. <dir>/` reports `Ran 118 tests ... OK`, rc 0. Any harness that
cannot tell a healthy tree from a broken one is not evidence, so the script
hard-codes the `cp -a` form and says why.

### 3.2 The battery still litters a checkout of `main`

`main` is `00a7395`; `git ls-tree -r --name-only main` still lists
`herdr: fake blocked` as a **tracked** file, and `git diff --name-status
00a7395 bc0f3a3` shows it deleted only at `bc0f3a3` — that is, only on #35.
In a throwaway copy checked out to `main`:

| step | result |
|---|---|
| unit suite on `main` | `Ran 117 tests ... FAILED (failures=3)` |
| delete the junk file, `git status --porcelain` | ` D "herdr: fake blocked"` |
| run `tests/smoke/run-headless.sh` | rc 0 |
| does the file exist again? | **yes**, zero bytes, recreated by the battery |
| `git status --porcelain` afterwards | **empty** |

That last row is the whole argument for #35 in one line: on `main` the litter
is *tracked*, so recreating it leaves the working tree looking clean. The
tracked-file gate could never have caught it, and the working-tree gate did not
exist yet. Until #35 lands, run the battery from a copy — which is what the
harness does.

---

## 4. Who merges

**Not this branch, and not a worker.** The merge is a network act against a
private repository and it is the reviewer's approval, not a build step. The
standing instruction for this run is explicit — Tom, 2026-09-06, verbatim:

> "Nothing is armed, kept, pushed, switched, deployed or restarted; every unit
> that needs a number of Tom's stops at its last honest commit and names the
> number."

— RULINGS.md, R-2026-09-06-09, operator reading.

So this unit banks the evidence and stops here. The command below is **prepared
and has not been run.** It matches the precedent set by #32, #33 and #34, which
landed as merge commits and left their source branches on the remote:

```sh
# NOT RUN. Tom's to run, from /home/tom/mecattaf/herdr-kitten, when he agrees.
gh pr merge 35 --repo mecattaf/herdr-kitten --merge
```

Preconditions a reviewer can re-check first, offline, in any order:

```sh
sh tests/proofs/pr35-proof.sh          # rc 0, 118 units, 12 gates, clean root
sh tests/proofs/pr35-proof.sh --red    # rc 0, the hygiene gate bites
git rev-parse origin/round2-03-followup      # want: bc0f3a3... — what #35 holds
git log --oneline bc0f3a3 ^main              # exactly one commit
```

**One caveat, measured, that a reviewer should see before running the merge.**
The *local* `round2-03-followup` in `/home/tom/mecattaf/herdr-kitten` is no
longer `bc0f3a3`: a parallel lane committed three commits onto it
(`2662e5d`, `727966f`, `58c3a2e`, all BUG-6 / `--spin` work belonging to issue
#23, not to #17). They are **local only** — `origin/round2-03-followup` is still
exactly `bc0f3a3`, nothing has been pushed — so **PR #35 as GitHub holds it is
unchanged** and the command above is still the right one. But `git push` on that
branch from that checkout would silently widen an open PR from one hygiene
commit to four commits spanning two issues. Those three commits want their own
branch (`hk/round2-08-bug6-focus`) before anything is pushed. Whether to move
them is not this unit's call.

And the one check that only means something *after* the merge:

```sh
git ls-tree -r --name-only main | grep -c 'herdr: fake blocked'   # want: 0
sh tests/proofs/pr35-proof.sh --branch main                       # want: rc 0
```

The repository is **private** and stays private through all of this: no
visibility flip, no `gh repo edit`, no announcement. Those are separate
decisions and they are Tom's too.

---

## 5. What this page does not claim

- It does not claim #35 is ready to ship the project. `#31` is the only issue
  allowed to declare ship-ready, and this is not it.
- It does not run `nix flake check`. `checks.herdr-kitten-build` wants kitty in
  the build sandbox and `herdr-kitten-smoke` wants the pinned herdr input built;
  neither is cheap-and-offline, so both are unmeasured here.
- It does not touch the six attended or conditional gates (G2, G10, G11, G12,
  G13, G-ssh), which are not in the headless driver's list.
