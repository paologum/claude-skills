# claude-skills

A personal collection of [Claude Code](https://claude.com/claude-code) skills and subagents, packaged as an installable plugin.

## What's in here

| Type | Name | What it does |
|------|------|--------------|
| Skill | `/pr-description` | Generates a concise PR description for the current branch (Why / What / Tested / Demo). Auto-triggers when you ask Claude to draft / write / open a PR. |
| Skill | `/unity-local-multiplayer` | Sets up Unity Multiplayer Play Mode (MPPM) in the current project for up to 4 local virtual players. Adds the package, writes a Player-Tag-aware bootstrap that auto-starts Host vs Client (Mirror or Netcode), documents the Editor steps. |
| Skill | `/unity-test` | Runs Unity Test Framework tests (EditMode/PlayMode) via batch CLI. Auto-detects Unity version, parses NUnit XML, reports pass/fail with failure details. |
| Skill | `/unity-build` | Builds the Unity project for Windows / Mac / WebGL / iOS / Android / Linux. Creates `Assets/Editor/BuildScript.cs` if missing. |
| Skill | `/unity-new-project` | Scaffolds a new empty Unity project, patches `Packages/manifest.json` with URP/HDRP/2D + Input System + Test Framework, writes a Unity `.gitignore`. |

## Install

Inside any Claude Code session, run:

```
/plugin marketplace add paologum/claude-skills
/plugin install claude-skills@claude-skills
/reload-plugins
```

That's it. Plugins persist across new sessions on the same machine.

To update later:

```
/plugin marketplace update claude-skills
/reload-plugins
```

## How to use

Skills are auto-invoked when Claude recognizes your request — no slash needed:

> *"Write a PR description for this branch"* → auto-triggers `/pr-description`

Or invoke manually:

```
/pr-description           # uses the default base branch
/pr-description develop   # against a specific base branch
```

---

## Adding a new skill

### 1. Create the file

```
skills/<your-skill-name>/SKILL.md
```

The directory name becomes the slash command (`/your-skill-name`).

### 2. Write the frontmatter

```yaml
---
name: your-skill-name
description: One sentence on what it does + when Claude should auto-invoke it. Include phrases the user would naturally say.
allowed-tools: "Read Bash(git *) Grep"
argument-hint: "[optional-arg]"
---
```

**The `description` is the single most important field.** It's how Claude decides whether to auto-invoke. Write it so it includes the natural trigger phrases — e.g., "Use when the user asks to X, Y, or Z."

Common frontmatter fields:

| Field | Purpose |
|-------|---------|
| `name` | Defaults to directory name. |
| `description` | When Claude should use this skill. Required for auto-invocation. |
| `allowed-tools` | Pre-approves tools — `"Read Bash(git *) Grep"` etc. |
| `argument-hint` | Autocomplete hint shown in the `/` menu. |
| `model` | `sonnet`, `opus`, `haiku`, or `inherit`. |
| `disable-model-invocation` | `true` = manual-only (no auto-trigger). |

### 3. Write the body

The markdown below the frontmatter is the instructions Claude follows when the skill runs.

Use the `` !`shell command` `` syntax to inject live context that runs *before* Claude sees the skill:

```markdown
## Current diff

!`git diff HEAD`

## Task

Summarize the diff above...
```

See [`skills/pr-description/SKILL.md`](skills/pr-description/SKILL.md) for a complete example.

### 4. Test it locally

Without committing, you can test against a live session:

```bash
claude --plugin-dir /Users/paologum/github
```

This loads your in-progress changes for that one session. Edit `SKILL.md`, then in the session run `/reload-plugins` to pick up changes.

### 5. Commit and push

```bash
git add skills/<your-skill-name>
git commit -m "Add /<your-skill-name> skill"
git push
```

Anyone with the plugin installed will get it after running `/plugin marketplace update claude-skills` + `/reload-plugins`.

---

## Adding a new agent

Agents are subagents Claude delegates to via the `Agent` tool — useful for parallel work, isolated context, or specialized behavior.

### 1. Create the file

```
agents/<your-agent-name>.md
```

(Single file, not a directory.)

### 2. Write the frontmatter

```yaml
---
name: your-agent-name
description: When Claude should delegate to this agent.
tools: Read, Grep, Glob, Bash
model: sonnet
---
```

Common fields:

| Field | Purpose |
|-------|---------|
| `name` | Required. Lowercase, hyphens. |
| `description` | Required. When Claude should delegate. |
| `tools` | Allowed tools. Omit to inherit all. |
| `model` | `sonnet`, `opus`, `haiku`, `inherit`. |
| `permissionMode` | `default`, `acceptEdits`, `plan`, etc. |

### 3. Write the system prompt

The markdown body is the agent's system prompt. Be explicit about behavior, output format, and constraints.

### 4. Document, commit, push

Add a row to the table at the top of this README, then commit and push.

---

## Publishing changes

1. Make your edit.
2. `git commit` + `git push`.
3. Users run `/plugin marketplace update claude-skills` then `/reload-plugins`.

No version bump or release process needed — the marketplace pulls the latest commit on `main`.

For a versioned release, bump `version` in `.claude-plugin/plugin.json` and tag the commit.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Skill doesn't auto-trigger | Rephrase the request to match the `description`. If it still doesn't trigger, broaden the description with more trigger phrases. |
| Edits to a `SKILL.md` not taking effect | Run `/reload-plugins`. New skill *directories* may require a session restart. |
| `/plugin install` says "not found" | Run `/plugin marketplace update claude-skills` first to refresh the catalog. |
| Skill runs but a tool is blocked | Add it to `allowed-tools` in the frontmatter. |

---

## Repo layout

```
.claude-plugin/
├── plugin.json         # plugin manifest
└── marketplace.json    # makes this repo its own marketplace
skills/
└── <name>/SKILL.md     # one directory per skill
agents/
└── <name>.md           # one file per agent
CLAUDE.md               # context for Claude when working in this repo
README.md               # this file
```
