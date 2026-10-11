---
name: address-review
description: Closes the reviewer-feedback loop on an open PR in one call — gathers everything reviewers posted since your last round (review bodies, line threads, conversation comments), fixes each point in a NEW commit or files an issue for out-of-scope items, merges the base branch and resolves conflicts, runs the tests LOCALLY (never waits on CI), pushes, posts one reply comment mapping every point to its fix, and re-requests the reviewers. With --merge, also merges once the PR is approved and local tests pass. Use when the user says "address <reviewer>'s comments", "address the nits", "he has new comments", "requested changes, please address", "fix the merge conflicts and re-request", "approved, address nits and merge", "rebase and update the PR", or pastes a PR link with "comments to address".
allowed-tools: "Read Edit Write Grep Glob Bash Bash(git *) Bash(gh *) Bash(gh api *)"
argument-hint: "<PR-url-or-number> [--merge] [--no-rerequest]"
---

# Address review

One call replaces the loop the user otherwise types by hand every round: *"address the comments with a new commit and comment, merge main, run tests locally, push, re-request review (and merge if approved)."*

**Authorization.** When the user typed `/address-review`, or their message asks for the feedback to be addressed/fixed/pushed, that is authorization to commit and push to the PR's branch, post the reply comment, and re-request review. If you reached this skill on your own (e.g. a hook suggested it) and the user only *asked about* a review, do steps 1–3 and report the triage — don't commit, push, or post until they say go. Nothing here authorizes force-pushing, rewriting history, closing the PR, or merging without `--merge` (or an explicit "merge it").

## Exit condition

Do not end the turn until one of these is true, and say which:

1. Pushed, reply comment posted, reviewers re-requested (and merged, with `--merge` + approved).
2. Blocked on a real decision only the user can make (a design question, a reviewer point you disagree with, a test that fails on the base branch too). State the blocker in one line and what you'd do for each answer.

"Waiting for CI" is never a blocker — this skill verifies locally.

## Step 1 — resolve the PR and its worktree

- Parse `$ARGUMENTS`: full URL, `owner/repo#N`, or bare `N` (resolve via `gh repo view --json nameWithOwner`). Flags: `--merge`, `--no-rerequest`.
- `gh pr view <N> --json number,title,url,headRefName,baseRefName,headRefOid,isDraft,state,mergeable,reviewDecision,author`
- If `state` isn't `OPEN`, stop and say so.
- Find a checkout of `headRefName`: `git worktree list --porcelain`. Reuse it if it exists **and is clean**; otherwise create one off the remote branch (`git fetch origin <head> && git worktree add <sibling-path> <head>`). Never switch the user's current checkout to another branch, and never discard uncommitted work you find there.
- **Sync it with the remote PR branch** before touching anything — reviewers apply suggestions and "Update branch" from the web UI: `git fetch origin <head> && git merge --ff-only origin/<head>`. If that fails because the local branch has unpushed commits, merge `origin/<head>` normally; if it's genuinely diverged in a way you don't understand, stop and report rather than risk a force-push.

## Step 2 — collect what's new

Get the full review surface in one GraphQL call (review bodies matter: many reviewers post one consolidated review instead of line threads):

```bash
gh api graphql -F owner=<o> -F repo=<r> -F n=<N> -f query='
query($owner:String!,$repo:String!,$n:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$n){
  reviews(last:30){nodes{author{login} state submittedAt body url}}
  comments(last:50){nodes{author{login} createdAt body url}}
  reviewThreads(first:100){nodes{id isResolved isOutdated path line
    comments(first:20){nodes{author{login} body createdAt url}}}}
  commits(last:1){nodes{commit{committedDate}}}}}}'
```

- **Me** = `gh api user --jq .login`.
- **Cutoff** = the `createdAt` of my last reply comment from a previous review round (one that starts `Addressed review`, or otherwise maps review points to fixes). Everything from other people after it is new. If there is no such comment, **everything** is in scope. Don't use commit dates — a commit made before a review can be pushed after it, and an unrelated push doesn't answer a review.
- Always re-read the most recent `CHANGES_REQUESTED` review, even if it predates the cutoff: its points must be re-checked against the current head.
- Unresolved review threads count regardless of date.
- Bot reviewers (`[bot]` logins, review workflows) count as reviewers, but see "Disagreeing" below.

Turn this into a numbered checklist of **points**. Split a multi-item review body into one point per item; keep the reviewer's own numbering when they used one.

## Step 3 — triage every point

Each point gets exactly one disposition:

| Disposition | When | Action |
|---|---|---|
| **Fix** | In scope, you agree | Change the code in this PR |
| **Issue** | Valid but out of the PR's scope, or large | `gh issue create` with the reviewer's point, a link to the comment, and acceptance criteria. Link it in the reply |
| **Already done** | The current head already handles it | Cite the file:line or commit that does |
| **Disagree** | You've verified it's wrong or would regress something | Don't change code. Explain with evidence in the reply. If it's a human reviewer's blocking point, stop and surface it to the user before replying |
| **Question** | The reviewer asked something | Answer it directly in the reply |

