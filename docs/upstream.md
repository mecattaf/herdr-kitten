# Upstream asks — ready-to-file drafts (filing is HUMAN-ATTENDED, spec 12.2)

Four asks, each a complete issue body for github.com/herdrdev/herdr. None filed tonight
(unattended run; herdr's tracker is an external, human-attended surface). Check for
duplicates at filing time; replace the placeholders with issue URLs once filed.

---

## Ask 1 — `pane split --command <argv>` (argv panes without a trampoline)

**URL once filed:** _pending_

**Title:** feature: `pane split --command` to launch a pane running a specific argv

**Body:**
`herdr pane split` today launches the configured shell; there is no way to create a pane
whose root process is a caller-chosen argv. Integrations that want "run this command in a
new pane, and reap the pane when it exits" must smuggle the argv through `--env` (e.g. a
base64 payload) plus a shell-rc trampoline hook that decodes and `exec`s it, so the payload's
exit becomes the pane's exit (`RuntimeExitAction::ClosePane`). That works (verified on 0.8.2)
but requires every user of the integration to install a shell hook.

Proposal: `herdr pane split [--command <argv...>]` (and the matching socket param on
`pane.split`) launching the argv directly as the pane root process, inheriting the
existing exit-action semantics. This removes the single largest piece of glue plumbing
for external integrations (ours: a kitty kitten that projects herdr panes onto kitty
windows).

---

## Ask 2 — raise or configure the `pane.read` 1000-line cap

**URL once filed:** _pending_

**Title:** feature: make the server-side `pane.read` line cap configurable

**Body:**
`pane read --lines N` silently clamps to 1000 lines server-side regardless of the requested
value (0.8.2: requesting 5000 over a 2000-line history returns 999 lines, exit 0, no
truncation indicator). Terminal emulators commonly hold 100k lines of scrollback; scripted
consumers (editors, pagers, log processors) reading through the socket hit a 99% reduction
with no signal that truncation happened.

Proposal: (a) a config key or request param to raise the cap for local sockets, and
(b) a `truncated: true` field in the read response so clients can surface the fact.
Either half alone is already useful.

---

## Ask 3 — `pane read --source last-cmd-output` (prompt-mark extents)

**URL once filed:** _pending_

**Title:** feature: read the last command's output via OSC 133 prompt marks

**Body:**
Sources today are visible|recent|recent-unwrapped|detection. Shells with OSC 133
integration mark prompt/output extents, and kitty exposes "last command output" natively
on plain windows; inside herdr panes those marks are consumed by the VT layer and no
equivalent read source exists. Scripted consumers (e.g. "send the failing command's
output to an agent") must heuristically parse `recent` output instead.

Proposal: `pane read --source last-cmd-output` returning the extent between the most
recent OSC 133;C and 133;D marks the VT layer already sees.

---

## Ask 4 — expose bracketed-paste state in `PaneInfo`

**URL once filed:** _pending_

**Title:** feature: bracketed-paste mode flag in pane snapshots

**Body:**
`pane send-text` sends raw bytes (correct, verified 0.8.2 — no auto-framing). A client
that wants to deliver pasted text safely must decide whether to frame it with
`\x1b[200~`/`\x1b[201~`, but whether the application in the pane has ENABLED bracketed
paste (DECSET 2004) is known only to the VT layer; the client can only guess. TUIs that
have not enabled it render the frame bytes as garbage.

Proposal: a `bracketed_paste: bool` field on `PaneInfo` (pane list/read responses),
reflecting the live DECSET 2004 state, so clients can frame if-and-only-if the
application will interpret it.
