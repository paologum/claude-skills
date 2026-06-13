---
name: unity-test
description: Runs Unity Test Framework tests (EditMode or PlayMode) from the command line in batch mode, parses the NUnit XML output, and reports pass/fail with failure details. Auto-detects the project's Unity version and locates the Editor binary. Use when the user asks to run Unity tests, run EditMode tests, run PlayMode tests, test the Unity project, check if tests pass, or run a specific test class/category.
allowed-tools: "Read Bash(/Applications/Unity/Hub/Editor/* *) Bash(ls /Applications/Unity/Hub/Editor*) Bash(cat *) Bash(grep *) Bash(find * -name *) Glob"
argument-hint: "[EditMode|PlayMode] [test-filter]"
---

## Project context

**Unity version pinned by project:**
```
!`cat ProjectSettings/ProjectVersion.txt 2>/dev/null | head -2 || echo "NOT A UNITY PROJECT"`
```

**Installed Unity Editors on this machine:**
```
!`ls /Applications/Unity/Hub/Editor/ 2>/dev/null || echo "Unity Hub not found"`
```

**Test assemblies / test files in project:**
```
!`find Assets/Tests -name "*.cs" -o -name "*.asmdef" 2>/dev/null | head -20`
```

**Arguments:**
```
!`echo "$ARGUMENTS"`
```

## Your task

Run Unity's test runner against the current project and report the results.

### Step 1 — resolve binary

1. Read the Unity version from `ProjectSettings/ProjectVersion.txt` (e.g. `6000.3.11f1`).
2. Construct the binary path: `/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity`.
3. If that exact version isn't installed, list installed versions from `/Applications/Unity/Hub/Editor/` and ask the user to install the pinned version (don't substitute — minor version mismatches can break tests).

### Step 2 — pick the test platform

- First argument (if provided): `EditMode` or `PlayMode`. Default to `EditMode` (faster, no Play mode entry).
- Second argument (optional): a filter — interpret as `-testFilter <value>` (regex match against test names) unless it starts with `@` in which case treat as `-testCategory <value-without-@>`.

### Step 3 — run

```bash
"/Applications/Unity/Hub/Editor/<version>/Unity.app/Contents/MacOS/Unity" \
  -runTests \
  -batchmode \
  -projectPath "$(pwd)" \
  -testPlatform <EditMode|PlayMode> \
  -testResults "$(pwd)/TestResults.xml" \
  -logFile - \
  [-testFilter <pattern>] [-testCategory <category>]
```

Notes:
- Do **not** add `-quit` — `-runTests` already exits when the run is complete.
- Do **not** add `-nographics` for PlayMode (some tests need a graphics context). It's fine for EditMode.
- Unity will refuse to run if the project is already open in another Editor — surface that error to the user.
- The run can take 30s–several minutes. Don't time out aggressively.

### Step 4 — parse and report

Read `TestResults.xml` and report:
- Total tests, passed, failed, skipped (from the `<test-run>` root element's attributes).
- For each failed test: the test name, the failure message, and the stack trace top line. Truncate stack traces to 5 lines max.
- Don't dump the full XML.

Format:

```
✓ 47 passed, ✗ 2 failed, ⊝ 1 skipped  (EditMode, 12.4s)

FAILED — CardIdTests.RoundTrip_Suit_Survives
  Expected: Hearts
  But was:  Spades
  at CardIdTests.cs:43

FAILED — SeatingTests.PartnerAcrossTable_FourPlayers
  Expected: 2
  But was:  3
  at SeatingTests.cs:18
```

If `TestResults.xml` doesn't exist after the run, surface the Unity log (last 50 lines) — there was likely a compile error or license issue.

### Don't

- Don't try to "fix" failing tests in the same skill invocation — report and stop. The user can ask for fixes next.
- Don't run both EditMode and PlayMode in one call. If the user wants both, run them sequentially in separate invocations.
- Don't delete or rename `TestResults.xml` — leave it for the user to inspect.
