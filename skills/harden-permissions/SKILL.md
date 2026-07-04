---
name: harden-permissions
description: Applies a vetted permission deny/ask list to a Claude Code settings.json so destructive commands are hard-blocked and pushes always confirm, and recommends the right permission mode so safe piped/read-only commands stop prompting. Use when the user asks to harden permissions, stop being asked about piped commands, add a deny list, set up safe defaults, "stop asking about find/grep", block dangerous commands, or make Claude safe to run without a VM.
allowed-tools: "Read Edit Write Bash(cat *) Bash(ls *) Bash(git rev-parse *) Glob"
---

## Context

**User settings (shared by CLI + Desktop):**
```
!`cat ~/.claude/settings.json 2>/dev/null || echo "no user settings yet"`
```

**Project settings, if in a repo:**
```
!`cat .claude/settings.json 2>/dev/null || echo "no project settings"`
```

## Your task

Merge a vetted `deny` + `ask` permission block into the target `settings.json`, then tell the user which permission mode to select. This is the "safe to dev on your real machine without a VM" setup: destructive commands are hard-blocked, pushes always confirm, and everything else is governed by the mode.

### Step 1 — pick the target file

- **Default: user settings** `~/.claude/settings.json` — applies to every project, in both CLI and Desktop. Use this unless the user says otherwise.
- **Project settings** `.claude/settings.json` — only if the user wants the rules checked into and shared with a specific repo. Never put secrets or machine-specific absolute paths in a checked-in file.

Ask which one only if it's ambiguous; otherwise default to user settings and say so.

### Step 2 — merge these blocks

Read the existing file, preserve `allow` and every other key, and add/merge these. If `deny`/`ask` already exist, union the entries (don't drop the user's existing ones, don't duplicate).

```jsonc
"deny": [                          // hard block — irreversible or dangerous
  "Bash(rm -rf *)", "Bash(rm -fr *)", "Bash(sudo *)",
  "Bash(git push --force*)", "Bash(git push -f*)",
  "Bash(git reset --hard*)", "Bash(git clean -f*)",
  "Bash(chmod -R 777*)", "Bash(dd *)",
  "Read(./.env)", "Read(./.env.*)", "Read(**/.env*)", "Read(./secrets/**)"
],
"ask": [                           // always confirm, even in permissive modes
  "Bash(git push*)"
]
```

Rationale to keep in mind (and share if asked):
- `git push` is in **ask**, not deny, so it still works but always stops for a yes — force-push is separately hard-denied.
- `deny` and `ask` rules fire **even in Auto and Bypass modes**, so they're the durable guardrail regardless of mode.
- Secret-file `Read` denies stop prompt-injection or accidents from exfiltrating `.env`/secrets.

Write the merged JSON back. Validate it parses. Do not reformat or reorder unrelated keys.

### Step 3 — recommend the mode

Deny/ask rules stop the *dangerous* prompts; the **permission mode** decides how much of the *safe* stuff auto-approves. Explain the ladder and give one recommendation:

| Mode | Piped/read-only cmds (`find … \| head`) | Dangerous cmds | When |
| --- | --- | --- | --- |
| Ask (default) | asks every time | asks | too chatty |
| Auto accept edits (`acceptEdits`) | still asks | asks | only covers file edits + `mkdir`/`mv` |
| **Auto** (`auto`) | auto-approved | still asks | **recommended for a trusted, non-sandboxed machine** |
| Bypass (`bypassPermissions`) | auto-approved | auto-approved | only inside a sandboxed container/VM |

- **Recommend Auto mode** for a normal dev machine — it kills the piped-command nagging (a real, recurring pain) while the deny/ask block above keeps the guardrails on. Auto needs Opus 4.6+ / Sonnet 4.6+.
- Tell them where to set it: Desktop → mode selector next to the send button; CLI → `--permission-mode` or `permissions.defaultMode` in settings.
- Only mention Bypass if they explicitly want zero prompts, and repeat the docs caution: sandboxed VM/container only, since it removes all protection except the `ask`/deny rules.

### Step 4 — report

Print what changed: target file path, the count of deny/ask rules added vs. already present, and the one-line mode recommendation. Do not enable Bypass mode or edit anything outside the chosen settings file.
