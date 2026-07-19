---
name: unity-switch-worktree
description: Restarts the Unity Editor on a different project path — closes the currently-running Editor, launches it on the target worktree, waits for Coplay's MCP bridge to come back online, and rebinds the MCP session to the new instance so `mcp__UnityMCP__*` tool calls route correctly. Use when the user says "switch Unity to <path>", "open Unity on the #NNN worktree", "restart Unity on this worktree", "point Unity at the other branch", or when Play-mode / MCP-driven work has to happen on a branch different from where the Editor is currently open. Especially useful for git-worktree workflows where Steam / networking / lobby PRs live on separate branches and need Editor-driven verification one at a time.
allowed-tools: "Read Bash(ls *) Bash(pgrep *) Bash(ps *) Bash(kill *) Bash(pkill *) Bash(osascript *) Bash(sleep *) Bash(lsof *) Bash(nohup *) Bash(disown *) Bash(mkdir *) Bash(git *) Bash(basename *) Bash(cat *) Bash(head *) Bash(tail *) Bash(dirname *)"
argument-hint: "<target-project-path | worktree-name>"
---

## Context

**Current working directory:**
```
!`pwd`
```

**Git worktrees available (targets you can switch to):**
```
!`git worktree list 2>/dev/null | head -20 || echo "not in a git repo"`
```

**Currently-running Unity Editor processes (should be at most one Editor per user):**
```
!`ps -eo pid,args | awk '/Unity\.app\/Contents\/MacOS\/Unity/ && /-projectPath/ && !/awk/' | head -5 || echo "no Editor currently open"`
```

**Coplay MCP bridge port status (Editor holds it once running):**
```
!`lsof -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | head -3 || echo "port 8080 free"`
```

**Installed Unity Editor versions:**
```
!`ls /Applications/Unity/Hub/Editor/ 2>/dev/null | head -5 || echo "Unity Hub not at default location"`
```

## Task

Switch the Unity Editor from its current project to `$ARGUMENTS`, wait for the MCP bridge to come back up on the new project, and rebind the Claude Code MCP session to the new instance. Report success only after you've made an actual MCP call against the new project and confirmed `Application.dataPath` matches.

### Step 0 — resolve the target path

- If `$ARGUMENTS` is an **absolute path**, use it directly.
- If it's a **relative path** (starts with `.` or contains no `/`), resolve against the current git repo root: `$(git rev-parse --show-toplevel)/$ARGUMENTS`.
- If it's a **worktree name** (matches the last path component of an entry in `git worktree list`), pick that worktree's absolute path.
- If it's an **issue number** (`#NNN` or `NNN`), look for a worktree whose path contains `github-issue-NNN` and use it.
- Verify the resolved path exists and contains `ProjectSettings/ProjectVersion.txt` — that's how you know it's a valid Unity project root. If not, stop and ask the user.

### Step 1 — read the target's Unity version and locate the binary

```bash
version=$(head -1 "<target>/ProjectSettings/ProjectVersion.txt" | awk '{print $2}')
unity="/Applications/Unity/Hub/Editor/${version}/Unity.app/Contents/MacOS/Unity"
```

If the binary isn't present, stop and tell the user to install that Editor version via Unity Hub. Do not silently substitute a different version.

### Step 2 — close the currently-running Editor (if any)

Try graceful quit first, fall back to signal:

```bash
osascript -e 'tell application "Unity" to quit' 2>&1 || true
sleep 4
# If still running, find the specific Editor process (NOT Unity Hub, NOT the license client)
editor_pid=$(pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath" | head -1)
if [ -n "$editor_pid" ]; then
  kill "$editor_pid" 2>/dev/null
  sleep 5
fi
# Force if still around after 10s
editor_pid=$(pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath" | head -1)
[ -n "$editor_pid" ] && kill -9 "$editor_pid"
```

