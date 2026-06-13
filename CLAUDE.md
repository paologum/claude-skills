# paologum-skills

A Claude Code plugin: reusable skills (slash commands) and subagents.

## Structure

```
.claude-plugin/
└── plugin.json      # manifest
skills/              # /skill-name commands (and auto-invoked by description)
└── <name>/
    └── SKILL.md
agents/              # subagents delegated to via the Agent tool
└── <name>.md
```

## Skills

| Command | Description |
|---------|-------------|
| `/pr-description` | Generate a concise PR description for the current branch (Why / What / Tested / Demo). Auto-triggers when you ask to draft a PR, write a PR description, or open a pull request. |

## Agents

| Name | Description |
|------|-------------|
| *(none yet)* | |

## Install

**Local development (this machine, any project):**

```bash
claude --plugin-dir /Users/paologum/github
```

**From a marketplace repo (other machines):**

```bash
# inside Claude Code
/plugin marketplace add paologum/<marketplace-repo>
/plugin install paologum-skills@<marketplace-name>
/reload-plugins
```

The marketplace repo is a separate repo containing `.claude-plugin/marketplace.json` that points at this plugin. Not set up yet — for now, use `--plugin-dir` or clone this repo into `~/.claude/plugins/`.

## Adding a skill

Create `skills/<name>/SKILL.md`:

```yaml
---
name: <name>
description: <when Claude should auto-invoke — include natural trigger phrases>
allowed-tools: "Read Bash"
---

## Instructions
...
```

The `description` is what makes Claude auto-invoke the skill. Include the phrases a user would naturally say.

## Adding an agent

Create `agents/<name>.md`:

```yaml
---
name: <name>
description: <when Claude should delegate>
tools: Read, Grep, Bash
model: sonnet
---

System prompt...
```
