---
name: pr-description
description: Generates a concise PR description for the current branch using a Why / What / Tested / Demo template (Conventional Commits title, auto-linked issues, UI-aware demo section). Use whenever the user asks to write a PR description, draft a PR, open a pull request, create a PR, summarize a branch for review, or asks "what should this PR say".
allowed-tools: "Bash(git *) Bash(gh *) Read Grep Glob"
argument-hint: "[base-branch]"
---

## Branch context

**Current branch:**
```
!`git rev-parse --abbrev-ref HEAD`
```

**Base branch (defaults to origin/HEAD, override with $ARGUMENTS):**
```
!`git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo main`
```

**Commits on this branch:**
```
!`git log --oneline "$(git merge-base HEAD @{u} 2>/dev/null || git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD origin/master 2>/dev/null)"..HEAD 2>/dev/null | head -50`
```

**Files changed:**
```
!`git diff --name-status "$(git merge-base HEAD @{u} 2>/dev/null || git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD origin/master 2>/dev/null)"..HEAD 2>/dev/null | head -100`
```

**Diff stat:**
```
!`git diff --stat "$(git merge-base HEAD @{u} 2>/dev/null || git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD origin/master 2>/dev/null)"..HEAD 2>/dev/null | tail -30`
```

**Full diff (first 800 lines):**
```
!`git diff "$(git merge-base HEAD @{u} 2>/dev/null || git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD origin/master 2>/dev/null)"..HEAD 2>/dev/null | head -800`
```

## Your task

Generate a PR description for the changes above. Output a single fenced markdown block the user can copy directly into GitHub. Do not include extra commentary outside the block.

### Title

First line, outside the markdown block:

```
Title: <type>(<scope>): <imperative verb phrase>
```

- Use Conventional Commits: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `build`, `ci`.
- Lowercase, imperative ("add", not "added" or "adds"), no trailing period, ≤ 72 characters.
- Infer `<scope>` from the dominant changed directory; omit scope if changes are cross-cutting.

### Body template

Output this exact structure in a fenced ` ```markdown ` block. Keep the entire body under ~250 words.

```markdown
## Why?
<!-- 1-3 sentences on the motivation. What problem does this solve, or what does it enable? -->
<!-- If the branch name or commits reference an issue (e.g. fix-123, ENG-456), add: Fixes #N -->

## What?
<!-- High-level summary in prose — describe the *behavior change*, not the file list. -->
<!-- Call out non-obvious decisions or alternatives considered. -->
<!-- If this is a breaking change, add a "### Breaking change" subsection with the migration path. -->

## Tested
<!-- 3-4 short bullets. Phrase as reviewer-reproducible steps, not past-tense self-reports. -->
- 
- 
- 

## Demo
<!-- Only include this section if the change touches UI (*.tsx, *.jsx, *.vue, *.svelte, *.css, *.scss, templates, views). -->
<!-- Otherwise OMIT this whole section. -->

| Before | After |
| --- | --- |
| _drag screenshot here_ | _drag screenshot here_ |

<!-- For a video, replace the table with:
https://github.com/user-attachments/assets/REPLACE-ME
-->
```

### Rules

1. **Concise & high-level.** No file-by-file walkthroughs. The diff already shows that. Aim for behavior and intent.
2. **Tested bullets are imperative reviewer steps.** "Run `pnpm test settings`", "Open /dashboard and toggle dark mode" — not "I tested X".
3. **Auto-detect UI changes.** Look at the file list above. If no UI files were touched, **omit the entire Demo section.**
4. **Link issues.** Scan the branch name and commit messages for issue references (`#123`, `ABC-456`, `fix-123`). Add a `Fixes #N` line under **Why?** if found.
5. **Breaking changes.** If you spot removed exports, renamed public APIs, or schema changes that aren't backward-compatible, add a `### Breaking change` subsection under **What?** with a one-line migration note.
6. **Don't invent test steps.** If you can't tell from the diff what to test, leave the bullets as `- [describe step here]` placeholders for the author to fill in — better than fabricating.
7. **No emoji, no checkboxes, no "Type of change" tables.** Keep it lean.