Before marking a point "Fix", confirm the claim against the actual code — reviewers (human and AI) are sometimes wrong. A fix for a misread finding is churn.

For nits on an approved PR, default to **Fix** — they're cheap and the user usually wants them in.

## Step 4 — sync with the base branch

- `git fetch origin <base>`; if the PR is `CONFLICTING` or behind, **merge** `origin/<base>` into the branch (a merge commit keeps the push fast-forward; never rebase + force-push unless the user asks).
- Resolve conflicts by understanding both sides. If a conflict sits in code the base branch moved or replaced, port the PR's intent onto the new shape rather than resurrecting deleted code.
- Unity scene/prefab conflicts (`.unity`, `.prefab`, `.asset`): use UnityYAMLMerge (`/unity-smart-merge` sets it up) or re-apply the PR's change through the Unity MCP after taking the base side. Never hand-merge scene YAML.
- If the base branch itself is broken (doesn't compile / tests fail on base), say so — fix it in a separate first commit only if it's tiny and obviously required, and call it out in the reply.

## Step 5 — implement and verify locally

- Make the fixes. Match surrounding style; keep the diff to the review's scope.
- Run the project's real checks **locally** — never push-and-wait on CI:
  - Unity: `/run-playmode` / `mcp__UnityMCP__run_tests` against the warm Editor, else `/unity-test` batchmode. Run the classes the change touches, then the full EditMode suite.
  - Other stacks: the test/lint/build commands the repo defines.
- A test that fails identically on the base branch is pre-existing: note it, don't block on it.
- If a fix changes UI, re-capture the affected screens (`/pr-screenshot` or `/unity-e2e-verify`) — stale screenshots in a PR are worse than none.

## Step 6 — commit, push

- **New** commit(s) on top — never amend or force-push a branch under review. Message: `fix(<scope>): address review — <short summary>` or one commit per substantial point.
- Respect the repo's commit conventions (CLAUDE.md, memory) — e.g. some repos forbid a Claude co-author trailer.
- `git push` (plain, fast-forward).

## Step 7 — reply and re-request

Post **one** conversation comment (`gh pr comment <N> --body-file <file>`):

```markdown
Addressed review from @<reviewer> in <sha-short>[, <sha-short>].

| # | Point | Resolution |
|---|---|---|
| 1 | <reviewer's point, ≤ 12 words> | Fixed in `abc1234`: <what changed> |
| 2 | … | Filed #NNN (out of scope: <why>) |
| 3 | … | Already handled at `path/File.cs:42` |
| 4 | … | Not changed: <evidence> |

Merged `<base>` (resolved conflicts in `<files>`).
Local verification: <suite> <passed>/<total>[; pre-existing failure: <name>, fails on <base> too].
```

- For line threads you fixed, also reply in-thread with the commit SHA and resolve the thread, using the thread `id` from step 2:
  ```bash
  gh api graphql -f query='mutation($t:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$t,body:$b}){comment{url}}}' -F t=<thread-id> -F b='Fixed in abc1234.'
  gh api graphql -f query='mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}' -F t=<thread-id>
  ```
- **Re-request review** (unless `--no-rerequest`): every non-self, non-bot user who submitted a review on this PR; if nobody has, the CODEOWNERS owners for the changed paths minus yourself. `gh pr edit <N> --add-reviewer <login>[,<login>]` — this re-requests even after a prior review.
- If the PR is a draft and the user's request implies it's ready ("publish", "open it", "request review"), `gh pr ready <N>` first.

## Step 8 — merge (only with `--merge`)

Merge only when **all** hold — otherwise report which one failed and stop:

- `reviewDecision == APPROVED` (re-query after pushing; a new commit can dismiss stale approvals if the repo requires it).
- `mergeable == MERGEABLE` after your push. GitHub reports `UNKNOWN` for a few seconds while it recomputes — re-query (up to ~5 times, a few seconds apart) before treating it as a failure.
- Local verification in step 5 passed.

If the base branch requires status checks, don't wait on them and never bypass them: use `gh pr merge --auto` (merges when checks pass) and report that, or stop if auto-merge is disabled. **Never `--admin`.**

Merge method: the repo's allowed method from `gh repo view --json squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed`, preferring squash, then merge commit. `gh pr merge <N> --squash --delete-branch` (drop `--delete-branch` if a worktree still has the branch checked out; remove the worktree first only if it's clean and yours).

## Report

End with: the PR link, the point → resolution table (same as the comment), commits pushed, verification evidence (command + pass/fail counts), who was re-requested, and merge status. Keep it to that — no narration of the steps.

## Guardrails

- Never force-push, `--admin`-merge, amend pushed commits, or rewrite the PR description's author-written sections without being asked.
- Never mark a point fixed without a passing local check that would catch its regression.
- Never reply defensively to an AI reviewer that's wrong — record "Not changed: <evidence>" and move on; if the user has asked to be consulted on wrong AI findings, stop and report instead.
- Never write operator identifiers (IPs, hostnames, personal paths) into commits or comments.
