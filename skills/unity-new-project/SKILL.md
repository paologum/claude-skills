---
name: unity-new-project
description: Scaffolds a new empty Unity project at a given path via the command-line Editor, then patches Packages/manifest.json to add a render pipeline (URP / HDRP) and common dev packages (Input System, Test Framework). Use when the user asks to create a new Unity project, scaffold a Unity game, start a new Unity codebase, bootstrap a Unity project, or initialize a fresh Unity project.
allowed-tools: "Read Write Edit Bash(/Applications/Unity/Hub/Editor/* *) Bash(ls /Applications/Unity/Hub/Editor*) Bash(mkdir -p *) Bash(ls *) Glob"
argument-hint: "<project-path> [URP|HDRP|2D|3D] [unity-version]"
---

## Host context

**Installed Unity Editors:**
```
!`ls /Applications/Unity/Hub/Editor/ 2>/dev/null || echo "Unity Hub not found"`
```

**Arguments:**
```
!`echo "$ARGUMENTS"`
```

## Your task

Create a new Unity project at the requested path with sensible defaults.

### Caveat to surface up front

Unity's CLI **`-createProject` only creates an empty project** — there's no template flag for URP/HDRP/2D Core. Unity Hub templates aren't reachable from the Editor CLI. So this skill creates empty then patches `Packages/manifest.json` to add the desired render pipeline package, plus common dev packages. The first time the user opens the project, Unity will import the packages and generate the render-pipeline assets.

If the user wants a "real" template-based project (with sample scenes, settings, materials), tell them to create it via Unity Hub instead — this skill is for clean, scriptable scaffolding.

### Step 1 — parse arguments

- Arg 1: project path (required). Resolve to absolute. If it exists and is non-empty, ask before overwriting.
- Arg 2: template — `URP` (default), `HDRP`, `2D`, `3D`. Maps to a package set below.
- Arg 3: Unity version — defaults to the newest installed version on this machine.

### Step 2 — create the empty project

```bash
"/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity" \
  -batchmode -quit -nographics \
  -createProject "<abs-path>" \
  -logFile -
```

Wait for it to finish (~30–60s).

### Step 3 — patch `Packages/manifest.json`

Read the manifest at `<abs-path>/Packages/manifest.json`. Merge in these dependencies based on template:

**Common (all templates):**
```json
"com.unity.inputsystem": "1.11.2",
"com.unity.test-framework": "1.4.5",
"com.unity.test-framework.performance": "3.0.3"
```

**URP:**
```json
"com.unity.render-pipelines.universal": "17.0.3"
```

**HDRP:**
```json
"com.unity.render-pipelines.high-definition": "17.0.3"
```

**2D:**
```json
"com.unity.2d.sprite": "1.0.0",
"com.unity.2d.tilemap": "1.0.0",
"com.unity.2d.animation": "10.1.4"
```

**3D:** (no extra packages — built-in render pipeline)

Pin versions appropriate to the installed Unity version (Unity 6 = 17.x render pipelines; Unity 2022 LTS = 14.x). Don't hardcode if you can detect the Unity version and pick the matching package version.

### Step 4 — create a minimal directory layout

```
Assets/
├── Editor/
├── Scenes/
├── Scripts/
└── Tests/
    ├── EditMode/
    └── PlayMode/
```

Use `mkdir -p`. Don't create stub scripts or scenes — the user will fill them in.

### Step 5 — write a starter `.gitignore`

Create `<abs-path>/.gitignore` with Unity's standard ignore set:

```
[Ll]ibrary/
[Tt]emp/
[Oo]bj/
[Bb]uild/
[Bb]uilds/
[Ll]ogs/
[Uu]ser[Ss]ettings/
[Mm]emoryCaptures/
[Rr]ecordings/

*.csproj
*.sln
*.suo
*.user
*.unityproj
*.booproj
*.tmp
*.log
*.pidb
*.svd
*.userprefs
*.app
*.apk
*.unitypackage
.DS_Store
.vsconfig
```

### Step 6 — report

Output:
- Project path
- Unity version used
- Packages added (list)
- Reminder: "Open the project in Unity once to let it install the packages and generate render-pipeline assets."

### Don't

- Don't `git init` — that's the user's choice. Suggest it but don't run it.
- Don't open the Editor GUI — `-batchmode` only.
- Don't add networking packages by default. Recommend Mirror or Netcode for GameObjects if the user asks about multiplayer.
- Don't add asset-store imports, sample scenes, or third-party packages without being asked.
