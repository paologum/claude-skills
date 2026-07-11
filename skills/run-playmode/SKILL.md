---
name: run-playmode
description: Runs Unity PlayMode tests filtered by class, namespace, or category — via the warm Unity MCP if available (~2s startup), else via batchmode CLI (~30s cold). Thin wrapper over `mcp__UnityMCP__run_tests` / `get_test_job` that also parses failures and prints them in a copy-paste-friendly form. Use when the user asks to run a specific PlayMode test, run tests in Play mode, run `SetValidator` tests, run tests matching a filter, or "run just the FooBar tests".
allowed-tools: "Bash(git *) Bash(grep *) Bash(find *) Bash(ls *) Read Grep Glob"
argument-hint: "<test-class-or-filter>"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || pwd`
```

**Is a Unity project?**
```
!`ls ProjectSettings/ProjectVersion.txt 2>/dev/null && head -1 ProjectSettings/ProjectVersion.txt || echo "no Unity project"`
```

**Requested filter:**
```
!`echo "${ARGUMENTS:-<all PlayMode tests>}"`
```

**Existing PlayMode test files matching the filter:**
```
!`find Assets -path '*/Tests/*' -name '*.cs' 2>/dev/null | xargs grep -l "$ARGUMENTS" 2>/dev/null | head -20`
```

## Task

Run PlayMode tests, filtered by the argument, and report results.

### Path A — Unity MCP (preferred)

If `mcp__UnityMCP__run_tests` is available in this session:

1. **Verify the Editor is idle.** Call `mcp__UnityMCP__manage_editor` `action: "get_state"`. If `isPlaying` is true, tell the user to stop Play mode first — refuse to run.
2. **Kick off the test job.**
   ```
   mcp__UnityMCP__run_tests({
     testMode: "PlayMode",
     testFilter: "$ARGUMENTS"   // full class name, namespace, or a fully-qualified test method
   })
   ```
   The tool returns a `jobId`. **Don't block** — the Editor takes 1–10s to enter test-run mode.
3. **Poll**: call `mcp__UnityMCP__get_test_job` with the jobId every ~2s until `status` is `Completed` or `Failed`. Print a one-line progress update every 3rd poll so the user sees liveness.
4. **Parse and report**:
   - Total / passed / failed / skipped counts on the first line.
   - Each failure as `<test-name>\n  <message>\n  <first stack frame>` — no full stack traces unless the user asks.
   - If any failure, print the exact filter the user can re-run: `/run-playmode <failing-class>`.

### Path B — batchmode CLI (fallback)

If MCP isn't available, fall back to `/unity-test` (the sibling skill) rather than re-implementing the CLI here. Emit:

> Unity MCP isn't loaded this session. Run `/unity-test PlayMode <filter>` for a batchmode run (~30s cold startup) — same output.

### Rules

- **PlayMode only.** For EditMode tests, tell the user to use `/unity-test EditMode <filter>` — this skill exists specifically because PlayMode + MCP is the fastest tight-loop combo, and EditMode is already fast in batchmode.
- **Refuse** if the filter is empty AND the running Editor has more than a few dozen PlayMode tests — a full run in the warm Editor blocks the user's Editor for minutes. Suggest they narrow the filter or use batchmode.
- Do NOT mutate the project. Do NOT enter Play mode manually — `run_tests` handles that.
- If the filter doesn't match any test class in `Assets/**/Tests/**`, warn before running: probably a typo.
- If the Editor is compiling (`get_state` reports `isCompiling: true`), wait for compile to finish before kicking off the run. Poll every 2s, max 60s.
