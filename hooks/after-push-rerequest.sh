#!/usr/bin/env bash
# PostToolUse Bash hook — after a successful `git push` to a branch whose open PR
# already has reviews from other people, remind the model to post a summary comment
# and re-request those reviewers. Users otherwise end up typing "rerequest X" and
# "did you rerequest?" after nearly every review round.
#
# Never blocks: any failure (no jq/gh, no PR, offline) exits 0 silently.

set -u

payload="$(cat)"
command -v jq >/dev/null 2>&1 || exit 0
command -v gh >/dev/null 2>&1 || exit 0

cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)"
printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+push([[:space:]]|$)' || exit 0
# A dry run or a rejected push isn't a new round.
printf '%s' "$cmd" | grep -Eq -- 'push[^;&|]*[[:space:]](--dry-run|-n)([[:space:]]|$)' && exit 0
printf '%s' "$payload" | jq -r '.tool_response | tostring' 2>/dev/null | grep -Eqi 'rejected|error:|fatal:' && exit 0

# macOS ships no `timeout`; fall back to running unbounded rather than never running.
t() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$@"; else shift; "$@"; fi; }

cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$cwd" ] && cd "$cwd" 2>/dev/null

pr_json="$(t 10 gh pr view --json number,state,isDraft,reviews,reviewRequests 2>/dev/null)" || exit 0
[ "$(printf '%s' "$pr_json" | jq -r '.state')" = "OPEN" ] || exit 0

me="$(t 5 gh api user --jq .login 2>/dev/null)"
reviewers="$(printf '%s' "$pr_json" | jq -r --arg me "$me" '
  [.reviews[].author.login | select(. != $me and (endswith("[bot]") | not))] | unique | join(", ")')"
[ -n "$reviewers" ] || exit 0

pending="$(printf '%s' "$pr_json" | jq -r '[.reviewRequests[].login] | join(", ")')"
num="$(printf '%s' "$pr_json" | jq -r '.number')"

msg="You just pushed to PR #${num}, which has been reviewed by: ${reviewers}."
if [ -n "$pending" ]; then
  msg="${msg} Review is currently requested from: ${pending}."
fi
msg="${msg} If this push addresses review feedback, finish the round before reporting done: post one PR comment mapping each review point to its fix (commit SHA) or follow-up issue, then re-request review (gh pr edit ${num} --add-reviewer <login>) from anyone not already requested. /claude-skills:address-review does the whole round."

jq -n --arg msg "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $msg}}'
exit 0
