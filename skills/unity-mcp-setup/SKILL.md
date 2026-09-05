---
name: unity-mcp-setup
description: Diagnoses whether Coplay's Unity MCP is correctly set up for the current Unity project and walks the user through fixing anything missing. Checks uv/uvx installation, the Coplay package in the project, the Editor's stdio bridge socket, and Claude Code's MCP registration. Use when the user asks to set up Unity MCP, connect Claude to Unity, configure the Unity MCP, "why isn't Unity MCP working", or troubleshoots MCP tool calls failing against Unity.
allowed-tools: "Read Bash(pwd) Bash(which *) Bash(uv --version) Bash(uvx --version) Bash(ls *) Bash(cat *) Bash(lsof *) Bash(ps *) Bash(claude mcp *) Bash(grep *) Bash(brew *) Bash(find *) Glob"
---

## Transport: stdio

This project family runs MCP for Unity over **stdio**, not HTTP. That choice decides
most of what follows, so understand the shape before diagnosing:

- **Claude Code spawns the server** (`uvx … mcp-for-unity --transport stdio`) as a child
  process of the session. Unity does not spawn anything.
- **The Unity Editor is just a TCP listener** on port 6400 (6401, 6402… for additional
  Editors). It publishes `~/.unity-mcp/unity-mcp-status-<hash>.json` with its port,
  `project_path`, `reloading` flag and heartbeat. The server discovers Editors by
  scanning those files and probing the ports.
- **There is no auth token and no shared bridge.** Nothing is pinned to "whichever
  Editor started it".
- **Tool binding is independent of Unity.** The server starts, binds its ~47 tools and
  stays alive even with zero Editors running; calls just fail with
  `"No Unity Editor instances found"` until one appears. So Unity can be closed,
  restarted or pointed at another worktree mid-session without losing MCP tools.

The practical consequence: **almost every "the bridge died" symptom is not a thing
anymore.** If tools are missing, it is a registration/session problem. If tools are
present but calls fail, it is a Unity-side problem. Those are the only two branches.

## Environment diagnostics

**Working directory (should be the Unity project root for the checks below):**
```
!`pwd`
```

**Is `uv` installed? (`uvx` runs the MCP server)**
```
!`which uvx 2>/dev/null && uv --version 2>/dev/null || echo "MISSING: run 'brew install uv'"`
```

**Coplay package in current project's `Packages/manifest.json`:**
```
!`grep -o "com.coplaydev.unity-mcp[^\"]*" Packages/manifest.json 2>/dev/null || echo "MISSING — add via Unity: Window → Package Manager → + → Add package from git URL"`
```

**Unity Editors publishing a stdio bridge (port, project, heartbeat):**
```
!`cat ~/.unity-mcp/unity-mcp-status-*.json 2>/dev/null || echo "No status files — no Editor has started its bridge"`
```

**Is an Editor actually listening on its socket?**
```
!`lsof -nP -iTCP:6400-6410 -sTCP:LISTEN 2>/dev/null | head -5 || echo "Nothing listening on 6400-6410 — open the Unity Editor and check the MCP window"`
```

**What Claude Code has registered for Unity MCP:**
```
!`claude mcp list 2>&1 | grep -iE "unity|coplay" | head -5 || echo "no unity/coplay MCP registered"`
```

## Your task

Print a clean status table (✓ / ✗ per component), then walk the user through fixing the
**earliest** `✗` only. Don't run `claude mcp remove` or package installs without asking.

### The setup, in the order it must happen

**1. `uv` installed system-wide.**
```bash
brew install uv
```

**2. Coplay's Unity package installed in the project.**

Unity: **Window → Package Manager → `+` → Add package from git URL**:

```
https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity
```

**3. Open the project in the Unity Editor** and wait for the import to finish.

**4. Set the Editor's transport to Stdio.**

Press **`Cmd+Shift+M`** (or **Window → MCP for Unity → Toggle MCP Window**). In the
Connection section, set the **Transport** dropdown to **Stdio**. The **Unity Port**
field below it shows the socket the Editor listens on — 6400 by default, auto-incremented
if another Editor already holds it.

