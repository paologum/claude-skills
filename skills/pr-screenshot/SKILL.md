---
name: pr-screenshot
description: Captures a Unity Play-mode screenshot via MCP, uploads it to GitHub's user-attachments CDN via `gh attach`, and embeds the resulting URL in the current PR's Demo section. Never commits image files to the repo. Falls back to a local temp path + drag-drop instructions when `gh attach` is unavailable. Use when the user asks to grab a PR screenshot, add a demo image to the PR, take a Unity screenshot for review, capture the current scene for the PR, or "show the change in the PR".
allowed-tools: "Bash(git *) Bash(gh *) Bash(gh attach *) Bash(mkdir *) Bash(ls *) Bash(rm *) Bash(stat *) Bash(curl *) Bash(which *) Read Write Edit"
argument-hint: "[PR-number]"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel`
```

**Current branch:**
```
!`git rev-parse --abbrev-ref HEAD`
```

**Target PR (arg or auto-detect from branch):**
```
!`gh pr view "${ARGUMENTS:-}" --json number,title,url 2>/dev/null || gh pr view --json number,title,url 2>/dev/null || echo "no PR yet — will save screenshot locally and print embed snippet"`
```

**Owner/repo (for `gh attach --target`):**
```
!`gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "not in a gh-recognized repo"`
```

**`gh attach` installed?**
```
!`gh attach --version 2>/dev/null || echo "MISSING — install: gh extension install Addono/gh-attach"`
```

**`gh attach` session valid?** (browser-session cookie must be logged in)
```
!`gh attach whoami 2>/dev/null || echo "NOT LOGGED IN — one-time setup: gh attach login (opens browser, saves cookie to keychain)"`
```

**Is Unity MCP available?** Check whether `mcp__UnityMCP__manage_editor` shows up in your tool list this session. Do NOT trust a `.mcp.json` file's presence — verify by calling `mcp__UnityMCP__manage_editor` with `action: "get_state"` (or `find_gameobjects` on `**`). If the tool is genuinely absent, skip to the batchmode fallback at the bottom.

## Task

Capture a screenshot showing the change on this branch, upload it to GitHub's user-attachments CDN, and embed the returned URL in the PR's Demo section. **No image file ever lands in the repo tree.**

### Steps (MCP path — preferred)

1. **Enter Play mode** with `mcp__UnityMCP__manage_editor` (`action: "get_state"` first — if `isPlaying: true`, don't re-enter; if a Play-mode test job is running, refuse). Otherwise `action: "play"`, wait ~1s.
2. **Get to the right scene state**. Read the diff (`git diff origin/main...HEAD --name-only`) — if a specific scene, canvas, or prefab was touched, navigate/set the scene so the change is on-screen. If the change is a UI element (LobbyCanvas, GameCanvas, etc.), make sure that canvas is active.
3. **Take the screenshot** into Unity's `Temp/` directory (auto-ignored by Unity's `.gitignore` — never touches the repo tree). Use `mcp__UnityMCP__execute_code`:
   ```csharp
   var slug = "<short-slug>";   // e.g. "pass-button", derive from branch/PR title
   var pr   = "<PR>";           // e.g. "42", or "nopr" if no PR yet
   var path = System.IO.Path.GetFullPath(System.IO.Path.Combine(
       UnityEngine.Application.dataPath, "..", "Temp",
       $"pr-screenshot-{pr}-{slug}.png"));
   System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
   UnityEngine.ScreenCapture.CaptureScreenshot(path);
   UnityEngine.Debug.Log("SCREENSHOT_PATH=" + path);
   ```
   Then wait one frame (call `mcp__UnityMCP__manage_editor` `action: "get_state"`) so the PNG flushes.
4. **Exit Play mode** (`action: "stop"`).
5. **Verify the PNG exists and is non-empty**:
   ```bash
   stat -f%z "Temp/pr-screenshot-<PR>-<slug>.png"    # must be > 0
   ```
   If missing or zero bytes: report the failure and stop. Do NOT fall back to committing anything.
