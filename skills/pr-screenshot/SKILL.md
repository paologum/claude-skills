---
name: pr-screenshot
description: Captures a Unity Play-mode screenshot via MCP and embeds it in the current PR description's Demo section. Uses the running Editor when the Coplay MCP bridge is up; otherwise falls back to a batchmode capture. Use when the user asks to grab a PR screenshot, add a demo image to the PR, take a Unity screenshot for review, capture the current scene for the PR, or "show the change in the PR".
allowed-tools: "Bash(git *) Bash(gh *) Bash(mkdir *) Bash(ls *) Read Write Edit"
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
!`gh pr view "${ARGUMENTS:-}" --json number,title,url 2>/dev/null || gh pr view --json number,title,url 2>/dev/null || echo "no PR yet — will save screenshot only"`
```

**Existing pr-screenshots directory:**
```
!`ls -la docs/pr-screenshots 2>/dev/null | head -20`
```

**Is Unity MCP available?** Check whether `mcp__UnityMCP__manage_editor` shows up in your tool list this session. Do NOT trust a `.mcp.json` file's presence — verify by calling `mcp__UnityMCP__manage_editor` with `action: "get_state"` (or `find_gameobjects` on `**`). If the tool is genuinely absent, skip to the batchmode fallback at the bottom.

## Task

Capture a screenshot showing the change on this branch and attach it to the PR's Demo section.

### Steps (MCP path — preferred)

1. **Enter Play mode** with `mcp__UnityMCP__manage_editor` (`action: "play"`). Wait ~1s.
2. **Get to the right scene state**. Read the diff (`git diff origin/main...HEAD --name-only`) — if a specific scene, canvas, or prefab was touched, navigate/set the scene so the change is on-screen. If the change is a UI element (LobbyCanvas, GameCanvas, etc.), make sure that canvas is active.
3. **Take the screenshot**. Use `mcp__UnityMCP__execute_code` to run:
   ```csharp
   var path = System.IO.Path.Combine(UnityEngine.Application.dataPath, "..", "docs", "pr-screenshots", System.IO.Path.GetFileName(System.IO.Path.GetTempFileName()).Replace(".tmp", ".png"));
   System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
   UnityEngine.ScreenCapture.CaptureScreenshot(path);
   UnityEngine.Debug.Log("SCREENSHOT_PATH=" + System.IO.Path.GetFullPath(path));
   ```
   Then wait one frame (call `mcp__UnityMCP__manage_editor` `action: "get_state"`) so the file flushes.
4. **Exit Play mode** (`action: "stop"`).
5. **Rename** the file to something meaningful for the diff: `docs/pr-screenshots/pr-<N>-<short-slug>.png` where `<N>` is the PR number and `<short-slug>` describes the change (e.g. `pr-42-pass-button.png`).
6. **Commit the screenshot** on the current branch — GitHub only renders images from paths that are actually in the tree at the head SHA:
   ```bash
   git add docs/pr-screenshots/<file>
   git commit -m "docs: PR screenshot for #<N>"
   git push
   ```
7. **Embed it in the PR body.** Do NOT try to inline-`sed` into `gh pr edit --body` — PR bodies routinely contain quotes, backticks, `$`, and newlines that shell-escape wrong. Instead:
   1. `gh pr view <N> --json body -q .body > /tmp/pr-body.md`
   2. Open `/tmp/pr-body.md` with the `Edit` tool and replace `_drag screenshot here_` with `![screenshot](docs/pr-screenshots/<file>)`. Relative paths inside PR body markdown resolve against the head SHA of the PR — this is the *only* embed form that reliably renders across public and private repos.
   3. `gh pr edit <N> --body-file /tmp/pr-body.md`
8. If **no PR exists** yet, skip steps 6–7 and just print the committed path so the user can include the same `![screenshot](docs/pr-screenshots/<file>)` snippet when they open the PR.

### Steps (batchmode fallback — no MCP)

The plain CLI can't drive the Editor into a specific scene state. Do this only if MCP is unavailable:

1. Tell the user which scene/state to check first.
2. `Assets/Editor/ScreenshotCapture.cs` — create it if missing with a static method that opens a scene, captures a frame, and exits.
3. Run Unity: `$(unity-editor-path) -batchmode -nographics -projectPath . -executeMethod ScreenshotCapture.Capture -logFile -quit`
4. Same rename + `gh pr edit` step as above.

### Rules

- **Never commit test/experiment screenshots.** Only commit the one that ends up in the PR body.
- **Screenshots go in `docs/pr-screenshots/`**, not the repo root. Create the dir if missing.
- **File names must include the PR number** so they're easy to prune later.
- If the diff has no UI/scene/prefab changes, tell the user: "No UI changes in this branch — a screenshot won't help the reviewer. Skip?"
- Do not enter Play mode if a Play-mode test job is already running (`mcp__UnityMCP__manage_editor` `action: "get_state"` — check `isPlaying` and any running test job).
