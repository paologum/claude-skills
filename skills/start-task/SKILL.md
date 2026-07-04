---
name: start-task
description: Starts a new unit of work in an isolated git worktree on a fresh branch off the default branch, so work never lands on the wrong branch. Given a GitHub issue number or a short description, it updates the base branch, creates ../<repo>-<slug> on branch <issue>-<slug>, pulls issue context via gh, and reports how to open a session there. Use when the user asks to start a task, start an issue, work on issue #N, spin up a worktree, start a new branch for a task, or "let's begin work on X".
allowed-tools: "Read Bash(git *) Bash(gh *) Bash(pwd) Bash(basename *) Bash(ls *) Glob"
argument-hint: "<issue-number | short description>"
disable-model-invocation: true
---

## Context

**Repo + current branch:**
```
!`git rev-parse --show-toplevel 2>/dev/null && git branch --show-current 2>/dev/null || echo "NOT A GIT REPO"`
```

**Default branch (base for the new branch):**
```
!`git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || echo "main"`
```

**Existing worktrees (avoid collisions):**
```
!`git worktree list 2>/dev/null`
```

**Uncommitted changes in the current tree (must not be dragged into the new task):**
```
!`git status --short 2>/dev/null | head -20`
```

## Your task

Create an isolated worktree + branch for `$ARGUMENTS` so the new work starts clean off the default branch — never on top of the current (possibly unrelated) branch. This directly prevents the "committed on the wrong branch" mistake.

### Step 1 — resolve the task

- If `$ARGUMENTS` is a **number** (or `#N`), treat it as a GitHub issue: run `gh issue view <N> --json number,title,body,labels` to get the title and details. Build the slug from the title.
- If it's **text**, use it directly as the description and slug source.
- **Slug rules:** lowercase, kebab-case, alphanumeric + hyphens, ≤ 6 words. Branch name = `<issue-number>-<slug>` when there's an issue (matches this project's convention, e.g. `99-organize-hand-into-sets`), otherwise just `<slug>`.

### Step 2 — pick the base and refresh it

- Base = the default branch from the context block (fall back to `main`).
- Fetch it fresh so the branch starts from the current tip: `git fetch origin <base>`.
- Do **not** switch the user's current working tree or branch. Everything happens in a new worktree.

### Step 3 — create the worktree off the base

- Location: a **sibling** of the repo root, `../<repo-name>-<slug>` (repo-name from `basename` of the toplevel). If that path exists, append `-2`, `-3`, etc.
- Create it in one step so the branch is based on the fetched base, not local state:

```bash
git worktree add -b <branch> ../<repo>-<slug> origin/<base>
```

- If the branch name already exists, either reuse it with `git worktree add ../<repo>-<slug> <branch>` (ask the user first) or pick a new slug.

### Step 4 — report and hand off

Print:
- The **worktree path** and **branch name**.
- The issue title/summary if there was one, plus a one-line restatement of the goal and what's out of scope (ask the user if scope is unclear — a precise goal up front beats corrections later).
- How to start working there: `cd <path>` then open a fresh Claude session (or, in Desktop, open that folder as a new session). A fresh session keeps context clean for implementation.
- Offer to continue into the implementation loop with **`/dev-loop`** once they're in the worktree.

### Guardrails

- **Never** create the branch on top of the current branch's HEAD when the current branch isn't the base — always base off `origin/<base>`.
- **Never** run `git reset --hard`, `git clean -f`, or delete existing worktrees/branches without explicit confirmation.
- If the repo has no `origin` or no default branch, base off local `main`/`master` and say so.
- Don't stash or move the user's uncommitted changes; the worktree is separate, so their current work is untouched.
