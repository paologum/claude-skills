---
name: pr-review
description: Perform a principal-engineer / appsec-style pull request review on a GitHub PR — think like a bad actor, verify every claim end-to-end against the actual code (never speculate), consolidate findings into ONE ranked comment with file:line references and concrete failure scenarios, and post a verdict (approve / non-blocking / request-changes). On follow-up rounds, re-verify each prior finding against the author's fix commits before approving. Use whenever the user asks to review a PR, do a code review, do a security review of a PR, audit changes for issues, "look at this PR", "what do you think of this PR", pastes a `github.com/.../pull/N` URL, or says `/pr-review` / `/cr`. Also use when the user asks you to re-check an earlier PR review after the author has pushed fixes.
allowed-tools: "Bash(git *) Bash(gh *) Bash(gh api *) Bash(mkdir *) Bash(ls *) Bash(cat *) Bash(wc *) Bash(rm *) Read Write Edit Grep Glob"
argument-hint: "[PR-url-or-number]"
---

# PR Review

Drive a rigorous, appsec-flavored review of a GitHub pull request. The output is a single consolidated comment with a clear verdict — not a scatter of nitpicks, and never "hey, look into this". Every finding you post is one you have verified against the actual code.

## What this skill is for

- The user linked a PR (URL, `owner/repo#N`, or bare `#N` in the current repo's remote) and wants a review.
- The user wants you to be adversarial — think supply chain, credential exfil, injection, footguns that will bite in the *next* PR — not just spellcheck.
- The user wants a decision, not a survey. Approve / non-blocking / request-changes, always stated up front.

If the user just wants a quick informal pass ("what does this PR do?"), skip this skill and answer directly.

## Ground rules (non-negotiable)

- **Verify or don't post.** If you can't stand behind a finding as a real defect — with a concrete failure scenario a reader could reproduce — leave it out. The reviewer never has to "investigate" a claim you make; you already did.
- **Read the actual code, not just the diff.** Diffs lie by omission. Fetch the file at the PR's head SHA and confirm the surrounding context, imports, callers, and invariants. When in doubt, run `gh pr checkout` or `git show <sha>:<path>` and open the whole file.
- **One consolidated comment per round.** Don't spray line comments unless the user asks for inline. A ranked list in one comment is easier to triage and to respond to.
- **File:line references, always.** `path/to/file.py:42` in every finding.
- **Explain the failure, not the smell.** "This can OOM on a 10MB input because …" beats "consider adding bounds". Give a reproducer or the exact inputs that break it.
- **No pushing code, no rewriting the PR.** Post review comments and reviews only. Never `git push` to the PR branch, never `gh pr edit` its body, never `--force` anything.
- **Respect the user's project-wide preferences.** No operator identifiers in anything you write (IPs, hostnames, account paths). No Claude co-author trailer in commits. If a plugin skill for something more specific applies (e.g. `security-review` for local diffs, `/code-review ultra` for multi-agent cloud review), point it out and let the user pick.

## The lenses (run all four, in this order)

Every finding falls into one of these. If it doesn't, it probably isn't a finding worth posting.

1. **Bad actor.** Who can trigger this code path and what's the most damaging thing they can make happen?
   - Supply chain: unpinned third-party actions / packages / images / URLs, fetch-then-execute without checksum, dependencies that resolve at build time.
   - Injection via user-controlled inputs: PR titles, commit messages, git tags, branch names, workflow_dispatch inputs, form fields, filenames, headers. Anything that ends up in a shell, SQL, template, HTML, log grep, or eval.
   - Credential handling: are secrets ever echoed, logged, written to a file world-readable, passed in argv where `ps` sees them, or persisted longer than one job needs them?
   - Blast radius: irreversible operations (Steam upload, prod deploy, force-push, DB drop) gated only on things forgeable by a leaked PAT (tag push, comment webhook)? Missing approval gate?
   - Cross-tenant / cross-user: does the change let user A see or affect user B's data?
2. **Appsec.** Standard OWASP-shaped hazards: authn/authz, path traversal, SSRF, deserialization, XSS, log injection, TOCTOU, cryptographic misuse, secret in the wrong scope (`env` vs `vars`, workflow-level vs job-level permissions).
3. **Principal engineer.** Correctness under failure modes.
   - Latent bugs that aren't exercised today but ship with the PR (a different platform, a different config, a `#else` branch, a `try` that swallows too much).
   - Semantic footguns and sentinel values that will silently invert when a constant changes (the classic "designer sets Inspector to 480 to mean Spacewar, then the real AppID lands").
   - Coupling between two files that must move in lockstep and no test enforces it.
   - Error handling at the wrong altitude — catching `Exception` and logging a warning where a hard failure would surface a real problem sooner.
4. **Good practice.** Least privilege on tokens/permissions, pinning to immutable references (SHA not tag), fail-closed defaults, structured logging over regex-grepping human strings, tests that would actually fail if the change regressed.

## The workflow

### 1. Resolve the target

- Bare `#N` → assume the current directory's `origin` remote, resolve owner/repo via `gh repo view --json nameWithOwner`.
- Full URL → parse `github.com/<owner>/<repo>/pull/<N>`.
- `owner/repo#N` → use directly.

Then, in parallel:

```bash
gh pr view <N> --repo <owner>/<repo> --json title,body,author,baseRefName,headRefName,files,additions,deletions,state,url,headRefOid
gh pr diff <N> --repo <owner>/<repo>
```

If the diff is over ~1500 lines, save it to your scratchpad and read it in pages. Never review from a truncated view.

### 2. Read the actual code, not just the diff

For every file the PR touches that isn't a docs/config-only change, fetch the full file at the head SHA:

```bash
git fetch origin pull/<N>/head:pr<N> --force
git show pr<N>:<path/to/file>
```

This catches: renamed symbols the diff shows out of context, `using`/`import` changes that alter which overload is called, tests that reference private fields via reflection, `#if` branches the diff crops out.

### 3. Verify every claim before writing it

For each candidate finding, satisfy at least one of:

- **Reproducer.** Concrete inputs + expected wrong output. If you can't state it in one sentence, you don't understand the bug yet.
- **Code path.** Walk the call chain and cite each hop with `file:line`. If a step relies on an assumption ("`X` is always non-null here"), find where that's enforced or note that it isn't.
- **Reference.** For appsec / supply-chain claims, cite the primary source (GitHub hardening guide, RFC, vendor doc). Not a blog post.

If none of these hold, cut the finding. A short review of real defects beats a long review with speculation in it.

### 4. Draft the comment

Write it to your scratchpad first (`pr-review-<N>.md`). Structure:

```markdown
## Review — principal-engineer / appsec pass

<one-line framing: what's good, what the findings collectively suggest>

### 1. <short claim, not "consider" — state the defect>

`path/to/file.py` line N:

```<lang>
<the smallest self-contained snippet that shows the problem>
```

<one paragraph: what breaks, under what conditions, with what consequences. Reproducer inline where useful.>

<suggested fix, one sentence, only when there's a clean one>

### 2. …
```

- **Rank by severity.** #1 is what you'd want fixed before merge; the tail is defense-in-depth. Say which is which in the closing line ("#1 and #4 are the ones I'd want addressed before <thing that raises the stakes>").
- **Consolidate the trivia.** Naming, redundant globs, minor doc drift → one "Minor / defense-in-depth" bullet list at the end.
- **Don't post fixes as diffs** unless the user asked. Suggest the shape ("gate on a GitHub Environment with required reviewers"), not the exact YAML.

### 5. Decide the verdict

Before posting, pick one:

- **Request changes.** There is at least one finding that would break production, leak a secret, or ship a wrong answer to users. Post via `gh pr review --request-changes --body-file <path>`.
- **Approve, non-blocking.** Findings exist but none of them are load-bearing for correctness *now*; the author can address them in a follow-up or as separate PRs. Post via `gh pr review --approve --body-file <path>`. State this at the top: "**Verdict: approve, non-blocking.**"
- **Comment (no verdict).** First-round review where you want the author to respond before you commit to a decision. Post via `gh pr comment --body-file <path>`.

Never post an approval when a finding you're unsure of is still open. If in doubt, comment; ask; then decide.

### 6. Post

```bash
gh pr comment <N> --repo <owner>/<repo> --body-file <scratchpad>/pr-review-<N>.md
# or
gh pr review <N> --repo <owner>/<repo> --approve --body-file <path>
gh pr review <N> --repo <owner>/<repo> --request-changes --body-file <path>
```

Return the resulting comment/review URL to the user.

## Follow-up rounds (the author pushed fixes)

When the user comes back and says "they responded" / "check the fixes" / "do another pass":

1. **Fetch the current state of the PR** (`gh pr view <N> --comments --json comments,commits,reviewDecision`). Read the author's response — you need to know which of your findings they accepted, deferred, or pushed back on.
2. **Diff the new commits against the last-reviewed head.** `git log <old-head>..<new-head>` and `git diff <old-head>..<new-head>`.
3. **Re-verify every prior finding.** For each one:
   - **Fixed as suggested?** Confirm the fix landed in code, not just in a comment reply. Read the actual change.
   - **Fixed differently?** Understand why. If the author's reasoning is sound, say so and quote the tradeoff.
   - **Deferred / rejected?** If the author explains why and it holds up, accept it. If not, restate the concern with the new evidence.
4. **Look for regressions and new issues.** Fix commits often introduce new code paths. Run the four lenses over the delta.
5. **Post a follow-up comment with a verification table.**

```markdown
## Follow-up review — verdict: <approve, non-blocking | request-changes | approve>

<one-line framing: what changed, how the fixes hold up>

### Verification of the N findings

| # | Finding | Fix landed | Verified |
| - | - | - | - |
| 1 | <one-line summary> | <what the author did> | ✅ / ⚠️ / ❌ |
| 2 | … | … | … |

### <Any residual concerns, non-blocking, none new>

### <Anything the author resolved differently — quote their reasoning if it holds up>

**Approving.** / **Blocking on #X.**
```

Post via `gh pr review --approve` (or `--request-changes`) with this body — that way the verdict is a formal review, not just a comment, and shows up in `reviewDecision`.

## What NOT to do

- Do not paste the same finding in multiple places (one consolidated comment, not one comment per finding).
- Do not use language like "may want to consider" or "you might look into" — that's noise; state the defect or don't state it.
- Do not post checklists of things you *didn't* find. The comment lists real findings; anything else is padding.
- Do not open the PR in a browser to look at the CI status; use `gh pr checks` / `gh run view`.
- Do not push to the branch, edit the PR body/title, or close/reopen. Review comments and reviews only.
- Do not `gh pr merge`. That's the author's / a maintainer's call.
- Do not run destructive git operations against the local repo to inspect the PR (`git reset --hard`, `git checkout -f` over uncommitted work). Use `git fetch origin pull/<N>/head:pr<N>` and `git show pr<N>:<path>` — read-only.

## Handoff to more specific skills

If a repo ships a more specialized review skill for the change type, prefer invoking it:

- **`security-review`** — for a *local diff* (uncommitted or unmerged branch), not a GitHub PR.
- **`/code-review ultra <PR>`** — if the user wants the multi-agent cloud review, not a single-pass one. Only the user can trigger that; explain and stop.
- Repo-specific `/*review*` skills — check `.claude/skills/` in the target repo first.

## Reference: gh flags cheat sheet

- `gh pr view <N> --json <fields>` — metadata. Useful fields: `title,body,author,baseRefName,headRefName,headRefOid,files,additions,deletions,state,url,comments,reviewDecision,mergeable,commits`.
- `gh pr diff <N>` — the diff. Add `--patch` for patch format.
- `gh pr checkout <N>` — check the branch out locally (avoid unless you need to run it).
- `gh pr comment <N> --body-file <path>` — add a comment. No verdict.
- `gh pr review <N> --approve|--request-changes|--comment --body-file <path>` — formal review, moves `reviewDecision`.
- `gh api repos/<owner>/<repo>/pulls/<N>/comments` — inline (line-anchored) comments; use only if the user asks for inline.
- `gh pr checks <N>` — CI state.
