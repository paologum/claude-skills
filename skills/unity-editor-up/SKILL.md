---
name: unity-editor-up
description: Brings up a usable Unity Editor for the current worktree without stalling the session — launches this worktree's own Editor (never touching other worktrees' Editors), waits for it in the background so the session is woken the moment MCP registers, and recovers on its own from compile errors and Safe Mode (fix → recompile over MCP, or restart only its own Editor). Use whenever a session needs the Editor and it isn't registered yet — "open Unity on this worktree", "wait for Unity", "it's importing", "it's in safe mode", "Unity has compile errors", "the Editor isn't showing up in MCP", or at the start of any Unity task in a fresh worktree.
allowed-tools: "Read Edit Bash Bash(python3 *) Bash(git *) Bash(gh *)"
argument-hint: "[worktree path — defaults to the repo root of the cwd]"
---

# Unity Editor up

Getting an Editor ready used to be the step where sessions stalled. They guessed an import time, ended the turn on a wakeup, and the user came back to type "it's up" or "it's in safe mode". This skill removes the guessing: a background wait wakes the session the moment there's something to act on.

## Exit condition

Return only when one of these is true:
- **Ready**: MCP routes to this worktree's Editor (`set_active_instance` done and `Application.dataPath` verified) and the console has no compile errors.
- **Blocked**: you hit an error you can't fix on this branch, such as a missing package or a license problem. State it in one line.

Waiting for an import is never a reason to end the turn or ask the user to check. Never ask the user whether Unity is up.

## Step 1 — start early

Launch the Editor **as soon as the worktree exists**, before reading the issue or writing code. A fresh worktree's first import takes minutes, so it should overlap the implementation work instead of following it.

Run the wait script with Bash **`run_in_background: true`**. Its path is this skill's base directory (printed above as "Base directory for this skill") plus `/unity_editor_up.py`:

```bash
python3 <skill-base-dir>/unity_editor_up.py --project "$(git rev-parse --show-toplevel)" --launch
```

The script:
- reuses this worktree's Editor if one is already running, or launches one with its log at `Logs/claude-editor.log`
- exits with one final line: `READY`, `READY_WITH_ERRORS`, `COMPILE_ERRORS`, `EXITED` or `TIMEOUT`

The harness re-invokes the session when it exits, so keep working until then. Don't call `ScheduleWakeup`, don't poll in a loop, and don't end the turn just to wait.

Other worktrees' Editors belong to other sessions. Never close, kill or "switch" them; `/unity-switch-worktree` closes the active Editor, so don't use it from a parallel session.

## Step 2 — act on the result

| Final line | Do |
|---|---|
| `READY <name>@<hash>` | `set_active_instance` with that exact id. Verify with `execute_code { return UnityEngine.Application.dataPath; }`. Continue the task. |
| `READY_WITH_ERRORS <id>` | Route to it as above, then fix the printed errors (Step 3) and recompile over MCP with `refresh_unity`, then `read_console` for errors. |
| `COMPILE_ERRORS` | This is Safe Mode: the Editor is parked at the Safe Mode prompt with an idle log, and MCP never came up. `-ignorecompilererrors` doesn't avoid this in Unity 6, so don't bother with it. Fix the printed errors (Step 3). Then restart **only this worktree's Editor**: `kill <pid>` using the pid on the final line, and run Step 1 again in the background. Safe Mode only recompiles when its window gets focus, and you don't drive OS input, so restarting is the reliable path. |
| `EXITED` | Read the log tail it printed (license, crash, a locked project). If another Editor already has this project open, attach to that one instead. Otherwise relaunch once. |
| `TIMEOUT` | Read the end of the log. If it's still importing (asset/script progress lines still moving), re-run Step 1. Otherwise report the last meaningful log line. |

## Step 3 — fixing compile errors

1. **Is it yours or the base branch's?** Run `git diff origin/<base> --stat`. If the erroring file isn't in your diff, the base branch is broken.
2. **Base branch broken:** before writing a fix, check whether one already exists:
   - `git log --all --oneline -S'<missing symbol>' -- <file>`
   - `gh pr list --search '<file name>'`

   Cherry-pick an existing fix as its own first commit, and say so in the PR body. If there's none, write the smallest fix as a separate commit and flag it: it should land on the base branch on its own.
3. **Your own code:** fix it, then let the recompile prove it.

## Guardrails

- Kill only the pid this skill launched or attached to for **this** worktree. Never `pkill Unity`/`killall Unity`.
- Never edit `.unity`/`.prefab` YAML to make errors go away. Scene changes go through MCP.
- Never drive the Editor with OS input (osascript, clicks, focus tricks) to trigger a refresh.
