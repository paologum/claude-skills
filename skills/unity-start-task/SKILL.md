---
name: unity-start-task
description: Starts a new Unity task in an isolated git worktree AND spins up a second Unity Editor on it without touching any Editor already running on another worktree. Handles the Coplay MCP bridge concurrency quirk — the Python `mcp-for-unity` process is pinned to the token of whichever Editor spawned it, so a stale bridge from another worktree has to be replaced before your Editor can register. Ends with the Claude Code session pinned to the new Editor via `set_active_instance`, verified. Use when the user asks to start a Unity task / issue on its own worktree while another Unity is open, "spin up a second Unity for issue #N", "start work on <issue> without closing the other Unity", or "give me a fresh Unity Editor on branch X".
allowed-tools: "Read Bash(git *) Bash(gh *) Bash(pwd) Bash(basename *) Bash(ls *) Bash(head *) Bash(cat *) Bash(pgrep *) Bash(ps *) Bash(kill *) Bash(lsof *) Bash(nohup *) Bash(disown *) Bash(mkdir *) Bash(awk *) Bash(sleep *) Glob"
argument-hint: "<issue-number | short description>"
disable-model-invocation: true
---

## Context

**Repo + current branch:**
```
!`git rev-parse --show-toplevel 2>/dev/null && git branch --show-current 2>/dev/null || echo "NOT A GIT REPO"`
```

**Default branch (base for the new branch):**
```
!`git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || echo "main"`
```

**Existing worktrees (avoid collisions):**
```
!`git worktree list 2>/dev/null`
```

**Uncommitted changes in the current tree (must not be dragged into the new task):**
```
!`git status --short 2>/dev/null | head -20`
```

**Currently-running Unity Editors (leave these alone):**
```
!`ps -eo pid,args | awk '/Unity\.app\/Contents\/MacOS\/Unity/ && /-projectPath/ && !/awk/' | head -5 || echo "no Editor currently open"`
```

**Coplay MCP HTTP bridge on :8080 (Python `mcp-for-unity` — pinned to the token of whichever Editor spawned it):**
```
!`lsof -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | head -3 || echo "port 8080 free"`
```

**Coplay Python bridge process (what its `--unity-instance-token` and `--pidfile` reveal about who owns it):**
```
!`ps -eo pid,args | awk '/mcp-for-unity/ && !/awk/' | head -3 || echo "no bridge running"`
```

**Installed Unity Editor versions:**
```
!`ls /Applications/Unity/Hub/Editor/ 2>/dev/null | head -5 || echo "Unity Hub not at default location"`
```

## Your task

Given `$ARGUMENTS` (issue number or short description), start a fresh task **in a new git worktree** and **on its own Unity Editor**, running alongside whatever Unity Editor is already open on another worktree. End with the Claude Code session pinned to the new Editor and verified. Never touch the other Editor.

### Step 1 — resolve the task + slug

Same as `start-task`:

- If `$ARGUMENTS` is a **number** (or `#N`), fetch it with `gh issue view <N> --json number,title,body,labels`; build the slug from the title.
- If it's **text**, use it directly as the description and slug source.
- **Slug rules:** lowercase, kebab-case, alphanumeric + hyphens, ≤ 6 words. Branch name = `<issue-number>-<slug>` when there's an issue, else `<slug>`.

### Step 2 — create the worktree off the fresh base

Look at how sibling worktrees are laid out on this repo (`.claude/worktrees/<name>` on Guandan, `../<repo>-<name>` on others) and match the pattern. Fetch first so the branch starts from the current tip:

```bash
git fetch origin <base>
git worktree add -b <branch> <worktree-path> origin/<base>
```

Do NOT switch the user's current working tree or branch. Everything happens in the new worktree.

### Step 3 — read the target's Unity version + locate the binary

```bash
version=$(head -1 "<worktree-path>/ProjectSettings/ProjectVersion.txt" | awk '{print $2}')
unity="/Applications/Unity/Hub/Editor/${version}/Unity.app/Contents/MacOS/Unity"
```

If the binary isn't installed, stop and tell the user to install it via Unity Hub. Do NOT substitute a different version — Guandan pins one and MPPM / package versions depend on it.

### Step 4 — launch the new Editor detached (concurrent with any existing)

```bash
mkdir -p "<worktree-path>/test-results"
nohup "$unity" -projectPath "<worktree-path>" > "<worktree-path>/test-results/editor.log" 2>&1 &
disown
```

Two Editors of the same version can run in parallel on macOS as long as they point at different project paths. This is by design — do not kill any other running Editor.

Editor startup on a fresh `Library/` takes 2–10 minutes (asset import). Go async — never block a single Bash call on the full import. Move to Step 5.

### Step 5 — handle the Coplay bridge concurrency quirk

This is the one that trips people up. Two things to know:

1. **The Python `mcp-for-unity` HTTP bridge accepts multiple Unity Editors as separate instances** — `mcpforunity://instances` returns a list, `set_active_instance` picks one.
2. **BUT** when Coplay's Editor code auto-launches the bridge on startup, it spawns the Python process with `--unity-instance-token <that-editor's-token>` and `--pidfile <that-editor's-worktree>/Library/MCPForUnity/RunState/mcp_http_8080.pid`. That token pins the STARTER — a second Editor booting later can't register with a bridge that already exists on :8080 pinned to a different token.

