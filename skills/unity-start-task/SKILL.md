---
name: unity-start-task
description: Starts a new Unity task in an isolated git worktree AND spins up a second Unity Editor on it without touching any Editor already running on another worktree. Under stdio transport each Editor owns its own socket (6400, 6401, …) and registers itself, so a second Editor needs no bridge surgery. Ends with the Claude Code session pinned to the new Editor via `set_active_instance`, verified. Use when the user asks to start a Unity task / issue on its own worktree while another Unity is open, "spin up a second Unity for issue #N", "start work on <issue> without closing the other Unity", or "give me a fresh Unity Editor on branch X".
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

**Unity Editors already publishing a stdio bridge (port + project each one owns):**
```
!`cat ~/.unity-mcp/unity-mcp-status-*.json 2>/dev/null || echo "no Editor bridges registered yet"`
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

### Step 4 — launch the new Editor and wait for it in the background

Launch **and** wait in one background call through `/unity-editor-up`'s script. Its path is the `unity-editor-up` skill's base directory plus `/unity_editor_up.py`, i.e. the sibling `skills/unity-editor-up/` of this skill's base directory. Run it with Bash `run_in_background: true`:

```bash
python3 <plugin>/skills/unity-editor-up/unity_editor_up.py --project "<worktree-path>" --launch
```

It starts the Editor with its own `-logFile`, so compile errors are visible. It ignores other worktrees' Editors and exits once with `READY <Name@hash>`, `COMPILE_ERRORS` (Safe Mode), `EXITED` or `TIMEOUT`, and the harness wakes the session then. Keep working while it runs. Don't `nohup` Unity yourself, don't poll, and don't end the turn on a timer. For `COMPILE_ERRORS`, follow `/unity-editor-up` Step 2 (fix, then `--restart`).

Two Editors of the same version run in parallel fine as long as they point at different project paths. Never kill another worktree's Editor.

### Step 5 — nothing to do for the bridge

Under stdio there is no shared bridge to contend for. Each Editor allocates its own
socket (6400, then 6401, 6402… if those are taken), publishes
`~/.unity-mcp/unity-mcp-status-<hash>.json` with its port and `project_path`, and is
discovered independently. The MCP server is a child of *your Claude Code session*, not
of any Editor, so nothing needs killing, restarting, or re-pinning.

Both Editors simply show up in `mcpforunity://instances`. Go to Step 6.

### Step 6 — take YOUR instance id from the wait result

When the background wait from Step 4 reports `READY <Name@hash>`, that `Name@hash` is your instance. Pick it by path, not name: two worktrees of the same repo can share a project name. To double-check, read `mcpforunity://instances` once with `ReadMcpResourceTool` and match `path` to your worktree.

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
- Bridge: Editor registered on port `<port>` (other Editors untouched).
- Pinned MCP to `<Name@hash>`; verified with `Application.dataPath`.
- Issue title + one-line goal (if there was an issue).
- Offer to continue into the implementation loop with `/dev-loop`.

## Guardrails / footguns

- **Never kill any Unity Editor other than the one at your worktree path.** Match on `Unity.app/Contents/MacOS/Unity -projectPath <your-path>` — never `pkill Unity` or `killall Unity` (both hit Unity Hub, the license client, and any MPPM clones).
- **Never kill the MCP server process.** Under stdio it is a child of your Claude Code session, shared across every Editor. Killing it takes the tools away for the rest of the session with no way to rebind — restarting Claude Code is the only recovery. Nothing about launching a second Editor requires touching it.
- **Never poll for readiness in a Bash loop.** Use `ReadMcpResourceTool` on `mcpforunity://instances`, or `/unity-editor-up`'s background wait between attempts — never `ScheduleWakeup`.
- **Never trust `set_active_instance`'s success alone.** Actually invoke a tool and read `Application.dataPath`. In a multi-instance world, a wrong pin looks identical to a right one until you route a call.
- **Never create the branch on top of the current branch's HEAD.** Always `git fetch origin <base>` and base off `origin/<base>`, otherwise the new task inherits unrelated in-progress work from wherever the current worktree is sitting.
- **Never assume a second Editor conflicts with the first.** It doesn't. If yours never appears in `mcpforunity://instances`, the cause is local to your Editor — still importing, or its Transport dropdown isn't on Stdio — not contention with the other one.
- **Play mode reverts scene edits made via `mcp__UnityMCP__execute_code`.** If your task does scene authoring, do it in Edit mode and enter Play only to screenshot. Otherwise you'll rebuild the same hierarchy twice.
- **Screenshots (`mcp__UnityMCP__manage_camera screenshot`) only capture fresh frames in Play mode.** In Edit mode, the Game view doesn't repaint on state changes — you'll get identical bytes on every call. Enter Play once the panel is authored.
