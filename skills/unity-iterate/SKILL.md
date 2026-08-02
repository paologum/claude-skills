---
name: unity-iterate
description: The iteration loop for Unity work driven by Coplay MCP — what to do (and NOT do) when you're taking many small edits + rebuilds + screenshots in a single session. Covers the runtime footguns that keep re-biting mid-session (MCP session going orphan, force-push blocked by classifier, editor restart vs unity-mcp-setup, screenshot cadence for UI PRs, image URLs that render vs 404 on private repos, when a "just rebase" gets you superseded upstream). NOT the same as `/unity-mcp-setup` (that's first-time install) or `/unity-switch-worktree` (that's target-project changes). This is the tight-loop iteration playbook. Use when a Unity+MCP session is going many rounds — screenshot / edit / test / push / re-check — and mid-session you hit "the bridge died", "the classifier blocked my push", "the reviewer says X, do I trust it", or "I just rebased and there's a conflict on code that got superseded upstream".
allowed-tools: "Read Bash(git *) Bash(gh *) Bash(pgrep *) Bash(kill *) Bash(lsof *) Bash(nohup *) Bash(disown *) Bash(mkdir *) Bash(osascript *) Bash(shasum *) Bash(diff *) Bash(ls *)"
argument-hint: "(optional) which loop phase to focus on"
---

## Context

**Which Unity Editor instance the MCP tools will hit:**
```
!`curl -s http://127.0.0.1:8080/mcp -H "Content-Type: application/json" -H "Accept: application/json,text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"resources/read","params":{"uri":"mcpforunity://instances"}}' 2>/dev/null | grep -oE '"name":[[:space:]]*"[^"]+"' | head -1 || echo "MCP HTTP endpoint not answering — either editor is down or session is orphaned"`
```

**Currently-running Unity Editor + Coplay Python holding the bridge:**
```
!`ps -eo pid,args | awk '/Unity\.app\/Contents\/MacOS\/Unity/ && /-projectPath/ && !/awk/' | head -3; lsof -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | head -3`
```

**Current branch + how far behind main it is (if in a git repo):**
```
!`git branch --show-current 2>/dev/null; git fetch origin 2>/dev/null; git log --oneline HEAD..origin/main 2>/dev/null | head -5 || echo "already up to date or no origin/main"`
```

## Your task

You are inside a Unity iteration loop — many small cycles of edit → refresh → test → screenshot → commit → push in a single session. This skill is the playbook for the recurring gotchas. Don't invoke it once and forget — re-read the relevant section whenever the symptom appears.

---

### Section 1 — MCP readiness: use the resource, never `curl`

The Coplay HTTP endpoint on `:8080` does **not** answer plain `GET /`. Any `curl http://127.0.0.1:8080` hangs until timeout. Any `Monitor` / `until` loop that curls the bridge hangs the same way. Don't do it.

**The right check is one call:** `ReadMcpResourceTool` with `server: "UnityMCP"`, `uri: "mcpforunity://instances"`.

- `instance_count > 0` → bridge is up. Call `mcp__UnityMCP__set_active_instance` with the `Name@hash` id, then verify with `execute_code { return UnityEngine.Application.dataPath; }`.
- `instance_count == 0` → wait. **Not with curl.** Foreground `Bash sleep 20 && echo done` (allowed), then retry `ReadMcpResourceTool`. Up to ~3 retries. If the editor is genuinely cold-importing a fresh `Library/`, one `sleep 60` between retries.

**The only time a pidfile poll is correct:** if `ReadMcpResourceTool` is not in this session's toolset at all (rare — deferred until after ToolSearch). Then use `until ls <target>/Library/MCPForUnity/RunState/mcp_http_*.pid; do sleep 15; done` — never `curl`.

If you catch yourself typing `until curl ...` in a Bash whose subject is Unity, stop.

---

### Section 2 — MCP session orphaned mid-session (NOT the same as unity-mcp-setup)

Symptoms: `execute_code` returns `{"success": false, ..., "reason": "no_unity_session"}`, but Editor process is alive AND the Python on `:8080` is alive. Editor log has `MCP-FOR-UNITY: Server no longer running; ending orphaned session`.

This is a **runtime** bind failure. First-time-setup (uv installed, pyenv Python 3.10+, Coplay package in manifest, Claude Code registered via HTTP) is all fine. **Don't invoke `/unity-mcp-setup`** — its diagnostic table will pass every check and you'll waste calls. It's a different problem.

The fix:

```bash
# Kill the stale Python that's holding :8080 but no longer connected to the editor.
lsof -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $2}' | xargs kill 2>/dev/null
# Restart the Editor on the same worktree it was on.
osascript -e 'tell application "Unity" to quit' 2>&1 || true
sleep 5
editor_pid=$(pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath" | head -1)
[ -n "$editor_pid" ] && kill "$editor_pid"
sleep 3
nohup "/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity" \
  -projectPath "<worktree>" > "<worktree>/test-results/editor.log" 2>&1 &
disown
```

Then Section 1 for wait-for-bridge, then `set_active_instance`, then verify with `Application.dataPath`.

This case has hit repeatedly in long sessions (5+ times in one). Recognize it fast so you don't burn tokens diagnosing setup.

---

### Section 2b — MCP is bound to a different worktree's Editor (multi-Editor case)

Symptoms: `ReadMcpResourceTool mcpforunity://instances` shows one instance whose `name` is a DIFFERENT worktree, not yours. Your Editor is running (`pgrep` shows it at your worktree path) but doesn't appear in the instance list, so every MCP call routes to the wrong project — or `set_active_instance <yours>` fails with "Instance hash does not match any running Unity editors."

Why: Coplay's Editor plugin only tries to spawn / register with the Python bridge at Editor **init**. The Python process is pinned to whichever Editor spawned it — a second Editor booting later can't register with an already-owned bridge on its own. See `unity-start-task` Case C for the full explanation; this section is the mid-session variant.

The fix is `unity-start-task`'s Case C shape, but scoped to your one worktree without creating a new one:

```bash
# 1. Kill just the Python bridge — leaves every Editor process running.
pkill -f "mcp-for-unity --transport http" 2>/dev/null
pkill -f "uvx.*mcp-for-unity" 2>/dev/null
sleep 2
lsof -nP -iTCP:8080 -sTCP:LISTEN   # must be empty

# 2. Kill only YOUR Editor — match on your worktree path. NEVER `pkill Unity`.
mine=$(pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath <your-worktree>")
[ -n "$mine" ] && kill "$mine" && sleep 5

# 3. Relaunch YOUR Editor. Its Coplay code spawns a fresh Python bridge pinned to YOUR token.
nohup "/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity" \
  -projectPath "<your-worktree>" > "<your-worktree>/test-results/editor.log" 2>&1 &
disown
```

Then wait for `mcpforunity://instances` to show BOTH yours AND the other Editors (this is the pattern — after step 3, the untouched Editors' Coplay plugins auto-re-register with the new bridge as separate instances). Pin: `set_active_instance <your-Name@hash>`. Verify: `execute_code { return UnityEngine.Application.dataPath; }` — must end in `<your-worktree>/Assets`.

**Don't:**
- Kill any Editor other than the one at your worktree path.
- Try to change the port via EditorPref (`MCPForUnity.HttpUrl`) — it's Unity-installation-wide, so all Editors of one Unity version read the same value. Per-editor port config only works for STDIO transport, not the HTTP one Claude Code uses.
- Add a second `unity-8081` MCP registration to `~/.claude.json` to route in parallel — the new tools don't appear in a session that was launched before the addition (MCP tools bind at session start). Only helps future sessions.
- Wait for Coplay to auto-recover on its own — it does not retry the launch. The kill+restart above is what actually recovers.

---

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
