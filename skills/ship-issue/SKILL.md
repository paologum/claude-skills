---
name: ship-issue
description: Takes a GitHub issue all the way to a review-ready PR with proof — isolated worktree off the default branch, implementation, local tests, in-Editor/visual evidence (screenshots at every supported resolution, video or GIF for animations), a human-readable PR description, an adversarial self-review with fixes, then opens the PR and requests the reviewers. Encodes the standing "definition of done" so it doesn't have to be restated in every prompt. Use when the user says "work on issue #N", "let's start on this issue", "give me a draft PR with screenshots and videos", "create a PR for this issue", "/goal draft pr", or pastes an issue URL with "let's do this". Pass --stack-on <PR> to base the work on another PR's branch.
allowed-tools: "Read Edit Write Grep Glob Bash Bash(git *) Bash(gh *) Bash(gh api *) Skill Agent"
argument-hint: "<issue-url-or-number> [--stack-on <PR>] [--draft-only] [extra instructions]"
---

# Ship issue

The user's recurring `/goal` prompts all restate the same bar: *a PR with screenshots and videos proving the acceptance criteria, tests, prefabs not runtime UI, a description a human can read, self-reviewed, then request review — and don't come back until it's up.* This skill is that bar.

**Authorization.** When the user typed `/ship-issue` or asked for the issue to be worked into a PR, that authorizes: creating a worktree + branch, committing, pushing that branch, opening the PR, posting the acceptance-criteria comment on the issue, filing follow-up issues, requesting reviewers, and turning on this session's PR monitor (Step 7) so it answers later review rounds itself. If you reached this skill on your own (a hook suggestion) from a prompt that didn't ask for a PR, confirm before the first push. Nothing here authorizes merging.

## Exit condition

Do not end the turn until one of these holds, and say which:

1. The PR is open (ready for review, or draft if `--draft-only`), every acceptance criterion has evidence in the PR, the self-review findings are resolved, and reviewers are requested.
2. Blocked on a decision only the user can make. Ask it as one concrete question with your recommended answer — then keep working on everything that doesn't depend on it.

Transient tool failures (MCP reconnecting, Editor importing, Safe Mode, a flaky network call) are not blockers. Handle them and keep going. Waiting for Unity is never a reason to end the turn or ask the user whether it's up: `/unity-editor-up`'s background wait wakes the session when there's something to act on. Don't end a turn on a `ScheduleWakeup` timer to wait for an import.

## Step 0 — claim the issue

Parallel threads and orchestrators draw from one issue pool, so the claim lives on GitHub, where every session and person can see it, and not in any session's memory.

1. **Check it's free.** Stop and report, without starting, if any of these holds:
   - the issue has the label `status:in-progress` or `blocked:decision`
   - it's assigned to someone other than you
   - an open PR fixes it (`gh pr list --state open --search "<N> in:body"`, then check the body says Fixes/Closes #N) or has a branch named `<N>-*` (`git ls-remote --heads origin '<N>-*'`)
   - another running session's title names `#<N>` (`mcp__ccd_session_mgmt__list_sessions`)
2. **Claim it** in one command: `gh issue edit <N> --add-label status:in-progress --add-assignee @me`. Create the label first if the repo doesn't have it. Do the same for each bundled issue the PR will fix.
3. **Blocked on the user** (exit condition 2): add `blocked:decision` to the issue and post the question as an issue comment, with the options and your recommendation, so decisions collect in one place. Remove the label once answered.
4. **Abandoning** (out of scope, duplicate, someone else took it): remove `status:in-progress` and your assignment.

A merged PR closes the issue, so the label needs no cleanup then.

## Step 1 — understand the issue

- `gh issue view <N> --json number,title,body,labels,comments` plus any parent/sibling issues or specs it links. Read the comments — scope is often refined there.
- Extract an explicit **acceptance-criteria checklist**. If the issue has none, write one from the body and post it as an issue comment so the scope is visible.
- Ask up front only about genuine design ambiguities (which of two layouts, a rule interpretation). Everything with a sensible default: pick it, note it in the PR.

## Step 2 — isolate

- **Stack when the work depends on an open PR. Prefer that over waiting or duplicating code.** Choose the base like this:
  - With `--stack-on <PR>`, use that PR's head branch.
  - Otherwise, check for an open, unmerged PR whose code this issue needs. Signs of that: the issue links or names the PR, its parent issue has that PR open, or the change has to call or modify code that exists only on that PR's branch (`gh pr list --author @me --state open --json number,headRefName,files`, compared against what you'll touch). If you find one, **stack on it** and say why in one line.
  - Otherwise, use the default branch.

  Stack on at most one parent; if the work needs two, stack on the one closer to merging and mention the other. `git fetch origin <base>`.
