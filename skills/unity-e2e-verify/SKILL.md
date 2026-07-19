---
name: unity-e2e-verify
description: End-to-end verifies a Unity feature by driving Play mode via MCP UI event dispatch (never OS input), captures a screenshot at each state transition, greps the Console for the diagnostic log line that proves the code path executed, uploads the screenshots to GitHub's user-attachments CDN via `gh attach` so they render inline in private-repo PR bodies, and posts a structured verification comment on the PR with an evidence table. Use when the user asks to "verify this end to end," "prove the fix works in-Editor," "add screenshots showing the change," "walk through the feature and show it," "generate PR evidence for this change," or when a change to gameplay / UI / networking needs visible proof beyond unit tests. Composes with `unity-switch-worktree` (rebind Editor to the right project first) and `pr-description` / `pr-screenshot` (single-shot variants).
allowed-tools: "Bash(gh *) Bash(gh attach *) Bash(git *) Bash(sleep *) Bash(ls *) Bash(mkdir *) Bash(cp *) Bash(mv *) Bash(basename *) Bash(dirname *) Bash(realpath *) Bash(grep *) Bash(head *) Bash(tail *) Read Write Edit"
argument-hint: "[PR-number]"
---

## Context

**Repo + current branch:**
```
!`git rev-parse --show-toplevel 2>/dev/null && git rev-parse --abbrev-ref HEAD`
```

**Target PR (arg or auto-detect from branch):**
```
!`gh pr view "${ARGUMENTS:-}" --json number,title,url,headRepositoryOwner,headRepository 2>/dev/null || gh pr view --json number,title,url,headRepositoryOwner,headRepository 2>/dev/null || echo "no PR yet — will capture locally only"`
```

**Owner/repo (needed for `gh attach --target`):**
```
!`gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "not in a gh-recognized repo"`
```

**Is Unity MCP available and bound to the right project?** Verify by calling `mcp__UnityMCP__execute_code` with `action: "execute"`, `code: 'return UnityEngine.Application.dataPath;'`. The returned path must end in `<current-worktree>/Assets`. If it points at a different worktree, stop and invoke `unity-switch-worktree` first — this skill assumes the Editor is on the branch under test.

**Is `gh attach` installed and logged in?**
```
!`gh attach --version 2>/dev/null || echo "MISSING — install with: gh extension install Addono/gh-attach"; gh attach whoami 2>/dev/null || echo "NOT LOGGED IN — one-time: gh attach login (opens browser, saves cookie to keychain)"`
```

## Task

Walk the feature end-to-end in the running Unity Editor, capture visual proof at each state transition, and post it as a structured verification comment on the PR — the kind of comment a reviewer can approve from without opening the branch themselves.

### Step 0 — plan the state transitions

Read `git diff origin/main...HEAD` and identify **what the user of this change would see**. Every meaningful state transition gets a screenshot. Typical shapes:

