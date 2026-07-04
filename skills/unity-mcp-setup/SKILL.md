---
name: unity-mcp-setup
description: Diagnoses whether Coplay's Unity MCP is correctly set up for the current Unity project and walks the user through fixing anything missing. Checks uv/uvx installation, Python discoverability (pyenv gotchas), Coplay package presence in the Unity project, Editor bridge status on port 8080, and Claude Code MCP registration. Use when the user asks to set up Unity MCP, connect Claude to Unity, configure the Unity MCP, "why isn't Unity MCP working", or troubleshoots MCP tool calls failing against Unity.
allowed-tools: "Read Bash(which *) Bash(pyenv *) Bash(brew *) Bash(ls *) Bash(cat *) Bash(lsof *) Bash(ps *) Bash(claude mcp *) Bash(grep *) Bash(*/python* --version) Bash(/opt/homebrew/bin/* --version) Bash(find *) Glob"
---

## Environment diagnostics

**Working directory (should be the Unity project root for the checks below):**
```
!`pwd`
```

**Is `uv` installed? (required — `uvx` and the Coplay HTTP server depend on it)**
```
!`which uv 2>/dev/null && uv --version 2>/dev/null || echo "MISSING: run 'brew install uv'"`
```

**pyenv shim Python (Coplay's Editor auto-detector checks `~/.pyenv/shims` first; if it returns < 3.10, Coplay rejects it silently):**
```
!`~/.pyenv/shims/python3 --version 2>/dev/null || echo "no pyenv shim"`
```

**pyenv global (if this is < 3.10, run `pyenv global 3.11.9` to fix):**
```
!`pyenv version 2>/dev/null || echo "pyenv not installed"`
```

**Homebrew Python (Coplay's fallback):**
```
!`/opt/homebrew/bin/python3 --version 2>/dev/null || echo "no /opt/homebrew/bin/python3 — brew install python@3.11"`
```

**Coplay package in current project's `Packages/manifest.json`:**
```
!`grep -o "com.coplaydev.unity-mcp[^\"]*" Packages/manifest.json 2>/dev/null || echo "MISSING — add via Unity: Window → Package Manager → + → Add package from git URL"`
```

**Is the Unity Editor open with a project? (Coplay HTTP server must be listening on 8080):**
```
!`lsof -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | grep -iE "python|mcp-for-unity" | head -1 || echo "Nothing listening on 8080 — open Unity Editor and press Cmd+Shift+M to start the bridge"`
```

**What Claude Code has registered for `unity` MCP:**
```
!`claude mcp list 2>&1 | grep -iE "unity|coplay" | head -5 || echo "no unity/coplay MCP registered"`
```

**Any leftover stdio registration (this must be removed — it fights with the HTTP one):**
```
!`claude mcp list 2>&1 | grep -E "uvx.*coplay-mcp-server" | head -3 || echo "no stale stdio entries"`
```

## Your task

Based on the diagnostics above, print a clean status table for the user (✓ / ✗ per component), then walk them through fixing each `✗` in order. Do not run destructive commands (`claude mcp remove`, package installs) without asking.

### The setup, in the order it must happen

Each step depends on the previous. Do not skip ahead.

**1. `uv` installed system-wide.**
```bash
brew install uv
```

**2. Python 3.10+ discoverable via one of the paths Coplay searches** (in this priority order: `~/.pyenv/shims`, `/opt/homebrew/bin`, `/usr/local/bin`).

The most common failure mode: **pyenv global is set to Python 3.9.x** (often via `~/.python-version`), so `~/.pyenv/shims/python3` returns 3.9 and Coplay's Editor plugin rejects it. Fix:

```bash
pyenv global 3.11.9    # or any 3.10+ pyenv already has installed
```

Verify: `~/.pyenv/shims/python3 --version` should now print 3.11.x or newer.

**3. Coplay's Unity package installed in the current project.**

In the Unity Editor: **Window → Package Manager → `+` → Add package from git URL**:

```
https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity
```

Or via OpenUPM if scoped registries are set up:

```bash
openupm add com.coplaydev.unity-mcp
```

**4. Open the Guandan (or target) project in the Unity Editor.** Wait for it to finish importing.

**5. Start the Coplay Editor bridge.**

Inside the Unity Editor, press **`Cmd+Shift+M`** (or menu: **Window → MCP for Unity → Toggle MCP Window**). Wait for the window's "Server Running" indicator to go green. This spawns the `mcp-for-unity` HTTP server on `127.0.0.1:8080`.

**6. Register Claude Code as a client — through the Coplay UI, not by hand.**

In the MCP for Unity window, find the **Clients** section listing Cursor / Claude Code / VS Code / etc. Click **Configure** (or **Install**) next to **Claude Code**. Coplay writes an HTTP-transport MCP entry into `~/.claude.json` with the current auth token baked in.

**Do not** manually run `claude mcp add ... uvx coplay-mcp-server@latest`. That's the OLD stdio architecture and it won't reach the new HTTP-based Editor bridge. If a stale entry exists, remove it first:

```bash
claude mcp remove unity --scope user
```

**7. Verify.**

```bash
claude mcp list
```

The `unity` line should show `http://127.0.0.1:8080` (not a `uvx …` command).

**8. Start a fresh Claude session in the Unity project directory.**

MCP tool registration happens at session start. An already-running session will not pick up new MCP tools even after `/reload-plugins`. Exit the current session and start a fresh `claude` in the project directory (no `/resume`). Try:

> *"call the unity get_editor_state tool"*

A real response means the full chain is working.

### Pitfalls to warn about

- **pyenv shim returns < 3.10.** Silent rejection. Symptom: "Python not found" in the Coplay Editor window despite `/opt/homebrew/bin/python3 --version` printing 3.13. Fix: `pyenv global 3.11.9`.
- **Old stdio MCP registration fights the new HTTP one.** If both `plugin:claude-skills:unity` and a user-scope `unity` point at `uvx coplay-mcp-server`, calls fail with "Requests directory missing." Fix: remove both, use only the HTTP one Coplay's UI writes.
- **Auth token rotates per Editor session.** The token in `--unity-instance-token …` in the running `mcp-for-unity` process changes when the Editor restarts. That's why Coplay's UI button must write the config — a hand-written token goes stale on the next Editor launch.
- **`/resume` restores the pre-setup tool binding.** Even after fixing everything, `/resume`-ing an old session gives you the old (broken) tool set. Use bare `claude` in the project directory.
- **`/reload-plugins` does NOT re-attach MCP tools mid-session.** It updates config only. Restart the session.

### Output format

Print exactly this shape:

```
Unity MCP setup status

 [✓] uv installed
 [✗] Python discoverable at Coplay's paths      ← pyenv shim returns 3.9.9
 [✓] Coplay package in project manifest
 [✗] Editor bridge running on :8080             ← Unity Editor not open, or window not activated
 [✗] Claude Code MCP registered via HTTP        ← still on old stdio path

Next step: run `pyenv global 3.11.9`, then open Unity and press Cmd+Shift+M.
```

Only show one "Next step" — the earliest ✗ in the list. Don't overwhelm.
