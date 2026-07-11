---
name: unity-smart-merge
description: Configures git in the current Unity project to use Unity's YAMLMerge tool for .unity, .prefab, .asset, and .mat files so merge conflicts on scenes/prefabs resolve cleanly instead of producing corrupt YAML. Writes .gitattributes, points `merge.unityyamlmerge.driver` at UnityYAMLMerge under the installed Editor, and adds a `git smerge` alias. Use when the user asks to set up Unity smart merge, fix scene merge conflicts, configure YAMLMerge, stop scene/prefab merges from breaking, or "why does my .unity file merge as one big blob".
allowed-tools: "Bash(git *) Bash(ls *) Bash(find *) Bash(cat *) Bash(mdfind *) Read Write Edit"
---

## Context

**Repo root:**
```
!`git rev-parse --show-toplevel 2>/dev/null || echo "not a git repo"`
```

**Is a Unity project?**
```
!`ls ProjectSettings/ProjectVersion.txt 2>/dev/null && cat ProjectSettings/ProjectVersion.txt 2>/dev/null || echo "no Unity project detected"`
```

**Existing .gitattributes:**
```
!`cat .gitattributes 2>/dev/null || echo "(none)"`
```

**Existing merge drivers in git config:**
```
!`git config --get-regexp '^merge\.' 2>/dev/null`
```

**Installed Unity editors (Hub default location on macOS):**
```
!`ls -1 "/Applications/Unity/Hub/Editor" 2>/dev/null | head -20`
```

## Task

Configure this Unity project so `.unity`, `.prefab`, `.asset`, `.mat`, `.anim`, `.controller`, `.physicMaterial`, `.physicsMaterial2D`, `.meta`, and `.asmdef` files merge via UnityYAMLMerge instead of the default text merger.

### Steps

1. **Locate `UnityYAMLMerge`.** It ships inside the Editor bundle. On macOS the path is:
   ```
   /Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/Tools/UnityYAMLMerge
   ```
   Use the project's `ProjectSettings/ProjectVersion.txt` `m_EditorVersion` to pick the right one. If that exact version isn't installed, pick the closest installed LTS and warn the user.
   On Linux: `~/Unity/Hub/Editor/<version>/Editor/Data/Tools/UnityYAMLMerge`.
   On Windows: `C:\Program Files\Unity\Hub\Editor\<version>\Editor\Data\Tools\UnityYAMLMerge.exe`.

2. **Register the merge driver in the project's local git config** (not global — this is per-project):
   ```bash
   git config merge.unityyamlmerge.name "Unity SmartMerge (UnityYAMLMerge)"
   git config merge.unityyamlmerge.driver '"<abs-path-to-UnityYAMLMerge>" merge -h -p --force --fallback none %O %B %A %A'
   git config merge.unityyamlmerge.recursive binary
   ```
   Quote the path — it contains spaces.

3. **Write `.gitattributes`** at the repo root (append if a subset already exists, otherwise create):
   ```
   # Unity YAML merge — driver defined per-clone in .git/config
   *.unity     merge=unityyamlmerge eol=lf
   *.prefab    merge=unityyamlmerge eol=lf
   *.asset     merge=unityyamlmerge eol=lf
   *.mat       merge=unityyamlmerge eol=lf
   *.anim      merge=unityyamlmerge eol=lf
   *.controller merge=unityyamlmerge eol=lf
   *.physicMaterial   merge=unityyamlmerge eol=lf
   *.physicsMaterial2D merge=unityyamlmerge eol=lf
   *.meta      merge=unityyamlmerge eol=lf
   *.asmdef    merge=unityyamlmerge eol=lf
   ```
   `eol=lf` is important — Unity writes LF regardless of platform, and CRLF creates spurious diffs on Windows.

4. **Add a `git smerge` alias** for one-shot fixups on legacy conflicts:
   ```bash
   git config alias.smerge '!git config --get merge.unityyamlmerge.driver >/dev/null && git mergetool --tool=unityyamlmerge'
   ```

5. **Verify** — echo the driver line and the .gitattributes tail so the user sees what changed.

### Notes for the user

- Because `.git/config` is not versioned, **every new clone** of the repo has to re-run this skill (or a `scripts/setup-git.sh` script) to register the driver. Suggest creating that script if the project doesn't already have one — reference it in the README.
- If the user's Editor path is non-standard (installed outside Unity Hub), ask them for the path instead of guessing.
- Do NOT set the driver globally. Different Unity versions ship different `UnityYAMLMerge` builds; using the wrong one silently corrupts scenes.
- On merge conflicts you can also run `git checkout --ours <file>` or `--theirs <file>` for single-user scenes where one side is obviously canonical — smart-merge is for the co-authored case.

### Rules

- **Never overwrite** an existing `.gitattributes` — merge into it, keeping any non-Unity rules.
- **Never write to `~/.gitconfig`.** Only touch `.git/config` inside this repo.
- If not in a Unity project (`ProjectSettings/ProjectVersion.txt` missing), refuse and tell the user.
- If the target Unity version isn't installed, refuse and list the installed versions — don't guess a substitute silently.
