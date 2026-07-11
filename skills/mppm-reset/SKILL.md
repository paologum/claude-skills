---
name: mppm-reset
description: Resets Unity Multiplayer Play Mode (MPPM) virtual player clones — kills any running clone processes, deletes/refreshes the clone Library caches so they re-hydrate from Assets, and gives the user the one-click Editor sequence to bring them back. Use when MPPM clones show stale code, "Missing Type" errors after an Assets change, refuse to enter Play mode with the host, or diverge from the main Editor. Trigger phrases: "reset MPPM", "MPPM clones broken", "virtual players out of sync", "restart local multiplayer", "clones showing old code".
allowed-tools: "Bash(ls *) Bash(rm *) Bash(pkill *) Bash(pgrep *) Bash(du *) Bash(git *) Bash(find *) Read Write"
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

**MPPM package installed?**
```
!`grep -E "com\.unity\.multiplayer\.playmode" Packages/manifest.json 2>/dev/null || echo "MPPM not in manifest — run /unity-local-multiplayer to install"`
```

**Existing clone directories:**
```
!`ls -1d Library/VP-* Library/VirtualProjects 2>/dev/null | head -20`
```

**Clone size:**
```
!`du -sh Library/VirtualProjects 2>/dev/null || echo "(no VirtualProjects dir)"`
```

**Running Unity processes:**
```
!`pgrep -fl "Unity" 2>/dev/null | head -10 || echo "no Unity processes"`
```

## Task

Bring MPPM virtual players back to a clean, in-sync state after Assets changes broke them.

### Steps

1. **Confirm the failure mode with the user** before deleting anything. Ask which of these fits:
   - (a) Clones show "Missing Type" / compile errors that don't exist in the main Editor.
   - (b) Clones can't enter Play mode when the host is in Play mode.
   - (c) Clones show stale scene / stale scripts.
   - (d) Just want a full reset.
   The remediation differs by case — don't nuke the Library for (b) when a re-sync will do.

2. **Kill any running clone processes.** MPPM clones run as separate Unity processes with `-virtualprojects/{tag}` in their args. Do NOT kill the main Editor. Use:
   ```bash
   pgrep -fl "Unity.*virtualprojects" | awk '{print $1}' | xargs -r kill
   ```
   Wait ~2s. If any are still alive: `pkill -9 -f "Unity.*virtualprojects"`.

3. **For case (a) or (c) — stale caches**: delete the per-clone `Library/` inside each virtual project:
   ```bash
   rm -rf Library/VirtualProjects/*/Library
   rm -rf Library/VirtualProjects/*/Temp
   ```
   Do NOT delete `Library/VirtualProjects` itself — that also deletes MPPM's Player Tag config for each clone, and the user has to reconfigure the roster in the Editor.

4. **For case (d) — full reset**: delete the whole VirtualProjects directory. The user WILL have to re-add each virtual player in the Multiplayer window afterwards.
   ```bash
   rm -rf Library/VirtualProjects
   ```

5. **Instruct the user how to bring clones back up** (one-time, in the main Editor):
   - Window → Multiplayer → Multiplayer Play Mode
   - For each virtual player row: click **Activate** (a fresh Unity process spawns and imports from Assets — this takes 1–3 min the first time after a reset)
   - Wait for each clone to finish compiling — its status bar in the Multiplayer window turns green.
   - Enter Play mode in the main Editor. The clones auto-follow.

6. **Sanity check.** Print `du -sh Library/VirtualProjects` so the user sees the cache actually rebuilt.

### Rules

- **Never kill the main Editor.** Only processes whose command line contains `virtualprojects`.
- **Never delete `Assets/`, `ProjectSettings/`, or `Packages/`.** Those are the source of truth — MPPM clones read them.
- If MPPM isn't installed, refuse and point the user at `/unity-local-multiplayer`.
- If no clone directories exist (`Library/VirtualProjects` missing), there's nothing to reset — say so instead of "succeeding" silently.
- If a run is in progress against MPPM (Play mode active), warn the user and ask them to stop it first — killing the clone process mid-run can leave the Library in a torn state.
