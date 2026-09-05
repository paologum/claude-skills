---
name: unity-iterate
description: The iteration loop for Unity work driven by Coplay MCP — what to do (and NOT do) when you're taking many small edits + rebuilds + screenshots in a single session. Covers the runtime footguns that keep re-biting mid-session (routing to the wrong Editor, force-push blocked by classifier, screenshot cadence for UI PRs, image URLs that render vs 404 on private repos, when a "just rebase" gets you superseded upstream). NOT the same as `/unity-mcp-setup` (that's first-time install) or `/unity-switch-worktree` (that's target-project changes). This is the tight-loop iteration playbook. Use when a Unity+MCP session is going many rounds — screenshot / edit / test / push / re-check — and mid-session you hit "my calls are hitting the wrong project", "the classifier blocked my push", "the reviewer says X, do I trust it", or "I just rebased and there's a conflict on code that got superseded upstream".
allowed-tools: "Read Bash(git *) Bash(gh *) Bash(pgrep *) Bash(kill *) Bash(lsof *) Bash(nohup *) Bash(disown *) Bash(mkdir *) Bash(osascript *) Bash(shasum *) Bash(diff *) Bash(ls *)"
argument-hint: "(optional) which loop phase to focus on"
---

## Context

**Unity Editors reachable over the stdio bridge (port + project each one owns):**
```
!`cat ~/.unity-mcp/unity-mcp-status-*.json 2>/dev/null || echo "no Editor bridges registered"`
```

**Currently-running Unity Editor processes:**
```
!`ps -eo pid,args | awk '/Unity\.app\/Contents\/MacOS\/Unity/ && /-projectPath/ && !/awk/' | head -3 || echo "no Editor running"`
```

**Current branch + how far behind main it is (if in a git repo):**
```
!`git branch --show-current 2>/dev/null; git fetch origin 2>/dev/null; git log --oneline HEAD..origin/main 2>/dev/null | head -5 || echo "already up to date or no origin/main"`
```

## Your task

You are inside a Unity iteration loop — many small cycles of edit → refresh → test → screenshot → commit → push in a single session. This skill is the playbook for the recurring gotchas. Don't invoke it once and forget — re-read the relevant section whenever the symptom appears.

---

### Section 1 — MCP readiness: use the resource, never a shell poll

**The right check is one call:** `ReadMcpResourceTool` with `server: "UnityMCP"`,
`uri: "mcpforunity://instances"`.

- `instance_count > 0` → an Editor is reachable. Call `mcp__UnityMCP__set_active_instance`
  with the `Name@hash` id, then verify with `execute_code { return UnityEngine.Application.dataPath; }`.
- `instance_count == 0` → the Editor isn't listening yet. **Don't loop in Bash.** Use
  `ScheduleWakeup` (60–90s) and re-check on wake. A cold `Library/` import can take
  minutes.

The fallback, if `ReadMcpResourceTool` isn't in this session's toolset (rare — deferred
until after ToolSearch), is to read the status files the Editors publish:

```bash
cat ~/.unity-mcp/unity-mcp-status-*.json
```

Each carries `unity_port`, `project_path`, `reloading` and `last_heartbeat` — everything
the resource reports. A single `cat` or `lsof` is fine; an `until … done` loop around
either is what's blocked, and rightly so.

---

### Section 2 — the MCP server outlives Unity; stop treating restarts as MCP events

Under stdio the server is a child of **your Claude Code session**, not of any Editor.
It binds its tools at session start and keeps them for the whole session, whether or not
Unity is running. Closing the Editor, restarting it, letting it domain-reload, or
switching it to another worktree does not disturb the MCP connection at all.

So when a call fails, read the failure literally:

- **`"No Unity Editor instances found"`** → no Editor is listening. It's importing,
  closed, or its Transport dropdown isn't on Stdio. Wait, or open it. Don't restart
  Claude Code, don't kill anything.
- **`"Unity is reloading; please retry"`** → a domain reload is in flight. Retry; the
  server already backs off and reconnects on its own.
- **Calls land on the wrong project** → Section 2b.
- **`mcp__UnityMCP__*` tools missing entirely** → this is the one failure stdio can't
  recover from mid-session: the server never spawned (usually `uvx` unresolvable in the
  launch environment). Nothing you do in-session brings the tools back. Report it, and
  point at `/unity-mcp-setup`.

**Never kill the MCP server process to "reset" it.** There's no mechanism to respawn it
mid-session; you'd be trading a recoverable problem for an unrecoverable one.

---

### Section 2b — calls are routing to a different worktree's Editor

Symptoms: `mcpforunity://instances` lists more than one Editor and your calls hit the
wrong one, or `execute_code { return UnityEngine.Application.dataPath; }` returns another
worktree's path, or a call errors with `instance_selection_required`.

This is routing, not breakage. Multiple Editors coexisting is the normal state — each
has its own socket (6400, 6401, …) and its own entry.

```
mcp__UnityMCP__set_active_instance instance="<Name@hash>"
```

Then **verify by routing a real call**, not by trusting the return value:

```csharp
// via mcp__UnityMCP__execute_code
return UnityEngine.Application.dataPath;
```

Must end in `<your-worktree>/Assets`. Match instances by `path`, not `name` — two
worktrees of the same repo report the same project name.

For one-off calls against another Editor without moving the session pin, pass
`unity_instance="6401"` (its port) or `unity_instance="<hash-prefix>"` on that call.

**Don't:** kill Editors, kill the server, or restart Claude Code for this. Under HTTP a
wrong-instance bind meant bridge surgery; under stdio it's one `set_active_instance`.

### Section 3 — Screenshot cadence for UI PRs

For any PR that touches UI (`*.unity`, `*.prefab`, `Assets/**/*.png`, HUD scripts), every code change deserves an inline screenshot in the same response — not a batched delivery, not "let me finish these three changes and then show you." The user shouldn't have to ask.

Rules that have hurt when broken:

- **Every affected screen, every response.** If the PR covers lobby / game / results / tax, re-embed all four every time, even if only one changed. Reviewers scroll one message, not the whole session.
- **Inspect each label before shipping.** Read every visible button / row / field for text wrap, truncation, clipping, misaligned columns. Static screenshots are the whole point — noticing "1st / 2nd / 3rd are visually staggered because of digit-glyph width variance" happens here, not after merge.
- **Before push, not after.** Capture → inline → wait for OK → then commit and push. Same for a PR body rewrite — preview inline first.
- **Never commit screenshots to the repo.** `docs/pr-screenshots/` (or wherever) is git-ignored. Upload via `gh attach upload --target <owner>/<repo>#<PR> --format url <path>` and paste the returned URL into the PR body. That's the flow `/pr-screenshot` and `/pr-video` automate — do it manually when they're not the right fit (e.g. images assembled outside Unity).
- **Image URL scheme matters.** `raw.githubusercontent.com/.../<slashy-branch>/...` 404s in private-repo PR bodies (branch-slash confused with path). Use `gh attach` — it returns either a release-asset URL or a `raw/refs/heads/gh-attach-assets/<uuid>/...` URL, both of which render inline.

---

### Section 4 — The classifier hard-blocks `git push --force-with-lease`

If the user tells you to force-push, don't try — the classifier blocks it regardless of consent. Report the block once, print the command, and let them run it:

```
cd <worktree> && git push --force-with-lease
```

Plain fast-forward `git push` **is** allowed (user-approved), so if you can avoid a rewrite (`--amend`, `rebase -i`, dropping commits), you can push yourself. Prefer that when possible — but never sneak amend just to dodge the block if the user asked for a rebase.

Note: `/harden-permissions` in this repo installs an `enforce-safety` hook that also blocks force-push. That's a defense in depth — the classifier + the hook + the memory `no-push-without-approval`. All three point the same way.

---

### Section 5 — When upstream advances, rebase before pushing more

If `git log HEAD..origin/main` shows commits, rebase before making more commits — not after. Merge conflicts on stale code are much worse than resolving them one commit ahead of upstream.

Resolution discipline:

- **Accept HEAD (main) when it supersedes yours.** If main introduced a more robust fix for the same bug you were fixing (typical for shared systems: netcode, tax, deal), drop your version wholesale. Don't try to keep both — they were solving the same problem.
- **Delete dead code from resolution.** If you dropped a method by taking HEAD, `grep` for its callers to prove it's orphaned, then delete the method, its private fields, its comment block. Merge resolution isn't done until the tree is clean of the dropped code.
- **Rebase + force-push is Section 4.** Push is on the user.

---

### Section 6 — Trust PR reviewers, but audit each claim

When a reviewer (human or AI) files findings, don't accept them wholesale. For each:

1. `grep`/`Read` the specific line they cite. If the claim isn't grounded in the current code, push back with the actual lines.
2. Reproduce the failure mode they describe. If you can't reproduce it, don't ship a fix for it — see Section 7.
3. Distinguish **must-fix** (correctness bugs, confirmed) from **nice-to-have** (style, refactor, hypothesis). Address must-fixes; be explicit about which nice-to-haves you skipped and why.
4. Reply with what you took, what you pushed back on, and why — with links to docs / specs when the reasoning depends on language / framework behavior (e.g. C# `%` sign, Unity's `RuntimeInitializeOnLoadMethod`).

The related memory `feedback_ai_review_wrong` covers the "stop when the review is wrong" case. This section covers the "review is mostly right, verify each item" case.

---

### Section 7 — Don't ship speculation for a bug you can't reproduce

When a bug's root cause is unclear:

- Reproduce it first. If reproduction requires a live 4-player MPPM session, spin one up — a defensive scattergun of `reset three things` is worse than an open issue with a clear repro request.
- If reproduction isn't possible in this session, **say so and don't fix.** Add a follow-up task, leave the issue open, note what you'd need. That's more professional than merging a "fix" you can't defend.
- If you already shipped a speculative fix, revert it cleanly and update the PR body / issue to reflect that the bug is still open.

The instinct to always ship a diff is wrong. "Verified I can't reproduce, needs live capture" is a legitimate outcome.

---

### Section 8 — Task list discipline for long sessions

Long iteration sessions accumulate 20+ tasks. Keep them accurate:

- Mark `in_progress` on the CURRENT task, `completed` the second it lands. Don't batch.
- When a task's premise changes (bug turned out to be something else, PR pivoted), `deleted` the old one and `TaskCreate` a fresh one — don't stretch a stale task to fit new scope.
- Clean up between phases. A task list from an older workstream on a different branch is misleading — either `deleted` those or don't reason from them.

The task list is what the user sees to know where you are. Wrong tasks are worse than no tasks.

---

## Composition

- Upstream: `/start-task` puts you in an isolated worktree.
- Enter: this skill, when the iteration loop begins.
- Sibling: `/unity-switch-worktree` — different problem (target project change).
- Sibling: `/unity-mcp-setup` — different problem (first-time install broken).
- Downstream: `/pr-description`, `/pr-screenshot`, `/pr-video`, `/unity-e2e-verify` — the actual work each iteration does.