6. **Upload via `gh attach`** — requires `gh attach whoami` to succeed:
   ```bash
   gh attach upload "Temp/pr-screenshot-<PR>-<slug>.png" \
     --target "<owner>/<repo>#<PR>" \
     --strategy browser-session \
     --format url
   ```
   Capture stdout — it's the bare URL, `https://github.com/user-attachments/assets/<uuid>`. If the exit code is non-zero or the output doesn't match that pattern, skip to the **`gh attach` unavailable** fallback below.
7. **Verify the URL is reachable**:
   ```bash
   curl -sI -L -o /dev/null -w "%{http_code}" "<the-url>"    # must be 200
   ```
8. **Embed it in the PR body.** Do NOT try to inline-`sed` into `gh pr edit --body` — PR bodies routinely contain quotes, backticks, `$`, and newlines that shell-escape wrong. Instead:
   1. `gh pr view <PR> --json body -q .body > /tmp/pr-body.md`
   2. Open `/tmp/pr-body.md` with the `Edit` tool. Replace `_drag screenshot here_` (or the Demo section placeholder) with:
      ```markdown
      ![screenshot](<the-url>)
      ```
      For image attachments the `![](URL)` form is correct — GitHub renders it as an inline `<img>` regardless of the viewer's login state, and works in both public and private repos.
   3. `gh pr edit <PR> --body-file /tmp/pr-body.md`
9. **Delete the local PNG** — the source of truth is now the CDN:
   ```bash
   rm "Temp/pr-screenshot-<PR>-<slug>.png"
   ```
10. **If no PR exists yet**, skip steps 6–9. Report the local `Temp/…` path and tell the user to either open the PR first and re-run, or drag-drop the PNG into the PR body manually.

### Steps (batchmode fallback — no MCP)

The plain CLI can't drive the Editor into a specific scene state. Do this only if MCP is unavailable:

1. Tell the user which scene/state to check first.
2. `Assets/Editor/ScreenshotCapture.cs` — create it if missing with a static method that opens the target scene, captures a frame into `Temp/pr-screenshot-<PR>-<slug>.png`, and exits.
3. Run Unity: `$(unity-editor-path) -batchmode -nographics -projectPath . -executeMethod ScreenshotCapture.Capture -logFile -quit`
4. Then continue from step 5 above (verify → upload → embed → delete).

### Fallback — `gh attach` unavailable

Triggered when the precheck shows `gh attach` missing, `gh attach whoami` fails, or the upload itself fails.

1. **Leave the PNG at the local `Temp/…` path.** Do NOT commit it. Do NOT copy it into `docs/`.
2. Print exactly:
   > `gh attach` isn't available (`<reason>`). The screenshot is at `Temp/pr-screenshot-<PR>-<slug>.png`. To finish:
   > - One-time setup: `gh extension install Addono/gh-attach && gh attach login`, then re-run `/pr-screenshot`, OR
   > - Drag the PNG into the PR body in GitHub's web UI (it auto-uploads to user-attachments) and copy the resulting markdown into the Demo section.
3. Stop. Do not attempt any commit/push workaround.

## Rules

- **Never commit or push screenshots.** No `git add`, no `git commit`, no `git push` in any path of this skill. Screenshots live on the GitHub user-attachments CDN or on the user's local disk — never in the repo tree.
- **Never write to `docs/pr-screenshots/`** or any other tracked path. Use Unity's `Temp/` directory (auto-ignored) exclusively.
- **After a successful upload, delete the local PNG.** No stale files hanging around.
- **Refuse cleanly** if `gh attach` isn't installed/authed — print the exact setup command and the drag-drop workaround, then stop.
- Do NOT use `sed` on PR bodies. Always the temp-file + `Edit` + `--body-file` pattern.
- If the diff has no UI/scene/prefab changes, tell the user: "No UI changes in this branch — a screenshot won't help the reviewer. Skip?"
- Do not enter Play mode if a Play-mode test job is already running (`mcp__UnityMCP__manage_editor` `action: "get_state"` — check `isPlaying` and any running test job).
