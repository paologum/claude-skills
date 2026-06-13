# claude-skills

A Claude Code plugin: reusable skills (slash commands) and subagents.

See **README.md** for the full skill catalog, install instructions, and authoring guide.

## Structure

```
.claude-plugin/
├── plugin.json         # plugin manifest
└── marketplace.json    # makes this repo its own marketplace
skills/
└── <name>/SKILL.md     # one directory per skill
agents/
└── <name>.md           # one file per agent
```

## Working in this repo

- Skill files live in `skills/<name>/SKILL.md`. The `description` frontmatter field is the trigger for auto-invocation — write it with the natural phrases a user would say.
- Agents live in `agents/<name>.md` as single files.
- When adding a new skill or agent, also add a row to the catalog table in `README.md`.
- This repo doubles as its own marketplace (`.claude-plugin/marketplace.json`). When publishing a change, just push `main` — users pick it up with `/plugin marketplace update claude-skills` + `/reload-plugins`.
