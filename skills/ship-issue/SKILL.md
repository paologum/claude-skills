---
name: ship-issue
description: Takes a GitHub issue all the way to a review-ready PR with proof — isolated worktree off the default branch, implementation, local tests, in-Editor/visual evidence (screenshots at every supported resolution, video or GIF for animations), a human-readable PR description, an adversarial self-review with fixes, then opens the PR and requests the reviewers. Encodes the standing "definition of done" so it doesn't have to be restated in every prompt. Use when the user says "work on issue #N", "let's start on this issue", "give me a draft PR with screenshots and videos", "create a PR for this issue", "/goal draft pr", or pastes an issue URL with "let's do this". Pass --stack-on <PR> to base the work on another PR's branch.
allowed-tools: "Read Edit Write Grep Glob Bash Bash(git *) Bash(gh *) Bash(gh api *) Skill Agent"
argument-hint: "<issue-url-or-number> [--stack-on <PR>] [--draft-only] [extra instructions]"
---

# Ship issue

The user's recurring `/goal` prompts all restate the same bar: *a PR with screenshots and videos proving the acceptance criteria, tests, prefabs not runtime UI, a description a human can read, self-reviewed, then request review — and don't come back until it's up.* This skill is that bar.

Invoking this skill authorizes: creating a worktree + branch, committing, pushing that branch, opening the PR, and requesting reviewers. It does **not** authorize merging.

## Exit condition

Do not end the turn until one of these holds, and say which:

1. The PR is open (ready for review, or draft if `--draft-only`), every acceptance criterion has evidence in the PR, the self-review findings are resolved, and reviewers are requested.
2. Blocked on a decision only the user can make. Ask it as one concrete question with your recommended answer — then keep working on everything that doesn't depend on it.

Transient tool failures (MCP reconnecting, Editor importing, a flaky network call) are not blockers: wait and retry.

## Step 1 — understand the issue

- `gh issue view <N> --json number,title,body,labels,comments` plus any parent/sibling issues or specs it links. Read the comments — scope is often refined there.
- Extract an explicit **acceptance-criteria checklist**. If the issue has none, write one from the body and post it as an issue comment so the scope is visible.
- Ask up front only about genuine design ambiguities (which of two layouts, a rule interpretation). Everything with a sensible default: pick it, note it in the PR.

## Step 2 — isolate

- Base = the default branch, or the head branch of `--stack-on <PR>`. `git fetch origin <base>`.
- If the session is already in a worktree on a fresh branch for this work, use it. Otherwise create one: branch `<issue-number>-<kebab-slug>` (≤ 6 words), worktree as a sibling of the repo root or via the session's worktree tool, based on `origin/<base>`. Never build on an unrelated branch's HEAD.
- Unity: make sure the MCP routes to **this** worktree's Editor (`/unity-switch-worktree`, or `set_active_instance` + verify `Application.dataPath`) before any Editor work.

## Step 3 — implement

Follow `/dev-loop` phases 1–4 and the repo's own rules (CLAUDE.md, memory). For Unity projects in particular:

- **Author UI in the Editor via the Unity MCP** (scene/prefab), not in C# builder code. New variants = a new prefab + palette/theme entry, not a hard-coded branch. Reuse existing prefabs and design tokens before making new ones.
- Drive the Editor through MCP tools only — no OS-level input, no hand-edited `.unity`/`.prefab` YAML.
- Add EditMode/PlayMode tests for the logic; a new test should fail on the old code.

## Step 4 — verify locally, with evidence

- Run the test suites locally (warm Editor via `/run-playmode` / `run_tests`, else `/unity-test`). Never push-and-wait on CI as the verification step.
- **Visual evidence** for anything a player can see — map each acceptance criterion to at least one artifact:
  - Screenshots via `/unity-e2e-verify` (drives real UI events, captures each state) or `/pr-screenshot`.
  - **Every supported resolution / aspect ratio** for layout work (at minimum 16:9 1920×1080, 16:10, 4:3, and an ultrawide), plus every player-count / mode variant the change touches.
  - Animations and multi-step flows: `/pr-video` (inline video, GIF fallback).
- **Inspect every capture** before using it: read each label for wrap, truncation, clipping, overlap, misalignment, wrong colors. Fix and re-capture; never ship a screenshot that shows a defect or predates the final code.
- Send each capture set to the user with `SendUserFile` as you produce it.

## Step 5 — PR description

Use `/pr-description`, then make sure the body:

- Leads with **Why** in plain language a non-author can follow; `Fixes #N`.
- Has an **acceptance-criteria table**: criterion → evidence (image/video/test name).
- Includes a Mermaid diagram when the change has a flow, state machine, or ordering worth seeing (`/mermaid-check` it).
- Embeds images large enough to read (full width, one per row with a caption — not tiny side-by-side thumbnails), uploaded the private-repo-safe way the screenshot skills use. Never commit screenshots to the repo.
- Lists deviations from the issue/spec and anything deferred to follow-up issues (file those issues now).

## Step 6 — adversarial self-review

- Push the branch and open the PR as a **draft**.
- Review it from a fresh context: `/pr-review <PR>` (or `/code-review`) in a subagent so the author isn't the grader.
- Fix every correctness / requirement finding in new commits; file issues for valid out-of-scope ones; re-run the local checks; re-capture any screen a fix touched. Repeat until the review is clean.

## Step 7 — open and request review

Unless `--draft-only`:

- `gh pr ready <N>`.
- Request reviewers: the CODEOWNERS owners of the changed paths minus yourself (`gh pr edit <N> --add-reviewer …`).
- Post nothing else — the description carries the evidence.

## Report

End with: PR link, the acceptance-criteria → evidence table, test results (command + counts), self-review findings and their resolutions, follow-up issues filed, and who was requested. Embed the key screenshots inline.

## Guardrails

- Never merge. Never force-push a branch someone has reviewed.
- Never mark a criterion met without an artifact or a test that shows it.
- Never expand scope silently — out-of-scope discoveries become issues linked in the PR.
- Respect the repo's commit conventions (e.g. no Claude co-author trailer where the project forbids it) and never write operator identifiers into commits, PRs, or issues.