Confirm it took: a `~/.unity-mcp/unity-mcp-status-*.json` appears whose `project_path`
is this project's `Assets` directory, and `lsof -nP -iTCP:6400-6410 -sTCP:LISTEN` shows
Unity holding a port.

**5. Register the MCP server with Claude Code.**

Unlike HTTP, the stdio command line is identical for every project and every Editor —
nothing project-specific, nothing that goes stale. The canonical config ships with this
plugin at `templates/unity-mcp.mcp.json`:

```json
{
  "mcpServers": {
    "UnityMCP": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "mcpforunityserver", "mcp-for-unity", "--transport", "stdio"]
    }
  }
}
```

Write it into the Unity project's `.mcp.json` (project scope, checked in, everyone on
the repo gets it), or register it for just this user:

```bash
claude mcp add UnityMCP --scope user -- "$(which uvx)" --from mcpforunityserver mcp-for-unity --transport stdio
```

**Resolve `uvx` to an absolute path** when you write the config, rather than leaving the
bare name. MCP servers are spawned from the client's environment, not from an interactive
shell that sourced the user's profile, so a GUI-launched client frequently can't find a
Homebrew `uvx` on PATH — and that failure costs the whole session (see Pitfalls).

The server name **must** be `UnityMCP` — every skill in this plugin calls
`mcp__UnityMCP__*` tools by that name.

Coplay's own **Configure Claude Code** button in the MCP window writes an equivalent
entry. Either route works; the button additionally respects a prerelease Unity package
by pinning `--prerelease explicit --from "mcpforunityserver>=0.0.0a0"`.

**6. Start a fresh Claude session in the Unity project directory.**

MCP tools bind at session start. Exit and start a bare `claude` (no `/resume`), then:

> *"call the unity get_editor_state tool"*

A real response means the whole chain works.

### Pitfalls

- **`uvx` not resolvable in the launching environment.** The one genuine stdio failure
  mode, and the reason step 5 writes an absolute path: MCP servers are spawned from the
  client's environment, not from a shell that sourced the user's profile. If `uvx` can't
  be resolved the server never starts and **no Unity tools exist for the entire session**
  — there is no mid-session recovery the way HTTP had. Symptom: `mcp__UnityMCP__*` absent,
  `claude mcp list` shows UnityMCP as failed. Fix: put the output of `which uvx` in
  `command`, then restart the session.
- **Tools bind at session start.** A server registered mid-session isn't attached, and
  `/reload-plugins` does not re-attach MCP tools — it updates config only. Restart the
  session. Likewise `/resume` restores the old session's tool binding; use a bare `claude`.
- **Never trust a green health check as proof the tools are callable.** `claude mcp list`
  showing ✓ means the handshake succeeded, not that the tools are in this session's
  registry. Verify by actually invoking `mcp__UnityMCP__get_editor_state`.
- **Tools present, every call says "No Unity Editor instances found".** The server is
  fine; Unity isn't listening. Check the status file and the socket (diagnostics above).
  Usually the Editor is still importing, or its Transport dropdown is not on Stdio.
- **Multiple Editors, calls landing on the wrong project.** Expected — each Editor is a
  separate instance. Pin with `mcp__UnityMCP__set_active_instance` using the full
  `Name@hash`, or pass `unity_instance="6401"` per call. Verify by routing a call and
  reading `Application.dataPath`. See `/unity-start-task`.
- **Duplicate registrations.** If both a plugin-scope and a user-scope Unity server
  exist, one wins arbitrarily. Keep exactly one named `UnityMCP`.

### Output format

```
Unity MCP setup status

 [✓] uv / uvx installed
 [✓] Coplay package in project manifest
 [✗] Editor bridge listening (stdio)          ← no status file; Editor not open, or Transport ≠ Stdio
 [✗] Claude Code MCP registered (UnityMCP)    ← not in `claude mcp list`

Next step: open Unity, press Cmd+Shift+M, set Transport to Stdio.
```

Only show one "Next step" — the earliest ✗. Don't overwhelm.
