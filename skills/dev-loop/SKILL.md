---
name: dev-loop
description: Runs a disciplined implementation loop that enforces good practice — Explore → Plan → Implement in small steps → Verify with a real check → Adversarial self-review → iterate until green → Commit → PR. Makes correctness measurable (tests/build/lint must pass) and shows evidence rather than asserting success. Use when the user asks to implement a task/issue properly, "do this the right way", run the full dev loop, ship a change with tests and review, or follow the plan-implement-verify workflow. Pairs with /start-task (isolation) upstream.
allowed-tools: "Read Edit Write Grep Glob Bash Bash(git *) Bash(gh *)"
argument-hint: "[task description or path to a plan/spec]"
---

## Context

**Where we are (must be a task branch, not the default branch):**
```
!`git branch --show-current 2>/dev/null; git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p'`
```

**Project check commands, if discoverable (tests / build / lint):**
```
!`ls package.json Makefile *.sln ProjectSettings/ProjectVersion.txt pyproject.toml 2>/dev/null; grep -oE '"(test|lint|build|typecheck)":' package.json 2>/dev/null | head`
```

## Your task

Take `$ARGUMENTS` (a task, issue, or a plan/spec file) from intent to a reviewed, verified, shippable change. The point is not speed — it is a **closed loop where correctness is measurable and proven**, not asserted. Follow the phases in order; do not skip verification or review.

### Phase 0 — guard the branch
If the current branch **is** the default branch, stop and tell the user to run `/start-task` first (or create a branch) — never implement directly on the default branch. If they insist, get explicit confirmation.

### Phase 1 — Explore (read before writing)
Understand the relevant code before changing it. Reference existing patterns in this repo rather than inventing new ones. For anything that spans many files, delegate the reading to a subagent (`use a subagent to investigate …`) so it doesn't flood the main context. Follow [[coding-principles]] — the `/coding-principles` skill — for what "good" looks like here.

### Phase 2 — Plan (unless the change is one sentence)
If the task is non-trivial or touches multiple files, produce a short plan: files to change, the approach, edge cases, and an **end-to-end verification step** that will prove it works. If scope is ambiguous, ask before coding — a precise goal up front beats corrections later. Skip the plan only for changes you could describe in a single diff (typo, log line, rename).

### Phase 3 — Implement in small steps
Make the smallest change that advances the plan, not a big multi-file rewrite (that is where quality collapses). Match the surrounding code's style and idioms. Keep the diff scoped to the task — do not refactor unrelated code.

### Phase 4 — Verify with a real check (the loop)
Identify the check that produces a pass/fail signal for this project and **run it**:
- Unity project → `/unity-test` (EditMode/PlayMode) and/or `/unity-build`.
- Node → the `test`/`lint`/`typecheck` scripts found above.
- Otherwise → the project's test suite, build, or a script that diffs output against a fixture; for UI, a screenshot compared to the target.

Run it, read the result, fix the **root cause** (never suppress the error), and re-run until it passes. **Show the evidence** — the command and its actual output — rather than saying "it works." If you can't verify it, say so; don't ship it.

### Phase 5 — Adversarial self-review
Once the check is green, get a second opinion from a fresh context so the author isn't the grader: run **`/code-review`** on the diff (it reviews in a fresh subagent and returns findings). Address findings that affect **correctness or the stated requirements**; treat pure style/speculative findings as optional — chasing every one leads to over-engineering. Re-verify (Phase 4) after any fix.

### Phase 6 — Commit & PR
When green and reviewed:
- Commit with a descriptive message scoped to this task. **Do not** add a `Co-Authored-By: Claude` trailer (project preference).
- Open a PR using **`/pr-description`** for the body. Confirm before pushing unless the user has already authorized it.

### Report
End with: the check you ran + its output (evidence), the review findings and how each was resolved, the files changed, and the PR link (or "ready to push, awaiting your OK").

### Guardrails
- Never mark work done on "looks done" alone — a check must have passed.
- Never implement on the default branch.
- Never expand scope beyond the task; surface follow-ups separately instead of doing them.
- Prefer running single/targeted tests over the whole suite for speed, but run the full check before declaring done.