- **Menu → Lobby → Game flow** (multiplayer feature): main menu, lobby with expected participants, game in-progress
- **New UI element** (button, overlay, HUD): before-trigger screenshot, after-trigger screenshot
- **Fixed regression** (e.g. cards didn't deal): repro state pre-fix (from logs, since fix is applied), current state post-fix, with the diagnostic log line captured

**Rule:** if a state has no visible UI change, screenshot the **Console** or a targeted runtime probe instead — never fake a screenshot of an unchanged view.

### Step 1 — load the scene the feature lives in

```
mcp__UnityMCP__manage_scene  action: "load"  name: "<SceneName>"  path: "Assets/Scenes"
```

Then wait one frame for `Awake`/`Start` to run. Do not enter Play mode against an unloaded scene — it's undefined behavior.

### Step 2 — enter Play mode

```
mcp__UnityMCP__manage_editor  action: "play"
```

Wait 4–6 seconds via `Bash sleep 5` — the SDK / NetworkManager / SceneManager all need to Awake before you drive them. If the feature involves `[RuntimeInitializeOnLoadMethod(BeforeSceneLoad)]` singletons (like `SteamManager.AutoBoot`), an extra frame beyond the sleep helps.

### Step 3 — screenshot the starting state

```csharp
// Via mcp__UnityMCP__execute_code (action: "execute")
UnityEngine.ScreenCapture.CaptureScreenshot("/tmp/<slug>-01-start.png");
System.Threading.Thread.Sleep(600);   // let the file flush
return "captured";
```

Then confirm the file exists via `Bash ls -la /tmp/<slug>-01-start.png`. **Do not skip this check** — silent capture failure is the #1 way to end up posting a broken image link.

### Step 4 — drive the UI via event dispatch, never OS input

This is the load-bearing rule of the whole workflow. **Never call `screencapture`, `cliclick`, `osascript "click at …"`, or any OS-level input tool** to interact with the game. Two reasons:

- Unity's UI event system in Play mode doesn't reliably receive synthetic OS clicks, especially when the Editor window isn't focused
- The project's E2E convention is UI-event dispatch only (canonical ground rule for this codebase)

Correct pattern — invoke `Button.onClick` directly via `execute_code`:

```csharp
var mainMenu = UnityEngine.Object.FindFirstObjectByType<MainMenu>();
if (mainMenu == null) return "MainMenu not found";
mainMenu.HostGame();                                // or button.onClick.Invoke()
return "HostGame invoked; NetworkServer.active=" + Mirror.NetworkServer.active;
```

For lobby-style flows:

```csharp
var lobbyUI = UnityEngine.Object.FindFirstObjectByType<LobbyUI>();
lobbyUI.readyButton.onClick.Invoke();               // client input path preserved
System.Threading.Thread.Sleep(400);                 // SyncVar round-trip
lobbyUI.startButton.onClick.Invoke();
return $"ready+start dispatched; localPlayer.isReady={Player.LocalPlayer?.isReady}";
```

Always return the state probe from the same `execute_code` call — one round trip, one confirmation.

### Step 5 — screenshot after each state transition

After each button click / scene change, wait long enough for Mirror / DealManager / TurnManager to complete their round-trips (typically 3–5 seconds for a scene change), then capture:

```csharp
UnityEngine.ScreenCapture.CaptureScreenshot("/tmp/<slug>-02-lobby.png");
System.Threading.Thread.Sleep(600);
return "captured";
```

Followed by `Bash ls -la /tmp/<slug>-02-lobby.png` — every capture gets its own existence check. If a capture returned instantly and the file isn't there, you're probably not in Play mode any more (the state transition failed and Play mode aborted).

### Step 6 — grep the Console for the diagnostic log line

The screenshot proves the pixels; the log line proves the **code path executed**. Both matter for a real audit:

```
mcp__UnityMCP__read_console  action: "get"  types: ["log", "error", "warning"]  count: 40  format: "plain"  filter_text: "<expected marker like [DealManager] or [SteamManager]>"
```

Capture the exact matching lines verbatim — they'll go into the PR comment as inline code. If the marker doesn't appear, the fix isn't actually running; **do not paper over this with a screenshot alone**.

### Step 7 — exit Play mode

```
mcp__UnityMCP__manage_editor  action: "stop"
```

Cleanly stops so a hanging test-runner or an Awake exception won't linger and confuse the next verification pass.

### Step 8 — upload screenshots to GitHub's user-attachments CDN

**This is the private-repo-critical step.** `raw.githubusercontent.com/…/<sha>/…` links **do not render inline** on private-repo PR bodies — every image comes out as a broken icon. The only URL scheme that renders inline is `github.com/user-attachments/assets/…` (or `github.com/<owner>/<repo>/releases/download/_gh-attach-assets/…`, which `gh attach` uses as a repo-branch fallback).

Upload each screenshot and capture the CDN URL:

```bash
gh attach upload /tmp/<slug>-01-start.png  --target <owner>/<repo>#<PR>  --format url
gh attach upload /tmp/<slug>-02-lobby.png  --target <owner>/<repo>#<PR>  --format url
gh attach upload /tmp/<slug>-03-game.png   --target <owner>/<repo>#<PR>  --format url
```

Each command prints one URL — capture it. If `gh attach whoami` was NOT LOGGED IN from the Context block, tell the user to run `gh attach login` (one-time, opens browser, cookie saved to keychain) and pause — do not try to embed images via a URL scheme you know renders broken.

### Step 9 — post the verification comment on the PR

Structure the comment like a small audit report — heading, flow narrative, embedded images at their moment in the narrative, log evidence in fenced code blocks, and a summary table of pass/fail for each check:

```markdown
## E2E verification against a real Editor session

Ran the full flow against the Editor bound to this worktree (via MCP for Unity). Screenshots captured with `UnityEngine.ScreenCapture.CaptureScreenshot` at each state transition, uploaded via `gh attach`.

### Flow

1. **MenuScene, Play mode entered** — game boots normally.
   ![Menu](<CDN-url-from-Step-8>)
2. **<Action dispatched>** — <state observed>.
   ![Lobby](<CDN-url>)
3. **<Terminal state>** — <log evidence>:
   ```
   [DealManager] Dealing 108 cards to 1 humans + 3 bots (26 each, seed=…)
   ```
   ![Game](<CDN-url>)

### Audit trail summary

| Check                                    | Result |
|------------------------------------------|--------|
| Play mode entered without exception       | ✅     |
| UI dispatch (`Button.onClick.Invoke`) reached the server code | ✅ |
| Diagnostic log line fired                 | ✅     |
| Terminal state screenshot matches spec    | ✅     |
| Clean exit from Play mode                 | ✅     |

Ready for review.
```

Post via:

```bash
gh pr comment <PR> --repo <owner>/<repo> --body "$(cat <<'EOF'
...
EOF
)"
```

### Step 10 — deliver to the user (when SendUserFile is available)

If the `SendUserFile` tool is in your toolset, also send each screenshot to the user with a caption pointing at what changed. Even with the PR comment posted, delivering directly makes the reviewer's job faster.

## Composes with

- **Before this skill:** `unity-switch-worktree` if the Editor isn't already on the branch under test; `pr-description` if the PR itself hasn't been drafted yet
- **After this skill:** `pr-video` if a static screenshot doesn't convey the change (animation, timing-sensitive behavior)

## Don'ts

- **Never OS input** — no `screencapture`-only workflows that don't drive the UI, no `cliclick`, no `osascript "click at …"`. Use `Button.onClick.Invoke()` via `execute_code`.
- **Never batch screenshots** and describe them all at the end — capture and describe each as you take it, so a failure mid-flow surfaces immediately instead of at the end. This project's convention is one iteration = one screenshot delivered.
- **Never embed screenshots via `raw.githubusercontent.com`** on a private repo — they 404-render as broken icons. Use `gh attach upload` and the CDN URL it returns.
- **Never skip the `ls -la /tmp/<file>` existence check** after a `CaptureScreenshot`. A silent capture failure looks identical to success in the return value.
- **Never trust `set_active_instance`'s success return alone** for MCP routing (see `unity-switch-worktree`); if the Editor's `Application.dataPath` doesn't match the worktree, everything below is invalid.
- **Never claim `Initialized=true` or `SDK loaded` from a screenshot alone** — always cite the log line (Step 6) that proves the code path executed.