**Diagnostic:** `ps -eo pid,args | awk '/mcp-for-unity/ && !/awk/'` shows `--pidfile <some-worktree>/…` — that reveals which Editor started the current bridge.

**Case A — port 8080 is free (no bridge running).** Nothing to do; your new Editor's Coplay code will auto-spawn a bridge on startup. Skip to Step 6.

**Case B — port 8080 is held and its `--pidfile` points at YOUR new worktree.** Nothing to do — already yours (probably a stale pidfile from a prior run of the same Editor). Skip to Step 6.

**Case C — port 8080 is held and its `--pidfile` points at ANOTHER worktree.** Kill JUST the Python process:

```bash
# Kill only the Python bridge, not any Unity Editor:
pkill -f "mcp-for-unity --transport http" 2>/dev/null
# Also kill its uv/uvx wrapper so it doesn't restart on the old token:
pkill -f "uvx.*mcp-for-unity" 2>/dev/null
sleep 2
lsof -nP -iTCP:8080 -sTCP:LISTEN   # should be empty now
```

Then **restart YOUR new Editor** (kill only the Editor at your worktree path — the other worktree's Editor is untouched):

```bash
mine=$(pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath <worktree-path>")
[ -n "$mine" ] && kill "$mine" && sleep 5
nohup "$unity" -projectPath "<worktree-path>" > "<worktree-path>/test-results/editor.log" 2>&1 &
disown
```

Your Editor's Coplay code will spawn a fresh Python bridge on :8080, this time tied to YOUR token. Once it's up, the OTHER worktree's Editor will also re-register with the same bridge as a separate instance — both end up visible in `mcpforunity://instances`. This IS the intended pattern; the two Editors coexist under one Python bridge.

### Step 6 — wait for YOUR instance to register

Use `ReadMcpResourceTool` on `mcpforunity://instances` — do NOT poll `curl http://127.0.0.1:8080` (the bridge doesn't answer plain GET; the loop hangs to timeout).

Poll until an instance whose `name` matches your worktree's basename appears and capture its full `id` (`Name@hash`). If both worktrees' Editors show up, that's expected — pick yours.

Fallback when `ReadMcpResourceTool` isn't in the toolset (rare): poll the on-disk pidfile:

```bash
pid_glob="<worktree-path>/Library/MCPForUnity/RunState/mcp_http_*.pid"
end=$(( $(date +%s) + 600 ))
while [ $(date +%s) -lt $end ]; do
  ls $pid_glob >/dev/null 2>&1 && { echo READY; break; }
  sleep 15
done
```

### Step 7 — pin the session to your new instance

```
mcp__UnityMCP__set_active_instance instance="<your-Name@hash>"
```

Full `Name@hash`, not just the name. Without pinning, per-tool calls in a multi-instance world will error with `instance_selection_required` and force you to pass `unity_instance=…` on every call — pinning once is the fix.

### Step 8 — verify the pin actually took effect

Do not trust `set_active_instance`'s return alone. Route a call:

```csharp
// via mcp__UnityMCP__execute_code
return UnityEngine.Application.dataPath;
```

Must end with `<worktree-path>/Assets`. If it lands on another worktree, the pin didn't hold — the other Editor's instance may have registered first and been picked as the default. Retry `set_active_instance` explicitly.

### Step 9 — report and hand off

Short, factual:

- Started task on branch `<branch>` at worktree `<worktree-path>`.
- Launched Editor pid `<pid>` (Unity `<version>`). Other Editor(s) on `<other worktrees>` left running.
- Bridge state: `<Case A/B/C>` — did you replace the Python bridge or not.
- Pinned MCP to `<Name@hash>`; verified with `Application.dataPath`.
- Issue title + one-line goal (if there was an issue).
- Offer to continue into the implementation loop with `/dev-loop`.

## Guardrails / footguns

- **Never kill any Unity Editor other than the one at your worktree path.** Match on `Unity.app/Contents/MacOS/Unity -projectPath <your-path>` — never `pkill Unity` or `killall Unity` (both hit Unity Hub, the license client, and any MPPM clones).
- **Never kill a Python bridge whose `--pidfile` already points at your worktree** — that IS your bridge; killing it just re-triggers the same launch.
- **Never poll `curl http://127.0.0.1:8080`** as a readiness check — the endpoint doesn't answer plain GET and the loop hangs to timeout. Use `mcpforunity://instances` via `ReadMcpResourceTool`, or the on-disk pidfile.
- **Never trust `set_active_instance`'s success alone.** Actually invoke a tool and read `Application.dataPath`. In a multi-instance world, a wrong pin looks identical to a right one until you route a call.
- **Never create the branch on top of the current branch's HEAD.** Always `git fetch origin <base>` and base off `origin/<base>`, otherwise the new task inherits unrelated in-progress work from wherever the current worktree is sitting.
- **Never assume the second Editor will auto-recover** when the bridge is pinned to the wrong token. Case C requires killing the Python process AND restarting your Editor — the Editor's monitor doesn't retry the bridge launch on its own if it thought one was already up.
- **Play mode reverts scene edits made via `mcp__UnityMCP__execute_code`.** If your task does scene authoring, do it in Edit mode and enter Play only to screenshot. Otherwise you'll rebuild the same hierarchy twice.
- **Screenshots (`mcp__UnityMCP__manage_camera screenshot`) only capture fresh frames in Play mode.** In Edit mode, the Game view doesn't repaint on state changes — you'll get identical bytes on every call. Enter Play once the panel is authored.
