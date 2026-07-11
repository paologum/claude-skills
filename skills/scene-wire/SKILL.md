---
name: scene-wire
description: Drives Unity MCP (`manage_gameobject`, `manage_ui`, `manage_components`) from a natural-language description of a scene/prefab wiring change — creating GameObjects, parenting them, setting RectTransform anchors, adding components, assigning serialized fields, and setting up event wiring. Reads the current scene state first (`find_gameobjects`), plans the smallest set of MCP calls, applies them, and reports what changed. Refuses to hand-edit `.unity` / `.prefab` YAML. Use when the user asks to add a UI element to a canvas, wire up a button, parent an object under another, set an anchor, add a component, "wire the Pass button to GameController.OnPass", or any concrete scene mutation.
allowed-tools: "Bash(git *) Bash(ls *) Read Grep Glob"
argument-hint: "<what to wire>"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || pwd`
```

**MCP available?** Before doing anything, confirm `mcp__UnityMCP__find_gameobjects` shows up in your tools this session. If not, refuse and point the user at `/unity-mcp-setup`. Editing scene / prefab YAML by hand is banned by the coder-agent principles — do NOT fall back to that.

**Editor state:**
Call `mcp__UnityMCP__manage_editor({ action: "get_state" })` — record the active scene name, `isPlaying`, and `isCompiling`. If `isPlaying` is true, **stop** first: `manage_editor({ action: "stop" })`, then wait for `isPlaying: false`. Wiring changes made during Play mode are discarded on stop.

## Task

Turn the argument (`$ARGUMENTS`) into a minimal, correct sequence of MCP calls. Work in this order — planning first, then applying:

### 1. Read the current scene

- Call `mcp__UnityMCP__find_gameobjects` with a broad pattern to see the top-level hierarchy (e.g. `search: "*", searchScope: "scene"`).
- Narrow to the parent GameObject the user named (e.g. `LobbyCanvas`, `GameCanvas`). Confirm it exists. If ambiguous (multiple matches), ask which one before proceeding.
- If the user described something relative to a prefab, open the prefab in prefab mode first via `manage_prefabs` — don't wire scene overrides for something that should live on the prefab.

### 2. Plan (announce, then act)

Print one short block to the user showing the plan:

```
Plan:
  1. Create <name> under <parent>
  2. Set RectTransform anchors (<preset>)
  3. Add <Component>, wire onClick → <target>.<method>
```

Then apply. If the plan has more than ~5 steps, ask the user to confirm before running — that's usually a sign of misunderstanding.

### 3. Apply

Preferred tools by task:

| Task | Tool |
|---|---|
| Create GameObject, parent, rename | `manage_gameobject` |
| Add / edit UI (Button, Image, TMP_Text, layout) | `manage_ui` |
| Add / remove / configure a Component | `manage_components` |
| Assign a serialized field or reference | `manage_components` (`action: "set_property"`) |
| Save/apply prefab changes | `manage_prefabs` |
| Sprite / texture assignment | `manage_asset` to resolve the GUID, `manage_components` to assign |

Rules while applying:

- **One thing per call.** Don't batch unrelated mutations into `execute_code` — use the typed tools so errors surface at the right step.
- **Verify after each mutation** you can't roll back from (adding a component, reparenting): call `find_gameobjects` on the target and confirm the result before moving on.
- **Anchor presets**: when the user says "top-left", "stretch", "bottom-center", etc., set the actual anchor min/max — don't just eyeball position values. `manage_ui` accepts named presets.
- **Event wiring**: for `Button.onClick` → `TargetComponent.Method`, use `manage_ui`'s event API, not raw `set_property` on the event list. The raw path silently fails if the target component hasn't been resolved.

### 4. Save

If the change is on a scene: `manage_scene({ action: "save" })`. If on a prefab: `manage_prefabs({ action: "apply" })`. Announce which was saved.

### 5. Report

One short block:

```
Wired:
  ✓ Created <name> under <parent>
  ✓ Set anchors (<preset>)
  ✓ Added <Component>, wired onClick → <target>.<method>
Saved to: <scene or prefab>
```

### Rules

- **Never** open, read, or write `.unity` / `.prefab` files directly. If MCP tools can't express what the user wants, say so and stop — do NOT reach for `Edit`.
- **Refuse** if Play mode is active and can't be stopped (e.g. an MPPM run is in flight).
- If the target GameObject doesn't exist, ask before creating it. "Wire the Pass button" is ambiguous when there's no Pass button yet — the user might have meant "on the existing one in a different canvas".
- If the user's description implies a Component the project doesn't have (e.g. a custom `GameController`), grep `Assets/**/*.cs` for the class first. If it doesn't exist, refuse and tell the user to create the script — don't wire against a nonexistent target.
- Keep the plan concise. If the user's ask is one-line ("rename Foo to Bar"), skip the plan block and just do it.
