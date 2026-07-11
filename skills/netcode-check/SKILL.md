---
name: netcode-check
description: Audits a Unity Netcode-for-GameObjects or Mirror project for the most common wiring bugs — NetworkManager's prefab list missing a NetworkObject prefab that's spawned in code, prefabs with a NetworkObject but no GlobalObjectIdHash, orphan NetworkObjects in scenes not registered anywhere, and duplicate prefab hashes. Read-only — reports findings, does not mutate. Use when the user asks to check netcode wiring, "why isn't my prefab spawning across the network", audit NetworkManager, find orphan NetworkObjects, or before opening a networking PR.
allowed-tools: "Bash(git *) Bash(grep *) Bash(find *) Bash(ls *) Read Grep Glob"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || pwd`
```

**Networking layer detected:**
```
!`grep -l -E "com\.unity\.netcode\.gameobjects|MirrorNG|com\.miragenet|Mirror" Packages/manifest.json 2>/dev/null | head -1; grep -E "\"com\.unity\.netcode\.gameobjects\"|\"com\.miragenet\.mirage\"|\"Mirror\"" Packages/manifest.json 2>/dev/null | head -3`
```

**Files referencing NetworkManager or NetworkObject:**
```
!`grep -rln -E "NetworkManager|NetworkObject|NetworkPrefab" Assets --include='*.cs' 2>/dev/null | head -30`
```

**All prefabs with a NetworkObject component:**
```
!`grep -rln "NetworkObject" Assets --include='*.prefab' 2>/dev/null | head -50`
```

**All scenes:**
```
!`find Assets -name "*.unity" 2>/dev/null | head -30`
```

## Task

Produce a findings report grouped by severity. Report only — do not modify files.

### Checks to run

1. **Prefabs spawned in code but not registered.**
   For each `.cs` file that calls `Spawn`, `NetworkManager.Singleton.SpawnManager.InstantiateAndSpawn`, or Mirror's `NetworkServer.Spawn`, identify the prefab reference. Cross-reference against the NetworkManager's `NetworkPrefabsList` asset (Netcode) or the registered spawn prefabs list (Mirror). Flag any spawned prefab that isn't registered — it will fail at runtime with "prefab not found".

2. **Prefab has NetworkObject but empty `PrefabGuid` / `GlobalObjectIdHash`.**
   Grep each `.prefab` with a NetworkObject for `GlobalObjectIdHash: 0` — this happens after copy-paste and causes spawns to error out.

3. **Duplicate `GlobalObjectIdHash`.**
   List all values and flag duplicates. Same hash → spawn errors.

4. **Orphan NetworkObjects in scenes.**
   Grep `.unity` files for `NetworkObject` components on GameObjects that aren't parented to a NetworkManager and aren't in the registered prefabs list. These behave as scene NetworkObjects — often intended, sometimes accidental leftovers. Flag with LOW severity.

5. **NetworkManager count.**
   There should be exactly ONE NetworkManager per scene. Grep and count. Flag multi-NetworkManager scenes.

6. **Bootstrap scene has NetworkManager.**
   Look for a `Bootstrap`, `Boot`, or `Loading` scene (or the first scene in `EditorBuildSettings.asset`). Confirm it hosts the NetworkManager — otherwise host/client connections initiated before other scenes load will fail.

### Report format

Emit one fenced markdown block with sections in this order:

```markdown
## Netcode wiring check

**Networking layer**: <detected>
**NetworkManager scene(s)**: <list>

### 🔴 High
<one line per finding: `file:line — problem — suggested fix`>

### 🟡 Medium
<same format>

### 🔵 Low
<same format>

### ✅ Clean
<one line per check that passed, so the user knows what was actually verified>
```

If nothing is wrong: emit only the **✅ Clean** section.

### Rules

- **Read-only.** Never edit .cs, .prefab, .unity, or NetworkManager assets. Report findings only — let the user apply fixes.
- **Skip the check** and say so explicitly if no networking package is installed (neither Netcode nor Mirror in `manifest.json`).
- Prefer file:line references in findings so the user can click straight to the problem.
- Don't invent findings from thin air. If the check couldn't be run (e.g. NetworkManager prefab list is a binary asset that's hard to parse), say so and move on.
- Do NOT report `Assets/**/*Test*.cs` or `Assets/**/Tests/**` findings unless the user asks — test scenes deliberately create ad-hoc NetworkObjects.
