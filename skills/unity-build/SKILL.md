---
name: unity-build
description: Builds the current Unity project from the command line for a target platform (Windows, Mac, WebGL, iOS, Android, Linux). Creates Assets/Editor/BuildScript.cs if it doesn't exist, invokes Unity in batch mode via -executeMethod, and reports build success or failure with the artifact path. Use when the user asks to build the Unity project, compile for Windows/Mac/WebGL/iOS/Android, do a release build, do a CI build, or "make a build".
allowed-tools: "Read Write Edit Bash(/Applications/Unity/Hub/Editor/* *) Bash(ls /Applications/Unity/Hub/Editor*) Bash(cat *) Bash(mkdir -p *) Glob"
argument-hint: "<Windows|Mac|WebGL|iOS|Android|Linux> [output-dir]"
---

## Project context

**Unity version:**
```
!`cat ProjectSettings/ProjectVersion.txt 2>/dev/null | head -2 || echo "NOT A UNITY PROJECT"`
```

**Installed Unity Editors:**
```
!`ls /Applications/Unity/Hub/Editor/ 2>/dev/null || echo "Unity Hub not found"`
```

**Existing BuildScript:**
```
!`ls Assets/Editor/BuildScript.cs 2>/dev/null || echo "BuildScript.cs does not exist — will create"`
```

**Build Profiles checked in:**
```
!`find Assets -path "*/Build Profiles/*.asset" 2>/dev/null | head -10`
```

**Arguments:**
```
!`echo "$ARGUMENTS"`
```

## Your task

Build the project for the requested target and report where the artifact landed.

### Step 1 — parse arguments

- First arg: target — one of `Windows`, `Mac`, `WebGL`, `iOS`, `Android`, `Linux`. Required. If missing, ask the user.
- Second arg: output directory. Default: `Builds/<target>/`.

Target → Unity flag mapping:

| Arg | `-buildTarget` | `BuildTarget` enum |
|-----|----------------|--------------------|
| Windows | `StandaloneWindows64` | `BuildTarget.StandaloneWindows64` |
| Mac     | `StandaloneOSX` | `BuildTarget.StandaloneOSX` |
| WebGL   | `WebGL` | `BuildTarget.WebGL` |
| iOS     | `iOS` | `BuildTarget.iOS` |
| Android | `Android` | `BuildTarget.Android` |
| Linux   | `StandaloneLinux64` | `BuildTarget.StandaloneLinux64` |

### Step 2 — ensure BuildScript.cs exists

If `Assets/Editor/BuildScript.cs` is missing, create it with this content:

```csharp
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class BuildScript
{
    public static void BuildWindows() => Build(BuildTarget.StandaloneWindows64, "Builds/Windows/Game.exe");
    public static void BuildMac()     => Build(BuildTarget.StandaloneOSX,       "Builds/Mac/Game.app");
    public static void BuildLinux()   => Build(BuildTarget.StandaloneLinux64,   "Builds/Linux/Game");
    public static void BuildWebGL()   => Build(BuildTarget.WebGL,               "Builds/WebGL");
    public static void BuildIOS()     => Build(BuildTarget.iOS,                 "Builds/iOS");
    public static void BuildAndroid() => Build(BuildTarget.Android,             "Builds/Android/Game.apk");

    static void Build(BuildTarget target, string defaultOutput)
    {
        string output = GetArg("--output") ?? defaultOutput;
        string version = GetArg("--version");
        if (!string.IsNullOrEmpty(version)) PlayerSettings.bundleVersion = version;

        Directory.CreateDirectory(Path.GetDirectoryName(output));

        var scenes = EditorBuildSettings.scenes
            .Where(s => s.enabled)
            .Select(s => s.path)
            .ToArray();

        if (scenes.Length == 0)
        {
            Debug.LogError("[BuildScript] No enabled scenes in Build Settings.");
            EditorApplication.Exit(1);
            return;
        }

        var opts = new BuildPlayerOptions
        {
            scenes           = scenes,
            locationPathName = output,
            target           = target,
            options          = BuildOptions.None
        };

        Debug.Log($"[BuildScript] Building {target} → {output}");
        BuildReport report = BuildPipeline.BuildPlayer(opts);
        var summary = report.summary;
        Debug.Log($"[BuildScript] Result: {summary.result}  Size: {summary.totalSize} bytes  Time: {summary.totalTime}");
        EditorApplication.Exit(summary.result == BuildResult.Succeeded ? 0 : 1);
    }

    static string GetArg(string name)
    {
        var args = System.Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
            if (args[i] == name) return args[i + 1];
        return null;
    }
}
```

Create the `Assets/Editor/` directory if it doesn't exist.

### Step 3 — invoke Unity

```bash
"/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity" \
  -batchmode -nographics -quit \
  -projectPath "$(pwd)" \
  -buildTarget <UnityBuildTargetFlag> \
  -executeMethod "BuildScript.Build<Target>" \
  -logFile - \
  --output "<resolved output path>"
```

Tail the log as it runs. Builds can take 1–30 minutes. Do not time out aggressively.

### Step 4 — report

On success: print the artifact path (and size if available from log).
On failure: extract the **last error block** from the log (lines containing `error CS`, `BuildPlayerWindow`, or `Exception`), show up to 20 lines around it.

### Don't

- Don't run `BuildScript.BuildXxx` against a target that needs platform modules not installed (e.g. WebGL build on a machine without the WebGL module). If the log shows "Build target group support not installed", surface that clearly and tell the user to install the module from Unity Hub.
- Don't add code-signing, notarization, or distribution steps — out of scope.
- Don't modify Player Settings or scenes — the build script reads from the existing Build Settings.
- Don't delete the previous build directory — Unity overwrites in place.
