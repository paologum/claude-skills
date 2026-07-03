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

**Lockfiles / build manifests present (for ecosystem-aware test commands):**
```
!`ls -1 pnpm-lock.yaml package-lock.json yarn.lock bun.lockb requirements.txt pyproject.toml Cargo.toml go.mod Gemfile.lock composer.lock pubspec.yaml mix.exs build.gradle pom.xml 2>/dev/null | head -10`
```

**CODEOWNERS (for reviewer suggestion):**
```
!`cat .github/CODEOWNERS CODEOWNERS docs/CODEOWNERS 2>/dev/null | head -50`
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
2. **Tested bullets are imperative reviewer steps and ecosystem-aware.** Look at the lockfiles block above and pick a real command — `pnpm test`, `npm test`, `pytest`, `cargo test`, `go test ./...`, `dotnet test`, etc. Add a path / filter when you can ("Run `pnpm test settings`", "Open `/dashboard` and toggle dark mode"). Never "I tested X."
3. **Auto-detect UI changes.** If no files matching `*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, `*.scss`, `*.html`, `views/**`, `templates/**`, `*.uxml`, `*.uss`, `*.unity` (UI prefabs), or `Assets/**/*.prefab` were touched, **omit the Demo section entirely.**
4. **Link issues.** Scan the branch name and commit messages for `#123`, `ABC-456`, `fix-123`. Add a `Fixes #N` line under **Why?** if found.
5. **Breaking-change detection is explicit.** Scan the diff for: removed public exports, renamed public APIs, changed method signatures on public types, removed CLI flags, changed config keys, removed/renamed DB columns or migration files, removed REST endpoints, or `package.json`/`Cargo.toml`/etc. major-version bumps to dependencies. **Always emit one of:**
   - A `### Breaking changes` subsection under **What?** with a one-line migration note per change, OR
   - A single line at the bottom of **What?**: `No breaking changes.`
6. **Risk callouts from sensitive paths.** If the changed files include any of these, add a short `### Heads up` block to **What?** listing what's touched:
   - `**/auth/**`, `**/security/**`, `**/secrets/**`
   - `**/migrations/**`, `*.sql`, schema files
   - `.github/workflows/**`, `Dockerfile*`, deploy scripts, `infra/**`, `terraform/**`
   - `**/package*.json`, `**/manifest.json`, lockfiles (dep changes)
   - `**/CODEOWNERS`, `**/.gitignore`, `**/CLAUDE.md`
   Keep each callout to one line. Skip the block entirely if none apply.
7. **Suggested reviewers from CODEOWNERS.** If a CODEOWNERS file is present, intersect its globs with the changed files and append a `### Suggested reviewers` line at the very bottom of the body (after Demo): `@owner1 @owner2` (deduped, max 4). Skip if no file or no matches.
8. **Don't invent test steps.** If you can't tell from the diff what to test, leave the bullets as `- [describe step here]` placeholders. Better than fabricating.
9. **No emoji, no checkboxes, no "Type of change" tables.** Keep it lean.

### Self-review gate

Before emitting, verify silently:

- Title matches `<type>(<scope>)?: <imperative phrase>`, ≤ 72 chars, no trailing period.
- **Demo** section is present iff UI files were touched.
- Either a `### Breaking changes` block exists, OR the line `No breaking changes.` is present.
- Tested bullets contain a real command from the detected ecosystem, not "I tested" / "verified manually" / vague prose.
- No file-by-file narration in **What?**.
- Body is ≤ ~250 words (excluding the CODEOWNERS reviewer line).

If any check fails, fix and re-emit. Never ship a description that fails the gate.