- **Never `pkill -9 -f Unity`** — that also kills Unity Hub, the licensing client, and any MPPM clones. Match on `Unity.app/Contents/MacOS/Unity -projectPath` specifically.
- **Save the user's work first if there might be unsaved scene edits.** If the Editor is currently focused and you're not sure, warn the user before killing and give them 10 seconds to `Cmd+S`.
- Wait until `pgrep -f "Unity\.app/Contents/MacOS/Unity -projectPath"` returns empty. If the old Editor is still holding the Coplay HTTP port (`lsof -nP -iTCP:8080 -sTCP:LISTEN`), the new one will fail to bind.

### Step 3 — launch the new Editor detached

```bash
mkdir -p "<target>/test-results"
nohup "$unity" -projectPath "<target>" > "<target>/test-results/editor.log" 2>&1 &
disown
```

Editor startup on a fresh `Library/` can take 2–10 minutes (asset import). Do not wait synchronously in one long Bash call — you'll block the conversation and burn the tool timeout. Instead go to Step 4.

### Step 4 — wait for the MCP bridge to appear, correctly

The right check is the MCP resource `mcpforunity://instances`, not an HTTP GET on port 8080 (the bridge does not answer plain GET at `/` — polling that with `curl` hangs your Monitor until timeout). Two forms:

**When you have `ReadMcpResourceTool` in your toolset**, call it directly and inspect `data.instances[]` for one whose `name` matches the target worktree's basename. When it appears, capture its full `id` (e.g. `github-issue-133-7904c4@c419cb5374192e4d`).

**When you don't have that tool** (rare — usually deferred until after ToolSearch), fall back to polling the on-disk pidfile the MCP server writes:

```bash
pid_glob="<target>/Library/MCPForUnity/RunState/mcp_http_*.pid"
# Wait up to 10 minutes for the pidfile to appear (Unity import can be slow)
end=$(( $(date +%s) + 600 ))
while [ $(date +%s) -lt $end ]; do
  if ls $pid_glob >/dev/null 2>&1; then
    echo "MCP_READY"
    break
  fi
  sleep 15
done
```

Do NOT use `curl http://127.0.0.1:8080` as the readiness check — it hangs. This is the specific mistake this skill exists to prevent.

If the Editor process died before the bridge came up, check `<target>/test-results/editor.log` for compile errors or license failures before retrying.

### Step 5 — rebind the MCP session

Call `mcp__UnityMCP__set_active_instance` with the exact `id` (Name@hash) from Step 4. Not the name alone — the full `Name@hash` string. Example:

```
mcp__UnityMCP__set_active_instance instance="github-issue-133-7904c4@c419cb5374192e4d"
```

If `set_active_instance` returns "Instance hash 'X' does not match any running Unity editors", the bridge is running but hasn't finished registering the new session yet — wait 5 seconds and retry. Do not retry more than 3 times.

### Step 6 — verify the switch actually took effect

Do not report success from the `set_active_instance` return value alone. Actually route a tool call and confirm it hits the new project:

```csharp
// via mcp__UnityMCP__execute_code
return UnityEngine.Application.dataPath;
```

The returned path must end in `<target>/Assets`. If it doesn't, the session is still bound to the old instance and something above went wrong.

### Step 7 — report

Short, factual:

- Switched Editor from `<old path>` → `<new path>`.
- New instance id: `<Name@hash>`.
- MCP session rebound and verified via `Application.dataPath`.

If the user asked to switch as a step toward another workflow (screenshots, Play-mode driving, `/run-playmode`), hand off directly — don't wait for them to say "now do X."

## Don'ts

- Don't `pkill Unity` or `killall Unity`. Kill the specific Editor process by matching on `Unity.app/Contents/MacOS/Unity -projectPath`.
- Don't check bridge readiness by polling `curl http://127.0.0.1:8080` — the endpoint doesn't answer plain GET; the Monitor / Bash `until` loop will hang until timeout. Use the MCP resource or the on-disk pidfile.
- Don't skip Step 6. `set_active_instance` returning success only means the server accepted the request — it doesn't confirm the tool calls will route to the new project. A stale session shows up as "code executes but returns dataPath from the old worktree."
- Don't attempt to switch while the current Editor has unsaved changes without warning the user. There is no undo.
- Don't launch the new Editor in the foreground and wait for it — go async, poll for readiness in Step 4.