- **Stacking is safe here:** when the parent merges, GitHub retargets your PR to the default branch automatically, as long as the repo has "Automatically delete head branches" on and merges never use `--delete-branch` (see `/address-review` Step 8). Put `Stacked on #<parent>. Merge that first.` at the top of the PR body.
- If the session is already in a worktree on a fresh branch for this work, use it. Otherwise create one: branch `<issue-number>-<kebab-slug>` (≤ 6 words), worktree as a sibling of the repo root or via the session's worktree tool, based on `origin/<base>`. Never build on an unrelated branch's HEAD.
- Unity: **start this worktree's Editor now**, right after creating the worktree and before reading code or implementing, with `/unity-editor-up`. Its wait runs in the background, so the first import (minutes on a fresh `Library/`) overlaps steps 1–3 instead of blocking step 4. When it reports `COMPILE_ERRORS` or Safe Mode, follow that skill's recovery. If the base branch itself is broken, that skill says how to find or land the fix. Route MCP only to **this** worktree's instance (`set_active_instance` + verify `Application.dataPath`). Never close or switch another session's Editor.

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

- Push the branch and open the PR as a **draft**: `gh pr create --draft --base <base>` — with `--stack-on`, `<base>` is the parent PR's head branch, so the diff shows only this work. (On a non-default base, `Fixes #N` won't auto-close the issue; note that in the body.)
- Review it from a fresh context: `/pr-review <PR>` (or `/code-review`) in a subagent so the author isn't the grader.
- Fix every correctness / requirement finding in new commits; file issues for valid out-of-scope ones; re-run the local checks; re-capture any screen a fix touched. Repeat until the review is clean.

## Step 7 — open and request review

Unless `--draft-only`:

- `gh pr ready <N>`.
- **Review tier:** if the repo has `.github/review-policy.yml`, compute the tier from your diff (paths, network-attribute lines, size) and set the `review:human` or `review:ai` label. Request the policy's human approvers **only for `review:human`**. A `review:ai` PR is reviewed by the AI review workflow and merges on its verdict.
- Without a policy: request reviewers from the CODEOWNERS owners of the changed paths, minus yourself (`gh pr edit <N> --add-reviewer …`).
- Post nothing else — the description carries the evidence.

Then make **this session the PR's attached thread**, so review feedback comes back here and is acted on immediately (this applies to `--draft-only` too). Do it whenever the `mcp__ccd_pr__*` tools exist:

1. `mcp__ccd_pr__get_status`. If this session isn't bound to the PR you just opened, call `mcp__ccd_pr__bind_pr` with its URL.
2. `mcp__ccd_pr__set_monitor` with `url`, `auto_fix: true`, `address_comments: true` and `auto_archive_on_close: true`. The app then wakes this session with a `<ci-monitor-event>` on review comments, CI failures and merge conflicts, and archives the thread once the PR merges or closes. Each event is handled by `/address-review` (see its "Woken by the PR monitor" section).
3. **Link the thread from the PR.** Read this session's `link` with `mcp__ccd_session_mgmt__get_session` (`session_id: "self"`) and append one line at the end of the PR body: `Claude thread: <link>`. That lets you jump from the PR on GitHub to the thread that owns it. Skip this if `link` is absent; the organization has app links turned off.

## Step 8 — release the Editor

Unity: once the PR is up (this applies to `--draft-only` too) and every capture is done, stop this worktree's Editor with `/unity-editor-up` Step 4: save over MCP, then `--stop`. Idle Editors left open by finished sessions use up the licensing client's connection limit, and new Editors then fail with "Connection Lost". Skip this when you end on exit condition 2 (blocked on the user), since work resumes there. Later review rounds relaunch it with `/unity-editor-up`.

## Report

End with: PR link, the acceptance-criteria → evidence table, test results (command + counts), self-review findings and their resolutions, follow-up issues filed, who was requested, whether the PR monitor is on (or why not), and whether the Editor was stopped. Embed the key screenshots inline.

## Guardrails

- Never merge. Never force-push a branch someone has reviewed.
- Never mark a criterion met without an artifact or a test that shows it.
- Never expand scope silently — out-of-scope discoveries become issues linked in the PR.
- Respect the repo's commit conventions (e.g. no Claude co-author trailer where the project forbids it) and never write operator identifiers into commits, PRs, or issues.
